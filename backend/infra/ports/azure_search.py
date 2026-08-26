from __future__ import annotations

import json
from functools import lru_cache

import structlog

from infra.config import get_settings

logger = structlog.get_logger(__name__)

SEARCH_CHUNK_SELECT_FIELDS = [
    "id",
    "analysis_id",
    "document_id",
    "page_number",
    "chunk_index",
    "heading_path",
    "heading_level",
    "section_path",
    "block_type",
    "table_ref",
    "primary_category",
    "secondary_categories",
    "blocks",  # LEGACY V2: mantenido por compatibilidad -- ver 'source' abajo.
    # FIX (auditoría 2026-08-12, hallazgo US-4.1): `ai_search.py` ya escribe
    # este campo al índice desde RAG PHASE 3 (2026-08-11) -- es el formato
    # estructurado que `highlight.py::compute_highlights_for_sources` y
    # `extractors/base.py::_augment_identificacion_payload` prefieren sobre
    # 'blocks', pero como nunca se pedía acá, la búsqueda nunca lo devolvía y
    # ambos consumidores caían siempre al fallback legacy. `_search_chunk_select_fields()`
    # ya filtra por lo que el índice realmente declare, así que agregarlo acá
    # es seguro aunque un índice viejo todavía no tenga el campo.
    "source",
    "content",
    # PARENT/CHILD CHUNKING (auditoría 2026-08-12, US-3.1): permiten detectar
    # chunks "child" en los resultados y expandirlos a su "parent" completo
    # antes de devolverlos -- ver `_expand_children_to_parents` más abajo y
    # `_bmad-output/parent-child-chunking-implementation.md`. Igual que
    # 'source', son seguros de pedir aunque el índice todavía no tenga estos
    # campos: `_search_chunk_select_fields()` filtra por lo que el índice
    # realmente declare.
    "chunk_type",
    "parent_chunk_id",
    "child_chunk_ids",
]


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


def _deserialize_blocks(raw_blocks: object) -> list[dict] | None:
    """Deserializa blocks de JSON string a lista de dicts.

    DEFINITIVO V2 (2026-08): Blocks con para_id + bbox para trazabilidad precisa
    chunk → block → bbox sin ambigüedad.
    """
    if not isinstance(raw_blocks, str) or not raw_blocks:
        return None
    try:
        blocks_list = json.loads(raw_blocks)
        if isinstance(blocks_list, list):
            return blocks_list
        return None
    except json.JSONDecodeError:
        return None


def _deserialize_source(raw_source: object) -> dict | None:
    """Deserializa el campo 'source' (JSON string) a dict.

    RAG PHASE 3 (2026-08-11): Formato estructurado {page, block_type,
    blocks: [{block_id, bbox, text}]}. `ai_search.py` lo escribe con
    `json.dumps(source, ...)`; acá se hace la vuelta simétrica."""
    if not isinstance(raw_source, str) or not raw_source:
        return None
    try:
        source_dict = json.loads(raw_source)
        if isinstance(source_dict, dict):
            return source_dict
        return None
    except json.JSONDecodeError:
        return None


def _token_overlap_score(query: str, content: str) -> float:
    """Desempate menor entre chunks con el mismo score de relevancia nativo de
    Azure -- nunca reemplaza ese score, solo rompe empates exactos."""
    query_terms = {term.lower() for term in query.split() if len(term) > 2}
    if not query_terms:
        return 0.0
    content_terms = set(content.lower().split())
    overlap = query_terms.intersection(content_terms)
    return len(overlap) / len(query_terms)


