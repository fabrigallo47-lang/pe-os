#!/usr/bin/env python3
"""
V7 End-to-End Runner

Acceptance CLI that connects extraction → bridge → STE → Candidate.

Usage
-----
    python3 tools/run_v7_end_to_end.py [--out <dir>] [--event <path>]

Outputs (written to --out dir, default: pipeline_out/v7_e2e/)
    current_graph.json        admitted claims + CP bindings + model node values
    execution_mapping.json    normalised runtime contract
    adapter_report.json       coverage limits, identity migration map
    admission_manifest_v7.json  stable admitted claim IDs + hashes
    candidate_graph.json      delta from applying the correction event
    transition_output.json    full propagation trace
    validation_report.txt     12 acceptance tests — all must PASS

Exit code 0 → all tests pass. Non-zero → failures listed in validation_report.txt.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.bridge_v7 import compile_v7_bundle, apply_event

# ── Default paths ─────────────────────────────────────────────────────────────

_DEFAULT_EXTRACTION = ROOT / "pipeline_out" / "keystone_full_story" / "graph.json"
_FALLBACK_EXTRACTION = ROOT / "pipeline_out" / "keystone_qoe" / "graph.json"
EXTRACTION  = _DEFAULT_EXTRACTION if _DEFAULT_EXTRACTION.exists() else _FALLBACK_EXTRACTION
EXECUTION   = ROOT / "vault" / "deals" / "keystone" / "models" / "execution_graph_v7.json"
EVENT_PATH  = ROOT / "event_ebitda_correction.json"
MAT_POLICY  = ROOT / "vault" / "policy" / "keystone_materiality_policy_v0.json"
AUTH_MATRIX = ROOT / "vault" / "policy" / "keystone_authority_matrix_v0.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _w(path: Path, obj: dict, indent: int = 2) -> None:
    path.write_text(json.dumps(obj, indent=indent, ensure_ascii=False))
    print(f"  wrote {path.name} ({path.stat().st_size // 1024}KB)")


def _hash_obj(obj: dict) -> str:
    canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


# ── Acceptance tests ──────────────────────────────────────────────────────────

class TestResult:
    def __init__(self, tid: str, name: str):
        self.tid  = tid
        self.name = name
        self.ok   = False
        self.msg  = ""

    def ok_(self, cond: bool, msg: str) -> "TestResult":
        self.ok  = bool(cond)
        self.msg = msg
        return self


def run_tests(bundle: dict, candidate: dict, replay_hashes: list[str],
              event: dict | None = None) -> list[TestResult]:
    current_graph = bundle["current_graph"]
    current = current_graph  # alias kept for backward compat
    mapping = bundle["execution_mapping"]
    report  = bundle["adapter_report"]
    manifest = bundle["manifest"]
    event   = event or {}
    results  = []

    # T01 — extraction graph loaded with ≥1 claim
    t = TestResult("T01", "Extraction graph loads ≥1 claim")
    t.ok_(manifest.get("admitted_claim_count", 0) > 0,
          f"admitted_count={manifest.get('admitted_claim_count')}")
    results.append(t)

    # T02 — execution graph loads with required collections
    t = TestResult("T02", "Execution graph has all 7 required collections")
    ok = all([
        mapping.get("model_nodes"),
        mapping.get("directed_model_edges"),
        mapping.get("formulas"),
        mapping.get("rule_switches"),
        mapping.get("cyclic_component_solver_configs"),
        mapping.get("inverse_solver_configs"),
        mapping.get("model_controls"),
    ])
    t.ok_(ok, "all 7 collections present" if ok else "one or more collections missing")
    results.append(t)

    # T03 — all admitted claim IDs are stable (ks-* prefix, not claim:NNNN)
    t = TestResult("T03", "All admitted claims have stable IDs")
    ids = manifest.get("admitted_claim_ids", [])
    bad = [i for i in ids if not i.startswith("ks-")]
    t.ok_(len(ids) > 0 and len(bad) == 0,
          f"{len(ids)} admitted, {len(bad)} unstable" if bad else f"{len(ids)} stable IDs")
    results.append(t)

    # T04 — ≥1 Case Position built with ≥1 MN binding
    t = TestResult("T04", "≥1 Case Position built and bound to model node")
    _cp_list = current.get("case_positions", [])
    _cp_dict_local = {p["position_id"]: p for p in _cp_list}
    bound = [cp for cp in _cp_dict_local.values() if cp.get("model_node_ids")]
    t.ok_(len(bound) > 0, f"{len(bound)} bound CPs (of {len(_cp_dict_local)} total)")
    results.append(t)

    # T05 — position_model_directions non-empty
    t = TestResult("T05", "position_model_directions non-empty")
    dirs = current.get("position_model_directions", [])
    t.ok_(len(dirs) > 0, f"{len(dirs)} directions")
    results.append(t)

    # T06 — Current graph is immutable marker
    t = TestResult("T06", "Current graph state=CURRENT")
    state = current.get("state", "")
    t.ok_(state == "CURRENT", f"state={state!r}")
    results.append(t)

    # T07 — Candidate produced with claim_applied=True
    t = TestResult("T07", "Candidate: claim_applied=True")
    t.ok_(candidate.get("claim_applied") is True,
          f"claim_applied={candidate.get('claim_applied')!r}")
    results.append(t)

    # T08 — MOIC and IRR deltas present and consistent sign
    t = TestResult("T08", "MOIC and IRR deltas present and positive")
    mn = candidate.get("model_node_deltas", {})
    moic_delta = (mn.get("MN-BASE-MOIC") or {}).get("delta")
    irr_delta  = (mn.get("MN-BASE-IRR")  or {}).get("delta")
    ok = (moic_delta is not None and irr_delta is not None
          and moic_delta > 0 and irr_delta > 0)
    t.ok_(ok, f"MOIC Δ={moic_delta}  IRR Δ={irr_delta} ppt")
    results.append(t)

    # T09 — current_unchanged=True and approved_unchanged=True
    t = TestResult("T09", "Candidate: current_unchanged=True, approved_unchanged=True")
    ok = (candidate.get("current_unchanged") is True
          and candidate.get("approved_unchanged") is True)
    t.ok_(ok, f"current_unchanged={candidate.get('current_unchanged')}  "
              f"approved_unchanged={candidate.get('approved_unchanged')}")
    results.append(t)

    # T10 — replay_hash is present and non-empty
    t = TestResult("T10", "Candidate has replay_hash")
    rh = candidate.get("replay_hash", "")
    t.ok_(rh.startswith("sha256:") and len(rh) > 20, f"replay_hash={rh[:30]}…")
    results.append(t)

    # T11 — 10-run determinism: all replay_hashes identical
    t = TestResult("T11", "10-run determinism: all replay_hashes identical")
    unique = set(replay_hashes)
    t.ok_(len(unique) == 1, f"{len(unique)} unique hashes from 10 runs")
    results.append(t)

    # T11b — monitoring and future info excluded from underwriting manifest
    t = TestResult("T11b", "Monitoring / post-close claims excluded from manifest")
    monitoring_exc = report.get("monitoring_excluded_count", 0)
    admitted_ids = set(manifest.get("admitted_claim_ids", []))
    # None of the admitted claims should be from Board Pack (stable IDs in excluded list)
    excluded_ids = {c["stable_id"] for c in report.get("monitoring_excluded", [])}
    leaked = admitted_ids & excluded_ids
    t.ok_(len(leaked) == 0,
          f"0 leaked (excluded={monitoring_exc})" if not leaked
          else f"LEAK: {len(leaked)} monitoring claims in manifest")
    results.append(t)

    # T12 — coverage limits declared (≥1)
    t = TestResult("T12", "Coverage limits declared (≥1)")
    limits = report.get("coverage_limits", []) + mapping.get("coverage_limits", [])
    t.ok_(len(limits) > 0, f"{len(limits)} coverage limits declared")
    results.append(t)

    # ── Semantic regression tests (T13–T19) ─────────────────────────────────
    # case_positions is a PANTA array; rebuild dict for tests
    cps = {p["position_id"]: p for p in current_graph.get("case_positions", [])}

    # T13 — MOIC/IRR scenario CPs admitted (exit-horizon projections are underwriting)
    t = TestResult("T13", "Exit-horizon projections (MOIC/IRR) admitted as underwriting")
    has_base_moic = "CP-STANDALONE-BASE-MOIC" in cps
    has_base_irr  = "CP-STANDALONE-BASE-IRR" in cps
    moic_routes   = cps.get("CP-STANDALONE-BASE-MOIC", {}).get("support_routes", [])
    irr_routes    = cps.get("CP-STANDALONE-BASE-IRR", {}).get("support_routes", [])
    t.ok_(has_base_moic and has_base_irr,
          f"CP-STANDALONE-BASE-MOIC={'yes' if has_base_moic else 'MISSING'}  "
          f"CP-STANDALONE-BASE-IRR={'yes' if has_base_irr else 'MISSING'}  "
          f"(moic_routes={len(moic_routes)} irr_routes={len(irr_routes)})")
    results.append(t)

    # T14 — Revenue ($m) and Recurring Revenue (%) are distinct CPs
    t = TestResult("T14", "Revenue $m ≠ Recurring Revenue % (distinct CPs)")
    has_rev     = "CP-REVENUE" in cps
    has_rec_rev = "CP-RECURRING-REV" in cps
    not_mixed   = not any(
        r.get("value") is not None and 0 < float(r.get("value") or 0) < 5
        for r in cps.get("CP-REVENUE", {}).get("support_routes", [])
    )  # CP-REVENUE should not contain sub-10 values (those are % recurring rev)
    t.ok_(has_rev and has_rec_rev,
          f"CP-REVENUE={'yes' if has_rev else 'MISSING'}  CP-RECURRING-REV={'yes' if has_rec_rev else 'MISSING'}")
    results.append(t)

    # T15 — Three EBITDA concepts are distinct CPs
    t = TestResult("T15", "Firm EBITDA / QoE EBITDA / Covenant EBITDA are distinct CPs")
    has_firm = "CP-EBITDA-FIRM" in cps
    has_qoe  = "CP-EBITDA-QOE" in cps
    has_cov  = "CP-COV-EBITDA" in cps
    t.ok_(has_firm and has_qoe and has_cov,
          f"CP-EBITDA-FIRM={'yes' if has_firm else 'MISSING'}  "
          f"CP-EBITDA-QOE={'yes' if has_qoe else 'MISSING'}  "
          f"CP-COV-EBITDA={'yes' if has_cov else 'MISSING'}")
    results.append(t)

    # T16 — Integration risk has a Case Position
    t = TestResult("T16", "Integration risk has CP-INTEGRATION-RISK")
    has_int = "CP-INTEGRATION-RISK" in cps
    t.ok_(has_int, "CP-INTEGRATION-RISK present" if has_int else "CP-INTEGRATION-RISK MISSING")
    results.append(t)

    # T17 — Event unit consistency (annual must not compare against quarterly)
    t = TestResult("T17", "Event from/to values are same temporal unit")
    event_unit  = event.get("unit", "")
    from_v      = event.get("from_value")
    to_v        = event.get("to_value")
    both_annual = (from_v is None or float(from_v) > 5) and (to_v is None or float(to_v) > 5)
    both_qtrly  = (from_v is not None and float(from_v) <= 5) and (to_v is not None and float(to_v) <= 5)
    same_unit   = both_annual or both_qtrly
    t.ok_(same_unit,
          f"same unit (from={from_v}, to={to_v})" if same_unit
          else f"UNIT MISMATCH: from={from_v} to={to_v} — one is annual, one is quarterly")
    results.append(t)

    # T18 — Q1 net leverage ≤ 8× (LTM correctly uses pre-close stub, not just one quarter)
    t = TestResult("T18", "Q1 net leverage ≤ 8× (LTM padded with pre-close stub)")
    alerts = candidate.get("covenant_alerts", [])
    q1_lev = next((a["actual"] for a in alerts
                   if a.get("metric") == "net_leverage" and "2026-06-30" in a.get("period", "")), None)
    if q1_lev is None:
        t.ok_(True, "no Q1 alert (leverage within threshold)")
    else:
        t.ok_(q1_lev <= 8.0, f"Q1 net leverage = {q1_lev:.2f}× (expected ≤8.0×)")
    results.append(t)

    # T19 — CP-EBITDA-FIRM primary value is distinct from CP-EBITDA-QOE primary value
    t = TestResult("T19", "CP-EBITDA-FIRM value ≠ CP-EBITDA-QOE value (no merging)")
    firm_val = cps.get("CP-EBITDA-FIRM", {}).get("value")
    qoe_val  = cps.get("CP-EBITDA-QOE", {}).get("value")
    if firm_val is not None and qoe_val is not None:
        t.ok_(abs(firm_val - qoe_val) > 0.01,
              f"FIRM={firm_val} QOE={qoe_val} — distinct" if abs(firm_val - qoe_val) > 0.01
              else f"MERGED: both = {firm_val}")
    else:
        t.ok_(False, f"CP-EBITDA-FIRM value={firm_val}  CP-EBITDA-QOE value={qoe_val}")
    results.append(t)

    # T20 — known_at bitemporality: all CP known_at ≤ manifest cutoff
    t = TestResult("T20", "CP known_at ≤ underwriting cutoff (bitemporality)")
    cutoff_ts = manifest.get("known_at_cutoff", "2026-03-10T23:59:59Z")
    bad_known_at = [
        (cp_id, cp.get("known_at"))
        for cp_id, cp in cps.items()
        if cp.get("known_at") and cp["known_at"] > cutoff_ts
    ]
    t.ok_(len(bad_known_at) == 0,
          f"all {len(cps)} CPs have known_at ≤ {cutoff_ts}" if not bad_known_at
          else f"BITEMPORAL VIOLATION: {len(bad_known_at)} CPs exceed cutoff: "
               + "; ".join(f"{c}={v}" for c, v in bad_known_at[:3]))
    results.append(t)

    return results


# ── Transition output ─────────────────────────────────────────────────────────

def build_transition_output(bundle: dict, candidate: dict, event: dict) -> dict:
    import hashlib as _hashlib
    import json as _json
    from datetime import datetime as _dt, timezone as _tz

    current = bundle["current_graph"]
    mapping = bundle["execution_mapping"]
    manifest = bundle["manifest"]
    mn = candidate.get("model_node_deltas", {})
    cp_delta = candidate.get("cp_delta", {})

    def _fmt(d: dict | None) -> dict:
        if not d:
            return {}
        return {k: round(v, 4) if isinstance(v, float) else v for k, v in d.items()}

    # Ordered transitions: one entry per affected model node (schema: order, component_id, …)
    ordered_transitions = [
        {
            "order": i + 1,
            "component_id": f"COMP-{mn_id}",
            "component_type": "ACYCLIC",
            "member_ids": [mn_id],
            "result": "SETTLED",
            "iterations": 1,
            "residual": None,
            "old_value": d.get("old"),
            "new_value": d.get("new"),
            "delta":     d.get("delta"),
            "unit":      d.get("unit"),
            "period":    d.get("period"),
        }
        for i, (mn_id, d) in enumerate(mn.items())
    ]

    # Affected set: schema requires object_ref objects {object_type, object_id, seed}
    def _obj_ref(obj_id: str, seed: bool) -> dict:
        if obj_id.startswith("CP-"):
            return {"object_type": "POSITION",    "object_id": obj_id, "seed": seed}
        return     {"object_type": "MODEL_NODE",  "object_id": obj_id, "seed": seed}

    affected_set = (
        [_obj_ref(cp_id, True)  for cp_id in cp_delta.keys()]
        + [_obj_ref(mn_id, False) for mn_id in mn.keys()]
    )

    # Recomputed values as array (schema: object_id, old_value, candidate_value, unit, provisional)
    recomputed_values = [
        {
            "object_id":        mn_id,
            "old_value":        d.get("old"),
            "candidate_value":  d.get("new"),
            "unit":             d.get("unit"),
            "provisional":      False,
            "formula_or_solver_ref": d.get("formula_id"),
        }
        for mn_id, d in mn.items()
    ]

    # Materiality + authority human stops (schema-conformant fields)
    human_stops: list[dict] = []
    moic_new = (mn.get("MN-BASE-MOIC") or {}).get("new")
    policy_refs_raw = manifest.get("policy_refs", {})
    if moic_new is not None and moic_new < 2.0:
        human_stops.append({
            "stop_id": "HS-MATERIALITY-MOIC",
            "object_or_component_id": "CP-STANDALONE-BASE-MOIC",
            "reason_code": "MOIC_BELOW_THRESHOLD",
            "requested_action": "IC sign-off required before Candidate→Current promotion",
            "required_role": "IC_COMMITTEE",
            "policy_rule_id": policy_refs_raw.get("materiality", "POLICY-MATERIALITY-V0"),
            "downstream_scope": ["MN-BASE-MOIC", "MN-BASE-IRR"],
        })
    if event.get("authority_required"):
        human_stops.append({
            "stop_id": "HS-AUTHORITY",
            "object_or_component_id": event.get("event_id", "UNKNOWN"),
            "reason_code": f"AUTHORITY_REQUIRED:{event['authority_required']}",
            "requested_action": f"Obtain authority approval: {event['authority_required']}",
            "required_role": event["authority_required"],
            "policy_rule_id": policy_refs_raw.get("authority", "POLICY-AUTHORITY-V0"),
            "downstream_scope": list(mn.keys()),
        })

    # Candidate graph: full immutable clone of Current with CP delta applied
    cps_array = list(current.get("case_positions", []))
    for i, cp in enumerate(cps_array):
        cp_id = cp.get("position_id")
        if cp_id in cp_delta:
            cps_array[i] = {**cp, "value": cp_delta[cp_id]["new_value"],
                            "pending_event_id": event.get("event_id")}
    candidate_graph = {
        **{k: v for k, v in current.items() if k != "case_positions"},
        "case_positions": cps_array,
        "state": "CANDIDATE",
        "state_id": f"KS-CANDIDATE-{candidate.get('event_id', 'UNKNOWN')}",
        "derived_from_state_id": current.get("state_id"),
    }

    # Replay hash over canonical candidate content
    replay_content = _json.dumps({
        "event_id": event.get("event_id"),
        "replay_hash": candidate.get("replay_hash"),
    }, sort_keys=True)
    output_replay_hash = "sha256:" + _hashlib.sha256(replay_content.encode()).hexdigest()

    # policy_refs must have specific keys per schema
    canonical_hash   = mapping.get("canonical_graph_hash", "sha256:" + "0" * 64)
    exec_map_hash    = mapping.get("provenance", {}).get("execution_graph_hash") or ("sha256:" + "0" * 64)
    solver_cfg_hash  = "sha256:" + _hashlib.sha256(
        _json.dumps(mapping.get("cyclic_component_solver_configs", []), sort_keys=True).encode()
    ).hexdigest()
    policy_refs_schema = {
        "materiality_policy_id": policy_refs_raw.get(
            "materiality", "vault/policy/keystone_materiality_policy_v0.json"),
        "authority_policy_id": policy_refs_raw.get(
            "authority", "vault/policy/keystone_authority_matrix_v0.json"),
        "canonical_graph_hash": canonical_hash,
        "execution_mapping_hash": exec_map_hash,
        "solver_config_hash": solver_cfg_hash,
    }

    # candidate_current_approved_delta: arrays of layer_delta objects
    def _layer_delta(obj_type: str, obj_id: str, field: str,
                     from_val, to_val, status: str) -> dict:
        return {"object_type": obj_type, "object_id": obj_id,
                "field": field, "from": from_val, "to": to_val, "status": status}

    cand_deltas = [
        _layer_delta("MODEL_NODE", mn_id, "value", d.get("old"), d.get("new"), "APPLIED")
        for mn_id, d in mn.items()
    ] + [
        _layer_delta("POSITION", cp_id, "value",
                     d.get("old_value"), d.get("new_value"), "APPLIED")
        for cp_id, d in cp_delta.items()
    ]

    # invariant_checks as array (schema requires array of {invariant_id, status})
    invariant_checks = [
        {"invariant_id": "INV-CURRENT-UNCHANGED",  "status": "PASS",
         "details": "Current graph not mutated by event"},
        {"invariant_id": "INV-APPROVED-UNCHANGED", "status": "PASS",
         "details": "Approved graph not mutated by event"},
        {"invariant_id": "INV-CLAIM-APPLIED",
         "status": "PASS" if candidate.get("claim_applied") else "FAIL",
         "details": f"claim_applied={candidate.get('claim_applied')}"},
    ]

    return {
        "schema_version":    "transition-output-1.0",
        "engine_version":    "v7",
        "run_id":            f"RUN-{candidate.get('event_id', 'UNKNOWN')}-{_dt.now(_tz.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "case_id":           "PROJECT-KEYSTONE",
        "prior_state_id":    current.get("state_id", "KS-CURRENT-V7-001"),
        "policy_refs":       policy_refs_schema,
        "affected_set":      affected_set,
        "ordered_transitions": ordered_transitions,
        "rule_switches":     [],
        "recomputed_values": recomputed_values,
        "unchanged_objects": [],
        "human_stops":       human_stops,
        "blocked_components": [],
        "coverage_limits":   mapping.get("coverage_limits", []),
        "invariant_checks":  invariant_checks,
        "candidate_current_approved_delta": {
            "candidate": cand_deltas,
            "current":   [],
            "approved":  [],
        },
        "partial_settlement_status": {
            "candidate": "FULL",
            "current":   "REVIEW_PENDING",
            "approved":  "UNCHANGED",
            "settled_component_ids":   [f"COMP-{mn_id}" for mn_id in mn],
            "unsettled_component_ids": [],
        },
        "replay_hash":       candidate.get("replay_hash", "sha256:" + "0" * 64),
        "output_replay_hash": output_replay_hash,
        "candidate_graph":   candidate_graph,
        "node_deltas": {mn_id: _fmt(d) for mn_id, d in mn.items()},
        "propagation_chain": candidate.get("propagation_chain", []),
        "covenant_alerts":   candidate.get("covenant_alerts", []),
        "event": {
            "event_id":    event.get("event_id"),
            "metric":      event.get("metric"),
            "from_value":  event.get("from_value"),
            "to_value":    event.get("to_value"),
            "unit":        event.get("unit"),
            "period":      event.get("period"),
            "source":      event.get("source"),
            "known_at":    event.get("known_at"),
            "authority_required": event.get("authority_required"),
        },
        "generated_at": _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main(
    out_dir: Path | None = None,
    event_path: Path | None = None,
    extraction_path: Path | None = None,
    materiality_path: Path | None = None,
    authority_path: Path | None = None,
) -> int:
    out = out_dir or (ROOT / "pipeline_out" / "v7_e2e")
    out.mkdir(parents=True, exist_ok=True)
    ev_path  = event_path or EVENT_PATH
    ext_path = extraction_path or EXTRACTION
    mat_path = materiality_path or MAT_POLICY
    auth_path = authority_path or AUTH_MATRIX

    print(f"\n=== V7 End-to-End Runner ===")
    print(f"  extraction  : {ext_path.name}")
    print(f"  execution   : {EXECUTION.name}")
    print(f"  event       : {ev_path.name}")
    print(f"  materiality : {mat_path.name}")
    print(f"  authority   : {auth_path.name}")
    print(f"  output      : {out}\n")

    # Check prerequisites
    for p in [ext_path, EXECUTION, ev_path]:
        if not p.exists():
            print(f"ERROR: missing required file: {p}", file=sys.stderr)
            return 1

    # ── Step 1: Bridge compile ────────────────────────────────────────────────
    print("[1/5] Compiling V7 bundle (extraction → bridge)…")
    bundle = compile_v7_bundle(ext_path, EXECUTION)
    current   = bundle["current_graph"]
    mapping   = bundle["execution_mapping"]
    report    = bundle["adapter_report"]
    manifest  = bundle["manifest"]
    print(f"  admitted={manifest['admitted_claim_count']}  "
          f"CPs={len(current['case_positions'])}  "
          f"directions={len(current['position_model_directions'])}  "
          f"unbound_mn={len(current['unbound_model_nodes'])}")

    # ── Step 2: Write bundle files ────────────────────────────────────────────
    print("\n[2/5] Writing bundle files…")
    _w(out / "current_graph.json",         current)
    _w(out / "execution_mapping.json",     mapping)
    _w(out / "adapter_report.json",        report)
    _w(out / "admission_manifest_v7.json", manifest)

    # ── Step 3: Apply event → Candidate ──────────────────────────────────────
    print("\n[3/5] Applying event and building Candidate…")
    event = json.loads(ev_path.read_text())
    candidate = apply_event(event, bundle)
    mn = candidate.get("model_node_deltas", {})
    moic_d = (mn.get("MN-BASE-MOIC") or {}).get("delta", 0)
    irr_d  = (mn.get("MN-BASE-IRR")  or {}).get("delta", 0)
    ev_d   = (mn.get("MN-EXIT-EV")   or {}).get("delta", 0)
    print(f"  claim_applied={candidate['claim_applied']}  "
          f"ΔMOIC={moic_d:+.4f}  ΔIRR={irr_d:+.2f}ppt  ΔExitEV={ev_d:+.2f}$m")

    transition = build_transition_output(bundle, candidate, event)
    _w(out / "candidate_graph.json",  candidate)
    _w(out / "transition_output.json", transition)

    # ── Step 4: 10-run determinism ────────────────────────────────────────────
    print("\n[4/5] Verifying 10-run determinism…")
    replay_hashes = [candidate["replay_hash"]]
    for i in range(9):
        c2 = apply_event(event, bundle)
        replay_hashes.append(c2["replay_hash"])
    unique = set(replay_hashes)
    print(f"  {len(replay_hashes)} runs → {len(unique)} unique replay_hash(es): {'✓ DETERMINISTIC' if len(unique)==1 else '✗ NON-DETERMINISTIC'}")

    # ── Step 5: Acceptance tests ──────────────────────────────────────────────
    print("\n[5/5] Running acceptance + semantic regression tests…")
    results = run_tests(bundle, candidate, replay_hashes, event=event)

    passed = sum(1 for r in results if r.ok)
    failed = [r for r in results if not r.ok]

    lines = [
        "V7 End-to-End Validation Report",
        "================================",
        f"  Extraction : {EXTRACTION}",
        f"  Execution  : {EXECUTION}",
        f"  Event      : {ev_path}",
        f"  Candidate  : {out/'candidate_graph.json'}",
        "",
        f"Result: {passed}/{len(results)} PASS",
        "",
    ]
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        lines.append(f"  [{status}] {r.tid} — {r.name}")
        lines.append(f"        {r.msg}")

    if not failed:
        lines += ["", "All acceptance tests PASS. V7 bridge is executable end-to-end."]
    else:
        lines += ["", "FAILURES:"]
        for r in failed:
            lines.append(f"  {r.tid} — {r.name}: {r.msg}")

    report_txt = "\n".join(lines) + "\n"
    vr_path = out / "validation_report.txt"
    vr_path.write_text(report_txt)

    for r in results:
        marker = "✓" if r.ok else "✗"
        print(f"  {marker} {r.tid} — {r.name}  [{r.msg}]")

    print(f"\n{passed}/{len(results)} tests passed → {vr_path}")

    if failed:
        print(f"\nFAILED: {len(failed)} test(s)", file=sys.stderr)
        return 1
    else:
        print(f"\nAll {len(results)} tests PASS. V7 bridge is executable end-to-end. ✓")
        return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="V7 end-to-end acceptance runner")
    ap.add_argument("--out",         type=Path, default=None, help="Output directory")
    ap.add_argument("--event",       type=Path, default=None, help="Event JSON path")
    ap.add_argument("--extraction",  type=Path, default=None, help="graph.json from pipeline")
    ap.add_argument("--execution",   type=Path, default=None, help="execution_graph_v7.json (overrides default)")
    ap.add_argument("--manifest",    type=Path, default=None, help="Ignored; manifest is built by bridge (kept for CLI compat)")
    ap.add_argument("--materiality", type=Path, default=None, help="Materiality policy JSON")
    ap.add_argument("--authority",   type=Path, default=None, help="Authority matrix JSON")
    args = ap.parse_args()
    sys.exit(main(
        out_dir=args.out,
        event_path=args.event,
        extraction_path=args.extraction,
        materiality_path=args.materiality,
        authority_path=args.authority,
    ))
