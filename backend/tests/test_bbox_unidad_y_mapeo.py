"""ING-06 e ING-07: por qué el 100% de los chunks salía con `bbox: []`.

  - ING-06: `_page_unit_scales` decidía la escala con `str(page.unit) == "inch"`.
    El SDK devuelve `LengthUnit.INCH`, un `class LengthUnit(str, Enum)`, y en un
    enum de Python `Enum.__str__` le gana a `str.__str__`: `str(LengthUnit.INCH)`
    es `"LengthUnit.INCH"`. La comparación fallaba en todas las páginas de todos
    los documentos, el diccionario de escalas quedaba vacío, y
    `_extract_bounding_boxes` descartaba cada bbox por su rama de "unidad
    desconocida". Medido sobre el pliego de Servidores 2025: 161 párrafos con
    polígono, 0 con bbox convertido.

  - ING-07: el índice bloque → bbox es POSICIONAL, `(página, orden)`. Sólo es
    correcto si el parser de markdown produce exactamente un bloque por párrafo
    de DI. En ese mismo pliego no lo hace: las 10 páginas tienen dos párrafos
    más que bloques. Con el bbox vacío eso no se notaba; restaurarlo sin más
    haría que cada bloque recibiera las coordenadas de OTRO texto -- y
    `_starts_on_same_line` (CHK-12) fusionaría encabezados mirando la geometría
    equivocada. Un mapeo corrido es peor que ninguno.
"""

from __future__ import annotations

from typing import Any

from extraction.document_intelligence import (
    _build_para_id_index,
    _enrich_blocks_with_para_id,
    _extract_bounding_boxes,
    _normalized_length_unit,
    _page_unit_scales,
    _POINTS_PER_INCH,
)


class _Region:
    def __init__(self, page: int, polygon: list[float]) -> None:
        self.page_number = page
        self.polygon = polygon


class _Para:
    def __init__(self, page: int, content: str, offset: int, polygon: list[float] | None = None) -> None:
        self.content = content
        self.bounding_regions = [_Region(page, polygon or [1.0, 2.0, 7.0, 2.0, 7.0, 2.2, 1.0, 2.2])]
        self.span = type("Span", (), {"offset": offset})()


class _Page:
    def __init__(self, page_number: int, unit: Any, width: float = 8.5, height: float = 11.0) -> None:
        self.page_number = page_number
        self.unit = unit
        self.width = width
        self.height = height


class _Result:
    def __init__(self, pages: list[_Page]) -> None:
        self.pages = pages


# ---------------------------------------------------------------------------
# ING-06: la unidad
# ---------------------------------------------------------------------------


def test_el_enum_del_sdk_se_reconoce_como_pulgadas() -> None:
    """El caso exacto: `LengthUnit.INCH` del SDK de Azure."""
    from azure.ai.documentintelligence.models import LengthUnit

    assert _normalized_length_unit(LengthUnit.INCH) == "inch"
    assert _normalized_length_unit(LengthUnit.PIXEL) == "pixel"


def test_str_del_enum_no_es_su_valor() -> None:
    """La premisa del bug, fijada para que no vuelva a asumirse lo contrario."""
    from azure.ai.documentintelligence.models import LengthUnit

    assert str(LengthUnit.INCH) != "inch"
    assert LengthUnit.INCH.value == "inch"


def test_un_pdf_en_pulgadas_recibe_la_escala_a_puntos() -> None:
    from azure.ai.documentintelligence.models import LengthUnit

    escalas = _page_unit_scales(_Result([_Page(n, LengthUnit.INCH) for n in (1, 2, 3)]))

    assert escalas == {1: _POINTS_PER_INCH, 2: _POINTS_PER_INCH, 3: _POINTS_PER_INCH}


def test_el_bbox_llega_convertido_a_puntos() -> None:
    """La consecuencia medible: 0 bbox útiles pasaban a ser todos."""
    from azure.ai.documentintelligence.models import LengthUnit

    escalas = _page_unit_scales(_Result([_Page(1, LengthUnit.INCH)]))
    bboxes = _extract_bounding_boxes(_Para(1, "Artículo 1: OBJETO", 0), escalas)

    assert bboxes, "el párrafo tenía polígono y no salió ningún bbox"
    assert bboxes[0]["x"] == 1.0 * _POINTS_PER_INCH
    assert bboxes[0]["y"] == 2.0 * _POINTS_PER_INCH


def test_una_imagen_en_pixeles_sigue_sin_escala() -> None:
    """No se puede convertir sin conocer el DPI: la rama de descarte se queda."""
    from azure.ai.documentintelligence.models import LengthUnit

    assert _page_unit_scales(_Result([_Page(1, LengthUnit.PIXEL)])) == {}


