"""HL-09, paso 1: guardar dónde leyó Document Intelligence cada renglón.

En el análisis de Santa Fe el resaltado falla al 100 % en exactamente dos de los
cinco documentos --el pliego principal y el Anexo 2-- y funciona al 100 % en los
otros tres. Los dos que fallan son escaneos: `compute_highlight_regions` usa
PyMuPDF `search_for`, que sólo encuentra texto EMBEBIDO, mientras que Azure DI
hace OCR y por eso el análisis sale completo.

Y no hay red debajo. Cuando no hay regiones el visor cae a decorar la capa de
texto de react-pdf (`PDFPage.tsx:83`), que en un escaneo también está vacía: la
persona no ve nada, ni rectángulo ni texto marcado. La decisión de HL-08 --que
pintar el párrafo entero es peor que no pintar nada-- era correcta PORQUE existía
esa red; en un escaneo la alternativa no es "marcado preciso", es nada.

Este paso sólo GUARDA la geometría por renglón que DI ya devuelve. No la lee
nadie todavía: es aditivo a propósito, para que indexar con o sin ella no cambie
ningún comportamiento actual.
"""

from __future__ import annotations

from typing import Any

from extraction.document_intelligence import (
    _attach_lines_to_blocks,
    _build_line_index,
)

# Azure DI reporta en PULGADAS para PDF; el pipeline trabaja en puntos.
PULGADAS_A_PUNTOS = {1: 72.0}


class _Renglon:
    def __init__(self, content: str, polygon: list[float]) -> None:
        self.content = content
        self.polygon = polygon


class _Pagina:
    def __init__(self, page_number: int, lines: list[_Renglon]) -> None:
        self.page_number = page_number
        self.lines = lines
        self.unit = "inch"
        self.width = 8.5
        self.height = 11.0


class _Resultado:
    def __init__(self, pages: list[_Pagina]) -> None:
        self.pages = pages


def _rect(x: float, y: float, ancho: float, alto: float) -> list[float]:
    """Polígono de DI: cuatro esquinas, top-left origin."""
    return [x, y, x + ancho, y, x + ancho, y + alto, x, y + alto]


def _resultado_de_una_pagina() -> _Resultado:
    """Tres renglones apilados, como los devuelve DI para un párrafo."""
    return _Resultado(
        [
            _Pagina(
                1,
                [
                    _Renglon("OBJETO: ADQUISICIÓN DE UN SISTEMA DE ALMACENAMIENTO", _rect(1.0, 2.0, 6.0, 0.15)),
                    _Renglon("COMPUESTO POR 2 (DOS) SUBSISTEMAS QUE TRABAJEN", _rect(1.0, 2.2, 5.8, 0.15)),
                    _Renglon("ACTIVO-ACTIVO Y SERVICIOS DE INSTALACIÓN", _rect(1.0, 2.4, 5.0, 0.15)),
                ],
            )
        ]
    )


# ---------------------------------------------------------------------------
# El índice de renglones
# ---------------------------------------------------------------------------


def test_los_renglones_salen_en_puntos_no_en_pulgadas() -> None:
    """ING-03/ING-06 otra vez: el contrato de `highlight_regions` es PUNTOS. Un
    renglón en pulgadas se dibuja como una mancha de 1 punto en la esquina."""
    index = _build_line_index(_resultado_de_una_pagina(), PULGADAS_A_PUNTOS)

    primero = index[1][0]
    assert primero["x"] == 72.0
    assert primero["y"] == 144.0
    assert round(primero["width"], 1) == 432.0


def test_cada_renglon_lleva_su_texto() -> None:
    """Sin el texto no se puede saber QUÉ renglón corresponde a la cita, y todo
    esto se vuelve el rectángulo del párrafo de nuevo."""
    index = _build_line_index(_resultado_de_una_pagina(), PULGADAS_A_PUNTOS)

    assert [r["t"] for r in index[1]] == [
        "OBJETO: ADQUISICIÓN DE UN SISTEMA DE ALMACENAMIENTO",
        "COMPUESTO POR 2 (DOS) SUBSISTEMAS QUE TRABAJEN",
        "ACTIVO-ACTIVO Y SERVICIOS DE INSTALACIÓN",
    ]


