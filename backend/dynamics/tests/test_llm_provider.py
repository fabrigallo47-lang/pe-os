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

    def test_openrouter_defaults_to_glm_5_2_over_anthropic_skin_with_zdr(self):
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
                "z-ai/glm-5.2",
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

    def test_openrouter_accepts_glm_short_names_and_explicit_model_slugs(self):
        with patch.dict(
            os.environ,
            {"PEOS_LLM_PROVIDER": "openrouter", "PEOS_MODEL": "glm-5.2"},
            clear=True,
        ):
            self.assertEqual(
                llm_provider.configured_model("claude-haiku-4-5-20251001"),
                "z-ai/glm-5.2",
            )

        with patch.dict(
            os.environ,
            {"PEOS_LLM_PROVIDER": "openrouter", "PEOS_MODEL": "glm-5.2-free"},
            clear=True,
        ):
            self.assertEqual(
                llm_provider.configured_model("claude-haiku-4-5-20251001"),
                "z-ai/glm-5.2:free",
            )

        with patch.dict(
            os.environ,
            {"PEOS_LLM_PROVIDER": "openrouter", "PEOS_MODEL": "google/gemini-3.5-flash"},
            clear=True,
        ):
            self.assertEqual(
                llm_provider.configured_model("claude-haiku-4-5-20251001"),
                "google/gemini-3.5-flash",
            )

    def test_extraction_disables_extended_thinking_on_openrouter(self):
        """GLM 5.2 spends the whole output budget thinking and never emits the
        tool call. Measured on a 202-word chunk: default -> stop=max_tokens,
        8192 output tokens, blocks=['thinking'], ZERO claims; with thinking
        disabled -> stop=tool_use, 3255 tokens, 17 claims. Three of eleven
        benchmark cases were abstaining for this reason alone (51.6% -> 65.0%).

        It must be the Anthropic-native `thinking` field: through the
        /v1/messages skin, reasoning={"effort":"low"} and {"enabled":False}
        were both ignored, and forcing tool_choice did not help either.
        """
        with patch.dict(os.environ, {"PEOS_LLM_PROVIDER": "openrouter"}, clear=True):
            self.assertEqual(llm_provider.thinking_parameter(), {"type": "disabled"})

    def test_anthropic_is_not_sent_a_thinking_field(self):
        """Its default is already no extended thinking; sending the field would
        only add a way to be wrong."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(llm_provider.thinking_parameter())

    def test_thinking_can_be_re_enabled_deliberately(self):
        with patch.dict(
            os.environ,
            {"PEOS_LLM_PROVIDER": "openrouter", "PEOS_OPENROUTER_THINKING": "true"},
            clear=True,
        ):
            self.assertIsNone(llm_provider.thinking_parameter())

    def test_anthropic_still_pins_the_tool_openrouter_does_not(self):
        """Forcing the tool is right on Anthropic and wrong on GLM: pinned it
        generates a tool call that never terminates (8192 tokens, 0 claims);
        left alone it emits text then a complete call (857 tokens, 3 claims).
        That was the last case abstaining after the thinking fix."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(llm_provider.forces_tool_choice())
        with patch.dict(os.environ, {"PEOS_LLM_PROVIDER": "openrouter"}, clear=True):
            self.assertFalse(llm_provider.forces_tool_choice())

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
        # 8192, not 4096. At 4096 a full Excel tool output hit the ceiling and
        # the call returned stop_reason=max_tokens with ZERO claims and no
        # exception -- reproduced 3/3 on real chunks, so the truncation was
        # silent and looked like an empty document. Assert against the module's
        # own constant so this pins the wiring, not a number that has to be
        # edited every time the budget changes.
        self.assertEqual(captured["max_tokens"], extract_v2.MAX_TOKENS)
        self.assertGreaterEqual(extract_v2.MAX_TOKENS, 8192)
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
        self.assertEqual(captured["thinking"], {"type": "disabled"})
        self.assertNotIn("tool_choice", captured)


if __name__ == "__main__":
    unittest.main()
