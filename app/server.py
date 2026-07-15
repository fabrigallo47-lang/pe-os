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

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import os

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
    require_writable()
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
    push()
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


def _llm_text(system: str, user: str, max_tokens: int = 4000) -> str:
    """One model call. Prefers the Anthropic API key (claude-sonnet-4-6); falls
    back to Vercel AI Gateway OIDC. Errors surface verbatim — no fake answers."""
    import urllib.request
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    try:
        if anthropic_key:
            payload = {"model": os.environ.get("PEOS_MODEL", "claude-sonnet-5"),
                       "max_tokens": max_tokens, "system": system,
                       "messages": [{"role": "user", "content": user}]}
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(payload).encode(), method="POST",
                headers={"Content-Type": "application/json", "x-api-key": anthropic_key,
                         "anthropic-version": "2023-06-01"})
            with urllib.request.urlopen(req, timeout=280) as resp:
                return json.loads(resp.read())["content"][0]["text"]
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


def _gateway_json(system: str, user: str, max_tokens: int = 4000):
    text = _llm_text(system, user, max_tokens)
    m = re.search(r"\[.*\]|\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"model returned no JSON: {text[:200]}")
    return json.loads(m.group(0))


def cloud_extract(deal: str, artifact: Path) -> list[str]:
    """Gateway extraction: artifact text → typed claim files. The model proposes
    JSON; the SERVER writes files through the same validated template as humans."""
    questions = "\n".join(f"- {f.stem}: {f.read_text(encoding='utf-8').split('# ',1)[1].splitlines()[0]}"
                          for f in (VAULT / "deals" / deal / "questions").glob("*.md"))
    existing_subjects = sorted({json.loads(fm).get("subject") for fm, in
                                con().execute("SELECT frontmatter FROM nodes WHERE type='claim' AND deal=?", (deal,))
                                if json.loads(fm).get("subject")})
    data = _gateway_json(
        "You are the PE OS extractor agent. Extract discrete factual claims from the artifact. "
        "Return ONLY a JSON array; each item: {subject (reuse an existing subject string when the same "
        "quantity is meant), value, epistemic (asserted|derived|observed|attested — type DOWN when unsure; "
        "recorded-interaction statements are observed), bears_on (list of question ids, by meaning), "
        "direction (supports|contradicts|context), locator (line/section), author, statement (one sentence), "
        "derivation (string or null — required if derived)}.",
        f"DEAL QUESTIONS:\n{questions}\n\nEXISTING SUBJECTS: {existing_subjects}\n\n"
        f"ARTIFACT ({artifact.name}):\n{artifact.read_text(encoding='utf-8')[:100_000]}")
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
            for f in sorted((VAULT / "inbox").glob("*")):
                if f.suffix.lower() in (".md", ".txt") and f.name not in done and f.stat().st_size < 150_000:
                    d = rt.deal_for(f.name)
                    if not d:
                        continue
                    ids = cloud_extract(d, f)
                    st = rt._state(); st.setdefault("extracted", []).append(f.name); rt._save(st)
                    rt.audit("extractor", "HVA_COMMERCIAL_01", "claims-extracted", f"{f.name} → {len(ids)}", ids)
                    push(); reindex()
                    return {"summary": f"{f.name} → {len(ids)} claims"}
            return {"summary": "nothing to extract"}
        if kind == "workstream":
            r = agent_workstream(deal, WorkstreamIn(workstream=body.config.get("workstream", "commercial_market")))
            return {"summary": r["output"][-200:]}
        if kind == "ask":
            return {"summary": _ask_via_gateway(body.config.get("question", "summarize the open risks"))[:600]}
        cls = {"sentinel": rt.Sentinel, "state-resolver": rt.StateResolver, "contradiction": rt.Contradiction,
               "librarian": rt.Librarian, "coordinator": rt.Coordinator, "staleness": rt.Staleness}.get(kind)
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


@app.get("/api/audit")
def audit_log(n: int = 20):
    sync()
    f = VAULT / "audit" / "agent-log.jsonl"
    if not f.exists():
        return []
    lines = f.read_text(encoding="utf-8").strip().splitlines()[-n:]
    return [json.loads(x) for x in reversed(lines)]


@app.post("/api/upload")
async def upload(file: UploadFile):
    require_writable()
    """Input connection: anything uploaded lands in vault/inbox — documents,
    transcripts, audio. The deployed agents take it from there (sentinel →
    transcriber/extractor → contradiction → librarian → coordinator)."""
    sync()  # cold instance: materialize the mirror before writing into it
    name = Path(file.filename or "upload").name  # strip any path component
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