def test_los_renglones_quedan_en_orden_de_lectura() -> None:
    desordenado = _Resultado(
        [
            _Pagina(
                1,
                [
                    _Renglon("tercero", _rect(1.0, 2.4, 5.0, 0.15)),
                    _Renglon("primero", _rect(1.0, 2.0, 6.0, 0.15)),
                    _Renglon("segundo", _rect(1.0, 2.2, 5.8, 0.15)),
                ],
            )
        ]
    )

    index = _build_line_index(desordenado, PULGADAS_A_PUNTOS)

    assert [r["t"] for r in index[1]] == ["primero", "segundo", "tercero"]


def test_un_renglon_vacio_no_entra() -> None:
    resultado = _Resultado([_Pagina(1, [_Renglon("   ", _rect(1.0, 2.0, 6.0, 0.15))])])

    assert _build_line_index(resultado, PULGADAS_A_PUNTOS) == {}


def test_sin_pages_devuelve_vacio() -> None:
    """Los fakes de los tests viejos no traen `pages`, y no pueden romperse."""

    class _SinPages:
        pass

    assert _build_line_index(_SinPages(), PULGADAS_A_PUNTOS) == {}
    assert _build_line_index(_Resultado([]), PULGADAS_A_PUNTOS) == {}


def test_una_pagina_sin_escala_conocida_se_descarta_entera() -> None:
    """Mismo criterio que `_extract_bounding_boxes`: antes que emitir una
    coordenada en una unidad que el visor no puede interpretar, no se emite."""
    index = _build_line_index(_resultado_de_una_pagina(), {})

    assert index == {}


# ---------------------------------------------------------------------------
# El colgado por bloque
# ---------------------------------------------------------------------------


def _bloque(x: float, y: float, ancho: float, alto: float) -> dict[str, Any]:
    return {"content": "…", "bbox": [{"page": 1, "x": x, "y": y, "width": ancho, "height": alto}]}


def test_el_bloque_se_queda_con_los_renglones_que_lo_componen() -> None:
    index = _build_line_index(_resultado_de_una_pagina(), PULGADAS_A_PUNTOS)
    # El párrafo entero: de y=144 a y=183.6 puntos.
    bloques = [_bloque(72.0, 144.0, 432.0, 40.0)]

    _attach_lines_to_blocks(bloques, index)

    assert [r["t"] for r in bloques[0]["lines"]] == [
        "OBJETO: ADQUISICIÓN DE UN SISTEMA DE ALMACENAMIENTO",
        "COMPUESTO POR 2 (DOS) SUBSISTEMAS QUE TRABAJEN",
        "ACTIVO-ACTIVO Y SERVICIOS DE INSTALACIÓN",
    ]


def test_un_bloque_no_se_lleva_los_renglones_de_otro_parrafo() -> None:
    """Si se llevara los de al lado, la cita se resaltaría en el párrafo
    equivocado -- que es exactamente el error que HL-08 vino a sacar."""
    index = _build_line_index(_resultado_de_una_pagina(), PULGADAS_A_PUNTOS)
    # Sólo el primer renglón: de y=144 a y=154.8.
    bloques = [_bloque(72.0, 144.0, 432.0, 11.0)]

    _attach_lines_to_blocks(bloques, index)

    assert [r["t"] for r in bloques[0]["lines"]] == [
        "OBJETO: ADQUISICIÓN DE UN SISTEMA DE ALMACENAMIENTO"
    ]


def test_un_renglon_que_sobresale_un_punto_sigue_siendo_del_parrafo() -> None:
    """Se contiene por el CENTRO del renglón: si se exigieran las cuatro
    esquinas, el renglón más largo --el que más probablemente tiene la cita--
    quedaría afuera por un punto de redondeo."""
    index = _build_line_index(_resultado_de_una_pagina(), PULGADAS_A_PUNTOS)
    # Un punto más angosto que el renglón más ancho.
    bloques = [_bloque(72.0, 144.0, 431.0, 40.0)]

    _attach_lines_to_blocks(bloques, index)

    assert len(bloques[0]["lines"]) == 3


