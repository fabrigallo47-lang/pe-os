#!/usr/bin/env python3
"""Turn declared model nodes (a CSV) into an execution mapping.

The second of the two ways a deal gets a model without anyone writing
Python for it. The first is compiling the deal's own workbook
(workbook_model_compiler). This is for a deal that has no workbook yet:
an analyst declares the nodes as rows, and they compile into the same
mapping shape the generic evaluator already runs.

The input format is the one the Silexara corpus ships in
SRC-21_MODEL_NODES.csv, which keeps identity explicit — metric, period,
perimeter, entity, scenario, version — precisely so that "rows with
different identities must not be compared as though they were the same
number" (its own binding note). Two rows can therefore share a metric and
still be different facts: detection_recall is 0.94 for a heavy vehicle at
300m on dry ground and 0.41 for a quiet crawler at 120m on mixed ground,
and collapsing those into one number would be a lie about what was tested.

Two admissions this makes and does not hide:

  * A row marked anything other than `proposed` does not enter the model.
    The corpus marks an analyst hypothesis `unadmitted`; loading it as a
    node would launder a guess into a fact.
  * A value that is not a number cannot be a DIRECT_INPUT value. "4-8"
    is a real answer to "how many months", and coercing it to 4 or 8 or 6
    would invent precision the analyst deliberately withheld.

Both cases are reported, never silently dropped.

    python3 tools/model_nodes_to_mapping.py NODES.csv [--case-id CASE] [-o out.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

ADMITTED = "proposed"
_NUMERIC = re.compile(r"^-?\d+(\.\d+)?$")


def _node_id(row: dict[str, str]) -> str:
    """Keep the analyst's own id. It is already stable and already unique,
    and renaming it would break the trail back to the source row."""
    return str(row.get("node_id") or "").strip()


def rows_to_mapping(rows: list[dict[str, str]], case_id: str) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []

    for row in rows:
        node_id = _node_id(row)
        if not node_id:
            excluded.append({"node_id": "(missing)", "reason": "row has no node_id"})
            continue

        status = (row.get("admission_status") or "").strip().lower()
        if status != ADMITTED:
            excluded.append({
                "node_id": node_id,
                "reason": f"admission_status is {status!r}, not {ADMITTED!r} — "
                          f"an unadmitted row is not part of the model",
            })
            continue

        raw_value = (row.get("value") or "").strip()
        node: dict[str, Any] = {
            "model_node_id": node_id,
            "label": (row.get("metric") or "").strip(),
            "computational_form": "DIRECT_INPUT",
            "unit": (row.get("unit") or "").strip(),
            "period": (row.get("period") or "").strip(),
            # Identity, carried through verbatim: two rows sharing a metric
            # are different facts when these differ, and the mapping must
            # keep saying so.
            "perimeter": (row.get("perimeter") or "").strip(),
            "entity": (row.get("entity") or "").strip(),
            "scenario": (row.get("scenario") or "").strip(),
            "version": (row.get("version") or "").strip(),
            "epistemic_class": (row.get("epistemic_status") or "").strip(),
            "source_ref": (row.get("source") or "").strip(),
            "formula_id": None,
            "directed_deps": [],
        }
        if _NUMERIC.match(raw_value):
            node["initial_value"] = float(raw_value)
        else:
            node["initial_value"] = None
            node["value_raw"] = raw_value
            excluded.append({
                "node_id": node_id,
                "reason": f"value {raw_value!r} is not a number — the node exists "
                          f"but carries no computable value",
            })
        nodes.append(node)

    return {
        "mapping_version": "v7",
        "deal": case_id,
        "provenance": {"built_from": "declared model nodes", "admitted_status": ADMITTED},
        "model_nodes": nodes,
        # No formulas: a declared-node model states what is known, not how to
        # compute anything. Formulas arrive when the analyst declares them,
        # and until then an empty list is the honest answer rather than a
        # guessed relationship between rows that merely look related.
        "formulas": [],
        "declared_exclusions": excluded,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--case-id", default="CASE-UNSPECIFIED")
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args(argv[1:])

    with args.csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    mapping = rows_to_mapping(rows, args.case_id)

    if args.output:
        args.output.write_text(json.dumps(mapping, indent=1), encoding="utf-8")
        print(f"wrote {args.output}")
    print(f"  nodes admitted : {len(mapping['model_nodes'])}")
    print(f"  exclusions     : {len(mapping['declared_exclusions'])}")
    for item in mapping["declared_exclusions"]:
        print(f"    - {item['node_id']}: {item['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
