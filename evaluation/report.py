"""Aggregate and render deterministic evaluation reports."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping


def _aggregate(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = list(rows)
    total = len(records)
    passed = sum(bool(record["passed"]) for record in records)
    total_weight = sum(float(record.get("weight", 1.0)) for record in records)
    passed_weight = sum(
        float(record.get("weight", 1.0)) for record in records if record["passed"]
    )
    return {
        "tests": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 6) if total else 0.0,
        "weight": round(total_weight, 6),
        "weighted_pass_rate": round(passed_weight / total_weight, 6) if total_weight else 0.0,
        "mean_score": round(
            sum(
                float(record["score"]) * float(record.get("weight", 1.0))
                for record in records
            ) / total_weight,
            6,
        ) if total_weight else 0.0,
    }


def build_summary(results: list[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, list[Mapping[str, Any]]]] = {
        "benchmark": defaultdict(list),
        "task": defaultdict(list),
        "family": defaultdict(list),
    }
    metric_values: dict[str, list[float]] = defaultdict(list)
    for result in results:
        groups["benchmark"][str(result["benchmark"])].append(result)
        groups["task"][str(result["task"])].append(result)
        for family in result["families"]:
            groups["family"][str(family)].append(result)
        for name, value in result.get("scores", {}).items():
            metric_values[name].append(float(value))
    return {
        "overall": _aggregate(results),
        "by_benchmark": {name: _aggregate(rows) for name, rows in sorted(groups["benchmark"].items())},
        "by_task": {name: _aggregate(rows) for name, rows in sorted(groups["task"].items())},
        "by_family": {name: _aggregate(rows) for name, rows in sorted(groups["family"].items())},
        "metrics": {
            name: {"tests": len(values), "mean": round(sum(values) / len(values), 6)}
            for name, values in sorted(metric_values.items())
        },
        "failures": [
            {"test_id": result["test_id"], "score": result["score"],
             "status": result["status"], "errors": result["errors"]}
            for result in results if not result["passed"]
        ],
    }


def render_markdown(run: Mapping[str, Any]) -> str:
    summary = run["summary"]
    overall = summary["overall"]
    lines = [
        "# PANTA Multimodal Evaluation Report",
        "",
        f"Run: `{run['run_id']}`  ",
        f"Cases: **{overall['tests']}** · Passed: **{overall['passed']}** · "
        f"Pass rate: **{overall['pass_rate']:.1%}** · Mean score: **{overall['mean_score']:.1%}**",
        "",
    ]
    for title, key in (("By family", "by_family"), ("By task", "by_task"),
                       ("By benchmark", "by_benchmark")):
        lines += [f"## {title}", "", "| Group | Tests | Passed | Pass rate | Mean score |",
                  "|---|---:|---:|---:|---:|"]
        for name, values in summary[key].items():
            lines.append(
                f"| {name} | {values['tests']} | {values['passed']} | "
                f"{values['pass_rate']:.1%} | {values['mean_score']:.1%} |"
            )
        lines.append("")
    lines += ["## Metrics", "", "| Metric | Cases | Mean |", "|---|---:|---:|"]
    for name, values in summary["metrics"].items():
        lines.append(f"| {name} | {values['tests']} | {values['mean']:.1%} |")
    lines.append("")
    if summary["failures"]:
        lines += ["## Failures", ""]
        for failure in summary["failures"]:
            detail = "; ".join(failure["errors"]) or "below acceptance threshold"
            lines.append(f"- `{failure['test_id']}` — {failure['score']:.1%}: {detail}")
        lines.append("")
    return "\n".join(lines)
