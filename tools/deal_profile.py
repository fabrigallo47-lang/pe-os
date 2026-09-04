#!/usr/bin/env python3
"""
Deal profile — per-deal institutional semantics for the V7 bridge.

Why this exists
---------------
A Case Position's *semantic identity* is its (perimeter, unit, period) triple.
PANTA's transition engine admits a mutation only when the event's triple matches
the object's exactly, so these values are a contract with the event layer — not
descriptive metadata.

They cannot be read reliably off the raw claims: the extractor may emit
'unknown', or disagree with itself across the claims backing one position
(Keystone's CP-EBITDA-FIRM is supported by claims labelled 'unknown',
'Keystone standalone' and 'Riverton Group'). So they are declared per deal.

The invariant that matters
--------------------------
A deal WITHOUT a profile never gets a borrowed perimeter. Earlier the bridge
defaulted to the literal "Alderstone standalone", which meant any second deal
would have had Alderstone's economic scope stamped onto its positions — a
wrong perimeter that reads as authoritative. Silence is recoverable; a
confident wrong answer is not.

Unmapped objects therefore get perimeter "" and a recorded warning. The engine
reports NON_APPLICABLE_PERIMETER and nothing settles — loudly, in the adapter
report, rather than passing with false semantics.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "vault"


class DealProfile:
    """Institutional semantics for one deal. Absent entries are absent, never guessed."""

    def __init__(self, deal: str, data: dict | None = None):
        self.deal = deal
        d = data or {}
        self.entity: str = d.get("entity", "")
        self.case_id: str = d.get("case_id", f"CASE-{deal.upper()}")
        self.state_id: str = d.get("state_id", f"{deal.upper()}-CURRENT-V7-001")
        self.claim_id_prefix: str = d.get("claim_id_prefix", "c")
        self.default_perimeter: str = d.get("default_perimeter", "")
        self.entity_aliases: list[str] = d.get("entity_aliases", [])
        self.perimeter_vocabulary: list[str] = d.get("perimeter_vocabulary", [])
        # entity name -> why it is a counterparty (never an economic perimeter)
        self.counterparty_entities: dict[str, str] = d.get("counterparty_entities", {})
        self.underwriting_cutoff: str = d.get("underwriting_cutoff", "")
        # Which module actually computes this deal's model, and its entrypoint.
        # Absent means "the caller's own default" — the hardcoded Keystone
        # module today — so an existing deal behaves exactly as before and only
        # a profile that names one is routed anywhere else. A deal whose model
        # is not Keystone's workbook has no business running Keystone's Python.
        self.runtime_module: str = d.get("runtime_module", "")
        self.runtime_entrypoint: str = d.get("runtime_entrypoint", "")
        self.cp_institutional: dict[str, dict] = d.get("cp_institutional", {})
        self.mn_unit_canonical: dict[str, str] = d.get("mn_unit_canonical", {})
        self.mn_period_override: dict[str, str] = d.get("mn_period_override", {})
        self.mn_quarterly_derive: dict[str, tuple[str, int]] = {
            k: (v[0], int(v[1]))
            for k, v in d.get("mn_quarterly_derive", {}).items()
            if isinstance(v, (list, tuple)) and len(v) == 2
        }
        self.loaded: bool = bool(d)
        # (object_id, field) pairs the profile could not supply
        self.warnings: list[str] = []

    # ── perimeter/unit resolution ────────────────────────────────────────────

    def cp_perimeter(self, cp_id: str, claim_perimeter: str | None) -> str:
        """Perimeter for a Case Position. Never invents one for an unknown deal."""
        inst = self.cp_institutional.get(cp_id, {})
        if inst.get("perimeter"):
            return inst["perimeter"]
        # A claim-supplied perimeter is weaker but still this deal's own data.
        if claim_perimeter and claim_perimeter.strip().lower() != "unknown":
            return claim_perimeter
        if self.default_perimeter:
            return self.default_perimeter
        self._warn(cp_id, "perimeter")
        return ""

    def cp_unit(self, cp_id: str, claim_unit: str | None) -> str:
        inst = self.cp_institutional.get(cp_id, {})
        if inst.get("unit") is not None:
            return inst["unit"]
        return claim_unit or ""

    def mn_perimeter(self, mn_id: str, raw_perimeter: str | None) -> str:
        if raw_perimeter:
            return raw_perimeter.replace("_", " ")
        if self.default_perimeter:
            return self.default_perimeter
        self._warn(mn_id, "perimeter")
        return ""

    def mn_unit(self, mn_id: str, raw_unit: str | None) -> str:
        return self.mn_unit_canonical.get(mn_id) or raw_unit or ""

    def claim_perimeter(self, claim_perimeter: str | None) -> str:
        """Perimeter for a schema-normalised claim record."""
        if claim_perimeter:
            return claim_perimeter
        if self.default_perimeter:
            return self.default_perimeter
        return "unknown"

    def _warn(self, object_id: str, field: str) -> None:
        msg = f"{object_id}: no {field} in deal profile '{self.deal}' — left empty"
        if msg not in self.warnings:
            self.warnings.append(msg)

    # ── reporting ────────────────────────────────────────────────────────────

    def conformance_report(self) -> dict:
        return {
            "deal": self.deal,
            "profile_loaded": self.loaded,
            "entity": self.entity,
            "positions_mapped": len(self.cp_institutional),
            "model_nodes_mapped": len(self.mn_unit_canonical),
            "unmapped_warnings": list(self.warnings),
            "status": "OK" if self.loaded and not self.warnings else (
                "NO_PROFILE" if not self.loaded else "PARTIAL"
            ),
        }


def profile_path(deal: str) -> Path:
    return VAULT / "deals" / deal / "deal_profile.json"


def load_profile(deal: str, strict: bool = False) -> DealProfile:
    """
    Load a deal's institutional semantics.

    strict=True raises if the profile is missing — use when compiling a bundle
    that must be event-conformant. Otherwise returns an empty profile that
    supplies nothing and records warnings.
    """
    path = profile_path(deal)
    if not path.exists():
        if strict:
            raise FileNotFoundError(
                f"No deal profile for '{deal}' at {path}.\n"
                "A bundle cannot be event-conformant without declared perimeter/unit "
                "per position. Create the profile (see vault/deals/keystone/"
                "deal_profile.json) rather than letting the bridge guess."
            )
        p = DealProfile(deal)
        p.warnings.append(f"no deal_profile.json for '{deal}' — no perimeters declared")
        return p
    return DealProfile(deal, json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    import sys
    deal = sys.argv[1] if len(sys.argv) > 1 else "keystone"
    print(json.dumps(load_profile(deal).conformance_report(), indent=2))
