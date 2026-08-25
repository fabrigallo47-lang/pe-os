#!/usr/bin/env python3
"""
bundle_seal — recompute every provenance hash from the artifacts as written.

The bridge computes hashes while it builds, but several artifacts are still
mutated after that point (storage export, policy copies, transition output).
The declared hashes then identify intermediate states that no longer exist on
disk, and PANTA's validator reports MANIFEST_HASHES / EXECUTION_PROVENANCE /
MAPPING_HASH_PROVENANCE. Its remediation note is literal: "Ricalcolare gli
SHA-256 dopo la scrittura finale degli artefatti."

So sealing is a separate, final pass: read the files exactly as they sit in
the bundle, recompute, write back.

Accepted hash forms
-------------------
The validator accepts either for a given file:
    sha256_file(path)          raw bytes
    canonical_hash(payload)    sha256 of json.dumps(sort_keys, separators)
We always write the raw-bytes form, except where a field is compared only
against sha256_file (admission manifest), which is the same value anyway.

Ordering matters
----------------
Hashes form a DAG — sealing a file changes its own hash, so anything that
declares it must be sealed afterwards:

    graph.json ─────────────┐
    execution_graph_v7.json ┤ (declares graph.json)
    admission_manifest_v7   ┤ (declares graph.json + execution_graph)
    current_graph.json      ┤ (refs only, no hashes)
    execution_mapping.json  ┤ (declares all four above)
    transition_output.json  ┘ (declares execution_mapping)

Usage
-----
  python3 tools/bundle_seal.py --bundle pipeline_out/e3/K-IC/adapter_alpha
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

GRAPH = "graph.json"
EXEC_GRAPH = "execution_graph_v7.json"
MANIFEST = "admission_manifest_v7.json"
CURRENT = "current_graph.json"
MAPPING = "execution_mapping.json"
OUTPUT = "transition_output.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _set(obj: dict, path: list[str], value: str) -> bool:
    """Set a nested key only if the parent mapping already exists."""
    cur = obj
    for key in path[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            return False
        cur = nxt
    cur[path[-1]] = value
    return True


def seal(bundle: Path, verbose: bool = True) -> list[str]:
    changed: list[str] = []

    def note(msg: str) -> None:
        changed.append(msg)
        if verbose:
            print(f"   {msg}")

    # ── 1. execution_graph_v7 declares graph.json ────────────────────────────
    graph_hash = sha256_file(bundle / GRAPH)
    eg_path = bundle / EXEC_GRAPH
    eg = load(eg_path)
    am = eg.get("admission_manifest")
    if isinstance(am, dict) and am.get("extraction_hash"):
        if str(am["extraction_hash"]).removeprefix("sha256:") != graph_hash:
            am["extraction_hash"] = f"sha256:{graph_hash}"
            dump(eg_path, eg)
            note(f"{EXEC_GRAPH}: admission_manifest.extraction_hash")

    # ── 2. admission manifest declares graph + execution graph ───────────────
    exec_graph_hash = sha256_file(bundle / EXEC_GRAPH)
    mf_path = bundle / MANIFEST
    mf = load(mf_path)
    dirty = False
    for field, value in (("source_graph_hash", graph_hash),
                         ("execution_graph_hash", exec_graph_hash)):
        if str(mf.get(field, "")).removeprefix("sha256:") != value:
            # this field is compared against the raw digest without a prefix
            mf[field] = value
            dirty = True
            note(f"{MANIFEST}: {field}")
    if dirty:
        dump(mf_path, mf)

    # ── 3. current_graph refs must be plain basenames ────────────────────────
    cur_path = bundle / CURRENT
    cur = load(cur_path)
    dirty = False
    for field, expected in (("extraction_ref", GRAPH), ("execution_ref", EXEC_GRAPH)):
        if Path(str(cur.get(field, ""))).name != expected:
            cur[field] = expected
            dirty = True
            note(f"{CURRENT}: {field} → {expected}")
    if dirty:
        dump(cur_path, cur)

    # ── 4. execution_mapping declares the four above ─────────────────────────
    manifest_hash = sha256_file(bundle / MANIFEST)
    current_hash = sha256_file(bundle / CURRENT)
    map_path = bundle / MAPPING
    mapping = load(map_path)
    dirty = False
    for field, value in (("extraction_hash", graph_hash),
                         ("execution_graph_hash", exec_graph_hash),
                         ("canonical_current_hash", current_hash),
                         ("admission_manifest_hash", manifest_hash)):
        prov = mapping.setdefault("provenance", {})
        if str(prov.get(field, "")).removeprefix("sha256:") != value:
            prov[field] = f"sha256:{value}"
            dirty = True
            note(f"{MAPPING}: provenance.{field}")
    if str(mapping.get("canonical_graph_hash", "")).removeprefix("sha256:") != current_hash:
        mapping["canonical_graph_hash"] = f"sha256:{current_hash}"
        dirty = True
        note(f"{MAPPING}: canonical_graph_hash")
    if dirty:
        dump(map_path, mapping)

    # ── 5. transition_output declares execution_mapping ──────────────────────
    mapping_hash = sha256_file(bundle / MAPPING)
    out_path = bundle / OUTPUT
    if out_path.exists():
        out = load(out_path)
        # policy_refs may sit at top level or inside transition_output
        targets = [out]
        if isinstance(out.get("transition_output"), dict):
            targets.append(out["transition_output"])
        dirty = False
        for target in targets:
            refs = target.get("policy_refs")
            if not isinstance(refs, dict):
                continue
            if str(refs.get("execution_mapping_hash", "")).removeprefix("sha256:") != mapping_hash:
                refs["execution_mapping_hash"] = f"sha256:{mapping_hash}"
                dirty = True
                note(f"{OUTPUT}: policy_refs.execution_mapping_hash")
        if dirty:
            dump(out_path, out)

    return changed


def verify(bundle: Path) -> list[str]:
    """Re-read and confirm every sealed hash identifies the file on disk."""
    problems: list[str] = []
    gh = sha256_file(bundle / GRAPH)
    eh = sha256_file(bundle / EXEC_GRAPH)
    mh = sha256_file(bundle / MANIFEST)
    ch = sha256_file(bundle / CURRENT)
    mph = sha256_file(bundle / MAPPING)

    mf = load(bundle / MANIFEST)
    if str(mf.get("source_graph_hash", "")).removeprefix("sha256:") != gh:
        problems.append("manifest.source_graph_hash")
    if str(mf.get("execution_graph_hash", "")).removeprefix("sha256:") != eh:
        problems.append("manifest.execution_graph_hash")

    mapping = load(bundle / MAPPING)
    prov = mapping.get("provenance", {})
    for field, want in (("extraction_hash", gh), ("execution_graph_hash", eh),
                        ("canonical_current_hash", ch), ("admission_manifest_hash", mh)):
        if str(prov.get(field, "")).removeprefix("sha256:") != want:
            problems.append(f"mapping.provenance.{field}")
    if str(mapping.get("canonical_graph_hash", "")).removeprefix("sha256:") != ch:
        problems.append("mapping.canonical_graph_hash")

    eg = load(bundle / EXEC_GRAPH)
    am = eg.get("admission_manifest")
    if isinstance(am, dict) and am.get("extraction_hash"):
        if str(am["extraction_hash"]).removeprefix("sha256:") != gh:
            problems.append("execution_graph.admission_manifest.extraction_hash")

    if (bundle / OUTPUT).exists():
        out = load(bundle / OUTPUT)
        for target in [out, out.get("transition_output", {})]:
            refs = target.get("policy_refs") if isinstance(target, dict) else None
            if isinstance(refs, dict) and "execution_mapping_hash" in refs:
                if str(refs["execution_mapping_hash"]).removeprefix("sha256:") != mph:
                    problems.append("output.policy_refs.execution_mapping_hash")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Seal bundle provenance hashes")
    ap.add_argument("--bundle", type=Path, required=True)
    a = ap.parse_args()

    print(f"[bundle_seal] {a.bundle}")
    changed = seal(a.bundle)
    if not changed:
        print("   (nessun hash da aggiornare)")
    problems = verify(a.bundle)
    if problems:
        print("[bundle_seal] VERIFICA FALLITA:")
        for p in problems:
            print("   -", p)
        return 1
    print("[bundle_seal] tutti gli hash identificano i file finali")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
