"""Story 12.1: Análisis de impacto de BM25 vs Vector en RRF actual.

Instrumentación temporal para medir cuánto contribuye cada componente del
hybrid search al ranking final. Se activa vía ENABLE_BM25_IMPACT_ANALYSIS=true.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def analyze_bm25_vs_vector_impact(
    client,
    analysis_filter: list[str],
    query_vector: list[float] | None,
    bm25_text: str,
    query: str,
    fetch_top: int,
    k_for_vector: int,
) -> dict:
    """Ejecuta 3 búsquedas separadas y calcula overlap metrics.
    
    Returns:
        {
            "vector_only": list[dict],  # Top chunks solo por vector
            "bm25_only": list[dict],    # Top chunks solo por BM25
            "hybrid_rrf": list[dict],   # Top chunks por RRF híbrido
            "metrics": {
                "overlap_v_to_rrf": int,     # Chunks del top-10 RRF que venían de vector
                "unique_bm25": int,           # Chunks del top-10 RRF que SOLO venían de BM25
                "bm25_contribution_rate": float,  # unique_bm25 / 10
            }
        }
    """
    from azure.search.documents.models import VectorizedQuery

    select_fields = _get_select_fields()
    filter_str = " and ".join(analysis_filter)
    
    # 1. Vector solo (sin search_text)
    vector_results = []
    if query_vector is not None:
        vector_query_obj = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=k_for_vector,
            fields="embedding",
        )
        vector_results = list(
            client.search(
                search_text="",  # Sin BM25
                top=fetch_top,
                filter=filter_str,
                select=select_fields,
                vector_queries=[vector_query_obj],
            )
        )
    
    # 2. BM25 solo (sin vector_queries)
    bm25_results = list(
        client.search(
            search_text=bm25_text,
            top=fetch_top,
            filter=filter_str,
            select=select_fields,
            # Sin vector_queries
        )
    )
    
    # 3. Hybrid RRF (ambos)
    hybrid_results = []
    search_kwargs = {
        "search_text": bm25_text,
        "top": fetch_top,
        "filter": filter_str,
        "select": select_fields,
    }
    if query_vector is not None:
        vector_query_obj = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=k_for_vector,
            fields="embedding",
        )
        search_kwargs["vector_queries"] = [vector_query_obj]
    
    hybrid_results = list(client.search(**search_kwargs))
    
    # Calcular métricas de overlap
    vector_ids = {r.get("id") for r in vector_results[:10]}
    bm25_ids = {r.get("id") for r in bm25_results[:10]}
    hybrid_ids = [r.get("id") for r in hybrid_results[:10]]  # Mantener orden
    
    # Chunks del top-10 RRF que venían del top-10 vector
    overlap_v_to_rrf = sum(1 for chunk_id in hybrid_ids if chunk_id in vector_ids)
    
    # Chunks del top-10 RRF que SOLO estaban en top-10 BM25 (no en vector)
    unique_bm25 = sum(
        1 for chunk_id in hybrid_ids
        if chunk_id in bm25_ids and chunk_id not in vector_ids
    )
    
    metrics = {
        "overlap_v_to_rrf": overlap_v_to_rrf,
        "unique_bm25": unique_bm25,
        "bm25_contribution_rate": unique_bm25 / 10.0 if hybrid_ids else 0.0,
        "total_hybrid_top10": len(hybrid_ids),
    }
    
    # Loguear resultados detallados
    logger.info(
        "bm25_impact_analysis_results",
        query=query[:60],
        vector_top10=[
            {"id": r.get("id", "")[:40], "score": float(r.get("@search.score") or 0)}
            for r in vector_results[:10]
        ],
        bm25_top10=[
            {"id": r.get("id", "")[:40], "score": float(r.get("@search.score") or 0)}
            for r in bm25_results[:10]
        ],
        hybrid_top10=[
            {"id": r.get("id", "")[:40], "score": float(r.get("@search.score") or 0)}
            for r in hybrid_results[:10]
        ],
        metrics=metrics,
    )
    
    return {
        "vector_only": vector_results,
        "bm25_only": bm25_results,
        "hybrid_rrf": hybrid_results,
        "metrics": metrics,
    }


def _get_select_fields() -> list[str]:
    """Reutiliza la lógica de select fields del módulo principal."""
    from infra.ports.azure_search import _search_chunk_select_fields
    return _search_chunk_select_fields()
