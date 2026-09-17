# Tests para el agrupado/split de chunks del map-reduce por documento
# (analysis/extraction/engine/item_merging.py) — fix 2026-09-11, diagnóstico
# de no-determinismo en garantías (ver reanalyze-preview-bug-and-nondeterminism
# en memoria): los grupos deben quedar ordenados por posición real en el
# documento (no por score de relevancia), y un documento con muchos chunks
# debe poder partirse en varios llamados en vez de uno solo gigante.
from __future__ import annotations

from analysis.extraction.engine.item_merging import (
    _group_chunks_by_document,
    _split_oversized_groups,
)


def _chunk(document_id: str, chunk_index: int) -> dict:
    return {
        "document_id": document_id,
        "chunk_index": chunk_index,
        "content": f"contenido {document_id}#{chunk_index}",
    }


class TestGroupChunksByDocument:
    def test_reorders_by_chunk_index_not_by_arrival_order(self) -> None:
        # Llegan en orden de relevancia (score), no de posición en el pliego.
        chunks = [_chunk("doc-a", 20), _chunk("doc-a", 3), _chunk("doc-a", 11)]

        groups = _group_chunks_by_document(chunks)

        assert [c["chunk_index"] for c in groups["doc-a"]] == [3, 11, 20]

    def test_groups_are_independent_per_document(self) -> None:
        chunks = [_chunk("doc-a", 5), _chunk("doc-b", 1), _chunk("doc-a", 1)]

        groups = _group_chunks_by_document(chunks)

        assert set(groups.keys()) == {"doc-a", "doc-b"}
        assert [c["chunk_index"] for c in groups["doc-a"]] == [1, 5]
        assert [c["chunk_index"] for c in groups["doc-b"]] == [1]


class TestSplitOversizedGroups:
    def test_group_under_limit_stays_as_one_call(self) -> None:
        groups = {"doc-a": [_chunk("doc-a", i) for i in range(5)]}

        batches = _split_oversized_groups(groups, max_chunks_per_call=15)

        assert len(batches) == 1
        assert batches[0][0] == "doc-a"
        assert len(batches[0][1]) == 5

    def test_group_over_limit_splits_into_contiguous_batches(self) -> None:
        groups = {"doc-a": [_chunk("doc-a", i) for i in range(35)]}

        batches = _split_oversized_groups(groups, max_chunks_per_call=15)

        assert len(batches) == 3
        assert [document_id for document_id, _ in batches] == ["doc-a", "doc-a", "doc-a"]
        assert [c["chunk_index"] for c in batches[0][1]] == list(range(0, 15))
        assert [c["chunk_index"] for c in batches[1][1]] == list(range(15, 30))
        assert [c["chunk_index"] for c in batches[2][1]] == list(range(30, 35))

    def test_multiple_documents_split_independently(self) -> None:
        groups = {
            "doc-a": [_chunk("doc-a", i) for i in range(20)],
            "doc-b": [_chunk("doc-b", i) for i in range(3)],
        }

        batches = _split_oversized_groups(groups, max_chunks_per_call=15)

        by_doc: dict[str, list[list[int]]] = {}
        for document_id, group_chunks in batches:
            by_doc.setdefault(document_id, []).append([c["chunk_index"] for c in group_chunks])

        assert by_doc["doc-a"] == [list(range(0, 15)), list(range(15, 20))]
        assert by_doc["doc-b"] == [list(range(0, 3))]

    def test_max_chunks_zero_or_negative_disables_split(self) -> None:
        groups = {"doc-a": [_chunk("doc-a", i) for i in range(50)]}

        batches = _split_oversized_groups(groups, max_chunks_per_call=0)

        assert len(batches) == 1
        assert len(batches[0][1]) == 50
