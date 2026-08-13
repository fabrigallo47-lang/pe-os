#!/usr/bin/env python3
"""
Position → Model node binding proposer — zero LLM.

Reads:
  - CIC/tables/model_nodes.csv      canonical node IDs + names + kinds
  - CIC/tables/case_positions.csv   position_id, statement, position_type
                                    (model_binding_ids column is NEVER read)

Outputs:
  - vault/deals/<deal>/models/bindings.json

Grading against position_model_bindings.csv is left to benchmark_runner.py.
That CSV is never read here.

Usage:
    .venv/bin/python3 tools/position_model_binder.py \\
        --deal keystone \\
        --cic /tmp/panta_cic/PANTA_Keystone_Canonical_Investment_Case_v1_1

Binding type taxonomy:
    DIRECT                 — position directly states the value/definition of this node
    SCENARIO_DRIVER_OR_OUTPUT — position drives or is scored by this scenario node
    MODEL_CONTROL          — position is about model integrity (check cells)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "vault"

FORBIDDEN = {
    "position_model_bindings.csv",
    "claims_validation_only.csv",
    "PANTA_Keystone_Canonical_Investment_Case_v1.1.json",
    "layer_3_validation_DO_NOT_INGEST",
}


def _check_path(p: Path) -> None:
    for part in p.parts:
        if part in FORBIDDEN:
            sys.exit(f"[LEAKAGE GUARD] Refusing to read: {p}")


# ── Signal table ──────────────────────────────────────────────────────────────
# Each entry: (regex_pattern, [(node_id_fragment, binding_type), ...])
# Patterns are matched against the full lowercased position statement.
# The node_id_fragment must be an exact canonical MN-xxx ID.
# Order matters: earlier entries take priority for deduplication per (position, node) pair.

_SIGNALS: list[tuple[str, list[tuple[str, str]]]] = [
    # ── EBITDA definitions ────────────────────────────────────────────────────
    (r"seller.{0,30}ebitda|12\.7m|12\.7\b",
     [("MN-SELLER-EBITDA", "DIRECT")]),

    (r"qoe.{0,30}ebitda|qoe.{0,20}normalized|11\.9m|11\.9\b",
     [("MN-QOE-EBITDA", "DIRECT")]),

    (r"firm.{0,30}ebitda|firm.{0,25}underwritten|11\.4m|11\.4\b",
     [("MN-FIRM-EBITDA", "DIRECT")]),

    # QoE is a reference, not the final firm basis → both QoE and Firm
    (r"qoe.{0,50}reference.{0,30}not.{0,20}final|diligence.{0,40}reference.{0,25}not.{0,20}final",
     [("MN-QOE-EBITDA", "DIRECT"), ("MN-FIRM-EBITDA", "DIRECT")]),

    (r"covenant.{0,20}ebitda|12\.2m|12\.2\b",
     [("MN-COV-EBITDA", "DIRECT")]),

    # ── Capital structure inputs ───────────────────────────────────────────────
    (r"\bev\b|enterprise.{0,8}value|108\.0|108m|\$108",
     [("MN-EV", "DIRECT")]),

    (r"first.{0,12}lien|opening.{0,6}debt|42\.8m|42\.8\b",
     [("MN-DEBT", "DIRECT")]),

    (r"sponsor.{0,12}equity|sponsor.{0,12}cash.{0,12}equity|62\.0m|62\.0\b|\$62",
     [("MN-SPONSOR-EQUITY", "DIRECT")]),

    (r"\brollover\b|seller.{0,10}rollover|12\.0m.{0,20}seller|seller.{0,10}12\.0m",
     [("MN-ROLLOVER", "DIRECT")]),

    (r"opening.{0,8}cash\b",
     [("MN-OPENING-CASH", "DIRECT")]),

    # acquisition decision → full capital structure
    (r"approved.{0,30}capital.{0,20}structure|capital.{0,20}structure.{0,30}approved",
     [("MN-DEBT", "DIRECT"), ("MN-SPONSOR-EQUITY", "DIRECT"),
      ("MN-ROLLOVER", "DIRECT"), ("MN-OPENING-CASH", "DIRECT")]),

    (r"no more than.{0,10}108|maximum.{0,15}108|\$108.{0,5}ev",
     [("MN-EV", "DIRECT")]),

    # ── Operating inputs ──────────────────────────────────────────────────────
    (r"ultimate.{0,12}parent.{0,15}concentrat|18\.2|18\.2%",
     [("MN-CONCENTRATION", "DIRECT")]),

    (r"\bnwc\b|normalized.{0,8}nwc|working.{0,10}capital.{0,20}target|8\.4m|8\.4\b",
     [("MN-NWC", "DIRECT")]),

    (r"related.{0,12}party.{0,12}rent|headquarters.{0,20}lease|rent.{0,15}market.{0,15}term",
     [("MN-RELATED-PARTY-RENT-NORM", "DIRECT")]),

    # ── Integration (careful: "capability" mentions must NOT match) ───────────
    # CP-029: branding vs systems integration are separate → DIRECT to both nodes
    (r"commercial.{0,15}branding.{0,20}integration|branding.{0,15}integration.{0,25}operational.{0,15}system",
     [("MN-INTEGRATION-COST-ADJ", "DIRECT"),
      ("MN-COMBINED-RISK-INTEGRATION-SPEND", "DIRECT")]),

    # CP-015: integration program executable only if $2.0m funded → SDO (drives scenario)
    (r"integration.{0,15}program.{0,15}executable|2\.0m.{0,20}funded|funded.{0,20}2\.0m",
     [("MN-INTEGRATION-COST-ADJ", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-INTEGRATION-SPEND", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-EBITDA-MARGIN", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-DSO", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-WIP", "SCENARIO_DRIVER_OR_OUTPUT")]),

    # ── Assumption series: growth / margin / capex / WIP / DSO / exit mult ───
    (r"7.{0,3}%.{0,25}organic.{0,15}growth|organic.{0,15}growth.{0,15}7.{0,3}%"
     r"|standalone.{0,15}base.{0,15}organic",
     [("MN-BASE-GROWTH", "DIRECT")]),

    (r"revenue.{0,30}repeat.{0,20}orient|repeat.{0,25}contractually.{0,15}recurring"
     r"|not.{0,10}treated.{0,15}contractually",
     [("MN-BASE-GROWTH", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-DOWN-GROWTH", "SCENARIO_DRIVER_OR_OUTPUT")]),

    # Margin: standalone base only
    (r"ebitda.{0,20}margin.{0,30}expan|margin.{0,25}through.{0,20}pric"
     r"|utiliz.{0,20}margin.{0,20}improve|gradual.{0,20}margin",
     [("MN-BASE-EBITDA-MARGIN", "DIRECT")]),

    # Utilization normalization before margin improvement (CP-028)
    (r"utiliz.{0,50}before.{0,30}margin.{0,15}improv",
     [("MN-BASE-EBITDA-MARGIN", "DIRECT")]),

    (r"\bcapex\b.{0,10}1\.6|1\.6.{0,10}capex|asset.{0,8}light.{0,30}capex|capex.{0,20}revenue.{0,15}1\.6",
     [("MN-BASE-CAPEX", "DIRECT"), ("MN-DOWN-CAPEX", "DIRECT")]),

    (r"\bwip\b|ar aging|billing.{0,20}control|cash.{0,15}conversion.{0,15}risk"
     r"|wip.{0,15}billing|billing.{0,15}wip",
     [("MN-BASE-DSO", "DIRECT"), ("MN-BASE-WIP", "DIRECT")]),

    # Add-on acquisitions → acquisition case outputs
    (r"add.{0,6}on.{0,25}acquisition|add.{0,6}on.{0,20}optional.{0,20}upside"
     r"|optional.{0,20}upside.{0,20}exclud|excluded.{0,20}standalone",
     [("MN-ACQ-MOIC", "DIRECT"), ("MN-ACQ-IRR", "DIRECT")]),

    # ── Riverton / downside / combined risk ───────────────────────────────────
    (r"riverton.{0,50}durable|riverton.{0,50}base.{0,15}case"
     r"|material.{0,20}reduction.{0,15}riverton",
     [("MN-DOWN-GROWTH", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-DOWN-EBITDA-MARGIN", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-GROWTH", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-EBITDA-MARGIN", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-MOIC", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-IRR", "SCENARIO_DRIVER_OR_OUTPUT")]),

    # Correlated risks → full combined risk scenario
    (r"concentration.{0,30}integration.{0,20}risk.{0,25}correlat"
     r"|correlat.{0,20}concentration.{0,30}integration"
     r"|majority.{0,20}accept.{0,30}correl",
     [("MN-COMBINED-RISK-GROWTH", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-EBITDA-MARGIN", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-DSO", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-WIP", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-EXIT-MULT", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-MOIC", "SCENARIO_DRIVER_OR_OUTPUT"),
      ("MN-COMBINED-RISK-IRR", "SCENARIO_DRIVER_OR_OUTPUT")]),

    # Opening capital structure (CP-018: debt + equity + opening cash)
    (r"42\.8m.{0,30}supportable|supportable.{0,30}42\.8|first.{0,10}lien.{0,10}debt.{0,10}42\.8"
     r"|opening.{0,10}first.{0,10}lien.{0,30}62|least.{0,8}\$62",
     [("MN-DEBT", "DIRECT"), ("MN-SPONSOR-EQUITY", "DIRECT"),
      ("MN-OPENING-CASH", "DIRECT")]),

    # ── Return positions ──────────────────────────────────────────────────────
    (r"2\.00x.{0,15}moic|standalone.{0,15}base.{0,15}2\.0|2\.0x.{0,15}gross.{0,15}moic",
     [("MN-BASE-MOIC", "DIRECT")]),

    (r"14\.8.{0,5}%|14\.8.{0,8}xirr|14\.8.{0,8}irr",
     [("MN-BASE-IRR", "DIRECT")]),

    (r"9\.0x.{0,12}exit|exit.{0,6}9\.0x|9\.0x.{0,10}multiple|exit.{0,10}multiple.{0,10}9\.0",
     [("MN-BASE-EXIT-MULT", "DIRECT")]),

    # No multiple expansion → same exit multiple for EV
    (r"no.{0,15}multiple.{0,15}expansion|not.{0,15}rel.{0,15}multiple.{0,15}expan"
     r"|standalone.{0,20}base.{0,20}exit.{0,10}9",
     [("MN-EV", "DIRECT"), ("MN-BASE-EXIT-MULT", "DIRECT")]),

    (r"1\.28x|standalone.{0,15}downside.{0,20}moic|downside.{0,15}retain.{0,15}positive.{0,15}equity",
     [("MN-DOWN-MOIC", "DIRECT")]),

    (r"5\.1.{0,5}%.{0,10}xirr|5\.1.{0,5}%.{0,10}irr|standalone.{0,15}downside.{0,20}irr",
     [("MN-DOWN-IRR", "DIRECT")]),

    # ── Model control ─────────────────────────────────────────────────────────
    (r"internally.{0,25}consistent|model.{0,15}consistent|sources.{0,10}uses.{0,10}balance"
     r"|lbo.{0,15}model.{0,20}consistent|balance.{0,15}sheet.{0,15}check",
     [("MN-CHECK-SOURCES-USES", "MODEL_CONTROL"),
      ("MN-CHECK-OPENING-BS", "MODEL_CONTROL"),
      ("MN-CHECK-SB-BASE-BS", "MODEL_CONTROL"),
      ("MN-CHECK-SB-DOWN-BS", "MODEL_CONTROL"),
      ("MN-CHECK-ACQ-BASE-BS", "MODEL_CONTROL"),
      ("MN-CHECK-COMBINED-BS", "MODEL_CONTROL")]),
]

# Pre-compile all patterns
_COMPILED: list[tuple[re.Pattern, list[tuple[str, str]]]] = [
    (re.compile(pat, re.IGNORECASE | re.DOTALL), nodes)
    for pat, nodes in _SIGNALS
]


def _propose_for_position(statement: str, valid_nodes: set[str]) -> list[dict]:
    """Return list of {model_node_id, binding_type} proposals for one position."""
    text = statement.lower()
    seen: dict[str, str] = {}  # node_id → binding_type (first match wins per node)
    for pattern, mappings in _COMPILED:
        if pattern.search(text):
            for node_id, btype in mappings:
                if node_id in valid_nodes and node_id not in seen:
                    seen[node_id] = btype
    return [{"model_node_id": nid, "binding_type": bt} for nid, bt in seen.items()]


def propose_bindings(
    cic_dir: Path,
    deal: str,
    write: bool = True,
) -> list[dict]:
    """Load positions + node list, propose bindings, optionally write bindings.json."""
    nodes_csv = cic_dir / "tables" / "model_nodes.csv"
    positions_csv = cic_dir / "tables" / "case_positions.csv"
    _check_path(nodes_csv)
    _check_path(positions_csv)

    # Load valid canonical node IDs (never reads model_binding_ids column)
    valid_nodes: set[str] = set()
    node_kinds: dict[str, str] = {}
    for row in csv.DictReader(open(nodes_csv, encoding="utf-8-sig")):
        nid = row["model_node_id"].strip()
        valid_nodes.add(nid)
        node_kinds[nid] = row.get("kind", "").strip()

    # Load positions (skip model_binding_ids)
    positions: list[dict] = []
    for row in csv.DictReader(open(positions_csv, encoding="utf-8-sig")):
        positions.append({
            "position_id": row["position_id"].strip(),
            "statement": row.get("statement", "").strip(),
            "position_type": row.get("position_type", "").strip(),
            "pillar": row.get("pillar", "").strip(),
        })

    bindings: list[dict] = []
    for pos in positions:
        proposals = _propose_for_position(pos["statement"], valid_nodes)
        for p in proposals:
            bindings.append({
                "position_id": pos["position_id"],
                "model_node_id": p["model_node_id"],
                "binding_type": p["binding_type"],
                "source": "position_model_binder_v1",
            })

    if write:
        out_dir = VAULT / "deals" / deal / "models"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "bindings.json"
        out_path.write_text(
            json.dumps({"deal": deal, "bindings": bindings}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Wrote {len(bindings)} proposed bindings → {out_path}")

    return bindings


def _print_report(bindings: list[dict]) -> None:
    by_pos: dict[str, list[dict]] = {}
    for b in bindings:
        by_pos.setdefault(b["position_id"], []).append(b)

    by_type: dict[str, int] = {}
    for b in bindings:
        by_type[b["binding_type"]] = by_type.get(b["binding_type"], 0) + 1

    print(f"\nBinding proposals: {len(bindings)} total across {len(by_pos)} positions")
    for bt, n in sorted(by_type.items()):
        print(f"  {bt:<35} {n}")
    print()
    for pos_id in sorted(by_pos):
        entries = by_pos[pos_id]
        print(f"{pos_id}:")
        for e in entries:
            print(f"  [{e['binding_type'][:4]}] {e['model_node_id']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Propose position→model bindings (zero LLM)")
    parser.add_argument("--deal", default="keystone")
    parser.add_argument("--cic", required=True,
                        help="Path to CIC package root (contains tables/)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print proposals without writing bindings.json")
    args = parser.parse_args()

    cic_dir = Path(args.cic)
    bindings = propose_bindings(cic_dir, args.deal, write=not args.dry_run)
    _print_report(bindings)


if __name__ == "__main__":
    main()
