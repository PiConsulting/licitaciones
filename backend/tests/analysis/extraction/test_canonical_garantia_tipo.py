# Regresión (2026-09-11, bug encontrado auditando garantías/dell):
# `_canonical_garantia_tipo` se escribió con solo 3 ramas (cumplimiento
# contrato / anticipo / mantenimiento_oferta) y nunca se actualizó cuando
# `TipoGarantia` (schemas.py) se amplió con contragarantia/impugnacion/
# fondo_reparo/por_vicios_ocultos/buen_uso_anticipo -- cualquier ítem que el
# LLM etiquetara correctamente con uno de esos 5 tipos se pisaba con "otra"
# en cada corrida, y de paso rompía el dedup entre un ítem "contragarantia" y
# su gemelo "anticipo" del mismo hecho (dedup agrupa por `tipo`).
from __future__ import annotations

import pytest

from analysis.extraction.graph.canonicalization import _canonical_garantia_tipo
from analysis.extraction.schemas import TipoGarantia


@pytest.mark.parametrize("tipo", list(TipoGarantia))
def test_valid_enum_values_pass_through_unchanged(tipo: TipoGarantia) -> None:
    """Si el LLM ya devolvió un valor válido del enum, no se debe reescribir
    -- antes del fix, todo lo que no fuera cumplimiento_contrato/anticipo/
    mantenimiento_oferta caía a "otra" sin importar que fuera válido."""
    assert _canonical_garantia_tipo(tipo.value) == tipo.value


def test_contragarantia_en_texto_libre_no_cae_a_otra() -> None:
    assert _canonical_garantia_tipo("Contragarantía") == "contragarantia"


def test_contragarantia_por_anticipo_no_se_confunde_con_anticipo() -> None:
    """'contragarantía por anticipo' contiene la palabra 'anticipo' -- el
    chequeo de contragarantía debe evaluarse antes para no perderla."""
    assert (
        _canonical_garantia_tipo("Contragarantía por el anticipo recibido")
        == "contragarantia"
    )


def test_anticipo_solo_sigue_siendo_anticipo() -> None:
    assert _canonical_garantia_tipo("Anticipo financiero") == "anticipo"


def test_impugnacion_en_texto_libre() -> None:
    assert _canonical_garantia_tipo("Garantía de impugnación al pliego") == "impugnacion"


def test_fondo_de_reparo_en_texto_libre() -> None:
    assert _canonical_garantia_tipo("Fondo de reparo") == "fondo_reparo"


def test_por_vicios_ocultos_en_texto_libre() -> None:
    assert _canonical_garantia_tipo("Garantía por vicios ocultos") == "por_vicios_ocultos"


def test_buen_uso_anticipo_en_texto_libre() -> None:
    assert _canonical_garantia_tipo("Garantía de buen uso del anticipo") == "buen_uso_anticipo"


def test_cumplimiento_contrato_sigue_funcionando() -> None:
    assert (
        _canonical_garantia_tipo("Garantía de Cumplimiento de Contrato")
        == "cumplimiento_contrato"
    )


def test_mantenimiento_oferta_sigue_funcionando() -> None:
    assert _canonical_garantia_tipo("Caución de oferta") == "mantenimiento_oferta"


def test_texto_no_reconocido_cae_a_otra() -> None:
    assert _canonical_garantia_tipo("un texto sin relación a ningún tipo conocido") == "otra"


def test_vacio_cae_a_otra() -> None:
    assert _canonical_garantia_tipo("") == "otra"
