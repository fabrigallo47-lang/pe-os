"""V20 API router — the contract the V20 frontend speaks.

All endpoints under /api/v20. Shapes derived from reading:
  ui/01_PRODUCT_BUILD/app/src/api.js      — what URLs the frontend calls
  ui/01_PRODUCT_BUILD/app/src/contracts.js — what shapes are validated
  ui/01_PRODUCT_BUILD/app/src/store.js    — how state is initialised
  ui/01_PRODUCT_BUILD/app/src/engine.js   — how boot/applyProjection work
"""
from __future__ import annotations

import datetime as dt
import asyncio
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
from tools.source_envelope import build_source_envelope

ROOT = Path(__file__).resolve().parent.parent
INDEX_DB = Path(os.environ["PEOS_DB"]) if os.environ.get("PEOS_DB") else ROOT / ".index" / "vault.db"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "ui" / "07_ENGINEERING_CONTRACTS_AND_ADAPTERS" / "adapters"))

VAULT = ROOT / "vault"
PIPELINE_OUT = ROOT / "pipeline_out" / "e3" / "K-IC" / "adapter_alpha"
CASE_PIPELINE_ROOT = ROOT / "pipeline_out" / "cases"
INGEST_JOBS_LOG = ROOT / "logs" / "ingest_jobs.json"
INGEST_BATCHES_LOG = ROOT / "logs" / "ingest_batches.json"
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
    "bulkIngest": {"status": "AVAILABLE", "method": "POST", "path": "/cases/{case_id}/ingest/batches"},
    "getIngestBatch": {"status": "AVAILABLE", "method": "GET", "path": "/cases/{case_id}/ingest/batches/{batch_id}"},
    "retryBatchJob": {"status": "AVAILABLE", "method": "POST", "path": "/cases/{case_id}/ingest/batches/{batch_id}/jobs/{job_id}/retry"},
    "getJob": {"status": "AVAILABLE", "method": "GET", "path": "/jobs/{job_id}"},
    "getEvidenceProposal": {"status": "AVAILABLE", "method": "GET", "path": "/cases/{case_id}/ingest/{job_id}/proposal"},
    "admitEvidence": {"status": "AVAILABLE", "method": "POST", "path": "/cases/{case_id}/ingest/{job_id}/admit"},
    "admitAllPending": {"status": "AVAILABLE", "method": "POST", "path": "/cases/{case_id}/admit-all"},
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
    "loadReunderwrite": {"status": "AVAILABLE", "method": "GET", "path": "/cases/{case_id}/re-underwrite"},
    "getFundLens": {"status": "AVAILABLE", "method": "GET", "path": "/cases/{case_id}/fund-lens"},
    "configureFundLens": {"status": "AVAILABLE", "method": "PUT", "path": "/cases/{case_id}/fund-lens"},
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
_batches: dict[str, dict] = {}
_runs: dict[str, dict] = {}   # run_id → {transition, candidate_graph, case_id}
_inbox_lock = threading.Lock()
_notes_lock = threading.Lock()
_source_lock = threading.Lock()
_work_drafts_lock = threading.Lock()
_compiler_reviews_lock = threading.Lock()
_ic_records_lock = threading.Lock()
_mission_drafts_lock = threading.Lock()
_registry_lock = threading.RLock()
_batch_lock = threading.RLock()
_graph_versions_lock = threading.Lock()
_fund_lens_lock = threading.Lock()

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


def _pipeline_out_for_case(case_id: str) -> Path:
    """Return the isolated runtime bundle for one case.

    Keystone keeps its historical path so existing fixtures and deployments do
    not move underneath callers. Every other case gets a dedicated bundle.
    """
    if not re.fullmatch(r"[A-Za-z0-9._-]+", case_id):
        raise HTTPException(400, "case_id contains unsupported characters")
    return PIPELINE_OUT if case_id == "keystone" else CASE_PIPELINE_ROOT / case_id


def _available_case_ids() -> list[str]:
    """Discover every durable case the connected UI can open."""
    deals_dir = VAULT / "deals"
    if not deals_dir.exists():
        return []
    return sorted(
        path.name
        for path in deals_dir.iterdir()
        if path.is_dir() and re.fullmatch(r"[A-Za-z0-9._-]+", path.name)
    )


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


def _default_decision_room(case_id: str) -> dict[str, Any]:
    """Return the conservative Connected-mode course exposed by the live API."""

    return {
        "request_id": f"AR-{case_id.upper()}-CURRENT-ADOPTION",
        "verb": "ADOPT_CURRENT",
        "title": "Review and adopt the settled Candidate scope",
        "deadline": None,
        "holder": "Assigned professional reviewer",
        "rule": "Only the explicitly prepared, authority-attested scope may enter Current.",
        "evidence_for": [],
        "evidence_against": [],
        "courses": [
            {
                "id": "ADOPT-CANDIDATE",
                "label": "Adopt prepared Candidate scope",
                "economics": "Promotes only the selected settled components.",
                "conditions": [
                    "Candidate and Current hashes still match",
                    "Every Human Stop has a scoped authority record",
                ],
                "policy": "WITHIN DECLARED AUTHORITY",
                "recommended": False,
                "effect_type": "INTERNAL",
                "execution": None,
            }
        ],
    }


def _default_execution_room() -> dict[str, Any]:
    return {
        "type": "Internal Current-state adoption",
        "recipient": None,
        "sender": None,
        "subject": None,
        "message": None,
        "attachments": [],
        "checks": [
            "Prepared selection hash matched",
            "Candidate compare-and-swap matched",
            "Authority records remained Candidate-scoped",
        ],
        "externality": "No external effect is created by the default course.",
    }


def _authority_actor(case_id: str, actor_id: str) -> dict[str, Any] | None:
    """Resolve authority from server-owned assignments, never from payload roles."""

    projection = _build_projection(case_id)
    actors = projection.get("actor_directory", [])
    actor = next(
        (
            dict(item)
            for item in actors
            if isinstance(item, dict)
            and str(item.get("actor_id") or item.get("participant_id") or item.get("id"))
            == actor_id
        ),
        None,
    )
    if actor is not None:
        return actor
    default_actor = _make_context(case_id, _current_state_id(case_id), _today()).get(
        "authenticated_actor", {}
    )
    if str(default_actor.get("actor_id") or "") == actor_id:
        return dict(default_actor)
    return None


def _actor_satisfies_role(actor: dict[str, Any], required_role: str) -> bool:
    granted = {
        str(actor.get("role") or ""),
        *(str(item) for item in actor.get("authority_roles", [])),
    }
    return required_role in granted


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
        id_field = {"jobs": "job_id", "batches": "batch_id"}.get(field, "run_id")
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


def _store_batch(batch_id: str, record: dict[str, Any] | None = None, **changes: Any) -> dict:
    """Persist one batch without embedding mutable copies of its jobs."""
    with _batch_lock:
        if record is not None:
            _batches[batch_id] = dict(record)
        batch = _batches.setdefault(batch_id, {"batch_id": batch_id})
        batch.update(changes)
        batch.setdefault("batch_id", batch_id)
        batch["updated_at"] = _now_iso()
        _write_registry(INGEST_BATCHES_LOG, "batches", _batches)
        return batch


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
        _batches.clear()
        _batches.update(_read_registry(INGEST_BATCHES_LOG, "batches"))
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

def _active_fund_lens(case_id: str) -> dict:
    """Return the case override or the repository's versioned buyout Fund Lens."""
    from bind_questions_e3 import DEFAULT_FUND_LENS_PATH, load_fund_lens

    override = VAULT / "deals" / case_id / "fund_lens.json"
    return load_fund_lens(override if override.exists() else DEFAULT_FUND_LENS_PATH)


def _fund_lens_archive_path(case_id: str, lens: dict) -> Path:
    lens_id = str(lens["lens_id"])
    version = str(lens["version"])
    return _case_vault_dir(case_id) / "fund_lenses" / f"{lens_id}__{version}.json"


