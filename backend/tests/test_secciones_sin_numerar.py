"""CHK-19: un encabezado sin numerar se llevaba puesta toda la jerarquía numerada.

Con CHK-16 y CHK-17 puestos, los encabezados **numerados** quedan en el nivel que
declara su numeración. Los **no numerados** siguen en el nivel que les asignó
Azure DI, que lo deduce de la tipografía. En el PET de Bancor las subsecciones en
viñeta de 3.1.8 salían en nivel 2 — el mismo que `3. Especificaciones técnicas`—
y un encabezado de nivel 2 hace `pop_to_level(2)`: se lleva puestos a `3.`,
`3.1.` y `3.1.8.` de una sola vez.

Medido sobre el reanálisis `476a0353` (113 chunks), ya con CHK-17 aplicado:

    chunk 34 | PLIEGO DE ESPECIFICACIONES TÉCNICAS > Capa de infraestructura y
               virtualización (VCF)
             ^ perdió 3., 3.1. y 3.1.8.

    chunk 69 | PLIEGO … > · Equipo Principal de Almacenamiento de BackUp
               > 3.3. Equipamiento de cómputo y dimensionamiento (sizing)
             ^ 3.3 colgada de una subsección de 3.2

El `section_path` alimenta el `section_hint` que desambigua el resaltado y el
contexto que ve el redactor de la síntesis: la jerarquía inventada se propaga a
las dos puntas.

La regla del fix: si el pliego hubiera querido que ese título fuera hermano de
las secciones numeradas, lo habría numerado.
"""

from __future__ import annotations

from typing import Any

from extraction.chunking import (
    _nest_unnumbered_headings_under_numbered,
    _to_intermediate_blocks,
)


def _h(contenido: str, nivel: int, orden: int, page: int = 1) -> dict[str, Any]:
    return {
        "content": contenido,
        "heading_level": nivel,
        "page_number": page,
        "source_order": orden,
    }


def _p(contenido: str, orden: int, page: int = 1) -> dict[str, Any]:
    return {
        "content": contenido,
        "heading_level": None,
        "page_number": page,
        "source_order": orden,
    }


def _niveles(bloques: list[dict[str, Any]]) -> dict[str, int | None]:
    return {str(b["content"]): b.get("heading_level") for b in bloques}


def _path_de(intermedios: list[dict[str, Any]], fragmento: str) -> list[str]:
    for bloque in intermedios:
        if fragmento in str(bloque.get("content", "")):
            return [str(h) for h in bloque.get("heading_path", [])]
    raise AssertionError(f"no hay ningún bloque que contenga {fragmento!r}")


# Reproduce la secuencia real del PET, con los niveles que salieron del
# reanálisis: los numerados ya normalizados por CHK-16 (base 2), los de viñeta
# en el nivel 2 que les puso DI.
def _bancor() -> list[dict[str, Any]]:
    return [
        _h("PLIEGO DE ESPECIFICACIONES TÉCNICAS", 1, 0),
        _h("3. Especificaciones técnicas", 2, 1),
        _h("3.1. Plataforma de software de nube privada", 3, 2),
        _h("3.1.8. Seguridad (Security by Design / Security by Default)", 4, 3),
        _p("La arquitectura deberá aplicar defensa en profundidad.", 4),
        _h("Capa de infraestructura y virtualización (VCF)", 2, 5),
        _p("Se deberán implementar controles de seguridad obligatorios sobre ESXi.", 6),
        _h("Resiliencia y backup seguro", 2, 7),
        _p("Será obligatorio implementar una arquitectura de resiliencia avanzada.", 8),
        _h("3.1.9. Alta disponibilidad y resiliencia", 4, 9),
        _p("Funcionamiento en clúster con tolerancia a fallas de nodos.", 10),
        _h("3.2. Solución integral de resguardo de información (backup)", 3, 11),
        _p("La solución de backup deberá ser integral.", 12),
        _h("· Equipo Principal de Almacenamiento de BackUp", 2, 13),
        _h("o Rendimiento y Conectividad Mínima:", 3, 14),
        _p("Streams concurrentes: hasta 2000 flujos de escritura.", 15),
        _h("3.3. Equipamiento de cómputo y dimensionamiento (sizing)", 3, 16),
        _p("El equipamiento ofertado deberá ser de una marca reconocida.", 17),
        _h("3.3.1. Capacidades a satisfacer y base de cálculo", 4, 18),
        _p("El dimensionamiento deberá satisfacer la totalidad de las cargas.", 19),
    ]


# ---------------------------------------------------------------------------
# Los dos casos medidos
# ---------------------------------------------------------------------------


def test_una_subseccion_en_vineta_no_borra_sus_ancestros_numerados() -> None:
    """El chunk 34: perdía `3.`, `3.1.` y `3.1.8.`."""
    intermedios = _to_intermediate_blocks(_bancor())

    path = _path_de(intermedios, "controles de seguridad obligatorios sobre ESXi")

    assert path == [
        "PLIEGO DE ESPECIFICACIONES TÉCNICAS",
        "3. Especificaciones técnicas",
        "3.1. Plataforma de software de nube privada",
        "3.1.8. Seguridad (Security by Design / Security by Default)",
        "Capa de infraestructura y virtualización (VCF)",
    ]


def test_una_seccion_numerada_no_cuelga_de_una_subseccion_de_otra() -> None:
    """El chunk 69: `3.3.` colgada de `· Equipo Principal de Almacenamiento de
    BackUp`, que es contenido de 3.2."""
    intermedios = _to_intermediate_blocks(_bancor())

    path = _path_de(intermedios, "El equipamiento ofertado deberá ser de una marca")

    assert path == [
        "PLIEGO DE ESPECIFICACIONES TÉCNICAS",
        "3. Especificaciones técnicas",
        "3.3. Equipamiento de cómputo y dimensionamiento (sizing)",
    ]


