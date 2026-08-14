"""Tests del contrato de índice de Azure AI Search.

REGRESIÓN IDX-01 / IDX-02 / IDX-06 (auditoría 2026-08-13).

`_assert_index_contract` es la última defensa contra el drift entre el schema
que el código asume y el índice real. Dos veces falló en ese rol:

  - primero con `primary_category` / `secondary_categories` (US-4.2), que
    quedaron fuera del índice y el filtro por categoría nunca matcheó;
  - después con `chunk_type` / `parent_chunk_id` / `child_chunk_ids` (IDX-06),
    que quedaron fuera y toda la funcionalidad parent/child quedó inerte.

En los dos casos el arranque pasó limpio y la degradación fue silenciosa.
"""
from __future__ import annotations

import pytest

from extraction.ai_search import _assert_index_contract


class _Field:
    def __init__(
        self,
        name: str,
        *,
        searchable: bool = False,
        filterable: bool = False,
        analyzer_name: str | None = None,
        vector_search_dimensions: int | None = None,
    ) -> None:
        self.name = name
        self.searchable = searchable
        self.filterable = filterable
        self.analyzer_name = analyzer_name
        self.vector_search_dimensions = vector_search_dimensions


class _Index:
    def __init__(self, fields: list[_Field]) -> None:
        self.fields = fields


def _valid_fields(**overrides) -> list[_Field]:
    """Índice que cumple el contrato -- el que produce create_search_index.py."""
    spec: dict[str, _Field] = {
        "analysis_id": _Field("analysis_id", filterable=True),
        "document_id": _Field("document_id", filterable=True),
        "page_number": _Field("page_number", filterable=True),
        "chunk_index": _Field("chunk_index", filterable=True),
        "content": _Field("content", searchable=True, analyzer_name="es.microsoft"),
        "title": _Field("title", searchable=True, analyzer_name="es.microsoft"),
        "section_path": _Field("section_path", searchable=True, analyzer_name="es.microsoft"),
        "heading_path": _Field("heading_path", searchable=True, analyzer_name="es.microsoft"),
        "primary_category": _Field("primary_category", filterable=True),
        "secondary_categories": _Field("secondary_categories", filterable=True),
        "chunk_type": _Field("chunk_type", filterable=True),
        "parent_chunk_id": _Field("parent_chunk_id", filterable=True),
        "child_chunk_ids": _Field("child_chunk_ids"),
        "embedding": _Field("embedding", searchable=True, vector_search_dimensions=3072),
    }
    spec.update(overrides)
    return [field for field in spec.values() if field is not None]


def test_indice_correcto_pasa_el_contrato() -> None:
    _assert_index_contract(_Index(_valid_fields()), expected_dimensions=3072)


@pytest.mark.parametrize("campo", ["chunk_type", "parent_chunk_id", "child_chunk_ids"])
def test_falta_de_campos_parent_child_tumba_el_arranque(campo: str) -> None:
    """IDX-06: era exactamente este drift el que dejaba la US-3.1 inerte."""
    fields = [f for f in _valid_fields() if f.name != campo]

    with pytest.raises(RuntimeError, match=campo):
        _assert_index_contract(_Index(fields), expected_dimensions=3072)


@pytest.mark.parametrize("campo", ["content", "title", "section_path", "heading_path"])
def test_campo_de_texto_no_searchable_tumba_el_arranque(campo: str) -> None:
    """IDX-01: el índice real tenía title/section_path/heading_path en False."""
    fields = _valid_fields(**{campo: _Field(campo, searchable=False, analyzer_name="es.microsoft")})

    with pytest.raises(RuntimeError, match="searchable"):
        _assert_index_contract(_Index(fields), expected_dimensions=3072)


@pytest.mark.parametrize("analyzer", [None, "standard.lucene", "en.microsoft"])
def test_analizador_no_espanol_tumba_el_arranque(analyzer: str | None) -> None:
    """IDX-02: el índice real tenía `content` con analyzer=null."""
    fields = _valid_fields(content=_Field("content", searchable=True, analyzer_name=analyzer))

    with pytest.raises(RuntimeError, match="analizador español"):
        _assert_index_contract(_Index(fields), expected_dimensions=3072)


@pytest.mark.parametrize("analyzer", ["es.microsoft", "es.lucene"])
def test_ambos_analizadores_espanoles_son_aceptados(analyzer: str) -> None:
    fields = _valid_fields(
        content=_Field("content", searchable=True, analyzer_name=analyzer),
        title=_Field("title", searchable=True, analyzer_name=analyzer),
        section_path=_Field("section_path", searchable=True, analyzer_name=analyzer),
        heading_path=_Field("heading_path", searchable=True, analyzer_name=analyzer),
    )
    _assert_index_contract(_Index(fields), expected_dimensions=3072)


def test_dimensiones_de_embedding_incompatibles_tumban_el_arranque() -> None:
    fields = _valid_fields(
        embedding=_Field("embedding", searchable=True, vector_search_dimensions=1536)
    )

    with pytest.raises(RuntimeError, match="dimensions"):
        _assert_index_contract(_Index(fields), expected_dimensions=3072)


def test_el_schema_del_script_de_creacion_cumple_el_contrato() -> None:
    """El script y el contrato no pueden divergir: si `create_search_index.py`
    produjera un índice que `_assert_index_contract` rechaza, el sistema no
    arrancaría después de una migración."""
    from scripts.create_search_index import build_index

    index = build_index("documents-index", 3072)
    _assert_index_contract(index, expected_dimensions=3072)


def test_el_script_declara_exactamente_los_campos_que_el_codigo_escribe() -> None:
    """Un campo declarado y no escrito queda siempre en null; uno escrito y no
    declarado se descarta en silencio. Las dos cosas ya pasaron en este índice."""
    import re
    from pathlib import Path

    from scripts.create_search_index import build_index

    source = Path(__file__).resolve().parents[1] / "extraction" / "ai_search.py"
    text = source.read_text(encoding="utf-8")
    block = text[text.index("documents.append(") : text.index("retries = settings.azure_search_retry_attempts")]
    written = set(re.findall(r'^\s*"(\w+)":', block, re.M))
    declared = {field.name for field in build_index("documents-index", 3072).fields}

    assert written - declared == set(), f"el código escribe campos que el schema no declara: {sorted(written - declared)}"
    assert declared - written == set(), f"el schema declara campos que el código nunca escribe: {sorted(declared - written)}"
