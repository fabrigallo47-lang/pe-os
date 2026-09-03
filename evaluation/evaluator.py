"""Evaluate one canonical prediction against one canonical gold case."""

from __future__ import annotations

from typing import Any, Mapping

from evaluation.metrics import score_metric
from evaluation.schema import SchemaValidationError, validate_prediction, validate_result


def evaluate_case(
    case: Mapping[str, Any],
    prediction: Mapping[str, Any] | None,
    *,
    run_id: str = "local",
    default_threshold: float = 0.8,
) -> dict[str, Any]:
    families = sorted({str(item["family"]) for item in case["inputs"]})
    threshold = float(case.get("acceptance", {}).get("min_score", default_threshold))
    base: dict[str, Any] = {
        "schema_version": "panta-eval.result/1.0",
        "run_id": run_id,
        "test_id": case["test_id"],
        "benchmark": case["benchmark"]["id"],
        "task": case["task"],
        "families": families,
        "weight": float(case.get("weight", 1.0)),
        "status": "evaluated",
        "passed": False,
        "score": 0.0,
        "scores": {},
        "native_scores": {},
        "threshold": threshold,
        "latency_ms": None,
        "cost": None,
        "errors": [],
        "warnings": [],
        "details": {},
    }
    if prediction is None:
        base["status"] = "missing_prediction"
        base["errors"].append("No prediction was supplied for this test case")
        validate_result(base)
        return base

    try:
        validate_prediction(prediction)
    except SchemaValidationError as exc:
        base["status"] = "invalid_prediction"
        base["errors"].extend(exc.errors)
        validate_result(base)
        return base
    if prediction["test_id"] != case["test_id"]:
        base["status"] = "invalid_prediction"
        base["errors"].append(
            f"Prediction test_id {prediction['test_id']!r} does not match {case['test_id']!r}"
        )
        validate_result(base)
        return base

    base["latency_ms"] = prediction.get("latency_ms")
    base["cost"] = prediction.get("cost")
    base["native_scores"] = dict(prediction.get("native_scores", {}))
    base["details"] = {
        "prediction_status": prediction["status"],
        "expected_status": case["gold"].get("expected_status", "success"),
    }

    scoring_metrics = list(case["metrics"])
    diagnostic_metrics = [
        name for name in case.get("diagnostic_metrics", []) if name not in scoring_metrics
    ]
    all_metrics = list(dict.fromkeys(scoring_metrics + diagnostic_metrics))
    base["details"].update({
        "evaluation_profile": case.get("evaluation_profile", "schema_strict"),
        "score_metrics": scoring_metrics,
        "diagnostic_metrics": diagnostic_metrics,
    })

    for metric_name in all_metrics:
        value = score_metric(metric_name, case, prediction)
        if value is None:
            if metric_name.startswith("native:"):
                native_name = metric_name.split(":", 1)[1]
                native = prediction.get("native_scores", {}).get(native_name)
                if native is not None:
                    value = float(native)
            if value is None:
                base["warnings"].append(
                    f"Metric {metric_name!r} requires an upstream evaluator or is not registered"
                )
                continue
        base["scores"][metric_name] = round(value, 6)

    required = case.get("acceptance", {}).get("required_metrics", [])
    missing_required = [name for name in required if name not in base["scores"]]
    if missing_required:
        base["errors"].append("Required metrics unavailable: " + ", ".join(missing_required))

    scoring_values = [base["scores"][name] for name in scoring_metrics if name in base["scores"]]
    if scoring_values:
        base["score"] = round(sum(scoring_values) / len(scoring_values), 6)
    expected_status = case["gold"].get("expected_status", "success")
    status_ok = prediction["status"] == expected_status
    latency_limit = case.get("acceptance", {}).get("max_latency_ms")
    latency_ok = latency_limit is None or (
        prediction.get("latency_ms") is not None and prediction["latency_ms"] <= latency_limit
    )
    base["passed"] = (
        not base["errors"] and status_ok and latency_ok and base["score"] >= threshold
    )
    if not status_ok:
        base["errors"].append(
            f"Expected status {expected_status!r}, received {prediction['status']!r}"
        )
    if not latency_ok:
        base["errors"].append(
            f"Latency {prediction.get('latency_ms')!r} exceeds {latency_limit} ms"
        )
    validate_result(base)
    return base
