#!/usr/bin/env python3
"""
live_store — what the extractor has actually produced, and nothing else.

The projection served to the UI was assembled from three places at once: a
bundle built earlier on disk, the vault, and the V17 package fixture. That made
"is this real?" a question you had to answer per section by reading a provenance
map.

This removes the question. Ingest writes here; the projection reads only here.
A section that no ingest produced is absent — not borrowed, not zero-filled.

Why a store and not a rebuild of Current
----------------------------------------
Writing extraction output straight into the Current Live Case would skip the
admission it exists to enforce: a source becomes an admitted fact only through
a proposed event and a human act. So this is a staging area. It holds what was
extracted, it is safe to discard, and nothing here is Current until it passes
through admission.

Layout
------
    pipeline_out/live/<deal>/
        manifest.json      what was ingested, when, and its digest
        claims.json        accumulated claims, keyed by claim_id
        model.json         model nodes and bindings from workbooks
        grounding.json     the review queue for the accumulated claims
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "pipeline_out" / "live"


def store_dir(deal: str) -> Path:
    return LIVE / deal


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8")


class LiveStore:
    def __init__(self, deal: str = "keystone"):
        self.deal = deal
        self.dir = store_dir(deal)
        self.manifest = _load(self.dir / "manifest.json",
                              {"deal": deal, "sources": []})
        self.claims = _load(self.dir / "claims.json", [])
        self.model = _load(self.dir / "model.json",
                           {"model_nodes": [], "bindings": [], "records": [],
                            "cells": 0})
        self.grounding = _load(self.dir / "grounding.json", {})

    # ── state ────────────────────────────────────────────────────────────────

    @property
    def is_empty(self) -> bool:
        return not self.manifest["sources"]

    def reset(self) -> None:
        """Start from nothing. The point of ingesting from zero is to see zero."""
        self.manifest = {"deal": self.deal, "sources": []}
        self.claims = []
        self.model = {"model_nodes": [], "bindings": [], "records": [], "cells": 0}
        self.grounding = {}
        self.save()

    def save(self) -> None:
        _save(self.dir / "manifest.json", self.manifest)
        _save(self.dir / "claims.json", self.claims)
        _save(self.dir / "model.json", self.model)
        _save(self.dir / "grounding.json", self.grounding)

    # ── ingestion ────────────────────────────────────────────────────────────

    def add_document(self, source: Path, result: dict) -> dict:
        """Merge claims from one document. Existing claim_ids are not duplicated."""
        seen = {c.get("claim_id") for c in self.claims}
        new = [c for c in result.get("claims", [])
               if c.get("claim_id") and c["claim_id"] not in seen]
        self.claims.extend(new)

        g = result.get("grounding") or {}
        if g.get("review_queue") is not None:
            existing = self.grounding.get("review_queue", [])
            keys = {(f.get("claim_id"), f.get("code")) for f in existing}
            existing.extend(f for f in g["review_queue"]
                            if (f.get("claim_id"), f.get("code")) not in keys)
            self.grounding = {**{k: v for k, v in g.items() if k != "review_queue"},
                              "review_queue": existing}

        entry = self._record(source, "document", {
            "claims_extracted": len(result.get("claims", [])),
            "claims_new": len(new),
            "pipeline": result.get("pipeline", {}),
        })
        self.save()
        return entry

    def add_workbook(self, source: Path, result: dict) -> dict:
        """Merge the model side from one workbook."""
        bindings = result.get("bindings", [])
        known = {(b["concept_id"], b["locator"]) for b in self.model["bindings"]}
        self.model["bindings"].extend(
            b for b in bindings if (b["concept_id"], b["locator"]) not in known)
        # Records are keyed by what they are a record of, so a second workbook
        # naming the same case replaces it rather than showing the case twice.
        recs = {r["record"]: r for r in self.model.get("records", [])}
        for r in result.get("records", []):
            recs[r["record"]] = r
        self.model["records"] = list(recs.values())
        self.model["cells"] = (result.get("L1_source_graph") or {}).get("cells", 0)
        self.model["sheet_kinds"] = (result.get("L2_semantics") or {}).get("sheet_kinds", {})
        self.model["resolution"] = result.get("L3_resolution", {})

        entry = self._record(source, "workbook", {
            "cells": self.model["cells"],
            "bindings_admitted": len(bindings),
            "records_extracted": len(result.get("records", [])),
            "L2": result.get("L2_semantics", {}),
            "L3": result.get("L3_resolution", {}),
        })
        self.save()
        return entry

    def attach_model_nodes(self, nodes: list[dict]) -> None:
        """
        Model nodes with computed values, from the execution graph.

        Kept separate from bindings because a binding says which cell carries a
        concept, while a node carries the value that came out of the formula.
        """
        self.model["model_nodes"] = nodes
        self.save()

    def _record(self, source: Path, kind: str, detail: dict) -> dict:
        raw = source.read_bytes()
        entry = {
            "source": source.name,
            "path": str(source),
            "kind": kind,
            "digest": "sha256:" + hashlib.sha256(raw).hexdigest()[:16],
            "size_bytes": len(raw),
            "ingested_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            **detail,
        }
        self.manifest["sources"] = [
            s for s in self.manifest["sources"] if s["path"] != entry["path"]
        ] + [entry]
        return entry

    # ── reporting ────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        gq = (self.grounding or {}).get("review_queue", [])
        return {
            "deal": self.deal,
            "sources": len(self.manifest["sources"]),
            "documents": sum(1 for s in self.manifest["sources"] if s["kind"] == "document"),
            "workbooks": sum(1 for s in self.manifest["sources"] if s["kind"] == "workbook"),
            "claims": len(self.claims),
            "model_nodes": len(self.model.get("model_nodes", [])),
            "bindings": len(self.model.get("bindings", [])),
            "records": len(self.model.get("records", [])),
            "cells": self.model.get("cells", 0),
            "grounding_findings": len(gq),
            "grounding_blocking": sum(1 for f in gq if f.get("blocking")),
        }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Inspect or reset the live store")
    ap.add_argument("--deal", default="keystone")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()

    st = LiveStore(a.deal)
    if a.reset:
        st.reset()
        print(f"[live_store] {a.deal}: azzerato")
        return 0

    s = st.summary()
    print(f"[live_store] {st.dir}")
    if st.is_empty:
        print("  vuoto: nessuna sorgente ingerita")
        return 0
    for k, v in s.items():
        print(f"  {k:20} {v}")
    print("\n  sorgenti:")
    for src in st.manifest["sources"]:
        print(f"    {src['kind']:9} {src['source'][:44]:46} {src['ingested_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
