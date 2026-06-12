from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class UIFileType(Enum):
    SWIFT_UI   = "SwiftUI"
    STORYBOARD = "Storyboard"
    XIB        = "XIB"
    HTML       = "HTML"
    CSS        = "CSS"
    REACT_JSX  = "React / JSX"
    VUE        = "Vue"
    SVELTE     = "Svelte"
    PYTHON     = "Python"
    JAVASCRIPT = "JavaScript"
    TYPESCRIPT = "TypeScript"
    MARKDOWN   = "Markdown"
    IMAGE      = "Screenshot"

    # ── Human-readable label used in the sidebar ──────────────────────────────
    @property
    def label(self) -> str:
        return self.value

    # ── Detect type from file extension + optional content ────────────────────
    @classmethod
    def from_path(cls, path: Path, content: str | None = None) -> Optional["UIFileType"]:
        ext = path.suffix.lower().lstrip(".")

        _IMAGE = {"png", "jpg", "jpeg", "heic", "heif", "webp", "tiff", "tif", "bmp", "gif"}

        if ext == "storyboard":  return cls.STORYBOARD
        if ext == "xib":         return cls.XIB
        if ext in ("html","htm"): return cls.HTML
        if ext == "css":         return cls.CSS
        if ext == "vue":         return cls.VUE
        if ext == "svelte":      return cls.SVELTE
        if ext in ("jsx","tsx"): return cls.REACT_JSX
        if ext in ("md","markdown"): return cls.MARKDOWN
        if ext in _IMAGE:        return cls.IMAGE

        # Content-gated types
        if ext == "swift":
            if content and any(kw in content for kw in (": View", "some View", "SwiftUI", "@ViewBuilder")):
                return cls.SWIFT_UI
            return None

        if ext == "py":
            if content and any(kw in content for kw in
                               ("tkinter", "PyQt6", "PySide6", "import wx", "from wx",
                                "kivy", "PySimpleGUI")):
                return cls.PYTHON
            return None

        if ext == "js":
            if content:
                lower = content.lower()
                if any(kw in lower for kw in ("react", "angular", "document.get",
                                               "queryselector", "innerhtml")):
                    return cls.JAVASCRIPT
            return None

        if ext == "ts":
            if content:
                lower = content.lower()
                if any(kw in lower for kw in ("react", "@component", "@ngmodule", "angular")):
                    return cls.TYPESCRIPT
            return None

        return None

    # ── Extensions that require reading content to classify ───────────────────
    @classmethod
    def needs_content(cls, path: Path) -> bool:
        return path.suffix.lower().lstrip(".") in ("swift", "py", "js", "ts")

    # ── Image types ───────────────────────────────────────────────────────────
    @property
    def is_image(self) -> bool:
        return self == UIFileType.IMAGE


class OutputMode(Enum):
    PROSE = "Prose"
    TABLE = "Table"


class TableFormat(Enum):
    MARKDOWN = "Markdown"
    HTML     = "HTML"


@dataclass
class UIAnalysis:
    content:      str
    mode:         OutputMode
    table_format: Optional[TableFormat]
    is_html:      bool = False


@dataclass
class UIFile:
    path:          Path
    relative_path: str
    file_type:     UIFileType
    id:            str          = field(default_factory=lambda: str(uuid.uuid4()))
    analysis:      Optional[UIAnalysis] = None
    is_analyzing:  bool         = False
    analyze_error: Optional[str] = None

    @property
    def name(self) -> str:
        return self.path.name
