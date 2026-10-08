# Regresión (2026-09-14): tipos SINGLETON de objeto_alcance pueden salir duplicados de lotes distintos (uno con dato real, otro placeholder) y el dedup por valor exacto no los detecta.
from __future__ import annotations

from analysis.extraction.engine.item_merging import _merge_singleton_tipo_duplicates


def _item(tipo: str, valor: str, **extra: object) -> dict:
    return {"tipo": tipo, "valor": valor, "confidence": 0.8, **extra}


def test_placeholder_se_descarta_a_favor_del_dato_real() -> None:
    items = [
        _item("lugar_entrega", "El plazo y lugar de entrega es según el Pliego de Especificaciones Técnicas"),
        _item("lugar_entrega", "No especificado en los fragmentos recuperados"),
        _item("resumen_objeto", "Concurso privado de precios para la adquisición de una solución integral"),
    ]

    result = _merge_singleton_tipo_duplicates(
        items, {"resumen_objeto", "lugar_entrega"}, category="objeto_alcance", correlation_id="corr-1"
    )

    lugar_entrega = [i for i in result if i["tipo"] == "lugar_entrega"]
    assert len(lugar_entrega) == 1
    assert "Pliego de Especificaciones" in lugar_entrega[0]["valor"]
    assert "No especificado" not in lugar_entrega[0]["valor"]


def test_tipo_no_singleton_no_se_toca() -> None:
    """'item' (uno por renglón) no está en el set de singleton -- debe poder
    repetirse sin que esta función lo colapse."""
    items = [
        _item("item", "Renglón 1: notebooks"),
        _item("item", "Renglón 2: monitores"),
    ]

    result = _merge_singleton_tipo_duplicates(
        items, {"resumen_objeto", "lugar_entrega"}, category="objeto_alcance", correlation_id="corr-2"
    )

    assert len(result) == 2


def test_sin_duplicados_no_cambia_nada() -> None:
    items = [_item("resumen_objeto", "Único resumen")]

    result = _merge_singleton_tipo_duplicates(
        items, {"resumen_objeto"}, category="objeto_alcance", correlation_id="corr-3"
    )

    assert result == items


def test_todos_placeholder_conserva_uno_en_vez_de_perder_el_tipo() -> None:
    items = [
        _item("lugar_entrega", "No especificado en los fragmentos"),
        _item("lugar_entrega", "No se especifica en el pliego"),
    ]

    result = _merge_singleton_tipo_duplicates(
        items, {"lugar_entrega"}, category="objeto_alcance", correlation_id="corr-4"
    )

    assert len(result) == 1