def test_las_formas_alternativas_de_la_unidad_tambien_se_entienden() -> None:
    """Guarda contra el próximo cambio del SDK: string pelado o StrEnum."""
    assert _normalized_length_unit("inch") == "inch"
    assert _normalized_length_unit("INCH") == "inch"
    assert _normalized_length_unit("LengthUnit.INCH") == "inch"
    assert _normalized_length_unit(None) == ""


# ---------------------------------------------------------------------------
# ING-07: el mapeo posicional
# ---------------------------------------------------------------------------


def _bloque(content: str, page: int, source_order: int) -> dict[str, Any]:
    return {"content": content, "page_number": page, "source_order": source_order}


def test_un_bloque_recibe_el_bbox_de_su_propio_parrafo() -> None:
    """El camino feliz: parser y DI en fase."""
    parrafos = [
        _Para(1, "Artículo 1: OBJETO", 0, [1.0, 1.0, 7.0, 1.0, 7.0, 1.2, 1.0, 1.2]),
        _Para(1, "La Municipalidad llama a Licitación Privada.", 100, [1.0, 2.0, 7.0, 2.0, 7.0, 2.2, 1.0, 2.2]),
    ]
    indice = _build_para_id_index(parrafos, {1: _POINTS_PER_INCH})
    bloques = [
        _bloque("Artículo 1: OBJETO", 1, 0),
        _bloque("La Municipalidad llama a Licitación Privada.", 1, 1),
    ]

    _enrich_blocks_with_para_id(bloques, indice, {1: (8.5 * 72, 11.0 * 72)})

    assert bloques[0]["bbox"][0]["y"] == 1.0 * _POINTS_PER_INCH
    assert bloques[1]["bbox"][0]["y"] == 2.0 * _POINTS_PER_INCH


def test_un_bloque_desfasado_encuentra_igual_su_parrafo() -> None:
    """ING-09, el caso del hallazgo: DI emite un párrafo que el parser de
    markdown no produce (una figura, el membrete), así que el índice posicional
    se corre y el bloque 0 apuntaba al párrafo 0, que es otro texto.

    Antes esto se resolvía descartando el bbox (ING-07): correcto pero caro --
    sobre el PET de Bancor sobrevivían 3 de 86. Emparejando por texto, el
    desfase deja de importar.
    """
    parrafos = [
        # Este párrafo NO aparece como bloque del parser de markdown.
        _Para(1, "Municipalidad de Rosario - LICITACIÓN PRIVADA", 0, [1.0, 0.5, 7.0, 0.5, 7.0, 0.7, 1.0, 0.7]),
        _Para(1, "Artículo 1: OBJETO", 100, [1.0, 1.0, 7.0, 1.0, 7.0, 1.2, 1.0, 1.2]),
    ]
    indice = _build_para_id_index(parrafos, {1: _POINTS_PER_INCH})
    bloques = [_bloque("Artículo 1: OBJETO", 1, 0)]

    _enrich_blocks_with_para_id(bloques, indice, {1: (8.5 * 72, 11.0 * 72)})

    assert bloques[0]["bbox"], "el bloque quedó sin bbox habiendo un párrafo con su texto"
    assert bloques[0]["bbox"][0]["y"] == 1.0 * _POINTS_PER_INCH, (
        "se quedó con las coordenadas del membrete, no con las suyas"
    )
    assert bloques[0]["para_id"] == (1, 1), "el para_id tiene que ser el del párrafo real"


def test_un_bloque_sin_parrafo_equivalente_no_toma_el_de_nadie() -> None:
    """La guarda sigue: si ningún párrafo de la página tiene ese texto, el
    bloque se queda sin bbox. Nunca hereda el del vecino."""
    parrafos = [_Para(1, "Un párrafo que no se parece en nada al bloque.", 0)]
    indice = _build_para_id_index(parrafos, {1: _POINTS_PER_INCH})
    bloques = [_bloque("Artículo 1: OBJETO", 1, 0)]

    _enrich_blocks_with_para_id(bloques, indice, {1: (8.5 * 72, 11.0 * 72)})

    assert bloques[0]["bbox"] == []
    assert bloques[0]["para_id"] is None


