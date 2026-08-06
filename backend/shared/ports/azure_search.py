from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import structlog

from shared.config import get_settings

logger = structlog.get_logger(__name__)

SEARCH_CHUNK_SELECT_FIELDS = [
    "analysis_id",
    "document_id",
    "page_number",
    "chunk_index",
    "section_key",
    "section_path",
    "section_level",
    "block_type",
    "table_ref",
    "content",
]

# Mapa de categoria semantica -> secciones estructurales del chunker.
# Se usa para boost de ranking, nunca como filtro excluyente.
CATEGORY_SECTION_PREFERENCE: dict[str, list[str]] = {
    "objeto_alcance": ["capitulos", "articulos"],
    "plazos": ["articulos", "capitulos"],
    "garantias": ["articulos", "capitulos"],
    "causales_rechazo": ["articulos", "capitulos"],
    "anexos_obligatorios": ["anexos", "articulos"],
    "documentos_requeridos": ["articulos", "incisos"],
    "restricciones_participacion": ["articulos", "incisos"],
    "criterios_evaluacion": ["articulos", "capitulos"],
    "cronograma_proceso": ["articulos", "capitulos"],
    "estimacion_presupuesto": ["articulos", "capitulos"],
    "identificacion_procedimiento": ["general", "capitulos"],
}


def _preferred_sections(section_key: str | None) -> list[str]:
    if not section_key:
        return []
    return CATEGORY_SECTION_PREFERENCE.get(section_key, [])


@lru_cache(maxsize=1)
def _azure_index_fields_cache(index_key: str) -> tuple[str, ...]:
    settings = get_settings()
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents.indexes import SearchIndexClient

    client = SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=AzureKeyCredential(settings.azure_search_key),
    )
    index = client.get_index(settings.azure_search_index_name)
    return tuple(field.name for field in index.fields)


def _search_chunk_select_fields() -> list[str]:
    settings = get_settings()
    index_key = f"{settings.azure_search_endpoint}:{settings.azure_search_index_name}"
    available_fields = set(_azure_index_fields_cache(index_key))
    return [field for field in SEARCH_CHUNK_SELECT_FIELDS if field in available_fields]


def _deserialize_table_ref(raw_table_ref: object) -> dict | None:
    if not isinstance(raw_table_ref, str) or not raw_table_ref:
        return None
    try:
        return json.loads(raw_table_ref)
    except json.JSONDecodeError:
        return None


def _section_bonus(section_key: str, preferred_sections: list[str] | None) -> float:
    if not preferred_sections:
        return 0.0
    return 0.4 if section_key in preferred_sections else 0.0


def _token_overlap_score(query: str, content: str) -> float:
    query_terms = {term.lower() for term in query.split() if len(term) > 2}
    if not query_terms:
        return 0.0
    content_terms = set(content.lower().split())
    overlap = query_terms.intersection(content_terms)
    return len(overlap) / len(query_terms)


