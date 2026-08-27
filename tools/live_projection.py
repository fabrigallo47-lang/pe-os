#!/usr/bin/env python3
"""
live_projection — a V17 projection containing only extraction output.

The earlier projection blended three sources: a bundle built earlier, the vault,
and the package fixture. Provenance flags told you which was which, per section,
which is better than hiding it but still leaves a screen you have to interrogate
before you can trust it.

This builds from the live store alone. A section no ingest produced is omitted,
not zero-filled and not borrowed. If the store is empty the projection is empty,
and the UI shows an empty deal — which is the correct picture of having
extracted nothing.

Where a screen has no data, `absent` says so and why, so the gap reads as a gap
rather than as a rendering failure.
"""
from __future__ import annotations

import re
from typing import Any

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "record"


def _field(rec: dict, name: str):
    v = (rec.get("fields", {}).get(name) or {}).get("value")
    return v if isinstance(v, (int, float)) else None


def _evidence_rooms(claims: list[dict]) -> dict:
    """
    S05 and S06 from claims alone.

    Without the bridge there are no case positions, so "what the deal rests on"
    is grouped by the metric each claim measures — the coarsest honest grouping
    the extraction supports. Strength is the highest epistemic class present,
    which is a fact about the claims rather than a score.
    """
    by_metric: dict[str, list[dict]] = {}
    for c in claims:
        key = (c.get("metric") or c.get("subject") or "—").strip() or "—"
        by_metric.setdefault(key, []).append(c)

    rank = ["attested", "observed", "derived", "asserted"]
    sets = []
    for metric, group in by_metric.items():
        classes = {c.get("epistemic") or c.get("epistemic_class") or "asserted"
                   for c in group}
        strength = next((r for r in rank if r in classes), "asserted")
        valued = [c for c in group if c.get("value") not in (None, "")]
        sets.append({
            "id": f"FND-{re.sub(r'[^A-Za-z0-9]+', '-', metric).upper()[:28]}",
            "label": metric,
            "strength": strength,
            "economic": (f"{valued[0].get('value')} {valued[0].get('unit','')}".strip()
                         if valued else "—"),
            "members": [f"{c.get('claim_id','')} · "
                        f"{c.get('epistemic') or c.get('epistemic_class')}"
                        for c in group[:6]],
            "claim_count": len(group),
            "provenance": "extraction",
        })
    sets.sort(key=lambda s: (rank.index(s["strength"]), -s["claim_count"]))
    return {
        "title": "What the deal rests on",
        "subtitle": (f"{len(sets)} metriche estratte, raggruppate per ciò che "
                     f"misurano. Senza Case Position il raggruppamento è per "
                     f"metrica: è il più fine che l'estrazione da sola sostenga."),
        "sets": sets,
    }


def _unknowns_from_grounding(grounding: dict) -> dict:
    """
    S06 from the grounding queue.

    What is genuinely unknown after an extraction is what the gate could not
    ground: a perimeter that names a counterparty, a figure absent from its
    cited source. These are the open items the extraction itself produced.
    """
    queue = (grounding or {}).get("review_queue", [])
    items = []
    for i, f in enumerate(sorted(queue, key=lambda x: not x.get("blocking")), start=1):
        items.append({
            "id": f"UNK-{f.get('claim_id','')[:14]}-{f.get('code','')[:10]}",
            "rank": i,
            "label": f.get("statement") or f.get("detail", ""),
            "value": "blocking" if f.get("blocking") else "review",
            "closure": f.get("code", ""),
            "owner": "—",
            # The view keys its click target and subtitle off question_id. What
            # a finding is about here is the claim it was raised on, so that is
            # what goes there rather than a question id we do not have.
            "question_id": f.get("claim_id", ""),
            "claim_id": f.get("claim_id"),
            "locator": f.get("locator"),
            "provenance": "extraction",
        })
    blocking = sum(1 for f in queue if f.get("blocking"))
    return {
        "title": "Everything we still do not know",
        "subtitle": (f"{len(items)} rilievi del grounding gate, {blocking} bloccanti. "
                     f"Sono le cose che l'estrazione non è riuscita a fondare, "
                     f"non una stima del valore d'informazione."),
        "items": items[:200],
    }


