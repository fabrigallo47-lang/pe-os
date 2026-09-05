"""Explicit simulated model responses, run through the real deterministic pipeline.

This validates parsing, typing and transport, not LLM extraction accuracy.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from app.statement_tracking import statement_context
from tools.extract_v2_physical import annotate_chunk, assemble, parse_markdown, validate, _to_e3_manifest


def annotations():
    base = dict(metric="Other", metric_label="Primary raise", unit="€m", period="FY2026",
                perimeter="Test Company primary round", entity="Test Company", scope="primary round",
                basis="cash proceeds", measurement="total", scenario="Base", claim_kind="QUANTITATIVE",
                bound="EXACT", definition_id="Primary capital subscribed before fees", epistemic_class="asserted")
    rows = [
        ("Euro raise", "FY2026 Base: Test Company proposes total primary cash proceeds of EUR 5 million, defined as primary capital subscribed before fees.", dict(value="5")),
        ("Dollar alternative", "FY2026 Base: Test Company proposes total primary cash proceeds of USD 5 million in the dollar alternative, before fees.", dict(value="5", unit="$m")),
        ("Timing", "The proposed completion interval is 30-60 days.", dict(value="30-60", unit="days", bound="RANGE", metric_label="Completion interval", period="unknown", scope="unspecified", basis="unspecified", definition_id=None)),
        ("Ownership", "The approximate ownership offered in the FY2026 primary round is 8.5%.", dict(value="8.5%", unit="%", bound="APPROXIMATE", metric_label="Ownership offered")),
        ("Verification", "Independent performance verification remains outstanding.", dict(value=None, unit=None, claim_kind="QUALITATIVE", bound="NONE", metric_label="Verification state")),
        ("Litigation", "No litigation is reported as of 2026-01-10.", dict(value=None, unit=None, claim_kind="NEGATIVE", bound="NONE", metric_label="Litigation", period="2026-01-10")),
        ("Attribution", "Test analyst recorded the view that independent verification must precede approval.", dict(value=None, unit=None, claim_kind="ATTRIBUTION", bound="NONE", metric_label="Recorded view", author="Test analyst")),
    ]
    return [{**base, **patch, "statement": text, "locator_hint": "## " + heading} for heading, text, patch in rows]


def build_typed_fixture(root: Path, case_id="CASE-1"):
    rows = annotations()
    inbox = root / "vault" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / "typed-tracking.md"
    path.write_text("# Synthetic tracking acceptance\n\n" + "\n\n".join(row["locator_hint"] + "\n" + row["statement"] for row in rows))
    version = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    envelope = dict(schema_version="panta.source-envelope/1.0", case_id=case_id, source_id="SRC-TYPED",
                    source_version_id=version, original_filename=path.name, stored_filename=path.name)
    source = dict(source_id="SRC-TYPED", name=path.name, doc_type="markdown", known_at="2026-01-10T09:00:00Z", source_envelope=envelope)
    chunks = parse_markdown(path, max_words=2000, source_record=source)

    def respond(**request):
        content = request["messages"][0]["content"]
        selected = [row for row in rows if row["statement"] in content]
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="emit_claims", input={"claims": selected})])

    simulated = SimpleNamespace(messages=SimpleNamespace(create=respond))
    raw = [claim for chunk in chunks for claim in annotate_chunk(chunk, simulated, case_id, rate_limit_delay=0, raise_errors=True)]
    graph = assemble([validate(claim) for claim in raw])
    e3 = _to_e3_manifest(graph, case_id, "SIMULATED-TYPED-TRACKING", [source])
    metadata = {row["claim_id"]: row for row in e3["extraction_metadata"]["compiler_fields_per_claim"]}
    claims = [{**claim, **metadata[claim["claim_id"]]} for claim in e3["claims"]]
    manifest_path = inbox / ".ingest-manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"items": []}
    manifest["items"].append({"case_id": case_id, "source_envelope": envelope})
    manifest_path.write_text(json.dumps(manifest))
    bundle = root / "cases" / case_id
    bundle.mkdir(parents=True, exist_ok=True)
    claim_file = bundle / "claims.json"
    existing = json.loads(claim_file.read_text()) if claim_file.exists() else []
    claim_file.write_text(json.dumps(existing + claims))
    return dict(source=source, raw=raw, graph=graph, e3=e3, claims=claims, path=path, projected=[{
        "id": c["claim_id"], "sourceId": c["source_id"], "sourceVersionId": c["source_version_id"],
        "locator": c["locator"], "type": "Simulated extraction", "label": c["statement"],
        "normalizedStatement": c["statement"], "claimKind": c["claim_kind"], "tracking": statement_context(c),
    } for c in claims])