def test_un_bloque_sin_bbox_no_recibe_renglones() -> None:
    bloques: list[dict[str, Any]] = [{"content": "…", "bbox": []}]

    _attach_lines_to_blocks(bloques, _build_line_index(_resultado_de_una_pagina(), PULGADAS_A_PUNTOS))

    assert "lines" not in bloques[0]


def test_sin_indice_no_se_toca_ningun_bloque() -> None:
    """Todo lo ya indexado antes de este cambio: la clave no está y nadie puede
    asumir que está."""
    bloques = [_bloque(72.0, 144.0, 432.0, 40.0)]
    antes = [dict(b) for b in bloques]

    _attach_lines_to_blocks(bloques, {})

    assert bloques == antes


def test_un_bloque_de_otra_pagina_no_se_lleva_nada() -> None:
    index = _build_line_index(_resultado_de_una_pagina(), PULGADAS_A_PUNTOS)
    bloques = [{"content": "…", "bbox": [{"page": 7, "x": 72.0, "y": 144.0, "width": 432.0, "height": 40.0}]}]

    _attach_lines_to_blocks(bloques, index)

    assert "lines" not in bloques[0]


# ---------------------------------------------------------------------------
# La propagación: la clave tiene que sobrevivir hasta el índice
# ---------------------------------------------------------------------------


def test_la_geometria_sobrevive_al_serializado_de_un_bloque_suelto() -> None:
    """El bug que ya costó `unverified` (SYN) y `chunk_id` (ATR-05): chunking
    reconstruye los bloques campo por campo, así que una clave nueva se pierde
    en silencio y el consumidor la ve siempre ausente."""
    from extraction.chunking import _blocks_data_for

    renglones = [{"x": 72.0, "y": 144.0, "width": 432.0, "height": 10.0, "t": "un renglón"}]
    bloque = {
        "para_id": [1, 4],
        "bbox": [{"page": 1, "x": 72.0, "y": 144.0, "width": 432.0, "height": 40.0}],
        "content": "un renglón",
        "lines": renglones,
    }

    serializado = _blocks_data_for(bloque, "un renglón", 1)

    assert serializado[0]["lines"] == renglones


def test_la_geometria_sobrevive_cuando_el_bloque_viene_de_varios_parrafos() -> None:
    """`_blocks_data_for` tiene DOS caminos y hay que probar los dos.

    El de arriba usa el retorno temprano de `if not merged_blocks`. Éste usa el
    comprehension del final, que es el camino normal: `_merge_intermediate_blocks`
    fusiona N párrafos y guarda sus `merged_blocks`, y después el bloque se parte
    en piezas. Lo agarró la verificación por reversión: sacando la propagación
    del comprehension, los 14 tests seguían pasando.
    """
    from extraction.chunking import _blocks_data_for

    primero = [{"x": 72.0, "y": 144.0, "width": 432.0, "height": 10.0, "t": "el primer párrafo"}]
    segundo = [{"x": 72.0, "y": 200.0, "width": 400.0, "height": 10.0, "t": "el segundo párrafo"}]
    bloque = {
        "content": "el primer párrafo\n\nel segundo párrafo",
        "merged_blocks": [
            {"para_id": [1, 4], "bbox": [{"page": 1, "x": 72.0, "y": 144.0, "width": 432.0, "height": 10.0}],
             "content": "el primer párrafo", "lines": primero},
            {"para_id": [1, 5], "bbox": [{"page": 1, "x": 72.0, "y": 200.0, "width": 400.0, "height": 10.0}],
             "content": "el segundo párrafo", "lines": segundo},
        ],
    }

    serializado = _blocks_data_for(bloque, "el primer párrafo\n\nel segundo párrafo", 1)

    assert [b.get("lines") for b in serializado] == [primero, segundo]


def test_un_bloque_sin_geometria_no_inventa_la_clave() -> None:
    from extraction.chunking import _blocks_data_for

    bloque = {
        "para_id": [1, 4],
        "bbox": [{"page": 1, "x": 72.0, "y": 144.0, "width": 432.0, "height": 40.0}],
        "content": "un renglón",
    }

    serializado = _blocks_data_for(bloque, "un renglón", 1)

    assert "lines" not in serializado[0]
