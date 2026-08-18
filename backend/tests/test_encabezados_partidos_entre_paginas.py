"""CHK-09: la fusión de encabezados partidos entre páginas concatenaba sin espacio.

`_merge_split_headings_across_pages` existe para el caso real de Document
Intelligence: página N `"ARTÍCULO 12: PLA"`, página N+1 `"ZO DE ENTREGA"`. Ahí DI
partió una PALABRA, y concatenar sin espacio es correcto.

Pero el disparador `next_starts_lowercase` se activa también cuando lo que DI
partió es un TÍTULO en dos renglones tipográficos, que es frecuente: página N
`"5. GARANTÍAS"`, página N+1 `"de cumplimiento de contrato"`. Con la
concatenación sin espacio eso producía:

    "5. GARANTÍASde cumplimiento de contrato"

El token "garantiasde" no existe en ningún lado. `_classify_by_heading` lo
sobrevive de casualidad —busca "garantia" por substring y sigue siendo prefijo—
pero el `title` que va al embedding y al campo `searchable` del índice queda
corrupto, y `_normalize_heading_value` no lo arregla. O sea: el chunk pierde
capacidad de ser recuperado por el texto de su propio título, que es justo lo
que IDX-01 vino a garantizar.

La distinción se hace por la FORMA de los tokens del borde, no por vocabulario:
un pedazo de palabra queda como una tirada corta en mayúsculas.
"""

from __future__ import annotations

from typing import Any

from extraction.chunking import _join_split_heading, _merge_split_headings_across_pages


def _heading(contenido: str, page: int, nivel: int = 2, source_order: int = 0) -> dict[str, Any]:
    return {
        "content": contenido,
        "heading_level": nivel,
        "page_number": page,
        "source_order": source_order,
    }


def _contenidos(blocks: list[dict[str, Any]]) -> list[str]:
    return [b["content"] for b in blocks]


# ---------------------------------------------------------------------------
# El caso del hallazgo
# ---------------------------------------------------------------------------


def test_un_titulo_partido_en_dos_renglones_se_une_con_espacio() -> None:
    bloques = [_heading("5. GARANTÍAS", 4), _heading("de cumplimiento de contrato", 5)]

    resultado = _merge_split_headings_across_pages(bloques)

    assert _contenidos(resultado) == ["5. GARANTÍAS de cumplimiento de contrato"]


def test_el_token_corrupto_ya_no_se_produce() -> None:
    """La consecuencia concreta: "garantiasde" no existe, y el título es lo que
    alimenta el embedding y el campo searchable del índice (IDX-01)."""
    bloques = [_heading("5. GARANTÍAS", 4), _heading("de cumplimiento de contrato", 5)]

    fusionado = _merge_split_headings_across_pages(bloques)[0]["content"]

    assert "GARANTÍASde" not in fusionado
    assert "GARANTÍAS" in fusionado.split(" de ")[0]


# ---------------------------------------------------------------------------
# Guarda: el caso que motivó la función tiene que seguir andando
# ---------------------------------------------------------------------------


def test_una_palabra_partida_se_une_sin_espacio() -> None:
    bloques = [_heading("ARTÍCULO 12: PLA", 4), _heading("ZO DE ENTREGA", 5)]

    resultado = _merge_split_headings_across_pages(bloques)

    assert _contenidos(resultado) == ["ARTÍCULO 12: PLAZO DE ENTREGA"]


def test_el_pedazo_puede_quedar_de_cualquiera_de_los_dos_lados() -> None:
    assert _join_split_heading("ARTÍCULO 12: PLAZ", "O DE ENTREGA") == "ARTÍCULO 12: PLAZO DE ENTREGA"
    assert _join_split_heading("Artículo Nº 10: GAR", "ANTÍA DE ADJUDICACIÓN") == (
        "Artículo Nº 10: GARANTÍA DE ADJUDICACIÓN"
    )


