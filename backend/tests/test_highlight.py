# Tests para highlight pre-computado

import pytest
from pathlib import Path

from analysis.extraction import highlight as highlight_module
from analysis.extraction.highlight import (
    compute_highlight_regions,
    compute_highlights_for_sources,
    _normalize_for_search,
)


def test_normalize_for_search():
    """Normalización debe ser tolerante a diferencias de OCR."""
    # Acentos
    assert _normalize_for_search("garantía del 10%") == _normalize_for_search("garantia del 10%")
    
    # Espacios múltiples
    assert _normalize_for_search("garantía  del   10%") == "garantia del 10%"
    
    # Guiones diferentes
    assert _normalize_for_search("art. 10-15") == _normalize_for_search("art. 10–15")
    assert _normalize_for_search("art. 10—15") == "art. 10-15"
    
    # Case insensitive
    assert _normalize_for_search("GARANTÍA") == _normalize_for_search("garantía")


def test_compute_highlight_regions_citation_too_short():
    """Citations muy cortas no deben procesarse."""
    regions = compute_highlight_regions(
        pdf_path="/fake/path.pdf",
        page_number=1,
        citation="10%",  # Muy corto
        correlation_id="test",
    )
    assert regions == []


def test_compute_highlights_for_sources_missing_pdf():
    """Sources sin PDF path deben conservarse con highlight_regions vacío."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 5,
            "citation": "Esta es una citation de prueba que es suficientemente larga.",
        }
    ]
    
    # Sin mapeo de PDF
    document_id_to_blob_path = {}
    
    enriched = compute_highlights_for_sources(
        sources=sources,
        document_id_to_blob_path=document_id_to_blob_path,
        correlation_id="test",
    )
    
    assert len(enriched) == 1
    assert enriched[0]["highlight_regions"] == []


def test_compute_highlights_for_sources_preserves_other_fields():
    """El enriquecimiento debe preservar todos los campos de la source."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 5,
            "citation": "Esta es una citation de prueba.",
            "unverified": True,  # Campo adicional
        }
    ]
    
    document_id_to_blob_path = {}
    
    enriched = compute_highlights_for_sources(
        sources=sources,
        document_id_to_blob_path=document_id_to_blob_path,
        correlation_id="test",
    )
    
    assert enriched[0]["id"] == 0
    assert enriched[0]["document_id"] == "doc-1"
    assert enriched[0]["page_number"] == 5
    assert enriched[0]["citation"] == "Esta es una citation de prueba."
    assert enriched[0]["unverified"] is True
    assert "highlight_regions" in enriched[0]


