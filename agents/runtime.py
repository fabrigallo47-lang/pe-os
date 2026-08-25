#!/usr/bin/env python3
"""PE OS agent runtime — the deployed agents.

A running process, not an endpoint. Watches the vault, activates functional agents
on changes, and refuses anything the contracts reserve for humans. Coordination is
state-mediated (invariant 9): agents observe, act, emit events, and append to the
audit log; the engine decides what that implies.

Each agent binds to its row in the human-vs-automatable register — the contract
that says machines may do this at all. Allowed classes only:
  deterministic_automation · machine_assisted_extraction · machine_assisted_analysis

Run:  make agents        (foreground loop, Ctrl+C to stop)
Audit: vault/audit/agent-log.jsonl (append-only, PR_023)
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import contracts  # noqa: E402
import indexer  # noqa: E402

VAULT = indexer.VAULT
AUDIT = VAULT / "audit" / "agent-log.jsonl"
STATE_FILE = VAULT / "audit" / "runtime-state.json"  # inside the vault so cloud sync persists it
POLL_SECONDS = 3

FORBIDDEN = {"human_judgment_required", "authority_only_human_action"}


# ---------------------------------------------------------------------------
# Direct Anthropic API helper — avoids Claude CLI (which has per-session and
# monthly limits). Used by any agent that needs LLM reasoning locally.
# ---------------------------------------------------------------------------

def _api_json(system: str, user: str, max_tokens: int = 8000) -> object:
    """Call Anthropic API directly, return parsed JSON from the response."""
    import os, urllib.request, re as _re
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    model = os.environ.get("PEOS_MODEL", "claude-sonnet-5")
    payload = {
        "model": model, "max_tokens": max_tokens,
        "thinking": {"type": "adaptive"}, "output_config": {"effort": "low"},
        "system": system, "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        blocks = json.loads(resp.read())["content"]
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    if not text:
        raise ValueError("no text block in response")
    fence = _re.search(r"```(?:json)?\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```", text)
    m = fence or _re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
    if not m:
        raise ValueError(f"no JSON in response: {text[:200]}")
    raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = _re.sub(r",\s*([}\]])", r"\1", raw)
        return json.loads(cleaned)


def audit(agent: str, activity_id: str, action: str, detail: str, wrote: list[str]):
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": datetime.now().isoformat(timespec="seconds"), "agent": agent,
           "contract_activity": activity_id, "action": action, "detail": detail, "wrote": wrote}
    with open(AUDIT, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"[{rec['ts']}] {agent}: {action} — {detail}" + (f" (wrote {', '.join(wrote)})" if wrote else ""))


class Agent:
    """Typed, contract-bound functional agent."""
    id: str
    activity_id: str          # row in the human-vs-automatable register
    watches: str

    def __init__(self):
        act = contracts.agent_activity(self.activity_id)
        if act is None:
            raise RuntimeError(f"{self.id}: no contract row {self.activity_id} — refusing to deploy")
        if act["automation_class"] in FORBIDDEN:
            raise RuntimeError(f"{self.id}: {self.activity_id} is {act['automation_class']} — agents may not do this")
        self.contract = act

    def snapshot(self) -> dict:  # what it watches: path -> mtime
        raise NotImplementedError

    def act(self, changed: list[str]):
        raise NotImplementedError


def deals() -> list[str]:
    return [d.name for d in (VAULT / "deals").iterdir() if d.is_dir()]


def _deal_state(deal: str) -> str | None:
    """Read the current deal state from deal.md frontmatter."""
    deal_file = VAULT / "deals" / deal / "deal.md"
    if not deal_file.exists():
        return None
    text = deal_file.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    try:
        import yaml as _yaml
        fm = _yaml.safe_load(text[3:end]) or {}
        return fm.get("state")
    except Exception:
        return None


def deal_for(filename: str) -> str | None:
    """Route an inbox artifact to a deal: filename prefix wins (astrelia-x.pdf →
    astrelia); a single existing deal is the fallback; otherwise unroutable."""
    ds = deals()
    for d in sorted(ds, key=len, reverse=True):
        if filename.lower().startswith(d.lower()):
            return d
    return ds[0] if len(ds) == 1 else None


def emit_event(deal: str, kind: str, actor: str, note: str) -> str:
    d = VAULT / "deals" / deal / "events"
    d.mkdir(parents=True, exist_ok=True)
    eid = f"ev-{deal}-{len(list(d.glob('*.md'))) + 1:03d}"
    (d / f"{eid}.md").write_text(
        f"---\ntype: event\nid: {eid}\ndeal: \"[[{deal}]]\"\nkind: {kind}\nactor: {actor}\n"
        f"at: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\nrelates-to: []\nsupersedes: null\n---\n\n{note}\n",
        encoding="utf-8")
    return eid


class Sentinel(Agent):
    """Perception edge: notices artifacts arriving in the inbox and announces them
    as immutable events. It never reads content — announcement only."""
    id = "sentinel"
    activity_id = "HVA_COMMERCIAL_01"  # ingest and index evidence (machine_assisted_extraction)
    watches = "vault/inbox"

    def snapshot(self):
        return {str(f): f.stat().st_mtime for f in (VAULT / "inbox").glob("*")
                if f.is_file() and ".16k." not in f.name and f.suffix != ".txt"}

    def act(self, changed):
        st = _state()
        announced = set(st.get("announced", []))
        for path in changed:
            name = Path(path).name
            if name in announced:
                continue
            deal = deal_for(name)
            if deal:
                eid = emit_event(deal, "ARTIFACT_ARRIVED", self.id, f"Artifact landed in inbox: {name}")
                audit(self.id, self.activity_id, "artifact-announced", f"{name} → {deal}", [eid])
                st = _state(); st.setdefault("announced", []).append(name); _save(st)
            else:
                audit(self.id, self.activity_id, "artifact-pending",
                      f"{name}: no deal prefix and multiple deals — rename to <deal>-… to route", [])


class StateResolver(Agent):
    """Deterministic automation: replays events through the transition contracts and
    writes the derived state (invariant 10). Never invents an event."""
    id = "state-resolver"
    activity_id = "HVA_COMMERCIAL_02"  # run deterministic checks (deterministic_automation)
    watches = "vault/deals/*/events"

    def snapshot(self):
        return {str(f): f.stat().st_mtime for f in (VAULT / "deals").glob("*/events/*.md")}

    def act(self, changed):
        for deal in {Path(p).parts[-3] for p in changed}:
            r = subprocess.run([sys.executable, str(ROOT / "tools" / "engine.py"), deal, "--write"],
                               capture_output=True, text=True, cwd=ROOT, timeout=60)
            line = next((ln for ln in r.stdout.splitlines() if "Derived primary state" in ln), "?")
            audit(self.id, self.activity_id, "state-derived", f"{deal}: {line.split(':')[-1].strip()}",
                  [f"{deal}/deal.md"])


class Contradiction(Agent):
    """Deterministic detection over the claim graph. Flags, never adjudicates."""
    id = "contradiction"
    activity_id = "HVA_COMMERCIAL_02"
    watches = "vault/deals/*/claims"

    def snapshot(self):
        return {str(f): f.stat().st_mtime for f in (VAULT / "deals").glob("*/claims/*.md")}

    def act(self, changed):
        indexer.build().close()
        con = sqlite3.connect(indexer.DB)
        for deal in {Path(p).parts[-3] for p in changed}:
            rows = con.execute(
                "SELECT subject, GROUP_CONCAT(id || ' [' || COALESCE(epistemic,'?') || ']=' || COALESCE(value,'?'), ' | ') "
                "FROM nodes WHERE type='claim' AND deal=? AND subject IS NOT NULL "
                "GROUP BY subject HAVING COUNT(DISTINCT value) > 1", (deal,)).fetchall()
            known = set(_state().get("flagged", {}).get(deal, []))
            new = [s for s, _ in rows if s not in known]
            if new:
                eid = emit_event(deal, "CONTRADICTION_FLAGGED", self.id,
                                 "Unresolved contradiction(s): " + "; ".join(new))
                audit(self.id, self.activity_id, "contradiction-flagged", f"{deal}: {', '.join(new)}", [eid])
                st = _state(); st.setdefault("flagged", {}).setdefault(deal, []).extend(new); _save(st)


class Transcriber(Agent):
    """Voice input: audio landing in the inbox (meeting recordings, expert calls,
    voice memos) becomes a timestamped transcript — locally, via whisper.cpp;
    nothing leaves the machine. The transcript is a new artifact: sentinel
    announces it and /ingest extracts `observed` claims from it. This is how
    Category-4 interaction data (the room nobody else was in) enters the graph."""
    id = "transcriber"
    activity_id = "HVA_COMMERCIAL_01"  # machine_assisted_extraction
    watches = "vault/inbox (audio)"
    AUDIO = {".m4a", ".mp3", ".wav", ".aiff", ".mp4", ".ogg", ".flac", ".webm"}
    MODEL = ROOT / ".models" / "ggml-base.bin"

    def snapshot(self):
        return {str(f): f.stat().st_mtime for f in (VAULT / "inbox").glob("*")
                if f.is_file() and f.suffix.lower() in self.AUDIO}

    def act(self, changed):
        import shutil
        if not (shutil.which("whisper-cli") and self.MODEL.exists()):
            audit(self.id, self.activity_id, "skipped",
                  "whisper-cli or model missing (brew install whisper-cpp; model in .models/)", [])
            return
        for path in changed:
            src = Path(path)
            out = src.with_suffix("")  # whisper adds .txt
            wav = src.with_suffix(".16k.wav")
            try:
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                                "-ar", "16000", "-ac", "1", str(wav)], check=True, timeout=600)
                subprocess.run(["whisper-cli", "-m", str(self.MODEL), "-f", str(wav),
                                "-otxt", "-of", str(out), "--no-prints"],
                               check=True, timeout=1800, capture_output=True)
                text = out.with_suffix(".txt").read_text(encoding="utf-8").strip()
                md = src.with_suffix(".transcript.md")
                md.write_text(
                    f"---\nsource-audio: {src.name}\ntranscribed: {datetime.now().isoformat(timespec='seconds')}\n"
                    f"transcriber: whisper.cpp ggml-base (local)\nepistemic-default: observed\n---\n\n"
                    f"# Transcript — {src.stem}\n\n{text}\n", encoding="utf-8")
                out.with_suffix(".txt").unlink(missing_ok=True)
                wav.unlink(missing_ok=True)
                audit(self.id, self.activity_id, "transcribed",
                      f"{src.name} → {md.name} ({len(text)} chars, local whisper)", [md.name])
            except Exception as exc:
                wav.unlink(missing_ok=True)
                audit(self.id, self.activity_id, "error", f"{src.name}: {exc}", [])


class Extractor(Agent):
    """The working agent: when a text artifact lands, it reads it and turns it into
    typed, provenanced claims bound to the deal's questions — via headless Claude,
    autonomously, once per artifact. This is machine_assisted_extraction: it files
    and links; it never resolves a question and never adjudicates."""
    id = "extractor"
    activity_id = "HVA_COMMERCIAL_01"
    watches = "vault/inbox (*.md,*.txt)"
    MAX_BYTES = 120_000  # cost guard for autonomous runs

    def snapshot(self):
        return {str(f): f.stat().st_mtime for f in (VAULT / "inbox").glob("*")
                if f.is_file() and f.suffix.lower() in (".md", ".txt") and ".16k." not in f.name}

    def act(self, changed):
        st = _state()
        done = set(st.get("extracted", []))
        for path in changed:
            src = Path(path)
            if src.name in done:
                continue
            if src.stat().st_size > self.MAX_BYTES:
                audit(self.id, self.activity_id, "skipped", f"{src.name} too large for autonomous run — use the Ingest button", [])
                continue
            deal = deal_for(src.name)
            if deal is None:
                audit(self.id, self.activity_id, "pending",
                      f"{src.name}: no deal prefix and multiple deals — rename to <deal>-… to route", [])
                continue
            # LS-02 guard (EMP-01 ENFORCE gate): initial assessment must precede full extraction.
            # Warn — do not block — when no IA-class claim or artifact exists for this deal yet.
            before = {f.name for f in (VAULT / "deals" / deal / "claims").glob("*.md")}
            if not before:
                # First-ever extraction for this deal — check if an initial assessment exists.
                ia_artifacts = list((VAULT / "deals" / deal).rglob("*.md"))
                ia_found = any("initial" in f.stem.lower() or "assessment" in f.stem.lower()
                               for f in ia_artifacts)
                try:
                    gates = contracts.gates_for_state(
                        _deal_state(deal) or "S0_DEAL_SOURCING")
                    ls02_required = any(g.get("kernel_id") == "LS-02" for g in gates)
                except Exception:
                    ls02_required, ia_found = True, False
                if ls02_required and not ia_found:
                    audit(self.id, self.activity_id, "ls02-warn",
                          f"[EMP-01 ENFORCE] Deal '{deal}' has no initial assessment on record. "
                          f"LS-02 (opportunity-specific IA, risk map, quick model) is required before "
                          f"full diligence extraction. Proceeding with extraction but flag this for review.",
                          [])
            audit(self.id, self.activity_id, "extraction-started", src.name, [])
            prompt = f"""You are the PE OS extractor agent. Work autonomously; never ask questions.

