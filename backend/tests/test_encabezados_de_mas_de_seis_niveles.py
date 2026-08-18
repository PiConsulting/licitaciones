"""CHK-17: los encabezados de más de seis almohadillas se perdían enteros.

`_MD_HEADING_RE` estaba escrito con el tope de CommonMark (`#{1,6}`). Document
Intelligence no emite CommonMark: cuando la jerarquía visual del documento pasa
de seis niveles sigue agregando almohadillas. En el PET de Bancor:

    ###### 3.1.10. Herramientas                         <- reconocido
    ####### 3.3. Equipamiento de cómputo y dimensionamiento (sizing)   <- NO
    ######## 3.3.1. Capacidades a satisfacer y base de cálculo         <- NO

Las dos últimas líneas no matcheaban y caían al acumulador de párrafos. Dos
consecuencias, las dos medidas sobre el reanálisis real:

  1. Las almohadillas quedaban LITERALES dentro del texto del chunk: el
     contenido del chunk 68 termina con "####### 3.3. Equipamiento de cómputo y
     dimensionamiento (sizing)" y el del 69 contiene "######## 3.3.1. ...". Eso
     va al embedding y al campo `searchable` del índice.

  2. Peor: la sección dejaba de existir como ancestro. Todo lo que colgaba de
     3.3 se enganchaba del último encabezado que sí había sido reconocido, que
     para la página 25 era de otra sección entera. Los chunks 64-72 —contenido
     de 3.3— salieron con `section_path`:

         PLIEGO … > · Equipo Principal de Almacenamiento de BackUp
                  > o Rendimiento y Conectividad Mínima:
                  > o Seguridad
                  > 2.3.3) ITEM 3: EQUIPO DE ALMACENAMIENTO DE BACKUP SECUNDARIO
                  > · Requerimiento de Capacidades

     Ese path alimenta el `section_hint` del resaltado y el contexto que ve el
     redactor de la síntesis: la jerarquía inventada se propaga a las dos
     puntas. Desde la página ~16 hasta la ~33 del PET estaba así.
"""

from __future__ import annotations

from typing import Any

from extraction.chunking import _to_intermediate_blocks
from extraction.document_intelligence import _MD_HEADING_RE, _parse_markdown_blocks

# Fragmento fiel al PET de Bancor: el salto de 6 a 7 almohadillas ocurre en
# medio de la jerarquía, no al principio.
MARKDOWN_BANCOR = """# PLIEGO DE ESPECIFICACIONES TÉCNICAS

## 3. Especificaciones técnicas

### 3.1. Plataforma de software de nube privada

###### 3.1.10. Herramientas

La plataforma deberá incluir herramientas de gestión centralizada.

####### 3.3. Equipamiento de cómputo y dimensionamiento (sizing)

######## 3.3.1. Capacidades a satisfacer y base de cálculo

El dimensionamiento deberá satisfacer las capacidades declaradas en la tabla adjunta.

######## 3.3.2. Requisitos mínimos por nodo de cómputo (referenciales)

Cada nodo deberá contar con al menos dos procesadores de la generación vigente.
"""


def _bloques_con_nivel(markdown: str) -> list[dict[str, Any]]:
    """Reproduce lo que hace `_build_markdown_blocks` para pegar el nivel al
    bloque, sin necesitar un `result` del SDK."""
    blocks, niveles, _ = _parse_markdown_blocks(markdown)
    for block in blocks:
        nivel = niveles.get(block["source_order"])
        if nivel is not None:
            block["heading_level"] = nivel
    return blocks


def _path_de(intermedios: list[dict[str, Any]], fragmento: str) -> list[str]:
    for bloque in intermedios:
        if fragmento in str(bloque.get("content", "")):
            return [str(h) for h in bloque.get("heading_path", [])]
    raise AssertionError(f"no hay ningún bloque que contenga {fragmento!r}")


# ---------------------------------------------------------------------------
# El caso del hallazgo
# ---------------------------------------------------------------------------


def test_siete_almohadillas_son_un_encabezado() -> None:
    match = _MD_HEADING_RE.match("####### 3.3. Equipamiento de cómputo y dimensionamiento (sizing)")

    assert match is not None
    assert match.group(2) == "3.3. Equipamiento de cómputo y dimensionamiento (sizing)"


def test_ocho_almohadillas_tambien() -> None:
    match = _MD_HEADING_RE.match("######## 3.3.1. Capacidades a satisfacer y base de cálculo")

    assert match is not None
    assert match.group(2) == "3.3.1. Capacidades a satisfacer y base de cálculo"


