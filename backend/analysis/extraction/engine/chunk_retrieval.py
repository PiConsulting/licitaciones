"""Recuperación de chunks candidatos desde AI Search con boost/penalty por categoría."""
from __future__ import annotations

from typing import Any

import structlog

from analysis.extraction.engine.citation_grounding import (
    _normalize_for_grounding,
)
from infra.config import get_settings
from infra.ports.pgvector_search import search_hybrid

logger = structlog.get_logger(__name__)


def _chunk_identity(chunk: dict[str, Any]) -> tuple[str, int]:
    return (str(chunk.get("document_id", "")), int(chunk.get("chunk_index", 0) or 0))


def _attach_chunk_identity(ref: dict[str, Any], chunk: dict[str, Any] | None) -> None:
    """Anota en la `source_reference` de qué chunk salió la evidencia."""
    if chunk is None:
        return

    chunk_id = chunk.get("id") or chunk.get("chunk_id")
    if chunk_id:
        ref["chunk_id"] = str(chunk_id)

    if ref.get("block_id"):
        return

    citation_normalized = _normalize_for_grounding(ref.get("citation", ""))
    if not citation_normalized:
        return

    source = chunk.get("source")
    blocks = source.get("blocks", []) if isinstance(source, dict) else (chunk.get("blocks") or [])
    if not isinstance(blocks, list):
        return

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_text = str(block.get("text") or block.get("content") or "")
        if not block_text:
            continue
        if citation_normalized in _normalize_for_grounding(block_text):
            block_id = block.get("block_id") or block.get("para_id")
            if block_id is not None:
                ref["block_id"] = str(block_id)
            return


def _score_chunks_for_category(
    candidates: list[dict[str, Any]],
    category: str,
    category_boost: float,
    category_penalty: float,
) -> tuple[list[tuple[float, dict]], int, int]:
    """Aplica el boost/penalty de categoría a una lista de candidatos ya
    recuperados, sin volver a pegarle a Azure. Extraído de
    `_retrieve_with_category_priority` (Fase 3, plan RAG v2 2026-08-24,
    sección 4.2) para poder reusarlo tanto sobre los candidatos de la query
    específica de una categoría como sobre el candidate pool compartido de
    `setup_node` -- mismo criterio de scoring en los dos casos, una sola
    implementación.

    Returns:
        (scored_chunks ordenados desc, category_match_count, category_mismatch_count)
    """
    BOOST_FACTOR = 1.0 + category_boost  # 0.50 → 1.50
    PENALTY_FACTOR = 1.0 - category_penalty  # 0.30 → 0.70

    scored_chunks: list[tuple[float, dict]] = []
    category_match_count = 0
    category_mismatch_count = 0

    for rank, chunk in enumerate(candidates):
        base_score = chunk.get("search_score")
        if base_score is None:
            base_score = 1.0 / (rank + 1)

        primary_category = chunk.get("primary_category")
        secondary_categories = chunk.get("secondary_categories", [])

        # Determinar ajuste de score
        if primary_category == category or category in secondary_categories:
            # Match: boost
            adjusted_score = base_score * BOOST_FACTOR
            category_match_count += 1
        elif primary_category and primary_category != "sin_categoria":
            # Mismatch explícito: penalty
            adjusted_score = base_score * PENALTY_FACTOR
            category_mismatch_count += 1
        else:
            # Sin categoría asignada: neutro (no boost ni penalty)
            adjusted_score = base_score

        scored_chunks.append((adjusted_score, chunk))

    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    return scored_chunks, category_match_count, category_mismatch_count


def _purity_rate(chunks: list[dict[str, Any]], category: str) -> float:
    if not chunks:
        return 0.0
    target_chunks = sum(
        1
        for chunk in chunks
        if chunk.get("primary_category") == category
        or category in chunk.get("secondary_categories", [])
    )
    return target_chunks / len(chunks)