Artifact: vault/inbox/{src.name}   Deal: {deal}

1. Read the artifact, vault/ontology/claim.md, every file in vault/deals/{deal}/questions/, and the existing claims in vault/deals/{deal}/claims/ (REUSE their exact `subject` strings when the same quantity is meant — contradiction detection groups on subject).
2. Extract each discrete factual claim from the artifact. Type it: statements of what happened or was said in a recorded interaction = observed; a speaker's assertions about the world = asserted; computed-with-visible-math = derived (requires derivation + rests-on); audited/contractual = attested. When unsure, type DOWN the hierarchy.
3. For each claim write vault/deals/{deal}/claims/c-{deal}-NNN.md (continue numbering after the highest existing NNN) following the schema EXACTLY: frontmatter with type, id, epistemic, subject, value, bears-on (the question ids it bears on, by meaning), direction (supports|contradicts|context relative to the first bears-on question), source (artifact path, locator such as a line or timestamp, author, date), derivation, rests-on, supersedes, extracted-by: extractor, extracted: today. Body: one sentence + exact quote.
4. Append each claim link under the matching question's ## Evidence section (- supports:/contradicts:/context: [[id]]).
5. NEVER change a question's state, never edit existing claims, never touch decisions.
6. Finish with one line per claim written: id — subject = value (epistemic).
"""
            try:
                r = subprocess.run(["claude", "-p", prompt, "--permission-mode", "acceptEdits"],
                                   capture_output=True, text=True, cwd=ROOT, timeout=480)
                after = {f.name for f in (VAULT / "deals" / deal / "claims").glob("*.md")}
                new = sorted(after - before)
                st = _state(); st.setdefault("extracted", []).append(src.name); _save(st)
                if r.returncode == 0 and new:
                    audit(self.id, self.activity_id, "claims-extracted",
                          f"{src.name} → {len(new)} claim(s): {', '.join(n.removesuffix('.md') for n in new)}", new)
                else:
                    audit(self.id, self.activity_id, "extraction-empty",
                          f"{src.name}: rc={r.returncode}, no new claims. tail: {r.stdout[-200:]}", [])
            except FileNotFoundError:
                audit(self.id, self.activity_id, "error", "claude CLI not found", [])
            except subprocess.TimeoutExpired:
                audit(self.id, self.activity_id, "error", f"{src.name}: extraction timed out", [])


class Proposer(Agent):
    """The OS proposes (V1 step 2): once per deal, when claims exist but no
    assumptions do, it derives the assumption set the deal rests on — quantified,
    based on the extracted claims — and links the questions that test each one.
    Runs exactly once autonomously; after that, proposing is human-triggered."""
    id = "proposer"
    activity_id = "HVA_COMMERCIAL_01"
    watches = "deals/*/claims (until assumptions exist)"

    def snapshot(self):
        return {str(f): f.stat().st_mtime for f in (VAULT / "deals").glob("*/claims/*.md")}

    def act(self, changed):
        st = _state()
        for deal in {Path(p).parts[-3] for p in changed}:
            adir = VAULT / "deals" / deal / "assumptions"
            if deal in st.get("proposed", []) or (adir.exists() and any(adir.glob("*.md"))):
                continue
            adir.mkdir(exist_ok=True)
            audit(self.id, self.activity_id, "proposal-started", deal, [])
            try:
                # Read deal context
                deal_txt = (VAULT / "deals" / deal / "deal.md").read_text(encoding="utf-8")
                q_files = sorted((VAULT / "deals" / deal / "questions").glob("*.md"))
                questions_txt = "\n\n".join(
                    f"[{f.stem}]\n{f.read_text(encoding='utf-8')[:300]}" for f in q_files[:20])
                # Sample claims (first 60, prioritise those with numeric values)
                claim_files = sorted((VAULT / "deals" / deal / "claims").glob("*.md"))
                claims_txt = "\n".join(
                    f"- {f.stem}: {f.read_text(encoding='utf-8').splitlines()[1] if len(f.read_text().splitlines())>1 else ''}"
                    for f in claim_files[:80])

                system = (
                    "You are the PE OS proposer agent. Return ONLY a JSON array of assumptions. "
                    "Each item: {id (string 'a-<deal>-NNN'), statement (one sentence quantified proposition "
                    "that must be true for the thesis to hold), value (the specific quantified value, "
                    "e.g. '$11.4m'), basis (list of claim ids from claims/), state: 'proposed', version: 1, "
                    "tests_questions (list of question ids from questions/ that test this assumption)}. "
                    "Produce 4-6 assumptions. Focus on the claims that most directly determine whether "
                    "the thesis works. Include one assumption per major risk dimension."
                )
                user = (
                    f"DEAL: {deal}\n\nTHESIS / DEAL.MD:\n{deal_txt[:800]}\n\n"
                    f"QUESTIONS:\n{questions_txt[:2000]}\n\n"
                    f"CLAIMS SAMPLE:\n{claims_txt[:3000]}"
                )
                items = _api_json(system, user)
                new = []
                for item in items:
                    aid = str(item.get("id", f"a-{deal}-{len(new)+1:03d}"))
                    basis = item.get("basis", []) or []
                    basis_yaml = "\n".join(f"  - {b}" for b in basis) or "  []"
                    tests = item.get("tests_questions", []) or []
                    tests_yaml = "\n".join(f"  - {q}" for q in tests) or "  []"
                    content = (
                        f"---\ntype: assumption\nid: {aid}\ndeal: \"[[{deal}]]\"\n"
                        f"statement: \"{str(item.get('statement','')).replace(chr(34), chr(39))}\"\n"
                        f"value: \"{item.get('value','?')}\"\nbasis:\n{basis_yaml}\n"
                        f"tests:\n{tests_yaml}\nstate: proposed\nversion: 1\nstale: false\n"
                        f"proposed-by: proposer\nwritten-by: proposer\n---\n\n"
                        f"## {aid}\n\n{item.get('statement','')}\n\n"
                        f"**Value**: {item.get('value','?')}\n\n"
                        f"v1 (proposer): derived from {len(basis)} claims.\n"
                    )
                    (adir / f"{aid}.md").write_text(content, encoding="utf-8")
                    new.append(aid)
                st = _state(); st.setdefault("proposed", []).append(deal); _save(st)
                audit(self.id, self.activity_id, "assumptions-proposed" if new else "proposal-empty",
                      f"{deal}: {', '.join(new)}", new)
            except Exception as exc:
                audit(self.id, self.activity_id, "error", f"{deal}: {exc}", [])


class Staleness(Agent):
    """V1 step 4, deterministic: when an assumption's value changes, every object
    that depends on it (questions that test it, outputs tied to it) is flagged
    stale and an ANALYTICAL_OBJECT_SUPERSEDED event is emitted. It never repairs —
    re-running the work is what clears the flag."""
    id = "staleness"
    activity_id = "HVA_COMMERCIAL_02"
    watches = "deals/*/assumptions"

    def snapshot(self):
        return {str(f): f.stat().st_mtime for f in (VAULT / "deals").glob("*/assumptions/*.md")}

    def act(self, changed):
        import re as _re
        indexer.build().close()
        con = sqlite3.connect(indexer.DB)
        st = _state()
        baseline = st.setdefault("assumption_values", {})
        for path in changed:
            f = Path(path)
            m = _re.search(r"^value:\s*\"?(.+?)\"?\s*$", f.read_text(encoding="utf-8"), _re.MULTILINE)
            if not m:
                continue
            aid, value = f.stem, m.group(1)
            old = baseline.get(aid)
            baseline[aid] = value
            if old is None or old == value:
                continue  # first sight = baseline; no change = nothing to do
            deal = f.parts[f.parts.index("deals") + 1]
            deps = con.execute(
                "SELECT n.id, n.path FROM edges e JOIN nodes n ON n.id=e.src "
                "WHERE e.dst=? AND e.rel IN ('tests','tied-to')", (aid,)).fetchall()
            flagged = []
            for dep_id, dep_path in deps:
                p = VAULT / dep_path
                text = p.read_text(encoding="utf-8")
                if _re.search(r"^stale:", text, _re.MULTILINE):
                    new_text = _re.sub(r"^stale:.*$", "stale: true", text, count=1, flags=_re.MULTILINE)
                else:
                    new_text = _re.sub(r"^(type:.*)$", r"\1\nstale: true", text, count=1, flags=_re.MULTILINE)
                if new_text != text:
                    p.write_text(new_text, encoding="utf-8")
                    flagged.append(dep_id)
            if flagged:
                eid = emit_event(deal, "ANALYTICAL_OBJECT_SUPERSEDED", self.id,
                                 f"Assumption {aid} changed ('{old}' → '{value}'); stale: {', '.join(flagged)}")
                audit(self.id, self.activity_id, "staleness-propagated",
                      f"{aid}: '{old}' → '{value}' ⇒ {len(flagged)} dependent(s) stale", flagged + [eid])
        _save(st)


class Coordinator(Agent):
    """Deterministic desk brief: keeps deal.md § 'State of the deal' current —
    derived state, held gates, open critical questions ranked by structural
    dependency, contradictions, and what the flow allows next. Machine-written
    section, so it never violates zero-maintenance."""
    id = "coordinator"
    activity_id = "HVA_COMMERCIAL_02"
    watches = "deals/*/{events,claims,questions}"
    HEAD, TAIL = "## State of the deal", "## Questions"

    def snapshot(self):
        return {str(f): f.stat().st_mtime
                for pat in ("*/events/*.md", "*/claims/*.md", "*/questions/*.md")
                for f in (VAULT / "deals").glob(pat)}

    def act(self, changed):
        import contracts
        indexer.build().close()
        con = sqlite3.connect(indexer.DB)
        for deal in {Path(p).parts[-3] for p in changed}:
            f = VAULT / "deals" / deal / "deal.md"
            text = f.read_text(encoding="utf-8")
            if self.HEAD not in text or self.TAIL not in text:
                continue
            state = (con.execute("SELECT state FROM nodes WHERE type='deal' AND id=?", (deal,))
                     .fetchone() or ["?"])[0]
            crit = con.execute(
                "SELECT n.id, n.title, (SELECT COUNT(*) FROM edges e WHERE e.dst=n.id AND e.rel IN ('depends-on','parent')) fanin "
                "FROM nodes n WHERE n.type='question' AND n.deal=? AND n.state IN ('open','reducing') "
                "AND json_extract(n.frontmatter,'$.critical')=1 ORDER BY fanin DESC", (deal,)).fetchall()
            contras = con.execute(
                "SELECT subject FROM nodes WHERE type='claim' AND deal=? AND subject IS NOT NULL "
                "GROUP BY subject HAVING COUNT(DISTINCT value)>1", (deal,)).fetchall()
            nxt = [t for t in contracts.transitions() if t["from"] == state and t["source"] == "v1-alias"][:4]
            lines = [f"_(coordinator, {datetime.now().strftime('%Y-%m-%d %H:%M')})_",
                     f"- **Derived state:** {state}"]
            if crit:
                lines.append("- **Blocking the decision** (critical, open — ranked by how much depends on them):")
                lines += [f"  {i+1}. [[{q}]] — {t} (fan-in {fi})" for i, (q, t, fi) in enumerate(crit)]
            for (s,) in contras:
                lines.append(f"- **Unresolved contradiction:** {s}")
            if nxt:
                lines.append("- **The flow allows next:** " + "; ".join(f"{t['triggers'][0]} → {t['to']}" for t in nxt))
            new_section = f"{self.HEAD}   <!-- agent-maintained -->\n" + "\n".join(lines) + "\n\n"
            head, rest = text.split(self.HEAD, 1)
            _, tail = rest.split(self.TAIL, 1)
            new_text = head + new_section + self.TAIL + tail
            if new_text != text:
                f.write_text(new_text, encoding="utf-8")
                audit(self.id, self.activity_id, "brief-updated", f"{deal}: state {state}, "
                      f"{len(crit)} critical open, {len(contras)} contradiction(s)", [f"{deal}/deal.md"])


class Librarian(Agent):
    """The brain's custodian. Cross-deal, deterministic: whenever claims or
    questions change, it rebuilds each question-type's Evidence archive so that
    evidence filed under any deal becomes findable from the firm brain — by what
    it bears on, not by keyword. This is the upward flow (deal → brain)."""
    id = "librarian"
    activity_id = "HVA_COMMERCIAL_02"
    watches = "deals/*/{claims,questions}"

    MARK = "## Evidence archive"

    def snapshot(self):
        return {str(f): f.stat().st_mtime
                for pat in ("*/claims/*.md", "*/questions/*.md")
                for f in (VAULT / "deals").glob(pat)}

    def act(self, changed):
        indexer.build().close()
        con = sqlite3.connect(indexer.DB)
        rows = con.execute(
            "SELECT qt.dst, c.deal, c.id, c.epistemic, c.subject, c.value "
            "FROM edges b JOIN edges qt ON b.dst = qt.src AND qt.rel='question-type' "
            "JOIN nodes c ON c.id = b.src AND c.type='claim' WHERE b.rel='bears-on' "
            "ORDER BY qt.dst, c.deal, c.id").fetchall()
        by_qt: dict[str, list] = {}
        for qt, deal, cid, ep, subj, val in rows:
            by_qt.setdefault(qt, []).append(f"- [[{cid}]] ({deal}, {ep}) — {subj}: {val}")
        wrote = []
        for f in (VAULT / "library" / "question-types").glob("qt-*.md"):
            entries = by_qt.get(f.stem, [])
            text = f.read_text(encoding="utf-8")
            if self.MARK not in text:
                continue
            head = text.split(self.MARK)[0]
            new = head + self.MARK + "\n(maintained by librarian — cross-deal evidence, by what it bears on)\n" \
                + ("\n".join(entries) + "\n" if entries else "(empty)\n")
            if new != text:
                f.write_text(new, encoding="utf-8")
                wrote.append(f.stem)
        if wrote:
            audit(self.id, self.activity_id, "brain-archives-updated",
                  f"{len(wrote)} question-type archive(s): {', '.join(wrote)}", wrote)


class PhaseCoordinator(Agent):
    """Part B — The palingenetic phase coordinator. Deterministic core:
    reads the derived deal state, maps it to the phase playbook, and proposes
    the next steps (what changed + what it opened). Writes deals/<id>/plan.md;
    emits PLAN_UPDATED event; audit under HVA_COMMERCIAL_02.

    Dispatch is STATE-MEDIATED: this agent never calls other agents.
    The plan's `proposed` list is returned to the canvas where the human
    presses 'Run plan' to execute them sequentially."""
    id = "phase-coordinator"
    activity_id = "HVA_COMMERCIAL_02"  # deterministic_automation
    watches = "deals/*/{events,claims,questions,assumptions}"

    # Phase playbook: deal state prefix → proposed steps
    PLAYBOOK = {
        # S0–S3 origination / screening
        "S0": [{"kind": "agent", "target": "extractor",  "why": "Process any unextracted inbox artifacts"},
               {"kind": "agent", "target": "sentinel",   "why": "Announce any un-announced inbox artifacts"},
               {"kind": "agent", "target": "proposer",   "why": "Derive assumption set from extracted claims (once per deal)"}],
        "S1": [{"kind": "agent", "target": "extractor",  "why": "Extract claims from ingested material"},
               {"kind": "agent", "target": "proposer",   "why": "Propose assumptions if claims exist and assumptions are missing"}],
        "S2": [{"kind": "agent", "target": "extractor",  "why": "Extract from case material"},
               {"kind": "agent", "target": "contradiction", "why": "Flag contradictions in new claims"},
               {"kind": "agent", "target": "librarian",  "why": "Update cross-deal brain archives"}],
        "S3": [{"kind": "agent", "target": "contradiction", "why": "Contradiction check before screening decision"},
               {"kind": "human", "target": "screening-decision", "why": "Human screening gate (policy row 7)"}],
        # S4–S5 diligence
        "S4": [{"kind": "agent", "target": "workstream", "why": "Run workstream for each open critical question's target-workstream"},
               {"kind": "agent", "target": "contradiction", "why": "Contradiction check over expanded evidence base"}],
        "S5": [{"kind": "agent", "target": "workstream", "why": "Complete remaining workstream analyses"},
               {"kind": "agent", "target": "contradiction", "why": "Contradiction check"},
               {"kind": "agent", "target": "staleness",   "why": "Flag stale assumptions after workstream revisions"}],
        # S6–S7 underwriting / IC
        "S6": [{"kind": "agent", "target": "ic-assembler", "why": "Assemble IC package from full graph"},
               {"kind": "human", "target": "ic-gate",    "why": "IC decision gate — human only (policy row 8)"}],
        "S7": [{"kind": "agent", "target": "ic-assembler", "why": "Regenerate IC package with final positions"},
               {"kind": "human", "target": "ic-decision", "why": "Investment committee decision — authority-only human action"}],
        # S8+ post-IC — human/external events only
        "S8": [{"kind": "external-event", "target": "legal-execution", "why": "Legal/documentation phase — requires external events"}],
        "S9": [{"kind": "external-event", "target": "closing", "why": "Closing — requires external confirmation"}],
        # S10–S13 ownership and exit loops
        "S10": [
            {"kind": "agent",          "target": "extractor",    "why": "Extract claims from new monitoring artifacts"},
            {"kind": "agent",          "target": "monitoring",   "why": "Flag performance divergence from IC underwriting"},
            {"kind": "agent",          "target": "staleness",    "why": "Propagate staleness when monitored metrics move assumptions"},
            {"kind": "agent",          "target": "contradiction","why": "Surface contradictions between IC underwriting and realized metrics"},
        ],
        "S11": [
            {"kind": "agent",          "target": "extractor",    "why": "Extract claims from reunderwriting materials"},
            {"kind": "agent",          "target": "monitoring",   "why": "Run monitoring analysis to calibrate reunderwriting"},
            {"kind": "agent",          "target": "ic-assembler", "why": "Assemble reunderwriting IC package for decision"},
            {"kind": "human",          "target": "reunderwriting-decision", "why": "Hold / exit / restructure decision — human only (policy row 7)"},
        ],
        "S12": [
            {"kind": "agent",          "target": "exit-assembler","why": "Assemble exit IC package comparing entry thesis to realized outcome"},
            {"kind": "human",          "target": "exit-decision", "why": "Exit decision — authority-only human action (policy row 8)"},
            {"kind": "agent",          "target": "archive",       "why": "Write outcome record and propagate Teaching to brain archives"},
        ],
        "S13": [
            {"kind": "agent",          "target": "archive",       "why": "Finalize outcome record if not yet written"},
            {"kind": "agent",          "target": "librarian",     "why": "Propagate realized outcomes to cross-deal brain archives"},
            {"kind": "agent",          "target": "pipeline",      "why": "Update portfolio pipeline brief to reflect closed position"},
        ],
    }

    def snapshot(self):
        return {str(f): f.stat().st_mtime
                for pat in ("*/events/*.md", "*/claims/*.md", "*/questions/*.md", "*/assumptions/*.md")
                for f in (VAULT / "deals").glob(pat)}

    def act(self, changed):
        for deal in {Path(p).parts[-3] for p in changed}:
            self.run(deal)

    def run(self, deal: str) -> dict:
        """Core dispatch: read state, build plan, write plan.md, emit event."""
        import re as _re
        indexer.build().close()
        db = sqlite3.connect(indexer.DB)

        # 1. Derived state (never compute here — read what state-resolver wrote)
        state_row = db.execute(
            "SELECT frontmatter FROM nodes WHERE type='deal' AND id=?", (deal,)).fetchone()
        if not state_row:
            return {"summary": f"{deal}: not in index", "proposed": []}
        dfm = json.loads(state_row[0])
        state = dfm.get("state", "S0_INTAKE")
        phase_key = state.split("_")[0] if "_" in state else state[:2]

        # 2. Open critical questions
        crit_open = db.execute(
            "SELECT n.id, n.title, n.frontmatter FROM nodes n "
            "WHERE n.type='question' AND n.deal=? AND n.state IN ('open','reducing') "
            "AND json_extract(n.frontmatter,'$.critical')=1", (deal,)).fetchall()

        # 3. Claims + contradictions
        claim_rows = db.execute(
            "SELECT id, epistemic FROM nodes WHERE type='claim' AND deal=?", (deal,)).fetchall()
        contra_rows = db.execute(
            "SELECT subject FROM nodes WHERE type='claim' AND deal=? AND subject IS NOT NULL "
            "GROUP BY subject HAVING COUNT(DISTINCT value)>1", (deal,)).fetchall()

        # 4. Assumptions
        assume_rows = db.execute(
            "SELECT id, frontmatter FROM nodes WHERE type='assumption' AND deal=?", (deal,)).fetchall()
        stale_assumes = [aid for aid, fm_r in assume_rows if json.loads(fm_r).get("stale")]

        # 5. Previous plan (to compute what changed)
        plan_path = VAULT / "deals" / deal / "plan.md"
        prev_plan_text = plan_path.read_text(encoding="utf-8") if plan_path.exists() else ""

        # 6. Workstream outputs
        output_rows = db.execute(
            "SELECT id, frontmatter FROM nodes WHERE type='workstream-output' AND deal=?", (deal,)).fetchall()

        # 7. Allowed next transitions from contracts
        allowed_next = [t for t in contracts.transitions()
                        if t["from"] == state][:6]

        # 8. Kernel gates for current phase (P3: process kernel integration)
        kernel_mandatory = contracts.gates_for_state(state)

        db.close()

        # --- build changed / opened sections ---
        # What changed: derive from diff of known counts vs previous plan
        prev_claim_count = 0
        prev_contra_count = 0
        if prev_plan_text:
            m = _re.search(r"claims extracted: (\d+)", prev_plan_text)
            if m:
                prev_claim_count = int(m.group(1))
            m = _re.search(r"contradictions: (\d+)", prev_plan_text)
            if m:
                prev_contra_count = int(m.group(1))

        new_claims = len(claim_rows) - prev_claim_count
        new_contras = len(contra_rows) - prev_contra_count

        changed_lines = []
        if new_claims > 0:
            changed_lines.append(f"- +{new_claims} new claim(s) extracted (total {len(claim_rows)})")
        elif prev_plan_text:
            changed_lines.append(f"- claims stable at {len(claim_rows)}")
        else:
            changed_lines.append(f"- {len(claim_rows)} claim(s) in graph")
        if new_contras > 0:
            changed_lines.append(f"- {new_contras} new contradiction(s) surfaced (total {len(contra_rows)})")
        if stale_assumes:
            changed_lines.append(f"- {len(stale_assumes)} assumption(s) stale: {', '.join(stale_assumes)}")
        if output_rows and not prev_plan_text:
            changed_lines.append(f"- {len(output_rows)} workstream output(s) exist")
        if not changed_lines:
            changed_lines.append("- no material change since last plan")

        # What it opened: proposed next steps from playbook
        proposed = self.PLAYBOOK.get(phase_key, self.PLAYBOOK.get("S0", []))

        # Enrich proposed with workstream-specific steps for open critical questions
        ws_targets = list({json.loads(fm_r).get("target-workstream")
                           for _, title, fm_r in crit_open
                           if json.loads(fm_r).get("target-workstream")} - {None, ""})
        if ws_targets and phase_key in ("S4", "S5"):
            proposed = [s for s in proposed if s.get("target") != "workstream"]
            for ws in ws_targets[:3]:
                proposed.append({"kind": "agent", "target": "workstream",
                                  "why": f"Workstream '{ws}' has open critical questions",
                                  "config": {"workstream": ws}})

        opened_lines = []
        for step in proposed:
            gate = " [HUMAN GATE]" if step["kind"] == "human" else ""
            ext = " [EXTERNAL EVENT]" if step["kind"] == "external-event" else ""
            opened_lines.append(f"- [{step['kind']}] → {step['target']}{gate}{ext}: {step['why']}")

        # Allowed transitions summary
        trans_lines = [f"- {t['triggers'][0]} → {t['to']}" for t in allowed_next[:4]] or ["(none found in contracts)"]

        # Kernel gate lines (P3): mandatory checkpoints from process kernel for this state
        kernel_lines = []
        for kg in kernel_mandatory:
            badge = "AXIOM — non-configurable" if kg["kernel_treatment"] == "AXIOM" else "ENFORCE — required"
            kernel_lines.append(
                f"- [{badge}] {kg['component_id']}: {kg['description'][:80]}"
                + (f"\n  locked: {kg['locked_elements']}" if kg['locked_elements'] and kg['locked_elements'] != "None." else "")
            )
        if not kernel_lines:
            kernel_lines.append("- (no AXIOM/ENFORCE gates mapped to this phase)")

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        plan_text = f"""---
type: plan
id: plan-{deal}
deal: "[[{deal}]]"
written-by: phase-coordinator
produced: {datetime.now().date()}
phase: {state}
claims extracted: {len(claim_rows)}
contradictions: {len(contra_rows)}
---

