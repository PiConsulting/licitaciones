"""ING-10: un párrafo se quedaba con el bbox de una celda de tabla.

`_same_text` aceptaba la contención en cualquier posición. Un párrafo corto se
mete por casualidad en el medio de cualquier párrafo largo que mencione las
mismas palabras — y `result.paragraphs` de Document Intelligence incluye las
**celdas de las tablas**, que son justamente textos cortos.

Medido en el reanálisis `7bce4799` del PET de Bancor, chunk 95:

    contenido | "· El adjudicatario deberá tener capacidad de brindar soporte
                 presencial (on-site) cuando la severidad lo requiera o el Banco
                 lo solicite, con un tiempo de respuesta on-site no mayor a 3
                 horas."                                     (192 caracteres)
    bbox      | 84,4 × 30,9 pt  ← la celda "Tiempo de respuesta" del encabezado
                                  de la tabla de la misma página

En 84 pt de ancho no entran 192 caracteres; los demás párrafos de esa página
miden ~450 pt. El resaltado de esa cita caía sobre una celda de la tabla. La
causa es literal: `"tiempo de respuesta"` está adentro del párrafo, en el medio.

Un fragmento de verdad está **anclado a un borde**: el parser corta el párrafo de
DI por el principio, o le saca una viñeta del principio. En el medio no hay
relación estructural, sólo vocabulario compartido.
"""

from __future__ import annotations

from extraction.document_intelligence import _same_text

# El texto exacto del chunk 95 y el de la celda que le robó el bbox.
PARRAFO_DEL_CHUNK_95 = (
    "· El adjudicatario deberá tener capacidad de brindar soporte presencial (on-site) cuando la "
    "severidad lo requiera o el Banco lo solicite, con un tiempo de respuesta on-site no mayor a 3 "
    "horas."
)
CELDA_DE_LA_TABLA = "Tiempo de respuesta"


# ---------------------------------------------------------------------------
# El caso del hallazgo
# ---------------------------------------------------------------------------


def test_una_celda_de_tabla_no_matchea_por_aparecer_en_el_medio() -> None:
    assert not _same_text(PARRAFO_DEL_CHUNK_95, CELDA_DE_LA_TABLA)


def test_la_contencion_en_el_medio_no_alcanza_en_ningun_sentido() -> None:
    largo = "El plazo de entrega será de cuarenta y cinco días corridos desde la adjudicación."

    assert not _same_text(largo, "plazo de entrega")
    assert not _same_text("plazo de entrega", largo)


# ---------------------------------------------------------------------------
# Los fragmentos legítimos siguen matcheando
# ---------------------------------------------------------------------------


def test_el_bloque_puede_ser_el_principio_del_parrafo_de_di() -> None:
    """El caso de CHK-12: DI parte una línea y el parser emite el encabezado
    solo. `"Artículo Nº 10: GAR"` es prefijo de la línea entera."""
    linea_entera = (
        "Artículo Nº 10: GARANTÍA DE ADJUDICACIÓN: En caso de corresponder, el importe de las "
        "garantías de la contratación se calculará sobre el monto adjudicado."
    )

    assert _same_text("Artículo Nº 10: GAR", linea_entera)


def test_el_parrafo_de_di_puede_ser_el_final_del_bloque() -> None:
    """El parser conserva la viñeta y DI no, o al revés: el corte cae en el
    borde, no en el medio."""
    con_vineta = "· Los componentes ofertados deberán ser nuevos, sin uso, originales de fábrica."
    sin_vineta = "Los componentes ofertados deberán ser nuevos, sin uso, originales de fábrica."

    assert _same_text(con_vineta, sin_vineta)
    assert _same_text(sin_vineta, con_vineta)


def test_el_texto_identico_matchea() -> None:
    texto = "El Oferente se obliga a mantener la más estricta confidencialidad."

    assert _same_text(texto, texto)


def test_los_espacios_y_los_saltos_de_linea_no_importan() -> None:
    del_parser = "Las entregas deberán ser totales,\nno aceptándose entregas parciales."
    de_di = "Las entregas deberán  ser totales, no aceptándose entregas parciales."

    assert _same_text(del_parser, de_di)


def test_el_prefijo_largo_sigue_alcanzando() -> None:
    """La otra rama: los dos textos empiezan igual pero divergen al final
    (DI recorta, el parser une el renglón siguiente)."""
    a = "Los oferentes deberán realizar una visita técnica obligatoria a ambos data centers."
    b = "Los oferentes deberán realizar una visita técnica obligatoria a los dos sitios del Banco."

    assert _same_text(a, b)


# ---------------------------------------------------------------------------
# Guardas
# ---------------------------------------------------------------------------


def test_los_textos_muy_cortos_siguen_exigiendo_igualdad() -> None:
    """Un índice es una página llena de números sueltos: sin igualdad exacta,
    "4" matchearía dentro de "41"."""
    assert _same_text("4", "4")
    assert not _same_text("4", "41")
    assert not _same_text("41", "4")


def test_un_texto_vacio_no_matchea_nada() -> None:
    assert not _same_text("", "algo")
    assert not _same_text("algo", "")
    assert not _same_text(None, None)


def test_dos_textos_distintos_no_matchean() -> None:
    assert not _same_text(
        "El plazo de entrega será de 45 días corridos.",
        "La garantía de mantenimiento de oferta será del 5%.",
    )
