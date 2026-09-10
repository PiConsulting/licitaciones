"""Recuperación de chunks candidatos desde AI Search con boost/penalty por categoría."""
from __future__ import annotations

from typing import Any

import structlog

from analysis.extraction.engine.citation_grounding import (
    _normalize_for_grounding,
)
from analysis.extraction.engine.llm_judge import llm_judge_rerank
from analysis.extraction.engine.reranking import rerank_chunks
from infra.config import get_settings
from infra.ports.pgvector_search import search_hybrid

logger = structlog.get_logger(__name__)

# FIX (2026-09-08): costo de inferencia del cross-encoder de reranking,
# medido en este entorno (CPU, cross-encoder/mmarco-mMiniLMv2-L12-H384-v1).
# Aislado (thread principal, modelo cargado, sin nada más corriendo) escala
# lineal a ~0.045s/par. Pero a través del ThreadPoolExecutor que usa
# `rerank_chunks` en la práctica, con contención real (varios workers de
# `EXTRACTION_MAX_CONCURRENCY` rerankeando en simultáneo), se midieron
# tiempos bastante más altos y variables para el mismo trabajo (hasta ~2x).
# Se usa un valor conservador -- calculado con margen, no el número de
# laboratorio limpio -- para no repetir el problema original (un guardrail
# calibrado contra condiciones ideales que en la práctica salta casi
# siempre). Se usa para calcular cuántos candidatos entran de forma segura
# en `rag_reranking_timeout_seconds` -- ver el guardrail de
# `rerank_skip_threshold` más abajo.
_RERANK_SECONDS_PER_PAIR = 0.09  # ~2x el 0.045s/par aislado, con margen para contención real


def _chunk_identity(chunk: dict[str, Any]) -> tuple[str, int]:
    return (str(chunk.get("document_id", "")), int(chunk.get("chunk_index", 0) or 0))


_NEIGHBOR_SEED_LIMIT = 10  # solo se expanden los N seeds más fuertes
_NEIGHBOR_MAX_ADDED = 12  # tope duro de chunks rescatados por consulta


def _heading_key(chunk: dict[str, Any]) -> tuple[str, ...] | None:
    hp = chunk.get("heading_path") or []
    # se exige >=2 niveles: el nivel 1 suele ser el título del documento y lo
    # comparten decenas de chunks -- expandir por ahí traería medio pliego.
    if len(hp) < 2:
        return None
    return (str(chunk.get("document_id", "")), *[str(h) for h in hp])


