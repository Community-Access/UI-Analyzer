"""Anthropic API client — streaming chat and model management."""

from __future__ import annotations
import json
from typing import Generator
import httpx

from ui_analyzer.services.ai_client import AIClient

class AnthropicClient(AIClient):
    """Anthropic API client using httpx."""

    def __init__(self, api_key: str, timeout: float = 120.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._base = "https://api.anthropic.com/v1/messages"

    def is_available(self) -> bool:
        """Quick check to see if the API key is valid via a simple call."""
        try:
            # Anthropic doesn't have a simple 'ping', so we check the API key
            # by attempting a very small request.
            with httpx.Client(timeout=5.0) as client:
                r = client.post(
                    self._base,
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "Hi"}],
                    },
                )
                return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[dict]:
        """Return common Anthropic models. The API doesn't easily list user-accessible models."""
        return [
            {"name": "claude-3-5-sonnet-20240620", "description": "Most capable model", "best_for": ["General", "Code"]},
            {"name": "claude-3-opus-20240229", "description": "Deep reasoning", "best_for": ["Complex Analysis"]},
            {"name": "claude-3-haiku-20240307", "description": "Fast and efficient", "best_for": ["Quick tasks"]},
        ]

    def stream_chat(
        self,
        model: str,
        messages: list[dict],
    ) -> Generator[str, None, None]:
        """Stream assistant content tokens from the Messages API."""
        payload = {
            "model":    model,
            "messages": messages,
            "stream":   True,
            "max_tokens": 4096,
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        with httpx.Client(timeout=self._timeout) as client:
            with client.stream("POST", self._base, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        if chunk.get("type") == "content_block_delta":
                            text = chunk.get("delta", {}).get("text", "")
                            if text:
                                yield text
                    except json.JSONDecodeError:
                        continue

    def respond(self, model: str, messages: list[dict]) -> str:
        """Non-streaming response."""
        return "".join(self.stream_chat(model, messages))
