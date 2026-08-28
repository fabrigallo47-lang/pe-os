#!/usr/bin/env python3
"""Executable acceptance suite for PANTA V19.B.

This suite is intentionally release-specific. It verifies the six V19.B
acceptance criteria and the integrity gates that protect them. It does not
claim production identity, a production compiler, or the external Anto
Transition Engine runtime.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import requests
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "01_PRODUCT_BUILD" / "app"
FIXTURES = ROOT / "01_PRODUCT_BUILD" / "fixtures"
SCHEMAS = APP / "contracts"
ADAPTER = ROOT / "07_ENGINEERING_CONTRACTS_AND_ADAPTERS" / "adapters" / "transition_runtime_adapter.py"
SAMPLES = ROOT / "07_ENGINEERING_CONTRACTS_AND_ADAPTERS" / "samples"
RESULTS_JSON = ROOT / "08_TEST_EVIDENCE" / "V19B_TEST_RESULTS.json"
RESULTS_TXT = ROOT / "08_TEST_EVIDENCE" / "V19B_TEST_RESULTS.txt"
BROWSER_DIR = ROOT / "08_TEST_EVIDENCE" / "browser"
BROWSER_DIR.mkdir(parents=True, exist_ok=True)

BINARY_SUFFIXES = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".mov", ".zip",
    ".xlsx", ".xls", ".docx", ".pptx", ".woff", ".woff2", ".ttf", ".otf",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_time(value: str) -> dt.datetime:
    text = str(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text += "T23:59:59Z"
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


def normalize_statement(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9%$]+", str(value).lower()))


def find_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("", 0))
        return int(sock.getsockname()[1])


def container_ip() -> str:
    output = subprocess.check_output(["hostname", "-I"], text=True).strip().split()
    return output[0] if output else "127.0.0.1"


class Suite:
    def __init__(self) -> None:
        self.results: list[dict[str, Any]] = []
        self.started_at = dt.datetime.now(dt.timezone.utc)

    def test(self, name: str, category: str, fn: Callable[[], Any]) -> None:
        start = time.perf_counter()
        try:
            evidence = fn()
            status = "PASS"
            error = None
        except Exception as exc:  # explicit test boundary
            status = "FAIL"
            evidence = None
            error = f"{type(exc).__name__}: {exc}"
        self.results.append(
            {
                "name": name,
                "category": category,
                "status": status,
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                "evidence": evidence,
                "error": error,
            }
        )
        print(f"[{status}] {category} :: {name}" + (f" — {error}" if error else ""), flush=True)

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            raise AssertionError(message)

    def finish(self) -> dict[str, Any]:
        ended = dt.datetime.now(dt.timezone.utc)
        counts = Counter(item["status"] for item in self.results)
        categories: dict[str, dict[str, int]] = {}
        for item in self.results:
            bucket = categories.setdefault(item["category"], {"PASS": 0, "FAIL": 0})
            bucket[item["status"]] += 1
        return {
            "suite": "PANTA V19.B acceptance and regression suite",
            "release": "19.1.0 / V19.B",
            "started_at": self.started_at.isoformat().replace("+00:00", "Z"),
            "ended_at": ended.isoformat().replace("+00:00", "Z"),
            "total": len(self.results),
            "passed": counts.get("PASS", 0),
            "failed": counts.get("FAIL", 0),
            "status": "PASS" if counts.get("FAIL", 0) == 0 else "FAIL",
            "categories": categories,
            "scope_limit": (
                "Tests the bundled V19.B product build, synthetic fixture packs, public schemas, "
                "pure engine-output adapter and stateful mock API. It does not certify production "
                "identity, enterprise persistence, external delivery, Fabri's production compiler, "
                "or Anto's separate frozen 22-case runtime implementation."
            ),
            "results": self.results,
        }


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None):
        response = requests.request(
            method,
            self.base + path,
            json=body,
            headers=headers or {},
            timeout=15,
        )
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}
        return response.status_code, data

    def bootstrap(self, case: str, actor: str = "partner", mode: str = "MOCK_CONNECTED"):
        status, data = self.call("GET", f"/bootstrap?mode={mode}&case_id={case}&actor={actor}")
        if status != 200:
            raise AssertionError(f"bootstrap failed: {status} {data}")
        return data

    def projection(self, case: str, session: str, as_of_date: str | None = None):
        suffix = f"&as_of_date={as_of_date}" if as_of_date else ""
        return self.call("GET", f"/cases/{case}/projection?session_id={session}{suffix}")


@contextlib.contextmanager
def server_process():
    port = find_free_port()
    server = ROOT / "01_PRODUCT_BUILD" / "mock_api" / "server.py"
    sessions = ROOT / "01_PRODUCT_BUILD" / "mock_api" / ".sessions"
    sessions.mkdir(exist_ok=True)
    for path in sessions.glob("*.json"):
        path.unlink()
    process = subprocess.Popen(
        [sys.executable, str(server), "--host", "0.0.0.0", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}/api/v19"
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            response = requests.get(base + "/bootstrap?mode=MOCK_CONNECTED&case_id=PROJECT-KEYSTONE", timeout=1)
            if response.status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.1)
    else:
        output = process.stdout.read() if process.stdout else ""
        process.kill()
        raise RuntimeError(f"mock server did not start: {output}")
    try:
        yield {
            "api": Api(base),
            "port": port,
            "browser_origin": f"http://{container_ip()}:{port}",
        }
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        for path in sessions.glob("*.json"):
            path.unlink()


def schema_registry() -> Registry:
    registry = Registry()
    for path in SCHEMAS.glob("*.schema.json"):
        schema = read_json(path)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


def assert_zero_schema_errors(schema_name: str, value: Any) -> None:
    schema = read_json(SCHEMAS / f"{schema_name}.schema.json")
    errors = sorted(
        Draft202012Validator(schema, registry=schema_registry(), format_checker=FormatChecker()).iter_errors(value),
        key=lambda error: list(error.path),
    )
    if errors:
        detail = "; ".join(f"{'.'.join(map(str, e.path))}: {e.message}" for e in errors[:10])
        raise AssertionError(f"{schema_name} validation returned {len(errors)} error(s): {detail}")


def typed_property_gaps(schema: Any, path: str = "$") -> list[str]:
    typing_keys = {"type", "const", "enum", "$ref", "anyOf", "oneOf", "allOf", "not"}
    output: list[str] = []
    if isinstance(schema, dict):
        for key, value in schema.get("properties", {}).items():
            if not typing_keys.intersection(value):
                output.append(f"{path}.properties.{key}")
            output.extend(typed_property_gaps(value, f"{path}.properties.{key}"))
        for key in ("$defs", "items", "additionalProperties"):
            if key in schema:
                output.extend(typed_property_gaps(schema[key], f"{path}.{key}"))
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            output.extend(typed_property_gaps(value, f"{path}[{index}]"))
    return output


def import_adapter():
    spec = importlib.util.spec_from_file_location("panta_v19b_transition_adapter", ADAPTER)
    if spec is None or spec.loader is None:
        raise RuntimeError("adapter import spec unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admission_payload(projection_payload: dict[str, Any], event_key: str, token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    projection = projection_payload["projection"]
    context = projection_payload["context"]
    event = projection["events"][event_key]
    payload = {
        "treatment_id": event["treatment_id"],
        "treatment_hash": sha256(event.get("proposed_treatment") or event.get("proposed_position")),
        "source_version_id": event["source_version_id"],
        "event_id": event["event_id"],
        "actor_id": context["authenticated_actor"]["actor_id"],
        "as_of_state_id": context["as_of_state_id"],
        "as_of_date": context["as_of_date"],
        "effective_date": event["effective_date"],
        "known_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "idempotency_key": token,
    }
    return event, payload


def browser_acceptance(origin: str) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    args = ["--no-sandbox", "--no-proxy-server", "--proxy-bypass-list=*"]
    chromium = "/usr/bin/chromium"
    if not Path(chromium).exists():
        raise AssertionError("system Chromium is unavailable")
    evidence: dict[str, Any] = {}

    def url(case: str, view: str = "deal-command") -> str:
        api = f"{origin}/api/v19"
        return (
            f"{origin}/?mode=mock&case={case}&actor=partner&api={api}"
            f"#case={case}&view={view}"
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=chromium, args=args)

        # General growth and bitemporal rendering.
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        console_errors: list[str] = []
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.goto(url("PROJECT-ORION"), wait_until="networkidle", timeout=30000)
        page.wait_for_selector("#as-of-switcher", timeout=15000)
        if page.locator("#case-switcher").input_value() != "PROJECT-ORION":
            raise AssertionError("case switcher did not load Orion")
        page.select_option("#as-of-switcher", "2026-05-12")
        page.wait_for_function("PantaStore.get().context && PantaStore.get().context.as_of_date === '2026-05-12'")
        historical_count = page.evaluate("PantaStore.get().projection.deal.claims.length")
        if historical_count != 6:
            raise AssertionError(f"historical Orion projection expected 6 claims, got {historical_count}")
        page.evaluate("PantaActions.setView('scenario')")
        scenario_text = page.locator("main").inner_text()
        for required in ("ARR", "NRR", "RUNWAY"):
            if required not in scenario_text.upper():
                raise AssertionError(f"growth Scenario Lab did not render {required}")
        for banned in ("MOIC", "IRR", "EBITDA"):
            if re.search(rf"\b{banned}\b", scenario_text, re.I):
                raise AssertionError(f"growth Scenario Lab rendered banned buyout metric {banned}")
        page.evaluate("PantaActions.setView('replay')")
        page.wait_for_selector(".replay-integrity")
        replay_text = page.locator("main").inner_text()
        if "DERIVED FROM EVENT LOG" not in replay_text.upper() or "EFFECTIVE DATE" not in replay_text.upper() or "KNOWN AT" not in replay_text.upper():
            raise AssertionError("Replay did not expose its event-derived bitemporal basis")
        page.screenshot(path=str(BROWSER_DIR / "orion_growth_bitemporal_replay.png"), full_page=True)
        evidence["historical_claim_count"] = historical_count
        evidence["scenario_growth_metrics"] = ["ARR", "NRR", "Runway"]
        evidence["replay_event_derived"] = True
        evidence["console_errors"] = console_errors
        if console_errors:
            raise AssertionError(f"browser console errors: {console_errors}")
        context.close()

        # Human Stop visible from the server transition.
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.goto(url("PROJECT-ORION"), wait_until="networkidle", timeout=30000)
        page.evaluate("PantaStore.set({reducedMotion:true}); PantaActions.startReview()")
        page.click('[data-action="admit-treatment"]')
        page.wait_for_selector(".human-stop", timeout=15000)
        human_text = page.locator(".human-stop").inner_text()
        if "HUMAN STOP" not in human_text.upper() or "AUTHORITY" not in human_text.upper():
            raise AssertionError("Human Stop was not rendered with its authority requirement")
        page.screenshot(path=str(BROWSER_DIR / "orion_human_stop.png"), full_page=True)
        evidence["human_stop_text"] = human_text
        context.close()

        # Blocked component visible from a separate event/session.
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.goto(url("PROJECT-ORION"), wait_until="networkidle", timeout=30000)
        page.evaluate("PantaStore.set({reducedMotion:true, activeEventId:'OR-EVENT-PIPELINE-GAP'}); PantaActions.startReview()")
        page.click('[data-action="admit-treatment"]')
        page.wait_for_selector(".blocked-component", timeout=15000)
        blocked_text = page.locator(".blocked-component").inner_text()
        if "BLOCKED COMPONENT" not in blocked_text.upper() or "MISSING" not in blocked_text.upper():
            raise AssertionError("Blocked component was not rendered with its reason/resolution")
        page.screenshot(path=str(BROWSER_DIR / "orion_blocked_component.png"), full_page=True)
        evidence["blocked_component_text"] = blocked_text
        context.close()
        browser.close()

    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-browser", action="store_true")
    args = parser.parse_args()
    # Stale evidence from a prior failed run must not contaminate the content scan.
    for stale in (RESULTS_JSON, RESULTS_TXT):
        if stale.exists():
            stale.unlink()
    suite = Suite()

    keystone = read_json(FIXTURES / "PROJECT-KEYSTONE" / "projection.json")
    orion = read_json(FIXTURES / "PROJECT-ORION" / "projection.json")
    k_registry = read_json(FIXTURES / "PROJECT-KEYSTONE" / "registry.json")
    o_registry = read_json(FIXTURES / "PROJECT-ORION" / "registry.json")
    k_transitions = read_json(FIXTURES / "PROJECT-KEYSTONE" / "transitions.json")
    o_transitions = read_json(FIXTURES / "PROJECT-ORION" / "transitions.json")

    def statement_overlap():
        k = {normalize_statement(item["statement"]) for item in keystone["deal"]["claims"]}
        o = {normalize_statement(item["statement"]) for item in orion["deal"]["claims"]}
        overlap = sorted(k & o)
        ratio = len(overlap) / max(1, len(o))
        suite.require(ratio < 0.20, f"Orion statement overlap is {ratio:.1%}, not below 20%")
        return {"keystone_statements": len(k), "orion_statements": len(o), "identical": len(overlap), "overlap_ratio": ratio}

    suite.test("Orion normalized statement overlap is below 20%", "ORION_GENERALIZATION", statement_overlap)

    def growth_grammar():
        text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for folder in (FIXTURES / "PROJECT-ORION", ROOT / "09_DEMO" / "fixture_packs" / "PROJECT-ORION")
            for path in folder.glob("*")
            if path.is_file()
        )
        terms = [
            r"\bEBITDA\b", r"\bMOIC\b", r"\bIRR\b", r"seller[- ]adjusted", r"\bfirst[- ]lien\b",
            r"\bdebt paydown\b", r"\bleverage\b", r"\brollover\b", r"\bentry multiple\b",
            r"\bexit multiple\b", r"\bbuyout\b", r"\bLBO\b", r"\bworking capital\b", r"\bNWC\b",
        ]
        hits = [term for term in terms if re.search(term, text, re.I)]
        suite.require(not hits, f"Orion contains buyout grammar: {hits}")
        required = ["ARR", "NRR", "GRR", "runway", "burn multiple", "onboarding", "primary"]
        missing = [term for term in required if term.lower() not in text.lower()]
        suite.require(not missing, f"Orion growth grammar is missing {missing}")
        return {"banned_hits": hits, "growth_terms_present": required, "case_type": orion["audit_meta"]["case_type"]}

    suite.test("Orion is a growth-equity case without LBO quantities", "ORION_GENERALIZATION", growth_grammar)

    def all_bitemporal():
        checked = {"claims": 0, "events": 0, "registry": 0}
        for projection, registry in ((keystone, k_registry), (orion, o_registry)):
            for claim in projection["deal"]["claims"]:
                suite.require(claim.get("effective_date") and claim.get("known_at"), f"claim lacks both dates: {claim.get('claim_id')}")
                parse_time(claim["effective_date"]); parse_time(claim["known_at"]); checked["claims"] += 1
            for event in projection.get("events", {}).values():
                suite.require(event.get("effective_date") and event.get("known_at"), f"event lacks both dates: {event.get('event_id')}")
                parse_time(event["effective_date"]); parse_time(event["known_at"]); checked["events"] += 1
            for entry in registry:
                suite.require(entry.get("effective_date") and entry.get("known_at"), f"registry entry lacks both dates: {entry.get('event_id')}")
                parse_time(entry["effective_date"]); parse_time(entry["known_at"]); checked["registry"] += 1
        return checked

    suite.test("Every fixture claim, source event and Registry entry is bitemporal", "BITEMPORALITY", all_bitemporal)

    def replay_fixture_contract():
        evidence = {}
        for name, projection, registry in (("Keystone", keystone, k_registry), ("Orion", orion, o_registry)):
            replay = projection["deal"]["replay"]
            suite.require(replay.get("source") == "REGISTRY_EVENTS", f"{name} replay source is not Registry events")
            suite.require(replay.get("hand_authored_snapshots") is False, f"{name} still permits handcrafted replay")
            suite.require(replay.get("snapshots") == [], f"{name} fixture contains pre-authored replay snapshots")
            suite.require(all(item.get("effective_date") and item.get("known_at") for item in registry), f"{name} Registry lacks dates")
            evidence[name] = {"fixture_snapshots": 0, "registry_events": len(registry)}
        return evidence

    suite.test("Replay fixtures contain no handwritten snapshots", "BITEMPORALITY", replay_fixture_contract)

    def epistemic_classes():
        claims = keystone["deal"]["claims"]
        distribution = Counter(item["epistemic_class"] for item in claims)
        firm_sources = {"SRC-IA", "SRC-IC"}
        firm_acts = [
            item for item in claims
            if item.get("source_id") in firm_sources
            or re.search(r"\b(the firm|investment committee|\bIC\b).*(approved|accepted|required|capped|decision|vote|underwritten)", item.get("statement", ""), re.I)
        ]
        suite.require(firm_acts, "firm-act detector found no claims")
        violations = [item["claim_id"] for item in firm_acts if item["epistemic_class"] == "attested"]
        suite.require(not violations, f"firm acts still carry attested: {violations}")
        firm_114 = [item for item in claims if item.get("value") == 11.4 and "Firm" in item.get("statement", "")]
        suite.require(firm_114 and all(item["epistemic_class"] == "institutional_act" for item in firm_114), "Firm EBITDA 11.4 is not institutional_act")
        ic_claims = [item for item in claims if item.get("source_id") == "SRC-IC"]
        suite.require(ic_claims and all(item["epistemic_class"] == "institutional_act" for item in ic_claims), "an IC claim is not institutional_act")
        suite.require(15 <= distribution["institutional_act"] <= 30, f"institutional_act distribution is implausible: {distribution}")
        suite.require(distribution["attested"] <= 20, f"attested remains inflated: {distribution}")
        return {"distribution": dict(distribution), "firm_act_count": len(firm_acts), "firm_act_attested_violations": violations}

    suite.test("Institutional acts are a fifth class and never attested", "EPISTEMIC_CLASS", epistemic_classes)

    def schema_quality():
        files = sorted(SCHEMAS.glob("*.schema.json"))
        suite.require(len(files) == 8, f"expected 8 public schemas, found {len(files)}")
        gaps: dict[str, list[str]] = {}
        for path in files:
            schema = read_json(path)
            Draft202012Validator.check_schema(schema)
            missing = typed_property_gaps(schema)
            if missing:
                gaps[path.name] = missing
        suite.require(not gaps, f"untyped schema properties: {gaps}")
        return {"schemas": [path.name for path in files], "schema_count": len(files), "untyped_properties": gaps}

    suite.test("All eight public contract schemas are structurally typed", "SCHEMAS_AND_ADAPTER", schema_quality)

    def projection_schema_validation():
        assert_zero_schema_errors("frontend_projection", keystone)
        assert_zero_schema_errors("frontend_projection", orion)
        return {"validated": ["PROJECT-KEYSTONE", "PROJECT-ORION"], "errors": 0}

    suite.test("Both case projections validate with zero schema errors", "SCHEMAS_AND_ADAPTER", projection_schema_validation)

    def transition_schema_validation():
        count = 0
        for case, transitions in (("PROJECT-KEYSTONE", k_transitions), ("PROJECT-ORION", o_transitions)):
            for name, transition in transitions.items():
                assert_zero_schema_errors("transition_result", transition)
                count += 1
        return {"transition_outputs": count, "errors": 0}

    suite.test("All fixture transition outputs validate against the frozen-field schema", "SCHEMAS_AND_ADAPTER", transition_schema_validation)

    def pure_adapter():
        module = import_adapter()
        source = read_json(SAMPLES / "sample_engine_output.json")
        first = module.map_engine_output(source)
        second = module.map_engine_output(read_json(SAMPLES / "sample_engine_output.json"))
        suite.require(canonical_json(first) == canonical_json(second), "Python adapter is not deterministic/pure")
        assert_zero_schema_errors("transition_result", first)
        suite.require(first["mapping_contract"]["frozen_required_field_count"] == 18, "frozen output field count is not 18")
        suite.require(first["mapping_contract"]["integration_required_field_count"] == 19, "source_event_id was not added as the integration field")
        source_after = read_json(SAMPLES / "sample_engine_output.json")
        suite.require(canonical_json(source) == canonical_json(source_after), "adapter mutated the sample input")
        return {"python_adapter": "PASS", "output_schema_errors": 0, "pure": True, "frozen_fields": 18, "integration_fields": 19}

    suite.test("Frozen engine output maps through a pure Python adapter", "SCHEMAS_AND_ADAPTER", pure_adapter)

    def javascript_adapter():
        sample = SAMPLES / "sample_engine_output.json"
        adapter = APP / "src" / "projection_adapter.js"
        script = f"""
