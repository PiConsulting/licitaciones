from __future__ import annotations

from unittest.mock import Mock

import pytest

from analysis.extraction.extractors.causales import extractor_causales
from analysis.extraction.extractors.criterios_evaluacion import extractor_criterios_evaluacion
from analysis.extraction.extractors.cronograma_proceso import extractor_cronograma_proceso
from analysis.extraction.extractors.documentos_requeridos import extractor_documentos_requeridos
from analysis.extraction.extractors.estimacion_presupuesto import extractor_estimacion_presupuesto
from analysis.extraction.extractors.garantias import extractor_garantias
from analysis.extraction.extractors.plazos import extractor_plazos
from analysis.extraction.extractors.restricciones_participacion import extractor_restricciones_participacion
from analysis.extraction.graph import calculate_confidence, graph, merge_node
from analysis.extraction.schemas import ExtractedData


@pytest.fixture
def mock_state() -> dict:
    return {
        "analysis_id": "analysis-123",
        "correlation_id": "corr-456",
    }


@pytest.fixture
def mock_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "analysis.extraction.extractors.base.search_hybrid",
        lambda **_kwargs: [
            {
                "document_id": "doc-1",
                "page_number": 3,
                "content": "Las ofertas deben presentarse hasta el 15 de mayo de 2024.",
                "section_key": "plazos",
            }
        ],
    )


