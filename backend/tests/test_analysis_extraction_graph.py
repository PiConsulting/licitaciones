from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import Mock

import pytest

from analysis.extraction.extractors.anexos_obligatorios import extractor_anexos_obligatorios
from analysis.extraction.extractors.base import (
    CANONICAL_CATEGORY_PROMPT_MAP,
    CANONICAL_PROMPT_FILES,
    _normalize_item,
    _parse_json_response,
    _verify_citation_grounding,
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
            }
        ],
    )


def _resolve_root_key(prompt: str) -> str:
    """Identifica la categoria que se esta extrayendo por el marcador que el
    system prompt renderiza a partir de `{root_key}`.

    Buscar la clave suelta (`'"garantias"' in prompt`) no sirve: los prompts se
    nombran entre si para delimitar su alcance -- garantias.txt menciona
    "plazos_clave" dos veces -- asi que el mock resolvia la categoria
    equivocada, devolvia el payload de otra y la categoria real quedaba vacia.
    """
    for candidate in CANONICAL_CATEGORY_PROMPT_MAP:
        if '{"' + candidate + '": [], "_diagnostic"' in prompt:
            return candidate
    return ""


def _fake_llm_result(messages: list[tuple[str, str]]) -> dict:
    prompt = "\n".join(content for _role, content in messages)
    root_key = _resolve_root_key(prompt)
    if root_key == "objeto_alcance":
        return {
            "objeto_alcance": [
                {
                    "tipo": "resumen_objeto",
                    "valor": "Contratación de servicio de limpieza",
                    "confidence": 0.9,
                    "source_references": [
                        {
                            "document_id": "doc-1",
                            "page_number": 3,
                            "citation": "Las ofertas deben presentarse hasta el 15 de mayo de 2024.",
                        }
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    if root_key == "plazos_clave":
        return {
            "plazos_clave": [
                {
                    "tipo": "presentación ofertas",
                    "fecha": "2024-05-15",
                    "confidence": 0.95,
                    "source_references": [
                        {
                            "document_id": "doc-1",
                            "page_number": 3,
                            "citation": "Las ofertas deben presentarse hasta el 15 de mayo de 2024.",
                        }
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    if root_key == "garantias":
        return {
            "garantias": [
                {
                    "tipo": "garantía de oferta",
                    "monto_porcentaje": 1.0,
                    "confidence": 0.9,
                    "source_references": [
                        {
                            "document_id": "doc-1",
                            "page_number": 3,
                            "citation": "Las ofertas deben presentarse hasta el 15 de mayo de 2024.",
                        }
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    if root_key == "causales_rechazo":
        return {
            "causales_rechazo": [
                {
                    "tipo": "inhabilitante",
                    "valor": "falta de certificado",
                    "confidence": 0.8,
                    "source_references": [
                        {
                            "document_id": "doc-1",
                            "page_number": 3,
                            "citation": "Las ofertas deben presentarse hasta el 15 de mayo de 2024.",
                        }
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    if root_key == "requisitos_admisibilidad":
        return {
            "requisitos_admisibilidad": [
                {
                    "tipo": "documento",
                    "valor": "Certificado fiscal para contratar",
                    "confidence": 0.8,
                    "source_references": [
                        {
                            "document_id": "doc-1",
                            "page_number": 3,
                            "citation": "Las ofertas deben presentarse hasta el 15 de mayo de 2024.",
                        }
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    if root_key == "criterios_evaluacion":
        return {
            "criterios_evaluacion": [
                {
                    "tipo": "técnico",
                    "valor": "60%",
                    "confidence": 0.8,
                    "source_references": [
                        {
                            "document_id": "doc-1",
                            "page_number": 3,
                            "citation": "Las ofertas deben presentarse hasta el 15 de mayo de 2024.",
                        }
                    ],
                    "extraction_status": "success",
                }
            ]
        }
    if root_key == "anexos_obligatorios":
        return {
            "anexos_obligatorios": [
                {
                    "tipo": "anexo",
                    "valor": "Anexo I - Formulario de oferta",
                    "confidence": 0.8,
                    "source_references": [
                        {
                            "document_id": "doc-1",
                            "page_number": 3,
                            "citation": "Las ofertas deben presentarse hasta el 15 de mayo de 2024.",
                        }
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
                "source_references": [{"document_id": "doc-1", "page_number": 1, "citation": "Cita literal de la fuente A del pliego."}],
                "extraction_status": "success",
                "confidence": 0.8,
            },
            {
                "tipo": "presentación ofertas",
                "fecha": "2024-05-20",
                "source_references": [{"document_id": "doc-2", "page_number": 2, "citation": "Cita literal de la fuente B del pliego."}],
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


def test_merge_fusiona_plazos_duplicados_del_mismo_hecho() -> None:
    """Bug real reportado: 'mantenimiento de oferta' aparecía dos veces en
    Plazos Clave porque cada documento citaba el mismo plazo por separado y
    nunca se fusionaban en un solo ítem (solo se comparaban para detectar
    conflictos, nunca para deduplicar)."""
    state = {
        "analysis_id": "analysis-1",
        "correlation_id": "corr-1",
        "plazos": [
            {
                "tipo": "mantenimiento de la oferta",
                "fecha": None,
                "expresion_relativa": "30 días corridos desde la apertura",
                "texto_original": "El oferente deberá mantener su oferta por 30 días corridos desde la apertura.",
                "source_references": [{"document_id": "doc-1", "page_number": 4, "citation": "El oferente deberá mantener su oferta por 30 días corridos desde la apertura del procedimiento."}],
                "extraction_status": "success",
                "confidence": 0.8,
            },
            {
                "tipo": "garantía de mantenimiento de oferta",
                "fecha": None,
                "expresion_relativa": "30 días corridos desde la apertura",
                "texto_original": "El oferente deberá mantener su oferta por 30 días corridos desde la apertura.",
                "source_references": [{"document_id": "doc-2", "page_number": 7, "citation": "El oferente deberá mantener su oferta por 30 días corridos desde la apertura del procedimiento."}],
                "extraction_status": "success",
                "confidence": 0.75,
            },
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
    plazos = result["extracted_data"]["plazos_clave"]

    mantenimiento = [item for item in plazos if item["tipo"] == "mantenimiento_oferta"]
    assert len(mantenimiento) == 1
    assert len(mantenimiento[0]["source_references"]) == 2
    assert result["conflicts"] == []


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
                # El enum `TipoPlazo` es el contrato del schema. La forma con
                # espacios la produce el LLM y la canonicaliza merge_node; este
                # test valida el schema directo, asi que usa el valor canonico.
                "tipo": "mantenimiento_oferta",
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


def test_verify_citation_grounding_expands_short_verified_citation() -> None:
    items = [
        {
            "tipo": "expediente",
            "valor": "0100-EXP-2026",
            "confidence": 0.9,
            "source_references": [
                {
                    "document_id": "doc-1",
                    "page_number": 2,
                    "citation": "Expediente N 0100-EXP-2026.",
                }
            ],
            "extraction_status": "success",
        }
    ]
    chunks = [
        {
            "document_id": "doc-1",
            "page_number": 2,
            "block_type": "paragraph",
            "content": (
                "Organismo convocante: Municipalidad de Villa Nueva. "
                "Expediente N 0100-EXP-2026. Procedimiento N 05/2026. "
                "Tipo de procedimiento: Licitacion publica."
            ),
        }
    ]

    _verify_citation_grounding(items, chunks, category="identificacion_procedimiento", correlation_id="corr-1")

    citation = items[0]["source_references"][0]["citation"]
    assert len(citation) >= 40
    assert "Expediente N 0100-EXP-2026" in citation


def test_merge_node_maps_plazo_types_to_schema_contract() -> None:
    state = {
        "analysis_id": "analysis-1",
        "correlation_id": "corr-1",
        "plazos": [
            {
                "tipo": "apertura de ofertas",
                "fecha": "2026-09-15",
                "source_references": [
                    {
                        "document_id": "doc-1",
                        "page_number": 1,
                        "citation": "Apertura de ofertas: 15/09/2026 a las 11:00 hs en la Sala de Licitaciones del municipio.",
                    }
                ],
                "extraction_status": "success",
                "confidence": 0.8,
            },
            {
                "tipo": "plazo de entrega",
                "expresion_relativa": "90 dias corridos",
                "source_references": [
                    {
                        "document_id": "doc-1",
                        "page_number": 2,
                        "citation": "El plazo de entrega de los productos sera como maximo de noventa dias corridos a partir de la recepcion de la orden de provision.",
                    }
                ],
                "extraction_status": "success",
                "confidence": 0.8,
            },
        ],
        "garantias": [],
        "causales": [],
        "requisitos_admisibilidad": [],
        "criterios": [],
        "identificacion": [],
        "plazos_status": "success",
        "garantias_status": "not_found",
        "causales_status": "not_found",
        "requisitos_admisibilidad_status": "not_found",
        "criterios_status": "not_found",
        "identificacion_status": "not_found",
    }

    result = merge_node(state)
    tipos = [item["tipo"] for item in result["extracted_data"]["plazos_clave"]]
    assert "apertura_ofertas" in tipos
    assert "otro" in tipos


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
                "source_references": [{"document_id": "doc-1", "page_number": 2, "citation": "Texto literal tomado del pliego analizado."}],
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


def test_merge_populates_datos_procedimiento_desde_identificacion() -> None:
    """`datos_procedimiento` solía quedar hardcodeado en `[]` porque el
    extractor de identificación nunca estaba conectado al grafo (bug real: el
    organismo convocante nunca se mostraba ni en el listado ni en el detalle
    de un análisis)."""
    state = {
        "analysis_id": "analysis-1",
        "correlation_id": "corr-1",
        "plazos": [],
        "garantias": [],
        "causales": [],
        "requisitos_admisibilidad": [],
        "criterios": [],
        "identificacion": [
            {
                "tipo": "organismo_convocante",
                "valor": "Municipalidad de Villa Nueva",
                "confidence": 0.9,
                "source_references": [{"document_id": "doc-1", "page_number": 1, "citation": "Texto literal tomado del fragmento recuperado."}],
                "extraction_status": "success",
            }
        ],
        "identificacion_status": "success",
    }

    result = merge_node(state)
    data = result["extracted_data"]

    assert data["datos_procedimiento_extraction_status"] == "success"
    assert len(data["datos_procedimiento"]) == 1
    assert data["datos_procedimiento"][0]["tipo"] == "organismo_convocante"
    assert data["datos_procedimiento"][0]["valor"] == "Municipalidad de Villa Nueva"


def test_extract_identificacion_esta_conectado_al_grafo() -> None:
    assert "extract_identificacion" in graph.get_graph().nodes


def test_individual_extractors(mock_state: dict, mock_search: None, mock_llm: None) -> None:
    assert extractor_objeto_alcance(dict(mock_state))["objeto_alcance_status"] in {"success", "not_found", "partial"}
    assert extractor_plazos(dict(mock_state))["plazos_status"] in {"success", "not_found", "partial"}
    assert extractor_garantias(dict(mock_state))["garantias_status"] in {"success", "not_found", "partial"}
    assert extractor_causales(dict(mock_state))["causales_status"] in {"success", "not_found", "partial"}
    assert extractor_anexos_obligatorios(dict(mock_state))["anexos_status"] in {"success", "not_found", "partial"}
    assert extractor_requisitos_admisibilidad(dict(mock_state))["requisitos_admisibilidad_status"] in {
        "success",
        "not_found",
        "partial",
    }
    assert extractor_criterios_evaluacion(dict(mock_state))["criterios_status"] in {"success", "not_found", "partial"}


def test_extractor_usa_una_query_semantica_rica_sin_glosario(
    mock_state: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cada extractor manda una descripcion semantica rica del concepto
    que busca, mas keywords del glossary para BM25."""
    captured_query = {"value": ""}
    captured_keyword = {"value": ""}

    def _fake_search_hybrid(
        *,
        query: str,
        analysis_id: str,
        top_k: int,
        keyword_query: str | None = None,
        category_filter: str | None = None,
    ):
        captured_query["value"] = query
        captured_keyword["value"] = keyword_query or ""
        return []

    monkeypatch.setattr("analysis.extraction.extractors.base.search_hybrid", _fake_search_hybrid)

    extractor_criterios_evaluacion(mock_state)
    assert "puntaje ponderado" in captured_keyword["value"].lower()
    assert "criterios de evaluacion" in captured_keyword["value"].lower()


def test_status_con_pipes_no_se_mapea_a_success() -> None:
    item = _normalize_item({"extraction_status": "success | partial | failed | not_found"})
    assert item["extraction_status"] != "success"


def test_confidence_invalida_se_deja_calcular_por_heuristica() -> None:
    # confidence=0.0 ahora se acepta como valor valido (no se stripea)
    item = _normalize_item({"extraction_status": "success", "confidence": 0.0})
    assert item["confidence"] == 0.0
    # Pero confidence invalida (>1.0, negativa, string) si se stripea
    item2 = _normalize_item({"extraction_status": "success", "confidence": 1.5})
    assert "confidence" not in item2
    item3 = _normalize_item({"extraction_status": "success", "confidence": "invalid"})
    assert "confidence" not in item3


def test_parser_tolera_texto_antes_del_json() -> None:
    parsed = _parse_json_response('Claro, aqui esta:\n```json\n{"plazos": []}\n```')
    assert parsed == {"plazos": []}


def test_todos_los_prompts_referenciados_existen_y_tienen_placeholders() -> None:
    base = Path("analysis/extraction")
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


def test_esquema_de_cada_prompt_usa_result_key_como_raiz() -> None:
    """Bug real detectado: plazos_clave.txt y causales_rechazo.txt declaraban un
    ESQUEMA con clave raiz "plazos"/"causales" en vez de "plazos_clave"/
    "causales_rechazo". run_extractor lee `llm_result.get(result_key)`, asi que
    ese desacople hace que el payload nunca se encuentre y la categoria quede
    vacia SIEMPRE, en cualquier pliego. Este test evita que el desacople
    reaparezca sin que ningun otro test lo note (los tests con LLM mockeado no
    lo detectan porque el mock no valida el texto literal del prompt)."""
    base = Path("analysis/extraction/prompts")

    for category_key, prompt_file_name in CANONICAL_CATEGORY_PROMPT_MAP.items():
        contenido = (base / prompt_file_name).read_text(encoding="utf-8")
        clave_declarada = re.search(r'^\s*"([a-z_]+)":\s*\[', contenido, re.MULTILINE)
        assert clave_declarada is not None, f"{prompt_file_name} no declara una clave raiz de ESQUEMA reconocible"
        assert clave_declarada.group(1) == category_key, (
            f"{prompt_file_name} declara la clave raiz '{clave_declarada.group(1)}' "
            f"pero result_key es '{category_key}': el LLM va a responder con la clave "
            f"equivocada y la categoria va a quedar vacia siempre"
        )


def _dedup_base_state() -> dict:
    return {
        "analysis_id": "analysis-1",
        "correlation_id": "corr-1",
        "plazos": [],
        "garantias": [],
        "objeto_alcance": [],
        "requisitos_admisibilidad": [],
        "causales": [],
        "anexos": [],
        "criterios": [],
        "identificacion": [],
    }


def _anexo_item(valor: str, page_number: int, **overrides: object) -> dict:
    item = {
        "tipo": "anexo",
        "valor": valor,
        "confidence": 0.8,
        "source_references": [{"document_id": "doc-1", "page_number": page_number, "citation": "Cita literal tomada del pliego analizado."}],
        "extraction_status": "success",
    }
    item.update(overrides)
    return item


def test_dedup_anexos_fusiona_duplicado_exacto() -> None:
    state = _dedup_base_state()
    state["anexos"] = [_anexo_item("Anexo I — Planilla de Cotización", 3), _anexo_item("Anexo I — Planilla de Cotización", 7)]

    result = merge_node(state)
    anexos = result["extracted_data"]["anexos_obligatorios"]

    assert len(anexos) == 1
    refs = anexos[0]["source_references"]
    assert {ref["page_number"] for ref in refs} == {3, 7}


def test_dedup_anexos_fusiona_con_espaciado_y_mayusculas_distintas() -> None:
    state = _dedup_base_state()
    state["anexos"] = [_anexo_item("Anexo I — Planilla", 3), _anexo_item("anexo i —  planilla", 7)]

    result = merge_node(state)
    anexos = result["extracted_data"]["anexos_obligatorios"]

    assert len(anexos) == 1


def test_dedup_anexos_no_fusiona_hechos_distintos() -> None:
    state = _dedup_base_state()
    state["anexos"] = [
        _anexo_item("Anexo I — Planilla de Cotización", 3),
        _anexo_item("Anexo II — Declaración Jurada", 7),
    ]

    result = merge_node(state)
    anexos = result["extracted_data"]["anexos_obligatorios"]

    assert len(anexos) == 2


def test_merge_descarta_items_sin_fuentes_y_baja_categoria_a_partial() -> None:
    state = _dedup_base_state()
    state["objeto_alcance"] = [
        {
            "tipo": "objeto",
            "valor": "Adquisición de servidores de aplicaciones y base de datos.",
            "confidence": 0.9,
            "source_references": [],
            "extraction_status": "partial",
        }
    ]
    state["objeto_alcance_status"] = "success"

    result = merge_node(state)

    assert result["extracted_data"]["objeto_alcance"] == []
    assert result["extracted_data"]["objeto_alcance_extraction_status"] == "partial"


def test_dedup_causales_sin_campo_tipo_util_no_fusiona_hechos_distintos() -> None:
    state = _dedup_base_state()
    state["causales"] = [
        {
            "tipo": "causal_rechazo",
            "valor": "No presentar la garantía de mantenimiento de oferta.",
            "confidence": 0.9,
            "source_references": [{"document_id": "doc-1", "page_number": 4, "citation": "Cita literal tomada del pliego analizado."}],
            "extraction_status": "success",
        },
        {
            "tipo": "causal_rechazo",
            "valor": "Presentar la oferta fuera del plazo establecido.",
            "confidence": 0.9,
            "source_references": [{"document_id": "doc-1", "page_number": 5, "citation": "Cita literal tomada del pliego analizado."}],
            "extraction_status": "success",
        },
    ]

    result = merge_node(state)
    causales = result["extracted_data"]["causales_rechazo"]

    assert len(causales) == 2


def test_dedup_causales_mismo_tipo_y_valor_se_fusiona() -> None:
    state = _dedup_base_state()
    state["causales"] = [
        {
            "tipo": "causal_rechazo",
            "valor": "No presentar la garantía de mantenimiento de oferta.",
            "confidence": 0.9,
            "source_references": [{"document_id": "doc-1", "page_number": 4, "citation": "Cita literal tomada del pliego analizado."}],
            "extraction_status": "success",
        },
        {
            "tipo": "causal_rechazo",
            "valor": "no presentar la garantía de mantenimiento de oferta.",
            "confidence": 0.85,
            "source_references": [{"document_id": "doc-1", "page_number": 9, "citation": "Cita literal tomada del pliego analizado."}],
            "extraction_status": "success",
        },
    ]

    result = merge_node(state)
    causales = result["extracted_data"]["causales_rechazo"]

    assert len(causales) == 1


def test_dedup_no_cambia_comportamiento_de_plazos_y_garantias() -> None:
    state = _dedup_base_state()
    state["plazos"] = [
        {
            "tipo": "presentación ofertas",
            "fecha": "2024-05-15",
            "confidence": 0.9,
            "source_references": [{"document_id": "doc-1", "page_number": 1, "citation": "Cita literal de la fuente A del pliego."}],
            "extraction_status": "success",
        },
        {
            "tipo": "presentación de ofertas",
            "fecha": "2024-05-15",
            "confidence": 0.8,
            "source_references": [{"document_id": "doc-2", "page_number": 2, "citation": "Cita literal de la fuente B del pliego."}],
            "extraction_status": "success",
        },
    ]
    state["garantias"] = [
        {
            "tipo": "garantía de oferta",
            "monto_porcentaje": 1.0,
            "monto_valor": None,
            "confidence": 0.9,
            "source_references": [{"document_id": "doc-1", "page_number": 5, "citation": "Cita literal de la fuente A del pliego."}],
            "extraction_status": "success",
        },
        {
            "tipo": "mantenimiento de oferta",
            "monto_porcentaje": 1.0,
            "monto_valor": None,
            "confidence": 0.85,
            "source_references": [{"document_id": "doc-1", "page_number": 6, "citation": "Cita literal de la fuente B del pliego."}],
            "extraction_status": "success",
        },
    ]

    result = merge_node(state)

    assert len(result["extracted_data"]["plazos_clave"]) == 1
    assert len(result["extracted_data"]["garantias"]) == 1
