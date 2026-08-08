from __future__ import annotations

import json
from pathlib import Path

from extraction.ports.search_client_port import SearchClientPort


class LocalJsonSearchAdapter(SearchClientPort):
    """No la usa ningún factory hoy (`ai_search._build_adapter` solo elige entre
    Azure y Chroma) — queda como implementación de referencia del puerto."""

    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir) / "analysis_index"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def upload_chunks(self, documents: list[dict]) -> None:
        if not documents:
            return

        analysis_id = documents[0]["analysis_id"]
        target = self._base_dir / f"{analysis_id}.jsonl"
        with target.open("w", encoding="utf-8") as handle:
            for doc in documents:
                handle.write(json.dumps(doc, ensure_ascii=True) + "\n")
