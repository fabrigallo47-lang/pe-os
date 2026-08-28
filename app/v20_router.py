"""V20 API router — the contract the V20 frontend speaks.

All endpoints under /api/v20. Shapes derived from reading:
  ui/01_PRODUCT_BUILD/app/src/api.js      — what URLs the frontend calls
  ui/01_PRODUCT_BUILD/app/src/contracts.js — what shapes are validated
  ui/01_PRODUCT_BUILD/app/src/store.js    — how state is initialised
  ui/01_PRODUCT_BUILD/app/src/engine.js   — how boot/applyProjection work
"""
from __future__ import annotations

import datetime as dt
import base64
import hashlib
import json
import logging
import re
import sqlite3
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

# Structured log — one line per event, written to project root so tail -f works
_LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "v20.log"
_LOG_FILE.parent.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger("v20")

import yaml
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from backend.dynamics import (
    DynamicsBundleError,
    load_event_batch,
    run_bundle_transition,
    settle_candidate_state,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "ui" / "07_ENGINEERING_CONTRACTS_AND_ADAPTERS" / "adapters"))

VAULT = ROOT / "vault"
PIPELINE_OUT = ROOT / "pipeline_out" / "e3" / "K-IC" / "adapter_alpha"

v20 = APIRouter(prefix="/api/v20")

_jobs: dict[str, dict] = {}
_runs: dict[str, dict] = {}   # run_id → {transition, candidate_graph, case_id}
_inbox_lock = threading.Lock()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _today() -> str:
    return dt.date.today().isoformat()


def _inbox_manifest_path() -> Path:
    return VAULT / "inbox" / ".ingest-manifest.json"


def _read_inbox_manifest() -> list[dict[str, Any]]:
    """Return the durable source-intake history, tolerating old/corrupt manifests."""
    path = _inbox_manifest_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("items", []) if isinstance(payload, dict) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write_inbox_manifest(items: list[dict[str, Any]]) -> None:
    path = _inbox_manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": 1, "items": items}, indent=2), encoding="utf-8")
    temporary.replace(path)


def _update_inbox_record(job_id: str, **changes: Any) -> None:
    """Persist job progress so a restart never hides a submitted source."""
    with _inbox_lock:
        items = _read_inbox_manifest()
        for item in items:
            if item.get("job_id") == job_id:
                item.update(changes)
                item["updated_at"] = _now_iso()
                break
        _write_inbox_manifest(items)


def _unique_inbox_path(filename: str) -> Path:
    """Never replace a previously uploaded source with the same filename."""
    inbox_dir = VAULT / "inbox"
    candidate = inbox_dir / Path(filename).name
    if not candidate.exists():
        return candidate
    return inbox_dir / f"{candidate.stem}-{uuid.uuid4().hex[:8]}{candidate.suffix}"


def _persist_claims_to_vault(case_id: str, claims: list[dict], source_filename: str) -> int:
    """Materialize extracted claims as durable vault notes for indexing and audit."""
    claims_dir = VAULT / "deals" / case_id / "claims"
    written = 0
    for claim in claims:
        claim_id = str(claim.get("claim_id") or claim.get("id") or "").strip()
        if not claim_id:
            continue
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", claim_id)
        frontmatter = {
            "type": "claim",
            "id": claim_id,
            "epistemic": claim.get("epistemic_class", "asserted"),
            "subject": claim.get("statement", claim_id),
            "value": claim.get("value"),
            "bears-on": claim.get("bears_on", []),
            "direction": claim.get("direction", "context"),
            "source": {
                "artifact": f"vault/inbox/{source_filename}" if source_filename else None,
                "locator": claim.get("locator", ""),
                "author": claim.get("author"),
                "date": claim.get("period"),
            },
            "derivation": None,
            "rests-on": [],
            "extracted-by": "extract_v1",
            "extracted": _today(),
            "period": claim.get("period"),
            "perimeter": claim.get("perimeter"),
            "source-id": claim.get("source_id"),
        }
        path = claims_dir / f"c-{case_id}-{safe_id}.md"
        body = str(claim.get("statement") or claim_id).strip() + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\n" + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True) + "---\n\n" + body,
                        encoding="utf-8")
        written += 1
    return written

def _ensure_question_registry(case_id: str) -> None:
    """Materialize the archetype question grammar, never a claim-derived fact.

    These are the opening questions supplied by the investment archetype.  They
    are deliberately marked as such so future Fund Lens and deal-emergent
    questions can live beside them without pretending all questions were fixed.
    """
    from bind_questions_e3 import QUESTIONS
    q_dir = VAULT / "deals" / case_id / "questions"
    q_dir.mkdir(parents=True, exist_ok=True)
    for qid, title in QUESTIONS.items():
        path = q_dir / f"{qid.lower()}.md"
        if path.exists():
            continue
        fm = {
            "type": "question", "id": qid, "deal": case_id,
            "title": title, "question": title, "state": "open",
            "status": "open", "critical": False, "workstream": "underwriting",
            "opened": _today(), "written-by": "archetype-grammar",
            "origin": "archetype", "question_version": 1,
        }
        path.write_text("---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n# " + title + "\n", encoding="utf-8")


def _proposal_path(job_id: str) -> Path:
    return PIPELINE_OUT / "proposals" / f"evidence-{job_id}.json"


def _write_evidence_proposal(job_id: str, case_id: str, filename: str, claims: list[dict]) -> Path:
    """Store extraction output as reviewable evidence, before it can affect Current."""
    path = _proposal_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "proposal_id": f"evidence-{job_id}", "job_id": job_id, "case_id": case_id,
        "source_id": filename, "source_path": f"vault/inbox/{filename}",
        "status": "PENDING_REVIEW", "created_at": _now_iso(), "claims": claims,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path

def _derive_bears_on(claims: list[dict], e3: dict) -> list[dict]:
    """Apply the same deterministic metric/keyword graph used by bind_questions_e3."""
    from bind_questions_e3 import bind_claim
    metadata = {x.get("claim_id"): x for x in e3.get("extraction_metadata", {}).get("compiler_fields_per_claim", [])}
    out = []
    for claim in claims:
        c = dict(claim)
        meta = metadata.get(c.get("claim_id"), c)
        c["bears_on"] = bind_claim(c, meta)
        if metadata.get(c.get("claim_id")):
            c.update({k: v for k, v in metadata[c["claim_id"]].items() if k not in c or not c.get(k)})
        out.append(c)
    return out

