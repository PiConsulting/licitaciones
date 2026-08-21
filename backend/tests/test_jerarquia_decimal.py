"""CHK-16: los encabezados con numeración decimal no se normalizaban nunca.

`_normalize_numbered_heading_levels` usa `^(\\d+)\\.\\s+[A-ZÁÉÍÓÚÑ]`, que matchea
"1. Generalidades" pero **no** "1.6.", "3.1.1." ni "5.3.". Es decir: no tocaba
ningún encabezado decimal, que es toda la numeración del PET de Bancor.

La jerarquía quedaba siendo la que Azure DI infirió del tamaño de la tipografía.
En el análisis `f33897ba` eso produjo el `section_path` del chunk 12:

    PLIEGO … > 1. Generalidades > 1.6. Visita técnica obligatoria > 1.7. Plazo de entrega

`1.6` y `1.7` son hermanos, no padre e hijo. Ese path alimenta el `section_hint`
que desambigua los resaltados en el PDF y el contexto que ve el redactor de la
síntesis, así que una jerarquía inventada se propaga a las dos puntas.

Un pliego que numera sus secciones está DECLARANDO la jerarquía: "3.1.2." dice,
sin ambigüedad, que cuelga de "3.1", que cuelga de "3".
"""

from __future__ import annotations

from typing import Any

from extraction.chunking import (
    _decimal_heading_depth,
    _normalize_decimal_heading_levels,
    create_chunks,
)


def _heading(contenido: str, nivel: int, page: int, source_order: int) -> dict[str, Any]:
    return {
        "content": contenido,
        "heading_level": nivel,
        "page_number": page,
        "source_order": source_order,
    }


def _parrafo(contenido: str, page: int, source_order: int) -> dict[str, Any]:
    return {"content": contenido, "page_number": page, "source_order": source_order}


# La estructura real de Bancor: DI le dio a 1.7 un nivel más profundo que a 1.6.
BLOQUES_BANCOR = [
    _heading("PLIEGO DE ESPECIFICACIONES TÉCNICAS", 1, 1, 0),
    _heading("1. Generalidades", 2, 4, 1),
    _heading("1.6. Visita técnica obligatoria", 3, 6, 2),
    _parrafo("Los oferentes deberán realizar una visita técnica obligatoria a ambos data centers.", 6, 3),
    _heading("1.7. Plazo de entrega", 4, 6, 4),
    _parrafo("La entrega deberá producirse dentro de los cuarenta y cinco (45) días corridos.", 6, 5),
]


# ---------------------------------------------------------------------------
# El caso del hallazgo
# ---------------------------------------------------------------------------


def test_dos_secciones_del_mismo_nivel_quedan_hermanas() -> None:
    normalizados = _normalize_decimal_heading_levels(BLOQUES_BANCOR)

    niveles = {b["content"]: b["heading_level"] for b in normalizados if b.get("heading_level")}

    assert niveles["1.6. Visita técnica obligatoria"] == niveles["1.7. Plazo de entrega"]


def test_el_section_path_deja_de_anidar_1_7_bajo_1_6() -> None:
    chunks = create_chunks(BLOQUES_BANCOR, document_id="doc", correlation_id="corr")

    plazo = next(c for c in chunks if "cuarenta y cinco (45) días" in c["content"])

    assert "1.6. Visita técnica obligatoria" not in plazo["section_path"], (
        f"1.7 sigue colgando de 1.6: {plazo['section_path']}"
    )
    assert "1. Generalidades" in plazo["section_path"]
    assert "1.7. Plazo de entrega" in plazo["section_path"]


def test_la_profundidad_declarada_manda_sobre_la_que_infirio_azure() -> None:
    """`3.1.1.` cuelga de `3.1.`, que cuelga de `3.`, sin importar qué nivel les
    haya dado DI."""
    bloques = [
        _heading("3. Especificaciones técnicas", 2, 8, 0),
        _heading("3.1. Plataforma de software de nube privada", 5, 8, 1),
        _heading("3.1.1. Definición de la solución", 3, 8, 2),
        _parrafo("Se busca una solución robusta y escalable para alojar aplicaciones.", 8, 3),
    ]

    chunks = create_chunks(bloques, document_id="doc", correlation_id="corr")
    definicion = next(c for c in chunks if "solución robusta" in c["content"])

    partes = definicion["section_path"].split(" > ")
    assert partes == [
        "3. Especificaciones técnicas",
        "3.1. Plataforma de software de nube privada",
        "3.1.1. Definición de la solución",
    ]


# ---------------------------------------------------------------------------
# La profundidad declarada
# ---------------------------------------------------------------------------


def test_la_profundidad_sale_de_la_numeracion() -> None:
    assert _decimal_heading_depth("1. Generalidades") == 1
    assert _decimal_heading_depth("1.7. Plazo de entrega") == 2
    assert _decimal_heading_depth("3.1.1. Definición de la solución") == 3
    assert _decimal_heading_depth("5.3. Garantía y servicio post-venta") == 2


def test_el_escape_de_markdown_no_rompe_la_deteccion() -> None:
    """Document Intelligence emite "6\\. Calidad" en el markdown."""
    assert _decimal_heading_depth("6\\. Calidad y antecedentes de los oferentes") == 1


def test_sin_punto_final_no_es_un_encabezado_numerado() -> None:
    """"1 Plataforma de software" es la columna Ítem de una planilla."""
    assert _decimal_heading_depth("1 Plataforma de software de Nube Privada") is None
    assert _decimal_heading_depth("ARTÍCULO 12: PLAZO DE ENTREGA") is None
    assert _decimal_heading_depth("") is None
    assert _decimal_heading_depth(None) is None


# ---------------------------------------------------------------------------
# Guardas
# ---------------------------------------------------------------------------


def test_un_pliego_sin_numeracion_decimal_no_se_toca() -> None:
    """El de Rosario numera con "Artículo N": nada de esto debe aplicar."""
    bloques = [
        _heading("Artículo 1: OBJETO", 2, 2, 0),
        _heading("Artículo 2: ACEPTACIÓN DE LAS CONDICIONES", 3, 2, 1),
    ]

    assert _normalize_decimal_heading_levels(bloques) == bloques


def test_los_encabezados_de_primer_nivel_no_los_toca_esta_funcion() -> None:
    """De la consecutividad de "1., 2., 3." se sigue ocupando
    `_normalize_numbered_heading_levels`, que usa una señal que acá no está."""
    bloques = [
        _heading("1. Generalidades", 2, 4, 0),
        _heading("2. Composición de la solución", 5, 7, 1),
        _heading("2.1. Ítems a cotizar", 6, 7, 2),
    ]

    normalizados = _normalize_decimal_heading_levels(bloques)

    assert normalizados[1]["heading_level"] == 5, "tocó un encabezado de primer nivel"
    assert normalizados[2]["heading_level"] == 3


def test_un_documento_sin_encabezados_no_rompe() -> None:
    bloques = [_parrafo("Un párrafo suelto del pliego.", 1, 0)]

    assert _normalize_decimal_heading_levels(bloques) == bloques


def test_sin_encabezados_de_primer_nivel_la_base_se_deduce() -> None:
    """Un anexo que arranca directamente en "4.1." sin traer el "4."."""
    bloques = [
        _heading("4.1. Obligaciones del proveedor", 3, 34, 0),
        _heading("4.2. Plan de trabajos", 5, 34, 1),
    ]

    normalizados = _normalize_decimal_heading_levels(bloques)

    assert normalizados[0]["heading_level"] == normalizados[1]["heading_level"]
