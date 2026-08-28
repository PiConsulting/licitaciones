from __future__ import annotations

from collections.abc import Callable

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from infra.database import _build_engine

logger = structlog.get_logger(__name__)

# Constante estándar de RRF (misma que usa Azure AI Search internamente en su
# fusión nativa). No es un parámetro a calibrar -- es la convención del
# algoritmo (Cormack et al. 2009).
RRF_K = 60

# ÉPICA 22.4 -- recalibrado del `MIN_SCORE_SMALL_ANALYSIS = 0.032` de Azure
# (pensado para su score coseno 0-1) al nuevo rango de scores RRF.
#
# Derivación: con `k=RRF_K=60`, el score de un chunk que aparece en SOLO una
# de las dos señales (vector o texto) a la posición MEDIANA de una ventana de
# `fetch_top=30` (el piso que usa `search_hybrid` para análisis chicos) es
# `1/(60 + 15) = 0.0133`. Un chunk así -- señal única y mediocre, ni siquiera
# entre los primeros puestos de una sola lista -- es justo el tipo de "ruido"
# que el filtro de Azure buscaba cortar en corpus chicos. `0.01` queda
# levemente por debajo de ese punto (conservador: prioriza no perder
# información real sobre limpiar agresivo), consistente con el comentario
# original de Azure ("mejor contexto de más que de menos"). Sin dataset real
# de evaluación todavía (Historia 22.13) -- valor a revisar empíricamente ahí.
MIN_SCORE_SMALL_ANALYSIS = 0.01
_SMALL_ANALYSIS_THRESHOLD = 50

SEARCH_CHUNK_COLUMNS = (
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
    "blocks",
    "source",
    "content",
    "chunk_type",
    "parent_chunk_id",
    "child_chunk_ids",
)

_COLUMNS_SQL = ", ".join(f"c.{col}" for col in SEARCH_CHUNK_COLUMNS)


def _session_factory() -> Callable[[], Session]:
    engine = _build_engine()
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


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


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def _row_to_chunk(row: dict, hybrid_score: float | None = None) -> dict:
    if hybrid_score is None:
        hybrid_score = float(row.get("rrf_score") or 0.0)
    return {
        "id": row.get("id"),
        "analysis_id": row.get("analysis_id"),
        "document_id": row.get("document_id"),
        "page_number": int(row.get("page_number") or 0),
        "chunk_index": int(row.get("chunk_index") or 0),
        "heading_path": list(row.get("heading_path") or []),
        "heading_level": int(row.get("heading_level") or 0),
        "section_path": row.get("section_path") or "general",
        "block_type": row.get("block_type") or "paragraph",
        "table_ref": row.get("table_ref"),
        "blocks": row.get("blocks"),
        "source": row.get("source"),
        "primary_category": row.get("primary_category"),
        "secondary_categories": list(row.get("secondary_categories") or []),
        "content": row.get("content") or "",
        "search_score": hybrid_score,
        "chunk_type": row.get("chunk_type") or "normal",
        "parent_chunk_id": row.get("parent_chunk_id"),
        "child_chunk_ids": list(row.get("child_chunk_ids") or []),
    }


_RRF_QUERY_WITH_VECTOR = text(
    f"""
    WITH vector_results AS (
        SELECT id, row_number() OVER (
            ORDER BY embedding::halfvec(3072) <=> CAST(:query_vector AS halfvec(3072))
        ) AS rank_v
        FROM chunks
        WHERE analysis_id = :analysis_id
        ORDER BY embedding::halfvec(3072) <=> CAST(:query_vector AS halfvec(3072))
        LIMIT :side_limit
    ),
    text_results AS (
        SELECT id, row_number() OVER (
            ORDER BY ts_rank_cd(content_tsv, plainto_tsquery('spanish', :query_text)) DESC, id
        ) AS rank_t
        FROM chunks
        WHERE analysis_id = :analysis_id
          AND content_tsv @@ plainto_tsquery('spanish', :query_text)
        ORDER BY rank_t
        LIMIT :side_limit
    )
    SELECT {_COLUMNS_SQL},
           COALESCE(1.0 / (:rrf_k + v.rank_v), 0) + COALESCE(1.0 / (:rrf_k + t.rank_t), 0) AS rrf_score
    FROM chunks c
    LEFT JOIN vector_results v ON v.id = c.id
    LEFT JOIN text_results t ON t.id = c.id
    WHERE v.id IS NOT NULL OR t.id IS NOT NULL
    ORDER BY rrf_score DESC, c.id
    LIMIT :fetch_top
    """
)