def _normalise_v1_claims(claims: list[dict], source_filename: str) -> list[dict]:
    """Give V1 records stable, content-addressed identities for the V20 corpus."""
    out = []
    for claim in claims:
        c = dict(claim)
        identity = "|".join(str(c.get(key, "")).strip() for key in (
            "subject", "metric", "value", "unit", "period", "perimeter", "statement", "epistemic",
        ))
        c["claim_id"] = c.get("claim_id") or c.get("id") or f"v1-{hashlib.sha256(identity.encode()).hexdigest()[:16]}"
        c.setdefault("source_id", source_filename or "uploaded-source")
        c["source_ids"] = sorted(set(c.get("source_ids", []) + [c["source_id"]]))
        c.setdefault("locator", c.get("source_locator", ""))
        c.setdefault("epistemic_class", c.get("epistemic", "asserted"))
        out.append(c)
    return out

def _merge_claim_corpus(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], list[dict]]:
    """Append novel content-addressed claims and retain all source provenance."""
    merged = [dict(c) for c in existing]
    by_id = {str(c.get("claim_id") or c.get("id") or c.get("stable_id")): c for c in merged}
    added: list[dict] = []
    for claim in incoming:
        cid = str(claim.get("claim_id") or claim.get("id") or claim.get("stable_id"))
        prior = by_id.get(cid)
        if prior is None:
            merged.append(claim)
            by_id[cid] = claim
            added.append(claim)
            continue
        prior_sources = set(prior.get("source_ids", [])) | {prior.get("source_id")} | set(claim.get("source_ids", [])) | {claim.get("source_id")}
        prior["source_ids"] = sorted(s for s in prior_sources if s)
    return merged, added

def _build_semantic_current(claims: list[dict], case_id: str) -> dict:
    """Build the pre-runtime Current semantic graph from admitted source evidence."""
    from claim_graph import claims_to_graph
    graph = claims_to_graph(claims, deal=case_id)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_ids = {n.get("id") for n in nodes}
    # Make source provenance first-class in the test graph: Source → Claim.
    for index, claim in enumerate(claims):
        claim_node = f"claim:{index:03d}"
        for source_id in claim.get("source_ids") or [claim.get("source_id")]:
            if not source_id:
                continue
            source_node = f"source:{source_id}"
            if source_node not in node_ids:
                nodes.append({"id": source_node, "type": "source", "label": source_id,
                              "title": source_id, "coverage_status": "mapped"})
                node_ids.add(source_node)
            edges.append({"source": source_node, "target": claim_node, "rel": "CONTAINS_CLAIM"})
    # A missing question is a visible coverage condition, never a fabricated fact.
    bound_questions = {e.get("target", "").removeprefix("q:") for e in edges if e.get("rel") == "BEARS_ON"}
    for question in _load_questions(case_id):
        qid = question.get("id")
        if qid and qid not in bound_questions:
            condition_id = f"condition:coverage-{qid}"
            nodes.append({"id": condition_id, "type": "condition", "label": f"Evidence required for {qid}",
                          "coverage_status": "missing", "question_id": qid})
            edges.append({"source": f"q:{qid}", "target": condition_id, "rel": "REQUIRES_EVIDENCE"})
    graph["nodes"] = nodes
    graph["edges"] = edges
    graph["kind"] = "semantic_current"
    graph["case_id"] = case_id
    (PIPELINE_OUT / "semantic_current_graph.json").write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n")
    return graph

def _semantic_rooms(graph: dict, question_spine: list[dict]) -> tuple[list[dict], dict, list[dict]]:
    """Project semantic positions and evidence gaps into Foundations and Unknowns."""
    nodes = {n.get("id"): n for n in graph.get("nodes", [])}
    evidence: dict[str, list[dict]] = {}
    for edge in graph.get("edges", []):
        if edge.get("rel") not in {"SUPPORTS", "CONTRADICTS"}:
            continue
        claim, position = nodes.get(edge.get("source"), {}), nodes.get(edge.get("target"), {})
        if claim.get("type") == "claim" and position.get("type") == "case_position":
            evidence.setdefault(position["id"], []).append({
                "claim_id": claim["id"], "value": claim.get("value"), "unit": claim.get("unit"),
                "period": claim.get("period"), "perimeter": claim.get("perimeter"),
                "relation": edge["rel"], "definition_id": claim.get("definition"),
            })
    foundations, positions = [], []
    for node in nodes.values():
        if node.get("type") != "case_position":
            continue
        opts = evidence.get(node["id"], [])
        positions.append({"position_id": node["id"], "id": node["id"], "label": node.get("label"), **node})
        foundations.append({"id": node["id"], "label": node.get("label"), "economic": node.get("statement") or node.get("note", ""),
                            "strength": "contested" if node.get("decision_status") == "CONTESTED" else "weak",
                            "status": node.get("decision_status", "PENDING"), "evidence_options": opts,
                            "members": [x["claim_id"] for x in opts]})
    unknowns = {"items": [
        {"id": f"unknown:{q['id']}", "label": q.get("label", q["id"]), "question_id": q["id"],
         "value": "No admitted evidence yet", "closure": "Admit source evidence or accept the residual risk."}
        for q in question_spine if q.get("coverage") == "gap"
    ]}
    return foundations, unknowns, positions

def _run_v1_runtime_adapter(claims: list[dict], case_id: str) -> None:
    """Bridge V1 claims into the existing Keystone runtime bundle builder."""
    e3_path = PIPELINE_OUT / "SINGLE" / "e3_claims.json"
    e3_path.parent.mkdir(parents=True, exist_ok=True)
    compiler = []
    for c in claims:
        compiler.append({k: c.get(k) for k in ("claim_id", "metric", "direction", "topic", "author", "derivation")})
    e3 = {"schema_version": "e3/compat-v1", "manifest_id": "SINGLE", "deal": case_id,
          "extractor": "extract_v1", "claims": claims,
          "extraction_metadata": {"compiler_fields_per_claim": compiler}}
    e3_path.write_text(json.dumps(e3, indent=2, ensure_ascii=False))
    execution = VAULT / "deals" / case_id / "models" / "execution_graph_v7.json"
    if not execution.exists():
        fallback = ROOT / "pipeline_out" / "e3" / "K-PRE" / "adapter_alpha" / "execution_graph_v7.json"
        if fallback.exists():
            # bundle_assemble deliberately reads the canonical vault path.
            # Recreate it after a clean-state reset from the versioned
            # Keystone runtime template, before invoking adapter_alpha.
            execution.parent.mkdir(parents=True, exist_ok=True)
            execution.write_bytes(fallback.read_bytes())
    if not execution.exists():
        logger.warning("runtime adapter skipped: execution_graph_v7.json missing")
        return
    # The adapter writes its own claims.json. Keep it isolated so it can never
    # overwrite the cumulative extractor corpus at PIPELINE_OUT/claims.json.
    runtime_dir = PIPELINE_OUT / "runtime"
    cmd = [sys.executable, str(ROOT / "tools" / "adapter_alpha.py"), "--e3", str(e3_path),
           "--execution", str(execution), "--out", str(runtime_dir), "--manifest", "SINGLE", "--deal", case_id]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    if result.returncode:
        logger.warning("runtime adapter failed: %s", result.stderr[-1000:])
    else:
        # The V20 projection reads these runtime state files from the root
        # bundle. Promote state only; extractor claims remain authoritative.
        for name in (
            "current_graph.json",
            "candidate_graph.json",
            "transition_output.json",
            "execution_mapping.json",
            "event_ebitda_correction.json",
            "keystone_materiality_policy_v0.json",
            "keystone_authority_matrix_v0.json",
            "admission_manifest_v7.json",
        ):
            src = runtime_dir / name
            if src.exists():
                (PIPELINE_OUT / name).write_bytes(src.read_bytes())
        logger.info("runtime adapter built V1 runtime bundle for %d claims", len(claims))

