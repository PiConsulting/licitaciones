"""Encabezados que Document Intelligence corta al medio.

REGRESIÓN (auditoría 2026-08-13, hallazgo detectado sobre un análisis real).

Sobre el pliego de Licitación Privada de la Municipalidad de Rosario, DI emitió:

    heading  "Artículo Nº 10: GAR"
    párrafo  "ANTÍA DE ADJUDICACIÓN: En caso de corresponder, el importe de las
              garantías de la contratación y otras que se estipulen..."

Ni el título ni el cuerpo contienen la palabra "garantía", así que el artículo
era invisible para BM25 y para el vector. La categoría `garantias` respondió
`not_applicable` -- "el pliego sólo prevé garantía técnica del equipamiento,
ninguna financiera" -- sobre un pliego cuyo Artículo 10 se titula GARANTÍA DE
ADJUDICACIÓN. Es una respuesta legal incorrecta, no un resaltado corrido.

`_merge_split_headings_across_pages` no lo cubría: exige dos encabezados en
páginas consecutivas, y acá la segunda mitad es cuerpo en la misma página.
"""
from __future__ import annotations

from extraction.chunking import create_chunks


def _bbox(page: int, y: float, height: float) -> list[dict]:
    return [{"page": page, "x": 0.77, "y": y, "width": 6.7, "height": height}]


def _heading(text: str, *, page: int, order: int, y: float, height: float = 0.17) -> dict:
    return {
        "page_number": page,
        "block_type": "paragraph",
        "content": text,
        "source_order": order,
        "table_ref": None,
        "heading_level": 2,
        "bbox": _bbox(page, y, height),
    }


def _para(text: str, *, page: int, order: int, y: float, height: float = 0.99) -> dict:
    return {
        "page_number": page,
        "block_type": "paragraph",
        "content": text,
        "source_order": order,
        "table_ref": None,
        "bbox": _bbox(page, y, height),
    }


def _chunks(blocks: list[dict]) -> list[dict]:
    return create_chunks(blocks, document_id="doc-1", correlation_id="corr-1")


_GARANTIAS_BODY = (
    "ANTÍA DE ADJUDICACIÓN: En caso de corresponder, el importe de las garantías de "
    "la contratación y otras que se estipulen deberán ajustarse cada vez que se verifique "
    "un incremento igual o mayor al veinte por ciento (20%) en la cotización de la moneda "
    "extranjera ofertada."
)


def test_reconstruye_el_articulo_de_garantias_del_pliego_real() -> None:
    blocks = [
        _heading("Artículo Nº 10: GAR", page=4, order=0, y=7.5798),
        _para(_GARANTIAS_BODY, page=4, order=1, y=7.5798),
    ]

    chunks = _chunks(blocks)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["title"] == "Artículo Nº 10: GARANTÍA DE ADJUDICACIÓN"
    # El cuerpo queda limpio, sin la cola del título.
    assert chunk["content"].startswith("En caso de corresponder")
    assert "ANTÍA" not in chunk["content"]


def test_la_categoria_garantias_deja_de_ser_invisible() -> None:
    """El efecto que importa: el chunk pasa a clasificarse como garantías."""
    blocks = [
        _heading("Artículo Nº 10: GAR", page=4, order=0, y=7.5798),
        _para(_GARANTIAS_BODY, page=4, order=1, y=7.5798),
    ]

    chunk = _chunks(blocks)[0]

    assert chunk["primary_category"] == "garantias", (
        f"quedó clasificado como {chunk['primary_category']!r}: el artículo de garantías "
        "sigue siendo invisible para el retrieval"
    )


def test_cola_de_titulo_sin_cuerpo_se_absorbe_en_el_encabezado() -> None:
    """El otro caso del mismo pliego: "ARTÍCULO 12: PLA" + "ZO DE ENTREGA"."""
    blocks = [
        _heading("ARTÍCULO 12: PLA", page=4, order=0, y=9.8477),
        _para("ZO DE ENTREGA", page=4, order=1, y=9.8477, height=0.16),
        _para(
            "El plazo de entrega de los productos será como máximo de noventa (90) días "
            "corridos a partir de la recepción de la Orden de Provisión.",
            page=5,
            order=0,
            y=1.6475,
        ),
    ]

    chunks = _chunks(blocks)

    assert len(chunks) == 1
    assert chunks[0]["title"] == "ARTÍCULO 12: PLAZO DE ENTREGA"
    assert chunks[0]["content"].startswith("El plazo de entrega")


