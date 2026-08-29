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
import copy
import hashlib
import json
import logging
import os
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
INDEX_DB = Path(os.environ["PEOS_DB"]) if os.environ.get("PEOS_DB") else ROOT / ".index" / "vault.db"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "ui" / "07_ENGINEERING_CONTRACTS_AND_ADAPTERS" / "adapters"))

VAULT = ROOT / "vault"
PIPELINE_OUT = ROOT / "pipeline_out" / "e3" / "K-IC" / "adapter_alpha"
INGEST_JOBS_LOG = ROOT / "logs" / "ingest_jobs.json"
RUNS_LOG = ROOT / "logs" / "runs.json"
_REGISTRY_LIMIT = 200

v20 = APIRouter(prefix="/api/v20")

V20_ACTION_CAPABILITIES: dict[str, dict[str, str]] = {
    "bootstrap": {"status": "AVAILABLE", "method": "GET", "path": "/bootstrap"},
    "loadProjection": {"status": "AVAILABLE", "method": "GET", "path": "/cases/{case_id}/projection"},
    "search": {"status": "AVAILABLE", "method": "GET", "path": "/cases/{case_id}/search"},
    "getObject": {"status": "AVAILABLE", "method": "GET", "path": "/cases/{case_id}/objects/{object_id:path}"},
    "listSources": {"status": "AVAILABLE", "method": "GET", "path": "/cases/{case_id}/sources"},
    "listInbox": {"status": "AVAILABLE", "method": "GET", "path": "/cases/{case_id}/inbox"},
    "ingest": {"status": "AVAILABLE", "method": "POST", "path": "/cases/{case_id}/ingest"},
    "getJob": {"status": "AVAILABLE", "method": "GET", "path": "/jobs/{job_id}"},
    "admitEvidence": {"status": "AVAILABLE", "method": "POST", "path": "/cases/{case_id}/ingest/{job_id}/admit"},
    "removeSource": {"status": "AVAILABLE", "method": "POST", "path": "/cases/{case_id}/sources/{source_id}/remove"},
    "addNote": {"status": "AVAILABLE", "method": "POST", "path": "/cases/{case_id}/notes"},
    "openDeal": {
        "status": "UNAVAILABLE", "method": "POST", "path": "/open-deal",
        "reason": "Connected deal creation is not implemented; no deal was created.",
    },
    "recordIC": {"status": "AVAILABLE", "method": "POST", "path": "/cases/{case_id}/ic-record"},
    "admitEvent": {"status": "AVAILABLE", "method": "POST", "path": "/cases/{case_id}/events/{event_id}/admit"},
    "listGraphVersions": {"status": "AVAILABLE", "method": "GET", "path": "/cases/{case_id}/graph-versions"},
    "getGraphVersion": {"status": "AVAILABLE", "method": "GET", "path": "/cases/{case_id}/graph-versions/{version_id:path}"},
    "prepareRun": {"status": "AVAILABLE", "method": "POST", "path": "/runs/{run_id}/prepare"},
    "attest": {"status": "AVAILABLE", "method": "POST", "path": "/runs/{run_id}/authority/attest"},
    "createPackage": {"status": "AVAILABLE", "method": "POST", "path": "/runs/{run_id}/execution-packages"},
    "sendPackage": {"status": "AVAILABLE", "method": "POST", "path": "/execution-packages/{package_id}/send"},
    "settle": {"status": "AVAILABLE", "method": "POST", "path": "/runs/{run_id}/settle"},
    "replay": {"status": "AVAILABLE", "method": "GET", "path": "/cases/{case_id}/replay"},
    "prepareWork": {"status": "AVAILABLE", "method": "POST", "path": "/cases/{case_id}/work-items/{work_id}/prepare"},
    "compilerProposals": {"status": "AVAILABLE", "method": "GET", "path": "/cases/{case_id}/compiler-proposals"},
    "reviewCompilerProposal": {"status": "AVAILABLE", "method": "POST", "path": "/cases/{case_id}/compiler-proposals/{kind}/{proposal_id}/review"},
    "prepareMission": {"status": "AVAILABLE", "method": "POST", "path": "/cases/{case_id}/missions/{mission_id}/prepare"},
    "runMission": {
        "status": "UNAVAILABLE", "method": "POST", "path": "/cases/{case_id}/missions/{mission_id}/run",
        "reason": "Connected mission execution is not implemented; no mission or external action ran.",
    },
    "newSession": {"status": "AVAILABLE", "method": "POST", "path": "/sessions"},
}

_jobs: dict[str, dict] = {}
_runs: dict[str, dict] = {}   # run_id → {transition, candidate_graph, case_id}
_inbox_lock = threading.Lock()
_notes_lock = threading.Lock()
_source_lock = threading.Lock()
_work_drafts_lock = threading.Lock()
_compiler_reviews_lock = threading.Lock()
_ic_records_lock = threading.Lock()
_mission_drafts_lock = threading.Lock()
_registry_lock = threading.RLock()
_graph_versions_lock = threading.Lock()

