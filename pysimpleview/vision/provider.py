"""Anthropic Messages-API vision provider (drives Claude and MiniMax M3)."""

from __future__ import annotations

import base64

from .base import VisionError, VisionProvider


class AnthropicProvider(VisionProvider):
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "",
        use_thinking: bool = False,
        max_tokens: int = 1024,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.use_thinking = use_thinking
        self.max_tokens = max_tokens

    def analyze(self, images: list[tuple[bytes, str]], prompt: str) -> str:
        if not self.api_key:
            raise VisionError("No API key set. Open AI settings… to add one.")
        if not images:
            raise VisionError("No image to analyze.")
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise VisionError("The 'anthropic' package is not installed.") from exc

        client = anthropic.Anthropic(
            api_key=self.api_key,
            base_url=self.base_url or None,
        )

        content: list[dict] = []
        for image_bytes, media_type in images:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.standard_b64encode(image_bytes).decode("ascii"),
                },
            })
        content.append({"type": "text", "text": prompt})

        kwargs = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": content}],
        )
        # Adaptive thinking is a Claude feature; a compatible endpoint may 400 on it.
        if self.use_thinking:
            kwargs["thinking"] = {"type": "adaptive"}

        try:
            response = client.messages.create(**kwargs)
        except anthropic.APIError as exc:
            raise VisionError(str(exc)) from exc
        except Exception as exc:  # network, auth, etc.
            raise VisionError(str(exc)) from exc

        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        return text or "(no description returned)"
