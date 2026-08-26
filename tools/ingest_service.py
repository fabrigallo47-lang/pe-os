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

def ingest_workbook(path: Path, deal: str = "keystone",
                    concepts_path: Path | None = None) -> dict:
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

    resolution: dict[str, Any] = {"admitted": 0, "violations": 0, "status": "NOT_RUN"}
    bindings_out: list[dict] = []
    if concepts_path and concepts_path.exists():
        concepts = binding_resolver.load_concepts(concepts_path)
        # feed L2's own proposals rather than a file written earlier
        cands = []
        by_alias = {}
        for c in concepts.values():
            for alias in [c.label, *c.aliases]:
                by_alias[alias.strip().lower()] = c.concept_id
        for r in reports:
            for p in r.proposals:
                if p.confidence < 0.6:
                    continue
                cid = by_alias.get((p.row_label or "").strip().lower())
                if not cid:
                    continue
                cands.append(binding_resolver.Binding(
                    concept_id=cid, locator=p.cell, period=p.col_header,
                    scenario=r.sheet, section=p.section, unit=p.unit,
                    confidence=p.confidence, evidence=p.evidence))
        res = binding_resolver.resolve(cands, concepts, graph.to_json())
        bindings_out = [{"concept_id": b.concept_id, "locator": b.locator,
                         "period": b.period, "scenario": b.scenario,
                         "section": b.section, "unit": b.unit,
                         "confidence": b.confidence} for b in res.admitted]
        resolution = {"admitted": len(res.admitted),
                      "violations": len(res.violations),
                      "status": res.status,
                      "candidates": len(cands)}

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
        "cells": graph.to_json()["cells"],
        # A workbook yields no claims. Saying so is the point.
        "claims": [],
        "note": ("Un workbook produce il lato modello: celle, formule, binding. "
                 "Non produce claim — quelli vengono dai documenti."),
    }


# ── document ─────────────────────────────────────────────────────────────────

def ingest_document(path: Path, deal: str = "keystone",
                    api_key: str | None = None) -> dict:
    """extract_v2 L1-L4 over one document."""
    import os
    sys.path.insert(0, str(ROOT / "vercel" / "api"))
    from _extract_flow import run_extraction

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return {"kind": "document", "source": path.name,
                "error": "ANTHROPIC_API_KEY non impostata: nessuna estrazione"}

    t0 = time.time()
    res = run_extraction(path.read_text(encoding="utf-8"), path.name, deal, key)
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
        rep = gate_run(tmp, deal)
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
           concepts_path: Path | None = None) -> dict:
    if not path.exists():
        return {"error": f"file non trovato: {path}"}
    if path.suffix.lower() in {".xlsx", ".xlsm", ".ods"}:
        return ingest_workbook(path, deal, concepts_path)
    return ingest_document(path, deal)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Ingest one source and report what it produced")
    ap.add_argument("--path", type=Path, required=True)
    ap.add_argument("--deal", default="keystone")
    ap.add_argument("--concepts", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    res = ingest(a.path, a.deal, a.concepts)
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
        print("  claim prodotti:", len(res["claims"]), "—", res["note"])
    else:
        print("  pipeline:", json.dumps(res["pipeline"], ensure_ascii=False))
        g = res.get("grounding", {})
        if "claims_total" in g:
            print(f"  gate: {g['claims_clean']}/{g['claims_total']} puliti · "
                  f"{g['blocking_total']} bloccanti")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str),
                         encoding="utf-8")
        print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
