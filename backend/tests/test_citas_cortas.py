"""Citas cortas: el largo de la cita ES el largo del resaltado.

`highlight.py::compute_highlights_for_sources` busca el texto de la cita dentro
del PDF con `page.search_for()`. Los rectángulos que devuelve son, literalmente,
dónde vive ese texto en la página -- así que una cita de párrafo produce un
subrayado de párrafo. No son dos cosas que se puedan regular por separado.

Con `CITATION_MAX_CHARS = 300`, un análisis real daba citas de mediana 129 y
máximo 264 caracteres: dos a cuatro renglones subrayados para señalar un dato
que ocupa media línea. El techo baja a 120.

Bajar el techo por sí solo no alcanza, y esto es lo que hace falta verificar:
`clip_citation` recorta desde el PRINCIPIO. La carátula de un pliego es un
bloque de ~210 caracteres que respalda varios items distintos, y el dato de
cada uno cae en un lugar distinto de ese mismo texto. Medido sobre el análisis
real: tanto "Presupuesto oficial: AR$ 12.000.000" como "Jurisdicción: Municipal"
caen DESPUÉS del carácter 120. Un prefijo dejaría a esos items citando un texto
que no prueba nada de lo que afirman.
"""

from __future__ import annotations

from typing import Any

from analysis.extraction.extractors.base import (
    _canonical_number,
    shorten_citation_to_evidence,
)
from analysis.extraction.schemas import CITATION_MAX_CHARS, CITATION_PREFERRED_MIN_CHARS

# Texto real, tomado del fixture `extracted_data.real.json` del frontend.
CARATULA = (
    "Organismo convocante: Municipalidad de Villa Nueva. Expediente Nº 0100-EXP-2026. "
    "Procedimiento Nº 05/2026. Tipo de procedimiento: Licitación pública. "
    "Presupuesto oficial: AR$ 12.000.000. Jurisdicción: Municipal."
)

GARANTIA_LARGA = (
    "Los oferentes deberán constituir una garantía de mantenimiento de oferta equivalente "
    "al 5% del presupuesto oficial, mediante póliza de caución, dentro de los 5 días "
    "hábiles de notificada la apertura, bajo apercibimiento de rechazo."
)


def _item(valor: Any, tipo: str = "dato") -> dict[str, Any]:
    return {"tipo": tipo, "valor": valor}


# ---------------------------------------------------------------------------
# 1. El techo
# ---------------------------------------------------------------------------


def test_el_techo_es_de_un_renglon() -> None:
    assert CITATION_MAX_CHARS == 120
    assert CITATION_PREFERRED_MIN_CHARS < CITATION_MAX_CHARS


def test_una_cita_corta_no_se_toca() -> None:
    corta = "garantía de mantenimiento de oferta del 5% del presupuesto oficial"
    assert shorten_citation_to_evidence(corta, _item("5%")) == corta


def test_ninguna_cita_supera_el_techo() -> None:
    for item in (_item("12000000.0 ARS"), _item("Municipal"), _item(None)):
        assert len(shorten_citation_to_evidence(CARATULA, item)) <= CITATION_MAX_CHARS


# ---------------------------------------------------------------------------
# 2. La ventana contiene el dato, no el prefijo
# ---------------------------------------------------------------------------


def test_el_monto_sobrevive_al_recorte_aunque_este_al_final() -> None:
    """En la carátula real, "AR$ 12.000.000" empieza en el carácter ~150."""
    citation = shorten_citation_to_evidence(CARATULA, _item("12000000.0 ARS", "presupuesto_oficial"))

    assert "12.000.000" in citation


def test_la_jurisdiccion_sobrevive_al_recorte() -> None:
    """"Jurisdicción: Municipal" está al final del mismo bloque de ~210."""
    citation = shorten_citation_to_evidence(CARATULA, _item("Municipal", "jurisdiccion"))

    assert "Jurisdicción: Municipal" in citation


def test_el_mismo_texto_da_citas_distintas_segun_el_item() -> None:
    """Es el punto entero: un párrafo que respalda tres items no puede dar la
    misma cita para los tres, porque cada uno afirma otra cosa."""
    presupuesto = shorten_citation_to_evidence(CARATULA, _item("12000000.0 ARS", "presupuesto_oficial"))
    expediente = shorten_citation_to_evidence(CARATULA, _item("0100-EXP-2026", "numero_expediente"))

    assert presupuesto != expediente
    assert "12.000.000" in presupuesto
    assert "0100-EXP-2026" in expediente


def test_un_valor_corto_ancla_por_palabra_completa() -> None:
    """`valor="Municipal"` también matchea como subcadena dentro de
    "Municipalidad", que está al principio del texto en el nombre del organismo.
    Esa coincidencia apuntaría a cualquier lado menos al dato."""
    citation = shorten_citation_to_evidence(CARATULA, _item("Municipal", "jurisdiccion"))

    assert not citation.startswith("Organismo convocante")


def test_sin_valor_ubicable_se_recorta_por_prefijo() -> None:
    """El comportamiento de siempre como red: nunca se pierde la cita."""
    citation = shorten_citation_to_evidence(CARATULA, _item(None))

    assert CARATULA.startswith(citation)


# ---------------------------------------------------------------------------
# 3. El recorte no puede romper el grounding ni el resaltado
# ---------------------------------------------------------------------------


def test_la_cita_recortada_sigue_siendo_literal_y_contigua() -> None:
    """De esto depende TODO lo de abajo: `_verify_citation_grounding` la busca
    como subcadena en el chunk, y `search_for` la busca en el PDF. Un recorte
    que arme un texto que no existe literalmente rompe las dos cosas."""
    plano = " ".join(CARATULA.split())
    for item in (
        _item("12000000.0 ARS"),
        _item("Municipal"),
        _item("0100-EXP-2026"),
        _item("Licitación pública"),
        _item(None),
    ):
        citation = shorten_citation_to_evidence(CARATULA, item)
        assert citation in plano, f"{citation!r} no existe literal en el texto original"


def test_no_se_parten_palabras_al_medio() -> None:
    citation = shorten_citation_to_evidence(GARANTIA_LARGA, _item("5% del presupuesto oficial"))

    plano = " ".join(GARANTIA_LARGA.split())
    inicio = plano.index(citation)
    fin = inicio + len(citation)
    assert inicio == 0 or plano[inicio - 1] == " "
    assert fin == len(plano) or plano[fin] == " "


# ---------------------------------------------------------------------------
# 4. Normalización de números: el formato del pliego != el del dato extraído
# ---------------------------------------------------------------------------


def test_el_monto_del_item_y_el_del_pliego_se_escriben_distinto() -> None:
    assert _canonical_number("12.000.000") == "12000000"
    assert _canonical_number("12000000.0") == "12000000"
    assert _canonical_number("AR$ 12.000.000") == "12000000"


def test_un_decimal_real_no_se_pierde() -> None:
    assert _canonical_number("1,5") == "15"
    assert _canonical_number("2.50") == "25"
