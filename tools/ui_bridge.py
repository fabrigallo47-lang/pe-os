#!/usr/bin/env python3
"""
ui_bridge — serve a real compiler bundle to the PANTA V17 frontend.

The V17 package ships a mock server that answers from fixtures. This answers the
same API from an actual bundle produced by adapter_alpha, so the UI shows the
deal we compiled rather than a rehearsal of it.

Nothing is transformed on the way out. app/src/projection_adapter.js exposes
frontendProjectionFromBackend(), which accepts a raw compiler bundle and reads
exactly the fields current_graph.json already carries — case_id, company, state,
claims, case_positions, support_routes, claim_position_edges,
position_dependencies, model_nodes, coverage_limits — plus execution_mapping and
admission_manifest alongside. So the bundle is handed over as it is.

Ownership, from integration/API.md
----------------------------------
  ours   source decoding, semantic compilation, Current Live Case, execution
         mapping, manifest, proposed and admitted events
  Anto   Candidate, propagation, numerical execution, policy evaluation, human
         stops, settlement, replay hash
  V17    presentation and interaction only

This server stays on our side of that line. /admit returns the transition output
the PANTA engine produced when the bundle was built — it does not compute a
disposition, and /settle records the request without deciding it, because
settlement is not ours to grant.

    python3 tools/ui_bridge.py --bundle pipeline_out/e3/K-IC/adapter_alpha
    open 'http://127.0.0.1:4178/?mode=connected&api=http://127.0.0.1:4178/api/v1'
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
UI_APP = ROOT / "ui" / "app"

BUNDLE_FILES = {
    "current_graph": "current_graph.json",
    "execution_mapping": "execution_mapping.json",
    "admission_manifest": "admission_manifest_v7.json",
    "transition_output": "transition_output.json",
    "candidate_graph": "candidate_graph.json",
    "event": "event_ebitda_correction.json",
}


class Bundle:
    """The compiler bundle, read once and served as-is."""

    def __init__(self, path: Path):
        self.path = path
        self.parts: dict[str, dict] = {}
        missing = []
        for key, name in BUNDLE_FILES.items():
            f = path / name
            if f.exists():
                self.parts[key] = json.loads(f.read_text(encoding="utf-8"))
            else:
                missing.append(name)
        if "current_graph" not in self.parts:
            raise SystemExit(f"bundle incompleto in {path}: manca current_graph.json")
        self.missing = missing

    @property
    def case_id(self) -> str:
        return self.parts["current_graph"].get("case_id", "UNKNOWN")

    def projection(self) -> dict:
        # Raw bundle: the frontend adapter reads it directly.
        return {
            "case_id": self.case_id,
            "current_graph": self.parts["current_graph"],
            "execution_mapping": self.parts.get("execution_mapping", {}),
            "admission_manifest": self.parts.get("admission_manifest", {}),
            "transition_output": self.parts.get("transition_output"),
        }

    def pending_events(self) -> dict:
        ev = self.parts.get("event")
        if not ev:
            return {"events": []}
        # Proposed, not admitted: admitting is a human act, and the disposition
        # belongs to the transition engine, not to this server.
        return {"events": [{
            "event_id": ev.get("event_id"),
            "event": ev.get("event"),
            "status": "PROPOSED",
            "effective_date": ev.get("effective_date"),
            "known_at": ev.get("known_at"),
            "source_ids": ev.get("source_ids", []),
            "trigger_claim_ids": ev.get("trigger_claim_ids", []),
            "mutations": ev.get("mutations", []),
            "note": ev.get("note", ""),
        }]}

    def admit(self, event_id: str) -> dict:
        out = self.parts.get("transition_output")
        if not out:
            return {"error": "nessun transition_output nel bundle"}
        # Handed back frozen. The frontend maps dispositions; it does not
        # invent them, and neither does this.
        return {"event_id": event_id, "transition_output": out}


class Handler(BaseHTTPRequestHandler):
    server_version = "PANTA-ui-bridge/1.0"
    bundle: Bundle

    def log_message(self, fmt, *args):
        pass                                  # quiet; the console is for results

    # ── helpers ──────────────────────────────────────────────────────────────

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode(),
                   "application/json; charset=utf-8")

    def _static(self, path: str) -> None:
        rel = path.lstrip("/") or "index.html"
        target = (UI_APP / rel).resolve()
        # never serve outside the app directory
        if not str(target).startswith(str(UI_APP.resolve())) or not target.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": f"not found: {path}"})
            return
        ctype, _ = mimetypes.guess_type(str(target))
        self._send(HTTPStatus.OK, target.read_bytes(),
                   ctype or "application/octet-stream")

    # ── routes ───────────────────────────────────────────────────────────────

    def do_OPTIONS(self):
        self._send(HTTPStatus.NO_CONTENT, b"", "text/plain")

    def do_GET(self):
        path = urlparse(self.path).path
        b = self.bundle

        if path == "/api/v1/bootstrap":
            self._json(HTTPStatus.OK, {
                "mode": "connected",
                "api_version": "v1",
                "package_version": "17.0.0",
                "case_ids": [b.case_id],
                "capabilities": ["projection", "admit_event", "settle", "replay"],
                "served_from": str(b.path),
                "bundle_incomplete": b.missing,
            })
            return

        m = re.match(r"^/api/v1/cases/([^/]+)/(projection|pending-events|replay)$", path)
        if m:
            case, endpoint = m.group(1), m.group(2)
            if case != b.case_id:
                self._json(HTTPStatus.NOT_FOUND,
                           {"error": f"case sconosciuto: {case}",
                            "available": [b.case_id]})
                return
            if endpoint == "projection":
                self._json(HTTPStatus.OK, b.projection())
            elif endpoint == "pending-events":
                self._json(HTTPStatus.OK, b.pending_events())
            else:
                # Replay is Anto's: bitemporal reconstruction is not compiled here.
                self._json(HTTPStatus.NOT_IMPLEMENTED, {
                    "error": "replay non è del compilatore",
                    "owner": "runtime (Anto)",
                })
            return

        self._static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        b = self.bundle
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(length)) if length else {}
        except Exception:
            body = {}

        m = re.match(r"^/api/v1/cases/([^/]+)/events/([^/]+)/admit$", path)
        if m:
            self._json(HTTPStatus.OK, b.admit(m.group(2)))
            return

        if re.match(r"^/api/v1/cases/([^/]+)/settle$", path):
            # Settlement is a human act on the runtime side. Recorded, not granted.
            self._json(HTTPStatus.ACCEPTED, {
                "status": "RECORDED_NOT_SETTLED",
                "candidate_id": body.get("candidate_id"),
                "decision": body.get("decision"),
                "note": "il compilatore registra la richiesta; la settlement "
                        "appartiene al runtime e all'atto umano",
            })
            return

        self._json(HTTPStatus.NOT_FOUND, {"error": f"rotta sconosciuta: {path}"})


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve a real bundle to the V17 UI")
    ap.add_argument("--bundle", type=Path,
                    default=ROOT / "pipeline_out" / "e3" / "K-IC" / "adapter_alpha")
    ap.add_argument("--port", type=int, default=4178)
    a = ap.parse_args()

    if not UI_APP.exists():
        raise SystemExit(f"UI non trovata in {UI_APP}")

    Handler.bundle = Bundle(a.bundle)
    b = Handler.bundle
    cg = b.parts["current_graph"]

    print("=" * 62)
    print("PANTA V17 — bundle reale")
    print("=" * 62)
    print(f"  bundle   : {a.bundle}")
    print(f"  case_id  : {b.case_id}")
    print(f"  claims   : {len(cg.get('claims', []))}")
    print(f"  positions: {len(cg.get('case_positions', []))}")
    print(f"  model    : {len(cg.get('model_nodes', []))} nodi")
    if b.missing:
        print(f"  assenti  : {', '.join(b.missing)}")
    url = (f"http://127.0.0.1:{a.port}/?mode=connected"
           f"&api=http://127.0.0.1:{a.port}/api/v1")
    print(f"\n  apri: {url}\n")

    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