def _local_bm25_score(chunk_text: str, keyword_query: str, k1: float = 1.5, b: float = 0.75) -> float:
    """Calcula BM25 score localmente sobre un chunk (Story 12.2).
    
    Implementación simplificada de BM25 para reranking local de chunks ya
    recuperados por vector search. No requiere estadísticas del corpus completo
    (usa heurísticas para IDF y avgdl).
    
    Args:
        chunk_text: Texto del chunk a rankear
        keyword_query: Keywords del glosario (espacio-separados)
        k1: Parámetro de saturación de frecuencia de términos (default: 1.5)
        b: Parámetro de normalización por largo del documento (default: 0.75)
    
    Returns:
        Score BM25 (suma de contribuciones IDF de cada término que matchea)
    """
    import math
    from collections import Counter
    
    if not keyword_query:
        return 0.0
    
    # Tokenizar query y chunk (case-insensitive)
    query_terms = keyword_query.lower().split()
    chunk_terms = chunk_text.lower().split()
    
    # Frecuencia de términos en el chunk
    term_freq = Counter(chunk_terms)
    
    # Largo del chunk (en términos)
    chunk_len = len(chunk_terms)
    
    if chunk_len == 0:
        return 0.0
    
    # Asumir corpus promedio de ~200 términos (heurística para chunks de párrafo)
    avgdl = 200.0
    
    score = 0.0
    for term in query_terms:
        if term in term_freq:
            # Frecuencia del término en este chunk
            freq = term_freq[term]
            
            # IDF simplificado (asumir que el término aparece en ~10% del corpus)
            # Para cálculo exacto necesitaríamos estadísticas del índice completo,
            # pero esta heurística es suficiente para reranking local.
            # IDF = log((N - df + 0.5) / (df + 0.5)) donde N=1000, df=100
            idf = math.log((1000 - 100 + 0.5) / (100 + 0.5))  # ≈ 2.2
            
            # BM25 score component
            numerator = freq * (k1 + 1)
            denominator = freq + k1 * (1 - b + b * (chunk_len / avgdl))
            
            score += idf * (numerator / denominator)
    
    return score


def _embed_query_or_none(
    query: str,
    *,
    analysis_id: str | None = None,
    category: str | None = None,
) -> list[float] | None:
    """Vectoriza la consulta; si falla, degradamos a búsqueda sólo léxica."""
    try:
        from indexing.embeddings import embed_query

        return embed_query(query, analysis_id=analysis_id, category=category)
    except Exception as exc:  # noqa: BLE001
        logger.warning("query_embedding_failed", error=str(exc)[:200])
        return None


def _document_to_chunk(item: dict, hybrid_score: float | None = None) -> dict:
    """Convierte un documento crudo de Azure AI Search al dict de chunk que
    usa el resto del pipeline.

    PARENT/CHILD CHUNKING (US-3.1): esta misma función se usa tanto para los
    resultados de `client.search()` (que traen '@search.score') como para un
    documento obtenido con `client.get_document()` durante la expansión
    children→parent (que no lo trae) -- por eso `hybrid_score` se puede pasar
    explícito: al expandir un child a su parent, el parent hereda el score
    del child que matcheó, en vez de recalcular uno artificial para un
    documento que nunca pasó por el ranking de búsqueda.

    FASE 1 (plan RAG v2, 2026-08-24; revisado el mismo día -- el servicio de
    Azure AI Search de este proyecto NO tiene el add-on de Semantic Ranker
    habilitado): `@search.score` es el único score que Azure devuelve acá,
    sea el path legacy (kNN puro) o el nativo (`AZURE_SEARCH_USE_NATIVE_HYBRID
    =true`, que fusiona BM25 real + vector vía RRF). No hay `@search.
    rerankerScore` en ningún path -- si en el futuro se contrata el add-on de
    Semantic Ranker, ese es el lugar para priorizarlo sobre `@search.score`.
    """
    if hybrid_score is None:
        hybrid_score = float(item.get("@search.score") or 0.0)
    return {
        "id": item.get("id"),
        "analysis_id": item.get("analysis_id"),
        "document_id": item.get("document_id"),
        "page_number": int(item.get("page_number", 0)),
        "chunk_index": int(item.get("chunk_index", 0)),
        "heading_path": list(item.get("heading_path") or []),
        "heading_level": int(item.get("heading_level") or 0),
        "section_path": item.get("section_path") or "general",
        "block_type": item.get("block_type") or "paragraph",
        "table_ref": _deserialize_table_ref(item.get("table_ref")),
        "blocks": _deserialize_blocks(
            item.get("blocks")
        ),  # LEGACY V2: mantenido por compatibilidad
        # FIX (auditoría 2026-08-12, hallazgo US-4.1): antes no se pedía
        # ni deserializaba -- ver comentario en SEARCH_CHUNK_SELECT_FIELDS.
        "source": _deserialize_source(item.get("source")),
        # Sin estos dos campos, `retrieval_metrics.purity_rate` en
        # run_extractor daba 0.0 siempre y la distribución de categorías
        # reportaba "unknown" para todo, dejando ciega la telemetría que
        # justamente serviría para detectar este problema.
        "primary_category": item.get("primary_category"),
        "secondary_categories": list(item.get("secondary_categories") or []),
        "content": item.get("content", ""),
        # FIX (auditoría 2026-08-12, hallazgo M-2): antes este score se
        # calculaba acá pero se descartaba al armar el chunk, así que
        # cualquier consumidor aguas abajo (p.ej. el boost por categoría
        # de _retrieve_with_category_priority) no tenía forma de acceder
        # al score real de relevancia híbrida de Azure y tenía que
        # inventar uno sintético a partir de la posición en el ranking.
        # Se expone acá para que quien lo necesite use la magnitud real,
        # no una aproximación por rank.
        "search_score": hybrid_score,
        # PARENT/CHILD CHUNKING (US-3.1): "normal" para chunks sin subdividir;
        # "parent"/"child" para artículos largos con incisos. Ver
        # `_expand_children_to_parents`.
        "chunk_type": item.get("chunk_type") or "normal",
        "parent_chunk_id": item.get("parent_chunk_id"),
        "child_chunk_ids": list(item.get("child_chunk_ids") or []),
    }


