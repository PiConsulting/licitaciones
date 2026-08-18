"""ATR-07: la cita ensanchada tiene que seguir siendo LA MISMA cita.

`_widen_citation_with_chunk_context` existe para que una cita corta pero
verificada (33 caracteres: "Item 3: 4 (cuatro) LCD KVM Switch") se lea como
evidencia por sí sola. Tomaba el texto del chunk alrededor del match y lo
devolvía ensanchado.

El ensanchado se hacía con dos constantes ciegas -- 100 caracteres a la
izquierda y 140 a la derecha -- y después se recortaba con `clip_citation`, que
recorta un PREFIJO. Con el núcleo viviendo en el offset 100 de esa ventana, el
prefijo de 120 se lo comía: la cita final arrancaba en mitad de una palabra,
enumeraba ítems ajenos al dato, y no contenía el dato del item.

Salido de un análisis real (`objeto_alcance`, fuente 3): el pliego lista tres
ítems de equipamiento y el item afirmaba el tercero; la cita mostrada terminaba
hablando del primero y del segundo.

El resaltado no es un problema aparte: sigue fielmente a la cita, así que
marcaba tres renglones equivocados en el PDF.
"""

from __future__ import annotations

from typing import Any

from analysis.extraction.extractors.base import (
    _build_context_citation,
    _widen_citation_with_chunk_context,
)
from analysis.extraction.schemas import CITATION_MAX_CHARS, CITATION_PREFERRED_MIN_CHARS

# El párrafo real que produjo el bug.
ANEXO_EQUIPAMIENTO = (
    "ANEXO I - ESPECIFICACIONES TECNICAS. El equipamiento a proveer comprende: "
    "Item 1: 4 (cuatro) Servidores de aplicaciones tipo XEN Item 2: 4 (cuatro) "
    "Servidores de base de datos. Item 3: 4 (cuatro) LCD KVM Switch para montaje "
    "en rack de 19 pulgadas."
)
CITA_DEL_MODELO = "Item 3: 4 (cuatro) LCD KVM Switch"


def _chunk(content: str) -> dict[str, Any]:
    return {"id": "an-1--doc-1--7", "content": content, "block_type": "paragraph"}


# ---------------------------------------------------------------------------
# El caso del hallazgo
# ---------------------------------------------------------------------------


def test_la_cita_ensanchada_conserva_lo_que_el_modelo_cito() -> None:
    ensanchada = _widen_citation_with_chunk_context(CITA_DEL_MODELO, [_chunk(ANEXO_EQUIPAMIENTO)])

    assert CITA_DEL_MODELO.lower() in ensanchada.lower(), (
        f"el ensanchado perdió el dato del item: {ensanchada!r}"
    )


def test_la_cita_ensanchada_no_arranca_en_mitad_de_una_palabra() -> None:
    """El síntoma visible: la cita empezaba con "m 1:" -- la cola de "Item 1"."""
    ensanchada = _widen_citation_with_chunk_context(CITA_DEL_MODELO, [_chunk(ANEXO_EQUIPAMIENTO)])

    primera_palabra = ensanchada.split()[0]
    assert primera_palabra in ANEXO_EQUIPAMIENTO.split(), (
        f"la cita arranca con un fragmento de palabra: {primera_palabra!r}"
    )
    assert ensanchada.split()[-1] in ANEXO_EQUIPAMIENTO.split()


def test_la_cita_ensanchada_no_enumera_los_items_vecinos() -> None:
    """Ensanchar es dar contexto, no cambiar de tema. El item habla del ítem 3;
    la cita traía enteros el 1 y el 2 y dejaba afuera el 3."""
    ensanchada = _widen_citation_with_chunk_context(CITA_DEL_MODELO, [_chunk(ANEXO_EQUIPAMIENTO)])

    assert "Servidores de aplicaciones" not in ensanchada


