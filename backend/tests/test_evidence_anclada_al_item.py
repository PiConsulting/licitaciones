"""SYN-01 + SYN-04: la evidencia del LLM de síntesis ahora se ancla al item.

El LLM de síntesis nunca ve los chunks del pliego: el único texto del pliego que
tiene es el campo `citation` dentro de los `source_references` de cada item. Y
sin embargo el prompt le pedía transcribirlo palabra por palabra a
`evidence.text`, y ese texto se usaba como la `citation` que ve el usuario --
validado únicamente contra "aparece en algún chunk de esa página".

Dos consecuencias, que son los dos hallazgos:

  - SYN-01: una tarea de copia exacta de cadenas delegada a un LLM generativo,
    de la que dependía que la categoría entera se mostrara o no.
  - SYN-04: nada obligaba a que `evidence.text` fuera una cita del item que la
    evidencia decía respaldar. Una frase copiada de OTRO item de la misma página
    resolvía sin error, y el usuario veía un bullet cuya fuente mostraba otro
    texto -- exactamente la falla que el docstring de `_resolve_narrative_sources`
    afirmaba que era estructuralmente imposible.
"""

from __future__ import annotations

from typing import Any

from analysis.extraction import synthesis
from analysis.extraction.schemas import RawCategoryNarrative

DOC = "11111111-1111-1111-1111-111111111111"
OTRO_DOC = "22222222-2222-2222-2222-222222222222"

CITA_OFERTA = (
    "La garantía de mantenimiento de oferta será equivalente al uno por ciento (1%) "
    "del presupuesto oficial."
)
CITA_CUMPLIMIENTO = (
    "La garantía de cumplimiento de contrato será del diez por ciento (10%) del monto "
    "adjudicado y deberá constituirse dentro de los cinco días."
)


def _item(citation: str, *, chunk_id: str, page: int = 4) -> dict[str, Any]:
    return {
        "tipo": "garantia",
        "valor": "garantía",
        "confidence": 0.9,
        "extraction_status": "success",
        "source_references": [
            {
                "document_id": DOC,
                "page_number": page,
                "citation": citation,
                "chunk_id": chunk_id,
            }
        ],
    }


def _raw(evidence: list[dict[str, Any]], item_refs: list[int]) -> RawCategoryNarrative:
    return RawCategoryNarrative.model_validate(
        {
            "blocks": [
                {
                    "type": "bullet_list",
                    "items": [
                        {
                            "text": "La garantía de cumplimiento es del 10%.",
                            "confidence_level": "alta",
                            "item_refs": item_refs,
                        }
                    ],
                }
            ],
            "evidence": evidence,
        }
    )


def _sources(narrative) -> list[Any]:
    return list(narrative.sources)


# ---------------------------------------------------------------------------
# SYN-04: la fuente no puede venir de otro item
# ---------------------------------------------------------------------------


def test_una_evidencia_copiada_de_otro_item_no_puede_ser_la_fuente() -> None:
    """El escenario del hallazgo: el bullet habla del item 1 (cumplimiento de
    contrato) pero la evidencia trae texto de la cita del item 0 (mantenimiento
    de oferta), que está en la MISMA página. Antes resolvía sin error y el
    usuario veía la cita equivocada."""
    items = [
        _item(CITA_OFERTA, chunk_id="chunk-a"),
        _item(CITA_CUMPLIMIENTO, chunk_id="chunk-b"),
    ]
    raw = _raw(
        evidence=[
            {
                "document_id": DOC,
                "page_number": 4,
                "text": "equivalente al uno por ciento (1%) del presupuesto oficial",
                "claim": "monto de la garantía",
                "item_refs": [1],  # dice respaldar el item de CUMPLIMIENTO
            }
        ],
        item_refs=[1],
    )

    narrative = synthesis._resolve_from_evidence(raw, None, items, correlation_id="corr-1")

    assert len(_sources(narrative)) == 1
    citation = _sources(narrative)[0].citation
    assert "uno por ciento" not in citation, "no puede citar el texto del otro item"
    assert citation == CITA_CUMPLIMIENTO
    assert _sources(narrative)[0].chunk_id == "chunk-b"


def test_el_document_id_sale_del_item_no_del_llm() -> None:
    """La segunda vía por la que una evidencia terminaba en otro lado: el modelo
    copiaba mal el UUID del documento."""
    items = [_item(CITA_CUMPLIMIENTO, chunk_id="chunk-b")]
    raw = _raw(
        evidence=[
            {
                "document_id": OTRO_DOC,  # el LLM se equivocó de documento
                "page_number": 99,  # y de página
                "text": "del diez por ciento (10%) del monto adjudicado",
                "claim": "monto",
                "item_refs": [0],
            }
        ],
        item_refs=[0],
    )

    narrative = synthesis._resolve_from_evidence(raw, None, items, correlation_id="corr-1")

    source = _sources(narrative)[0]
    assert source.document_id == DOC
    assert source.page_number == 4


def test_una_evidencia_sin_item_valido_no_produce_fuente() -> None:
    items = [_item(CITA_CUMPLIMIENTO, chunk_id="chunk-b")]
    raw = _raw(
        evidence=[
            {
                "document_id": DOC,
                "page_number": 4,
                "text": "del diez por ciento (10%) del monto adjudicado",
                "claim": "monto",
                "item_refs": [7],  # índice fuera de rango
            }
        ],
        item_refs=[7],
    )

    narrative = synthesis._resolve_from_evidence(raw, None, items, correlation_id="corr-1")

    assert _sources(narrative) == []
    assert narrative.blocks == []


