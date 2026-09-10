from __future__ import annotations

import pytest

from analysis.extraction.extractors.preview_criterios import (
    _project_plazos_clave,
    _project_preview_llm_fields_from_riesgos,
    _project_requisitos_tecnicos,
)


def _requisito(tipo: str, valor: str, *, obligatorio: str = "no_especificado") -> dict:
    return {
        "tipo": tipo,
        "valor": valor,
        "metadata": {"obligatorio": obligatorio},
        "confidence": 0.9,
        "source_references": [
            {"document_id": "doc-1", "page_number": 3, "citation": valor}
        ],
        "extraction_status": "success",
    }


def test_project_requisitos_tecnicos_usa_el_tag_del_extractor() -> None:
    """Camino primario: filtra por `tipo` = certificacion / requisito_tecnico_
    excluyente, sin depender de que el vocabulario matchee una keyword."""
    requisitos = [
        _requisito("documento", "Constancia de inscripción en el registro de proveedores"),
        _requisito(
            "requisito_tecnico_excluyente",
            "Deberá garantizar compatibilidad para ejecutar alguna distribución GNU/Linux",
        ),
        _requisito("certificacion", "Certificación ISO/IEC 27001 vigente exigida para admisibilidad"),
    ]

    projected = _project_requisitos_tecnicos(requisitos)

    assert len(projected) == 1
    item = projected[0]
    assert item["tipo"] == "requisitos_tecnicos_excluyentes"
    assert item["extraction_status"] == "success"
    # "GNU/Linux" no matchea ninguna keyword del fallback -- entra por el tag.
    assert "GNU/Linux" in str(item["valor"])


def test_project_requisitos_tecnicos_cae_al_fallback_por_keyword_si_no_hay_tag() -> None:
    """Pliego analizado antes del cambio (ningún ítem taggeado): sigue andando
    la heurística vieja (obligatorio + keyword)."""
    requisitos = [
        _requisito("documento", "Balance de los últimos 3 ejercicios"),
        _requisito(
            "capacidad_minima",
            "Certificación ISO 9001 del fabricante",
            obligatorio="si",
        ),
    ]

    projected = _project_requisitos_tecnicos(requisitos)

    assert projected[0]["tipo"] == "requisitos_tecnicos_excluyentes"
    assert projected[0]["extraction_status"] == "success"


def test_project_requisitos_tecnicos_sin_nada_emite_not_found() -> None:
    projected = _project_requisitos_tecnicos(
        [_requisito("documento", "Declaración jurada de no encontrarse inhabilitado")]
    )

    assert projected[0]["tipo"] == "requisitos_tecnicos_excluyentes"
    assert projected[0]["extraction_status"] == "not_found"


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


def test_project_preview_llm_fields_union_llm_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    riesgos = [
        {
            "tipo": "financiero",
            "subtipo": "otro_explicito",
            "valor": "La moneda de cotización será USD.",
            "confidence": 0.8,
            "source_references": [{"citation": "Moneda: USD"}],
            "extraction_status": "success",
        },
        {
            "tipo": "financiero",
            "subtipo": "otro_explicito",
            "valor": "Se admite anticipo financiero con contragarantía.",
            "confidence": 0.82,
            "source_references": [{"citation": "anticipo financiero"}],
            "extraction_status": "success",
        },
    ]

    def fake_call_llm(_messages, correlation_id):
        assert "preview-projection" in correlation_id
        return ({"classifications": [{"index": 1, "tipos": ["anticipo_financiero"]}]}, {})

    monkeypatch.setattr("analysis.extraction.extractors.preview_criterios._call_llm", fake_call_llm)

    projected = _project_preview_llm_fields_from_riesgos(riesgos, correlation_id="corr-1")
    by_tipo = {item["tipo"]: item for item in projected}

    assert by_tipo["moneda"]["extraction_status"] == "success"
    assert by_tipo["anticipo_financiero"]["extraction_status"] == "success"
    assert by_tipo["anticipo_financiero"]["metadata"].get("_projection_source") == "llm_union_regex"


def test_project_preview_llm_fields_fallback_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    riesgos = [
        {
            "tipo": "operativo",
            "subtipo": "operativo",
            "valor": "Todos los servicios de transporte estarán a cargo del proveedor.",
            "confidence": 0.75,
            "source_references": [{"citation": "transporte a cargo del proveedor"}],
            "extraction_status": "success",
        }
    ]

    def fake_call_llm(_messages, _correlation_id):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr("analysis.extraction.extractors.preview_criterios._call_llm", fake_call_llm)

    projected = _project_preview_llm_fields_from_riesgos(riesgos, correlation_id="corr-2")
    by_tipo = {item["tipo"]: item for item in projected}

    assert by_tipo["responsabilidad_costos_logisticos"]["extraction_status"] == "success"
    assert by_tipo["responsabilidad_costos_logisticos"]["metadata"].get("_projection_source") == "regex_fallback"


def test_project_preview_llm_fields_fallback_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    riesgos = [
        {
            "tipo": "financiero",
            "subtipo": "otro_explicito",
            "valor": "Forma de pago: contra entrega.",
            "confidence": 0.7,
            "source_references": [{"citation": "contra entrega"}],
            "extraction_status": "success",
        }
    ]

    def fake_call_llm(_messages, _correlation_id):
        raise TimeoutError("timeout")

    monkeypatch.setattr("analysis.extraction.extractors.preview_criterios._call_llm", fake_call_llm)

    projected = _project_preview_llm_fields_from_riesgos(riesgos, correlation_id="corr-3")
    by_tipo = {item["tipo"]: item for item in projected}

    assert by_tipo["forma_pago"]["extraction_status"] == "success"
    assert by_tipo["forma_pago"]["metadata"].get("_projection_source") == "regex_fallback"