def test_la_cita_ensanchada_es_literal_y_vuelve_a_verificar() -> None:
    """Todo el pipeline aguas abajo (grounding, `search_for` en el PDF) asume
    que la cita es una subcadena contigua del chunk."""
    ensanchada = " ".join(
        _widen_citation_with_chunk_context(CITA_DEL_MODELO, [_chunk(ANEXO_EQUIPAMIENTO)]).split()
    )

    assert ensanchada in " ".join(ANEXO_EQUIPAMIENTO.split())


def test_el_ensanchado_llega_al_minimo_legible() -> None:
    """La razón de ser de la función: 33 caracteres no se entienden solos."""
    ensanchada = _widen_citation_with_chunk_context(CITA_DEL_MODELO, [_chunk(ANEXO_EQUIPAMIENTO)])

    assert len(ensanchada) >= CITATION_PREFERRED_MIN_CHARS
    assert len(ensanchada) <= CITATION_MAX_CHARS


# ---------------------------------------------------------------------------
# Guardas: lo que el fix no puede romper
# ---------------------------------------------------------------------------


def test_una_cita_que_ya_es_legible_no_se_toca() -> None:
    larga = "El plazo de entrega será de noventa (90) días corridos desde la Orden de Compra"

    assert _widen_citation_with_chunk_context(larga, [_chunk(f"Artículo 12. {larga}.")]) == larga


def test_sin_chunk_donde_ubicarla_se_devuelve_la_cita_original() -> None:
    corta = "del 5% del presupuesto"

    assert _widen_citation_with_chunk_context(corta, [_chunk("Un texto que no la contiene.")]) == corta


def test_las_tablas_no_ensanchan() -> None:
    """Una cita de tabla tiene su propio camino de verificación."""
    corta = "Item 3: 4 (cuatro)"
    tabla = {"content": ANEXO_EQUIPAMIENTO, "block_type": "table"}

    assert _widen_citation_with_chunk_context(corta, [tabla]) == corta


# ---------------------------------------------------------------------------
# `_build_context_citation` directo: el invariante, no el caso
# ---------------------------------------------------------------------------


def test_el_nucleo_sobrevive_este_donde_este_en_el_parrafo() -> None:
    """El bug dependía de la posición del dato dentro del párrafo: al principio
    salía bien, al final se perdía. Se recorre todo el párrafo."""
    texto = " ".join(ANEXO_EQUIPAMIENTO.split())
    dato = "4 (cuatro)"

    posicion = texto.find(dato)
    while posicion >= 0:
        snippet = _build_context_citation(
            texto, posicion, posicion + len(dato), min_chars=CITATION_PREFERRED_MIN_CHARS
        )
        assert dato in snippet, f"el dato en el offset {posicion} se perdió: {snippet!r}"
        assert snippet in texto
        assert len(snippet) <= CITATION_MAX_CHARS
        posicion = texto.find(dato, posicion + 1)


def test_un_nucleo_mas_largo_que_el_techo_se_recorta_a_si_mismo() -> None:
    """No se lo puede contener entero. Lo que NO puede pasar es que se lo
    reemplace por texto vecino: la cita tiene que seguir siendo evidencia."""
    texto = "Contexto previo que no es la evidencia. " + "palabra " * 40 + "Contexto posterior."
    inicio = texto.index("palabra")
    fin = inicio + len("palabra " * 40)

    snippet = _build_context_citation(texto, inicio, fin)

    assert len(snippet) <= CITATION_MAX_CHARS
    assert "Contexto previo" not in snippet
    assert snippet in texto


def test_el_nucleo_al_borde_del_parrafo_no_rompe() -> None:
    texto = "Presupuesto oficial: AR$ 12.000.000."

    al_principio = _build_context_citation(texto, 0, 20, min_chars=CITATION_PREFERRED_MIN_CHARS)
    al_final = _build_context_citation(
        texto, len(texto) - 15, len(texto), min_chars=CITATION_PREFERRED_MIN_CHARS
    )

    assert al_principio in texto
    assert al_final in texto
    assert "12.000.000" in al_final
