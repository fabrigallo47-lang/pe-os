#!/usr/bin/env python3
"""
ingest_service — run a real extraction and report what it produced.

Two sources, two pipelines, and they populate different halves of a deal:

  document (.md/.txt/.pdf)  extract_v2  -> claims, with locators and periods
  workbook (.xlsx)          extract_v3  -> a computable cell graph, then
                                           sheet_semantics and binding_resolver

The distinction matters for what appears on screen. A document produces the
claim side — evidence, support routes, the change-arrival screens. A workbook
produces the model side — cells, formulas, bindings. Neither produces the other,
and a workbook ingest that showed claims would be showing something it did not
extract.

Everything here reports counts of what it actually built. An empty section is
returned empty rather than filled from a fixture, because the point of ingesting
from zero is to see the shape of what is genuinely missing.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── workbook ─────────────────────────────────────────────────────────────────

def default_concepts(deal: str) -> Path:
    """The deal's declared model vocabulary. Absent means nothing is bound."""
    return ROOT / "vault" / "deals" / deal / "model_concepts.json"


def _compute_values(path: Path, digest: str) -> dict[str, float]:
    """
    Every cell's value, from the workbook's own formulas.

    Evaluating the whole graph takes about a minute, which is too long to repeat
    for a file that has not changed, so results are cached under the L1 digest —
    the same content-address the source graph computes. A different workbook is
    a different digest and gets computed afresh; there is no way for a stale
    value to be served for a file that changed.
    """
    cache = ROOT / "pipeline_out" / "cellvalues" / f"{digest}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    from tools.extract_v3 import compile_workbook
    model = compile_workbook(path)
    values = {k: v["value"] for k, v in model.cells.items()
              if isinstance(v.get("value"), (int, float))}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(values), encoding="utf-8")
    return values


def _candidates(reports, concepts, binding_resolver):
    """
    L2 proposals that name a declared concept, as binding candidates.

    Two sheet shapes, two ways a cell is identified, and the difference matters:

      model sheet   the row label names the quantity, the column header names
                    the period, and the sheet names the scenario
      record table  the column header names the field, and the row's key names
                    the record — the case, the customer, the project

    Reading a record table as if it were a model sheet loses the record, which
    is exactly what identifies the value: a Gross MOIC belonging to no case is
    not a fact about anything.
    """
    by_alias: dict[str, str] = {}
    for c in concepts.values():
        for alias in [c.label, *c.aliases]:
            by_alias[alias.strip().lower()] = c.concept_id

    cands = []
    for r in reports:
        for p in r.proposals:
            if p.confidence < 0.6:
                continue
            if p.record_key:
                cid = by_alias.get((p.col_header or "").strip().lower())
                period, scenario = "", p.record_key
            else:
                cid = by_alias.get((p.row_label or "").strip().lower())
                period, scenario = p.col_header, r.sheet
            if not cid:
                continue
            cands.append(binding_resolver.Binding(
                concept_id=cid, locator=p.cell, period=period,
                scenario=scenario, section=p.section, unit=p.unit,
                confidence=p.confidence, evidence=p.evidence))
    return cands


def _records(bindings: list[dict], concepts_doc: dict) -> list[dict]:
    """
    Admitted bindings from record tables, regrouped into the records they came
    from: one row per case, carrying every field bound for it.

    The regrouping is the inverse of the extraction — L2 walks cells, this walks
    records — and it is what lets a scenario be shown as a scenario instead of
    as eleven unrelated numbers.
    """
    fields = concepts_doc.get("returns_table", {})
    wanted = {v: k for k, v in fields.items() if not k.startswith("_")}
    by_scenario: dict[str, dict] = {}
    for b in bindings:
        if b["concept_id"] not in wanted or not b.get("scenario"):
            continue
        rec = by_scenario.setdefault(b["scenario"], {"record": b["scenario"],
                                                     "fields": {}})
        rec["fields"][wanted[b["concept_id"]]] = {
            "concept_id": b["concept_id"], "value": b.get("value"),
            "unit": b.get("unit", ""), "locator": b["locator"],
        }
    return [r for r in by_scenario.values() if r["fields"]]


