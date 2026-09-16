"""Auditoría de chunking (Rosario, real): Document Intelligence partió un
heading en su propio MARKDOWN aunque su capa de layout (bbox/línea de OCR)
sabe que es una sola línea física.

Confirmado con el dato real (bbox crudo de la corrida real, tabla `chunks`):
el bloque de cuerpo que sigue a `"ARTÍCULO 12: PLA"` (heading, página 4) tiene
adjunta -- vía `_attach_lines_to_blocks`, por caer su bbox dentro de ella -- la
línea de OCR completa "ARTÍCULO 12: PLAZO DE ENTREGA", aunque su propio
`content` (derivado del markdown) es solo "ZO DE ENTREGA". No es la misma
causa que un heading cortado entre páginas (`headings.py`, que usa forma de
palabra) -- es una sola línea de DI que su heurística de estilo para el
markdown partió mal. La fuente de verdad es la línea real, no una heurística.
"""

from __future__ import annotations

from typing import Any

from indexing.document_intelligence.markdown_parsing import (
    _repair_heading_split_within_single_line,
)


def _heading(contenido: str, page: int, nivel: int = 1) -> dict[str, Any]:
    return {"content": contenido, "heading_level": nivel, "page_number": page}


def _parrafo(contenido: str, page: int, lines: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"content": contenido, "page_number": page, "lines": lines or []}


def _linea(texto: str) -> dict[str, Any]:
    return {"t": texto}


def test_reconstruye_el_heading_desde_la_linea_real_de_di() -> None:
    """Caso real de Rosario, con la línea de OCR real como fuente de verdad."""
    blocks = [
        _heading("ARTÍCULO 12: PLA", page=4),
        _parrafo(
            "ZO DE ENTREGA El plazo de entrega de los productos será como máximo de noventa "
            "(90) días corridos.",
            page=4,
            lines=[_linea("ARTÍCULO 12: PLAZO DE ENTREGA")],
        ),
    ]

    _repair_heading_split_within_single_line(blocks)

    assert blocks[0]["content"] == "ARTÍCULO 12: PLAZO DE ENTREGA"
    assert blocks[1]["content"] == (
        "El plazo de entrega de los productos será como máximo de noventa (90) días corridos."
    )


def test_no_toca_nada_si_no_hay_linea_de_di_adjunta() -> None:
    """Sin la evidencia de la línea real, no se adivina nada."""
    blocks = [
        _heading("ARTÍCULO 12: PLA", page=4),
        _parrafo("ZO DE ENTREGA El plazo de entrega...", page=4, lines=[]),
    ]

    _repair_heading_split_within_single_line(blocks)

    assert blocks[0]["content"] == "ARTÍCULO 12: PLA"
    assert blocks[1]["content"] == "ZO DE ENTREGA El plazo de entrega..."


def test_no_toca_nada_si_el_cuerpo_no_coincide_con_lo_que_falta_de_la_linea() -> None:
    """Guarda: si el cuerpo, tal como llegó, no es exactamente la cola de la
    línea real (ej. porque de verdad son dos cosas distintas), no se fusiona."""
    blocks = [
        _heading("ARTÍCULO 12: PLA", page=4),
        _parrafo(
            "Un párrafo cualquiera que no tiene nada que ver.",
            page=4,
            lines=[_linea("ARTÍCULO 12: PLAZO DE ENTREGA")],
        ),
    ]

    _repair_heading_split_within_single_line(blocks)

    assert blocks[0]["content"] == "ARTÍCULO 12: PLA"
    assert blocks[1]["content"] == "Un párrafo cualquiera que no tiene nada que ver."


def test_no_fusiona_un_heading_ya_completo() -> None:
    """Guarda: si el heading ya coincide exactamente con la línea real (no hay
    nada que reconstruir), no se toca -- evita falsos positivos con headings
    normales seguidos de un párrafo que por casualidad empieza igual."""
    blocks = [
        _heading("NOTA", page=2),
        _parrafo("Aclaraciones adicionales.", page=2, lines=[_linea("NOTA")]),
    ]

    _repair_heading_split_within_single_line(blocks)

    assert blocks[0]["content"] == "NOTA"
    assert blocks[1]["content"] == "Aclaraciones adicionales."


def test_no_fusiona_a_traves_de_una_tabla() -> None:
    blocks = [
        _heading("ARTÍCULO 12: PLA", page=4),
        {
            "content": "col_1: Item",
            "page_number": 4,
            "table_ref": {"table_id": "T1"},
            "lines": [_linea("ARTÍCULO 12: PLAZO DE ENTREGA")],
        },
    ]

    _repair_heading_split_within_single_line(blocks)

    assert blocks[0]["content"] == "ARTÍCULO 12: PLA"


def test_no_fusiona_entre_paginas_distintas() -> None:
    """Este mecanismo es específicamente para el caso de UNA sola línea de DI
    -- por definición, misma página. El caso entre páginas ya lo cubre
    `chunking/headings.py::_merge_truncated_headings_across_pages`."""
    blocks = [
        _heading("ARTÍCULO 12: PLA", page=4),
        _parrafo(
            "ZO DE ENTREGA El plazo de entrega...",
            page=5,
            lines=[_linea("ARTÍCULO 12: PLAZO DE ENTREGA")],
        ),
    ]

    _repair_heading_split_within_single_line(blocks)

    assert blocks[0]["content"] == "ARTÍCULO 12: PLA"
    assert blocks[1]["content"] == "ZO DE ENTREGA El plazo de entrega..."
