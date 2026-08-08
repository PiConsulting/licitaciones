from __future__ import annotations

import json
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
                    # Chroma no acepta listas en metadata: se serializa igual que
                    # table_ref, y chroma_search.py la deserializa de vuelta.
                    "heading_path": json.dumps(list(doc.get("heading_path") or []), ensure_ascii=True),
                    "heading_level": int(doc.get("heading_level", 0) or 0),
                    "section_path": str(doc.get("section_path", "general")),
                    "block_type": str(doc.get("block_type", "paragraph")),
                    # upload_chunks() ya serializó table_ref a JSON (o None); Chroma
                    # no acepta None en metadata, así que el "sin tabla" es "null".
                    "table_ref": doc.get("table_ref") or "null",
                }
            )

        collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=contents)
