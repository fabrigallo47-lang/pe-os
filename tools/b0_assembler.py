#!/usr/bin/env python3
"""B0 Assembler — reads vault data and emits the B0-compliant JSON state object.

The B0 contract (B0_RENDER_CONTRACT.md) defines what the frontend expects.
This module derives that object from the canonical vault + SQLite index.

Usage:
    python3 tools/b0_assembler.py <deal-id>          # prints JSON
    python3 tools/b0_assembler.py <deal-id> --pretty # pretty-printed
    from tools.b0_assembler import assemble           # programmatic
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import indexer

DB = indexer.DB
VAULT = indexer.VAULT


# ─── lifecycle state → phase spine position ────────────────────────────────────

PHASE_MAP = {
    "S0_INTAKE":                  0,
    "S1_ACCESS_CLEARANCE":        0,
    "S2_CASE_INGESTION":          0,
    "S3_SCREENING_ASSESSMENT":    0,
    "S4_QUESTION_PLANNING":       1,
    "S5_DILIGENCE_ACTIVE":        1,
    "S6_UNDERWRITING_VALUATION":  2,
    "S7_INVESTMENT_DECISION":     3,
    "S8_EXECUTION_DOCUMENTATION": 4,
    "S9_CLOSING_ADMINISTRATION":  4,
    "S10_MONITORING":             5,
    "S11_REUNDERWRITING":         5,
    "S12_EXIT_REALIZATION":       5,
    "SX_TERMINATED_STALLED_DECLINED": 6,
}

PHASE_SPINE = [
    {"id": "screen",     "label": "Screen"},
    {"id": "diligence",  "label": "Diligence"},
    {"id": "underwrite", "label": "Underwrite", "gate": True},
    {"id": "decide",     "label": "Decide",     "gate": True},
    {"id": "execute",    "label": "Execute"},
    {"id": "own",        "label": "Own"},
]

WORKSTREAM_LABELS = {
    "commercial":      "Commercial DD",
    "commercial_market": "Commercial DD",
    "financial_qoe":   "Financial DD",
    "financial":       "Financial DD",
    "operational":     "Operational DD",
    "operations":      "Operational DD",
    "management":      "Management",
    "legal":           "Legal",
    "tax":             "Tax",
    "financing":       "Financing",
    "credit":          "Credit",
    "governance":      "Governance",
}

# Causal dependency graph topology — subject slugs → node descriptors.
# Values are filled in from vault claims at runtime.
GRAPH_TOPOLOGY = [
    {
        "id": "source", "label": "Source evidence", "kind": "evidence",
        "upstream": [], "downstream": ["ebitda"],
        "subjects": ["QoE-normalized EBITDA", "seller-adjusted EBITDA", "initial assessment information basis"],
        "formula": "Independent third-party source",
    },
    {
        "id": "ebitda", "label": "Firm EBITDA", "kind": "metric",
        "upstream": ["source"], "downstream": ["debt", "lender"],
        "subjects": ["firm-underwritten EBITDA", "opening firm EBITDA", "EBITDA adjustment supportability"],
        "formula": "QoE EBITDA − firm reserves",
    },
    {
        "id": "debt", "label": "Debt capacity", "kind": "model",
        "upstream": ["ebitda"], "downstream": ["equity"],
        "subjects": ["first-lien opening debt", "opening net debt"],
        "formula": "Firm EBITDA × leverage multiple",
    },
    {
        "id": "equity", "label": "Sponsor equity", "kind": "model",
        "upstream": ["debt"], "downstream": ["irr"],
        "subjects": ["sponsor initial cash equity", "opening equity after transaction expense"],
        "formula": "EV − debt − fees",
    },
    {
        "id": "irr", "label": "Base IRR / MOIC", "kind": "model",
        "upstream": ["equity"], "downstream": ["ceiling"],
        "subjects": ["sponsor gross MOIC and XIRR - Standalone Base", "opening net leverage ratio"],
        "formula": "Return on sponsor equity at exit",
    },
    {
        "id": "ceiling", "label": "Model price ceiling", "kind": "authority",
        "upstream": ["irr"], "downstream": ["ic", "offer"],
        "subjects": ["enterprise value", "exit multiple assumption"],
        "formula": "Firm EBITDA × exit multiple",
    },
    {
        "id": "lender", "label": "Lender case", "kind": "model",
        "upstream": ["ebitda"], "downstream": ["ic"],
        "subjects": ["lender covenant EBITDA basis", "covenant limits on add-backs, cash netting, acquisition capacity and minimum liquidity"],
        "formula": "Debt + covenant branch on accepted definitions",
    },
    {
        "id": "ic", "label": "IC basis", "kind": "decision",
        "upstream": ["ceiling", "lender"], "downstream": [],
        "subjects": ["firm initial assessment recommendation", "IC decision"],
        "formula": "Decision basis after model + risk + authority",
    },
    {
        "id": "offer", "label": "Offer authority", "kind": "decision",
        "upstream": ["ceiling"], "downstream": [],
        "subjects": ["enterprise value"],
        "formula": "Current offer vs model ceiling",
    },
]

PROPAGATION_ORDER = ["source", "ebitda", "debt", "equity", "irr", "ceiling", "lender", "ic", "offer"]


def _read_frontmatter(text: str) -> dict:
    import yaml
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except Exception:
        return {}


def _read_deal_md(deal: str) -> dict:
    path = VAULT / "deals" / deal / "deal.md"
    if not path.exists():
        return {}
    return _read_frontmatter(path.read_text(encoding="utf-8"))


def _deal_objects(con: sqlite3.Connection, deal: str, obj_type: str) -> list[dict]:
    rows = con.execute(
        "SELECT frontmatter, title FROM nodes WHERE type=? AND deal=?", (obj_type, deal)
    ).fetchall()
    out = []
    for fm_raw, title in rows:
        d = json.loads(fm_raw)
        if title:
            d.setdefault("title", title)
        out.append(d)
    return out


def _best_value(claims: list[dict], subjects: list[str]) -> str | None:
    """Pick the most epistemically strong value for any of the given subjects."""
    priority = {"attested": 0, "observed": 1, "derived": 2, "asserted": 3}
    candidates = [c for c in claims if c.get("subject") in subjects]
    if not candidates:
        return None
    candidates.sort(key=lambda c: priority.get(c.get("epistemic", "asserted"), 9))
    return str(candidates[0].get("value", ""))


def _build_workstreams(questions: list[dict]) -> list[dict]:
    """Derive workstream summaries from questions."""
    by_ws: dict[str, list] = {}
    for q in questions:
        ws = q.get("target-workstream") or q.get("workstream") or "other"
        by_ws.setdefault(ws, []).append(q)

    result = []
    for ws_id, qs in by_ws.items():
        total = len(qs)
        resolved = sum(1 for q in qs if q.get("state") == "resolved")
        critical_open = [q for q in qs if q.get("critical") and q.get("state") in ("open", "reducing")]

        # Current question = first critical open, else first open, else last resolved
        current_q = None
        for q in qs:
            if q.get("critical") and q.get("state") in ("open", "reducing"):
                current_q = q
                break
        if not current_q:
            for q in qs:
                if q.get("state") in ("open", "reducing"):
                    current_q = q
                    break

        status = "complete"
        if critical_open:
            status = "blocked"
        elif any(q.get("state") in ("open", "reducing") for q in qs):
            status = "active"

        label = WORKSTREAM_LABELS.get(ws_id, ws_id.replace("-", " ").title())
        current_text = ""
        if current_q:
            title_line = re.search(r"^#\s+(.+)$", current_q.get("title", ""), re.MULTILINE)
            current_text = current_q.get("title") or ""
        elif qs:
            current_text = qs[-1].get("title") or ""

        result.append({
            "id": ws_id,
            "label": label,
            "status": status,
            "question": current_text[:120],
            "progress": int((resolved / total) * 100) if total else 0,
        })

    return sorted(result, key=lambda w: list(WORKSTREAM_LABELS.keys()).index(w["id"])
                  if w["id"] in WORKSTREAM_LABELS else 99)


def _build_graph(claims: list[dict], lifecycle_state: str) -> dict:
    """Build the causal dependency graph from vault claims."""
    nodes = []
    for topo in GRAPH_TOPOLOGY:
        value = _best_value(claims, topo["subjects"]) or "—"
        # Determine epistemic class from the winning claim
        priority = {"attested": 0, "observed": 1, "derived": 2, "asserted": 3}
        candidates = [c for c in claims if c.get("subject") in topo["subjects"]]
        candidates.sort(key=lambda c: priority.get(c.get("epistemic", "asserted"), 9))
        ep_class = candidates[0].get("epistemic", "derived") if candidates else "derived"

        # Determine staleness: any upstream claim marked stale → this node stale
        any_stale = any(c.get("stale") for c in candidates)

        node = {
            "id": topo["id"],
            "label": topo["label"],
            "kind": topo["kind"],
            "value": value,
            "evidenceClass": ep_class,
            "status": "stale" if any_stale else "current",
            "formula": topo["formula"],
            "upstream": topo["upstream"],
            "downstream": topo["downstream"],
        }
        nodes.append(node)

    # Propagate staleness downstream in topological order
    stale_ids = {n["id"] for n in nodes if n["status"] == "stale"}
    for node_id in PROPAGATION_ORDER:
        node = next((n for n in nodes if n["id"] == node_id), None)
        if node and any(up in stale_ids for up in node["upstream"]):
            node["status"] = "stale"
            stale_ids.add(node_id)

    edges = []
    for topo in GRAPH_TOPOLOGY:
        for ds in topo["downstream"]:
            edges.append([topo["id"], ds])

    return {
        "nodes": nodes,
        "edges": edges,
        "propagationOrder": PROPAGATION_ORDER,
    }


def _build_state_stack(claims: list[dict], events: list[dict], lifecycle_state: str) -> dict:
    """Derive the three-slot state stack from vault data."""
    # Approved = last IC/investment decision event
    ic_events = [e for e in events if e.get("kind") in (
        "IC_APPROVED", "SCREENING_APPROVED", "FINAL_MODEL_APPROVED_FOR_IC", "EXIT_APPROVED"
    )]
    ic_events.sort(key=lambda e: str(e.get("at", "")))

    # EV
    ev = _best_value(claims, ["enterprise value"]) or "—"

    if ic_events:
        last_ic = ic_events[-1]
        approved = {
            "label": "Gate · " + last_ic["kind"].replace("_", " ").title(),
            "value": f"EV {ev}",
            "asOf": str(last_ic.get("at", "")),
        }
    else:
        approved = {
            "label": "Pending gate decision",
            "value": f"EV {ev}",
            "asOf": "",
        }

    # Current = most recent significant claim
    firm_ebitda = _best_value(claims, ["firm-underwritten EBITDA", "opening firm EBITDA"]) or "—"
    qoe_ebitda = _best_value(claims, ["QoE-normalized EBITDA"]) or "—"
    current = {
        "label": "Latest evidence",
        "value": f"Firm EBITDA {firm_ebitda}",
        "asOf": datetime.now(tz=timezone.utc).isoformat(),
    }

    # Working = model in progress
    debt = _best_value(claims, ["first-lien opening debt"]) or "—"
    irr_val = _best_value(claims, ["sponsor gross MOIC and XIRR - Standalone Base"]) or "—"
    working = {
        "label": "Working model",
        "value": f"Debt {debt} · return {irr_val}",
        "asOf": datetime.now(tz=timezone.utc).isoformat(),
    }

    return {"approved": approved, "current": current, "working": working}


def _build_source_event(events: list[dict]) -> dict | None:
    """Most recent artifact arrival."""
    arrivals = [e for e in events if e.get("kind") == "ARTIFACT_ARRIVED"]
    if not arrivals:
        return None
    arrivals.sort(key=lambda e: str(e.get("at", "")))
    last = arrivals[-1]
    return {
        "title": last.get("relates-to", ["Artifact"])[0] if last.get("relates-to") else "Artifact",
        "received": str(last.get("at", "")),
        "workstream": "—",
        "evidenceClass": "observed",
    }


def _build_contradiction(claims: list[dict]) -> dict | None:
    """First unresolved contradiction (multi-value subject)."""
    by_subject: dict[str, list] = {}
    for c in claims:
        subj = c.get("subject")
        if subj:
            by_subject.setdefault(subj, []).append(c)

    for subject, cs in by_subject.items():
        values = {str(c.get("value")) for c in cs}
        if len(values) > 1:
            items = []
            for c in cs[:4]:
                items.append({
                    "class": c.get("epistemic", "asserted"),
                    "label": str(c.get("value", ""))[:60],
                    "value": str(c.get("value", "")),
                    "detail": c.get("id", ""),
                })
            return {
                "question": f"Which value for '{subject}' is correct?",
                "items": items,
            }
    return None


def _build_history(events: list[dict]) -> list[dict]:
    """Timeline of significant events for the history rail."""
    kind_to_label = {
        "DEAL_REGISTERED":        "Deal registered",
        "ARTIFACT_ARRIVED":       "Artifact arrived",
        "CONTRADICTION_FLAGGED":  "Contradiction flagged",
        "SCREENING_APPROVED":     "Screening approved",
        "WORKSTREAMS_ASSIGNED":   "Workstreams assigned",
        "IC_APPROVED":            "IC approved",
        "DOCUMENTS_SIGNED":       "Documents signed",
        "EXPOSURE_OPENED":        "Exposure opened",
        "EXIT_APPROVED":          "Exit approved",
        "COVENANT_BREACH_DETECTED": "Covenant breach detected",
    }
    result = []
    seen_kinds = set()
    for ev in events:
        kind = ev.get("kind", "")
        label = kind_to_label.get(kind)
        if not label:
            continue
        # Deduplicate artifact arrivals (just show count)
        if kind == "ARTIFACT_ARRIVED" and kind in seen_kinds:
            continue
        seen_kinds.add(kind)
        at = str(ev.get("at", ""))[:10]
        ep = "observed" if kind in ("ARTIFACT_ARRIVED",) else (
            "attested" if kind in ("IC_APPROVED", "SCREENING_APPROVED", "EXIT_APPROVED") else "derived"
        )
        result.append({"date": at, "event": label, "evidenceClass": ep})
    return result


def _current_objective(lifecycle_state: str, questions: list[dict]) -> str:
    """Derive current objective from lifecycle state."""
    objectives = {
        "S0_INTAKE":                  "Register the deal and load initial materials.",
        "S1_ACCESS_CLEARANCE":        "Obtain confidential access and clear CIM.",
        "S2_CASE_INGESTION":          "Index case materials and map key claim sources.",
        "S3_SCREENING_ASSESSMENT":    "Assess deal screen and decide whether to proceed.",
        "S4_QUESTION_PLANNING":       "Define question set and assign workstreams.",
        "S5_DILIGENCE_ACTIVE":        "Work down the open questions and build the evidence base.",
        "S6_UNDERWRITING_VALUATION":  "Underwrite EBITDA basis and build the financing model.",
        "S7_INVESTMENT_DECISION":     "Resolve remaining open questions and seek IC approval.",
        "S8_EXECUTION_DOCUMENTATION": "Execute legal documents and close the transaction.",
        "S9_CLOSING_ADMINISTRATION":  "Complete closing administration and fund the deal.",
        "S10_MONITORING":             "Monitor performance against investment thesis and covenants.",
        "S11_REUNDERWRITING":         "Reunderwrite the position following a material event.",
        "S12_EXIT_REALIZATION":       "Manage exit process and realize proceeds.",
    }
    return objectives.get(lifecycle_state, "Advance the deal.")


def assemble(deal: str) -> dict:
    """Build and return the B0 state object for the given deal."""
    if not DB.exists():
        raise RuntimeError("no index — run `make index` first")

    con = sqlite3.connect(DB)
    dfm = _read_deal_md(deal)

    if not dfm:
        raise ValueError(f"deal '{deal}' not found in vault")

    questions = _deal_objects(con, deal, "question")
    claims = _deal_objects(con, deal, "claim")
    events = _deal_objects(con, deal, "event")
    events.sort(key=lambda e: str(e.get("at", "")))

    lifecycle_state = dfm.get("state", "S0_INTAKE")
    phase_idx = PHASE_MAP.get(lifecycle_state, 0)

    # Counts for core
    open_q = sum(1 for q in questions if q.get("state") in ("open", "reducing"))
    contras = {}
    for c in claims:
        subj = c.get("subject")
        if subj:
            contras.setdefault(subj, set()).add(str(c.get("value")))
    active_contras = sum(1 for vs in contras.values() if len(vs) > 1)

    # Resolve company name: wikilink [[slug]] → entity file → claim authors
    company = dfm.get("company", deal)
    if isinstance(company, str) and company.startswith("[["):
        slug = company.strip("[]")
        entity_path = VAULT / "entities" / "companies" / f"{slug}.md"
        if entity_path.exists():
            efm = _read_frontmatter(entity_path.read_text(encoding="utf-8"))
            company = (efm.get("legal-name") or efm.get("real-name")
                       or efm.get("aliases", [None])[0] or slug.replace("-", " ").title())
            # Strip parenthetical project nicknames
            company = re.sub(r"\s*\(Project\)", "", company).strip()
        else:
            company = slug.replace("-", " ").title()
    fund = dfm.get("fund", dfm.get("Fund", "—"))
    deal_type = dfm.get("deal-type") or dfm.get("dealType") or "buyout"
    title = dfm.get("title", f"Project {deal.title()}")

    graph = _build_graph(claims, lifecycle_state)
    workstreams = _build_workstreams(questions)
    state_stack = _build_state_stack(claims, events, lifecycle_state)

    result = {
        "id": deal,
        "title": title,
        "fund": fund,
        "dealType": deal_type,
        "asOf": datetime.now(tz=timezone.utc).isoformat(),
        "currentObjective": _current_objective(lifecycle_state, questions),
        "nextObjective": None,
        "phaseSpine": {
            "phases": PHASE_SPINE,
            "currentPhase": phase_idx,
        },
        "stateStack": state_stack,
        "core": {
            "label": f"PROJECT {deal.upper()}",
            "company": company,
            "currentOffer": _best_value(claims, ["enterprise value"]) or "—",
            "linkedObjects": len(claims),
            "activeDependencies": active_contras,
            "openQuestions": open_q,
        },
        "workstreams": workstreams,
        "agents": [
            {"id": "evidence",   "label": "Evidence Agent",  "role": "source ingestion + lineage", "status": "idle", "detail": f"{len(claims)} claims indexed"},
            {"id": "contradict", "label": "Contradiction",   "role": "conflict detection",          "status": "idle", "detail": f"{active_contras} open conflicts"},
            {"id": "lifecycle",  "label": "Lifecycle",       "role": "state machine + transitions", "status": "idle", "detail": lifecycle_state},
        ],
        "graph": graph,
        "sourceEvent": _build_source_event(events),
        "contradiction": _build_contradiction(claims),
        "changeSet": None,
        "decision": None,
        "history": _build_history(events),
    }
    return result


def propagate_staleness(graph: dict, changed_node_id: str) -> dict:
    """Return a copy of the graph with staleness propagated from changed_node_id downstream."""
    import copy
    g = copy.deepcopy(graph)
    nodes_by_id = {n["id"]: n for n in g["nodes"]}

    stale_ids = {changed_node_id}
    for node_id in g["propagationOrder"]:
        node = nodes_by_id.get(node_id)
        if node is None:
            continue
        if node_id in stale_ids:
            node["status"] = "stale"
        elif any(up in stale_ids for up in node.get("upstream", [])):
            node["status"] = "stale"
            stale_ids.add(node_id)
    return g


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("deal")
    p.add_argument("--pretty", action="store_true")
    args = p.parse_args()

    state = assemble(args.deal)
    indent = 2 if args.pretty else None
    print(json.dumps(state, indent=indent, ensure_ascii=False))
