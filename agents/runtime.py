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
            before = {f.name for f in (VAULT / "deals" / deal / "claims").glob("*.md")}
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
            prompt = f"""You are the PE OS proposer agent. Work autonomously; never ask questions.

Deal: {deal}. Read vault/deals/{deal}/deal.md (the thesis), every question in questions/, every claim in claims/, and the schemas vault/ontology/assumption.md and vault/ontology/question.md.

1. Derive the 3-5 ASSUMPTIONS the deal proceeds on: each a quantified proposition that must be true for the thesis to hold, grounded in the extracted claims. Write one file each: vault/deals/{deal}/assumptions/a-{deal}-NNN.md following the schema exactly (statement, value quantified, basis = the claim ids it currently rests on, state: proposed, version: 1, proposed-by: proposer). Body: why the deal rests on it + revision history line v1.
2. For each existing question, add a `tests:` frontmatter field listing the assumption id(s) it tests (only where it genuinely tests one). Do not change any other field, never change state.
3. If a load-bearing assumption has NO question testing it, create the missing question file per the question schema (state: open, written-by: proposer, critical only if the thesis fails without it, tests: the assumption).
4. Report one line per file written."""
            try:
                r = subprocess.run(["claude", "-p", prompt, "--permission-mode", "acceptEdits"],
                                   capture_output=True, text=True, cwd=ROOT, timeout=480)
                new = sorted(f.stem for f in adir.glob("*.md"))
                st = _state(); st.setdefault("proposed", []).append(deal); _save(st)
                audit(self.id, self.activity_id, "assumptions-proposed" if new else "proposal-empty",
                      f"{deal}: {', '.join(new) if new else 'rc=' + str(r.returncode)}", new)
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


def _state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def _save(st: dict):
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(st))


def main():
    agents = [Sentinel(), StateResolver(), Contradiction(), Librarian(), Transcriber(),
              Extractor(), Coordinator(), Proposer(), Staleness()]
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