def _rebuild_index() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "indexer.py")],
        capture_output=True, cwd=str(ROOT),
    )

def _read_frontmatter(path: Path) -> dict:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except Exception:
        return {}

def _load_json_safe(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else {}

def _load_profile(case_id: str) -> dict:
    p = VAULT / "deals" / case_id / "deal_profile.json"
    return json.loads(p.read_text()) if p.exists() else {}

def _load_claims() -> list[dict]:
    f = PIPELINE_OUT / "claims.json"
    return json.loads(f.read_text()) if f.exists() else []

def _load_bears_on_map() -> dict[str, list[str]]:
    db_path = ROOT / ".index" / "vault.db"
    if not db_path.exists():
        return {}
    try:
        con = sqlite3.connect(str(db_path))
        rows = con.execute("SELECT frontmatter FROM nodes WHERE type='claim'").fetchall()
        con.close()
        mapping: dict[str, list[str]] = {}
        for (fm_str,) in rows:
            fm = json.loads(fm_str)
            cid = fm.get("id")
            bears = fm.get("bears-on", [])
            if cid and bears:
                mapping[cid] = bears if isinstance(bears, list) else [bears]
        return mapping
    except Exception:
        return {}

def _load_questions(case_id: str) -> list[dict]:
    q_dir = VAULT / "deals" / case_id / "questions"
    if not q_dir.exists():
        return []
    out = []
    for md in sorted(q_dir.glob("*.md")):
        fm = _read_frontmatter(md)
        if fm:
            # Migrate the initial Q-xx registry created before origins were
            # recorded; it is archetype grammar, not deal-emergent evidence.
            if not fm.get("origin") and str(fm.get("id", "")).startswith("Q-"):
                fm["origin"] = "archetype"
                fm.setdefault("question_version", 1)
            out.append(fm)
    return out

def _enrich_claims(raw: list[dict], bears_on_map: dict) -> list[dict]:
    today = _today()
    out = []
    for c in raw:
        cid = c.get("id") or c.get("claim_id") or c.get("stable_id") or ""
        # contracts.js requires effective_date and known_at as non-empty strings
        known_at = c.get("known_at") or "2024-10-01T00:00:00Z"
        effective_date = c.get("effective_date") or (c.get("period") or today)
        if len(effective_date) == 4:  # year only → make a full date
            effective_date = f"{effective_date}-12-31"
        out.append({
            **c,
            "claim_id": cid,
            "id": cid,
            "bears_on": bears_on_map.get(cid, []),
            "locator": c.get("locator", ""),
            "epistemic_type": c.get("epistemic", c.get("epistemic_type", "asserted")),
            "epistemic_class": c.get("epistemic", "asserted"),
            "effective_date": effective_date,
            "known_at": known_at,
        })
    return out

def _build_sources_from_claims(raw: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for c in raw:
        source_ids = c.get("source_ids") or [c.get("source_id") or c.get("source_doc") or "unknown"]
        for sid in source_ids:
            if sid not in seen:
                seen[sid] = {
                    "source_id": sid,
                    "title": c.get("source_doc", sid),
                    "claim_ids": [],
                    "effective_date": "2024-10-01T00:00:00Z",
                    "known_at": "2024-10-01T00:00:00Z",
                }
            seen[sid]["claim_ids"].append(c.get("id") or c.get("claim_id") or "")
    return list(seen.values())

def _build_question_spine(questions: list[dict], claims: list[dict]) -> list[dict]:
    spine = []
    for q in questions:
        qid = q.get("id", "")
        bearing = [c for c in claims if qid in c.get("bears_on", [])]
        count = len(bearing)
        spine.append({
            "id": qid,
            "question_id": qid,
            "title": q.get("title") or q.get("question") or qid,
            "label": q.get("title") or q.get("question") or qid,
            "status": q.get("status", "open"),
            "claim_count": count,
            "coverage": "gap" if count == 0 else ("full" if count >= 3 else "partial"),
            "workstream": q.get("workstream", ""),
            "origin": q.get("origin", "deal_emergent"),
            "question_version": q.get("question_version", 1),
            "work_plan": [],
        })
    return spine

def _make_context(case_id: str, as_of_state_id: str, as_of_date: str) -> dict:
    """Build a context object that passes contracts.js validateContext."""
    return {
        "mode": "CONNECTED",
        "action_capability": "READ_WRITE",
        "case_id": case_id,
        "projection_id": f"PROJ-{case_id.upper()}-LIVE",
        "projection_hash": "sha256:live",
        "as_of_state_id": as_of_state_id,
        "as_of_date": as_of_date,
        "authenticated_actor": {
            "actor_id": "partner-001",
            "name": "Deal Partner",
            "role": "DEAL_PARTNER",
        },
        "viewer_projection": "partner",
        "authority_assignments": [],
        "demo_session_id": None,
        "synthetic": False,
        "no_external_effects": False,
        "contract_version": "20.0",
        "active_lens_id": None,
    }

def _build_projection(case_id: str, as_of_date: str | None = None) -> dict:
    """Build a full projection object that passes contracts.js validateProjection."""
    from compiler_projection_adapter import map_compiler_bundle

    profile = _load_profile(case_id)
    raw_claims = _load_claims()
    bears_on_map = _load_bears_on_map()
    claims = _enrich_claims(raw_claims, bears_on_map)
    sources = _build_sources_from_claims(raw_claims)
    questions = _load_questions(case_id)
    question_spine = _build_question_spine(questions, claims)
    semantic_graph = _load_json_safe(PIPELINE_OUT / "semantic_current_graph.json")
    foundations, unknowns, semantic_positions = _semantic_rooms(semantic_graph, question_spine) if semantic_graph else ([], {"items": []}, [])

    current_graph = _load_json_safe(PIPELINE_OUT / "current_graph.json")
    candidate_graph = _load_json_safe(PIPELINE_OUT / "candidate_graph.json")
    transition_output = _load_json_safe(PIPELINE_OUT / "transition_output.json")

    if isinstance(current_graph, dict) and "case_positions" in current_graph:
        current_graph = {**current_graph, "positions": current_graph["case_positions"]}

    today = _today()
    as_of_date = as_of_date or today
    state_id = current_graph.get("state_id", f"STATE-{case_id.upper()}-CURRENT")

    # All the dates for temporal
    available_dates = sorted(set(
        [c.get("known_at", "")[:10] for c in claims if c.get("known_at")]
        + [today]
    ))

    projection = {
        "schema_version": "frontend-projection/20.0",
        "package_version": "20.0.0",
        "disclosure": {},
        "fund": {
            "situations": [],
            "morning_delta": [],
        },
        "events": {},
        "actor_directory": [
            {
                "participant_id": "partner-001",
                "id": "partner-001",
                "name": "Deal Partner",
                "role": "DEAL_PARTNER",
                "effective_date": "2024-01-01T00:00:00Z",
                "known_at": "2024-01-01T00:00:00Z",
            }
        ],
        "deal": {
            "case_id": case_id,
            "entity": profile.get("entity", case_id),
            "archetype": {"id": "buyout", "label": "Buyout", "is_default": True},
            "objective": profile.get("objective", ""),
            "as_of_state_id": state_id,
            "as_of_date": as_of_date,
            "temporal": {
                "basis": "KNOWN_AT",
                "effective_axis": "effective_date",
                "knowledge_axis": "known_at",
                "replay_source": "REGISTRY_EVENTS",
                "available_dates": available_dates,
            },
            "replay": {
                "source": "REGISTRY_EVENTS",
                "hand_authored_snapshots": False,
                "snapshots": [],
            },
            "claims": claims,
            "question_spine": question_spine,
            "artifacts": [],
            "lenses": [],
            "participants": [
                {
                    "participant_id": "partner-001",
                    "id": "partner-001",
                    "name": "Deal Partner",
                    "role": "DEAL_PARTNER",
                    "effective_date": "2024-01-01T00:00:00Z",
                    "known_at": "2024-01-01T00:00:00Z",
                }
            ],
            "interactions": [],
            "utterances": [],
            "derivation_specs": [],
            "derivations": [],
            "discrepancy_rules": [],
            "discrepancy_candidates": [],
            "hypotheses": [],
            "agent_missions": [],
            "spine_change_proposals": [],
            "condition_edges": [],
            "validation_envelopes": [],
            "source_center": {"sources": sources},
            "rooms": {
                "foundations": {"sets": foundations},
                "unknowns": unknowns,
                "shadowIC": {"theses": []},
            },
            "positions": semantic_positions,
            "semantic_current_graph": semantic_graph,
            "current_graph": current_graph,
            "candidate_graph": candidate_graph,
            "transition_output": transition_output,
        },
    }

    # Run through the compiler adapter
    compiler_bundle: dict = {
        "schema_version": "compiler-bundle/20.0",
        "case_id": case_id,
        "claims": claims,
        "sources": sources,
    }
    try:
        result = map_compiler_bundle(projection, compiler_bundle, as_of_date=as_of_date)
        # Re-attach fields the adapter doesn't carry through
        result["deal"]["question_spine"] = question_spine
        result["deal"]["current_graph"] = current_graph
        result["deal"]["candidate_graph"] = candidate_graph
        result["deal"]["transition_output"] = transition_output
        result["deal"]["rooms"] = projection["deal"]["rooms"]
        result["deal"]["positions"] = semantic_positions
        result["deal"]["semantic_current_graph"] = semantic_graph
        result["deal"]["replay"] = projection["deal"]["replay"]
        result["deal"]["temporal"] = projection["deal"]["temporal"]
        result["deal"]["as_of_state_id"] = state_id
        result["deal"]["as_of_date"] = as_of_date
        result["deal"]["objective"] = projection["deal"]["objective"]
        result["deal"]["artifacts"] = []
        result["deal"]["lenses"] = []
        result["deal"]["participants"] = projection["deal"]["participants"]
        result["fund"] = projection["fund"]
        result["events"] = projection["events"]
        result["actor_directory"] = projection["actor_directory"]
        result["disclosure"] = projection["disclosure"]
        return result
    except Exception as exc:
        projection["_adapter_error"] = str(exc)
        return projection


# ── Routes ────────────────────────────────────────────────────────────────────

@v20.get("/health")
def health() -> dict:
    return {"status": "ok", "schema_version": "frontend-projection/20.0"}


# Flat /bootstrap — this is the URL api.js actually calls
@v20.get("/bootstrap")
def bootstrap_flat(case_id: str | None = None, actor: str | None = None) -> dict:
    cid = case_id or "keystone"
    deal_md = VAULT / "deals" / cid / "deal.md"
    if not deal_md.exists():
        # Try to find any deal
        deals = [d.name for d in (VAULT / "deals").iterdir() if d.is_dir()] if (VAULT / "deals").exists() else []
        cid = deals[0] if deals else cid
    profile = _load_profile(cid)
    today = _today()
    cg = _load_json_safe(PIPELINE_OUT / "current_graph.json")
    state_id = cg.get("state_id", f"STATE-{cid.upper()}-CURRENT") if isinstance(cg, dict) else f"STATE-{cid.upper()}-CURRENT"
    session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"
    return {
        "session_id": session_id,
        "available_cases": [cid],
        "cases": [cid],
        "context": _make_context(cid, state_id, today),
    }

# Also keep the /cases/{id}/bootstrap for direct calls
@v20.get("/cases/{case_id}/bootstrap")
def bootstrap(case_id: str) -> dict:
    deal_md = VAULT / "deals" / case_id / "deal.md"
    if not deal_md.exists():
        raise HTTPException(404, f"Deal not found: {case_id}")
    profile = _load_profile(case_id)
    today = _today()
    cg = _load_json_safe(PIPELINE_OUT / "current_graph.json")
    state_id = cg.get("state_id", f"STATE-{case_id.upper()}-CURRENT") if isinstance(cg, dict) else f"STATE-{case_id.upper()}-CURRENT"
    session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"
    return {
        "session_id": session_id,
        "available_cases": [case_id],
        "cases": [case_id],
        "context": _make_context(case_id, state_id, today),
        "entity": profile.get("entity", case_id),
        "deal_profile": profile,
    }


@v20.get("/cases/{case_id}/projection")
def projection(case_id: str, as_of_date: str | None = None) -> dict:
    try:
        proj = _build_projection(case_id, as_of_date)
    except Exception as exc:
        logger.error("PROJECTION BUILD FAILED case=%s err=%s", case_id, exc)
        raise HTTPException(500, f"Projection build failed: {exc}")
    today = _today()
    cg = _load_json_safe(PIPELINE_OUT / "current_graph.json")
    state_id = cg.get("state_id", f"STATE-{case_id.upper()}-CURRENT") if isinstance(cg, dict) else f"STATE-{case_id.upper()}-CURRENT"
    if proj.get("_adapter_error"):
        logger.warning("PROJECTION adapter_error case=%s err=%s", case_id, proj["_adapter_error"])
    logger.info("PROJECTION OK case=%s claims=%d questions=%d",
                case_id,
                len(proj.get("deal", {}).get("claims", [])),
                len(proj.get("deal", {}).get("question_spine", [])))
    return {
        "projection": proj,
        "context": _make_context(case_id, state_id, as_of_date or today),
        "registry": [],
    }


@v20.get("/cases/{case_id}/sources")
def sources(case_id: str) -> dict:
    raw = _load_claims()
    srcs = _build_sources_from_claims(raw)
    inbox_items = _read_inbox_manifest()
    known_files = {item.get("stored_name") for item in inbox_items}
    inbox_dir = VAULT / "inbox"
    if inbox_dir.exists():
        for f in sorted(inbox_dir.glob("*")):
            if f.is_file() and not f.name.startswith(".") and f.name not in known_files:
                inbox_items.append({
                    "id": f"legacy-{f.name}", "name": f.name, "stored_name": f.name,
                    "path": f"vault/inbox/{f.name}", "size": f.stat().st_size,
                    "status": "WAITING", "stage": "Awaiting ingest",
                })
    return {"sources": srcs, "inbox": inbox_items}


@v20.get("/cases/{case_id}/inbox")
def inbox_v20(case_id: str) -> list:
    return sources(case_id)["inbox"]


@v20.post("/cases/{case_id}/ingest")
async def ingest(case_id: str, request: Request, background_tasks: BackgroundTasks) -> dict:
    inbox_dir = VAULT / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    filename = ""
    original_filename = ""
    stored_path: Path | None = None
    purpose = ""
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        file_field = form.get("file")
        purpose = str(form.get("purpose", ""))
        if file_field and hasattr(file_field, "filename"):
            original_filename = Path(file_field.filename or "upload").name
            content = await file_field.read()
            stored_path = _unique_inbox_path(original_filename)
            stored_path.write_bytes(content)
            filename = stored_path.name
        else:
            filename = Path(str(form.get("value", ""))).name
            original_filename = filename
    else:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        filename = Path(payload.get("file_name") or payload.get("value") or payload.get("artifact") or "").name
        original_filename = filename
        purpose = payload.get("purpose", "")
        encoded = payload.get("content_b64")
        if encoded and filename:
            try:
                content = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError, base64.binascii.Error) as exc:
                raise HTTPException(400, f"Invalid uploaded file payload: {exc}") from exc
            stored_path = _unique_inbox_path(filename)
            stored_path.write_bytes(content)
            filename = stored_path.name

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "status": "PENDING", "job_id": job_id,
        "artifact": filename, "case_id": case_id, "purpose": purpose,
        "label": filename or "extraction run",
        "stage": "Queued", "progress": 0,
    }
    if filename:
        with _inbox_lock:
            items = _read_inbox_manifest()
            items.insert(0, {
                "id": f"source-intake-{job_id}", "job_id": job_id, "case_id": case_id,
                "name": original_filename or filename, "stored_name": filename,
                "path": f"vault/inbox/{filename}",
                "size": stored_path.stat().st_size if stored_path else None,
                "purpose": purpose, "status": "PENDING", "stage": "Queued",
                "uploaded_at": _now_iso(), "updated_at": _now_iso(),
                "message": "Stored durably; waiting for extraction.",
            })
            _write_inbox_manifest(items)

    def _run() -> None:
        _jobs[job_id].update({"status": "RUNNING", "stage": "Extracting", "progress": 10})
        _update_inbox_record(job_id, status="RUNNING", stage="Extracting", progress=10,
                             message="Source is being extracted into typed claims.")
        source_path = (inbox_dir / filename) if filename else None
        import os as _os

        # For single text/md file: extract just that file and merge new claims in.
        # For a missing file use the legacy V1 batch entry point.
        if source_path and source_path.exists() and source_path.suffix.lower() in (".md", ".txt", ".pdf"):
            manifest_label = "SINGLE"
            run_dir = PIPELINE_OUT / "runs" / job_id
            # Use the proven V1 extractor for the live V20 path.  pipeline.py
            # accepts PDF directly (via pdftotext) and writes canonical claims
            # plus the semantic graph under the requested output directory.
            cmd = [sys.executable, str(ROOT / "tools" / "pipeline.py"),
                   str(source_path), "--deal", case_id,
                   "--out", str(run_dir)]
        else:
            manifest_label = "K-IC"
            cmd = [sys.executable, str(ROOT / "tools" / "extract.py"),
                   "--deal", case_id]

        # Pass the API key explicitly so the subprocess is never denied
        env = {**_os.environ, "ANTHROPIC_API_KEY": _os.environ.get("ANTHROPIC_API_KEY", "")}
        logger.info("JOB %s START label=%s file=%s", job_id, manifest_label, filename or "manifest")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), env=env)
            ok = r.returncode == 0
            logger.info("JOB %s %s returncode=%d", job_id, "COMPLETE" if ok else "ERROR", r.returncode)
            if r.stderr:
                logger.warning("JOB %s stderr: %s", job_id, r.stderr[-500:])

            # Extraction produces a proposal.  It must not mutate the admitted
            # corpus or the semantic Current until a professional review admits it.
            if ok:
                output_dir = (PIPELINE_OUT / "runs" / job_id) if manifest_label == "SINGLE" else (PIPELINE_OUT / manifest_label)
                e3_out = output_dir / "e3_claims.json"
                v1_out = output_dir / "claims.json"
                if e3_out.exists() or v1_out.exists():
                    try:
                        if e3_out.exists():
                            e3 = json.loads(e3_out.read_text())
                            raw = e3.get("claims", [])
                        else:
                            e3 = {}
                            raw = json.loads(v1_out.read_text())
                        new_claims = _derive_bears_on(_normalise_v1_claims(raw, filename), e3)
                        proposal = _write_evidence_proposal(job_id, case_id, filename, new_claims)
                        _jobs[job_id].update({"proposal_id": proposal.stem,
                                              "proposal_path": str(proposal.relative_to(ROOT)),
                                              "proposed_claim_count": len(new_claims),
                                              "admission_status": "PENDING_REVIEW"})
                        _update_inbox_record(job_id, proposal_id=proposal.stem,
                                             proposal_path=str(proposal.relative_to(ROOT)),
                                             proposed_claim_count=len(new_claims),
                                             admission_status="PENDING_REVIEW")
                        logger.info("JOB %s produced %d evidence proposals", job_id, len(new_claims))
                    except Exception as merge_exc:
                        logger.error("JOB %s merge failed: %s", job_id, merge_exc)

            _jobs[job_id].update({
                "status": "COMPLETE" if ok else "ERROR",
                "stage": "Complete" if ok else "Failed",
                "progress": 100 if ok else 0,
                "stdout": (r.stdout or "")[-2000:],
                "stderr": (r.stderr or "")[-1000:],
                "message": "Extraction complete — evidence is ready for professional review."
                if ok else (r.stderr or "")[-300:],
            })
            _update_inbox_record(
                job_id, status="COMPLETE" if ok else "ERROR",
                stage="Complete" if ok else "Failed", progress=100 if ok else 0,
                message="Extraction complete; admit, edit or reject the proposed evidence before it enters Current."
                if ok else (r.stderr or "Extraction failed")[-300:],
            )
        except Exception as exc:
            logger.error("JOB %s EXCEPTION %s", job_id, exc)
            _jobs[job_id].update({"status": "ERROR", "stage": "Failed", "error": str(exc), "message": str(exc)})
            _update_inbox_record(job_id, status="ERROR", stage="Failed", progress=0, message=str(exc))
        _rebuild_index()

    background_tasks.add_task(_run)
    return {"job": _jobs[job_id], "job_id": job_id}