_COMPILER_PROPOSAL_COLLECTIONS = {
    "discrepancy": "discrepancy_candidates",
    "derivation": "derivations",
    "hypothesis": "hypotheses",
    "spine": "spine_change_proposals",
}
_COMPILER_REVIEW_DECISIONS = {"ADMITTED", "REJECTED", "CORRECTED", "ACCEPTED"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _today() -> str:
    return dt.date.today().isoformat()


def _action_capability_manifest() -> dict:
    return {
        "schema_version": "v20-action-capabilities/1.0",
        "api_prefix": "/api/v20",
        "actions": {name: dict(spec) for name, spec in V20_ACTION_CAPABILITIES.items()},
    }


def _capability_unavailable(action: str) -> JSONResponse:
    spec = V20_ACTION_CAPABILITIES[action]
    return JSONResponse(
        status_code=501,
        content={
            "error": {
                "code": "CAPABILITY_UNAVAILABLE",
                "message": spec["reason"],
                "details": {
                    "action": action,
                    "method": spec["method"],
                    "path": f"/api/v20{spec['path']}",
                },
            }
        },
    )


def _run_packages(run: dict) -> dict[str, dict]:
    packages = run.setdefault("execution_packages", {})
    if isinstance(packages, list):
        packages = {
            str(item.get("execution_package_id")): item
            for item in packages
            if isinstance(item, dict) and item.get("execution_package_id")
        }
        run["execution_packages"] = packages
    return packages


def _find_execution_package(package_id: str) -> tuple[str, dict, dict] | None:
    for run_id, run in _runs.items():
        package = _run_packages(run).get(package_id)
        if package:
            return run_id, run, package
    return None


def _execution_course(case_id: str, course_id: str) -> tuple[dict, dict]:
    projection = _build_projection(case_id)
    deal = projection.get("deal", {})
    decision_room = deal.get("decisionRoom") or deal.get("decision_room") or {}
    course = next(
        (item for item in decision_room.get("courses", []) if item.get("id") == course_id),
        {},
    )
    execution_room = deal.get("executionRoom") or deal.get("execution_room") or {}
    return course, execution_room


def _package_payload_hash(package: dict) -> str:
    mutable = {"status", "ack_id", "acknowledged_at", "failed_at"}
    payload = {key: value for key, value in package.items() if key not in mutable | {"artifact_hash"}}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _build_execution_package(run_id: str, authority_record: dict) -> dict:
    run = _runs[run_id]
    if run.get("status") != "PREPARED":
        raise HTTPException(409, "Run must be PREPARED before package creation")
    if authority_record.get("run_id") != run_id:
        raise HTTPException(409, "Authority record belongs to another run")
    if authority_record.get("candidate_state_id") != run.get("candidate_state_id"):
        raise HTTPException(409, "Authority record belongs to another Candidate")
    if authority_record.get("status") != "ATTESTED":
        raise HTTPException(409, "Execution package requires an ATTESTED authority record")
    if authority_record.get("effect_type") != "EXTERNAL_PACKAGE":
        raise HTTPException(409, "Attested course does not require an execution package")

    identity = hashlib.sha256(authority_record["authority_record_id"].encode("utf-8")).hexdigest()[:16]
    package_id = f"EXEC-{identity.upper()}"
    existing = _run_packages(run).get(package_id)
    if existing:
        return existing

    course, execution_room = _execution_course(run["case_id"], authority_record["course_id"])
    execution = course.get("execution") or {}
    known_at = _now_iso()
    package = {
        "execution_package_id": package_id,
        "run_id": run_id,
        "candidate_state_id": run["candidate_state_id"],
        "course_id": authority_record["course_id"],
        "authority_record_id": authority_record["authority_record_id"],
        "source_artifact_hash": authority_record["artifact_hash"],
        "package_type": execution_room.get("type", "Execution package"),
        "destination": execution_room.get("recipient"),
        "sender": execution_room.get("sender"),
        "subject": execution_room.get("subject"),
        "message": execution_room.get("message"),
        "attachments": execution_room.get("attachments", []),
        "checks": execution_room.get("checks", []),
        "amount": execution.get("amount"),
        "currency": execution.get("currency"),
        "document_version": execution.get("document_version"),
        "status": "READY",
        "created_at": known_at,
        "effective_date": known_at[:10],
        "known_at": known_at,
        "synthetic": True,
        "no_external_effects": True,
    }
    package["artifact_hash"] = _package_payload_hash(package)
    _run_packages(run)[package_id] = package
    _store_run(run_id, run)
    return package


def _validate_execution_package_scope(
    run: dict,
    authority_records: list[dict],
    package_ids: list[str],
) -> None:
    packages = _run_packages(run)
    for record in authority_records:
        if record.get("effect_type") != "EXTERNAL_PACKAGE":
            continue
        matches = [
            packages.get(package_id)
            for package_id in package_ids
            if packages.get(package_id)
        ]
        if not any(
            package.get("authority_record_id") == record.get("authority_record_id")
            and package.get("candidate_state_id") == run.get("candidate_state_id")
            and package.get("status") == "ACCEPTED"
            and package.get("artifact_hash") == _package_payload_hash(package)
            for package in matches
        ):
            raise HTTPException(409, "External execution package lacks a scoped simulated acknowledgment")


def _read_registry(path: Path, field: str) -> dict[str, dict]:
    """Read a durable registry without letting a missing/corrupt log stop boot."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        if not isinstance(exc, FileNotFoundError):
            logger.warning("Ignoring unreadable state registry %s: %s", path, exc)
        return {}
    records = payload.get(field, {}) if isinstance(payload, dict) else {}
    if isinstance(records, list):
        id_field = "job_id" if field == "jobs" else "run_id"
        records = {
            str(item[id_field]): item
            for item in records
            if isinstance(item, dict) and item.get(id_field)
        }
    if not isinstance(records, dict):
        return {}
    return {
        str(record_id): dict(record)
        for record_id, record in records.items()
        if isinstance(record, dict)
    }


def _write_registry(path: Path, field: str, records: dict[str, dict]) -> None:
    """Atomically persist the newest registry entries in insertion order."""
    retained = list(records.items())[-_REGISTRY_LIMIT:]
    records.clear()
    records.update(retained)
    payload = {
        "version": 1,
        "updated_at": _now_iso(),
        field: records,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _store_job(job_id: str, record: dict[str, Any] | None = None, **changes: Any) -> dict:
    with _registry_lock:
        if record is not None:
            _jobs[job_id] = dict(record)
        job = _jobs.setdefault(job_id, {"job_id": job_id})
        job.update(changes)
        job.setdefault("job_id", job_id)
        job["updated_at"] = _now_iso()
        _write_registry(INGEST_JOBS_LOG, "jobs", _jobs)
        return job


def _store_run(run_id: str, record: dict[str, Any] | None = None, **changes: Any) -> dict:
    with _registry_lock:
        if record is not None:
            _runs[run_id] = dict(record)
        run = _runs.setdefault(run_id, {"run_id": run_id})
        run.update(changes)
        run.setdefault("run_id", run_id)
        run["updated_at"] = _now_iso()
        _write_registry(RUNS_LOG, "runs", _runs)
        return run


def _load_durable_registries() -> None:
    """Hydrate jobs and admission runs when the API process starts."""
    with _registry_lock:
        _jobs.clear()
        _jobs.update(_read_registry(INGEST_JOBS_LOG, "jobs"))
        _runs.clear()
        _runs.update(_read_registry(RUNS_LOG, "runs"))


_load_durable_registries()


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
    from vercel.api._claim_graph import claims_to_graph
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

def _write_json_atomic(path: Path, payload: Any) -> None:
    """Persist one JSON artifact without exposing a partially written bundle."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _graph_versions_dir() -> Path:
    return PIPELINE_OUT / "graph_versions"


def _graph_version_index_path() -> Path:
    return _graph_versions_dir() / "index.json"


def _graph_content_hash(graph: dict) -> str:
    canonical = json.dumps(
        graph,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _graph_counts(graph: dict) -> dict[str, int]:
    return {
        "claims": len(graph.get("claims", [])),
        "case_positions": len(graph.get("case_positions", graph.get("positions", []))),
        "model_nodes": len(graph.get("model_nodes", [])),
        "support_routes": len(graph.get("support_routes", [])),
        "claim_position_edges": len(graph.get("claim_position_edges", [])),
    }


def _read_graph_version_index() -> list[dict[str, Any]]:
    payload = _load_json_safe(_graph_version_index_path())
    versions = payload.get("versions", []) if isinstance(payload, dict) else []
    return [dict(item) for item in versions if isinstance(item, dict)]


def _list_graph_versions(case_id: str) -> list[dict[str, Any]]:
    versions = [
        item for item in _read_graph_version_index()
        if str(item.get("case_id")) == str(case_id)
    ]
    return sorted(
        versions,
        key=lambda item: (
            str(item.get("created_at") or item.get("known_at") or ""),
            str(item.get("version_id") or ""),
        ),
    )


def _archive_graph_version(
    case_id: str,
    state_id: str,
    kind: str,
    graph: dict,
    *,
    run_id: str | None = None,
    event_id: str | None = None,
    prior_state_id: str | None = None,
    effective_date: str | None = None,
    known_at: str | None = None,
) -> dict[str, Any]:
    """Persist one immutable, addressable graph snapshot.

    Operational ``current_graph.json`` and ``candidate_graph.json`` may be
    promoted or cleared.  These snapshots are never rewritten with different
    content, so every institutional moment remains independently inspectable.
    """
    if not isinstance(graph, dict) or not graph:
        raise DynamicsBundleError("cannot archive an empty graph version")
    state_id = str(state_id or "").strip()
    if not state_id:
        raise DynamicsBundleError("graph version requires a state_id")
    kind = str(kind or "").upper()
    if kind not in {"CURRENT", "CANDIDATE"}:
        raise DynamicsBundleError("graph version kind must be CURRENT or CANDIDATE")

    graph_hash = _graph_content_hash(graph)
    version_id = state_id
    archive_identity = f"{case_id}\0{version_id}"
    filename = (
        re.sub(r"[^A-Za-z0-9._-]+", "-", case_id).strip("-")
        + "--"
        + re.sub(r"[^A-Za-z0-9._-]+", "-", version_id).strip("-")
        + "-"
        + hashlib.sha256(archive_identity.encode("utf-8")).hexdigest()[:10]
        + ".json"
    )
    path = _graph_versions_dir() / filename
    archived_at = dt.datetime.now(dt.timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    metadata = {
        "schema_version": "graph-version/1.0",
        "version_id": version_id,
        "state_id": state_id,
        "case_id": case_id,
        "kind": kind,
        "graph_hash": graph_hash,
        "run_id": run_id,
        "event_id": event_id,
        "prior_state_id": prior_state_id,
        "effective_date": effective_date or _today(),
        "known_at": known_at or archived_at,
        "created_at": archived_at,
        "counts": _graph_counts(graph),
        "filename": filename,
    }
    snapshot = {**metadata, "graph": copy.deepcopy(graph)}

    with _graph_versions_lock:
        if path.exists():
            existing = _load_json_safe(path)
            if (
                existing.get("version_id") != version_id
                or existing.get("case_id") != case_id
                or existing.get("graph_hash") != graph_hash
            ):
                raise DynamicsBundleError(
                    f"graph version {version_id} already exists with different content"
                )
            versions = _read_graph_version_index()
            if not any(
                item.get("case_id") == case_id
                and item.get("version_id") == version_id
                for item in versions
            ):
                existing_metadata = {
                    key: value for key, value in existing.items() if key != "graph"
                }
                versions.append(existing_metadata)
                _write_json_atomic(
                    _graph_version_index_path(),
                    {
                        "schema_version": "graph-version-index/1.0",
                        "updated_at": _now_iso(),
                        "versions": versions,
                    },
                )
            return {key: value for key, value in existing.items() if key != "graph"}

        _write_json_atomic(path, snapshot)
        versions = _read_graph_version_index()
        if not any(
            item.get("case_id") == case_id
            and item.get("version_id") == version_id
            for item in versions
        ):
            versions.append(metadata)
        _write_json_atomic(
            _graph_version_index_path(),
            {
                "schema_version": "graph-version-index/1.0",
                "updated_at": _now_iso(),
                "versions": versions,
            },
        )
    return metadata


def _load_graph_version(case_id: str, version_id: str) -> dict[str, Any]:
    metadata = next(
        (
            item for item in _list_graph_versions(case_id)
            if str(item.get("version_id")) == str(version_id)
        ),
        None,
    )
    if not metadata:
        raise HTTPException(404, f"Graph version not found: {version_id}")
    snapshot = _load_json_safe(
        _graph_versions_dir() / Path(str(metadata["filename"])).name
    )
    graph = snapshot.get("graph") if isinstance(snapshot, dict) else None
    if (
        not snapshot
        or not isinstance(graph, dict)
        or snapshot.get("graph_hash") != metadata.get("graph_hash")
        or _graph_content_hash(graph) != metadata.get("graph_hash")
    ):
        raise HTTPException(500, f"Graph version archive is inconsistent: {version_id}")
    return snapshot


def _runtime_execution_graph(case_id: str) -> Path:
    candidates = (
        VAULT / "deals" / case_id / "models" / "execution_graph_v7.json",
        PIPELINE_OUT / "execution_graph_v7.json",
        ROOT / "pipeline_out" / "e3" / "K-PRE" / "adapter_alpha" / "execution_graph_v7.json",
    )
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        raise DynamicsBundleError("execution_graph_v7.json is required to compile admitted evidence")
    return path


def _runtime_policy_path(filename: str) -> Path:
    candidates = (
        VAULT / "policy" / filename,
        ROOT / "backend" / "dynamics" / "benchmark" / filename,
    )
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        raise DynamicsBundleError(f"missing dynamics input: {filename}")
    return path


def _compile_live_runtime_bundle(claims: list[dict], case_id: str) -> dict[str, Any]:
    """Compile admitted extractor claims without inventing a fixture event.

    ``adapter_alpha`` historically assembled and executed a hard-coded EBITDA
    correction as part of bundle construction.  The connected path instead
    stages only the real Current, mapping, policies and admission manifest; the
    executable event is built separately from the newly admitted claims.
    """
    if not claims:
        raise DynamicsBundleError("at least one admitted claim is required for runtime compilation")

    from tools.adapter_alpha import _e3_to_extraction_graph
    from tools.bridge_v7 import compile_v7_bundle

    runtime_dir = PIPELINE_OUT / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    compiler_fields = [
        {
            key: claim.get(key)
            for key in ("claim_id", "metric", "direction", "topic", "author", "derivation")
        }
        for claim in claims
    ]
    e3 = {
        "schema_version": "e3/live-admission-v1",
        "manifest_id": "LIVE-ADMISSION",
        "deal": case_id,
        "extractor": "connected-v20",
        "claims": claims,
        "extraction_metadata": {"compiler_fields_per_claim": compiler_fields},
    }
    e3_path = runtime_dir / "admitted_e3_claims.json"
    _write_json_atomic(e3_path, e3)
    extraction_graph = _e3_to_extraction_graph(e3)
    extraction_graph["graph"]["e3_claims_sha256"] = hashlib.sha256(
        e3_path.read_bytes()
    ).hexdigest()
    extraction_path = runtime_dir / "extraction_graph.json"
    _write_json_atomic(extraction_path, extraction_graph)

    execution_path = _runtime_execution_graph(case_id)
    bundle = compile_v7_bundle(
        extraction_path,
        execution_path,
        status="LIVE",
        deal=case_id,
    )
    staged = {
        "current_graph.json": bundle["current_graph"],
        "execution_mapping.json": bundle["execution_mapping"],
        "adapter_report.json": bundle["adapter_report"],
        "admission_manifest_v7.json": bundle["manifest"],
    }
    for filename, value in staged.items():
        _write_json_atomic(runtime_dir / filename, value)
    (runtime_dir / "execution_graph_v7.json").write_bytes(execution_path.read_bytes())
    for filename in (
        "keystone_materiality_policy_v0.json",
        "keystone_authority_matrix_v0.json",
    ):
        source = _runtime_policy_path(filename)
        (runtime_dir / filename).write_bytes(source.read_bytes())
    return {**bundle, "runtime_dir": runtime_dir, "execution_graph_path": execution_path}


def _runtime_current_graph(case_id: str) -> dict:
    runtime_state = _load_json_safe(PIPELINE_OUT / "runtime_state.json")
    if (
        isinstance(runtime_state, dict)
        and runtime_state.get("case_id") == case_id
        and isinstance(runtime_state.get("current_graph"), dict)
    ):
        return copy.deepcopy(runtime_state["current_graph"])
    current = _load_json_safe(PIPELINE_OUT / "current_graph.json")
    if isinstance(current, dict) and current.get("case_id") == case_id:
        return copy.deepcopy(current)
    return {}


def _without_claims(graph: dict, claim_ids: set[str]) -> dict:
    """Create the pre-event runtime skeleton from a freshly compiled Current."""
    baseline = copy.deepcopy(graph)
    baseline["claims"] = [
        claim for claim in baseline.get("claims", [])
        if str(claim.get("claim_id")) not in claim_ids
    ]
    baseline["claim_position_edges"] = [
        edge for edge in baseline.get("claim_position_edges", [])
        if str(edge.get("claim_id")) not in claim_ids
    ]
    for position in baseline.get("case_positions", []):
        for field in ("support_claim_ids", "contradicting_claim_ids"):
            if isinstance(position.get(field), list):
                position[field] = [item for item in position[field] if str(item) not in claim_ids]
        if isinstance(position.get("support_routes"), list):
            position["support_routes"] = [
                route for route in position["support_routes"]
                if str(route.get("claim_stable_id")) not in claim_ids
            ]
    retained_routes = []
    for route in baseline.get("support_routes", []):
        if str(route.get("claim_stable_id")) in claim_ids:
            continue
        for field in ("member_claim_ids", "counter_claim_ids"):
            if isinstance(route.get(field), list):
                route[field] = [item for item in route[field] if str(item) not in claim_ids]
        retained_routes.append(route)
    baseline["support_routes"] = retained_routes
    return baseline


def _normalise_runtime_unit(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    aliases = {"$m": "$mm", "$mn": "$mm", "usd_m": "$mm", "decimal ratio": "decimal_ratio"}
    return aliases.get(value.strip().lower(), value.strip())


def _claim_mapping_is_applicable(claim: dict, position: dict) -> bool:
    pairs = (
        (claim.get("definition_id"), position.get("definition_id", position.get("definition"))),
        (claim.get("period_iso") or claim.get("period"), position.get("period")),
        (claim.get("perimeter"), position.get("perimeter")),
        (_normalise_runtime_unit(claim.get("unit")), _normalise_runtime_unit(position.get("unit"))),
    )
    return all(left is None or right is None or left == right for left, right in pairs)


def _build_admitted_runtime_event(
    case_id: str,
    job_id: str,
    proposal: dict,
    added_claims: list[dict],
    compiled_graph: dict,
    baseline_graph: dict,
) -> dict:
    added_ids = {
        str(claim.get("claim_id") or claim.get("id") or claim.get("stable_id"))
        for claim in added_claims
    }
    compiled_claims = {
        str(claim.get("claim_id")): claim
        for claim in compiled_graph.get("claims", [])
        if str(claim.get("claim_id")) in added_ids
    }
    if not compiled_claims:
        raise DynamicsBundleError(
            "new evidence produced no runtime-admitted claims; inspect temporal/validation coverage"
        )

    baseline_positions = {
        str(position.get("position_id")): position
        for position in baseline_graph.get("case_positions", [])
    }
    edges_by_claim: dict[str, list[dict]] = {}
    for edge in compiled_graph.get("claim_position_edges", []):
        claim_id = str(edge.get("claim_id") or "")
        if claim_id in compiled_claims:
            edges_by_claim.setdefault(claim_id, []).append(edge)

    mutations = []
    mapped_claim_ids = []
    for claim_id in sorted(compiled_claims):
        claim = compiled_claims[claim_id]
        mutation = {
            "operation": "ADD",
            "object_type": "CLAIM",
            "object_id": claim_id,
            "statement": claim.get("statement") or claim_id,
            "locator": claim.get("locator") or f"proposal:{proposal.get('proposal_id', job_id)}",
            "epistemic_class": claim.get("epistemic_class", "observed"),
            "period": claim.get("period_iso") or claim.get("period") or "UNSPECIFIED",
            "perimeter": claim.get("perimeter") or "UNSPECIFIED",
            "ground_truth_flag": bool(claim.get("ground_truth_flag", False)),
        }
        for field in ("definition_id", "unit", "value"):
            if claim.get(field) is not None:
                mutation[field] = copy.deepcopy(claim[field])

        for edge in sorted(
            edges_by_claim.get(claim_id, []),
            key=lambda item: (str(item.get("position_id")), str(item.get("relation_type"))),
        ):
            position_id = str(edge.get("position_id") or "")
            position = baseline_positions.get(position_id)
            if position and _claim_mapping_is_applicable(claim, position):
                mutation["relation_type"] = edge.get("relation_type", "SUPPORTS")
                mutation["target_position_id"] = position_id
                mapped_claim_ids.append(claim_id)
                break
        mutations.append(mutation)

    now = _now_iso()
    source_ids = sorted(
        {
            str(claim.get("source_id"))
            for claim in compiled_claims.values()
            if claim.get("source_id")
        }
        | ({str(proposal.get("source_id"))} if proposal.get("source_id") else set())
    )
    return {
        "event_id": f"EVIDENCE-ADMITTED-{job_id}",
        "event": f"EVIDENCE_ADMITTED: {proposal.get('source_id') or 'reviewed source'}",
        "event_type": "evidence_admitted",
        "event_status": "ADMITTED_SOURCE_EVENT",
        "deal": case_id,
        "effective_date": _today(),
        "known_at": now,
        "source_ids": source_ids,
        "trigger_claim_ids": sorted(compiled_claims),
        "mutations": mutations,
        "proposal_id": proposal.get("proposal_id"),
        "evidence_claim_ids": sorted(compiled_claims),
        "mapped_claim_ids": sorted(mapped_claim_ids),
        "unmapped_claim_ids": sorted(set(compiled_claims) - set(mapped_claim_ids)),
        "note": "Built from professionally admitted extractor output; no fixture event or claim was introduced.",
    }


def _promote_live_runtime_bundle(compiled: dict, baseline_graph: dict, event: dict) -> Path:
    runtime_dir = Path(compiled["runtime_dir"])
    _write_json_atomic(PIPELINE_OUT / "current_graph.json", baseline_graph)
    for filename in (
        "execution_mapping.json",
        "adapter_report.json",
        "admission_manifest_v7.json",
    ):
        _write_json_atomic(PIPELINE_OUT / filename, _load_json_safe(runtime_dir / filename))
    for filename in (
        "execution_graph_v7.json",
        "keystone_materiality_policy_v0.json",
        "keystone_authority_matrix_v0.json",
    ):
        (PIPELINE_OUT / filename).write_bytes((runtime_dir / filename).read_bytes())
    event_path = PIPELINE_OUT / f"event_evidence_admitted_{event['event_id'].removeprefix('EVIDENCE-ADMITTED-')}.json"
    _write_json_atomic(event_path, event)
    _write_json_atomic(PIPELINE_OUT / "candidate_graph.json", {})
    _write_json_atomic(PIPELINE_OUT / "transition_output.json", {})
    return event_path

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


def _note_record(path: Path) -> dict:
    """Read one append-only note without relying on the derived search index."""
    raw = path.read_text(encoding="utf-8")
    metadata = _read_frontmatter(path)
    match = re.match(r"^---\n.*?\n---\n?(.*)$", raw, re.DOTALL)
    return {
        **metadata,
        "text": (match.group(1) if match else raw).strip(),
    }


def _case_vault_dir(case_id: str) -> Path:
    """Resolve a case directory while preventing path traversal."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", case_id):
        raise HTTPException(400, "case_id contains unsupported characters")
    return VAULT / "deals" / case_id


def _notes_dir(case_id: str) -> Path:
    return _case_vault_dir(case_id) / "notes"


def _compiler_proposal_id(kind: str, item: dict) -> str:
    keys = {
        "discrepancy": ("discrepancy_id", "id"),
        "derivation": ("derivation_id", "id"),
        "hypothesis": ("hypothesis_id", "id"),
        "spine": ("proposal_id", "id"),
    }[kind]
    return str(next((item.get(key) for key in keys if item.get(key)), ""))


def _load_compiler_reviews(case_id: str) -> dict[str, dict]:
    review_dir = _case_vault_dir(case_id) / "compiler_reviews"
    if not review_dir.exists():
        return {}
    reviews: dict[str, dict] = {}
    records = [_note_record(path) for path in sorted(review_dir.glob("compiler-review-*.md"))]
    records.sort(key=lambda item: (str(item.get("known_at", "")), str(item.get("review_id", ""))))
    for record in records:
        kind = str(record.get("kind") or "")
        object_id = str(record.get("object_id") or "")
        if kind in _COMPILER_PROPOSAL_COLLECTIONS and object_id:
            reviews[f"{kind}:{object_id}"] = record
    return reviews


def _apply_compiler_reviews(projection: dict, case_id: str) -> dict:
    """Overlay review state without mutating proposal facts or Current case state."""
    deal = projection.get("deal") if isinstance(projection, dict) else None
    if not isinstance(deal, dict):
        return projection
    reviews = _load_compiler_reviews(case_id)
    for kind, collection in _COMPILER_PROPOSAL_COLLECTIONS.items():
        reviewed_items = []
        for original in deal.get(collection, []) or []:
            item = dict(original)
            object_id = _compiler_proposal_id(kind, item)
            review = reviews.get(f"{kind}:{object_id}")
            if review:
                item["review_status"] = review.get("decision")
                item["latest_review"] = review
            reviewed_items.append(item)
        deal[collection] = reviewed_items
    return projection

def _load_json_safe(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else {}


def _current_state_id(case_id: str) -> str:
    """Use the settled runtime state as the authoritative Current version."""
    runtime_state = _load_json_safe(PIPELINE_OUT / "runtime_state.json")
    if isinstance(runtime_state, dict) and runtime_state.get("state_id"):
        return str(runtime_state["state_id"])
    current_graph = _load_json_safe(PIPELINE_OUT / "current_graph.json")
    if isinstance(current_graph, dict) and current_graph.get("state_id"):
        return str(current_graph["state_id"])
    return f"STATE-{case_id.upper()}-CURRENT"

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


def _load_projection_events(case_id: str) -> dict[str, dict]:
    """Project durable vault events into the V20 change-arrival contract."""
    events_dir = VAULT / "deals" / case_id / "events"
    if not events_dir.exists():
        return {}
    events: dict[str, dict] = {}
    for md in sorted(events_dir.glob("*.md")):
        fm = _read_frontmatter(md)
        event_id = str(fm.get("id") or fm.get("event_id") or "")
        if not event_id:
            continue
        known_at = str(fm.get("known_at") or fm.get("timestamp") or _now_iso())
        if len(known_at) == 8 and known_at.isdigit():
            known_at = f"{known_at[:4]}-{known_at[4:6]}-{known_at[6:]}T00:00:00Z"
        events[event_id] = {
            "event_id": event_id, "id": event_id,
            "type": fm.get("type", "institutional_event"),
            "label": fm.get("label") or f"{fm.get('type', 'Event').replace('_', ' ').title()}: {fm.get('source', event_id)}",
            "source_title": fm.get("source", "PANTA evidence intake"),
            "source_version_id": fm.get("proposal_id", fm.get("source", "")),
            "source_passage": fm.get("detail", "Evidence admitted after professional review."),
            "locator": fm.get("locator", ""), "definition": fm.get("definition_id", ""),
            "period": fm.get("period", ""), "perimeter": fm.get("perimeter", ""),
            "effective_date": str(fm.get("effective_date") or known_at[:10]),
            "known_at": known_at, "proposed_treatment": fm.get("proposed_treatment", "Run dynamics against the admitted semantic Current."),
            "proposed_position": fm.get("proposed_position", "Run dynamics against the admitted semantic Current."),
        }
    return events

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

def _load_source_retirements(case_id: str) -> dict[str, dict]:
    events_dir = _case_vault_dir(case_id) / "events"
    if not events_dir.exists():
        return {}
    retired: dict[str, dict] = {}
    for path in sorted(events_dir.glob("*.md")):
        metadata = _read_frontmatter(path)
        if str(metadata.get("type", "")).lower() != "source_retired":
            continue
        source_id = str(metadata.get("source_id") or "")
        if source_id:
            retired[source_id] = metadata
    return retired


def _apply_source_retirements(items: list[dict], case_id: str) -> list[dict]:
    retirements = _load_source_retirements(case_id)
    sources = []
    for item in items:
        source = dict(item)
        retirement = retirements.get(str(source.get("source_id") or ""))
        if retirement:
            source.update(
                status="RETIRED",
                retired_at=retirement.get("known_at"),
                retirement_event_id=retirement.get("id"),
            )
        else:
            source.setdefault("status", "ACTIVE")
        sources.append(source)
    return sources


def _build_sources_from_claims(raw: list[dict], case_id: str | None = None) -> list[dict]:
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
    sources = list(seen.values())
    return _apply_source_retirements(sources, case_id) if case_id else sources

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
    sources = _build_sources_from_claims(raw_claims, case_id)
    events = _load_projection_events(case_id)
    questions = _load_questions(case_id)
    question_spine = _build_question_spine(questions, claims)
    semantic_graph = _load_json_safe(PIPELINE_OUT / "semantic_current_graph.json")
    foundations, unknowns, semantic_positions = _semantic_rooms(semantic_graph, question_spine) if semantic_graph else ([], {"items": []}, [])

    current_graph = _load_json_safe(PIPELINE_OUT / "current_graph.json")
    candidate_graph = _load_json_safe(PIPELINE_OUT / "candidate_graph.json")
    transition_output = _load_json_safe(PIPELINE_OUT / "transition_output.json")
    graph_versions = _list_graph_versions(case_id)

    if isinstance(current_graph, dict) and "case_positions" in current_graph:
        current_graph = {**current_graph, "positions": current_graph["case_positions"]}

    today = _today()
    as_of_date = as_of_date or today
    state_id = _current_state_id(case_id)

    # All the dates for temporal
    available_dates = sorted(set(
        [c.get("known_at", "")[:10] for c in claims if c.get("known_at")]
        + [e.get("known_at", "")[:10] for e in events.values() if e.get("known_at")]
        + [today]
    ))
    snapshots = [{
        "id": f"STATE-{event_id}", "event_id": event_id,
        "date": event["effective_date"], "effective_date": event["effective_date"],
        "known_at": event["known_at"], "label": event["label"],
        "known": [event["source_title"]], "believed": [], "approved": [], "open": [],
        "stable_hash": "sha256:" + hashlib.sha256(event_id.encode()).hexdigest(),
    } for event_id, event in events.items()]

    projection = {
        "schema_version": "frontend-projection/20.0",
        "package_version": "20.0.0",
        "disclosure": {},
        "fund": {
            "situations": [],
            "morning_delta": [],
        },
        "events": events,
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
                "snapshots": snapshots,
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
            "graph_versions": graph_versions,
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
        result["deal"]["graph_versions"] = graph_versions
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
        return _apply_compiler_reviews(result, case_id)
    except Exception as exc:
        projection["_adapter_error"] = str(exc)
        return _apply_compiler_reviews(projection, case_id)


# ── Routes ────────────────────────────────────────────────────────────────────

@v20.get("/health")
def health() -> dict:
    return {"status": "ok", "schema_version": "frontend-projection/20.0"}


@v20.get("/capabilities")
def action_capabilities() -> dict:
    """Publish the connected-mode action contract consumed by clients and tests."""
    return _action_capability_manifest()


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
    state_id = _current_state_id(cid)
    session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"
    return {
        "session_id": session_id,
        "available_cases": [cid],
        "cases": [cid],
        "context": _make_context(cid, state_id, today),
        "action_capabilities": _action_capability_manifest(),
    }

# Also keep the /cases/{id}/bootstrap for direct calls
@v20.get("/cases/{case_id}/bootstrap")
def bootstrap(case_id: str) -> dict:
    deal_md = VAULT / "deals" / case_id / "deal.md"
    if not deal_md.exists():
        raise HTTPException(404, f"Deal not found: {case_id}")
    profile = _load_profile(case_id)
    today = _today()
    state_id = _current_state_id(case_id)
    session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"
    return {
        "session_id": session_id,
        "available_cases": [case_id],
        "cases": [case_id],
        "context": _make_context(case_id, state_id, today),
        "action_capabilities": _action_capability_manifest(),
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
    state_id = _current_state_id(case_id)
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


@v20.get("/cases/{case_id}/graph-versions")
def list_graph_versions(case_id: str) -> dict:
    return {
        "case_id": case_id,
        "versions": _list_graph_versions(case_id),
    }


@v20.get("/cases/{case_id}/graph-versions/{version_id:path}")
def get_graph_version(case_id: str, version_id: str) -> dict:
    return _load_graph_version(case_id, version_id)


@v20.get("/cases/{case_id}/sources")
def sources(case_id: str) -> dict:
    raw = _load_claims()
    srcs = _build_sources_from_claims(raw, case_id)
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


@v20.post("/cases/{case_id}/sources/{source_id}/remove")
def retire_source(case_id: str, source_id: str, payload: dict | None = None) -> dict:
    """Retire a source from Current without deleting its claims or history."""
    payload = payload or {}
    current_sources = _build_sources_from_claims(_load_claims(), case_id)
    source = next((item for item in current_sources if item.get("source_id") == source_id), None)
    if not source:
        raise HTTPException(404, f"Source not found: {source_id}")
    if source.get("status") == "RETIRED":
        return {"status": "RETIRED", "source": source, "idempotent_replay": True}

    identity = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:16]
    event_id = f"SOURCE-RETIRED-{identity.upper()}"
    known_at = _now_iso()
    metadata = {
        "type": "source_retired",
        "id": event_id,
        "case": case_id,
        "source_id": source_id,
        "label": "Source retired from Current projection",
        "detail": "Historical source data and claims remain available for audit.",
        "actor": payload.get("actor_id", "source-registry"),
        "effective_date": payload.get("effective_date") or known_at[:10],
        "known_at": known_at,
        "written-by": "v20-api",
    }
    events_dir = _case_vault_dir(case_id) / "events"
    event_path = events_dir / f"source-retired-{identity}.md"
    with _source_lock:
        events_dir.mkdir(parents=True, exist_ok=True)
        try:
            with event_path.open("x", encoding="utf-8") as handle:
                handle.write(
                    "---\n"
                    + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
                    + "---\n\n"
                    + metadata["detail"]
                    + "\n"
                )
        except FileExistsError:
            existing = _read_frontmatter(event_path)
            source.update(
                status="RETIRED",
                retired_at=existing.get("known_at"),
                retirement_event_id=existing.get("id"),
            )
            return {"status": "RETIRED", "source": source, "idempotent_replay": True}

    source.update(status="RETIRED", retired_at=known_at, retirement_event_id=event_id)
    return {"status": "RETIRED", "source": source, "idempotent_replay": False}


@v20.post("/open-deal")
def open_deal_unavailable() -> JSONResponse:
    return _capability_unavailable("openDeal")


@v20.post("/cases/{case_id}/ic-record")
def record_ic(case_id: str, payload: dict | None = None) -> dict:
    """Persist the IC ritual as a decision record without rewriting Approved."""
    payload = payload or {}
    decision = str(payload.get("decision") or "").upper()
    allowed = {"APPROVE", "REJECT", "DEFER", "APPROVE_WITH_CONDITIONS"}
    if decision not in allowed:
        raise HTTPException(400, "decision must be APPROVE, REJECT, DEFER or APPROVE_WITH_CONDITIONS")
    authority = str(payload.get("authority") or "").strip()
    if not authority:
        raise HTTPException(400, "authority / quorum is required")

    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if idempotency_key:
        identity = hashlib.sha256(f"{case_id}|{idempotency_key}".encode("utf-8")).hexdigest()[:16]
    else:
        identity = uuid.uuid4().hex[:16]
    record_id = f"IC-{identity.upper()}"
    decisions_dir = _case_vault_dir(case_id) / "decisions"
    record_path = decisions_dir / f"decision-ic-{identity}.md"

    with _ic_records_lock:
        if record_path.exists():
            return {
                "status": "ACKNOWLEDGED",
                "record": _note_record(record_path),
                "message": "Existing IC record returned; Approved was not rewritten.",
                "idempotent_replay": True,
            }

        known_at = _now_iso()
        actor_id = str(payload.get("actor_id") or "ic-recorder")
        conditions = str(payload.get("conditions") or "").strip()
        dissent = str(payload.get("dissent") or "").strip()
        record = {
            "type": "decision",
            "id": record_id,
            "deal": case_id,
            "date": payload.get("effective_date") or known_at[:10],
            "decided-by": [actor_id],
            "commitment": decision,
            "dissent": [dissent] if dissent else [],
            "conditions": conditions,
            "authority": authority,
            "as_of_state_id": payload.get("as_of_state_id"),
            "known_at": known_at,
            "idempotency_key": idempotency_key or None,
            "institutional_effect": "RECORD_ONLY",
            "approved_state_mutation": False,
            "supersedes": None,
            "written-by": actor_id,
        }
        decisions_dir.mkdir(parents=True, exist_ok=True)
        body = (
            f"# Decision: {decision}\n\n"
            "## Resolved — on what strength\n"
            "Decision basis remains the referenced Current case; this endpoint records the ritual only.\n\n"
            "## Accepted as unresolved — and why tolerable\n"
            f"{conditions or 'None recorded.'}\n\n"
            "## Dissent\n"
            f"{dissent or 'None recorded.'}\n\n"
            "## Basis\n"
            f"Authority / quorum recorded as: {authority}.\n"
        )
        with record_path.open("x", encoding="utf-8") as handle:
            handle.write(
                "---\n"
                + yaml.safe_dump(record, sort_keys=False, allow_unicode=True)
                + "---\n\n"
                + body
            )
    return {
        "status": "ACKNOWLEDGED",
        "record": record,
        "message": "IC decision, conditions and dissent recorded; Approved remains unchanged.",
        "idempotent_replay": False,
    }


@v20.get("/cases/{case_id}/ic-records")
def list_ic_records(case_id: str) -> dict:
    decisions_dir = _case_vault_dir(case_id) / "decisions"
    if not decisions_dir.exists():
        return {"records": []}
    records = [_note_record(path) for path in sorted(decisions_dir.glob("decision-ic-*.md"))]
    records.sort(key=lambda item: (str(item.get("known_at", "")), str(item.get("id", ""))))
    return {"records": records}


@v20.post("/runs/{run_id}/execution-packages")
def create_execution_package(run_id: str, payload: dict | None = None) -> dict:
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, f"Run not found: {run_id}")
    payload = payload or {}
    record_id = str(payload.get("authority_record_id") or "")
    records = run.get("authority_records", [])
    record = next(
        (item for item in records if not record_id or item.get("authority_record_id") == record_id),
        None,
    )
    if record is None:
        raise HTTPException(409, "A scoped authority record is required")
    package = _build_execution_package(run_id, record)
    return {"execution_package": package, "registry": []}


@v20.post("/execution-packages/{package_id}/send")
def send_execution_package(package_id: str, payload: dict | None = None):
    located = _find_execution_package(package_id)
    if not located:
        raise HTTPException(404, f"Execution package not found: {package_id}")
    run_id, run, package = located
    if package.get("artifact_hash") != _package_payload_hash(package):
        raise HTTPException(409, "Execution package immutable payload hash mismatch")
    payload = payload or {}
    known_at = _now_iso()
    if payload.get("simulate_failure"):
        package["status"] = "FAILED"
        package["failed_at"] = known_at
        _store_run(run_id, run)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "DELIVERY_FAILED",
                    "message": "Simulated delivery failed; nothing was sent.",
                    "details": {"execution_package_id": package_id},
                }
            },
        )
    if package.get("status") != "ACCEPTED":
        package["status"] = "ACCEPTED"
        package["ack_id"] = "ACK-" + hashlib.sha256(package_id.encode("utf-8")).hexdigest()[:12].upper()
        package["acknowledged_at"] = known_at
        _store_run(run_id, run)
    return {"execution_package": package, "registry": []}


@v20.post("/cases/{case_id}/work-items/{work_id}/prepare")
def prepare_work(case_id: str, work_id: str, payload: dict | None = None) -> dict:
    """Prepare and persist a draft without dispatching work or creating authority."""
    payload = payload or {}
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if idempotency_key:
        identity_seed = f"{case_id}|{work_id}|{idempotency_key}"
        identity = hashlib.sha256(identity_seed.encode("utf-8")).hexdigest()[:16]
    else:
        identity = uuid.uuid4().hex[:16]
    draft_id = f"DRAFT-{identity.upper()}"
    drafts_dir = _case_vault_dir(case_id) / "work_drafts"
    draft_path = drafts_dir / f"work-draft-{identity}.md"

    with _work_drafts_lock:
        if draft_path.exists():
            return {
                "draft": _note_record(draft_path),
                "message": "Existing draft returned. Nothing was dispatched externally.",
                "idempotent_replay": True,
            }

        known_at = _now_iso()
        metadata = {
            "type": "work_draft",
            "id": draft_id,
            "draft_id": draft_id,
            "case": case_id,
            "work_item_id": work_id,
            "status": "DRAFT",
            "owner": payload.get("owner"),
            "object_id": payload.get("object_id"),
            "actor_id": payload.get("actor_id", "unknown-actor"),
            "instructions": payload.get("instructions"),
            "created_at": known_at,
            "effective_date": payload.get("effective_date") or known_at[:10],
            "known_at": known_at,
            "idempotency_key": idempotency_key or None,
            "synthetic": False,
            "no_external_effects": True,
            "written-by": "v20-api",
        }
        drafts_dir.mkdir(parents=True, exist_ok=True)
        with draft_path.open("x", encoding="utf-8") as handle:
            handle.write(
                "---\n"
                + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
                + "---\n\n"
                + f"Draft for work item {work_id}. Prepared only; no external dispatch occurred.\n"
            )
    return {
        "draft": metadata,
        "message": "Draft prepared in PANTA. It was not dispatched externally.",
        "idempotent_replay": False,
    }


@v20.get("/cases/{case_id}/work-items/{work_id}/drafts")
def list_work_drafts(case_id: str, work_id: str) -> dict:
    drafts_dir = _case_vault_dir(case_id) / "work_drafts"
    if not drafts_dir.exists():
        return {"drafts": []}
    drafts = [
        _note_record(path)
        for path in sorted(drafts_dir.glob("work-draft-*.md"))
        if _read_frontmatter(path).get("work_item_id") == work_id
    ]
    drafts.sort(key=lambda draft: (str(draft.get("known_at", "")), str(draft.get("draft_id", ""))))
    return {"drafts": drafts}


@v20.get("/cases/{case_id}/compiler-proposals")
def compiler_proposals(case_id: str) -> dict:
    projection = _apply_compiler_reviews(_build_projection(case_id), case_id)
    deal = projection.get("deal", {})
    return {
        "discrepancies": deal.get("discrepancy_candidates", []),
        "derivations": deal.get("derivations", []),
        "hypotheses": deal.get("hypotheses", []),
        "spine_changes": deal.get("spine_change_proposals", []),
    }


@v20.post("/cases/{case_id}/compiler-proposals/{kind}/{proposal_id}/review")
def review_compiler_proposal(
    case_id: str,
    kind: str,
    proposal_id: str,
    payload: dict | None = None,
) -> dict:
    """Record a professional proposal disposition without silently mutating Current."""
    payload = payload or {}
    if kind not in _COMPILER_PROPOSAL_COLLECTIONS:
        raise HTTPException(400, "kind must be discrepancy, derivation, hypothesis or spine")
    decision = str(payload.get("decision") or "").upper()
    if decision not in _COMPILER_REVIEW_DECISIONS:
        raise HTTPException(400, "decision must be ADMITTED, ACCEPTED, CORRECTED or REJECTED")

    projection = _apply_compiler_reviews(_build_projection(case_id), case_id)
    collection = _COMPILER_PROPOSAL_COLLECTIONS[kind]
    proposal = next(
        (
            item for item in projection.get("deal", {}).get(collection, [])
            if _compiler_proposal_id(kind, item) == proposal_id
        ),
        None,
    )
    if proposal is None:
        raise HTTPException(404, f"Compiler proposal not found: {proposal_id}")

    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if idempotency_key:
        identity_seed = f"{case_id}|{kind}|{proposal_id}|{idempotency_key}"
        identity = hashlib.sha256(identity_seed.encode("utf-8")).hexdigest()[:16]
    else:
        identity = uuid.uuid4().hex[:16]
    review_id = f"REVIEW-{identity.upper()}"
    review_dir = _case_vault_dir(case_id) / "compiler_reviews"
    review_path = review_dir / f"compiler-review-{identity}.md"

    with _compiler_reviews_lock:
        if review_path.exists():
            review = _note_record(review_path)
            replayed = True
        else:
            known_at = _now_iso()
            review = {
                "type": "compiler_review",
                "id": review_id,
                "review_id": review_id,
                "case": case_id,
                "kind": kind,
                "object_id": proposal_id,
                "decision": decision,
                "rationale": payload.get("rationale"),
                "actor_id": payload.get("actor_id", "professional-reviewer"),
                "effective_date": payload.get("effective_date") or known_at[:10],
                "known_at": known_at,
                "idempotency_key": idempotency_key or None,
                "institutional_effect": "REVIEW_RECORDED_ONLY",
                "current_mutation": False,
                "written-by": "v20-api",
            }
            review_dir.mkdir(parents=True, exist_ok=True)
            with review_path.open("x", encoding="utf-8") as handle:
                handle.write(
                    "---\n"
                    + yaml.safe_dump(review, sort_keys=False, allow_unicode=True)
                    + "---\n\n"
                    + f"Professional review of {kind} proposal {proposal_id}: {decision}.\n"
                )
            replayed = False

    updated_projection = _apply_compiler_reviews(_build_projection(case_id), case_id)
    as_of_date = updated_projection.get("deal", {}).get("as_of_date") or _today()
    state_id = updated_projection.get("deal", {}).get("as_of_state_id") or _current_state_id(case_id)
    return {
        "review": review,
        "projection": updated_projection,
        "context": _make_context(case_id, state_id, as_of_date),
        "registry": [],
        "idempotent_replay": replayed,
    }


@v20.post("/cases/{case_id}/missions/{mission_id}/prepare")
def prepare_mission(case_id: str, mission_id: str, payload: dict | None = None) -> dict:
    """Persist the governed mission envelope without running any mission work."""
    payload = payload or {}
    projection = _build_projection(case_id)
    mission = next(
        (
            item for item in projection.get("deal", {}).get("agent_missions", [])
            if mission_id in {item.get("mission_id"), item.get("id")}
        ),
        None,
    )
    if mission is None:
        raise HTTPException(404, f"Mission not found: {mission_id}")

    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if idempotency_key:
        identity_seed = f"{case_id}|{mission_id}|{idempotency_key}"
        identity = hashlib.sha256(identity_seed.encode("utf-8")).hexdigest()[:16]
    else:
        identity = uuid.uuid4().hex[:16]
    mission_run_id = f"MISSION-DRAFT-{identity.upper()}"
    drafts_dir = _case_vault_dir(case_id) / "mission_runs"
    draft_path = drafts_dir / f"mission-draft-{identity}.md"

    with _mission_drafts_lock:
        if draft_path.exists():
            return {
                "mission_run": _note_record(draft_path),
                "message": "Existing mission draft returned. No research or human contact occurred.",
                "idempotent_replay": True,
            }

        known_at = _now_iso()
        draft = {
            "type": "mission_draft",
            "id": mission_run_id,
            "mission_run_id": mission_run_id,
            "mission_id": mission_id,
            "case": case_id,
            "status": "PREPARED",
            "label": mission.get("label"),
            "mission_type": mission.get("mission_type"),
            "objective": mission.get("objective"),
            "question_ids": mission.get("question_ids", []),
            "unknown_ids": mission.get("unknown_ids", []),
            "allowed_sources": mission.get("allowed_sources", []),
            "prohibited_sources": mission.get("prohibited_sources", []),
            "confidential_context_policy": mission.get("confidential_context_policy"),
            "data_egress_policy": mission.get("data_egress_policy"),
            "expected_output": mission.get("expected_output"),
            "stop_condition": mission.get("stop_condition"),
            "authority_class": mission.get("authority_class"),
            "reviewer_id": mission.get("reviewer_id"),
            "external_human_contact": bool(mission.get("external_human_contact")),
            "auto_executable_in_mock": bool(mission.get("auto_executable_in_mock")),
            "prepared_by": payload.get("actor_id", "mission-preparer"),
            "effective_date": payload.get("effective_date") or known_at[:10],
            "known_at": known_at,
            "idempotency_key": idempotency_key or None,
            "synthetic": False,
            "no_external_effects": True,
            "written-by": "v20-api",
        }
        drafts_dir.mkdir(parents=True, exist_ok=True)
        with draft_path.open("x", encoding="utf-8") as handle:
            handle.write(
                "---\n"
                + yaml.safe_dump(draft, sort_keys=False, allow_unicode=True)
                + "---\n\n"
                + "Governed mission envelope prepared. No research, data egress or human contact occurred.\n"
            )
    return {
        "mission_run": draft,
        "message": "Mission draft prepared. No research or human contact occurred.",
        "idempotent_replay": False,
    }


@v20.get("/cases/{case_id}/missions/{mission_id}/drafts")
def list_mission_drafts(case_id: str, mission_id: str) -> dict:
    drafts_dir = _case_vault_dir(case_id) / "mission_runs"
    if not drafts_dir.exists():
        return {"mission_runs": []}
    drafts = [
        _note_record(path)
        for path in sorted(drafts_dir.glob("mission-draft-*.md"))
        if _read_frontmatter(path).get("mission_id") == mission_id
    ]
    drafts.sort(key=lambda item: (str(item.get("known_at", "")), str(item.get("mission_run_id", ""))))
    return {"mission_runs": drafts}


@v20.post("/cases/{case_id}/missions/{mission_id}/run")
def run_mission_unavailable(case_id: str, mission_id: str) -> JSONResponse:
    return _capability_unavailable("runMission")


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
    _store_job(job_id, {
        "status": "PENDING", "job_id": job_id,
        "artifact": filename, "case_id": case_id, "purpose": purpose,
        "label": filename or "extraction run",
        "stage": "Queued", "progress": 0,
        "created_at": _now_iso(),
    })
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
        _store_job(job_id, status="RUNNING", stage="Extracting", progress=10)
        _update_inbox_record(job_id, status="RUNNING", stage="Extracting", progress=10,
                             message="Source is being extracted into typed claims.")
        source_path = (inbox_dir / filename) if filename else None
        import os as _os

        # Excel is routed to V2: unlike V1 it chunks a workbook by sheet/range
        # and retains formula + cached-value provenance. V1 flattens a workbook
        # to one prompt and therefore truncates non-trivial models.
        if source_path and source_path.exists() and source_path.suffix.lower() in (".xlsx", ".xlsm"):
            manifest_label = "SINGLE_V2"
            run_dir = PIPELINE_OUT / "runs" / job_id
            cmd = [sys.executable, str(ROOT / "tools" / "extract_v2.py"),
                   "--source", str(source_path), "--deal", case_id,
                   "--output", str(run_dir)]
        # For PDF and narrative files, V1 is the lightweight extraction path.
        elif source_path and source_path.exists() and source_path.suffix.lower() in (".md", ".txt", ".pdf"):
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

        # Pass the selected provider environment explicitly to the extractor.
        provider = _os.environ.get("PEOS_LLM_PROVIDER", "anthropic").lower()
        key_name = "OPENROUTER_API_KEY" if provider == "openrouter" else "ANTHROPIC_API_KEY"
        env = {**_os.environ, key_name: _os.environ.get(key_name, "")}
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
                output_dir = (PIPELINE_OUT / "runs" / job_id) if manifest_label in {"SINGLE", "SINGLE_V2"} else (PIPELINE_OUT / manifest_label)
                # V2 writes the manifest under its deterministic SINGLE label;
                # V1 writes directly to its requested output directory.
                e3_out = output_dir / "e3_claims.json"
                if manifest_label == "SINGLE_V2":
                    e3_out = output_dir / "SINGLE" / "e3_claims.json"
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
                        proposal_display_path = (
                            str(proposal.relative_to(ROOT))
                            if proposal.is_relative_to(ROOT)
                            else str(proposal)
                        )
                        _store_job(job_id, proposal_id=proposal.stem,
                                   proposal_path=proposal_display_path,
                                   proposed_claim_count=len(new_claims),
                                   admission_status="PENDING_REVIEW")
                        _update_inbox_record(job_id, proposal_id=proposal.stem,
                                             proposal_path=proposal_display_path,
                                             proposed_claim_count=len(new_claims),
                                             admission_status="PENDING_REVIEW")
                        logger.info("JOB %s produced %d evidence proposals", job_id, len(new_claims))
                    except Exception as merge_exc:
                        logger.error("JOB %s merge failed: %s", job_id, merge_exc)

            _store_job(
                job_id,
                status="COMPLETE" if ok else "ERROR",
                stage="Complete" if ok else "Failed",
                progress=100 if ok else 0,
                stdout=(r.stdout or "")[-2000:],
                stderr=(r.stderr or "")[-1000:],
                message="Extraction complete — evidence is ready for professional review."
                if ok else (r.stderr or "")[-300:],
            )
            _update_inbox_record(
                job_id, status="COMPLETE" if ok else "ERROR",
                stage="Complete" if ok else "Failed", progress=100 if ok else 0,
                message="Extraction complete; admit, edit or reject the proposed evidence before it enters Current."
                if ok else (r.stderr or "Extraction failed")[-300:],
            )
        except Exception as exc:
            logger.error("JOB %s EXCEPTION %s", job_id, exc)
            _store_job(job_id, status="ERROR", stage="Failed", error=str(exc), message=str(exc))
            _update_inbox_record(job_id, status="ERROR", stage="Failed", progress=0, message=str(exc))
        _rebuild_index()

    background_tasks.add_task(_run)
    return {"job": _jobs[job_id], "job_id": job_id}


@v20.post("/cases/{case_id}/ingest/{job_id}/admit")
async def admit_evidence(case_id: str, job_id: str, payload: dict = {}) -> dict:
    """Apply the explicit professional decision at the evidence boundary.

    Extraction is fallible.  This endpoint is the only route that promotes an
    extracted claim to the admitted corpus.  It rebuilds the semantic Current,
    compiles the live runtime inputs and emits an executable event made only
    from the newly admitted extractor claims.  Candidate creation remains a
    separate explicit action at ``/events/{event_id}/admit``.
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
        _store_job(job_id, admission_status="REJECTED", stage="Evidence rejected")
        return {"status": "REJECTED", "proposal_id": proposal.get("proposal_id")}

    # Optional corrected claims are supplied by a review UI/API client.  The
    # default is to admit the extractor proposal unchanged.
    reviewed_claims = payload.get("claims") if isinstance(payload.get("claims"), list) else proposal.get("claims", [])
    reviewed_claims = [dict(c) for c in reviewed_claims if isinstance(c, dict)]
    _ensure_question_registry(case_id)
    existing_path = PIPELINE_OUT / "claims.json"
    existing = json.loads(existing_path.read_text()) if existing_path.exists() else []
    merged, added = _merge_claim_corpus(existing, reviewed_claims)
    if added and (PIPELINE_OUT / "candidate_state.json").exists():
        raise HTTPException(
            409,
            "An unsettled Candidate already exists; settle it before admitting more evidence.",
        )

    compiled = None
    runtime_event = None
    event_path = None
    prior_graph = _runtime_current_graph(case_id)
    if added:
        try:
            compiled = _compile_live_runtime_bundle(merged, case_id)
            added_ids = {
                str(claim.get("claim_id") or claim.get("id") or claim.get("stable_id"))
                for claim in added
            }
            baseline_graph = prior_graph or _without_claims(
                compiled["current_graph"], added_ids
            )
            runtime_event = _build_admitted_runtime_event(
                case_id,
                job_id,
                proposal,
                added,
                compiled["current_graph"],
                baseline_graph,
            )
            if not prior_graph:
                (PIPELINE_OUT / "runtime_state.json").unlink(missing_ok=True)
            event_path = _promote_live_runtime_bundle(
                compiled,
                baseline_graph,
                runtime_event,
            )
        except (DynamicsBundleError, ValueError, KeyError, OSError) as exc:
            logger.exception("runtime compilation failed for evidence job %s", job_id)
            raise HTTPException(422, f"Admitted evidence could not be compiled: {exc}") from exc

    _write_json_atomic(existing_path, merged)
    persisted = _persist_claims_to_vault(case_id, added, proposal.get("source_id", ""))
    graph = _build_semantic_current(merged, case_id)
    proposal.update({"status": "ADMITTED", "reviewed_at": _now_iso(),
                     "reviewed_by": payload.get("actor_id", "professional-review"),
                     "review_note": payload.get("note", ""),
                     "admitted_claim_count": len(added),
                     "runtime_event_id": runtime_event.get("event_id") if runtime_event else None,
                     "runtime_event_path": str(event_path) if event_path else None})
    _write_json_atomic(proposal_file, proposal)
    _update_inbox_record(job_id, admission_status="ADMITTED", stage="Runtime event ready",
                         admitted_claim_count=len(added),
                         runtime_event_id=runtime_event.get("event_id") if runtime_event else None,
                         message=(
                             f"Admitted {len(added)} new claims and compiled the executable runtime event."
                             if runtime_event else "Evidence was already represented; no new runtime event was required."
                         ))
    _store_job(job_id, admission_status="ADMITTED", stage="Runtime event ready",
               admitted_claim_count=len(added),
               runtime_event_id=runtime_event.get("event_id") if runtime_event else None)
    events_dir = VAULT / "deals" / case_id / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    event_id = f"EVIDENCE-ADMITTED-{job_id}"
    event_fm = {"type": "evidence_admitted", "id": event_id, "case": case_id,
                "source": proposal.get("source_id"), "proposal_id": proposal.get("proposal_id"),
                "claim_count": len(added), "known_at": _now_iso(), "effective_date": _today(),
                "label": f"Admitted evidence: {proposal.get('source_id', 'source')}",
                "detail": f"{len(added)} new claims admitted after professional review.",
                "runtime_event_id": runtime_event.get("event_id") if runtime_event else None,
                "runtime_event_path": str(event_path) if event_path else None,
                "actor": payload.get("actor_id", "professional-review")}
    (events_dir / f"e-{case_id}-evidence-admitted-{job_id}.md").write_text(
        "---\n" + yaml.safe_dump(event_fm, sort_keys=False, allow_unicode=True) + "---\n\n"
        "Admitted evidence event compiled for dynamics. Candidate has not yet been created.\n",
        encoding="utf-8",
    )
    _rebuild_index()
    return {"status": "ADMITTED", "proposal_id": proposal.get("proposal_id"), "event_id": event_id,
            "new_claim_count": len(added), "persisted_claim_count": persisted,
            "semantic_graph": {"nodes": len(graph.get("nodes", [])), "edges": len(graph.get("edges", []))},
            "runtime_event": ({
                "event_id": runtime_event["event_id"],
                "path": str(event_path),
                "mutation_count": len(runtime_event["mutations"]),
                "mapped_claim_count": len(runtime_event["mapped_claim_ids"]),
                "unmapped_claim_count": len(runtime_event["unmapped_claim_ids"]),
            } if runtime_event else None),
            "message": "Evidence admitted into semantic Current and compiled for dynamics."}


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
    prior_state_id = transition_output.get("prior_state_id", "STATE-PRIOR")
    event_record = event_batch[0] if event_batch else {}
    current_graph = _load_json_safe(PIPELINE_OUT / "current_graph.json")
    try:
        current_graph_version = _archive_graph_version(
            case_id,
            prior_state_id,
            "CURRENT",
            current_graph,
            run_id=run_id,
            event_id=event_id,
            effective_date=event_record.get("effective_date"),
            known_at=event_record.get("known_at"),
        )
        candidate_graph_version = _archive_graph_version(
            case_id,
            cand_state_id,
            "CANDIDATE",
            candidate_graph,
            run_id=run_id,
            event_id=event_id,
            prior_state_id=prior_state_id,
            effective_date=event_record.get("effective_date"),
            known_at=event_record.get("known_at"),
        )
    except DynamicsBundleError as exc:
        raise HTTPException(500, f"Dynamics graph versioning failed: {exc}") from exc

    # Store run so /runs/{run_id}/settle can find it
    _store_run(run_id, {
        "case_id": case_id,
        "event_id": event_id,
        "candidate_graph": candidate_graph,
        "candidate_state": candidate_state,
        "history_append": dynamics_result.get("history_append", []),
        "transition_output": transition_output,
        "candidate_state_id": cand_state_id,
        "current_graph_version": current_graph_version,
        "candidate_graph_version": candidate_graph_version,
        "bundle_dir": str(PIPELINE_OUT),
        "authority_records": [],
        "status": "CANDIDATE_READY",
        "created_at": _now_iso(),
    })

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
        "prior_state_id": prior_state_id,
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
        "candidate_graph": candidate_graph,
        "current_graph_version": current_graph_version,
        "candidate_graph_version": candidate_graph_version,
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
    selected_change_ids = payload.get("selected_change_ids")
    if selected_change_ids is None:
        selected_change_ids = run.get("selected_change_ids", [])
    if not isinstance(selected_change_ids, list):
        raise HTTPException(400, "selected_change_ids must be an array")
    selected_change_ids = [str(change_id) for change_id in selected_change_ids]

    supplied_record_ids = set(payload.get("authority_record_ids", []))
    recorded = {
        item["authority_record_id"]: item
        for item in run.get("authority_records", [])
    }
    human_stops = run["transition_output"].get("human_stops", [])
    if human_stops:
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

    scoped_records = [recorded[record_id] for record_id in supplied_record_ids if record_id in recorded]
    package_ids = [str(item) for item in payload.get("execution_package_ids", [])]
    _validate_execution_package_scope(run, scoped_records, package_ids)

    settled_at = dt.datetime.now(dt.timezone.utc)
    ts = settled_at.strftime("%Y%m%dT%H%M%S%fZ")
    settled_known_at = settled_at.isoformat().replace("+00:00", "Z")
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
    try:
        settled_graph_version = _archive_graph_version(
            case_id,
            new_state_id,
            "CURRENT",
            settled_state["current_graph"],
            run_id=run_id,
            event_id=event_id,
            prior_state_id=run["transition_output"].get("prior_state_id"),
            effective_date=payload.get("effective_date", today),
            known_at=settled_known_at,
        )
    except DynamicsBundleError as exc:
        raise HTTPException(500, f"Settled graph versioning failed: {exc}") from exc
    run["settled_state_id"] = new_state_id
    run["settled_graph_version"] = settled_graph_version
    run["status"] = "SETTLED"
    run["selected_change_ids"] = list(selected_change_ids)
    _store_run(run_id, run)

    # Append the institutional settlement event only after runtime persistence
    # succeeds, so the audit trail can never claim a failed promotion occurred.
    events_dir = VAULT / "deals" / case_id / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    settle_file = events_dir / f"e-{case_id}-settle-{ts}.md"
    settlement_fm = {
        "id": f"e-{case_id}-settle-{ts}",
        "type": "settlement",
        "settles": event_id,
        "run_id": run_id,
        "candidate_state_id": run["candidate_state_id"],
        "current_state_id": new_state_id,
        "selected-change-ids": list(selected_change_ids),
        "replay_hash": run["transition_output"].get("replay_hash", "sha256:settled"),
        "decision": decision,
        "actor": actor,
        "timestamp": settled_known_at,
        "written-by": "v20-api",
    }
    settle_file.write_text(
        "---\n" + yaml.safe_dump(settlement_fm, sort_keys=False, allow_unicode=True)
        + "---\n",
        encoding="utf-8",
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
        "selected_change_ids": list(selected_change_ids),
        "partial": run["transition_output"].get("partial_settlement_status", {}).get(
            "candidate"
        ) == "PARTIAL",
        "summary": f"Settled {event_id} → new Current {new_state_id}",
        "replay_hash": run["transition_output"].get("replay_hash", "sha256:settled"),
        "timestamp": settled_known_at,
        "effective_date": payload.get("effective_date", today),
        "known_at": settled_known_at,
        "as_of_state_id": new_state_id,
        "as_of_date": today,
        "projection": {"projection": updated_projection, "context": _make_context(case_id, new_state_id, today), "registry": []},
        "context": _make_context(case_id, new_state_id, today),
        "registry": [],
        "runtime_state_id": settled_state["state_id"],
        "graph_version": settled_graph_version,
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
    _store_run(run_id, {
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
        "status": "CANDIDATE_READY",
        "created_at": _now_iso(),
    })
    return await settle_run(run_id, background_tasks, payload)


@v20.post("/runs/{run_id}/prepare")
async def prepare_run(run_id: str, payload: dict = {}) -> dict:
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, f"Run not found: {run_id}")
    selected_change_ids = payload.get("selected_change_ids", [])
    if not isinstance(selected_change_ids, list):
        raise HTTPException(400, "selected_change_ids must be an array")
    selected_change_ids = [str(change_id) for change_id in selected_change_ids]
    run["selected_change_ids"] = selected_change_ids
    run["status"] = "PREPARED"
    _store_run(run_id, run)

    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    case_id = run["case_id"]
    event_record_id = f"e-{case_id}-run-prepared-{ts}-{uuid.uuid4().hex[:8]}"
    events_dir = VAULT / "deals" / case_id / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    event_fm = {
        "id": event_record_id,
        "type": "run_prepared",
        "run_id": run_id,
        "candidate_state_id": run["candidate_state_id"],
        "selected-change-ids": selected_change_ids,
        "replay_hash": run["transition_output"].get("replay_hash", "sha256:live"),
        "actor": payload.get("actor_id", "preparer-001"),
        "timestamp": ts,
        "written-by": "v20-api",
    }
    (events_dir / f"{event_record_id}.md").write_text(
        "---\n" + yaml.safe_dump(event_fm, sort_keys=False, allow_unicode=True)
        + "---\n",
        encoding="utf-8",
    )
    return {
        "run_id": run_id,
        "status": "PREPARED",
        "selected_change_ids": selected_change_ids,
    }


@v20.post("/runs/{run_id}/authority/attest")
async def attest(run_id: str, payload: dict = {}) -> dict:
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, f"Run not found: {run_id}")
    if run.get("status") != "PREPARED":
        raise HTTPException(409, "Run must be PREPARED before authority attestation")
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
    if payload.get("candidate_state_id") != run.get("candidate_state_id"):
        raise HTTPException(409, "Authority request Candidate does not match the run")
    course_id = str(payload.get("course_id") or "")
    if not course_id:
        raise HTTPException(400, "course_id is required")
    if not payload.get("artifact_hash"):
        raise HTTPException(400, "artifact_hash is required")
    course, _ = _execution_course(run["case_id"], course_id)
    effect_type = str(course.get("effect_type") or "INTERNAL")
    if effect_type not in {"EXTERNAL_PACKAGE", "INTERNAL", "DEFER"}:
        raise HTTPException(409, f"Unsupported course effect_type: {effect_type}")
    record_key = "|".join(
        (
            run_id,
            human_stop_id,
            str(payload.get("actor_id", "partner-001")),
            course_id,
        )
    )
    record_id = "AUTH-" + hashlib.sha256(record_key.encode("utf-8")).hexdigest()[:12].upper()
    existing = next(
        (item for item in run.get("authority_records", []) if item.get("authority_record_id") == record_id),
        None,
    )
    if existing:
        package = None
        if existing.get("effect_type") == "EXTERNAL_PACKAGE":
            package = _build_execution_package(run_id, existing)
        return {"authority_record": existing, "execution_package": package, "registry": []}
    authority_record = {
        "authority_record_id": record_id,
        "run_id": run_id,
        "candidate_state_id": run["candidate_state_id"],
        "human_stop_id": human_stop_id,
        "course_id": course_id,
        "actor_id": payload.get("actor_id", "partner-001"),
        "actor_role": payload.get("actor_role", "DEAL_PARTNER"),
        "timestamp": ts,
        "effective_date": today,
        "known_at": ts,
        "artifact_hash": payload["artifact_hash"],
        "authority_verb": "APPROVE",
        "effect_type": effect_type,
        "status": "ATTESTED",
        "synthetic": False,
    }
    run.setdefault("authority_records", []).append(authority_record)
    _store_run(run_id, run)
    execution_package = None
    if effect_type == "EXTERNAL_PACKAGE":
        execution_package = _build_execution_package(run_id, authority_record)
    return {
        "authority_record": authority_record,
        "execution_package": execution_package,
        "registry": [],
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
async def add_note(case_id: str, payload: dict) -> dict:
    """Persist a review or annotation as an immutable, append-only vault note."""
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "note text is required")

    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if idempotency_key:
        identity = hashlib.sha256(f"{case_id}|{idempotency_key}".encode("utf-8")).hexdigest()[:16]
    else:
        identity = uuid.uuid4().hex[:16]
    note_id = f"NOTE-{identity.upper()}"
    notes_dir = _notes_dir(case_id)
    note_path = notes_dir / f"note-{identity}.md"

    with _notes_lock:
        if note_path.exists():
            return {
                "status": "PERSISTED",
                "note": _note_record(note_path),
                "idempotent_replay": True,
            }

        acknowledged_at = _now_iso()
        known_at = str(payload.get("known_at") or payload.get("timestamp") or acknowledged_at)
        effective_date = str(payload.get("effective_date") or known_at[:10] or _today())
        metadata = {
            "type": "note",
            "id": note_id,
            "case": case_id,
            "kind": payload.get("kind", "ANNOTATION"),
            "object_id": payload.get("object_id"),
            "claim_id": payload.get("claim_id"),
            "decision": payload.get("decision"),
            "action": payload.get("action"),
            "correction": payload.get("correction"),
            "actor_id": payload.get("actor_id", "unknown-actor"),
            "effective_date": effective_date,
            "known_at": known_at,
            "idempotency_key": idempotency_key or None,
            "written-by": "v20-api",
            "written_at": acknowledged_at,
        }
        notes_dir.mkdir(parents=True, exist_ok=True)
        note_path.write_text(
            "---\n"
            + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
            + "---\n\n"
            + text
            + "\n",
            encoding="utf-8",
        )
    return {
        "status": "PERSISTED",
        "note": {**metadata, "text": text, "server_ack_at": acknowledged_at},
        "idempotent_replay": False,
    }


@v20.get("/cases/{case_id}/notes")
def list_notes(case_id: str) -> dict:
    """Return the durable case notes in deterministic chronological order."""
    notes_dir = _notes_dir(case_id)
    if not notes_dir.exists():
        return {"notes": []}
    notes = [_note_record(path) for path in sorted(notes_dir.glob("note-*.md"))]
    notes.sort(key=lambda note: (str(note.get("known_at", "")), str(note.get("id", ""))))
    return {"notes": notes}


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
    """Search the derived vault index using the V20 command-palette contract."""
    if not INDEX_DB.exists():
        return {"results": []}

    term = q.strip()
    pattern = f"%{term}%"
    try:
        with sqlite3.connect(str(INDEX_DB)) as con:
            rows = con.execute(
                """
                SELECT id, type, title, subject, value, frontmatter
                FROM nodes
                WHERE LOWER(COALESCE(deal, '')) = LOWER(?)
                  AND LOWER(COALESCE(type, '')) IN ('claim', 'question', 'artifact')
                  AND (
                    ? = ''
                    OR COALESCE(id, '') LIKE ? COLLATE NOCASE
                    OR COALESCE(title, '') LIKE ? COLLATE NOCASE
                    OR COALESCE(subject, '') LIKE ? COLLATE NOCASE
                    OR COALESCE(value, '') LIKE ? COLLATE NOCASE
                    OR COALESCE(frontmatter, '') LIKE ? COLLATE NOCASE
                  )
                ORDER BY
                  CASE LOWER(type) WHEN 'claim' THEN 0 WHEN 'question' THEN 1 ELSE 2 END,
                  LOWER(COALESCE(title, subject, id)),
                  id
                LIMIT 50
                """,
                (case_id, term, pattern, pattern, pattern, pattern, pattern),
            ).fetchall()

        results = []
        for node_id, node_type, title, subject, value, raw_frontmatter in rows:
            try:
                frontmatter = json.loads(raw_frontmatter or "{}")
            except (TypeError, json.JSONDecodeError):
                frontmatter = {}
            normalized_type = str(node_type or "").upper()
            if normalized_type == "CLAIM":
                label = subject or frontmatter.get("statement") or title or node_id
                route = "deal-command"
            elif normalized_type == "QUESTION":
                label = frontmatter.get("question") or frontmatter.get("title") or title or node_id
                route = "deal-command"
            else:
                label = frontmatter.get("title") or title or node_id
                route = "artifacts"
            search_text = " ".join(
                str(item)
                for item in (
                    node_id,
                    title,
                    subject,
                    value,
                    frontmatter.get("statement"),
                    frontmatter.get("question"),
                    frontmatter.get("bearing"),
                    frontmatter.get("kind"),
                )
                if item not in (None, "")
            )
            results.append(
                {
                    "id": node_id,
                    "type": normalized_type,
                    "label": str(label),
                    "route": route,
                    "search_text": search_text,
                }
            )
        return {"results": results}
    except Exception as exc:
        return {"results": [], "error": str(exc)}

@v20.get("/cases/{case_id}/search")
def search_case(case_id: str, q: str = "") -> dict:
    return search(q=q, case_id=case_id)
