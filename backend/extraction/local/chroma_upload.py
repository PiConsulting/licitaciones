from __future__ import annotations

from pathlib import Path

from extraction.ports.search_client_port import SearchClientPort


class LocalChromaSearchAdapter(SearchClientPort):
    def __init__(self, persist_dir: str) -> None:
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)

    def upload_chunks(self, documents: list[dict]) -> None:
        if not documents:
            return

        import chromadb

        client = chromadb.PersistentClient(path=str(self._persist_dir))
        collection = client.get_or_create_collection(name="analysis_chunks")

        ids: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict] = []
        contents: list[str] = []

        for doc in documents:
            ids.append(doc["id"])
            embeddings.append(list(doc["embedding"]))
            contents.append(doc["content"])
            metadatas.append(
                {
                    "analysis_id": str(doc["analysis_id"]),
                    "document_id": str(doc["document_id"]),
                    "page_number": int(doc["page_number"]),
                    "chunk_index": int(doc["chunk_index"]),
                    "section_key": str(doc.get("section_key", "general")),
                    "section_path": str(doc.get("section_path", doc.get("section_key", "general"))),
                    "section_level": int(doc.get("section_level", 0) or 0),
                    "block_type": str(doc.get("block_type", "paragraph")),
                    # upload_chunks() ya serializó table_ref a JSON (o None); Chroma
                    # no acepta None en metadata, así que el "sin tabla" es "null".
                    "table_ref": doc.get("table_ref") or "null",
                    # Chroma no acepta None en metadata: "sin valor" es "" para estos.
                    "chapter": doc.get("chapter") or "",
                    "article": doc.get("article") or "",
                    "anexo": doc.get("anexo") or "",
                    "inciso": doc.get("inciso") or "",
                    "title": doc.get("title") or "",
                }
            )

        collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=contents)
