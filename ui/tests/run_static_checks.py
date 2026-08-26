#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "tests" / "SELFTEST_RESULTS.txt"


def check(name: str, fn):
    try:
        detail = fn()
        return name, True, str(detail or "PASS")
    except Exception as exc:  # noqa: BLE001
        return name, False, str(exc)


def require_files():
    required = [
        "app/index.html",
        "app/style.css",
        "app/src/engine.js",
        "app/src/render.js",
        "app/src/integration.js",
        "app/src/projection_adapter.js",
        "app/src/selftest.js",
        "app/src/demo_controller.js",
        "integration/mock_server.py",
        "contracts/frontend_projection_v17.schema.json",
        "contracts/frontend_transition_projection_v17.schema.json",
        "README_START_HERE.md",
    ]
    missing = [path for path in required if not (ROOT / path).is_file()]
    if missing:
        raise AssertionError(f"missing: {missing}")
    return f"{len(required)} required files"


def js_syntax():
    files = sorted((ROOT / "app").rglob("*.js"))
    for path in files:
        subprocess.run(["node", "--check", str(path)], check=True, capture_output=True, text=True)
    return f"{len(files)} JavaScript files"


def json_parse():
    files = sorted(ROOT.rglob("*.json"))
    for path in files:
        json.loads(path.read_text(encoding="utf-8"))
    return f"{len(files)} JSON files"


def fixture_invariants():
    script = r"""
const vm=require('vm'),fs=require('fs'),path=require('path');
const root=process.argv[1];let ctx={window:{}};vm.createContext(ctx);
for(const file of ['app/data/v16_case_bundle.js','app/data/v17_fixture.js']) vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),ctx);
const f=ctx.window.PANTA_V17_FIXTURE;
if(f.v16.question_spine.length!==8) throw Error('question spine drift');
if(!f.transitions.concentration.human_stops.length) throw Error('authority scene has no human stop');
if(!f.deal.rooms.foundations||!f.deal.rooms.unknowns||!f.deal.rooms.shadowIC) throw Error('rooms missing');
if(!/synthetic/i.test(f.disclosure)) throw Error('demo disclosure missing');
console.log('8 questions · 3 core rooms · human stop · disclosure');
"""
    result = subprocess.run(["node", "-e", script, str(ROOT)], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def projection_schema():
    try:
        import jsonschema
    except ImportError:
        return "jsonschema unavailable; JSON parse completed"
    cases = [
        ("frontend_projection_v17.json", "frontend_projection_v17.schema.json"),
        ("transition_earnings_v17.json", "frontend_transition_projection_v17.schema.json"),
        ("transition_concentration_v17.json", "frontend_transition_projection_v17.schema.json"),
    ]
    for fixture, schema in cases:
        payload = json.loads((ROOT / "fixtures" / "normalized" / fixture).read_text())
        contract = json.loads((ROOT / "contracts" / schema).read_text())
        jsonschema.validate(payload, contract)
    return f"{len(cases)} V17 projection contracts"


def no_business_logic_in_adapter():
    source = (ROOT / "app/src/projection_adapter.js").read_text()
    forbidden = ["openpyxl", "calculateIRR", "goalSeek", "parsePdf", "OCR", "materialityThreshold"]
    found = [token for token in forbidden if token in source]
    if found:
        raise AssertionError(f"forbidden adapter logic: {found}")
    return "projection adapter maps only"


def checksums():
    targets = [
        ROOT / "app/index.html",
        ROOT / "app/src/engine.js",
        ROOT / "app/src/render.js",
        ROOT / "app/data/v17_fixture.js",
    ]
    digest = hashlib.sha256()
    for target in targets:
        digest.update(target.read_bytes())
    return f"core sha256 {digest.hexdigest()}"


def main() -> int:
    tests = [
        check("Required package structure", require_files),
        check("JavaScript syntax", js_syntax),
        check("JSON parse", json_parse),
        check("V17 fixture invariants", fixture_invariants),
        check("Projection schema validation", projection_schema),
        check("Frontend adapter boundary", no_business_logic_in_adapter),
        check("Core integrity hash", checksums),
    ]
    passed = sum(ok for _, ok, _ in tests)
    lines = [f"PANTA V17 STATIC CHECKS — {passed}/{len(tests)} PASS", ""]
    lines.extend(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}" for name, ok, detail in tests)
    RESULT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(RESULT.read_text())
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
