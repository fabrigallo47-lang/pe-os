#!/usr/bin/env python3
"""PANTA V17 local handoff server.

Serves the integration-ready frontend and a small API with the exact endpoints
expected by app/src/integration.js. It is deliberately stdlib-only so Anto and
Fabri can run it without installing dependencies.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
FIXTURES = ROOT / "fixtures" / "normalized"


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class Handler(BaseHTTPRequestHandler):
    server_version = "PANTA-V17/1.0"

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.is_file() or APP not in path.resolve().parents and path.resolve() != APP.resolve():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/v1/bootstrap":
            self._send_json({
                "mode": "connected",
                "api_version": "v1",
                "package_version": "17.0.0",
                "case_ids": ["PROJECT-KEYSTONE"],
                "capabilities": ["projection", "admit_event", "settle", "replay"],
            })
            return
        if path == "/api/v1/cases/PROJECT-KEYSTONE/projection":
            self._send_json({"frontend_projection": load_json("frontend_projection_v17.json")})
            return
        if path == "/api/v1/cases/PROJECT-KEYSTONE/pending-events":
            projection = load_json("frontend_projection_v17.json")
            self._send_json({"case_id": "PROJECT-KEYSTONE", "events": list(projection["events"].values())})
            return
        if path == "/api/v1/cases/PROJECT-KEYSTONE/replay":
            query = parse_qs(parsed.query)
            requested = (query.get("known_at") or [None])[0]
            payload = load_json("replay_snapshots_v17.json")
            item = next((x for x in payload["snapshots"] if x["id"] == requested), payload["snapshots"][0])
            self._send_json(item)
            return
        if path.startswith("/api/"):
            self._send_json({"error": "Unknown API route", "path": path}, 404)
            return
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (APP / rel).resolve()
        try:
            target.relative_to(APP.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        self._send_file(target)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return
        prefix = "/api/v1/cases/PROJECT-KEYSTONE/events/"
        suffix = "/admit"
        if path.startswith(prefix) and path.endswith(suffix):
            event_id = path[len(prefix):-len(suffix)]
            fixture = "transition_concentration_v17.json" if "concentration" in event_id.lower() else "transition_earnings_v17.json"
            self._send_json(load_json(fixture))
            return
        if path == "/api/v1/cases/PROJECT-KEYSTONE/settle":
            now = int(time.time() * 1000)
            self._send_json({
                "case_id": "PROJECT-KEYSTONE",
                "candidate_id": body.get("candidate_id"),
                "status": "SETTLED",
                "current_state_id": f"current-v17-{now}",
                "approved_unchanged": True,
                "decision": body.get("decision", {}),
                "replay_hash": f"sha256:mock-settlement-{now}",
            })
            return
        self._send_json({"error": "Unknown API route", "path": path}, 404)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[PANTA V17] {self.address_string()} - {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the PANTA V17 handoff package.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4177)
    parser.add_argument("--open", action="store_true", help="Open the app in the default browser.")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/?mode=connected"
    print(f"PANTA V17 running at {url}")
    if args.open:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping PANTA V17.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
