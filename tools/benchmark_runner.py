#!/usr/bin/env python3
"""
Three-stage benchmark runner for the PE OS Semantic Compiler.

Stages:
  1. model   — xlsx_parser vs model_nodes.csv   (deterministic, no LLM)
  2. claims  — vault claims vs claims_live.csv   (per-dimension accuracy)
  3. bindings — binding_proposer vs position_model_bindings.csv (F1 by type)

Usage:
    .venv/bin/python3 tools/benchmark_runner.py --cic /path/to/PANTA_CIC_v1.1
    .venv/bin/python3 tools/benchmark_runner.py --cic /path/to/PANTA_CIC_v1.1 --stage model
    .venv/bin/python3 tools/benchmark_runner.py --cic /path/to/PANTA_CIC_v1.1 --deal keystone --json

Leakage guard: this script never reads layer_3_validation_DO_NOT_INGEST, claims_validation_only.csv,
or canonical/PANTA_Keystone_Canonical_Investment_Case_v1.1.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

VAULT = ROOT / "vault"

# ── security: files we must never read ──────────────────────────────────────
FORBIDDEN = {
    "layer_3_validation_DO_NOT_INGEST",
    "claims_validation_only.csv",
    "PANTA_Keystone_Canonical_Investment_Case_v1.1.json",
}


def _check_path(p: pathlib.Path) -> None:
    for part in p.parts:
        if part in FORBIDDEN:
            sys.exit(f"[LEAKAGE GUARD] Refusing to read forbidden path: {p}")


# ── text similarity (no external deps) ───────────────────────────────────────

def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    inter = ta & tb
    union = ta | tb
    return len(inter) / len(union) if union else 0.0


def _num_close(a: str, b: str, tol: float = 0.02) -> bool:
    """Return True if both strings contain a numeric value within tol of each other."""
    def nums(s: str) -> list[float]:
        return [float(m) for m in re.findall(r"-?\d+\.?\d*", s)]
    an, bn = nums(a), nums(b)
    for av in an:
        for bv in bn:
            if abs(av - bv) <= abs(av) * tol + tol:
                return True
    return False


# ── Stage 1: Model ───────────────────────────────────────────────────────────

def stage_model(cic_dir: pathlib.Path, xlsx_path: Optional[pathlib.Path]) -> dict:
    target_csv = cic_dir / "tables" / "model_nodes.csv"
    _check_path(target_csv)

    if xlsx_path is None:
        # try canonical location
        xlsx_path = cic_dir / "source_materials" / "layer_1_ingested" / "keystone_lbo_model_working.xlsx"
    if not xlsx_path.exists():
        return {"error": f"xlsx not found: {xlsx_path}"}

    from tools.xlsx_parser import parse_workbook, _score
    nodes = parse_workbook(str(xlsx_path))
    return _score(nodes, pathlib.Path(target_csv), silent=True)


# ── Stage 2: Claims ──────────────────────────────────────────────────────────

@dataclass
class VaultClaim:
    id: str
    epistemic: str = ""
    subject: str = ""
    value: str = ""
    locator: str = ""
    period: str = ""
    perimeter: str = ""
    statement: str = ""
    source_id: str = ""      # mapped from artifact path


def _parse_vault_claims(deal: str) -> list[VaultClaim]:
    cdir = VAULT / "deals" / deal / "claims"
    if not cdir.exists():
        return []
    claims = []
    for f in sorted(cdir.glob("c-*.md")):
        txt = f.read_text(encoding="utf-8")
        parts = txt.split("---", 2)
        if len(parts) < 3:
            continue
        fm_txt, body = parts[1], parts[2].strip()
        fm: dict = {}
        # multi-line source block
        in_source = False
        for line in fm_txt.splitlines():
            if line.strip() == "source:":
                in_source = True
                continue
            if in_source:
                m = re.match(r"\s+(\w[\w-]*):\s*(.*)", line)
                if m:
                    fm[f"source.{m.group(1)}"] = m.group(2).strip().strip('"')
                    continue
                else:
                    in_source = False
            m = re.match(r"^(\w[\w-]*):\s*(.*)", line)
            if m:
                fm[m.group(1)] = m.group(2).strip().strip('"')

        # derive source_id from artifact path
        artifact = fm.get("artifact", fm.get("source.artifact", ""))
        src_id = ""
        if "cim" in artifact.lower():
            src_id = "SRC-CIM"
        elif "data_room" in artifact.lower() or "dataroom" in artifact.lower():
            src_id = "SRC-DR"
        elif "initial_assessment" in artifact.lower() or "firm_initial" in artifact.lower():
            src_id = "SRC-IA"
        elif "ic_memo" in artifact.lower():
            src_id = "SRC-IC"
        elif "model_summary" in artifact.lower() or "model-sum" in artifact.lower():
            src_id = "SRC-MODEL-SUM"
        elif "model_working" in artifact.lower() or "model-part" in artifact.lower():
            src_id = "SRC-MODEL"
        elif "qoe" in artifact.lower():
            src_id = "SRC-QOE"
        elif "question_list" in artifact.lower():
            src_id = "SRC-QL"
        elif "boardpack1" in artifact.lower() or "board_pack_1" in artifact.lower() or "boardpack_dec" in artifact.lower():
            src_id = "SRC-BP1"
        elif "boardpack2" in artifact.lower() or "board_pack_2" in artifact.lower() or "boardpack_mar" in artifact.lower():
            src_id = "SRC-BP2"
        elif "june" in artifact.lower() or "jun2027" in artifact.lower() or "junecompliance" in artifact.lower():
            src_id = "SRC-JUN27"
        elif "august" in artifact.lower() or "aug2027" in artifact.lower() or "augustamendment" in artifact.lower():
            src_id = "SRC-AUG27"
        elif "exit" in artifact.lower() or "exit2031" in artifact.lower() or "recovery_exit" in artifact.lower():
            src_id = "SRC-EXIT31"

        c = VaultClaim(
            id=f.stem,
            epistemic=fm.get("epistemic", ""),
            subject=fm.get("subject", ""),
            value=fm.get("value", ""),
            locator=fm.get("locator", fm.get("source.locator", "")),
            period=fm.get("period", ""),
            perimeter=fm.get("perimeter", ""),
            statement=body,
            source_id=src_id,
        )
        claims.append(c)
    return claims


def _match_vault_to_canonical(canonical: dict, vault: list[VaultClaim]) -> Optional[VaultClaim]:
    """Return the vault claim with highest statement Jaccard similarity."""
    canon_text = canonical["statement"] + " " + canonical["value"]
    best, best_score = None, 0.0
    for vc in vault:
        vault_text = vc.statement + " " + vc.value
        score = _jaccard(canon_text, vault_text)
        if score > best_score:
            best_score = score
            best = vc
    # Only accept if similarity is meaningful
    return best if best_score >= 0.05 else None


def _score_claim_pair(canon: dict, vault: VaultClaim) -> dict[str, bool]:
    scores: dict[str, bool] = {}

    # value: numeric near-match or exact string match (for empty-value claims)
    canon_val = canon["value"].strip()
    if canon_val == "":
        scores["value"] = True  # qualitative claim — no numeric target
    else:
        scores["value"] = _num_close(canon_val, vault.value)

    # epistemic
    scores["epistemic"] = (canon["epistemic_class"].strip().lower() == vault.epistemic.strip().lower())

    # period: vault claim period field vs canonical period
    if canon["period"].strip() == "":
        scores["period"] = True
    else:
        canon_period = canon["period"].strip().lower()
        vault_period = vault.period.strip().lower()
        if vault_period == "":
            scores["period"] = False
        else:
            # exact or keyword overlap
            scores["period"] = (vault_period == canon_period) or (_jaccard(canon_period, vault_period) >= 0.4)

    # perimeter: vault claim perimeter field vs canonical perimeter
    if canon["perimeter"].strip() == "":
        scores["perimeter"] = True
    else:
        canon_perim = canon["perimeter"].strip().lower()
        vault_perim = vault.perimeter.strip().lower()
        if vault_perim == "":
            scores["perimeter"] = False
        else:
            scores["perimeter"] = (_jaccard(canon_perim, vault_perim) >= 0.3)

    # locator: loose match (any overlap)
    canon_loc = canon["locator"].strip()
    vault_loc = vault.locator.strip()
    if canon_loc == "":
        scores["locator"] = True
    elif vault_loc == "":
        scores["locator"] = False
    else:
        scores["locator"] = (_jaccard(canon_loc, vault_loc) >= 0.2)

    return scores


def stage_claims(cic_dir: pathlib.Path, deal: str) -> dict:
    target_csv = cic_dir / "tables" / "claims_live.csv"
    _check_path(target_csv)

    canonical = list(csv.DictReader(open(target_csv, encoding="utf-8-sig")))
    # exclude validation_only
    canonical = [r for r in canonical if r.get("validation_only", "").strip().lower() != "true"]

    vault_claims = _parse_vault_claims(deal)
    if not vault_claims:
        return {"error": f"No vault claims found for deal '{deal}'"}

    dims = ["value", "epistemic", "period", "perimeter", "locator"]
    dim_hits = {d: 0 for d in dims}
    matched = 0
    unmatched_ids: list[str] = []
    details: list[dict] = []

    for canon in canonical:
        vc = _match_vault_to_canonical(canon, vault_claims)
        if vc is None:
            unmatched_ids.append(canon["claim_id"])
            details.append({"id": canon["claim_id"], "matched": False})
            continue
        matched += 1
        scores = _score_claim_pair(canon, vc)
        for d in dims:
            if scores.get(d):
                dim_hits[d] += 1
        details.append({
            "id": canon["claim_id"],
            "matched": True,
            "vault_id": vc.id,
            "similarity": round(_jaccard(canon["statement"], vc.statement), 3),
            "scores": scores,
        })

    total = len(canonical)
    result = {
        "total_canonical": total,
        "matched": matched,
        "recall": round(matched / total, 3) if total else 0,
        "dim_accuracy": {d: round(dim_hits[d] / total, 3) for d in dims},
        "dim_hits": dim_hits,
        "unmatched_ids": unmatched_ids,
        "details": details,
    }
    return result


# ── Stage 3: Bindings ────────────────────────────────────────────────────────

def stage_bindings(cic_dir: pathlib.Path, deal: str) -> dict:
    target_csv = cic_dir / "tables" / "position_model_bindings.csv"
    _check_path(target_csv)

    canonical = list(csv.DictReader(open(target_csv, encoding="utf-8-sig")))

    # Try to load binding_proposer output from vault
    binding_file = VAULT / "deals" / deal / "models" / "bindings.json"
    if not binding_file.exists():
        return {
            "error": "No binding output found",
            "hint": f"Run: .venv/bin/python3 tools/binding_proposer.py --deal {deal}",
            "total_canonical": len(canonical),
        }

    _check_path(binding_file)
    proposed = json.loads(binding_file.read_text(encoding="utf-8"))
    if isinstance(proposed, dict):
        proposed = proposed.get("bindings", [])

    # Build sets of (position_id, model_node_id) pairs
    canonical_pairs = {(r["position_id"].strip(), r["model_node_id"].strip()) for r in canonical}
    proposed_pairs = {
        (b.get("position_id", "").strip(), b.get("model_node_id", "").strip())
        for b in proposed
    }

    by_type: dict[str, dict] = {}
    for r in canonical:
        bt = r.get("binding_type", "UNKNOWN")
        by_type.setdefault(bt, {"tp": 0, "fp": 0, "fn": 0})

    tp_total, fp_total, fn_total = 0, 0, 0
    for r in canonical:
        bt = r["binding_type"]
        pair = (r["position_id"].strip(), r["model_node_id"].strip())
        if pair in proposed_pairs:
            by_type[bt]["tp"] += 1
            tp_total += 1
        else:
            by_type[bt]["fn"] += 1
            fn_total += 1

    for pair in proposed_pairs:
        if pair not in canonical_pairs:
            # try to assign to a type (best-effort)
            fp_total += 1

    def _f1(d: dict) -> float:
        p = d["tp"] / (d["tp"] + d["fp"]) if (d["tp"] + d["fp"]) > 0 else 0.0
        r = d["tp"] / (d["tp"] + d["fn"]) if (d["tp"] + d["fn"]) > 0 else 0.0
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    overall_p = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else 0.0
    overall_r = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else 0.0
    overall_f1 = 2 * overall_p * overall_r / (overall_p + overall_r) if (overall_p + overall_r) > 0 else 0.0

    return {
        "total_canonical": len(canonical),
        "total_proposed": len(proposed_pairs),
        "tp": tp_total, "fp": fp_total, "fn": fn_total,
        "precision": round(overall_p, 3),
        "recall": round(overall_r, 3),
        "f1": round(overall_f1, 3),
        "by_type": {
            bt: {
                "tp": d["tp"], "fn": d["fn"],
                "recall": round(d["tp"] / (d["tp"] + d["fn"]), 3) if (d["tp"] + d["fn"]) > 0 else 0.0,
            }
            for bt, d in by_type.items()
        },
    }


# ── Reporting ─────────────────────────────────────────────────────────────────

def _bar(frac: float, width: int = 20) -> str:
    filled = round(frac * width)
    return "█" * filled + "░" * (width - filled)


def print_report(results: dict) -> None:
    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║       PE OS Semantic Compiler Benchmark — Keystone               ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    # Stage 1
    print("\n── Stage 1: Model Parser ──────────────────────────────────────────")
    m = results.get("model", {})
    if "error" in m:
        print(f"  ERROR: {m['error']}")
    else:
        rec = m.get("recall", 0)
        prec = m.get("precision", 0)
        f1 = m.get("f1", 0)
        tp = m.get("tp", 0)
        total = m.get("total", 0)
        print(f"  Target nodes:  {total}")
        print(f"  Recall:        {rec*100:.1f}%  {_bar(rec)}  {tp}/{total} found")
        print(f"  Precision:     {prec*100:.1f}%  {_bar(prec)}")
        print(f"  F1:            {f1*100:.1f}%  {_bar(f1)}")
        by_kind = m.get("per_kind", {})
        if by_kind:
            print("  Per kind:")
            for k, v in sorted(by_kind.items()):
                hit, tot = v.get("tp", 0), v.get("total", 0)
                r = hit / tot if tot else 0
                print(f"    {k:<30} {hit}/{tot}  {_bar(r, 10)}")

    # Stage 2
    print("\n── Stage 2: Claim Extractor ───────────────────────────────────────")
    c = results.get("claims", {})
    if "error" in c:
        print(f"  ERROR: {c['error']}")
        if "hint" in c:
            print(f"  Hint: {c['hint']}")
    else:
        total = c.get("total_canonical", 0)
        matched = c.get("matched", 0)
        rec = c.get("recall", 0)
        print(f"  Canonical claims:  {total}")
        print(f"  Matched in vault:  {matched}/{total}  ({rec*100:.1f}% recall)")
        da = c.get("dim_accuracy", {})
        if da:
            print("  Per-dimension accuracy (of canonical set):")
            for dim, acc in da.items():
                hits = c["dim_hits"][dim]
                print(f"    {dim:<12} {acc*100:5.1f}%  {_bar(acc)}  {hits}/{total}")
        unmatched = c.get("unmatched_ids", [])
        if unmatched:
            print(f"  Unmatched canonical IDs ({len(unmatched)}): {', '.join(unmatched[:10])}" +
                  (f" +{len(unmatched)-10} more" if len(unmatched) > 10 else ""))

    # Stage 3
    print("\n── Stage 3: Binding Proposer ──────────────────────────────────────")
    b = results.get("bindings", {})
    if "error" in b:
        print(f"  ERROR: {b['error']}")
        if "hint" in b:
            print(f"  Hint: {b['hint']}")
    else:
        total = b.get("total_canonical", 0)
        f1 = b.get("f1", 0)
        prec = b.get("precision", 0)
        rec = b.get("recall", 0)
        print(f"  Canonical bindings:  {total}")
        print(f"  Precision:           {prec*100:.1f}%")
        print(f"  Recall:              {rec*100:.1f}%")
        print(f"  F1:                  {f1*100:.1f}%  {_bar(f1)}")
        by_type = b.get("by_type", {})
        if by_type:
            print("  Per binding type:")
            for bt, v in sorted(by_type.items()):
                r = v.get("recall", 0)
                tp, fn = v["tp"], v["fn"]
                print(f"    {bt:<35} {tp}/{tp+fn}  {_bar(r, 10)}")

    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def stage_claims_from_file(cic_dir: pathlib.Path, claims_json: pathlib.Path) -> dict:
    """Score a benchmark_extract.py output JSON against claims_live.csv."""
    target_csv = cic_dir / "tables" / "claims_live.csv"
    _check_path(target_csv)
    _check_path(claims_json)

    canonical = list(csv.DictReader(open(target_csv, encoding="utf-8-sig")))
    canonical = [r for r in canonical if r.get("validation_only", "").strip().lower() != "true"]

    raw = json.loads(claims_json.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("claims", [])

    # Wrap raw items as VaultClaim-like objects
    vault_claims = []
    for item in raw:
        vc = VaultClaim(
            id=f"bm-{len(vault_claims)}",
            # extract_v2 emits `epistemic_class`; older/vault shapes use `epistemic`.
            # Accept both so the scorer measures extraction quality, not key naming.
            epistemic=item.get("epistemic_class") or item.get("epistemic", ""),
            subject=item.get("subject") or item.get("metric", ""),
            value=str(item.get("value", "")),
            locator=item.get("locator", ""),
            period=str(item.get("period", "")),
            perimeter=str(item.get("perimeter", "")),
            statement=item.get("statement", ""),
            source_id=item.get("source_id", ""),
        )
        vault_claims.append(vc)

    dims = ["value", "epistemic", "period", "perimeter", "locator"]
    dim_hits = {d: 0 for d in dims}
    matched = 0
    unmatched_ids: list[str] = []
    details: list[dict] = []

    for canon in canonical:
        vc = _match_vault_to_canonical(canon, vault_claims)
        if vc is None:
            unmatched_ids.append(canon["claim_id"])
            details.append({"id": canon["claim_id"], "matched": False})
            continue
        matched += 1
        scores = _score_claim_pair(canon, vc)
        for d in dims:
            if scores.get(d):
                dim_hits[d] += 1
        details.append({
            "id": canon["claim_id"], "matched": True,
            "vault_id": vc.id,
            "similarity": round(_jaccard(canon["statement"], vc.statement), 3),
            "scores": scores,
        })

    total = len(canonical)
    return {
        "total_canonical": total,
        "matched": matched,
        "recall": round(matched / total, 3) if total else 0,
        "dim_accuracy": {d: round(dim_hits[d] / total, 3) for d in dims},
        "dim_hits": dim_hits,
        "unmatched_ids": unmatched_ids,
        "details": details,
        "source": str(claims_json),
    }


def main():
    parser = argparse.ArgumentParser(description="PE OS three-stage benchmark runner")
    parser.add_argument("--cic", required=True, help="Path to PANTA_CIC_v1.1 package root")
    parser.add_argument("--deal", default="keystone", help="Vault deal slug (default: keystone)")
    parser.add_argument("--xlsx", help="Override xlsx workbook path (default: from CIC layer_1)")
    parser.add_argument("--claims-file", help="Score a benchmark_extract JSON instead of vault claims")
    parser.add_argument("--stage", choices=["model", "claims", "bindings", "all"],
                        default="all", help="Which stage(s) to run")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    cic_dir = pathlib.Path(args.cic)
    if not cic_dir.exists():
        sys.exit(f"CIC directory not found: {cic_dir}")

    xlsx_path = pathlib.Path(args.xlsx) if args.xlsx else None
    results: dict = {}

    if args.stage in ("model", "all"):
        print("Running Stage 1: model parser...", end=" ", flush=True)
        results["model"] = stage_model(cic_dir, xlsx_path)
        print("done")

    if args.stage in ("claims", "all"):
        if args.claims_file:
            print("Running Stage 2: claim extractor (from file)...", end=" ", flush=True)
            results["claims"] = stage_claims_from_file(cic_dir, pathlib.Path(args.claims_file))
        else:
            print("Running Stage 2: claim extractor (vault)...", end=" ", flush=True)
            results["claims"] = stage_claims(cic_dir, args.deal)
        print("done")

    if args.stage in ("bindings", "all"):
        print("Running Stage 3: binding proposer...", end=" ", flush=True)
        results["bindings"] = stage_bindings(cic_dir, args.deal)
        print("done")

    if args.json:
        out = {k: {kk: vv for kk, vv in v.items() if kk != "details"}
               for k, v in results.items()}
        print(json.dumps(out, indent=2))
    else:
        print_report(results)


if __name__ == "__main__":
    main()
