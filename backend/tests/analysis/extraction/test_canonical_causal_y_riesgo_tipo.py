# Regresión (2026-09-14): faltaba chequeo de match exacto contra el enum antes de caer al default por keyword, pisando valores ya válidos; también faltaba "etica" en TipoCausal.
from __future__ import annotations

import pytest

from analysis.extraction.graph.canonicalization import (
    _canonical_causal_tipo,
    _canonical_riesgo_subtipo,
)
from analysis.extraction.schemas import SubtipoRiesgo, TipoCausal


@pytest.mark.parametrize("tipo", list(TipoCausal))
def test_causal_valid_enum_values_pass_through_unchanged(tipo: TipoCausal) -> None:
    assert _canonical_causal_tipo(tipo.value) == tipo.value


def test_causal_etica_en_texto_libre_ya_no_cae_a_otra() -> None:
    assert _canonical_causal_tipo("Oferta de dádivas a un funcionario público") == "etica"
    assert _canonical_causal_tipo("colusión entre oferentes") == "etica"


def test_causal_texto_no_reconocido_cae_a_otra() -> None:
    assert _canonical_causal_tipo("algo sin relación a ningún tipo conocido") == "otra"


def test_causal_vacio_cae_a_otra() -> None:
    assert _canonical_causal_tipo("") == "otra"


@pytest.mark.parametrize("subtipo", list(SubtipoRiesgo))
def test_riesgo_valid_enum_values_pass_through_unchanged(subtipo: SubtipoRiesgo) -> None:
    """Antes del fix, 'comercial' (el único de los 9 valores cuyo slug no
    aparece dentro de ninguna de sus propias palabras clave de fallback)
    caía a 'otro_explicito' pese a ser un valor válido."""
    assert _canonical_riesgo_subtipo(subtipo.value) == subtipo.value


def test_riesgo_comercial_en_texto_libre_sigue_funcionando() -> None:
    assert _canonical_riesgo_subtipo("moneda de cotización") == "comercial"


def test_riesgo_texto_no_reconocido_cae_a_otro_explicito() -> None:
    assert _canonical_riesgo_subtipo("algo sin relación a ningún subtipo") == "otro_explicito"
