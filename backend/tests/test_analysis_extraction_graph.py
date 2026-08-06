from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from analysis.extraction.extractors.anexos_obligatorios import extractor_anexos_obligatorios
from analysis.extraction.extractors.base import (
    CANONICAL_PROMPT_FILES,
    _normalize_item,
    _parse_json_response,
    validate_category_prompt_mapping,
    validate_prompt_inventory,
)
from analysis.extraction.extractors.causales import extractor_causales
from analysis.extraction.extractors.criterios_evaluacion import extractor_criterios_evaluacion
from analysis.extraction.extractors.garantias import extractor_garantias
from analysis.extraction.extractors.objeto_alcance import extractor_objeto_alcance
from analysis.extraction.extractors.plazos import extractor_plazos
from analysis.extraction.extractors.requisitos_admisibilidad import extractor_requisitos_admisibilidad
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


def _fake_llm_result(messages: list[tuple[str, str]]) -> dict:
    prompt = "\n".join(content for _role, content in messages)
    if '"objeto_alcance"' in prompt:
        return {
            "objeto_alcance": [
                {
                    "tipo": "resumen_objeto",
                    "valor": "Contratación de servicio de limpieza",
                    "confidence": 0.9,
                    "source_references": [
                        {"document_id": "doc-1", "page_number": 2, "citation": "texto literal"}
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    if '"plazos_clave"' in prompt:
        return {
            "plazos_clave": [
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
    if '"causales_rechazo"' in prompt:
        return {
            "causales_rechazo": [
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
    if '"requisitos_admisibilidad"' in prompt:
        return {
            "requisitos_admisibilidad": [
                {
                    "tipo": "documento",
                    "valor": "Certificado fiscal para contratar",
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
    if '"anexos_obligatorios"' in prompt:
        return {
            "anexos_obligatorios": [
                {
                    "tipo": "anexo",
                    "valor": "Anexo I - Formulario de oferta",
                    "confidence": 0.8,
                    "source_references": [
                        {"document_id": "doc-1", "page_number": 13, "citation": "texto literal"}
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    return {"criterios_evaluacion": []}


@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "analysis.extraction.extractors.base._call_llm",
        lambda messages, correlation_id: (
            _fake_llm_result(messages),
            {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        ),
    )


def test_graph_execution_all_success(mock_state: dict, mock_search: None, mock_llm: None) -> None:
    result = graph.invoke(mock_state)
    assert "extracted_data" in result
    assert len(result["extracted_data"]["plazos"]) > 0
    assert len(result["extracted_data"]["garantias"]) > 0
    assert "objeto_alcance" in result["extracted_data"]
    assert "anexos_obligatorios" in result["extracted_data"]


def test_extractor_retry_on_failure(mock_state: dict, mock_search: None, monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        content = '{"plazos_clave": []}'
        response_metadata = {"token_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}

    mock_client = Mock()
    mock_client.bind.return_value = mock_client
    mock_client.invoke.side_effect = [Exception("Timeout"), Response()]
    monkeypatch.setattr("analysis.extraction.extractors.base.get_azure_openai_client", lambda: mock_client)

    result = extractor_plazos(mock_state)
    assert mock_client.invoke.call_count == 2
    assert result["plazos_status"] in {"success", "not_found"}


def test_extractor_failure_continues(mock_state: dict, mock_search: None, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = Mock()
    mock_client.bind.return_value = mock_client
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
        "requisitos_admisibilidad": [],
        "criterios": [],
        "plazos_status": "success",
        "garantias_status": "success",
        "causales_status": "success",
        "requisitos_admisibilidad_status": "success",
        "criterios_status": "success",
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


def test_json_contract_allows_not_applicable_status() -> None:
    payload = {
        "plazos": [
            {
                "tipo": "mantenimiento de oferta",
                "fecha": None,
                "confidence": 0.85,
                "source_references": [
                    {
                        "document_id": "doc-1",
                        "page_number": 4,
                        "citation": "No se exige plazo de mantenimiento de oferta.",
                    }
                ],
                "extraction_status": "not_applicable",
            }
        ],
        "garantias": [],
        "causales_rechazo": [],
        "requisitos_admisibilidad": [],
        "criterios_evaluacion": [],
        "anexos_obligatorios": [],
        "estimacion_presupuesto": None,
    }

    validated = ExtractedData(**payload)
    assert validated.plazos[0].extraction_status == "not_applicable"


def test_merge_preserves_table_citation_header_and_row() -> None:
    state = {
        "analysis_id": "analysis-1",
        "correlation_id": "corr-1",
        "plazos": [
            {
                "tipo": "presentacion_ofertas",
                "fecha": "2024-05-15",
                "texto_original": "Fecha limite de presentacion de ofertas: 15/05/2024",
                "source_references": [
                    {
                        "document_id": "doc-1",
                        "page_number": 4,
                        "citation": "Encabezado: Fecha limite | Fila: Presentacion de ofertas | Valor: 15/05/2024",
                    }
                ],
                "extraction_status": "success",
                "confidence": 0.9,
            }
        ],
        "garantias": [],
        "causales": [],
        "requisitos_admisibilidad": [],
        "criterios": [],
        "plazos_status": "success",
        "garantias_status": "not_found",
        "causales_status": "not_found",
        "requisitos_admisibilidad_status": "not_found",
        "criterios_status": "not_found",
    }

    result = merge_node(state)
    citation = result["extracted_data"]["plazos"][0]["source_references"][0]["citation"]
    assert "Encabezado:" in citation
    assert "Fila:" in citation


def test_merge_exposes_ui_category_keys() -> None:
    state = {
        "analysis_id": "analysis-1",
        "correlation_id": "corr-1",
        "plazos": [],
        "garantias": [],
        "causales": [],
        "requisitos_admisibilidad": [
            {
                "tipo": "documento",
                "valor": "estatuto",
                "confidence": 0.8,
                "source_references": [{"document_id": "doc-1", "page_number": 2, "citation": "texto"}],
                "extraction_status": "success",
            }
        ],
        "criterios": [],
        "plazos_status": "not_found",
        "garantias_status": "not_found",
        "causales_status": "not_found",
        "requisitos_admisibilidad_status": "success",
        "criterios_status": "not_found",
    }

    result = merge_node(state)
    data = result["extracted_data"]

    assert "requisitos_admisibilidad" in data
    assert "plazos_clave" in data
    assert "datos_procedimiento" in data
    assert "objeto_alcance" in data
    assert "anexos_obligatorios" in data
    assert data["requisitos_admisibilidad_extraction_status"] == "success"


def test_individual_extractors(mock_state: dict, mock_search: None, mock_llm: None) -> None:
    assert extractor_objeto_alcance(dict(mock_state))["objeto_alcance_status"] in {"success", "not_found"}
    assert extractor_plazos(dict(mock_state))["plazos_status"] in {"success", "not_found"}
    assert extractor_garantias(dict(mock_state))["garantias_status"] in {"success", "not_found"}
    assert extractor_causales(dict(mock_state))["causales_status"] in {"success", "not_found"}
    assert extractor_anexos_obligatorios(dict(mock_state))["anexos_status"] in {"success", "not_found"}
    assert extractor_requisitos_admisibilidad(dict(mock_state))["requisitos_admisibilidad_status"] in {
        "success",
        "not_found",
    }
    assert extractor_criterios_evaluacion(dict(mock_state))["criterios_status"] in {"success", "not_found"}


def test_extractor_uses_query_from_glossary(
    mock_state: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_query = {"value": ""}

    def _fake_search_hybrid(*, query: str, analysis_id: str, top_k: int, section_key: str | None):
        captured_query["value"] = query
        return []

    monkeypatch.setattr("analysis.extraction.extractors.base.search_hybrid", _fake_search_hybrid)

    extractor_criterios_evaluacion(mock_state)
    assert "matriz de evaluacion" in captured_query["value"].lower()


def test_status_con_pipes_no_se_mapea_a_success() -> None:
    item = _normalize_item({"extraction_status": "success | partial | failed | not_found"})
    assert item["extraction_status"] != "success"


def test_confidence_invalida_se_deja_calcular_por_heuristica() -> None:
    item = _normalize_item({"extraction_status": "success", "confidence": 0.0})
    assert "confidence" not in item


def test_parser_tolera_texto_antes_del_json() -> None:
    parsed = _parse_json_response('Claro, aqui esta:\n```json\n{"plazos": []}\n```')
    assert parsed == {"plazos": []}


def test_todos_los_prompts_referenciados_existen_y_tienen_placeholders() -> None:
    base = Path("backend/analysis/extraction")
    extractor_files = [
        "objeto_alcance.py",
        "requisitos_admisibilidad.py",
        "garantias.py",
        "plazos.py",
        "criterios_evaluacion.py",
        "causales.py",
        "anexos_obligatorios.py",
    ]
    extractor_sources = "\n".join(
        (base / "extractors" / name).read_text(encoding="utf-8") for name in extractor_files
    )

    import re

    referenciados = set(re.findall(r'prompt_file_name="([^"]+)"', extractor_sources))

    for nombre in referenciados:
        archivo = base / "prompts" / nombre
        assert archivo.exists(), f"prompt referenciado inexistente: {nombre}"
        contenido = archivo.read_text(encoding="utf-8")
        assert "{chunks}" in contenido, f"{nombre} no tiene placeholder {{chunks}}"

    en_disco = {path.name for path in (base / "prompts").glob("*.txt")}
    assert en_disco == CANONICAL_PROMPT_FILES


def test_inventario_canonico_de_prompts_es_estricto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    for name in CANONICAL_PROMPT_FILES:
        (prompts_dir / name).write_text("{chunks}", encoding="utf-8")

    fake_base = tmp_path / "extractors"
    fake_base.mkdir(parents=True, exist_ok=True)
    fake_file = fake_base / "base.py"
    fake_file.write_text("# test", encoding="utf-8")

    monkeypatch.setattr("analysis.extraction.extractors.base.__file__", str(fake_file))

    validate_prompt_inventory()

    (prompts_dir / "legacy.txt").write_text("{chunks}", encoding="utf-8")
    with pytest.raises(ValueError, match="sobran prompts no permitidos"):
        validate_prompt_inventory()


def test_mapeo_categoria_prompt_canonico() -> None:
    validate_category_prompt_mapping("plazos_clave", "plazos_clave.txt")
    with pytest.raises(ValueError, match="debe usar"):
        validate_category_prompt_mapping("plazos_clave", "garantias.txt")
