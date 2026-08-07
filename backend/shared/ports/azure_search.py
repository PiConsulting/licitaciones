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
    "section_key",
    "section_path",
    "section_level",
    "block_type",
    "table_ref",
    "content",
    "chapter",
    "article",
    "anexo",
    "inciso",
    "title",
]

# Mapa de categoria semantica -> secciones estructurales del chunker.
# Se usa para boost de ranking, nunca como filtro excluyente.
CATEGORY_SECTION_PREFERENCE: dict[str, list[str]] = {
    "objeto_alcance": ["capitulos", "articulos"],
    "plazos": ["articulos", "capitulos"],
    "requisitos_admisibilidad": ["articulos", "incisos", "capitulos"],
    "garantias": ["articulos", "capitulos"],
    "causales_rechazo": ["articulos", "capitulos"],
    "anexos_obligatorios": ["anexos", "articulos"],
    "criterios_evaluacion": ["articulos", "capitulos"],
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
        chunk_section_key = item.get("section_key") or "general"
        chunks.append(
            {
                "analysis_id": item.get("analysis_id"),
                "document_id": item.get("document_id"),
                "page_number": int(item.get("page_number", 0)),
                "chunk_index": int(item.get("chunk_index", 0)),
                "section_key": chunk_section_key,
                "section_path": item.get("section_path") or chunk_section_key,
                "section_level": int(item.get("section_level") or 0),
                "block_type": item.get("block_type") or "paragraph",
                "table_ref": _deserialize_table_ref(item.get("table_ref")),
                "content": item.get("content", ""),
                "chapter": item.get("chapter") or None,
                "article": item.get("article") or None,
                "anexo": item.get("anexo") or None,
                "inciso": item.get("inciso") or None,
                "title": item.get("title") or None,
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
        from shared.ports.local.chroma_search import _search_local

        return _search_local(query=query, analysis_id=analysis_id, top_k=top_k, section_key=section_key)

    return _search_azure(query=query, analysis_id=analysis_id, top_k=top_k, section_key=section_key)