def test_dos_bloques_con_el_mismo_texto_toman_parrafos_distintos() -> None:
    """El membrete "BANCOR" aparece dos veces en la misma página. Sin control,
    los dos bloques se llevarían el primero y el segundo quedaría con el
    rectángulo del de arriba."""
    parrafos = [
        _Para(1, "BANCOR", 0, [1.0, 0.5, 3.0, 0.5, 3.0, 0.7, 1.0, 0.7]),
        _Para(1, "Texto intermedio del pliego que separa los dos membretes.", 50),
        _Para(1, "BANCOR", 200, [1.0, 9.0, 3.0, 9.0, 3.0, 9.2, 1.0, 9.2]),
    ]
    indice = _build_para_id_index(parrafos, {1: _POINTS_PER_INCH})
    bloques = [_bloque("BANCOR", 1, 0), _bloque("BANCOR", 1, 1)]

    _enrich_blocks_with_para_id(bloques, indice, {1: (8.5 * 72, 11.0 * 72)})

    assert bloques[0]["bbox"][0]["y"] == 0.5 * _POINTS_PER_INCH
    assert bloques[1]["bbox"][0]["y"] == 9.0 * _POINTS_PER_INCH, (
        "el segundo membrete se llevó las coordenadas del primero"
    )


def test_un_numero_suelto_no_matchea_con_otro_que_lo_contiene() -> None:
    """Una tabla de contenidos es una página llena de números sueltos. Con
    contención, el bloque "4" matchearía el párrafo "41"."""
    parrafos = [
        _Para(1, "41", 0, [1.0, 0.5, 3.0, 0.5, 3.0, 0.7, 1.0, 0.7]),
        _Para(1, "4", 50, [1.0, 2.0, 3.0, 2.0, 3.0, 2.2, 1.0, 2.2]),
    ]
    indice = _build_para_id_index(parrafos, {1: _POINTS_PER_INCH})
    bloques = [_bloque("4", 1, 0)]

    _enrich_blocks_with_para_id(bloques, indice, {1: (8.5 * 72, 11.0 * 72)})

    assert bloques[0]["bbox"][0]["y"] == 2.0 * _POINTS_PER_INCH


def test_el_orden_de_lectura_desempata_antes_que_el_barrido_completo() -> None:
    """Dos párrafos idénticos y dos bloques: el primero se queda con el de
    arriba aunque el barrido completo también lo encontraría."""
    parrafos = [
        _Para(1, "Artículo 1: OBJETO", 0, [1.0, 1.0, 7.0, 1.0, 7.0, 1.2, 1.0, 1.2]),
        _Para(1, "Artículo 1: OBJETO", 100, [1.0, 5.0, 7.0, 5.0, 7.0, 5.2, 1.0, 5.2]),
    ]
    indice = _build_para_id_index(parrafos, {1: _POINTS_PER_INCH})
    bloques = [_bloque("Artículo 1: OBJETO", 1, 0), _bloque("Artículo 1: OBJETO", 1, 1)]

    _enrich_blocks_with_para_id(bloques, indice, {1: (8.5 * 72, 11.0 * 72)})

    assert bloques[0]["para_id"] == (1, 0)
    assert bloques[1]["para_id"] == (1, 1)


def test_las_diferencias_de_normalizacion_no_cuentan_como_desalineacion() -> None:
    """El parser colapsa espacios y une líneas: eso no es otro párrafo."""
    parrafos = [_Para(1, "Artículo 1:   OBJETO\nDe la contratación", 0)]
    indice = _build_para_id_index(parrafos, {1: _POINTS_PER_INCH})
    bloques = [_bloque("Artículo 1: OBJETO De la contratación", 1, 0)]

    _enrich_blocks_with_para_id(bloques, indice, {1: (8.5 * 72, 11.0 * 72)})

    assert bloques[0]["bbox"], "una diferencia de espacios tiró un bbox correcto"


def test_un_bloque_que_es_un_fragmento_del_parrafo_conserva_el_bbox() -> None:
    """El parser a veces recorta viñetas o parte un párrafo largo."""
    parrafos = [_Para(1, "a) Documentación que acredite la personería y capacidad legal.", 0)]
    indice = _build_para_id_index(parrafos, {1: _POINTS_PER_INCH})
    bloques = [_bloque("Documentación que acredite la personería y capacidad legal.", 1, 0)]

    _enrich_blocks_with_para_id(bloques, indice, {1: (8.5 * 72, 11.0 * 72)})

    assert bloques[0]["bbox"]


def test_las_tablas_siguen_sin_para_id() -> None:
    """Guarda: las filas de tabla se extraen por separado, con su propio bbox."""
    indice = _build_para_id_index([_Para(1, "Un párrafo cualquiera.", 0)], {1: _POINTS_PER_INCH})
    bloques = [{"content": "fila", "page_number": 1, "source_order": 0, "table_ref": {"id": "T1"}}]

    _enrich_blocks_with_para_id(bloques, indice, {1: (8.5 * 72, 11.0 * 72)})

    assert bloques[0]["para_id"] is None
    assert bloques[0]["bbox"] == []
