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


def build_foundations(positions: list[dict], routes: list[dict],
                      spine: list[dict]) -> dict:
    """
    S05 "What the Deal Rests On": the minimal support sets under each position.

    A support route is a claim standing under a position, so the set of routes
    for a position is literally what that position rests on. Strength is read
    from the epistemic classes present: a position held up only by asserted
    claims is weaker than one an attestation reaches, and saying so needs no
    scoring model.
    """
    # Routes are nested on each position, which is the authoritative grouping.
    # The flat support_routes list carries no position field — only a route_id
    # like SR-CP-INTEGRATION-RISK-00 that would have to be parsed back apart.
    q_for_pos = {}
    for q in spine:
        for pid in q.get("position_ids", []):
            q_for_pos.setdefault(pid, q["id"])

    sets = []
    for pos in positions:
        pid = pos.get("position_id", "")
        rs = pos.get("support_routes", [])
        if not rs:
            continue
        classes = {r.get("epistemic_class", "asserted") for r in rs}
        if "attested" in classes:
            strength = "attested"
        elif "observed" in classes:
            strength = "observed"
        elif classes == {"derived"}:
            strength = "derived only"
        else:
            strength = "asserted only"
        unit = pos.get("unit") or ""
        val = pos.get("value")
        sets.append({
            "id": f"FND-{pid}",
            "label": pos.get("metric") or pid,
            "strength": strength,
            "economic": f"{val} {unit}".strip() if val is not None else "—",
            "members": [
                f"{r.get('claim_stable_id','')} · {r.get('epistemic_class','?')}"
                for r in rs[:6]
            ],
            "question_id": q_for_pos.get(pid),
            "position_id": pid,
            "provenance": "compiler",
        })
    sets.sort(key=lambda x: ("attested observed derived only asserted only"
                             .index(x["strength"])))
    return {
        "title": "What the deal rests on",
        "subtitle": (f"{len(sets)} posizioni, ciascuna con le sue support route reali. "
                     "La forza è la classe epistemica più alta presente, non un punteggio."),
        "sets": sets,
    }


def build_unknowns(spine: list[dict]) -> dict:
    """
    S06 "Everything We Still Do Not Know": the open questions, ordered.

    Ranking by value of information is not computed. The register records
    whether a question is critical and whether it is stale, which is real; an
    invented score would look like more than it is.
    """
    open_q = [q for q in spine if q.get("state") != "resolved"]
    items = []
    for i, q in enumerate(sorted(open_q, key=lambda x: (
            x["origin"]["binding"] != "critical", x["id"])), start=1):
        items.append({
            "id": f"UNK-{q['id']}",
            "rank": i,
            "label": q["label"],
            "value": "critical" if q["origin"]["binding"] == "critical" else "standard",
            "closure": "—",
            "owner": q.get("owner", "—"),
            "question_id": q["id"],
            "stale": q.get("stale", False),
            "provenance": "compiler",
        })
    return {
        "title": "Everything we still do not know",
        "subtitle": (f"{len(items)} domande aperte su {len(spine)} nel registro. "
                     "L'ordine segue il flag critical: il valore d'informazione "
                     "non è calcolato e non viene inventato."),
        "items": items,
    }


def load_events(deal: str, limit: int = 200) -> list[dict]:
    """S10 Registry: the append-only event trail already in the vault."""
    edir = VAULT / "deals" / deal / "events"
    if not edir.exists():
        return []
    out = []
    for path in sorted(edir.glob("*.md")):
        m = _FM.match(path.read_text(encoding="utf-8"))
        if not m:
            continue
        meta = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"')
        title = _H1.search(m.group(2))
        out.append({
            "id": meta.get("id", path.stem),
            "kind": meta.get("type", "event").upper(),
            "actor": meta.get("written-by", "—"),
            "time": (meta.get("at") or meta.get("timestamp") or "")[:16],
            "label": title.group(1).strip() if title else path.stem,
            "detail": meta.get("deal", ""),
            "object_id": meta.get("about") or meta.get("subject"),
            "provenance": "compiler",
        })
    return out[-limit:]


