import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20CapabilitiesTests(unittest.TestCase):
    def test_manifest_is_versioned_and_bootstrap_exposes_it(self):
        manifest = router.action_capabilities()

        self.assertEqual(manifest["schema_version"], "v20-action-capabilities/1.0")
        self.assertEqual(manifest["actions"]["addNote"]["status"], "AVAILABLE")
        self.assertEqual(manifest["actions"]["openDeal"]["status"], "UNAVAILABLE")
        bootstrap = router.bootstrap_flat("keystone")
        self.assertEqual(bootstrap["action_capabilities"], manifest)
        session_id = bootstrap["session_id"]
        self.assertRegex(session_id, r"^SES-[A-Za-z0-9_-]{32,128}$")
        session_hash = router._authentication_session_hash(session_id)
        self.assertIn(session_hash, router._authenticated_sessions)
        self.assertNotIn(session_id, router._authenticated_sessions)
        self.assertEqual(
            bootstrap["context"]["authentication"]["principal_id"],
            bootstrap["context"]["authenticated_actor"]["actor_id"],
        )

    def test_unavailable_response_has_stable_machine_readable_shape(self):
        response = router.open_deal_unavailable()
        body = json.loads(response.body)

        self.assertEqual(response.status_code, 501)
        self.assertEqual(body["error"]["code"], "CAPABILITY_UNAVAILABLE")
        self.assertEqual(body["error"]["details"]["action"], "openDeal")
        self.assertIn("no deal was created", body["error"]["message"])

    def test_every_unavailable_action_declares_a_reason(self):
        unavailable = [
            spec for spec in router.V20_ACTION_CAPABILITIES.values()
            if spec["status"] == "UNAVAILABLE"
        ]

        self.assertTrue(all(spec.get("reason") for spec in unavailable))


if __name__ == "__main__":
    unittest.main()
