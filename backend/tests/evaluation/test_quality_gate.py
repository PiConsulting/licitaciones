from __future__ import annotations

from evaluation.quality_gate import Thresholds, evaluate_quality_gate, resolve_thresholds


def _report(overall_5: float, overall_10: float, by_category: dict[str, tuple[float, float]] | None = None):
    cat_payload = by_category or {}
    return {
        "n_cases_total": 2,
        "n_cases_measured": 2,
        "n_cases_skipped": 0,
        "aggregate_with_boost": {
            5: {
                "overall_mean": overall_5,
                "by_category": {k: v[0] for k, v in cat_payload.items()},
            },
            10: {
                "overall_mean": overall_10,
                "by_category": {k: v[1] for k, v in cat_payload.items()},
            },
        },
        "skipped_cases": [],
    }


def test_resolve_thresholds_uses_baseline_defaults_when_not_provided() -> None:
    baseline = _report(overall_5=0.75, overall_10=0.8)
    thresholds = resolve_thresholds(baseline, min_recall_5=None, min_recall_10=None)
    assert thresholds.recall_at_5 == 0.75
    assert thresholds.recall_at_10 == 0.8


def test_gate_passes_without_regression() -> None:
    baseline = _report(overall_5=0.75, overall_10=0.8, by_category={"cronograma": (0.7, 0.75)})
    current = _report(overall_5=0.8, overall_10=0.85, by_category={"cronograma": (0.71, 0.76)})
    result = evaluate_quality_gate(
        baseline_report=baseline,
        current_report=current,
        thresholds=Thresholds(recall_at_5=0.74, recall_at_10=0.79),
        critical_categories=["cronograma"],
    )
    assert result["passed"] is True
    assert result["regressions"] == []


def test_gate_fails_when_overall_below_threshold() -> None:
    baseline = _report(overall_5=0.75, overall_10=0.8)
    current = _report(overall_5=0.72, overall_10=0.79)
    result = evaluate_quality_gate(
        baseline_report=baseline,
        current_report=current,
        thresholds=Thresholds(recall_at_5=0.74, recall_at_10=0.8),
        critical_categories=[],
    )
    assert result["passed"] is False
    assert len(result["regressions"]) == 2
    assert {r["metric"] for r in result["regressions"]} == {"recall@5", "recall@10"}


def test_gate_fails_when_critical_category_drops_against_baseline() -> None:
    baseline = _report(overall_5=0.75, overall_10=0.8, by_category={"riesgos": (0.8, 0.9)})
    current = _report(overall_5=0.8, overall_10=0.85, by_category={"riesgos": (0.79, 0.88)})
    result = evaluate_quality_gate(
        baseline_report=baseline,
        current_report=current,
        thresholds=Thresholds(recall_at_5=0.7, recall_at_10=0.75),
        critical_categories=["riesgos"],
    )
    assert result["passed"] is False
    assert any(r.get("scope") == "category" for r in result["regressions"])
