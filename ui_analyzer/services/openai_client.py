"""OpenAI API client — streaming chat and model management."""

from __future__ import annotations
import json
from typing import Generator
import httpx

from ui_analyzer.services.ai_client import AIClient

class OpenAIClient(AIClient):
    """OpenAI API client using httpx."""

    def __init__(self, api_key: str, timeout: float = 120.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._base = "https://api.openai.com/v1/chat/completions"

    def is_available(self) -> bool:
        """Quick check to see if the API key is valid."""
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.post(
                    self._base,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": "Hi"}],
                        "max_tokens": 1,
                    },
                )
                return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[dict]:
        """Return common OpenAI models."""
        return [
            {"name": "gpt-4o", "description": "Highest intelligence", "best_for": ["General", "Complex Analysis"]},
            {"name": "gpt-4o-mini", "description": "Fast and cost-efficient", "best_for": ["General", "Quick tasks"]},
            {"name": "o1-preview", "description": "Advanced reasoning", "best_for": ["Deep Code Analysis"]},
        ]

    def stream_chat(
        self,
        model: str,
        messages: list[dict],
    ) -> Generator[str, None, None]:
        """Stream assistant content tokens from the Chat Completions API."""
        payload = {
            "model":    model,
            "messages": messages,
            "stream":   True,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

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
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    def respond(self, model: str, messages: list[dict]) -> str:
        """Non-streaming response."""
        return "".join(self.stream_chat(model, messages))