# Cuántos ids se piden por llamada al resolver parents. Azure acepta filtros
# OData largos, pero un `search.in` con miles de claves engorda la URL/cuerpo sin
# necesidad; 100 por vuelta mantiene el filtro chico y, para una ventana de
# expansión típica (2x top_k), resuelve todo en una o dos llamadas.
_PARENT_LOOKUP_BATCH_SIZE = 100


def _fetch_parents_by_id(client, parent_ids: list[str]) -> dict[str, dict]:
    """Resuelve varios parents en UNA búsqueda por lote en vez de un
    `get_document()` por child.

    FIX (auditoría 2026-08-13, hallazgo RET-03): `_expand_children_to_parents`
    hacía `client.get_document(key=parent_id)` dentro del loop -- una llamada
    HTTP sincrónica por cada child de la ventana de expansión. Para `garantias`
    (top_k=35 en el glossary) la ventana llega a 70 chunks, y el grafo corre las
    8 categorías en paralelo: cientos de round-trips secuenciales en el camino
    más caliente del análisis.

    Peor que lento: el costo escala con cuántos artículos con incisos tiene el
    pliego, no con su largo. Como `calculate_timeout_minutes` dimensiona el
    timeout por cantidad de páginas, un pliego bien estructurado podía vencer
    por timeout mientras uno plano del mismo largo no.

    El delimitador es `|` porque los ids son `{analysis_id}--{document_id}--{n}`
    (UUIDs y dígitos): nunca contienen `|` ni `'`. Aun así se escapan las
    comillas simples, que es lo único que rompería el string OData.
    """
    if not parent_ids:
        return {}

    select_fields = _search_chunk_select_fields()
    parents: dict[str, dict] = {}

    for start in range(0, len(parent_ids), _PARENT_LOOKUP_BATCH_SIZE):
        batch = parent_ids[start : start + _PARENT_LOOKUP_BATCH_SIZE]
        joined = "|".join(parent_id.replace("'", "''") for parent_id in batch)
        search_kwargs: dict = {
            "search_text": "*",
            "top": len(batch),
            "filter": f"search.in(id, '{joined}', '|')",
        }
        if select_fields:
            search_kwargs["select"] = select_fields

        try:
            for document in client.search(**search_kwargs):
                document_id = document.get("id")
                if document_id:
                    parents[str(document_id)] = document
        except Exception as exc:  # noqa: BLE001
            # Un lote que falla no puede tumbar la búsqueda entera: los children
            # cuyos parents no se resolvieron se conservan tal cual.
            logger.warning(
                "parent_chunk_batch_lookup_failed",
                batch_size=len(batch),
                error=str(exc)[:200],
            )

    missing = [parent_id for parent_id in parent_ids if parent_id not in parents]
    if missing:
        logger.warning(
            "parent_chunks_not_found",
            missing_count=len(missing),
            requested=len(parent_ids),
            sample=missing[:3],
        )

    return parents