def _fake_llm_result(prompt: str) -> dict:
    if '"plazos"' in prompt:
        return {
            "plazos": [
                {
                    "tipo": "presentación ofertas",
                    "fecha": "2024-05-15",
                    "confidence": 0.95,
                    "source_references": [
                        {"document_id": "doc-1", "page_number": 3, "citation": "texto literal"}
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    if '"garantias"' in prompt:
        return {
            "garantias": [
                {
                    "tipo": "garantía de oferta",
                    "monto_porcentaje": 1.0,
                    "confidence": 0.9,
                    "source_references": [
                        {"document_id": "doc-1", "page_number": 5, "citation": "texto literal"}
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    if '"causales"' in prompt:
        return {
            "causales": [
                {
                    "tipo": "inhabilitante",
                    "valor": "falta de certificado",
                    "confidence": 0.8,
                    "source_references": [
                        {"document_id": "doc-1", "page_number": 7, "citation": "texto literal"}
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    if '"documentos_requeridos"' in prompt:
        return {
            "documentos_requeridos": [
                {
                    "tipo": "legal",
                    "valor": "CUIT",
                    "confidence": 0.8,
                    "source_references": [
                        {"document_id": "doc-1", "page_number": 8, "citation": "texto literal"}
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    if '"criterios_evaluacion"' in prompt:
        return {
            "criterios_evaluacion": [
                {
                    "tipo": "técnico",
                    "valor": "60%",
                    "confidence": 0.8,
                    "source_references": [
                        {"document_id": "doc-1", "page_number": 9, "citation": "texto literal"}
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    if '"restricciones_participacion"' in prompt:
        return {
            "restricciones_participacion": [
                {
                    "tipo": "experiencia",
                    "valor": "3 contratos",
                    "confidence": 0.8,
                    "source_references": [
                        {"document_id": "doc-1", "page_number": 10, "citation": "texto literal"}
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    if '"cronograma_proceso"' in prompt:
        return {
            "cronograma_proceso": [
                {
                    "tipo": "apertura",
                    "valor": "2024-05-20",
                    "confidence": 0.8,
                    "source_references": [
                        {"document_id": "doc-1", "page_number": 11, "citation": "texto literal"}
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    return {
        "estimacion_presupuesto": {
            "monto": 1000000,
            "moneda": "ARS",
            "confidence": 0.8,
            "source_references": [{"document_id": "doc-1", "page_number": 12, "citation": "texto literal"}],
            "extraction_status": "success",
        }
    }


@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "analysis.extraction.extractors.base._call_llm",
        lambda prompt, correlation_id: (
            _fake_llm_result(prompt),
            {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        ),
    )


def test_graph_execution_all_success(mock_state: dict, mock_search: None, mock_llm: None) -> None:
    result = graph.invoke(mock_state)
    assert "extracted_data" in result
    assert len(result["extracted_data"]["plazos"]) > 0
    assert len(result["extracted_data"]["garantias"]) > 0


def test_extractor_retry_on_failure(mock_state: dict, mock_search: None, monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        content = '{"plazos": []}'
        response_metadata = {"token_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}

    mock_client = Mock()
    mock_client.invoke.side_effect = [Exception("Timeout"), Response()]
    monkeypatch.setattr("analysis.extraction.extractors.base.get_azure_openai_client", lambda: mock_client)

    result = extractor_plazos(mock_state)
    assert mock_client.invoke.call_count == 2
    assert result["plazos_status"] in {"success", "not_found"}


def test_extractor_failure_continues(mock_state: dict, mock_search: None, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = Mock()
    mock_client.invoke.side_effect = Exception("Permanent failure")
    monkeypatch.setattr("analysis.extraction.extractors.base.get_azure_openai_client", lambda: mock_client)

    result = extractor_plazos(mock_state)
    assert result["plazos_status"] == "failed"


def test_merge_node_detects_conflicts() -> None:
    state = {
        "analysis_id": "analysis-1",
        "correlation_id": "corr-1",
        "plazos": [
            {
                "tipo": "presentación ofertas",
                "fecha": "2024-05-15",
                "source_references": [{"document_id": "doc-1", "page_number": 1, "citation": "a"}],
                "extraction_status": "success",
                "confidence": 0.8,
            },
            {
                "tipo": "presentación ofertas",
                "fecha": "2024-05-20",
                "source_references": [{"document_id": "doc-2", "page_number": 2, "citation": "b"}],
                "extraction_status": "success",
                "confidence": 0.8,
            },
        ],
        "garantias": [],
        "causales": [],
        "documentos": [],
        "criterios": [],
        "restricciones": [],
        "cronograma": [],
        "presupuesto": {},
        "plazos_status": "success",
        "garantias_status": "success",
        "causales_status": "success",
        "documentos_status": "success",
        "criterios_status": "success",
        "restricciones_status": "success",
        "cronograma_status": "success",
        "presupuesto_status": "not_found",
    }

    result = merge_node(state)
    assert len(result["conflicts"]) > 0
    assert result["conflicts"][0]["category"] == "plazos"


def test_confidence_calculation() -> None:
    confidence_high = calculate_confidence(
        [{"citation": "A" * 150}, {"citation": "B" * 150}],
        "success",
    )
    confidence_low = calculate_confidence([{"citation": "A" * 50}], "success")

    assert confidence_high >= 0.8
    assert confidence_low < 0.8


def test_json_contract_compliance() -> None:
    payload = {
        "plazos": [
            {
                "tipo": "presentación",
                "fecha": "2024-05-15",
                "confidence": 0.95,
                "source_references": [
                    {
                        "document_id": "doc-1",
                        "page_number": 3,
                        "citation": "texto literal",
                    }
                ],
                "extraction_status": "success",
            }
        ],
        "garantias": [],
        "causales_rechazo": [],
        "documentos_requeridos": [],
        "criterios_evaluacion": [],
        "restricciones_participacion": [],
        "cronograma_proceso": [],
        "estimacion_presupuesto": None,
    }

    validated = ExtractedData(**payload)
    assert validated.plazos[0].confidence == 0.95


def test_individual_extractors(mock_state: dict, mock_search: None, mock_llm: None) -> None:
    assert extractor_plazos(dict(mock_state))["plazos_status"] in {"success", "not_found"}
    assert extractor_garantias(dict(mock_state))["garantias_status"] in {"success", "not_found"}
    assert extractor_causales(dict(mock_state))["causales_status"] in {"success", "not_found"}
    assert extractor_documentos_requeridos(dict(mock_state))["documentos_status"] in {"success", "not_found"}
    assert extractor_criterios_evaluacion(dict(mock_state))["criterios_status"] in {"success", "not_found"}
    assert extractor_restricciones_participacion(dict(mock_state))["restricciones_status"] in {"success", "not_found"}
    assert extractor_cronograma_proceso(dict(mock_state))["cronograma_status"] in {"success", "not_found"}
    assert extractor_estimacion_presupuesto(dict(mock_state))["presupuesto_status"] in {"success", "not_found"}