# ---------------------------------------------------------------------------
# Guardas: palabras cortas que NO son pedazos
# ---------------------------------------------------------------------------


def test_una_preposicion_al_borde_no_es_una_palabra_partida() -> None:
    """"LAS" es corta y está en mayúsculas, pero es una palabra completa."""
    assert _join_split_heading("CAPÍTULO II — DE LAS", "OBLIGACIONES DEL ADJUDICATARIO") == (
        "CAPÍTULO II — DE LAS OBLIGACIONES DEL ADJUDICATARIO"
    )


def test_un_titulo_que_termina_en_dos_puntos_se_une_con_espacio() -> None:
    """El corte no es dentro de una palabra: hay puntuación en el borde."""
    assert _join_split_heading("ARTÍCULO 12:", "PLAZO DE ENTREGA") == "ARTÍCULO 12: PLAZO DE ENTREGA"


def test_una_continuacion_en_minusculas_de_un_titulo_largo_lleva_espacio() -> None:
    assert _join_split_heading("3.1. Plataforma de", "software de nube privada") == (
        "3.1. Plataforma de software de nube privada"
    )


# ---------------------------------------------------------------------------
# Guardas: lo que no se puede fusionar
# ---------------------------------------------------------------------------


def test_dos_anexos_consecutivos_no_se_fusionan() -> None:
    bloques = [_heading("ANEXO I", 4), _heading("ANEXO II", 5)]

    assert _contenidos(_merge_split_headings_across_pages(bloques)) == ["ANEXO I", "ANEXO II"]


def test_dos_titulos_completos_en_paginas_seguidas_no_se_fusionan() -> None:
    bloques = [_heading("ARTÍCULO 12: PLAZO DE ENTREGA", 4), _heading("ARTÍCULO 13: DEL PAGO", 5)]

    assert len(_merge_split_headings_across_pages(bloques)) == 2


def test_paginas_no_consecutivas_no_se_fusionan() -> None:
    bloques = [_heading("5. GARANTÍAS", 4), _heading("de cumplimiento", 7)]

    assert len(_merge_split_headings_across_pages(bloques)) == 2


def test_niveles_distintos_no_se_fusionan() -> None:
    bloques = [_heading("5. GARANTÍAS", 4, nivel=2), _heading("de cumplimiento", 5, nivel=3)]

    assert len(_merge_split_headings_across_pages(bloques)) == 2


# ---------------------------------------------------------------------------
# Bordes
# ---------------------------------------------------------------------------


def test_una_mitad_vacia_devuelve_la_otra() -> None:
    assert _join_split_heading("", "ZO DE ENTREGA") == "ZO DE ENTREGA"
    assert _join_split_heading("ARTÍCULO 12: PLA", "") == "ARTÍCULO 12: PLA"
    assert _join_split_heading("", "") == ""


def test_una_palabra_larga_partida_con_cambio_de_caja_se_une_sin_espacio() -> None:
    """"DOCUMEN" + "tación": el pedazo de la izquierda puede ser largo. La
    primera versión del fix miraba sólo el largo del token izquierdo y trataba
    esto como un título en dos renglones, produciendo "DOCUMEN tación".

    Lo atrapó un test que ya existía (`test_merge_split_headings.py`).
    """
    assert _join_split_heading("ARTÍCULO 6: DOCUMEN", "tación a Presentar") == (
        "ARTÍCULO 6: DOCUMENtación a Presentar"
    )


def test_la_izquierda_terminada_en_palabra_corta_completa_nunca_es_corte_de_palabra() -> None:
    """Es lo que separa "DOCUMEN"+"tación" de "Plataforma de"+"software"."""
    assert _join_split_heading("3.1. Plataforma de", "software de nube privada") == (
        "3.1. Plataforma de software de nube privada"
    )
    assert _join_split_heading("Artículo 9. Adjudicación", "y notificación a oferentes") == (
        "Artículo 9. Adjudicación y notificación a oferentes"
    )