def _expand_children_to_parents(client, chunks: list[dict]) -> list[dict]:
    """Expande cada chunk "child" matcheado a su chunk "parent" completo
    (US-3.1).

    El retrieval matchea sobre children -- más chicos y precisos, menos
    ruido -- pero extracción/síntesis necesitan el contexto completo del
    artículo para no perder matices jurídicos (ej: condiciones generales que
    aplican a todos los incisos). Por eso acá se reemplaza cada child por su
    parent antes de devolver los resultados.

    Si dos children del mismo parent matchean, el parent se incluye una sola
    vez -- con el score del primero en aparecer (la lista ya viene ordenada
    por relevancia descendente, así que es el de mayor score). Si un chunk
    "parent" ya vino matcheado directamente, también se registra para que un
    child del mismo parent no lo duplique.

    FIX (auditoría 2026-08-13, hallazgo RET-01): esa dedupe era ASIMÉTRICA.
    Funcionaba en el orden parent→child, pero no en child→parent: la rama de
    `chunk_type == "parent"` appendeaba sin consultar `seen_parent_ids`, así
    que si el child aparecía PRIMERO (se expandía a su parent y lo registraba)
    y el parent original llegaba después en la lista, el mismo artículo entraba
    dos veces al contexto.

    Y child→parent es el orden ESPERABLE, no el raro: el texto del parent
    contiene al del child por construcción (`chunking.py`), así que los dos
    matchean la misma query, y el child -- más corto -- gana en BM25 por la
    normalización por longitud. El costo era doble: dos slots de `top_k`
    gastados en el mismo texto (desplazando chunks relevantes fuera del
    contexto) y evidencia duplicada que el prompt del sistema premia como
    "dato consistente en múltiples fragmentos" (+0.2 de confidence, ver
    `prompts/_base_system.txt`) -- el sistema autovalidándose con una copia
    de sí mismo.

    Si la expansión falla (parent borrado, error de red, etc.) se conserva
    el child tal cual -- mejor contexto parcial que nada.
    """
    # Una sola resolución por lote para toda la ventana, antes del loop
    # (hallazgo RET-03). Se piden los parents de TODOS los children, aunque el
    # dedupe después descarte algunos: son claves, no documentos, y agruparlas
    # en una llamada es más barato que decidir una por una.
    needed_parent_ids: list[str] = []
    for chunk in chunks:
        if chunk.get("chunk_type") != "child":
            continue
        parent_id = chunk.get("parent_chunk_id")
        if parent_id and parent_id not in needed_parent_ids:
            needed_parent_ids.append(str(parent_id))

    parents_by_id = _fetch_parents_by_id(client, needed_parent_ids)

    expanded: list[dict] = []
    seen_parent_ids: set[str] = set()

    for chunk in chunks:
        chunk_type = chunk.get("chunk_type")

        if chunk_type == "parent":
            chunk_id = chunk.get("id")
            if chunk_id and chunk_id in seen_parent_ids:
                # Ya entró al contexto, expandido desde un child de mejor score.
                logger.debug(
                    "parent_chunk_already_expanded_skipped",
                    parent_chunk_id=chunk_id,
                )
                continue
            if chunk_id:
                seen_parent_ids.add(chunk_id)
            expanded.append(chunk)
            continue

        if chunk_type != "child" or not chunk.get("parent_chunk_id"):
            expanded.append(chunk)
            continue

        parent_id = chunk["parent_chunk_id"]
        if parent_id in seen_parent_ids:
            # Ya se expandió este parent por otro child con mejor (o igual) score.
            continue

        parent_document = parents_by_id.get(parent_id)
        if parent_document is None:
            # Parent borrado, o el lote que lo contenía falló. Mejor contexto
            # parcial que nada: se conserva el child tal cual.
            logger.warning(
                "parent_chunk_expansion_failed",
                parent_chunk_id=parent_id,
                child_chunk_id=chunk.get("id"),
                reason="el parent no se pudo resolver en la búsqueda por lote",
            )
            expanded.append(chunk)
            continue

        parent_chunk = _document_to_chunk(parent_document, hybrid_score=chunk.get("search_score"))
        # Metadata útil para highlighting: qué inciso puntual matcheó dentro
        # del parent expandido, para poder priorizarlo al resaltar evidencia.
        parent_chunk["matched_child_chunk_id"] = chunk.get("id")
        parent_chunk["matched_child_content"] = chunk.get("content")
        seen_parent_ids.add(parent_id)
        expanded.append(parent_chunk)

    return expanded


