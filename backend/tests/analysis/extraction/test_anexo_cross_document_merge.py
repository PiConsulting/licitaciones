# Regresión (2026-09-14, Fase 2 de la auditoría RAG): un anexo numerado
# ("Anexo II") tiene una sola identidad real en todo el pliego, sin importar
# en qué documento subido aparece -- puede estar mencionado en el índice del
# pliego principal (documento A) y, por separado, ser su propio archivo
# subido con el contenido real (documento B). Antes `_item_section_key`
# incluía SIEMPRE `document_id` en la clave de fusión, así que esas dos
# apariciones del mismo anexo nunca se fusionaban -- medido en un pliego
# real multi-documento (santa_fe, 6 anexos numerados): cada uno salía
# duplicado dos veces.
from __future__ import annotations

from analysis.extraction.engine.item_merging import _merge_items_by_document_section


def _chunk(chunk_id: str, document_id: str, section_path: str) -> dict:
    return {
        "id": chunk_id,
        "document_id": document_id,
        "section_path": section_path,
    }


def _item(valor: str, chunk_id: str, document_id: str, *, citation: str) -> dict:
    return {
        "tipo": "anexo",
        "valor": valor,
        "confidence": 0.8,
        "extraction_status": "success",
        "source_references": [
            {"document_id": document_id, "chunk_id": chunk_id, "citation": citation}
        ],
    }


def test_mismo_anexo_numerado_en_dos_documentos_distintos_se_fusiona() -> None:
    """El caso real: el pliego principal (doc A) menciona 'Anexo II' en su
    índice; el propio archivo del Anexo II (doc B) también genera un ítem.
    Mismo identificador ('ii') -> un solo ítem final, con las citas de
    ambos documentos."""
    chunks = [
        _chunk("c1", "doc-A", "9. ANEXOS"),
        _chunk("c2", "doc-B", "ANEXO II"),
    ]
    items = [
        _item(
            "Anexo II — Nota Declaración Jurada",
            "c1",
            "doc-A",
            citation="Forman parte del presente el Anexo II — Nota Declaración Jurada",
        ),
        _item(
            "ANEXO II - DECLARACIÓN JURADA",
            "c2",
            "doc-B",
            citation="ANEXO II - DECLARACIÓN JURADA DE ACEPTACIÓN DEL PUBCG",
        ),
    ]

    result = _merge_items_by_document_section(
        items, chunks, category="anexos_obligatorios", correlation_id="corr-1"
    )

    assert len(result) == 1
    refs = result[0]["source_references"]
    assert {r["document_id"] for r in refs} == {"doc-A", "doc-B"}


def test_anexos_distintos_en_el_mismo_documento_no_se_fusionan() -> None:
    """Comportamiento previo intacto: 'Anexo I' y 'Anexo II' listados juntos
    en la misma sección del mismo documento siguen siendo DOS ítems."""
    chunks = [_chunk("c1", "doc-A", "9. ANEXOS")]
    items = [
        _item(
            "Anexo I — Planilla de Cotización", "c1", "doc-A", citation="Anexo I — Planilla de Cotización"
        ),
        _item(
            "Anexo II — Declaración Jurada", "c1", "doc-A", citation="Anexo II — Declaración Jurada"
        ),
    ]

    result = _merge_items_by_document_section(
        items, chunks, category="anexos_obligatorios", correlation_id="corr-2"
    )

    assert len(result) == 2


def test_fantasmas_sin_identificador_en_documentos_distintos_no_se_fusionan() -> None:
    """Sin identificador reconocible (el caso 'fantasma' que la función ya
    cubría), sigue sin fusionar entre documentos distintos -- no hay forma
    confiable de saber si son la misma unidad."""
    items = [
        {
            "tipo": "anexo",
            "valor": "Documentación técnica general",
            "confidence": 0.5,
            "extraction_status": "partial",
            "source_references": [],
            "_source_document_id": "doc-A",
        },
        {
            "tipo": "anexo",
            "valor": "Documentación técnica adicional",
            "confidence": 0.5,
            "extraction_status": "partial",
            "source_references": [],
            "_source_document_id": "doc-B",
        },
    ]
    chunks = [_chunk("c1", "doc-A", "GENERALIDADES"), _chunk("c2", "doc-B", "GENERALIDADES")]

    result = _merge_items_by_document_section(
        items, chunks, category="anexos_obligatorios", correlation_id="corr-3"
    )

    assert len(result) == 2
