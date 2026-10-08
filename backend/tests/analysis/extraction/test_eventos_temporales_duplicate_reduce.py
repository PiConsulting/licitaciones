"""Tests para `_consolidate_duplicates_via_llm`
(`analysis/extraction/extractors/eventos_temporales.py`).

Pendiente #4 de `eventos-temporales-auditoria-completa-2026-09-21`: duplicados
con nombres COMPLETAMENTE distintos entre sí ("Apertura de Ofertas"/"Acto de
Apertura") no los resuelve ningún tier de similitud de texto sin arriesgar
falsos positivos ("Adjudicación"/"Preadjudicación"). Este paso reemplaza esa
idea por un llamado LLM dedicado que ve todos los nombres+citas juntos y
decide semánticamente cuáles son la misma ocurrencia -- estos tests mockean
`_call_llm` (mismo patrón que `test_synthesis.py`) para no depender de una
llamada real.
"""
from __future__ import annotations

import pytest

from analysis.extraction.extractors.eventos_temporales import (
    _consolidate_duplicates_via_llm,
)


def _hito(nombre: str, fragmento: str, **overrides) -> dict:
    defaults = {
        "nombre": nombre,
        "fecha_explicita": None,
        "origen_fecha": "pendiente",
        "evento_disparador": None,
        "cantidad": None,
        "unidad": None,
        "tipo_dias": None,
        "direccion": None,
        "es_plazo_maximo": False,
        "mencion_propia": True,
        "accion_concreta": f"se produce la acción de {nombre}",
        "es_ocurrencia_unica": True,
        "depende_de_decision_discrecional": False,
        "fuente_documento_id": "doc-1",
        "fuente_pagina": 1,
        "fuente_fragmento": fragmento,
        "extraction_status": "success",
    }
    defaults.update(overrides)
    return defaults


def test_fusiona_el_grupo_que_devuelve_el_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    items = [
        _hito("Apertura de Ofertas", "El acto de apertura se realizará el 10/03."),
        _hito("Acto de Apertura", "La apertura de las ofertas será pública."),
        _hito("Adjudicación", "La adjudicación se notificará por cédula."),
    ]

    def fake_call_llm(messages, correlation_id=None):
        return ({"grupos": [[0, 1]]}, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})

    monkeypatch.setattr(
        "analysis.extraction.extractors.eventos_temporales._call_llm", fake_call_llm
    )

    result = _consolidate_duplicates_via_llm(items, correlation_id="test")

    assert len(result) == 2
    nombres = {item["nombre"] for item in result}
    assert "Adjudicación" in nombres
    merged = next(item for item in result if item["nombre"] != "Adjudicación")
    # Se conserva el nombre del ítem con fecha explícita si el otro no la tiene.
    assert merged["nombre"] in {"Apertura de Ofertas", "Acto de Apertura"}


def test_no_fusiona_si_el_llm_no_devuelve_grupos(monkeypatch: pytest.MonkeyPatch) -> None:
    items = [
        _hito("Adjudicación", "La adjudicación se notificará por cédula."),
        _hito("Preadjudicación", "La preadjudicación se publicará en la web."),
    ]

    def fake_call_llm(messages, correlation_id=None):
        return ({"grupos": []}, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})

    monkeypatch.setattr(
        "analysis.extraction.extractors.eventos_temporales._call_llm", fake_call_llm
    )

    result = _consolidate_duplicates_via_llm(items, correlation_id="test")

    assert len(result) == 2


def test_ignora_un_grupo_que_fusionaria_disparador_con_su_dependiente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aunque el LLM sugiera fusionarlos, nunca se fusiona un disparador con
    su propio dependiente -- protección explícita, igual que en
    `_consolidate_duplicate_hitos` (la versión por similitud de texto,
    descartada) y en `_merge_enumerated_fragment_duplicates`."""
    items = [
        _hito("Adjudicación", "La entrega se hará 45 días desde la Adjudicación."),
        _hito(
            "Entrega del Equipamiento",
            "La entrega se hará 45 días desde la Adjudicación.",
            evento_disparador="Adjudicación",
            cantidad=45,
            unidad="dias",
            tipo_dias="corridos",
        ),
    ]

    def fake_call_llm(messages, correlation_id=None):
        return ({"grupos": [[0, 1]]}, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})

    monkeypatch.setattr(
        "analysis.extraction.extractors.eventos_temporales._call_llm", fake_call_llm
    )

    result = _consolidate_duplicates_via_llm(items, correlation_id="test")

    assert len(result) == 2


def test_propaga_el_renombre_a_quien_lo_usaba_como_disparador(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [
        _hito("Apertura de Ofertas", "El acto de apertura se realizará el 10/03.", fecha_explicita="2026-03-10"),
        _hito("Acto de Apertura", "La apertura de las ofertas será pública."),
        _hito(
            "Impugnación al Acto de Apertura",
            "Dentro de los 3 días de la apertura de ofertas se podrá impugnar.",
            evento_disparador="Acto de Apertura",
            cantidad=3,
            unidad="dias",
            tipo_dias="habiles",
        ),
    ]

    def fake_call_llm(messages, correlation_id=None):
        return ({"grupos": [[0, 1]]}, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})

    monkeypatch.setattr(
        "analysis.extraction.extractors.eventos_temporales._call_llm", fake_call_llm
    )

    result = _consolidate_duplicates_via_llm(items, correlation_id="test")

    assert len(result) == 2
    impugnacion = next(item for item in result if "Impugnación" in item["nombre"])
    merged = next(item for item in result if item is not impugnacion)
    assert impugnacion["evento_disparador"] == merged["nombre"]


def test_no_llama_al_llm_si_hay_menos_de_2_items(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"value": False}

    def fake_call_llm(messages, correlation_id=None):
        called["value"] = True
        return ({"grupos": []}, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})

    monkeypatch.setattr(
        "analysis.extraction.extractors.eventos_temporales._call_llm", fake_call_llm
    )

    items = [_hito("Apertura de Ofertas", "cita")]
    result = _consolidate_duplicates_via_llm(items, correlation_id="test")

    assert result == items
    assert called["value"] is False


def test_falla_abierto_si_el_llm_da_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nunca se pierden ítems por un fallo de este paso -- ante error, se
    devuelven los ítems originales sin consolidar."""
    items = [
        _hito("Apertura de Ofertas", "cita 1"),
        _hito("Acto de Apertura", "cita 2"),
    ]

    def fake_call_llm(messages, correlation_id=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "analysis.extraction.extractors.eventos_temporales._call_llm", fake_call_llm
    )

    result = _consolidate_duplicates_via_llm(items, correlation_id="test")

    assert result == items


def test_ignora_indices_invalidos_del_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    items = [
        _hito("Apertura de Ofertas", "cita 1"),
        _hito("Acto de Apertura", "cita 2"),
    ]

    def fake_call_llm(messages, correlation_id=None):
        return (
            {"grupos": [[0, 99], ["no-es-un-indice"]]},
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr(
        "analysis.extraction.extractors.eventos_temporales._call_llm", fake_call_llm
    )

    result = _consolidate_duplicates_via_llm(items, correlation_id="test")

    assert len(result) == 2
