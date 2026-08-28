"""Reranking semántico local (cross-encoder) -- Historia 22.5.

Retoma el diseño (nunca implementado) de la Story 2.18, adaptado a un modelo
local vía `sentence-transformers` en vez de un proveedor externo pago: corre
100% en CPU, sin llamadas de red.

Punto de inserción previsto (cuando una historia futura conecte el pipeline
completo sobre pgvector): entre `infra.ports.pgvector_search.search_hybrid`
(Historia 22.4) y `chunk_retrieval.py::_score_chunks_for_category` -- ver
Dev Notes de la Historia 22.5. Este módulo se construye y testea standalone,
sin modificar `chunk_retrieval.py`, mismo patrón que 22.3/22.4.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from functools import lru_cache
from typing import Any

import structlog

from infra.config import get_settings

logger = structlog.get_logger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="reranker")


@lru_cache(maxsize=1)
def _load_model(model_name: str):
    from sentence_transformers import CrossEncoder

    logger.info("reranker_model_loading", model=model_name)
    return CrossEncoder(model_name)


def _predict_scores(model_name: str, pairs: list[tuple[str, str]]) -> list[float]:
    model = _load_model(model_name)
    return [float(score) for score in model.predict(pairs)]


def rerank_chunks(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    top_k: int,
    model_name: str | None = None,
    timeout_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """Reordena `chunks` (ya recuperados por `search_hybrid`, orden RRF) por
    relevancia semántica real vía cross-encoder, y devuelve los `top_k`
    mejores (AC2).

    Contrato de salida estable (AC4): cada elemento sigue siendo el mismo
    dict de chunk que entró, sin agregar ni quitar keys -- solo cambia el
    orden/subset.

    Fallback seguro (AC3): si el flag está apagado, no hay chunks, el modelo
    falla al cargar/inferir, o se excede `timeout_seconds`, se devuelve
    `chunks[:top_k]` tal cual (orden RRF sin rerankear) -- nunca interrumpe
    el pipeline de extracción.
    """
    settings = get_settings()
    if not settings.rag_reranking_enabled or not chunks:
        return chunks[:top_k]

    model_name = model_name or settings.rag_reranking_model
    timeout_seconds = (
        timeout_seconds if timeout_seconds is not None else settings.rag_reranking_timeout_seconds
    )
    pairs = [(query, str(chunk.get("content") or "")) for chunk in chunks]

    started = time.monotonic()
    try:
        future = _executor.submit(_predict_scores, model_name, pairs)
        scores = future.result(timeout=timeout_seconds)
    except FutureTimeoutError:
        elapsed = time.monotonic() - started
        logger.warning(
            "reranking_timeout_fallback_to_rrf_order",
            model=model_name,
            timeout_seconds=timeout_seconds,
            elapsed_seconds=round(elapsed, 3),
            candidates=len(chunks),
        )
        return chunks[:top_k]
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "reranking_failed_fallback_to_rrf_order",
            model=model_name,
            error=str(exc)[:200],
            candidates=len(chunks),
        )
        return chunks[:top_k]

    elapsed = time.monotonic() - started
    scored = sorted(zip(scores, chunks, strict=True), key=lambda pair: pair[0], reverse=True)
    reranked = [chunk for _score, chunk in scored[:top_k]]

    logger.info(
        "reranking_applied",
        model=model_name,
        candidates=len(chunks),
        returned=len(reranked),
        elapsed_seconds=round(elapsed, 3),
    )
    return reranked
