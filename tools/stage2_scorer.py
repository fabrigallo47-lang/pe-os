#!/usr/bin/env python3
"""Public, deterministic Stage-2 scorer for E3 extraction manifests.

The scorer deliberately accepts only an E3 extraction manifest and a caller-
supplied live-claims CSV.  It refuses Keystone validation-layer, validation-
only, and canonical JSON inputs so it cannot become an ingestion path for the
private answer key.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


DEFAULT_MATCH_THRESHOLD = 0.35
DEFAULT_FIELD_THRESHOLD = 0.30
SCORED_FIELDS = ("value", "epistemic", "period", "perimeter", "locator")
REQUIRED_REFERENCE_FIELDS = {
    "claim_id",
    "statement",
    "source_id",
    "locator",
    "epistemic_class",
    "value",
    "period",
    "perimeter",
}
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "with",
}
_TRUE_VALUES = {"1", "true", "yes", "y"}


class Stage2ScorerError(ValueError):
    """Raised when scorer input is invalid or violates the leakage guard."""


def _normalise(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").casefold()
    return " ".join(re.findall(r"[a-z]+|\d+(?:\.\d+)?", text))


def _tokens(value: Any) -> set[str]:
    return set(_normalise(value).split()) - _STOPWORDS


def _text_similarity(left: Any, right: Any) -> float:
    """Return a deterministic lexical score in [0, 1]."""
    left_normalised = _normalise(left)
    right_normalised = _normalise(right)
    if left_normalised == right_normalised:
        return 1.0
    if not left_normalised or not right_normalised:
        return 0.0

    left_tokens = _tokens(left_normalised)
    right_tokens = _tokens(right_normalised)
    if left_tokens or right_tokens:
        dice = 2.0 * len(left_tokens & right_tokens) / (
            len(left_tokens) + len(right_tokens)
        )
    else:
        dice = 0.0
    character_ratio = SequenceMatcher(
        None, left_normalised, right_normalised, autojunk=False
    ).ratio()
    return (0.70 * dice) + (0.30 * character_ratio)


def _claim_similarity(reference: dict[str, Any], prediction: dict[str, Any]) -> float:
    statement_score = _text_similarity(
        reference.get("statement"), prediction.get("statement")
    )
    same_source = bool(_normalise(reference.get("source_id"))) and (
        _normalise(reference.get("source_id"))
        == _normalise(prediction.get("source_id"))
    )
    return min(1.0, (0.95 * statement_score) + (0.05 if same_source else 0.0))


def _looks_forbidden(value: Any) -> bool:
    raw = str(value or "").strip().replace("\\", "/").casefold()
    if not raw:
        return False
    if "layer_3_validation_do_not_ingest" in raw:
        return True
    if "claims_validation_only.csv" in raw:
        return True
    # A canonical JSON is an answer-key input.  Restrict this rule to strings
    # that actually look like JSON paths so ordinary prose is not rejected.
    return ".json" in raw and "canonical" in raw


def _walk_values(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_values(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_values(child)
    else:
        yield value


def guard_no_leakage(path: Path, payload: Any | None = None) -> None:
    """Reject prohibited grading/canonical inputs by path and embedded refs."""
    try:
        resolved = path.expanduser().resolve(strict=False)
    except OSError as exc:
        raise Stage2ScorerError(f"cannot resolve input path {path}: {exc}") from exc
    if _looks_forbidden(resolved):
        raise Stage2ScorerError(f"leakage guard rejected prohibited input: {path}")
    if payload is not None:
        for value in _walk_values(payload):
            if _looks_forbidden(value):
                raise Stage2ScorerError(
                    "leakage guard rejected a prohibited reference embedded in "
                    f"{path}: {value}"
                )


def _ensure_unique_claim_ids(claims: list[dict[str, Any]], label: str) -> None:
    seen: set[str] = set()
    for index, claim in enumerate(claims, start=1):
        claim_id = str(claim.get("claim_id") or "").strip()
        if not claim_id:
            raise Stage2ScorerError(f"{label} row {index} has no claim_id")
        if claim_id in seen:
            raise Stage2ScorerError(f"{label} contains duplicate claim_id {claim_id}")
        seen.add(claim_id)


def load_e3_manifest(path: Path) -> dict[str, Any]:
    guard_no_leakage(path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Stage2ScorerError(f"cannot read E3 manifest {path}: {exc}") from exc
    guard_no_leakage(path, manifest)

    if not isinstance(manifest, dict):
        raise Stage2ScorerError("E3 manifest root must be a JSON object")
    claims = manifest.get("claims")
    metadata = manifest.get("extraction_metadata")
    compiler_fields = (
        metadata.get("compiler_fields_per_claim")
        if isinstance(metadata, dict)
        else None
    )
    if not isinstance(claims, list) or not all(isinstance(c, dict) for c in claims):
        raise Stage2ScorerError("E3 manifest must contain a claims object array")
    if not isinstance(compiler_fields, list) or not all(
        isinstance(record, dict) for record in compiler_fields
    ):
        raise Stage2ScorerError(
            "E3 manifest must contain an extraction_metadata."
            "compiler_fields_per_claim object array"
        )
    _ensure_unique_claim_ids(claims, "E3 claims")
    _ensure_unique_claim_ids(compiler_fields, "E3 compiler metadata")
    claim_ids = {str(claim["claim_id"]) for claim in claims}
    metadata_ids = {str(record["claim_id"]) for record in compiler_fields}
    if claim_ids != metadata_ids:
        missing = sorted(claim_ids - metadata_ids)
        unknown = sorted(metadata_ids - claim_ids)
        raise Stage2ScorerError(
            "E3 compiler metadata is not a one-to-one claim_id join "
            f"(missing={missing}, unknown={unknown})"
        )
    for claim in claims:
        if not str(claim.get("statement") or "").strip():
            raise Stage2ScorerError(
                f"E3 claim {claim['claim_id']} has no statement"
            )
        if str(claim.get("validation_only") or "").casefold() in _TRUE_VALUES:
            raise Stage2ScorerError(
                f"leakage guard rejected validation-only E3 claim {claim['claim_id']}"
            )
    return manifest


def load_live_claims(path: Path) -> list[dict[str, str]]:
    guard_no_leakage(path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or [])
            missing = sorted(REQUIRED_REFERENCE_FIELDS - fields)
            if missing:
                raise Stage2ScorerError(
                    "claims-live CSV is missing columns: " + ", ".join(missing)
                )
            claims = [dict(row) for row in reader]
    except OSError as exc:
        raise Stage2ScorerError(f"cannot read claims-live CSV {path}: {exc}") from exc
    guard_no_leakage(path, claims)
    _ensure_unique_claim_ids(claims, "claims-live CSV")
    for claim in claims:
        if not str(claim.get("statement") or "").strip():
            raise Stage2ScorerError(
                f"claims-live row {claim['claim_id']} has no statement"
            )
        if str(claim.get("validation_only") or "").casefold() in _TRUE_VALUES:
            raise Stage2ScorerError(
                "leakage guard rejected validation-only live claim "
                f"{claim['claim_id']}"
            )
    return claims


def _parse_decimal(value: Any) -> Decimal | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.fullmatch(
        r"\s*[$€£]?\s*([-+]?\d[\d,]*(?:\.\d+)?)\s*(?:%|x|m|mm|million)?\s*",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def _is_percent_unit(unit: Any) -> bool:
    return _normalise(unit) in {"percent", "percentage", "pct"} or "%" in str(
        unit or ""
    )


def _normalised_number(value: Any, unit: Any) -> Decimal | None:
    number = _parse_decimal(value)
    if number is None:
        return None
    # claims_live stores percentages as ratios (0.182), while extraction
    # manifests commonly store their displayed percentage (18.2).
    if _is_percent_unit(unit) and abs(number) <= 1:
        return number * Decimal(100)
    return number


def _value_matches(reference: dict[str, Any], prediction: dict[str, Any]) -> bool:
    expected = reference.get("value")
    actual = prediction.get("value")
    if not str(expected or "").strip() or not str(actual or "").strip():
        return not str(expected or "").strip() and not str(actual or "").strip()

    expected_number = _normalised_number(expected, reference.get("unit"))
    actual_number = _normalised_number(actual, prediction.get("unit"))
    if expected_number is not None and actual_number is not None:
        difference = abs(expected_number - actual_number)
        scale = max(abs(expected_number), abs(actual_number), Decimal(1))
        return difference <= max(Decimal("0.000001"), scale * Decimal("0.000001"))
    return _normalise(expected) == _normalise(actual)


def _text_field_matches(expected: Any, actual: Any, threshold: float) -> bool:
    expected_normalised = _normalise(expected)
    actual_normalised = _normalise(actual)
    if not expected_normalised or not actual_normalised:
        return not expected_normalised and not actual_normalised
    return _text_similarity(expected, actual) >= threshold


def _field_result(
    field: str,
    reference: dict[str, Any],
    prediction: dict[str, Any],
    field_threshold: float,
) -> dict[str, Any]:
    if field == "value":
        expected = reference.get("value")
        actual = prediction.get("value")
        correct = _value_matches(reference, prediction)
    elif field == "epistemic":
        # CAP-003 names this field epistemic_class.  Do not read the obsolete
        # item["epistemic"] key that caused the historical zero-score bug.
        expected = reference.get("epistemic_class")
        actual = prediction.get("epistemic_class")
        correct = bool(_normalise(expected)) and (
            _normalise(expected) == _normalise(actual)
        )
    else:
        expected = reference.get(field)
        actual = prediction.get(field)
        correct = _text_field_matches(expected, actual, field_threshold)
    return {"correct": correct, "expected": expected, "actual": actual}


def _deterministic_matches(
    references: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    threshold: float,
) -> dict[int, tuple[float, int]]:
    """Greedily select non-reused pairs by descending transparent score."""
    candidates: list[tuple[float, str, str, int, int]] = []
    for reference_index, reference in enumerate(references):
        for prediction_index, prediction in enumerate(predictions):
            score = _claim_similarity(reference, prediction)
            candidates.append(
                (
                    score,
                    str(reference.get("claim_id")),
                    str(prediction.get("claim_id")),
                    reference_index,
                    prediction_index,
                )
            )
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

    used_references: set[int] = set()
    used_predictions: set[int] = set()
    matches: dict[int, tuple[float, int]] = {}
    for score, _reference_id, _prediction_id, reference_index, prediction_index in candidates:
        if score < threshold:
            break
        if reference_index in used_references or prediction_index in used_predictions:
            continue
        used_references.add(reference_index)
        used_predictions.add(prediction_index)
        matches[reference_index] = (score, prediction_index)
    return matches


def score_stage2(
    manifest: dict[str, Any],
    live_claims: list[dict[str, Any]],
    *,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    field_threshold: float = DEFAULT_FIELD_THRESHOLD,
) -> dict[str, Any]:
    if not 0 <= match_threshold <= 1:
        raise Stage2ScorerError("match threshold must be between 0 and 1")
    if not 0 <= field_threshold <= 1:
        raise Stage2ScorerError("field threshold must be between 0 and 1")

    references = sorted(live_claims, key=lambda c: str(c.get("claim_id")))
    predictions = sorted(manifest["claims"], key=lambda c: str(c.get("claim_id")))
    matches = _deterministic_matches(references, predictions, match_threshold)
    field_correct = {field: 0 for field in SCORED_FIELDS}
    details: list[dict[str, Any]] = []

    for reference_index, reference in enumerate(references):
        match = matches.get(reference_index)
        if match is None:
            details.append(
                {
                    "reference_claim_id": reference["claim_id"],
                    "prediction_claim_id": None,
                    "matched": False,
                    "match_score": 0.0,
                    "reference_statement": reference.get("statement"),
                    "prediction_statement": None,
                    "fields": {
                        field: {
                            "correct": False,
                            "expected": reference.get(
                                "epistemic_class" if field == "epistemic" else field
                            ),
                            "actual": None,
                        }
                        for field in SCORED_FIELDS
                    },
                }
            )
            continue

        score, prediction_index = match
        prediction = predictions[prediction_index]
        results = {
            field: _field_result(field, reference, prediction, field_threshold)
            for field in SCORED_FIELDS
        }
        for field, result in results.items():
            field_correct[field] += int(result["correct"])
        details.append(
            {
                "reference_claim_id": reference["claim_id"],
                "prediction_claim_id": prediction["claim_id"],
                "matched": True,
                "match_score": round(score, 6),
                "reference_statement": reference.get("statement"),
                "prediction_statement": prediction.get("statement"),
                "fields": results,
            }
        )

    reference_total = len(references)
    matched_total = len(matches)
    recall = matched_total / reference_total if reference_total else 1.0
    metrics: dict[str, dict[str, Any]] = {}
    for field in SCORED_FIELDS:
        correct = field_correct[field]
        metrics[field] = {
            "correct": correct,
            "evaluated": matched_total,
            "accuracy": correct / matched_total if matched_total else 0.0,
            "end_to_end_accuracy": correct / reference_total if reference_total else 1.0,
        }

    return {
        "schema_version": "stage2-public-score-1.0",
        "scorer": "public_deterministic_stage2",
        "manifest": {
            "schema_version": manifest.get("schema_version"),
            "manifest_id": manifest.get("manifest_id"),
            "deal": manifest.get("deal"),
            "extractor": manifest.get("extractor"),
            "claims": len(predictions),
            "compiler_metadata_records": len(
                manifest["extraction_metadata"]["compiler_fields_per_claim"]
            ),
        },
        "thresholds": {
            "claim_match": match_threshold,
            "text_field": field_threshold,
        },
        "recall": {
            "matched": matched_total,
            "reference_total": reference_total,
            "recall": recall,
        },
        "metrics": metrics,
        "details": details,
    }


def _percentage(value: float) -> str:
    return f"{value * 100:.1f}%"


def format_text_report(report: dict[str, Any], *, include_details: bool) -> str:
    recall = report["recall"]
    lines = [
        "Stage 2 public extraction score",
        "=" * 40,
        (
            f"Recall: {_percentage(recall['recall'])} "
            f"({recall['matched']}/{recall['reference_total']})"
        ),
    ]
    for field in SCORED_FIELDS:
        metric = report["metrics"][field]
        lines.append(
            f"{field:10s}: {_percentage(metric['accuracy'])} "
            f"({metric['correct']}/{metric['evaluated']})"
        )
    if include_details:
        lines.extend(["", "Deterministic match details"])
        for detail in report["details"]:
            if not detail["matched"]:
                lines.append(f"- {detail['reference_claim_id']} -> UNMATCHED")
                continue
            outcomes = ", ".join(
                f"{field}={'ok' if detail['fields'][field]['correct'] else 'miss'}"
                for field in SCORED_FIELDS
            )
            lines.append(
                f"- {detail['reference_claim_id']} -> "
                f"{detail['prediction_claim_id']} "
                f"score={detail['match_score']:.6f}; {outcomes}"
            )
    return "\n".join(lines)


def _write_json(path: Path, report: dict[str, Any]) -> None:
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if str(path) == "-":
        sys.stdout.write(payload)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Score an E3 claims manifest against a caller-supplied claims_live.csv "
            "without accessing canonical or validation-only inputs."
        )
    )
    parser.add_argument("--e3-manifest", required=True, type=Path)
    parser.add_argument("--claims-live", required=True, type=Path)
    parser.add_argument(
        "--match-threshold", type=float, default=DEFAULT_MATCH_THRESHOLD
    )
    parser.add_argument(
        "--field-threshold", type=float, default=DEFAULT_FIELD_THRESHOLD
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="write the complete deterministic report as JSON; use - for stdout",
    )
    parser.add_argument(
        "--details", action="store_true", help="include per-claim details in text output"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = load_e3_manifest(args.e3_manifest)
        live_claims = load_live_claims(args.claims_live)
        report = score_stage2(
            manifest,
            live_claims,
            match_threshold=args.match_threshold,
            field_threshold=args.field_threshold,
        )
    except Stage2ScorerError as exc:
        parser.error(str(exc))

    if args.json_out is not None:
        _write_json(args.json_out, report)
    if args.json_out is None or str(args.json_out) != "-":
        print(format_text_report(report, include_details=args.details))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
