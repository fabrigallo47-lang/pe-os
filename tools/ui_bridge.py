#!/usr/bin/env python3
"""
ui_bridge — serve real extraction output to the PANTA V17 frontend.

The V17 package ships a mock server that answers from fixtures. This answers the
same API from work we actually did, in one of two modes:

  live (default)  the store the extractor writes to. Nothing else is readable
                  from here, so no screen can show a number no ingest produced.
  --bundle        a compilation done earlier, with the package fixture filling
                  the product structures the compiler does not produce. Every
                  such use is labelled in the projection's provenance map.

Live is the default because "is this real?" should not be a question you have to
answer per section.

    python3 tools/ui_bridge.py --reset
    curl -s localhost:4178/api/v1/ingest -H 'content-type: application/json' \\
         -d '{"path": "~/Downloads/keystone_lbo_model_working.xlsx"}'

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

    open 'http://127.0.0.1:4178/?mode=connected&api=http://127.0.0.1:4178/api/v1'
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))       # run from anywhere, not just the repo root
UI_APP = ROOT / "ui" / "app"

BUNDLE_FILES = {
    "current_graph": "current_graph.json",
    "execution_mapping": "execution_mapping.json",
    "admission_manifest": "admission_manifest_v7.json",
    "transition_output": "transition_output.json",
    "candidate_graph": "candidate_graph.json",
    "event": "event_ebitda_correction.json",
    "grounding": "grounding_review.json",
}


class Bundle:
    """The compiler bundle, read once and served as-is."""

    def __init__(self, path: Path, deal: str = "keystone",
                 scaffold_path: Path | None = None):
        self.path = path
        self.deal = deal
        # The package fixture supplies only the product scaffolding the
        # compiler does not produce; every use of it is labelled in provenance.
        self.scaffold: dict = {}
        if scaffold_path and scaffold_path.exists():
            self.scaffold = json.loads(scaffold_path.read_text(encoding="utf-8"))
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
        self.last_ingest: dict | None = None

    @property
    def case_id(self) -> str:
        return self.parts["current_graph"].get("case_id", "UNKNOWN")

    def projection(self) -> dict:
        """
        A frontend_projection, not the raw bundle.

        engine.js adopts a projection only when it carries fund, deal or events:
        a raw bundle becomes {compiler, transition} and fails that test, so the
        UI keeps rendering its fixture while reporting itself connected. The
        projection is built by ui_projection, which fills what the compiler owns
        and marks what it does not.
        """
        from tools.ui_projection import build_projection
        proj = build_projection(
            {"current_graph": self.parts["current_graph"],
             "execution_mapping": self.parts.get("execution_mapping", {}),
             "admission_manifest": self.parts.get("admission_manifest", {}),
             "transition_output": self.parts.get("transition_output"),
             "event": self.parts.get("event")},
            deal=self.deal, scaffold=self.scaffold,
            grounding=(self.parts.get("grounding") or {}).get("review_queue"))
        return {
            "frontend_projection": proj,
            # the bundle travels alongside so nothing is lost to the projection
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


class Live:
    """
    The other thing this server can serve: the live store, and only that.

    A Bundle answers from a compilation that already happened; this answers from
    what the extractor has produced in this session. It exposes the same API, so
    the UI cannot tell the difference — but it can never show a number that no
    ingest put there, because there is nowhere else for it to read from.
    """

    def __init__(self, deal: str = "keystone"):
        from tools.live_store import LiveStore
        self.deal = deal
        self.store = LiveStore(deal)
        self.last_ingest: dict | None = None

    @property
    def case_id(self) -> str:
        return "PROJECT-KEYSTONE"

    def reload(self) -> None:
        from tools.live_store import LiveStore
        self.store = LiveStore(self.deal)

    def projection(self) -> dict:
        from tools import live_projection
        self.reload()
        return {"frontend_projection": live_projection.build(self.store)}

    def pending_events(self) -> dict:
        """
        What an ingest proposes, never what it decided.

        Admission is a human act, so an extracted finding leaves here as a
        proposal with its source attached and nothing more.
        """
        from tools import live_projection
        self.reload()
        proj = live_projection.build(self.store)
        return {"events": [{
            "event_id": e["event_id"], "event": e["type"], "status": "PROPOSED",
            "source_ids": [e["source_title"]],
            "trigger_claim_ids": [e["claim_id"]] if e.get("claim_id") else [],
            "mutations": [], "note": e["proposed_position"],
        } for e in proj["events"].values()]}

    def admit(self, event_id: str) -> dict:
        # There is no transition engine on this side, and inventing a
        # disposition would be exactly the adjudication we do not do.
        return {"event_id": event_id, "status": "NOT_ADMITTED",
                "reason": "il motore di transizione è del runtime; il "
                          "compilatore propone, non ammette"}

    def ingest(self, src: Path, concepts: Path | None) -> dict:
        from tools.ingest_service import ingest as run
        res = run(src, self.deal, concepts, self.store)
        res.pop("cells", None)
        res.pop("e3", None)
        self.last_ingest = res
        return res

    def reset(self) -> dict:
        self.store.reset()
        return {"status": "RESET", "deal": self.deal,
                "note": "lo store è vuoto: la UI ora mostra un deal senza fonti"}


class Handler(BaseHTTPRequestHandler):
    server_version = "PANTA-ui-bridge/1.0"
    bundle: Bundle | Live

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
                "served_from": str(getattr(b, "path", "live store")),
                "bundle_incomplete": getattr(b, "missing", []),
                "source": "live" if isinstance(b, Live) else "bundle",
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

        if path == "/api/v1/ingest":
            src = Path(body.get("path", "")).expanduser()
            if not src.exists():
                self._json(HTTPStatus.BAD_REQUEST,
                           {"error": f"file non trovato: {src}"})
                return
            concepts = body.get("concepts")
            cp = Path(concepts).expanduser() if concepts else None
            if isinstance(b, Live):
                self._json(HTTPStatus.OK, b.ingest(src, cp))
                return
            from tools.ingest_service import ingest
            res = ingest(src, b.deal, cp)
            # Heavy payloads stay on disk; the response reports what was built.
            res.pop("cells", None)
            res.pop("e3", None)
            b.last_ingest = res
            self._json(HTTPStatus.OK, res)
            return

        if path == "/api/v1/reset":
            if not isinstance(b, Live):
                self._json(HTTPStatus.CONFLICT,
                           {"error": "in modalità bundle non c'è nulla da azzerare"})
                return
            self._json(HTTPStatus.OK, b.reset())
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
    ap = argparse.ArgumentParser(description="Serve real extraction output to the V17 UI")
    ap.add_argument("--bundle", type=Path, default=None,
                    help="modalità bundle: serve una compilazione già fatta "
                         "invece dello store dell'estrattore")
    ap.add_argument("--port", type=int, default=4178)
    ap.add_argument("--deal", default="keystone")
    ap.add_argument("--reset", action="store_true",
                    help="azzera lo store prima di partire: la UI parte da zero")
    ap.add_argument("--scaffold", type=Path,
                    default=ROOT / "ui" / "fixtures" / "normalized"
                            / "frontend_projection_v17.json",
                    help="modalità bundle soltanto: fixture del pacchetto per le "
                         "strutture di prodotto che il compilatore non produce")
    ap.add_argument("--no-scaffold", action="store_true",
                    help="modalità bundle: niente fixture")
    a = ap.parse_args()

    if not UI_APP.exists():
        raise SystemExit(f"UI non trovata in {UI_APP}")

    url = (f"http://127.0.0.1:{a.port}/?mode=connected"
           f"&api=http://127.0.0.1:{a.port}/api/v1")

    if a.bundle:
        Handler.bundle = Bundle(a.bundle, deal=a.deal,
                                scaffold_path=None if a.no_scaffold else a.scaffold)
        b = Handler.bundle
        cg = b.parts["current_graph"]
        print("=" * 62)
        print("PANTA V17 — modalità bundle")
        print("=" * 62)
        print(f"  bundle   : {a.bundle}")
        print(f"  case_id  : {b.case_id}")
        print(f"  claims   : {len(cg.get('claims', []))}")
        print(f"  positions: {len(cg.get('case_positions', []))}")
        print(f"  model    : {len(cg.get('model_nodes', []))} nodi")
        if b.missing:
            print(f"  assenti  : {', '.join(b.missing)}")
    else:
        Handler.bundle = Live(deal=a.deal)
        b = Handler.bundle
        if a.reset:
            b.reset()
        s = b.store.summary()
        print("=" * 62)
        print("PANTA V17 — solo estrazione")
        print("=" * 62)
        print(f"  store    : {b.store.dir}")
        if b.store.is_empty:
            print("  vuoto: la UI mostrerà un deal senza fonti, che è il quadro")
            print("  corretto di non aver ancora estratto nulla.")
        else:
            for src in b.store.manifest["sources"]:
                print(f"  {src['kind']:9} {src['source'][:46]:48} {src['ingested_at']}")
            print(f"  {s['claims']} claim · {s['bindings']} binding · "
                  f"{s['records']} record · {s['cells']} celle")
        # Said here rather than discovered on the first ingest: a workbook needs
        # no model call, a document needs one, and knowing which half of the
        # pipeline can run is worth more before you try than after.
        import os
        from tools.ingest_service import _key_from_env_file
        if os.environ.get("ANTHROPIC_API_KEY"):
            print("  documenti : estrazione attiva (chiave dall'ambiente)")
        elif _key_from_env_file():
            print("  documenti : estrazione attiva (chiave da .env.local)")
        else:
            print("  documenti : NON estraibili — nessuna ANTHROPIC_API_KEY.")
            print("              i workbook funzionano comunque: L1-L3 è locale.")
        print("\n  ingest:")
        print(f"    curl -s localhost:{a.port}/api/v1/ingest -H 'content-type: "
              f"application/json' \\")
        print(f"      -d '{{\"path\":\"~/Downloads/....pdf\"}}'")

    print(f"\n  apri: {url}\n")
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
