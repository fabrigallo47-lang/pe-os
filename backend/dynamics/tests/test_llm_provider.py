import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from tools import llm_provider  # noqa: E402
from tools import extract_v2_physical as extract_v2  # noqa: E402


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

    def test_v2_allows_complete_excel_tool_output(self):
        captured = {}

        class FakeMessages:
            def create(self, **request):
                captured.update(request)
                return SimpleNamespace(content=[])

        chunk = extract_v2.Chunk(
            chunk_id="ch-test",
            locator="model.xlsx::Inputs!52:64",
            body="A57=Standalone Upside - DSO | B57=days | C57=62",
            source_path="model.xlsx",
            source_type="xlsx",
            source_record={
                "source_id": "SRC-MODEL",
                "name": "Keystone model",
                "doc_type": "LBO Model",
                "effective_date": "2026-03-05",
                "known_at": "2026-03-05",
            },
            word_count=8,
        )
        client = SimpleNamespace(messages=FakeMessages())
        with patch.dict(
            os.environ,
            {"PEOS_LLM_PROVIDER": "openrouter"},
            clear=True,
        ):
            claims = extract_v2.annotate_chunk(
                chunk,
                client,
                "keystone",
                rate_limit_delay=0,
            )

        self.assertEqual(claims, [])
        self.assertEqual(captured["max_tokens"], 4096)
        self.assertIn(
            "EFFECTIVE DATE: 2026-03-05",
            captured["messages"][0]["content"],
        )
        self.assertEqual(
            captured["tools"][0]["input_schema"]["properties"]["claims"]["maxItems"],
            20,
        )
        self.assertEqual(
            captured["extra_body"]["provider"]["data_collection"],
            "deny",
        )


if __name__ == "__main__":
    unittest.main()