def build_events(claims: list[dict], event: dict | None,
                 grounding: list[dict] | None = None) -> dict:
    """
    S11-S13: the arriving change, built from a real extracted claim.

    The UI's two "pending review" buttons are hard-coded in its render.js as
    data-open-scene="earnings" and "concentration", and are not generated from
    the projection. So rather than edit their code, real content is supplied
    under the keys it already looks for.

    The fields a change-arrival needs — source_passage, locator, definition,
    period, perimeter — are exactly the fields extract_v2 puts on a claim. The
    two are the same object seen from different ends, which is why this reads
    as a mapping and not a construction.
    """
    by_id = {c.get("claim_id"): c for c in claims}
    scenes: dict[str, dict] = {}

    def scene(key: str, claim: dict, label: str, why: str) -> dict:
        return {
            "event_id": f"EVENT-{key.upper()}-LIVE",
            "type": "SOURCE_TREATMENT",
            "label": label,
            "source_title": claim.get("source_id", "—"),
            "source_passage": claim.get("statement", ""),
            "locator": claim.get("locator", ""),
            "definition": claim.get("metric") or claim.get("definition_id") or "—",
            "period": claim.get("period") or claim.get("period_iso") or "—",
            "perimeter": claim.get("perimeter", "—"),
            "proposed_position": why,
            "scene_id": key,
            "synthetic": False,
            "claim_id": claim.get("claim_id"),
            "epistemic_class": claim.get("epistemic_class"),
            "provenance": "compiler",
        }

    # earnings: the claim the correction event actually targets
    if event and event.get("trigger_claim_ids"):
        cid = event["trigger_claim_ids"][0]
        c = by_id.get(cid)
        if c:
            mut = (event.get("mutations") or [{}])[0]
            scenes["earnings"] = scene(
                "earnings", c,
                event.get("event") or "Correzione del claim di earnings",
                f"Correzione proposta: {mut.get('from')} → {mut.get('to')} "
                f"{mut.get('unit','')}. {event.get('note','')}".strip())

    # concentration: a claim the grounding gate refuses to admit unchecked
    for f in (grounding or []):
        if not f.get("blocking"):
            continue
        c = by_id.get(f.get("claim_id"))
        if not c:
            continue
        scenes["concentration"] = scene(
            "concentration", c,
            f"Grounding: {f.get('code')}",
            f"Il gate blocca questo claim: {f.get('detail','')}")
        break

    return scenes


SCENARIOS = [
    ("base",     "Standalone Base",     "MN-BASE-MOIC",          "MN-BASE-IRR"),
    ("downside", "Standalone Downside", "MN-DOWN-MOIC",          "MN-DOWN-IRR"),
    ("acq",      "Acquisition Base",    "MN-ACQ-MOIC",           "MN-ACQ-IRR"),
    ("combined", "Combined Risk",       "MN-COMBINED-RISK-MOIC", "MN-COMBINED-RISK-IRR"),
]


def build_scenario_lab(model_nodes: list[dict]) -> dict:
    """
    S08 Scenario Lab, from returns the workbook actually computes.

    These figures came out of extract_v3 evaluating the workbook's own formulas
    — the transcription in keystone_model.py carried none of them, so before
    that they were all None and this screen had nothing but fixture behind it.

    Units are inconsistent in the source: MOIC appears as both "x" and "RATIO",
    IRR as "%" and "PERCENT". They are normalised for display and the raw value
    is kept, because a screen that quietly rewrites a number is worse than one
    that shows two spellings.
    """
    by_id = {m.get("model_node_id"): m for m in model_nodes}

    def num(node_id: str):
        v = (by_id.get(node_id) or {}).get("value")
        return v if isinstance(v, (int, float)) else None

    debt = num("MN-DEBT")
    scenarios = []
    for key, label, moic_id, irr_id in SCENARIOS:
        moic, irr = num(moic_id), num(irr_id)
        if moic is None and irr is None:
            continue                      # absent, not zero
        scenarios.append({
            "id": key,
            "label": label,
            "state": "computed",
            "color": None,
            "drivers": [],                # driver series are not bound yet
            "moic": round(moic, 3) if moic is not None else None,
            "irr": round(irr * 100, 2) if irr is not None else None,
            "irr_unit": "%",
            "debt": debt,
            "markers": [],
            "sources": {"moic": moic_id, "irr": irr_id},
            "provenance": "compiler",
        })
    return {
        "selected": scenarios[0]["id"] if scenarios else None,
        "scenarios": scenarios,
        "note": (f"{len(scenarios)} scenari con ritorni calcolati dalle formule "
                 f"del workbook. I driver non sono ancora legati: la colonna "
                 f"resta vuota invece di essere riempita."),
    }