def _retrieve_with_category_priority(
    *,
    query: str,
    analysis_id: str,
    top_k: int,
    keyword_query: str | None,
    category: str,
    correlation_id: str,
    category_boost: float = 0.50,  # Aumentado de 0.20 a 0.50 (50% boost)
    category_penalty: float = 0.30,  # NUEVO: penalty para chunks de otras categorías
    global_candidates: list[dict[str, Any]] | None = None,  # FASE 3 (4.2)
) -> list[dict[str, Any]]:
    """Recupera chunks relevantes usando SCORING HÍBRIDO con boost Y penalty por categoría.

    FIX (2026-08-21): Agregado penalty para chunks de categorías incorrectas.
    El sistema anterior solo boosteaba matches (+20%), pero no penalizaba mismatches.
    Resultado: chunks de requisitos_admisibilidad con alta similitud vectorial
    ganaban sobre chunks de plazos_clave con boost.

    Ahora:
    - Chunks con categoría correcta: +50% score
    - Chunks SIN categoría (sin_categoria): score original (neutro)
    - Chunks con categoría INCORRECTA: -30% score

    FASE 3 (plan RAG v2, 2026-08-24, sección 4.2): si `global_candidates` viene
    poblado (setup_node lo llenó porque `USE_SHARED_CANDIDATE_POOL=true`), se
    intenta primero boostear/penalizar ESE pool para esta categoría, sin
    ningún round-trip a Azure. Si alcanza el `purity_rate` mínimo configurado
    con suficientes chunks, se devuelve directo -- ahorra la query específica
    por completo. Si no alcanza, se hace la query específica como siempre Y
    se fusiona con el pool (dedup por chunk id, se queda con el mejor score
    de las dos fuentes) -- el pool nunca resta información, en el peor caso
    no aporta nada nuevo. Con `global_candidates=None` (flag apagado, o
    `setup_node` no lo pudo poblar) el comportamiento es exactamente el de
    antes de esta fase.
    """
    settings = get_settings()
    use_shared_pool = bool(global_candidates) and settings.use_shared_candidate_pool

    pool_scored: list[tuple[float, dict]] = []
    if use_shared_pool:
        pool_scored, pool_match_count, pool_mismatch_count = _score_chunks_for_category(
            global_candidates, category, category_boost, category_penalty
        )
        pool_top = [chunk for _score, chunk in pool_scored[:top_k]]
        pool_purity = _purity_rate(pool_top, category)

        logger.info(
            "shared_candidate_pool_evaluated",
            correlation_id=correlation_id,
            category=category,
            pool_size=len(global_candidates),
            pool_matches=pool_match_count,
            pool_mismatches=pool_mismatch_count,
            pool_top_purity=round(pool_purity, 3),
            purity_threshold=settings.shared_candidate_pool_purity_threshold,
        )

        if len(pool_top) >= top_k and pool_purity >= settings.shared_candidate_pool_purity_threshold:
            logger.info(
                "shared_candidate_pool_reused_no_roundtrip",
                correlation_id=correlation_id,
                category=category,
                purity_rate=round(pool_purity, 3),
                chunks_returned=len(pool_top),
                reason="pool compartido ya alcanza el purity_rate mínimo -- se evita la query específica",
            )
            return pool_top

    over_fetch_k = top_k * 3

    # ÉPICA 11: Pasar category para caché determinista de embeddings
    all_candidates = search_hybrid(
        query=query,
        analysis_id=analysis_id,
        top_k=over_fetch_k,
        keyword_query=keyword_query,
        category=category,
    )

    if not all_candidates:
        if use_shared_pool and pool_scored:
            # Sin candidatos de la query específica (falla puntual, o el
            # análisis ya se enumeró completo antes) -- mejor devolver lo que
            # el pool compartido trajo, aunque no llegara al umbral de
            # pureza, que devolver una lista vacía.
            fallback_chunks = [chunk for _score, chunk in pool_scored[:top_k]]
            logger.warning(
                "retrieval_no_candidates_using_shared_pool_fallback",
                correlation_id=correlation_id,
                category=category,
                query=query[:120],
                chunks_from_pool=len(fallback_chunks),
            )
            return fallback_chunks

        logger.warning(
            "retrieval_no_candidates",
            correlation_id=correlation_id,
            category=category,
            query=query[:120],
        )
        return []

    scored_chunks, category_match_count, category_mismatch_count = _score_chunks_for_category(
        all_candidates, category, category_boost, category_penalty
    )

    if use_shared_pool and pool_scored:
        # Fusionar con el pool compartido: dedup por chunk id, quedándose con
        # el mejor score de las dos fuentes (pueden diferir si el mismo chunk
        # aparece en ambos con distinto rank/score de origen).
        combined: dict[str, tuple[float, dict]] = {}
        for score, chunk in [*pool_scored, *scored_chunks]:
            chunk_id = chunk.get("id")
            if chunk_id is None:
                continue
            existing = combined.get(chunk_id)
            if existing is None or score > existing[0]:
                combined[chunk_id] = (score, chunk)
        merged_scored = sorted(combined.values(), key=lambda x: x[0], reverse=True)
        final_chunks = [chunk for _score, chunk in merged_scored[:top_k]]
    else:
        final_chunks = [chunk for _score, chunk in scored_chunks[:top_k]]

    category_distribution: dict[str, int] = {}
    for chunk in final_chunks:
        primary = chunk.get("primary_category") or "sin_categoria"
        category_distribution[primary] = category_distribution.get(primary, 0) + 1

    target_chunks = sum(
        1
        for chunk in final_chunks
        if chunk.get("primary_category") == category
        or category in chunk.get("secondary_categories", [])
    )

    logger.info(
        "retrieval_hybrid_scoring",
        correlation_id=correlation_id,
        category=category,
        total_candidates=len(all_candidates),
        category_matches=category_match_count,
        category_mismatches=category_mismatch_count,
        final_chunks=len(final_chunks),
        target_chunks_in_final=target_chunks,
        category_distribution=category_distribution,
        strategy="hybrid_scoring_with_category_boost_and_penalty",
        category_boost_factor=f"+{category_boost:.0%}",
        category_penalty_factor=f"-{category_penalty:.0%}",
        merged_with_shared_pool=use_shared_pool and bool(pool_scored),
    )

    return final_chunks
