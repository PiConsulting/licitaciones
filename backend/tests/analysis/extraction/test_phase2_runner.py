from __future__ import annotations

import pytest
from uuid import uuid4

from analysis.extraction.runner import extract_categories_phase2
from analysis.models import Analysis, AnalysisVersion
from documents.models import Document
from infra.database import SessionLocal
from users.models import User


def test_extract_categories_phase2_updates_same_version_and_materializes_timeline(
    monkeypatch,
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="en_revision",
        current_stage="completed",
        progress_percentage=100,
        correlation_id=str(uuid4()),
    )
    db.add(analysis)
    db.flush()

    version = AnalysisVersion(
        analysis_id=analysis.id,
        version_number=1,
        extracted_data={
            "preview_criterios": [{"tipo": "forma_pago", "valor": "30 dias"}],
            "objeto_alcance": [{"tipo": "resumen_objeto", "valor": "Compra de insumos"}],
            "identificacion_procedimiento": [
                {"tipo": "organismo_convocante", "valor": "Municipalidad"}
            ],
        },
        conflicts=[],
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    analysis.current_version_id = version.id
    db.commit()

    monkeypatch.setattr("analysis.extraction.runner.validate_prompt_inventory", lambda: None)

    phase2_result = {
        "extracted_data": {
            "requisitos_admisibilidad": [
                {
                    "item": "Inscripcion en registro",
                    "descripcion": "Acreditar inscripcion vigente",
                    "aplica_a": ["oferente"],
                    "source_references": [
                        {
                            "document_id": "doc-1",
                            "page_number": 2,
                            "citation": "El oferente debera acreditar inscripcion vigente",
                        }
                    ],
                    "confidence": 0.86,
                }
            ],
            "requisitos_admisibilidad_extraction_status": "success",
            "requisitos_admisibilidad_narrative": {
                "summary": "Acreditar requisitos",
                "confidence": 0.84,
                "blocks": [{"type": "paragraph", "text": "Acreditar requisitos"}],
                "evidences": [],
            },
            "plazos_clave": [
                {
                    "referencia": "Entrega",
                    "fecha": "2026-12-01",
                    "texto_original": "Entrega en 30 dias",
                    "confidence": 0.8,
                    "source_references": [
                        {
                            "document_id": "doc-1",
                            "page_number": 1,
                            "citation": "Entrega en 30 dias corridos desde adjudicacion",
                        }
                    ],
                    "extraction_status": "success",
                }
            ],
            "plazos_clave_extraction_status": "success",
            "plazos_clave_narrative": {
                "summary": "Plazo de entrega",
                "confidence": 0.82,
                "blocks": [{"type": "paragraph", "text": "Entrega en 30 dias"}],
                "evidences": [],
            },
            "eventos_temporales": [{"nombre": "Adjudicacion"}],
            "eventos_temporales_extraction_status": "success",
            "plazos_relativos": [{"descripcion": "Entrega", "evento_disparador": "Adjudicacion"}],
            "plazos_relativos_extraction_status": "success",
            "calidad_por_categoria": {"plazos_clave": {"valid_items": 1}},
        },
        "conflicts": [],
        "eventos_temporales": [{"nombre": "Adjudicacion"}],
        "plazos_relativos": [{"descripcion": "Entrega", "evento_disparador": "Adjudicacion"}],
        "extraction_metadata": {"token_usage": {}},
    }
    monkeypatch.setattr(
        "analysis.extraction.runner.graph_phase2",
        type("_Graph", (), {"invoke": staticmethod(lambda *_args, **_kwargs: phase2_result)}),
    )

    captured_materializer_call: dict = {}

    class _Result:
        events_created = 1
        deadlines_created = 1
        skipped = []

    def _fake_materialize(_db, **kwargs):
        captured_materializer_call.update(kwargs)
        return _Result()

    monkeypatch.setattr(
        "analysis.extraction.runner.materialize_timeline_from_extraction",
        _fake_materialize,
    )

    extract_categories_phase2(db, analysis, total_nodes=8)

    db.refresh(analysis)
    db.refresh(version)

    assert analysis.status == "analyzed"
    assert analysis.current_version_id == version.id
    assert version.version_number == 1
    assert version.extracted_data["objeto_alcance"][0]["valor"] == "Compra de insumos"
    assert "plazos_clave_extraction_status" not in version.extracted_data
    assert "plazos_clave_narrative" not in version.extracted_data
    assert "requisitos_admisibilidad_extraction_status" not in version.extracted_data
    assert "requisitos_admisibilidad" not in version.extracted_data
    assert "requisitos_admisibilidad_narrative" not in version.extracted_data

    assert captured_materializer_call["eventos_temporales"] == phase2_result["eventos_temporales"]
    assert captured_materializer_call["plazos_relativos"] == phase2_result["plazos_relativos"]

    db.close()


def test_extract_categories_phase2_fails_fast_without_phase1_version(monkeypatch) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="en_revision",
        current_stage="completed",
        progress_percentage=100,
        correlation_id=str(uuid4()),
    )
    db.add(analysis)
    db.commit()

    monkeypatch.setattr("analysis.extraction.runner.validate_prompt_inventory", lambda: None)

    with pytest.raises(RuntimeError, match="AnalysisVersion de fase 1"):
        extract_categories_phase2(db, analysis, total_nodes=8)

    db.refresh(analysis)
    assert analysis.progress_percentage == 100
    assert analysis.current_stage == "completed"
    assert analysis.status == "en_revision"
    db.close()


