"""Configuration management for UI-Analyzer — persists settings and secrets."""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any

import keyring
from platformdirs import user_config_dir

APP_NAME = "ui-analyzer"

class ConfigManager:
    """Manages user preferences and secure API key storage."""

    def __init__(self) -> None:
        self._config_dir = Path(user_config_dir(APP_NAME))
        self._config_file = self._config_dir / "config.json"
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Load settings from disk."""
        if self._config_file.exists():
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = self._get_defaults()

    def save(self) -> None:
        """Save settings to disk."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        with open(self._config_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=4)

    def _get_defaults(self) -> dict[str, Any]:
        return {
            "provider": "ollama",
            "ollama_url": "http://localhost:11434",
            "model": "",
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get a general setting."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a general setting."""
        self._data[key] = value
        self.save()

    # ── Secret Management (Keyring) ──────────────────────────────────────────────────

    def get_api_key(self, provider: str) -> str | None:
        """Retrieve API key from the OS secure store."""
        try:
            return keyring.get_password(APP_NAME, provider)
        except Exception:
            return None

    def set_api_key(self, provider: str, key: str) -> None:
        """Store API key in the OS secure store."""
        try:
            keyring.set_password(APP_NAME, provider, key)
        except Exception as e:
            raise RuntimeError(f"Failed to store API key in keyring: {e}")

    def delete_api_key(self, provider: str) -> None:
        """Remove API key from the OS secure store."""
        try:
            keyring.delete_password(APP_NAME, provider)
        except Exception:
            pass

    # ── Crawl config helpers ──────────────────────────────────────────────────

    def get_crawl_config(self) -> dict:
        """Return the saved crawl config dict (or empty dict for defaults)."""
        return dict(self._data.get("crawl_config", {}))

    def set_crawl_config(self, config_dict: dict) -> None:
        """Persist crawl config to disk."""
        self._data["crawl_config"] = config_dict
        self.save()
