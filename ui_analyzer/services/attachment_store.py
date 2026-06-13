"""Persists source-file → screenshot attachment bindings.

The attachment for `foo.swift` is stored as `foo.swift.context.png` at the
folder root.  The binding from relative_path → attachment_filename is kept in
a JSON map at %LOCALAPPDATA%/UIAnalyzer/attachments.json so it survives scans
(UIFile.id is ephemeral; relative_path is stable).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

_SUFFIX = ".context"


def attachment_filename(source_name: str) -> str:
    """Return the conventional attachment filename for *source_name*.

    `loginView.swift` → `loginView.swift.context.png`
    """
    return f"{source_name}{_SUFFIX}.png"


def looks_like_attachment(name: str) -> bool:
    """True if *name* matches the `*.context.png` pattern."""
    return name.endswith(".context.png")


# ── Persistence ───────────────────────────────────────────────────────────────

def _store_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "UIAnalyzer" / "attachments.json"


def _load() -> dict[str, str]:
    p = _store_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(mapping: dict[str, str]) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(mapping, indent=2), encoding="utf-8")


def set_attachment(attachment_name: Optional[str], for_relative_path: str) -> None:
    """Bind or clear the attachment for *for_relative_path*."""
    m = _load()
    if attachment_name:
        m[for_relative_path] = attachment_name
    else:
        m.pop(for_relative_path, None)
    _save(m)


def lookup_attachment(relative_path: str) -> Optional[str]:
    """Return the attachment filename for *relative_path*, or None."""
    return _load().get(relative_path)
