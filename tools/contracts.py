#!/usr/bin/env python3
"""Machine-contract loader (PR_030): the final spec package is data, not documentation.

Single access point for: the final state machine (46 transitions), the permission
grid (877 policies), authority actions, the human-vs-automatable register, and the
enforce-vs-configure register. Nothing here hand-codes a rule the contracts state.
"""
from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINAL = ROOT / "sources" / "domain-contracts-final"
V1 = ROOT / "sources" / "workflow-backbone-v1"
KERNEL = ROOT / "sources" / "process-kernel"

# Enforcement class hierarchy: AXIOM > ENFORCE > CONFIGURE > SUGGEST
_ENFORCEMENT_RANK = {"AXIOM": 4, "ENFORCE": 3, "CONFIGURE": 2, "SUGGEST": 1}
_ENFORCEMENT_LABEL = {
    "AXIOM": "HARD_GATE",      # schema/logic invariant — non-configurable
    "ENFORCE": "REQUIRED",     # empirically universal — artifact may vary, function may not
    "CONFIGURE": "CONFIGURABLE",  # firm-editable within bounds
    "SUGGEST": "ADVISORY",     # conventional artifact — substitutable
}


@lru_cache(maxsize=None)
def _load(name: str):
    return json.loads((FINAL / name).read_text(encoding="utf-8"))


def state_machine() -> dict:
    return _load("state_machine_final.json")


def transitions() -> list[dict]:
    """Unified transition table: final contracts first, v1 rows kept as legacy
    aliases so pre-existing event kinds still replay. Normalized shape:
    {id, from, to, triggers[], guard, authority}."""
    out = []
    for t in state_machine()["transitions"]:
        out.append({
            "id": t["transition_id"],
            "from": t.get("source_state") or "START",
            "to": t["target_state"],
            "triggers": [t["trigger_event_type"]],
            "guard": t.get("guard_predicate", ""),
            "authority": (t.get("authority_rule") or {}).get("action_type"),
            "source": "final",
        })
    with open(V1 / "state_transitions_v1.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append({
                "id": r["id"], "from": r["from"], "to": r["to"],
                "triggers": [x.strip() for x in r["trigger_event"].split(" or ")],
                "guard": r["guard_condition"], "authority": None, "source": "v1-alias",
            })
    return out


def repair_precedence() -> list[str]:
    pr = state_machine()["primary_state_resolution"]
    seq = pr["precedence_when_repairing"] if isinstance(pr, dict) else pr[0].get("precedence_when_repairing", "")
    return [s.strip() for s in str(seq).split(">")]


def automatable_register() -> list[dict]:
    return _load("epistemic_schemas_final.json")["human_vs_automatable_register"]


def workstream_schema(ws_id: str) -> dict | None:
    """The epistemic 'skill' for a workstream: governing question, what it seeks,
    sufficiency rules. Injected into that agent's prompt — the harness."""
    for s in _load("epistemic_schemas_final.json")["workstream_schemas"]:
        if s.get("workstream_id") == ws_id:
            return s
    return None


def reasoning_operators() -> list[dict]:
    return _load("epistemic_schemas_final.json")["reasoning_operators"]


def permission_policies() -> list[dict]:
    return _load("permission_authority_model_final.json")["permission_policies"]


def authority_actions() -> list[dict]:
    return _load("permission_authority_model_final.json")["authority_actions"]


def permitted(entity: str, action: str, role: str | None = None) -> dict | None:
    """PR_019: permission evaluated independently from authority. Returns the first
    matching policy, or None — and None means NOT permitted (default-deny)."""
    for p in permission_policies():
        if p["object_entity_id"] == entity and p["action"] == action \
                and (role is None or p["subject_role_id"] == role):
            return p
    return None


def authority_required(action_type: str) -> dict | None:
    """Whether an authority action gates this operation. Non-None ⇒ a human
    authority record is required; agents must stop."""
    for a in authority_actions():
        if action_type.lower() in a["authority_action"].lower() \
                or a.get("authority_action_id") == action_type:
            return a
    return None


def agent_activity(activity_id: str) -> dict | None:
    """Bind an agent to its contract row in the human-vs-automatable register."""
    for a in automatable_register():
        if a["activity_id"] == activity_id:
            return a
    return None


def automatable_classes() -> set[str]:
    return {a["automation_class"] for a in automatable_register()}


# ---------------------------------------------------------------------------
# Process kernel (P3) — edge classifications and macro flows
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def kernel_edges() -> tuple[dict, ...]:
    """Load process-kernel edge classifications.

    Returns a tuple (hashable for lru_cache) of dicts, each with:
      edge_id, source_node, target_node, kernel_treatment,
      final_classification, enforcement_class (HARD_GATE/REQUIRED/CONFIGURABLE/ADVISORY),
      enforcement_rank (4=AXIOM > 3=ENFORCE > 2=CONFIGURE > 1=SUGGEST)
    """
    path = KERNEL / "edge_classification_engineering.csv"
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            treatment = r.get("kernel_treatment", "").strip()
            rows.append({
                "edge_id": r.get("edge_id", "").strip(),
                "source_node": r.get("source_node", "").strip(),
                "target_node": r.get("target_node", "").strip(),
                "edge_label": r.get("edge_label", "").strip(),
                "relation_type": r.get("relation_type", "").strip(),
                "kernel_treatment": treatment,
                "final_classification": r.get("final_classification", "").strip(),
                "archetype_condition": r.get("archetype_condition", "").strip(),
                "confidence": r.get("confidence", "").strip(),
                "enforcement_class": _ENFORCEMENT_LABEL.get(treatment, treatment),
                "enforcement_rank": _ENFORCEMENT_RANK.get(treatment, 0),
            })
    return tuple(rows)


