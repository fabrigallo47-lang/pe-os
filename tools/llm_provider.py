"""Shared LLM provider configuration for PANTA extraction entry points."""
from __future__ import annotations

import os
from typing import Any


DEFAULT_OPENROUTER_EXTRACTION_MODEL = "z-ai/glm-5.2"

_OPENROUTER_MODEL_ALIASES = {
    "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4.5",
    "claude-sonnet-5": "anthropic/claude-sonnet-5",
    "glm-5.2": DEFAULT_OPENROUTER_EXTRACTION_MODEL,
    "glm-5.2-free": f"{DEFAULT_OPENROUTER_EXTRACTION_MODEL}:free",
}


def provider_name() -> str:
    return os.environ.get("PEOS_LLM_PROVIDER", "anthropic").strip().lower()


def is_openrouter() -> bool:
    return provider_name() == "openrouter"


def configured_api_key() -> str:
    variable = "OPENROUTER_API_KEY" if is_openrouter() else "ANTHROPIC_API_KEY"
    return os.environ.get(variable, "").strip()


def missing_key_message() -> str:
    variable = "OPENROUTER_API_KEY" if is_openrouter() else "ANTHROPIC_API_KEY"
    return f"{variable} not set"


def configured_model(default_anthropic_model: str) -> str:
    explicit = os.environ.get("PEOS_MODEL", "").strip()
    if explicit:
        if is_openrouter():
            return _OPENROUTER_MODEL_ALIASES.get(explicit.lower(), explicit)
        return explicit
    if is_openrouter():
        return DEFAULT_OPENROUTER_EXTRACTION_MODEL
    return default_anthropic_model


def _openrouter_base_url() -> str:
    return os.environ.get(
        "PEOS_LLM_BASE_URL", "https://openrouter.ai/api"
    ).rstrip("/")


def raw_messages_url() -> str:
    if not is_openrouter():
        return "https://api.anthropic.com/v1/messages"
    base = _openrouter_base_url()
    return f"{base}/messages" if base.endswith("/v1") else f"{base}/v1/messages"


def request_headers(api_key: str) -> dict[str, str]:
    if is_openrouter():
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://panta.local",
            "X-Title": "PANTA Extraction Pipeline",
        }
    return {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }


def openrouter_provider_preferences() -> dict[str, Any]:
    zdr = os.environ.get("PEOS_OPENROUTER_ZDR", "true").strip().lower()
    return {
        "zdr": zdr not in {"0", "false", "no", "off"},
        "data_collection": "deny",
        "require_parameters": True,
    }


def openrouter_extra_body() -> dict[str, Any] | None:
    if not is_openrouter():
        return None
    return {"provider": openrouter_provider_preferences()}


def forces_tool_choice() -> bool:
    """Whether to pin the model to the tool, or leave the choice to it.

    Anthropic: yes. Forcing removes the failure where the model answers in
    prose instead of calling emit_claims.

    OpenRouter/GLM: NO, and this one is counter-intuitive. Forcing the tool
    makes GLM generate a degenerate tool call that never terminates. Same
    chunk, same prompt, thinking already disabled:

        tool_choice forced   stop=max_tokens  out=8192  0 claims
        tool_choice auto     stop=tool_use    out= 857  3 claims

    Left to itself the model emits a short text block and then a complete tool
    call. Pinned, it fills the entire budget and returns nothing. This was the
    last benchmark case abstaining after the thinking fix.
    """
    return not is_openrouter()


def thinking_parameter() -> dict[str, Any] | None:
    """Turn extended thinking OFF for extraction on OpenRouter.

    GLM 5.2 is a reasoning model, and on a tool-use call it spends the WHOLE
    output budget thinking and never emits the tool block. Measured on
    panta-semantic.keystone.identity-and-derivation-001, a 202-word chunk:

        default             stop=max_tokens  out=8192  blocks=['thinking']         0 claims
        thinking disabled   stop=tool_use    out=3255  blocks=['text','tool_use'] 17 claims

    Three of eleven benchmark cases abstained for exactly this reason, scoring
    zero on documents the model never got to answer.

    It has to be the Anthropic-native `thinking` parameter, not OpenRouter's
    `reasoning` field: through the /v1/messages compatibility skin,
    reasoning={"effort":"low"} and reasoning={"enabled":False} were both
    ignored, still burning all 8192 tokens. Forcing tool_choice does not help
    either -- the model thinks first regardless.

    Returns None on Anthropic, where the default is already no extended
    thinking and sending the field would only add a way to be wrong.
    """
    if not is_openrouter():
        return None
    if os.environ.get("PEOS_OPENROUTER_THINKING", "").strip().lower() in {"1", "true", "on"}:
        return None
    return {"type": "disabled"}


def anthropic_client_kwargs(api_key: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"api_key": api_key}
    if is_openrouter():
        kwargs["base_url"] = _openrouter_base_url()
    else:
        workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
        if workspace_id:
            kwargs["default_headers"] = {
                "anthropic-workspace-id": workspace_id
            }
    return kwargs