def test_la_siguiente_seccion_numerada_recupera_la_jerarquia() -> None:
    """`3.1.9.` tiene que volver a colgar de `3.1.`, no de la viñeta anterior."""
    intermedios = _to_intermediate_blocks(_bancor())

    path = _path_de(intermedios, "Funcionamiento en clúster")

    assert path == [
        "PLIEGO DE ESPECIFICACIONES TÉCNICAS",
        "3. Especificaciones técnicas",
        "3.1. Plataforma de software de nube privada",
        "3.1.9. Alta disponibilidad y resiliencia",
    ]


def test_las_vinetas_de_3_2_quedan_dentro_de_3_2() -> None:
    intermedios = _to_intermediate_blocks(_bancor())

    path = _path_de(intermedios, "Streams concurrentes")

    assert path[:3] == [
        "PLIEGO DE ESPECIFICACIONES TÉCNICAS",
        "3. Especificaciones técnicas",
        "3.2. Solución integral de resguardo de información (backup)",
    ]
    assert "· Equipo Principal de Almacenamiento de BackUp" in path


# ---------------------------------------------------------------------------
# Cómo se desplaza
# ---------------------------------------------------------------------------


def test_el_tramo_se_desplaza_en_bloque_y_no_se_aplasta() -> None:
    """Aplastar todo al piso convertiría en hermanos a encabezados que DI puso
    uno dentro del otro. Se desplaza el tramo entero por el mismo delta."""
    bloques = [
        _h("2. Objeto", 2, 0),
        _h("· Padre", 2, 1),
        _h("o Hijo", 3, 2),
        _h("o Otro hijo", 3, 3),
    ]

    niveles = _niveles(_nest_unnumbered_headings_under_numbered(bloques))

    assert niveles["· Padre"] == 3
    assert niveles["o Hijo"] == 4
    assert niveles["o Otro hijo"] == 4


def test_un_tramo_que_ya_esta_debajo_no_se_toca() -> None:
    bloques = [
        _h("2. Objeto", 2, 0),
        _h("Subtítulo", 5, 1),
    ]

    assert _nest_unnumbered_headings_under_numbered(bloques) == bloques


def test_el_piso_es_el_del_ultimo_numerado_no_el_del_primero() -> None:
    bloques = [
        _h("1. Generalidades", 2, 0),
        _h("1.1. Objetivo", 3, 1),
        _h("Detalle", 2, 2),
    ]

    assert _niveles(_nest_unnumbered_headings_under_numbered(bloques))["Detalle"] == 4


# ---------------------------------------------------------------------------
# Guardas
# ---------------------------------------------------------------------------


def test_un_pliego_sin_numeracion_decimal_no_se_toca() -> None:
    """El de Rosario numera por "Artículo Nº 10:", que no declara profundidad.
    Sin encabezados numerados no hay piso y la función no puede opinar."""
    bloques = [
        _h("PLIEGO DE CONDICIONES PARTICULARES", 1, 0),
        _h("Artículo Nº 10: GARANTÍA DE ADJUDICACIÓN", 2, 1),
        _h("ARTÍCULO 12: PLAZO DE ENTREGA", 2, 2),
    ]

    assert _nest_unnumbered_headings_under_numbered(bloques) == bloques


def test_los_encabezados_previos_al_primer_numerado_no_se_tocan() -> None:
    """La carátula del pliego es ancestro de todo, no descendiente de nada."""
    bloques = [
        _h("PLIEGO DE ESPECIFICACIONES TÉCNICAS", 1, 0),
        _h("1. Generalidades", 2, 1),
    ]

    assert _nest_unnumbered_headings_under_numbered(bloques) == bloques


def test_un_anexo_sigue_siendo_hermano_de_las_secciones() -> None:
    """Es la excepción a la regla: un pliego que numera sus secciones igual pone
    el anexo al mismo nivel. El anexo no cuelga del último artículo."""
    bloques = [
        _h("5. Niveles de servicio", 2, 0),
        _h("5.3. Garantía", 3, 1),
        _h("ANEXO I - Planilla de cotización", 2, 2),
        _h("APÉNDICE A", 2, 3),
    ]

    niveles = _niveles(_nest_unnumbered_headings_under_numbered(bloques))

    assert niveles["ANEXO I - Planilla de cotización"] == 2
    assert niveles["APÉNDICE A"] == 2


def test_despues_de_un_anexo_el_piso_sigue_siendo_el_del_ultimo_numerado() -> None:
    """El anexo corta el tramo pero no puede fijar piso: su propio nivel lo sigue
    poniendo DI, así que usarlo como piso propagaría el error que se corrige."""
    bloques = [
        _h("5. Niveles de servicio", 2, 0),
        _h("ANEXO I", 2, 1),
        _h("Contenido del anexo", 2, 2),
    ]

    niveles = _niveles(_nest_unnumbered_headings_under_numbered(bloques))

    assert niveles["Contenido del anexo"] == 3


def test_los_parrafos_no_cuentan_como_encabezados() -> None:
    bloques = [
        _h("2. Objeto", 2, 0),
        _p("3.1. Esto es una cita dentro de un párrafo, no un encabezado.", 1),
        _h("Subtítulo", 2, 2),
    ]

    assert _niveles(_nest_unnumbered_headings_under_numbered(bloques))["Subtítulo"] == 3


def test_una_lista_vacia_no_rompe() -> None:
    assert _nest_unnumbered_headings_under_numbered([]) == []
