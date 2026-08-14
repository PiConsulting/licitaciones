"""Una categoría entera no puede perderse por UN item mal formado.

Caso real (análisis del 2026-08-14): `requisitos_admisibilidad` volvió con
`[]` y `extraction_status: "failed"`, mientras las otras siete categorías
salieron bien. `"failed"` con lista vacía sólo se escribe en un lugar --el
`except` de `run_extractor`--, así que fue una excepción dentro del nodo.

Estos tests cubren las dos excepciones que un solo item podía provocar, y que
costaban las 30 afirmaciones de la categoría:

  1. `"source_references": null` -> `list(None)` -> TypeError.
     El prompt lo induce: "`not_found` -- los fragmentos no mencionan el dato +
     SIN cita".
  2. `"page_number": "3-4"` -> `int("3-4")` -> ValueError.
     Aparece cuando la cita cruza dos páginas del pliego.

`requisitos_admisibilidad` es la categoría con más items (su prompt pide "un
item por requisito, y si vienen en incisos, uno por inciso"), así que es la que
más chances tenía de que uno saliera raro.
"""

from __future__ import annotations

from typing import Any

import pytest

from analysis.extraction.extractors.base import (
    _as_page_number,
    _normalize_item,
    _verify_citation_grounding,
)


def _chunk(content: str, page: int = 4) -> dict[str, Any]:
    return {
        "id": "an-1--doc-1--3",
        "document_id": "doc-1",
        "page_number": page,
        "content": content,
        "block_type": "paragraph",
    }


CITA = "Constancia de inscripción en el Registro Único de Proveedores vigente"


# ---------------------------------------------------------------------------
# 1. source_references raro
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("refs", [None, "no es una lista", 3, {"document_id": "doc-1"}])
def test_source_references_no_lista_no_lanza(refs) -> None:
    item = _normalize_item({"valor": "x", "confidence": 0.5, "source_references": refs})

    assert item["source_references"] == []


def test_los_refs_validos_de_una_lista_mixta_se_conservan() -> None:
    """Un ref malo entre varios buenos no puede llevarse los buenos puestos."""
    bueno = {"document_id": "doc-1", "page_number": 4, "citation": CITA}
    item = _normalize_item(
        {"valor": "x", "confidence": 0.9, "source_references": [bueno, None, "texto suelto", 7]}
    )

    assert item["source_references"] == [bueno]


# ---------------------------------------------------------------------------
# 2. page_number raro
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (3, 3),
        ("3", 3),
        (3.0, 3),
        ("3-4", 3),
        ("12 y 13", 12),
        ("pág. 7", 7),
        ("s/n", 0),
        ("", 0),
        (None, 0),
        (True, 0),
    ],
)
def test_el_numero_de_pagina_tolera_lo_que_emita_el_llm(valor, esperado) -> None:
    assert _as_page_number(valor) == esperado


def test_un_ref_con_pagina_rara_no_tumba_la_verificacion() -> None:
    """El item tiene dos refs: uno con `page_number` inservible y uno válido.
    Antes, el primero lanzaba ValueError y se perdía la categoría entera."""
    item = {
        "valor": "Constancia RUP",
        "extraction_status": "success",
        "source_references": [
            {"document_id": "doc-1", "page_number": "3-4", "citation": CITA},
            {"document_id": "doc-1", "page_number": 4, "citation": CITA},
        ],
    }

    _verify_citation_grounding(
        [item], [_chunk(f"{CITA}.")], category="requisitos_admisibilidad", correlation_id="c1"
    )

    assert item["extraction_status"] == "success"
    assert len(item["source_references"]) >= 1


def test_un_ref_que_no_es_dict_se_saltea() -> None:
    item = {
        "valor": "Constancia RUP",
        "extraction_status": "success",
        "source_references": [
            "esto no es un ref",
            {"document_id": "doc-1", "page_number": 4, "citation": CITA},
        ],
    }

    _verify_citation_grounding(
        [item], [_chunk(f"{CITA}.")], category="requisitos_admisibilidad", correlation_id="c1"
    )

    assert item["extraction_status"] == "success"


# ---------------------------------------------------------------------------
# 3. El techo de tokens de la respuesta
# ---------------------------------------------------------------------------


def test_el_tope_de_tokens_alcanza_para_una_categoria_larga() -> None:
    """Con 4000 tokens entraban ~25 items. `requisitos_admisibilidad` pide uno
    por requisito y uno por inciso: en un pliego real son 30-40. Pasado el
    tope, el JSON llega truncado y la categoría entera se pierde."""
    import inspect

    from shared.ports import azure_openai

    fuente = inspect.getsource(azure_openai.get_azure_openai_client)

    assert "max_tokens=12000" in fuente
    assert "timeout=180" in fuente
