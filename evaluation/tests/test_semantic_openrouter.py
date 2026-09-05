from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from evaluation.semantic_openrouter import completion_request, configured_model


class SemanticOpenRouterTests(unittest.TestCase):
    def test_glm_5_2_is_the_default_and_request_is_strict_and_private(self):
        case = {"test_id": "semantic-test", "query": "Extract claims", "inputs": []}
        with patch.dict(os.environ, {}, clear=True):
            request = completion_request(case, "source text")
            self.assertEqual(configured_model(), "z-ai/glm-5.2")

        self.assertEqual(request["model"], "z-ai/glm-5.2")
        self.assertEqual(request["temperature"], 0)
        self.assertTrue(request["response_format"]["json_schema"]["strict"])
        self.assertEqual(
            request["extra_body"]["provider"],
            {
                "zdr": True,
                "data_collection": "deny",
                "require_parameters": True,
            },
        )
        self.assertEqual(request["extra_body"]["reasoning"]["effort"], "high")

    def test_exact_openrouter_model_and_reasoning_are_overridable(self):
        environment = {
            "PANTA_SEMANTIC_OPENROUTER_MODEL": "z-ai/glm-5.2:free",
            "PANTA_SEMANTIC_OPENROUTER_REASONING": "xhigh",
            "PEOS_OPENROUTER_ZDR": "false",
        }
        case = {"test_id": "semantic-test", "query": "Extract claims", "inputs": []}
        with patch.dict(os.environ, environment, clear=True):
            request = completion_request(case, "source text")
            self.assertEqual(configured_model(), "z-ai/glm-5.2:free")

        self.assertEqual(request["extra_body"]["reasoning"]["effort"], "xhigh")
        self.assertFalse(request["extra_body"]["provider"]["zdr"])


if __name__ == "__main__":
    unittest.main()