# Plan — {deal}

_(phase-coordinator, {now})_

## Current phase
`{state}` — {len(crit_open)} critical question(s) open, {len(claim_rows)} claim(s), {len(contra_rows)} contradiction(s)

## Critical open questions
{chr(10).join(f"- [[{qid}]] — {qtitle}" for qid, qtitle, _ in crit_open) or "- (none)"}

## What changed
{chr(10).join(changed_lines)}

## What it opened (proposed next steps)
{chr(10).join(opened_lines)}

## Kernel gates for this phase (process kernel — non-negotiable)
{chr(10).join(kernel_lines)}

## Allowed next transitions (from contracts)
{chr(10).join(trans_lines)}
"""
        plan_path.write_text(plan_text, encoding="utf-8")

        # Emit PLAN_UPDATED event
        eid = emit_event(deal, "PLAN_UPDATED", self.id, f"Phase coordinator plan written for {deal} (state: {state})")
        audit(self.id, self.activity_id, "plan-updated",
              f"{deal}: phase {state}, {len(proposed)} proposed steps, plan.md written",
              [f"deals/{deal}/plan.md", eid])

        summary = (f"{deal}: plan written — phase {state}, {len(crit_open)} critical open, "
                   f"{len(proposed)} proposed steps")
        return {"summary": summary, "proposed": proposed}


class IcAssembler(Agent):
    """Part C — Self-assembling IC package (LLM on claude-sonnet-5).
    Contract HVA_COMMERCIAL_01 (machine_assisted_extraction). Reads the full
    deal graph (questions+states, claims by epistemic type, assumptions+versions,
    contradictions, workstream outputs, prior decisions) and writes
    deals/<id>/ic/ic-package.md. Previous versions kept append-only as
    ic-package-vN.md. Never writes a decision record — the human decides."""
    id = "ic-assembler"
    activity_id = "HVA_COMMERCIAL_01"  # machine_assisted_extraction
    watches = "deals/*/ic"

    def snapshot(self):
        return {str(f): f.stat().st_mtime for f in (VAULT / "deals").glob("*/ic/*.md")}

    def act(self, changed):
        for deal in {Path(p).parts[-4] for p in changed if Path(p).parts[-2] == "ic"}:
            self.run(deal)

    def run(self, deal: str) -> dict:
        """Assemble the IC package via LLM and write it as deals/<id>/ic/ic-package.md."""
        import sys as _sys
        # Load vault context for this deal
        deal_root = VAULT / "deals" / deal
        ic_dir = deal_root / "ic"
        ic_dir.mkdir(parents=True, exist_ok=True)

        # Build version: keep previous as ic-package-vN.md
        pkg_path = ic_dir / "ic-package.md"
        version = 1
        if pkg_path.exists():
            existing_versions = sorted(ic_dir.glob("ic-package-v*.md"))
            version = len(existing_versions) + 2
            # Archive the current one
            archive_path = ic_dir / f"ic-package-v{version - 1}.md"
            archive_path.write_text(pkg_path.read_text(encoding="utf-8"), encoding="utf-8")

        # --- Gather context ---
        indexer.build().close()
        db = sqlite3.connect(indexer.DB)

        questions = db.execute(
            "SELECT id, title, state, frontmatter FROM nodes WHERE type='question' AND deal=? ORDER BY id",
            (deal,)).fetchall()
        claims = db.execute(
            "SELECT id, epistemic, subject, value, frontmatter FROM nodes WHERE type='claim' AND deal=? ORDER BY id",
            (deal,)).fetchall()
        assumptions = db.execute(
            "SELECT id, title, frontmatter FROM nodes WHERE type='assumption' AND deal=? ORDER BY id",
            (deal,)).fetchall()
        events = db.execute(
            "SELECT id, frontmatter FROM nodes WHERE type='event' AND deal=? ORDER BY id",
            (deal,)).fetchall()
        outputs = db.execute(
            "SELECT id, path FROM nodes WHERE type='workstream-output' AND deal=? ORDER BY id",
            (deal,)).fetchall()
        decisions = db.execute(
            "SELECT id, title, frontmatter FROM nodes WHERE type='decision' AND deal=? ORDER BY id",
            (deal,)).fetchall()

        # Contradictions: same subject, >1 distinct value
        contra_rows = db.execute(
            "SELECT subject, GROUP_CONCAT(id || ' [' || COALESCE(epistemic,'?') || ']=' || COALESCE(value,'?'), ' | ') "
            "FROM nodes WHERE type='claim' AND deal=? AND subject IS NOT NULL "
            "GROUP BY subject HAVING COUNT(DISTINCT value) > 1", (deal,)).fetchall()

        # Prior IC packages (for footer diff)
        prior_pkgs = sorted(ic_dir.glob("ic-package-v*.md"))

        db.close()

        # Format context sections
        def fmt_questions(qs):
            lines = []
            for qid, qtitle, qstate, fm_r in qs:
                fm = json.loads(fm_r)
                crit = " [CRITICAL]" if fm.get("critical") else ""
                ws = f" [ws:{fm.get('target-workstream','')}]" if fm.get("target-workstream") else ""
                lines.append(f"  - [{qstate}]{crit}{ws} {qid}: {qtitle}")
            return "\n".join(lines) or "  (none)"

        def fmt_claims(cs):
            by_ep: dict = {}
            for cid, ep, subj, val, _ in cs:
                by_ep.setdefault(ep or "asserted", []).append(f"  {cid}: {subj} = {val}")
            lines = []
            for ep in ("attested", "observed", "derived", "asserted"):
                if ep in by_ep:
                    lines.append(f"  [{ep}]")
                    lines.extend(by_ep[ep][:20])
            return "\n".join(lines) or "  (none)"

        def fmt_assumptions(as_):
            lines = []
            for aid, atitle, fm_r in as_:
                fm = json.loads(fm_r)
                stale = " [STALE]" if fm.get("stale") else ""
                lines.append(f"  {aid} v{fm.get('version',1)}{stale}: {fm.get('value','?')} — {atitle or fm.get('statement','')}")
            return "\n".join(lines) or "  (none)"

        def fmt_contras(cs):
            lines = []
            for subj, detail in cs:
                lines.append(f"  {subj}: {detail}")
            return "\n".join(lines) or "  (none)"

        def fmt_outputs(os_):
            lines = []
            for oid, opath in os_:
                full = VAULT / opath
                if full.exists():
                    body = full.read_text(encoding="utf-8")
                    # first 400 chars of body after frontmatter
                    body_text = body.split("---", 2)[-1].strip()[:400]
                    lines.append(f"  {oid}:\n  {body_text}")
            return "\n".join(lines) or "  (none)"

        def fmt_decisions(ds):
            lines = []
            for did, dtitle, fm_r in ds:
                lines.append(f"  {did}: {dtitle}")
            return "\n".join(lines) or "  (none)"

        # Deal frontmatter
        deal_fm_raw = (VAULT / "deals" / deal / "deal.md").read_text(encoding="utf-8")
        thesis = ""
        state = "S0_INTAKE"
        m = __import__("re").search(r"^thesis:\s*\"?(.+?)\"?\s*$", deal_fm_raw, __import__("re").MULTILINE)
        if m:
            thesis = m.group(1)
        m = __import__("re").search(r"^state:\s*(\S+)", deal_fm_raw, __import__("re").MULTILINE)
        if m:
            state = m.group(1)

        # Prior version footer
        prev_footer = ""
        if prior_pkgs:
            prev_text = prior_pkgs[-1].read_text(encoding="utf-8")
            prev_m = __import__("re").search(r"## Footer.*?$", prev_text, __import__("re").DOTALL)
            if prev_m:
                prev_footer = prev_m.group(0)[:400]

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        system_prompt = (
            "You are the PE OS ic-assembler agent. Your role is EPISTEMIC ONLY — you assemble the "
            "decision basis, you NEVER write the decision itself. The human decides. "
            "Produce a structured IC package in plain markdown. "
            "You MUST include ALL of these sections in your output, clearly headed:\n"
            "1. ## Recommendation-neutral decision basis\n"
            "2. ## Resolved questions (with strongest epistemic chain)\n"
            "3. ## Accepted-unresolved ledger (what proceeding accepts; exposure)\n"
            "4. ## Unresolved contradictions (verbatim from the graph)\n"
            "5. ## Assumptions table (id | value | version | stale)\n"
            "6. ## IC Shadowing (likely objections inferred from question types + past decisions)\n"
            "7. ## Footer: changed / opened since previous package\n"
            "Be precise, cite claim ids, weigh epistemic types "
            "(attested > observed > derived > asserted). "
            "Do not invent any data not present in the context."
        )

        user_prompt = (
            f"DEAL: {deal}\n"
            f"THESIS: {thesis}\n"
            f"DERIVED STATE: {state}\n\n"
            f"QUESTIONS:\n{fmt_questions(questions)}\n\n"
            f"CLAIMS BY EPISTEMIC TYPE:\n{fmt_claims(claims)}\n\n"
            f"ASSUMPTIONS:\n{fmt_assumptions(assumptions)}\n\n"
            f"CONTRADICTIONS:\n{fmt_contras(contra_rows)}\n\n"
            f"WORKSTREAM OUTPUTS:\n{fmt_outputs(outputs)}\n\n"
            f"PRIOR DECISIONS:\n{fmt_decisions(decisions)}\n\n"
            f"PREVIOUS IC FOOTER (for diff):\n{prev_footer}\n\n"
            "Produce the complete IC package following all 7 sections above."
        )

        # Call LLM: prefer ANTHROPIC_API_KEY (direct), then AI Gateway, then headless claude CLI.
        import json as _json
        import os as _os
        import shutil as _shutil
        import urllib.request
        anthropic_key = _os.environ.get("ANTHROPIC_API_KEY")
        gateway_token = _os.environ.get("VERCEL_OIDC_TOKEN") or _os.environ.get("AI_GATEWAY_API_KEY")
        ic_body = None
        last_exc = None
        if anthropic_key:
            try:
                payload = {
                    "model": _os.environ.get("PEOS_MODEL", "claude-sonnet-5"),
                    "max_tokens": 8000,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}]
                }
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    data=_json.dumps(payload).encode(), method="POST",
                    headers={"Content-Type": "application/json",
                             "x-api-key": anthropic_key,
                             "anthropic-version": "2023-06-01"})
                with urllib.request.urlopen(req, timeout=280) as resp:
                    blocks = _json.loads(resp.read())["content"]
                    ic_body = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            except Exception as exc:
                last_exc = exc
        if ic_body is None and gateway_token:
            try:
                payload = {
                    "model": _os.environ.get("PEOS_GATEWAY_MODEL", "anthropic/claude-sonnet-4.6"),
                    "max_tokens": 8000,
                    "messages": [{"role": "system", "content": system_prompt},
                                 {"role": "user", "content": user_prompt}]
                }
                req = urllib.request.Request(
                    "https://ai-gateway.vercel.sh/v1/chat/completions",
                    data=_json.dumps(payload).encode(), method="POST",
                    headers={"Content-Type": "application/json",
                             "Authorization": f"Bearer {gateway_token}"})
                with urllib.request.urlopen(req, timeout=280) as resp:
                    ic_body = _json.loads(resp.read())["choices"][0]["message"]["content"]
            except Exception as exc:
                last_exc = exc
        if ic_body is None and _shutil.which("claude"):
            # Fallback: headless claude CLI (uses OAuth, same as extractor/proposer)
            prompt_text = f"SYSTEM: {system_prompt}\n\nUSER: {user_prompt}"
            try:
                r = subprocess.run(
                    ["claude", "-p", prompt_text, "--permission-mode", "acceptEdits"],
                    capture_output=True, text=True, cwd=ROOT, timeout=480)
                if r.returncode == 0 and r.stdout.strip():
                    ic_body = r.stdout.strip()
                else:
                    last_exc = RuntimeError(f"claude CLI returned rc={r.returncode}: {r.stderr[:200]}")
            except Exception as exc:
                last_exc = exc
        if not ic_body:
            raise RuntimeError(f"ic-assembler: all LLM paths failed. Last error: {last_exc}")

        # Write ic-package.md with frontmatter
        pkg_text = f"""---