_RRF_QUERY_TEXT_ONLY = text(
    f"""
    WITH text_results AS (
        SELECT id, row_number() OVER (
            ORDER BY ts_rank_cd(content_tsv, plainto_tsquery('spanish', :query_text)) DESC, id
        ) AS rank_t
        FROM chunks
        WHERE analysis_id = :analysis_id
          AND content_tsv @@ plainto_tsquery('spanish', :query_text)
        ORDER BY rank_t
        LIMIT :side_limit
    )
    SELECT {_COLUMNS_SQL},
           COALESCE(1.0 / (:rrf_k + t.rank_t), 0) AS rrf_score
    FROM chunks c
    JOIN text_results t ON t.id = c.id
    ORDER BY rrf_score DESC, c.id
    LIMIT :fetch_top
    """
)


def _run_rrf_query(
    db: Session,
    *,
    analysis_id: str,
    query_vector: list[float] | None,
    query_text_value: str,
    side_limit: int,
    fetch_top: int,
) -> list[dict]:
    params = {
        "analysis_id": str(analysis_id),
        "query_text": query_text_value,
        "side_limit": side_limit,
        "fetch_top": fetch_top,
        "rrf_k": RRF_K,
    }
    if query_vector is not None:
        params["query_vector"] = _vector_literal(query_vector)
        result = db.execute(_RRF_QUERY_WITH_VECTOR, params)
    else:
        result = db.execute(_RRF_QUERY_TEXT_ONLY, params)

    return [dict(row._mapping) for row in result]


_PARENT_LOOKUP_QUERY = text(f"SELECT {_COLUMNS_SQL} FROM chunks c WHERE c.id = ANY(:parent_ids)")


def _fetch_parents_by_id(db: Session, parent_ids: list[str]) -> dict[str, dict]:
    if not parent_ids:
        return {}
    result = db.execute(_PARENT_LOOKUP_QUERY, {"parent_ids": parent_ids})
    parents: dict[str, dict] = {}
    for row in result:
        row_dict = dict(row._mapping)
        parents[str(row_dict["id"])] = row_dict

    missing = [parent_id for parent_id in parent_ids if parent_id not in parents]
    if missing:
        logger.warning(
            "parent_chunks_not_found",
            missing_count=len(missing),
            requested=len(parent_ids),
            sample=missing[:3],
        )
    return parents


def _expand_children_to_parents(db: Session, chunks: list[dict]) -> list[dict]:
    """Expande cada chunk "child" matcheado a su chunk "parent" completo.

    Reescritura de `infra/ports/azure_search.py::_expand_children_to_parents`
    contra Postgres -- misma lógica de dedup simétrico (RET-01): un chunk
    "parent" ya visto (sea porque llegó directo, sea porque otro child con
    mejor score ya lo expandió) nunca se duplica en el resultado final.
    """
    needed_parent_ids: list[str] = []
    for chunk in chunks:
        if chunk.get("chunk_type") != "child":
            continue
        parent_id = chunk.get("parent_chunk_id")
        if parent_id and parent_id not in needed_parent_ids:
            needed_parent_ids.append(str(parent_id))

    parents_by_id = _fetch_parents_by_id(db, needed_parent_ids)

    expanded: list[dict] = []
    seen_parent_ids: set[str] = set()

    for chunk in chunks:
        chunk_type = chunk.get("chunk_type")

        if chunk_type == "parent":
            chunk_id = chunk.get("id")
            if chunk_id and chunk_id in seen_parent_ids:
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
            continue

        parent_row = parents_by_id.get(parent_id)
        if parent_row is None:
            logger.warning(
                "parent_chunk_expansion_failed",
                parent_chunk_id=parent_id,
                child_chunk_id=chunk.get("id"),
                reason="el parent no se pudo resolver en la búsqueda por lote",
            )
            expanded.append(chunk)
            continue

        parent_chunk = _row_to_chunk(parent_row, hybrid_score=chunk.get("search_score"))
        parent_chunk["matched_child_chunk_id"] = chunk.get("id")
        parent_chunk["matched_child_content"] = chunk.get("content")
        seen_parent_ids.add(parent_id)
        expanded.append(parent_chunk)

    return expanded


