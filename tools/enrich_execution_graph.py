#!/usr/bin/env python3
"""
enrich_execution_graph — fill model-node values the transcription left empty.

The execution graph is compiled from tools/keystone_model.py, a hand
transcription of the workbook. Audited cell by cell against values computed
from the workbook's own formulas, that transcription is faithful where it
carries a value: 9 of 9 agree, none diverge. It is simply incomplete — 12 nodes
cite a workbook cell and carry no value at all.

Those 12 are not incidental. They are the exit bridge and the returns:
MN-EXIT-EV, MN-EXIT-EQUITY, MN-BASE-MOIC, MN-BASE-IRR and their scenario
variants — the nodes behind the CL-INVERSE-SOLVER-NOT-COMPILED coverage limit
declared to PANTA, whose stated cause was that the model "does not yet compute
the exit bridge inside PANTA".

It does compute it. The workbook has the formulas; the transcription omitted
them, and nothing downstream could tell the difference because a missing value
and an uncomputable one look identical once they are both None.

This fills only what is missing, never overwrites, and records where each value
came from so the enrichment is auditable rather than absorbed.

    python3 tools/enrich_execution_graph.py --cells cell_graph.json [--apply]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXEC_GRAPH = ROOT / "vault" / "deals" / "keystone" / "models" / "execution_graph_v7.json"

_REF = re.compile(r"^'?([^'!]+)'?!\$?([A-Z]{1,3})\$?(\d+)$")


def normalise_ref(workbook_ref: str) -> str | None:
    """
    'model.xlsx:Inputs!B3' -> 'INPUTS!B3'. Anything ambiguous returns None.

    A reference containing " / " is not safe to resolve. The separator means two
    different things in this data: on MN-SPONSOR-EQUITY, "Inputs!B8 /
    S&U_Opening!E21" is the same figure in two places, but on
    MN-BASE-EBITDA-MARGIN, "Scenario_Drivers!C7 / C5" is a ratio — EBITDA over
    revenue. Taking the first reference filled the margin with 3.088, an EBITDA
    amount presented as a 308% margin. Nothing in the string distinguishes the
    two cases, so neither is filled.
    """
    ref = workbook_ref or ""
    if ".xlsx:" in ref:
        ref = ref.split(".xlsx:", 1)[1]
    if " / " in ref:
        return None
    m = _REF.match(ref.strip())
    return f"{m.group(1).upper()}!{m.group(2)}{m.group(3)}" if m else None


def enrich(graph: dict, cells: dict) -> tuple[dict, list[dict]]:
    """Return (graph, report). Only None values are filled."""
    filled: list[dict] = []
    for node_id, node in graph.get("model_nodes", {}).items():
        if node.get("value_current") is not None:
            continue
        loc = normalise_ref(node.get("workbook_ref", ""))
        if not loc:
            continue
        computed = (cells.get(loc) or {}).get("value")
        if not isinstance(computed, (int, float)):
            continue
        node["value_current"] = computed
        # provenance travels with the value: a reader must be able to see that
        # this came from evaluating a formula, not from the transcription
        node["value_source"] = {"from": "workbook_formula", "cell": loc}
        filled.append({"node": node_id, "cell": loc, "value": computed})

    if filled:
        # The graph carries a hash of its own content. Filling values without
        # recomputing it leaves the graph claiming to be a document it no longer
        # is — the same defect that made the V7 bundle's provenance meaningless.
        content = {
            "model_nodes": graph.get("model_nodes", {}),
            "formulas": graph.get("formulas", []),
            "directed_model_edges": graph.get("directed_model_edges", []),
        }
        digest = hashlib.sha256(
            json.dumps(content, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        graph.setdefault("admission_manifest", {})["extraction_hash"] = digest
    return graph, filled


def main() -> int:
    ap = argparse.ArgumentParser(description="Fill empty model-node values from computed cells")
    ap.add_argument("--cells", type=Path, required=True,
                    help="cell_graph.json prodotto da extract_v3")
    ap.add_argument("--graph", type=Path, default=EXEC_GRAPH)
    ap.add_argument("--apply", action="store_true", help="scrive; altrimenti solo anteprima")
    a = ap.parse_args()

    graph = json.loads(a.graph.read_text(encoding="utf-8"))
    cells = json.loads(a.cells.read_text(encoding="utf-8")).get("cells", {})

    empty_before = sum(1 for n in graph.get("model_nodes", {}).values()
                       if n.get("value_current") is None)
    graph, filled = enrich(graph, cells)

    print(f"[enrich] {a.graph.name}")
    print(f"  nodi senza valore prima : {empty_before}")
    print(f"  riempiti dalle formule  : {len(filled)}")
    print(f"  ancora senza valore     : {empty_before - len(filled)}")
    for f in filled:
        print(f"    {f['node']:26} {f['cell']:22} = {f['value']}")

    if a.apply:
        a.graph.write_text(json.dumps(graph, indent=2, ensure_ascii=False),
                           encoding="utf-8")
        print(f"\n  scritto → {a.graph}")
    else:
        print("\n  (anteprima: usa --apply per scrivere)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