def ingest_workbook(path: Path, deal: str = "keystone",
                    concepts_path: Path | None = None,
                    compute: bool = True) -> dict:
    """L1 -> L2 -> L3 over a workbook. No model call: sheet judgments come from
    the cache if one exists, and are simply absent if it does not."""
    from tools import source_graph, sheet_semantics, binding_resolver

    t0 = time.time()
    graph = source_graph.capture(path)
    l1 = graph.stats()

    judgments = sheet_semantics.load_judgments(
        ROOT / "vault" / "policy" / "sheet_classifications.json")
    reports = sheet_semantics.analyse_workbook(path, judgments)
    proposals = [p for r in reports for p in r.proposals]
    confident = [p for r in reports for p in r.confident]

    if concepts_path is None:
        concepts_path = default_concepts(deal)

    values: dict[str, float] = {}
    resolution: dict[str, Any] = {"admitted": 0, "violations": 0, "status": "NOT_RUN"}
    bindings_out: list[dict] = []
    records: list[dict] = []
    if concepts_path.exists():
        concepts_doc = json.loads(concepts_path.read_text(encoding="utf-8"))
        concepts = binding_resolver.load_concepts(concepts_path)
        cands = _candidates(reports, concepts, binding_resolver)
        res = binding_resolver.resolve(cands, concepts, graph.to_json())
        if compute:
            values = _compute_values(path, graph.digest)
        bindings_out = [{"concept_id": b.concept_id, "locator": b.locator,
                         "period": b.period, "scenario": b.scenario,
                         "section": b.section, "unit": b.unit,
                         "confidence": b.confidence,
                         "value": values.get(b.locator)} for b in res.admitted]
        records = _records(bindings_out, concepts_doc)
        resolution = {"admitted": len(res.admitted),
                      "violations": len(res.violations),
                      "status": res.status,
                      "candidates": len(cands),
                      "concepts_declared": len(concepts),
                      "values_computed": bool(values)}

    return {
        "kind": "workbook",
        "source": path.name,
        "digest": graph.digest,
        "elapsed": round(time.time() - t0, 2),
        "L1_source_graph": l1,
        "L2_semantics": {
            "sheets": len(reports),
            "proposals": len(proposals),
            "confident": len(confident),
            "review": len(proposals) - len(confident),
            "sheet_kinds": {r.sheet: r.kind for r in reports},
            "judgments_used": len(judgments),
        },
        "L3_resolution": resolution,
        "bindings": bindings_out,
        "records": records,
        "cells": graph.to_json()["cells"],
        # A workbook yields no claims. Saying so is the point.
        "claims": [],
        "note": ("Un workbook produce il lato modello: celle, formule, binding. "
                 "Non produce claim — quelli vengono dai documenti."),
    }


# ── document ─────────────────────────────────────────────────────────────────

def _key_from_env_file() -> str:
    """
    The API key from .env.local, if the environment does not already carry one.

    Read locally and used locally. Policy row 3 covers the model call itself;
    reading the key from a gitignored file next to the code is the same act as
    exporting it, minus having to remember to. A redacted placeholder is not a
    key — treat it as absent rather than sending it and getting a 401 that looks
    like a pipeline failure.
    """
    f = ROOT / ".env.local"
    if not f.exists():
        return ""
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.startswith("ANTHROPIC_API_KEY"):
            continue
        val = line.split("=", 1)[1].strip().strip('"').strip("'")
        return val if val.startswith("sk-ant-") else ""
    return ""


def _document_text(path: Path) -> str:
    """
    The document's full text, for grounding claims back against it.

    Built from the same chunker the extraction used, so what the gate checks
    against is what the model was shown — not a second reading of the file that
    might differ from the first.
    """
    try:
        sys.path.insert(0, str(ROOT / "vercel" / "api"))
        from _extract_v2 import parse_source
        return "\n".join(ch.body for ch in parse_source(path))
    except Exception:
        return ""