@lru_cache(maxsize=None)
def macro_flow(flow_id: str = "F01") -> tuple[dict, ...]:
    """Load process-kernel macro flow for a given flow_id (default: lead-sponsor F01).

    Returns sequence of steps ordered by sequence_order, each with:
      component_id, component_type (NODE/GATE/LOOP/WORKSTREAM/FEEDBACK),
      description, kernel_treatment, enforcement_class, enforcement_rank,
      editable_elements, locked_elements, source_edge_ids
    """
    path = KERNEL / "macro_flows_engineering.csv"
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("flow_id", "").strip() != flow_id:
                continue
            treatment = r.get("kernel_treatment", "").strip()
            rows.append({
                "component_id": r.get("component_id", "").strip(),
                "component_type": r.get("component_type", "").strip(),
                "description": r.get("description", "").strip(),
                "sequence_order": int(r.get("sequence_order", 0) or 0),
                "kernel_treatment": treatment,
                "archetype_condition": r.get("archetype_condition", "").strip(),
                "editable_elements": r.get("editable_elements", "").strip(),
                "locked_elements": r.get("locked_elements", "").strip(),
                "source_edge_ids": r.get("source_edge_ids", "").strip(),
                "enforcement_class": _ENFORCEMENT_LABEL.get(treatment, treatment),
                "enforcement_rank": _ENFORCEMENT_RANK.get(treatment, 0),
            })
    rows.sort(key=lambda r: r["sequence_order"])
    return tuple(rows)


def kernel_gates_hard() -> list[dict]:
    """Return only AXIOM edges (non-configurable hard gates)."""
    return [e for e in kernel_edges() if e["kernel_treatment"] == "AXIOM"]


def kernel_gates_required() -> list[dict]:
    """Return AXIOM + ENFORCE edges (mandatory steps, function may not be skipped)."""
    return [e for e in kernel_edges() if e["enforcement_rank"] >= 3]


def flow_step_enforcement(component_id: str, flow_id: str = "F01") -> dict | None:
    """Return the enforcement record for a macro flow step by component_id."""
    for step in macro_flow(flow_id):
        if step["component_id"] == component_id:
            return step
    return None


# Map from our lifecycle state prefix to kernel macro flow component IDs
# (the steps that MUST be evidenced before advancing past this state)
_STATE_TO_KERNEL_GATES: dict[str, list[str]] = {
    "S0": ["LS-02"],                     # initial assessment (ENFORCE) before any commitment
    "S1": ["LS-02", "LS-03"],            # initial assessment + pursue gate (AXIOM)
    "S2": ["LS-02"],                     # case ingestion: initial assessment must exist
    "S3": ["LS-02"],                     # screening: same
    "S4": ["LS-06"],                     # diligence loop (CONFIGURE) — firm-editable depth
    "S5": ["LS-06", "LS-07", "LS-08"],   # diligence active → final synthesis (ENFORCE)
    "S6": ["LS-08", "LS-09"],            # underwriting → valid authority gate (CONFIGURE)
    "S7": ["LS-09"],                     # IC decision: valid authority gate (CONFIGURE)
    "S8": ["LS-10"],                     # execution: signing/binding commitment (AXIOM)
    "S9": ["LS-11", "LS-12"],            # closing: readiness gate + funding (AXIOM)
    "S10": ["LS-13", "LS-14"],           # monitoring loop (CONFIGURE)
    "S11": ["LS-14"],                    # reunderwriting: part of monitoring loop
    "S12": ["LS-15"],                    # exit: exit authority gate (CONFIGURE)
}


def gates_for_state(state: str) -> list[dict]:
    """Return kernel flow steps that are mandatory checkpoints for the given lifecycle state.

    Only returns AXIOM and ENFORCE items (hard requirements)."""
    prefix = state.split("_")[0] if "_" in state else state[:2]
    component_ids = _STATE_TO_KERNEL_GATES.get(prefix, [])
    return [s for s in macro_flow("F01")
            if s["component_id"] in component_ids and s["enforcement_rank"] >= 3]


if __name__ == "__main__":
    print(f"transitions: {len(transitions())} (final + v1 aliases)")
    print(f"permission policies: {len(permission_policies())}, authority actions: {len(authority_actions())}")
    print(f"automatable register: {len(automatable_register())} activities, classes: {sorted(automatable_classes())}")
    print(f"repair precedence: {' > '.join(repair_precedence()[:5])} …")
    print()
    print("── Process kernel ──")
    edges = kernel_edges()
    from collections import Counter
    by_class = Counter(e["enforcement_class"] for e in edges)
    print(f"kernel edges: {len(edges)} total — {dict(by_class)}")
    print(f"hard gates (AXIOM): {[e['edge_id'] for e in kernel_gates_hard()]}")
    print(f"required (ENFORCE): {[e['edge_id'] for e in kernel_gates_required() if e['kernel_treatment']=='ENFORCE']}")
    flow = macro_flow("F01")
    print(f"lead-sponsor macro flow: {len(flow)} steps (F01)")
    for step in flow[:5]:
        print(f"  [{step['sequence_order']:2}] {step['component_id']:8} {step['enforcement_class']:15} {step['description'][:55]}")
