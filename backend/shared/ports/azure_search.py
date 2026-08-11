from __future__ import annotations

import json
from functools import lru_cache

import structlog

from shared.config import get_settings

logger = structlog.get_logger(__name__)

SEARCH_CHUNK_SELECT_FIELDS = [
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
    "content",
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


def _token_overlap_score(query: str, content: str) -> float:
    """Desempate menor entre chunks con el mismo score de relevancia nativo de
    Azure -- nunca reemplaza ese score, solo rompe empates exactos."""
    query_terms = {term.lower() for term in query.split() if len(term) > 2}
    if not query_terms:
        return 0.0
    content_terms = set(content.lower().split())
    overlap = query_terms.intersection(content_terms)
    return len(overlap) / len(query_terms)


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
    keyword_query: str | None = None,
    category_filter: str | None = None,
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
    # BM25 usa keywords del glossary (discriminantes); vector usa la query
    # descriptiva completa (semántica). Esto evita diluir BM25 con stopwords.
    bm25_text = keyword_query if keyword_query else query

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
        # BM25 recibe keywords del glossary; vector recibe la query semántica.
        if query_vector is not None:
            from azure.search.documents.models import VectorizedQuery

            search_kwargs["vector_queries"] = [
                VectorizedQuery(vector=query_vector, k_nearest_neighbors=top, fields="embedding")
            ]

        return list(client.search(**search_kwargs))

    analysis_filter = [f"analysis_id eq '{analysis_id}'"]

    # Filtro de categoría: busca en primary_category O en secondary_categories
    if category_filter:
        category_escaped = category_filter.replace("'", "''")
        category_condition = (
            f"(primary_category eq '{category_escaped}' or "
            f"secondary_categories/any(c: c eq '{category_escaped}'))"
        )
        analysis_filter.append(category_condition)

    raw_results = _run_query(analysis_filter, bm25_text, top=over_fetch)

    # FIX MEDIUM (#13): Limitar fallback wildcard para evitar chunks irrelevantes.
    # Solo hacer fallback si no hay filtro de categoría — si ya se filtró por
    # categoría y no hay resultados, retornar vacío es más seguro que retornar
    # chunks aleatorios que el LLM podría usar para "extraer" información incorrecta.
    if not raw_results and not category_filter:
        logger.warning(
            "azure_search_wildcard_fallback",
            analysis_id=analysis_id,
            query=query[:120],
            reason="no results without category filter - trying wildcard",
        )
        raw_results = _run_query(analysis_filter, "*", top=over_fetch)
    elif not raw_results and category_filter:
        logger.info(
            "azure_search_no_results_with_category",
            analysis_id=analysis_id,
            category=category_filter,
            query=query[:120],
            reason="no results with category filter - returning empty (safer than wildcard)",
        )

    # Se ordena por el score de relevancia hibrida que Azure ya calculo
    # (BM25 + vectorial fusionados por RRF) -- nunca se descarta ese score para
    # reordenar solo con heuristica propia. El overlap lexico es apenas un
    # desempate para scores exactamente iguales, no un segundo criterio con
    # peso propio: sumarlo mezclaria dos escalas que no son comparables.
    scored: list[tuple[float, float, dict]] = []
    for item in raw_results:
        hybrid_score = float(item.get("@search.score") or 0.0)
        chunk = {
            "analysis_id": item.get("analysis_id"),
            "document_id": item.get("document_id"),
            "page_number": int(item.get("page_number", 0)),
            "chunk_index": int(item.get("chunk_index", 0)),
            "heading_path": list(item.get("heading_path") or []),
            "heading_level": int(item.get("heading_level") or 0),
            "section_path": item.get("section_path") or "general",
            "block_type": item.get("block_type") or "paragraph",
            "table_ref": _deserialize_table_ref(item.get("table_ref")),
            # Sin estos dos campos, `retrieval_metrics.purity_rate` en
            # run_extractor daba 0.0 siempre y la distribución de categorías
            # reportaba "unknown" para todo, dejando ciega la telemetría que
            # justamente serviría para detectar este problema.
            "primary_category": item.get("primary_category"),
            "secondary_categories": list(item.get("secondary_categories") or []),
            "content": item.get("content", ""),
        }
        scored.append((hybrid_score, _token_overlap_score(query, chunk["content"]), chunk))

    scored.sort(key=lambda triple: (triple[0], triple[1]), reverse=True)
    return [chunk for _score, _overlap, chunk in scored[:top_k]]


def search_hybrid(
    query: str,
    analysis_id: str,
    top_k: int = 10,
    keyword_query: str | None = None,
    category_filter: str | None = None,
) -> list[dict]:
    """Recupera chunks relevantes para una categoría, filtrados por analysis_id.

    Args:
        query: Query semántica para búsqueda vectorial
        analysis_id: ID del análisis
        top_k: Cantidad de chunks a retornar
        keyword_query: Query de keywords para BM25 (discriminante)
        category_filter: Si se especifica, filtra chunks donde:
            primary_category eq '{category_filter}' OR
            secondary_categories/any(c: c eq '{category_filter}')
    """
    return _search_azure(
        query=query,
        analysis_id=analysis_id,
        top_k=top_k,
        keyword_query=keyword_query,
        category_filter=category_filter,
    )
