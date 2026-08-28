#!/usr/bin/env python3
"""PE OS local app server — the API layer over the vault.

Every write goes through ontology-shaped templates; every agent action maps to a
policy-table row; nothing listens beyond localhost. The vault stays canonical:
this server is a doorway, not a database.

Run:  make app   (uvicorn on http://127.0.0.1:8787)
"""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import os

# Load .env at project root so ANTHROPIC_API_KEY reaches the server
# even when uvicorn is started without an explicit export in the shell.
def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)

_load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
IS_CLOUD = os.environ.get("VERCEL") == "1"
HAS_STORE = bool(os.environ.get("BLOB_READ_WRITE_TOKEN"))
if IS_CLOUD:
    os.environ.setdefault("PEOS_DB", "/tmp/vault.db")
    os.environ.setdefault("PEOS_VAULT", "/tmp/vault")
sys.path.insert(0, str(ROOT / "tools"))
from engine import load_transitions  # noqa: E402
from ui import replay, state_label  # noqa: E402
import indexer  # noqa: E402
import vaultsync  # noqa: E402

DB = indexer.DB
VAULT = indexer.VAULT
WRITABLE = (not IS_CLOUD) or HAS_STORE


def sync():
    """Cloud: pull the vault mirror current from Blob before reading."""
    if IS_CLOUD and HAS_STORE:
        VAULT.mkdir(parents=True, exist_ok=True)
        vaultsync.sync_down(VAULT)


def push():
    """Cloud: push mirror changes to Blob after writing."""
    if IS_CLOUD and HAS_STORE:
        vaultsync.push_dirty(VAULT)

app = FastAPI(title="PE OS", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── V20 router (the contract the frontend speaks) ─────────────────────────────
from app.v20_router import v20  # noqa: E402
app.include_router(v20)

# ── V20 frontend — served at /ui so API routes always win ─────────────────────
_UI_DIR = ROOT / "ui" / "01_PRODUCT_BUILD" / "app"
if _UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_UI_DIR), html=True), name="v20-ui")

EPISTEMIC = ("asserted", "derived", "observed", "attested")
Q_STATES = ("open", "reducing", "resolved", "accepted-unresolved")


def reindex():
    indexer.build().close()


def con():
    return sqlite3.connect(DB)


def rows(c, q, *a):
    return [(json.loads(fm), title) for fm, title in c.execute(q, a).fetchall()]


def next_id(deal: str, prefix: str, folder: str) -> str:
    d = VAULT / "deals" / deal / folder
    d.mkdir(parents=True, exist_ok=True)
    n = len(list(d.glob(f"{prefix}-{deal}-*.md"))) + 1
    return f"{prefix}-{deal}-{n:03d}"


# ---------------------------------------------------------------- reads

@app.get("/")
def home():
    if IS_CLOUD:
        sync()
        reindex()  # cold start: mirror + index into /tmp
    return FileResponse(ROOT / "app" / "static" / "canvas.html")


@app.get("/desks")
def desks_page():
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.get("/api/mode")
def mode():
    if IS_CLOUD and HAS_STORE:
        note = "cloud live mode — vault in Blob storage; run the agents tick to make them work through the backlog"
    elif IS_CLOUD:
        note = "cloud read-only — no Blob store connected"
    else:
        note = "local node — full capability"
    return {"cloud": IS_CLOUD, "writable": WRITABLE, "note": note}


def require_writable():
    if not WRITABLE:
        raise HTTPException(501, "read-only: no datastore connected in this environment")


@app.get("/api/deals")
def deals():
    """Read from the filesystem directly — the vault is canonical, never the index."""
    sync()
    out = []
    for f in sorted((VAULT / "deals").glob("*/deal.md")):
        text = f.read_text(encoding="utf-8")
        state = re.search(r"^state:\s*(\S+)", text, re.MULTILINE)
        title = re.search(r"^# (.+)$", text, re.MULTILINE)
        out.append({"id": f.parent.name, "title": title.group(1) if title else f.parent.name,
                    "state": state.group(1) if state else "?"})
    return out


@app.get("/api/deal/{deal}")
def deal_view(deal: str):
    sync()
    reindex()  # cheap at this scale; guarantees the view is never stale
    c = con()
    d = rows(c, "SELECT frontmatter, title FROM nodes WHERE type='deal' AND deal=?", deal)
    if not d:
        raise HTTPException(404, "deal not in index")
    dfm, dtitle = d[0]
    questions = rows(c, "SELECT frontmatter, title FROM nodes WHERE type='question' AND deal=? ORDER BY id", deal)
    claims = rows(c, "SELECT frontmatter, title FROM nodes WHERE type='claim' AND deal=? ORDER BY id", deal)
    events = sorted(rows(c, "SELECT frontmatter, title FROM nodes WHERE type='event' AND deal=?", deal),
                    key=lambda x: str(x[0].get("at", "")))
    crit_open = [q for q, _ in questions if q.get("critical") and q.get("state") in ("open", "reducing")]
    state, trail, held = replay([e for e, _ in events], load_transitions(), crit_open)

    by_subject: dict[str, list] = {}
    for fm, _ in claims:
        by_subject.setdefault(fm.get("subject") or "—", []).append(fm)
    contras = [{"subject": s, "claims": cs} for s, cs in by_subject.items()
               if len({str(x.get("value")) for x in cs}) > 1]

    assumptions = rows(c, "SELECT frontmatter, title FROM nodes WHERE type='assumption' AND deal=? ORDER BY id", deal)
    outputs = [{**json.loads(fm), "title": t,
                "body": (VAULT / p).read_text(encoding="utf-8").split("---", 2)[-1].strip()}
               for fm, t, p in c.execute(
                   "SELECT frontmatter, title, path FROM nodes WHERE type='workstream-output' AND deal=? ORDER BY id",
                   (deal,)).fetchall()]
    return {
        "deal": {**dfm, "title": dtitle},
        "assumptions": [{**a, "title": t} for a, t in assumptions],
        "outputs": outputs,
        "state": state, "state_label": state_label(state),
        "trail": [{"event": ev, "from": frm, "to": (t["to"] if t else None),
                   "tid": (t["id"] if t else None), "blocked": blocked}
                  for ev, frm, t, blocked in trail],
        "held": [{"tid": t["id"], "to": t["to"], "critical_open": len(crit_open)} for t in held],
        "questions": [{**q, "title": t} for q, t in questions],
        "claims": [{**cfm, "title": t} for cfm, t in claims],
        "events": [e for e, _ in events],
        "contradictions": contras,
    }