def ingest_document(path: Path, deal: str = "keystone",
                    api_key: str | None = None) -> dict:
    """extract_v2 L1-L4 over one document."""
    import os
    sys.path.insert(0, str(ROOT / "vercel" / "api"))
    from _extract_flow import run_extraction

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "") or _key_from_env_file()
    if not key:
        return {"kind": "document", "source": path.name,
                "error": "ANTHROPIC_API_KEY non impostata: nessuna estrazione",
                "fix": "mettila in .env.local o esportala; i workbook non ne "
                       "hanno bisogno, L1-L3 è tutto locale"}

    t0 = time.time()
    # The file is already on disk here, so hand it over directly: chunking a PDF
    # means reading the PDF, not a string we made from it.
    res = run_extraction("", path.name, deal, key, source_path=path)
    if res.get("error"):
        return {"kind": "document", "source": path.name, "error": res["error"]}

    claims = res["claims"]
    e3 = res.get("e3", {})
    grounding: dict = {}
    try:
        import tempfile
        from tools.grounding_gate import run as gate_run
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(e3, f, ensure_ascii=False)
            tmp = Path(f.name)
        # The gate resolves a locator by filename, and extract_v2's locators are
        # page ranges. We have the document open right here, so hand the text
        # over instead of letting the gate fail to find it and report every
        # claim as unverifiable.
        rep = gate_run(tmp, deal, sources={path.name: _document_text(path)})
        tmp.unlink(missing_ok=True)
        grounding = {k: v for k, v in rep.items() if k != "review_queue"}
        grounding["review_queue"] = rep.get("review_queue", [])
    except Exception as exc:
        grounding = {"error": str(exc)}

    return {
        "kind": "document",
        "source": path.name,
        "elapsed": round(time.time() - t0, 2),
        "pipeline": res["pipeline"],
        "claims": claims,
        "e3": e3,
        "grounding": grounding,
    }


def ingest(path: Path, deal: str = "keystone",
           concepts_path: Path | None = None, store=None) -> dict:
    """
    Run the right pipeline for the source and, if given a store, record it there.

    The store is where the frontend reads from, so a source that was ingested
    but not stored would be work nobody can see. It is passed in rather than
    opened here because whether an ingest is kept is the caller's decision.
    """
    if not path.exists():
        return {"error": f"file non trovato: {path}"}
    if path.suffix.lower() in {".xlsx", ".xlsm", ".ods"}:
        res = ingest_workbook(path, deal, concepts_path)
        if store is not None and not res.get("error"):
            res["stored"] = store.add_workbook(path, res)
    else:
        res = ingest_document(path, deal)
        if store is not None and not res.get("error"):
            res["stored"] = store.add_document(path, res)
    return res


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Ingest one source and report what it produced")
    ap.add_argument("--path", type=Path, required=True)
    ap.add_argument("--deal", default="keystone")
    ap.add_argument("--concepts", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--store", action="store_true",
                    help="scrivi il risultato nello store che alimenta la UI")
    ap.add_argument("--reset", action="store_true",
                    help="azzera lo store prima di ingerire")
    a = ap.parse_args()

    store = None
    if a.store or a.reset:
        from tools.live_store import LiveStore
        store = LiveStore(a.deal)
        if a.reset:
            store.reset()
            print(f"[ingest] store {a.deal} azzerato")

    res = ingest(a.path, a.deal, a.concepts, store)
    if res.get("error"):
        print("errore:", res["error"])
        return 1

    print(f"[ingest] {res['source']}  ({res['kind']}, {res.get('elapsed','?')}s)")
    if res["kind"] == "workbook":
        print("  L1:", json.dumps(res["L1_source_graph"], ensure_ascii=False))
        l2 = res["L2_semantics"]
        print(f"  L2: {l2['sheets']} fogli · {l2['confident']}/{l2['proposals']} sicure "
              f"· {l2['review']} in revisione · {l2['judgments_used']} giudizi in cache")
        print("  L3:", json.dumps(res["L3_resolution"], ensure_ascii=False))
        for rec in res.get("records", []):
            fields = " · ".join(
                f"{k}={v['value']:.3f}" if isinstance(v["value"], float)
                else f"{k}={v['value']}"
                for k, v in rec["fields"].items() if v["value"] is not None)
            print(f"  record  {rec['record']:22} {fields}")
        print("  claim prodotti:", len(res["claims"]), "—", res["note"])
    else:
        print("  pipeline:", json.dumps(res["pipeline"], ensure_ascii=False))
        g = res.get("grounding", {})
        if "claims_total" in g:
            print(f"  gate: {g['claims_clean']}/{g['claims_total']} puliti · "
                  f"{g['blocking_total']} bloccanti")

    if store is not None:
        s = store.summary()
        print(f"  store: {s['sources']} sorgenti · {s['claims']} claim · "
              f"{s['bindings']} binding · {s['records']} record · "
              f"{s['grounding_findings']} rilievi ({s['grounding_blocking']} bloccanti)")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str),
                         encoding="utf-8")
        print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