def _search_local(
    query: str,
    analysis_id: str,
    top_k: int,
    section_key: str | None,
) -> list[dict]:
    settings = get_settings()
    chroma_dir = Path(settings.chroma_persist_directory)
    if not chroma_dir.exists():
        logger.warning("chroma_dir_missing", path=str(chroma_dir), analysis_id=analysis_id)
        return []

    import chromadb
    from sentence_transformers import SentenceTransformer

    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(name="analysis_chunks")
    model = SentenceTransformer(settings.sentence_transformers_model)
    query_embedding = model.encode([query], normalize_embeddings=True)[0].tolist()

    over_fetch = max(top_k * 3, 30)

    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=over_fetch,
        where={"analysis_id": analysis_id},
        include=["metadatas", "documents", "distances"],
    )

    metadatas = result.get("metadatas", [[]])[0]
    documents = result.get("documents", [[]])[0]
    distances = result.get("distances", [[]])[0]

    preferred = _preferred_sections(section_key)
    scored: list[tuple[float, dict]] = []

    for metadata, content, distance in zip(metadatas, documents, distances, strict=False):
        table_ref = _deserialize_table_ref(metadata.get("table_ref"))
        chunk_section = metadata.get("section_key", "general")
        base_score = 1.0 - float(distance or 0.0)
        score = (
            base_score
            + _section_bonus(chunk_section, preferred)
            + (0.25 * _token_overlap_score(query, content or ""))
        )

        scored.append(
            (
                score,
                {
                    "analysis_id": metadata.get("analysis_id"),
                    "document_id": metadata.get("document_id"),
                    "page_number": int(metadata.get("page_number", 0)),
                    "chunk_index": int(metadata.get("chunk_index", 0)),
                    "section_key": chunk_section,
                    "section_path": metadata.get("section_path", chunk_section),
                    "section_level": int(metadata.get("section_level", 0) or 0),
                    "block_type": metadata.get("block_type", "paragraph"),
                    "table_ref": table_ref,
                    "content": content,
                },
            )
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    chunks = [item[1] for item in scored[:top_k]]

    if not chunks:
        logger.warning(
            "local_search_empty",
            analysis_id=analysis_id,
            section_key=section_key,
            query=query[:120],
        )
    else:
        logger.info(
            "local_search_completed",
            analysis_id=analysis_id,
            section_key=section_key,
            returned=len(chunks),
            top_score=round(scored[0][0], 4),
        )
    return chunks


def _embed_query_or_none(query: str) -> list[float] | None:
    """Vectoriza la consulta; si falla, degradamos a búsqueda sólo léxica."""
    try:
        from extraction.embeddings import embed_query

        return embed_query(query)
    except Exception as exc:  # noqa: BLE001
        logger.warning("query_embedding_failed", error=str(exc)[:200])
        return None


def _search_azure(
    query: str,
    analysis_id: str,
    top_k: int,
    section_key: str | None,
) -> list[dict]:
    settings = get_settings()
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient

    client = SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        credential=AzureKeyCredential(settings.azure_search_key),
    )

    over_fetch = max(top_k * 3, 30)
    query_vector = _embed_query_or_none(query)

    def _run_query(filters: list[str], search_text: str, top: int) -> list[dict]:
        search_kwargs = {
            "search_text": search_text,
            "top": top,
            "filter": " and ".join(filters),
        }
        select_fields = _search_chunk_select_fields()
        if select_fields:
            search_kwargs["select"] = select_fields

        # Búsqueda híbrida real: BM25 + vectorial fusionados por Azure (RRF).
        # Sin esto sólo se recupera lo que coincide léxicamente, y un pliego que
        # no usa las palabras del glosario queda invisible.
        if query_vector is not None:
            from azure.search.documents.models import VectorizedQuery

            search_kwargs["vector_queries"] = [
                VectorizedQuery(vector=query_vector, k_nearest_neighbors=top, fields="embedding")
            ]

        return list(client.search(**search_kwargs))

    analysis_filter = [f"analysis_id eq '{analysis_id}'"]

    raw_results = _run_query(analysis_filter, query, top=over_fetch)

    if not raw_results:
        logger.warning(
            "azure_search_wildcard_fallback",
            analysis_id=analysis_id,
            section_key=section_key,
            query=query[:120],
        )
        raw_results = _run_query(analysis_filter, "*", top=over_fetch)

    chunks: list[dict] = []
    for item in raw_results:
        # `.get(key, default)` sólo aplica el default cuando la clave está AUSENTE.
        # Azure Search devuelve la clave presente con valor None para chunks
        # indexados antes de que el campo existiera en el esquema, así que acá
        # hace falta `or` explícito para no propagar None a los extractores.
        section_key = item.get("section_key") or "general"
        chunks.append(
            {
                "analysis_id": item.get("analysis_id"),
                "document_id": item.get("document_id"),
                "page_number": int(item.get("page_number", 0)),
                "chunk_index": int(item.get("chunk_index", 0)),
                "section_key": section_key,
                "section_path": item.get("section_path") or section_key,
                "section_level": int(item.get("section_level") or 0),
                "block_type": item.get("block_type") or "paragraph",
                "table_ref": _deserialize_table_ref(item.get("table_ref")),
                "content": item.get("content", ""),
            }
        )
    preferred = _preferred_sections(section_key)
    chunks.sort(
        key=lambda c: (
            _section_bonus(c.get("section_key", "general"), preferred)
            + (0.25 * _token_overlap_score(query, c.get("content", "")))
        ),
        reverse=True,
    )
    return chunks[:top_k]


def search_hybrid(
    query: str,
    analysis_id: str,
    top_k: int = 10,
    section_key: str | None = None,
) -> list[dict]:
    """Recupera chunks para una categoría con filtro por analysis_id y sección."""
    settings = get_settings()
    if settings.is_development:
        return _search_local(query=query, analysis_id=analysis_id, top_k=top_k, section_key=section_key)

    return _search_azure(query=query, analysis_id=analysis_id, top_k=top_k, section_key=section_key)