@app.get("/api/deal/{deal}/state")
def deal_b0(deal: str):
    """B0 state object — the contract between backend and frontend renderer."""
    sync()
    reindex()
    try:
        from b0_assembler import assemble
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location("b0_assembler", ROOT / "tools" / "b0_assembler.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assemble = mod.assemble
    try:
        return JSONResponse(assemble(deal))
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/deal/{deal}/state/staleness")
def deal_staleness(deal: str, payload: dict):
    """Propagate staleness from a changed node and return the updated graph."""
    sync()
    reindex()
    changed_node = payload.get("node")
    if not changed_node:
        raise HTTPException(400, "body must include 'node'")
    try:
        from b0_assembler import assemble, propagate_staleness
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location("b0_assembler", ROOT / "tools" / "b0_assembler.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assemble = mod.assemble
        propagate_staleness = mod.propagate_staleness
    try:
        state = assemble(deal)
    except ValueError as e:
        raise HTTPException(404, str(e))
    updated_graph = propagate_staleness(state["graph"], changed_node)
    return JSONResponse({
        "changedNode": changed_node,
        "propagationOrder": updated_graph["propagationOrder"],
        "staleNodes": [n["id"] for n in updated_graph["nodes"] if n["status"] == "stale"],
        "graph": updated_graph,
    })


@app.get("/api/deal/{deal}/claims")
def deal_claims_as_of(deal: str, as_of: str | None = None):
    """Return claims for a deal, optionally filtered to an as-of date (YYYY-MM-DD).

    Each claim carries two timestamps:
      - source.date / extracted-date: when the underlying fact was true
      - extracted / ingested-at: when the firm knew it

    as_of filters by source.date: only claims whose source date ≤ as_of are returned.
    This lets you reconstruct "what did we know on <date>?".
    """
    sync()
    reindex()
    c = con()
    rows = c.execute(
        "SELECT id, frontmatter FROM nodes WHERE type='claim' AND deal=? ORDER BY id", (deal,)
    ).fetchall()
    out = []
    for cid, fm_raw in rows:
        fm = json.loads(fm_raw)
        if as_of:
            # Extract source date: source.date > extracted > ingested-at
            src = fm.get("source") or {}
            src_date = (src.get("date") if isinstance(src, dict) else None) or fm.get("extracted") or ""
            src_date_str = str(src_date)[:10] if src_date else ""
            if src_date_str and src_date_str > as_of:
                continue  # claim was not known as of this date
        out.append({
            "id": cid,
            "epistemic": fm.get("epistemic"),
            "subject": fm.get("subject"),
            "value": fm.get("value"),
            "sourceDate": str((fm.get("source") or {}).get("date", "") if isinstance(fm.get("source"), dict) else fm.get("extracted", "")),
            "provenance": f"{fm.get('artifact') or (fm.get('source') or {}).get('artifact', '')} · {fm.get('locator') or (fm.get('source') or {}).get('locator', '')}".strip(" ·"),
        })
    return JSONResponse({"deal": deal, "asOf": as_of, "count": len(out), "claims": out})


@app.get("/api/deal/{deal}/stale")
def deal_stale(deal: str):
    """Return all stale derived claims for a deal."""
    sync()
    reindex()
    try:
        from recalc import query_stale
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location("recalc", ROOT / "tools" / "recalc.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        query_stale = mod.query_stale
    c = con()
    return JSONResponse({"deal": deal, "stale": query_stale(c, deal)})


class RecalcIn(BaseModel):
    claim_id: str
    new_value: str
    write_stale: bool = False


@app.post("/api/deal/{deal}/recalc")
def deal_recalc(deal: str, payload: RecalcIn):
    """Deterministic recalculation from a changed claim value.

    If write_stale=true, marks descendants stale in vault files.
    """
    sync()
    reindex()
    try:
        from recalc import recalc, mark_stale, report
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location("recalc", ROOT / "tools" / "recalc.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        recalc = mod.recalc
        mark_stale = mod.mark_stale
        report = mod.report
    c = con()
    result = recalc(c, deal, payload.claim_id, payload.new_value)
    marked = []
    if payload.write_stale:
        require_writable()
        marked = mark_stale(deal, payload.claim_id)
        push()
    return JSONResponse({
        "changed": result.changed,
        "order": result.order,
        "recomputed": [{"id": cid, "value": val} for cid, val in result.recomputed],
        "stale": [{"id": cid, "old": old, "new": new} for cid, old, new in result.stale],
        "marked_stale_in_vault": marked,
    })


@app.get("/api/brain")
def brain():
    sync()
    """The firm brain: question-type archives (librarian-maintained) + entities."""
    qts = [{"kind": "question-type", "name": f.stem, "content": f.read_text(encoding="utf-8")}
           for f in sorted((VAULT / "library" / "question-types").glob("*.md"))]
    ents = [{"kind": "entity", "name": f.stem, "content": f.read_text(encoding="utf-8")}
            for d in ("companies", "people") for f in sorted((VAULT / "entities" / d).glob("*.md"))]
    return qts + ents


@app.get("/api/ontology")
def ontology():
    sync()
    files = sorted((VAULT / "ontology").glob("*.md")) + [VAULT / "policy" / "policy-table.md"]
    return [{"name": f.stem, "content": f.read_text(encoding="utf-8")} for f in files]


# ---------------------------------------------------------------- writes (human context — written-by: human)

class DealIn(BaseModel):
    name: str
    company: str
    thesis: str


@app.post("/api/deals")
def create_deal(d: DealIn):
    require_writable()
    """Deal open — real human input, the first of the two ritual inputs."""
    slug = re.sub(r"[^a-z0-9]+", "-", d.name.lower()).strip("-")[:30]
    root = VAULT / "deals" / slug
    if root.exists():
        raise HTTPException(409, f"deal '{slug}' already exists")
    for sub in ("questions", "claims", "events", "decisions", "assumptions", "outputs", "exceptions"):
        (root / sub).mkdir(parents=True)
    cslug = re.sub(r"[^a-z0-9]+", "-", d.company.lower()).strip("-")[:30]
    if cslug == slug:
        cslug += "-co"  # ids are global across the graph; a deal and its company must not collide
    ent = VAULT / "entities" / "companies" / f"{cslug}.md"
    if not ent.exists():
        ent.write_text(f"---\ntype: company\nid: {cslug}\naliases: [\"{d.company}\"]\nrole: target\n"
                       f"written-by: human\n---\n\n# {d.company}\n", encoding="utf-8")
    (root / "deal.md").write_text(f"""---
type: deal
id: {slug}
company: "[[{cslug}]]"
state: S0_INTAKE
lead: "[[fabrizio]]"
thesis: "{d.thesis}"
opened: {datetime.now().date()}
written-by: human
---

# {d.name}

## Thesis
{d.thesis}

## State of the deal   <!-- agent-maintained -->

## Questions

## Decisions
""", encoding="utf-8")
    (root / "events" / f"ev-{slug}-001.md").write_text(f"""---
type: event
id: ev-{slug}-001
deal: "[[{slug}]]"
kind: DEAL_REGISTERED
actor: human
at: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}
relates-to: []
supersedes: null
---

Deal registered via app.
""", encoding="utf-8")
    push()
    reindex()
    return {"id": slug}


METRIC_CATEGORIES = {
    "revenue", "ebitda", "debt", "equity", "irr", "leverage", "multiple",
    "headcount", "margin", "growth", "cash", "capex", "working-capital",
    "customer-concentration", "churn", "price", "volume",
}


class ClaimIn(BaseModel):
    subject: str
    value: str
    epistemic: str
    bears_on: list[str] = []
    direction: str = "context"
    locator: str = ""
    author: str = ""
    author_entity: str = ""      # entity ID e.g. "big4-advisory"
    source_date: str = ""
    artifact: str = ""
    artifact_id: str = ""        # artifact node ID e.g. "art-keystone-qoe-2026"
    company: str = ""            # company entity ID e.g. "keystone-project"
    digital_source: str = ""     # permanent URL or VDR path
    metric_category: str = ""    # one of METRIC_CATEGORIES
    part_of: str = ""            # parent aggregate claim ID (micro-claim hierarchy)
    period: str = ""             # e.g. "FY2025", "LTM", "Opening", "Q4 2025"
    perimeter: str = ""          # e.g. "Firm View", "QoE View", "consolidated", "standalone"
    perimeter_note: str = ""     # free-text scope clarification
    statement: str = ""
    derivation: str | None = None
    rests_on: list[str] = []     # explicit dependency chain (for derived claims)


def _write_claim(deal: str, c_in: ClaimIn, extracted_by: str = "human") -> str:
    """Write one claim file to vault/deals/<deal>/claims/ and return its ID."""
    cid = next_id(deal, "c", "claims")
    today = str(datetime.now().date())
    bears = ", ".join(f'"[[{b}]]"' for b in c_in.bears_on)
    rests = ", ".join(f'"[[{r}]]"' for r in c_in.rests_on)
    artifact_id_line = f'artifact-id: "[[{c_in.artifact_id}]]"' if c_in.artifact_id else "artifact-id: null"
    company_line = f'company: "[[{c_in.company}]]"' if c_in.company else "company: null"
    author_entity_line = f'author-entity: "[[{c_in.author_entity}]]"' if c_in.author_entity else "author-entity: null"
    metric_line = f"metric-category: {c_in.metric_category}" if c_in.metric_category in METRIC_CATEGORIES else "metric-category: null"
    digital_line = f'digital-source: "{c_in.digital_source}"' if c_in.digital_source else "digital-source: null"
    part_of_line = f'part-of: "[[{c_in.part_of}]]"' if c_in.part_of else "part-of: null"
    period_line = f'period: "{c_in.period}"' if c_in.period else "period: null"
    perimeter_line = f'perimeter: "{c_in.perimeter}"' if c_in.perimeter else "perimeter: null"
    perimeter_note_line = f'perimeter-note: "{c_in.perimeter_note}"' if c_in.perimeter_note else "perimeter-note: null"
    body = f"""---
type: claim
id: {cid}
epistemic: {c_in.epistemic}
subject: "{c_in.subject}"
value: "{c_in.value}"
bears-on: [{bears}]
direction: {c_in.direction}
source:
  artifact: "{c_in.artifact or 'entered via app'}"
  locator: "{c_in.locator}"
  author: "{c_in.author}"
  date: {c_in.source_date or today}
{artifact_id_line}
{company_line}
{author_entity_line}
{digital_line}
{metric_line}
{part_of_line}
{period_line}
{perimeter_line}
{perimeter_note_line}
derivation: {json.dumps(c_in.derivation) if c_in.derivation else 'null'}
rests-on: [{rests}]
supersedes: null
extracted-by: {extracted_by}
extracted: {today}
last-seen: {today}
stale: false
---

{c_in.statement or c_in.subject + ': ' + c_in.value}
"""
    (VAULT / "deals" / deal / "claims" / f"{cid}.md").write_text(body, encoding="utf-8")
    return cid


def _touch_last_seen(claim_path: Path) -> bool:
    """Stamp last-seen: today on an existing claim file. Returns True if updated."""
    today = str(datetime.now().date())
    text = claim_path.read_text(encoding="utf-8")
    if f"last-seen: {today}" in text:
        return False  # already current
    if "last-seen:" in text:
        new_text = re.sub(r"last-seen:\s*\S+", f"last-seen: {today}", text)
    else:
        # Insert before extracted-by or at end of frontmatter
        if "extracted-by:" in text:
            new_text = text.replace("extracted-by:", f"last-seen: {today}\nextracted-by:", 1)
        else:
            new_text = text.replace("\n---\n\n", f"\nlast-seen: {today}\n---\n\n", 1)
    claim_path.write_text(new_text, encoding="utf-8")
    return True


@app.post("/api/deal/{deal}/claims")
def add_claim(deal: str, c_in: ClaimIn):
    require_writable()
    if c_in.epistemic not in EPISTEMIC:
        raise HTTPException(422, f"epistemic must be one of {EPISTEMIC}")
    if c_in.epistemic == "derived" and not (c_in.derivation or "").strip():
        raise HTTPException(422, "ontology rule 3: a derived claim requires an inspectable derivation")
    cid = _write_claim(deal, c_in)
    push()
    reindex()
    return {"id": cid}


class ConfirmIn(BaseModel):
    """A batch of (subject, value) pairs from a new ingestion pass.

    For each pair: if an existing claim matches, stamp last-seen today.
    If no match, return it as 'new' (caller decides whether to create).
    """
    pairs: list[dict]   # [{subject, value, locator?, source_date?}, ...]
    artifact_id: str = ""


@app.post("/api/deal/{deal}/claims/confirm")
def confirm_claims(deal: str, body: ConfirmIn):
    """Deduplication + last-seen update for an ingestion pass.

    For each (subject, value) pair:
    - If an existing claim with that subject+value exists → stamp last-seen: today
    - If not → return as 'new' so the caller can create it
    """
    require_writable()
    c = con()
    try:
        rows = c.execute(
            "SELECT id, subject, value, path FROM nodes WHERE type='claim' AND deal=?", (deal,)
        ).fetchall()
    finally:
        c.close()

    existing: dict[tuple, str] = {}  # (subject_lower, value_lower) → claim_id
    path_map: dict[str, str] = {}    # claim_id → vault-relative path
    for cid, subj, val, path_str in rows:
        if subj and val:
            existing[(subj.strip().lower(), val.strip().lower())] = cid
            path_map[cid] = path_str

    confirmed, new_claims = [], []
    for pair in body.pairs:
        subj = str(pair.get("subject", "")).strip()
        val = str(pair.get("value", "")).strip()
        key = (subj.lower(), val.lower())
        if key in existing:
            cid = existing[key]
            fpath = VAULT / path_map[cid]
            updated = _touch_last_seen(fpath) if fpath.exists() else False
            confirmed.append({"id": cid, "subject": subj, "last_seen_updated": updated})
        else:
            new_claims.append(pair)

    reindex()
    return {
        "confirmed": confirmed,
        "confirmed_count": len(confirmed),
        "new": new_claims,
        "new_count": len(new_claims),
    }


@app.get("/api/deal/{deal}/claims/unseen")
def claims_unseen(deal: str, since: str):
    """Claims not reconfirmed since `since` (YYYY-MM-DD).

    These are facts the vault holds but no recent ingestion has confirmed.
    """
    c = con()
    try:
        rows = c.execute(
            "SELECT id, subject, value, epistemic, last_seen, extracted "
            "FROM nodes WHERE type='claim' AND deal=? "
            "AND (last_seen IS NULL OR last_seen < ?) "
            "ORDER BY last_seen ASC NULLS FIRST, id",
            (deal, since),
        ).fetchall()
    finally:
        c.close()
    return [
        {"id": cid, "subject": subj, "value": val, "epistemic": ep,
         "last_seen": ls, "extracted": ext}
        for cid, subj, val, ep, ls, ext in rows
    ]


@app.get("/api/vault/manifest")
def vault_manifest():
    """Return the global graph intake timestamp from vault/manifest.md (read from file — always fresh)."""
    mp = VAULT / "manifest.md"
    if not mp.exists():
        return {"last_intake": None, "node_count": None, "edge_count": None}
    try:
        import yaml as _yaml
        text = mp.read_text(encoding="utf-8")
        end = text.find("\n---", 3)
        fm = _yaml.safe_load(text[3:end]) or {} if end != -1 else {}
        return {
            "last_intake": str(fm.get("last-intake", "")),
            "last_intake_date": str(fm.get("last-intake-date", "")),
            "node_count": fm.get("node-count"),
            "edge_count": fm.get("edge-count"),
        }
    except Exception:
        return {"last_intake": None}


# ── analysis endpoints: coverage · identity · binding ─────────────────────────

def _load_tool(name: str):
    """Lazy-load a tools/ module by filename without package import."""
    import importlib.util, sys as _sys
    if name in _sys.modules:
        return _sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[name] = mod  # register before exec so @dataclass finds its own module
    spec.loader.exec_module(mod)
    return mod


@app.get("/api/deal/{deal}/coverage")
def deal_coverage(deal: str):
    """Coverage report: how many claims are bound, unbound, stale, period-tagged."""
    c = con()
    try:
        mod = _load_tool("coverage_report")
        return mod.coverage(c, deal)
    finally:
        c.close()


@app.get("/api/deal/{deal}/identity")
def deal_identity(deal: str, threshold: float = 0.60):
    """Identity resolution: candidate pairs that may describe the same quantity."""
    c = con()
    try:
        mod = _load_tool("identity_resolver")
        results = mod.batch_resolve(c, deal, threshold)
        return [
            {
                "claim_a": r.claim_a, "claim_b": r.claim_b,
                "score": r.score, "verdict": r.verdict,
                "period_match": r.period_match, "perimeter_match": r.perimeter_match,
                "same_metric_category": r.same_metric_category,
                "reasons": r.reasons,
            }
            for r in results
        ]
    finally:
        c.close()


@app.get("/api/deal/{deal}/binding")
def deal_binding(deal: str, min_confidence: float = 0.35):
    """Binding proposals: unbound claims ranked by best-match question."""
    c = con()
    try:
        mod = _load_tool("binding_proposer")
        proposals = mod.propose_bindings(c, deal)
        return [
            {
                "claim_id": p.claim_id, "claim_subject": p.claim_subject,
                "question_id": p.question_id, "question_title": p.question_title,
                "confidence": p.confidence, "category": p.category,
                "reasons": p.reasons,
            }
            for p in proposals if p.confidence >= min_confidence
        ]
    finally:
        c.close()


@app.post("/api/deal/{deal}/parse-model")
def parse_model(deal: str, payload: dict):
    """Parse markdown model files and write claims to vault.

    payload: {files: ["vault/inbox/keystone-model-part1.md", ...], artifact_id: "..."}
    """
    require_writable()
    mod = _load_tool("model_parser")
    vault = VAULT

    files = [Path(f) for f in payload.get("files", [])]
    if not files:
        # Auto-discover
        files = sorted((vault / "inbox").glob(f"*{deal}*model*.md"))
    if not files:
        raise HTTPException(404, f"No model files found for deal '{deal}'")

    artifact_id = payload.get("artifact_id", "")
    all_cells = []
    for f in files:
        cells = mod.parse_file(f, deal)
        all_cells.extend(cells)

    all_cells = mod.resolve_dependencies(all_cells, deal)
    written = mod.write_claims(all_cells, deal, artifact_id, vault)
    reindex()
    return {
        "deal": deal,
        "files_parsed": [str(f) for f in files],
        "cells_found": len(all_cells),
        "claims_written": len(written),
        "claim_ids": written[:20],  # first 20 for inspection
    }


# ── artifact nodes ────────────────────────────────────────────────────────────

class ArtifactIn(BaseModel):
    title: str
    kind: str = "document"         # deck | model | transcript | email | report | contract | vdr-document
    digital_source: str = ""       # local path or external URL
    url: str = ""                  # permanent external URL
    received: str = ""
    source_date: str = ""
    author: str = ""
    author_entity: str = ""
    company: str = ""              # company entity ID


@app.post("/api/deal/{deal}/artifacts")
def add_artifact(deal: str, a_in: ArtifactIn):
    """Register a source document as a first-class artifact node."""
    require_writable()
    slug = re.sub(r"[^a-z0-9]+", "-", a_in.title.lower()).strip("-")[:40]
    art_id = f"art-{deal}-{slug}"
    art_dir = VAULT / "deals" / deal / "artifacts"
    art_dir.mkdir(exist_ok=True)
    company_line = f'company: "[[{a_in.company}]]"' if a_in.company else "company: null"
    author_entity_line = f'author-entity: "[[{a_in.author_entity}]]"' if a_in.author_entity else "author-entity: null"
    body = f"""---
type: artifact
id: {art_id}
deal: "[[{deal}]]"
title: "{a_in.title}"
kind: {a_in.kind}
digital-source: "{a_in.digital_source or ''}"
url: {json.dumps(a_in.url) if a_in.url else 'null'}
received: {a_in.received or datetime.now().date()}
source-date: {a_in.source_date or 'null'}
author: "{a_in.author}"
{author_entity_line}
{company_line}
written-by: extractor
---

# {a_in.title}

### Claims extracted
"""
    (art_dir / f"{art_id}.md").write_text(body, encoding="utf-8")
    push()
    reindex()
    return {"id": art_id}


@app.get("/api/deal/{deal}/artifacts")
def list_artifacts(deal: str):
    """List all artifact nodes for a deal with claim counts."""
    c = con()
    try:
        rows = c.execute(
            "SELECT n.id, n.title, n.frontmatter, "
            "COUNT(e.src) as claim_count "
            "FROM nodes n "
            "LEFT JOIN edges e ON e.dst=n.id AND e.rel='artifact-id' "
            "WHERE n.type='artifact' AND n.deal=? "
            "GROUP BY n.id ORDER BY n.id",
            (deal,),
        ).fetchall()
    finally:
        c.close()
    result = []
    for aid, title, fm_raw, claim_count in rows:
        fm = json.loads(fm_raw or "{}")
        result.append({
            "id": aid, "title": title,
            "kind": fm.get("kind"), "received": fm.get("received"),
            "source_date": fm.get("source-date"), "author": fm.get("author"),
            "digital_source": fm.get("digital-source"),
            "claim_count": claim_count,
        })
    return result


# ── batch extraction endpoint ─────────────────────────────────────────────────

class ExtractIn(BaseModel):
    text: str                      # raw document text
    artifact_id: str = ""          # existing artifact node ID (if already registered)
    artifact_title: str = ""       # used to auto-create artifact node if artifact_id is empty
    kind: str = "document"
    digital_source: str = ""
    source_date: str = ""
    author: str = ""
    author_entity: str = ""
    company: str = ""
    max_claims: int = 40


_EXTRACT_SYSTEM = """You are a claim extraction agent for a private equity knowledge vault.

## Atomicity rule
One claim = one fact. Never pack multiple numbers or assertions into a single claim value.
If a table row has N numbers, extract N micro-claims plus one parent aggregate claim.

## Hierarchy rule
When a document shows a bridge or roll-forward (e.g. EBITDA bridge, revenue bridge, debt schedule):
1. Extract one PARENT claim: the aggregate/total, epistemic=derived, with a derivation field.
2. Extract one CHILD claim per line item: the atomic number, with part_of set to the parent's
   position in the array (use a placeholder like "parent:0" referencing the parent's index).
3. The parent's rests_on should list all child subjects.

## Output format
Return a JSON array of claim objects. Each object:
{
  "subject": "normalized topic string — same concept must use same subject across documents",
  "value": "single fact (one number, one assertion)",
  "epistemic": "asserted|derived|observed|attested",
  "locator": "slide N / page N / cell Sheet1!D42 / timestamp HH:MM:SS",
  "metric_category": "revenue|ebitda|debt|equity|irr|leverage|multiple|headcount|margin|growth|cash|capex|working-capital|customer-concentration|churn|price|volume|null",
  "derivation": "formula in plain English if derived, else null",
  "rests_on_subjects": ["subject of child claim 1", ...],  // for derived parent claims
  "part_of_index": null,  // integer index of parent claim in this array, for child claims
  "statement": "one sentence in plain English"
}

No prose, no markdown — pure JSON array."""


@app.post("/api/deal/{deal}/extract")
def extract_claims(deal: str, body: ExtractIn):
    """LLM-powered atomic claim extraction from raw document text.

    Creates an artifact node if artifact_id is empty, then returns structured
    claim objects for human review before committing to vault.

    Policy row 3 applies: no real VDR content until ZDR endpoint is configured.
    """
    require_writable()
    import os
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(503, "ANTHROPIC_API_KEY not set — cannot run extraction")

    # Auto-register artifact node
    art_id = body.artifact_id
    if not art_id and body.artifact_title:
        a_in = ArtifactIn(
            title=body.artifact_title, kind=body.kind,
            digital_source=body.digital_source, source_date=body.source_date,
            author=body.author, author_entity=body.author_entity, company=body.company,
        )
        result = add_artifact(deal, a_in)
        art_id = result["id"]

    # Call LLM for extraction
    import urllib.request as _req
    model = os.environ.get("PEOS_MODEL", "claude-sonnet-5")
    user_msg = (
        f"Document metadata: author={body.author!r}, date={body.source_date!r}, "
        f"kind={body.kind!r}, company={body.company!r}\n\n"
        f"Extract up to {body.max_claims} atomic claims from this document:\n\n"
        f"{body.text[:80_000]}"
    )
    payload = {
        "model": model, "max_tokens": 8000,
        "system": _EXTRACT_SYSTEM,
        "messages": [{"role": "user", "content": user_msg}],
    }
    req = _req.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"},
    )
    with _req.urlopen(req, timeout=120) as resp:
        raw = json.loads(resp.read())

    text_out = next((b["text"] for b in raw.get("content", []) if b.get("type") == "text"), "[]")
    # Strip markdown code fences if present
    text_out = re.sub(r"^```[a-z]*\n?", "", text_out.strip())
    text_out = re.sub(r"\n?```$", "", text_out.strip())
    try:
        extracted = json.loads(text_out)
    except json.JSONDecodeError:
        raise HTTPException(500, f"LLM returned non-JSON: {text_out[:300]}")

    if not isinstance(extracted, list):
        extracted = [extracted]

    return {
        "artifact_id": art_id,
        "deal": deal,
        "claim_count": len(extracted),
        "claims": extracted,
        "note": "Review claims then POST each to /api/deal/{deal}/claims to commit to vault.",
    }


@app.post("/api/deal/{deal}/extract/commit")
def commit_extracted(deal: str, payload: dict):
    """Commit reviewed claim objects (from /extract) to vault in one batch.

    Handles micro-claim hierarchy: claims with part_of_index get linked to the
    parent claim at that index once the parent's ID is known.
    """
    require_writable()
    claims_raw = payload.get("claims", [])
    artifact_id = payload.get("artifact_id", "")
    committed: list[str] = []  # list of claim IDs in order

    for c in claims_raw:
        # Resolve part_of from index to actual claim ID
        part_of_id = ""
        poi = c.get("part_of_index")
        if poi is not None and isinstance(poi, int) and 0 <= poi < len(committed):
            part_of_id = committed[poi]

        c_in = ClaimIn(
            subject=c.get("subject", ""),
            value=str(c.get("value", "")),
            epistemic=c.get("epistemic", "asserted"),
            locator=c.get("locator", ""),
            author=payload.get("author", ""),
            author_entity=payload.get("author_entity", ""),
            artifact=payload.get("digital_source", ""),
            artifact_id=artifact_id,
            company=payload.get("company", ""),
            digital_source=payload.get("digital_source", ""),
            source_date=payload.get("source_date", ""),
            metric_category=c.get("metric_category") or "",
            part_of=part_of_id,
            statement=c.get("statement", ""),
            derivation=c.get("derivation"),
        )
        if c_in.epistemic not in EPISTEMIC:
            c_in.epistemic = "asserted"
        cid = _write_claim(deal, c_in, extracted_by="extractor")
        committed.append(cid)

    push()
    reindex()
    return {"committed": committed, "count": len(committed)}


class QuestionIn(BaseModel):
    title: str
    bearing: str = ""
    critical: bool = False
    target_workstream: str = ""
    parent: str | None = None
    question_type: str | None = None


@app.post("/api/deal/{deal}/questions")
def add_question(deal: str, q: QuestionIn):
    require_writable()
    slug = re.sub(r"[^a-z0-9]+", "-", q.title.lower()).strip("-")[:40]
    qid = f"q-{deal}-{slug}"
    body = f"""---
type: question
id: {qid}
deal: "[[{deal}]]"
parent: {f'"[[{q.parent}]]"' if q.parent else 'null'}
question-type: {f'"[[{q.question_type}]]"' if q.question_type else 'null'}
state: open
resolution: null
critical: {str(q.critical).lower()}
target-workstream: {q.target_workstream or 'null'}
depends-on: []
owner: "[[fabrizio]]"
opened: {datetime.now().date()}
state-changed: {datetime.now().date()}
written-by: human
---

# {q.title}

## Bearing
{q.bearing}

## Evidence

## Resolution note | Acceptance rationale
(open)
"""
    (VAULT / "deals" / deal / "questions" / f"{qid}.md").write_text(body, encoding="utf-8")
    push()
    reindex()
    return {"id": qid}


class EventIn(BaseModel):
    kind: str
    actor: str = "human"
    note: str = ""


@app.post("/api/deal/{deal}/events")
def add_event(deal: str, e: EventIn):
    require_writable()
    eid = next_id(deal, "ev", "events")
    body = f"""---
type: event
id: {eid}
deal: "[[{deal}]]"
kind: {e.kind}
actor: {e.actor}
at: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}
relates-to: []
supersedes: null
---

{e.note or e.kind}
"""
    (VAULT / "deals" / deal / "events" / f"{eid}.md").write_text(body, encoding="utf-8")
    push()
    reindex()
    return {"id": eid}


# ---------------------------------------------------------------- agents

@app.post("/api/agents/state/{deal}")
def agent_state(deal: str):
    require_writable()
    """Policy row 4: derive + write deal.state (invariant 10)."""
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "engine.py"), deal, "--write"],
                       capture_output=True, text=True, cwd=ROOT, timeout=60)
    if r.returncode != 0:
        raise HTTPException(500, r.stderr or r.stdout)
    push()
    reindex()
    return {"output": r.stdout}


