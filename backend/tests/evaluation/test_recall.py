"""Tests de la lógica pura de Recall@K (sin credenciales de Azure)."""

from __future__ import annotations

import math

from evaluation.recall import AggregateRecall, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank
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


def test_precision_at_k_perfect_match():
    hits, total = precision_at_k(["a", "b"], ["a", "b", "x"], k=2)
    assert hits == 2
    assert total == 2


def test_precision_at_k_partial_match_respects_k():
    hits, total = precision_at_k(["a", "b", "c"], ["x", "a", "y", "b"], k=3)
    assert hits == 1
    assert total == 3


def test_precision_at_k_empty_retrieved_returns_zero_total():
    hits, total = precision_at_k(["a"], [], k=5)
    assert hits == 0
    assert total == 0


def test_reciprocal_rank_first_hit_position():
    rr = reciprocal_rank(["z"], ["a", "b", "z", "c"])
    assert math.isclose(rr, 1 / 3)


def test_reciprocal_rank_no_hit_returns_zero():
    rr = reciprocal_rank(["z"], ["a", "b", "c"])
    assert rr == 0.0


def test_ndcg_at_k_perfect_is_one():
    ndcg = ndcg_at_k(["a", "b"], ["a", "b", "x"], k=2)
    assert math.isclose(ndcg, 1.0)


def test_ndcg_at_k_partial_between_zero_and_one():
    ndcg = ndcg_at_k(["a", "b"], ["x", "a", "b"], k=2)
    assert 0.0 < ndcg < 1.0


def test_ndcg_at_k_no_gold_is_nan():
    assert math.isnan(ndcg_at_k([], ["a", "b"], k=2))
