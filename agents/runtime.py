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

VAULT = ROOT / "vault"
AUDIT = VAULT / "audit" / "agent-log.jsonl"
STATE_FILE = ROOT / ".index" / "runtime-state.json"
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
        return {str(f): f.stat().st_mtime for f in (VAULT / "inbox").glob("*") if f.is_file()}

    def act(self, changed):
        ds = deals()
        for path in changed:
            name = Path(path).name
            if len(ds) == 1:
                eid = emit_event(ds[0], "ARTIFACT_ARRIVED", self.id, f"Artifact landed in inbox: {name}")
                audit(self.id, self.activity_id, "artifact-announced", name, [eid])
            else:
                audit(self.id, self.activity_id, "artifact-pending", f"{name} — multiple deals, needs routing", [])


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
        con = sqlite3.connect(ROOT / ".index" / "vault.db")
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
        con = sqlite3.connect(ROOT / ".index" / "vault.db")
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
    agents = [Sentinel(), StateResolver(), Contradiction(), Librarian()]
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
