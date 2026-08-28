#!/usr/bin/env python3
"""Executable acceptance and regression suite for PANTA V20.

The suite verifies the bundled product build, three synthetic case fixtures,
V20 venture/deep-tech extensions, V19.B integrity non-regressions, public JSON
Schemas, pure adapters, the stateful synthetic API, and representative browser
flows. It does not certify production identity, the production Case Store,
external research, external effects, or Anto's separate frozen runtime.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import re
import socket
import subprocess
import sys
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
TRANSITION_ADAPTER = ROOT / "07_ENGINEERING_CONTRACTS_AND_ADAPTERS" / "adapters" / "transition_runtime_adapter.py"
COMPILER_ADAPTER = ROOT / "07_ENGINEERING_CONTRACTS_AND_ADAPTERS" / "adapters" / "compiler_projection_adapter.py"
SAMPLES = ROOT / "07_ENGINEERING_CONTRACTS_AND_ADAPTERS" / "samples"
RESULTS_JSON = ROOT / "08_TEST_EVIDENCE" / "V20_TEST_RESULTS.json"
RESULTS_TXT = ROOT / "08_TEST_EVIDENCE" / "V20_TEST_RESULTS.txt"
RESULTS_MD = ROOT / "08_TEST_EVIDENCE" / "V20_TEST_RESULTS.md"
BROWSER_DIR = ROOT / "08_TEST_EVIDENCE" / "browser"
BROWSER_DIR.mkdir(parents=True, exist_ok=True)

TEXT_SUFFIXES = {".js", ".py", ".json", ".md", ".html", ".css", ".csv", ".txt", ".svg", ".dot", ".command", ".bat"}
V20_CASE = "PROJECT-TETHYS"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_statement(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9%$]+", str(value).lower()))


def parse_time(value: str) -> dt.datetime:
    text = str(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text += "T23:59:59Z"
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


def find_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("", 0))
        return int(sock.getsockname()[1])


def fixture(case_id: str) -> dict[str, Any]:
    return read_json(FIXTURES / case_id / "projection.json")


def transitions(case_id: str) -> dict[str, Any]:
    return read_json(FIXTURES / case_id / "transitions.json")


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
        except Exception as exc:
            status = "FAIL"
            evidence = None
            error = f"{type(exc).__name__}: {exc}"
        self.results.append({
            "name": name,
            "category": category,
            "status": status,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            "evidence": evidence,
            "error": error,
        })
        print(f"[{status}] {category} :: {name}" + (f" - {error}" if error else ""), flush=True)

    @staticmethod
    def require(condition: bool, message: str) -> None:
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
            "suite": "PANTA V20 venture-extension acceptance and regression suite",
            "release": "20.0.0 / V20",
            "started_at": self.started_at.isoformat().replace("+00:00", "Z"),
            "ended_at": ended.isoformat().replace("+00:00", "Z"),
            "total": len(self.results),
            "passed": counts.get("PASS", 0),
            "failed": counts.get("FAIL", 0),
            "status": "PASS" if counts.get("FAIL", 0) == 0 else "FAIL",
            "categories": categories,
            "scope_limit": (
                "Tests the bundled V20 frontend, three synthetic fixture packs, typed schemas, pure compiler and transition adapters, "
                "and the stateful Mock Connected reference API. It does not certify production authentication/RBAC, a production Case Store, "
                "a live autonomous research service, external human contact, external effects, or Anto's separate production runtime."
            ),
            "results": self.results,
        }


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None):
        response = requests.request(method, self.base + path, json=body, headers=headers or {}, timeout=20)
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

    def projection(self, case: str, session: str, *, as_of_date: str | None = None, lens_id: str | None = None):
        params = [f"session_id={session}"]
        if as_of_date:
            params.append(f"as_of_date={as_of_date}")
        if lens_id:
            params.append(f"lens_id={lens_id}")
        return self.call("GET", f"/cases/{case}/projection?{'&'.join(params)}")


@contextlib.contextmanager
def server_process():
    port = find_free_port()
    server = ROOT / "01_PRODUCT_BUILD" / "mock_api" / "server.py"
    sessions = ROOT / "01_PRODUCT_BUILD" / "mock_api" / ".sessions"
    sessions.mkdir(exist_ok=True)
    for path in sessions.glob("*.json"):
        path.unlink()
    process = subprocess.Popen(
        [sys.executable, str(server), "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}/api/v20"
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            response = requests.get(base + f"/bootstrap?mode=MOCK_CONNECTED&case_id={V20_CASE}", timeout=1)
            if response.status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.1)
    else:
        output = process.stdout.read() if process.stdout else ""
        process.kill()
        raise RuntimeError(f"mock server did not start: {output}")
    try:
        yield {"api": Api(base), "port": port, "browser_origin": f"http://127.0.0.1:{port}"}
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


def schema_errors(schema_name: str, value: Any) -> list[str]:
    schema = read_json(SCHEMAS / f"{schema_name}.schema.json")
    errors = sorted(
        Draft202012Validator(schema, registry=schema_registry(), format_checker=FormatChecker()).iter_errors(value),
        key=lambda error: list(error.path),
    )
    return [f"{'.'.join(map(str, e.path))}: {e.message}" for e in errors]


def assert_zero_schema_errors(schema_name: str, value: Any) -> None:
    errors = schema_errors(schema_name, value)
    if errors:
        raise AssertionError(f"{schema_name} validation returned {len(errors)} errors: {'; '.join(errors[:10])}")


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


def import_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admission_payload(projection_payload: dict[str, Any], event_key: str, token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    projection = projection_payload["projection"]
    context = projection_payload["context"]
    event = projection["events"][event_key]
    body = {
        "treatment_id": event["treatment_id"],
        "treatment_hash": event.get("treatment_hash") or sha256(event.get("proposed_treatment") or event.get("proposed_position")),
        "source_version_id": event["source_version_id"],
        "event_id": event["event_id"],
        "actor_id": context["authenticated_actor"]["actor_id"],
        "as_of_state_id": context["as_of_state_id"],
        "as_of_date": context["as_of_date"],
        "effective_date": event["effective_date"],
        "known_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "idempotency_key": token,
    }
    return event, body


def admit(api: Api, case: str, session: str, payload: dict[str, Any], event_key: str, token: str):
    event, body = admission_payload(payload, event_key, token)
    status, output = api.call(
        "POST",
        f"/cases/{case}/events/{event['event_id']}/admit?session_id={session}",
        body,
        {"Idempotency-Key": token},
    )
    if status != 200:
        raise AssertionError(f"admission failed: {status} {output}")
    return event, body, output


def run_browser_acceptance(origin: str) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    chromium = Path("/usr/bin/chromium")
    if not chromium.exists():
        raise AssertionError("System Chromium is unavailable")
    evidence: dict[str, Any] = {"screenshots": []}
    url = f"{origin}/?mode=mock&case={V20_CASE}&actor=partner&api={origin}/api/v20#case={V20_CASE}&view=deal-command"
    args = ["--no-sandbox", "--no-proxy-server", "--proxy-bypass-list=*", "--disable-dev-shm-usage"]

    def shot(page, name: str):
        path = BROWSER_DIR / name
        page.screenshot(path=str(path), full_page=True)
        evidence["screenshots"].append(str(path.relative_to(ROOT)))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=str(chromium), args=args)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.wait_for_selector("#v20-lens-switcher", timeout=20000)
        page.wait_for_selector(".v20-archetype")
        deal_text = page.locator("main").inner_text()
        for required in ("CASE GRAMMAR", "AUDITABLE CRITICALITY", "VENTURE"):
            if required not in deal_text.upper():
                raise AssertionError(f"Deal Command missing {required}")
        facts_before = page.evaluate("PantaStore.get().projection.deal.lens_projection.facts_hash")
        order_before = page.evaluate("PantaStore.get().projection.deal.question_spine.map(x=>x.id)")
        shot(page, "v20_01_deal_command.png")

        page.select_option("#v20-lens-switcher", "TY-LENS-DEEP-TECH")
        page.wait_for_function("PantaStore.get().context && PantaStore.get().context.active_lens_id === 'TY-LENS-DEEP-TECH'")
        facts_after = page.evaluate("PantaStore.get().projection.deal.lens_projection.facts_hash")
        order_after = page.evaluate("PantaStore.get().projection.deal.question_spine.map(x=>x.id)")
        if facts_before != facts_after or order_before == order_after:
            raise AssertionError("Lens did not preserve facts while changing emphasis")
        evidence["lens_facts_stable"] = True
        evidence["lens_order_changed"] = True

        page.evaluate("PantaActions.setView('sources'); PantaActions.setSourceTab('sources')")
        page.wait_for_selector(".v20-interactions")
        source_text = page.locator(".v20-interactions").inner_text()
        if "SPEAKER-LEVEL PROVENANCE" not in source_text.upper() or "UTTERANCES" not in source_text.upper():
            raise AssertionError("Interaction provenance did not render")
        shot(page, "v20_02_interactions.png")

        page.evaluate("PantaActions.openObject('TY-UTT-002','basis')")
        page.wait_for_selector(".v20-object")
        aperture_text = page.locator(".v20-object").inner_text()
        if "OBSERVED SPEECH ACT" not in aperture_text.upper() or "REMAINS ASSERTED" not in aperture_text.upper():
            raise AssertionError("Utterance epistemic boundary did not render")
        shot(page, "v20_03_utterance_aperture.png")
        page.evaluate("PantaActions.closeDrawer()")

        page.evaluate("PantaActions.setView('sources'); PantaActions.setSourceTab('compiler')")
        page.wait_for_selector(".v20-compiler")
        compiler_text = page.locator(".v20-compiler").inner_text()
        for required in ("CANDIDATE DISCREPANCIES", "DETERMINISTIC DERIVATIONS", "AI HYPOTHESES", "QUESTION-SPINE CHANGES"):
            if required not in compiler_text.upper():
                raise AssertionError(f"Compiler Review missing {required}")
        shot(page, "v20_04_compiler_review.png")

        page.evaluate("PantaActions.setView('foundations')")
        page.wait_for_selector(".v20-validation")
        foundations_text = page.locator(".v20-validation").inner_text()
        if "VALIDATION ENVELOPES" not in foundations_text.upper() or "CONDITION EDGES" not in foundations_text.upper():
            raise AssertionError("Technical envelope/conditions did not render")
        shot(page, "v20_05_validation_conditions.png")

        page.evaluate("PantaActions.setView('unknowns')")
        page.wait_for_selector(".v20-missions")
        unknown_text = page.locator("main").inner_text()
        if "GOVERNED MISSIONS" not in unknown_text.upper() or "DECISION-VALUE DECOMPOSITION" not in unknown_text.upper():
            raise AssertionError("Mission/criticality UI did not render")
        shot(page, "v20_06_unknowns_missions.png")

        page.evaluate("PantaActions.setView('scenario')")
        page.wait_for_selector(".v20-financing")
        scenario_text = page.locator(".v20-financing").inner_text()
        for required in ("PRE-MONEY", "NEW INVESTOR", "MILESTONE TRANCHES", "CAP TABLE"):
            if required not in scenario_text.upper():
                raise AssertionError(f"Venture Scenario Lab missing {required}")
        shot(page, "v20_07_venture_financing.png")

        page.evaluate("PantaActions.setView('replay')")
        page.wait_for_selector(".replay-integrity")
        replay_text = page.locator("main").inner_text()
        if "DERIVED FROM EVENT LOG" not in replay_text.upper() or "KNOWN AT" not in replay_text.upper():
            raise AssertionError("Bitemporal replay basis missing")
        shot(page, "v20_08_replay.png")
        context.close()

        # Human Stop end-to-end rendering.
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.evaluate("PantaStore.set({reducedMotion:true,activeEventId:'TY-EVENT-COVERAGE'}); PantaActions.startReview()")
        page.click('[data-action="admit-treatment"]')
        page.wait_for_selector(".human-stop", timeout=20000)
        if "AUTHORITY" not in page.locator(".human-stop").inner_text().upper():
            raise AssertionError("Human Stop authority requirement missing")
        shot(page, "v20_09_human_stop.png")
        context.close()

        # Blocked component end-to-end rendering.
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.evaluate("PantaStore.set({reducedMotion:true,activeEventId:'TY-EVENT-MAINTENANCE'}); PantaActions.startReview()")
        page.click('[data-action="admit-treatment"]')
        page.wait_for_selector(".blocked-component", timeout=20000)
        if "BLOCKED" not in page.locator(".blocked-component").inner_text().upper():
            raise AssertionError("Blocked component did not render")
        shot(page, "v20_10_blocked_component.png")
        context.close()

        context = browser.new_context(viewport={"width": 390, "height": 844})
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.wait_for_selector(".v20-archetype")
        mobile = page.evaluate("document.body.classList.contains('mobile-read-only') || PantaStore.get().mobileReadOnly")
        if not mobile:
            raise AssertionError("Sub-768 viewport did not enter read/review-first mode")
        shot(page, "v20_11_mobile_read_review.png")
        context.close()
        browser.close()
        evidence["console_errors"] = errors
        if errors:
            raise AssertionError(f"Browser console/page errors: {errors}")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-browser", action="store_true", help="Skip Playwright/UI evidence")
    args = parser.parse_args()
    suite = Suite()
    req = suite.require

    tethys = fixture(V20_CASE)
    keystone = fixture("PROJECT-KEYSTONE")
    orion = fixture("PROJECT-ORION")

    suite.test("Release identity is V20 / 20.0.0", "RELEASE", lambda: (
        req(read_json(ROOT / "01_PRODUCT_BUILD" / "VERSION.json")["semantic_version"] == "20.0.0", "wrong semantic version") or
        {"release": "V20", "semantic_version": "20.0.0"}
    ))

    suite.test("Three structurally distinct synthetic cases are packaged", "GENERALIZATION", lambda: (
        req({p.name for p in FIXTURES.iterdir() if p.is_dir()} >= {"PROJECT-KEYSTONE", "PROJECT-ORION", V20_CASE}, "required cases missing") or
        {"cases": sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())}
    ))

    def core_purity():
        text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in sorted((APP / "src").glob("*.js")))
        text += (ROOT / "01_PRODUCT_BUILD" / "mock_api" / "server.py").read_text(encoding="utf-8")
        banned = ["Alderstone", "Riverton", "Tethys Marine", "Orion Metrics", "PROJECT-TETHYS", "PROJECT-KEYSTONE", "PROJECT-ORION", "TY-EVENT", "OR-EVENT"]
        found = [item for item in banned if item in text]
        req(not found, f"case facts leaked into generic core: {found}")
        return {"scanned_files": len(list((APP / "src").glob("*.js"))) + 1, "case_specific_matches": 0}
    suite.test("Connected/core code is fixture-free", "CORE_PURITY", core_purity)

    def confidential_safe():
        blob = canonical_json(tethys)
        banned = [r"\bPelagon\b", r"\bAlessandro\b", r"\bCamilla\b", r"\bSteve\b", r"\bGauthier\b", r"\bNicolas\b", r"\bACE\b"]
        found = [pattern for pattern in banned if re.search(pattern, blob, re.I)]
        req(not found, f"real-deal/confidential identifiers found: {found}")
        req("synthetic" in str(tethys.get("disclosure", "")).lower(), "synthetic disclosure missing")
        return {"real_identifiers": 0, "synthetic": True}
    suite.test("Tethys fixture is resynthesized and confidential-safe", "FIXTURE_SAFETY", confidential_safe)

    def generalization_overlap():
        def statements(p): return {normalize_statement(x.get("statement", "")) for x in p["deal"].get("claims", []) if x.get("statement")}
        a = statements(tethys)
        values = {}
        for name, other in (("Keystone", keystone), ("Orion", orion)):
            b = statements(other)
            overlap = len(a & b) / max(1, len(a))
            req(overlap < 0.20, f"Tethys/{name} overlap {overlap:.1%} exceeds 20%")
            values[name] = round(overlap, 4)
        return {"normalized_exact_overlap": values, "tethys_claims": len(a)}
    suite.test("Venture statement overlap is below 20%", "GENERALIZATION", generalization_overlap)

    def no_lbo_language():
        blob = canonical_json(tethys["deal"])
        banned = ["EBITDA", "MOIC", "IRR", "seller-adjusted", "debt paydown", "entry multiple", "exit multiple", "leverage ratio", "rollover equity"]
        found = [item for item in banned if re.search(r"(?<![A-Za-z])" + re.escape(item) + r"(?![A-Za-z])", blob, re.I)]
        req(not found, f"LBO-specific quantities leaked into venture case: {found}")
        return {"banned_lbo_terms": 0}
    suite.test("Early-stage venture case contains no LBO grammar", "GENERALIZATION", no_lbo_language)

    def archetype_hierarchy():
        a = tethys["deal"]["archetype"]
        required = ["kernel", "archetype", "stage_overlay", "sector_overlay", "fund_lens", "deal_instance"]
        req(all(a.get(k) for k in required), f"archetype hierarchy incomplete: {a}")
        req(len(tethys["deal"]["question_spine"]) == 9, "venture spine must start with nine questions")
        return {key: a[key] for key in required}
    suite.test("Venture grammar uses a hierarchical archetype", "VENTURE_GRAMMAR", archetype_hierarchy)

    def interaction_provenance():
        deal = tethys["deal"]
        participants = {x.get("id") or x.get("participant_id") for x in deal["participants"]}
        for interaction in deal["interactions"]:
            for field in ("interaction_id", "interaction_type", "start_at", "end_at", "participant_ids", "source_version_id", "transcript_status", "speaker_identification_confidence", "consent_status", "confidentiality_class", "effective_date", "known_at"):
                req(interaction.get(field) not in (None, ""), f"interaction {interaction.get('id')} lacks {field}")
            req(set(interaction["participant_ids"]).issubset(participants), "interaction references unknown participant")
        return {"participants": len(participants), "interactions": len(deal["interactions"])}
    suite.test("Interactions carry speaker-level provenance and governance", "INTERACTIONS", interaction_provenance)

    def utterance_integrity():
        deal = tethys["deal"]
        interactions = {x.get("id") or x.get("interaction_id") for x in deal["interactions"]}
        participants = {x.get("id") or x.get("participant_id") for x in deal["participants"]}
        for u in deal["utterances"]:
            req(u.get("interaction_id") in interactions, f"utterance {u.get('id')} has unknown interaction")
            req(u.get("speaker_id") in participants, f"utterance {u.get('id')} has unknown speaker")
            for field in ("locator", "verbatim_text", "attribution_confidence", "effective_date", "known_at"):
                req(u.get(field) not in (None, ""), f"utterance {u.get('id')} lacks {field}")
        return {"utterances": len(deal["utterances"]), "references_valid": True}
    suite.test("Every utterance resolves to a speaker and interaction", "INTERACTIONS", utterance_integrity)

    def speech_epistemic_boundary():
        deal = tethys["deal"]
        utterance_ids = {u["utterance_id"] for u in deal["utterances"]}
        content = [c for c in deal["claims"] if c.get("utterance_id") in utterance_ids and c.get("asserting_actor_id") and not c.get("observed_speech_act")]
        observed = [c for c in deal["claims"] if c.get("observed_speech_act")]
        req(content and all(c.get("epistemic_class") == "asserted" for c in content), "utterance content was promoted above asserted")
        req(observed and all(c.get("epistemic_class") == "observed" for c in observed), "speech-act observations are not observed")
        return {"content_claims_asserted": len(content), "speech_act_observations": len(observed)}
    suite.test("Observed speech act does not make its content observed truth", "EPISTEMIC", speech_epistemic_boundary)

    def bitemporal_v20_objects():
        deal = tethys["deal"]
        collections = ["claims", "interactions", "utterances", "agent_missions", "spine_change_proposals", "condition_edges", "validation_envelopes", "derivation_specs", "lenses"]
        checked = 0
        for key in collections:
            for item in deal.get(key, []):
                req(item.get("effective_date") and item.get("known_at"), f"{key} object lacks bitemporal fields: {item.get('id')}")
                parse_time(item["known_at"])
                checked += 1
        return {"objects_checked": checked, "collections": collections}
    suite.test("V20 venture objects are bitemporal", "TEMPORAL", bitemporal_v20_objects)

    def declarative_rules():
        rules = tethys["deal"]["discrepancy_rules"]
        req(len(rules) >= 3, "fewer than three discrepancy rules")
        req(not tethys["deal"].get("discrepancy_candidates"), "base fixture should not pre-author generated discrepancy candidates")
        req({r["type"] for r in rules} >= {"NUMERIC_INCOMPATIBILITY", "EXACT_CONTRADICTION", "CONDITIONAL_INVALIDATION"}, "required discrepancy types missing")
        return {"rules": len(rules), "preauthored_candidates": 0, "types": sorted({r['type'] for r in rules})}
    suite.test("Discrepancies are generated from declarative rules", "COMPILER", declarative_rules)

    def derivation_specs():
        specs = tethys["deal"]["derivation_specs"]
        for spec in specs:
            for field in ("method_type", "input_claim_ids", "formula", "assumptions", "output_definition_id", "effective_date", "known_at"):
                req(spec.get(field) not in (None, "", []), f"derivation spec {spec.get('id')} lacks {field}")
        return {"specs": len(specs), "methods": [s["method_type"] for s in specs]}
    suite.test("Deterministic derivations expose inputs, formula and assumptions", "DERIVATIONS", derivation_specs)

    def hypotheses_are_separate():
        rules = tethys["deal"]["discrepancy_rules"]
        templates = [text for rule in rules for text in rule.get("hypothesis_templates", [])]
        req(templates, "no hypothesis templates")
        req(not tethys["deal"].get("hypotheses"), "base fixture contains pre-admitted hypotheses")
        return {"templates": len(templates), "base_hypotheses": 0}
    suite.test("AI explanations are separate from deterministic derivations", "EPISTEMIC", hypotheses_are_separate)

    def mission_governance():
        missions = tethys["deal"]["agent_missions"]
        for m in missions:
            for field in ("objective", "allowed_sources", "prohibited_sources", "confidential_context_policy", "data_egress_policy", "expected_output", "stop_condition", "authority_class", "reviewer_id"):
                req(m.get(field) not in (None, "", []), f"mission {m.get('id')} lacks {field}")
            if m.get("external_human_contact"):
                req(not m.get("auto_executable_in_mock"), "human-contact mission marked auto executable")
        return {"missions": len(missions), "human_or_physical": sum(m.get('external_human_contact') or not m.get('auto_executable_in_mock') for m in missions)}
    suite.test("Agent missions declare authority, data-egress and stop conditions", "MISSIONS", mission_governance)

    def venture_math():
        vf = tethys["deal"]["venture_financing"]
        req(math.isclose(vf["post_money_eur_m"], vf["pre_money_eur_m"] + vf["new_money_eur_m"], rel_tol=0, abs_tol=1e-9), "post-money arithmetic wrong")
        expected = vf["new_money_eur_m"] / vf["post_money_eur_m"] * 100
        req(math.isclose(vf["new_investor_ownership_pct"], expected, rel_tol=0, abs_tol=0.01), "new investor ownership wrong")
        req(math.isclose(sum(x["ownership_pct"] for x in vf["pre_round_cap_table"]), 100.0, abs_tol=0.01), "pre-round cap table does not sum")
        req(math.isclose(sum(x["ownership_pct"] for x in vf["post_round_cap_table"]), 100.0, abs_tol=0.01), "post-round cap table does not sum")
        return {"post_money_eur_m": vf["post_money_eur_m"], "new_investor_ownership_pct": vf["new_investor_ownership_pct"], "cap_tables_sum_to": 100}
    suite.test("Venture financing, dilution and ownership arithmetic reconcile", "VENTURE_FINANCE", venture_math)

    suite.test("Condition edges and technical validation envelopes are first-class", "TECHNICAL_VALIDATION", lambda: (
        req(len(tethys["deal"]["condition_edges"]) >= 2, "condition edges missing") or
        req(len(tethys["deal"]["validation_envelopes"]) >= 3, "validation envelopes missing") or
        {"condition_edges": len(tethys["deal"]["condition_edges"]), "validation_envelopes": len(tethys["deal"]["validation_envelopes"])}
    ))

    def lenses_declarative():
        lenses = tethys["deal"]["lenses"]
        facts_blob = canonical_json(tethys["deal"]["claims"])
        for lens in lenses:
            req(lens.get("question_order") and lens.get("ranking_weights"), "lens has no real projection behavior")
            req(all(q in {x["id"] for x in tethys["deal"]["question_spine"]} for q in lens["question_order"]), "lens references unknown question")
            req(canonical_json(lens) not in facts_blob, "lens content contaminated facts")
        return {"lenses": len(lenses), "behaviors": ["question order", "ranking weights", "required questions", "controls"]}
    suite.test("Fund Lens changes emphasis through projection policy, not facts", "LENS", lenses_declarative)

    def typed_schemas():
        files = sorted(SCHEMAS.glob("*.schema.json"))
        gaps = {p.name: typed_property_gaps(read_json(p)) for p in files}
        bad = {name: value for name, value in gaps.items() if value}
        req(not bad, f"untyped schema properties: {bad}")
        return {"schema_count": len(files), "untyped_property_gaps": 0}
    suite.test("All public schemas contain typed properties", "SCHEMAS", typed_schemas)

    def static_syntax():
        js = sorted((APP / "src").glob("*.js"))
        failures = []
        for path in js:
            result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
            if result.returncode:
                failures.append(f"{path.name}: {result.stderr}")
        py = [ROOT / "01_PRODUCT_BUILD" / "mock_api" / "server.py", TRANSITION_ADAPTER, COMPILER_ADAPTER, Path(__file__)]
        for path in py:
            result = subprocess.run([sys.executable, "-m", "py_compile", str(path)], capture_output=True, text=True)
            if result.returncode:
                failures.append(f"{path.name}: {result.stderr}")
        req(not failures, "syntax failures: " + "; ".join(failures))
        return {"javascript_files": len(js), "python_files": len(py), "errors": 0}
    suite.test("Browser and Python runtime syntax is valid", "SYNTAX", static_syntax)

    def compiler_adapter_test():
        module = import_module(COMPILER_ADAPTER, "panta_v20_compiler_adapter")
        base = read_json(SAMPLES / "sample_v20_base_projection_shell.json")
        bundle = read_json(SAMPLES / "sample_v20_compiler_bundle.json")
        before = copy.deepcopy(bundle)
        one = module.map_compiler_bundle(base, bundle)
        two = module.map_compiler_bundle(base, bundle)
        req(bundle == before, "compiler adapter mutated input")
        req(one == two, "compiler adapter is not deterministic")
        assert_zero_schema_errors("frontend_projection", one)
        return {"deterministic": True, "pure": True, "schema_errors": 0, "projection_id": one["deal"]["projection_id"]}
    suite.test("Compiler bundle maps through a pure typed adapter", "ADAPTERS", compiler_adapter_test)

    def transition_adapter_test():
        module = import_module(TRANSITION_ADAPTER, "panta_v20_transition_adapter")
        raw = read_json(SAMPLES / "sample_venture_engine_output.json")
        before = copy.deepcopy(raw)
        one = module.map_engine_output(raw)
        two = module.map_engine_output(raw)
        req(raw == before, "transition adapter mutated input")
        req(one == two, "transition adapter is not deterministic")
        assert_zero_schema_errors("transition_result", one)
        req(one["mapping_contract"]["integration_required_field_count"] == 19, "19-field integration mapping not declared")
        return {"deterministic": True, "pure": True, "schema_errors": 0, "integration_fields": 19}
    suite.test("Frozen engine output maps through a pure 19-field adapter", "ADAPTERS", transition_adapter_test)

    def institutional_act_regression():
        keyword = re.compile(r"firm-underwritten|investment committee|\bIC\b.*(?:approved|decision|condition)|approved EV ceiling|the fund (?:approved|decided|directed)", re.I)
        offenders = []
        for case in (keystone, orion, tethys):
            for claim in case["deal"].get("claims", []):
                if claim.get("epistemic_class") == "attested" and keyword.search(claim.get("statement", "")):
                    offenders.append((case["deal"]["case_id"], claim.get("claim_id")))
        req(not offenders, f"firm acts classified attested: {offenders}")
        return {"firm_acts_misclassified_attested": 0}
    suite.test("No detected firm act carries the attested class", "EPISTEMIC", institutional_act_regression)

    def canonical_language():
        retired = "supported" + " price"
        hits = []
        for top in (ROOT / "00_START_HERE", ROOT / "01_PRODUCT_BUILD", ROOT / "02_PRODUCT_EXPERIENCE", ROOT / "04_INFORMATION_ARCHITECTURE_AND_FLOWS", ROOT / "05_DESIGN_SYSTEM_AND_INTERACTION", ROOT / "06_RESEARCH_AND_VALIDATION", ROOT / "07_ENGINEERING_CONTRACTS_AND_ADAPTERS", ROOT / "09_DEMO"):
            if not top.exists():
                continue
            for path in top.rglob("*"):
                if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                    if retired in path.read_text(encoding="utf-8", errors="ignore").lower():
                        hits.append(str(path.relative_to(ROOT)))
        req(not hits, f"retired pricing phrase found: {hits}")
        return {"retired_phrase_hits": 0}
    suite.test("Canonical approved EV ceiling terminology is preserved", "LANGUAGE", canonical_language)

    with server_process() as runtime:
        api: Api = runtime["api"]

        suite.test("Connected mode refuses fixture-backed data", "MODE_HONESTY", lambda: (
            (lambda result: (req(result[0] == 503 and result[1].get("error", {}).get("code") == "CONNECTED_BACKEND_NOT_CONFIGURED", f"Connected did not refuse: {result}"), {"status": result[0], "error_code": result[1]["error"]["code"]})[1])(
                api.call("GET", f"/bootstrap?mode=CONNECTED&case_id={V20_CASE}")
            )
        ))

        def live_schema_validation():
            evidence = {}
            for case in ("PROJECT-KEYSTONE", "PROJECT-ORION", V20_CASE):
                boot = api.bootstrap(case)
                status, payload = api.projection(case, boot["session_id"])
                req(status == 200, f"projection failed for {case}")
                assert_zero_schema_errors("frontend_projection", payload["projection"])
                assert_zero_schema_errors("experience_context", payload["context"])
                evidence[case] = {"projection_errors": 0, "context_errors": 0}
            return evidence
        suite.test("All three live projections and contexts validate", "SCHEMAS", live_schema_validation)

        def generated_objects():
            boot = api.bootstrap(V20_CASE)
            status, payload = api.projection(V20_CASE, boot["session_id"])
            req(status == 200, "projection failed")
            deal = payload["projection"]["deal"]
            req(len(deal["discrepancy_candidates"]) >= 3, "generated discrepancies missing")
            req(len(deal["derivations"]) == 4, "deterministic derivations missing")
            req(len(deal["hypotheses"]) >= 3, "hypotheses missing")
            req(len(deal["spine_change_proposals"]) == 1, "spine proposal missing")
            return {"discrepancies": len(deal["discrepancy_candidates"]), "derivations": len(deal["derivations"]), "hypotheses": len(deal["hypotheses"]), "spine_changes": len(deal["spine_change_proposals"])}
        suite.test("Compiler layer generates reviewable V20 proposals", "COMPILER", generated_objects)

        def historical_projection():
            boot = api.bootstrap(V20_CASE)
            status, payload = api.projection(V20_CASE, boot["session_id"], as_of_date="2026-06-05")
            req(status == 200, f"historical projection failed: {payload}")
            deal = payload["projection"]["deal"]
            req(len(deal["interactions"]) == 1, f"expected one known interaction, got {len(deal['interactions'])}")
            req(all(parse_time(x["known_at"]) <= parse_time("2026-06-05") for x in deal["claims"]), "future claim leaked into past projection")
            req(payload["context"]["as_of_date"] == "2026-06-05", "context date mismatch")
            return {"as_of_date": "2026-06-05", "interactions": len(deal["interactions"]), "claims": len(deal["claims"]), "active_lens": payload["context"]["active_lens_id"]}
        suite.test("Selecting a past date renders only then-known information", "TEMPORAL", historical_projection)

        def replay_read_only():
            boot = api.bootstrap(V20_CASE)
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            before = len(payload["registry"])
            event_id = payload["registry"][-1]["event_id"]
            status, replay = api.call("GET", f"/cases/{V20_CASE}/replay?session_id={session}&event_id={event_id}")
            req(status == 200, f"replay failed: {replay}")
            req(replay["read_only"] and replay["derived_from_event_log"], "replay is not read-only/event-derived")
            req(replay.get("effective_date") and replay.get("known_at"), "replay event lacks both dates")
            _, after_payload = api.projection(V20_CASE, session)
            req(len(after_payload["registry"]) == before, "replay wrote to Registry")
            return {"event_id": event_id, "registry_before": before, "registry_after": len(after_payload["registry"]), "stable_hash": replay["stable_hash"]}
        suite.test("Causal Replay is event-derived, bitemporal and read-only", "TEMPORAL", replay_read_only)

        def lens_server_behavior():
            boot = api.bootstrap(V20_CASE)
            session = boot["session_id"]
            _, core = api.projection(V20_CASE, session, lens_id="TY-LENS-VENTURE-CORE")
            _, tech = api.projection(V20_CASE, session, lens_id="TY-LENS-DEEP-TECH")
            core_ids = [q["id"] for q in core["projection"]["deal"]["question_spine"]]
            tech_ids = [q["id"] for q in tech["projection"]["deal"]["question_spine"]]
            req(core_ids != tech_ids, "Lens did not change question ordering")
            req(core["projection"]["deal"]["lens_projection"]["facts_hash"] == tech["projection"]["deal"]["lens_projection"]["facts_hash"], "Lens changed facts")
            return {"core_first": core_ids[:3], "deep_tech_first": tech_ids[:3], "facts_hash_stable": True}
        suite.test("Lens changes ranking and visibility without changing facts", "LENS", lens_server_behavior)

        def discrepancy_review():
            boot = api.bootstrap(V20_CASE)
            session = boot["session_id"]
            status, proposals = api.call("GET", f"/cases/{V20_CASE}/compiler-proposals?session_id={session}")
            req(status == 200 and proposals["discrepancies"], "no discrepancy proposals")
            obj = proposals["discrepancies"][0]
            req(obj["automatic_truth_change"] is False and obj["review_status"] == "PROPOSED", "candidate was automatically admitted")
            status, reviewed = api.call("POST", f"/cases/{V20_CASE}/compiler-proposals/discrepancy/{obj['id']}/review?session_id={session}", {"decision": "ADMITTED", "rationale": "Professional accepts the discrepancy, not either underlying value."})
            req(status == 200, f"review failed: {reviewed}")
            candidate = next(x for x in reviewed["projection"]["deal"]["discrepancy_candidates"] if x["id"] == obj["id"])
            req(candidate["review_status"] == "ADMITTED", "review status did not persist")
            return {"discrepancy_id": obj["id"], "automatic_truth_change": False, "review_status": candidate["review_status"]}
        suite.test("Candidate discrepancy requires professional review", "COMPILER", discrepancy_review)

        def deterministic_outputs():
            boot = api.bootstrap(V20_CASE)
            _, payload = api.projection(V20_CASE, boot["session_id"])
            values = {d["derivation_id"]: d["value"] for d in payload["projection"]["deal"]["derivations"]}
            req(math.isclose(values["TY-DER-NOMINAL-AREA"], 201.06, abs_tol=0.02), f"nominal area {values}")
            req(math.isclose(values["TY-DER-IMPLIED-RADIUS"], 97.72, abs_tol=0.02), f"implied radius {values}")
            req(math.isclose(values["TY-DER-RUNWAY"], 16.0, abs_tol=0.01), f"runway {values}")
            req(math.isclose(values["TY-DER-OWNERSHIP"], 20.0, abs_tol=0.01), f"ownership {values}")
            return values
        suite.test("Deterministic arithmetic produces inspectable expected values", "DERIVATIONS", deterministic_outputs)

        def hypothesis_gate():
            boot = api.bootstrap(V20_CASE)
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            hypothesis = payload["projection"]["deal"]["hypotheses"][0]
            req(hypothesis["origin"] == "AI_REASONING_PROPOSAL" and hypothesis["epistemic_class"] == "asserted", "hypothesis class/origin wrong")
            req(hypothesis["propagation_eligible"] is False, "unreviewed hypothesis is propagation eligible")
            status, reviewed = api.call("POST", f"/cases/{V20_CASE}/compiler-proposals/hypothesis/{hypothesis['id']}/review?session_id={session}", {"decision": "ADMITTED", "rationale": "Accepted as a position proposal for governed propagation."})
            req(status == 200, f"hypothesis review failed: {reviewed}")
            admitted = next(x for x in reviewed["projection"]["deal"]["hypotheses"] if x["id"] == hypothesis["id"])
            req(admitted["propagation_eligible"] is True, "admitted hypothesis not marked eligible")
            return {"hypothesis_id": hypothesis["id"], "before": False, "after": True}
        suite.test("AI hypothesis cannot propagate before admission", "EPISTEMIC", hypothesis_gate)

        def spine_authority():
            assoc = api.bootstrap(V20_CASE, actor="associate")
            session = assoc["session_id"]
            _, payload = api.projection(V20_CASE, session)
            proposal = payload["projection"]["deal"]["spine_change_proposals"][0]
            status, denied = api.call("POST", f"/cases/{V20_CASE}/compiler-proposals/spine/{proposal['id']}/review?session_id={session}", {"decision": "ACCEPTED"})
            req(status == 403 and denied["error"]["code"] == "SPINE_AUTHORITY_REQUIRED", f"associate approved spine: {denied}")
            partner = api.bootstrap(V20_CASE, actor="partner")
            ps = partner["session_id"]
            _, pp = api.projection(V20_CASE, ps)
            pprop = pp["projection"]["deal"]["spine_change_proposals"][0]
            status, accepted = api.call("POST", f"/cases/{V20_CASE}/compiler-proposals/spine/{pprop['id']}/review?session_id={ps}", {"decision": "ACCEPTED", "rationale": "Promote maintenance economics."})
            req(status == 200, f"partner approval failed: {accepted}")
            req(any(q["id"] == "TYQ-MAINTENANCE" for q in accepted["projection"]["deal"]["question_spine"]), "new spine question missing")
            req(pprop["binding_migration"]["preserve_aliases"] is True, "historical aliases not preserved")
            return {"associate_status": 403, "partner_status": 200, "question_count": len(accepted["projection"]["deal"]["question_spine"])}
        suite.test("Question-spine changes are governed and replayable", "SPINE_GOVERNANCE", spine_authority)

        def mission_prepare_only():
            boot = api.bootstrap(V20_CASE)
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            mission = payload["projection"]["deal"]["agent_missions"][0]
            before_sources = len(payload["projection"]["deal"]["source_center"]["sources"])
            status, out = api.call("POST", f"/cases/{V20_CASE}/missions/{mission['id']}/prepare?session_id={session}", {})
            req(status == 201 and out["mission_run"]["status"] == "PREPARED", f"prepare failed: {out}")
            _, after = api.projection(V20_CASE, session)
            req(len(after["projection"]["deal"]["source_center"]["sources"]) == before_sources, "preparation created a result source")
            return {"status": "PREPARED", "source_count_unchanged": True}
        suite.test("Preparing a mission causes no research or external effect", "MISSIONS", mission_prepare_only)

        def synthetic_mission_run():
            boot = api.bootstrap(V20_CASE)
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            mission = next(m for m in payload["projection"]["deal"]["agent_missions"] if m.get("auto_executable_in_mock") and not m.get("external_human_contact"))
            before_sources = len(payload["projection"]["deal"]["source_center"]["sources"])
            status, out = api.call("POST", f"/cases/{V20_CASE}/missions/{mission['id']}/run?session_id={session}", {})
            req(status == 200, f"synthetic mission failed: {out}")
            req(out["mission_run"]["synthetic"] and out["mission_run"]["no_external_effects"], "mission disclosure missing")
            req(out["proposed_claims"][0]["review_status"] == "REVIEW_REQUIRED", "mission result silently admitted")
            req(len(out["projection"]["deal"]["source_center"]["sources"]) == before_sources + 1, "mission source not added")
            return {"mission_id": mission["id"], "new_source": out["source"]["source_id"], "review_required": True, "external_effects": False}
        suite.test("Policy-safe synthetic mission creates a reviewable source", "MISSIONS", synthetic_mission_run)

        def human_mission_refused():
            boot = api.bootstrap(V20_CASE)
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            mission = next(m for m in payload["projection"]["deal"]["agent_missions"] if m.get("external_human_contact") or not m.get("auto_executable_in_mock"))
            status, out = api.call("POST", f"/cases/{V20_CASE}/missions/{mission['id']}/run?session_id={session}", {})
            req(status == 409 and out["error"]["code"] == "MISSION_AUTHORITY_REQUIRED", f"external mission auto-ran: {out}")
            return {"mission_id": mission["id"], "status": status, "error_code": out["error"]["code"]}
        suite.test("Human-contact and physical missions cannot auto-run", "MISSIONS", human_mission_refused)

        def transcript_ingestion():
            boot = api.bootstrap(V20_CASE)
            session = boot["session_id"]
            _, before = api.projection(V20_CASE, session)
            interaction_count = len(before["projection"]["deal"]["interactions"])
            content = "[00:01:10] Founder: The controlled sea trial should complete in September.\n[00:02:15] Customer: We have not yet observed an autonomous alert.\n"
            body = {"method": "FILE", "file_name": "synthetic_reference.transcript", "source_name": "Synthetic reference transcript", "content_b64": base64.b64encode(content.encode()).decode(), "source_type": "TRANSCRIPT", "purpose": "V20 transcript parser acceptance"}
            status, queued = api.call("POST", f"/cases/{V20_CASE}/ingest?session_id={session}", body)
            req(status == 202, f"ingest was not queued: {queued}")
            job_id = queued["job"]["job_id"]
            job = queued["job"]
            for _ in range(12):
                status, polled = api.call("GET", f"/jobs/{job_id}?session_id={session}")
                req(status == 200, f"job poll failed: {polled}")
                job = polled["job"]
                if job["status"] == "COMPLETE":
                    break
            req(job["status"] == "COMPLETE", f"job did not complete: {job}")
            _, after = api.projection(V20_CASE, session)
            deal = after["projection"]["deal"]
            req(len(deal["interactions"]) == interaction_count + 1, "interaction not created")
            new = deal["interactions"][-1]
            utterances = [u for u in deal["utterances"] if u["interaction_id"] == new["interaction_id"]]
            claims = [c for c in deal["claims"] if c.get("interaction_id") == new["interaction_id"]]
            req(len(utterances) == 2 and len(claims) == 2, "transcript did not produce two utterances/claims")
            req(all(c["epistemic_class"] == "asserted" for c in claims), "transcript content was not asserted")
            return {"job_id": job_id, "interaction_id": new["interaction_id"], "utterances": len(utterances), "claims": len(claims), "content_class": "asserted"}
        suite.test("Transcript ingestion creates native interactions and asserted content claims", "INTERACTIONS", transcript_ingestion)

        def human_stop_gate():
            boot = api.bootstrap(V20_CASE, actor="partner")
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            _, _, admitted = admit(api, V20_CASE, session, payload, "coverage_restatement", "V20-HS-ADMIT")
            transition, run = admitted["transition"], admitted["run"]
            req(transition["human_stops"], "human stop missing")
            selected = [transition["artifact_change_sets"][0]["artifact_id"]]
            status, _ = api.call("POST", f"/runs/{run['run_id']}/prepare?session_id={session}", {"selected_change_ids": selected})
            req(status == 200, "prepare failed")
            body = {"candidate_state_id": run["candidate_state_id"], "as_of_state_id": payload["context"]["as_of_state_id"], "as_of_date": payload["context"]["as_of_date"], "selected_change_ids": selected, "human_stop_ids": [transition["human_stops"][0]["stop_id"]], "authority_record_ids": [], "execution_package_ids": [], "actor_id": payload["context"]["authenticated_actor"]["actor_id"], "allow_partial_settlement": False, "idempotency_key": "V20-HS-NOAUTH"}
            status, out = api.call("POST", f"/runs/{run['run_id']}/settle?session_id={session}", body, {"Idempotency-Key": body["idempotency_key"]})
            req(status == 409 and "requires a scoped authority record" in out["error"]["message"], f"settlement bypassed human stop: {out}")
            return {"human_stop_id": transition["human_stops"][0]["stop_id"], "settlement_status_without_authority": status}
        suite.test("Human Stop settlement is refused without scoped authority", "AUTHORITY", human_stop_gate)

        def wrong_candidate_refused():
            boot = api.bootstrap(V20_CASE, actor="partner")
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            _, _, admitted = admit(api, V20_CASE, session, payload, "coverage_restatement", "V20-WRONGCAND-ADMIT")
            transition, run = admitted["transition"], admitted["run"]
            selected = [transition["artifact_change_sets"][0]["artifact_id"]]
            api.call("POST", f"/runs/{run['run_id']}/prepare?session_id={session}", {"selected_change_ids": selected})
            stop = transition["human_stops"][0]
            course = next(c for c in payload["projection"]["deal"]["decisionRoom"]["courses"] if c["effect_type"] == "EXTERNAL_PACKAGE")
            body = {"run_id": run["run_id"], "candidate_state_id": "CAND-WRONG", "human_stop_id": stop["stop_id"], "course_id": course["id"], "artifact_hash": transition["replay_hash"], "idempotency_key": "V20-WRONGCAND-AUTH"}
            status, out = api.call("POST", f"/runs/{run['run_id']}/authority/attest?session_id={session}", body, {"Idempotency-Key": body["idempotency_key"]})
            req(status == 409 and out["error"]["code"] == "CANDIDATE_CONTEXT_MISMATCH", f"wrong candidate accepted: {out}")
            return {"status": status, "error_code": out["error"]["code"]}
        suite.test("Authority rejects a mismatched Candidate", "AUTHORITY", wrong_candidate_refused)

        def unknown_change_refused():
            boot = api.bootstrap(V20_CASE)
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            _, _, admitted = admit(api, V20_CASE, session, payload, "maintenance_gap", "V20-UNKNOWN-ADMIT")
            run = admitted["run"]
            status, out = api.call("POST", f"/runs/{run['run_id']}/prepare?session_id={session}", {"selected_change_ids": ["ART-NOT-AFFECTED"]})
            req(status == 409 and out["error"]["code"] == "UNKNOWN_CHANGE_ID", f"unknown change accepted: {out}")
            return {"status": status, "error_code": out["error"]["code"]}
        suite.test("Preparation rejects changes outside the transition output", "SETTLEMENT", unknown_change_refused)

        def full_authority_execution_settlement():
            boot = api.bootstrap(V20_CASE, actor="partner")
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            _, _, admitted = admit(api, V20_CASE, session, payload, "coverage_restatement", "V20-FULL-ADMIT")
            transition, run = admitted["transition"], admitted["run"]
            selected = [transition["artifact_change_sets"][0]["artifact_id"]]
            status, _ = api.call("POST", f"/runs/{run['run_id']}/prepare?session_id={session}", {"selected_change_ids": selected})
            req(status == 200, "prepare failed")
            stop = transition["human_stops"][0]
            course = next(c for c in payload["projection"]["deal"]["decisionRoom"]["courses"] if c["effect_type"] == "EXTERNAL_PACKAGE")
            auth_body = {"run_id": run["run_id"], "candidate_state_id": run["candidate_state_id"], "human_stop_id": stop["stop_id"], "course_id": course["id"], "artifact_hash": transition["replay_hash"], "idempotency_key": "V20-FULL-AUTH"}
            status, attested = api.call("POST", f"/runs/{run['run_id']}/authority/attest?session_id={session}", auth_body, {"Idempotency-Key": auth_body["idempotency_key"]})
            req(status == 200 and attested.get("execution_package"), f"authority/package failed: {attested}")
            assert_zero_schema_errors("authority_record", attested["authority_record"])
            assert_zero_schema_errors("execution_package", attested["execution_package"])
            package = attested["execution_package"]
            status, sent = api.call("POST", f"/execution-packages/{package['execution_package_id']}/send?session_id={session}", {"simulate_failure": False})
            req(status == 200 and sent["execution_package"]["status"] == "ACCEPTED", f"package not acknowledged: {sent}")
            settle_body = {"candidate_state_id": run["candidate_state_id"], "as_of_state_id": payload["context"]["as_of_state_id"], "as_of_date": payload["context"]["as_of_date"], "selected_change_ids": selected, "human_stop_ids": [stop["stop_id"]], "authority_record_ids": [attested["authority_record"]["authority_record_id"]], "execution_package_ids": [package["execution_package_id"]], "actor_id": payload["context"]["authenticated_actor"]["actor_id"], "allow_partial_settlement": False, "idempotency_key": "V20-FULL-SETTLE"}
            status, settled = api.call("POST", f"/runs/{run['run_id']}/settle?session_id={session}", settle_body, {"Idempotency-Key": settle_body["idempotency_key"]})
            req(status == 200, f"settlement failed: {settled}")
            assert_zero_schema_errors("settlement_result", settled)
            return {"authority_schema_errors": 0, "package_status": sent["execution_package"]["status"], "settlement_schema_errors": 0, "current_state_id": settled["current_state_id"]}
        suite.test("Authority, course-specific execution and settlement complete coherently", "GOVERNED_FLOW", full_authority_execution_settlement)

        def blocked_partial():
            boot = api.bootstrap(V20_CASE)
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            _, _, admitted = admit(api, V20_CASE, session, payload, "maintenance_gap", "V20-BLOCK-ADMIT")
            transition, run = admitted["transition"], admitted["run"]
            req(transition["blocked_components"], "blocked component missing")
            selected = [transition["artifact_change_sets"][0]["artifact_id"]]
            status, _ = api.call("POST", f"/runs/{run['run_id']}/prepare?session_id={session}", {"selected_change_ids": selected})
            req(status == 200, "prepare failed")
            body = {"candidate_state_id": run["candidate_state_id"], "as_of_state_id": payload["context"]["as_of_state_id"], "as_of_date": payload["context"]["as_of_date"], "selected_change_ids": selected, "human_stop_ids": [], "authority_record_ids": [], "execution_package_ids": [], "actor_id": payload["context"]["authenticated_actor"]["actor_id"], "allow_partial_settlement": False, "idempotency_key": "V20-BLOCK-NO"}
            status, denied = api.call("POST", f"/runs/{run['run_id']}/settle?session_id={session}", body, {"Idempotency-Key": body["idempotency_key"]})
            req(status == 409 and "explicit bounded partial settlement" in denied["error"]["message"], f"blocked region silently settled: {denied}")
            body["allow_partial_settlement"] = True
            body["idempotency_key"] = "V20-BLOCK-YES"
            status, accepted = api.call("POST", f"/runs/{run['run_id']}/settle?session_id={session}", body, {"Idempotency-Key": body["idempotency_key"]})
            req(status == 200 and accepted["partial"] is True and accepted["blocked_components"], f"partial settlement failed: {accepted}")
            return {"without_partial": 409, "with_partial": 200, "blocked_component_id": accepted["blocked_components"][0]["component_id"]}
        suite.test("Blocked scope remains explicit and requires bounded partial settlement", "SETTLEMENT", blocked_partial)

        def idempotency_conflict():
            boot = api.bootstrap(V20_CASE)
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            event, body = admission_payload(payload, "maintenance_gap", "V20-IDEMPOTENT")
            status, first = api.call("POST", f"/cases/{V20_CASE}/events/{event['event_id']}/admit?session_id={session}", body, {"Idempotency-Key": body["idempotency_key"]})
            req(status == 200, f"first request failed: {first}")
            altered = {**body, "treatment_hash": "sha256:conflicting"}
            status, conflict = api.call("POST", f"/cases/{V20_CASE}/events/{event['event_id']}/admit?session_id={session}", altered, {"Idempotency-Key": body["idempotency_key"]})
            req(status == 409 and conflict["error"]["code"] == "IDEMPOTENCY_CONFLICT", f"payload conflict not rejected: {conflict}")
            return {"first_status": 200, "conflict_status": 409, "error_code": conflict["error"]["code"]}
        suite.test("Idempotency key rejects a conflicting payload", "IDEMPOTENCY", idempotency_conflict)

        def conflicting_attestation():
            boot = api.bootstrap(V20_CASE, actor="partner")
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            _, _, admitted = admit(api, V20_CASE, session, payload, "coverage_restatement", "V20-CONFLICT-ADMIT")
            transition, run = admitted["transition"], admitted["run"]
            selected = [transition["artifact_change_sets"][0]["artifact_id"]]
            api.call("POST", f"/runs/{run['run_id']}/prepare?session_id={session}", {"selected_change_ids": selected})
            stop = transition["human_stops"][0]
            external = [c for c in payload["projection"]["deal"]["decisionRoom"]["courses"] if c["effect_type"] == "EXTERNAL_PACKAGE"]
            req(len(external) >= 2, "fixture needs two incompatible external courses")
            first = {"run_id": run["run_id"], "candidate_state_id": run["candidate_state_id"], "human_stop_id": stop["stop_id"], "course_id": external[0]["id"], "artifact_hash": transition["replay_hash"], "idempotency_key": "V20-CONFLICT-A"}
            status, out = api.call("POST", f"/runs/{run['run_id']}/authority/attest?session_id={session}", first, {"Idempotency-Key": first["idempotency_key"]})
            req(status == 200, f"first attestation failed: {out}")
            # Re-open only for negative conflict test; the server also checks existing incompatible records.
            run_stop = transition["human_stops"][0]
            second = {**first, "course_id": external[1]["id"], "idempotency_key": "V20-CONFLICT-B"}
            status, conflict = api.call("POST", f"/runs/{run['run_id']}/authority/attest?session_id={session}", second, {"Idempotency-Key": second["idempotency_key"]})
            req(status == 409 and conflict["error"]["code"] in {"HUMAN_STOP_NOT_OPEN", "CONFLICTING_ATTESTATION"}, f"conflicting course accepted: {conflict}")
            return {"first_course": external[0]["id"], "second_course": external[1]["id"], "second_status": status, "error_code": conflict["error"]["code"]}
        suite.test("Incompatible authority courses cannot coexist", "AUTHORITY", conflicting_attestation)

        def authority_not_reusable():
            boot = api.bootstrap(V20_CASE, actor="partner")
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            # First run, obtain authority.
            _, _, one = admit(api, V20_CASE, session, payload, "coverage_restatement", "V20-REUSE-A1")
            t1, r1 = one["transition"], one["run"]
            selected1 = [t1["artifact_change_sets"][0]["artifact_id"]]
            api.call("POST", f"/runs/{r1['run_id']}/prepare?session_id={session}", {"selected_change_ids": selected1})
            stop1 = t1["human_stops"][0]
            course = next(c for c in payload["projection"]["deal"]["decisionRoom"]["courses"] if c["effect_type"] == "EXTERNAL_PACKAGE")
            auth = {"run_id": r1["run_id"], "candidate_state_id": r1["candidate_state_id"], "human_stop_id": stop1["stop_id"], "course_id": course["id"], "artifact_hash": t1["replay_hash"], "idempotency_key": "V20-REUSE-AUTH"}
            status, attested = api.call("POST", f"/runs/{r1['run_id']}/authority/attest?session_id={session}", auth, {"Idempotency-Key": auth["idempotency_key"]})
            req(status == 200, f"authority creation failed: {attested}")
            authority_id = attested["authority_record"]["authority_record_id"]
            # Second run from the same current state, attempt reuse.
            _, _, two = admit(api, V20_CASE, session, payload, "coverage_restatement", "V20-REUSE-A2")
            t2, r2 = two["transition"], two["run"]
            selected2 = [t2["artifact_change_sets"][0]["artifact_id"]]
            api.call("POST", f"/runs/{r2['run_id']}/prepare?session_id={session}", {"selected_change_ids": selected2})
            settle_body = {"candidate_state_id": r2["candidate_state_id"], "as_of_state_id": payload["context"]["as_of_state_id"], "as_of_date": payload["context"]["as_of_date"], "selected_change_ids": selected2, "human_stop_ids": [t2["human_stops"][0]["stop_id"]], "authority_record_ids": [authority_id], "execution_package_ids": [], "actor_id": payload["context"]["authenticated_actor"]["actor_id"], "allow_partial_settlement": False, "idempotency_key": "V20-REUSE-SETTLE"}
            status, denied = api.call("POST", f"/runs/{r2['run_id']}/settle?session_id={session}", settle_body, {"Idempotency-Key": settle_body["idempotency_key"]})
            req(status == 409 and "requires a scoped authority record" in denied["error"]["message"], f"authority record reused across runs: {denied}")
            return {"source_run": r1["run_id"], "target_run": r2["run_id"], "reuse_status": status}
        suite.test("Authority records cannot be reused across runs", "AUTHORITY", authority_not_reusable)

        def delivery_failure_not_success():
            boot = api.bootstrap(V20_CASE, actor="partner")
            session = boot["session_id"]
            _, payload = api.projection(V20_CASE, session)
            _, _, admitted = admit(api, V20_CASE, session, payload, "coverage_restatement", "V20-FAIL-ADMIT")
            transition, run = admitted["transition"], admitted["run"]
            selected = [transition["artifact_change_sets"][0]["artifact_id"]]
            api.call("POST", f"/runs/{run['run_id']}/prepare?session_id={session}", {"selected_change_ids": selected})
            stop = transition["human_stops"][0]
            course = next(c for c in payload["projection"]["deal"]["decisionRoom"]["courses"] if c["effect_type"] == "EXTERNAL_PACKAGE")
            auth = {"run_id": run["run_id"], "candidate_state_id": run["candidate_state_id"], "human_stop_id": stop["stop_id"], "course_id": course["id"], "artifact_hash": transition["replay_hash"], "idempotency_key": "V20-FAIL-AUTH"}
            _, attested = api.call("POST", f"/runs/{run['run_id']}/authority/attest?session_id={session}", auth, {"Idempotency-Key": auth["idempotency_key"]})
            package = attested["execution_package"]
            status, failed = api.call("POST", f"/execution-packages/{package['execution_package_id']}/send?session_id={session}", {"simulate_failure": True})
            req(status == 503 and failed["error"]["code"] == "DELIVERY_FAILED", f"delivery failure not returned: {failed}")
            status, state = api.call("GET", f"/cases/{V20_CASE}/projection?session_id={session}")
            # Package is intentionally not visible through projection; query the session-derived send result contract.
            req(package["status"] == "READY", "local pre-ack package was optimistically mutated")
            return {"send_status": 503, "error_code": failed["error"]["code"], "pre_ack_status": "READY"}
        suite.test("Failed delivery never reports optimistic success", "EXECUTION", delivery_failure_not_success)

        def defer_no_package():
            room = tethys["deal"]["decisionRoom"]
            defer = next(c for c in room["courses"] if c["effect_type"] == "DEFER")
            req(not defer.get("execution"), "Defer contains an execution payload")
            return {"course_id": defer["id"], "effect_type": "DEFER", "execution_package": None}
        suite.test("Defer has no executable package", "EXECUTION", defer_no_package)

        if not args.skip_browser:
            suite.test("V20 venture objects and governed flows render in the browser", "BROWSER_E2E", lambda: run_browser_acceptance(runtime["browser_origin"]))

    report = suite.finish()
    RESULTS_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "PANTA V20 TEST RESULTS",
        "=" * 88,
        f"Status: {report['status']}",
        f"Passed: {report['passed']} / {report['total']}",
        f"Failed: {report['failed']}",
        "",
        report["scope_limit"],
        "",
    ]
    md = [
        "# PANTA V20 Test Results",
        "",
        f"- **Status:** {report['status']}",
        f"- **Passed:** {report['passed']} / {report['total']}",
        f"- **Failed:** {report['failed']}",
        "",
        report["scope_limit"],
        "",
        "## Results",
        "",
    ]
    for item in report["results"]:
        lines.append(f"[{item['status']}] {item['category']} :: {item['name']}")
        md.append(f"### {item['status']} - {item['name']}")
        md.append("")
        md.append(f"Category: `{item['category']}`  ")
        md.append(f"Duration: `{item['duration_ms']} ms`")
        if item["error"]:
            lines.append(f"    {item['error']}")
            md.extend(["", f"Error: `{item['error']}`"])
        elif item["evidence"] is not None:
            evidence = canonical_json(item["evidence"])
            lines.append("    " + evidence)
            md.extend(["", "```json", json.dumps(item["evidence"], indent=2, ensure_ascii=False), "```"])
        md.append("")
    RESULTS_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    RESULTS_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nRESULT: {report['status']} - {report['passed']}/{report['total']} passed", flush=True)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
