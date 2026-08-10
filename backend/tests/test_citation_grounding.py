from __future__ import annotations

from analysis.extraction.extractors.base import _verify_citation_grounding


def _paragraph_chunk(**overrides: object) -> dict:
    base = {
        "document_id": "doc-1",
        "page_number": 3,
        "section_key": "garantias",
        "block_type": "paragraph",
        "table_ref": None,
        "content": "La garantía de mantenimiento de oferta es del 5% del monto cotizado.",
    }
    base.update(overrides)
    return base


def _table_chunk(**overrides: object) -> dict:
    base = {
        "document_id": "doc-1",
        "page_number": 3,
        "section_key": "criterios",
        "block_type": "table",
        "content": "Tabla T1 | Fila 2 | Criterio: Experiencia | Ponderacion: 40%",
        "table_ref": {"table_id": "T1", "row_index": 2, "headers": ["Criterio", "Ponderacion"]},
    }
    base.update(overrides)
    return base


def test_cita_de_parrafo_verificada() -> None:
    chunk = _paragraph_chunk()
    item = {
        "extraction_status": "success",
        "source_references": [
            {"document_id": "doc-1", "page_number": 3, "citation": "garantía de mantenimiento de oferta es del 5%"}
        ],
    }

    _verify_citation_grounding([item], [chunk], category="garantias", correlation_id="corr-1")

    assert item["extraction_status"] == "success"
    assert "_warning" not in item


def test_cita_de_parrafo_alucinada() -> None:
    chunk = _paragraph_chunk()
    item = {
        "extraction_status": "success",
        "source_references": [
            {
                "document_id": "doc-1",
                "page_number": 3,
                "citation": "la garantía de cumplimiento de contrato es del 10%",
            }
        ],
    }

    _verify_citation_grounding([item], [chunk], category="garantias", correlation_id="corr-1")

    assert item["extraction_status"] == "partial"
    assert item["_warning"] == "cita_no_verificada"


def test_cita_de_parrafo_con_espaciado_distinto_legitimo() -> None:
    # El chunk tiene un salto de linea en medio de la frase; el LLM la cita con
    # un espacio simple. Esto NO debe considerarse una alucinacion.
    chunk = _paragraph_chunk(content="La garantía de mantenimiento\nde oferta es del 5% del monto cotizado.")
    item = {
        "extraction_status": "success",
        "source_references": [
            {"document_id": "doc-1", "page_number": 3, "citation": "garantía de mantenimiento de oferta es del 5%"}
        ],
    }

    _verify_citation_grounding([item], [chunk], category="garantias", correlation_id="corr-1")

    assert item["extraction_status"] == "success"
    assert "_warning" not in item


def test_cita_de_tabla_verificada() -> None:
    chunk = _table_chunk()
    item = {
        "extraction_status": "success",
        "source_references": [
            {"document_id": "doc-1", "page_number": 3, "citation": "Encabezado: Ponderacion | Fila: 2 | Valor: 40%"}
        ],
    }

    _verify_citation_grounding([item], [chunk], category="criterios_evaluacion", correlation_id="corr-1")

    assert item["extraction_status"] == "success"
    assert "_warning" not in item


def test_cita_de_tabla_alucinada() -> None:
    chunk = _table_chunk()
    item = {
        "extraction_status": "success",
        "source_references": [
            {"document_id": "doc-1", "page_number": 3, "citation": "Encabezado: Ponderacion | Fila: 2 | Valor: 90%"}
        ],
    }

    _verify_citation_grounding([item], [chunk], category="criterios_evaluacion", correlation_id="corr-1")

    assert item["extraction_status"] == "partial"
    assert item["_warning"] == "cita_no_verificada"


def test_item_con_una_referencia_valida_y_otra_alucinada_no_se_penaliza() -> None:
    chunk = _paragraph_chunk()
    item = {
        "extraction_status": "success",
        "source_references": [
            {"document_id": "doc-1", "page_number": 3, "citation": "garantía de mantenimiento de oferta es del 5%"},
            {"document_id": "doc-1", "page_number": 3, "citation": "esto no aparece en ningun lado del pliego"},
        ],
    }

    _verify_citation_grounding([item], [chunk], category="garantias", correlation_id="corr-1")

    assert item["extraction_status"] == "success"
    assert "_warning" not in item


