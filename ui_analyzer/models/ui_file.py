from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class VisionMode(Enum):
    NOT_ATTACHED = "not_attached"
    MULTIMODAL   = "multimodal"   # model receives raw image bytes
    OCR_TEXT     = "ocr_text"     # text-only model, OCR transcript injected

    @property
    def label(self) -> str:
        return {
            VisionMode.NOT_ATTACHED: "Text only",
            VisionMode.MULTIMODAL:   "Multimodal — model sees the image",
            VisionMode.OCR_TEXT:     "OCR fallback — model reads text approximation",
        }[self]


@dataclass
class ValidationClaim:
    text: str


@dataclass
class ValidationRetraction:
    text: str
    original_index: Optional[int] = None  # 1-based paragraph number


@dataclass
class ValidationResult:
    """Structured result of a 'Validate against screenshot' pass."""
    stands_by: list[ValidationClaim]
    retracts:  list[ValidationRetraction]
    additions: list[ValidationClaim]


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
    is_html:      bool             = False
    vision_mode:  VisionMode       = VisionMode.NOT_ATTACHED
    validation:   Optional[ValidationResult] = None


@dataclass
class UIFile:
    path:          Path
    relative_path: str
    file_type:     UIFileType
    folder_path:   Optional[Path]   = None   # root of the scanned folder
    id:            str              = field(default_factory=lambda: str(uuid.uuid4()))
    analysis:      Optional[UIAnalysis]    = None
    is_analyzing:  bool             = False
    analyze_error: Optional[str]    = None
    is_validating: bool             = False
    validate_error: Optional[str]   = None
    # Relative path (from folder_path) of an attached screenshot, e.g.
    # "loginView.swift.context.png". None = no attachment.
    attached_image_path: Optional[str] = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def screenshot_abs_path(self) -> Optional[Path]:
        """Resolve the attached screenshot to an absolute path, or None."""
        if self.attached_image_path and self.folder_path:
            return self.folder_path / self.attached_image_path
        return None