def test_las_almohadillas_no_quedan_dentro_del_texto_de_ningun_bloque() -> None:
    """La consecuencia visible en el reanálisis: el contenido del chunk 68
    terminaba con la línea de almohadillas literal."""
    bloques = _bloques_con_nivel(MARKDOWN_BANCOR)

    assert not [b for b in bloques if "#" in str(b.get("content", ""))]


def test_el_encabezado_profundo_es_un_bloque_de_encabezado_no_un_parrafo() -> None:
    bloques = _bloques_con_nivel(MARKDOWN_BANCOR)

    profundos = [
        b
        for b in bloques
        if str(b.get("content", "")).startswith(("3.3.", "3.3 "))
        or str(b.get("content", "")).startswith("3.3.")
    ]
    assert profundos, "el fixture tiene encabezados 3.3.x"
    assert all(b.get("heading_level") is not None for b in profundos)


def test_la_profundidad_real_se_conserva_no_se_recorta_a_seis() -> None:
    """Recortar a 6 dejaría a `3.3.` y `3.3.1.` en el mismo nivel, o sea
    hermanos para `pop_to_level`. `_normalize_decimal_heading_levels` (CHK-16)
    sólo puede reparar lo que está numerado; el resto quedaría aplastado."""
    _, niveles, _ = _parse_markdown_blocks(MARKDOWN_BANCOR)

    assert 7 in niveles.values()
    assert 8 in niveles.values()


# ---------------------------------------------------------------------------
# La consecuencia que importa: el section_path
# ---------------------------------------------------------------------------


def test_el_cuerpo_de_3_3_1_cuelga_de_3_3() -> None:
    intermedios = _to_intermediate_blocks(_bloques_con_nivel(MARKDOWN_BANCOR))

    path = _path_de(intermedios, "El dimensionamiento deberá satisfacer")

    assert any(p.startswith("3.3.1.") for p in path)
    assert any(p.startswith("3.3.") and not p.startswith("3.3.1") for p in path)


def test_el_cuerpo_de_3_3_ya_no_cuelga_de_la_seccion_anterior() -> None:
    """El error medido: contenido de 3.3 colgado de 3.1.10 (y más abajo en el
    PET real, de "2.3.3) ITEM 3: EQUIPO DE ALMACENAMIENTO DE BACKUP
    SECUNDARIO", que es otra sección entera)."""
    intermedios = _to_intermediate_blocks(_bloques_con_nivel(MARKDOWN_BANCOR))

    path = _path_de(intermedios, "El dimensionamiento deberá satisfacer")

    assert not any("3.1.10" in p for p in path)


def test_dos_subsecciones_hermanas_no_se_anidan_entre_si() -> None:
    intermedios = _to_intermediate_blocks(_bloques_con_nivel(MARKDOWN_BANCOR))

    path = _path_de(intermedios, "Cada nodo deberá contar")

    assert not any("3.3.1" in p for p in path)
    assert any(p.startswith("3.3.2.") for p in path)


def test_la_raiz_del_documento_se_conserva() -> None:
    intermedios = _to_intermediate_blocks(_bloques_con_nivel(MARKDOWN_BANCOR))

    path = _path_de(intermedios, "El dimensionamiento deberá satisfacer")

    assert path[0] == "PLIEGO DE ESPECIFICACIONES TÉCNICAS"


# ---------------------------------------------------------------------------
# Guardas: lo que NO es un encabezado sigue sin serlo
# ---------------------------------------------------------------------------


def test_los_niveles_de_uno_a_seis_no_cambian() -> None:
    for cantidad in range(1, 7):
        linea = "#" * cantidad + " ARTÍCULO 10: GARANTÍAS"
        match = _MD_HEADING_RE.match(linea)

        assert match is not None
        assert len(match.group(1)) == cantidad
        assert match.group(2) == "ARTÍCULO 10: GARANTÍAS"


def test_una_almohadilla_sin_espacio_no_es_encabezado() -> None:
    assert _MD_HEADING_RE.match("#3 de la serie") is None
    assert _MD_HEADING_RE.match("#######3.3. Equipamiento") is None


def test_una_linea_de_puras_almohadillas_no_es_encabezado() -> None:
    """Un separador tipográfico no tiene texto: sin `.+` después del espacio no
    hay match."""
    assert _MD_HEADING_RE.match("########") is None
    assert _MD_HEADING_RE.match("####### ") is None


def test_el_texto_en_mayusculas_sin_almohadillas_sigue_sin_ser_encabezado() -> None:
    assert _MD_HEADING_RE.match("ARTÍCULO 10: GARANTÍAS") is None
    assert _MD_HEADING_RE.match("**ARTÍCULO 10**") is None
