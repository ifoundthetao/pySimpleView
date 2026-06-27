"""Pluggable AI vision providers for identifying captured images.

Everything goes through the Anthropic Messages SDK. MiniMax (and other
Anthropic-compatible services) are reached by pointing the same SDK at their
``base_url``; Claude uses the default endpoint. Swapping providers is just a
change of ``base_url`` + ``model``.
"""

from __future__ import annotations

from .base import VisionError, VisionProvider
from .provider import AnthropicProvider

# Built-in presets. `anthropic_native` gates Claude-only request features
# (adaptive thinking) that a compatible endpoint may reject.
PROVIDERS: dict[str, dict] = {
    "minimax": {
        "label": "MiniMax M3",
        "base_url": "https://api.minimax.io/anthropic",
        "model": "MiniMax-M3",
        "anthropic_native": False,
    },
    "anthropic": {
        "label": "Claude (Anthropic)",
        "base_url": "",
        "model": "claude-opus-4-8",
        "anthropic_native": True,
    },
    "custom": {
        "label": "Custom (Anthropic-compatible)",
        "base_url": "",
        "model": "",
        "anthropic_native": False,
    },
}

DEFAULT_PROVIDER = "minimax"


def preset(provider_key: str) -> dict:
    return PROVIDERS.get(provider_key, PROVIDERS[DEFAULT_PROVIDER])


def build_provider(
    provider_key: str, model: str, base_url: str, api_key: str
) -> AnthropicProvider:
    spec = preset(provider_key)
    return AnthropicProvider(
        api_key=api_key,
        model=model or spec["model"],
        base_url=base_url or spec["base_url"],
        use_thinking=spec["anthropic_native"],
    )


__all__ = [
    "AnthropicProvider",
    "VisionError",
    "VisionProvider",
    "PROVIDERS",
    "DEFAULT_PROVIDER",
    "preset",
    "build_provider",
]