type: ic-package
id: ic-package-{deal}
deal: "[[{deal}]]"
version: {version}
produced: {datetime.now().date()}
written-by: ic-assembler
state: {state}
---

# IC Package — {deal}

_(ic-assembler, {now_str}, v{version})_

{ic_body}
"""
        pkg_path.write_text(pkg_text, encoding="utf-8")

        audit(self.id, self.activity_id, "ic-package-written",
              f"{deal}: v{version}, {len(questions)} questions, {len(claims)} claims, "
              f"{len(contra_rows)} contradiction(s)",
              [f"deals/{deal}/ic/ic-package.md"])

        summary = (f"{deal}: IC package v{version} written — {len(questions)} questions, "
                   f"{len(claims)} claims, {len(contra_rows)} contradiction(s), "
                   f"{len(contra_rows)} contradictions verbatim")
        return {"summary": summary}


def _state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def _save(st: dict):
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(st))


# ── Model graph helpers ──────────────────────────────────────────────────────

def _model_graph(deal: str) -> dict | None:
    """Load the model graph (nodes + dependency map) for a deal, or None."""
    path = VAULT / "deals" / deal / "models" / "model_graph.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# Keys that live alongside the node adjacency map in model_graph.json but are
# not themselves model nodes.
_GRAPH_RESERVED_KEYS = {"stale_nodes", "dependencies", "nodes", "edges", "metadata"}


def _node_for_subject(graph: dict, subject: str) -> str | None:
    """Best-effort: find the best-matching model node for a claim subject.

    Priority: specific EBITDA basis > generic EBITDA keyword > other keywords.
    """
    subj = subject.lower()
    # model_graph.json is a flat adjacency map (node_id -> [dependent ids]).
    # Older/richer shapes carry a "nodes" list of dicts. Normalise both to a
    # list of {model_node_id, name} so lookup works regardless of shape.
    raw_nodes = graph.get("nodes")
    if isinstance(raw_nodes, list):
        nodes = raw_nodes
    else:
        nodes = [{"model_node_id": nid, "name": nid}
                 for nid in graph if nid not in _GRAPH_RESERVED_KEYS]

    # Tier 1: specific EBITDA basis matching
    ebitda_basis = [
        ("qoe",        "MN-QOE-EBITDA"),
        ("firm",       "MN-FIRM-EBITDA"),
        ("covenant",   "MN-COV-EBITDA"),
        ("seller",     "MN-SELLER-EBITDA"),
    ]
    if "ebitda" in subj or "ebita" in subj:
        for key, nid in ebitda_basis:
            if key in subj:
                if any(n.get("model_node_id") == nid for n in nodes):
                    return nid
        # generic EBITDA — prefer firm (our underwriting basis)
        return "MN-FIRM-EBITDA" if any(n.get("model_node_id") == "MN-FIRM-EBITDA" for n in nodes) else None

    # Tier 2: direct node name Jaccard match
    from tools.benchmark_runner import _jaccard as _j
    best_nid, best_score = None, 0.0
    for node in nodes:
        name = node.get("name", "").lower()
        score = _j(subj, name)
        if score > best_score:
            best_score = score
            best_nid = node.get("model_node_id")
    if best_score >= 0.25:
        return best_nid

    # Tier 3: keyword fallback
    kw_map = [
        (["revenue"],                    "input"),
        (["exit multiple", "exit_multiple"], "assumption_series"),
        (["growth", "platform growth"],  "assumption_series"),
        (["margin"],                     "assumption_series"),
        (["dso"],                        "assumption_series"),
        (["capex"],                      "assumption_series"),
        (["wip"],                        "assumption_series"),
        (["moic"],                       "output"),
        (["irr", "xirr"],               "output"),
        (["debt"],                       "input"),
        (["equity", "sponsor"],         "input"),
        (["concentration"],              "input"),
        (["nwc", "working capital"],    "input"),
    ]
    for patterns, kind in kw_map:
        if any(p in subj for p in patterns):
            for node in nodes:
                if node.get("kind") == kind:
                    return node["model_node_id"]
    return None


def _mark_model_node_stale(deal: str, graph: dict, node_id: str) -> list[str]:
    """Mark a model node and its downstream dependents stale in the model graph JSON.
    Returns list of node_ids marked stale."""
    # model_graph.json stores the dependency map at the top level
    # (node_id -> [dependent ids]); richer shapes nest it under "dependencies".
    # "stale_nodes" is a marker list we write back, never a node.
    deps = graph.get("dependencies")
    if not isinstance(deps, dict):
        deps = {k: v for k, v in graph.items()
                if k not in _GRAPH_RESERVED_KEYS and isinstance(v, list)}
    # Collect transitive downstream
    downstream: list[str] = []
    frontier = [node_id]
    visited = {node_id}
    while frontier:
        cur = frontier.pop()
        for tgt in deps.get(cur, []):
            if tgt not in visited:
                visited.add(tgt)
                downstream.append(tgt)
                frontier.append(tgt)
    # Write stale markers into model_graph.json
    stale_set = graph.setdefault("stale_nodes", [])
    for nid in [node_id] + downstream:
        if nid not in stale_set:
            stale_set.append(nid)
    path = VAULT / "deals" / deal / "models" / "model_graph.json"
    path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    return [node_id] + downstream


# ── Monitoring IC baseline helper ────────────────────────────────────────────

def _ic_baseline_claims(deal: str) -> list[dict]:
    """Load IC-era claims (epistemic=attested, from IC/firm sources) as baseline."""
    import re as _re
    cdir = VAULT / "deals" / deal / "claims"
    if not cdir.exists():
        return []
    baseline = []
    for f in sorted(cdir.glob("c-*.md")):
        txt = f.read_text(encoding="utf-8")
        ep_m = _re.search(r'^epistemic:\s*(\w+)', txt, _re.MULTILINE)
        subj_m = _re.search(r'^subject:\s*"?([^"\n]+)"?', txt, _re.MULTILINE)
        val_m  = _re.search(r'^value:\s*"?([^"\n]+)"?', txt, _re.MULTILINE)
        art_m  = _re.search(r'^artifact:\s*"?([^"\n]+)"?', txt, _re.MULTILINE)
        if not (ep_m and subj_m and val_m):
            continue
        ep = ep_m.group(1)
        artifact = art_m.group(1).lower() if art_m else ""
        # IC / firm baseline: attested + from IC memo or firm assessment
        if ep not in ("attested",) or not any(k in artifact for k in ("ic_memo", "initial_assessment", "firm")):
            continue
        try:
            v = float(val_m.group(1).replace("$", "").replace("m", "").replace("mm", "").replace("%", "").strip())
        except ValueError:
            continue
        baseline.append({
            "id": f.stem, "subject": subj_m.group(1).strip(),
            "value": v, "artifact": artifact,
        })
    return baseline


# ── New agents: Monitoring, ExitAssembler, Archive, Pipeline ─────────────────

class MonitoringAgent(Agent):
    """S10/S11 — Compares realized monitoring metrics against IC underwriting baseline.

    Watches deals/*/claims for new monitoring-era claims (identified by source artifact).
    For each numeric monitoring claim:
      1. Finds the best-matching IC baseline claim (same subject).
      2. If divergence > threshold → emits PERFORMANCE_ALERT event.
      3. Identifies the corresponding model node → marks it and downstream stale
         via model_graph.json (staleness cascade).
      4. Logs delta table for human review.

    Deterministic — no LLM. Agents never adjudicate which value is right.
    """
    id = "monitoring"
    activity_id = "HVA_COMMERCIAL_02"  # deterministic_automation
    watches = "deals/*/claims"

    MONITORING_KEYWORDS = ["boardpack", "board_pack", "monitoring", "compliance",
                           "amendment", "exit", "recovery"]
    DIVERGENCE_THRESHOLD = 0.10  # 10% divergence triggers alert

    def snapshot(self) -> dict:
        return {str(f): f.stat().st_mtime for f in (VAULT / "deals").glob("*/claims/*.md")}

    def act(self, changed: list[str]):
        import re as _re
        st = _state()
        seen = set(st.get("monitoring_seen", []))

        for path_str in changed:
            f = Path(path_str)
            if f.stem in seen:
                continue
            txt = f.read_text(encoding="utf-8")
            art_m = _re.search(r'^artifact:\s*"?([^"\n]+)"?', txt, _re.MULTILINE)
            if not art_m:
                continue
            artifact = art_m.group(1).lower()
            if not any(kw in artifact for kw in self.MONITORING_KEYWORDS):
                seen.add(f.stem)
                continue

            deal = f.parts[f.parts.index("deals") + 1]
            graph = _model_graph(deal)
            baseline = _ic_baseline_claims(deal)

            subj_m = _re.search(r'^subject:\s*"?([^"\n]+)"?', txt, _re.MULTILINE)
            val_m  = _re.search(r'^value:\s*"?([^"\n]+)"?', txt, _re.MULTILINE)
            if not (subj_m and val_m):
                seen.add(f.stem)
                continue

            subject = subj_m.group(1).strip()
            try:
                mon_val = float(val_m.group(1).replace("$","").replace("m","").replace("mm","").replace("%","").strip())
            except ValueError:
                seen.add(f.stem)
                continue

            # Match to IC baseline
            best_base = None
            best_score = 0.0
            for b in baseline:
                from tools.benchmark_runner import _jaccard
                score = _jaccard(subject, b["subject"])
                if score > best_score:
                    best_score = score
                    best_base = b

            if best_base and best_score >= 0.25:
                ic_val = best_base["value"]
                if ic_val != 0:
                    divergence = abs(mon_val - ic_val) / abs(ic_val)
                    if divergence >= self.DIVERGENCE_THRESHOLD:
                        pct = f"{divergence*100:.1f}%"
                        note = (f"MONITORING ALERT — {subject}: IC baseline={ic_val} "
                                f"vs realized={mon_val} ({pct} divergence). "
                                f"Source: {artifact}")
                        eid = emit_event(deal, "PERFORMANCE_ALERT", self.id, note)
                        wrote = [eid]

                        # Model node staleness cascade
                        if graph:
                            node_id = _node_for_subject(graph, subject)
                            if node_id:
                                stale_chain = _mark_model_node_stale(deal, graph, node_id)
                                cascade_note = f"Model staleness cascade: {' → '.join(stale_chain[:4])}"
                                eid2 = emit_event(deal, "ANALYTICAL_OBJECT_SUPERSEDED",
                                                 self.id, cascade_note)
                                wrote.append(eid2)
                                audit(self.id, self.activity_id, "model-stale",
                                      f"{deal}/{node_id}: {len(stale_chain)} downstream nodes stale",
                                      wrote)
                            else:
                                audit(self.id, self.activity_id, "alert-emitted",
                                      f"{deal} {subject}: {pct} divergence (no model node matched)",
                                      wrote)
                        else:
                            audit(self.id, self.activity_id, "alert-emitted",
                                  f"{deal} {subject}: {pct} divergence", wrote)

            seen.add(f.stem)

        st["monitoring_seen"] = sorted(seen)
        _save(st)


