"""Tests para deduplicacion de citations y resolucion deterministica de
fuentes en sintesis."""
from __future__ import annotations

from analysis.extraction.schemas import RawCategoryNarrative
from analysis.extraction.synthesis import (
    _dedupe_narrative_sources,
    _normalize_text_for_comparison,
    _resolve_narrative_sources,
)


def test_normalize_text_for_comparison() -> None:
    assert _normalize_text_for_comparison("Hola Mundo") == "hola mundo"
    assert _normalize_text_for_comparison("  múltiples   espacios  ") == "multiples espacios"
    assert _normalize_text_for_comparison("Ñoño") == "nono"
    assert _normalize_text_for_comparison("") == ""


def test_dedupe_narrative_sources_duplicados_exactos() -> None:
    sources = [
        {"id": 0, "document_id": "doc-1", "page_number": 1, "citation": "Primera cita literal"},
        {"id": 1, "document_id": "doc-1", "page_number": 1, "citation": "Primera cita literal"},
        {"id": 2, "document_id": "doc-1", "page_number": 2, "citation": "Segunda cita"},
    ]

    deduped, id_mapping = _dedupe_narrative_sources(sources)

    assert len(deduped) == 2
    assert deduped[0]["citation"] == "Primera cita literal"
    assert deduped[1]["citation"] == "Segunda cita"

    # Mapping debe redirigir el ID 1 al 0
    assert id_mapping[0] == 0
    assert id_mapping[1] == 0
    assert id_mapping[2] == 1


def test_dedupe_narrative_sources_con_variaciones_de_espacios() -> None:
    sources = [
        {"id": 0, "document_id": "doc-1", "page_number": 1, "citation": "cita   con espacios"},
        {"id": 1, "document_id": "doc-1", "page_number": 1, "citation": "cita con espacios"},
        {"id": 2, "document_id": "doc-1", "page_number": 1, "citation": "cita  con   espacios"},
    ]

    deduped, id_mapping = _dedupe_narrative_sources(sources)

    assert len(deduped) == 1
    assert id_mapping[0] == 0
    assert id_mapping[1] == 0
    assert id_mapping[2] == 0


def test_dedupe_narrative_sources_diferentes_documentos() -> None:
    sources = [
        {"id": 0, "document_id": "doc-1", "page_number": 1, "citation": "misma cita"},
        {"id": 1, "document_id": "doc-2", "page_number": 1, "citation": "misma cita"},
    ]

    deduped, id_mapping = _dedupe_narrative_sources(sources)

    # Mismo texto pero diferentes documentos = fuentes distintas
    assert len(deduped) == 2
    assert id_mapping[0] == 0
    assert id_mapping[1] == 1


def test_dedupe_narrative_sources_diferentes_paginas() -> None:
    sources = [
        {"id": 0, "document_id": "doc-1", "page_number": 1, "citation": "misma cita"},
        {"id": 1, "document_id": "doc-1", "page_number": 2, "citation": "misma cita"},
    ]

    deduped, id_mapping = _dedupe_narrative_sources(sources)

    # Mismo texto pero diferentes páginas = fuentes distintas
    assert len(deduped) == 2
    assert id_mapping[0] == 0
    assert id_mapping[1] == 1


# ---------------------------------------------------------------------------
# _resolve_narrative_sources: traduccion deterministica item_refs -> sources
# ---------------------------------------------------------------------------


def _items(*citations: str) -> list[dict]:
    return [
        {
            "source_references": [
                {"document_id": "doc-1", "page_number": i + 1, "citation": citation}
            ]
        }
        for i, citation in enumerate(citations)
    ]


def test_resolve_item_refs_validos_producen_source_ids_y_sources_correctos() -> None:
    items = _items(
        "Anexo I - Formulario de oferta económica presentado con la oferta.",
        "Constancia de inscripción en el Registro de Proveedores del Municipio.",
    )
    raw = RawCategoryNarrative.model_validate(
        {
            "blocks": [
                {
                    "type": "bullet_list",
                    "items": [
                        {"text": "Presentar Anexo I.", "confidence_level": "alta", "item_refs": [0]},
                        {"text": "Presentar constancia RUP.", "confidence_level": "alta", "item_refs": [1]},
                    ],
                }
            ]
        }
    )

    narrative = _resolve_narrative_sources(raw, items, correlation_id="corr")

    assert len(narrative.sources) == 2
    bullets = narrative.blocks[0].items
    assert bullets[0].source_ids == [0]
    assert bullets[1].source_ids == [1]
    assert narrative.sources[0].citation == items[0]["source_references"][0]["citation"]
    assert narrative.sources[1].citation == items[1]["source_references"][0]["citation"]