def test_extract_categories_phase2_materializes_from_extracted_data_when_top_level_absent(
    monkeypatch,
) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="en_revision",
        current_stage="completed",
        progress_percentage=100,
        correlation_id=str(uuid4()),
    )
    db.add(analysis)
    db.flush()

    version = AnalysisVersion(
        analysis_id=analysis.id,
        version_number=1,
        extracted_data={"preview_criterios": []},
        conflicts=[],
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    analysis.current_version_id = version.id
    db.commit()

    monkeypatch.setattr("analysis.extraction.runner.validate_prompt_inventory", lambda: None)

    phase2_result = {
        "extracted_data": {
            "eventos_temporales": [{"nombre": "Apertura de Cotizaciones"}],
            "eventos_temporales_extraction_status": "success",
            "plazos_relativos": [
                {
                    "descripcion": "Mantenimiento de la Oferta",
                    "evento_disparador": "Apertura de Cotizaciones",
                    "cantidad": 40,
                    "unidad": "días",
                    "tipo_dias": "hábiles",
                    "direccion": "desde",
                }
            ],
            "plazos_relativos_extraction_status": "success",
            "calidad_por_categoria": {},
        },
        "conflicts": [],
        # Regresión real: estos campos no siempre vienen top-level.
        "extraction_metadata": {"token_usage": {}},
    }
    monkeypatch.setattr(
        "analysis.extraction.runner.graph_phase2",
        type("_Graph", (), {"invoke": staticmethod(lambda *_args, **_kwargs: phase2_result)}),
    )

    captured_materializer_call: dict = {}

    class _Result:
        events_created = 1
        deadlines_created = 1
        skipped = []

    def _fake_materialize(_db, **kwargs):
        captured_materializer_call.update(kwargs)
        return _Result()

    monkeypatch.setattr(
        "analysis.extraction.runner.materialize_timeline_from_extraction",
        _fake_materialize,
    )

    extract_categories_phase2(db, analysis, total_nodes=8)

    assert captured_materializer_call["eventos_temporales"] == phase2_result["extracted_data"][
        "eventos_temporales"
    ]
    assert captured_materializer_call["plazos_relativos"] == phase2_result["extracted_data"][
        "plazos_relativos"
    ]

    db.close()


def test_extract_categories_phase2_reuses_setup_cache_in_initial_state(monkeypatch) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="en_revision",
        current_stage="completed",
        progress_percentage=100,
        correlation_id=str(uuid4()),
    )
    db.add(analysis)
    db.flush()

    doc = Document(
        analysis_id=analysis.id,
        filename="pliego.pdf",
        blob_name="blob/pliego.pdf",
        file_size_bytes=1,
        page_count=1,
        sha256_hash="abc",
        extraction_status="completed",
        created_by=user.id,
    )
    db.add(doc)
    db.flush()

    version = AnalysisVersion(
        analysis_id=analysis.id,
        version_number=1,
        extracted_data={"preview_criterios": []},
        conflicts=[],
        created_by=user.id,
    )
    db.add(version)
    db.flush()

    analysis.current_version_id = version.id
    analysis.extraction_metadata = {
        "setup_cache": {
            "analysis_id": analysis.id,
            "document_ids": [doc.id],
            "document_id_to_blob_path": {doc.id: "blob/pliego.pdf"},
            "document_labels": {doc.id: {"filename": "pliego.pdf", "is_primary": True}},
            "global_candidates": [{"id": "chunk-1", "content": "texto"}],
        }
    }
    db.commit()

    monkeypatch.setattr("analysis.extraction.runner.validate_prompt_inventory", lambda: None)

    captured: dict = {}

    def _phase2_invoke(initial_state, **_kwargs):
        captured.update(initial_state)
        return {
            "extracted_data": {
                "eventos_temporales": [],
                "plazos_relativos": [],
                "calidad_por_categoria": {},
            },
            "conflicts": [],
            "extraction_metadata": {"token_usage": {}},
        }

    monkeypatch.setattr(
        "analysis.extraction.runner.graph_phase2",
        type("_Graph", (), {"invoke": staticmethod(_phase2_invoke)}),
    )
    monkeypatch.setattr(
        "analysis.extraction.runner.materialize_timeline_from_extraction",
        lambda _db, **_kwargs: type("_R", (), {"events_created": 0, "deadlines_created": 0, "skipped": []})(),
    )

    extract_categories_phase2(db, analysis, total_nodes=4)

    assert captured.get("document_id_to_blob_path") == {doc.id: "blob/pliego.pdf"}
    assert captured.get("document_labels", {}).get(doc.id, {}).get("filename") == "pliego.pdf"
    assert captured.get("global_candidates") == [{"id": "chunk-1", "content": "texto"}]
    db.close()