def test_no_penaliza_items_not_found_sin_referencias() -> None:
    item = {"extraction_status": "not_found", "source_references": []}

    _verify_citation_grounding([item], [_paragraph_chunk()], category="garantias", correlation_id="corr-1")

    assert item["extraction_status"] == "not_found"
    assert "_warning" not in item


def test_no_aplica_chequeo_de_tabla_a_cita_de_parrafo() -> None:
    # Cita de tabla legitima verificada solo contra chunks de tabla; no debe
    # aplicarse el chequeo de subcadena literal de parrafo a este formato.
    table_chunk = _table_chunk()
    paragraph_chunk = _paragraph_chunk(content="Encabezado: Ponderacion | Fila: 2 | Valor: 40% no es texto real")
    item = {
        "extraction_status": "success",
        "source_references": [
            {"document_id": "doc-1", "page_number": 3, "citation": "Encabezado: Ponderacion | Fila: 2 | Valor: 40%"}
        ],
    }

    _verify_citation_grounding(
        [item], [table_chunk, paragraph_chunk], category="criterios_evaluacion", correlation_id="corr-1"
    )

    assert item["extraction_status"] == "success"
    assert "_warning" not in item


def test_plazo_cita_corta_prioriza_texto_original_para_evitar_match_ambiguo() -> None:
    chunks = [
        _paragraph_chunk(
            page_number=9,
            content="La adjudicación se realizará por menor precio entre las ofertas admisibles.",
        ),
        _paragraph_chunk(
            page_number=9,
            content="Presentación de ofertas: 15/09/2026, 10:00 hs, en la Oficina de Compras.",
        ),
    ]
    item = {
        "tipo": "presentacion_ofertas",
        "texto_original": "Presentación de ofertas: 15/09/2026, 10:00 hs, en la Oficina de Compras.",
        "extraction_status": "success",
        "source_references": [
            {"document_id": "doc-1", "page_number": 9, "citation": "ofertas"},
        ],
    }

    _verify_citation_grounding([item], chunks, category="plazos_clave", correlation_id="corr-1")

    assert item["extraction_status"] == "success"
    assert item["source_references"][0]["citation"] == item["texto_original"]


def test_cita_de_una_palabra_no_pasa_grounding_estricto() -> None:
    chunk = _paragraph_chunk(
        content="La garantía de mantenimiento de oferta es del 5% del monto cotizado.",
    )
    item = {
        "extraction_status": "success",
        "source_references": [
            {"document_id": "doc-1", "page_number": 3, "citation": "oferta"},
        ],
    }

    _verify_citation_grounding([item], [chunk], category="garantias", correlation_id="corr-1")

    # La palabra existe en el chunk, pero no cumple la política mínima de cita.
    assert item["extraction_status"] == "partial"
    assert item["_warning"] == "cita_no_verificada"
    assert item["source_references"] == []


def test_rescata_cita_desde_valor_literal_del_item_en_mismo_chunk() -> None:
    chunk = _paragraph_chunk(
        page_number=4,
        content=(
            "Constancia de inscripción en el Registro de Proveedores del Municipio, "
            "debidamente vigente al momento de la apertura de sobres."
        ),
    )
    item = {
        "valor": "Constancia de inscripción en el Registro de Proveedores del Municipio, debidamente vigente al momento de la apertura de sobres.",
        "extraction_status": "success",
        "source_references": [
            {"document_id": "doc-1", "page_number": 4, "citation": "Registro de Proveedores"},
        ],
    }

    _verify_citation_grounding([item], [chunk], category="requisitos_admisibilidad", correlation_id="corr-1")

    assert item["extraction_status"] == "success"
    assert item["source_references"][0]["citation"] == item["valor"]
    assert "_warning" not in item