@app.post("/api/agents/contradictions/{deal}")
def agent_contradictions(deal: str):
    require_writable()
    """Policy row 5: flag contradictions, autonomous. Emits an event per finding batch."""
    view = deal_view(deal)
    found = view["contradictions"]
    if found:
        add_event(deal, EventIn(kind="CONTRADICTION_FLAGGED", actor="contradiction",
                                note=f"{len(found)} unresolved contradiction(s): "
                                     + "; ".join(c["subject"] for c in found)))
    return {"contradictions": found}


class IngestIn(BaseModel):
    filename: str
    hint: str = ""


@app.post("/api/agents/ingest/{deal}")
def agent_ingest(deal: str, body: IngestIn):
    require_writable()
    """Policy row 3+4: LLM extraction via headless Claude Code running the /ingest skill.
    Long-running; the UI shows the returned transcript when done."""
    target = (VAULT / "inbox" / body.filename).resolve()
    if not target.is_file() or not target.is_relative_to(VAULT / "inbox"):
        raise HTTPException(404, f"file not found in vault/inbox: {body.filename}")
    prompt = (f"Use the ingest skill on artifact vault/inbox/{body.filename} for deal '{deal}'. "
              f"{body.hint} Follow vault/ontology strictly; do not ask questions; report what you wrote.")
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--permission-mode", "acceptEdits"],
            capture_output=True, text=True, cwd=ROOT, timeout=600,
        )
    except FileNotFoundError:
        raise HTTPException(501, "claude CLI not found — run the /ingest skill from a Claude Code session instead")
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "ingest agent timed out (10 min)")
    reindex()
    return {"output": r.stdout[-8000:], "ok": r.returncode == 0}