def _scenario_lab(model: dict) -> dict | None:
    """
    S08 from the returns records the workbook ingest extracted.

    A scenario here is a record of the workbook's returns table — a row keyed by
    the case it describes — not a node id this code knows in advance. Nothing is
    named ahead of time, so a workbook with five cases shows five and a workbook
    with none shows none.
    """
    records = model.get("records", [])
    if not records:
        return None
    # The order the fields are shown in, and what to call them. Nothing is
    # renamed: these are the workbook's own field headers, kept so a figure on
    # screen can be matched to the column it came from.
    order = [("invested", "Sponsor invested", "$mm"),
             ("multiple", "Exit multiple", "x"),
             ("exit_ev", "Exit EV", "$mm"),
             ("net_debt", "Exit net debt", "$mm"),
             ("equity", "Exit equity", "$mm"),
             ("moic", "Gross MOIC", "x"),
             ("irr", "Gross XIRR", "%")]
    scenarios = []
    for rec in records:
        moic, irr = _field(rec, "moic"), _field(rec, "irr")
        if moic is None and irr is None:
            continue
        loc = {k: v.get("locator") for k, v in rec.get("fields", {}).items()}
        fields = []
        for key, label, unit in order:
            v = _field(rec, key)
            if v is None:
                continue
            reach = (rec.get("fields", {}).get(key) or {}).get("reach") or {}
            fields.append({
                "label": label, "unit": unit,
                "value": round(v * 100, 2) if unit == "%" else round(v, 3),
                "locator": loc.get(key, ""),
                # Whether a what-if on this figure could do anything. A field
                # the workbook pastes rather than computes gets no control,
                # because a control that cannot move its number is worse than
                # no control at all.
                "derivable": bool(reach.get("derivable")),
                "reach_role": reach.get("role", "unknown"),
                "reach_reason": reach.get("reason", ""),
                "drivers": reach.get("drivers", []),
            })
        scenarios.append({
            "id": _slug(rec["record"]), "label": rec["record"],
            "state": "extracted", "color": None, "drivers": [],
            "moic": round(moic, 3) if moic is not None else None,
            "irr": round(irr * 100, 2) if irr is not None else None,
            "irr_unit": "%",
            "debt": _field(rec, "net_debt"),
            "fields": fields,
            "markers": [], "sources": loc, "provenance": "extraction",
        })
    if not scenarios:
        return None
    derivable = sum(1 for s in scenarios for f in s["fields"] if f["derivable"])
    total = sum(len(s["fields"]) for s in scenarios)
    if derivable:
        note = (f"{len(scenarios)} casi dalla tabella dei ritorni. "
                f"{derivable} campi su {total} sono calcolati dal modello e "
                f"rispondono a un what-if; gli altri sono valori incollati.")
    else:
        note = (f"{len(scenarios)} casi dalla tabella dei ritorni. "
                f"Nessuno dei {total} campi è calcolato dal workbook: sono tutti "
                f"valori incollati, quindi nessun input del modello può muoverli "
                f"e non viene offerto alcun comando what-if.")
    return {"selected": scenarios[0]["id"], "scenarios": scenarios,
            "derivable_fields": derivable, "total_fields": total,
            "whatif_available": bool(derivable), "note": note}


def _arrivals(claims: list[dict], grounding: dict) -> dict:
    """
    S11-S13, built from claims the gate refuses to admit unchecked.

    The UI's two pending-review buttons are hard-coded to the keys "earnings"
    and "concentration", so real findings are supplied under those keys rather
    than editing the package's render.js.
    """
    by_id = {c.get("claim_id"): c for c in claims}
    queue = (grounding or {}).get("review_queue", [])
    blocking = [f for f in queue if f.get("blocking") and by_id.get(f.get("claim_id"))]
    scenes: dict[str, dict] = {}
    for key, f in zip(("earnings", "concentration"), blocking):
        c = by_id[f["claim_id"]]
        scenes[key] = {
            "event_id": f"EVENT-{key.upper()}-LIVE",
            "type": "SOURCE_TREATMENT",
            "label": f"Grounding: {f.get('code')}",
            "source_title": c.get("source_doc") or c.get("source_id") or "—",
            "source_passage": c.get("statement", ""),
            "locator": c.get("locator", ""),
            "definition": c.get("metric", "—"),
            "period": c.get("period") or "—",
            "perimeter": c.get("perimeter") or "—",
            "proposed_position": f.get("detail", ""),
            "scene_id": key,
            "synthetic": False,
            "claim_id": c.get("claim_id"),
            "provenance": "extraction",
        }
    return scenes


# Which V17 screen each absence darkens. The frontend should not have to know
# our vocabulary, so the mapping travels with the projection.
SCREEN_VIEWS = {
    "S01_fund_command": "fund-command",
    "S02_deal_command": "deal-command",
    "S03_work": "work",
    "S05_foundations": "foundations",
    "S06_unknowns": "unknowns",
    "S07_shadow_ic": "shadow-ic",
    "S08_scenario_lab": "scenario",
    "S09_artifacts": "artifacts",
    "S11_S13_change_review": "change",
    "S16_decision_room": "decision",
    "S17_execution_room": "execution",
    "S19_causal_replay": "replay",
}