def test_sin_pdf_no_se_emite_el_bbox_del_parrafo():
    """El bbox del campo 'source' es el del párrafo entero: nunca se emite."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Presupuesto oficial de $3.850.000",
        }
    ]
    
    # Simular chunks con el nuevo formato 'source'
    chunks_by_doc_page = {
        ("doc-1", 1): [
            {
                "content": "Presupuesto oficial de $3.850.000",
                "source": {
                    "page": 1,
                    "block_type": "table",
                    "blocks": [
                        {
                            "block_id": "para_1",
                            "bbox": {"x": 100.0, "y": 200.0, "width": 300.0, "height": 50.0},
                            "text": "Presupuesto oficial de $3.850.000"
                        }
                    ]
                }
            }
        ]
    }
    
    enriched = compute_highlights_for_sources(
        sources=sources,
        document_id_to_blob_path={},
        correlation_id="test",
        chunks_by_doc_page=chunks_by_doc_page,
    )
    
    # FIX (2026-08-14): sin PDF no hay coordenadas. Este test afirmaba que se
    # emitía el bbox del bloque de Azure DI, que es el del PÁRRAFO completo --
    # el "resaltado por párrafo" que reportó la usuaria. Pintar un párrafo
    # entero le dice a la persona que la evidencia es todo eso, y no le deja
    # ninguna señal de que el sistema no supo ubicar la cita.
    assert len(enriched) == 1
    assert enriched[0]["highlight_regions"] == []


def test_sin_pdf_tampoco_se_emite_el_bbox_legacy():
    """Mismo contrato para el formato legacy 'blocks'."""
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Garantía del 5%",
        }
    ]
    
    # Simular chunks con formato legacy (blocks directamente en el chunk)
    chunks_by_doc_page = {
        ("doc-1", 1): [
            {
                "content": "Garantía del 5%",
                "blocks": [
                    {
                        "page": 1,
                        "content": "Garantía del 5%",
                        "bbox": [
                            {"page": 1, "x": 150.0, "y": 250.0, "width": 200.0, "height": 40.0}
                        ]
                    }
                ]
            }
        ]
    }
    
    enriched = compute_highlights_for_sources(
        sources=sources,
        document_id_to_blob_path={},
        correlation_id="test",
        chunks_by_doc_page=chunks_by_doc_page,
    )
    
    assert len(enriched) == 1
    assert enriched[0]["highlight_regions"] == []


def test_un_bloque_que_no_contiene_la_cita_nunca_aporta_coordenadas():
    """Esta garantía sigue en pie, ahora por construcción: sin PDF no se emite
    ninguna región, venga de donde venga el bbox.

    (Este test ya venía fallando antes de este cambio: afirmaba que el bloque
    que SÍ contiene la cita aportaba su bbox, y ese bbox es el del párrafo.)
    """
    sources = [
        {
            "id": 0,
            "document_id": "doc-1",
            "page_number": 1,
            "citation": "Garantía de mantenimiento de oferta del 5%",
        }
    ]
    chunks_by_doc_page = {
        ("doc-1", 1): [
            {
                "content": "Otro texto. Garantía de mantenimiento de oferta del 5%. Fin.",
                "source": {
                    "blocks": [
                        {
                            "text": "Un bloque que no tiene la cita",
                            "bbox": {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0},
                        },
                        {
                            "text": "Garantía de mantenimiento de oferta del 5%",
                            "bbox": {"x": 10.0, "y": 20.0, "width": 30.0, "height": 40.0},
                        },
                    ]
                },
            }
        ]
    }

    enriched = compute_highlights_for_sources(
        sources=sources,
        document_id_to_blob_path={},
        correlation_id="test",
        chunks_by_doc_page=chunks_by_doc_page,
    )

    assert enriched[0]["highlight_regions"] == []


class TestLiveSearchFirst:
    """La búsqueda viva sobre el PDF real es el ÚNICO camino de coordenadas.

    NOTA (2026-08-14): estos dos tests se reescribieron después de que un
    editado mío borrara la clase original por accidente. El primero conserva la
    intención del que existía (que se use el PDF real cuando está disponible);
    el segundo reemplaza a `test_falls_back_to_stored_bbox_when_live_search_finds_nothing`,
    que afirmaba justamente el fallback que se eliminó.
    """

    def test_usa_el_pdf_real_cuando_hay_ruta_disponible(self, monkeypatch):
        calls = []

        def _fake(pdf_path, page_number, citation, correlation_id=None, section_hint=None):
            calls.append((pdf_path, page_number, citation, section_hint))
            return [{"x": 10.0, "y": 20.0, "width": 300.0, "height": 15.0}]

        monkeypatch.setattr(highlight_module, "compute_highlight_regions", _fake)

        enriched = highlight_module.compute_highlights_for_sources(
            sources=[
                {
                    "document_id": "doc-1",
                    "page_number": 3,
                    "citation": "La garantia de mantenimiento de oferta sera del 1%",
                }
            ],
            document_id_to_blob_path={"doc-1": "/tmp/fake.pdf"},
            correlation_id="test",
            category_key="garantia_oferta",
        )

        assert calls[0][0] == "/tmp/fake.pdf"
        assert calls[0][1] == 3
        # Sin chunk que aporte `section_path`, el hint cae al nombre de la
        # categoría, como antes.
        assert calls[0][3] == "garantia oferta"
        assert enriched[0]["highlight_regions"] == [
            {"x": 10.0, "y": 20.0, "width": 300.0, "height": 15.0}
        ]

    def test_el_section_path_del_chunk_le_gana_al_nombre_de_categoria(self, monkeypatch):
        """ATR-01, ahora donde sirve: el chunk que verificó la cita dice en qué
        artículo del pliego estaba la evidencia. Eso desambigua entre varias
        apariciones de la misma frase mucho mejor que el nombre de la
        categoría."""
        calls = []

        def _fake(pdf_path, page_number, citation, correlation_id=None, section_hint=None):
            calls.append(section_hint)
            return [{"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0}]

        monkeypatch.setattr(highlight_module, "compute_highlight_regions", _fake)

        highlight_module.compute_highlights_for_sources(
            sources=[
                {
                    "document_id": "doc-1",
                    "page_number": 3,
                    "citation": "conforme lo establecido en el presente pliego",
                    "chunk_id": "an-1--doc-1--8",
                }
            ],
            document_id_to_blob_path={"doc-1": "/tmp/fake.pdf"},
            correlation_id="test",
            category_key="garantias",
            chunks_by_doc_page={
                ("doc-1", 3): [
                    {
                        "id": "an-1--doc-1--7",
                        "content": "conforme lo establecido en el presente pliego",
                        "section_path": "Artículo 9 > Adjudicación",
                    },
                    {
                        "id": "an-1--doc-1--8",
                        "content": "conforme lo establecido en el presente pliego",
                        "section_path": "Artículo 10 > Garantías",
                    },
                ]
            },
        )

        assert calls[0] == "Artículo 10 > Garantías"


def _build_pdf_with_marker_at(tmp_path, marker: str, y_position: float, page_height: float = 800.0):
    """PDF de una página con `marker` dibujado a `y_position` puntos del tope."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=400, height=page_height)
    page.insert_text((50, y_position), marker)
    pdf_path = tmp_path / "coords.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)


