#!/usr/bin/env python3
"""
bind_questions_e3.py — bind E3 claims through the active versioned Fund Lens.

Uses two configured rule layers (no LLM and no archetype branching):
  R1  metric → question IDs   (primary, deterministic)
  R2  keyword scan of statement text → question IDs (secondary)

Outputs:
  bindings.json        — claim_id → [question_ids], confidence
  question_summary.txt — per-question claim count + samples
  binding_report.txt   — coverage / recall / unbound stats

Usage:
  python3 tools/bind_questions_e3.py --e3 pipeline_out/e3/K-IC/e3_claims.json \\
      --out pipeline_out/e3/K-IC/bindings/
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FUND_LENS_PATH = ROOT / "vault" / "policy" / "fund_lens_buyout_keystone_v1.json"
FUND_LENS_SCHEMA_PATH = ROOT / "vault" / "policy" / "fund_lens.schema.json"


_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_LENS_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_QUESTION_ID = re.compile(r"^[A-Za-z0-9._:-]+$")


class BindingProfileReviewBlocker(ValueError):
    """A machine-readable stop when evidence cannot be bound safely.

    Binding policy is governed input, so a missing or malformed profile must
    stop automated binding without discarding the evidence that reached the
    boundary.  Callers can persist :meth:`as_dict` in a review proposal.
    """

    def __init__(
        self,
        reason_code: str,
        detail: str,
        *,
        profile_id: str | None = None,
        profile_path: str | None = None,
    ) -> None:
        self.reason_code = reason_code
        self.detail = detail
        self.profile_id = profile_id
        self.profile_path = profile_path
        super().__init__(f"{reason_code}: {detail}")

    def as_dict(self) -> dict:
        blocker = {
            "status": "REVIEW_BLOCKED",
            "reason_code": self.reason_code,
            "profile_id": self.profile_id,
            "detail": self.detail,
            "required_action": "CONFIGURE_VALID_FUND_LENS_BINDING_PROFILE",
        }
        if self.profile_path:
            blocker["profile_path"] = self.profile_path
        return blocker


def validate_fund_lens(value: Mapping[str, Any]) -> dict:
    """Validate and detach one versioned Fund Lens configuration.

    This deliberately stays dependency-free so the same governance check runs
    in the CLI, API and serverless deployment.  ``fund_lens.schema.json`` is
    the portable contract; these checks are its executable counterpart.
    """
    if not isinstance(value, Mapping):
        raise ValueError("Fund Lens must be a JSON object")
    lens = copy.deepcopy(dict(value))
    allowed_fields = {
        "schema_version",
        "lens_id",
        "version",
        "label",
        "description",
        "archetype",
        "binding_profile",
        "binding_config",
        "effective_date",
        "questions",
    }
    unexpected = sorted(set(lens) - allowed_fields)
    if unexpected:
        raise ValueError("Fund Lens has unsupported fields: " + ", ".join(unexpected))
    required_strings = allowed_fields - {"questions", "description", "binding_config"}
    missing = [
        key
        for key in sorted(required_strings)
        if not isinstance(lens.get(key), str) or not lens[key].strip()
    ]
    if missing:
        raise ValueError("Fund Lens missing required fields: " + ", ".join(missing))
    if "description" not in lens or not isinstance(lens["description"], str):
        raise ValueError("Fund Lens description must be a string")
    if lens["schema_version"] != "fund-lens/1.0":
        raise ValueError("Fund Lens must use schema_version fund-lens/1.0")
    if not _LENS_ID.fullmatch(str(lens["lens_id"])):
        raise ValueError("Fund Lens lens_id contains unsupported characters")
    if not _SEMVER.fullmatch(str(lens["version"])):
        raise ValueError("Fund Lens version must be semantic x.y.z")
    try:
        dt.date.fromisoformat(str(lens["effective_date"]))
    except ValueError as exc:
        raise ValueError("Fund Lens effective_date must be YYYY-MM-DD") from exc
    if not _LENS_ID.fullmatch(str(lens["binding_profile"])):
        raise ValueError("Fund Lens binding_profile contains unsupported characters")

    questions = lens.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("Fund Lens must declare at least one question")
    ids: list[str] = []
    for index, question in enumerate(questions):
        if not isinstance(question, Mapping):
            raise ValueError(f"Fund Lens question {index} must be an object")
        unexpected_question_fields = sorted(
            set(question) - {"id", "version", "workstream", "title"}
        )
        if unexpected_question_fields:
            raise ValueError(
                f"Fund Lens question {index} has unsupported fields: "
                + ", ".join(unexpected_question_fields)
            )
        qid = str(question.get("id") or "").strip()
        title = str(question.get("title") or "").strip()
        workstream = str(question.get("workstream") or "").strip()
        question_version = question.get("version")
        if not qid or not _QUESTION_ID.fullmatch(qid):
            raise ValueError(f"Fund Lens question {index} has an invalid id")
        if not title:
            raise ValueError(f"Fund Lens question {qid} must have a title")
        if not workstream:
            raise ValueError(f"Fund Lens question {qid} must have a workstream")
        if (
            isinstance(question_version, bool)
            or not isinstance(question_version, int)
            or question_version < 1
        ):
            raise ValueError(f"Fund Lens question {qid} version must be a positive integer")
        ids.append(qid)
    if len(ids) != len(set(ids)):
        raise ValueError("Fund Lens question IDs must be unique")
    if "binding_config" not in lens:
        raise ValueError("Fund Lens requires a versioned binding_config")
    lens["binding_config"] = validate_binding_config(lens["binding_config"], set(ids))
    return lens


def validate_binding_config(value: Any, allowed_question_ids: set[str]) -> dict:
    """Validate portable deterministic rules owned by a Fund Lens.

    Rules only select questions declared by the same lens.  They do not create
    questions or infer a conclusion; unmatched claims deliberately remain
    unbound for the governed deal-emergent-question flow.
    """
    if not isinstance(value, Mapping):
        raise ValueError("binding_config must be an object")
    config = copy.deepcopy(dict(value))
    allowed_fields = {
        "schema_version",
        "permitted_question_ids",
        "metric_rules",
        "keyword_rules",
    }
    if set(config) - allowed_fields:
        raise ValueError("binding_config has unsupported fields")
    if config.get("schema_version") != "binding-config/1.0":
        raise ValueError("binding_config must use schema_version binding-config/1.0")
    missing = sorted(allowed_fields - set(config))
    if missing:
        raise ValueError("binding_config missing required fields: " + ", ".join(missing))
    permitted_question_ids = config.get("permitted_question_ids")
    if (
        not isinstance(permitted_question_ids, list)
        or not permitted_question_ids
        or any(
            not isinstance(qid, str)
            or not _QUESTION_ID.fullmatch(qid)
            or qid not in allowed_question_ids
            for qid in permitted_question_ids
        )
        or len(permitted_question_ids) != len(set(permitted_question_ids))
    ):
        raise ValueError(
            "binding_config permitted_question_ids must be unique questions declared by the lens"
        )
    permitted_qids = set(permitted_question_ids)
    for group in ("metric_rules", "keyword_rules"):
        rules = config[group]
        if not isinstance(rules, list):
            raise ValueError(f"binding_config {group} must be a list")
        for index, rule in enumerate(rules):
            if not isinstance(rule, Mapping):
                raise ValueError(f"binding_config {group}[{index}] must be an object")
            allowed_rule_fields = (
                {"question_ids", "confidence", "rank", "aliases"}
                if group == "metric_rules"
                else {"question_ids", "confidence", "rank", "pattern"}
            )
            if set(rule) - allowed_rule_fields:
                raise ValueError(f"binding_config {group}[{index}] has unsupported fields")
            missing_rule_fields = sorted(allowed_rule_fields - set(rule))
            if missing_rule_fields:
                raise ValueError(
                    f"binding_config {group}[{index}] missing required fields: "
                    + ", ".join(missing_rule_fields)
                )
            qids = rule["question_ids"]
            if (
                not isinstance(qids, list)
                or not qids
                or any(not isinstance(qid, str) or qid not in permitted_qids for qid in qids)
                or len(qids) != len(set(qids))
            ):
                raise ValueError(
                    f"binding_config {group}[{index}] references a question "
                    "not permitted by the profile"
                )
            confidence = rule["confidence"]
            if (
                isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not 0 <= confidence <= 1
            ):
                raise ValueError(
                    f"binding_config {group}[{index}] confidence must be between 0 and 1"
                )
            rank = rule["rank"]
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 0:
                raise ValueError(
                    f"binding_config {group}[{index}] rank must be a non-negative integer"
                )
            if group == "metric_rules":
                aliases = rule["aliases"]
                if (
                    not isinstance(aliases, list)
                    or not aliases
                    or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)
                    or len({alias.casefold() for alias in aliases}) != len(aliases)
                ):
                    raise ValueError(f"binding_config metric_rules[{index}] needs aliases")
            else:
                pattern = rule["pattern"]
                if not isinstance(pattern, str) or not pattern:
                    raise ValueError(f"binding_config keyword_rules[{index}] needs pattern")
                try:
                    re.compile(pattern, re.I)
                except re.error as exc:
                    raise ValueError(
                        f"binding_config keyword_rules[{index}] has invalid pattern: {exc}"
                    ) from exc
    return config


def load_fund_lens(path: Path | str = DEFAULT_FUND_LENS_PATH) -> dict:
    """Load a durable binding policy or raise an explicit review blocker."""
    candidate = Path(path)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BindingProfileReviewBlocker(
            "BINDING_PROFILE_MISSING",
            "The active Fund Lens file does not exist; evidence must remain unbound.",
            profile_path=str(candidate),
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise BindingProfileReviewBlocker(
            "BINDING_PROFILE_INVALID",
            f"The active Fund Lens cannot be read as valid JSON: {exc}",
            profile_path=str(candidate),
        ) from exc
    try:
        return validate_fund_lens(payload)
    except (TypeError, ValueError) as exc:
        profile_id = payload.get("binding_profile") if isinstance(payload, Mapping) else None
        reason_code = (
            "BINDING_PROFILE_MISSING"
            if not isinstance(payload, Mapping) or "binding_config" not in payload
            else "BINDING_PROFILE_INVALID"
        )
        raise BindingProfileReviewBlocker(
            reason_code,
            str(exc),
            profile_id=str(profile_id) if profile_id else None,
            profile_path=str(candidate),
        ) from exc

# ── 20 Keystone diligence questions ──────────────────────────────────────────
QUESTIONS: dict[str, str] = {
    "Q-01": "Which billing accounts share parent-company relationships?",
    "Q-02": "What percentage of revenue is generated by the largest parent customer across all billing accounts?",
    "Q-03": "Which customer agreements have minimum-volume commitments, and which can be reduced or terminated on short notice?",
    "Q-04": "How much revenue is scheduled/programmatic versus repeat-project versus new/discrete project work?",
    "Q-05": "Which top customers have non-standard pricing, margin or service-level terms?",
    "Q-06": "Which EBITDA adjustments are implemented, supportable and non-recurring?",
    "Q-07": "What is the support for the pricing and utilization initiative add-back?",
    "Q-08": "What is the correct normalized working-capital target?",
    "Q-09": "What portion of unbilled WIP is aged, disputed or missing customer approval?",
    "Q-10": "Which liabilities are debt-like and which are ordinary working-capital items?",
    "Q-11": "Which time-entry, billing, ERP and customer-master systems are still active?",
    "Q-12": "What failed or was delayed in prior integrations and systems migrations?",
    "Q-13": "Who owns the post-close integration program and what is the required cash budget?",
    "Q-14": "How are utilization, rework and project profitability defined across branches?",
    "Q-15": "Which contracts require change-of-control notice or consent?",
    "Q-16": "What is the treatment of the founder-related headquarters lease?",
    "Q-17": "What EBITDA basis will lenders use for covenant calculations?",
    "Q-18": "What are the proposed limits on add-backs, cash netting, acquisition capacity and minimum liquidity?",
    "Q-19": "Which executives and branch leaders require retention arrangements?",
    "Q-20": "What board approvals should be required before acquisitions or major systems cutovers?",
}

# The public constants remain backwards compatible, but their active ID/title
# set is owned by the versioned Fund Lens rather than by this module.
DEFAULT_FUND_LENS = load_fund_lens()
QUESTIONS = {
    str(item["id"]): str(item["title"])
    for item in DEFAULT_FUND_LENS["questions"]
}

# Vault question IDs → list of question IDs (for cross-reference reporting)
VAULT_TO_Q: dict[str, list[str]] = {
    "kq-01-parent-concentration":  ["Q-01", "Q-02"],
    "kq-02-revenue-durability":    ["Q-04", "Q-05"],
    "kq-03-contract-protections":  ["Q-03"],
    "kq-04-ebitda-adjustments":    ["Q-06", "Q-07"],
    "kq-05-working-capital":       ["Q-08"],
    "kq-06-wip-quality":           ["Q-09"],
    "kq-07-debt-classification":   ["Q-10"],
    "kq-08-integration-systems":   ["Q-11", "Q-14"],
    "kq-09-integration-history":   ["Q-12", "Q-13"],
    "kq-10-covenant-definition":   ["Q-17", "Q-18"],
    "kq-11-change-of-control":     ["Q-15", "Q-16"],
    "kq-12-governance":            ["Q-19", "Q-20"],
}

# Legacy public views are derived from the active default configuration.  They
# remain import-compatible, but no binding policy is authored in Python.
METRIC_TO_Q: dict[str, list[str]] = {
    str(alias): list(rule["question_ids"])
    for rule in DEFAULT_FUND_LENS["binding_config"]["metric_rules"]
    for alias in rule["aliases"]
}
KEYWORD_TO_Q: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(str(rule["pattern"]), re.I), list(rule["question_ids"]))
    for rule in DEFAULT_FUND_LENS["binding_config"]["keyword_rules"]
]


def ranked_bindings(
    claim: dict,
    compiler_meta: dict,
    fund_lens: dict | None = None,
) -> list[dict]:
    """Return deterministic binding evidence, ordered by policy rank/confidence."""
    source_lens = DEFAULT_FUND_LENS if fund_lens is None else fund_lens
    try:
        lens = validate_fund_lens(source_lens)
    except (TypeError, ValueError) as exc:
        profile_id = (
            source_lens.get("binding_profile")
            if isinstance(source_lens, Mapping)
            else None
        )
        reason_code = (
            "BINDING_PROFILE_MISSING"
            if not isinstance(source_lens, Mapping) or "binding_config" not in source_lens
            else "BINDING_PROFILE_INVALID"
        )
        raise BindingProfileReviewBlocker(
            reason_code,
            str(exc),
            profile_id=str(profile_id) if profile_id else None,
        ) from exc
    allowed = {str(item["id"]) for item in lens["questions"]}
    matches: dict[str, dict] = {}

    def add(qids: list[str], rule: str, confidence: float, rank: int) -> None:
        for qid in qids:
            if qid not in allowed:
                continue
            candidate = {
                "question_id": qid,
                "rule": rule,
                "confidence": confidence,
                "rank": rank,
            }
            current = matches.get(qid)
            if current is None or (rank, -confidence, rule) < (
                current["rank"],
                -current["confidence"],
                current["rule"],
            ):
                matches[qid] = candidate

    metric = str(compiler_meta.get("metric", ""))
    stmt = str(claim.get("statement", ""))
    config = lens["binding_config"]
    for rule in config["metric_rules"]:
        aliases = {str(alias).casefold() for alias in rule["aliases"]}
        if metric.casefold() in aliases:
            add(
                rule["question_ids"],
                "metric",
                float(rule["confidence"]),
                int(rule["rank"]),
            )
    for rule in config["keyword_rules"]:
        if re.search(rule["pattern"], stmt, re.I):
            add(
                rule["question_ids"],
                "keyword",
                float(rule["confidence"]),
                int(rule["rank"]),
            )
    return sorted(
        matches.values(),
        key=lambda item: (item["rank"], -item["confidence"], item["question_id"]),
    )


def bind_claim(claim: dict, compiler_meta: dict, fund_lens: dict | None = None) -> list[str]:
    """Return ordered question IDs this claim bears on (legacy-compatible API)."""
    return [item["question_id"] for item in ranked_bindings(claim, compiler_meta, fund_lens)]


def review_blocked_result(e3: Mapping[str, Any], blocker: BindingProfileReviewBlocker) -> dict:
    """Preserve extracted evidence when binding policy requires human review."""
    claims = copy.deepcopy(e3.get("claims", []))
    return {
        "status": "REVIEW_BLOCKED",
        "manifest_id": e3.get("manifest_id"),
        "deal": e3.get("deal"),
        "review_blocker": blocker.as_dict(),
        "total_claims": len(claims),
        "bound_claims": 0,
        "unbound_claims": len(claims),
        "bindings": [
            {
                "claim_id": claim.get("claim_id"),
                "question_ids": [],
                "rule": "review_blocked",
            }
            for claim in claims
        ],
        "unbound_evidence": claims,
        "deal_emergent_question_policy": {
            "status": "PENDING_REVIEW",
            "automatic_question_creation": False,
            "required_action": "PROPOSE_DEAL_EMERGENT_QUESTION",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--e3", required=True, help="e3_claims.json path")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument(
        "--fund-lens",
        default=str(DEFAULT_FUND_LENS_PATH),
        help="versioned Fund Lens JSON",
    )
    args = ap.parse_args()

    e3_path = Path(args.e3)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(e3_path) as f:
        e3 = json.load(f)
    try:
        fund_lens = load_fund_lens(args.fund_lens)
    except BindingProfileReviewBlocker as blocker:
        blocked = review_blocked_result(e3, blocker)
        (out_dir / "bindings.json").write_text(
            json.dumps(blocked, indent=2) + "\n",
            encoding="utf-8",
        )
        report = (
            "E3 Question Binding Report\n"
            + "=" * 50
            + f"\n  Status      : REVIEW_BLOCKED"
            + f"\n  Reason      : {blocker.reason_code}"
            + f"\n  Total claims: {blocked['total_claims']}"
            + "\n  Evidence was preserved unbound; no question was created automatically."
        )
        (out_dir / "binding_report.txt").write_text(report + "\n", encoding="utf-8")
        print(report, file=sys.stderr)
        return 2
    questions = {str(item["id"]): str(item["title"]) for item in fund_lens["questions"]}

    claims = e3["claims"]
    compiler_fields = {
        cf["claim_id"]: cf
        for cf in e3.get("extraction_metadata", {}).get("compiler_fields_per_claim", [])
    }

    # Build bindings
    bindings: list[dict] = []
    q_to_claims: dict[str, list[str]] = {q: [] for q in questions}
    unbound: list[str] = []

    for c in claims:
        cid = c["claim_id"]
        meta = compiler_fields.get(cid, {})
        qids = bind_claim(c, meta, fund_lens)
        bindings.append({
            "claim_id": cid,
            "statement": c["statement"],
            "metric": meta.get("metric", ""),
            "source_id": c["source_id"],
            "question_ids": qids,
            "rule": "R1+R2" if qids else "none",
        })
        if qids:
            for qid in qids:
                q_to_claims[qid].append(cid)
        else:
            unbound.append(cid)

    # ── Stats ─────────────────────────────────────────────────────────────────
    total = len(claims)
    bound_count = total - len(unbound)
    bound_ratio = bound_count / total if total else 0.0
    unbound_ratio = len(unbound) / total if total else 0.0
    covered_qs = [q for q in questions if q_to_claims[q]]
    uncovered_qs = [q for q in questions if not q_to_claims[q]]
    coverage = len(covered_qs) / len(questions)

    # Write bindings JSON
    out = {
        "manifest_id": e3.get("manifest_id"),
        "deal": e3.get("deal"),
        "fund_lens": {
            "lens_id": fund_lens["lens_id"],
            "version": fund_lens["version"],
            "binding_profile": fund_lens["binding_profile"],
        },
        "total_claims": total,
        "bound_claims": bound_count,
        "unbound_claims": len(unbound),
        "questions_covered": len(covered_qs),
        "questions_total": len(questions),
        "coverage_recall": round(coverage, 3),
        "bindings": bindings,
        "q_coverage": {q: len(q_to_claims[q]) for q in questions},
    }
    (out_dir / "bindings.json").write_text(json.dumps(out, indent=2))

    # Write human-readable report
    lines = [
        "E3 Question Binding Report",
        "=" * 50,
        f"  Manifest    : {e3.get('manifest_id')}",
        f"  Deal        : {e3.get('deal')}",
        f"  Total claims: {total}",
        f"  Bound claims: {bound_count} ({100*bound_ratio:.1f}%)",
        f"  Unbound     : {len(unbound)} ({100*unbound_ratio:.1f}%)",
        f"  Questions covered: {len(covered_qs)} / {len(questions)}",
        f"  Coverage recall : {coverage:.1%}",
        "",
        "Per-question claim counts:",
    ]
    for qid, qtxt in questions.items():
        count = len(q_to_claims[qid])
        flag = "" if count > 0 else "  ← ZERO COVERAGE"
        lines.append(f"  {qid}: {count:3d}  {qtxt[:65]}{flag}")

    lines += ["", "Uncovered questions:"]
    if uncovered_qs:
        for qid in uncovered_qs:
            lines.append(f"  {qid}: {questions[qid]}")
    else:
        lines.append("  None — full coverage.")

    lines += ["", "Metrics with no question mapping (top unbound):"]
    unbound_metrics: dict[str, int] = {}
    for b in bindings:
        if not b["question_ids"]:
            m = b["metric"] or "(no metric)"
            unbound_metrics[m] = unbound_metrics.get(m, 0) + 1
    for m, cnt in sorted(unbound_metrics.items(), key=lambda x: -x[1])[:15]:
        lines.append(f"  {cnt:3d}  {m}")

    report_text = "\n".join(lines)
    (out_dir / "binding_report.txt").write_text(report_text)
    print(report_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