def test_extract_categories_phase2_invalidates_setup_cache_when_document_set_changes(monkeypatch) -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(
        created_by=user.id,
        status="en_revision",
        current_stage="completed",
        progress_percentage=100,
        correlation_id=str(uuid4()),
    )
    db.add(analysis)
    db.flush()

    doc = Document(
        analysis_id=analysis.id,
        filename="pliego.pdf",
        blob_name="blob/pliego.pdf",
        file_size_bytes=1,
        page_count=1,
        sha256_hash="def",
        extraction_status="completed",
        created_by=user.id,
    )
    db.add(doc)
    db.flush()

    version = AnalysisVersion(
        analysis_id=analysis.id,
        version_number=1,
        extracted_data={"preview_criterios": []},
        conflicts=[],
        created_by=user.id,
    )
    db.add(version)
    db.flush()

    analysis.current_version_id = version.id
    analysis.extraction_metadata = {
        "setup_cache": {
            "analysis_id": analysis.id,
            "document_ids": ["otro-documento"],
            "document_id_to_blob_path": {"otro-documento": "blob/otro.pdf"},
            "document_labels": {"otro-documento": {"filename": "otro.pdf", "is_primary": True}},
            "global_candidates": [{"id": "chunk-legacy"}],
        }
    }
    db.commit()

    monkeypatch.setattr("analysis.extraction.runner.validate_prompt_inventory", lambda: None)

    captured: dict = {}

    def _phase2_invoke(initial_state, **_kwargs):
        captured.update(initial_state)
        return {
            "extracted_data": {
                "eventos_temporales": [],
                "plazos_relativos": [],
                "calidad_por_categoria": {},
            },
            "conflicts": [],
            "extraction_metadata": {"token_usage": {}},
        }

    monkeypatch.setattr(
        "analysis.extraction.runner.graph_phase2",
        type("_Graph", (), {"invoke": staticmethod(_phase2_invoke)}),
    )
    monkeypatch.setattr(
        "analysis.extraction.runner.materialize_timeline_from_extraction",
        lambda _db, **_kwargs: type("_R", (), {"events_created": 0, "deadlines_created": 0, "skipped": []})(),
    )

    extract_categories_phase2(db, analysis, total_nodes=4)

    assert "document_id_to_blob_path" not in captured
    assert "document_labels" not in captured
    assert "global_candidates" not in captured
    db.close()
