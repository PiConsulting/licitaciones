from __future__ import annotations

import json
from functools import lru_cache
from time import sleep
from uuid import UUID

import structlog
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient

from extraction.errors import TransientExtractionError
from extraction.ports.search_client_port import SearchClientPort
from shared.config import get_settings
from shared.security import sanitize_error_message

logger = structlog.get_logger(__name__)

# Tope de vueltas de borrado. Cada vuelta saca hasta 500 documentos, así que
# esto cubre 50.000 chunks -- muy por encima de cualquier análisis real. Es un
# corte de seguridad contra la consistencia eventual del índice, no un límite
# de capacidad.
_MAX_DELETE_ROUNDS = 100


class AzureSearchAdapter(SearchClientPort):
    def __init__(self, endpoint: str, key: str, index_name: str) -> None:
        self._endpoint = endpoint
        self._key = key
        self._index_name = index_name
        self._cached_index_fields: set[str] | None = None

    def _index_field_names(self) -> set[str]:
        if self._cached_index_fields is not None:
            return self._cached_index_fields

        client = SearchIndexClient(
            endpoint=self._endpoint,
            credential=AzureKeyCredential(self._key),
        )
        index = client.get_index(self._index_name)
        self._cached_index_fields = {field.name for field in index.fields}
        return self._cached_index_fields

    def _to_index_document(self, document: dict) -> dict:
        allowed = self._index_field_names()
        # FIX (auditoría 2026-08-12, hallazgo US-4.2): antes se descartaban en
        # silencio los campos que el índice real no declaraba -- si el schema
        # de Azure quedaba desactualizado respecto al código (como pasó con
        # primary_category/secondary_categories), los datos se perdían sin
        # ningún rastro en los logs. Este warning hace visible el drift.
        discarded = sorted(key for key in document if key not in allowed)
        if discarded:
            logger.warning(
                "search_index_document_fields_discarded",
                discarded_fields=discarded,
                reason="campos no declarados en el schema real del índice de Azure AI Search",
            )
        return {key: value for key, value in document.items() if key in allowed}

    def upload_chunks(self, documents: list[dict]) -> None:
        from azure.search.documents import SearchClient

        client = SearchClient(
            endpoint=self._endpoint,
            index_name=self._index_name,
            credential=AzureKeyCredential(self._key),
        )
        result = client.upload_documents(documents=[self._to_index_document(document) for document in documents])
        failed = [item for item in result if not item.succeeded]
        if failed:
            raise TransientExtractionError(f"Fallaron {len(failed)} documentos en upload")

    def delete_analysis_chunks(self, analysis_id: str) -> int:
        from azure.search.documents import SearchClient

        client = SearchClient(
            endpoint=self._endpoint,
            index_name=self._index_name,
            credential=AzureKeyCredential(self._key),
        )
        escaped_analysis_id = analysis_id.replace("'", "''")
        filter_expr = f"analysis_id eq '{escaped_analysis_id}'"

        # FIX (auditoría 2026-08-13, hallazgo IDX-05): esto era un `while True`
        # sin corte. Azure AI Search es de consistencia eventual, así que un
        # documento ya borrado puede seguir apareciendo en la búsqueda durante
        # unos segundos, y `delete_documents` sobre un id inexistente devuelve
        # éxito -- el bucle no tenía forma de distinguir "quedan documentos" de
        # "el índice todavía no se actualizó". Importa más ahora que IDX-03
        # hace que esto corra en CADA análisis y no sólo en el borrado duro.
        deleted: set[str] = set()
        for _round in range(_MAX_DELETE_ROUNDS):
            found = [
                doc_id
                for doc in client.search(search_text="*", top=500, select=["id"], filter=filter_expr)
                if (doc_id := doc.get("id"))
            ]
            if not found:
                break

            pending = [doc_id for doc_id in found if doc_id not in deleted]
            if not pending:
                # Todo lo que devuelve la búsqueda ya se borró: es el índice
                # poniéndose al día, no documentos que falten. Reintentar no
                # aporta nada.
                logger.info(
                    "search_delete_index_still_catching_up",
                    analysis_id=analysis_id,
                    deleted_chunks=len(deleted),
                )
                break

            client.delete_documents(documents=[{"id": doc_id} for doc_id in pending])
            deleted.update(pending)
            # Rate limiting: 100ms entre batches previene exceder límites de Azure Search
            # con análisis muy grandes (50k+ chunks = 100+ batches)
            sleep(0.1)
        else:
            logger.error(
                "search_delete_max_rounds_reached",
                analysis_id=analysis_id,
                max_rounds=_MAX_DELETE_ROUNDS,
                deleted_chunks=len(deleted),
                impact="pueden quedar chunks del análisis en el índice",
            )

        return len(deleted)


