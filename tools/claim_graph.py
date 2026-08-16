#!/usr/bin/env python3
"""Convert extracted claims to a typed graph (nodes + edges).

Graph schema
------------
Node types:
  subject  — unique subject string (the "entity" being claimed about)
  claim    — individual extracted claim (epistemic, value, period, perimeter …)
  question — question ID from a bears-on link

Edge types:
  HAS_CLAIM   subject → claim
  BEARS_ON    claim   → question
  CONTRADICTS claim   → claim  (same subject, opposing directions)
"""
from __future__ import annotations


def claims_to_graph(claims: list[dict], source_name: str = "") -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def upsert(nid: str, **kw) -> None:
        if nid not in nodes:
            nodes[nid] = {"id": nid, **kw}

    # Build subject + claim nodes
    for i, c in enumerate(claims):
        subject = (c.get("subject") or "").strip()
        if not subject:
            continue

        s_id = f"subj:{subject}"
        upsert(s_id, type="subject", label=subject)

        c_id = f"claim:{i:03d}"
        label = subject
        if c.get("value"):
            label = f"{subject} = {c['value']}"
        upsert(c_id,
               type="claim",
               label=label,
               metric=c.get("metric", ""),
               unit=c.get("unit", ""),
               as_of=c.get("as_of", ""),
               topic=c.get("topic", ""),
               source_doc=c.get("source_doc", source_name),
               epistemic=c.get("epistemic", "asserted"),
               value=c.get("value", ""),
               period=c.get("period", ""),
               perimeter=c.get("perimeter", ""),
               direction=c.get("direction", "context"),
               locator=c.get("locator", ""),
               author=c.get("author", ""),
               statement=c.get("statement", ""),
               derivation=c.get("derivation"))

        edges.append({"source": s_id, "target": c_id, "rel": "HAS_CLAIM"})

        for q in (c.get("bears_on") or []):
            q = (q or "").strip()
            if not q:
                continue
            q_id = f"q:{q}"
            upsert(q_id, type="question", label=q)
            edges.append({"source": c_id, "target": q_id, "rel": "BEARS_ON"})

    # Contradiction edges: same subject, opposing directions
    by_subject: dict[str, list[tuple[str, str]]] = {}
    for nid, n in nodes.items():
        if n["type"] != "claim":
            continue
        # recover subject id from the HAS_CLAIM edges
        for e in edges:
            if e["rel"] == "HAS_CLAIM" and e["target"] == nid:
                by_subject.setdefault(e["source"], []).append((nid, n.get("direction", "context")))
                break

    for _s_id, claim_list in by_subject.items():
        supports   = [cid for cid, d in claim_list if d == "supports"]
        contradicts = [cid for cid, d in claim_list if d == "contradicts"]
        for s_cid in supports:
            for c_cid in contradicts:
                edges.append({"source": s_cid, "target": c_cid, "rel": "CONTRADICTS"})

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "stats": {
            "subjects":  sum(1 for n in nodes.values() if n["type"] == "subject"),
            "claims":    sum(1 for n in nodes.values() if n["type"] == "claim"),
            "questions": sum(1 for n in nodes.values() if n["type"] == "question"),
            "edges":     len(edges),
        },
    }