class AssumptionPatch(BaseModel):
    value: str
    rationale: str = ""


@app.patch("/api/deal/{deal}/assumptions/{aid}")
def patch_assumption(deal: str, aid: str, body: AssumptionPatch):
    require_writable()
    """V1 step 4 trigger: a human revises an assumption's value. Version bumps,
    history appends, and the staleness agent propagates to dependents."""
    f = VAULT / "deals" / deal / "assumptions" / f"{aid}.md"
    if not f.is_file():
        raise HTTPException(404, "assumption not found")
    text = f.read_text(encoding="utf-8")
    m = re.search(r"^version:\s*(\d+)", text, re.MULTILINE)
    version = (int(m.group(1)) if m else 1) + 1
    text = re.sub(r"^value:.*$", f'value: "{body.value}"', text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^version:.*$", f"version: {version}", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^state: proposed", "state: revised", text, count=1, flags=re.MULTILINE)
    if "## Revision history" in text:
        text += f"- v{version} ({datetime.now().date()}): {body.value} — {body.rationale or 'revised by human'}\n"
    f.write_text(text, encoding="utf-8")
    push()
    reindex()
    return {"id": aid, "version": version,
            "note": "staleness agent will flag dependents within seconds — watch the feed"}


class WorkstreamIn(BaseModel):
    workstream: str = "commercial_market"


@app.post("/api/agents/workstream/{deal}")
def agent_workstream(deal: str, body: WorkstreamIn):
    require_writable()
    """V1 step 3: run ONE workstream via LLM — structured findings tied to assumptions."""
    import shutil
    sync()
    ws = body.workstream
    odir = VAULT / "deals" / deal / "outputs"
    odir.mkdir(parents=True, exist_ok=True)
    n = len(list(odir.glob(f"wso-{deal}-{ws}-*.md"))) + 1
    oid = f"wso-{deal}-{ws}-{n:03d}"
    if not shutil.which("claude"):
        # cloud path: model proposes JSON findings; the server writes the typed output
        droot = VAULT / "deals" / deal
        ctx = "\n\n".join(f"### {f.relative_to(droot)}\n{f.read_text(encoding='utf-8')}"
                          for pat in ("questions/*.md", "assumptions/*.md", "claims/*.md")
                          for f in sorted(droot.glob(pat)))[:130_000]
        import contracts as _contracts
        eps = _contracts.workstream_schema(ws) or {}
        brain_ctx = "\n".join(f.read_text(encoding="utf-8")[:1500]
                              for f in (VAULT / "library" / "question-types").glob("*.md"))[:6000]
        data = _gateway_json(
            f"You are the PE OS workstream-runner for workstream '{ws}'.\n"
            f"YOUR EPISTEMIC CONTRACT (follow it): {json.dumps(eps)[:4000]}\n"
            f"FIRM BRAIN (cross-deal evidence archives — use what bears on your questions): {brain_ctx}\n"
            "From the deal context, produce findings "
            "grounded ONLY in the claims present (cite claim ids); weigh epistemic types (observed beats asserted); "
            "if claims contradict, mark the finding contested. Return ONLY JSON: "
            "{\"findings\":[{\"finding\":str,\"tied_to\":[assumption ids],\"direction\":\"supports|challenges\","
            "\"materiality\":\"high|medium|low\",\"established_from\":[claim ids],\"missing\":str}],\"open\":str}",
            f"DEAL CONTEXT ({deal}):\n{ctx}", max_tokens=6000)
        tied = sorted({a for f_ in data.get("findings", []) for a in f_.get("tied_to", [])})
        uses = sorted({c for f_ in data.get("findings", []) for c in f_.get("established_from", [])})
        lines = [f"# {ws} — findings\n"]
        for i, f_ in enumerate(data.get("findings", []), 1):
            lines += [f"## F{i} — {f_.get('finding','')}",
                      f"- Tied to: {' '.join(f'[[{a}]]' for a in f_.get('tied_to', []))} · direction: {f_.get('direction','')} · materiality: {f_.get('materiality','')}",
                      f"- Established from: {', '.join(f'[[{c}]]' for c in f_.get('established_from', []))}",
                      f"- Missing evidence that would settle it: {f_.get('missing','')}", ""]
        lines += ["## Open per this workstream", str(data.get("open", ""))]
        (odir / f"{oid}.md").write_text(f"""---
type: workstream-output
id: {oid}
deal: "[[{deal}]]"
workstream: {ws}
tied-to: [{', '.join(f'"[[{a}]]"' for a in tied)}]
uses: [{', '.join(f'"[[{c}]]"' for c in uses)}]
stale: false
supersedes: {f'"[[wso-{deal}-{ws}-{n-1:03d}]]"' if n > 1 else 'null'}
written-by: workstream-runner
produced: {datetime.now().date()}
---

""" + "\n".join(lines) + "\n", encoding="utf-8")
        push()
        reindex()
        return {"id": oid, "output": f"{oid}: {len(data.get('findings', []))} finding(s) written"}
    prompt = f"""You are the PE OS workstream-runner agent for workstream '{ws}'. Work autonomously; never ask questions.

Deal: {deal}. Read vault/ontology/workstream-output.md (schema), vault/deals/{deal}/deal.md, the questions in questions/ with target-workstream: {ws} (and their tests links), the assumptions in assumptions/, and ALL claims in claims/.

Produce ONE file: vault/deals/{deal}/outputs/{oid}.md following the schema exactly:
- frontmatter: type workstream-output, id {oid}, deal, workstream {ws}, tied-to = the assumption ids your findings bear on, uses = the claim ids consumed, stale: false, supersedes: {'wso-' + deal + '-' + ws + '-' + format(n-1, '03d') if n > 1 else 'null'}, written-by: workstream-runner, produced: today.
- body: numbered findings. Each finding: one line conclusion; Tied to: assumption id + direction (supports|challenges) + materiality (high|medium|low); Established from: claim ids; Missing evidence that would settle it. End with '## Open per this workstream'.
Rules: conclusions only from the claims present (cite them); never resolve questions; weigh epistemic types (observed beats asserted); if claims contradict, say the finding is contested and by what.
Finish by printing the file id and one line per finding."""
    try:
        r = subprocess.run(["claude", "-p", prompt, "--permission-mode", "acceptEdits"],
                           capture_output=True, text=True, cwd=ROOT, timeout=480)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "workstream run timed out")
    push()
    reindex()
    if not (odir / f"{oid}.md").exists():
        raise HTTPException(500, f"no output produced: {(r.stderr or r.stdout)[-300:]}")
    return {"id": oid, "output": r.stdout[-2000:]}


