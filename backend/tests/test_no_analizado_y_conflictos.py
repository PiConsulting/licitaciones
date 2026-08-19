"""CTX-03 y CTX-04: dos formas de callar información que el sistema tiene.

  - CTX-03: cuatro campos del contrato (`documentos_requeridos`,
    `restricciones_participacion`, `cronograma_proceso`,
    `estimacion_presupuesto`) están hardcodeados a vacío con `not_found`. Pero
    ningún nodo del grafo los completa. `not_found` significa, en toda la UI,
    "el pliego no lo dice"; la verdad es "no lo buscamos". Para
    `estimacion_presupuesto` la diferencia es grave: un oferente puede concluir
    que el pliego no publica presupuesto oficial.

  - CTX-04: `merge_node` detecta contradicciones -- dos fechas para el mismo
    hito, dos montos para la misma garantía -- y las guarda en el estado. La
    síntesis nunca las recibía, así que la narrativa decía las dos cosas en dos
    bullets seguidos sin marcar que se contradicen. El sistema LO SABE y no lo
    dice.
"""

from __future__ import annotations

from typing import Any

from analysis.extraction.schemas import NOT_ANALYZED_STATUS, ExtractedData
from analysis.extraction.synthesis import _conflict_block


# ---------------------------------------------------------------------------
# CTX-03
# ---------------------------------------------------------------------------


def test_las_categorias_sin_extractor_no_dicen_no_encontrado() -> None:
    data = ExtractedData()

    for campo in (
        "documentos_extraction_status",
        "restricciones_extraction_status",
        "cronograma_extraction_status",
        "presupuesto_extraction_status",
    ):
        assert getattr(data, campo) == NOT_ANALYZED_STATUS, campo
        assert getattr(data, campo) != "not_found", campo


def test_el_estado_nuevo_es_distinguible_de_los_demas() -> None:
    """No puede colisionar con ningún estado existente: el frontend decide qué
    mostrar a partir de este string."""
    assert NOT_ANALYZED_STATUS not in {"success", "partial", "failed", "not_found", "not_applicable"}


def test_las_categorias_que_si_se_analizan_conservan_sus_estados() -> None:
    """Guarda: el cambio no puede tocar a las ocho categorías reales."""
    data = ExtractedData()

    assert data.garantias_extraction_status == "unknown"
    assert data.plazos_clave_extraction_status == "unknown"


# ---------------------------------------------------------------------------
# CTX-04
# ---------------------------------------------------------------------------


def _conflicto_de_garantias() -> dict[str, Any]:
    return {
        "category": "garantias",
        "tipo": "mantenimiento_oferta",
        "reason": "Montos diferentes en distintos documentos",
        "values": [
            {
                "valor": "1% del presupuesto oficial",
                "source_references": [{"document_id": "doc-1", "page_number": 4}],
            },
            {
                "valor": "5% del presupuesto oficial",
                "source_references": [{"document_id": "doc-2", "page_number": 1}],
            },
        ],
    }


def test_sin_conflictos_el_bloque_lo_dice_explicitamente() -> None:
    assert "sin contradicciones" in _conflict_block("garantias", []).lower()
    assert "sin contradicciones" in _conflict_block("garantias", None).lower()


def test_el_conflicto_llega_al_prompt_con_los_dos_valores() -> None:
    bloque = _conflict_block("garantias", [_conflicto_de_garantias()])

    assert "1% del presupuesto oficial" in bloque
    assert "5% del presupuesto oficial" in bloque
    assert "mantenimiento_oferta" in bloque


def test_el_conflicto_dice_donde_esta_cada_version() -> None:
    """Sin la página, la persona no puede ir a verificar cuál rige."""
    bloque = _conflict_block("garantias", [_conflicto_de_garantias()])

    assert "pág. 4" in bloque
    assert "pág. 1" in bloque


def test_cada_categoria_recibe_solo_sus_conflictos() -> None:
    """El redactor de garantías no tiene por qué enterarse de un conflicto de
    plazos: lo mencionaría fuera de lugar."""
    conflicto_plazos = {
        "category": "plazos",
        "tipo": "apertura_ofertas",
        "reason": "Fechas diferentes en distintos documentos",
        "values": [{"fecha": "2026-09-14"}, {"fecha": "2026-09-21"}],
    }

    bloque_garantias = _conflict_block("garantias", [conflicto_plazos])
    bloque_plazos = _conflict_block("plazos_clave", [conflicto_plazos])

    assert "sin contradicciones" in bloque_garantias.lower()
    assert "2026-09-14" in bloque_plazos


def test_el_nombre_de_la_categoria_de_conflicto_no_es_el_de_la_narrativa() -> None:
    """`merge_node` registra el conflicto bajo "plazos"; la narrativa se llama
    "plazos_clave". Sin el mapeo, los conflictos de plazos no llegaban nunca."""
    conflicto = {
        "category": "plazos",
        "tipo": "apertura_ofertas",
        "reason": "Fechas diferentes",
        "values": [{"fecha": "2026-09-14"}, {"fecha": "2026-09-21"}],
    }

    assert "sin contradicciones" not in _conflict_block("plazos_clave", [conflicto]).lower()


def test_el_prompt_de_sintesis_tiene_el_placeholder() -> None:
    """Si el placeholder no está, el bloque se calcula y se tira."""
    from analysis.extraction.synthesis import _load_response_base_prompt

    assert "{conflicts_block}" in _load_response_base_prompt()