# ---------------------------------------------------------------------------
# SYN-01: la transcripción deja de decidir qué se muestra
# ---------------------------------------------------------------------------


def test_una_transcripcion_inexacta_degrada_la_precision_pero_no_pierde_el_dato() -> None:
    """Antes, una paráfrasis mínima hacía que la evidencia no resolviera. Ahora
    se cae a la cita verificada completa del item."""
    items = [_item(CITA_CUMPLIMIENTO, chunk_id="chunk-b")]
    raw = _raw(
        evidence=[
            {
                "document_id": DOC,
                "page_number": 4,
                # paráfrasis: "10 por ciento" en vez de "diez por ciento"
                "text": "La garantía de cumplimiento de contrato será del 10 por ciento del monto adjudicado",
                "claim": "monto",
                "item_refs": [0],
            }
        ],
        item_refs=[0],
    )

    narrative = synthesis._resolve_from_evidence(raw, None, items, correlation_id="corr-1")

    assert len(_sources(narrative)) == 1
    assert _sources(narrative)[0].citation == CITA_CUMPLIMIENTO
    assert len(narrative.blocks) == 1


def test_un_fragmento_literal_conserva_la_precision_de_resaltado() -> None:
    """El motivo por el que el campo `evidence` existe: resaltar la frase, no el
    párrafo entero. Eso se conserva cuando el texto SÍ es literal."""
    items = [_item(CITA_CUMPLIMIENTO, chunk_id="chunk-b")]
    fragmento = "del diez por ciento (10%) del monto adjudicado"
    raw = _raw(
        evidence=[
            {
                "document_id": DOC,
                "page_number": 4,
                "text": fragmento,
                "claim": "monto",
                "item_refs": [0],
            }
        ],
        item_refs=[0],
    )

    narrative = synthesis._resolve_from_evidence(raw, None, items, correlation_id="corr-1")

    assert _sources(narrative)[0].citation == fragmento
    assert len(fragmento) < len(CITA_CUMPLIMIENTO)


def test_el_camino_evidence_ya_no_necesita_los_chunks() -> None:
    """`chunks_by_id` era necesario porque la validación era "el texto del LLM
    aparece en algún chunk de esta página". Ahora el ancla es el item, y los
    chunks sólo completan el `chunk_id` de análisis viejos que no lo traigan."""
    item_sin_chunk_id = {
        "tipo": "garantia",
        "valor": "garantía",
        "confidence": 0.9,
        "extraction_status": "success",
        "source_references": [
            {"document_id": DOC, "page_number": 4, "citation": CITA_CUMPLIMIENTO}
        ],
    }
    raw = _raw(
        evidence=[
            {
                "document_id": DOC,
                "page_number": 4,
                "text": "del diez por ciento (10%) del monto adjudicado",
                "claim": "monto",
                "item_refs": [0],
            }
        ],
        item_refs=[0],
    )

    sin_chunks = synthesis._resolve_from_evidence(
        raw, None, [item_sin_chunk_id], correlation_id="corr-1"
    )
    assert len(_sources(sin_chunks)) == 1
    assert _sources(sin_chunks)[0].chunk_id is None

    con_chunks = synthesis._resolve_from_evidence(
        raw,
        {"chunk-b": {"chunk_id": "chunk-b", "document_id": DOC, "page_number": 4, "content": CITA_CUMPLIMIENTO}},
        [item_sin_chunk_id],
        correlation_id="corr-1",
    )
    assert _sources(con_chunks)[0].chunk_id == "chunk-b"


# ---------------------------------------------------------------------------
# Consistencia interna
# ---------------------------------------------------------------------------


def test_los_source_ids_del_bloque_coinciden_con_las_fuentes_construidas() -> None:
    """El segundo recorrido (`get_source_ids_for_item_refs`) rehacía toda la
    resolución por su cuenta y podía discrepar en silencio con las sources ya
    construidas. Ahora reusa el mapeo de la primera pasada."""
    items = [
        _item(CITA_OFERTA, chunk_id="chunk-a"),
        _item(CITA_CUMPLIMIENTO, chunk_id="chunk-b"),
    ]
    raw = RawCategoryNarrative.model_validate(
        {
            "blocks": [
                {
                    "type": "bullet_list",
                    "items": [
                        {"text": "Mantenimiento de oferta: 1%.", "confidence_level": "alta", "item_refs": [0]},
                        {"text": "Cumplimiento de contrato: 10%.", "confidence_level": "alta", "item_refs": [1]},
                    ],
                }
            ],
            "evidence": [
                {
                    "document_id": DOC,
                    "page_number": 4,
                    "text": "equivalente al uno por ciento (1%) del presupuesto oficial",
                    "claim": "oferta",
                    "item_refs": [0],
                },
                {
                    "document_id": DOC,
                    "page_number": 4,
                    "text": "del diez por ciento (10%) del monto adjudicado",
                    "claim": "cumplimiento",
                    "item_refs": [1],
                },
            ],
        }
    )

    narrative = synthesis._resolve_from_evidence(raw, None, items, correlation_id="corr-1")

    sources_by_id = {source.id: source for source in narrative.sources}
    bullets = narrative.blocks[0].items
    assert "uno por ciento" in sources_by_id[bullets[0].source_ids[0]].citation
    assert "diez por ciento" in sources_by_id[bullets[1].source_ids[0]].citation
