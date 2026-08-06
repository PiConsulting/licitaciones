import json
from pathlib import Path
from uuid import uuid4

import fitz

from analysis.extraction.extractors.base import _format_chunks
from analysis.models import Analysis
from documents.models import Document
from extraction.ai_search import upload_chunks
from extraction.chunking import create_chunks
from extraction.document_intelligence import _serialize_table_rows
from extraction.runner import extract_and_index
from shared.config import get_settings
from shared.database import SessionLocal
from users.models import User


def _create_pdf_with_blank_page(target: Path) -> None:
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    try:
        doc.save(target)
    finally:
        doc.close()


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


def test_create_chunks_adds_unified_contract_fields_for_legacy_pages() -> None:
    pages = [{"page_number": 1, "content": "Capitulo I\nContenido general del pliego"}]

    chunks = create_chunks(pages, document_id="doc-legacy", correlation_id="corr-legacy", chunk_size=30, overlap=5)

    assert chunks
    chunk = chunks[0]
    assert chunk["section_key"] == "capitulos"
    assert "section_path" in chunk
    assert "section_level" in chunk
    assert chunk["block_type"] == "paragraph"
    assert chunk["table_ref"] is None


def test_create_chunks_keeps_table_rows_atomic() -> None:
    pages = [
        {
            "page_number": 1,
            "block_type": "paragraph",
            "role": "title",
            "content": "Pliego base",
            "source_order": 1,
            "table_ref": None,
        },
        {
            "page_number": 1,
            "block_type": "table",
            "role": "tableRow",
            "content": "Tabla T1 | Fila 1 | Criterio: Experiencia | Ponderacion: 40%",
            "source_order": 2,
            "table_ref": {"table_id": "T1", "row_index": 1, "headers": ["Criterio", "Ponderacion"]},
        },
        {
            "page_number": 1,
            "block_type": "table",
            "role": "tableRow",
            "content": "Tabla T1 | Fila 2 | Criterio: Precio | Ponderacion: 60%",
            "source_order": 3,
            "table_ref": {"table_id": "T1", "row_index": 2, "headers": ["Criterio", "Ponderacion"]},
        },
    ]

    chunks = create_chunks(pages, document_id="doc-table", correlation_id="corr-table", chunk_size=5, overlap=1)

    table_chunks = [chunk for chunk in chunks if chunk["block_type"] == "table"]
    assert len(table_chunks) == 2
    assert table_chunks[0]["table_ref"]["row_index"] == 1
    assert table_chunks[1]["table_ref"]["row_index"] == 2
    assert "Ponderacion: 40%" in table_chunks[0]["content"]
    assert "Ponderacion: 60%" in table_chunks[1]["content"]


def test_format_chunks_marks_table_context() -> None:
    formatted = _format_chunks(
        [
            {
                "document_id": "doc-1",
                "page_number": 3,
                "section_key": "criterios",
                "section_path": "Titulo > Criterios",
                "block_type": "table",
                "table_ref": {"table_id": "T2", "row_index": 4},
                "content": "Tabla T2 | Fila 4 | Criterio: Oferta economica | Ponderacion: 40%",
            }
        ]
    )

    assert "Tipo: TABLA" in formatted
    assert "Tabla: T2, Fila: 4" in formatted


class _FakeCell:
    def __init__(self, row_index: int, column_index: int, content: str, kind: str) -> None:
        self.row_index = row_index
        self.column_index = column_index
        self.content = content
        self.kind = kind


class _FakeTable:
    def __init__(self) -> None:
        self.row_count = 3
        self.column_count = 2
        self.cells = [
            _FakeCell(0, 0, "Criterio", "columnHeader"),
            _FakeCell(0, 1, "Ponderacion", "columnHeader"),
            _FakeCell(1, 0, "Experiencia", "content"),
            _FakeCell(1, 1, "40%", "content"),
            _FakeCell(2, 0, "Precio", "content"),
            _FakeCell(2, 1, "60%", "content"),
        ]
        self.bounding_regions = []
        self.spans = []


def test_serialize_table_rows_includes_headers_and_row_reference() -> None:
    rows = _serialize_table_rows(_FakeTable(), table_id="T1")

    assert len(rows) == 2
    assert rows[0]["table_ref"]["table_id"] == "T1"
    assert rows[0]["table_ref"]["row_index"] == 2
    assert "Criterio: Experiencia" in rows[0]["content"]
    assert "Ponderacion: 40%" in rows[0]["content"]


def test_upload_chunks_local_writes_metadata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "true")
    monkeypatch.setenv("LOCAL_BLOB_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("CHROMA_PERSIST_DIRECTORY", str(tmp_path / "chroma"))
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

    chroma_dir = tmp_path / "chroma"
    assert chroma_dir.exists()
    assert any(chroma_dir.rglob("*"))


def test_upload_chunks_local_serializes_table_ref_as_json_string(monkeypatch, tmp_path: Path) -> None:
    """table_ref debe llegar a Chroma como texto (Chroma no acepta dict ni None en
    metadata), y sin doble-serializar: upload_chunks() en extraction/ai_search.py
    ya lo convierte a JSON una sola vez antes de pasarlo al adaptador."""
    monkeypatch.setenv("USE_LOCAL_ADAPTERS", "true")
    monkeypatch.setenv("LOCAL_BLOB_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("CHROMA_PERSIST_DIRECTORY", str(tmp_path / "chroma"))
    get_settings.cache_clear()

    analysis_id = str(uuid4())
    chunks = [
        {
            "document_id": "doc-1",
            "page_number": 3,
            "chunk_index": 0,
            "section_key": "anexos",
            "section_path": "Anexo I",
            "section_level": 1,
            "block_type": "table",
            "table_ref": {"table_id": "T1", "row_index": 1, "headers": ["Cantidad"]},
            "content": "Tabla T1 | Fila 1 | Cantidad: 200",
            "embedding": [0.1, 0.2],
        },
        {
            "document_id": "doc-1",
            "page_number": 1,
            "chunk_index": 1,
            "section_key": "general",
            "content": "contenido sin tabla",
            "embedding": [0.3, 0.4],
        },
    ]

    upload_chunks(chunks, analysis_id=analysis_id, correlation_id=str(uuid4()))

    import chromadb

    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    collection = client.get_collection(name="analysis_chunks")
    stored = collection.get(
        ids=[f"{analysis_id}_doc-1_0", f"{analysis_id}_doc-1_1"],
        include=["metadatas"],
    )
    metadata_by_id = dict(zip(stored["ids"], stored["metadatas"], strict=True))

    table_metadata = metadata_by_id[f"{analysis_id}_doc-1_0"]
    assert table_metadata["block_type"] == "table"
    assert json.loads(table_metadata["table_ref"]) == {"table_id": "T1", "row_index": 1, "headers": ["Cantidad"]}

    plain_metadata = metadata_by_id[f"{analysis_id}_doc-1_1"]
    assert plain_metadata["table_ref"] == "null"


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
    monkeypatch.setattr(
        "extraction.runner.extract_categories",
        lambda db_session, analysis: (
            setattr(analysis, "status", "analyzed"),
            setattr(analysis, "current_stage", "completed"),
            db_session.commit(),
        ),
    )

    extract_and_index(analysis_id)

    db = SessionLocal()
    updated = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    assert updated is not None
    assert updated.status == "analyzed"
    assert updated.current_stage == "completed"
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
    assert "No se pudo leer el texto" in (updated.error_message or "")
    db.close()