def test_resolve_indice_fuera_de_rango_no_tumba_los_indices_validos_del_mismo_bloque() -> None:
    items = _items("Cita valida y suficientemente larga para pasar el minimo.")
    raw = RawCategoryNarrative.model_validate(
        {
            "blocks": [
                {
                    "type": "paragraph",
                    "text": "Texto.",
                    "confidence_level": "alta",
                    "item_refs": [0, 99],
                }
            ]
        }
    )

    narrative = _resolve_narrative_sources(raw, items, correlation_id="corr")

    assert len(narrative.blocks) == 1
    assert narrative.blocks[0].source_ids == [0]
    assert len(narrative.sources) == 1


def test_resolve_item_refs_vacio_descarta_el_bullet_y_el_bloque_si_era_el_unico() -> None:
    items = _items("Cita valida y suficientemente larga para pasar el minimo.")
    raw = RawCategoryNarrative.model_validate(
        {
            "blocks": [
                {
                    "type": "bullet_list",
                    "items": [
                        {"text": "Sin evidencia.", "confidence_level": "alta", "item_refs": []},
                    ],
                }
            ]
        }
    )

    narrative = _resolve_narrative_sources(raw, items, correlation_id="corr")

    assert narrative.blocks == []
    assert narrative.sources == []


def test_resolve_no_puede_mezclar_evidencia_de_otro_item() -> None:
    """El bug reportado: un bloque sobre el item 1 nunca puede terminar con la
    cita del item 0, aunque ambos esten en la misma categoria/lista."""
    items = _items(
        "Anexo I - Formulario de oferta económica presentado con la oferta.",
        "Anexo II - Declaración jurada de aptitud para contratar según pliego.",
    )
    raw = RawCategoryNarrative.model_validate(
        {
            "blocks": [
                {
                    "type": "bullet_list",
                    "items": [
                        {"text": "Presentar Anexo I.", "confidence_level": "alta", "item_refs": [0]},
                        {"text": "Presentar Anexo II.", "confidence_level": "alta", "item_refs": [1]},
                    ],
                }
            ]
        }
    )

    narrative = _resolve_narrative_sources(raw, items, correlation_id="corr")

    bullets = narrative.blocks[0].items
    anexo_i_source = next(s for s in narrative.sources if s.id == bullets[0].source_ids[0])
    anexo_ii_source = next(s for s in narrative.sources if s.id == bullets[1].source_ids[0])

    assert "Anexo I" in anexo_i_source.citation
    assert "Anexo II" in anexo_ii_source.citation
    assert anexo_i_source.citation != anexo_ii_source.citation


def test_resolve_misma_cita_en_dos_items_dedupea_y_queda_referenciada_por_ambos() -> None:
    items = _items(
        "Cita compartida idéntica en ambos ítems del pliego.",
        "Cita compartida idéntica en ambos ítems del pliego.",
    )
    # Forzar mismo document_id/page_number para que el dedup los reconozca como
    # la misma fuente (por defecto _items les da paginas distintas).
    items[1]["source_references"][0]["page_number"] = 1

    raw = RawCategoryNarrative.model_validate(
        {
            "blocks": [
                {
                    "type": "bullet_list",
                    "items": [
                        {"text": "Elemento A.", "confidence_level": "alta", "item_refs": [0]},
                        {"text": "Elemento B.", "confidence_level": "alta", "item_refs": [1]},
                    ],
                }
            ]
        }
    )

    narrative = _resolve_narrative_sources(raw, items, correlation_id="corr")

    assert len(narrative.sources) == 1
    bullets = narrative.blocks[0].items
    assert bullets[0].source_ids == bullets[1].source_ids == [narrative.sources[0].id]


def test_resolve_ningun_source_queda_huerfano() -> None:
    items = _items(
        "Primera cita valida y suficientemente larga para el minimo.",
        "Segunda cita valida y suficientemente larga para el minimo.",
        "Tercera cita valida y suficientemente larga para el minimo.",
    )
    raw = RawCategoryNarrative.model_validate(
        {
            "blocks": [
                {
                    "type": "bullet_list",
                    "items": [
                        {"text": "Con evidencia valida.", "confidence_level": "alta", "item_refs": [0]},
                        {"text": "Sin evidencia.", "confidence_level": "alta", "item_refs": []},
                        {"text": "Con indice invalido.", "confidence_level": "alta", "item_refs": [42]},
                    ],
                }
            ]
        }
    )

    narrative = _resolve_narrative_sources(raw, items, correlation_id="corr")

    referenced_ids = {sid for bullet in narrative.blocks[0].items for sid in bullet.source_ids}
    source_ids = {s.id for s in narrative.sources}
    assert referenced_ids == source_ids