class ExitAssembler(Agent):
    """S12 — Assembles the exit IC package via LLM, once per exit-phase deal.

    Reads entry IC package + exit-era claims + realized outcome claims → writes
    deals/<deal>/ic/exit-package.md comparing entry thesis to realized outcome.
    LLM-assisted (machine_assisted_extraction). Append-only versions.
    Humans decide; this agent only assembles.
    """
    id = "exit-assembler"
    activity_id = "HVA_COMMERCIAL_01"  # machine_assisted_extraction
    watches = "deals/*/events"

    def snapshot(self) -> dict:
        return {str(f): f.stat().st_mtime for f in (VAULT / "deals").glob("*/events/*.md")}

    def act(self, changed: list[str]):
        import re as _re
        for path_str in changed:
            f = Path(path_str)
            txt = f.read_text(encoding="utf-8")
            kind_m = _re.search(r'^kind:\s*(\S+)', txt, _re.MULTILINE)
            if not kind_m or "EXIT" not in kind_m.group(1).upper():
                continue
            deal = f.parts[f.parts.index("deals") + 1]
            self.run(deal)

    def run(self, deal: str) -> str:
        """Assemble exit IC package. Returns path of written file."""
        deal_root = VAULT / "deals" / deal
        ic_dir = deal_root / "ic"
        ic_dir.mkdir(parents=True, exist_ok=True)
        exit_pkg = ic_dir / "exit-package.md"

        # Archive previous if exists
        if exit_pkg.exists():
            vn = len(list(ic_dir.glob("exit-package-v*.md"))) + 1
            (ic_dir / f"exit-package-v{vn}.md").write_text(
                exit_pkg.read_text(encoding="utf-8"), encoding="utf-8")

        # Gather: entry IC package + all claims grouped by era
        entry_pkg_text = (ic_dir / "ic-package.md").read_text(encoding="utf-8") \
            if (ic_dir / "ic-package.md").exists() else "(no IC entry package found)"

        import re as _re
        cdir = deal_root / "claims"
        exit_claims, monitoring_claims = [], []
        for cf in sorted(cdir.glob("c-*.md")) if cdir.exists() else []:
            txt = cf.read_text(encoding="utf-8")
            art_m = _re.search(r'^artifact:\s*"?([^"\n]+)"?', txt, _re.MULTILINE)
            artifact = art_m.group(1).lower() if art_m else ""
            if any(k in artifact for k in ("exit", "recovery")):
                exit_claims.append(txt[:400])
            elif any(k in artifact for k in ("boardpack", "board_pack", "monitoring", "compliance")):
                monitoring_claims.append(txt[:400])

        system = (
            "You are the PE OS exit assembler. Assemble an exit investment case package "
            "comparing the entry thesis to realized outcomes. Structure: "
            "1) Entry thesis summary, 2) Realized operating performance, "
            "3) Exit terms and returns, 4) Lessons learned for library. "
            "Agents never judge — only assemble. Be factual and precise."
        )
        user = (
            f"DEAL: {deal}\n\n"
            f"ENTRY IC PACKAGE (summary):\n{entry_pkg_text[:3000]}\n\n"
            f"MONITORING CLAIMS ({len(monitoring_claims)} items):\n" +
            "\n---\n".join(monitoring_claims[:10]) +
            f"\n\nEXIT-ERA CLAIMS ({len(exit_claims)} items):\n" +
            "\n---\n".join(exit_claims[:10]) +
            "\n\nWrite the exit IC package in markdown."
        )

        pkg_text = self._skeleton(deal, monitoring_claims, exit_claims)
        try:
            result = _api_json(system, user, max_tokens=4000)
            # _api_json expects JSON but exit assembler returns markdown — handle gracefully
            pkg_text = str(result) if isinstance(result, str) else json.dumps(result, indent=2)
        except Exception:
            pass  # keep skeleton as fallback

        header = (f"---\ntype: exit-package\ndeal: {deal}\nwritten-by: exit-assembler\n"
                  f"generated: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n---\n\n")
        exit_pkg.write_text(header + pkg_text, encoding="utf-8")
        eid = emit_event(deal, "EXIT_PACKAGE_ASSEMBLED", self.id,
                         f"Exit IC package written: {len(exit_claims)} exit claims, "
                         f"{len(monitoring_claims)} monitoring claims")
        audit(self.id, self.activity_id, "exit-package-written",
              f"{deal}: exit-package.md ({len(exit_claims)} exit claims)", [str(exit_pkg), eid])
        return str(exit_pkg)

    def _skeleton(self, deal: str, monitoring: list, exit_claims: list) -> str:
        return (
            f"# Exit Investment Case — {deal}\n\n"
            f"_Generated {datetime.now().strftime('%Y-%m-%d')}_\n\n"
            f"## Entry Thesis\n\nSee ic/ic-package.md for the entry IC.\n\n"
            f"## Monitoring Summary\n\n{len(monitoring)} monitoring claims on record.\n\n"
            f"## Exit Terms\n\n{len(exit_claims)} exit-era claims on record.\n\n"
            f"## Lessons Learned\n\n_Human to complete._\n"
        )


