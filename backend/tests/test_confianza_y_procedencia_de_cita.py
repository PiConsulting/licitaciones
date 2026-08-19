"""ATR-02 y SYN-05: qué se le muestra a la persona como evidencia y como confianza.

Los dos hallazgos son el mismo problema visto desde dos lados: el pipeline
reescribe la cita después de verificarla, y después se premia a sí mismo por el
resultado.

  - ATR-02: tres transformaciones distintas cambian la cita. La más delicada es
    el "rescate": cuando la cita QUE EL MODELO DECLARÓ como evidencia no
    verifica contra ningún chunk, el sistema busca si el `valor` del item
    aparece literalmente en la página y, si aparece, lo usa como cita -- y el
    item quedaba en `success`. Que ese otro texto exista en la página no prueba
    que respalde ESTE dato.

  - SYN-05: la confianza que se muestra era la autoevaluación del mismo modelo
    que produjo el dato, porque el prompt le pide el campo `confidence` y el
    código lo respetaba. La fórmula determinista casi nunca corría. Y las dos
    fórmulas premiaban la longitud de la cita, que el propio pipeline alarga.
"""

from __future__ import annotations

from typing import Any

from analysis.extraction.extractors.base import _verify_citation_grounding
from analysis.extraction.graph import _normalize_confidence, calculate_confidence

CITA_REAL = "La garantía de mantenimiento de oferta será del 5% del presupuesto"


def _chunk(content: str, page: int = 4) -> dict[str, Any]:
    return {
        "id": "an-1--doc-1--3",
        "document_id": "doc-1",
        "page_number": page,
        "content": content,
        "block_type": "paragraph",
    }


def _ref(citation: str, page: int = 4) -> dict[str, Any]:
    return {"document_id": "doc-1", "page_number": page, "citation": citation}


# ---------------------------------------------------------------------------
# ATR-02: procedencia de la cita
# ---------------------------------------------------------------------------


def test_una_cita_del_modelo_que_verifica_queda_marcada_como_del_modelo() -> None:
    item = {
        "valor": "5% del presupuesto",
        "extraction_status": "success",
        "source_references": [_ref(CITA_REAL)],
    }

    _verify_citation_grounding([item], [_chunk(f"{CITA_REAL}.")], category="garantias", correlation_id="c1")

    ref = item["source_references"][0]
    assert ref["citation_origin"] == "llm"
    assert ref["citation_llm"] == CITA_REAL


def test_una_cita_ensanchada_por_el_pipeline_se_marca_como_tal() -> None:
    """El ensanchado toma la cita verificada y le agrega contexto del chunk. El
    texto sigue siendo literal del pliego, pero no es lo que el modelo citó."""
    corta = "del 5% del presupuesto"  # 22 caracteres: por debajo del umbral de utilidad
    contenido = f"Artículo 10. {CITA_REAL} oficial, mediante póliza de caución."
    item = {
        "valor": "5%",
        "extraction_status": "success",
        "source_references": [_ref(corta)],
    }

    _verify_citation_grounding([item], [_chunk(contenido)], category="garantias", correlation_id="c1")

    ref = item["source_references"][0]
    assert ref["citation_llm"] == corta
    if ref["citation"] != corta:
        assert ref["citation_origin"] == "ensanchada"


def test_una_cita_rescatada_degrada_el_item_a_partial() -> None:
    """El caso del hallazgo: el modelo citó algo que no existe en ningún chunk.
    El rescate encuentra el `valor` del item en la página y lo usa como cita.

    Antes esto restauraba `success`: la verificación anti-alucinación fallaba y
    el sistema la reemplazaba por otra que sí pasa.
    """
    contenido = "El plazo de entrega será de noventa (90) días corridos desde la Orden."
    item = {
        "valor": "noventa (90) días corridos desde la Orden",
        "extraction_status": "success",
        "source_references": [_ref("una frase que el modelo inventó y no está en el pliego")],
    }

    _verify_citation_grounding([item], [_chunk(contenido)], category="plazos_clave", correlation_id="c1")

    assert item["extraction_status"] == "partial", "un rescate no es una verificación"
    assert item["_warning"] == "cita_reemplazada_por_rescate"
    ref = item["source_references"][0]
    assert ref["citation_origin"] == "rescatada"
    assert ref["citation_llm"] == "una frase que el modelo inventó y no está en el pliego"