def _llm_text(system: str, user: str, max_tokens: int = 8000) -> str:
    """One model call. Prefers the Anthropic API key; falls back to Vercel AI Gateway.
    For claude-sonnet-5 uses adaptive thinking with effort=low so output is always a
    text block (not consumed by thinking tokens). Errors surface verbatim."""
    import urllib.request
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    try:
        if anthropic_key:
            model = os.environ.get("PEOS_MODEL", "claude-sonnet-5")
            payload = {"model": model, "max_tokens": max_tokens, "system": system,
                       "messages": [{"role": "user", "content": user}]}
            # claude-sonnet-5 uses adaptive thinking; set effort=low so extraction
            # stays in text blocks and doesn't exhaust the token budget thinking.
            if "sonnet-5" in model or "fable" in model:
                payload["thinking"] = {"type": "adaptive"}
                payload["output_config"] = {"effort": "low"}
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(payload).encode(), method="POST",
                headers={k: v for k, v in {
                    "Content-Type": "application/json", "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "anthropic-workspace-id": os.environ.get("ANTHROPIC_WORKSPACE_ID", "") or None,
                }.items() if v})
            with urllib.request.urlopen(req, timeout=280) as resp:
                blocks = json.loads(resp.read())["content"]
                text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
                if not text:
                    raise ValueError(f"no text block in response: {str(blocks)[:200]}")
                return text
        token = os.environ.get("VERCEL_OIDC_TOKEN") or os.environ.get("AI_GATEWAY_API_KEY")
        if not token:
            raise HTTPException(501, "no model access (no ANTHROPIC_API_KEY, no gateway token)")
        payload = {"model": os.environ.get("PEOS_GATEWAY_MODEL", "anthropic/claude-sonnet-4.6"),
                   "max_tokens": max_tokens,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        req = urllib.request.Request("https://ai-gateway.vercel.sh/v1/chat/completions",
                                     data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=280) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"]
    except HTTPException:
        raise
    except Exception as exc:
        detail = getattr(exc, "read", lambda: b"")()
        raise HTTPException(502, f"model error: {exc} {detail[:300] if detail else ''}")


def _gateway_json(system: str, user: str, max_tokens: int = 8000):
    text = _llm_text(system, user, max_tokens)
    # prefer ```json fences, then bare array/object
    fence = re.search(r"```(?:json)?\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```", text)
    m = fence or re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
    if not m:
        raise ValueError(f"model returned no JSON: {text[:200]}")
    raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # strip trailing comma before ] or } — common LLM mistake
        cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
        return json.loads(cleaned)


_EXTRACT_SYSTEM = """\
You are the PE OS extractor agent for a private equity firm.
Extract every discrete factual claim from the artifact that would be useful for deal analysis.

EPISTEMIC TYPING (get these right):
- asserted: document states a fact (seller CIM, management report)
- observed: direct observation or recorded interaction (meeting notes, call transcripts)
- attested: third-party verified (QoE firm certifies, auditor confirms)
- derived: you computed it from other values (requires derivation field)

SUBJECT NAMING (critical — prevents false contradictions):
- Use a DIFFERENT subject for each distinct EBITDA definition:
  "reported EBITDA", "seller-adjusted EBITDA", "QoE-normalized EBITDA",
  "firm-underwritten EBITDA", "covenant EBITDA" — never all under "EBITDA"
- Use a DIFFERENT subject for billing-account vs ultimate-parent concentration:
  "largest billing-account customer concentration" vs "largest ultimate-parent customer concentration"
- Reuse EXISTING subject strings when the exact same quantity/basis/definition is meant
- Create a NEW subject when definition, basis, party, or time period differs

Return ONLY a JSON array. Each element:
{"subject": "...", "value": "...", "epistemic": "asserted|derived|observed|attested",
 "bears_on": ["question-id", ...], "direction": "supports|contradicts|context",
 "locator": "section/line", "author": "party", "statement": "one complete sentence",
 "derivation": "computation string or null"}\
"""


def _brain_context(deal: str, max_chars: int = 5000) -> str:
    """Read question-type archives from the brain library relevant to this deal's questions.
    Returns a compact excerpt: methodology + top evidence entries per QT, capped at max_chars.
    This is how agents go from the knowledge graph → the brain when they need methodology."""
    c = con()
    # Find question-types linked from this deal's questions
    qt_ids = [row[0] for row in c.execute(
        "SELECT DISTINCT e2.dst FROM edges e1 JOIN edges e2 ON e1.dst=e2.src "
        "WHERE e1.rel='bears-on' AND e2.rel='question-type' "
        "AND e1.src IN (SELECT id FROM nodes WHERE type='claim' AND deal=?)", (deal,)
    ).fetchall()]
    c.close()
    if not qt_ids:
        qt_ids = [f.stem for f in (VAULT / "library" / "question-types").glob("qt-*.md")][:6]
    parts = []
    for qt_id in qt_ids[:8]:
        f = VAULT / "library" / "question-types" / f"{qt_id}.md"
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        # Include methodology + up to 5 evidence entries
        lines = text.splitlines()
        methodology = []
        evidence = []
        in_arch = False
        for ln in lines:
            if ln.startswith("## Evidence archive"):
                in_arch = True
                continue
            if in_arch:
                if ln.startswith("- [[") and len(evidence) < 5:
                    evidence.append(ln)
            elif not ln.startswith("---") and not ln.startswith("type:") and not ln.startswith("id:"):
                methodology.append(ln)
        excerpt = "\n".join(methodology[:20]) + ("\n\nCross-deal evidence:\n" + "\n".join(evidence) if evidence else "")
        parts.append(f"[{qt_id}]\n{excerpt.strip()}")
    result = "\n\n---\n".join(parts)
    return result[:max_chars] if result else "(brain library empty — run librarian)"


def cloud_extract(deal: str, artifact: Path) -> list[str]:
    """Extract claims from one artifact for one deal (works for any deal).
    Model proposes JSON; server writes files through the validated claim template.
    Reads from the brain library for methodology context before extracting.
    After extraction, automatically runs derivation pass if artifact has a
    customer concentration table."""
    q_dir = VAULT / "deals" / deal / "questions"
    questions = "\n".join(
        f"- {f.stem}: {f.read_text(encoding='utf-8').split('# ',1)[1].splitlines()[0]}"
        for f in sorted(q_dir.glob("*.md"))
    ) if q_dir.exists() else "(no questions defined yet)"
    existing_subjects = sorted({json.loads(fm).get("subject") for fm, in
                                con().execute("SELECT frontmatter FROM nodes WHERE type='claim' AND deal=?", (deal,))
                                if json.loads(fm).get("subject")})
    brain = _brain_context(deal)
    text = artifact.read_text(encoding="utf-8")[:100_000]
    data = _gateway_json(
        _EXTRACT_SYSTEM,
        f"DEAL: {deal}\nDEAL QUESTIONS:\n{questions}\n\n"
        f"FIRM BRAIN (cross-deal methodology — use subject names and epistemic standards from here):\n{brain}\n\n"
        f"EXISTING SUBJECTS (reuse when same quantity/basis): {existing_subjects}\n\n"
        f"ARTIFACT ({artifact.name}):\n{text}")
    written = []
    for item in data:
        if item.get("epistemic") not in EPISTEMIC:
            item["epistemic"] = "asserted"
        if item["epistemic"] == "derived" and not item.get("derivation"):
            item["epistemic"] = "asserted"
        c = ClaimIn(subject=str(item.get("subject", "?")), value=str(item.get("value", "?")),
                    epistemic=item["epistemic"], bears_on=[b for b in item.get("bears_on", []) if b],
                    direction=item.get("direction", "context"), locator=str(item.get("locator", "")),
                    author=str(item.get("author", "")), artifact=f"vault/inbox/{artifact.name}",
                    statement=str(item.get("statement", "")), derivation=item.get("derivation"))
        written.append(add_claim(deal, c)["id"])

    # Auto-run concentration derivation for data-room files with a customer schedule
    full_text = artifact.read_text(encoding="utf-8")
    if "ultimate parent" in full_text[:8000].lower() and "% revenue" in full_text[:8000].lower():
        try:
            sys.path.insert(0, str(ROOT / "tools"))
            import derive_concentrations as dc
            dc.derive_for_artifact(deal, artifact)
        except Exception:
            pass  # non-fatal; standard claims already written

    return written


@app.post("/api/agents/tick")
def agents_tick():
    """One full cycle of the agent fleet — the cloud equivalent of the local
    runtime's loop. Sync down, work, push up. Every action lands in the audit log."""
    require_writable()
    sync()
    sys.path.insert(0, str(ROOT / "agents"))
    import runtime as rt
    reindex()
    report = []
    # sentinel: announce unannounced inbox artifacts
    sent = rt.Sentinel()
    sent.act(list(sent.snapshot().keys()))
    # extractor: one unextracted text artifact per tick (bounded runtime)
    st = rt._state()
    done = set(st.get("extracted", []))
    for f in sorted((VAULT / "inbox").glob("*")):
        if f.suffix.lower() in (".md", ".txt") and f.name not in done and f.stat().st_size < 150_000:
            deal = rt.deal_for(f.name)
            if not deal:
                continue
            try:
                ids = cloud_extract(deal, f)
                rt.audit("extractor", "HVA_COMMERCIAL_01", "claims-extracted",
                         f"{f.name} → {len(ids)} claim(s) via gateway", ids)
                report.append(f"extracted {f.name}: {len(ids)} claims")
            except Exception as exc:
                rt.audit("extractor", "HVA_COMMERCIAL_01", "error", f"{f.name}: {exc}", [])
                report.append(f"extract error {f.name}: {exc}")
            st = rt._state(); st.setdefault("extracted", []).append(f.name); rt._save(st)
            break
    # deterministic fleet
    for cls in (rt.StateResolver, rt.Contradiction, rt.Librarian, rt.Coordinator, rt.Staleness):
        a = cls()
        try:
            a.act(list(a.snapshot().keys()))
            report.append(f"{a.id}: ran")
        except Exception as exc:
            rt.audit(a.id, a.activity_id, "error", str(exc), [])
            report.append(f"{a.id}: error {exc}")
    push()
    reindex()
    return {"report": report}


def _flow_file():
    return VAULT / "flows" / "flow.json"


@app.get("/canvas")
def canvas_page():
    return FileResponse(ROOT / "app" / "static" / "canvas.html")


@app.get("/graph")
def graph_page():
    return FileResponse(ROOT / "app" / "static" / "graph.html")


@app.get("/preview")
def preview_page():
    return FileResponse(ROOT / "app" / "static" / "preview.html")


@app.get("/pipeline")
def pipeline_page():
    return FileResponse(ROOT / "app" / "static" / "pipeline.html")


@app.get("/api/graph")
def api_graph(deal: str | None = None):
    """Part A: knowledge graph — nodes + edges from the SQLite index.
    Firm-wide by default; filter by deal when ?deal= given. Calls sync+reindex
    first so the view is never stale. Returns stale flag, epistemic type, degree."""
    sync()
    reindex()
    # The live Keystone path has a richer semantic Current graph than the
    # vault index alone: it carries source→claim, question, case-position,
    # support/contradiction and coverage-condition edges. Prefer it when it
    # exists so the test viewer and V20 read the same semantic state.
    semantic = ROOT / "pipeline_out" / "e3" / "K-IC" / "adapter_alpha" / "semantic_current_graph.json"
    if deal and semantic.exists():
        graph = json.loads(semantic.read_text(encoding="utf-8"))
        nodes = [
            {"id": n.get("id"), "type": n.get("type", "unknown"),
             "title": n.get("label") or n.get("title") or n.get("id"),
             "deal": deal, "state": n.get("decision_status") or n.get("coverage_status"),
             "epistemic": n.get("epistemic"), "stale": False, "degree": 0}
            for n in graph.get("nodes", [])
        ]
        degree: dict[str, int] = {}
        for edge in graph.get("edges", []):
            degree[edge.get("source")] = degree.get(edge.get("source"), 0) + 1
            degree[edge.get("target")] = degree.get(edge.get("target"), 0) + 1
        for node in nodes:
            node["degree"] = degree.get(node["id"], 0)
        return {"nodes": nodes, "links": [
            {"source": e.get("source"), "target": e.get("target"), "rel": e.get("rel", "")}
            for e in graph.get("edges", [])
        ]}
    c = con()
    if deal:
        node_rows = c.execute(
            "SELECT id, type, title, deal, state, epistemic, frontmatter FROM nodes WHERE deal=?",
            (deal,)).fetchall()
    else:
        node_rows = c.execute(
            "SELECT id, type, title, deal, state, epistemic, frontmatter FROM nodes").fetchall()
    # compute degree map
    ids = {r[0] for r in node_rows}
    degree: dict[str, int] = {}
    for nid in ids:
        d_out = c.execute("SELECT COUNT(*) FROM edges WHERE src=?", (nid,)).fetchone()[0]
        d_in  = c.execute("SELECT COUNT(*) FROM edges WHERE dst=?", (nid,)).fetchone()[0]
        degree[nid] = d_out + d_in
    nodes = []
    for nid, ntype, title, ndeal, state, epistemic, fm_raw in node_rows:
        fm = json.loads(fm_raw) if fm_raw else {}
        stale = bool(fm.get("stale"))
        nodes.append({"id": nid, "type": ntype or "unknown", "title": title or nid,
                      "deal": ndeal, "state": state, "epistemic": epistemic,
                      "stale": stale, "degree": degree.get(nid, 0)})
    if deal:
        edge_rows = c.execute(
            "SELECT e.src, e.dst, e.rel FROM edges e "
            "JOIN nodes s ON s.id=e.src JOIN nodes t ON t.id=e.dst "
            "WHERE s.deal=? OR t.deal=?", (deal, deal)).fetchall()
    else:
        edge_rows = c.execute("SELECT src, dst, rel FROM edges").fetchall()
    links = [{"source": src, "target": dst, "rel": rel} for src, dst, rel in edge_rows]
    c.close()
    return {"nodes": nodes, "links": links}


@app.get("/api/node/{node_id:path}")
def api_node(node_id: str):
    """Part A: raw markdown content of a node from nodes.path. Used by the graph
    side-panel click to show file content without a separate vault read."""
    sync()
    reindex()
    c = con()
    row = c.execute("SELECT path, frontmatter, title FROM nodes WHERE id=?", (node_id,)).fetchone()
    c.close()
    if not row:
        raise HTTPException(404, f"node not found: {node_id}")
    fpath, fm_raw, title = row
    full = VAULT / fpath
    if not full.exists():
        raise HTTPException(404, f"file missing from vault: {fpath}")
    content = full.read_text(encoding="utf-8")
    fm = json.loads(fm_raw) if fm_raw else {}
    return {"id": node_id, "path": fpath, "title": title, "frontmatter": fm, "content": content}


@app.get("/api/flow")
def get_flow():
    sync()
    f = _flow_file()
    return json.loads(f.read_text()) if f.exists() else {"nodes": [], "edges": []}


@app.put("/api/flow")
def put_flow(flow: dict):
    require_writable()
    sync()
    f = _flow_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(flow, indent=1))
    push()
    return {"ok": True}


class RunIn(BaseModel):
    config: dict = {}


