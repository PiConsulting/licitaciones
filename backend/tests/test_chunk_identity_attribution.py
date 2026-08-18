"""Trazabilidad del chunk desde la verificación de grounding hasta el highlight.

REGRESIÓN ATR-01 / ATR-04 / ATR-05 (auditoría 2026-08-13).

`_verify_citation_grounding` sabía cuál de los chunks candidatos respaldaba
cada cita -- lo estaba iterando dentro de un `any(...)` -- pero descartaba esa
información. Como el matcheo era por `(document_id, page_number)`, todo aguas
abajo tenía que RECONSTRUIR el origen buscando el texto de la cita de nuevo,
primero en la síntesis y después en el highlighting. Dos reconstrucciones
frágiles de un dato que ya se tenía.

El síntoma: una frase que aparece en dos chunks de la misma página (fórmulas
jurídicas del tipo "conforme lo establecido en el presente pliego") se podía
resolver al chunk equivocado -- el usuario clickea un dato de garantías y
aterriza en adjudicación.
"""
from __future__ import annotations

from analysis.extraction.extractors.base import _find_grounding_chunk, _verify_citation_grounding

_FRASE_AMBIGUA = "conforme lo establecido en el presente pliego de condiciones"


def _chunk(chunk_id: str, content: str, *, page: int = 4, blocks: list[dict] | None = None) -> dict:
    chunk: dict = {
        "id": chunk_id,
        "document_id": "doc-1",
        "page_number": page,
        "chunk_index": int(chunk_id.rsplit("--", 1)[-1]),
        "content": content,
        "block_type": "paragraph",
    }
    if blocks is not None:
        chunk["source"] = {"page": page, "block_type": "paragraph", "blocks": blocks}
    return chunk


def _item(citation: str) -> dict:
    return {
        "tipo": "mantenimiento_oferta",
        "valor": "1%",
        "extraction_status": "success",
        "source_references": [
            {"document_id": "doc-1", "page_number": 4, "citation": citation}
        ],
    }


def test_la_referencia_verificada_registra_el_chunk_que_la_respalda() -> None:
    citation = "La garantía de mantenimiento de oferta será del 1% del presupuesto"
    chunks = [_chunk("an-1--doc-1--7", f"Artículo 12. {citation}.")]
    items = [_item(citation)]

    _verify_citation_grounding(items, chunks, category="garantias", correlation_id="atr01")

    ref = items[0]["source_references"][0]
    assert ref["chunk_id"] == "an-1--doc-1--7"


def test_la_referencia_verificada_arrastra_metadata_de_documento() -> None:
    citation = "La garantía de mantenimiento de oferta será del 1% del presupuesto"
    chunk = _chunk("an-1--doc-1--7", f"Artículo 12. {citation}.")
    chunk["source"] = {
        "page": 4,
        "block_type": "paragraph",
        "blocks": [],
        "filename": "pliego.pdf",
        "is_primary": True,
    }
    items = [_item(citation)]

    _verify_citation_grounding(items, [chunk], category="garantias", correlation_id="atr01")

    ref = items[0]["source_references"][0]
    assert ref["filename"] == "pliego.pdf"
    assert ref["is_primary"] is True


def test_elige_el_chunk_correcto_cuando_la_frase_se_repite_en_la_pagina() -> None:
    """El caso que motivó el hallazgo: misma frase, dos chunks, misma página."""
    chunks = [
        _chunk("an-1--doc-1--7", f"Artículo 9. Adjudicación. {_FRASE_AMBIGUA}."),
        _chunk("an-1--doc-1--8", f"Artículo 10. Garantías. {_FRASE_AMBIGUA}."),
    ]

    # La cita del item incluye el contexto que lo desambigua.
    citation = f"Artículo 10. Garantías. {_FRASE_AMBIGUA}"
    items = [_item(citation)]

    _verify_citation_grounding(items, chunks, category="garantias", correlation_id="atr01")

    ref = items[0]["source_references"][0]
    assert ref["chunk_id"] == "an-1--doc-1--8", (
        "se registró el chunk de adjudicación para un dato de garantías"
    )


def test_find_grounding_chunk_devuelve_none_si_ninguno_respalda_la_cita() -> None:
    chunks = [_chunk("an-1--doc-1--7", "Texto que no contiene la cita buscada en absoluto.")]

    assert _find_grounding_chunk("Una cita que no existe en ningún chunk", chunks) is None


def test_cita_demasiado_corta_no_ancla_a_ningun_chunk() -> None:
    """El piso de CITATION_MIN_CHARS sigue vigente: no se ancla por una palabra."""
    chunks = [_chunk("an-1--doc-1--7", "La oferta y la garantía del oferente.")]

    assert _find_grounding_chunk("oferta", chunks) is None


def test_se_registra_el_block_id_del_bloque_que_contiene_la_cita() -> None:
    """ATR-04: antes `block_id` sólo lo poblaba el augment de identificación, y
    tomaba `blocks[0]` sin verificar cuál bloque contenía la cita."""
    citation = "La garantía de mantenimiento de oferta será del 1% del presupuesto"
    chunks = [
        _chunk(
            "an-1--doc-1--7",
            f"Párrafo introductorio del artículo.\n\n{citation}.",
            blocks=[
                {"block_id": "(4, 0)", "text": "Párrafo introductorio del artículo.", "bbox": []},
                {"block_id": "(4, 1)", "text": f"{citation}.", "bbox": []},
            ],
        )
    ]
    items = [_item(citation)]

    _verify_citation_grounding(items, chunks, category="garantias", correlation_id="atr01")

    ref = items[0]["source_references"][0]
    assert ref["block_id"] == "(4, 1)", "se anotó el bloque equivocado (o el primero por defecto)"