def test_el_rescate_conserva_el_dato_en_vez_de_tirarlo() -> None:
    """Degradar no es descartar: el texto rescatado SÍ es literal del pliego, y
    perder el item entero sería peor que mostrarlo marcado."""
    contenido = "El plazo de entrega será de noventa (90) días corridos desde la Orden."
    item = {
        "valor": "noventa (90) días corridos desde la Orden",
        "extraction_status": "success",
        "source_references": [_ref("frase inventada que no aparece en ninguna parte")],
    }

    _verify_citation_grounding([item], [_chunk(contenido)], category="plazos_clave", correlation_id="c1")

    assert item["source_references"], "no se descarta el item"
    assert item["source_references"][0]["citation"] in contenido


# ---------------------------------------------------------------------------
# SYN-05: la confianza que ve la persona
# ---------------------------------------------------------------------------


def test_la_autoevaluacion_del_modelo_no_es_la_confianza_que_se_muestra() -> None:
    item = {
        "confidence": 0.98,  # el modelo se puntuó altísimo
        "extraction_status": "partial",
        "source_references": [{"citation": CITA_REAL}],
    }

    _normalize_confidence(item)

    assert item["confidence"] != 0.98
    assert item["confidence"] == calculate_confidence(item["source_references"], "partial")


def test_la_autoevaluacion_se_conserva_para_telemetria() -> None:
    item = {
        "confidence": 0.98,
        "extraction_status": "success",
        "source_references": [{"citation": CITA_REAL}],
    }

    _normalize_confidence(item)

    assert item["confidence_llm"] == 0.98


def test_un_item_sin_confidence_del_modelo_no_inventa_telemetria() -> None:
    item = {"extraction_status": "success", "source_references": [{"citation": CITA_REAL}]}

    _normalize_confidence(item)

    assert "confidence_llm" not in item
    assert item["confidence"] > 0


def test_el_largo_de_la_cita_ya_no_mueve_la_confianza() -> None:
    """Medía una decisión del propio pipeline: el código ensancha la cita y
    después se premiaba por tenerla larga."""
    corta = [{"citation": "del 5% del presupuesto oficial"}]
    larga = [{"citation": "x" * 200}]

    assert calculate_confidence(corta, "success") == calculate_confidence(larga, "success")


def test_lo_que_sigue_moviendo_la_confianza_es_la_evidencia() -> None:
    una = [{"citation": CITA_REAL}]
    dos = [{"citation": CITA_REAL}, {"citation": "otra cita distinta del pliego"}]

    assert calculate_confidence(dos, "success") > calculate_confidence(una, "success")
    assert calculate_confidence(una, "partial") < calculate_confidence(una, "success")
    assert calculate_confidence([], "not_found") == 0.0


def test_un_item_rescatado_termina_con_menos_confianza_que_uno_verificado() -> None:
    """La cadena completa: el rescate baja el status a `partial`, y `partial`
    baja la confianza. Antes el item llegaba al usuario como `success` con la
    autoevaluación alta del modelo."""
    contenido = "El plazo de entrega será de noventa (90) días corridos desde la Orden."
    rescatado = {
        "valor": "noventa (90) días corridos desde la Orden",
        "confidence": 0.95,
        "extraction_status": "success",
        "source_references": [_ref("frase inventada que no está en el pliego")],
    }
    verificado = {
        "valor": "noventa (90) días",
        "confidence": 0.95,
        "extraction_status": "success",
        "source_references": [_ref("El plazo de entrega será de noventa (90) días corridos")],
    }

    for item in (rescatado, verificado):
        _verify_citation_grounding([item], [_chunk(contenido)], category="plazos_clave", correlation_id="c1")
        _normalize_confidence(item)

    assert rescatado["confidence"] < verificado["confidence"]
