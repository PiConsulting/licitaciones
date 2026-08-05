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
        return []

    import chromadb
    from sentence_transformers import SentenceTransformer

    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(name="analysis_chunks")
    model = SentenceTransformer(settings.sentence_transformers_model)
    query_embedding = model.encode([query], normalize_embeddings=True)[0].tolist()

    where_filter: dict = {"analysis_id": analysis_id}
    if section_key:
        where_filter["section_key"] = section_key

    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_filter,
        include=["metadatas", "documents", "distances"],
    )

    metadatas = result.get("metadatas", [[]])[0]
    documents = result.get("documents", [[]])[0]

    chunks: list[dict] = []
    for metadata, content in zip(metadatas, documents, strict=False):
        raw_table_ref = metadata.get("table_ref")
        table_ref = None
        if isinstance(raw_table_ref, str) and raw_table_ref:
            try:
                table_ref = json.loads(raw_table_ref)
            except json.JSONDecodeError:
                table_ref = None

        chunks.append(
            {
                "analysis_id": metadata.get("analysis_id"),
                "document_id": metadata.get("document_id"),
                "page_number": int(metadata.get("page_number", 0)),
                "chunk_index": int(metadata.get("chunk_index", 0)),
                "section_key": metadata.get("section_key", "general"),
                "section_path": metadata.get("section_path", metadata.get("section_key", "general")),
                "section_level": int(metadata.get("section_level", 0) or 0),
                "block_type": metadata.get("block_type", "paragraph"),
                "table_ref": table_ref,
                "content": content,
            }
        )
    return chunks


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

    def _run_query(filters: list[str], search_text: str) -> list[dict]:
        search_kwargs = {
            "search_text": search_text,
            "top": top_k,
            "filter": " and ".join(filters),
        }
        select_fields = _search_chunk_select_fields()
        if select_fields:
            search_kwargs["select"] = select_fields
        return list(client.search(**search_kwargs))

    scoped_filters = [f"analysis_id eq '{analysis_id}'"]
    if section_key:
        scoped_filters.append(f"section_key eq '{section_key}'")

    analysis_filter = [f"analysis_id eq '{analysis_id}'"]

    raw_results = _run_query(scoped_filters, query)
    if section_key and not raw_results:
        logger.info(
            "azure_search_section_fallback",
            analysis_id=analysis_id,
            section_key=section_key,
            query=query,
        )
        raw_results = _run_query(analysis_filter, query)

    if not raw_results:
        logger.info(
            "azure_search_wildcard_fallback",
            analysis_id=analysis_id,
            section_key=section_key,
            query=query,
        )
        raw_results = _run_query(analysis_filter, "*")

    chunks: list[dict] = []
    for item in raw_results:
        chunks.append(
            {
                "analysis_id": item.get("analysis_id"),
                "document_id": item.get("document_id"),
                "page_number": int(item.get("page_number", 0)),
                "chunk_index": int(item.get("chunk_index", 0)),
                "section_key": item.get("section_key", "general"),
                "section_path": item.get("section_path", item.get("section_key", "general")),
                "section_level": int(item.get("section_level", 0) or 0),
                "block_type": item.get("block_type", "paragraph"),
                "table_ref": item.get("table_ref"),
                "content": item.get("content", ""),
            }
        )
    return chunks


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