@app.post("/api/agents/run/{kind}")
def run_agent(kind: str, body: RunIn):
    """Canvas executor: one agent, one unit of work, summary out. Same policy
    rows and audit trail as always — the canvas is just another trigger."""
    require_writable()
    sync()
    sys.path.insert(0, str(ROOT / "agents"))
    import runtime as rt
    reindex()
    deal = body.config.get("deal") or (rt.deals()[0] if len(rt.deals()) == 1 else body.config.get("deal", ""))
    try:
        if kind == "extractor":
            st = rt._state(); done = set(st.get("extracted", []))
            skipped = []
            for f in sorted((VAULT / "inbox").glob("*")):
                if not f.is_file() or f.name.startswith("."):
                    continue
                if f.name in done:
                    continue
                if f.suffix.lower() not in (".md", ".txt"):
                    skipped.append(f"{f.name}: {f.suffix} not extractable — convert to .md/.txt")
                    continue
                if f.stat().st_size >= 150_000:
                    skipped.append(f"{f.name}: too large (>150KB)")
                    continue
                d = rt.deal_for(f.name) or body.config.get("deal")  # filename routing wins; config is fallback
                if not d:
                    skipped.append(f"{f.name}: cannot route — {len(rt.deals())} deals exist; rename to <deal>-{f.name}")
                    continue
                if body.config.get("deal") and d != body.config.get("deal"):
                    continue  # config scopes the run to one deal; other deals' files wait their turn
                ids = cloud_extract(d, f)
                st = rt._state(); st.setdefault("extracted", []).append(f.name); rt._save(st)
                rt.audit("extractor", "HVA_COMMERCIAL_01", "claims-extracted", f"{f.name} → {len(ids)}", ids)
                push(); reindex()
                return {"summary": f"{f.name} → {len(ids)} claims"}
            return {"summary": "nothing to extract" + ("; skipped → " + " | ".join(skipped) if skipped else " — inbox has no new text files")}
        if kind == "workstream":
            r = agent_workstream(deal, WorkstreamIn(workstream=body.config.get("workstream", "commercial_market")))
            return {"summary": r["output"][-200:]}
        if kind == "ask":
            return {"summary": _ask_via_gateway(body.config.get("question", "summarize the open risks"))[:600]}
        if kind == "phase-coordinator":
            a = rt.PhaseCoordinator()
            result = a.run(deal)
            push(); reindex()
            return {"summary": result["summary"], "proposed": result.get("proposed", [])}
        if kind == "ic-assembler":
            a = rt.IcAssembler()
            result = a.run(deal)
            push(); reindex()
            return {"summary": result["summary"]}
        cls = {"sentinel": rt.Sentinel, "state-resolver": rt.StateResolver, "contradiction": rt.Contradiction,
               "librarian": rt.Librarian, "coordinator": rt.Coordinator, "staleness": rt.Staleness,
               "proposer": rt.Proposer}.get(kind)
        if not cls:
            raise HTTPException(404, f"unknown agent kind: {kind}")
        a = cls()
        a.act(list(a.snapshot().keys()))
        push(); reindex()
        return {"summary": f"{kind}: ran over current graph"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"{kind}: {exc}")


class AskIn(BaseModel):
    question: str


class ChatMsg(BaseModel):
    message: str
    deal: str | None = None
    history: list[dict] = []  # [{role: "user"|"assistant", content: str}]


def _vault_context(cap: int = 160_000) -> str:
    """Compact textual snapshot of the graph for cloud inference (read-only)."""
    parts = []
    for pat in ("deals/*/deal.md", "deals/*/questions/*.md", "deals/*/assumptions/*.md",
                "deals/*/claims/*.md", "library/question-types/*.md"):
        for f in sorted(VAULT.glob(pat)):
            parts.append(f"### {f.relative_to(VAULT)}\n{f.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)[:cap]


def _ask_via_gateway(question: str) -> str:
    return _llm_text(
        "You are the PE OS brain interface. Answer strictly from the vault snapshot provided. "
        "Cite file ids like [c-astrelia-002]. Weigh epistemic types (attested>observed>derived>asserted). "
        "If the vault does not contain the answer, say so plainly.",
        f"VAULT SNAPSHOT:\n{_vault_context()}\n\nQUESTION: {question}", max_tokens=1200)


@app.post("/api/agents/ask")
def agent_ask(body: AskIn):
    """Chat with the brain (policy rows 1+3). Local: headless Claude with read-only
    tools over the vault. Cloud: AI Gateway with a vault snapshot in-context."""
    import shutil
    if not shutil.which("claude"):
        return {"answer": _ask_via_gateway(body.question)}
    prompt = (
        "You are the PE OS brain interface. Answer the user's question strictly from the "
        "contents of vault/ (questions, claims with epistemic types, events, decisions, "
        "question-type archives, entities). Cite file ids like [c-astrelia-002]. Distinguish "
        "epistemic types when weighing evidence. If the vault does not contain the answer, "
        f"say so plainly.\n\nQuestion: {body.question}"
    )
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools", "Read,Grep,Glob"],
            capture_output=True, text=True, cwd=ROOT, timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "brain query timed out (5 min)")
    if r.returncode != 0:
        raise HTTPException(500, (r.stderr or r.stdout)[-500:])
    return {"answer": r.stdout.strip()}


# ---------------------------------------------------------------- brain chat (SSE, agentic loop)

def _chat_brain_methodology(max_chars: int = 9000) -> str:
    """Compact methodology excerpt from every brain QT — injected into the system prompt
    so Claude always has the firm's epistemic standards without needing a tool call."""
    qt_files = sorted((VAULT / "library" / "question-types").glob("qt-*.md"))
    parts = []
    for f in qt_files:
        text = f.read_text(encoding="utf-8")
        lines = text.splitlines()
        heading = next((ln.lstrip("# ") for ln in lines if ln.startswith("# ")), f.stem)
        body: list[str] = []
        in_evidence = False
        for ln in lines:
            if ln.startswith("## Evidence archive"):
                in_evidence = True
            if in_evidence:
                continue
            if ln.startswith("---") or ln.startswith("type:") or ln.startswith("id:") \
               or ln.startswith("domain:") or ln.startswith("decomposes") or ln.startswith("written-by:"):
                continue
            body.append(ln)
        excerpt = "\n".join(body).strip()[:400]
        parts.append(f"[{f.stem}]\n{heading}\n{excerpt}")
    return ("\n\n---\n".join(parts))[:max_chars]


_CHAT_TOOLS = [
    {
        "name": "query_brain",
        "description": (
            "Query the PE OS knowledge vault. Use this to answer factual questions about what is stored. "
            "query_type: 'stats'=graph totals, 'deals'=list all deals, 'questions'=deal questions, "
            "'claims'=claim summary, 'assumptions'=deal assumptions, 'question_types'=brain library."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["stats", "deals", "questions", "claims", "assumptions", "question_types"],
                },
                "deal": {"type": "string", "description": "Deal ID e.g. 'keystone'. Required for questions/claims/assumptions."},
                "filter": {"type": "string", "description": "Optional text filter on results."},
            },
            "required": ["query_type"],
        },
    },
    {
        "name": "run_contradiction_check",
        "description": "Run the contradiction detector on a deal — groups all claims by subject and surfaces any with conflicting values.",
        "input_schema": {
            "type": "object",
            "properties": {"deal": {"type": "string", "description": "Deal ID to check."}},
            "required": ["deal"],
        },
    },
    {
        "name": "run_lifecycle_state",
        "description": "Replay the deal's event history through the state machine and return the current lifecycle state plus recent event trail.",
        "input_schema": {
            "type": "object",
            "properties": {"deal": {"type": "string", "description": "Deal ID."}},
            "required": ["deal"],
        },
    },
    {
        "name": "read_question_type",
        "description": (
            "Read the full content of a brain question type — methodology, epistemic standards, "
            "and the cross-deal evidence archive the librarian maintains. Use this when you need "
            "deep methodology or want to see what the firm has learned about a question type across deals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "qt_id": {"type": "string", "description": "Question type ID e.g. 'qt-customer-concentration', 'qt-ebitda-quality'"},
            },
            "required": ["qt_id"],
        },
    },
    {
        "name": "find_claims",
        "description": (
            "Search the vault for claims matching a free-text query. ALWAYS call this first when "
            "the user asks a factual question about a deal (e.g. 'did X happen?', 'what is the EBITDA?', "
            "'was the equity cure used?'). Returns claims ranked by epistemic precedence: attested (★) "
            "first, then observed (◉), derived (◎), asserted (○). If an attested or observed claim "
            "directly answers the question, cite it and let it override model reasoning."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text question or keywords to search for in claim subjects and values."},
                "deal": {"type": "string", "description": "Optional deal ID to restrict search (e.g. 'keystone')."},
                "as_of": {"type": "string", "description": "Optional YYYY-MM-DD date. When set, only claims whose source date or extracted date is on or before this date are returned. Use this for point-in-time questions like 'what did we know as of the IC meeting?'"},
            },
            "required": ["query"],
        },
    },
]


_EPISTEMIC_RANK = {"attested": 0, "observed": 1, "derived": 2, "asserted": 3}
_EPISTEMIC_BADGE = {"attested": "★", "observed": "◉", "derived": "◎", "asserted": "○"}
_STOP_WORDS = {
    "the", "a", "an", "is", "was", "did", "does", "what", "how", "why", "when",
    "which", "that", "this", "it", "in", "on", "at", "to", "of", "for", "and",
    "or", "do", "not", "has", "have", "been", "be", "are", "were", "with", "by",
}


def _chat_tool_find_claims(inputs: dict) -> dict:
    """Vault-first claim lookup ranked by epistemic precedence + relevance score (F6)."""
    query = str(inputs.get("query", ""))
    deal = inputs.get("deal")
    as_of = inputs.get("as_of")  # optional YYYY-MM-DD point-in-time filter

    # Strip deal name from keywords when deal is scoped (it matches everything in that deal)
    stop_extra = {deal.lower()} if deal else set()
    keywords = [
        w.lower().strip("?.,!;:'\"")
        for w in query.split()
        if w.lower().strip("?.,!;:'\"") not in (_STOP_WORDS | stop_extra) and len(w) > 2
    ]

    c = con()
    try:
        base_q = "SELECT id, epistemic, subject, frontmatter, extracted FROM nodes WHERE type='claim'"
        params: list = []
        if deal:
            base_q += " AND deal=?"
            params.append(deal)
        if keywords:
            # OR across keywords — we'll score in Python
            conds = []
            for kw in keywords[:6]:
                conds.append(
                    "(LOWER(COALESCE(subject,'')) LIKE ? OR LOWER(COALESCE(value,'')) LIKE ?"
                    " OR LOWER(frontmatter) LIKE ?)"
                )
                params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
            base_q += " AND (" + " OR ".join(conds) + ")"
        rows = c.execute(base_q, params).fetchall()
    finally:
        c.close()

    results = []
    for cid, ep_col, subj_col, fm_raw, extracted_col in rows:
        fm = json.loads(fm_raw or "{}")
        ep = ep_col or fm.get("epistemic", "asserted")
        source = fm.get("source", {}) or {}
        artifact = source.get("artifact", fm.get("artifact", ""))
        locator = source.get("locator", fm.get("locator", ""))
        art_short = str(artifact).split("/")[-1].replace(".md", "") if artifact else ""
        provenance = " · ".join(filter(None, [art_short, locator]))
        source_date = str(source.get("date") or fm.get("extracted") or extracted_col or "")
        value = fm.get("value", fm.get("statement", ""))
        subject = fm.get("subject", subj_col or "")

        # as_of filter: skip claims whose source date is after the as_of cutoff
        if as_of and source_date and source_date > as_of:
            continue

        # Relevance score: count how many keywords match in subject+value
        haystack = (f"{subject} {value}").lower()
        score = sum(1 for kw in keywords if kw in haystack)

        results.append({
            "id": cid,
            "epistemic": ep,
            "ep_rank": _EPISTEMIC_RANK.get(ep, 99),
            "score": score,
            "subject": subject,
            "value": value,
            "provenance": provenance,
            "source_date": source_date,
        })

    # Sort: best relevance among attested/observed first, then fall back to all epistemic tiers
    results.sort(key=lambda r: (r["ep_rank"], -r["score"], r["id"]))

    if not results:
        asof_note = f" as of {as_of}" if as_of else ""
        return {
            "steps": [f"Searched vault for: {query!r}{asof_note} — keywords: {keywords}"],
            "output": f"No vault claims match this query{asof_note}.",
        }

    lines = []
    for r in results[:8]:
        badge = _EPISTEMIC_BADGE.get(r["epistemic"], "?")
        prov = f"  [{r['provenance']}]" if r["provenance"] else ""
        date = f"  ({r['source_date']})" if r["source_date"] else ""
        val = str(r["value"])[:150]
        lines.append(f"{badge} {r['id']} ({r['epistemic']}, score={r['score']})  {r['subject']}\n    → {val}{prov}{date}")

    top = results[0]
    asof_note = f" (as-of {as_of})" if as_of else ""
    steps = [
        f"Searched vault for: {query!r}{asof_note} (keywords: {keywords})",
        f"Found {len(results)} claim(s) — top: {top['id']} ({top['epistemic']}, score={top['score']})",
    ]
    if top["ep_rank"] <= 1:
        steps.append(
            f"VAULT-AUTHORITATIVE: {top['id']} ({top['epistemic']}) overrides model inference — cite this claim."
        )

    return {"steps": steps, "output": "\n".join(lines)}