def test_highlight_region_y_is_measured_from_top_of_page(tmp_path):
    """Un texto cerca del borde superior debe devolver un `y` chico."""
    from analysis.extraction.highlight import compute_highlight_regions

    page_height = 800.0
    pdf_path = _build_pdf_with_marker_at(tmp_path, "ARRIBA", y_position=60.0, page_height=page_height)

    regions = compute_highlight_regions(
        pdf_path, page_number=1, citation="ARRIBA", correlation_id="test-hl01"
    )

    assert len(regions) == 1
    # El texto está a ~60pt del tope: y debe estar en la mitad superior.
    assert regions[0]["y"] < page_height / 2, (
        f"y={regions[0]['y']} corresponde a la mitad inferior de la página; "
        "el eje Y está invertido (regresión de HL-01)"
    )
    assert regions[0]["y"] == pytest.approx(60.0, abs=15.0)


def test_highlight_region_y_grows_downward(tmp_path):
    """Un texto más abajo en la página debe devolver un `y` mayor."""
    from analysis.extraction.highlight import compute_highlight_regions

    page_height = 800.0

    doc_dir = tmp_path / "pair"
    doc_dir.mkdir()
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=400, height=page_height)
    page.insert_text((50, 60.0), "TOKENARRIBA")
    page.insert_text((50, 740.0), "TOKENABAJO")
    pdf_path = doc_dir / "pair.pdf"
    doc.save(str(pdf_path))
    doc.close()

    arriba = compute_highlight_regions(
        str(pdf_path), page_number=1, citation="TOKENARRIBA", correlation_id="test-hl01"
    )
    abajo = compute_highlight_regions(
        str(pdf_path), page_number=1, citation="TOKENABAJO", correlation_id="test-hl01"
    )

    assert arriba and abajo
    assert arriba[0]["y"] < abajo[0]["y"], (
        "el texto de arriba debe tener menor `y` que el de abajo; "
        "si es al revés, el eje está invertido (regresión de HL-01)"
    )


def test_highlight_region_matches_pymupdf_rect_y0(tmp_path):
    """El contrato es exactamente `rect.y0`, sin ninguna transformación."""
    import fitz

    from analysis.extraction.highlight import compute_highlight_regions

    pdf_path = _build_pdf_with_marker_at(tmp_path, "ANCLA", y_position=200.0)

    regions = compute_highlight_regions(
        pdf_path, page_number=1, citation="ANCLA", correlation_id="test-hl01"
    )

    doc = fitz.open(pdf_path)
    rect = doc[0].search_for("ANCLA")[0]
    doc.close()

    assert regions[0]["y"] == pytest.approx(rect.y0)
    assert regions[0]["x"] == pytest.approx(rect.x0)
    assert regions[0]["height"] == pytest.approx(rect.height)


def test_hay_un_solo_camino_de_coordenadas():
    """HL-01 pedía que los dos caminos del módulo emitieran la MISMA convención
    de coordenadas. Se resolvió de la forma más fuerte posible: ahora hay un
    solo camino, el de la búsqueda viva sobre el PDF real.

    El segundo camino (bbox almacenado de Azure DI) no sólo tenía riesgo de
    divergir en la convención: emitía el rectángulo del párrafo entero, y su
    unidad ni siquiera estaba unificada (Azure DI devuelve pulgadas para PDF y
    píxeles para imagen, y esa unidad no se persistía en el chunk).
    """
    from analysis.extraction.highlight import compute_highlights_for_sources

    citation = "La garantia de mantenimiento de oferta sera del uno por ciento"
    chunks_by_doc_page = {
        ("doc-1", 3): [
            {
                "content": f"Texto previo. {citation}. Texto posterior.",
                "source": {
                    "blocks": [
                        {
                            "text": f"Texto previo. {citation}. Texto posterior.",
                            "bbox": [{"page": 3, "x": 70.0, "y": 120.0, "width": 400.0, "height": 30.0}],
                        }
                    ]
                },
            }
        ]
    }

    enriched = compute_highlights_for_sources(
        sources=[{"document_id": "doc-1", "page_number": 3, "citation": citation}],
        document_id_to_blob_path={},
        correlation_id="test-hl01",
        chunks_by_doc_page=chunks_by_doc_page,
    )

    assert enriched[0]["highlight_regions"] == []