def test_corte_en_limite_de_palabra_se_une_con_espacio() -> None:
    blocks = [
        _heading("ARTÍCULO 5: PLAZOS", page=2, order=0, y=3.0),
        _para("DE ENTREGA: Los plazos se cuentan en días corridos desde la orden.", page=2, order=1, y=3.0),
    ]

    chunk = _chunks(blocks)[0]

    assert chunk["title"] == "ARTÍCULO 5: PLAZOS DE ENTREGA"


# ---------------------------------------------------------------------------
# Falsos positivos: lo que NO se debe fusionar
# ---------------------------------------------------------------------------


def test_no_fusiona_un_parrafo_que_arranca_en_otra_linea() -> None:
    """Caso normal: el cuerpo empieza debajo del encabezado, no al lado."""
    blocks = [
        _heading("ARTÍCULO 13: DEL PAGO", page=5, order=0, y=3.0, height=0.17),
        _para("NOTA: La Municipalidad de Rosario pagará en moneda de curso legal.", page=5, order=1, y=3.4),
    ]

    chunk = _chunks(blocks)[0]

    assert chunk["title"] == "ARTÍCULO 13: DEL PAGO"
    assert chunk["content"].startswith("NOTA:")


def test_no_fusiona_cuando_el_cuerpo_esta_en_otra_pagina() -> None:
    blocks = [
        _heading("Artículo 6: DOCUMENTACIÓN A PRESENTAR", page=2, order=0, y=1.5),
        _para("NOTA: Se informa que de acuerdo con lo dispuesto en el Decreto 1259/24...", page=3, order=0, y=1.5),
    ]

    chunk = _chunks(blocks)[0]

    assert chunk["title"] == "Artículo 6: DOCUMENTACIÓN A PRESENTAR"
    assert chunk["content"].startswith("NOTA:")


def test_no_fusiona_cuerpo_en_minusculas_aunque_este_en_la_misma_linea() -> None:
    """Un run-in normal ("Artículo 7: FORMA DE COTIZAR Los oferentes deberán...")
    no es un título cortado: la cola tendría minúsculas."""
    blocks = [
        _heading("Artículo 7: FORMA DE COTIZAR", page=3, order=0, y=4.19),
        _para("Los oferentes deberán cotizar incluyendo en el precio el IVA: por ser exenta.", page=3, order=1, y=4.19),
    ]

    chunk = _chunks(blocks)[0]

    assert chunk["title"] == "Artículo 7: FORMA DE COTIZAR"
    assert chunk["content"].startswith("Los oferentes")


def test_sin_bbox_no_fusiona_nada() -> None:
    """Sin la evidencia estructural preferimos no tocar el encabezado."""
    blocks = [
        {
            "page_number": 4,
            "block_type": "paragraph",
            "content": "Artículo Nº 10: GAR",
            "source_order": 0,
            "table_ref": None,
            "heading_level": 2,
            "bbox": [],
        },
        {
            "page_number": 4,
            "block_type": "paragraph",
            "content": _GARANTIAS_BODY,
            "source_order": 1,
            "table_ref": None,
            "bbox": [],
        },
    ]

    chunk = _chunks(blocks)[0]

    assert chunk["title"] == "Artículo Nº 10: GAR"


def test_no_fusiona_un_encabezado_con_una_tabla() -> None:
    blocks = [
        _heading("ARTÍCULO 9: ADJUDICACIÓN", page=4, order=0, y=4.6),
        {
            "page_number": 4,
            "block_type": "table",
            "content": "col_1: Item\ncol_2: Cantidad",
            "source_order": 1,
            "row_order": 0,
            "table_ref": {"table_id": "T1", "row_index": 1, "headers": ["col_1", "col_2"]},
            "bbox": _bbox(4, 4.6, 0.5),
        },
    ]

    chunks = _chunks(blocks)

    assert chunks[0]["title"] == "ARTÍCULO 9: ADJUDICACIÓN"
    assert chunks[0]["block_type"] == "table"
