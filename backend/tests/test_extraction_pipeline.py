from pathlib import Path
from uuid import uuid4

import pypdf

from analysis.models import Analysis
from documents.models import Document
from extraction.ai_search import upload_chunks
from extraction.chunking import create_chunks
from extraction.runner import extract_and_index
from shared.config import get_settings
from shared.database import SessionLocal
from users.models import User


def _create_pdf_with_blank_page(target: Path) -> None:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with target.open("wb") as handle:
        writer.write(handle)


def test_create_chunks_with_overlap() -> None:
    pages = [
        {
            "page_number": 1,
            "content": " ".join([f"token{i}" for i in range(1200)]),
        }
    ]

    chunks = create_chunks(pages, document_id="doc-1", correlation_id="corr-1", chunk_size=500, overlap=50)

    assert len(chunks) >= 3
    assert all(1 <= item["token_count"] <= 500 for item in chunks)

    first_tokens = chunks[0]["content"].split()
    second_tokens = chunks[1]["content"].split()
    assert set(first_tokens[-60:]) & set(second_tokens[:80])


def test_upload_chunks_local_writes_metadata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "true")
    monkeypatch.setenv("LOCAL_BLOB_STORAGE_PATH", str(tmp_path))
    get_settings.cache_clear()

    analysis_id = str(uuid4())
    correlation_id = str(uuid4())
    chunks = [
        {
            "document_id": "doc-1",
            "page_number": 1,
            "chunk_index": 0,
            "section_key": "general",
            "content": "contenido",
            "embedding": [0.1, 0.2],
        }
    ]

    upload_chunks(chunks, analysis_id=analysis_id, correlation_id=correlation_id)

    target_file = tmp_path / "analysis_index" / f"{analysis_id}.jsonl"
    assert target_file.exists()
    line = target_file.read_text(encoding="utf-8").strip()
    assert analysis_id in line
    assert '"section_key": "general"' in line


def test_extract_and_index_transitions_to_analyzing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "true")
    monkeypatch.setenv("LOCAL_BLOB_STORAGE_PATH", str(tmp_path))
    get_settings.cache_clear()

    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="queued", current_stage="queued", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()

    blob_name = f"{analysis.id}/doc.pdf"
    file_path = tmp_path / blob_name
    file_path.parent.mkdir(parents=True, exist_ok=True)
    _create_pdf_with_blank_page(file_path)

    document = Document(
        analysis_id=analysis.id,
        filename="doc.pdf",
        blob_name=blob_name,
        file_size_bytes=file_path.stat().st_size,
        page_count=1,
        is_primary=True,
        sha256_hash="a" * 64,
        content_hash="b" * 64,
        created_by=user.id,
    )
    db.add(document)
    db.commit()
    analysis_id = analysis.id
    db.close()

    monkeypatch.setattr(
        "extraction.runner.extract_text",
        lambda *_args, **_kwargs: [{"page_number": 1, "content": "contenido pagina"}],
    )
    monkeypatch.setattr(
        "extraction.runner.create_chunks",
        lambda *_args, **_kwargs: [
            {
                "document_id": "doc-1",
                "page_number": 1,
                "chunk_index": 0,
                "content": "contenido pagina",
                "token_count": 2,
                "section_key": "general",
            }
        ],
    )
    monkeypatch.setattr(
        "extraction.runner.generate_embeddings",
        lambda chunks, *_args, **_kwargs: [dict(chunk, embedding=[0.1, 0.2]) for chunk in chunks],
    )
    monkeypatch.setattr("extraction.runner.upload_chunks", lambda *_args, **_kwargs: None)

    extract_and_index(analysis_id)

    db = SessionLocal()
    updated = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    assert updated is not None
    assert updated.status == "analyzing"
    assert updated.current_stage == "Analizando contenido"
    db.close()


def test_extract_and_index_marks_error_on_unreadable_pdf(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "true")
    monkeypatch.setenv("LOCAL_BLOB_STORAGE_PATH", str(tmp_path))
    get_settings.cache_clear()

    db = SessionLocal()
    user = db.query(User).filter(User.email == "test@cedia.com").first()
    assert user is not None

    analysis = Analysis(created_by=user.id, status="queued", current_stage="queued", correlation_id=str(uuid4()))
    db.add(analysis)
    db.flush()

    document = Document(
        analysis_id=analysis.id,
        filename="ilegible.pdf",
        blob_name=f"{analysis.id}/ilegible.pdf",
        file_size_bytes=100,
        page_count=1,
        is_primary=True,
        sha256_hash="a" * 64,
        content_hash="b" * 64,
        created_by=user.id,
    )
    db.add(document)
    db.commit()
    analysis_id = analysis.id
    db.close()

    from extraction.errors import DocumentTextExtractionError

    monkeypatch.setattr(
        "extraction.runner.extract_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(DocumentTextExtractionError("fallo")),
    )

    extract_and_index(analysis_id)

    db = SessionLocal()
    updated = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    assert updated is not None
    assert updated.status == "error"
    assert "No se pudo leer el texto" in (updated.current_stage or "")
    db.close()
