from __future__ import annotations

import structlog

from shared.config import get_settings
from shared.ports.azure_search import (
    _deserialize_table_ref,
    _preferred_sections,
    _section_bonus,
    _token_overlap_score,
)

logger = structlog.get_logger(__name__)


def _search_local(
    query: str,
    analysis_id: str,
    top_k: int,
    section_key: str | None,
) -> list[dict]:
    settings = get_settings()
    from pathlib import Path

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
                    # LocalChromaSearchAdapter guarda "" en vez de None (Chroma no
                    # acepta None en metadata) -- se normaliza de vuelta a None acá
                    # para que el contrato de salida sea igual al de Azure.
                    "chapter": metadata.get("chapter") or None,
                    "article": metadata.get("article") or None,
                    "anexo": metadata.get("anexo") or None,
                    "inciso": metadata.get("inciso") or None,
                    "title": metadata.get("title") or None,
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