def _fund_lens_hash(lens: dict) -> str:
    encoded = json.dumps(
        lens, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _fund_lens_versions(case_id: str) -> list[dict]:
    versions_dir = _case_vault_dir(case_id) / "fund_lenses"
    versions: list[dict] = []
    if not versions_dir.exists():
        return versions
    from bind_questions_e3 import validate_fund_lens

    for path in sorted(versions_dir.glob("*.json")):
        try:
            lens = validate_fund_lens(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Ignoring invalid Fund Lens archive %s: %s", path, exc)
            continue
        versions.append({
            "lens_id": lens["lens_id"],
            "version": lens["version"],
            "label": lens["label"],
            "effective_date": lens["effective_date"],
            "artifact_hash": _fund_lens_hash(lens),
        })
    versions.sort(key=lambda item: (item["effective_date"], item["lens_id"], item["version"]))
    return versions


def _configure_fund_lens(case_id: str, payload: dict) -> dict:
    """Persist one manual Lens without permitting version mutation."""
    from bind_questions_e3 import validate_fund_lens

    _case_vault_dir(case_id)
    try:
        lens = validate_fund_lens(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    q_dir = _case_vault_dir(case_id) / "questions"
    for question in lens["questions"]:
        path = q_dir / f"{str(question['id']).lower()}.md"
        if not path.exists():
            continue
        existing = _read_frontmatter(path)
        if existing.get("origin") == "deal_emergent":
            raise HTTPException(
                409,
                f"Fund Lens question {question['id']} conflicts with a deal-emergent question",
            )

    active_path = _case_vault_dir(case_id) / "fund_lens.json"
    archive_path = _fund_lens_archive_path(case_id, lens)
    with _fund_lens_lock:
        archived = _load_json_safe(archive_path)
        if archived and _fund_lens_hash(archived) != _fund_lens_hash(lens):
            raise HTTPException(
                409,
                f"Fund Lens {lens['lens_id']} version {lens['version']} is immutable",
            )
        previous = _load_json_safe(active_path)
        idempotent = bool(previous) and _fund_lens_hash(previous) == _fund_lens_hash(lens)
        if not archived:
            _write_json_atomic(archive_path, lens)
        if not idempotent:
            _write_json_atomic(active_path, lens)
        _ensure_question_registry(case_id, lens)
    return {
        "case_id": case_id,
        "active": lens,
        "artifact_hash": _fund_lens_hash(lens),
        "idempotent_replay": idempotent,
        "versions": _fund_lens_versions(case_id),
    }


def _ensure_question_registry(case_id: str, fund_lens: dict | None = None) -> None:
    """Materialize versioned Fund Lens questions, never claim-derived facts."""
    lens = fund_lens or _active_fund_lens(case_id)
    q_dir = VAULT / "deals" / case_id / "questions"
    q_dir.mkdir(parents=True, exist_ok=True)
    for question in lens["questions"]:
        qid = str(question["id"])
        title = str(question["title"])
        path = q_dir / f"{qid.lower()}.md"
        existing = _read_frontmatter(path) if path.exists() else {}
        if existing.get("origin") == "deal_emergent":
            raise HTTPException(409, f"Fund Lens question {qid} conflicts with a deal-emergent question")
        fm = {
            **existing,
            "type": "question", "id": qid, "deal": case_id,
            "title": title, "question": title,
            "state": existing.get("state", "open"),
            "status": existing.get("status", "open"),
            "critical": existing.get("critical", False),
            "workstream": question.get("workstream", "underwriting"),
            "opened": existing.get("opened", _today()),
            "written-by": "fund-lens-registry",
            "origin": "fund_lens", "question_version": question.get("version", 1),
            "fund_lens_id": lens["lens_id"], "fund_lens_version": lens["version"],
        }
        _write_text_atomic(
            path,
            "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n# " + title + "\n",
        )


def _proposal_path(job_id: str, case_id: str = "keystone") -> Path:
    return _pipeline_out_for_case(case_id) / "proposals" / f"evidence-{job_id}.json"


def _excel_model_graphs_path(case_id: str) -> Path:
    return _pipeline_out_for_case(case_id) / "excel_model_graphs.json"


def _load_excel_model_graphs(case_id: str) -> list[dict]:
    payload = _load_json_safe(_excel_model_graphs_path(case_id))
    graphs = payload.get("graphs", []) if isinstance(payload, dict) else []
    return [dict(item) for item in graphs if isinstance(item, dict)]


def _admit_excel_formula_graph(case_id: str, proposal: dict, actor_id: str) -> dict | None:
    """Persist one reviewed workbook graph without recalculating any formula."""
    incoming = proposal.get("excel_formula_graph")
    if not isinstance(incoming, dict) or not isinstance(incoming.get("nodes"), list):
        return None
    source = incoming.get("source", {})
    digest = str(source.get("digest") or "").strip()
    if not digest:
        raise DynamicsBundleError("Excel formula graph is missing its source digest")
    admitted = {
        **copy.deepcopy(incoming),
        "admission": {
            "status": "ADMITTED",
            "proposal_id": proposal.get("proposal_id"),
            "reviewed_by": actor_id,
            "reviewed_at": _now_iso(),
        },
    }
    existing = _load_excel_model_graphs(case_id)
    def source_identity(item: dict) -> tuple[str, str]:
        item_source = item.get("source", {})
        return (
            str(item_source.get("source_id") or item_source.get("workbook") or ""),
            str(item_source.get("digest") or ""),
        )

    by_identity = {source_identity(item): item for item in existing}
    by_identity[source_identity(admitted)] = admitted
    graphs = sorted(
        by_identity.values(),
        key=lambda item: (
            str(item.get("source", {}).get("workbook", "")),
            str(item.get("source", {}).get("digest", "")),
        ),
    )
    _write_json_atomic(
        _excel_model_graphs_path(case_id),
        {"schema_version": "excel-model-graph-registry/1.0", "graphs": graphs},
    )
    return admitted


def _write_evidence_proposal(
    job_id: str,
    case_id: str,
    filename: str,
    claims: list[dict],
    question_proposals: list[dict] | None = None,
    fund_lens: dict | None = None,
    excel_formula_graph: dict | None = None,
    workbook_formula_graphs: dict | None = None,
    source_envelope: dict | None = None,
) -> Path:
    """Store extraction output as reviewable evidence, before it can affect Current."""
    # Backwards-compatible positional callers supplied workbook sidecars as
    # the first formula argument before PAN-51 added excel_formula_graph.
    if (isinstance(excel_formula_graph, dict)
            and str(excel_formula_graph.get("schema", "")).startswith("workbook-formula-graphs")):
        workbook_formula_graphs = excel_formula_graph
        excel_formula_graph = None
    path = _proposal_path(job_id, case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    formula_graphs = workbook_formula_graphs or {"schema": "workbook-formula-graphs-1.0", "workbooks": []}
    artifact_path = path.with_name(f"{path.stem}-workbook-formula-graphs.json")
    if formula_graphs.get("workbooks"):
        _write_json_atomic(artifact_path, formula_graphs)
    summaries = [
        {
            "source_id": item.get("source_id"),
            "source_filename": item.get("source_filename"),
            **(item.get("summary") or {}),
        }
        for item in formula_graphs.get("workbooks", [])
        if isinstance(item, dict)
    ]
    payload = {
        "proposal_id": f"evidence-{job_id}", "job_id": job_id, "case_id": case_id,
        "source_id": (source_envelope or {}).get("source_id") or filename,
        "source_path": f"vault/inbox/{filename}",
        "source_envelope": source_envelope,
        "status": "PENDING_REVIEW", "created_at": _now_iso(), "claims": claims,
        "question_proposals": question_proposals or [],
        "excel_formula_graph": excel_formula_graph,
        "workbook_formula_graph": {
            "available": bool(summaries),
            "artifact": artifact_path.name if summaries else None,
            "workbooks": summaries,
        },
        "fund_lens": {
            "lens_id": (fund_lens or {}).get("lens_id"),
            "version": (fund_lens or {}).get("version"),
            "binding_profile": (fund_lens or {}).get("binding_profile"),
        },
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _proposal_workbook_formula_graphs(proposal_file: Path, proposal: dict) -> dict:
    """Load the immutable formula graph stored beside an evidence proposal."""
    artifact = (proposal.get("workbook_formula_graph") or {}).get("artifact")
    if not artifact:
        return {"schema": "workbook-formula-graphs-1.0", "workbooks": []}
    candidate = proposal_file.parent / Path(str(artifact)).name
    payload = _load_json_safe(candidate)
    if not isinstance(payload.get("workbooks"), list):
        return {"schema": "workbook-formula-graphs-1.0", "workbooks": []}
    return payload


def _promote_workbook_formula_graphs(case_id: str, proposal_file: Path, proposal: dict) -> dict:
    """Persist admitted workbook structure separately from LLM claim output."""
    incoming = _proposal_workbook_formula_graphs(proposal_file, proposal)
    if not incoming["workbooks"]:
        return {"schema": "workbook-formula-graphs-1.0", "workbooks": []}
    destination = _pipeline_out_for_case(case_id) / "workbook_formula_graphs.json"
    existing = _load_json_safe(destination)
    retained = {
        str(item.get("source_id") or item.get("source_filename")): item
        for item in existing.get("workbooks", [])
        if isinstance(item, dict)
    }
    for item in incoming["workbooks"]:
        if isinstance(item, dict):
            retained[str(item.get("source_id") or item.get("source_filename"))] = item
    promoted = {"schema": "workbook-formula-graphs-1.0", "workbooks": list(retained.values())}
    _write_json_atomic(destination, promoted)
    return promoted

def _derive_bears_on(claims: list[dict], e3: dict, fund_lens: dict | None = None) -> list[dict]:
    """Apply the same deterministic metric/keyword graph used by bind_questions_e3."""
    from bind_questions_e3 import ranked_bindings
    metadata = {x.get("claim_id"): x for x in e3.get("extraction_metadata", {}).get("compiler_fields_per_claim", [])}
    out = []
    for claim in claims:
        c = dict(claim)
        meta = metadata.get(c.get("claim_id"), c)
        binding_evidence = ranked_bindings(
            c, meta, fund_lens or _active_fund_lens(str(e3.get("deal") or "keystone"))
        )
        c["bears_on"] = [item["question_id"] for item in binding_evidence]
        c["binding_evidence"] = binding_evidence
        if metadata.get(c.get("claim_id")):
            c.update({k: v for k, v in metadata[c["claim_id"]].items() if k not in c or not c.get(k)})
        out.append(c)
    return out


def _derive_question_proposals(claims: list[dict], case_id: str) -> list[dict]:
    """Turn unbound evidence into deterministic, review-only spine proposals."""
    groups: dict[str, list[dict]] = {}
    for claim in claims:
        if claim.get("bears_on"):
            continue
        topic = str(
            claim.get("topic")
            or claim.get("metric")
            or claim.get("subject")
            or "uncategorised evidence"
        ).strip()
        normalized = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-") or "evidence"
        groups.setdefault(normalized[:64], []).append(claim)

    proposals = []
    for topic_key, bearing in sorted(groups.items()):
        claim_ids = sorted(
            str(item.get("claim_id") or item.get("id")) for item in bearing
            if item.get("claim_id") or item.get("id")
        )
        seed = f"{case_id}|{topic_key}|{'|'.join(claim_ids)}"
        suffix = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10].upper()
        question_id = f"DQ-{suffix}"
        topic_label = str(
            bearing[0].get("topic")
            or bearing[0].get("metric")
            or bearing[0].get("subject")
            or "this evidence"
        ).strip()
        proposals.append({
            "proposal_id": f"SPINE-{suffix}",
            "id": f"SPINE-{suffix}",
            "proposal_type": "ADD_QUESTION",
            "label": f"Add deal-emergent question: {topic_label}",
            "reason": f"{len(claim_ids)} extracted claim(s) are not covered by the active Fund Lens.",
            "status": "PENDING_REVIEW",
            "effective_date": _today(),
            "known_at": _now_iso(),
            "required_authority_level": "DEAL_TEAM_REVIEW",
            "affected_artifact_ids": [],
            "proposed_question": {
                "id": question_id,
                "title": f"What must we establish about {topic_label}?",
                "workstream": "deal-emergent",
                "origin": "deal_emergent",
                "question_version": 1,
            },
            "binding_migration": {"claim_ids": claim_ids, "target_question_id": question_id},
            "case_id": case_id,
        })
    return proposals

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


def _claim_locator_covers_formula(
    claim: dict,
    formula_locator: str,
    workbook: str,
) -> bool:
    """True when an extracted cell/range locator contains a formula output."""
    locator = str(claim.get("locator") or claim.get("source_locator") or "")
    if not locator or "!" not in locator or "!" not in formula_locator:
        return False
    if "::" in locator:
        located_workbook, locator = locator.rsplit("::", 1)
        if workbook and Path(located_workbook).name.lower() != Path(workbook).name.lower():
            return False
    claim_sheet, claim_ref = locator.rsplit("!", 1)
    formula_sheet, formula_ref = formula_locator.rsplit("!", 1)
    if claim_sheet.strip("'").upper() != formula_sheet.strip("'").upper():
        return False
    match = re.fullmatch(r"\$?([A-Z]{1,3})\$?(\d+)", formula_ref.upper())
    if not match:
        return False
    formula_col, formula_row = match.group(1), int(match.group(2))
    if re.fullmatch(r"\d+:\d+", claim_ref):
        start, end = (int(value) for value in claim_ref.split(":", 1))
        return start <= formula_row <= end
    cell_match = re.fullmatch(r"\$?([A-Z]{1,3})\$?(\d+)", claim_ref.upper())
    if cell_match:
        return (formula_col, formula_row) == (cell_match.group(1), int(cell_match.group(2)))
    range_match = re.fullmatch(
        r"\$?([A-Z]{1,3})\$?(\d+):\$?([A-Z]{1,3})\$?(\d+)",
        claim_ref.upper(),
    )
    if not range_match:
        return False

    def column_number(column: str) -> int:
        value = 0
        for character in column:
            value = value * 26 + ord(character) - ord("A") + 1
        return value

    min_col, max_col = sorted((column_number(range_match.group(1)), column_number(range_match.group(3))))
    min_row, max_row = sorted((int(range_match.group(2)), int(range_match.group(4))))
    return min_col <= column_number(formula_col) <= max_col and min_row <= formula_row <= max_row


def _semantic_graph_from_claims(
    claims: list[dict],
    case_id: str,
    excel_models: list[dict] | None = None,
) -> dict:
    """Derive a semantic graph without mutating the operational Current."""
    from vercel.api._claim_graph import claims_to_graph, is_hygiene_noise

    # The V1/V2 extraction envelope carries ``metric``/``statement`` and
    # ``source_id``/``epistemic_class``; claims_to_graph's Pass 1 requires the
    # older ``subject``/``source_doc``/``epistemic`` names and silently drops
    # any claim with an empty subject. Without this, every claim from this
    # envelope disappears from the graph before a single edge is built —
    # matching normalization to _build_semantic_current's boundary.
    semantic_claims = []
    for claim in claims:
        current = dict(claim)
        current.setdefault("source_doc", current.get("source_id", ""))
        current.setdefault("epistemic", current.get("epistemic_class", "asserted"))
        current.setdefault("as_of", current.get("effective_date") or current.get("period", ""))
        current.setdefault("subject", current.get("metric") or current.get("statement", "")[:96])
        semantic_claims.append(current)
    # claims_to_graph applies its own hygiene filter internally (Pass 0) and
    # numbers claim:NNN nodes by position in the *filtered* list. Filter here
    # first, identically, so the index space used for the Source -> Claim
    # provenance edges below matches the node ids claims_to_graph creates.
    semantic_claims = [c for c in semantic_claims if not is_hygiene_noise(c)]

    graph = claims_to_graph(semantic_claims, deal=case_id)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_ids = {n.get("id") for n in nodes}
    # Make source provenance first-class in the test graph: Source → Claim.
    for index, claim in enumerate(semantic_claims):
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
    # A covered underwriting question forms a reviewable Case Position even
    # before an archetype supplies executable model mappings.  This makes the
    # semantic case visible in Foundations without treating it as runtime fact.
    question_nodes = {str(q.get("id")): q for q in _load_questions(case_id)}
    # Compiler-origin question nodes may use a different question-type ID from
    # the Fund Lens. They still form explicit case positions; evidence links
    # are added below where claim bindings are available.
    for node in list(nodes):
        if node.get("type") != "question" or not node.get("id"):
            continue
        qid = str(node["id"]).removeprefix("q:")
        position_id = f"position:{qid}"
        if position_id not in node_ids:
            nodes.append({"id": position_id, "type": "case_position", "label": node.get("label") or qid,
                          "statement": node.get("label") or qid, "question_id": qid,
                          "decision_status": node.get("decision_status", "PENDING"),
                          "epistemic_status": "EVIDENCE_FORMING"})
            node_ids.add(position_id)
            edges.append({"source": node["id"], "target": position_id, "rel": "FRAMES_POSITION"})
    for edge in list(edges):
        if edge.get("rel") not in {"BEARS_ON", "ANSWERS_TO"}:
            continue
        claim_id, qid = edge.get("source"), str(edge.get("target", "")).removeprefix("q:")
        question = question_nodes.get(qid)
        if not question or not claim_id:
            continue
        position_id = f"position:{qid}"
        if position_id not in node_ids:
            nodes.append({"id": position_id, "type": "case_position",
                          "label": question.get("title") or qid,
                          "statement": question.get("title") or qid,
                          "question_id": qid, "decision_status": "PENDING",
                          "epistemic_status": "EVIDENCE_FORMING"})
            node_ids.add(position_id)
            edges.append({"source": f"q:{qid}", "target": position_id, "rel": "FRAMES_POSITION"})
        claim = nodes[next((i for i,n in enumerate(nodes) if n.get("id") == claim_id), -1)] if claim_id in node_ids else {}
        direction = str(claim.get("direction", "")).lower()
        edges.append({"source": claim_id, "target": position_id,
                      "rel": "CONTRADICTS" if direction in {"against", "negative", "downside"} else "SUPPORTS"})
    # Workbook formulas are deterministic source evidence.  Keep the complete
    # cell/dependency graph in its sidecar (so a large model does not make the
    # interactive semantic canvas unusable) and project one inspectable model
    # node per admitted workbook into the main graph.
    formula_graphs = _load_json_safe(_pipeline_out_for_case(case_id) / "workbook_formula_graphs.json")
    formula_summaries = []
    for workbook in formula_graphs.get("workbooks", []):
        if not isinstance(workbook, dict):
            continue
        source_id = str(workbook.get("source_id") or workbook.get("source_filename") or "workbook")
        summary = workbook.get("summary") or {}
        model_node = f"workbook:{source_id}"
        if model_node not in node_ids:
            nodes.append({
                "id": model_node, "type": "workbook_formula_graph",
                "label": workbook.get("source_filename") or source_id,
                "formula_count": int(summary.get("formula_count", 0)),
                "precedent_edge_count": int(summary.get("precedent_edge_count", 0)),
                "cached_formula_value_count": int(summary.get("cached_formula_value_count", 0)),
                "coverage_status": "mapped",
            })
            node_ids.add(model_node)
        source_node = f"source:{source_id}"
        if source_node not in node_ids:
            nodes.append({"id": source_node, "type": "source", "label": source_id,
                          "title": source_id, "coverage_status": "mapped"})
            node_ids.add(source_node)
        edges.append({"source": source_node, "target": model_node, "rel": "CONTAINS_FORMULA_GRAPH"})
        formula_summaries.append({
            "source_id": source_id,
            "source_filename": workbook.get("source_filename"),
            **summary,
        })
    graph["nodes"] = nodes
    graph["edges"] = edges
    graph["workbook_formula_graphs"] = formula_summaries
    graph["kind"] = "semantic_current"
    graph["case_id"] = case_id
    model_graphs = _load_excel_model_graphs(case_id) if excel_models is None else excel_models
    formulas = []
    coverage_limits = []
    model_sources = []
    for model_graph in model_graphs:
        if not isinstance(model_graph, dict):
            continue
        source = model_graph.get("source", {})
        model_sources.append({
            **source,
            "admission": copy.deepcopy(model_graph.get("admission")),
        })
        for node in model_graph.get("nodes", []):
            if not isinstance(node, dict) or not node.get("id") or node.get("id") in node_ids:
                continue
            nodes.append(copy.deepcopy(node))
            node_ids.add(node["id"])
        for edge in model_graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            if edge.get("source") in node_ids and edge.get("target") in node_ids:
                edges.append(copy.deepcopy(edge))
        formulas.extend(copy.deepcopy(model_graph.get("formulas", [])))
        coverage_limits.extend(copy.deepcopy(model_graph.get("coverage_limits", [])))
        workbook = str(source.get("workbook") or source.get("source_id") or "")
        for claim_index, claim in enumerate(claims):
            claim_node_id = f"claim:{claim_index:03d}"
            if claim_node_id not in node_ids:
                continue
            for formula in model_graph.get("formulas", []):
                if not isinstance(formula, dict):
                    continue
                output_id = formula.get("output_model_node_id")
                locator = str(formula.get("locator") or "")
                if (
                    output_id in node_ids
                    and _claim_locator_covers_formula(claim, locator, workbook)
                ):
                    edges.append({
                        "source": claim_node_id,
                        "target": output_id,
                        "rel": "GROUNDED_IN_MODEL",
                        "formula_id": formula.get("formula_id"),
                        "locator": locator,
                    })
    graph["excel_model_sources"] = model_sources
    graph["excel_formulas"] = formulas
    graph["coverage_limits"] = coverage_limits
    return graph


def _build_semantic_current(claims: list[dict], case_id: str) -> dict:
    """Build and persist the pre-runtime Current semantic graph."""
    graph = _semantic_graph_from_claims(claims, case_id)
    pipeline_out = _pipeline_out_for_case(case_id)
    pipeline_out.mkdir(parents=True, exist_ok=True)
    (pipeline_out / "semantic_current_graph.json").write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n")
    return graph

def _semantic_rooms(graph: dict, question_spine: list[dict]) -> tuple[list[dict], dict, list[dict]]:
    """Project semantic positions and evidence gaps into Foundations and Unknowns.

    Foundations = Case Position nodes plus their SUPPORTS/CONTRADICTS evidence,
    plus CONDITION nodes -- declared coverage gaps a position's underlying
    question still rests on (REQUIRES_EVIDENCE edges from ``_build_semantic_current``).
    The Unknowns room returned here is a minimal fallback (question-spine gaps
    only); ``_apply_decision_intelligence`` is the authority that ranks it and
    folds in conflicts/runtime blockers, and always runs after this.
    """
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

    for edge in graph.get("edges", []):
        if edge.get("rel") != "REQUIRES_EVIDENCE":
            continue
        condition = nodes.get(edge.get("target"), {})
        if condition.get("type") != "condition":
            continue
        foundations.append({
            "id": condition["id"], "label": condition.get("label", condition["id"]),
            "economic": "", "strength": "weak", "status": "MISSING_EVIDENCE",
            "kind": "condition", "question_id": condition.get("question_id"),
            "evidence_options": [], "members": [],
        })

    unknowns = {"items": [
        {"id": f"unknown:{q['id']}", "label": q.get("label", q["id"]), "question_id": q["id"],
         "value": "No admitted evidence yet", "closure": "Admit source evidence or accept the residual risk."}
        for q in question_spine if q.get("coverage") == "gap"
    ]}
    return foundations, unknowns, positions


def _scenario_lab(current_graph: dict | None) -> dict:
    """Project mapped model nodes and support routes into the Scenario Lab room.

    A 'scenario' here is a support route: an alternative, governed way a Case
    Position's value is argued or computed from its member claims/positions,
    together with the model nodes bound to that position. Nothing is invented
    -- a position with no support route yet simply contributes no branch, and
    a case with no compiled runtime bundle gets an empty lab, not a fixture.
    """
    if not isinstance(current_graph, dict):
        return {"scenarios": []}
    model_nodes = {
        n.get("model_node_id"): n
        for n in current_graph.get("model_nodes", []) or []
        if isinstance(n, dict) and n.get("model_node_id")
    }
    positions = {
        p.get("position_id"): p
        for p in current_graph.get("case_positions", []) or []
        if isinstance(p, dict) and p.get("position_id")
    }
    bindings_by_position: dict[str, list[dict]] = {}
    for binding in current_graph.get("position_model_bindings", []) or []:
        if isinstance(binding, dict) and binding.get("position_id"):
            bindings_by_position.setdefault(str(binding["position_id"]), []).append(binding)

    scenarios = []
    for route in current_graph.get("support_routes", []) or []:
        if not isinstance(route, dict):
            continue
        target_id = route.get("target_position_id")
        position = positions.get(target_id, {})
        bound_model_nodes = [
            model_nodes[binding["model_node_id"]]
            for binding in bindings_by_position.get(str(target_id), [])
            if binding.get("model_node_id") in model_nodes
        ]
        scenarios.append({
            "id": route.get("route_id"),
            "label": position.get("statement") or position.get("metric") or route.get("route_id"),
            "state": position.get("decision_status_at_ic", "MAPPED"),
            "drivers": [*route.get("member_claim_ids", []), *route.get("member_position_ids", [])],
            "metrics": [
                {"label": mn.get("name", mn.get("model_node_id")), "value": mn.get("value")}
                for mn in bound_model_nodes
            ],
            "trajectory": [
                {"stage": mn.get("period_raw") or mn.get("period", ""), "value": mn.get("value")}
                for mn in bound_model_nodes if mn.get("value") is not None
            ],
        })
    return {"scenarios": scenarios}

def _write_json_atomic(path: Path, payload: Any) -> None:
    """Persist one JSON artifact without exposing a partially written bundle."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_text_atomic(path: Path, content: str) -> None:
    """Persist one UTF-8 text artifact without exposing a partial write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _graph_versions_dir(case_id: str) -> Path:
    return _pipeline_out_for_case(case_id) / "graph_versions"


def _graph_version_index_path(case_id: str) -> Path:
    return _graph_versions_dir(case_id) / "index.json"


def _graph_content_hash(graph: dict) -> str:
    canonical = json.dumps(
        graph,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


_GRAPH_OBJECT_COLLECTIONS = (
    ("claims", "claim_id"),
    ("case_positions", "position_id"),
    ("model_nodes", "model_node_id"),
    ("support_routes", "route_id"),
    ("artifacts", "artifact_id"),
)


def _frontend_authority_verb(stop: dict[str, Any]) -> str:
    """Map a runtime Human Stop to one stable application authority verb."""

    if stop.get("authority_verb"):
        return str(stop["authority_verb"])
    reason_code = str(stop.get("reason_code") or "")
    object_id = str(stop.get("object_or_component_id") or "")
    if reason_code == "APPROVED_FROZEN" or object_id == "approved-snapshot":
        return "APPROVE"
    if reason_code in {"NON_WAIVABLE_AXIOM", "HARD_POLICY_BLOCKER"}:
        return "RESOLVE_BLOCKER"
    if reason_code in {
        "BATCH_VALUE_CONFLICT",
        "PRIOR_VALUE_MISMATCH",
        "UNKNOWN_OBJECT_ID",
        "UNKNOWN_TARGET_POSITION_ID",
        "OBJECT_TYPE_MISMATCH",
        "IMMUTABLE_HISTORICAL_FIELD",
    }:
        return "CORRECT_INPUT"
    if reason_code == "CIRCULAR_SUPPORT":
        return "ADMIT_GROUNDED_EVIDENCE"
    if reason_code in {
        "DECISION_REQUIRES_HUMAN",
        "APPLICABLE_MATERIAL_CONTRADICTION",
        "SELF_ADOPTION_FORBIDDEN",
    }:
        return "ADOPT_CURRENT"
    return "RESOLVE_HUMAN_STOP"


def _frontend_human_stop(stop: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(stop)
    result.setdefault(
        "reason",
        str(stop.get("requested_action") or stop.get("reason_code") or "Human review required."),
    )
    result.setdefault("status", "OPEN")
    result.setdefault("authority_verb", _frontend_authority_verb(stop))
    result.setdefault(
        "required_authority_level",
        str(stop.get("required_role") or "PROFESSIONAL_REVIEWER"),
    )
    result.setdefault("downstream_scope", [])
    return result


def _frontend_blocked_component(component: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(component)
    missing = component.get("missing_assumption_or_condition")
    result.setdefault(
        "reason",
        str(missing or component.get("reason_code") or "The component cannot settle."),
    )
    result.setdefault("status", "BLOCKED")
    result.setdefault("downstream_scope", copy.deepcopy(component.get("dependent_ids", [])))
    result.setdefault(
        "resolvable_by",
        str(missing or "Resolve the declared blocking condition and replay the event."),
    )
    return result


def _candidate_deltas(transition_output: dict[str, Any]) -> list[dict[str, Any]]:
    delta = transition_output.get("candidate_current_approved_delta", {}).get("candidate", [])
    if isinstance(delta, dict):
        delta = delta.get("deltas", [])
    return [dict(item) for item in delta if isinstance(item, dict)]


def _blocked_scope_ids(transition_output: dict[str, Any]) -> set[str]:
    blocked: set[str] = set()
    for component in transition_output.get("blocked_components", []):
        if not isinstance(component, dict):
            continue
        blocked.update(str(item) for item in component.get("member_ids", []))
        blocked.update(str(item) for item in component.get("dependent_ids", []))
    for component in transition_output.get("ordered_transitions", []):
        if isinstance(component, dict) and component.get("result") != "SETTLED":
            blocked.update(str(item) for item in component.get("member_ids", []))
    return blocked


def _build_transition_change_sets(
    transition_output: dict[str, Any],
    *,
    candidate_state_id: str,
) -> list[dict[str, Any]]:
    """Build one safe, canonical settlement scope from settled Candidate deltas.

    The live runtime does not own artifact presentation.  The API therefore
    exposes one explicit state-change set whose object scope is derived only
    from SETTLED components.  This avoids representing affected-but-unchanged
    or blocked objects as adoptable work.
    """

    settled_ids = {
        str(member_id)
        for component in transition_output.get("ordered_transitions", [])
        if isinstance(component, dict) and component.get("result") == "SETTLED"
        for member_id in component.get("member_ids", [])
    }
    blocked_ids = _blocked_scope_ids(transition_output)
    partial_status = transition_output.get("partial_settlement_status", {})
    if (
        partial_status.get("candidate") == "FULL"
        and not partial_status.get("unsettled_component_ids")
        and not blocked_ids
    ):
        # Direct/sub-tolerance mutations can be fully reconciled without an
        # executable propagation component.  They are still real Candidate
        # deltas and must remain explicitly selectable.
        settled_ids.update(
            str(item.get("object_id"))
            for item in _candidate_deltas(transition_output)
            if item.get("object_id")
        )
    deltas = [
        item
        for item in _candidate_deltas(transition_output)
        if str(item.get("object_id")) in settled_ids
        and str(item.get("object_id")) not in blocked_ids
    ]
    if not deltas:
        return []
    deltas.sort(
        key=lambda item: (
            str(item.get("object_type") or ""),
            str(item.get("object_id") or ""),
            str(item.get("field") or ""),
        )
    )
    object_ids = sorted({str(item["object_id"]) for item in deltas})
    blocking_stop_ids = sorted(
        {
            str(stop.get("stop_id"))
            for stop in transition_output.get("human_stops", [])
            if isinstance(stop, dict)
            and stop.get("stop_id")
            and (
                str(stop.get("object_or_component_id") or "")
                in set(object_ids) | {"candidate-change-set"}
                or bool(
                    set(str(item) for item in stop.get("downstream_scope", []))
                    & set(object_ids)
                )
            )
        }
    )
    identity = {
        "replay_hash": transition_output.get("replay_hash"),
        "candidate_state_id": candidate_state_id,
        "deltas": [
            {
                "object_id": item.get("object_id"),
                "field": item.get("field"),
                "from": item.get("from"),
                "to": item.get("to"),
            }
            for item in deltas
        ],
    }
    token = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()[:16].upper()
    partial = (
        transition_output.get("partial_settlement_status", {}).get("candidate") != "FULL"
        or bool(blocked_ids)
    )
    return [
        {
            "artifact_id": f"CHANGESET-{token}",
            "change_set_id": f"CHANGESET-{token}",
            "selection_kind": "CANONICAL_STATE_SCOPE",
            "title": (
                "Adopt settled Candidate scope"
                if partial
                else "Adopt Candidate into Current"
            ),
            "version_before": str(transition_output.get("prior_state_id") or "CURRENT"),
            "version_after": candidate_state_id,
            "status": "PARTIAL_READY" if partial else "READY",
            "partial": partial,
            "object_ids": object_ids,
            "blocking_stop_ids": blocking_stop_ids,
            "changes": [
                {
                    "label": f"{item.get('object_id')}.{item.get('field')}",
                    "before": copy.deepcopy(item.get("from")),
                    "after": copy.deepcopy(item.get("to")),
                    "trace_id": str(item.get("object_id")),
                    "object_type": item.get("object_type"),
                    "field": item.get("field"),
                    "reason_code": item.get("reason_code"),
                }
                for item in deltas
            ],
        }
    ]


def _normalise_selected_change_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise HTTPException(400, "selected_change_ids must be an array")
    selected: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str) or not raw.strip():
            raise HTTPException(400, "selected_change_ids must contain non-empty strings")
        change_id = raw.strip()
        if change_id in seen:
            raise HTTPException(409, f"Duplicate selected change id: {change_id}")
        seen.add(change_id)
        selected.append(change_id)
    return selected


def _change_set_index(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["artifact_id"]): item
        for item in run.get("artifact_change_sets", [])
        if isinstance(item, dict) and item.get("artifact_id")
    }


def _selected_object_ids(run: dict[str, Any], selected_ids: list[str]) -> set[str]:
    index = _change_set_index(run)
    return {
        str(object_id)
        for change_id in selected_ids
        for object_id in index[change_id].get("object_ids", [])
    }


def _required_human_stop_ids(
    run: dict[str, Any],
    selected_ids: list[str],
    selected_object_ids: set[str],
) -> set[str]:
    """Return only Human Stops governing the explicitly selected scope."""

    index = _change_set_index(run)
    explicitly_scoped = all(
        "blocking_stop_ids" in index[change_id] for change_id in selected_ids
    )
    if explicitly_scoped:
        return {
            str(stop_id)
            for change_id in selected_ids
            for stop_id in index[change_id].get("blocking_stop_ids", [])
            if stop_id
        }

    # Backward-compatible derivation for pre-V20.1 stored runs.
    required: set[str] = set()
    for stop in run.get("transition_output", {}).get("human_stops", []):
        if not isinstance(stop, dict) or not stop.get("stop_id"):
            continue
        object_id = str(stop.get("object_or_component_id") or "")
        downstream = {str(item) for item in stop.get("downstream_scope", [])}
        if (
            object_id == "candidate-change-set"
            or object_id in selected_object_ids
            or bool(downstream & selected_object_ids)
        ):
            required.add(str(stop["stop_id"]))
    return required


def _bounded_settlement_graph(
    current_graph: dict[str, Any],
    candidate_graph: dict[str, Any],
    selected_object_ids: set[str],
) -> dict[str, Any]:
    """Overlay only explicitly selected Candidate objects onto Current."""

    graph = copy.deepcopy(current_graph)
    for collection, id_field in _GRAPH_OBJECT_COLLECTIONS:
        candidate_items = [
            item
            for item in candidate_graph.get(collection, [])
            if isinstance(item, dict)
            and str(item.get(id_field) or "") in selected_object_ids
        ]
        if collection not in graph and not candidate_items:
            continue
        current_items = graph.setdefault(collection, [])
        positions = {
            str(item.get(id_field)): index
            for index, item in enumerate(current_items)
            if isinstance(item, dict) and item.get(id_field)
        }
        for candidate_item in candidate_items:
            object_id = str(candidate_item.get(id_field) or "")
            if object_id in positions:
                current_items[positions[object_id]] = copy.deepcopy(candidate_item)
            else:
                positions[object_id] = len(current_items)
                current_items.append(copy.deepcopy(candidate_item))

    edge_specs = (
        ("claim_position_edges", "edge_id", ("claim_id", "position_id")),
        ("position_dependencies", "edge_id", ("from_position_id", "to_position_id")),
        ("position_model_bindings", "binding_id", ("position_id", "model_node_id")),
    )
    for collection, id_field, endpoints in edge_specs:
        candidate_items = [
            item
            for item in candidate_graph.get(collection, [])
            if isinstance(item, dict)
            and any(
                str(item.get(field) or "") in selected_object_ids
                for field in endpoints
            )
        ]
        if collection not in graph and not candidate_items:
            continue
        current_items = graph.setdefault(collection, [])
        positions = {
            str(item.get(id_field)): index
            for index, item in enumerate(current_items)
            if isinstance(item, dict) and item.get(id_field)
        }
        graph_object_ids = {
            str(item.get(id_name) or "")
            for object_collection, id_name in _GRAPH_OBJECT_COLLECTIONS
            for item in graph.get(object_collection, [])
            if isinstance(item, dict) and item.get(id_name)
        }
        for candidate_item in candidate_items:
            edge_id = str(candidate_item.get(id_field) or "")
            if not edge_id:
                continue
            endpoint_ids = [str(candidate_item.get(field) or "") for field in endpoints]
            if not all(endpoint_id in graph_object_ids for endpoint_id in endpoint_ids):
                continue
            if edge_id in positions:
                # Existing relations are changed only when their complete scope
                # was explicitly selected.  Unchanged one-sided relations need
                # no overlay and cannot import a blocked endpoint.
                if all(endpoint_id in selected_object_ids for endpoint_id in endpoint_ids):
                    current_items[positions[edge_id]] = copy.deepcopy(candidate_item)
            else:
                positions[edge_id] = len(current_items)
                current_items.append(copy.deepcopy(candidate_item))
    return graph


def _graph_counts(graph: dict) -> dict[str, int]:
    return {
        "claims": len(graph.get("claims", [])),
        "case_positions": len(graph.get("case_positions", graph.get("positions", []))),
        "model_nodes": len(graph.get("model_nodes", [])),
        "support_routes": len(graph.get("support_routes", [])),
        "claim_position_edges": len(graph.get("claim_position_edges", [])),
    }


def _read_graph_version_index(case_id: str) -> list[dict[str, Any]]:
    payload = _load_json_safe(_graph_version_index_path(case_id))
    versions = payload.get("versions", []) if isinstance(payload, dict) else []
    return [dict(item) for item in versions if isinstance(item, dict)]


def _list_graph_versions(case_id: str) -> list[dict[str, Any]]:
    versions = [
        item for item in _read_graph_version_index(case_id)
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
    path = _graph_versions_dir(case_id) / filename
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
            versions = _read_graph_version_index(case_id)
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
                    _graph_version_index_path(case_id),
                    {
                        "schema_version": "graph-version-index/1.0",
                        "updated_at": _now_iso(),
                        "versions": versions,
                    },
                )
            return {key: value for key, value in existing.items() if key != "graph"}

        _write_json_atomic(path, snapshot)
        versions = _read_graph_version_index(case_id)
        if not any(
            item.get("case_id") == case_id
            and item.get("version_id") == version_id
            for item in versions
        ):
            versions.append(metadata)
        _write_json_atomic(
            _graph_version_index_path(case_id),
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
        _graph_versions_dir(case_id) / Path(str(metadata["filename"])).name
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


def _current_graph_as_of(
    case_id: str,
    cutoff: dt.datetime,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return the latest immutable Current graph known by the cutoff."""
    eligible = [
        item
        for item in _list_graph_versions(case_id)
        if str(item.get("kind")) == "CURRENT" and _known_by(item, cutoff)
    ]
    if not eligible:
        return {}, None
    metadata = max(
        eligible,
        key=lambda item: (
            _parse_temporal_instant(item.get("known_at"))
            or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
            str(item.get("version_id") or ""),
        ),
    )
    snapshot = _load_graph_version(case_id, str(metadata["version_id"]))
    graph = snapshot.get("graph") if isinstance(snapshot, dict) else None
    return (copy.deepcopy(graph), metadata) if isinstance(graph, dict) else ({}, metadata)


def _graph_collection_delta(
    baseline: dict,
    current: dict,
    collection: str,
    id_fields: tuple[str, ...],
) -> dict[str, Any]:
    """Compare one graph collection by stable object identity."""
    def indexed(graph: dict) -> dict[str, dict]:
        records: dict[str, dict] = {}
        for item in graph.get(collection, []) or []:
            if not isinstance(item, dict):
                continue
            object_id = next(
                (str(item[field]) for field in id_fields if item.get(field)),
                "",
            )
            if object_id:
                records[object_id] = item
        return records

    before = indexed(baseline)
    after = indexed(current)
    added = sorted(after.keys() - before.keys())
    removed = sorted(before.keys() - after.keys())
    unchanged = []
    changed = []
    for object_id in sorted(before.keys() & after.keys()):
        if _stable_json_hash(before[object_id]) == _stable_json_hash(after[object_id]):
            unchanged.append(object_id)
            continue
        changed_fields = sorted(
            key
            for key in before[object_id].keys() | after[object_id].keys()
            if before[object_id].get(key) != after[object_id].get(key)
        )
        changed.append({
            "object_id": object_id,
            "changed_fields": changed_fields,
            "before_hash": _stable_json_hash(before[object_id]),
            "after_hash": _stable_json_hash(after[object_id]),
        })
    return {
        "collection": collection,
        "added_ids": added,
        "removed_ids": removed,
        "changed": changed,
        "unchanged_ids": unchanged,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": len(unchanged),
        },
    }


def _build_reunderwrite(
    case_id: str,
    baseline_state_id: str | None = None,
    current_state_id: str | None = None,
) -> dict[str, Any]:
    """Compare two immutable Current states and project the selected latest one."""
    versions = [
        item for item in _list_graph_versions(case_id)
        if str(item.get("kind")) == "CURRENT"
    ]
    versions.sort(key=lambda item: (
        _parse_temporal_instant(item.get("known_at"))
        or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        str(item.get("version_id") or ""),
    ))
    if not versions:
        raise HTTPException(409, "Re-underwrite requires immutable Current graph versions")

    by_state = {str(item.get("state_id")): item for item in versions}
    current_meta = by_state.get(str(current_state_id)) if current_state_id else versions[-1]
    if current_meta is None:
        raise HTTPException(404, f"Current state version not found: {current_state_id}")
    current_index = versions.index(current_meta)
    if baseline_state_id:
        baseline_meta = by_state.get(str(baseline_state_id))
        if baseline_meta is None:
            raise HTTPException(404, f"Baseline state version not found: {baseline_state_id}")
    elif current_index > 0:
        baseline_meta = versions[current_index - 1]
    else:
        raise HTTPException(409, "Re-underwrite requires a prior Current graph version")
    if baseline_meta["state_id"] == current_meta["state_id"]:
        raise HTTPException(400, "Baseline and Current state must be different")
    if versions.index(baseline_meta) >= current_index:
        raise HTTPException(400, "Baseline state must precede Current state")

    baseline_snapshot = _load_graph_version(case_id, str(baseline_meta["version_id"]))
    current_snapshot = _load_graph_version(case_id, str(current_meta["version_id"]))
    baseline_graph = copy.deepcopy(baseline_snapshot["graph"])
    current_graph = copy.deepcopy(current_snapshot["graph"])
    deltas = [
        _graph_collection_delta(
            baseline_graph,
            current_graph,
            "claims",
            ("claim_id", "stable_id", "id"),
        ),
        _graph_collection_delta(
            baseline_graph,
            current_graph,
            "case_positions",
            ("position_id", "id"),
        ),
        _graph_collection_delta(
            baseline_graph,
            current_graph,
            "model_nodes",
            ("model_node_id", "id"),
        ),
    ]
    comparison = {
        "schema_version": "reunderwrite-comparison/1.0",
        "case_id": case_id,
        "baseline_state_id": baseline_meta["state_id"],
        "current_state_id": current_meta["state_id"],
        "baseline_graph_hash": baseline_meta["graph_hash"],
        "current_graph_hash": current_meta["graph_hash"],
        "baseline_known_at": baseline_meta["known_at"],
        "current_known_at": current_meta["known_at"],
        "collections": {item["collection"]: item for item in deltas},
        "changed_object_count": sum(
            item["counts"]["added"]
            + item["counts"]["removed"]
            + item["counts"]["changed"]
            for item in deltas
        ),
        "method": {
            "identity": "stable object ID within each graph collection",
            "change_detection": "canonical JSON SHA-256 inequality",
            "field_explanation": "top-level fields whose values differ",
        },
    }

    projection = _build_projection(case_id)
    deal = projection["deal"]
    if "case_positions" in current_graph:
        current_graph["positions"] = current_graph["case_positions"]
    graph_claims = current_graph.get("claims", [])
    if isinstance(graph_claims, list):
        claims = _enrich_claims(graph_claims, _load_bears_on_map(case_id))
        deal["claims"] = claims
        deal["source_center"] = {
            "sources": _build_sources_from_claims(claims, case_id)
        }
        deal["question_spine"] = _build_question_spine(
            _load_questions(case_id),
            claims,
        )
    deal.update({
        "as_of_state_id": str(current_meta["state_id"]),
        "as_of_date": str(current_meta["known_at"])[:10],
        "current_graph": current_graph,
        "candidate_graph": {},
        "transition_output": {},
        "reunderwrite": comparison,
    })
    projection = _apply_decision_intelligence(projection)
    context = _make_context(
        case_id,
        str(current_meta["state_id"]),
        str(current_meta["known_at"])[:10],
    )
    return {
        "mode": "RE_UNDERWRITE",
        "read_only": True,
        "comparison": comparison,
        "projection": {
            "projection": projection,
            "context": context,
            "registry": [],
        },
    }


def _runtime_execution_graph(case_id: str) -> Path:
    pipeline_out = _pipeline_out_for_case(case_id)
    candidates = (
        VAULT / "deals" / case_id / "models" / "execution_graph_v7.json",
        pipeline_out / "execution_graph_v7.json",
    )
    if case_id == "keystone":
        candidates += (
            ROOT / "pipeline_out" / "e3" / "K-PRE" / "adapter_alpha" / "execution_graph_v7.json",
        )
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is not None:
        return path
    # No hand-curated or previously-compiled mapping exists yet for this case.
    # extract_v2 captures a workbook_formula_graphs.json for every uploaded
    # .xlsx/.xlsm regardless of case -- if this case has one, mechanically
    # compile a runtime mapping from its own formulas (PAN-55) rather than
    # borrowing keystone's or declaring a blocker a case could resolve itself
    # just by having uploaded a spreadsheet.
    formula_graphs_path = pipeline_out / "workbook_formula_graphs.json"
    if formula_graphs_path.exists():
        from tools.workbook_model_compiler import (
            WorkbookModelCompilerError,
            compile_workbook_formula_graphs,
        )
        try:
            payload = json.loads(formula_graphs_path.read_text(encoding="utf-8"))
            # PAN-67 activates only when PAN-65 has persisted its auditable
            # resolution.  Without that artifact the PAN-55 cell-address graph
            # remains the conservative fallback; no semantic binding is guessed
            # merely because workbook formulas exist.
            binding_resolution_path = pipeline_out / "model_binding_resolution.json"
            graph = compile_workbook_formula_graphs(
                payload,
                case_id,
                binding_resolution=(
                    binding_resolution_path
                    if binding_resolution_path.exists()
                    else None
                ),
            )
        except WorkbookModelCompilerError as exc:
            # Same failure shape admit_evidence already knows how to turn
            # into a declared RUNTIME_MAPPING_REQUIRED Human Stop -- a case
            # whose workbook has no formulas, or none the compiler can
            # honestly resolve, is exactly the case that gets no mapping.
            raise DynamicsBundleError(
                f"execution_graph_v7.json could not be mechanically compiled: {exc}"
            ) from exc
        derived_path = VAULT / "deals" / case_id / "models" / "execution_graph_v7.json"
        derived_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(derived_path, graph)
        return derived_path
    raise DynamicsBundleError("execution_graph_v7.json is required to compile admitted evidence")


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

    from tools.adapter_alpha import compile_e3_runtime_bundle

    runtime_dir = _pipeline_out_for_case(case_id) / "runtime"
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
    extraction_path = runtime_dir / "extraction_graph.json"
    execution_path = _runtime_execution_graph(case_id)
    artifacts = compile_e3_runtime_bundle(
        e3,
        execution_path,
        status="LIVE",
        deal=case_id,
        e3_claims_sha256=hashlib.sha256(e3_path.read_bytes()).hexdigest(),
        extraction_graph_path=extraction_path,
    )
    bundle = artifacts.bundle
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
    # The compiled graph's own ``case_id`` is institutional metadata from the
    # execution manifest (e.g. keystone's is "PROJECT-KEYSTONE") and is not
    # guaranteed to equal the URL case slug; _pipeline_out_for_case already
    # gives every case its own bundle directory, so that isolation -- not a
    # string match against embedded metadata -- is what guarantees this file
    # belongs to this case. A strict equality check here previously made this
    # function return empty on every call, silently discarding every prior
    # settled state and recomputing a wrong baseline on each admission.
    pipeline_out = _pipeline_out_for_case(case_id)
    runtime_state = _load_json_safe(pipeline_out / "runtime_state.json")
    if isinstance(runtime_state, dict) and isinstance(runtime_state.get("current_graph"), dict):
        return copy.deepcopy(runtime_state["current_graph"])
    current = _load_json_safe(pipeline_out / "current_graph.json")
    if isinstance(current, dict) and current:
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


def _promote_live_runtime_bundle(
    case_id: str,
    compiled: dict,
    baseline_graph: dict,
    event: dict,
) -> Path:
    pipeline_out = _pipeline_out_for_case(case_id)
    pipeline_out.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(compiled["runtime_dir"])
    _write_json_atomic(pipeline_out / "current_graph.json", baseline_graph)
    for filename in (
        "execution_mapping.json",
        "adapter_report.json",
        "admission_manifest_v7.json",
    ):
        _write_json_atomic(pipeline_out / filename, _load_json_safe(runtime_dir / filename))
    for filename in (
        "execution_graph_v7.json",
        "keystone_materiality_policy_v0.json",
        "keystone_authority_matrix_v0.json",
    ):
        (pipeline_out / filename).write_bytes((runtime_dir / filename).read_bytes())
    event_path = pipeline_out / f"event_evidence_admitted_{event['event_id'].removeprefix('EVIDENCE-ADMITTED-')}.json"
    _write_json_atomic(event_path, event)
    _write_json_atomic(pipeline_out / "candidate_graph.json", {})
    _write_json_atomic(pipeline_out / "transition_output.json", {})
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
    pipeline_out = _pipeline_out_for_case(case_id)
    runtime_state = _load_json_safe(pipeline_out / "runtime_state.json")
    if isinstance(runtime_state, dict) and runtime_state.get("state_id"):
        return str(runtime_state["state_id"])
    current_graph = _load_json_safe(pipeline_out / "current_graph.json")
    if isinstance(current_graph, dict) and current_graph.get("state_id"):
        return str(current_graph["state_id"])
    return f"STATE-{case_id.upper()}-CURRENT"

def _load_profile(case_id: str) -> dict:
    p = VAULT / "deals" / case_id / "deal_profile.json"
    return json.loads(p.read_text()) if p.exists() else {}

def _load_claims(case_id: str = "keystone") -> list[dict]:
    f = _pipeline_out_for_case(case_id) / "claims.json"
    return json.loads(f.read_text()) if f.exists() else []

def _load_bears_on_map(case_id: str = "keystone") -> dict[str, list[str]]:
    db_path = INDEX_DB
    if not db_path.exists():
        return {}
    try:
        con = sqlite3.connect(str(db_path))
        rows = con.execute(
            "SELECT frontmatter FROM nodes WHERE type='claim' AND LOWER(COALESCE(deal, '')) = LOWER(?)",
            (case_id,),
        ).fetchall()
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
    lens = _active_fund_lens(case_id)
    lens_questions = {str(item["id"]): item for item in lens["questions"]}
    lens_order = {str(item["id"]): index for index, item in enumerate(lens["questions"])}
    out = []
    if q_dir.exists():
        for md in sorted(q_dir.glob("*.md")):
            fm = _read_frontmatter(md)
            if fm:
                # Migrate the initial Q-xx registry created before origins were
                # recorded; it is archetype grammar, not deal-emergent evidence.
                if not fm.get("origin") and str(fm.get("id", "")).startswith("Q-"):
                    fm["origin"] = "archetype"
                    fm.setdefault("question_version", 1)
                qid = str(fm.get("id") or "")
                if fm.get("origin") in {"fund_lens", "archetype"}:
                    active = lens_questions.get(qid)
                    if not active:
                        continue
                    fm.update({
                        "title": active["title"],
                        "question": active["title"],
                        "workstream": active.get("workstream", "underwriting"),
                        "origin": "fund_lens",
                        "question_version": active.get("version", 1),
                        "fund_lens_id": lens["lens_id"],
                        "fund_lens_version": lens["version"],
                    })
                out.append(fm)
    existing = {str(item.get("id")) for item in out}
    for question in lens["questions"]:
        if str(question["id"]) in existing:
            continue
        out.append({
            "type": "question", "id": question["id"], "deal": case_id,
            "title": question["title"], "question": question["title"],
            "state": "open", "status": "open", "critical": False,
            "workstream": question.get("workstream", "underwriting"),
            "origin": "fund_lens", "question_version": question.get("version", 1),
            "fund_lens_id": lens["lens_id"], "fund_lens_version": lens["version"],
        })
    out.sort(key=lambda item: (
        0 if str(item.get("id") or "") in lens_order else 1,
        lens_order.get(str(item.get("id") or ""), 10**9),
        str(item.get("id") or ""),
    ))
    return out


def _load_spine_change_proposals(case_id: str) -> list[dict]:
    """Collect deal-emergent question proposals from durable evidence reviews."""
    proposals_dir = _pipeline_out_for_case(case_id) / "proposals"
    if not proposals_dir.exists():
        return []
    collected: dict[str, dict] = {}
    for path in sorted(proposals_dir.glob("evidence-*.json")):
        evidence = _load_json_safe(path)
        if not isinstance(evidence, dict) or evidence.get("case_id") != case_id:
            continue
        for raw in evidence.get("question_proposals", []) or []:
            if not isinstance(raw, dict) or not raw.get("proposal_id"):
                continue
            item = dict(raw)
            item["evidence_proposal_id"] = evidence.get("proposal_id")
            item["evidence_job_id"] = evidence.get("job_id")
            item["source_id"] = evidence.get("source_id")
            collected[str(item["proposal_id"])] = item
    return [collected[key] for key in sorted(collected)]


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
            "kind": fm.get("kind", fm.get("type", "institutional_event")),
            "label": fm.get("label") or f"{fm.get('type', 'Event').replace('_', ' ').title()}: {fm.get('source', event_id)}",
            "source_title": fm.get("source", "PANTA evidence intake"),
            "source_id": fm.get("source_id", fm.get("source", "")),
            "source_version_id": fm.get("proposal_id", fm.get("source", "")),
            "source_passage": fm.get("detail", "Evidence admitted after professional review."),
            "locator": fm.get("locator", ""), "definition": fm.get("definition_id", ""),
            "period": fm.get("period", ""), "perimeter": fm.get("perimeter", ""),
            "effective_date": str(fm.get("effective_date") or known_at[:10]),
            "known_at": known_at, "proposed_treatment": fm.get("proposed_treatment", "Run dynamics against the admitted semantic Current."),
            "proposed_position": fm.get("proposed_position", "Run dynamics against the admitted semantic Current."),
            "source_state_id": fm.get("source_state_id", fm.get("prior_state_id")),
            "result_state_id": fm.get("result_state_id", fm.get("current_state_id")),
            "run_id": fm.get("run_id"),
            "actor": fm.get("actor"),
        }
    return events


def _parse_temporal_instant(value: Any) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raw += "T00:00:00Z"
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _known_by(record: dict, cutoff: dt.datetime) -> bool:
    known_at = _parse_temporal_instant(record.get("known_at"))
    return known_at is not None and known_at <= cutoff


def _stable_json_hash(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _event_replay_snapshots(events: list[dict]) -> list[dict]:
    """Fold known events into the four replay quadrants."""
    ordered = sorted(
        events,
        key=lambda item: (
            _parse_temporal_instant(item.get("known_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
            str(item.get("event_id") or ""),
        ),
    )
    state: dict[str, list[str]] = {
        "known": [], "believed": [], "approved": [], "open": [],
    }
    snapshots = []
    prior_state_id = "STATE-ORIGIN"
    for index, event in enumerate(ordered, start=1):
        kind = str(event.get("kind") or event.get("type") or "").upper()
        summary = str(event.get("label") or event.get("event_id") or "Event")
        if kind in {"SOURCE", "INGEST", "INGEST_REQUESTED", "EVIDENCE_ADMITTED", "COMPILER", "ORIGIN"}:
            bucket = "known"
        elif kind in {"AUTHORITY", "IC_RECORD", "DECISION", "SETTLEMENT"}:
            bucket = "approved"
        elif kind in {"COVERAGE", "BLOCK", "HUMAN_STOP"}:
            bucket = "open"
        else:
            bucket = "believed"
        state[bucket].append(summary)
        event_id = str(event["event_id"])
        result_state_id = str(event.get("result_state_id") or f"STATE-{event_id}")
        source_state_id = str(event.get("source_state_id") or prior_state_id)
        snapshots.append({
            "id": result_state_id,
            "event_id": event_id,
            "date": event["effective_date"],
            "effective_date": event["effective_date"],
            "known_at": event["known_at"],
            "label": summary,
            "known": state["known"][-4:],
            "believed": state["believed"][-4:],
            "approved": state["approved"][-4:],
            "open": state["open"][-4:],
            "event_index": index,
            "source_state_id": source_state_id,
            "result_state_id": result_state_id,
            "derived_from_event_log": True,
            "stable_hash": _stable_json_hash(event),
        })
        prior_state_id = result_state_id
    return snapshots

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
            "bears_on": bears_on_map.get(cid, c.get("bears_on", [])),
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
            "critical": bool(q.get("critical", False)),
            "owner": q.get("owner", "Unassigned"),
            "origin": q.get("origin", "deal_emergent"),
            "question_version": q.get("question_version", 1),
            "work_plan": q.get("work_plan", []) if isinstance(q.get("work_plan"), list) else [],
        })
    return spine


def _apply_decision_intelligence(projection: dict) -> dict:
    """Add transparent structural rankings without inventing business weights."""
    deal = projection.get("deal") if isinstance(projection, dict) else None
    if not isinstance(deal, dict):
        return projection

    graph = deal.get("current_graph") if isinstance(deal.get("current_graph"), dict) else {}
    positions = graph.get("case_positions", graph.get("positions", [])) or []
    bindings = graph.get("position_model_bindings", []) or []
    dependencies = graph.get("position_dependencies", []) or []
    load_bearing = []
    for position in positions:
        position_id = str(position.get("position_id") or position.get("id") or "")
        if not position_id:
            continue
        model_node_ids = {
            str(item)
            for item in position.get("model_node_ids", [])
            if item
        }
        model_node_ids.update(
            str(binding.get("model_node_id"))
            for binding in bindings
            if binding.get("position_id") == position_id
            and str(binding.get("status", "ACTIVE")).upper() == "ACTIVE"
            and binding.get("model_node_id")
        )
        dependent_position_ids = sorted({
            str(edge.get("target_position_id") or edge.get("target") or "")
            for edge in dependencies
            if str(edge.get("source_position_id") or edge.get("source") or "") == position_id
            and (edge.get("target_position_id") or edge.get("target"))
        })
        decision_status = str(
            position.get("decision_status")
            or position.get("decision_status_at_ic")
            or "PENDING"
        ).upper()
        epistemic_status = str(
            position.get("epistemic_status")
            or position.get("epistemic_status_at_ic")
            or "UNKNOWN"
        ).upper()
        gate_relevant = decision_status in {
            "BLOCKED", "PENDING", "CONTESTED", "ACCEPTED_WITH_CONDITIONS",
        }
        contested = epistemic_status in {"CONTESTED", "WEAK", "UNKNOWN"}
        load_bearing.append({
            "position_id": position_id,
            "id": position_id,
            "label": position.get("label") or position.get("metric") or position_id,
            "statement": position.get("statement", ""),
            "decision_status": decision_status,
            "epistemic_status": epistemic_status,
            "active_model_node_ids": sorted(model_node_ids),
            "dependent_position_ids": dependent_position_ids,
            "gate_relevant": gate_relevant,
            "contested": contested,
            "ranking_basis": {
                "ordering": [
                    "gate_relevant descending",
                    "active_model_node_count descending",
                    "dependent_position_count descending",
                    "contested descending",
                    "position_id ascending",
                ],
                "gate_relevant": gate_relevant,
                "active_model_node_count": len(model_node_ids),
                "dependent_position_count": len(dependent_position_ids),
                "contested": contested,
            },
        })
    load_bearing.sort(key=lambda item: (
        not item["gate_relevant"],
        -item["ranking_basis"]["active_model_node_count"],
        -item["ranking_basis"]["dependent_position_count"],
        not item["contested"],
        item["position_id"],
    ))
    for rank, item in enumerate(load_bearing, start=1):
        item["rank"] = rank
        item["explanation"] = (
            f"gate_relevant={str(item['gate_relevant']).lower()}; "
            f"active_model_nodes={item['ranking_basis']['active_model_node_count']}; "
            f"dependent_positions={item['ranking_basis']['dependent_position_count']}; "
            f"contested={str(item['contested']).lower()}"
        )
    deal["load_bearing_assumptions"] = load_bearing

    spine = deal.get("question_spine", []) or []
    open_questions = [
        item for item in spine
        if item.get("coverage") in {"gap", "partial"}
        and str(item.get("status", "open")).lower() not in {"closed", "resolved"}
    ]
    open_questions.sort(key=lambda item: (
        not bool(item.get("critical")),
        item.get("coverage") != "gap",
        int(item.get("claim_count") or 0),
        str(item.get("id") or ""),
    ))
    unknowns = []
    for rank, question in enumerate(open_questions, start=1):
        question_id = str(question.get("id") or question.get("question_id") or "")
        work_plan = question.get("work_plan", []) or []
        first_work = work_plan[0] if work_plan and isinstance(work_plan[0], dict) else {}
        unknowns.append({
            "id": f"unknown:{question_id}",
            "label": question.get("label", question_id),
            "question_id": question_id,
            "value": "Critical evidence gap" if question.get("critical") else "Open evidence gap",
            "closure": first_work.get("label") or first_work.get("task") or f"Admit evidence that bears on {question_id}.",
            "owner": first_work.get("owner") or question.get("owner") or "Unassigned",
            "rank": rank,
            "status": "OPEN",
            "ranking_basis": {
                "ordering": [
                    "critical descending",
                    "coverage gap before partial",
                    "admitted claim count ascending",
                    "question_id ascending",
                ],
                "critical": bool(question.get("critical")),
                "coverage": question.get("coverage"),
                "admitted_claim_count": int(question.get("claim_count") or 0),
            },
        })

    # Conflicts: positions the runtime itself marked CONTESTED after a
    # material CONTRADICTS landed (panta_transition_engine.py sets
    # epistemic_status="CONTESTED" only on that path -- this is a real
    # disagreement between admitted claims, not mere thin coverage).
    for item in load_bearing:
        if item["epistemic_status"] != "CONTESTED":
            continue
        unknowns.append({
            "id": f"conflict:{item['position_id']}",
            "label": f"Contested: {item['label']}",
            "question_id": None,
            "value": "Admitted claims disagree",
            "closure": "Resolve the contradiction or accept the residual risk.",
            "status": "CONTESTED",
        })

    # Runtime blockers: what the transition engine itself declared while
    # computing the current Candidate, surfaced verbatim rather than
    # re-derived, so Unknowns never claims a coverage state the runtime
    # didn't actually report.
    transition_output = deal.get("transition_output") if isinstance(deal.get("transition_output"), dict) else {}
    for stop in transition_output.get("human_stops") or []:
        if not isinstance(stop, dict):
            continue
        unknowns.append({
            "id": f"blocker:{stop.get('stop_id') or stop.get('id') or len(unknowns)}",
            "label": stop.get("reason") or stop.get("label") or stop.get("code") or "Runtime Human Stop",
            "question_id": None, "value": stop.get("code", "HUMAN_STOP"),
            "closure": stop.get("required_action") or "Requires an explicit human decision to proceed.",
            "status": "HUMAN_STOP",
        })
    for limit in transition_output.get("coverage_limits") or []:
        if not isinstance(limit, dict):
            continue
        unknowns.append({
            "id": f"blocker:{limit.get('reason_code') or len(unknowns)}",
            "label": limit.get("effect") or limit.get("reason_code") or "Runtime coverage limit",
            "question_id": None, "value": limit.get("reason_code", "COVERAGE_LIMIT"),
            "closure": limit.get("resolution") or "Requires review before dynamics can complete.",
            "status": "COVERAGE_LIMIT",
        })

    rooms = deal.setdefault("rooms", {})
    rooms.setdefault("foundations", {"sets": []})
    rooms["unknowns"] = {"items": unknowns}
    rooms.setdefault("shadowIC", {"theses": []})

    if unknowns:
        first = unknowns[0]
        basis = first["ranking_basis"]
        deal["next_best_work"] = {
            "id": f"NBW-{first['question_id']}",
            "question_id": first["question_id"],
            "label": first["closure"],
            "reason": (
                f"Ranked first by declared lexicographic policy: critical={str(basis['critical']).lower()}, "
                f"coverage={basis['coverage']}, admitted_claims={basis['admitted_claim_count']}."
            ),
            "owner": first["owner"],
            "duration": "Not estimated",
            "unlocks": [first["question_id"]],
            "ranking_basis": basis,
        }
    else:
        deal["next_best_work"] = {
            "id": None,
            "label": "No unresolved evidence gap",
            "reason": "Every open question has full admitted-claim coverage.",
            "owner": "Unassigned",
            "duration": "Not applicable",
            "unlocks": [],
        }
    return projection

def _make_context(case_id: str, as_of_state_id: str, as_of_date: str) -> dict:
    """Build a context object that passes contracts.js validateContext."""
    active_lens_id = _active_fund_lens(case_id)["lens_id"]
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
            "authority_roles": [
                "WORKSTREAM_REVIEWER",
                "QUALIFIED_PROFESSIONAL_REVIEWER",
                "FINANCIAL_OR_WORKSTREAM_REVIEWER",
                "PROFESSIONAL_REVIEWER",
                "AUTHORITY_HOLDER",
                "PARTNER",
                "DEAL_PARTNER",
            ],
            "authority_verbs": [
                "ADOPT_CURRENT",
                "APPROVE",
                "CORRECT_INPUT",
                "ADMIT_GROUNDED_EVIDENCE",
                "RESOLVE_BLOCKER",
                "RESOLVE_HUMAN_STOP",
            ],
        },
        "viewer_projection": "partner",
        "authority_assignments": [],
        "demo_session_id": None,
        "synthetic": False,
        "no_external_effects": False,
        "contract_version": "20.0",
        "active_lens_id": active_lens_id,
    }

def _build_projection(case_id: str, as_of_date: str | None = None) -> dict:
    """Build a full projection object that passes contracts.js validateProjection."""
    from compiler_projection_adapter import map_compiler_bundle

    pipeline_out = _pipeline_out_for_case(case_id)
    profile = _load_profile(case_id)
    raw_claims = _load_claims(case_id)
    bears_on_map = _load_bears_on_map(case_id)
    claims = _enrich_claims(raw_claims, bears_on_map)
    sources = _build_sources_from_claims(raw_claims, case_id)
    events = _load_projection_events(case_id)
    questions = _load_questions(case_id)
    fund_lens = _active_fund_lens(case_id)
    question_spine = _build_question_spine(questions, claims)
    semantic_graph = _load_json_safe(pipeline_out / "semantic_current_graph.json")
    current_graph = _load_json_safe(pipeline_out / "current_graph.json")
    candidate_graph = _load_json_safe(pipeline_out / "candidate_graph.json")
    transition_output = _load_json_safe(pipeline_out / "transition_output.json")
    graph_versions = _list_graph_versions(case_id)
    foundations, unknowns, semantic_positions = (
        _semantic_rooms(semantic_graph, question_spine)
        if semantic_graph else ([], {"items": []}, [])
    )
    scenario_lab = _scenario_lab(current_graph)

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
    snapshots = _event_replay_snapshots(list(events.values()))

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
                "authority_roles": [
                    "WORKSTREAM_REVIEWER",
                    "QUALIFIED_PROFESSIONAL_REVIEWER",
                    "FINANCIAL_OR_WORKSTREAM_REVIEWER",
                    "PROFESSIONAL_REVIEWER",
                    "AUTHORITY_HOLDER",
                    "PARTNER",
                    "DEAL_PARTNER",
                ],
                "authority_verbs": [
                    "ADOPT_CURRENT",
                    "APPROVE",
                    "CORRECT_INPUT",
                    "ADMIT_GROUNDED_EVIDENCE",
                    "RESOLVE_BLOCKER",
                    "RESOLVE_HUMAN_STOP",
                ],
                "effective_date": "2024-01-01T00:00:00Z",
                "known_at": "2024-01-01T00:00:00Z",
            }
        ],
        "deal": {
            "case_id": case_id,
            "entity": profile.get("entity", case_id),
            "archetype": {
                "id": "buyout", "label": "Buyout", "is_default": True,
                "fund_lens": fund_lens["lens_id"],
                "fund_lens_version": fund_lens["version"],
            },
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
            "decisionRoom": _default_decision_room(case_id),
            "executionRoom": _default_execution_room(),
            "lenses": [{
                "lens_id": fund_lens["lens_id"],
                "id": fund_lens["lens_id"],
                "version": fund_lens["version"],
                "label": fund_lens["label"],
                "description": fund_lens.get("description", ""),
                "question_order": [item["id"] for item in fund_lens["questions"]],
                "required_question_ids": [item["id"] for item in fund_lens["questions"]],
                "effective_date": fund_lens.get("effective_date"),
                "known_at": str(fund_lens.get("effective_date") or _today()) + "T00:00:00Z",
            }],
            "default_lens_id": fund_lens["lens_id"],
            "active_lens_id": fund_lens["lens_id"],
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
            "spine_change_proposals": _load_spine_change_proposals(case_id),
            "condition_edges": [],
            "validation_envelopes": [],
            "source_center": {"sources": sources},
            "rooms": {
                "foundations": {"sets": foundations},
                "unknowns": unknowns,
                "shadowIC": {"theses": []},
            },
            "scenarioLab": scenario_lab,
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
        result["deal"]["scenarioLab"] = projection["deal"]["scenarioLab"]
        result["deal"]["positions"] = semantic_positions
        result["deal"]["semantic_current_graph"] = semantic_graph
        result["deal"]["replay"] = projection["deal"]["replay"]
        result["deal"]["temporal"] = projection["deal"]["temporal"]
        result["deal"]["as_of_state_id"] = state_id
        result["deal"]["as_of_date"] = as_of_date
        result["deal"]["objective"] = projection["deal"]["objective"]
        result["deal"]["artifacts"] = []
        result["deal"]["decisionRoom"] = projection["deal"]["decisionRoom"]
        result["deal"]["executionRoom"] = projection["deal"]["executionRoom"]
        result["deal"]["lenses"] = projection["deal"]["lenses"]
        result["deal"]["default_lens_id"] = projection["deal"]["default_lens_id"]
        result["deal"]["active_lens_id"] = projection["deal"]["active_lens_id"]
        result["deal"]["spine_change_proposals"] = projection["deal"]["spine_change_proposals"]
        result["deal"]["participants"] = projection["deal"]["participants"]
        result["fund"] = projection["fund"]
        result["events"] = projection["events"]
        result["actor_directory"] = projection["actor_directory"]
        result["disclosure"] = projection["disclosure"]
        return _apply_decision_intelligence(
            _apply_compiler_reviews(result, case_id)
        )
    except Exception as exc:
        projection["_adapter_error"] = str(exc)
        return _apply_decision_intelligence(
            _apply_compiler_reviews(projection, case_id)
        )


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
    available_cases = _available_case_ids()
    # An explicit URL case is an operator choice.  It may be a newly opened
    # clean case whose deal.md has not been materialized yet; never substitute
    # a different live deal (previously the alphabetical Astrelia fallback).
    if case_id is None and not deal_md.exists():
        # Try to find any deal
        cid = available_cases[0] if available_cases else cid
    if cid not in available_cases:
        available_cases.insert(0, cid)
    profile = _load_profile(cid)
    today = _today()
    state_id = _current_state_id(cid)
    session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"
    return {
        "session_id": session_id,
        "available_cases": available_cases,
        "cases": available_cases,
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
    available_cases = _available_case_ids()
    return {
        "session_id": session_id,
        "available_cases": available_cases,
        "cases": available_cases,
        "context": _make_context(case_id, state_id, today),
        "action_capabilities": _action_capability_manifest(),
        "entity": profile.get("entity", case_id),
        "deal_profile": profile,
    }


@v20.get("/cases/{case_id}/projection")
def projection(
    case_id: str,
    as_of_date: str | None = None,
    lens_id: str | None = None,
) -> dict:
    active_lens_id = _active_fund_lens(case_id)["lens_id"]
    if lens_id and lens_id != active_lens_id:
        raise HTTPException(
            409,
            f"Fund Lens {lens_id} is not active for {case_id}; active lens is {active_lens_id}",
        )
    if as_of_date:
        # The UI refreshes this route after choosing a replay date. Reuse the
        # same causal reconstruction so the rendered projection cannot regain
        # claims or graph state learned after the cutoff.
        try:
            return replay(case_id, as_of_date=as_of_date)["projection"]
        except HTTPException as exc:
            if exc.status_code != 404 or _load_projection_events(case_id):
                raise
            # A brand-new case has no event to replay yet. Returning its empty
            # Current plus Fund Lens gaps keeps Connected bootable without
            # pretending that a hand-authored temporal snapshot exists.
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


@v20.get("/cases/{case_id}/fund-lens")
def get_fund_lens(case_id: str) -> dict:
    active_path = _case_vault_dir(case_id) / "fund_lens.json"
    lens = _active_fund_lens(case_id)
    return {
        "case_id": case_id,
        "active": lens,
        "source": "case_override" if active_path.exists() else "repository_default",
        "artifact_hash": _fund_lens_hash(lens),
        "versions": _fund_lens_versions(case_id),
    }


@v20.put("/cases/{case_id}/fund-lens")
def configure_fund_lens(case_id: str, payload: dict) -> dict:
    return _configure_fund_lens(case_id, payload)


@v20.get("/cases/{case_id}/graph-versions/{version_id:path}")
def get_graph_version(case_id: str, version_id: str) -> dict:
    return _load_graph_version(case_id, version_id)


@v20.get("/cases/{case_id}/re-underwrite")
def reunderwrite(
    case_id: str,
    baseline_state_id: str | None = None,
    current_state_id: str | None = None,
) -> dict:
    return _build_reunderwrite(
        case_id,
        baseline_state_id=baseline_state_id,
        current_state_id=current_state_id,
    )


@v20.get("/cases/{case_id}/sources")
def sources(case_id: str) -> dict:
    raw = _load_claims(case_id)
    srcs = _build_sources_from_claims(raw, case_id)
    inbox_items = [
        item for item in _read_inbox_manifest()
        if item.get("case_id") == case_id
    ]
    known_files = {
        item.get("stored_name")
        for item in _read_inbox_manifest()
    }
    inbox_dir = VAULT / "inbox"
    if inbox_dir.exists():
        for f in sorted(inbox_dir.glob("*")):
            belongs_to_case = f.name.lower().startswith(
                (f"{case_id.lower()}_", f"{case_id.lower()}-")
            )
            if (
                f.is_file()
                and not f.name.startswith(".")
                and f.name not in known_files
                and belongs_to_case
            ):
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
    current_sources = _build_sources_from_claims(_load_claims(case_id), case_id)
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


def _accept_spine_change(case_id: str, proposal: dict) -> dict:
    """Materialize an explicitly approved deal-emergent question and bindings."""
    question = proposal.get("proposed_question") or {}
    question_id = str(question.get("id") or "").strip()
    title = str(question.get("title") or "").strip()
    if not question_id or not title:
        raise HTTPException(422, "Spine proposal does not contain a valid proposed_question")

    question_dir = _case_vault_dir(case_id) / "questions"
    question_path = question_dir / f"{question_id.lower()}.md"
    created = not question_path.exists()
    if created:
        question_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "type": "question", "id": question_id, "deal": case_id,
            "title": title, "question": title, "state": "open", "status": "open",
            "critical": False, "workstream": question.get("workstream", "deal-emergent"),
            "opened": _today(), "written-by": "professional-spine-review",
            "origin": "deal_emergent", "question_version": question.get("question_version", 1),
            "source_proposal_id": proposal.get("proposal_id"),
        }
        question_path.write_text(
            "---\n" + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
            + f"---\n\n# {title}\n",
            encoding="utf-8",
        )

    migration = proposal.get("binding_migration") or {}
    claim_ids = {str(value) for value in migration.get("claim_ids", []) if value}
    evidence_job_id = str(proposal.get("evidence_job_id") or "")
    evidence_path = _proposal_path(evidence_job_id, case_id) if evidence_job_id else None
    if evidence_path and evidence_path.exists():
        evidence = _load_json_safe(evidence_path)
        for claim in evidence.get("claims", []) or []:
            if str(claim.get("claim_id") or claim.get("id")) in claim_ids:
                claim["bears_on"] = sorted(set(claim.get("bears_on", [])) | {question_id})
        _write_json_atomic(evidence_path, evidence)

    claims_path = _pipeline_out_for_case(case_id) / "claims.json"
    admitted = _load_json_safe(claims_path)
    admitted = admitted if isinstance(admitted, list) else []
    migrated = 0
    for claim in admitted:
        if str(claim.get("claim_id") or claim.get("id")) not in claim_ids:
            continue
        before = set(claim.get("bears_on", []))
        claim["bears_on"] = sorted(before | {question_id})
        migrated += int(question_id not in before)
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", str(claim.get("claim_id") or claim.get("id")))
        note_path = _case_vault_dir(case_id) / "claims" / f"c-{case_id}-{safe_id}.md"
        if note_path.exists():
            text = note_path.read_text(encoding="utf-8")
            end = text.find("\n---", 3)
            if end != -1:
                frontmatter = yaml.safe_load(text[3:end]) or {}
                frontmatter["bears-on"] = claim["bears_on"]
                note_path.write_text(
                    "---\n" + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
                    + "---" + text[end + 4:],
                    encoding="utf-8",
                )
    if admitted:
        _write_json_atomic(claims_path, admitted)
        if migrated:
            _build_semantic_current(admitted, case_id)
    _rebuild_index()
    return {"question_id": question_id, "question_created": created, "bindings_migrated": migrated}


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
            structural_effect = kind == "spine" and decision in {"ACCEPTED", "ADMITTED"}
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
                "institutional_effect": (
                    "QUESTION_SPINE_UPDATED" if structural_effect else "REVIEW_RECORDED_ONLY"
                ),
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

    spine_result = None
    if kind == "spine" and review.get("decision") in {"ACCEPTED", "ADMITTED"}:
        spine_result = _accept_spine_change(case_id, proposal)

    updated_projection = _apply_compiler_reviews(_build_projection(case_id), case_id)
    as_of_date = updated_projection.get("deal", {}).get("as_of_date") or _today()
    state_id = updated_projection.get("deal", {}).get("as_of_state_id") or _current_state_id(case_id)
    return {
        "review": review,
        "projection": updated_projection,
        "context": _make_context(case_id, state_id, as_of_date),
        "registry": [],
        "idempotent_replay": replayed,
        "spine_change": spine_result,
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


class UnsupportedUploadFormat(ValueError):
    """Raised when live intake cannot route an uploaded source safely."""


def _extraction_command(
    source_path: Path | None,
    case_id: str,
    job_id: str,
    source_envelope_path: Path | None = None,
) -> tuple[str, list[str]]:
    """Select the extractor at the product boundary without executing it."""
    pipeline_out = _pipeline_out_for_case(case_id)
    if source_path is not None:
        suffix = source_path.suffix.lower()
        if suffix in (".xlsx", ".xlsm", ".md", ".txt", ".pdf"):
            run_dir = pipeline_out / "runs" / job_id
            command = [
                sys.executable,
                str(ROOT / "tools" / "extract_v2.py"),
                "--source",
                str(source_path),
                "--deal",
                case_id,
                "--output",
                str(run_dir),
            ]
            if source_envelope_path is not None:
                command.extend(["--source-envelope", str(source_envelope_path)])
            return "SINGLE_V2", command
        if suffix == ".xls":
            raise UnsupportedUploadFormat(
                "Legacy .xls is not supported; convert the workbook to .xlsx before upload."
            )
    return "K-IC", [
        sys.executable,
        str(ROOT / "tools" / "extract.py"),
        "--deal",
        case_id,
    ]


@v20.post("/cases/{case_id}/ingest")
async def ingest(case_id: str, request: Request, background_tasks: BackgroundTasks) -> dict:
    inbox_dir = VAULT / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    filename = ""
    original_filename = ""
    stored_path: Path | None = None
    purpose = ""
    declared_metadata: dict[str, Any] = {}
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        file_field = form.get("file")
        purpose = str(form.get("purpose", ""))
        raw_metadata = form.get("source_metadata", "")
        if raw_metadata:
            try:
                declared_metadata = json.loads(str(raw_metadata))
            except json.JSONDecodeError as exc:
                raise HTTPException(400, f"source_metadata must be JSON: {exc.msg}") from exc
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
        declared_metadata = payload.get("source_metadata") or {}
        if not isinstance(declared_metadata, dict):
            raise HTTPException(400, "source_metadata must be a JSON object")
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
    source_path_for_envelope = stored_path or ((inbox_dir / filename) if filename else None)
    source_envelope: dict[str, Any] | None = None
    if source_path_for_envelope and source_path_for_envelope.exists():
        source_envelope = build_source_envelope(
            source_path_for_envelope,
            case_id,
            _now_iso(),
            original_filename=original_filename or filename,
            declared_metadata=declared_metadata,
        )
    _store_job(job_id, {
        "status": "PENDING", "job_id": job_id,
        "artifact": filename, "case_id": case_id, "purpose": purpose,
        "label": filename or "extraction run",
        "stage": "Queued", "progress": 0,
        "created_at": _now_iso(),
        "source_envelope": source_envelope,
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
                "source_envelope": source_envelope,
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
        envelope_path: Path | None = None
        if source_envelope:
            envelope_path = _pipeline_out_for_case(case_id) / "runs" / job_id / "source-envelope.json"
            _write_json_atomic(envelope_path, source_envelope)
        manifest_label, cmd = _extraction_command(source_path, case_id, job_id, envelope_path)

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
                pipeline_out = _pipeline_out_for_case(case_id)
                output_dir = (pipeline_out / "runs" / job_id) if manifest_label in {"SINGLE", "SINGLE_V2"} else (pipeline_out / manifest_label)
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
                            workbook_formula_graphs = _load_json_safe(
                                e3_out.parent / "workbook_formula_graphs.json"
                            )
                        else:
                            e3 = {}
                            raw = json.loads(v1_out.read_text())
                            workbook_formula_graphs = {}
                        fund_lens = _active_fund_lens(case_id)
                        _ensure_question_registry(case_id, fund_lens)
                        new_claims = _derive_bears_on(
                            _normalise_v1_claims(raw, filename), e3, fund_lens
                        )
                        excel_formula_graph = None
                        if manifest_label == "SINGLE_V2" and source_path is not None:
                            try:
                                from tools.excel_formula_graph import compile_workbook
                                excel_formula_graph = compile_workbook(source_path)
                            except Exception as formula_exc:
                                # Extraction can still expose claim evidence, but
                                # the missing model capture must be visible and
                                # must never degrade into an invented value.
                                excel_formula_graph = {
                                    "schema_version": "excel-formula-graph/1.0",
                                    "status": "HUMAN_STOP",
                                    "source": {
                                        "source_id": filename,
                                        "workbook": filename,
                                        "digest": "sha256:" + hashlib.sha256(
                                            source_path.read_bytes()
                                        ).hexdigest(),
                                    },
                                    "nodes": [],
                                    "edges": [],
                                    "formulas": [],
                                    "coverage_limits": [{
                                        "reason_code": "WORKBOOK_CAPTURE_FAILED",
                                        "effect": str(formula_exc),
                                        "resolution": "HUMAN_STOP",
                                        "scope_ids": [],
                                    }],
                                }
                                logger.warning(
                                    "JOB %s Excel formula capture stopped: %s",
                                    job_id,
                                    formula_exc,
                                )
                        question_proposals = _derive_question_proposals(new_claims, case_id)
                        proposal = _write_evidence_proposal(
                            job_id,
                            case_id,
                            filename,
                            new_claims,
                            question_proposals,
                            fund_lens,
                            excel_formula_graph,
                            workbook_formula_graphs,
                            source_envelope,
                        )
                        proposal_display_path = (
                            str(proposal.relative_to(ROOT))
                            if proposal.is_relative_to(ROOT)
                            else str(proposal)
                        )
                        _store_job(job_id, proposal_id=proposal.stem,
                                   proposal_path=proposal_display_path,
                                   proposed_claim_count=len(new_claims),
                                   formula_node_count=len((excel_formula_graph or {}).get("formulas", [])),
                                   admission_status="PENDING_REVIEW")
                        _update_inbox_record(job_id, proposal_id=proposal.stem,
                                             proposal_path=proposal_display_path,
                                             proposed_claim_count=len(new_claims),
                                             admission_status="PENDING_REVIEW")
                        logger.info(
                            "JOB %s produced %d claim proposals and %d formula nodes",
                            job_id,
                            len(new_claims),
                            len((excel_formula_graph or {}).get("formulas", [])),
                        )
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


class _InlineJSONRequest:
    """Minimal request surface used to reuse the governed single-file intake."""

    def __init__(self, payload: dict[str, Any]):
        self.headers = {"content-type": "application/json"}
        self._payload = payload

    async def json(self) -> dict[str, Any]:
        return self._payload


def _job_snapshot(job_id: str) -> dict[str, Any]:
    job = _jobs.get(job_id)
    if job:
        return dict(job)
    return dict(next(
        (item for item in _read_inbox_manifest() if item.get("job_id") == job_id),
        {"job_id": job_id, "status": "UNKNOWN"},
    ))


def _batch_view(batch_id: str) -> dict[str, Any]:
    batch = _batches.get(batch_id)
    if not batch:
        raise HTTPException(404, f"Ingest batch not found: {batch_id}")
    jobs = [_job_snapshot(job_id) for job_id in batch.get("job_ids", [])]
    statuses = [str(job.get("status", "UNKNOWN")).upper() for job in jobs]
    terminal = {"COMPLETE", "FAILED", "ERROR", "CANCELLED"}
    error_states = {"FAILED", "ERROR", "CANCELLED"}
    if statuses and all(status in terminal for status in statuses):
        if all(status in error_states for status in statuses):
            status = "ERROR"
        elif any(status in error_states for status in statuses):
            status = "PARTIAL_ERROR"
        else:
            status = "COMPLETE"
    elif any(status == "RUNNING" for status in statuses):
        status = "RUNNING"
    else:
        status = "QUEUED"
    counts = {
        "total": len(jobs),
        "queued": sum(status in {"PENDING", "QUEUED", "UNKNOWN"} for status in statuses),
        "running": statuses.count("RUNNING"),
        "complete": statuses.count("COMPLETE"),
        "error": sum(status in error_states for status in statuses),
        "proposal_ready": sum(job.get("admission_status") == "PENDING_REVIEW" for job in jobs),
        "admitted": sum(job.get("admission_status") == "ADMITTED" for job in jobs),
        "rejected": sum(job.get("admission_status") == "REJECTED" for job in jobs),
    }
    return {**batch, "status": status, "counts": counts, "jobs": jobs}


async def _run_ingest_batch(
    batch_id: str,
    children: list[BackgroundTasks],
    concurrency: int,
) -> None:
    """Run independent per-file jobs with a bounded concurrency ceiling."""
    semaphore = asyncio.Semaphore(max(1, min(8, concurrency)))

    async def run_child(child: BackgroundTasks) -> None:
        async with semaphore:
            for task in child.tasks:
                await task()

    _store_batch(batch_id, status="RUNNING")
    await asyncio.gather(*(run_child(child) for child in children))
    _store_batch(batch_id, status=_batch_view(batch_id)["status"])


@v20.post("/cases/{case_id}/ingest/batches")
async def bulk_ingest(case_id: str, request: Request, background_tasks: BackgroundTasks) -> dict:
    """Queue multiple sources as one durable, idempotent intake batch."""
    content_type = request.headers.get("content-type", "")
    purpose = ""
    concurrency = 3
    idempotency_key = request.headers.get("idempotency-key", "")
    payloads: list[dict[str, Any]] = []

    if "multipart/form-data" in content_type:
        form = await request.form()
        purpose = str(form.get("purpose", ""))
        idempotency_key = str(form.get("idempotency_key", idempotency_key))
        concurrency = int(form.get("concurrency", 3) or 3)
        uploads = list(form.getlist("files") or form.getlist("file"))
        for upload in uploads:
            if not hasattr(upload, "read"):
                continue
            filename = Path(getattr(upload, "filename", "upload") or "upload").name
            payloads.append({
                "file_name": filename,
                "content_b64": base64.b64encode(await upload.read()).decode("ascii"),
                "purpose": purpose,
            })
    else:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        purpose = str(payload.get("purpose", ""))
        idempotency_key = str(payload.get("idempotency_key", idempotency_key))
        concurrency = int(payload.get("concurrency", 3) or 3)
        for item in payload.get("files", []) or []:
            if isinstance(item, dict):
                payloads.append({**item, "purpose": item.get("purpose", purpose)})

    if not payloads:
        raise HTTPException(400, "At least one file is required for bulk intake")
    if len(payloads) > 50:
        raise HTTPException(413, "A bulk intake may contain at most 50 files")
    concurrency = max(1, min(8, concurrency))
    if not idempotency_key:
        idempotency_key = f"BATCH-{uuid.uuid4().hex}"
    for existing in _batches.values():
        if (
            existing.get("case_id") == case_id
            and existing.get("idempotency_key") == idempotency_key
        ):
            return {"batch": _batch_view(existing["batch_id"]), "idempotent_replay": True}

    batch_id = f"batch-{uuid.uuid4().hex[:12]}"
    _store_batch(batch_id, {
        "batch_id": batch_id,
        "case_id": case_id,
        "idempotency_key": idempotency_key,
        "purpose": purpose,
        "concurrency": concurrency,
        "status": "QUEUED",
        "job_ids": [],
        "retry_history": [],
        "created_at": _now_iso(),
    })
    children: list[BackgroundTasks] = []
    job_ids: list[str] = []
    for index, item in enumerate(payloads):
        filename = Path(str(item.get("file_name") or item.get("name") or "")).name
        encoded = item.get("content_b64")
        if not filename or not encoded:
            raise HTTPException(400, f"Batch file {index + 1} requires file_name and content_b64")
        child = BackgroundTasks()
        queued = await ingest(
            case_id,
            _InlineJSONRequest({
                "file_name": filename,
                "content_b64": encoded,
                "purpose": item.get("purpose", purpose),
            }),
            child,
        )
        job_id = queued["job_id"]
        _store_job(job_id, batch_id=batch_id, batch_index=index, original_filename=filename)
        _update_inbox_record(job_id, batch_id=batch_id, batch_index=index)
        job_ids.append(job_id)
        children.append(child)
    _store_batch(batch_id, job_ids=job_ids)
    background_tasks.add_task(_run_ingest_batch, batch_id, children, concurrency)
    return {"batch": _batch_view(batch_id), "batch_id": batch_id}


@v20.get("/cases/{case_id}/ingest/batches/{batch_id}")
def get_ingest_batch(case_id: str, batch_id: str) -> dict:
    batch = _batch_view(batch_id)
    if batch.get("case_id") != case_id:
        raise HTTPException(404, f"Ingest batch not found for case: {batch_id}")
    return {"batch": batch, **batch}


@v20.post("/cases/{case_id}/ingest/batches/{batch_id}/jobs/{job_id}/retry")
async def retry_batch_job(
    case_id: str,
    batch_id: str,
    job_id: str,
    background_tasks: BackgroundTasks,
    payload: dict | None = None,
) -> dict:
    batch = _batches.get(batch_id)
    if not batch or batch.get("case_id") != case_id or job_id not in batch.get("job_ids", []):
        raise HTTPException(404, "Batch job not found")
    failed = _job_snapshot(job_id)
    if str(failed.get("status", "")).upper() not in {"FAILED", "ERROR", "CANCELLED"}:
        raise HTTPException(409, "Only failed batch files can be retried")
    artifact = str(failed.get("artifact") or "")
    if not artifact or not (VAULT / "inbox" / artifact).exists():
        raise HTTPException(409, "The durable source file is unavailable for retry")

    child = BackgroundTasks()
    queued = await ingest(
        case_id,
        _InlineJSONRequest({
            "file_name": artifact,
            "purpose": (payload or {}).get("purpose") or failed.get("purpose", batch.get("purpose", "")),
        }),
        child,
    )
    new_job_id = queued["job_id"]
    index = int(failed.get("batch_index", batch["job_ids"].index(job_id)))
    job_ids = list(batch["job_ids"])
    job_ids[index] = new_job_id
    history = list(batch.get("retry_history", []))
    history.append({"job_id": job_id, "retry_job_id": new_job_id, "retried_at": _now_iso()})
    _store_job(
        new_job_id,
        batch_id=batch_id,
        batch_index=index,
        retry_of=job_id,
        original_filename=failed.get("original_filename") or failed.get("artifact"),
    )
    _update_inbox_record(new_job_id, batch_id=batch_id, batch_index=index, retry_of=job_id)
    _store_batch(batch_id, job_ids=job_ids, retry_history=history, status="QUEUED")
    background_tasks.add_task(_run_ingest_batch, batch_id, [child], 1)
    return {"batch": _batch_view(batch_id), "job_id": new_job_id, "retry_of": job_id}


@v20.get("/cases/{case_id}/ingest/{job_id}/proposal")
def get_evidence_proposal(case_id: str, job_id: str) -> dict:
    """Return the editable extraction boundary without changing Current."""
    proposal_path = _proposal_path(job_id, case_id)
    if not proposal_path.exists():
        raise HTTPException(404, "No evidence proposal exists for this ingestion job")
    proposal = _load_json_safe(proposal_path)
    if proposal.get("case_id") != case_id:
        raise HTTPException(409, "Evidence proposal belongs to another case")
    existing = _load_claims(case_id)
    preview_claims, _ = _merge_claim_corpus(existing, proposal.get("claims", []))
    preview_models = _load_excel_model_graphs(case_id)
    if isinstance(proposal.get("excel_formula_graph"), dict):
        preview_models.append(proposal["excel_formula_graph"])
    preview = _semantic_graph_from_claims(
        preview_claims,
        case_id,
        excel_models=preview_models,
    )
    return {
        "proposal": proposal,
        "workbook_formula_graphs": _proposal_workbook_formula_graphs(proposal_path, proposal),
        "questions": _build_question_spine(_load_questions(case_id), proposal.get("claims", [])),
        "semantic_preview": {
            "nodes": len(preview.get("nodes", [])),
            "edges": len(preview.get("edges", [])),
            "formula_nodes": len(preview.get("excel_formulas", [])),
            "human_stops": len(preview.get("coverage_limits", [])),
            "current_mutated": False,
        },
    }


def _validated_reviewed_claims(case_id: str, proposal: dict, payload: dict) -> list[dict]:
    """Apply editable fields while preserving proposal identity and provenance."""
    supplied = payload.get("claims")
    if not isinstance(supplied, list):
        return [dict(claim) for claim in proposal.get("claims", []) if isinstance(claim, dict)]

    originals = {
        str(item.get("claim_id") or item.get("id")): item
        for item in proposal.get("claims", []) if isinstance(item, dict)
    }
    registry_ids = {str(item.get("id")) for item in _load_questions(case_id)}
    reviewed = []
    seen: set[str] = set()
    editable = {
        "statement", "value", "unit", "period", "perimeter", "locator",
        "epistemic", "epistemic_class", "direction", "topic", "metric",
        "definition_id", "author", "bears_on",
    }
    for raw in supplied:
        if not isinstance(raw, dict):
            raise HTTPException(422, "Reviewed claims must be objects")
        claim_id = str(raw.get("claim_id") or raw.get("id") or "")
        original = originals.get(claim_id)
        if original is None or claim_id in seen:
            raise HTTPException(422, f"Reviewed claim is not unique in this proposal: {claim_id}")
        seen.add(claim_id)
        claim = dict(original)
        claim.update({key: raw[key] for key in editable if key in raw})
        bears_on = claim.get("bears_on", [])
        if not isinstance(bears_on, list):
            raise HTTPException(422, f"bears_on must be a list for claim {claim_id}")
        unknown = sorted({str(qid) for qid in bears_on if str(qid) not in registry_ids})
        if unknown:
            raise HTTPException(422, f"Unknown question binding(s) for {claim_id}: {', '.join(unknown)}")
        claim["bears_on"] = sorted({str(qid) for qid in bears_on})
        claim["claim_id"] = claim_id
        claim["source_id"] = original.get("source_id") or proposal.get("source_id")
        claim["source_ids"] = original.get("source_ids") or [claim["source_id"]]
        reviewed.append(claim)
    return reviewed


@v20.post("/cases/{case_id}/ingest/{job_id}/admit")
async def admit_evidence(case_id: str, job_id: str, payload: dict = {}) -> dict:
    """Apply the explicit professional decision at the evidence boundary.

    Extraction is fallible.  This endpoint is the only route that promotes an
    extracted claim to the admitted corpus.  It rebuilds the semantic Current,
    compiles the live runtime inputs and emits an executable event made only
    from the newly admitted extractor claims.  Candidate creation remains a
    separate explicit action at ``/events/{event_id}/admit``.
    """
    pipeline_out = _pipeline_out_for_case(case_id)
    proposal_file = _proposal_path(job_id, case_id)
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
    reviewed_claims = _validated_reviewed_claims(case_id, proposal, payload)
    _ensure_question_registry(case_id)
    existing_path = pipeline_out / "claims.json"
    existing = json.loads(existing_path.read_text()) if existing_path.exists() else []
    merged, added = _merge_claim_corpus(existing, reviewed_claims)
    if added and (pipeline_out / "candidate_state.json").exists():
        raise HTTPException(
            409,
            "An unsettled Candidate already exists; settle it before admitting more evidence.",
        )

    compiled = None
    runtime_event = None
    event_path = None
    runtime_blocker = None
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
                (pipeline_out / "runtime_state.json").unlink(missing_ok=True)
            event_path = _promote_live_runtime_bundle(
                case_id,
                compiled,
                baseline_graph,
                runtime_event,
            )
        except (DynamicsBundleError, ValueError, KeyError, OSError) as exc:
            # A new case may have a valid semantic graph before its archetype
            # runtime template exists. Admission must not lose reviewed source
            # evidence merely because dynamics has no governed mapping yet.
            if isinstance(exc, DynamicsBundleError) and "execution_graph_v7.json" in str(exc):
                logger.info("runtime mapping pending for evidence job %s: %s", job_id, exc)
                runtime_blocker = {
                    "code": "RUNTIME_MAPPING_REQUIRED",
                    "reason": str(exc),
                    "required_action": "Configure an archetype runtime template and case execution mapping before dynamics.",
                }
            else:
                logger.exception("runtime compilation failed for evidence job %s", job_id)
                raise HTTPException(422, f"Admitted evidence could not be compiled: {exc}") from exc

    admitted_excel_model = _admit_excel_formula_graph(
        case_id,
        proposal,
        str(payload.get("actor_id", "professional-review")),
    )
    _write_json_atomic(existing_path, merged)
    persisted = _persist_claims_to_vault(case_id, added, proposal.get("source_id", ""))
    promoted_formula_graphs = _promote_workbook_formula_graphs(case_id, proposal_file, proposal)
    graph = _build_semantic_current(merged, case_id)
    proposal.update({"status": "ADMITTED", "reviewed_at": _now_iso(),
                     "reviewed_by": payload.get("actor_id", "professional-review"),
                     "review_note": payload.get("note", ""),
                     "admitted_claim_count": len(added),
                     "admitted_formula_count": len((admitted_excel_model or {}).get("formulas", [])),
                     "runtime_event_id": runtime_event.get("event_id") if runtime_event else None,
                     "runtime_event_path": str(event_path) if event_path else None})
    _write_json_atomic(proposal_file, proposal)
    _update_inbox_record(job_id, admission_status="ADMITTED", stage="Runtime event ready",
                         admitted_claim_count=len(added),
                         runtime_event_id=runtime_event.get("event_id") if runtime_event else None,
                         runtime_blocker=runtime_blocker,
        message=(
             f"Admitted {len(added)} new claims and compiled the executable runtime event."
                             if runtime_event else ("Evidence admitted into semantic Current; runtime mapping is required before dynamics."
                             if runtime_blocker else "Evidence was already represented; no new runtime event was required.")
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
            "semantic_graph": {
                "nodes": len(graph.get("nodes", [])),
                "edges": len(graph.get("edges", [])),
                "formula_nodes": len(graph.get("excel_formulas", [])),
                "human_stops": len(graph.get("coverage_limits", [])),
            },
            "workbook_formula_graphs": [
                {"source_id": item.get("source_id"), "source_filename": item.get("source_filename"),
                 **(item.get("summary") or {})}
             for item in promoted_formula_graphs.get("workbooks", []) if isinstance(item, dict)
            ],
            "runtime_event": ({
                "event_id": runtime_event["event_id"],
                "path": str(event_path),
                "mutation_count": len(runtime_event["mutations"]),
                "mapped_claim_count": len(runtime_event["mapped_claim_ids"]),
                "unmapped_claim_count": len(runtime_event["unmapped_claim_ids"]),
            } if runtime_event else None),
            "human_stops": [runtime_blocker] if runtime_blocker else [],
            "message": ("Evidence admitted into semantic Current; dynamics is blocked until a runtime mapping is configured."
                        if runtime_blocker else "Evidence admitted into semantic Current and compiled for dynamics.")}


@v20.post("/cases/{case_id}/admit-all")
async def admit_all_pending(
    case_id: str,
    background_tasks: BackgroundTasks,
    payload: dict = {},
) -> dict:
    """Admit every PENDING_REVIEW proposal for a case, one at a time.

    Each admission runs through dynamics and, when it compiles into a
    Candidate with no Human Stops, is settled immediately before the next
    proposal is admitted -- the same sequence a reviewer would run by hand
    through /admit-evidence, /events/{id}/admit and /runs/{id}/settle. Stops
    on the first proposal that can't proceed rather than silently skipping it,
    so a batch run never hides a real blocker.
    """
    actor_id = str(payload.get("actor_id") or "batch-admit")
    proposals_dir = _pipeline_out_for_case(case_id) / "proposals"
    pending_job_ids = []
    if proposals_dir.exists():
        for path in sorted(proposals_dir.glob("evidence-*.json")):
            data = _load_json_safe(path)
            if (
                isinstance(data, dict)
                and data.get("status") == "PENDING_REVIEW"
                and data.get("case_id") == case_id
                and data.get("job_id")
            ):
                pending_job_ids.append((str(data.get("created_at") or ""), str(data["job_id"])))
    pending_job_ids.sort()

    processed: list[dict[str, Any]] = []
    for _created_at, job_id in pending_job_ids:
        entry: dict[str, Any] = {"job_id": job_id}
        try:
            admitted = await admit_evidence(case_id, job_id, {"decision": "ADMIT", "actor_id": actor_id})
        except HTTPException as exc:
            entry["stage"] = "admit_evidence"
            entry["error"] = exc.detail
            processed.append(entry)
            break
        entry["source_id"] = admitted.get("proposal_id")
        entry["new_claim_count"] = admitted.get("new_claim_count")
        entry["human_stops"] = admitted.get("human_stops") or []
        runtime_event = admitted.get("runtime_event")
        if not runtime_event or not runtime_event.get("event_id"):
            entry["outcome"] = "ADMITTED_NO_DYNAMICS"
            processed.append(entry)
            continue
        try:
            transitioned = await admit(case_id, runtime_event["event_id"], background_tasks, {"actor_id": actor_id})
        except HTTPException as exc:
            entry["stage"] = "transition"
            entry["error"] = exc.detail
            processed.append(entry)
            break
        run_id = transitioned["run"]["run_id"]
        transition_human_stops = transitioned["transition"].get("human_stops") or []
        entry["run_id"] = run_id
        if transition_human_stops:
            entry["outcome"] = "CANDIDATE_AWAITING_HUMAN_STOP"
            entry["human_stops"] = transition_human_stops
            processed.append(entry)
            break
        try:
            settled = await settle_run(run_id, background_tasks, {"actor_id": actor_id})
        except HTTPException as exc:
            entry["stage"] = "settle"
            entry["error"] = exc.detail
            processed.append(entry)
            break
        entry["outcome"] = "SETTLED"
        entry["current_state_id"] = settled.get("current_state_id")
        processed.append(entry)

    settled_count = sum(1 for item in processed if item.get("outcome") == "SETTLED")
    return {
        "requested": len(pending_job_ids),
        "processed": processed,
        "settled_count": settled_count,
        "message": (
            f"Settled {settled_count} of {len(pending_job_ids)} pending source(s)."
            if not processed or "error" not in processed[-1]
            else f"Stopped after {len(processed)} source(s): {processed[-1].get('error')}"
        ),
    }


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
    pipeline_out = _pipeline_out_for_case(case_id)
    try:
        event_batch = load_event_batch(pipeline_out, event_id, payload)
        dynamics_result = run_bundle_transition(
            pipeline_out,
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

    human_stops = [
        _frontend_human_stop(item)
        for item in transition_output.get("human_stops", [])
        if isinstance(item, dict)
    ]
    blocked = [
        _frontend_blocked_component(item)
        for item in transition_output.get("blocked_components", [])
        if isinstance(item, dict)
    ]
    run_id = transition_output.get("run_id", f"RUN-{uuid.uuid4().hex[:8].upper()}")
    cand_state_id = candidate_state.get(
        "state_id", f"CAND-{uuid.uuid4().hex[:8].upper()}"
    )
    prior_state_id = transition_output.get("prior_state_id", "STATE-PRIOR")
    artifact_change_sets = _build_transition_change_sets(
        transition_output,
        candidate_state_id=cand_state_id,
    )
    event_record = event_batch[0] if event_batch else {}
    current_graph = _load_json_safe(pipeline_out / "current_graph.json")
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
        "prior_state_id": prior_state_id,
        "prior_graph_hash": _graph_content_hash(current_graph),
        "candidate_state_hash": _graph_content_hash(candidate_state),
        "candidate_graph_hash": candidate_state.get("candidate_graph_hash"),
        "artifact_change_sets": artifact_change_sets,
        "current_graph_version": current_graph_version,
        "candidate_graph_version": candidate_graph_version,
        "bundle_dir": str(pipeline_out),
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
        "artifact_change_sets": artifact_change_sets,
    }

    return {
        "run": {
            "run_id": run_id,
            "status": "CANDIDATE_READY",
            "candidate_state_id": cand_state_id,
            "prior_state_id": prior_state_id,
        },
        "transition": transition,
        "candidate_graph": candidate_graph,
        "current_graph_version": current_graph_version,
        "candidate_graph_version": candidate_graph_version,
        "context": {
            **_make_context(case_id, prior_state_id, _today()),
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
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if not idempotency_key:
        raise HTTPException(
            409,
            "Settlement requires a non-empty idempotency_key for durable recovery",
        )
    recover_committed = False
    retry_settling = False
    with _registry_lock:
        run = _runs.get(run_id)
        if not run:
            raise HTTPException(
                404,
                f"Run not found: {run_id}. Call /admit first to create a run.",
            )
        if run.get("status") == "SETTLED" or run.get("settled_state_id"):
            if (
                idempotency_key
                and idempotency_key == run.get("settlement_idempotency_key")
                and run.get("settlement_response")
            ):
                response = copy.deepcopy(run["settlement_response"])
                today = _today()
                context = _make_context(
                    run["case_id"], response["current_state_id"], today
                )
                response.update(
                    projection={
                        "projection": _build_projection(run["case_id"]),
                        "context": context,
                        "registry": [],
                    },
                    context=context,
                    registry=[],
                )
                return response
            if (
                idempotency_key
                and idempotency_key == run.get("settlement_idempotency_key")
                and run.get("settlement_state_id")
            ):
                recover_committed = True
            else:
                raise HTTPException(409, f"Run {run_id} is already settled")
        if run.get("status") == "SETTLING":
            if not idempotency_key or idempotency_key != run.get(
                "settlement_idempotency_key"
            ):
                raise HTTPException(409, f"Run {run_id} settlement is already in progress")
            runtime_state = _load_json_safe(
                Path(run.get("bundle_dir", _pipeline_out_for_case(run["case_id"])))
                / "runtime_state.json"
            )
            settlement_bundle = Path(
                run.get("bundle_dir", _pipeline_out_for_case(run["case_id"]))
            )
            if (settlement_bundle / "settlement_journal.json").exists():
                retry_settling = True
            elif runtime_state.get("state_id") == run.get("settlement_state_id"):
                recover_committed = True
            else:
                # A caught pre-commit failure may leave the durable run marker
                # behind.  Only return it to PREPARED when Current is still the
                # exact Candidate base; every other state needs investigation.
                current_graph = _load_json_safe(
                    Path(run.get("bundle_dir", _pipeline_out_for_case(run["case_id"])))
                    / "current_graph.json"
                )
                if (
                    runtime_state.get("state_id") == run.get("prior_state_id")
                    and _graph_content_hash(current_graph) == run.get("prior_graph_hash")
                ):
                    run["status"] = "PREPARED"
                    _store_run(run_id, run)
                else:
                    raise HTTPException(
                        409,
                        "Settlement recovery found an indeterminate Current state",
                    )
        if (
            run.get("status") != "PREPARED"
            and not recover_committed
            and not retry_settling
        ):
            raise HTTPException(409, "Run must be PREPARED before settlement")

    case_id = run["case_id"]
    event_id = run["event_id"]
    transition_output = run.get("transition_output", {})
    supplied_candidate_id = str(payload.get("candidate_state_id") or "")
    if supplied_candidate_id != str(run.get("candidate_state_id") or ""):
        raise HTTPException(409, "Settlement Candidate does not match the PREPARED run")

    if "selected_change_ids" not in payload:
        raise HTTPException(409, "Settlement must repeat the explicit PREPARED selection")
    selected_change_ids = _normalise_selected_change_ids(payload["selected_change_ids"])
    prepared_ids = list(run.get("selected_change_ids", []))
    if sorted(selected_change_ids) != sorted(prepared_ids):
        raise HTTPException(409, "Settlement scope does not match the PREPARED selection")
    available = _change_set_index(run)
    unknown = sorted(set(selected_change_ids) - set(available))
    if unknown:
        raise HTTPException(
            409,
            "Settlement contains an unknown prepared change id: " + ", ".join(unknown),
        )
    expected_selection_hash = _graph_content_hash(
        {
            "run_id": run_id,
            "candidate_state_id": run.get("candidate_state_id"),
            "selected_change_ids": sorted(selected_change_ids),
        }
    )
    if run.get("prepared_selection_hash") != expected_selection_hash:
        raise HTTPException(409, "Prepared selection hash no longer matches the run")

    partial_status = transition_output.get("partial_settlement_status", {})
    candidate_status = str(partial_status.get("candidate") or "NONE")
    blocked_components = [
        _frontend_blocked_component(item)
        for item in transition_output.get("blocked_components", [])
        if isinstance(item, dict)
    ]
    unsettled_component_ids = sorted(
        {
            str(item)
            for item in partial_status.get("unsettled_component_ids", [])
            if item
        }
        | {
            str(item.get("component_id"))
            for item in transition_output.get("ordered_transitions", [])
            if isinstance(item, dict)
            and item.get("component_id")
            and item.get("result") != "SETTLED"
        }
    )
    if candidate_status == "NONE":
        raise HTTPException(409, "Candidate has no settleable state delta")
    partial = bool(
        candidate_status != "FULL"
        or blocked_components
        or unsettled_component_ids
        or any(bool(available[item].get("partial")) for item in selected_change_ids)
    )
    if partial and payload.get("allow_partial_settlement") is not True:
        raise HTTPException(
            409,
            "Candidate contains partial or blocked scope; explicit partial settlement is required",
        )

    selected_object_ids = _selected_object_ids(run, selected_change_ids)
    if not selected_object_ids:
        raise HTTPException(409, "Prepared change set has no settleable object scope")

    raw_record_ids = payload.get("authority_record_ids", [])
    if not isinstance(raw_record_ids, list):
        raise HTTPException(400, "authority_record_ids must be an array")
    supplied_record_ids = [str(item) for item in raw_record_ids]
    if len(supplied_record_ids) != len(set(supplied_record_ids)):
        raise HTTPException(409, "Duplicate authority_record_id in settlement")
    recorded = {
        str(item["authority_record_id"]): item
        for item in run.get("authority_records", [])
        if isinstance(item, dict) and item.get("authority_record_id")
    }
    unknown_records = sorted(set(supplied_record_ids) - set(recorded))
    if unknown_records:
        raise HTTPException(409, "Settlement contains an unknown authority record")
    scoped_records = [recorded[record_id] for record_id in supplied_record_ids]
    for record in scoped_records:
        if (
            record.get("run_id") != run_id
            or record.get("candidate_state_id") != run.get("candidate_state_id")
            or record.get("status") != "ATTESTED"
            or record.get("artifact_hash") != transition_output.get("replay_hash")
            or record.get("prepared_selection_hash") != run.get("prepared_selection_hash")
        ):
            raise HTTPException(409, "Authority record is not scoped to this prepared Candidate")
        if record.get("effect_type") == "DEFER":
            raise HTTPException(409, "A DEFER authority record cannot settle Candidate scope")

    all_stop_ids = {
        str(item.get("stop_id"))
        for item in transition_output.get("human_stops", [])
        if isinstance(item, dict) and item.get("stop_id")
    }
    required_stops = _required_human_stop_ids(
        run,
        selected_change_ids,
        selected_object_ids,
    )
    if "human_stop_ids" in payload:
        supplied_stop_ids = {str(item) for item in payload.get("human_stop_ids", [])}
        if supplied_stop_ids != required_stops:
            raise HTTPException(409, "Settlement Human Stop scope does not match the Candidate")
    covered_stops = {
        str(record.get("human_stop_id")) for record in scoped_records
    }
    if not required_stops.issubset(covered_stops):
        missing = sorted(required_stops - covered_stops)
        raise HTTPException(
            409,
            "Candidate requires recorded human approval before settlement: "
            + ", ".join(missing),
        )

    raw_package_ids = payload.get("execution_package_ids", [])
    if not isinstance(raw_package_ids, list):
        raise HTTPException(400, "execution_package_ids must be an array")
    package_ids = [str(item) for item in raw_package_ids]
    _validate_execution_package_scope(run, scoped_records, package_ids)

    bundle_dir = Path(run.get("bundle_dir", _pipeline_out_for_case(case_id)))
    current_graph = _load_json_safe(bundle_dir / "current_graph.json")
    if not current_graph:
        raise HTTPException(409, "Persisted Current graph is missing")
    candidate_graph = run.get("candidate_graph")
    candidate_state = run.get("candidate_state")
    if not isinstance(candidate_graph, dict) or not isinstance(candidate_state, dict):
        raise HTTPException(409, "Prepared Candidate artifacts are missing")
    settlement_graph = _bounded_settlement_graph(
        current_graph,
        candidate_graph,
        selected_object_ids,
    )

    prior_runtime = _load_json_safe(bundle_dir / "runtime_state.json")
    settlement_runtime_flags = copy.deepcopy(
        dict(prior_runtime.get("runtime_flags", {}))
    )
    candidate_runtime_flags = candidate_state.get("runtime_flags", {})
    for object_id in selected_object_ids:
        if object_id in candidate_runtime_flags:
            settlement_runtime_flags[object_id] = copy.deepcopy(
                candidate_runtime_flags[object_id]
            )

    pending_settlement = None
    if partial:
        pending_settlement = {
            "status": "OPEN",
            "source_run_id": run_id,
            "candidate_state_id": run["candidate_state_id"],
            "candidate_state_hash": run.get("candidate_state_hash")
            or _graph_content_hash(candidate_state),
            "candidate_graph_hash": run.get("candidate_graph_hash")
            or _graph_content_hash(candidate_graph),
            "candidate_graph_version_id": (
                run.get("candidate_graph_version") or {}
            ).get("version_id"),
            "settled_change_set_ids": list(selected_change_ids),
            "settled_object_ids": sorted(selected_object_ids),
            "unsettled_component_ids": unsettled_component_ids,
            "unresolved_human_stop_ids": sorted(all_stop_ids - required_stops),
            "blocked_components": copy.deepcopy(blocked_components),
            "coverage_limits": copy.deepcopy(
                transition_output.get("coverage_limits", [])
            ),
            "known_at": _now_iso(),
        }

    settled_started = str(run.get("settlement_started_at") or "")
    if settled_started:
        try:
            settled_at = dt.datetime.fromisoformat(
                settled_started.replace("Z", "+00:00")
            )
        except ValueError:
            settled_at = dt.datetime.now(dt.timezone.utc)
    else:
        settled_at = dt.datetime.now(dt.timezone.utc)
    ts = settled_at.strftime("%Y%m%dT%H%M%S%fZ")
    settled_known_at = settled_at.isoformat().replace("+00:00", "Z")
    today = _today()
    new_state_id = str(
        run.get("settlement_state_id") or f"STATE-{case_id.upper()}-{ts}"
    )

    if recover_committed:
        settled_state = _load_json_safe(bundle_dir / "runtime_state.json")
    else:
        if not retry_settling:
            with _registry_lock:
                if run.get("status") != "PREPARED":
                    raise HTTPException(409, "Run settlement state changed concurrently")
                run["status"] = "SETTLING"
                run["settlement_state_id"] = new_state_id
                run["settlement_idempotency_key"] = idempotency_key
                run["settlement_started_at"] = settled_known_at
                _store_run(run_id, run)
        try:
            settled_state = settle_candidate_state(
                bundle_dir,
                candidate_state,
                run.get("history_append", []),
                current_state_id=new_state_id,
                settlement_graph=settlement_graph,
                expected_prior_state_id=run.get("prior_state_id"),
                expected_prior_graph_hash=run.get("prior_graph_hash"),
                expected_candidate_state_id=run.get("candidate_state_id"),
                expected_candidate_state_hash=(
                    run.get("candidate_state_hash")
                    or _graph_content_hash(candidate_state)
                ),
                expected_candidate_graph_hash=(
                    run.get("candidate_graph_hash")
                    or _graph_content_hash(candidate_graph)
                ),
                settlement_runtime_flags=settlement_runtime_flags,
                pending_settlement=pending_settlement,
            )
        except DynamicsBundleError as exc:
            with _registry_lock:
                if (
                    run.get("status") == "SETTLING"
                    and not (bundle_dir / "settlement_journal.json").exists()
                ):
                    run["status"] = "PREPARED"
                    _store_run(run_id, run)
            raise HTTPException(409, str(exc)) from exc

    try:
        settled_graph_version = _archive_graph_version(
            case_id,
            new_state_id,
            "CURRENT",
            settled_state["current_graph"],
            run_id=run_id,
            event_id=event_id,
            prior_state_id=run.get("prior_state_id"),
            effective_date=payload.get("effective_date", today),
            known_at=settled_known_at,
        )
        archive_warning = None
    except Exception as exc:
        # Current already advanced.  Preserve that institutional truth and make
        # the archive fault explicit instead of returning the run to PREPARED.
        settled_graph_version = None
        archive_warning = str(exc)
        logger.exception("settled graph version archive failed for %s", run_id)

    actor = str(payload.get("actor_id") or "partner-001")
    with _registry_lock:
        run["settled_state_id"] = new_state_id
        run["settled_graph_version"] = settled_graph_version
        run["status"] = "SETTLED"
        run["selected_change_ids"] = list(selected_change_ids)
        run["partial"] = partial
        run["pending_settlement"] = copy.deepcopy(pending_settlement)
        if archive_warning:
            run["settlement_warning"] = archive_warning
        _store_run(run_id, run)

    events_dir = VAULT / "deals" / case_id / "events"
    settle_file = events_dir / f"e-{case_id}-settle-{ts}.md"
    settlement_fm = {
        "id": f"e-{case_id}-settle-{ts}",
        "type": "settlement",
        "settles": event_id,
        "run_id": run_id,
        "candidate_state_id": run["candidate_state_id"],
        "current_state_id": new_state_id,
        "selected-change-ids": list(selected_change_ids),
        "settled-object-ids": sorted(selected_object_ids),
        "partial": partial,
        "unsettled-component-ids": unsettled_component_ids,
        "replay_hash": transition_output.get("replay_hash", "sha256:settled"),
        "decision": "accepted",
        "actor": actor,
        "timestamp": settled_known_at,
        "written-by": "v20-api",
    }
    try:
        events_dir.mkdir(parents=True, exist_ok=True)
        _write_text_atomic(
            settle_file,
            "---\n"
            + yaml.safe_dump(settlement_fm, sort_keys=False, allow_unicode=True)
            + "---\n",
        )
        audit_warning = None
    except OSError as exc:
        audit_warning = str(exc)
        logger.exception("settlement audit event write failed for %s", run_id)
    background_tasks.add_task(_rebuild_index)

    context = _make_context(case_id, new_state_id, today)
    response = {
        "settlement_id": f"SETTLE-{run_id}",
        "case_id": case_id,
        "run_id": run_id,
        "candidate_state_id": run["candidate_state_id"],
        "prior_state_id": run.get("prior_state_id", "STATE-PRIOR"),
        "current_state_id": new_state_id,
        "selected_change_ids": list(selected_change_ids),
        "settled_change_set_ids": list(selected_change_ids),
        "settled_object_ids": sorted(selected_object_ids),
        "partial": partial,
        "blocked_components": blocked_components,
        "unsettled_component_ids": unsettled_component_ids,
        "pending_settlement": pending_settlement,
        "summary": (
            f"Partially settled {event_id} into Current {new_state_id}"
            if partial
            else f"Settled {event_id} into Current {new_state_id}"
        ),
        "replay_hash": transition_output.get("replay_hash", "sha256:settled"),
        "timestamp": settled_known_at,
        "effective_date": payload.get("effective_date", today),
        "known_at": settled_known_at,
        "as_of_state_id": new_state_id,
        "as_of_date": today,
        "context": context,
        "registry": [],
        "runtime_state_id": settled_state["state_id"],
        "graph_version": settled_graph_version,
    }
    if archive_warning:
        response["warning"] = "Current settled, but graph-version archive failed: " + archive_warning
    if audit_warning:
        response["warning"] = (
            str(response.get("warning") or "")
            + ("; " if response.get("warning") else "")
            + "Current settled, but audit-event write failed: "
            + audit_warning
        )
    run["settlement_response"] = copy.deepcopy(response)
    _store_run(run_id, run)
    updated_projection = _build_projection(case_id)
    response["projection"] = {
        "projection": updated_projection,
        "context": context,
        "registry": [],
    }
    return response

# Also keep the event-based settle for direct calls
@v20.post("/cases/{case_id}/events/{event_id}/settle")
async def settle_event(
    case_id: str, event_id: str,
    background_tasks: BackgroundTasks,
    payload: dict = {},
) -> dict:
    raise HTTPException(
        409,
        "Direct event settlement is disabled; admit the event, prepare its explicit "
        "change set, attest every Human Stop, then settle the resulting run",
    )


def _write_run_prepared_event(
    run_id: str,
    run: dict,
    selected_change_ids: list[str],
    selection_hash: str,
) -> str:
    """Durably bind one PREPARED selection to its audit event.

    The identifier is deterministic, so a retry can repair a missing legacy
    event without creating a second preparation record.  Callers write this
    event before persisting the PREPARED state.
    """

    case_id = str(run["case_id"])
    digest = selection_hash.removeprefix("sha256:")[:20]
    event_record_id = str(
        run.get("prepared_event_id")
        or f"e-{case_id}-run-prepared-{digest}"
    )
    event_fm = {
        "id": event_record_id,
        "type": "run_prepared",
        "run_id": run_id,
        "candidate_state_id": run["candidate_state_id"],
        "selected-change-ids": list(selected_change_ids),
        "replay_hash": run["transition_output"].get(
            "replay_hash", "sha256:live"
        ),
        "selection_hash": selection_hash,
        "actor": run.get("prepared_by") or "system-preparer",
        "timestamp": run.get("prepared_at") or _now_iso(),
        "written-by": "v20-api",
    }
    event_path = (
        VAULT / "deals" / case_id / "events" / f"{event_record_id}.md"
    )
    _write_text_atomic(
        event_path,
        "---\n"
        + yaml.safe_dump(event_fm, sort_keys=False, allow_unicode=True)
        + "---\n",
    )
    return event_record_id


@v20.post("/runs/{run_id}/prepare")
async def prepare_run(run_id: str, payload: dict = {}) -> dict:
    with _registry_lock:
        run = _runs.get(run_id)
        if not run:
            raise HTTPException(404, f"Run not found: {run_id}")
        if run.get("settled_state_id") or run.get("status") in {"SETTLING", "SETTLED"}:
            raise HTTPException(409, f"Run {run_id} can no longer be prepared")

        supplied_candidate_id = payload.get("candidate_state_id")
        if (
            supplied_candidate_id is not None
            and str(supplied_candidate_id) != str(run.get("candidate_state_id"))
        ):
            raise HTTPException(409, "Prepare request Candidate does not match the run")

        selected_change_ids = _normalise_selected_change_ids(
            payload.get("selected_change_ids", [])
        )
        if not selected_change_ids:
            raise HTTPException(409, "Select at least one Candidate change before prepare")
        available = _change_set_index(run)
        if not available:
            raise HTTPException(409, "Candidate contains no settleable change set")
        unknown = sorted(set(selected_change_ids) - set(available))
        if unknown:
            raise HTTPException(
                409,
                "Unknown or out-of-scope Candidate change id(s): " + ", ".join(unknown),
            )

        selection_hash = _graph_content_hash(
            {
                "run_id": run_id,
                "candidate_state_id": run.get("candidate_state_id"),
                "selected_change_ids": sorted(selected_change_ids),
            }
        )
        if run.get("status") == "PREPARED":
            if run.get("prepared_selection_hash") != selection_hash:
                raise HTTPException(409, "Run is already PREPARED with another selection")
            try:
                prepared_event_id = _write_run_prepared_event(
                    run_id,
                    run,
                    list(run["selected_change_ids"]),
                    selection_hash,
                )
            except OSError as exc:
                raise HTTPException(
                    503,
                    "PREPARED audit event could not be persisted; retry is safe",
                ) from exc
            if run.get("prepared_event_id") != prepared_event_id:
                run["prepared_event_id"] = prepared_event_id
                _store_run(run_id, run)
            return {
                "run_id": run_id,
                "candidate_state_id": run["candidate_state_id"],
                "status": "PREPARED",
                "selected_change_ids": list(run["selected_change_ids"]),
                "selection_hash": selection_hash,
            }
        if run.get("status") != "CANDIDATE_READY":
            raise HTTPException(
                409,
                f"Run must be CANDIDATE_READY before prepare; found {run.get('status')}",
            )

        prepared_run = copy.deepcopy(run)
        prepared_run["selected_change_ids"] = selected_change_ids
        prepared_run["prepared_selection_hash"] = selection_hash
        prepared_run["prepared_by"] = str(
            payload.get("actor_id") or "system-preparer"
        )
        prepared_run["prepared_at"] = _now_iso()
        prepared_run["status"] = "PREPARED"
        try:
            prepared_run["prepared_event_id"] = _write_run_prepared_event(
                run_id,
                prepared_run,
                selected_change_ids,
                selection_hash,
            )
        except OSError as exc:
            raise HTTPException(
                503,
                "Prepare audit event could not be persisted; run remains CANDIDATE_READY",
            ) from exc
        run = _store_run(run_id, prepared_run)

        return {
            "run_id": run_id,
            "candidate_state_id": run["candidate_state_id"],
            "status": "PREPARED",
            "selected_change_ids": selected_change_ids,
            "selection_hash": selection_hash,
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
    human_stop_id = str(payload.get("human_stop_id") or "")
    declared_stops = {
        str(item.get("stop_id")): _frontend_human_stop(item)
        for item in run["transition_output"].get("human_stops", [])
        if isinstance(item, dict) and item.get("stop_id")
    }
    if not declared_stops:
        raise HTTPException(409, "Candidate has no Human Stop to attest")
    if human_stop_id not in declared_stops:
        raise HTTPException(409, "human_stop_id is not part of this Candidate")
    human_stop = declared_stops[human_stop_id]
    if payload.get("candidate_state_id") != run.get("candidate_state_id"):
        raise HTTPException(409, "Authority request Candidate does not match the run")
    course_id = str(payload.get("course_id") or "")
    if not course_id:
        raise HTTPException(400, "course_id is required")
    artifact_hash = str(payload.get("artifact_hash") or "")
    if not artifact_hash:
        raise HTTPException(400, "artifact_hash is required")
    replay_hash = str(run["transition_output"].get("replay_hash") or "")
    if not replay_hash or artifact_hash != replay_hash:
        raise HTTPException(409, "Authority artifact hash does not match this Candidate replay")
    course, _ = _execution_course(run["case_id"], course_id)
    if not course:
        raise HTTPException(409, "course_id is not available for this decision")
    effect_type = str(course.get("effect_type") or "")
    if effect_type not in {"EXTERNAL_PACKAGE", "INTERNAL", "DEFER"}:
        raise HTTPException(409, f"Unsupported course effect_type: {effect_type}")

    actor_id = str(payload.get("actor_id") or "partner-001")
    actor = _authority_actor(run["case_id"], actor_id)
    if actor is None:
        raise HTTPException(403, "Actor has no server-side authority assignment for this case")
    required_role = str(
        human_stop.get("required_role")
        or human_stop.get("required_authority_level")
        or "PROFESSIONAL_REVIEWER"
    )
    if not _actor_satisfies_role(actor, required_role):
        raise HTTPException(403, f"Actor lacks required authority role: {required_role}")
    authority_verb = str(human_stop.get("authority_verb") or "RESOLVE_HUMAN_STOP")
    if authority_verb not in {
        str(item) for item in actor.get("authority_verbs", [])
    }:
        raise HTTPException(403, f"Actor lacks required authority verb: {authority_verb}")
    distinct_from = str(human_stop.get("required_actor_distinct_from") or "")
    if distinct_from and actor_id == distinct_from:
        raise HTTPException(409, "Human Stop requires an independent authority actor")

    record_key = "|".join(
        (
            run_id,
            human_stop_id,
            actor_id,
            course_id,
        )
    )
    record_id = "AUTH-" + hashlib.sha256(record_key.encode("utf-8")).hexdigest()[:12].upper()
    records_for_stop = [
        item
        for item in run.get("authority_records", [])
        if item.get("human_stop_id") == human_stop_id
        and item.get("status") == "ATTESTED"
    ]
    existing = next(
        (item for item in records_for_stop if item.get("authority_record_id") == record_id),
        None,
    )
    if existing:
        package = None
        if existing.get("effect_type") == "EXTERNAL_PACKAGE":
            package = _build_execution_package(run_id, existing)
        remaining = sorted(
            set(declared_stops)
            - {
                str(item.get("human_stop_id"))
                for item in run.get("authority_records", [])
                if item.get("status") == "ATTESTED"
            }
        )
        return {
            "authority_record": existing,
            "execution_package": package,
            "remaining_open_stop_ids": remaining,
            "registry": [],
        }
    if records_for_stop:
        raise HTTPException(409, "Human Stop already has a conflicting authority record")
    authority_record = {
        "authority_record_id": record_id,
        "run_id": run_id,
        "candidate_state_id": run["candidate_state_id"],
        "human_stop_id": human_stop_id,
        "course_id": course_id,
        "actor_id": actor_id,
        "actor_role": actor.get("role"),
        "timestamp": ts,
        "effective_date": today,
        "known_at": ts,
        "artifact_hash": artifact_hash,
        "authority_verb": authority_verb,
        "required_role": required_role,
        "prepared_selection_hash": run.get("prepared_selection_hash"),
        "effect_type": effect_type,
        "status": "ATTESTED",
        "synthetic": False,
    }
    run.setdefault("authority_records", []).append(authority_record)
    _store_run(run_id, run)
    execution_package = None
    if effect_type == "EXTERNAL_PACKAGE":
        execution_package = _build_execution_package(run_id, authority_record)
    remaining = sorted(
        set(declared_stops)
        - {
            str(item.get("human_stop_id"))
            for item in run.get("authority_records", [])
            if item.get("status") == "ATTESTED"
        }
    )
    return {
        "authority_record": authority_record,
        "execution_package": execution_package,
        "remaining_open_stop_ids": remaining,
        "registry": [],
    }


@v20.get("/cases/{case_id}/replay")
def replay(case_id: str, as_of_date: str | None = None, event_id: str | None = None) -> dict:
    if as_of_date and event_id:
        raise HTTPException(400, "Choose either as_of_date or event_id, not both")

    all_events = _load_projection_events(case_id)
    if event_id:
        target_event = all_events.get(event_id)
        if not target_event:
            raise HTTPException(404, f"Replay event not found: {event_id}")
        cutoff = _parse_temporal_instant(target_event.get("known_at"))
        if cutoff is None:
            raise HTTPException(422, f"Replay event has invalid known_at: {event_id}")
        date = cutoff.date().isoformat()
    else:
        date = as_of_date or _today()
        try:
            parsed_date = dt.date.fromisoformat(date)
        except ValueError as exc:
            raise HTTPException(400, "as_of_date must be an ISO date (YYYY-MM-DD)") from exc
        cutoff = dt.datetime.combine(
            parsed_date,
            dt.time.max,
            tzinfo=dt.timezone.utc,
        )
        target_event = None

    known_events = [
        copy.deepcopy(event)
        for event in all_events.values()
        if _known_by(event, cutoff)
    ]
    snapshots = _event_replay_snapshots(known_events)
    if not snapshots:
        raise HTTPException(404, "No event was known by the requested replay cutoff")
    snapshot = next(
        (item for item in snapshots if item["event_id"] == event_id),
        snapshots[-1],
    )
    if target_event is None:
        target_event = all_events[snapshot["event_id"]]

    proj = _build_projection(case_id, date)
    deal = proj.get("deal", {})
    filtered_claims = [
        copy.deepcopy(claim)
        for claim in deal.get("claims", [])
        if _known_by(claim, cutoff)
    ]
    filtered_events = {
        event["event_id"]: event
        for event in known_events
    }
    questions = _load_questions(case_id)
    question_spine = _build_question_spine(questions, filtered_claims)
    semantic_graph = _semantic_graph_from_claims(filtered_claims, case_id)
    foundations, unknowns, semantic_positions = _semantic_rooms(
        semantic_graph,
        question_spine,
    )
    sources = _build_sources_from_claims(filtered_claims)
    retired_sources = {
        str(event.get("source_id") or ""): event
        for event in known_events
        if str(event.get("type") or "").lower() == "source_retired"
        and event.get("source_id")
    }
    for source in sources:
        retirement = retired_sources.get(str(source.get("source_id") or ""))
        source["status"] = "RETIRED" if retirement else "ACTIVE"
        if retirement:
            source["retired_at"] = retirement["known_at"]
            source["retirement_event_id"] = retirement["event_id"]

    current_graph, graph_metadata = _current_graph_as_of(case_id, cutoff)
    if "case_positions" in current_graph:
        current_graph = {
            **current_graph,
            "positions": current_graph["case_positions"],
        }
    state_id = str(
        (graph_metadata or {}).get("state_id")
        or snapshot.get("result_state_id")
        or snapshot["id"]
    )
    snapshot = {**snapshot, "id": state_id, "result_state_id": state_id}
    deal.update({
        "as_of_date": date,
        "as_of_state_id": state_id,
        "claims": filtered_claims,
        "question_spine": question_spine,
        "source_center": {"sources": sources},
        "semantic_current_graph": semantic_graph,
        "rooms": {
            "foundations": {"sets": foundations},
            "unknowns": unknowns,
            "shadowIC": {"theses": []},
        },
        "scenarioLab": _scenario_lab(current_graph),
        "positions": semantic_positions,
        "current_graph": current_graph,
        "candidate_graph": {},
        "transition_output": {},
        "graph_versions": [
            item for item in _list_graph_versions(case_id)
            if _known_by(item, cutoff)
        ],
        "replay": {
            "source": "REGISTRY_EVENTS",
            "hand_authored_snapshots": False,
            "snapshots": snapshots,
        },
    })
    proj["events"] = filtered_events
    proj = _apply_decision_intelligence(proj)
    stable_hash = _stable_json_hash({
        "case_id": case_id,
        "cutoff": cutoff.isoformat(),
        "event_ids": [item["event_id"] for item in snapshots],
        "claim_ids": sorted(str(item.get("claim_id") or "") for item in filtered_claims),
        "graph_hash": (graph_metadata or {}).get("graph_hash"),
        "state_id": state_id,
    })
    context = _make_context(case_id, state_id, date)
    return {
        "snapshot": snapshot,
        "event": target_event,
        "source_state_id": snapshot["source_state_id"],
        "result_state_id": state_id,
        "stable_hash": stable_hash,
        "effective_date": target_event["effective_date"],
        "known_at": target_event["known_at"],
        "as_of_date": date,
        "read_only": True,
        "derived_from_event_log": True,
        "projection": {"projection": proj, "context": context, "registry": known_events},
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
    raw = _load_claims(case_id)
    bears_on_map = _load_bears_on_map(case_id)
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
