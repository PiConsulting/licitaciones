"""CHK-05: `identificacion_procedimiento` era el tacho de basura de la clasificación.

`classify_chunk_categories` terminaba con un fallback que asignaba
`identificacion_procedimiento` a todo chunk que no matcheara ni por heading ni
por densidad de keywords, con el argumento de que era "la categoría menos
específica". En un pliego real eso es la mayoría del texto de relleno:
considerandos, remisiones normativas, formalidades.

No era una etiqueta inocua: `_retrieve_with_category_priority` bonifica un +20%
a los chunks cuya `primary_category` coincide con la categoría objetivo, así que
al extraer la carátula TODO el ruido del documento competía boosteado contra la
carátula real.

El fix es `None`. Estos tests cubren las dos mitades: que el clasificador deje
de etiquetar, y que el retrieval haga lo correcto con un chunk sin categoría.
"""

from __future__ import annotations

from typing import Any

import pytest

from extraction.chunking import classify_chunk_categories


def _chunk(content: str, heading_path: list[str] | None = None, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "chunk_id": "chunk-1",
        "heading_path": heading_path or [],
        "content": content,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. El clasificador ya no inventa una categoría
# ---------------------------------------------------------------------------


def test_un_considerando_no_queda_etiquetado_como_identificacion() -> None:
    """Texto jurídico de relleno: ni heading de categoría, ni densidad de
    keywords. Antes salía como `identificacion_procedimiento`."""
    resultado = classify_chunk_categories(
        _chunk(
            "Que por las actuaciones citadas en el Visto tramita la presente "
            "gestión, conforme lo establecido en el marco normativo vigente y "
            "sus modificatorias."
        )
    )

    assert resultado["primary_category"] is None
    assert resultado["primary_category"] != "identificacion_procedimiento"


def test_texto_sin_senal_alguna_queda_sin_categoria() -> None:
    resultado = classify_chunk_categories(_chunk("Fojas útiles: diez. Continúa en la página siguiente."))

    assert resultado["primary_category"] is None


def test_la_caratula_real_sigue_clasificando_como_identificacion() -> None:
    """Guarda del otro lado: sacar el fallback no puede romper el caso en que
    la categoría SÍ corresponde."""
    resultado = classify_chunk_categories(
        _chunk(
            "Licitación Privada N° 3/2025. Expediente EX-2025-00012345. "
            "Organismo contratante: Ministerio.",
            heading_path=["Identificación del procedimiento"],
        )
    )

    assert resultado["primary_category"] == "identificacion_procedimiento"


def test_una_categoria_que_matchea_por_keywords_no_se_ve_afectada() -> None:
    resultado = classify_chunk_categories(
        _chunk(
            "La garantía de mantenimiento de oferta será equivalente al uno por "
            "ciento (1%) del monto total ofertado, constituida mediante póliza "
            "de caución."
        )
    )

    assert resultado["primary_category"] == "garantias"


def test_el_contrato_de_retorno_admite_none() -> None:
    """El docstring de la función ya declaraba `str | None`; el cuerpo lo
    contradecía."""
    resultado = classify_chunk_categories(_chunk("Texto neutro sin señal."))

    assert set(resultado) == {"primary_category", "secondary_categories", "category_scores"}
    assert resultado["primary_category"] is None
    assert resultado["secondary_categories"] == []


# ---------------------------------------------------------------------------
# 2. El impacto real: el boost de retrieval
# ---------------------------------------------------------------------------


def _candidato(chunk_index: int, primary: str | None, score: float) -> dict[str, Any]:
    return {
        "document_id": "doc-1",
        "page_number": 1,
        "chunk_index": chunk_index,
        "content": f"contenido {chunk_index}",
        "primary_category": primary,
        "secondary_categories": [],
        "search_score": score,
    }


def test_el_ruido_sin_categoria_no_le_gana_a_la_caratula_real(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reproduce el escenario de falla del hallazgo.

    Con el fallback viejo, el considerando también era
    `identificacion_procedimiento`: cobraba el mismo +20% que la carátula y,
    teniendo mejor score base, quedaba primero. Sin categoría no cobra boost y
    la carátula gana pese a su score más bajo.
    """
    from analysis.extraction.extractors import base

    candidatos = [
        _candidato(0, None, 1.00),  # considerando: mejor score base, sin categoría
        _candidato(1, "identificacion_procedimiento", 0.90),  # la carátula real
    ]

    monkeypatch.setattr(
        base,
        "search_hybrid",
        lambda *, query, analysis_id, top_k, keyword_query: list(candidatos),
    )

    resultado = base._retrieve_with_category_priority(
        query="identificación del procedimiento",
        analysis_id="analysis-1",
        top_k=2,
        keyword_query="expediente licitacion",
        category="identificacion_procedimiento",
        correlation_id="corr-1",
    )

    # 0.90 * 1.20 = 1.08 > 1.00
    assert [chunk["chunk_index"] for chunk in resultado] == [1, 0]


def test_un_chunk_sin_categoria_sigue_siendo_recuperable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin categoría no significa excluido: no hay filtro, sólo ausencia de
    boost. Un chunk sin clasificar con buen score entra igual al contexto."""
    from analysis.extraction.extractors import base

    candidatos = [_candidato(0, None, 5.0), _candidato(1, "garantias", 0.1)]

    monkeypatch.setattr(
        base,
        "search_hybrid",
        lambda *, query, analysis_id, top_k, keyword_query: list(candidatos),
    )

    resultado = base._retrieve_with_category_priority(
        query="garantías exigidas",
        analysis_id="analysis-1",
        top_k=2,
        keyword_query="garantia caucion",
        category="garantias",
        correlation_id="corr-1",
    )

    assert [chunk["chunk_index"] for chunk in resultado] == [0, 1]


def test_la_telemetria_reporta_sin_categoria_y_no_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """`chunk.get("primary_category", "unknown")` no alcanzaba: la clave existe
    con valor None, así que el default nunca se aplicaba y el log salía con una
    clave None en el diccionario de distribución."""
    from analysis.extraction.extractors import base

    capturado: dict[str, Any] = {}

    class _Logger:
        def info(self, event, **kwargs):
            if event == "retrieval_hybrid_scoring":
                capturado.update(kwargs)

        def warning(self, event, **kwargs):
            pass

        def error(self, event, **kwargs):
            pass

        def debug(self, event, **kwargs):
            pass

    monkeypatch.setattr(base, "logger", _Logger())
    monkeypatch.setattr(
        base,
        "search_hybrid",
        lambda *, query, analysis_id, top_k, keyword_query: [_candidato(0, None, 1.0)],
    )

    base._retrieve_with_category_priority(
        query="identificación del procedimiento",
        analysis_id="analysis-1",
        top_k=1,
        keyword_query="expediente",
        category="identificacion_procedimiento",
        correlation_id="corr-1",
    )

    distribucion = capturado.get("category_distribution", {})
    assert None not in distribucion
    assert distribucion.get("sin_categoria") == 1
