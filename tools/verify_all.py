#!/usr/bin/env python3
"""
verify_all — one command that runs everything and prints a single verdict.

  make verify
  python3 tools/verify_all.py [--reference-kit PATH]

Stages
------
  1 regression suite        pins the audit fixes
  2 V7 acceptance           181 contract tests
  3 V7 end-to-end           21 executable-bridge tests
  4 retrieval + cascade     staleness propagation actually walks the graph
  5 grounding gate          how much extraction is human-verifiable
  6 PANTA reference runtime Antonio's engine, if his kit is present

Stage 6 is skipped when the reference kit is not on this machine — it ships
separately. Point --reference-kit at the unpacked PANTA_V7_INDEPENDENT_VALIDATOR
directory to include it.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

CIC_DEFAULT = Path.home() / "Downloads" / "PANTA_CIC_v1.1" / \
    "PANTA_Keystone_Canonical_Investment_Case_v1_1"


class Stage:
    def __init__(self, name: str):
        self.name = name
        self.ok: bool | None = None
        self.detail = ""

    def done(self, ok: bool, detail: str) -> "Stage":
        self.ok, self.detail = ok, detail
        return self


def _run(cmd: list[str], timeout: int = 900) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except Exception as exc:                       # pragma: no cover
        return 1, str(exc)


def stage_regression() -> Stage:
    s = Stage("Regression suite")
    rc, out = _run([PY, "tools/test_regression.py"])
    m = re.search(r"(\d+) passed, (\d+) failed", out)
    if not m:
        return s.done(False, "no result line")
    p, f = int(m.group(1)), int(m.group(2))
    return s.done(rc == 0 and f == 0, f"{p} passed, {f} failed")


def stage_v7() -> Stage:
    s = Stage("V7 acceptance")
    rc, out = _run([PY, "tools/test_v7.py"])
    m = re.search(r"(\d+)/(\d+) passed", out)
    if not m:
        return s.done(False, "no result line")
    got, tot = int(m.group(1)), int(m.group(2))
    return s.done(rc == 0 and got == tot, f"{got}/{tot} passed")


def stage_e2e() -> Stage:
    s = Stage("V7 end-to-end")
    rc, out = _run([PY, "tools/run_v7_end_to_end.py",
                    "--out", "pipeline_out/e3/K-IC/adapter_alpha/v7_e2e",
                    "--manifest", "K-IC"])
    m = re.search(r"(\d+)/(\d+) tests passed", out)
    if not m:
        return s.done(False, "no result line")
    got, tot = int(m.group(1)), int(m.group(2))
    return s.done(got == tot, f"{got}/{tot} tests passed")


def stage_cascade() -> Stage:
    s = Stage("Retrieval + staleness cascade")
    rc, out = _run([PY, "tools/test_retrieval.py", "--reset"])
    m = re.search(r"Stale model nodes:\s+(\d+)", out)
    node = re.search(r"Model node affected:\s+(\S+)", out)
    if not m:
        return s.done(False, "no cascade result")
    n = int(m.group(1))
    matched = node.group(1) if node else "?"
    # A cascade that marks only the trigger node is the bug this pins.
    return s.done(n > 1 and matched != "none",
                  f"{matched} → {n} nodes stale")


def stage_grounding() -> Stage:
    s = Stage("Grounding gate")
    claims = ROOT / "pipeline_out/e3/K-IC/e3_claims.json"
    if not claims.exists():
        return s.done(True, "skipped — no extraction on disk")
    rc, out = _run([PY, "tools/grounding_gate.py", "--claims", str(claims),
                    "--deal", "keystone"])
    clean = re.search(r"clean\s+:\s+(\d+)", out)
    total = re.search(r"claims\s+:\s+(\d+)", out)
    block = re.search(r"blocking findings\s+:\s+(\d+)", out)
    if not (clean and total):
        return s.done(False, "no gate result")
    # The gate is diagnostic: it reports, it does not fail the build.
    return s.done(True, f"{clean.group(1)}/{total.group(1)} clean, "
                        f"{block.group(1) if block else '?'} blocking")


def stage_reference(kit: Path | None) -> Stage:
    s = Stage("PANTA reference runtime (Antonio)")
    if kit is None or not kit.exists():
        return s.done(True, "skipped — reference kit not on this machine")
    engine = kit / "panta_reference"
    if not (engine / "runtime" / "panta_transition_engine.py").exists():
        return s.done(False, f"kit at {kit} has no runtime/panta_transition_engine.py")

    bundle = ROOT / "pipeline_out/e3/K-IC/adapter_alpha"
    script = f'''
import json, sys
sys.path.insert(0, {str(engine)!r})
from runtime.panta_transition_engine import apply_state_transition
B = {str(bundle)!r}
L = lambda n: json.load(open(B + "/" + n))
r = apply_state_transition(L("current_graph.json"),
                           [L("event_ebitda_correction.json")],
                           L("execution_mapping.json"),
                           L("keystone_materiality_policy_v0.json"),
                           L("keystone_authority_matrix_v0.json"))
to = r.get("transition_output", r)
ordered = to.get("ordered_transitions", [])
settled = [c for c in ordered if c.get("result") == "SETTLED"]
blocked = [c for c in ordered if c.get("result") == "BLOCKED"]
print(json.dumps({{
    "settlement": (to.get("partial_settlement_status") or {{}}).get("candidate"),
    "settled": len(settled), "blocked": len(blocked),
    "components": [c.get("member_ids") for c in settled],
}}))
'''
    rc, out = _run([PY, "-c", script])
    line = out.strip().splitlines()[-1] if out.strip() else ""
    try:
        d = json.loads(line)
    except Exception:
        return s.done(False, f"engine error: {out.strip()[:120]}")
    ok = d["settlement"] == "FULL" and d["settled"] > 0 and d["blocked"] == 0
    return s.done(ok, f"{d['settlement']}, {d['settled']} settled, {d['blocked']} blocked")


def _find_reference_kit() -> Path | None:
    """
    Locate Antonio's validator. It is distributed as a zip, so accept either an
    unpacked directory or the archive, which is expanded into a cache dir.
    """
    dirs = [
        ROOT / "PANTA_V7_INDEPENDENT_VALIDATOR",
        Path.home() / "Downloads" / "PANTA_V7_INDEPENDENT_VALIDATOR",
    ]
    for d in dirs:
        if (d / "panta_reference").exists():
            return d
        # some archives nest one level
        nested = d / "PANTA_V7_INDEPENDENT_VALIDATOR"
        if (nested / "panta_reference").exists():
            return nested

    for z in (ROOT / "PANTA_V7_INDEPENDENT_VALIDATOR.zip",
              Path.home() / "Downloads" / "PANTA_V7_INDEPENDENT_VALIDATOR.zip"):
        if not z.exists():
            continue
        import zipfile
        dest = ROOT / ".index" / "reference_kit"
        try:
            if not (dest / "panta_reference").exists():
                dest.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(z) as zf:
                    zf.extractall(dest)
            if (dest / "panta_reference").exists():
                return dest
            for child in dest.iterdir():
                if (child / "panta_reference").exists():
                    return child
        except Exception:
            return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Run every check and print one verdict")
    ap.add_argument("--reference-kit", type=Path, default=None,
                    help="Path to unpacked PANTA_V7_INDEPENDENT_VALIDATOR")
    a = ap.parse_args()

    kit = a.reference_kit or _find_reference_kit()

    bar = "=" * 66
    print(bar)
    print("PE OS — FULL VERIFICATION")
    print(bar)

    stages = [stage_regression(), stage_v7(), stage_e2e(), stage_cascade(),
              stage_grounding(), stage_reference(kit)]

    print()
    for s in stages:
        mark = "PASS" if s.ok else "FAIL"
        print(f"  [{mark}] {s.name:<34} {s.detail}")

    failed = [s for s in stages if not s.ok]
    print()
    print(bar)
    if failed:
        print(f"RESULT : FAIL — {len(failed)} stage(s)")
        for s in failed:
            print(f"         · {s.name}: {s.detail}")
    else:
        print("RESULT : PASS — all stages green")
    print(bar)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