class ArchiveAgent(Agent):
    """S12/S13 — Writes the outcome record once the exit package is assembled.

    Watches deals/*/ic for exit-package.md. On first appearance:
      - Writes deals/<deal>/outcomes/o-<deal>-<n>.md (append-only, never edited).
      - Tags teaching claims (epistemic=derived, rests-on the exit outcome)
        so the Librarian can propagate them to the cross-deal brain.
    Deterministic — no LLM.
    """
    id = "archive"
    activity_id = "HVA_COMMERCIAL_02"  # deterministic_automation
    watches = "deals/*/ic"

    def snapshot(self) -> dict:
        return {str(f): f.stat().st_mtime for f in (VAULT / "deals").glob("*/ic/*.md")}

    def act(self, changed: list[str]):
        st = _state()
        archived = set(st.get("archived_outcomes", []))

        for path_str in changed:
            f = Path(path_str)
            if "exit-package" not in f.name or f.stem in archived:
                continue
            deal = f.parts[f.parts.index("deals") + 1]
            self._write_outcome(deal, f)
            archived.add(f.stem)

        st["archived_outcomes"] = sorted(archived)
        _save(st)

    def _write_outcome(self, deal: str, exit_pkg: Path) -> str:
        out_dir = VAULT / "deals" / deal / "outcomes"
        out_dir.mkdir(parents=True, exist_ok=True)
        n = len(list(out_dir.glob("o-*.md"))) + 1
        oid = f"o-{deal}-{n:03d}"
        pkg_text = exit_pkg.read_text(encoding="utf-8")

        # Load model graph for final MOIC/IRR if available
        graph = _model_graph(deal)
        moic_node = None
        if graph:
            moic_node = next(
                (nd for nd in graph.get("nodes", []) if "MOIC" in nd.get("model_node_id", "") and "BASE" in nd.get("model_node_id", "")),
                None)

        returns_line = (f"model-moic: {moic_node['value']}" if moic_node else "model-moic: (see exit package)")

        content = (
            f"---\ntype: outcome\nid: {oid}\ndeal: {deal}\n"
            f"exit-package: \"[[{exit_pkg.stem}]]\"\n"
            f"{returns_line}\n"
            f"archived: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n"
            f"written-by: archive\n---\n\n"
            f"# Outcome Record — {deal}\n\n"
            f"Outcome recorded from exit package. See [[{exit_pkg.stem}]] for full detail.\n\n"
            f"## Teaching\n\n"
            f"_Key lessons to propagate to cross-deal library — human to complete._\n"
        )
        (out_dir / f"{oid}.md").write_text(content, encoding="utf-8")
        eid = emit_event(deal, "OUTCOME_ARCHIVED", self.id,
                         f"Outcome record {oid} written from {exit_pkg.name}")
        audit(self.id, self.activity_id, "outcome-archived",
              f"{deal}: {oid} written", [oid, eid])
        return oid


