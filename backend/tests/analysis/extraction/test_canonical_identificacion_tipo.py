# Regresión (2026-09-14): el golden pedía datos de contacto/consulta sin tipo canónico -- se agregaron `canal_consultas` y `lugar_consulta_pliego`.
from __future__ import annotations

import pytest

from analysis.extraction.graph.canonicalization import _canonical_identificacion_tipo
from analysis.extraction.schemas import TipoIdentificacion


@pytest.mark.parametrize("tipo", list(TipoIdentificacion))
def test_valid_enum_values_pass_through_unchanged(tipo: TipoIdentificacion) -> None:
    assert _canonical_identificacion_tipo(tipo.value) == tipo.value


def test_domicilio_electronico_en_texto_libre() -> None:
    assert (
        _canonical_identificacion_tipo("Domicilio electrónico de notificaciones")
        == "canal_consultas"
    )


def test_correo_de_consultas_en_texto_libre() -> None:
    assert _canonical_identificacion_tipo("Correo de consultas técnicas") == "canal_consultas"


def test_lugar_de_consulta_del_pliego_en_texto_libre() -> None:
    assert (
        _canonical_identificacion_tipo("Lugar de consulta del pliego")
        == "lugar_consulta_pliego"
    )


def test_consulta_en_linea_en_texto_libre() -> None:
    assert _canonical_identificacion_tipo("Consulta en línea") == "lugar_consulta_pliego"


def test_texto_no_reconocido_cae_a_none() -> None:
    """A diferencia de garantías/causales/riesgos (que tienen 'otra'), acá el
    fallback es None -- el ítem sobrevive en el campo legacy `datos_procedimiento`
    (texto libre), no en el canónico. Comportamiento previo, sin tocar."""
    assert _canonical_identificacion_tipo("un dato sin relación a ningún tipo") is None
