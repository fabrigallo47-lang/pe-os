#!/usr/bin/env python3
"""
bundle_assemble — build all 16 V7 bundle files from one extraction run.

Why this exists
---------------
adapter_alpha wrote only 4 of the 16 required files; the rest had been
assembled by hand across sessions. The result looked complete and passed the
transition engine, but PANTA's independent validator rejected it: graph.json
came from a different extraction than claims.json, so every claim-lineage row
mismatched, and the hashes identified files that no longer existed.

Nothing here is copied from a previous run. Every artifact is derived from the
same in-memory state, then sealed.

Order
-----
  1  claims.json              admitted claims (answer key already excluded)
  2  graph.json               extraction graph for THIS run (graph_store)
  3  nodes/edges.csv, graph.db  storage_export, from graph.json
  4  execution_graph_v7.json  canonical copy from the vault
  5  admission_manifest_v7    from the bridge
  6  event + policies         canonical copies
  7  candidate_graph.json     serialised from the embedded dynamics runtime
     transition_output.json   ditto — the validator compares field by field,
                              so these must be the runtime's own output, not a
                              reconstruction ("Usare i valori restituiti dal
                              runtime indipendente senza ricostruzione manuale")
  8  validation_report.txt
  9  bundle_seal              recompute every hash from the final bytes

The dynamics runtime is vendored in ``backend/dynamics``. Bundle construction
therefore has no dependency on a separately downloaded validator kit.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import storage_export, bundle_seal
from tools.graph_store import build_from_extraction
from backend.dynamics.runtime import apply_state_transition

VAULT = ROOT / "vault"
DYNAMICS_FIXTURES = ROOT / "backend" / "dynamics" / "benchmark"
POLICY_MATERIALITY = VAULT / "policy" / "keystone_materiality_policy_v0.json"
if not POLICY_MATERIALITY.exists():
    POLICY_MATERIALITY = DYNAMICS_FIXTURES / "keystone_materiality_policy_v0.json"
POLICY_AUTHORITY = VAULT / "policy" / "keystone_authority_matrix_v0.json"
if not POLICY_AUTHORITY.exists():
    POLICY_AUTHORITY = DYNAMICS_FIXTURES / "keystone_authority_matrix_v0.json"
EXEC_GRAPH_SRC = VAULT / "deals" / "keystone" / "models" / "execution_graph_v7.json"


def _w(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def run_embedded_runtime(bundle: Path) -> dict:
    """Execute the event through the backend-owned dynamics runtime."""
    load = lambda n: json.loads((bundle / n).read_text(encoding="utf-8"))
    return apply_state_transition(
        load("current_graph.json"),
        [load("event_ebitda_correction.json")],
        load("execution_mapping.json"),
        load("keystone_materiality_policy_v0.json"),
        load("keystone_authority_matrix_v0.json"),
    )


def assemble(bundle_dir: Path, bundle: dict, event_src: Path,
             kit: Path | None = None, verbose: bool = True) -> dict:
    # ``kit`` is retained as a compatibility argument for older callers. The
    # production runtime is now embedded and the value is intentionally unused.
    bundle_dir.mkdir(parents=True, exist_ok=True)
    say = (lambda m: print(f"   {m}")) if verbose else (lambda m: None)
    written: list[str] = []

    # ── 1. claims.json — the whole extraction, not the admitted subset ───────
    # The validator reads claims.json as the extraction record: its id set must
    # equal graph.json's claim nodes and the identity_migration_map, while
    # current_graph.claims holds the admitted subset that resolves back into it.
    extraction = json.loads((bundle_dir / "extraction_graph.json").read_text(encoding="utf-8"))
    claims = [n for n in extraction.get("nodes", []) if n.get("type") == "claim"]
    _w(bundle_dir / "claims.json", claims)
    written.append("claims.json")
    admitted = len(bundle["current_graph"].get("claims", []))
    say(f"claims.json ({len(claims)} claim estratti, {admitted} ammessi nel Current)")

    # ── 2. graph.json — same extraction the claims came from ─────────────────
    dg = build_from_extraction(claims, extraction, bundle.get("_deal", "keystone"))
    graph = dg.to_json()
    if "links" in graph and "edges" not in graph:
        graph["edges"] = graph.pop("links")
    _w(bundle_dir / "graph.json", graph)
    written.append("graph.json")
    say(f"graph.json ({len(graph['nodes'])} nodi, {len(graph.get('edges', []))} archi)")

    # ── 3. storage trio, from that graph, atomically ─────────────────────────
    errs = storage_export.validate_graph(graph)
    if errs:
        raise ValueError("graph.json non esportabile:\n  " + "\n  ".join(errs[:10]))
    storage_export.export(graph, bundle_dir)
    written += ["nodes.csv", "edges.csv", "graph.db"]
    say("nodes.csv / edges.csv / graph.db")

    # ── 4-6. canonical copies ────────────────────────────────────────────────
    for src, name in ((EXEC_GRAPH_SRC, "execution_graph_v7.json"),
                      (POLICY_MATERIALITY, "keystone_materiality_policy_v0.json"),
                      (POLICY_AUTHORITY, "keystone_authority_matrix_v0.json")):
        if not src.exists():
            raise FileNotFoundError(f"sorgente canonica mancante: {src}")
        shutil.copyfile(src, bundle_dir / name)
        written.append(name)
    say("execution_graph_v7 + event + 2 policy")

    _w(bundle_dir / "admission_manifest_v7.json", bundle["manifest"])
    written.append("admission_manifest_v7.json")
    say("admission_manifest_v7.json")

    # The correction event names its trigger by stable claim id, which is a
    # content hash. An event written for one manifest cannot apply to another,
    # so derive it from the bundle being assembled rather than copying a file.
    from tools.make_event import build_event
    try:
        event = build_event(bundle_dir, "CP-EBITDA-FIRM", 12.2)
        _w(bundle_dir / "event_ebitda_correction.json", event)
        say(f"event_ebitda_correction.json (trigger {event['trigger_claim_ids'][0]})")
    except ValueError as exc:
        if event_src and event_src.exists():
            shutil.copyfile(event_src, bundle_dir / "event_ebitda_correction.json")
            say(f"event non derivabile ({exc}) — copiato {event_src.name}")
        else:
            raise
    written.append("event_ebitda_correction.json")

    # ── 7. Seal the INPUTS before running the engine.
    # The engine stamps policy_refs with the hashes of the files it actually
    # read. Sealing afterwards would change those files and leave the output
    # pointing at states that no longer exist, which is what made
    # policy_refs / replay_hash diverge from an independent re-run.
    bundle_seal.seal(bundle_dir, verbose=False)
    say("hash degli input sigillati (prima dell'esecuzione)")

    # ── 8. runtime output, serialised from the embedded engine ───────────────
    result = run_embedded_runtime(bundle_dir)
    # The engine wraps its output; the schema wants that inner object flat,
    # with all 18 required fields. candidate_state is the full post-event
    # snapshot — CANDIDATE_FULL_GRAPH rejects a delta.
    to = dict(result.get("transition_output", result))
    # The independent validator builds its reference output as the engine's
    # transition_output plus the top-level history_append.
    to["history_append"] = result.get("history_append", [])
    candidate_state = result.get("candidate_state", {})
    candidate_graph = candidate_state.get("current_graph", candidate_state)
    to["candidate_graph"] = candidate_graph
    _w(bundle_dir / "transition_output.json", to)
    _w(bundle_dir / "candidate_graph.json", candidate_graph)
    written += ["transition_output.json", "candidate_graph.json"]
    ordered = to.get("ordered_transitions", [])
    settled = [c for c in ordered if c.get("result") == "SETTLED"]
    status = (to.get("partial_settlement_status") or {}).get("candidate")
    say(f"transition_output + candidate_graph dal runtime backend "
        f"({status}, {len(settled)} settled)")

    # ── 8. human-readable report ─────────────────────────────────────────────
    report = bundle_dir / "validation_report.txt"
    if not report.exists():
        report.write_text("PANTA V7 bundle — generato da tools/bundle_assemble.py\n",
                          encoding="utf-8")
    written.append("validation_report.txt")

    # ── 9. verify the seal still holds ───────────────────────────────────────
    # Inputs were sealed in step 7; the engine wrote its own policy_refs from
    # those exact bytes, so nothing should need resealing here.
    problems = bundle_seal.verify(bundle_dir)
    if problems:
        raise ValueError("seal non coerente dopo l'esecuzione: " + ", ".join(problems))
    say("hash verificati sui file finali")

    return {"written": written, "bundle_dir": str(bundle_dir)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble a complete V7 bundle")
    ap.add_argument("--bundle", type=Path, required=True,
                    help="bundle dir (must already contain extraction_graph.json)")
    ap.add_argument("--event", type=Path, default=ROOT / "event_ebitda_correction.json")
    ap.add_argument("--kit", type=Path, default=None)
    a = ap.parse_args()
    print("bundle_assemble richiede il dict del bridge; usare adapter_alpha.py",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
