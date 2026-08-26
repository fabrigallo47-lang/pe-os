#!/usr/bin/env python3
"""
ui_projection — build the V17 frontend projection from what we actually own.

Why this exists
---------------
Handing the raw compiler bundle to the UI connects the API and changes nothing
on screen. engine.js only adopts a projection when it carries `fund`, `deal` or
`events`:

    return Boolean(projection.fund||projection.deal||projection.events);

A raw bundle becomes {compiler, transition} through the projection adapter, so
that check fails, `projectionSource` stays 'embedded', and every screen keeps
rendering the fixture while the status line says "connected". Connected and real
are not the same thing, and nothing in the UI distinguishes them.

What is ours and what is not
----------------------------
Measured against the shipped fixture:

  model_node_ids   18 of 18 cited by the UI exist in our bundle
  position_ids      0 of 24 — the fixture uses CP-001, we use CP-EBITDA-FIRM

So the model vocabulary is already shared with the runtime; position ids are
not, and the deal's product scaffolding — rooms, scenario lab, decision room,
execution room, replay — is not compiler output at all. Those are product
concepts the V17 package owns.

This therefore fills the compiler-owned parts from real data and marks
everything it did not produce, rather than quietly passing fixture material off
as ours. `provenance` on the payload says which is which, per section, so the
screen can be read for what it is.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "vault"

_FM = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)
_H1 = re.compile(r"^#\s+(.+)$", re.M)

WORKSTREAM_LABEL = {
    "financial": "Financial", "commercial": "Commercial", "legal": "Legal",
    "operational": "Operational", "tax": "Tax", "technology": "Technology",
}


def _read_question(path: Path) -> dict | None:
    m = _FM.match(path.read_text(encoding="utf-8"))
    if not m:
        return None
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    title = _H1.search(m.group(2))
    return {
        "id": meta.get("id", path.stem),
        "label": title.group(1).strip() if title else path.stem,
        "workstream": WORKSTREAM_LABEL.get(meta.get("target-workstream", ""),
                                           meta.get("target-workstream", "—")),
        "state": meta.get("state", "open"),
        "critical": meta.get("critical") == "true",
        "stale": meta.get("stale") == "true",
        "question_type": meta.get("question-type", "").strip("[]"),
    }


def load_questions(deal: str) -> list[dict]:
    qdir = VAULT / "deals" / deal / "questions"
    if not qdir.exists():
        return []
    out = [_read_question(p) for p in sorted(qdir.glob("*.md"))]
    return [q for q in out if q]


def _positions_for(question: dict, positions: list[dict]) -> list[str]:
    """
    Bind a question to positions by the words they share.

    Deliberately crude and deliberately visible: this is a proposal, not a
    resolved binding. The real binding belongs to the vault's bears-on links,
    which the question files carry as claim references rather than positions.
    """
    words = {w for w in re.findall(r"[a-z]{4,}", question["label"].lower())}
    hits = []
    for p in positions:
        pid = p.get("position_id", "")
        tokens = {t.lower() for t in re.findall(r"[A-Z]+", pid)}
        if tokens & {w.upper().lower() for w in words} or any(
            w in pid.lower() for w in words):
            hits.append(pid)
    return hits[:4]


def build_projection(bundle: dict, deal: str = "keystone",
                     scaffold: dict | None = None) -> dict:
    """
    bundle: {current_graph, execution_mapping, admission_manifest, transition_output}
    scaffold: the package fixture, used only for product structures we do not own.
    """
    cg = bundle.get("current_graph", {})
    positions = cg.get("case_positions", [])
    model_nodes = cg.get("model_nodes", [])
    claims = cg.get("claims", [])
    questions = load_questions(deal)

    spine = []
    for q in questions:
        spine.append({
            "id": q["id"].upper(),
            "label": q["label"],
            "workstream": q["workstream"],
            "owner": "—",
            "origin": {
                "entry_type": "Vault question",
                "source_type": "Deal question register",
                "label": q["question_type"] or "—",
                "source_ids": [q["id"]],
                "binding": "critical" if q["critical"] else "standard",
            },
            "question_ids": [q["id"]],
            "position_ids": _positions_for(q, positions),
            "model_node_ids": [],
            "state": q["state"],
            "stale": q["stale"],
            "provenance": "compiler",
        })

    scaffold = scaffold or {}
    sd = scaffold.get("deal", {})

    deal_obj = {
        "case_id": cg.get("case_id", ""),
        "name": cg.get("case_id", ""),
        "company": cg.get("company", ""),
        "question_spine": spine,
        # Product structures the compiler does not produce. Carried through so
        # the screens still render, and named as not ours.
        "rooms": sd.get("rooms", {}),
        "scenarioLab": sd.get("scenarioLab", {}),
        "decisionRoom": sd.get("decisionRoom", {}),
        "executionRoom": sd.get("executionRoom", {}),
        "replay": sd.get("replay", {}),
        "artifacts": sd.get("artifacts", []),
        "versions": sd.get("versions", []),
        "objective": sd.get("objective", ""),
        "branches": sd.get("branches", []),
        "morning_delta": sd.get("morning_delta", []),
        "next_best_work": sd.get("next_best_work", []),
        "command_suggestions": sd.get("command_suggestions", []),
    }

    return {
        "schema_version": "frontend-projection/1.0",
        "package_version": "17.0.0",
        "disclosure": (
            f"Compilato da {len(claims)} claim, {len(positions)} posizioni e "
            f"{len(model_nodes)} model node reali. Le stanze, lo Scenario Lab, "
            f"la Decision Room, l'Execution Room e il replay provengono dalla "
            f"fixture del pacchetto: non sono output del compilatore."
        ),
        "fund": scaffold.get("fund", {}),
        "deal": deal_obj,
        "events": scaffold.get("events", {}),
        "provenance": {
            "question_spine": "compiler",
            "claims": "compiler",
            "case_positions": "compiler",
            "model_nodes": "compiler",
            "fund": "package_fixture",
            "rooms": "package_fixture",
            "scenarioLab": "package_fixture",
            "decisionRoom": "package_fixture",
            "executionRoom": "package_fixture",
            "replay": "package_fixture",
            "events": "package_fixture",
        },
        "compiler": {
            "claims": len(claims),
            "case_positions": len(positions),
            "model_nodes": len(model_nodes),
            "questions": len(questions),
        },
    }
