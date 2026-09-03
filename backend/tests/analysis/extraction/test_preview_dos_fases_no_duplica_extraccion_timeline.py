from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from analysis import routes as analysis_routes
from analysis.extraction.extractors import identificacion_procedimiento as identificacion_module
from analysis.extraction.extractors import objeto_alcance as objeto_module
from analysis.extraction.graph.nodes import extractor_nodes_phase2
from analysis.extraction.runner import extract_categories_phase1, extract_categories_phase2
from analysis.models import Analysis, AnalysisVersion
from infra.database import SessionLocal
from users.models import User


def test_flujo_dos_fases_no_duplicacion_objeto_identificacion_y_timeline_en_fase2(
    client: TestClient,
    auth_token: str,
    monkeypatch,
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="processing",
        current_stage="analyzing",
        progress_percentage=0,
        correlation_id=str(uuid4()),
    )
    db.add(analysis)
    db.commit()

    monkeypatch.setattr("analysis.extraction.runner.validate_prompt_inventory", lambda: None)

    invocation_counter = {"objeto": 0, "identificacion": 0}
    timeline_materialize_calls: list[dict] = []

    def _fake_run_extractor_objeto(**kwargs):
        invocation_counter["objeto"] += 1
        state = kwargs["state"]
        state[kwargs["state_field"]] = [
            {
                "tipo": "resumen_objeto",
                "valor": "Adquisicion de equipamiento",
                "confidence": 0.9,
                "source_references": [],
                "extraction_status": "success",
            }
        ]
        state[kwargs["status_field"]] = "success"
        return state

    def _fake_run_extractor_identificacion(**kwargs):
        invocation_counter["identificacion"] += 1
        state = kwargs["state"]
        state[kwargs["state_field"]] = [
            {
                "tipo": "organismo_convocante",
                "valor": "Ministerio de Salud",
                "confidence": 0.9,
                "source_references": [],
                "extraction_status": "success",
            }
        ]
        state[kwargs["status_field"]] = "success"
        return state

    monkeypatch.setattr(objeto_module, "run_extractor", _fake_run_extractor_objeto)
    monkeypatch.setattr(identificacion_module, "run_extractor", _fake_run_extractor_identificacion)

    phase2_result = {
        "extracted_data": {
            "requisitos_admisibilidad": [],
            "requisitos_admisibilidad_extraction_status": "not_found",
            "garantias": [],
            "garantias_extraction_status": "not_found",
            "plazos_clave": [],
            "plazos_clave_extraction_status": "not_found",
            "criterios_evaluacion": [],
            "criterios_evaluacion_extraction_status": "not_found",
            "causales_rechazo": [],
            "causales_rechazo_extraction_status": "not_found",
            "anexos_obligatorios": [],
            "anexos_obligatorios_extraction_status": "not_found",
            "riesgos": [],
            "riesgos_extraction_status": "not_found",
            "eventos_temporales": [
                {
                    "nombre": "Acto de apertura",
                    "fecha_explicita": "2026-12-12",
                    "origen_fecha": "explicita",
                }
            ],
            "eventos_temporales_extraction_status": "success",
            "plazos_relativos": [
                {
                    "descripcion": "Presentacion de oferta",
                    "cantidad": 10,
                    "unidad": "dias",
                    "tipo_dias": "habiles",
                    "evento_disparador": "Acto de apertura",
                    "direccion": "antes",
                    "es_plazo_maximo": False,
                }
            ],
            "plazos_relativos_extraction_status": "success",
            "calidad_por_categoria": {"eventos_temporales": {"valid_items": 1}},
        },
        "conflicts": [],
        "eventos_temporales": [
            {
                "nombre": "Acto de apertura",
                "fecha_explicita": "2026-12-12",
                "origen_fecha": "explicita",
            }
        ],
        "plazos_relativos": [
            {
                "descripcion": "Presentacion de oferta",
                "cantidad": 10,
                "unidad": "dias",
                "tipo_dias": "habiles",
                "evento_disparador": "Acto de apertura",
                "direccion": "antes",
                "es_plazo_maximo": False,
            }
        ],
        "extraction_metadata": {"token_usage": {}},
    }

    def _phase1_invoke(initial_state, **_kwargs):
        state = dict(initial_state)
        state["preview_criterios"] = [
            {
                "tipo": "forma_pago",
                "valor": "30 dias",
                "confidence": 0.85,
                "source_references": [],
                "extraction_status": "success",
            }
        ]
        state["preview_criterios_status"] = "success"

        state = objeto_module.extractor_objeto_alcance(state)
        state = identificacion_module.extractor_identificacion_procedimiento(state)

        return {
            "extracted_data": {
                "preview_criterios": state["preview_criterios"],
                "preview_criterios_extraction_status": state["preview_criterios_status"],
                "objeto_alcance": state["objeto_alcance"],
                "objeto_alcance_extraction_status": state["objeto_alcance_status"],
                "identificacion_procedimiento": state["identificacion"],
                "identificacion_procedimiento_extraction_status": state["identificacion_status"],
                "datos_procedimiento": state["identificacion"],
                "datos_procedimiento_extraction_status": state["identificacion_status"],
            },
            "conflicts": [],
            "extraction_metadata": {"token_usage": {}},
        }

    def _phase2_invoke(*_args, **_kwargs):
        return phase2_result

    monkeypatch.setattr(
        "analysis.extraction.runner.graph_phase1",
        type("_Graph", (), {"invoke": staticmethod(_phase1_invoke)}),
    )
    monkeypatch.setattr(
        "analysis.extraction.runner.graph_phase2",
        type("_Graph", (), {"invoke": staticmethod(_phase2_invoke)}),
    )

    class _TimelineResult:
        events_created = 1
        deadlines_created = 1
        skipped = []

    def _fake_materialize(_db, **kwargs):
        timeline_materialize_calls.append(kwargs)
        return _TimelineResult()

    monkeypatch.setattr("analysis.extraction.runner.materialize_timeline_from_extraction", _fake_materialize)

    assert "extract_objeto_alcance" not in extractor_nodes_phase2
    assert "extract_identificacion" not in extractor_nodes_phase2

    extract_categories_phase1(db, analysis, total_nodes=3)

    db.refresh(analysis)
    assert analysis.status == "en_revision"
    assert len(timeline_materialize_calls) == 0
    assert invocation_counter == {"objeto": 1, "identificacion": 1}

    phase1_version = (
        db.query(AnalysisVersion)
        .filter(AnalysisVersion.id == analysis.current_version_id)
        .first()
    )
    assert phase1_version is not None
    assert "preview_criterios" in phase1_version.extracted_data
    assert "objeto_alcance" in phase1_version.extracted_data
    assert "identificacion_procedimiento" in phase1_version.extracted_data
    assert "plazos_clave" not in phase1_version.extracted_data

    def _enqueue_and_run_phase2(_background_tasks, analysis_id: str) -> None:
        inner_db = SessionLocal()
        try:
            analysis_from_db = inner_db.query(Analysis).filter(Analysis.id == analysis_id).first()
            assert analysis_from_db is not None
            extract_categories_phase2(inner_db, analysis_from_db, total_nodes=8)
        finally:
            inner_db.close()

    monkeypatch.setattr(analysis_routes, "enqueue_analysis_categories", _enqueue_and_run_phase2)

    response = client.post(
        f"/api/v1/analyses/{analysis.id}/start-categories",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "queued"

    db.refresh(analysis)
    db.refresh(phase1_version)

    assert analysis.status == "analyzed"
    assert analysis.current_version_id == phase1_version.id
    assert invocation_counter == {"objeto": 1, "identificacion": 1}
    assert len(timeline_materialize_calls) == 1

    final_data = phase1_version.extracted_data
    expected_checklist_categories = {
        "objeto_alcance",
        "requisitos_admisibilidad",
        "garantias",
        "plazos_clave",
        "criterios_evaluacion",
        "causales_rechazo",
        "anexos_obligatorios",
        "riesgos",
    }
    assert expected_checklist_categories.issubset(set(final_data.keys()))
    assert "preview_criterios" in final_data
    assert "identificacion_procedimiento" in final_data

    db.close()