def _search_azure(
    query: str,
    analysis_id: str,
    top_k: int,
    keyword_query: str | None = None,
    category: str | None = None,  # Epic 11: para caché de embeddings
) -> list[dict]:
    settings = get_settings()
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient

    client = SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        credential=AzureKeyCredential(settings.azure_search_key),
    )

    # FIX (auditoría 2026-08-13, hallazgo RET-03): acá se pedían `top_k * 3`
    # documentos, pero aguas abajo la ventana de expansión corta en `top_k * 2`
    # (ver `expansion_window`) y todo lo que queda después de ese corte se
    # descarta sin mirarse. O sea que un tercio de los documentos pedidos --
    # con su `content` completo -- se traía de Azure para tirarlo. Ahora se pide
    # exactamente lo que la ventana puede consumir.
    #
    # El k del kNN vectorial SÍ conserva el margen de 3x: es cuántos vecinos
    # entran a la fusión RRF con BM25, no cuántos documentos se devuelven.
    # Recortarlo cambiaría el ranking; recortar `top` no.
    #
    # ÉPICA 10 (2026-08-21): Con análisis pequeños (< 50 chunks), fetch_top alto
    # recupera TODOS los chunks sin filtrado vectorial efectivo. Mantenemos el
    # comportamiento para NO perder información (requisito: "siempre recuperar
    # los mismos datos"), pero agregamos filtrado por score abajo.
    fetch_top = max(top_k * 2, 30)
    # Azure AI Search limita k_nearest_neighbors a 1000 max para búsquedas vectoriales
    k_for_vector = min(max(top_k * 3, 30), 1000)

    # ÉPICA 11 (2026-08-21): Caché de embeddings con query_id determinista
    query_vector = _embed_query_or_none(query, analysis_id=analysis_id, category=category)

    # STORY 12.2 (2026-08-21): Pipeline de 2 etapas — vector puro + BM25 reranking opcional
    # Etapa 1: Vector search recupera top_k*2 candidatos
    # Etapa 2: BM25 reranking local (solo si keyword_query existe) mejora ranking
    #
    # FASE 1 del plan RAG v2 (2026-08-24): esta función queda como el path
    # DEFAULT (`AZURE_SEARCH_USE_NATIVE_HYBRID=false`). El path nuevo,
    # `_run_native_hybrid_query` más abajo, reemplaza la fusión manual por
    # Hybrid Search nativo de Azure (BM25 real sobre el corpus completo,
    # fusionado con el vector vía RRF -- sin reranking semántico, que
    # requiere el add-on de Semantic Ranker, no disponible en este proyecto).
    def _run_vector_only_query(filters: list[str], top: int) -> list[dict]:
        """Ejecuta búsqueda vectorial pura sin BM25 (Story 12.2)."""
        search_kwargs = {
            "search_text": "",  # Sin BM25 — solo vector search
            "top": top,
            "filter": " and ".join(filters),
        }
        select_fields = _search_chunk_select_fields()
        if select_fields:
            search_kwargs["select"] = select_fields

        if query_vector is not None:
            from azure.search.documents.models import VectorizedQuery

            vector_query_obj = VectorizedQuery(
                vector=query_vector, k_nearest_neighbors=k_for_vector, fields="embedding"
            )
            search_kwargs["vector_queries"] = [vector_query_obj]

            logger.info(
                "vector_only_search",
                k_nearest_neighbors=k_for_vector,
                vector_length=len(query_vector),
            )

        return list(client.search(**search_kwargs))

    def _run_native_hybrid_query(filters: list[str], top: int) -> list[dict]:
        """Hybrid Search nativo de Azure (Fase 1, plan RAG v2 2026-08-24;
        revisado el mismo día: el servicio de Azure AI Search de este
        proyecto NO tiene el add-on de Semantic Ranker habilitado, así que
        este path usa Hybrid Search "clásico" -- BM25 + vector fusionados por
        Azure vía RRF -- sin el paso de reranking semántico, que requiere ese
        add-on pago). Reemplaza `_run_vector_only_query` + `_local_bm25_score`
        cuando `AZURE_SEARCH_USE_NATIVE_HYBRID=true`.

        La diferencia real contra el path legacy no es el reranking (que acá
        no existe) sino QUÉ corpus ve el BM25: pasando `search_text` junto
        con `vector_queries` en la misma llamada, Azure corre BM25 real sobre
        el corpus COMPLETO del análisis y lo fusiona con el kNN vía RRF antes
        de truncar a `top` -- en vez de `_local_bm25_score`, que sólo
        reordena los ~30-90 candidatos que el kNN ya trajo, así que un chunk
        con match léxico exacto (un monto, un artículo, un código) pero mal
        rankeado por el vector nunca llega a competir. Azure no necesita un
        `query_type` especial para esto: alcanza con mandar ambos parámetros
        juntos.
        """
        from azure.search.documents.models import VectorizedQuery

        # `keyword_query` (términos del glosario) es más discriminante que la
        # query semántica larga para el BM25 nativo (montos, artículos,
        # códigos puntuales). Si la categoría no tiene términos de glosario
        # configurados, se cae a la query semántica original -- sigue siendo
        # mejor que search_text="" (el path legacy), porque agrega la mitad
        # léxica real a la fusión en vez de prescindir de ella.
        search_text = keyword_query or query
        search_kwargs: dict = {
            "search_text": search_text,
            "top": top,
            "filter": " and ".join(filters),
        }
        select_fields = _search_chunk_select_fields()
        if select_fields:
            search_kwargs["select"] = select_fields

        if query_vector is not None:
            vector_query_obj = VectorizedQuery(
                vector=query_vector, k_nearest_neighbors=k_for_vector, fields="embedding"
            )
            search_kwargs["vector_queries"] = [vector_query_obj]

        logger.info(
            "native_hybrid_search",
            search_text=search_text[:80],
            has_vector=query_vector is not None,
        )

        return list(client.search(**search_kwargs))

    analysis_filter = [f"analysis_id eq '{analysis_id}'"]

    # AUDITORÍA 10.1: logueamos info pre-búsqueda para diagnosticar embedding fallido
    logger.info(
        "search_azure_debug",
        query=query[:80],
        keyword_query=(keyword_query or "")[:80],
        has_vector=query_vector is not None,
        vector_preview=query_vector[:3] if query_vector else None,
    )

    # FASE 1 (plan RAG v2, 2026-08-24): con el flag activo, Azure hace la
    # fusión BM25 real + vector (RRF) en una sola llamada nativa. Sin el
    # flag, se mantiene el pipeline de 2 etapas de Story 12.2 (vector puro +
    # BM25 local aproximado sobre el pool ya recuperado), por retrocompatibilidad
    # mientras se valida el path nuevo con el dataset de evaluación.
    use_native_hybrid = settings.azure_search_use_native_hybrid
    raw_results = (
        _run_native_hybrid_query(analysis_filter, top=fetch_top)
        if use_native_hybrid
        else _run_vector_only_query(analysis_filter, top=fetch_top)
    )

    # INVESTIGACIÓN 10.4: loguear primeros resultados para diagnosticar
    if raw_results:
        first_5_results = []
        for item in list(raw_results)[:5]:
            first_5_results.append({
                "id": item.get("id", "N/A")[:40],
                "score": float(item.get("@search.score") or 0.0),
                "primary_category": item.get("primary_category", "N/A"),
            })
        logger.info(
            "azure_search_raw_results_sample",
            query=query[:60],
            total_results=len(list(raw_results)),
            first_5=first_5_results,
        )

    # STORY 10.3: Wildcard fallback eliminado — si la búsqueda no devuelve
    # resultados, es un error crítico que debe detener la extracción, no
    # degradarse silenciosamente a chunks arbitrarios.
    if not raw_results:
        if query_vector is None:
            # El embedding de la query falló: la búsqueda fue puramente léxica
            # y BM25 no matcheó nada. Esto significa que el servicio de embeddings
            # no está funcionando.
            logger.error(
                "azure_search_embedding_failed_critical",
                analysis_id=analysis_id,
                query=query[:120],
                reason=(
                    "el embedding de la query falló (query_vector es None): "
                    "retrieval no funcional, extracción debe abortar"
                ),
            )
            raise RuntimeError(
                f"Embedding de query falló para '{query[:60]}...' — retrieval no funcional"
            )
        else:
            # La búsqueda híbrida corrió completa y no devolvió nada: no hay
            # chunks indexados para este análisis. Es un problema de indexación.
            logger.error(
                "azure_search_analysis_sin_chunks",
                analysis_id=analysis_id,
                query=query[:120],
                reason=(
                    "la búsqueda híbrida (BM25 + vectorial) no devolvió ningún "
                    "documento con este analysis_id: el análisis no está indexado"
                ),
            )
            raise RuntimeError(
                f"Análisis {analysis_id} no tiene chunks indexados — "
                f"búsqueda híbrida devolvió 0 resultados para query '{query[:60]}...'"
            )

    # STORY 12.2 / FASE 1: cómo se computa `combined_score` depende del path.
    #
    # - Nativo (use_native_hybrid=true): Azure ya fusionó BM25 real + vector
    #   (RRF) antes de devolver los resultados -- sin reranking semántico
    #   (add-on no disponible en este proyecto). El score ya viene combinado
    #   en `chunk["search_score"]` (`@search.score`, ver `_document_to_chunk`).
    #   No hay nada más que combinar acá.
    # - Legacy (use_native_hybrid=false): sin BM25 real disponible sobre el
    #   pool ya recortado por kNN, se aproxima con `_local_bm25_score` y se
    #   combina manualmente con el score vectorial (comportamiento sin cambios
    #   respecto de antes de la Fase 1).
    scored: list[tuple[float, float, dict]] = []
    for item in raw_results:
        chunk = _document_to_chunk(item)
        base_score = chunk["search_score"]

        if use_native_hybrid:
            combined_score = base_score
            logger.debug(
                "native_hybrid_ranking",
                chunk_id=chunk.get("id", "N/A")[:40],
                score=round(base_score, 4),
            )
        elif keyword_query:
            # ETAPA 2 (legacy): BM25 reranking local aproximado
            bm25_score = _local_bm25_score(chunk["content"], keyword_query)
            # Normalizar BM25 score a escala similar a vector (típicamente 0-1)
            # BM25 puede dar scores ~5-10 para buenos matches
            bm25_normalized = min(bm25_score / 10.0, 1.0)
            # Combinar: 60% vector + 40% BM25 (similar a RRF de Azure)
            combined_score = 0.6 * base_score + 0.4 * bm25_normalized

            if bm25_score > 0:  # Solo loguear si BM25 aportó algo
                logger.debug(
                    "bm25_reranking_applied",
                    chunk_id=chunk.get("id", "N/A")[:40],
                    vector_score=round(base_score, 4),
                    bm25_score=round(bm25_score, 4),
                    combined_score=round(combined_score, 4),
                )
        else:
            combined_score = base_score
            logger.debug(
                "vector_only_ranking",
                chunk_id=chunk.get("id", "N/A")[:40],
                vector_score=round(base_score, 4),
                reason="no_keyword_query",
            )

        scored.append((combined_score, _token_overlap_score(query, chunk["content"]), chunk))

    scored.sort(key=lambda triple: (triple[0], triple[1]), reverse=True)
    ranked_chunks = [chunk for _score, _overlap, chunk in scored]

    # ÉPICA 10 (2026-08-21): Con análisis pequeños (< 50 chunks totales), Azure
    # retorna TODOS los chunks sin filtrado vectorial efectivo. Los scores quedan
    # muy bajos (~0.031-0.033) porque la búsqueda híbrida no rankea bien con tan
    # pocos vectores. Filtramos chunks de score muy bajo para mejorar precisión.
    #
    # FASE 1 (2026-08-24): este threshold se calibró para el score vectorial
    # coseno (escala 0-1) del path legacy. El `@search.score` del Hybrid
    # Search nativo es un score de fusión RRF, en otra escala -- aplicar el
    # mismo threshold ahí no filtraría nada (falso negativo) o filtraría de
    # más si algún día se combina distinto -- se salta este filtro bajo
    # `use_native_hybrid` hasta calibrar un threshold propio con
    # el dataset de evaluación (sección 6 del plan RAG v2).
    total_chunks_available = len(ranked_chunks)
    if total_chunks_available < 50 and not use_native_hybrid:
        logger.warning(
            "retrieval_small_analysis_detected",
            analysis_id=analysis_id,
            total_chunks=total_chunks_available,
            query=query[:60],
            impact=(
                "con pocos chunks, búsqueda vectorial no rankea efectivamente; "
                "aplicamos threshold de score para filtrar irrelevantes"
            ),
        )
        
        # Threshold de score mínimo: filtrar chunks con score muy bajo
        # (típicamente < 0.032 son ruido cuando solo hay ~20 chunks)
        MIN_SCORE_SMALL_ANALYSIS = 0.032
        before_filter = len(ranked_chunks)
        ranked_chunks = [
            chunk for chunk in ranked_chunks 
            if chunk.get("search_score", 0.0) >= MIN_SCORE_SMALL_ANALYSIS
        ]
        
        if len(ranked_chunks) < before_filter:
            logger.info(
                "retrieval_low_score_chunks_filtered",
                analysis_id=analysis_id,
                before=before_filter,
                after=len(ranked_chunks),
                filtered=before_filter - len(ranked_chunks),
                threshold=MIN_SCORE_SMALL_ANALYSIS,
            )

    # PARENT/CHILD CHUNKING (US-3.1): expandir children a su parent completo
    # antes de truncar a top_k -- expandir sobre una ventana más amplia que
    # top_k (en vez de sobre top_k directo) da margen para que el dedupe de
    # children del mismo parent no deje menos de top_k resultados finales de
    # los necesarios. Si no hay ningún "child" entre los resultados (índice
    # viejo, o análisis sin artículos subdivididos) esto es un no-op y el
    # comportamiento es idéntico al de antes de US-3.1.
    # `fetch_top` ya se dimensionó para esta ventana: el slice es un no-op
    # salvo cuando `top_k * 2 < 30` (categorías con top_k chico), donde el piso
    # de 30 documentos sigue dando margen para el dedupe children->parent.
    expansion_window = ranked_chunks[: max(top_k * 2, top_k)]
    expanded_chunks = _expand_children_to_parents(client, expansion_window)

    return expanded_chunks[:top_k]