def test_el_chunk_id_sobrevive_hasta_la_source_de_la_narrativa() -> None:
    """ATR-05: `NarrativeSource` no declaraba `chunk_id`, así que pydantic lo
    descartaba al validar y el dato moría antes de llegar al highlighting."""
    from analysis.extraction.schemas import RawCategoryNarrative
    from analysis.extraction.synthesis import _resolve_narrative_sources

    citation = "La garantía de mantenimiento de oferta será del 1% del presupuesto"
    items = [_item(citation)]
    items[0]["source_references"][0]["chunk_id"] = "an-1--doc-1--7"

    raw = RawCategoryNarrative.model_validate(
        {
            "blocks": [
                {
                    "type": "paragraph",
                    "text": "Se exige garantía del 1%.",
                    "confidence_level": "alta",
                    "item_refs": [0],
                }
            ]
        }
    )

    narrative = _resolve_narrative_sources(raw, items, correlation_id="atr01")

    assert narrative.sources[0].chunk_id == "an-1--doc-1--7"


def _pdf_con_la_frase_dos_veces(tmp_path, frase: str) -> str:
    """Un PDF donde la misma frase aparece bajo dos artículos distintos."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    # Los títulos van con cuerpo más grande: así es como `_select_best_instance`
    # los reconoce como encabezados en un pliego real.
    page.insert_text((57, 100), "Artículo 9. Adjudicación.", fontsize=15)
    page.insert_text((57, 120), frase, fontsize=10)
    page.insert_text((57, 500), "Artículo 10. Garantías.", fontsize=15)
    page.insert_text((57, 520), frase, fontsize=10)
    ruta = tmp_path / "ambigua.pdf"
    doc.save(str(ruta))
    doc.close()
    return str(ruta)


def test_el_chunk_id_desambigua_entre_dos_apariciones(tmp_path) -> None:
    """La misma frase aparece dos veces en la página, bajo artículos distintos.
    El `chunk_id` que anotó `_verify_citation_grounding` dice en cuál estaba la
    evidencia, y de ahí sale el `section_hint` que elige la aparición.

    NOTA (2026-08-14): antes esto se verificaba a través del camino de bbox
    almacenado, que emitía el rectángulo del PÁRRAFO entero y se eliminó por
    ser la causa del "resaltado por párrafo". La desambiguación por chunk sigue
    existiendo, pero ahora opera sobre el PDF real: elige QUÉ aparición
    resaltar, no qué párrafo pintar.
    """
    from analysis.extraction.highlight import compute_highlights_for_sources

    ruta = _pdf_con_la_frase_dos_veces(tmp_path, _FRASE_AMBIGUA)

    chunks_by_doc_page = {
        ("doc-1", 1): [
            {
                "id": "an-1--doc-1--7",
                "content": f"Artículo 9. Adjudicación. {_FRASE_AMBIGUA}.",
                "section_path": "Artículo 9 > Adjudicación",
            },
            {
                "id": "an-1--doc-1--8",
                "content": f"Artículo 10. Garantías. {_FRASE_AMBIGUA}.",
                "section_path": "Artículo 10 > Garantías",
            },
        ]
    }

    enriched = compute_highlights_for_sources(
        sources=[
            {
                "document_id": "doc-1",
                "page_number": 1,
                "citation": _FRASE_AMBIGUA,
                "chunk_id": "an-1--doc-1--8",
            }
        ],
        document_id_to_blob_path={"doc-1": ruta},
        correlation_id="atr01",
        chunks_by_doc_page=chunks_by_doc_page,
    )

    regions = enriched[0]["highlight_regions"]
    assert len(regions) == 1
    assert regions[0]["y"] > 400, (
        "resaltó la aparición del artículo de adjudicación (arriba) en vez de "
        "la del artículo de garantías (abajo)"
    )


def test_sin_pdf_no_hay_coordenadas_aunque_haya_chunk(tmp_path) -> None:
    """El bbox almacenado de Azure DI es el del párrafo entero: nunca se emite.
    Sin PDF real no hay coordenadas, y eso es lo correcto -- el visor tiene así
    la señal de que debe degradar a marcar sobre la capa de texto."""
    from analysis.extraction.highlight import compute_highlights_for_sources

    citation = "La garantía de mantenimiento de oferta será del 1% del presupuesto"
    bloque = {
        "block_id": "(4, 0)",
        "text": f"{citation}.",
        "bbox": [{"page": 4, "x": 10.0, "y": 250.0, "width": 300.0, "height": 20.0}],
    }
    chunks_by_doc_page = {
        ("doc-1", 4): [_chunk("an-1--doc-1--7", f"{citation}.", blocks=[bloque])]
    }

    enriched = compute_highlights_for_sources(
        sources=[{"document_id": "doc-1", "page_number": 4, "citation": citation}],
        document_id_to_blob_path={},
        correlation_id="atr01",
        chunks_by_doc_page=chunks_by_doc_page,
    )

    assert enriched[0]["highlight_regions"] == []
