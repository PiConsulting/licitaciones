from __future__ import annotations

from analysis.extraction.extractors.preview_criterios import (
    _project_plazos_clave,
    _project_preview_llm_fields_from_riesgos,
)


def test_project_plazos_clave_detecta_validez_plural_como_mantenimiento_oferta() -> None:
    plazos = [
        {
            "referencia": "Validez de las ofertas",
            "texto_original": "El mantenimiento de las ofertas será de sesenta (60) días corridos.",
            "confidence": 0.85,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 12,
                    "citation": "El mantenimiento de las ofertas será de sesenta (60) días corridos.",
                }
            ],
            "extraction_status": "success",
        }
    ]

    projected = _project_plazos_clave(plazos)
    mantenimiento = next(item for item in projected if item["tipo"] == "mantenimiento_oferta")

    assert mantenimiento["extraction_status"] == "success"
    assert "sesenta (60) días" in str(mantenimiento["valor"])


def test_project_plazos_clave_sin_match_emite_not_found_para_ambos_tipos() -> None:
    plazos = [
        {
            "referencia": "Acto de apertura",
            "texto_original": "La apertura de sobres se realizará el 15 de octubre.",
            "confidence": 0.8,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 7,
                    "citation": "La apertura de sobres se realizará el 15 de octubre.",
                }
            ],
            "extraction_status": "success",
        }
    ]

    projected = _project_plazos_clave(plazos)
    by_tipo = {item["tipo"]: item for item in projected}

    assert by_tipo["tiempo_entrega"]["extraction_status"] == "not_found"
    assert by_tipo["mantenimiento_oferta"]["extraction_status"] == "not_found"


def test_project_plazos_clave_detecta_mantenimiento_sin_articulo() -> None:
    """Caso real reportado: pliego de Tucumán, referencia sin artículo entre
    'de' y 'oferta', y texto_original que usa el verbo 'mantener' + la
    palabra 'propuestas' en vez del sustantivo 'mantenimiento' + 'ofertas'.
    Antes del fix (`las?` exigía literalmente la palabra "la"/"las"), esto
    quedaba como not_found pese a estar bien extraído en plazos_clave."""
    plazos = [
        {
            "referencia": "Mantenimiento de oferta",
            "texto_original": (
                "Los oferentes deberán mantener sus propuestas por el plazo de 40 "
                "(cuarenta) días hábiles administrativos, contados a partir de la "
                "fecha fijada para la apertura de cotizaciones."
            ),
            "confidence": 0.8,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 26,
                    "citation": (
                        "Los oferentes deberán mantener sus propuestas por el "
                        "plazo de 40 (cuarenta) días hábiles administrativos,"
                    ),
                }
            ],
            "extraction_status": "success",
        }
    ]

    projected = _project_plazos_clave(plazos)
    mantenimiento = next(item for item in projected if item["tipo"] == "mantenimiento_oferta")

    assert mantenimiento["extraction_status"] == "success"
    assert "40 (cuarenta)" in str(mantenimiento["valor"])


def test_project_plazos_clave_no_falso_positivo_con_mantener_no_relacionado() -> None:
    """Guardrail: 'mantener' cerca de otra palabra que no sea oferta/propuesta
    (ej. una garantía que se debe 'mantener vigente') no debe clasificarse
    como mantenimiento de oferta."""
    plazos = [
        {
            "referencia": "Vigencia de garantía de cumplimiento",
            "texto_original": (
                "El adjudicatario deberá mantener vigente la garantía de "
                "cumplimiento del contrato durante 12 meses."
            ),
            "confidence": 0.8,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 9,
                    "citation": (
                        "El adjudicatario deberá mantener vigente la garantía de "
                        "cumplimiento del contrato durante 12 meses."
                    ),
                }
            ],
            "extraction_status": "success",
        }
    ]

    projected = _project_plazos_clave(plazos)
    mantenimiento = next(item for item in projected if item["tipo"] == "mantenimiento_oferta")

    assert mantenimiento["extraction_status"] == "not_found"


def test_project_preview_llm_fields_from_riesgos_detecta_moneda_y_logistica() -> None:
    riesgos = [
        {
            "tipo": "financiero",
            "subtipo": "otro_explicito",
            "valor": "Todos los precios deberán cotizarse en dólares estadounidenses (USD) sin IVA.",
            "confidence": 0.8,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 44,
                    "citation": "Todos los precios deberán cotizarse en dólares estadounidenses (USD) sin IVA.",
                }
            ],
            "extraction_status": "success",
        },
        {
            "tipo": "operativo",
            "subtipo": "operativo",
            "valor": "El proveedor adjudicatario asume transporte, entrega, desembalaje y seguros.",
            "confidence": 0.75,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 34,
                    "citation": "Todos los servicios de transporte, entrega y desembalaje estarán a cargo del proveedor.",
                }
            ],
            "extraction_status": "success",
        },
    ]

    projected = _project_preview_llm_fields_from_riesgos(riesgos)
    by_tipo = {item["tipo"]: item for item in projected}

    assert by_tipo["moneda"]["extraction_status"] == "success"
    assert "usd" in str(by_tipo["moneda"]["valor"]).lower()

    assert by_tipo["responsabilidad_costos_logisticos"]["extraction_status"] == "success"
    assert "transporte" in str(by_tipo["responsabilidad_costos_logisticos"]["valor"]).lower()


def test_project_preview_llm_fields_from_riesgos_sin_evidencia_emite_not_found() -> None:
    riesgos = [
        {
            "tipo": "financiero",
            "subtipo": "otro_explicito",
            "valor": "La adjudicación depende de menor precio evaluado.",
            "confidence": 0.7,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 44,
                    "citation": "La adjudicación recaerá sobre la oferta de menor precio total evaluado.",
                }
            ],
            "extraction_status": "success",
        }
    ]

    projected = _project_preview_llm_fields_from_riesgos(riesgos)
    by_tipo = {item["tipo"]: item for item in projected}

    assert by_tipo["forma_pago"]["extraction_status"] == "not_found"
    assert by_tipo["tipo_cambio"]["extraction_status"] == "not_found"
    assert by_tipo["anticipo_financiero"]["extraction_status"] == "not_found"