def _expand_neighbors(
    ranked_chunks: list[dict[str, Any]], top_k: int, window: int
) -> list[dict[str, Any]]:
    """Expansión ESTRUCTURAL: para los `_NEIGHBOR_SEED_LIMIT` chunks más
    fuertes del top_k, trae del pool todos los chunks que comparten su
    `heading_path` exacto (misma subsección), insertándolos detrás del seed.
    No hace fetch a la DB -- solo reordena `ranked_chunks`; el corte `[:top_k]`
    de aguas abajo hace que los rescatados desplacen a los más débiles.

    Recupera subsecciones partidas en muchos chunks consecutivos (ej.
    'Artículo 16.1 CLASES: a) ... b) ... c) ...' en 9 chunks, donde el scoring
    por RRF/categoría solo destaca 2-3). `window` se conserva por
    compatibilidad de firma pero ya no se usa (la expansión es por sección).
    """
    del window
    if len(ranked_chunks) <= top_k:
        return ranked_chunks

    seeds = ranked_chunks[:top_k]
    seed_ids = {id(c) for c in seeds}

    by_heading: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for chunk in ranked_chunks:
        key = _heading_key(chunk)
        if key is not None:
            by_heading.setdefault(key, []).append(chunk)

    result: list[dict[str, Any]] = []
    added_ids: set[int] = set()
    rescued = 0

    def _push(chunk: dict[str, Any]) -> None:
        if id(chunk) not in added_ids:
            added_ids.add(id(chunk))
            result.append(chunk)

    for rank, chunk in enumerate(seeds):
        _push(chunk)
        if rank >= _NEIGHBOR_SEED_LIMIT or rescued >= _NEIGHBOR_MAX_ADDED:
            continue
        key = _heading_key(chunk)
        if key is None:
            continue
        for sibling in by_heading.get(key, ()):
            if id(sibling) in seed_ids or id(sibling) in added_ids:
                continue
            if rescued >= _NEIGHBOR_MAX_ADDED:
                break
            _push(sibling)
            rescued += 1

    for chunk in ranked_chunks:
        _push(chunk)
    return result


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
    # `secondary_categories` (clasificador mono-label) se puebla con densidad
    # de keywords >= 0.12 -- umbral bajísimo, muy propenso a falsos positivos
    # (un chunk que menciona "oferta"/"presentación" una vez queda con
    # `anexos` en secondary y, con el boost binario, saltaba al puesto #1).
    # El match SECUNDARIO recibe un boost menor que el primario.
    SECONDARY_BOOST_FACTOR = 1.0 + 0.4 * category_boost  # 0.50 → 1.20
    PENALTY_FACTOR = 1.0 - category_penalty  # 0.30 → 0.70

    # Boost graduado desde `category_scores` (reindex C+D). Opt-in por
    # categoría en glossary.json (`graded_category_scores: true`) -- medido:
    # ayuda a categorías con gold disperso, perjudica a las de gold limpio.
    from analysis.extraction.glossary import (
        get_category_graded_scores,
        get_category_rank_fusion,
    )

    use_graded_scores = get_category_graded_scores(category)
    use_rank_fusion = get_category_rank_fusion(category)

    # --- Rank-fusion (Causa 2 de la auditoría de ranking, 2026-09-09) -------
    # Los scores RRF crudos están comprimidos (0.0164 → 0.0091 en 50 chunks);
    # un boost multiplicativo sobre ese campo plano no separa un gold con
    # señal de categoría clara de un chunk-ruido con RRF apenas mayor. La
    # rank-fusion le da a la señal de categoría su PROPIO ranking y lo fusiona
    # por posición (RRF, scale-free) con el ranking híbrido:
    #   final = 1/(K + rank_híbrido) + W · 1/(K + rank_categoría)
    if use_rank_fusion:
        RRF_K = 60
        W_CAT = 1.0

        def _cat_signal(chunk: dict[str, Any]) -> float:
            prim = chunk.get("primary_category")
            sec = chunk.get("secondary_categories", [])
            binary = (
                1.0 if prim == category
                else 0.55 if category in sec
                else 0.15 if not prim or prim == "sin_categoria"
                else 0.0
            )
            cs = 0.0
            if use_graded_scores:
                cs = float((chunk.get("category_scores") or {}).get(category, 0.0) or 0.0)
            return max(binary, cs)

        hybrid_rank = {id(ch): i for i, ch in enumerate(candidates)}
        by_cat = sorted(candidates, key=_cat_signal, reverse=True)
        cat_rank = {id(ch): i for i, ch in enumerate(by_cat)}

        scored_chunks = []
        cat_matches = 0
        for chunk in candidates:
            hr = hybrid_rank[id(chunk)]
            cr = cat_rank[id(chunk)]
            fused = 1.0 / (RRF_K + hr + 1) + W_CAT / (RRF_K + cr + 1)
            chunk["retrieval_score"] = fused
            if _cat_signal(chunk) >= 0.5:
                cat_matches += 1
            scored_chunks.append((fused, chunk))
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        return scored_chunks, cat_matches, 0
    # ---------------------------------------------------------------------

    scored_chunks: list[tuple[float, dict]] = []
    category_match_count = 0
    category_mismatch_count = 0

    for rank, chunk in enumerate(candidates):
        base_score = chunk.get("search_score")
        if base_score is None:
            base_score = 1.0 / (rank + 1)

        primary_category = chunk.get("primary_category")
        secondary_categories = chunk.get("secondary_categories", [])

        is_primary_match = primary_category == category
        is_secondary_match = (not is_primary_match) and category in secondary_categories
        matches = is_primary_match or is_secondary_match
        match_factor = BOOST_FACTOR if is_primary_match else SECONDARY_BOOST_FACTOR

        if use_graded_scores:
            category_scores = chunk.get("category_scores") or {}
            graded_score = float(category_scores.get(category, 0.0) or 0.0)
            graded_factor = 1.0 + category_boost * graded_score  # 1.0 → 1.50
            if matches:
                # Match limpio: no se diluye el boost binario (primario o
                # secundario según corresponda).
                adjusted_score = base_score * max(match_factor, graded_factor)
                category_match_count += 1
            elif graded_score >= 0.1:
                # Chunk multi-categoría con señal parcial -> lift graduado,
                # sin penalty. Recupera gold que el clasificador mono-label
                # mandó a otra categoría.
                adjusted_score = base_score * graded_factor
                if graded_score >= 0.3:
                    category_match_count += 1
            elif primary_category and primary_category != "sin_categoria":
                adjusted_score = base_score * PENALTY_FACTOR
                category_mismatch_count += 1
            else:
                adjusted_score = base_score
        elif matches:
            adjusted_score = base_score * match_factor
            category_match_count += 1
        elif primary_category and primary_category != "sin_categoria":
            adjusted_score = base_score * PENALTY_FACTOR
            category_mismatch_count += 1
        else:
            adjusted_score = base_score

        # Se persiste el score ajustado para que los pasos posteriores
        # (corte por relevancia, telemetría, debugging) no pierdan la señal
        # de priorización por categoría.
        chunk["retrieval_score"] = adjusted_score
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

    if use_shared_pool and pool_scored and settings.shared_candidate_pool_augment_on_roundtrip:
        # Fusionar con el pool compartido: dedup por chunk id, quedándose con
        # el mejor score de las dos fuentes (pueden diferir si el mismo chunk
        # aparece en ambos con distinto rank/score de origen).
        # NOTA (2026-09-10): esta fusión cuesta ~-0.021 de recall efectivo sin
        # ahorrar el roundtrip -- con `shared_candidate_pool_augment_on_roundtrip`
        # en false se salta y el pool solo aporta cuando reemplaza la query.
        combined: dict[str, tuple[float, dict]] = {}
        for score, chunk in [*pool_scored, *scored_chunks]:
            chunk_id = chunk.get("id")
            if chunk_id is None:
                continue
            existing = combined.get(chunk_id)
            if existing is None or score > existing[0]:
                combined[chunk_id] = (score, chunk)
        merged_scored = sorted(combined.values(), key=lambda x: x[0], reverse=True)
        ranked_chunks = [chunk for _score, chunk in merged_scored]
    else:
        ranked_chunks = [chunk for _score, chunk in scored_chunks]

    if settings.rag_neighbor_expansion_enabled:
        before = len(ranked_chunks[:top_k])
        ranked_chunks = _expand_neighbors(
            ranked_chunks, top_k, settings.rag_neighbor_expansion_window
        )
        logger.info(
            "neighbor_expansion_applied",
            correlation_id=correlation_id,
            category=category,
            window=settings.rag_neighbor_expansion_window,
            top_k_before=before,
            pool_after=len(ranked_chunks),
        )

    # Experimental (2026-09-10): reranking por LLM-as-judge. Toma precedencia
    # sobre el cross-encoder (son experimentos mutuamente excluyentes). Fallback
    # seguro al orden RRF dentro de `llm_judge_rerank`.
    if settings.rag_llm_judge_enabled:
        w = min(len(ranked_chunks), settings.rag_llm_judge_window)
        judged = llm_judge_rerank(
            query, category, ranked_chunks[:w], correlation_id=correlation_id
        )
        ranked_chunks = [*judged, *ranked_chunks[w:]]

    # Historia 22.5: insertar reranking semántico real entre el scoring
    # híbrido actual y el corte final top_k. Se limita la ventana para que
    # el costo de CPU sea acotado en categorías con over-fetch alto.
    rerank_window = min(len(ranked_chunks), top_k * 2)

    # Historia 23.4: guardrail para evitar timeouts del cross-encoder en
    # ventanas muy grandes -- prioriza estabilidad/latencia sobre intentar un
    # reranking condenado a expirar, y conserva el orden RRF ya scoreado por
    # categoría en ese caso.
    # FIX (2026-09-08): el guardrail original comparaba `len(ranked_chunks)`
    # -- el pool CRUDO, hasta `over_fetch_k = top_k * 3` -- contra un umbral
    # derivado de ese mismo pool, en vez de comparar contra `rerank_window`
    # (arriba), que es lo que en realidad se le manda al cross-encoder. Con
    # top_k=35 (la mayoría de las categorías tras la auditoría de retrieval
    # de esta sesión) el pool crudo llega habitualmente a 105 y el umbral
    # viejo daba 63, así que el reranking se salteaba casi siempre aunque
    # `rerank_window` (70 para top_k=35) estuviera muy por debajo de lo que
    # el modelo soporta. El umbral ahora se deriva del presupuesto real de
    # `rag_reranking_timeout_seconds` y del costo medido de
    # `_RERANK_SECONDS_PER_PAIR`, y se compara contra `rerank_window`.
    rerank_skip_threshold = max(
        top_k, int(settings.rag_reranking_timeout_seconds / _RERANK_SECONDS_PER_PAIR)
    )
    if not settings.rag_reranking_enabled:
        final_chunks = ranked_chunks[:top_k]
        logger.info(
            "reranking_disabled",
            correlation_id=correlation_id,
            category=category,
            candidates=len(ranked_chunks),
            returned=len(final_chunks),
            strategy="keep_rrf_order",
        )
    elif rerank_window > rerank_skip_threshold:
        final_chunks = ranked_chunks[:top_k]
        logger.info(
            "reranking_skipped_window_too_large",
            correlation_id=correlation_id,
            category=category,
            candidates=len(ranked_chunks),
            rerank_window=rerank_window,
            threshold=rerank_skip_threshold,
            returned=len(final_chunks),
            strategy="keep_rrf_order",
        )
    else:
        final_chunks = rerank_chunks(
            query,
            ranked_chunks[:rerank_window],
            top_k=min(top_k, rerank_window),
        )

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
