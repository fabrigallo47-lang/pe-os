#!/usr/bin/env python3
"""
make_event — regenerate the canonical correction event against a built bundle.

Two reasons this cannot be a static file:

1. Stable claim ids are content hashes. Re-extract and every id changes, so a
   hand-written trigger_claim_ids goes stale — ours pointed at
   ks-41c79954bd44, a legacy-extractor id absent from the v2 extraction, which
   is what TRIGGER_ADMISSION reported.

2. PANTA rejects a claim_correction whose mutations touch derived objects.
   EVENT_MUTATION_SCOPE: "mutare il CLAIM trigger; lasciare POSITION e
   MODEL_NODE alla propagazione." The old event corrected CP-EBITDA-FIRM.value
   and two MODEL_NODE initial_values directly — the graph never had to
   propagate anything, so the settlement was real but the reasoning was not.

So the event is derived from the bundle: find the claim that carries the
position's value, and correct that one claim.

  python3 tools/make_event.py --bundle DIR --position CP-EBITDA-FIRM --to 12.2
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def pick_trigger_claim(current: dict, position_id: str, from_value: float) -> dict | None:
    """The claim a correction should target: the position's own evidence.

    Prefer attested over derived over asserted — correcting the claim the IC
    actually relied on, not a restatement of it.
    """
    positions = {p.get("position_id"): p for p in current.get("case_positions", [])}
    cp = positions.get(position_id)
    if not cp:
        return None
    claims = {c.get("claim_id"): c for c in current.get("claims", [])}
    rank = {"attested": 0, "observed": 1, "derived": 2, "asserted": 3}
    candidates = []
    for route in cp.get("support_routes", []):
        c = claims.get(route.get("claim_stable_id"))
        if not c:
            continue
        try:
            if abs(float(c.get("value")) - from_value) > 1e-9:
                continue
        except (TypeError, ValueError):
            continue
        candidates.append(c)
    if not candidates:
        return None
    candidates.sort(key=lambda c: rank.get(c.get("epistemic_class", "asserted"), 9))
    return candidates[0]


def build_event(bundle: Path, position_id: str, to_value: float,
                event_id: str = "EV-KS-EBITDA-001") -> dict:
    current = json.loads((bundle / "current_graph.json").read_text(encoding="utf-8"))
    positions = {p.get("position_id"): p for p in current.get("case_positions", [])}
    cp = positions.get(position_id)
    if not cp:
        raise ValueError(f"posizione {position_id} assente dal Current")
    from_value = float(cp.get("value"))

    claim = pick_trigger_claim(current, position_id, from_value)
    if claim is None:
        raise ValueError(f"nessun claim con valore {from_value} sostiene {position_id}")

    claim_id = claim.get("claim_id")
    # The claim carries the raw unit ($m); the position carries the institutional
    # one ($m/year). A mutation is matched against the object it targets, so use
    # the claim's own semantics here.
    return {
        "event_id": event_id,
        # 'event' is the required envelope label in the PANTA event schema —
        # a human-readable classification, not a structure.
        "event": ("CLAIM_CORRECTION:INPUT_REVISION — Firm underwritten EBITDA "
                  "revised upward at IC gate"),
        "event_type": "claim_correction",
        "event_status": "SYNTHETIC_TEST_EVENT",
        "deal": current.get("case_id", ""),
        "company": current.get("company", ""),
        "effective_date": "2026-03-10",
        "known_at": "2026-03-10T00:00:00Z",
        "source": "IC Memo 2026-03-10",
        "author": "IC",
        "authority_required": "IC_MEMO",
        "note": (
            f"IC Memo 2026-03-10: firm underwritten EBITDA corrected from "
            f"${from_value}m to ${to_value}m (QoE v2 conclusion and covenant "
            f"add-backs). Only the claim is corrected; {position_id} and the "
            f"model nodes follow by propagation."
        ),
        "source_ids": [claim.get("source_id", "")],
        "trigger_claim_ids": [claim_id],
        # Convenience mirrors of the mutation, read by tools/bridge_v7.apply_event.
        # The mutation list stays the authority; these must agree with it.
        "metric": (claim.get("metric") or "").lower().strip(),
        "from_value": from_value,
        "to_value": to_value,
        "unit": claim.get("unit", ""),
        "period": claim.get("period_iso") or claim.get("period"),
        "perimeter": claim.get("perimeter", ""),
        "mutations": [
            {
                "operation": "CORRECT",
                "object_type": "CLAIM",
                "object_id": claim_id,
                "field": "value",
                "from": from_value,
                "to": to_value,
                "unit": claim.get("unit", ""),
                "definition_id": claim.get("definition_id"),
                "period": claim.get("period_iso") or claim.get("period"),
                "perimeter": claim.get("perimeter", ""),
            }
        ],
        "propagation_expected": {
            "chain": [
                f"CLAIM {claim_id}: {from_value} → {to_value}",
                f"→ {position_id} (support route re-evaluated)",
                "→ bound model nodes recomputed by the execution mapping",
            ]
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate the correction event")
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--position", default="CP-EBITDA-FIRM")
    ap.add_argument("--to", type=float, required=True)
    ap.add_argument("--event-id", default="EV-KS-EBITDA-001")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    event = build_event(a.bundle, a.position, a.to, a.event_id)
    out = a.out or (a.bundle / "event_ebitda_correction.json")
    out.write_text(json.dumps(event, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    m = event["mutations"][0]
    print(f"[make_event] {event['event_id']} → {out}")
    print(f"   trigger CLAIM {m['object_id']}  {m['from']} → {m['to']} {m['unit']}")
    print(f"   mutazioni: {len(event['mutations'])} (solo CLAIM)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
