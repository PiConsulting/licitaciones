# Regresión (2026-09-16): `monto_porcentaje` con `le=100.0` descartaba contragarantías reales >100% (caso real: santa_fe, 150% de sobre-colateralización legítima).
from __future__ import annotations

import pytest
from pydantic import ValidationError

from analysis.extraction.schemas import GarantiaItem, TipoGarantia


def _item(**overrides: object) -> GarantiaItem:
    defaults: dict[str, object] = {"tipo": TipoGarantia.CONTRAGARANTIA, "confidence": 0.9}
    defaults.update(overrides)
    return GarantiaItem(**defaults)  # type: ignore[arg-type]


def test_150_por_ciento_es_valido() -> None:
    """Caso real: contragarantía del 150% del anticipo financiero (santa_fe)."""
    item = _item(monto_porcentaje=150.0)
    assert item.monto_porcentaje == 150.0


def test_100_por_ciento_sigue_siendo_valido() -> None:
    item = _item(monto_porcentaje=100.0)
    assert item.monto_porcentaje == 100.0


def test_porcentaje_negativo_sigue_rechazado() -> None:
    with pytest.raises(ValidationError):
        _item(monto_porcentaje=-1.0)


def test_porcentaje_absurdo_sigue_rechazado() -> None:
    """El techo se subió, no se eliminó -- un error de unidad grotesco
    (ej. confundir un monto en pesos con un porcentaje) sigue detectándose."""
    with pytest.raises(ValidationError):
        _item(monto_porcentaje=50000.0)


def test_mutua_exclusividad_con_monto_valor_sigue_vigente() -> None:
    with pytest.raises(ValidationError):
        _item(monto_porcentaje=150.0, monto_valor=1000.0)