def _chat_tool_query_brain(inputs: dict) -> dict:
    q_type = inputs.get("query_type", "stats")
    deal = inputs.get("deal")
    filt = (inputs.get("filter") or "").lower()
    steps = []
    c = con()
    try:
        if q_type == "stats":
            steps.append("Counting nodes and edges in the knowledge graph...")
            total = c.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            n_deals = c.execute("SELECT COUNT(*) FROM nodes WHERE type='deal'").fetchone()[0]
            n_q = c.execute("SELECT COUNT(*) FROM nodes WHERE type='question'").fetchone()[0]
            n_c = c.execute("SELECT COUNT(*) FROM nodes WHERE type='claim'").fetchone()[0]
            n_e = c.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            steps.append(f"Graph: {total} nodes · {n_e} edges")
            output = f"{n_deals} deals · {n_q} questions · {n_c} claims · {n_e} edges in the knowledge graph"

        elif q_type == "deals":
            steps.append("Loading deal list from the vault...")
            deal_rows = c.execute(
                "SELECT id, state FROM nodes WHERE type='deal' ORDER BY id"
            ).fetchall()
            parts = []
            for d_id, state in deal_rows:
                if filt and filt not in d_id.lower():
                    continue
                n_q = c.execute("SELECT COUNT(*) FROM nodes WHERE type='question' AND deal=?", (d_id,)).fetchone()[0]
                n_c = c.execute("SELECT COUNT(*) FROM nodes WHERE type='claim' AND deal=?", (d_id,)).fetchone()[0]
                parts.append(f"• {d_id}: state={state or '?'} · {n_q} questions · {n_c} claims")
            steps.append(f"Found {len(deal_rows)} deals")
            output = "\n".join(parts) if parts else "No deals found."

        elif q_type == "questions" and deal:
            steps.append(f"Loading questions for deal '{deal}'...")
            q_rows = c.execute(
                "SELECT id, state, title, frontmatter FROM nodes WHERE type='question' AND deal=? ORDER BY id",
                (deal,),
            ).fetchall()
            n_crit = sum(1 for _, st, _, fm in q_rows
                         if json.loads(fm or "{}").get("critical") and st in ("open", "reducing"))
            steps.append(f"Found {len(q_rows)} questions · {n_crit} critical open")
            parts = []
            for qid, state, title, fm_raw in q_rows:
                if filt and filt not in (qid + (title or "")).lower():
                    continue
                critical = "⚠ " if json.loads(fm_raw or "{}").get("critical") else ""
                parts.append(f"• {critical}{qid} [{state}]: {title or '(no title)'}")
            output = "\n".join(parts) if parts else "No questions found."

        elif q_type == "claims" and deal:
            steps.append(f"Summarising claims for deal '{deal}'...")
            total_c = c.execute(
                "SELECT COUNT(*) FROM nodes WHERE type='claim' AND deal=?", (deal,)
            ).fetchone()[0]
            by_epi = c.execute(
                "SELECT epistemic, COUNT(*) FROM nodes WHERE type='claim' AND deal=? GROUP BY epistemic",
                (deal,),
            ).fetchall()
            bound = c.execute(
                "SELECT COUNT(DISTINCT e.src) FROM edges e JOIN nodes n ON e.src=n.id "
                "WHERE n.type='claim' AND n.deal=? AND e.rel='bears-on'",
                (deal,),
            ).fetchone()[0]
            steps.append(f"{total_c} claims · {bound} bound to questions")
            epi_str = " · ".join(f"{ep or '?'}={cnt}" for ep, cnt in by_epi)
            output = f"{total_c} claims ({epi_str})\n{bound} bound to questions · {total_c - bound} unbound"

        elif q_type == "assumptions" and deal:
            steps.append(f"Loading assumptions for deal '{deal}'...")
            a_rows = c.execute(
                "SELECT id, frontmatter FROM nodes WHERE type='assumption' AND deal=? ORDER BY id",
                (deal,),
            ).fetchall()
            parts = []
            for aid, fm_raw in a_rows:
                fm = json.loads(fm_raw or "{}")
                stmt = fm.get("statement", "")
                if filt and filt not in (aid + stmt).lower():
                    continue
                parts.append(f"• {aid} [{fm.get('state', '?')}]: {stmt[:90]}")
            steps.append(f"Found {len(a_rows)} assumptions")
            output = "\n".join(parts) if parts else "No assumptions found."

        elif q_type == "question_types":
            steps.append("Loading brain question-type library...")
            qt_files = sorted((VAULT / "library" / "question-types").glob("qt-*.md"))
            parts = []
            for f in qt_files:
                heading = next((ln.lstrip("# ") for ln in f.read_text(encoding="utf-8").splitlines()
                                if ln.startswith("# ")), f.stem)
                if not filt or filt in (f.stem + heading).lower():
                    parts.append(f"• {f.stem}: {heading}")
            steps.append(f"Found {len(qt_files)} question types in the brain")
            output = "\n".join(parts) if parts else "Brain library empty."
        else:
            output = f"query_type '{q_type}' requires a 'deal' parameter." if not deal else f"Unknown query_type '{q_type}'."
    finally:
        c.close()
    return {"steps": steps, "output": output}


def _chat_tool_contradiction(inputs: dict) -> dict:
    deal = inputs.get("deal", "")
    steps = [f"Scanning claims for deal '{deal}' grouped by subject..."]
    c = con()
    try:
        total = c.execute(
            "SELECT COUNT(*) FROM nodes WHERE type='claim' AND deal=?", (deal,)
        ).fetchone()[0]
        steps.append(f"Found {total} claims — grouping by subject, looking for value conflicts...")
        rows_data = c.execute(
            "SELECT subject, COUNT(DISTINCT value) as cnt, "
            "GROUP_CONCAT(id || ' [' || COALESCE(epistemic,'?') || ']=' || COALESCE(value,'?'), ' | ') "
            "FROM nodes WHERE type='claim' AND deal=? AND subject IS NOT NULL "
            "GROUP BY subject HAVING COUNT(DISTINCT value) > 1",
            (deal,),
        ).fetchall()
    finally:
        c.close()
    if not rows_data:
        steps.append("All subjects have consistent values — no contradictions detected.")
        return {"steps": steps, "output": "No contradictions detected."}
    steps.append(f"Found {len(rows_data)} subject(s) with conflicting values.")
    lines = []
    for subject, cnt, claims_str in rows_data:
        lines.append(f"SUBJECT: {subject}  ({cnt} distinct values)")
        for part in claims_str.split(" | ")[:6]:
            lines.append(f"  {part}")
        lines.append("")
    return {"steps": steps, "output": f"{len(rows_data)} contradiction(s):\n\n" + "\n".join(lines)}


def _chat_tool_lifecycle(inputs: dict) -> dict:
    deal = inputs.get("deal", "")
    steps = [f"Loading events for deal '{deal}'..."]
    c = con()
    try:
        ev_rows = c.execute(
            "SELECT frontmatter FROM nodes WHERE type='event' AND deal=? ORDER BY id", (deal,)
        ).fetchall()
        q_rows = c.execute(
            "SELECT frontmatter FROM nodes WHERE type='question' AND deal=?", (deal,)
        ).fetchall()
    finally:
        c.close()
    events = [json.loads(r[0]) for r in ev_rows]
    questions = [json.loads(r[0]) for r in q_rows]
    steps.append(f"Replaying {len(events)} events through the 46-transition state machine contracts...")
    crit_open = [q for q in questions if q.get("critical") and q.get("state") in ("open", "reducing")]
    state, trail, held = replay(events, load_transitions(), crit_open)
    steps.append(f"Derived state: {state_label(state)} ({state})")
    if held:
        steps.append(f"⚠ {len(held)} transition(s) HELD by guards")
    trail_lines = []
    for ev, frm, t, blocked in trail[-12:]:
        to = t["to"] if t else frm
        marker = " [HELD]" if blocked else ""
        trail_lines.append(f"• {str(ev.get('at', ''))[:10]}  {ev.get('kind', '?')}  →  {state_label(to)}{marker}")
    output = f"State: {state_label(state)} ({state})\n\nEvent trail (last {len(trail_lines)}):\n" + "\n".join(trail_lines)
    if held:
        output += "\n\n⚠ Held: " + ", ".join(t["id"] for t in held)
    return {"steps": steps, "output": output}


def _chat_tool_read_qt(inputs: dict) -> dict:
    qt_id = inputs.get("qt_id", "").strip()
    f = VAULT / "library" / "question-types" / f"{qt_id}.md"
    if not f.exists():
        # fuzzy match
        matches = [x for x in (VAULT / "library" / "question-types").glob("qt-*.md")
                   if qt_id.lower().replace("qt-", "") in x.stem.lower()]
        if matches:
            f = matches[0]
            qt_id = f.stem
        else:
            return {"steps": [f"No QT found for '{qt_id}'"],
                    "output": f"Question type '{qt_id}' not found. Available: " +
                              ", ".join(x.stem for x in sorted(
                                  (VAULT / "library" / "question-types").glob("qt-*.md")))}
    steps = [f"Reading brain QT: {qt_id}"]
    content = f.read_text(encoding="utf-8")
    # count evidence entries
    n_evidence = content.count("\n- [[")
    steps.append(f"Found methodology + {n_evidence} cross-deal evidence entries")
    return {"steps": steps, "output": content[:6000]}


def _chat_execute_tool(name: str, inputs: dict) -> dict:
    if name == "find_claims":
        return _chat_tool_find_claims(inputs)
    if name == "query_brain":
        return _chat_tool_query_brain(inputs)
    if name == "run_contradiction_check":
        return _chat_tool_contradiction(inputs)
    if name == "run_lifecycle_state":
        return _chat_tool_lifecycle(inputs)
    if name == "read_question_type":
        return _chat_tool_read_qt(inputs)
    return {"steps": [], "output": f"unknown tool: {name}"}


def _chat_api_call(messages: list, system: str) -> dict:
    import urllib.request
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — cannot use brain chat")
    model = os.environ.get("PEOS_MODEL", "claude-sonnet-5")
    payload: dict = {
        "model": model, "max_tokens": 4000,
        "system": system, "messages": messages,
        "tools": _CHAT_TOOLS, "tool_choice": {"type": "auto"},
    }
    if "sonnet-5" in model or "fable" in model:
        payload["thinking"] = {"type": "adaptive"}
        payload["output_config"] = {"effort": "low"}
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


