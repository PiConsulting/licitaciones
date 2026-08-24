"""Tests de la lógica pura de Recall@K (sin credenciales de Azure)."""

from __future__ import annotations

import math

from evaluation.recall import AggregateRecall, recall_at_k
from evaluation.schemas import EvaluationCase, EvaluationDataset


def test_recall_at_k_perfect_match():
    gold = ["a", "b", "c"]
    retrieved = ["a", "b", "c", "d", "e"]
    hits, total = recall_at_k(gold, retrieved, k=5)
    assert hits == 3
    assert total == 3


def test_recall_at_k_partial_match_respects_k():
    gold = ["a", "b", "c"]
    # "c" solo aparece en la posición 4, fuera de top-3
    retrieved = ["x", "a", "b", "c"]
    hits, total = recall_at_k(gold, retrieved, k=3)
    assert hits == 2
    assert total == 3


def test_recall_at_k_no_gold_returns_zero_total():
    hits, total = recall_at_k([], ["a", "b"], k=5)
    assert hits == 0
    assert total == 0


def test_recall_at_k_no_matches():
    hits, total = recall_at_k(["a", "b"], ["x", "y", "z"], k=5)
    assert hits == 0
    assert total == 2


def test_aggregate_recall_overall_mean():
    agg = AggregateRecall(k=10)
    agg.add("garantias", 1.0)
    agg.add("garantias", 0.5)
    agg.add("plazos_clave", 0.0)

    means = agg.category_means()
    assert means["garantias"] == 0.75
    assert means["plazos_clave"] == 0.0
    assert math.isclose(agg.overall_mean(), (1.0 + 0.5 + 0.0) / 3)


def test_evaluation_case_dedups_gold_chunk_ids_preserving_order():
    case = EvaluationCase(
        case_id="c1",
        analysis_id="a1",
        category="garantias",
        gold_chunk_ids=["x", "y", "x", "z"],
    )
    assert case.gold_chunk_ids == ["x", "y", "z"]


def test_evaluation_dataset_filters_cases_with_gold():
    dataset = EvaluationDataset(
        cases=[
            EvaluationCase(case_id="c1", analysis_id="a1", category="garantias", gold_chunk_ids=["x"]),
            EvaluationCase(case_id="c2", analysis_id="a1", category="plazos_clave", gold_chunk_ids=[]),
        ]
    )
    with_gold = dataset.cases_with_gold()
    assert len(with_gold) == 1
    assert with_gold[0].case_id == "c1"


def test_evaluation_dataset_cases_for_category():
    dataset = EvaluationDataset(
        cases=[
            EvaluationCase(case_id="c1", analysis_id="a1", category="garantias", gold_chunk_ids=["x"]),
            EvaluationCase(case_id="c2", analysis_id="a1", category="plazos_clave", gold_chunk_ids=["y"]),
        ]
    )
    only_garantias = dataset.cases_for_category("garantias")
    assert [c.case_id for c in only_garantias] == ["c1"]
