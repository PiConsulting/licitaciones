from __future__ import annotations

from evaluation.measure_recall import run
from evaluation.schemas import EvaluationCase, EvaluationDataset


def _dataset() -> EvaluationDataset:
    return EvaluationDataset(
        cases=[
            EvaluationCase(
                case_id="ok_case",
                analysis_id="a1",
                category="garantias",
                gold_chunk_ids=["g1"],
            ),
            EvaluationCase(
                case_id="missing_index_case",
                analysis_id="a2",
                category="preview_criterios",
                gold_chunk_ids=["g2"],
            ),
        ]
    )


def test_run_skips_cases_with_retrieval_error(monkeypatch):
    def fake_retrieve(case, _top_k, *, with_boost, category_boost=None, category_penalty=None):
        if case.case_id == "missing_index_case":
            raise RuntimeError("no tiene chunks indexados")
        return [{"id": "g1"}] if with_boost else [{"id": "x1"}]

    monkeypatch.setattr("evaluation.measure_recall._retrieve_chunks", fake_retrieve)

    report = run(_dataset(), [5, 10])

    assert report["n_cases_total"] == 2
    assert report["n_cases_measured"] == 1
    assert report["n_cases_skipped"] == 1
    assert report["per_case"][0]["case_id"] == "ok_case"
    assert report["skipped_cases"][0]["case_id"] == "missing_index_case"
    assert "no tiene chunks indexados" in report["skipped_cases"][0]["reason"]


def test_run_keeps_existing_recall_keys_when_skipping(monkeypatch):
    def fake_retrieve(case, _top_k, *, with_boost, category_boost=None, category_penalty=None):
        if case.case_id == "missing_index_case":
            raise RuntimeError("sin chunks")
        return [{"id": "g1"}]

    monkeypatch.setattr("evaluation.measure_recall._retrieve_chunks", fake_retrieve)

    report = run(_dataset(), [5])

    measured = report["per_case"][0]
    assert "recall_with_boost" in measured
    assert "recall_baseline" in measured
    assert measured["recall_with_boost"]["recall@5"] == 1.0
    assert measured["recall_baseline"]["recall@5"] == 1.0


def test_run_reports_precision_ndcg_and_mrr(monkeypatch):
    def fake_retrieve(_case, _top_k, *, with_boost, category_boost=None, category_penalty=None):
        return [{"id": "g1"}, {"id": "x1"}] if with_boost else [{"id": "x1"}, {"id": "g1"}]

    monkeypatch.setattr("evaluation.measure_recall._retrieve_chunks", fake_retrieve)

    dataset = EvaluationDataset(
        cases=[
            EvaluationCase(
                case_id="case_metrics",
                analysis_id="a1",
                category="garantias",
                gold_chunk_ids=["g1"],
            )
        ]
    )

    report = run(dataset, [1, 2])
    measured = report["per_case"][0]

    assert "precision_with_boost" in measured
    assert "precision_baseline" in measured
    assert "ndcg_with_boost" in measured
    assert "ndcg_baseline" in measured
    assert "mrr_with_boost" in measured
    assert "mrr_baseline" in measured
    assert "precision@1" in measured["precision_with_boost"]
    assert "ndcg@2" in measured["ndcg_baseline"]

    assert "aggregate_precision_with_boost" in report
    assert "aggregate_precision_baseline" in report
    assert "aggregate_ndcg_with_boost" in report
    assert "aggregate_ndcg_baseline" in report
    assert "aggregate_mrr_with_boost" in report
    assert "aggregate_mrr_baseline" in report


def test_run_reports_production_effective_recall(monkeypatch):
    """El recall efectivo debe reflejar top_k/relevance_min_* por categoría,
    no solo el retrieval crudo -- ver `_production_effective_ids`. Antes de
    esto, `top_k`/`relevance_min_ratio`/`relevance_min_chunks` en
    glossary.json no tenían NINGÚN efecto medible por este script."""

    def fake_retrieve(_case, _top_k, *, with_boost, category_boost=None, category_penalty=None):
        return [{"id": "g1"}, {"id": "x1"}] if with_boost else [{"id": "x1"}, {"id": "g1"}]

    monkeypatch.setattr("evaluation.measure_recall._retrieve_chunks", fake_retrieve)

    report = run(_dataset(), [5])
    measured = report["per_case"][0]

    assert "recall_production_effective" in measured
    assert "production_chunks_sent" in measured
    assert measured["recall_production_effective"] == 1.0
    assert measured["production_chunks_sent"] >= 1

    assert "aggregate_production_effective" in report
    assert "aggregate_production_chunks_sent" in report
