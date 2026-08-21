"""ING-11: los escapes de markdown de DI rompían el emparejamiento con el bbox.

En modo markdown, Document Intelligence **escapa** la puntuación que markdown
interpretaría como sintaxis: emite `1\\. Etapa 1`, `\\+ 10 Gb`, `\\> Planificación`,
`\\- Intel Xeon`. Pero `result.paragraphs[].content` es texto plano, sin escapes.
El mismo texto llega distinto por los dos caminos, y `_same_text` los daba por
diferentes desde el segundo carácter — ni contención ni prefijo salvan un
backslash en la posición 1.

Medido sobre el PET de Bancor: 14 de 721 bloques sin bbox (`match_rate 98.1%`).
Entre ellos, las tres etapas de migración del apartado 3.1.10:

    "1\\. Etapa 1 - Migración por el proveedor: el proveedor migrará, documentará
     y realizará el skill transfer correspondiente a 4 servidores…"

que es contenido de `plazos_clave`, no relleno. Se ve en los chunks 44 y 45 del
reanálisis `7bce4799`: `"para_id": null, "bbox": []`.
"""

from __future__ import annotations

from extraction.document_intelligence import _same_text, _unescape_markdown

# ---------------------------------------------------------------------------
# El caso del hallazgo, con los textos reales de los dos pliegos
# ---------------------------------------------------------------------------


def test_la_numeracion_escapada_matchea_con_el_texto_plano() -> None:
    del_markdown = (
        "1\\. Etapa 1 - Migración por el proveedor: el proveedor migrará, documentará y realizará "
        "el skill transfer correspondiente a 4 servidores por cada tipo de plataforma."
    )
    de_di = (
        "1. Etapa 1 - Migración por el proveedor: el proveedor migrará, documentará y realizará "
        "el skill transfer correspondiente a 4 servidores por cada tipo de plataforma."
    )

    assert _same_text(del_markdown, de_di)


def test_las_tres_etapas_de_migracion_de_bancor() -> None:
    """El caso concreto: los chunks 44 y 45 del reanálisis `7bce4799` salieron
    con `bbox: []` para las etapas 2 y 3."""
    for numero in ("2", "3"):
        del_markdown = f"{numero}\\. Etapa {numero} - el proveedor acompañará a los técnicos de Bancor."
        de_di = f"{numero}. Etapa {numero} - el proveedor acompañará a los técnicos de Bancor."

        assert _same_text(del_markdown, de_di)


# ---------------------------------------------------------------------------
# Escapes que YA matcheaban sin el fix (revertirlo no los rompe)
#
# Se dejan explícitos para no confundirlos con el hallazgo: sólo rompe el
# emparejamiento el escape que cae DENTRO de los primeros 40 caracteres y no
# pega contra ningún borde. Los de acá se salvaban por prefijo o por sufijo.
# ---------------------------------------------------------------------------


def test_guarda_el_mas_escapado_lejos_del_principio() -> None:
    """`"20 Gb agregados (10 \\+ 10 Gb)"` (apartado 1.3 de Bancor): el escape cae
    en el carácter ~95, así que los primeros 40 ya coincidían."""
    del_markdown = "La interconexión cuenta con 20 Gb agregados (10\n\\+ 10 Gb), para sincronización."
    de_di = "La interconexión cuenta con 20 Gb agregados (10 + 10 Gb), para sincronización."

    assert _same_text(del_markdown, de_di)


def test_guarda_los_marcadores_de_lista_escapados() -> None:
    """El escape está en el carácter 0, así que el texto de DI ya era sufijo del
    bloque y el anclaje de ING-10 lo aceptaba."""
    assert _same_text("\\> Planificación", "> Planificación")
    assert _same_text("\\- Intel Xeon Platinum 4th Generación", "- Intel Xeon Platinum 4th Generación")


# ---------------------------------------------------------------------------
# La pieza
# ---------------------------------------------------------------------------


def test_saca_el_backslash_solo_de_la_puntuacion() -> None:
    assert _unescape_markdown("1\\. Etapa") == "1. Etapa"
    assert _unescape_markdown("\\+ 10 Gb") == "+ 10 Gb"
    assert _unescape_markdown("\\[Anexo\\]") == "[Anexo]"


def test_un_texto_sin_escapes_no_se_toca() -> None:
    texto = "El adjudicatario deberá presentar la documentación en sobre cerrado."

    assert _unescape_markdown(texto) == texto


def test_una_barra_que_no_precede_puntuacion_se_conserva() -> None:
    """No es un escape de markdown: es una barra del texto del pliego."""
    assert _unescape_markdown("ruta\\archivo") == "ruta\\archivo"


# ---------------------------------------------------------------------------
# Guardas: no aflojar el emparejamiento
# ---------------------------------------------------------------------------


def test_dos_textos_distintos_siguen_sin_matchear() -> None:
    assert not _same_text(
        "1\\. Etapa 1 - Migración por el proveedor de los servidores.",
        "2. Etapa 2 - Acompañamiento presencial a los técnicos del Banco.",
    )


def test_los_numeros_cortos_siguen_exigiendo_igualdad() -> None:
    assert not _same_text("4", "41")
    assert _same_text("4", "4")


def test_la_celda_de_tabla_en_el_medio_sigue_sin_matchear() -> None:
    """ING-10 no se afloja: el escape se saca ANTES de exigir el anclaje."""
    parrafo = (
        "· El adjudicatario deberá tener capacidad de brindar soporte presencial (on-site) cuando "
        "la severidad lo requiera, con un tiempo de respuesta on-site no mayor a 3 horas."
    )

    assert not _same_text(parrafo, "Tiempo de respuesta")