# Campos de texto cuyo contenido tiene que ser alcanzable por BM25. `content`
# se indexa SIN el encabezado (ver `upload_chunks`), así que si los tres campos
# de encabezado no son buscables el texto del título no existe para la mitad
# léxica de la búsqueda híbrida (hallazgo IDX-01, auditoría 2026-08-13).
_REQUIRED_SEARCHABLE_TEXT_FIELDS = ("content", "title", "section_path", "heading_path")

# Analizadores que lematizan y normalizan acentos en castellano. Sin uno de
# estos, Azure usa `standard.lucene`: "garantia" no matchea "garantía" y
# "plazos" no matchea "plazo" (hallazgo IDX-02).
_ACCEPTED_SPANISH_ANALYZERS = {"es.microsoft", "es.lucene"}


def _assert_index_contract(index, expected_dimensions: int) -> None:
    fields = {field.name: field for field in index.fields}
    required_fields = {
        "analysis_id",
        "content",
        "document_id",
        "page_number",
        "chunk_index",
        "embedding",
        # FIX (auditoría 2026-08-12, hallazgo US-4.2): estos dos campos son
        # justamente los que en el incidente histórico documentado en
        # upload_chunks() quedaron fuera del índice real -- daban null para
        # el 100% de los chunks y el filtro por categoría del retrieval
        # nunca matcheaba, sin que nada fallara ruidosamente. Incluirlos acá
        # hace que ese drift de schema tumbe el arranque en vez de degradar
        # silenciosamente el retrieval en producción.
        "primary_category",
        "secondary_categories",
        # FIX (auditoría 2026-08-13, hallazgo IDX-06): exactamente el mismo
        # incidente volvió a pasar con parent/child. Estos tres campos nunca
        # se agregaron al índice real, así que `_to_index_document` los
        # descartaba en CADA subida y toda la US-3.1 quedó inerte: el
        # retrieval veía todo como "normal", `_expand_children_to_parents` no
        # hacía nada, y parent y children convivían en el índice como
        # documentos independientes con el mismo texto. El contrato anterior
        # no los pedía, así que el arranque pasaba limpio.
        "chunk_type",
        "parent_chunk_id",
        "child_chunk_ids",
    }
    missing_fields = sorted(name for name in required_fields if name not in fields)
    if missing_fields:
        raise RuntimeError(
            "Índice de AI Search incompleto. Campos faltantes: "
            + ", ".join(missing_fields)
            + ". Recrear con: python scripts/create_search_index.py"
        )

    if not bool(getattr(fields["analysis_id"], "filterable", False)):
        raise RuntimeError("Campo analysis_id debe ser filterable en AI Search")

    # IDX-01: los encabezados tienen que ser buscables.
    not_searchable = sorted(
        name
        for name in _REQUIRED_SEARCHABLE_TEXT_FIELDS
        if name in fields and not bool(getattr(fields[name], "searchable", False))
    )
    if not_searchable:
        raise RuntimeError(
            "Campos de texto que deben ser searchable en AI Search: "
            + ", ".join(not_searchable)
            + ". Sin esto BM25 no puede matchear el texto de los encabezados. "
            "Recrear con: python scripts/create_search_index.py"
        )

    # IDX-02: y con un analizador que entienda castellano.
    #
    # `analyzer_name` llega como string cuando el índice viene del servicio
    # (`get_index`), pero como enum `LexicalAnalyzerName` cuando el objeto se
    # armó localmente (p.ej. `scripts/create_search_index.py`). `str()` sobre
    # el enum da "LexicalAnalyzerName.ES_MICROSOFT", no "es.microsoft", así
    # que hay que normalizar por `.value` antes de comparar -- si no, el
    # contrato rechaza un índice que él mismo produjo.
    def _analyzer_of(field) -> str:
        raw = getattr(field, "analyzer_name", None)
        if raw is None:
            return ""
        return str(getattr(raw, "value", raw))

    wrong_analyzer = sorted(
        f"{name}={_analyzer_of(fields[name]) or 'null (standard.lucene)'}"
        for name in _REQUIRED_SEARCHABLE_TEXT_FIELDS
        if name in fields and _analyzer_of(fields[name]) not in _ACCEPTED_SPANISH_ANALYZERS
    )
    if wrong_analyzer:
        raise RuntimeError(
            "Campos sin analizador español en AI Search: "
            + ", ".join(wrong_analyzer)
            + f". Aceptados: {', '.join(sorted(_ACCEPTED_SPANISH_ANALYZERS))}. "
            "Sin stemming ni normalización de acentos, BM25 aporta muy poco a la "
            "búsqueda híbrida en castellano. Recrear con: python scripts/create_search_index.py"
        )

    vector_dimensions = getattr(fields["embedding"], "vector_search_dimensions", None)
    if int(vector_dimensions or 0) != expected_dimensions:
        raise RuntimeError(
            "Campo embedding incompatible. "
            f"Esperado dimensions={expected_dimensions}, recibido={vector_dimensions}"
        )


