#!/usr/bin/env python3
"""PE OS local app server — the API layer over the vault.

Every write goes through ontology-shaped templates; every agent action maps to a
policy-table row; nothing listens beyond localhost. The vault stays canonical:
this server is a doorway, not a database.

Run:  make app   (uvicorn on http://127.0.0.1:8787)
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from engine import load_transitions  # noqa: E402
from ui import replay, state_label  # noqa: E402
import indexer  # noqa: E402

DB = ROOT / ".index" / "vault.db"
VAULT = ROOT / "vault"

app = FastAPI(title="PE OS", docs_url=None, redoc_url=None)

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
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.get("/api/deals")
def deals():
    c = con()
    out = [{"id": fm.get("id"), "title": t, "state": fm.get("state"), "demo": fm.get("demo", False)}
           for fm, t in rows(c, "SELECT frontmatter, title FROM nodes WHERE type='deal'")]
    return out


@app.get("/api/deal/{deal}")
def deal_view(deal: str):
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

    return {
        "deal": {**dfm, "title": dtitle},
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


@app.get("/api/ontology")
def ontology():
    files = sorted((VAULT / "ontology").glob("*.md")) + [VAULT / "policy" / "policy-table.md"]
    return [{"name": f.stem, "content": f.read_text(encoding="utf-8")} for f in files]


# ---------------------------------------------------------------- writes (human context — written-by: human)

class ClaimIn(BaseModel):
    subject: str
    value: str
    epistemic: str
    bears_on: list[str] = []
    direction: str = "context"
    locator: str = ""
    author: str = ""
    source_date: str = ""
    artifact: str = ""
    statement: str = ""
    derivation: str | None = None


@app.post("/api/deal/{deal}/claims")
def add_claim(deal: str, c_in: ClaimIn):
    if c_in.epistemic not in EPISTEMIC:
        raise HTTPException(422, f"epistemic must be one of {EPISTEMIC}")
    if c_in.epistemic == "derived" and not (c_in.derivation or "").strip():
        raise HTTPException(422, "ontology rule 3: a derived claim requires an inspectable derivation")
    cid = next_id(deal, "c", "claims")
    bears = ", ".join(f'"[[{b}]]"' for b in c_in.bears_on)
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
  date: {c_in.source_date or datetime.now().date()}
derivation: {json.dumps(c_in.derivation) if c_in.derivation else 'null'}
rests-on: []
supersedes: null
extracted-by: human
extracted: {datetime.now().date()}
---

{c_in.statement or c_in.subject + ': ' + c_in.value}
"""
    (VAULT / "deals" / deal / "claims" / f"{cid}.md").write_text(body, encoding="utf-8")
    reindex()
    return {"id": cid}


class QuestionIn(BaseModel):
    title: str
    bearing: str = ""
    critical: bool = False
    target_workstream: str = ""
    parent: str | None = None
    question_type: str | None = None


@app.post("/api/deal/{deal}/questions")
def add_question(deal: str, q: QuestionIn):
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
    reindex()
    return {"id": qid}


class EventIn(BaseModel):
    kind: str
    actor: str = "human"
    note: str = ""


@app.post("/api/deal/{deal}/events")
def add_event(deal: str, e: EventIn):
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
    reindex()
    return {"id": eid}


# ---------------------------------------------------------------- agents

@app.post("/api/agents/state/{deal}")
def agent_state(deal: str):
    """Policy row 4: derive + write deal.state (invariant 10)."""
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "engine.py"), deal, "--write"],
                       capture_output=True, text=True, cwd=ROOT, timeout=60)
    if r.returncode != 0:
        raise HTTPException(500, r.stderr or r.stdout)
    reindex()
    return {"output": r.stdout}


@app.post("/api/agents/contradictions/{deal}")
def agent_contradictions(deal: str):
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


class AskIn(BaseModel):
    question: str


@app.post("/api/agents/ask")
def agent_ask(body: AskIn):
    """Chat with the brain: read-only LLM agent over the whole vault (policy row 1+3).
    Tools restricted to Read/Grep/Glob — it can look, it cannot touch."""
    prompt = (
        "You are the PE OS brain interface. Answer the user's question strictly from the "
        "contents of vault/ (questions, claims with epistemic types, events, decisions, "
        "question-type archives, entities). Cite file ids like [c-aurora-002]. Distinguish "
        "epistemic types when weighing evidence. If the vault does not contain the answer, "
        f"say so plainly.\n\nQuestion: {body.question}"
    )
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools", "Read,Grep,Glob"],
            capture_output=True, text=True, cwd=ROOT, timeout=300,
        )
    except FileNotFoundError:
        raise HTTPException(501, "claude CLI not found")
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "brain query timed out (5 min)")
    if r.returncode != 0:
        raise HTTPException(500, (r.stderr or r.stdout)[-500:])
    return {"answer": r.stdout.strip()}


@app.get("/api/audit")
def audit_log(n: int = 20):
    f = VAULT / "audit" / "agent-log.jsonl"
    if not f.exists():
        return []
    lines = f.read_text(encoding="utf-8").strip().splitlines()[-n:]
    return [json.loads(x) for x in reversed(lines)]


@app.get("/api/inbox")
def inbox():
    return [f.name for f in sorted((VAULT / "inbox").glob("*")) if f.is_file() and f.name != ".gitkeep"]


@app.exception_handler(Exception)
async def unhandled(request, exc):
    return JSONResponse(status_code=500, content={"detail": str(exc)})
