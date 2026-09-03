from __future__ import annotations

from uuid import uuid4

from analysis.extraction.runner import extract_categories_phase1
from analysis.models import Analysis, AnalysisVersion
from infra.database import SessionLocal
from users.models import User


def test_extract_categories_phase1_persists_only_preview_objeto_identificacion(monkeypatch) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="processing",
        current_stage="analyzing",
        progress_percentage=30,
        correlation_id=str(uuid4()),
    )
    db.add(analysis)
    db.commit()

    monkeypatch.setattr("analysis.extraction.runner.validate_prompt_inventory", lambda: None)

    phase1_result = {
        "extracted_data": {
            "preview_criterios": [{"tipo": "forma_pago", "valor": "contado"}],
            "preview_criterios_extraction_status": "success",
            "preview_criterios_narrative": {
                "summary": "Pago contado",
                "confidence": 0.8,
                "blocks": [{"type": "paragraph", "text": "Pago contado"}],
                "evidences": [],
            },
            "objeto_alcance": [{"tipo": "resumen_objeto", "valor": "Compra"}],
            "objeto_alcance_extraction_status": "success",
            "objeto_alcance_narrative": {
                "summary": "Compra de bienes",
                "confidence": 0.85,
                "blocks": [{"type": "paragraph", "text": "Compra de bienes"}],
                "evidences": [],
            },
            "identificacion_procedimiento": [{"tipo": "expediente", "valor": "EX-2026-1"}],
            "identificacion_procedimiento_extraction_status": "success",
            "identificacion_procedimiento_narrative": {
                "summary": "Expediente identificado",
                "confidence": 0.9,
                "blocks": [{"type": "paragraph", "text": "Expediente EX-2026-1"}],
                "evidences": [],
            },
            "datos_procedimiento": [
                {"tipo": "expediente", "valor": "EX-2026-1", "confidence": 0.9}
            ],
            "datos_procedimiento_extraction_status": "success",
            "plazos_clave": [{"referencia": "No deberia persistirse en fase1"}],
        },
        "conflicts": [],
        "extraction_metadata": {"token_usage": {}},
    }
    monkeypatch.setattr(
        "analysis.extraction.runner.graph_phase1",
        type("_Graph", (), {"invoke": staticmethod(lambda *_args, **_kwargs: phase1_result)}),
    )

    extract_categories_phase1(db, analysis, total_nodes=3)

    db.refresh(analysis)
    stored_version = (
        db.query(AnalysisVersion)
        .filter(AnalysisVersion.id == analysis.current_version_id)
        .first()
    )
    assert stored_version is not None

    assert analysis.status == "en_revision"
    assert "preview_criterios" in stored_version.extracted_data
    assert "preview_criterios_narrative" in stored_version.extracted_data
    assert "objeto_alcance" in stored_version.extracted_data
    assert "objeto_alcance_narrative" in stored_version.extracted_data
    assert "identificacion_procedimiento" in stored_version.extracted_data
    assert "identificacion_procedimiento_narrative" in stored_version.extracted_data
    assert "datos_procedimiento" in stored_version.extracted_data
    assert "plazos_clave" not in stored_version.extracted_data
    assert "preview_data" not in stored_version.extracted_data

    db.close()
