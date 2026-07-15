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


if __name__ == "__main__":
    print(f"transitions: {len(transitions())} (final + v1 aliases)")
    print(f"permission policies: {len(permission_policies())}, authority actions: {len(authority_actions())}")
    print(f"automatable register: {len(automatable_register())} activities, classes: {sorted(automatable_classes())}")
    print(f"repair precedence: {' > '.join(repair_precedence()[:5])} …")