def build_projection(bundle: dict, deal: str = "keystone",
                     scaffold: dict | None = None,
                     grounding: list[dict] | None = None) -> dict:
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

    live_events = build_events(claims, bundle.get("event"), grounding)
    routes = cg.get("support_routes", [])
    foundations = build_foundations(positions, routes, spine)
    unknowns = build_unknowns(spine)
    registry_events = load_events(deal)

    scenario_lab = build_scenario_lab(model_nodes)
    rooms = dict(sd.get("rooms", {}))
    rooms["foundations"] = foundations          # S05, real
    rooms["unknowns"] = unknowns                # S06, real
    # shadowIC stays scaffold: it needs bull and bear routes with dissent, and
    # vault/deals/keystone/contradictions is empty, so there is nothing to build
    # it from that would not be invented.

    deal_obj = {
        "case_id": cg.get("case_id", ""),
        "name": cg.get("case_id", ""),
        "company": cg.get("company", ""),
        "question_spine": spine,
        # Product structures the compiler does not produce. Carried through so
        # the screens still render, and named as not ours.
        "rooms": rooms,
        "scenarioLab": scenario_lab if scenario_lab["scenarios"]
                       else sd.get("scenarioLab", {}),
        "decisionRoom": sd.get("decisionRoom", {}),
        "executionRoom": sd.get("executionRoom", {}),
        "replay": sd.get("replay", {}),
        "artifacts": sd.get("artifacts", []),
        "versions": sd.get("versions", []),
        "registry": registry_events,
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
        "events": live_events or scaffold.get("events", {}),
        "screens": {
            "S02_deal_command": "compiler",
            "S04_object_aperture": "compiler",
            "S05_foundations": "compiler",
            "S06_unknowns": "compiler",
            "S10_registry": "compiler",
            "S12_change_review_evidence": "compiler",
            "S13_change_review_treatment": "compiler",
            "S14_change_impact": "runtime (PANTA engine output, served by us)",
            "S01_fund_command": "package_fixture",
            "S03_work": "package_fixture",
            "S07_shadow_ic": "package_fixture (contradictions vuote nel vault)",
            "S08_scenario_lab": ("compiler (ritorni dal workbook; branching e "
                                 "what-if restano runtime)"
                                 if scenario_lab["scenarios"] else "runtime (Anto)"),
            "S09_artifacts": "package_fixture",
            "S11_change_arrival": "compiler" if live_events else "package_fixture",
            "S15_action_frontier": "package_fixture",
            "S16_decision_room": "runtime (Anto)",
            "S17_execution_room": "runtime (Anto)",
            "S18_settled_state": "runtime (Anto)",
            "S19_causal_replay": "runtime (Anto)",
        },
        "provenance": {
            "question_spine": "compiler",
            "foundations": "compiler",
            "unknowns": "compiler",
            "scenarioLab": "compiler" if scenario_lab["scenarios"] else "package_fixture",
            "registry": "compiler",
            "claims": "compiler",
            "case_positions": "compiler",
            "model_nodes": "compiler",
            "fund": "package_fixture",
            "rooms": "package_fixture",
            "scenarioLab": "package_fixture",
            "decisionRoom": "package_fixture",
            "executionRoom": "package_fixture",
            "replay": "package_fixture",
            "events": "compiler" if live_events else "package_fixture",
        },
        "compiler": {
            "claims": len(claims),
            "case_positions": len(positions),
            "model_nodes": len(model_nodes),
            "questions": len(questions),
            "support_routes": len(routes),
            "foundations_sets": len(foundations["sets"]),
            "open_questions": len(unknowns["items"]),
            "registry_events": len(registry_events),
        },
    }