const fs=require('fs'); global.window={{}};
eval(fs.readFileSync({json.dumps(str(adapter))},'utf8'));
const input=JSON.parse(fs.readFileSync({json.dumps(str(sample))},'utf8'));
const before=JSON.stringify(input);
const output=window.PantaProjectionAdapter.mapFrozenEngineOutput(input);
if(before!==JSON.stringify(input)) throw new Error('input mutated');
process.stdout.write(JSON.stringify(output));
"""
        output = subprocess.check_output(["node", "-e", script], text=True)
        mapped = json.loads(output)
        assert_zero_schema_errors("transition_result", mapped)
        suite.require(mapped["mapping_contract"]["pure_function"] is True, "JS adapter does not declare pure function")
        return {"javascript_adapter": "PASS", "output_schema_errors": 0, "affected_set": len(mapped["affected_set"])}

    suite.test("Frozen engine output maps through the browser adapter", "SCHEMAS_AND_ADAPTER", javascript_adapter)

    def transition_objects_present():
        human = o_transitions["retention_restatement"]["human_stops"]
        blocked = o_transitions["pipeline_coverage_gap"]["blocked_components"]
        suite.require(len(human) >= 1, "human-stop fixture is empty")
        suite.require(len(blocked) >= 1, "blocked-component fixture is empty")
        suite.require(human[0].get("authority_verb") and human[0].get("required_role"), "human stop lacks authority contract")
        suite.require(blocked[0].get("reason_code") and blocked[0].get("reason"), "blocked component lacks reason contract")
        return {"human_stops": len(human), "blocked_components": len(blocked), "human_stop_id": human[0]["stop_id"], "blocked_component_id": blocked[0]["component_id"]}

    suite.test("Fixture data exercises Human Stop and blocked component objects", "TRANSITION_OBJECTS", transition_objects_present)

    def banned_term_scan():
        exact = re.compile("support" + r"ed[ _-]?(?:pri" + "ce|ceiling)", re.I)
        hits: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".sessions" in path.parts:
                continue
            if path.suffix.lower() in BINARY_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if exact.search(text):
                hits.append(str(path.relative_to(ROOT)))
        pdftotext = shutil.which("pdftotext")
        pdf_hits: list[str] = []
        if pdftotext:
            with tempfile.TemporaryDirectory() as temp:
                for pdf in ROOT.rglob("*.pdf"):
                    output = Path(temp) / (hashlib.sha1(str(pdf).encode()).hexdigest() + ".txt")
                    subprocess.run([pdftotext, str(pdf), str(output)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if exact.search(output.read_text(encoding="utf-8", errors="ignore")):
                        pdf_hits.append(str(pdf.relative_to(ROOT)))
        suite.require(not hits and not pdf_hits, f"banned terminology remains: {hits + pdf_hits}")
        return {"text_hits": hits, "pdf_hits": pdf_hits, "replacement": "approved EV ceiling"}

    suite.test("Retired pricing terminology is absent", "LANGUAGE_REGRESSION", banned_term_scan)

    # Compile/static syntax checks.
    def syntax_checks():
        subprocess.run([sys.executable, "-m", "py_compile", str(ROOT / "01_PRODUCT_BUILD" / "mock_api" / "server.py"), str(ADAPTER)], check=True)
        checked = []
        for path in sorted((APP / "src").glob("*.js")):
            subprocess.run(["node", "--check", str(path)], check=True, stdout=subprocess.DEVNULL)
            checked.append(path.name)
        return {"python_files": 2, "javascript_files": checked}

    suite.test("Python and browser runtime files pass syntax checks", "STATIC_RUNTIME", syntax_checks)

    with server_process() as runtime:
        api: Api = runtime["api"]

        def connected_refusal():
            status, data = api.call("GET", "/bootstrap?mode=CONNECTED&case_id=PROJECT-ORION&actor=partner")
            suite.require(status == 503, f"Connected returned {status}")
            suite.require(data.get("error", {}).get("code") == "CONNECTED_BACKEND_NOT_CONFIGURED", f"wrong error: {data}")
            return {"status": status, "error_code": data["error"]["code"]}

        suite.test("Bundled server refuses fixture-backed Connected mode", "MODE_HONESTY", connected_refusal)

        def date_projection_and_replay():
            boot = api.bootstrap("PROJECT-ORION")
            session = boot["session_id"]
            early_status, early = api.projection("PROJECT-ORION", session, "2026-05-12")
            late_status, late = api.projection("PROJECT-ORION", session, "2026-08-26")
            suite.require(early_status == late_status == 200, "date projection failed")
            early_claims = early["projection"]["deal"]["claims"]
            late_claims = late["projection"]["deal"]["claims"]
            suite.require(len(early_claims) == 6 and len(late_claims) == 42, f"date-driven claim counts wrong: {len(early_claims)}, {len(late_claims)}")
            cutoff = parse_time("2026-05-12")
            suite.require(all(parse_time(item["known_at"]) <= cutoff for item in early_claims), "early projection leaked future knowledge")
            status, replay = api.call("GET", f"/cases/PROJECT-ORION/replay?session_id={session}&event_id=OR-REG-003")
            suite.require(status == 200, f"replay failed: {replay}")
            suite.require(replay.get("derived_from_event_log") is True, "replay not derived from event log")
            suite.require(replay["event"]["event_id"] == "OR-REG-003", "replay resolved the wrong event")
            suite.require(replay["event"]["effective_date"] and replay["event"]["known_at"], "replay event lacks both dates")
            bad_status, bad = api.call("GET", f"/cases/PROJECT-ORION/replay?session_id={session}&as_of_date=not-a-date")
            suite.require(bad_status == 400, f"invalid date was not rejected: {bad_status} {bad}")
            return {
                "early_claims": len(early_claims),
                "late_claims": len(late_claims),
                "replayed_event": replay["event"]["event_id"],
                "effective_date": replay["event"]["effective_date"],
                "known_at": replay["event"]["known_at"],
                "invalid_date_status": bad_status,
            }

        suite.test("Any past date reconstructs knowledge and event-derived replay", "BITEMPORALITY", date_projection_and_replay)

        def context_schema():
            boot = api.bootstrap("PROJECT-KEYSTONE")
            assert_zero_schema_errors("experience_context", boot["context"])
            return {"schema": "experience_context", "errors": 0}

        suite.test("Mock bootstrap context validates with zero errors", "SCHEMAS_AND_ADAPTER", context_schema)

        def ingest_and_review_schemas():
            boot = api.bootstrap("PROJECT-ORION")
            session = boot["session_id"]
            job_body = {
                "method": "text",
                "value": "Synthetic ARR evidence",
                "file_name": "orion_arr_note.txt",
                "source_type": "operating_note",
                "purpose": "underwriting",
                "effective_date": "2026-08-27",
                "actor_id": boot["context"]["authenticated_actor"]["actor_id"],
            }
            status, result = api.call("POST", f"/cases/PROJECT-ORION/ingest?session_id={session}", job_body, {"Idempotency-Key": "SCHEMA-JOB"})
            suite.require(status == 202, f"ingest failed: {result}")
            assert_zero_schema_errors("ingest_job", result["job"])
            review = {
                "claim_id": "OR-CL-001",
                "object_id": "OR-CL-001",
                "actor_id": boot["context"]["authenticated_actor"]["actor_id"],
                "action": "ACCEPTED",
                "decision": "ACCEPTED",
                "correction": "",
                "timestamp": "2026-08-27T15:00:00Z",
                "effective_date": "2026-08-27",
                "known_at": "2026-08-27T15:00:00Z",
                "idempotency_key": "SCHEMA-REVIEW",
            }
            assert_zero_schema_errors("claim_review", review)
            note_status, note = api.call("POST", f"/cases/PROJECT-ORION/notes?session_id={session}", review)
            suite.require(note_status == 201, f"claim review was not acknowledged: {note}")
            return {"ingest_job_errors": 0, "claim_review_errors": 0, "note_status": note_status}

        suite.test("Ingest job and claim-review records validate with zero errors", "SCHEMAS_AND_ADAPTER", ingest_and_review_schemas)

        def human_stop_server_gate():
            boot = api.bootstrap("PROJECT-ORION")
            session = boot["session_id"]
            p_status, payload = api.projection("PROJECT-ORION", session)
            suite.require(p_status == 200, "projection failed")
            event, admission = admission_payload(payload, "retention_restatement", "HS-ADMIT")
            status, admitted = api.call(
                "POST", f"/cases/PROJECT-ORION/events/{event['event_id']}/admit?session_id={session}", admission,
                {"Idempotency-Key": admission["idempotency_key"]},
            )
            suite.require(status == 200, f"admission failed: {admitted}")
            transition = admitted["transition"]
            assert_zero_schema_errors("transition_result", transition)
            run = admitted["run"]
            stop = transition["human_stops"][0]
            selected = [transition["artifact_change_sets"][0]["artifact_id"]]

            authority_body = {
                "run_id": run["run_id"],
                "candidate_state_id": run["candidate_state_id"],
                "human_stop_id": stop["stop_id"],
                "course_id": "OR-COURSE-C",
                "artifact_hash": transition["replay_hash"],
                "idempotency_key": "HS-AUTH",
            }
            pre_status, pre = api.call(
                "POST", f"/runs/{run['run_id']}/authority/attest?session_id={session}", authority_body,
                {"Idempotency-Key": authority_body["idempotency_key"]},
            )
            suite.require(pre_status == 409 and pre.get("error", {}).get("code") == "RUN_NOT_PREPARED", f"authority-before-prepare was not refused: {pre_status} {pre}")

            wrong_body = {**authority_body, "candidate_state_id": "CANDIDATE-WRONG", "idempotency_key": "HS-AUTH-WRONG"}
            # First prepare, then prove candidate binding.
            prep_status, prepared = api.call("POST", f"/runs/{run['run_id']}/prepare?session_id={session}", {"selected_change_ids": selected})
            suite.require(prep_status == 200, f"prepare failed: {prepared}")
            wrong_status, wrong = api.call(
                "POST", f"/runs/{run['run_id']}/authority/attest?session_id={session}", wrong_body,
                {"Idempotency-Key": wrong_body["idempotency_key"]},
            )
            suite.require(wrong_status == 409 and wrong.get("error", {}).get("code") == "CANDIDATE_CONTEXT_MISMATCH", f"wrong Candidate was not refused: {wrong}")

            settlement = {
                "candidate_state_id": run["candidate_state_id"],
                "as_of_state_id": payload["context"]["as_of_state_id"],
                "as_of_date": payload["context"]["as_of_date"],
                "selected_change_ids": selected,
                "human_stop_ids": [stop["stop_id"]],
                "authority_record_ids": [],
                "execution_package_ids": [],
                "actor_id": payload["context"]["authenticated_actor"]["actor_id"],
                "allow_partial_settlement": False,
                "idempotency_key": "HS-SETTLE-NO-AUTH",
            }
            no_auth_status, no_auth = api.call(
                "POST", f"/runs/{run['run_id']}/settle?session_id={session}", settlement,
                {"Idempotency-Key": settlement["idempotency_key"]},
            )
            suite.require(no_auth_status == 409 and "requires a scoped authority record" in no_auth.get("error", {}).get("message", ""), f"settlement without authority was not refused: {no_auth}")

            auth_status, attested = api.call(
                "POST", f"/runs/{run['run_id']}/authority/attest?session_id={session}", authority_body,
                {"Idempotency-Key": authority_body["idempotency_key"]},
            )
            suite.require(auth_status == 200, f"proper authority failed: {attested}")
            authority_record = attested["authority_record"]
            assert_zero_schema_errors("authority_record", authority_record)
            settlement["authority_record_ids"] = [authority_record["authority_record_id"]]
            settlement["idempotency_key"] = "HS-SETTLE-OK"
            settle_status, settled = api.call(
                "POST", f"/runs/{run['run_id']}/settle?session_id={session}", settlement,
                {"Idempotency-Key": settlement["idempotency_key"]},
            )
            suite.require(settle_status == 200, f"properly governed settlement failed: {settled}")
            assert_zero_schema_errors("settlement_result", settled)
            return {
                "human_stop_id": stop["stop_id"],
                "authority_before_prepare_status": pre_status,
                "wrong_candidate_status": wrong_status,
                "settlement_without_authority_status": no_auth_status,
                "authority_record_schema_errors": 0,
                "settlement_schema_errors": 0,
                "settled_state_id": settled["current_state_id"],
            }

        suite.test("Human Stop settlement is server-refused without scoped authority", "TRANSITION_OBJECTS", human_stop_server_gate)

        def unknown_change_refused():
            boot = api.bootstrap("PROJECT-ORION")
            session = boot["session_id"]
            _, payload = api.projection("PROJECT-ORION", session)
            event, admission = admission_payload(payload, "pipeline_coverage_gap", "UNKNOWN-ADMIT")
            status, admitted = api.call("POST", f"/cases/PROJECT-ORION/events/{event['event_id']}/admit?session_id={session}", admission, {"Idempotency-Key": admission["idempotency_key"]})
            suite.require(status == 200, f"admission failed: {admitted}")
            run_id = admitted["run"]["run_id"]
            reject_status, reject = api.call("POST", f"/runs/{run_id}/prepare?session_id={session}", {"selected_change_ids": ["ART-NOT-AFFECTED"]})
            suite.require(reject_status == 409 and reject.get("error", {}).get("code") == "UNKNOWN_CHANGE_ID", f"unknown change accepted: {reject}")
            return {"status": reject_status, "error_code": reject["error"]["code"]}

        suite.test("Preparation rejects changes outside the transition output", "SETTLEMENT_INTEGRITY", unknown_change_refused)

        def blocked_partial_settlement():
            boot = api.bootstrap("PROJECT-ORION")
            session = boot["session_id"]
            _, payload = api.projection("PROJECT-ORION", session)
            event, admission = admission_payload(payload, "pipeline_coverage_gap", "BLOCK-ADMIT")
            status, admitted = api.call("POST", f"/cases/PROJECT-ORION/events/{event['event_id']}/admit?session_id={session}", admission, {"Idempotency-Key": admission["idempotency_key"]})
            suite.require(status == 200, f"admission failed: {admitted}")
            transition, run = admitted["transition"], admitted["run"]
            suite.require(transition["blocked_components"], "blocked transition returned no blocked components")
            selected = [transition["artifact_change_sets"][0]["artifact_id"]]
            prep_status, _ = api.call("POST", f"/runs/{run['run_id']}/prepare?session_id={session}", {"selected_change_ids": selected})
            suite.require(prep_status == 200, "prepare failed")
            body = {
                "candidate_state_id": run["candidate_state_id"],
                "as_of_state_id": payload["context"]["as_of_state_id"],
                "as_of_date": payload["context"]["as_of_date"],
                "selected_change_ids": selected,
                "human_stop_ids": [],
                "authority_record_ids": [],
                "execution_package_ids": [],
                "actor_id": payload["context"]["authenticated_actor"]["actor_id"],
                "allow_partial_settlement": False,
                "idempotency_key": "BLOCK-SETTLE-NO-PARTIAL",
            }
            refuse_status, refused = api.call("POST", f"/runs/{run['run_id']}/settle?session_id={session}", body, {"Idempotency-Key": body["idempotency_key"]})
            suite.require(refuse_status == 409 and "explicit bounded partial settlement" in refused.get("error", {}).get("message", ""), f"blocked scope was silently settled: {refused}")
            body["allow_partial_settlement"] = True
            body["idempotency_key"] = "BLOCK-SETTLE-PARTIAL"
            accept_status, accepted = api.call("POST", f"/runs/{run['run_id']}/settle?session_id={session}", body, {"Idempotency-Key": body["idempotency_key"]})
            suite.require(accept_status == 200 and accepted.get("partial") is True, f"explicit partial settlement failed: {accepted}")
            assert_zero_schema_errors("settlement_result", accepted)
            return {"blocked_component_id": transition["blocked_components"][0]["component_id"], "without_partial_status": refuse_status, "with_partial_status": accept_status, "partial": accepted["partial"]}

        suite.test("Blocked scope requires explicit bounded partial settlement", "TRANSITION_OBJECTS", blocked_partial_settlement)

        def external_execution_schema():
            boot = api.bootstrap("PROJECT-KEYSTONE")
            session = boot["session_id"]
            _, payload = api.projection("PROJECT-KEYSTONE", session)
            event, admission = admission_payload(payload, "concentration", "EXEC-ADMIT")
            status, admitted = api.call("POST", f"/cases/PROJECT-KEYSTONE/events/{event['event_id']}/admit?session_id={session}", admission, {"Idempotency-Key": admission["idempotency_key"]})
            suite.require(status == 200, f"admission failed: {admitted}")
            transition, run = admitted["transition"], admitted["run"]
            selected = [transition["artifact_change_sets"][0]["artifact_id"]]
            prep_status, _ = api.call("POST", f"/runs/{run['run_id']}/prepare?session_id={session}", {"selected_change_ids": selected})
            suite.require(prep_status == 200, "prepare failed")
            stop = transition["human_stops"][0]
            room = payload["projection"]["deal"]["decisionRoom"]
            course = next(item for item in room["courses"] if item.get("effect_type") == "EXTERNAL_PACKAGE")
            body = {
                "run_id": run["run_id"],
                "candidate_state_id": run["candidate_state_id"],
                "human_stop_id": stop["stop_id"],
                "course_id": course["id"],
                "artifact_hash": transition["replay_hash"],
                "idempotency_key": "EXEC-AUTH",
            }
            auth_status, attested = api.call("POST", f"/runs/{run['run_id']}/authority/attest?session_id={session}", body, {"Idempotency-Key": body["idempotency_key"]})
            suite.require(auth_status == 200 and attested.get("execution_package"), f"external course did not derive package: {attested}")
            assert_zero_schema_errors("authority_record", attested["authority_record"])
            assert_zero_schema_errors("execution_package", attested["execution_package"])
            package = attested["execution_package"]
            send_status, sent = api.call("POST", f"/execution-packages/{package['execution_package_id']}/send?session_id={session}", {"simulate_failure": False})
            suite.require(send_status == 200 and sent["execution_package"]["status"] == "ACCEPTED", f"server acknowledgment failed: {sent}")
            return {"authority_schema_errors": 0, "execution_package_schema_errors": 0, "package_status": sent["execution_package"]["status"]}

        suite.test("Course-specific external package validates and requires server acknowledgment", "SCHEMAS_AND_ADAPTER", external_execution_schema)

        if not args.skip_browser:
            suite.test("Mapped transitions and bitemporal growth case render in the UI", "BROWSER_E2E", lambda: browser_acceptance(runtime["browser_origin"]))

    report = suite.finish()
    RESULTS_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "PANTA V19.B TEST RESULTS",
        "=" * 80,
        f"Status: {report['status']}",
        f"Passed: {report['passed']} / {report['total']}",
        f"Failed: {report['failed']}",
        "",
        report["scope_limit"],
        "",
    ]
    for item in report["results"]:
        lines.append(f"[{item['status']}] {item['category']} :: {item['name']}")
        if item["error"]:
            lines.append(f"    {item['error']}")
        elif item["evidence"] is not None:
            lines.append("    " + canonical_json(item["evidence"]))
    RESULTS_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nRESULT: {report['status']} — {report['passed']}/{report['total']} passed", flush=True)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