def _skeleton() -> dict:
    """
    Every key the V17 views reach for, present and empty.

    The frontend replaces its whole deal object with this one, so a key it reads
    without checking — a drawer looking up a foundation by id — must exist even
    when the section is empty. Present-and-empty renders as nothing; absent
    throws.
    """
    return {
        "objective": {"statement": "", "deadline": ""},
        "branches": {"current": [], "working": [], "approved": []},
        "morning_delta": {"label": "", "from": "", "to": "", "source": ""},
        "next_best_work": {"label": "", "owner": "", "duration": "",
                           "reason": "", "unlocks": []},
        "command_suggestions": [],
        "rooms": {"foundations": {"sets": []}, "unknowns": {"items": []},
                  "shadowIC": {"theses": []}},
        "scenarioLab": {"selected": None, "scenarios": []},
        "decisionRoom": {}, "executionRoom": {},
        "replay": {"snapshots": []},
    }


def build(store) -> dict:
    """store: a LiveStore. Returns a projection containing only its contents."""
    claims = store.claims
    model = store.model
    grounding = store.grounding
    summary = store.summary()

    absent: dict[str, str] = {}
    deal: dict[str, Any] = {
        **_skeleton(),
        "case_id": "PROJECT-KEYSTONE",
        "name": "Project Keystone",
        "company": "",
        "question_spine": [],
        "registry": [
            {"id": f"REG-{i+1:03d}", "kind": s["kind"].upper(), "actor": "ingest",
             "time": s["ingested_at"][11:16], "label": f"Ingerito {s['source']}",
             "detail": s["digest"], "object_id": None, "provenance": "extraction"}
            for i, s in enumerate(store.manifest["sources"])
        ],
    }

    if claims:
        deal["rooms"]["foundations"] = _evidence_rooms(claims)
    elif summary["documents"]:
        # A document that produced nothing is a different situation from no
        # document at all, and collapsing the two hides a failed extraction.
        why = []
        for s in store.manifest["sources"]:
            if s["kind"] != "document" or s.get("claims_extracted"):
                continue
            pl = s.get("pipeline", {})
            failed = pl.get("chunks_failed", 0)
            why.append(f"{s['source']} ({failed}/{pl.get('chunks', 0)} chunk falliti)"
                       if failed else s["source"])
        absent["S05_foundations"] = (
            f"{summary['documents']} documenti ingeriti, 0 claim estratti"
            + (f": {', '.join(why)}" if why else ""))
    else:
        absent["S05_foundations"] = "nessun documento ingerito: non ci sono claim"

    if (grounding or {}).get("review_queue"):
        deal["rooms"]["unknowns"] = _unknowns_from_grounding(grounding)
    else:
        absent["S06_unknowns"] = "nessun rilievo del grounding gate"

    lab = _scenario_lab(model)
    if lab:
        deal["scenarioLab"] = lab
    else:
        absent["S08_scenario_lab"] = "nessun workbook ingerito, o ritorni non calcolati"

    events = _arrivals(claims, grounding)
    if not events:
        absent["S11_S13_change_review"] = "nessun claim bloccato dal gate da rivedere"

    # Screens this pipeline does not produce at all. Named, not filled.
    for screen, why in [
        ("S01_fund_command", "livello fondo: richiede più deal, fuori da una estrazione"),
        ("S02_deal_command", "la question spine viene dal registro domande, non dall'estrazione"),
        ("S03_work", "orchestrazione del lavoro: non è output del compilatore"),
        ("S07_shadow_ic", "richiede rotte bull/bear e dissenso registrato"),
        ("S09_artifacts", "binding degli artefatti non prodotti"),
        ("S14_change_impact", "output del transition engine: serve un evento ammesso"),
        ("S15_action_frontier", "richiede un Candidate valido"),
        ("S16_decision_room", "policy e autorità: runtime"),
        ("S17_execution_room", "servizio di esecuzione: runtime"),
        ("S18_settled_state", "settlement: runtime"),
        ("S19_causal_replay", "replay bitemporale: runtime"),
    ]:
        absent.setdefault(screen, why)

    return {
        "schema_version": "frontend-projection/1.0",
        "package_version": "17.0.0",
        "disclosure": (
            f"Solo output di estrazione. {summary['documents']} documenti e "
            f"{summary['workbooks']} workbook ingeriti: {summary['claims']} claim, "
            f"{summary['bindings']} binding, {summary['cells']} celle. "
            f"Nessun dato di fixture."
            if not store.is_empty else
            "Nessuna sorgente ingerita. La projection è vuota di proposito."
        ),
        "fund": {"id": "", "name": "", "date": "", "situations": [],
                 "morning_delta": []},
        "deal": deal,
        "events": events,
        "absent": absent,
        "absent_views": {SCREEN_VIEWS[k]: v for k, v in absent.items()
                         if k in SCREEN_VIEWS},
        # An empty screen is more useful when it says where the data did go.
        "available_views": ["registry"] + sorted(
            v for k, v in SCREEN_VIEWS.items() if k not in absent),
        "extraction": summary,
        "sources": store.manifest["sources"],
    }
