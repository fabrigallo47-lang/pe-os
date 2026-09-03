#!/usr/bin/env python3
"""Command-line interface for the PANTA multimodal evaluation suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from evaluation.adapters import ADAPTERS, get_adapter
from evaluation.io import read_cases, read_records, write_json, write_ndjson
from evaluation.registry import BenchmarkRegistry, DatasetManager, DEFAULT_DATA_ROOT, DEFAULT_REGISTRY
from evaluation.report import render_markdown
from evaluation.runner import EvaluationRunError, EvaluationRunner
from evaluation.schema import SchemaValidationError, validate_case, validate_prediction


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = ROOT / "evaluation" / "fixtures" / "cases"


def _parse_options(values: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Adapter option must be KEY=VALUE: {value!r}")
        key, raw = value.split("=", 1)
        try:
            parsed[key] = json.loads(raw)
        except json.JSONDecodeError:
            parsed[key] = raw
    return parsed


def _set(values: list[str] | None) -> set[str] | None:
    return set(values) if values else None


def cmd_validate(args: argparse.Namespace) -> int:
    cases = read_cases(args.cases)
    errors: list[str] = []
    ids: set[str] = set()
    for index, case in enumerate(cases):
        try:
            validate_case(case)
        except SchemaValidationError as exc:
            errors.extend(f"case[{index}] {message}" for message in exc.errors)
            continue
        if case["test_id"] in ids:
            errors.append(f"duplicate test_id: {case['test_id']}")
        ids.add(case["test_id"])
        if args.require_files:
            for item in case["inputs"]:
                if "path" not in item:
                    continue
                input_path = Path(item["path"])
                if not input_path.is_absolute():
                    input_path = args.asset_root / input_path
                if not input_path.exists():
                    errors.append(f"{case['test_id']}: missing input {item['path']}")
                    continue
                expected_hash = item.get("sha256")
                if expected_hash and input_path.is_file():
                    actual_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
                    if actual_hash.casefold() != str(expected_hash).casefold():
                        errors.append(
                            f"{case['test_id']}: SHA-256 mismatch for {item['path']} "
                            f"(expected {expected_hash}, got {actual_hash})"
                        )
    prediction_count = 0
    if args.predictions:
        for index, prediction in enumerate(read_records(args.predictions)):
            try:
                validate_prediction(prediction)
            except SchemaValidationError as exc:
                errors.extend(f"prediction[{index}] {message}" for message in exc.errors)
            prediction_count += 1
    if errors:
        print(f"INVALID: {len(errors)} finding(s)", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    suffix = f", {prediction_count} predictions" if args.predictions else ""
    print(f"VALID: {len(cases)} cases{suffix}")
    return 0


def cmd_adapt(args: argparse.Namespace) -> int:
    adapter = get_adapter(args.adapter)
    cases = adapter.adapt(
        args.source,
        dataset_root=args.dataset_root,
        split=args.split,
        version=args.version,
        options=_parse_options(args.option),
    )
    for case in cases:
        validate_case(case)
    write_ndjson(args.output, cases)
    print(f"Adapted {len(cases)} cases with {args.adapter} -> {args.output}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cases = read_cases(args.cases)
    runner = EvaluationRunner(default_threshold=args.threshold)
    run = runner.run(
        cases,
        predictions_path=args.predictions,
        system_command=args.system_command,
        timeout=args.timeout,
        tasks=_set(args.task),
        families=_set(args.family),
        benchmarks=_set(args.benchmark),
        tags=_set(args.tag),
    )
    output_dir = args.output_dir or ROOT / ".panta-eval" / "runs" / run["run_id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run.pop("report_markdown")
    write_json(output_dir / "run.json", run)
    write_ndjson(output_dir / "results.ndjson", run["results"])
    write_json(output_dir / "summary.json", run["summary"])
    (output_dir / "report.md").write_text(report + "\n", encoding="utf-8")
    overall = run["summary"]["overall"]
    print(
        f"{run['run_id']}: {overall['passed']}/{overall['tests']} passed, "
        f"mean score {overall['mean_score']:.1%} -> {output_dir}"
    )
    return 0 if args.no_gate or overall["failed"] == 0 else 1


def cmd_report(args: argparse.Namespace) -> int:
    payload = json.loads(args.run.read_text(encoding="utf-8"))
    markdown = render_markdown(payload)
    if args.output:
        args.output.write_text(markdown + "\n", encoding="utf-8")
        print(args.output)
    else:
        print(markdown)
    return 0


def cmd_datasets(args: argparse.Namespace) -> int:
    registry = BenchmarkRegistry.load(args.registry)
    manager = DatasetManager(registry, args.data_root)
    rows = manager.status(args.dataset)
    print("DATASET                         VERSION      AVAILABLE  ACQUISITION")
    for row in rows:
        acquisition = row["acquisition"]["type"]
        print(f"{row['id']:<31} {row['version']:<12} {str(row['available']):<10} {acquisition}")
        if args.verbose and not row["available"]:
            note = row["acquisition"].get("note")
            if note:
                print(f"  {note}")
            if row.get("data_url") or row.get("source_url"):
                print(f"  {row.get('data_url') or row.get('source_url')}")
    if args.lock:
        manager.write_lock(args.lock)
        print(f"Lock written: {args.lock}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate cases and predictions")
    validate_parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    validate_parser.add_argument("--predictions", type=Path)
    validate_parser.add_argument("--require-files", action="store_true")
    validate_parser.add_argument(
        "--asset-root", type=Path, default=ROOT,
        help="base directory for relative input paths (default: repository root)",
    )
    validate_parser.set_defaults(func=cmd_validate)

    adapt_parser = subparsers.add_parser("adapt", help="normalize a public benchmark")
    adapt_parser.add_argument("--adapter", required=True, choices=sorted(ADAPTERS))
    adapt_parser.add_argument("--source", required=True, type=Path)
    adapt_parser.add_argument("--dataset-root", type=Path)
    adapt_parser.add_argument("--split", default="validation")
    adapt_parser.add_argument("--version", default="unknown")
    adapt_parser.add_argument("--option", action="append", default=[])
    adapt_parser.add_argument("--output", required=True, type=Path)
    adapt_parser.set_defaults(func=cmd_adapt)

    run_parser = subparsers.add_parser("run", help="evaluate predictions")
    run_parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    prediction_source = run_parser.add_mutually_exclusive_group(required=True)
    prediction_source.add_argument("--predictions", type=Path)
    prediction_source.add_argument("--system-command")
    run_parser.add_argument("--output-dir", type=Path)
    run_parser.add_argument("--threshold", type=float, default=0.8)
    run_parser.add_argument("--timeout", type=int, default=300)
    run_parser.add_argument("--task", action="append")
    run_parser.add_argument("--family", action="append")
    run_parser.add_argument("--benchmark", action="append")
    run_parser.add_argument("--tag", action="append")
    run_parser.add_argument("--no-gate", action="store_true")
    run_parser.set_defaults(func=cmd_run)

    report_parser = subparsers.add_parser("report", help="re-render a saved run report")
    report_parser.add_argument("--run", required=True, type=Path)
    report_parser.add_argument("--output", type=Path)
    report_parser.set_defaults(func=cmd_report)

    dataset_parser = subparsers.add_parser("datasets", help="show public dataset availability")
    dataset_parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    dataset_parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    dataset_parser.add_argument("--dataset", action="append")
    dataset_parser.add_argument("--lock", type=Path)
    dataset_parser.add_argument("--verbose", action="store_true")
    dataset_parser.set_defaults(func=cmd_datasets)

    adapters_parser = subparsers.add_parser("adapters", help="list installed adapters")
    adapters_parser.set_defaults(func=lambda _: print("\n".join(sorted(ADAPTERS))) or 0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (EvaluationRunError, SchemaValidationError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