async def _chat_stream(message: str, deal: str | None = None, history: list[dict] | None = None):
    def sse(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    # ── Step 1: load vault context + brain methodology ──────────────────
    yield sse({"type": "agent_start", "agent": "brain", "label": "Loading vault + brain..."})
    brain_methodology = ""
    n_qt = 0
    try:
        c = con()
        n_deals = c.execute("SELECT COUNT(*) FROM nodes WHERE type='deal'").fetchone()[0]
        n_q = c.execute("SELECT COUNT(*) FROM nodes WHERE type='question'").fetchone()[0]
        n_c = c.execute("SELECT COUNT(*) FROM nodes WHERE type='claim'").fetchone()[0]
        deal_list = [r[0] for r in c.execute("SELECT id FROM nodes WHERE type='deal' ORDER BY id").fetchall()]
        n_qt = len(list((VAULT / "library" / "question-types").glob("qt-*.md")))
        c.close()
        context_line = (f"{n_deals} deals ({', '.join(deal_list)}) · "
                        f"{n_q} questions · {n_c} claims · {n_qt} brain question types")
        yield sse({"type": "agent_step", "agent": "brain", "content": context_line})
        brain_methodology = _chat_brain_methodology()
        yield sse({"type": "agent_step", "agent": "brain",
                   "content": f"Brain loaded: {n_qt} question-type methodologies"})
    except Exception as exc:
        context_line = "vault index unavailable — run make index"
        yield sse({"type": "agent_step", "agent": "brain", "content": f"Index error: {exc}"})
    yield sse({"type": "agent_done", "agent": "brain"})

    # ── Step 2: agentic loop ─────────────────────────────────────────────
    # Build initial messages from prior turns then append current message
    prior: list[dict] = []
    for turn in (history or []):
        role = turn.get("role", "")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            prior.append({"role": role, "content": content})

    system = f"""You are the PE OS assistant — an AI operating system for private equity deal intelligence.

The vault is a typed knowledge graph: deals, questions (open→resolved), claims (epistemic type: attested > observed > derived > asserted), events (lifecycle triggers), assumptions, decisions, and a brain library of {n_qt} cross-deal question types.

Current vault: {context_line}.{f" Focus: {deal}" if deal else ""}

## Epistemic-first retrieval (MANDATORY)

For ANY factual question about a deal — "did X happen?", "what is the EBITDA?", "was the equity cure used?", "what is the debt?" — you MUST call `find_claims` first with relevant keywords before answering. This is not optional.

The vault uses epistemic precedence: attested (★) > observed (◉) > derived (◎) > asserted (○).
- If `find_claims` returns a ★ attested or ◉ observed claim that answers the question, CITE IT and let it override your model reasoning. Do not contradict vault-authoritative claims.
- Always cite the claim ID (e.g. c-keystone-041) when vault evidence exists.
- Only use model inference when no vault claim covers the question.

Key concepts:
- Contradictions: same subject, irreconcilable values across claims — flagged by agents, never adjudicated
- Lifecycle: S0 intake → S13 archive, 46 state machine transitions, some with guards (e.g. no IC while critical questions are open)
- Brain library = cross-deal evidence archives; use read_question_type to get the full evidence archive for any QT

BRAIN — FIRM METHODOLOGY ({n_qt} question types, methodology only; use read_question_type for the evidence archive):
{brain_methodology}"""

    messages = prior + [{"role": "user", "content": message}]
    for _round in range(6):
        try:
            resp = await asyncio.to_thread(_chat_api_call, messages, system)
        except Exception as exc:
            yield sse({"type": "error", "content": str(exc)})
            break

        content_blocks = resp.get("content", [])
        thinking_parts = [b["thinking"] for b in content_blocks if b.get("type") == "thinking" and b.get("thinking")]
        text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
        tool_calls = [b for b in content_blocks if b.get("type") == "tool_use"]

        if thinking_parts:
            yield sse({"type": "thinking", "content": "\n\n".join(thinking_parts)})

        if text_parts:
            yield sse({"type": "text", "content": "".join(text_parts)})

        if resp.get("stop_reason") == "end_turn" or not tool_calls:
            break

        messages.append({"role": "assistant", "content": content_blocks})
        tool_results = []
        for tc in tool_calls:
            name, inputs, tc_id = tc["name"], tc["input"], tc["id"]
            label = {
                "query_brain": f"Query vault · {inputs.get('query_type', '')}" + (f" · {inputs['deal']}" if inputs.get("deal") else ""),
                "run_contradiction_check": f"Contradiction check · {inputs.get('deal', '')}",
                "run_lifecycle_state": f"Lifecycle replay · {inputs.get('deal', '')}",
            }.get(name, name)
            yield sse({"type": "agent_start", "agent": name, "label": label})
            try:
                result = await asyncio.to_thread(_chat_execute_tool, name, inputs)
                for step in result["steps"]:
                    yield sse({"type": "agent_step", "agent": name, "content": step})
                yield sse({"type": "agent_result", "agent": name, "content": result["output"]})
                yield sse({"type": "agent_done", "agent": name})
                tool_results.append({"type": "tool_result", "tool_use_id": tc_id, "content": result["output"]})
            except Exception as exc:
                yield sse({"type": "agent_step", "agent": name, "content": f"Error: {exc}"})
                yield sse({"type": "agent_done", "agent": name})
                tool_results.append({"type": "tool_result", "tool_use_id": tc_id, "content": f"Error: {exc}"})
        messages.append({"role": "user", "content": tool_results})

    yield sse({"type": "done"})


@app.get("/chat")
def chat_page():
    return FileResponse(ROOT / "app" / "static" / "chat.html")


@app.post("/api/chat")
async def chat_endpoint(msg: ChatMsg):
    return StreamingResponse(
        _chat_stream(msg.message, msg.deal, msg.history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------- audit

@app.get("/api/audit")
def audit_log(n: int = 20):
    sync()
    f = VAULT / "audit" / "agent-log.jsonl"
    if not f.exists():
        return []
    lines = f.read_text(encoding="utf-8").strip().splitlines()[-n:]
    return [json.loads(x) for x in reversed(lines)]


@app.post("/api/upload")
async def upload(file: UploadFile, deal: str | None = None):
    require_writable()
    """Input connection: anything uploaded lands in vault/inbox — documents,
    transcripts, audio. The deployed agents take it from there (sentinel →
    transcriber/extractor → contradiction → librarian → coordinator)."""
    sync()  # cold instance: materialize the mirror before writing into it
    name = Path(file.filename or "upload").name  # strip any path component
    if deal and not name.lower().startswith(deal.lower()):
        name = f"{deal}-{name}"  # deal scoping: route by selection, not by convention
    dest = VAULT / "inbox" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = await file.read()
    if len(data) > 200_000_000:
        raise HTTPException(413, "file too large")
    dest.write_bytes(data)
    push()
    suffix = dest.suffix.lower()
    if suffix in (".m4a", ".mp3", ".wav", ".aiff", ".mp4", ".ogg", ".flac", ".webm"):
        note = "audio → transcriber will produce a transcript, then extraction runs on it"
    elif suffix in (".md", ".txt") and len(data) <= 120_000:
        note = "text → extractor will pull typed claims automatically (1-3 min)"
    else:
        note = ("stored, but automatic extraction only handles .md/.txt ≤120KB — "
                "export/convert this file to markdown or plain text and upload that")
    return {"stored": f"vault/inbox/{name}", "size": len(data), "note": note,
            "routing": "tip: name files <deal>-… when multiple deals exist"}


@app.get("/api/coordinator")
def coordinator_view():
    """The main agent's recent reasonings: latest brief per deal + its audit trail."""
    sync()
    briefs = []
    for f in sorted((VAULT / "deals").glob("*/deal.md")):
        text = f.read_text(encoding="utf-8")
        if "## State of the deal" in text:
            sec = text.split("## State of the deal", 1)[1].split("## Questions")[0]
            briefs.append({"deal": f.parent.name, "brief": sec.replace("<!-- agent-maintained -->", "").strip()[:1500]})
    log = []
    af = VAULT / "audit" / "agent-log.jsonl"
    if af.exists():
        for line in af.read_text(encoding="utf-8").strip().splitlines()[-60:]:
            r = json.loads(line)
            if r.get("agent") in ("coordinator", "librarian", "staleness", "contradiction"):
                log.append(r)
    return {"briefs": briefs, "reasonings": list(reversed(log))[:20]}


@app.get("/api/inflow")
def inflow():
    """The perception desk's view: every artifact and what became of it —
    announced? extracted? into which claims? The 'where did my input go' answer."""
    sync()
    reindex()
    st = {}
    sf = VAULT / "audit" / "runtime-state.json"
    if sf.exists():
        st = json.loads(sf.read_text())
    announced, extracted = set(st.get("announced", [])), set(st.get("extracted", []))
    c = con()
    by_artifact: dict[str, list] = {}
    for (fm,) in c.execute("SELECT frontmatter FROM nodes WHERE type='claim'"):
        f = json.loads(fm)
        src = str((f.get("source") or {}).get("artifact", ""))
        if "inbox/" in src:
            by_artifact.setdefault(src.split("inbox/")[-1].split(" ")[0], []).append(
                {"id": f.get("id"), "subject": f.get("subject"), "epistemic": f.get("epistemic")})
    out = []
    for f in sorted((VAULT / "inbox").glob("*")):
        if not f.is_file() or f.name.startswith("."):
            continue
        claims = by_artifact.get(f.name, [])
        auto = f.suffix.lower() in (".md", ".txt") and f.stat().st_size <= 150_000
        status = ("extracted" if f.name in extracted or claims else
                  "queued for extraction" if auto and f.name in announced else
                  "announced" if f.name in announced else
                  "waiting" if auto else "stored (convert to text for extraction)")
        out.append({"name": f.name, "size": f.stat().st_size, "status": status, "claims": claims})
    return out


@app.get("/api/inbox")
def inbox():
    sync()
    return [f.name for f in sorted((VAULT / "inbox").glob("*")) if f.is_file() and f.name != ".gitkeep"]


@app.exception_handler(Exception)
async def unhandled(request, exc):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ── Keystone model routes ─────────────────────────────────────────────────────

_MODEL_NODES_CSV = ROOT / "vault" / "runs" / "e4v6" / "model_nodes.csv"
_MODEL_DEPS_JSON  = ROOT / "vault" / "runs" / "e4v6" / "deps.json"

try:
    import csv as _csv_mod, json as _json_mod
    from keystone_model import (
        propagate_claim as _propagate_claim,
        run_lbo         as _run_lbo,
        PERIODS         as _MODEL_PERIODS,
    )
    _MODEL_READY = True
except Exception as _me:
    _MODEL_READY = False
    _MODEL_IMPORT_ERR = str(_me)


@app.get("/api/model/nodes")
def model_nodes():
    if not _MODEL_NODES_CSV.exists():
        raise HTTPException(404, f"model_nodes.csv not found: {_MODEL_NODES_CSV}")
    nodes = list(_csv_mod.DictReader(open(_MODEL_NODES_CSV, encoding="utf-8-sig")))
    deps: dict = _json_mod.loads(_MODEL_DEPS_JSON.read_text()) if _MODEL_DEPS_JSON.exists() else {}
    periods = [str(p) for p in _MODEL_PERIODS] if _MODEL_READY else []
    return {"nodes": nodes, "deps": deps, "periods": periods, "ready": _MODEL_READY}


@app.get("/api/model/snapshot")
def model_snapshot():
    if not _MODEL_READY:
        raise HTTPException(503, f"Model not loaded: {_MODEL_IMPORT_ERR}")
    result = _run_lbo()
    q = result.quarters
    return {
        "scenario":       "standalone_base",
        "exit_revenue":   round(result.exit_ltm_revenue, 3),
        "exit_ebitda":    round(result.exit_ltm_ebitda,  3),
        "exit_ev":        round(result.exit_ev,           3),
        "exit_net_debt":  round(result.exit_net_debt,     3),
        "exit_equity":    round(result.exit_equity,       3),
        "gross_moic":     round(result.gross_moic,        4),
        "gross_irr_pct":  round(result.gross_xirr * 100, 2),
        "periods":        [str(r.period)                  for r in q],
        "revenue":        [round(r.revenue,     3)        for r in q],
        "ebitda":         [round(r.firm_ebitda, 3)        for r in q],
        "net_leverage":   [round(r.net_leverage_covenant, 3) for r in q],
        "end_cash":       [round(r.end_cash,    3)        for r in q],
        "term_loan":      [round(r.term_loan,   3)        for r in q],
    }


@app.post("/api/model/propagate")
def model_propagate(payload: dict):
    if not _MODEL_READY:
        raise HTTPException(503, f"Model not loaded: {_MODEL_IMPORT_ERR}")
    claim    = payload.get("claim", {})
    scenario = payload.get("scenario", "standalone_base")
    if not claim or not claim.get("metric") or claim.get("value") is None:
        raise HTTPException(400, "claim requires {metric, value, period}")
    return _propagate_claim(claim, scenario=scenario)