def search_hybrid(
    query: str,
    analysis_id: str,
    top_k: int = 10,
    keyword_query: str | None = None,
    category: str | None = None,  # Epic 11: para caché de embeddings
) -> list[dict]:
    """Recupera chunks relevantes para una categoría, filtrados por analysis_id.

    Reemplazo de `infra/ports/azure_search.py::search_hybrid` contra Postgres
    + pgvector: fusión RRF (Reciprocal Rank Fusion, k=60) de un ranking
    vectorial (`embedding <=> query_vector`, vía índice HNSW sobre `halfvec`)
    y un ranking de texto completo nativo (`ts_rank_cd` + `plainto_tsquery`),
    en vez de kNN de Azure + BM25 (real o local aproximado). Mismo contrato
    de salida que la versión Azure -- `chunk_retrieval.py` no cambia.

    No hay filtro por categoría (mismo comportamiento que antes): la
    categoría es señal de ranking (`chunk_retrieval.py`), no compuerta.
    """
    fetch_top = max(top_k * 2, 30)
    side_limit = min(max(top_k * 3, 30), 1000)

    query_vector = _embed_query_or_none(query, analysis_id=analysis_id, category=category)
    text_query = keyword_query or query

    session_factory = _session_factory()
    with session_factory() as db:
        raw_rows = _run_rrf_query(
            db,
            analysis_id=analysis_id,
            query_vector=query_vector,
            query_text_value=text_query,
            side_limit=side_limit,
            fetch_top=fetch_top,
        )

        if not raw_rows:
            if query_vector is None:
                logger.error(
                    "pgvector_search_embedding_failed_critical",
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
            logger.error(
                "pgvector_search_analysis_sin_chunks",
                analysis_id=analysis_id,
                query=query[:120],
                reason=(
                    "la búsqueda híbrida RRF no devolvió ningún documento con este "
                    "analysis_id: el análisis no está indexado"
                ),
            )
            raise RuntimeError(
                f"Análisis {analysis_id} no tiene chunks indexados — "
                f"búsqueda híbrida devolvió 0 resultados para query '{query[:60]}...'"
            )

        ranked_chunks = [_row_to_chunk(row) for row in raw_rows]

        # ÉPICA 22.4 (paridad con Épica 10 de Azure): con análisis pequeños
        # (< 50 chunks recuperados), la fusión RRF no discrimina bien -- ver
        # derivación de MIN_SCORE_SMALL_ANALYSIS arriba.
        total_chunks_available = len(ranked_chunks)
        if total_chunks_available < _SMALL_ANALYSIS_THRESHOLD:
            logger.warning(
                "retrieval_small_analysis_detected",
                analysis_id=analysis_id,
                total_chunks=total_chunks_available,
                query=query[:60],
            )
            before_filter = len(ranked_chunks)
            ranked_chunks = [
                chunk
                for chunk in ranked_chunks
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

        expansion_window = ranked_chunks[: max(top_k * 2, top_k)]
        expanded_chunks = _expand_children_to_parents(db, expansion_window)

    return expanded_chunks[:top_k]


# Tope de seguridad para `fetch_all_analysis_chunks` -- protege contra un
# analysis_id corrupto trayendo una tabla entera a memoria. A diferencia de
# Azure, Postgres no tiene continuation tokens ni límite artificial de
# paginación: esto es sólo una guarda defensiva, no una limitación del motor.
_MAX_ENUMERABLE_CHUNKS = 50_000
_ENUMERATION_PAGE_SIZE = 1000

_ENUMERATE_QUERY = text(
    f"""
    SELECT {_COLUMNS_SQL} FROM chunks c
    WHERE c.analysis_id = :analysis_id
    ORDER BY c.id
    LIMIT :limit OFFSET :offset
    """
)


def fetch_all_analysis_chunks(analysis_id: str) -> tuple[list[dict], bool]:
    """Enumera TODOS los chunks de un análisis (sin expansión children->parent
    -- se quiere el índice tal cual está, ver docstring de la versión Azure).

    Returns:
        (chunks, truncated) -- `truncated` es True si se alcanzó el tope de
        seguridad, para que el llamador pueda avisar en vez de degradar en
        silencio.
    """
    session_factory = _session_factory()
    chunks: list[dict] = []
    truncated = False

    with session_factory() as db:
        offset = 0
        while True:
            rows = db.execute(
                _ENUMERATE_QUERY,
                {"analysis_id": str(analysis_id), "limit": _ENUMERATION_PAGE_SIZE, "offset": offset},
            ).fetchall()
            if not rows:
                break
            for row in rows:
                if len(chunks) >= _MAX_ENUMERABLE_CHUNKS:
                    truncated = True
                    break
                chunks.append(_row_to_chunk(dict(row._mapping), hybrid_score=0.0))
            if truncated or len(rows) < _ENUMERATION_PAGE_SIZE:
                break
            offset += _ENUMERATION_PAGE_SIZE

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
