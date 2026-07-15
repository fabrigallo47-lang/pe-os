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


def main():
    agents = [Sentinel(), StateResolver(), Contradiction(), Librarian(), Transcriber(),
              Extractor(), Coordinator(), Proposer(), Staleness(), PhaseCoordinator(),
              IcAssembler()]
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