class PipelineAgent(Agent):
    """S13 / cross-deal — Maintains vault/PIPELINE.md, a portfolio brief.

    Deterministic. Rebuilds whenever any deal state changes. Shows each deal's
    current phase, deal state, critical open questions, and last event.
    Never set deal state — only reads derived state.
    """
    id = "pipeline"
    activity_id = "HVA_COMMERCIAL_02"  # deterministic_automation
    watches = "deals/*/events"

    def snapshot(self) -> dict:
        return {str(f): f.stat().st_mtime for f in (VAULT / "deals").glob("*/events/*.md")}

    def act(self, changed: list[str]) -> None:  # noqa: ARG002
        self.rebuild()

    def rebuild(self) -> str:
        """Rebuild PIPELINE.md. Returns the written content."""
        import re as _re
        lines = [
            f"---\ntype: pipeline-brief\nwritten-by: pipeline\n"
            f"updated: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n---\n\n",
            "# Portfolio Pipeline\n\n",
            f"_Updated {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n",
            "| Deal | State | Phase | Critical Open | Last Event |\n",
            "|------|-------|-------|---------------|------------|\n",
        ]

        for deal in sorted(deals()):
            deal_root = VAULT / "deals" / deal
            state = _deal_state(deal) or "unknown"
            phase_key = state.split("_")[0] if "_" in state else state[:2]

            # Count critical open questions
            q_dir = deal_root / "questions"
            crit_open = 0
            if q_dir.exists():
                for qf in q_dir.glob("*.md"):
                    txt = qf.read_text(encoding="utf-8")
                    if _re.search(r'^critical:\s*true', txt, _re.MULTILINE) and \
                       _re.search(r'^state:\s*(open|reducing)', txt, _re.MULTILINE):
                        crit_open += 1

            # Last event
            ev_dir = deal_root / "events"
            last_ev = "—"
            if ev_dir.exists():
                evs = sorted(ev_dir.glob("*.md"))
                if evs:
                    last_txt = evs[-1].read_text(encoding="utf-8")
                    kind_m = _re.search(r'^kind:\s*(\S+)', last_txt, _re.MULTILINE)
                    last_ev = kind_m.group(1) if kind_m else evs[-1].stem

            lines.append(f"| {deal} | {state} | {phase_key} | {crit_open} | {last_ev} |\n")

        lines.append("\n---\n_This file is machine-written. Edit the underlying deal files to change it._\n")
        content = "".join(lines)
        out = VAULT / "PIPELINE.md"
        out.write_text(content, encoding="utf-8")
        audit(self.id, self.activity_id, "pipeline-updated",
              f"{len(deals())} deals in portfolio brief", [str(out)])
        return content


def main():
    agents = [Sentinel(), StateResolver(), Contradiction(), Librarian(), Transcriber(),
              Extractor(), Coordinator(), Proposer(), Staleness(), PhaseCoordinator(),
              IcAssembler(), MonitoringAgent(), ExitAssembler(), ArchiveAgent(), PipelineAgent()]
    print("PE OS agent runtime — deployed agents:")
    for a in agents:
        print(f"  · {a.id:<15} watches {a.watches:<24} contract {a.activity_id} "
              f"[{a.contract['automation_class']}]")
    print(f"polling every {POLL_SECONDS}s · audit → vault/audit/agent-log.jsonl · Ctrl+C to stop\n")
    audit("runtime", "-", "deployed", f"{len(agents)} agents online", [])
    snaps = {a.id: a.snapshot() for a in agents}
    while True:
        time.sleep(POLL_SECONDS)
        for a in agents:
            try:
                now = a.snapshot()
                changed = [p for p, m in now.items() if snaps[a.id].get(p) != m]
                snaps[a.id] = now
                if changed:
                    a.act(changed)
            except Exception as exc:  # an agent failing must never kill the runtime
                audit(a.id, a.activity_id, "error", str(exc), [])


if __name__ == "__main__":
    main()
