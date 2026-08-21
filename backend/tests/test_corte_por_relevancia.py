"""CTX-02: los 25-35 chunks recuperados entraban completos al prompt.

Se recuperaba `category_top_k` y sólo se recortaba por presupuesto de tokens. No
había ningún corte por relevancia, así que el chunk de la posición 35 —con un
score de RRF típicamente la mitad del primero— entraba con el mismo peso visual
que el primero.

Dónde duele: una categoría que en ESE pliego no tiene evidencia real (por
ejemplo `criterios_evaluacion` en un pliego que adjudica por menor precio, sin
matriz de puntajes) igual llenaba sus 25-35 chunks con secciones tangenciales
boosteadas. Al modelo se le pide ser "un analista experto que reconoce el
concepto aunque el vocabulario cambie", y después se le da mucho material del
cual construir un criterio que el pliego no tiene.

El error caro es el inverso: descartar el chunk que sí tenía el dato reproduce
exactamente la falla que esta auditoría viene persiguiendo. Por eso más de la
mitad de estos tests son guardas sobre el piso.
"""

from __future__ import annotations

from typing import Any

from analysis.extraction.extractors.base import (
    _RELEVANCE_MIN_CHUNKS,
    _RELEVANCE_MIN_RATIO,
    _drop_low_relevance_chunks,
)


def _chunk(indice: int, score: float | None) -> dict[str, Any]:
    chunk: dict[str, Any] = {
        "id": f"chunk-{indice}",
        "content": f"Contenido del chunk {indice}.",
        "document_id": "doc-1",
        "page_number": indice,
    }
    if score is not None:
        chunk["search_score"] = score
    return chunk


def _cola_larga(cantidad: int = 30) -> list[dict[str, Any]]:
    """Un top con evidencia real y una cola que el retrieval trajo por
    completar el `top_k`: los scores caen a menos de la mitad."""
    fuertes = [_chunk(i, 0.032 - i * 0.0005) for i in range(_RELEVANCE_MIN_CHUNKS)]
    debiles = [_chunk(_RELEVANCE_MIN_CHUNKS + i, 0.005) for i in range(cantidad - _RELEVANCE_MIN_CHUNKS)]
    return fuertes + debiles


# ---------------------------------------------------------------------------
# El caso del hallazgo
# ---------------------------------------------------------------------------


def test_la_cola_irrelevante_no_llega_al_prompt() -> None:
    resultado = _drop_low_relevance_chunks(_cola_larga(), category="criterios_evaluacion")

    assert len(resultado) == _RELEVANCE_MIN_CHUNKS


def test_los_chunks_relevantes_se_conservan_todos() -> None:
    """Una categoría con evidencia real y pareja no pierde nada."""
    chunks = [_chunk(i, 0.032 - i * 0.0002) for i in range(30)]

    assert _drop_low_relevance_chunks(chunks, category="garantias") == chunks


def test_el_orden_de_relevancia_se_conserva() -> None:
    """Lo más relevante primero es lo que favorece la atención del modelo."""
    resultado = _drop_low_relevance_chunks(_cola_larga(), category="plazos_clave")

    assert [c["id"] for c in resultado] == [f"chunk-{i}" for i in range(_RELEVANCE_MIN_CHUNKS)]


# ---------------------------------------------------------------------------
# Guardas: el piso
# ---------------------------------------------------------------------------


def test_nunca_se_baja_del_piso_de_chunks() -> None:
    """Aunque TODA la cola esté por debajo del umbral, los primeros entran."""
    chunks = [_chunk(0, 1.0)] + [_chunk(i, 0.001) for i in range(1, 30)]

    resultado = _drop_low_relevance_chunks(chunks, category="garantias")

    assert len(resultado) == _RELEVANCE_MIN_CHUNKS


def test_una_lista_corta_no_se_toca() -> None:
    chunks = [_chunk(0, 1.0)] + [_chunk(i, 0.001) for i in range(1, _RELEVANCE_MIN_CHUNKS)]

    assert _drop_low_relevance_chunks(chunks, category="garantias") == chunks


def test_sin_scores_no_se_descarta_nada() -> None:
    """Mocks y fuentes legacy no traen `search_score`. No tenerlo no puede
    costar chunks: sin score no hay criterio."""
    chunks = [_chunk(i, None) for i in range(30)]

    assert _drop_low_relevance_chunks(chunks, category="garantias") == chunks


def test_un_chunk_sin_score_entre_otros_con_score_se_conserva() -> None:
    """El parent expandido desde un child hereda el score, pero si por alguna
    razón faltara, no se lo puede juzgar."""
    chunks = _cola_larga()
    chunks[15].pop("search_score")

    resultado = _drop_low_relevance_chunks(chunks, category="garantias")

    assert any(c["id"] == "chunk-15" for c in resultado)


def test_un_score_invalido_se_trata_como_ausente() -> None:
    chunks = _cola_larga()
    chunks[15]["search_score"] = None
    chunks[16]["search_score"] = "no es un numero"

    resultado = _drop_low_relevance_chunks(chunks, category="garantias")

    assert {c["id"] for c in resultado} >= {"chunk-15", "chunk-16"}


def test_el_umbral_es_relativo_al_mejor_score_de_esa_consulta() -> None:
    """Los scores de RRF no son comparables entre consultas: un umbral
    absoluto descartaría todo en una y nada en otra."""
    escala_chica = [_chunk(i, 0.03) for i in range(_RELEVANCE_MIN_CHUNKS)]
    escala_chica += [_chunk(_RELEVANCE_MIN_CHUNKS + i, 0.029) for i in range(10)]

    escala_grande = [_chunk(i, 30.0) for i in range(_RELEVANCE_MIN_CHUNKS)]
    escala_grande += [_chunk(_RELEVANCE_MIN_CHUNKS + i, 29.0) for i in range(10)]

    assert len(_drop_low_relevance_chunks(escala_chica, category="c")) == len(escala_chica)
    assert len(_drop_low_relevance_chunks(escala_grande, category="c")) == len(escala_grande)


def test_el_umbral_es_el_declarado() -> None:
    """Fija la relación entre la constante y el comportamiento, para que
    cambiarla no requiera releer la implementación."""
    mejor = 1.0
    justo_encima = mejor * _RELEVANCE_MIN_RATIO + 0.001
    justo_debajo = mejor * _RELEVANCE_MIN_RATIO - 0.001

    chunks = [_chunk(i, mejor) for i in range(_RELEVANCE_MIN_CHUNKS)]
    chunks.append(_chunk(90, justo_encima))
    chunks.append(_chunk(91, justo_debajo))

    ids = {c["id"] for c in _drop_low_relevance_chunks(chunks, category="c")}

    assert "chunk-90" in ids
    assert "chunk-91" not in ids


def test_lo_descartado_queda_registrado(caplog: Any) -> None:
    """CHK-10: nada se descarta en silencio, y menos evidencia."""
    import logging

    with caplog.at_level(logging.INFO):
        _drop_low_relevance_chunks(_cola_larga(), category="garantias")

    assert "extraction_chunks_dropped_low_relevance" in caplog.text