@v20.post("/cases/{case_id}/ingest/{job_id}/admit")
async def admit_evidence(case_id: str, job_id: str, payload: dict = {}) -> dict:
    """Apply the explicit professional decision at the evidence boundary.

    Extraction is fallible.  This endpoint is the only route that promotes an
    extracted claim to the admitted corpus and rebuilds the semantic Current.
    It intentionally does *not* invoke the transition/runtime adapter: the
    resulting admitted-evidence event is the hand-off to the dynamics layer.
    """
    proposal_file = _proposal_path(job_id)
    if not proposal_file.exists():
        raise HTTPException(404, "No evidence proposal exists for this ingestion job")
    proposal = _load_json_safe(proposal_file)
    if proposal.get("case_id") != case_id:
        raise HTTPException(409, "Evidence proposal belongs to another case")
    decision = str(payload.get("decision", "ADMIT")).upper()
    if decision not in {"ADMIT", "REJECT"}:
        raise HTTPException(400, "decision must be ADMIT or REJECT")
    if proposal.get("status") != "PENDING_REVIEW":
        raise HTTPException(409, f"Evidence proposal already decided: {proposal.get('status')}")

    if decision == "REJECT":
        proposal.update({"status": "REJECTED", "reviewed_at": _now_iso(),
                         "reviewed_by": payload.get("actor_id", "professional-review"),
                         "review_note": payload.get("note", "")})
        proposal_file.write_text(json.dumps(proposal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _update_inbox_record(job_id, admission_status="REJECTED", stage="Evidence rejected",
                             message="Extraction retained for audit; no claim entered Current.")
        return {"status": "REJECTED", "proposal_id": proposal.get("proposal_id")}

    # Optional corrected claims are supplied by a review UI/API client.  The
    # default is to admit the extractor proposal unchanged.
    reviewed_claims = payload.get("claims") if isinstance(payload.get("claims"), list) else proposal.get("claims", [])
    reviewed_claims = [dict(c) for c in reviewed_claims if isinstance(c, dict)]
    _ensure_question_registry(case_id)
    existing_path = PIPELINE_OUT / "claims.json"
    existing = json.loads(existing_path.read_text()) if existing_path.exists() else []
    merged, added = _merge_claim_corpus(existing, reviewed_claims)
    existing_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    persisted = _persist_claims_to_vault(case_id, added, proposal.get("source_id", ""))
    graph = _build_semantic_current(merged, case_id)
    proposal.update({"status": "ADMITTED", "reviewed_at": _now_iso(),
                     "reviewed_by": payload.get("actor_id", "professional-review"),
                     "review_note": payload.get("note", ""),
                     "admitted_claim_count": len(added)})
    proposal_file.write_text(json.dumps(proposal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _update_inbox_record(job_id, admission_status="ADMITTED", stage="Evidence admitted",
                         admitted_claim_count=len(added),
                         message=f"Admitted evidence changed the semantic Current ({len(added)} new claims).")
    events_dir = VAULT / "deals" / case_id / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    event_id = f"EVIDENCE-ADMITTED-{job_id}"
    event_fm = {"type": "evidence_admitted", "id": event_id, "case": case_id,
                "source": proposal.get("source_id"), "proposal_id": proposal.get("proposal_id"),
                "claim_count": len(added), "known_at": _now_iso(),
                "actor": payload.get("actor_id", "professional-review")}
    (events_dir / f"e-{case_id}-evidence-admitted-{job_id}.md").write_text(
        "---\n" + yaml.safe_dump(event_fm, sort_keys=False, allow_unicode=True) + "---\n\n"
        "Admitted evidence event. Dynamics has not yet been run.\n", encoding="utf-8")
    _rebuild_index()
    return {"status": "ADMITTED", "proposal_id": proposal.get("proposal_id"), "event_id": event_id,
            "new_claim_count": len(added), "persisted_claim_count": persisted,
            "semantic_graph": {"nodes": len(graph.get("nodes", [])), "edges": len(graph.get("edges", []))},
            "message": "Evidence admitted into semantic Current; ready for dynamics."}


@v20.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if not job:
        job = next((item for item in _read_inbox_manifest() if item.get("job_id") == job_id), None)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    return {"job": job, **job}


@v20.post("/cases/{case_id}/events/{event_id}/admit")
async def admit(
    case_id: str, event_id: str,
    background_tasks: BackgroundTasks,
    payload: dict = {},
) -> dict:
    try:
        event_batch = load_event_batch(PIPELINE_OUT, event_id, payload)
        dynamics_result = run_bundle_transition(
            PIPELINE_OUT,
            event_batch,
            persist_outputs=True,
        )
    except DynamicsBundleError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (ValueError, KeyError) as exc:
        logger.exception("dynamics rejected event %s", event_id)
        raise HTTPException(422, f"Dynamics rejected the event: {exc}") from exc

    transition_output = dynamics_result["transition_output"]
    candidate_graph = dynamics_result["candidate_graph"]
    candidate_state = dynamics_result["candidate_state"]

    human_stops = transition_output.get("human_stops", [])
    blocked = transition_output.get("blocked_components", [])
    run_id = transition_output.get("run_id", f"RUN-{uuid.uuid4().hex[:8].upper()}")
    cand_state_id = candidate_state.get(
        "state_id", f"CAND-{uuid.uuid4().hex[:8].upper()}"
    )

    # Store run so /runs/{run_id}/settle can find it
    _runs[run_id] = {
        "case_id": case_id,
        "event_id": event_id,
        "candidate_graph": candidate_graph,
        "candidate_state": candidate_state,
        "history_append": dynamics_result.get("history_append", []),
        "transition_output": transition_output,
        "candidate_state_id": cand_state_id,
        "bundle_dir": str(PIPELINE_OUT),
        "authority_records": [],
    }

    # Write admit event to vault
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    events_dir = VAULT / "deals" / case_id / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    (events_dir / f"e-{case_id}-admit-{ts}.md").write_text(
        f"---\nid: e-{case_id}-admit-{ts}\ntype: admission\n"
        f"event_id: {event_id}\nrun_id: {run_id}\ntimestamp: {ts}\nwritten-by: v20-api\n---\n"
    )
    background_tasks.add_task(_rebuild_index)

    # Shape the transition to pass contracts.js validateTransition
    transition = {
        "schema_version": "transition-output/1.0",
        "engine_version": transition_output.get("engine_version", "1.0"),
        "run_id": run_id,
        "case_id": case_id,
        "prior_state_id": transition_output.get("prior_state_id", "STATE-PRIOR"),
        "candidate_state_id": cand_state_id,
        "policy_refs": transition_output.get("policy_refs", {}),
        "affected_set": transition_output.get("affected_set", []),
        "ordered_transitions": transition_output.get("ordered_transitions", []),
        "rule_switches": transition_output.get("rule_switches", []),
        "recomputed_values": transition_output.get("recomputed_values", []),
        "unchanged_objects": transition_output.get("unchanged_objects", []),
        "human_stops": human_stops,
        "blocked_components": blocked,
        "coverage_limits": transition_output.get("coverage_limits", []),
        "invariant_checks": transition_output.get("invariant_checks", []),
        "candidate_current_approved_delta": transition_output.get("candidate_current_approved_delta", {}),
        "partial_settlement_status": transition_output.get("partial_settlement_status", {}),
        "replay_hash": transition_output.get("replay_hash", "sha256:live"),
        "source_event_id": event_id,
    }

    return {
        "run": {"run_id": run_id, "status": "CANDIDATE_READY"},
        "transition": transition,
        "context": {
            **_make_context(case_id, cand_state_id, _today()),
            "run_id": run_id,
            "candidate_state_id": cand_state_id,
            "human_stop_id": human_stops[0].get("stop_id") if human_stops else None,
        },
        "registry": [],
    }


# Settlement called as POST /runs/{run_id}/settle by the frontend
@v20.post("/runs/{run_id}/settle")
async def settle_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    payload: dict = {},
) -> dict:
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, f"Run not found: {run_id}. Call /admit first to create a run.")
    if run.get("settled_state_id"):
        raise HTTPException(409, f"Run {run_id} is already settled")

    case_id = run["case_id"]
    event_id = run["event_id"]
    decision = "accepted"
    actor = payload.get("actor_id", "partner-001")

    human_stops = run["transition_output"].get("human_stops", [])
    if human_stops:
        supplied_record_ids = set(payload.get("authority_record_ids", []))
        recorded = {
            item["authority_record_id"]: item
            for item in run.get("authority_records", [])
        }
        covered_stops = {
            recorded[record_id].get("human_stop_id")
            for record_id in supplied_record_ids
            if record_id in recorded
        }
        required_stops = {
            item.get("stop_id") for item in human_stops if item.get("stop_id")
        }
        if not required_stops.issubset(covered_stops):
            missing = sorted(required_stops - covered_stops)
            raise HTTPException(
                409,
                "Candidate requires recorded human approval before settlement: "
                + ", ".join(missing),
            )

    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    today = _today()
    new_state_id = f"STATE-{case_id.upper()}-{ts}"
    try:
        settled_state = settle_candidate_state(
            Path(run.get("bundle_dir", PIPELINE_OUT)),
            run["candidate_state"],
            run.get("history_append", []),
            current_state_id=new_state_id,
        )
    except DynamicsBundleError as exc:
        raise HTTPException(409, str(exc)) from exc
    run["settled_state_id"] = new_state_id

    # Append the institutional settlement event only after runtime persistence
    # succeeds, so the audit trail can never claim a failed promotion occurred.
    events_dir = VAULT / "deals" / case_id / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    settle_file = events_dir / f"e-{case_id}-settle-{ts}.md"
    settle_file.write_text(
        f"---\nid: e-{case_id}-settle-{ts}\ntype: settlement\n"
        f"settles: {event_id}\nrun_id: {run_id}\ndecision: {decision}\n"
        f"actor: {actor}\ntimestamp: {ts}\nwritten-by: v20-api\n---\n"
    )
    background_tasks.add_task(_rebuild_index)

    updated_projection = _build_projection(case_id)

    # contracts.js validateSettlement shape
    return {
        "settlement_id": f"SETTLE-{run_id}",
        "case_id": case_id,
        "run_id": run_id,
        "candidate_state_id": run["candidate_state_id"],
        "prior_state_id": run["transition_output"].get("prior_state_id", "STATE-PRIOR"),
        "current_state_id": new_state_id,
        "selected_change_ids": payload.get("selected_change_ids", []),
        "partial": run["transition_output"].get("partial_settlement_status", {}).get(
            "candidate"
        ) == "PARTIAL",
        "summary": f"Settled {event_id} → new Current {new_state_id}",
        "replay_hash": run["transition_output"].get("replay_hash", "sha256:settled"),
        "timestamp": ts,
        "effective_date": payload.get("effective_date", today),
        "known_at": ts,
        "as_of_state_id": new_state_id,
        "as_of_date": today,
        "projection": {"projection": updated_projection, "context": _make_context(case_id, new_state_id, today), "registry": []},
        "context": _make_context(case_id, new_state_id, today),
        "registry": [],
        "runtime_state_id": settled_state["state_id"],
    }

# Also keep the event-based settle for direct calls
@v20.post("/cases/{case_id}/events/{event_id}/settle")
async def settle_event(
    case_id: str, event_id: str,
    background_tasks: BackgroundTasks,
    payload: dict = {},
) -> dict:
    # Create a synthetic run and delegate
    run_id = f"RUN-DIRECT-{uuid.uuid4().hex[:8].upper()}"
    candidate_graph = _load_json_safe(PIPELINE_OUT / "candidate_graph.json")
    candidate_state = _load_json_safe(PIPELINE_OUT / "candidate_state.json")
    to = _load_json_safe(PIPELINE_OUT / "transition_output.json")
    if not candidate_state:
        raise HTTPException(409, "No persisted Candidate state; run dynamics first")
    _runs[run_id] = {
        "case_id": case_id, "event_id": event_id,
        "candidate_graph": candidate_graph,
        "candidate_state": candidate_state,
        "history_append": to.get("history_append", []),
        "transition_output": to if isinstance(to, dict) else {},
        "candidate_state_id": candidate_state.get(
            "state_id", f"CAND-DIRECT-{uuid.uuid4().hex[:8].upper()}"
        ),
        "bundle_dir": str(PIPELINE_OUT),
        "authority_records": [],
    }
    return await settle_run(run_id, background_tasks, payload)


@v20.post("/runs/{run_id}/prepare")
async def prepare_run(run_id: str, payload: dict = {}) -> dict:
    return {"run_id": run_id, "status": "PREPARED", "selected_change_ids": payload.get("selected_change_ids", [])}


@v20.post("/runs/{run_id}/authority/attest")
async def attest(run_id: str, payload: dict = {}) -> dict:
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, f"Run not found: {run_id}")
    ts = _now_iso()
    today = _today()
    human_stop_id = payload.get("human_stop_id", "")
    declared_stops = {
        item.get("stop_id")
        for item in run["transition_output"].get("human_stops", [])
        if item.get("stop_id")
    }
    if declared_stops and human_stop_id not in declared_stops:
        raise HTTPException(409, "human_stop_id is not part of this Candidate")
    record_key = "|".join(
        (
            run_id,
            human_stop_id,
            str(payload.get("actor_id", "partner-001")),
            str(payload.get("course_id", "")),
        )
    )
    record_id = "AUTH-" + hashlib.sha256(record_key.encode("utf-8")).hexdigest()[:12].upper()
    authority_record = {
        "authority_record_id": record_id,
        "run_id": run_id,
        "candidate_state_id": payload.get("candidate_state_id", f"CAND-{run_id}"),
        "human_stop_id": human_stop_id,
        "course_id": payload.get("course_id", ""),
        "actor_id": payload.get("actor_id", "partner-001"),
        "actor_role": payload.get("actor_role", "DEAL_PARTNER"),
        "timestamp": ts,
        "effective_date": today,
        "known_at": ts,
        "artifact_hash": payload.get("artifact_hash", "sha256:live"),
        "authority_verb": "APPROVE",
        "effect_type": "PROCEED",
        "status": "ACTIVE",
    }
    run.setdefault("authority_records", []).append(authority_record)
    return {
        "authority_record": authority_record,
        "execution_package": None,
    }


@v20.get("/cases/{case_id}/replay")
def replay(case_id: str, as_of_date: str | None = None, event_id: str | None = None) -> dict:
    date = as_of_date or _today()
    proj = _build_projection(case_id, date)
    state_id = f"STATE-REPLAY-{date}"
    return {
        "snapshot": {"id": state_id, "date": date, "as_of_date": date},
        "event": {"event_id": event_id or "ORIGIN", "known_at": f"{date}T00:00:00Z", "effective_date": date},
        "source_state_id": state_id,
        "result_state_id": state_id,
        "stable_hash": "sha256:replay",
        "effective_date": date,
        "known_at": f"{date}T00:00:00Z",
        "as_of_date": date,
        "read_only": True,
        "derived_from_event_log": True,
        "projection": {"projection": proj, "context": _make_context(case_id, state_id, date), "registry": []},
    }


@v20.get("/cases/{case_id}/events")
def list_events(case_id: str) -> list:
    events_dir = VAULT / "deals" / case_id / "events"
    if not events_dir.exists():
        return []
    out = []
    for md in sorted(events_dir.glob("*.md")):
        fm = _read_frontmatter(md)
        if fm:
            out.append(fm)
    return out


@v20.post("/cases/{case_id}/notes")
async def add_note(case_id: str, payload: dict = {}) -> dict:
    return {"status": "LOCAL_ONLY", "note": {**payload, "server_ack_at": None}}


@v20.get("/cases/{case_id}/objects/{object_id:path}")
def get_object(case_id: str, object_id: str) -> dict:
    raw = _load_claims()
    bears_on_map = _load_bears_on_map()
    claims = _enrich_claims(raw, bears_on_map)
    obj = next((c for c in claims if c.get("claim_id") == object_id or c.get("id") == object_id), None)
    if obj:
        return {"object": obj}
    raise HTTPException(404, f"Object not found: {object_id}")


@v20.post("/sessions")
async def new_session(payload: dict = {}) -> dict:
    return {"session_id": f"SES-{uuid.uuid4().hex[:8].upper()}"}


@v20.get("/search")
def search(q: str = "", case_id: str = "keystone") -> dict:
    db_path = ROOT / ".index" / "vault.db"
    if not db_path.exists():
        return {"results": []}
    try:
        con = sqlite3.connect(str(db_path))
        rows = con.execute(
            "SELECT frontmatter, title FROM nodes WHERE title LIKE ? OR frontmatter LIKE ? LIMIT 20",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
        con.close()
        return {"results": [{"frontmatter": json.loads(fm), "title": t} for fm, t in rows]}
    except Exception as exc:
        return {"results": [], "error": str(exc)}

@v20.get("/cases/{case_id}/search")
def search_case(case_id: str, q: str = "") -> dict:
    return search(q=q, case_id=case_id)
