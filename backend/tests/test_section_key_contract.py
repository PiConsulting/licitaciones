from __future__ import annotations

import inspect

from extraction.chunking import _SECTION_PATTERNS, create_chunks
from shared.ports import azure_search

SECCIONES_EMITIDAS = {key for key, _ in _SECTION_PATTERNS} | {"general"}


def test_chunker_solo_emite_secciones_estructurales() -> None:
    pages = [
        {"page_number": 1, "content": "Capitulo 1 - Objeto\nArticulo 1 - Texto del objeto.\na) inciso"},
        {"page_number": 2, "content": "Anexo I - Planilla\nTexto libre sin encabezado."},
    ]
    chunks = create_chunks(pages, "doc", "corr")
    emitidas = {chunk["section_key"] for chunk in chunks}
    assert emitidas <= SECCIONES_EMITIDAS, f"section_key inesperada: {emitidas - SECCIONES_EMITIDAS}"


def test_preferencias_de_categoria_apuntan_a_secciones_reales() -> None:
    for categoria, preferidas in azure_search.CATEGORY_SECTION_PREFERENCE.items():
        desconocidas = set(preferidas) - SECCIONES_EMITIDAS
        assert not desconocidas, f"{categoria} referencia secciones que el chunker no emite: {desconocidas}"


def test_search_local_no_filtra_por_section_key() -> None:
    fuente = inspect.getsource(azure_search._search_local)
    where_segment = fuente.split("where=", maxsplit=1)[1].split(")", maxsplit=1)[0]
    assert '"section_key"' not in where_segment, "_search_local no debe filtrar por section_key"