# Tope de seguridad para `fetch_all_analysis_chunks`. No es un límite del
# servicio (la paginación por continuation token no tiene tope): sólo evita que
# un analysis_id corrupto o un filtro mal armado traigan el índice entero a
# memoria. Un pliego muy grande ronda los pocos miles de chunks.
_MAX_ENUMERABLE_CHUNKS = 50_000


def fetch_all_analysis_chunks(analysis_id: str) -> tuple[list[dict], bool]:
    """Enumera TODOS los chunks de un análisis. No es una búsqueda.

    FIX (auditoría 2026-08-13, hallazgo SYN-03): antes esto se hacía con
    `search_hybrid(query="*", top_k=1000)`, que NO enumera:

      - vectorizaba el literal `"*"` (una llamada de embedding real a Azure
        OpenAI) y hacía kNN contra ese vector, así que los resultados eran los
        1000 chunks más cercanos al embedding de un asterisco -- un subconjunto
        SESGADO, no una muestra uniforme ni el conjunto completo;
      - fusionaba ese kNN con BM25 vía RRF, gastando `top=3000` en el servicio;
      - corría `_expand_children_to_parents` sobre 2000 candidatos, con una
        llamada HTTP `get_document()` por cada child -- y de paso REEMPLAZABA
        los children por sus parents, así que los chunk_id de los children
        desaparecían del índice resultante;
      - truncaba en 1000 sin ninguna señal.

    Acá se va directo al servicio con `search_text="*"` y sin vector: el
    paginador del SDK sigue los continuation tokens hasta agotar el conjunto.

    Returns:
        (chunks, truncated) -- `truncated` es True si se alcanzó el tope de
        seguridad, para que el llamador pueda avisar en vez de degradar en
        silencio.
    """
    settings = get_settings()
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient

    client = SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        credential=AzureKeyCredential(settings.azure_search_key),
    )

    escaped_analysis_id = str(analysis_id).replace("'", "''")
    search_kwargs: dict = {
        "search_text": "*",
        "filter": f"analysis_id eq '{escaped_analysis_id}'",
    }
    select_fields = _search_chunk_select_fields()
    if select_fields:
        # Excluye `embedding` (no está en SEARCH_CHUNK_SELECT_FIELDS): traer
        # 3072 floats por chunk multiplicaría el payload por dos órdenes de
        # magnitud sin que nadie los use.
        search_kwargs["select"] = select_fields

    chunks: list[dict] = []
    truncated = False
    for item in client.search(**search_kwargs):
        if len(chunks) >= _MAX_ENUMERABLE_CHUNKS:
            truncated = True
            break
        # Sin expansión children->parent: acá se quiere el índice TAL CUAL está,
        # con children y parents por separado. La expansión es una decisión de
        # retrieval, no de enumeración.
        chunks.append(_document_to_chunk(item))

    logger.info(
        "analysis_chunks_enumerated",
        analysis_id=str(analysis_id),
        total_chunks=len(chunks),
        truncated=truncated,
    )
    if truncated:
        logger.error(
            "analysis_chunks_enumeration_truncated",
            analysis_id=str(analysis_id),
            limit=_MAX_ENUMERABLE_CHUNKS,
            impact=(
                "el índice de chunks está incompleto; la resolución de evidencias y "
                "el highlighting pueden fallar para los chunks faltantes"
            ),
        )

    return chunks, truncated


def search_hybrid(
    query: str,
    analysis_id: str,
    top_k: int = 10,
    keyword_query: str | None = None,
    category: str | None = None,  # Epic 11: para caché de embeddings
) -> list[dict]:
    """Recupera chunks relevantes para una categoría, filtrados por analysis_id.

    Args:
        query: Query semántica para búsqueda vectorial
        analysis_id: ID del análisis
        top_k: Cantidad de chunks a retornar
        keyword_query: Query de keywords para BM25 (discriminante)
        category: Categoría de extracción (opcional, para caché de embeddings)

    No hay filtro por categoría. La categoría se aplica como SEÑAL de ranking
    (`category_boost` en `_retrieve_with_category_priority`), no como compuerta:
    la información de una categoría suele estar repartida en chunks clasificados
    en otras, y un filtro duro la perdía. El parámetro `category_filter` existía
    en esta firma pero ningún llamador real lo pasaba desde el cambio de
    arquitectura de 2026-08-12 -- se eliminó junto con el filtro OData que
    construía (hallazgo RET-02).
    """
    return _search_azure(
        query=query,
        analysis_id=analysis_id,
        top_k=top_k,
        keyword_query=keyword_query,
        category=category,
    )
