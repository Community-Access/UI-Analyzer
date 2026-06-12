"""Ollama local API client — streaming chat and model management."""

from __future__ import annotations

import json
from typing import Generator, Optional
import httpx

BASE_URL = "http://localhost:11434"

# ── Model capability metadata ─────────────────────────────────────────────────
# Maps model family prefix → (description, best-for tags, min RAM GB)

MODEL_PROFILES: list[tuple[str, str, list[str], int]] = [
    ("qwen2.5-coder",  "Excellent code analysis across many languages",
     ["Python", "JavaScript", "TypeScript", "Swift", "React"], 5),
    ("deepseek-coder", "Deep code understanding, great for accessibility analysis",
     ["Python", "React", "JavaScript", "TypeScript"], 5),
    ("codellama",      "Solid general code analysis, good with older codebases",
     ["Python", "JavaScript", "C/ObjC", "Swift"], 5),
    ("phi4",           "Efficient reasoning, good for lower-RAM machines",
     ["General", "Python", "JavaScript"], 4),
    ("phi3",           "Lightweight, fast, good for quick analysis",
     ["General", "Python"], 3),
    ("mistral-nemo",   "Strong instruction following, great for web frameworks",
     ["React Native", "JavaScript", "TypeScript", "Vue"], 5),
    ("mistral",        "Reliable all-rounder, good structured output",
     ["React", "JavaScript", "Vue", "Svelte"], 5),
    ("llama3.2",       "Good general-purpose prose and code descriptions",
     ["General", "SwiftUI", "Python"], 3),
    ("llama3.1",       "Strong reasoning and structured output",
     ["General", "React", "Python"], 5),
    ("llama3",         "Capable all-rounder for code and description tasks",
     ["General"], 5),
    ("gemma3",         "Good prose output, solid code understanding",
     ["General", "HTML", "CSS"], 3),
    ("gemma2",         "Reliable balanced model",
     ["General"], 5),
]

# ── File type → best model families ──────────────────────────────────────────

FILETYPE_BEST_MODELS: dict[str, list[str]] = {
    "SwiftUI":      ["qwen2.5-coder", "codellama", "llama3.2"],
    "Python":       ["qwen2.5-coder", "deepseek-coder", "codellama"],
    "React / JSX":  ["qwen2.5-coder", "deepseek-coder", "mistral-nemo"],
    "JavaScript":   ["qwen2.5-coder", "deepseek-coder", "mistral"],
    "TypeScript":   ["qwen2.5-coder", "deepseek-coder", "mistral-nemo"],
    "Vue":          ["mistral", "mistral-nemo", "qwen2.5-coder"],
    "Svelte":       ["mistral", "qwen2.5-coder"],
    "HTML":         ["gemma3", "mistral", "llama3.2"],
    "CSS":          ["gemma3", "mistral", "llama3.2"],
    "Markdown":     ["llama3.2", "gemma3", "mistral"],
    "Screenshot":   ["llama3.2", "gemma3", "mistral"],
}


def _profile_for(model_name: str) -> tuple[str, list[str], int]:
    """Return (description, best-for tags, min_ram_gb) for a model name."""
    lower = model_name.lower()
    for prefix, desc, tags, ram in MODEL_PROFILES:
        if lower.startswith(prefix):
            return desc, tags, ram
    return "General-purpose language model", ["General"], 5


def best_model_for_filetype(installed: list[str], file_type_label: str) -> Optional[str]:
    """Return the name of the best installed model for this file type, or None."""
    preferred = FILETYPE_BEST_MODELS.get(file_type_label, [])
    for family in preferred:
        for model in installed:
            if model.lower().startswith(family):
                return model
    return installed[0] if installed else None


# ── OllamaClient ─────────────────────────────────────────────────────────────

class OllamaClient:
    def __init__(self, base_url: str = BASE_URL, timeout: float = 120.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def is_available(self) -> bool:
        try:
            r = httpx.get(f"{self._base}/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[dict]:
        """Return list of installed models with enriched metadata."""
        try:
            r = httpx.get(f"{self._base}/api/tags", timeout=5.0)
            r.raise_for_status()
            raw = r.json().get("models", [])
        except Exception:
            return []

        enriched = []
        for m in raw:
            name = m.get("name", "")
            desc, tags, ram = _profile_for(name)
            size_bytes = m.get("size", 0)
            size_gb = size_bytes / 1_073_741_824
            enriched.append({
                "name":        name,
                "description": desc,
                "best_for":    tags,
                "min_ram_gb":  ram,
                "size_gb":     round(size_gb, 1),
                "raw":         m,
            })
        return enriched

    def stream_chat(
        self,
        model: str,
        messages: list[dict],
    ) -> Generator[str, None, None]:
        """Stream assistant content tokens from the /api/chat endpoint.

        Yields incremental content strings as they arrive.
        Raises on HTTP or connection errors.
        """
        payload = {
            "model":    model,
            "messages": messages,
            "stream":   True,
        }
        with httpx.Client(timeout=self._timeout) as client:
            with client.stream("POST", f"{self._base}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done"):
                        break

    def respond(self, model: str, messages: list[dict]) -> str:
        """Non-streaming chat response — collects and returns the full reply."""
        return "".join(self.stream_chat(model, messages))
