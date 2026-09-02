"""Execute canonical evaluation cases from saved or command-generated predictions."""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from evaluation.evaluator import evaluate_case
from evaluation.io import read_records
from evaluation.report import build_summary, render_markdown
from evaluation.schema import validate_case


class EvaluationRunError(RuntimeError):
    pass


def _prediction_map(path: Path) -> dict[str, dict[str, Any]]:
    records = read_records(path)
    mapped: dict[str, dict[str, Any]] = {}
    for record in records:
        test_id = str(record.get("test_id", ""))
        if not test_id:
            raise EvaluationRunError("Every prediction requires test_id")
        if test_id in mapped:
            raise EvaluationRunError(f"Duplicate prediction test_id: {test_id}")
        mapped[test_id] = record
    return mapped


def _run_id(cases: Iterable[Mapping[str, Any]]) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha256(
        "\n".join(sorted(str(case["test_id"]) for case in cases)).encode("utf-8")
    ).hexdigest()[:10]
    return f"{timestamp}-{digest}"


class CommandSystem:
    """One-case-per-process JSON stdin/stdout protocol for arbitrary systems."""

    def __init__(self, command: str, timeout: int = 300):
        self.argv = shlex.split(command)
        self.timeout = timeout
        if not self.argv:
            raise EvaluationRunError("System command cannot be empty")

    def predict(self, case: Mapping[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        # Gold, evidence targets, metric names and thresholds are evaluator-only.
        # Passing them to the system under test would invalidate every result.
        system_input = {
            key: case[key]
            for key in ("schema_version", "test_id", "benchmark", "split", "task", "inputs", "query", "tags")
            if key in case
        }
        try:
            process = subprocess.run(
                self.argv,
                input=json.dumps(system_input, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "schema_version": "panta-eval.prediction/1.0", "test_id": case["test_id"],
                "status": "error", "error": f"System command timed out after {self.timeout}s",
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
            }
        latency = round((time.monotonic() - started) * 1000, 3)
        if process.returncode:
            return {
                "schema_version": "panta-eval.prediction/1.0", "test_id": case["test_id"],
                "status": "error", "error": (process.stderr or process.stdout).strip()[-2000:],
                "latency_ms": latency,
            }
        try:
            prediction = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            return {
                "schema_version": "panta-eval.prediction/1.0", "test_id": case["test_id"],
                "status": "error", "error": f"System command emitted invalid JSON: {exc}",
                "latency_ms": latency,
            }
        prediction.setdefault("latency_ms", latency)
        return prediction


class EvaluationRunner:
    def __init__(self, *, default_threshold: float = 0.8):
        self.default_threshold = default_threshold

    def run(
        self,
        cases: list[dict[str, Any]],
        *,
        predictions_path: Path | None = None,
        system_command: str | None = None,
        timeout: int = 300,
        tasks: set[str] | None = None,
        families: set[str] | None = None,
        benchmarks: set[str] | None = None,
        tags: set[str] | None = None,
    ) -> dict[str, Any]:
        if bool(predictions_path) == bool(system_command):
            raise EvaluationRunError("Choose exactly one of predictions_path or system_command")
        seen: set[str] = set()
        selected = []
        for case in cases:
            validate_case(case)
            if case["test_id"] in seen:
                raise EvaluationRunError(f"Duplicate case test_id: {case['test_id']}")
            seen.add(case["test_id"])
            case_families = {item["family"] for item in case["inputs"]}
            if tasks and case["task"] not in tasks:
                continue
            if families and not case_families.intersection(families):
                continue
            if benchmarks and case["benchmark"]["id"] not in benchmarks:
                continue
            if tags and not set(case.get("tags", [])).intersection(tags):
                continue
            selected.append(case)
        if not selected:
            raise EvaluationRunError("No cases matched the requested filters")

        run_id = _run_id(selected)
        predictions = _prediction_map(predictions_path) if predictions_path else {}
        system = CommandSystem(system_command, timeout) if system_command else None
        results = []
        used_prediction_ids: set[str] = set()
        for case in selected:
            prediction = system.predict(case) if system else predictions.get(case["test_id"])
            if prediction is not None:
                used_prediction_ids.add(str(prediction.get("test_id", "")))
            results.append(evaluate_case(
                case, prediction, run_id=run_id, default_threshold=self.default_threshold
            ))
        extras = sorted(set(predictions) - used_prediction_ids)
        run = {
            "schema": "panta-eval.run/1.0",
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "default_threshold": self.default_threshold,
            "case_count": len(selected),
            "extra_prediction_ids": extras,
            "summary": build_summary(results),
            "results": results,
        }
        run["report_markdown"] = render_markdown(run)
        return run
