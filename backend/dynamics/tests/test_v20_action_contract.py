import re
import sys
import unittest
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from app.server import app  # noqa: E402
import app.v20_router as router  # noqa: E402


class V20ConnectedActionContractTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _frontend_remote_actions() -> set[str]:
        source = (PROJECT_ROOT / "ui" / "01_PRODUCT_BUILD" / "app" / "src" / "api.js").read_text(
            encoding="utf-8"
        )
        remote = source.split("const remote={", 1)[1].split("\n  };\n  function adapter", 1)[0]
        return set(re.findall(r"async\s+([A-Za-z_$][\w$]*)\s*\(", remote))

    @staticmethod
    def _materialize(path: str) -> str:
        values = {
            "case_id": "keystone",
            "source_id": "SRC-001",
            "run_id": "RUN-001",
            "package_id": "PKG-001",
            "work_id": "WORK-001",
            "kind": "derivation",
            "proposal_id": "PROP-001",
            "mission_id": "MISSION-001",
            "version_id": "STATE-001",
        }

        def replace(match: re.Match) -> str:
            return values[match.group(1)]

        return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::path)?\}", replace, path)

    def test_frontend_remote_methods_equal_manifest_actions(self):
        self.assertEqual(
            self._frontend_remote_actions(),
            set(router.V20_ACTION_CAPABILITIES),
        )

    def test_every_manifest_action_has_a_matching_api_route(self):
        registered = {
            (method, route.path)
            for route in router.v20.routes
            for method in (route.methods or set())
        }

        missing = []
        for action, spec in router.V20_ACTION_CAPABILITIES.items():
            route_key = (spec["method"], f"/api/v20{spec['path']}")
            if route_key not in registered:
                missing.append((action, route_key))
        self.assertEqual(missing, [])

    async def test_unavailable_actions_are_explicit_over_http(self):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://panta.test") as client:
            for action, spec in router.V20_ACTION_CAPABILITIES.items():
                if spec["status"] != "UNAVAILABLE":
                    continue
                path = "/api/v20" + self._materialize(spec["path"])
                response = await client.request(spec["method"], path, json={})
                body = response.json()
                with self.subTest(action=action):
                    self.assertEqual(response.status_code, 501)
                    self.assertEqual(body["error"]["code"], "CAPABILITY_UNAVAILABLE")
                    self.assertEqual(body["error"]["details"]["action"], action)


if __name__ == "__main__":
    unittest.main()
