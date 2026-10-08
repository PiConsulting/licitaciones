# Regresión (auditoría RAG Fase 2, 2026-09-16, `backend/debug/rag-audit/
# fase2-generacion-2026-09-16.md`): confirmado con un experimento controlado
# que el LLM omite `valor` en una fracción real de las corridas de garantías
# -- incluso con un solo chunk limpio y sin ruido, dos corridas seguidas del
# mismo prompt dieron resultados distintos (no-determinismo de muestreo, no
# falta de información ni de instrucción). Reforzar la instrucción en el
# prompt para TODO status se probó y tuvo un efecto secundario negativo
# (indujo al LLM a partir un mismo hecho en dos ítems -- medido en
# extraction_eval.py: wrong_rate 0.211->0.292 sobre los 8 pliegos golden).
# Se revirtió el prompt y se agregó este fallback determinístico en código en
# su lugar: compone `valor` a partir de lo que el ítem ya trae, sin depender
# de que el LLM recuerde la instrucción cada corrida.
from __future__ import annotations

from analysis.extraction.engine.normalization import (
    _compose_garantia_valor,
    _fill_missing_valor_for_garantias,
)


def test_compone_desde_monto_porcentaje_y_forma_constitucion() -> None:
    item = {
        "tipo": "mantenimiento_oferta",
        "valor": None,
        "monto_porcentaje": 1.0,
        "base_calculo": "presupuesto oficial",
        "forma_constitucion": "póliza de seguro de caución",
    }
    valor = _compose_garantia_valor(item)
    assert valor is not None
    assert valor.startswith("Garantía de Mantenimiento de Oferta:")
    assert "1.0% de presupuesto oficial" in valor
    assert "mediante póliza de seguro de caución" in valor


def test_compone_desde_monto_valor_y_moneda() -> None:
    item = {
        "tipo": "cumplimiento_contrato",
        "monto_valor": 500000.0,
        "moneda": "ARS",
    }
    valor = _compose_garantia_valor(item)
    assert valor == "Garantía de Cumplimiento de Contrato: ARS 500000.0"


def test_sin_campos_estructurados_usa_la_cita_verificada() -> None:
    """El caso de exención (not_applicable): no hay monto porque la garantía
    no corresponde -- el único dato útil es la condición, ya citada."""
    item = {
        "tipo": "mantenimiento_oferta",
        "source_references": [
            {
                "citation": "no resulta necesario presentar la garantía de "
                "oferta cuando el monto no supere $40.000.000"
            }
        ],
    }
    valor = _compose_garantia_valor(item)
    assert valor == (
        "Garantía de Mantenimiento de Oferta: no resulta necesario presentar "
        "la garantía de oferta cuando el monto no supere $40.000.000"
    )


def test_sin_nada_para_componer_devuelve_none() -> None:
    item = {"tipo": "otra", "source_references": []}
    assert _compose_garantia_valor(item) is None


def test_tipo_no_mapeado_usa_fallback_generico_del_enum() -> None:
    item = {"tipo": "algo_nuevo", "monto_porcentaje": 3.0}
    valor = _compose_garantia_valor(item)
    assert valor == "Algo nuevo: 3.0%"


def test_fill_missing_valor_no_pisa_valor_ya_presente() -> None:
    items = [
        {"tipo": "anticipo", "valor": "Ya viene completo por el LLM", "monto_porcentaje": 5.0}
    ]
    result = _fill_missing_valor_for_garantias(items)
    assert result[0]["valor"] == "Ya viene completo por el LLM"


def test_fill_missing_valor_completa_solo_los_vacios() -> None:
    items = [
        {"tipo": "anticipo", "valor": "", "monto_porcentaje": 5.0},
        {"tipo": "impugnacion", "valor": "  ", "monto_porcentaje": 3.0},
        {"tipo": "otra", "valor": None},
    ]
    result = _fill_missing_valor_for_garantias(items)
    assert result[0]["valor"] == "Anticipo Financiero: 5.0%"
    assert result[1]["valor"] == "Garantía de Impugnación: 3.0%"
    assert result[2]["valor"] is None  # nada de qué componer -- no inventa


def test_fill_missing_valor_ignora_items_no_dict() -> None:
    items = [{"tipo": "anticipo", "valor": None, "monto_porcentaje": 5.0}, "no_es_dict"]  # type: ignore[list-item]
    result = _fill_missing_valor_for_garantias(items)
    assert result[0]["valor"] == "Anticipo Financiero: 5.0%"
    assert result[1] == "no_es_dict"
