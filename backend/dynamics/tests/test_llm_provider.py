import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from tools import llm_provider  # noqa: E402


class LLMProviderTests(unittest.TestCase):
    def test_anthropic_defaults_remain_backward_compatible(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(llm_provider.provider_name(), "anthropic")
            self.assertEqual(
                llm_provider.raw_messages_url(),
                "https://api.anthropic.com/v1/messages",
            )
            self.assertEqual(
                llm_provider.configured_model("claude-sonnet-5"),
                "claude-sonnet-5",
            )
            self.assertIsNone(llm_provider.openrouter_extra_body())

    def test_openrouter_uses_anthropic_skin_with_zdr(self):
        environment = {
            "PEOS_LLM_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "test-key",
        }
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(
                llm_provider.raw_messages_url(),
                "https://openrouter.ai/api/v1/messages",
            )
            self.assertEqual(
                llm_provider.configured_model("claude-haiku-4-5-20251001"),
                "anthropic/claude-haiku-4.5",
            )
            self.assertEqual(llm_provider.configured_api_key(), "test-key")
            self.assertEqual(
                llm_provider.request_headers("test-key")["Authorization"],
                "Bearer test-key",
            )
            self.assertEqual(
                llm_provider.openrouter_extra_body(),
                {
                    "provider": {
                        "zdr": True,
                        "data_collection": "deny",
                        "require_parameters": True,
                    }
                },
            )


if __name__ == "__main__":
    unittest.main()
