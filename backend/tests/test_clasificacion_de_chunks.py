"""CHK-07 y CHK-08: cómo un chunk termina con una categoría que no le toca.

  - CHK-07: un término de varias palabras se descomponía en un CONJUNTO de
    tokens y matcheaba si todos aparecían en cualquier lugar del chunk, en
    cualquier orden y a cualquier distancia. `"mantenimiento de oferta"` se
    volvía `{mantenimiento, de, oferta}`, y "de" está en el 100% de los chunks
    en castellano.

  - CHK-08: la densidad satura con un solo match en cualquier chunk de menos de
    100 palabras, y eso alcanza exactamente el umbral primario. Acá sólo se fija
    el comportamiento actual y la constante que lo gobierna: corregirlo es
    calibración y necesita datos. Ver el docstring de `_compute_density_score`.
"""

from __future__ import annotations

from extraction.chunking import (
    _DEFAULT_PRIMARY_THRESHOLD,
    _DENSITY_SATURATION_PER_100_WORDS,
    _compute_density_score,
    _count_keyword_matches,
    _term_appears_in,
)

GLOSARIO = {
    "garantias": {
        "query_terms": ["garantia de mantenimiento de oferta", "poliza de caucion"],
        "aliases": ["mantenimiento de oferta"],
        "weight": 1.0,
    },
    "criterios_evaluacion": {
        "query_terms": ["oferta economica"],
        "aliases": [],
        "weight": 1.0,
    },
}


# ---------------------------------------------------------------------------
# CHK-07: el caso del hallazgo
# ---------------------------------------------------------------------------


PARRAFO_DE_SERVICIOS = (
    "El adjudicatario será responsable del mantenimiento preventivo de los equipos durante "
    "toda la vigencia del contrato. La oferta económica deberá contemplar los insumos."
)


def test_un_parrafo_de_servicios_ya_no_matchea_garantias() -> None:
    """El escenario del hallazgo: "mantenimiento", "de" y "oferta" aparecen
    sueltas y en desorden, y el chunk quedaba matcheando garantías."""
    assert "garantias" not in _count_keyword_matches(PARRAFO_DE_SERVICIOS, GLOSARIO)


def test_la_frase_real_si_matchea() -> None:
    contenido = (
        "Los oferentes deberán constituir una garantía de mantenimiento de oferta "
        "equivalente al 5% del presupuesto oficial."
    )

    assert _count_keyword_matches(contenido, GLOSARIO).get("garantias", 0) >= 1


def test_el_orden_de_las_palabras_importa() -> None:
    """"oferta de mantenimiento" no es "mantenimiento de oferta"."""
    assert "garantias" not in _count_keyword_matches(
        "Se presentará una oferta de mantenimiento para los equipos instalados.", GLOSARIO
    )


def test_la_distancia_entre_las_palabras_importa() -> None:
    contenido = (
        "El mantenimiento correctivo se factura aparte. En un apartado distinto y varias "
        "líneas más abajo se define el plazo de la oferta presentada."
    )

    assert "garantias" not in _count_keyword_matches(contenido, GLOSARIO)


# ---------------------------------------------------------------------------
# CHK-07: las piezas
# ---------------------------------------------------------------------------


def test_un_termino_de_una_palabra_sigue_matcheando_por_token() -> None:
    tokens = {"caucion", "poliza"}
    padded = " se presenta una poliza de caucion vigente "

    assert _term_appears_in("caucion", tokens, padded)
    assert not _term_appears_in("aval", tokens, padded)


def test_una_frase_no_matchea_a_mitad_de_palabra() -> None:
    """Sin bordes de palabra, "oferta economica" matchearía dentro de
    "ofertas economicas"... y también dentro de cualquier palabra que las
    contenga."""
    tokens = {"el", "ofertante", "economico"}
    padded = " el ofertante economico "

    assert not _term_appears_in("oferta economica", tokens, padded)


def test_un_termino_vacio_no_matchea_nada() -> None:
    assert not _term_appears_in("", {"algo"}, " algo ")


def test_las_frases_de_categorias_distintas_no_se_pisan() -> None:
    contenido = "La oferta económica deberá presentarse en sobre cerrado."
    conteos = _count_keyword_matches(contenido, GLOSARIO)

    assert conteos.get("criterios_evaluacion", 0) >= 1
    assert "garantias" not in conteos


# ---------------------------------------------------------------------------
# CHK-08: el comportamiento actual, fijado antes de calibrar
# ---------------------------------------------------------------------------


def test_un_chunk_corto_con_un_solo_match_alcanza_el_umbral_primario() -> None:
    """Esto es el hallazgo, y sigue vigente a propósito: arreglarlo es mover la
    calibración, y para eso hace falta el set de chunks etiquetados. El test
    documenta el estado actual para que el día que se calibre se vea qué cambió.
    """
    score = _compute_density_score(match_count=1, content_length=40)

    assert score == _DEFAULT_PRIMARY_THRESHOLD


def test_la_densidad_penaliza_los_chunks_largos_y_eso_es_lo_correcto() -> None:
    """El comentario del código decía lo contrario de lo que hace. El
    equivocado era el comentario: un término que aparece una vez en 700
    palabras es menos indicativo que uno que aparece una vez en 100."""
    corto = _compute_density_score(match_count=4, content_length=100)
    largo = _compute_density_score(match_count=4, content_length=700)

    assert corto > largo


def test_el_punto_de_saturacion_es_una_constante_con_nombre() -> None:
    """Estaba implícito en la unidad de una división. Es el único lugar que hay
    que tocar cuando lleguen los datos de calibración."""
    assert _DENSITY_SATURATION_PER_100_WORDS == 1.0

    # Y gobierna de verdad el resultado: al doble de saturación, la mitad de
    # densidad para el mismo chunk.
    score = _compute_density_score(match_count=2, content_length=200)
    assert score == min(2 / 4, 1.0) * min((2 / 2.0) / _DENSITY_SATURATION_PER_100_WORDS, 1.0)


def test_sin_matches_no_hay_score() -> None:
    assert _compute_density_score(match_count=0, content_length=100) == 0.0
    assert _compute_density_score(match_count=3, content_length=0) == 0.0


def test_el_peso_de_categoria_se_sigue_aplicando() -> None:
    assert _compute_density_score(4, 100, category_weight=0.5) == 0.5