@lru_cache(maxsize=1)
def _validate_index_contract_cached(index_key: str) -> bool:
    settings = get_settings()
    client = SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=AzureKeyCredential(settings.azure_search_key),
    )
    index = client.get_index(settings.azure_search_index_name)
    _assert_index_contract(index, expected_dimensions=settings.azure_search_embedding_dimensions)
    return True


def validate_index_contract() -> None:
    settings = get_settings()
    index_key = f"{settings.azure_search_endpoint}:{settings.azure_search_index_name}:{settings.azure_search_embedding_dimensions}"
    _validate_index_contract_cached(index_key)


def _build_adapter() -> SearchClientPort:
    settings = get_settings()
    return AzureSearchAdapter(
        endpoint=settings.azure_search_endpoint,
        key=settings.azure_search_key,
        index_name=settings.azure_search_index_name,
    )


def upload_chunks(chunks_with_embeddings: list[dict], analysis_id: str | UUID, correlation_id: str | UUID) -> None:
    settings = get_settings()
    if settings.is_production:
        validate_index_contract()
    adapter = _build_adapter()

    logger.info(
        "search_upload_started",
        correlation_id=str(correlation_id),
        analysis_id=str(analysis_id),
        total_chunks=len(chunks_with_embeddings),
    )

    # FIX (auditoría 2026-08-13, hallazgo IDX-03): borrar los chunks previos de
    # este análisis ANTES de subir los nuevos.
    #
    # `upload_documents` es un UPSERT y el id es
    # `{analysis_id}--{document_id}--{chunk_index}`, así que un re-análisis que
    # produzca MENOS chunks que el anterior pisaba los primeros y dejaba vivos
    # los sobrantes. El índice quedaba con dos chunkings distintos del mismo
    # documento mezclados bajo el mismo `analysis_id`, y el retrieval devolvía
    # fragmentos que ya no correspondían al texto actual.
    #
    # No es hipotético: `start_analysis` permite reintentar un análisis en
    # estado `error`, y cualquier cambio de chunking (los de esta misma
    # auditoría, sin ir más lejos) cambia la cantidad de chunks.
    removed = adapter.delete_analysis_chunks(str(analysis_id)) or 0
    if removed:
        logger.info(
            "search_stale_chunks_removed",
            correlation_id=str(correlation_id),
            analysis_id=str(analysis_id),
            removed_chunks=removed,
            reason="re-indexación: se limpia el estado previo para no mezclar dos chunkings",
        )

    documents: list[dict] = []
    for chunk in chunks_with_embeddings:
        # Validar que chunk tiene embedding antes de construir documento
        if "embedding" not in chunk:
            raise ValueError(
                f"Chunk missing 'embedding' field: document_id={chunk.get('document_id')}, "
                f"chunk_index={chunk.get('chunk_index')}"
            )
        
        # Usar '--' como separador (permitido por Azure Search, menos ambiguo que '_')
        chunk_id = f"{analysis_id}--{chunk['document_id']}--{chunk['chunk_index']}"
        table_ref = chunk.get("table_ref")
        source = chunk.get("source")  # RAG PHASE 3: Metadata estructurada para highlighting

        # PARENT/CHILD CHUNKING (US-3.1): `create_chunks` sólo conoce
        # `chunk_index` (entero, único dentro del documento) -- el `analysis_id`
        # recién se conoce acá. Por eso `parent_chunk_index`/`child_chunk_indices`
        # (índices enteros) se traducen a los mismos ids compuestos
        # `{analysis_id}--{document_id}--{chunk_index}` que ya se usan como id
        # de documento, para que la expansión children→parent en retrieval
        # pueda resolverlos con un simple `get_document(key=...)`.
        parent_chunk_index = chunk.get("parent_chunk_index")
        parent_chunk_id = (
            f"{analysis_id}--{chunk['document_id']}--{parent_chunk_index}"
            if parent_chunk_index is not None
            else None
        )
        child_chunk_indices = chunk.get("child_chunk_indices") or []
        child_chunk_ids = [
            f"{analysis_id}--{chunk['document_id']}--{child_index}" for child_index in child_chunk_indices
        ]

        documents.append(
            {
                "id": chunk_id,
                "analysis_id": str(analysis_id),
                "document_id": chunk["document_id"],
                "page_number": chunk["page_number"],
                "chunk_index": chunk["chunk_index"],
                "heading_path": list(chunk.get("heading_path") or []),
                "heading_level": int(chunk.get("heading_level", 0) or 0),
                "section_path": chunk.get("section_path", "general"),
                # RAG ARCHITECTURE (2026-08-11): Campo title explícito
                # Usado para contexto semántico en embeddings pero separado de content
                "title": chunk.get("title"),  # None si no hay título (ej: contenido top-level)
                "block_type": chunk.get("block_type", "paragraph"),
                # Serializado una sola vez acá: tanto el índice de Azure Search
                # (Edm.String) como la metadata de Chroma requieren texto plano,
                # nunca un dict crudo.
                "table_ref": json.dumps(table_ref, ensure_ascii=True) if table_ref is not None else None,
                # RAG PHASE 3 (2026-08-11): Source estructurado para highlighting
                # Separa claramente metadata para localizar fuente vs metadata para highlighting
                # Contiene: page, block_type, blocks[{block_id, bbox, text}]
                "source": json.dumps(source, ensure_ascii=True) if source is not None else None,
                # `create_chunks` ya clasifica cada chunk, pero estos dos campos
                # no se subían al índice: quedaban en null para el 100% de los
                # chunks, el filtro por categoría del retrieval no matcheaba
                # nunca y toda extracción caía al fallback sin filtro.
                # `_to_index_document` descarta lo que el índice no declare, así
                # que incluirlos es seguro aunque el índice no esté migrado.
                "primary_category": chunk.get("primary_category"),
                "secondary_categories": list(chunk.get("secondary_categories") or []),
                # LEGACY V2 (2026-08): Blocks con para_id + bbox - mantener por compatibilidad
                # RAG PHASE 3: Usar campo 'source' en su lugar (más estructurado)
                "blocks": json.dumps(chunk.get("blocks", []), ensure_ascii=True) if chunk.get("blocks") else None,
                # RAG ARCHITECTURE: content es PURO (sin títulos)
                # Embedding ya fue generado con contexto (title + content)
                "content": chunk["content"],
                "embedding": chunk["embedding"],
                # PARENT/CHILD CHUNKING (US-3.1): "normal" para chunks que no se
                # subdividieron, "parent"/"child" para artículos largos con
                # incisos. `_to_index_document` descarta esto si el índice
                # todavía no fue migrado (ver
                # scripts/migrate_search_index_add_parent_child_fields.py).
                "chunk_type": chunk.get("chunk_type", "normal"),
                "parent_chunk_id": parent_chunk_id,
                "child_chunk_ids": child_chunk_ids,
            }
        )

    retries = settings.azure_search_retry_attempts
    backoff_seconds = [2, 10, 30]

    for attempt in range(1, retries + 1):
        try:
            batch_size = settings.azure_search_upload_batch_size
            for start in range(0, len(documents), batch_size):
                adapter.upload_chunks(documents[start : start + batch_size])
            logger.info(
                "search_upload_completed",
                correlation_id=str(correlation_id),
                analysis_id=str(analysis_id),
                uploaded_chunks=len(documents),
            )
            return
        except Exception as exc:
            logger.warning(
                "search_upload_attempt_failed",
                correlation_id=str(correlation_id),
                analysis_id=str(analysis_id),
                attempt=attempt,
                retries=retries,
                error=sanitize_error_message(str(exc)),
            )
            if attempt >= retries:
                raise TransientExtractionError(str(exc)) from exc
            sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])


def delete_analysis_chunks(analysis_id: str | UUID) -> int:
    adapter = _build_adapter()
    return adapter.delete_analysis_chunks(str(analysis_id)) or 0
