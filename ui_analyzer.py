#!/usr/bin/env python3
"""
ui-analyzer — Describe a UI source file or screenshot for a blind developer.

Analysis goes to stdout. Progress notes go to stderr.
Pipe stdout to capture only the analysis; stderr shows what the tool is doing.

  python ui_analyzer.py <file-or-figma-url> [options]

BACKENDS
  auto    Try Ollama first; then OpenAI-compatible if key set; then Claude.  [default]
  ollama  Ollama local or cloud models (minimax-m3:cloud, gemma4, qwen2.5-coder, …)
  openai  Any OpenAI-compatible server — set OPENAI_API_KEY or use --openai-key
  claude  Anthropic Claude API — set ANTHROPIC_API_KEY first

OUTPUT MODES
  prose   6-section Markdown (default)
  table   Markdown elements table + layout table
  html    Accessible HTML5 document with tables and prose sections

FIGMA
  Pass a figma.com URL as the path argument.
  python ui_analyzer.py "https://www.figma.com/design/ABC/MyApp" --figma-token figd_...
  Or set FIGMA_TOKEN environment variable.

EXIT CODES
  0  Analysis complete
  1  Analysis or streaming error
  2  Invalid arguments or file not found
  3  Backend unavailable (Ollama not running, API key missing, Figma token missing)

EXAMPLES
  python ui_analyzer.py Views/LoginView.swift
  python ui_analyzer.py screenshot.png --backend openai --openai-key sk-...
  python ui_analyzer.py card.jsx --output-mode html -o card.html
  python ui_analyzer.py "https://www.figma.com/design/ABC/MyApp" --figma-token figd_...
  python ui_analyzer.py styles.css --backend openai --openai-url http://localhost:1234/v1
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ── Optional dependencies ────────────────────────────────────────────────────
try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

try:
    import anthropic as _anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False

try:
    import pytesseract
    from PIL import Image as _PILImage
    _HAS_OCR = True
except ImportError:
    _HAS_OCR = False


# ── Constants ─────────────────────────────────────────────────────────────────
DEFAULT_OLLAMA_URL    = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL  = "minimax-m3:cloud"
DEFAULT_OPENAI_URL    = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL  = "gpt-4o"
DEFAULT_CLAUDE_MODEL  = "claude-sonnet-4-6"
CONTENT_LIMIT         = 8_000

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".webp", ".tiff", ".bmp", ".gif"}

_SWIFTUI_SIGNALS   = (": View", "some View", "import SwiftUI")
_PYTHON_UI_SIGNALS = ("import tkinter", "from tkinter", "import wx", "from wx",
                       "import pyqt6", "from pyqt6", "import pyside6", "from pyside6",
                       "import kivy", "from kivy")
_JS_UI_SIGNALS     = ("React", "angular", "document.", "window.", "createElement")
_TS_UI_SIGNALS     = ("React", "angular", "@Component", "@NgModule")
_DESIGN_SPEC_SIGNALS = ("color palette", "typography", "spacing scale", "design token",
                         "color system", "visual system", "accessibility target",
                         "font stack", "border radius", "shadow")


# ── Output helpers ───────────────────────────────────────────────────────────
def _progress(msg: str, quiet: bool) -> None:
    if not quiet:
        print(f"[ui-analyzer] {msg}", file=sys.stderr, flush=True)


def _err(msg: str) -> None:
    print(f"[ui-analyzer] ERROR: {msg}", file=sys.stderr, flush=True)


# ── File type detection ──────────────────────────────────────────────────────
def detect_file_type(path: Path, content: str) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext == ".swift":
        return "swiftui" if any(s in content for s in _SWIFTUI_SIGNALS) else "swift"
    if ext in (".html", ".htm"):
        return "html"
    if ext == ".css":
        return "css"
    if ext in (".jsx", ".tsx"):
        return "react_jsx"
    if ext == ".vue":
        return "vue"
    if ext == ".svelte":
        return "svelte"
    if ext in (".storyboard", ".xib"):
        return ext[1:]
    if ext == ".py":
        lower = content.lower()
        return "python_ui" if any(s in lower for s in _PYTHON_UI_SIGNALS) else "unknown"
    if ext == ".js":
        return "react_jsx" if any(s in content for s in _JS_UI_SIGNALS) else "unknown"
    if ext == ".ts":
        return "react_jsx" if any(s in content for s in _TS_UI_SIGNALS) else "unknown"
    if ext in (".md", ".markdown"):
        return "markdown"
    return "unknown"


# ── Content loading ──────────────────────────────────────────────────────────
def truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    prefix = text[:limit]
    pos = prefix.rfind("\n\n")
    if pos > 0:
        return prefix[:pos], True
    pos = prefix.rfind("\n")
    if pos > 0:
        return prefix[:pos], True
    return prefix, True


def load_content(path: Path, file_type: str) -> tuple[str, bool]:
    if file_type == "image":
        return extract_image_text(path), False
    raw = path.read_text(encoding="utf-8", errors="replace")
    return truncate(raw, CONTENT_LIMIT)


def extract_image_text(path: Path) -> str:
    lines = [f"UI Screenshot: {path.name}"]
    if not _HAS_OCR:
        lines.append("[OCR not available — install pytesseract and Pillow for text extraction]")
        return "\n".join(lines)
    try:
        img = _PILImage.open(path)
        w, h = img.size
        lines.append(f"Dimensions: {w}x{h}px")
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        n = len(data["text"])
        detected = False
        for i in range(n):
            word = str(data["text"][i]).strip()
            if not word or int(data["conf"][i]) < 30:
                continue
            cx = (data["left"][i] + data["width"][i] / 2) / w
            cy = (data["top"][i] + data["height"][i] / 2) / h
            vert  = "top"    if cy < 0.20 else \
                    "upper"  if cy < 0.45 else \
                    "middle" if cy < 0.55 else \
                    "lower"  if cy < 0.80 else "bottom"
            horiz = "left"   if cx < 0.30 else \
                    "center" if cx < 0.70 else "right"
            lines.append(f"  [{vert}-{horiz}] {word}")
            detected = True
        if not detected:
            lines.append("No text detected by OCR.")
    except Exception as e:
        lines.append(f"OCR error: {e}")
    return "\n".join(lines)


# ── Contrast advisor ──────────────────────────────────────────────────────────

_HEX_RE = re.compile(r'#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b')


def _hex_luminance(hex_color: str) -> float:
    h = hex_color.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast_ratio(h1: str, h2: str) -> float:
    l1, l2 = _hex_luminance(h1), _hex_luminance(h2)
    lo, hi = min(l1, l2), max(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def contrast_report(source: str) -> str | None:
    """Pre-compute WCAG contrast ratios for literal hex colors in source.
    Returns a text block to inject into the analysis prompt, or None if
    fewer than two distinct colors are found."""
    colors = list(dict.fromkeys(_HEX_RE.findall(source)))
    if len(colors) < 2:
        return None
    lines = ["AUTOMATED CONTRAST PRE-COMPUTATION (cite these exact ratios — do not re-compute):"]
    checked = 0
    for i, c1 in enumerate(colors):
        for c2 in colors[i + 1:]:
            ratio = _contrast_ratio(c1, c2)
            aa_text = ratio >= 4.5
            aa_ui   = ratio >= 3.0
            status  = "AA PASS" if aa_text else ("3:1 UI PASS" if aa_ui else "AA FAIL")
            lines.append(f"  {c1} on {c2}: {ratio:.2f}:1 — {status}")
            checked += 1
            if checked >= 12:
                lines.append("  (additional pairs omitted — check remaining colors manually)")
                return "\n".join(lines)
    return "\n".join(lines) if checked else None


# ── Framework accessibility API references ────────────────────────────────────

_SWIFTUI_A11Y = """\
SWIFTUI ACCESSIBILITY API — suggest specific fixes in the Accessibility section:
• .accessibilityLabel("name") — VoiceOver name for any view
• .accessibilityHint("action") — describes what happens when activated
• .accessibilityHidden(true) — hides decorative views from VoiceOver
• .accessibilityAddTraits(.isHeader / .isButton / .isSelected / .isImage)
• .accessibilityElement(children: .combine) — merges children into one VoiceOver element
• @AccessibilityFocusState + .accessibilityFocused($focused) — programmatic focus
• .focusable() + .onKeyPress(.return) { action() } — keyboard activation (macOS)
• .frame(minWidth: 44, minHeight: 44) — WCAG 2.5.5 minimum touch target
• AccessibilityNotification.Announcement("text").post() — announce dynamic changes
• @Environment(\\.accessibilityReduceMotion) var reduceMotion — respect Reduce Motion"""

_REACT_A11Y = """\
REACT ACCESSIBILITY API — suggest specific fixes in the Accessibility section:
• <button> not <div onClick> — semantic HTML first (WCAG 4.1.2)
• aria-label="name" — accessible name when visible text is absent
• aria-describedby="id" — link element to its description
• aria-hidden="true" — hides decorative elements from screen readers
• aria-expanded / aria-selected / aria-checked — announce interactive state
• tabIndex={0} — makes custom element keyboard-focusable
• tabIndex={-1} + ref.current.focus() — programmatic focus management
• aria-live="polite" — announce dynamic content changes
• <label htmlFor="inputId"> — always link labels to inputs
• min-width: 44px; min-height: 44px — WCAG 2.5.5 touch target"""

_HTML_CSS_A11Y = """\
HTML/CSS ACCESSIBILITY — suggest specific fixes in the Accessibility section:
• Semantic elements: <button>, <a href>, <nav>, <main>, <header>, <footer>
• <img alt="description"> for meaningful images; alt="" for decorative
• <label for="inputId"> linked to every <input id="inputId">
• aria-label or aria-labelledby for elements without visible text
• role="alert" or aria-live="polite" — announce dynamic content
• :focus-visible { outline: 2px solid; } — visible keyboard focus indicator
• min-width: 44px; min-height: 44px — WCAG 2.5.5 touch target
• @media (prefers-reduced-motion: reduce) — disable animations
• <table> needs <caption>, <th scope="col">, <th scope="row">
• <dialog showModal()> — native accessible modal with automatic focus trap"""

_VUE_A11Y = """\
VUE.JS ACCESSIBILITY API — suggest specific fixes in the Accessibility section:
• :aria-label="label" — dynamic accessible names via v-bind
• :aria-expanded="isOpen" — update ARIA state dynamically
• ref="el" + this.$refs.el.focus() — programmatic focus management
• aria-live="polite" — announce dynamic content to screen readers
• <label :for="inputId"> — link labels to inputs
• :focus-visible { outline: 2px solid; } — visible focus ring"""

_REACT_NATIVE_A11Y = """\
REACT NATIVE ACCESSIBILITY API — suggest specific fixes in the Accessibility section:
• accessible={true} — marks a view as an accessibility element
• accessibilityLabel="name" — VoiceOver/TalkBack readable name
• accessibilityHint="action" — what happens when activated
• accessibilityRole="button" / "header" / "image" / "link"
• accessibilityState={{ disabled: true, selected: false, checked: true }}
• AccessibilityInfo.announceForAccessibility("msg") — programmatic announce
• hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }} — expand touch target
• minWidth: 44, minHeight: 44 — WCAG 2.5.5 minimum touch target"""

_PYQT_A11Y = """\
PYQT6/PYSIDE6 ACCESSIBILITY API — suggest specific fixes in the Accessibility section:
• widget.setAccessibleName("name") — AT-SPI/MSAA accessible name
• widget.setAccessibleDescription("hint") — accessible description
• QLabel.setBuddy(widget) — links label to input for screen readers
• widget.setFocusPolicy(Qt.FocusPolicy.TabFocus) — keyboard focus
• widget.setTabOrder(first, second) — explicit keyboard tab order
• QShortcut / QAction.setShortcut() — keyboard shortcut for actions"""

_TKINTER_A11Y = """\
TKINTER ACCESSIBILITY — suggest specific improvements in the Accessibility section:
• widget.configure(takefocus=True) — enable Tab focus
• Label(text="…") before Entry() — always provide visible labels
• widget.bind("<Return>", handler) — keyboard activation
• ttk widgets (ttk.Button, ttk.Entry, ttk.Combobox) — better accessibility
• focus_set() — programmatic keyboard focus management"""


def framework_api_ref(content: str, file_type: str) -> str:
    """Return the accessibility API cheat-sheet for the detected framework."""
    if 'import SwiftUI' in content:
        return _SWIFTUI_A11Y
    if 'react-native' in content.lower():
        return _REACT_NATIVE_A11Y
    if "from 'react'" in content or 'import React' in content:
        return _REACT_A11Y
    if "from 'vue'" in content or 'from "vue"' in content:
        return _VUE_A11Y
    if 'from PyQt6' in content or 'from PySide6' in content:
        return _PYQT_A11Y
    if 'import tkinter' in content or 'from tkinter' in content:
        return _TKINTER_A11Y
    if file_type in ('html', 'css'):
        return _HTML_CSS_A11Y
    if file_type in ('react_jsx', 'vue', 'svelte'):
        return _REACT_A11Y
    return ''


# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are a UI accessibility and visual design expert helping a blind developer \
understand what their UI looks like to sighted users.

HONESTY RULES — mandatory, never break them:

• Only report properties directly stated in the source code. \
Do not invent, assume, or guess values that are not explicitly written.
• COLORS: Only name a color and give a hex value if a literal color is in the code. \
If a color comes from a theme/token/environment, write: \
"Theme-provided — exact hex not available from this file alone." Never fabricate hex values.
• FONTS: Only name a font family if explicitly set in code. \
For .headline/.body/.footnote, write: "Default system text style — family not specified."
• REGIONS: Only describe a screen region if it appears in the code. \
Do not infer standard chrome that is not present.
• SPACING: Only give exact pt/px values that appear as literals.
• SF SYMBOLS: Image(systemName:) is an SF Symbol vector icon, never a photo. \
Write "SF Symbol icon: <name>".
• THEME TOKENS: Named property accessors are design tokens. Write the token name + \
"theme-provided — value not available from this file alone."

For every initial analysis, cover all five sections — never skip any:

## 1. Visual Appearance
Colors (literals only), typography, spacing, layout, icons/images. \
Cover: Colors, Typography, Spacing, Graphics & icons, Overall composition.

## 2. Ease of Use for Sighted Users
Is the visual hierarchy clear? Are interactive elements obviously tappable?

## 3. Professional Quality
Direct verdict — Polished / Mostly Polished / Needs Polish — with specific reasons.

## 4. Accessibility
WCAG AA contrast (only report ratios when both hex values are known). \
Touch/click targets (44x44pt min). Keyboard navigation. Labels present or missing. \
Tag each issue [cosmetic] or [design discussion].

## 5. Other Important Details
Animations, dark/light mode, error states, empty states, conditional UI.\
"""


# ── Prose prompt ──────────────────────────────────────────────────────────────

def build_user_prompt(content: str, path: Path, file_type: str,
                       spec_text: str | None, truncated: bool,
                       api_ref: str = '', contrast: str | None = None) -> str:
    if file_type == "image":
        prompt = (
            "Analyze this screenshot and describe what a sighted person sees.\n\n"
            f"{content}\n\n"
            "Describe: layout, visible UI elements and positions, text hierarchy, "
            "color impression, interactive elements, professional quality, and accessibility concerns."
        )
        if spec_text:
            prompt += _spec_check_suffix(spec_text)
        return prompt

    if file_type == "markdown":
        lower = content.lower()
        is_spec = any(s in lower for s in _DESIGN_SPEC_SIGNALS)
        if is_spec:
            prompt = (
                f"Analyze this design specification document: {path.name}\n\n"
                f"```\n{content}\n```\n\n"
                "Cover five sections:\n"
                "## 1. Color System\n"
                "Every literal hex/rgb: name, hex, WCAG contrast. 'No literal hex in spec' if absent.\n"
                "## 2. Typography\nFont families, weights, sizes, line-heights. 'Not specified' where absent.\n"
                "## 3. Spacing & Layout\nEvery literal spacing value with unit and usage. Rhythm verdict.\n"
                "## 4. Components & Patterns\nKey UI components and their visual rules.\n"
                "## 5. Accessibility Decisions\nEvery WCAG/accessibility requirement stated."
            )
        else:
            prompt = f"Analyze this document: {path.name}\n\n```\n{content}\n```"
        if spec_text:
            prompt += _spec_check_suffix(spec_text)
        return prompt

    trunc_note = (
        "\n[Source truncated — only the first portion is shown. "
        "Only describe what is present above. Do not infer or invent content from the unshown remainder.]\n"
        if truncated else ""
    )
    extras = ''
    if api_ref:
        extras += api_ref + '\n\n'
    if contrast:
        extras += contrast + '\n\n'
    prompt = f"Analyze this UI source file: {path.name} ({file_type})\n\n{extras}```\n{content}\n```{trunc_note}"
    if spec_text:
        prompt += _spec_check_suffix(spec_text)
    return prompt


def _spec_check_suffix(spec_text: str) -> str:
    return (
        "\n\n---\n\n"
        "VISUAL STANDARDS CHECK\n"
        "For each rule, state PASS / FAIL / CANNOT DETERMINE and cite the specific "
        "element, value, or absence that leads to your verdict. "
        "Add a '## 6. Visual Standards Check' section covering every rule.\n\n"
        + spec_text
    )


# ── Table and HTML prompts ────────────────────────────────────────────────────

def _spec_suffix(spec_text: str | None) -> str:
    if not spec_text:
        return ''
    return (
        "\n\n---\n\nVISUAL STANDARDS CHECK\n"
        "For each rule, state PASS / FAIL / CANNOT DETERMINE and cite the specific "
        "element, value, or absence that leads to your verdict. "
        "Add a '## 6. Visual Standards Check' section covering every rule.\n\n"
        + spec_text
    )


def build_table_prompt(content: str, path: Path, file_type: str,
                        spec_text: str | None, truncated: bool,
                        api_ref: str = '', contrast: str | None = None) -> str:
    trunc_note = (
        "\n[Source truncated — only the first portion shown. "
        "Only describe what is present above.]\n" if truncated else ""
    )
    extras = ''
    if api_ref:
        extras += api_ref + '\n\n'
    if contrast:
        extras += contrast + '\n\n'

    return f"""File: {path.name} ({file_type})

{extras}Write a brief summary paragraph first. Cover: concrete visual facts (colors, layout, fonts if set), sighted usability, professional quality verdict, most actionable accessibility findings, then anything requiring judgment.

Then produce a Markdown elements table for every UI element in the source.
Columns: | Element | Label / Text | Color Name | Hex | Position | Font (family/weight/size) | Image / Icon | Spacing / Size | Notes |
For light/dark mode files use: | Element | Label/Text | Color—Light | Hex—Light | Color—Dark | Hex—Dark | Position | Font | Image/Icon | Spacing/Size | Notes |

COLOR RULE — never invent hex. Write the literal hex or "No literal color in source".
FONT RULE — only write font if explicitly set; otherwise "not specified".
IMAGE/ICON RULE — list every Image("…") / <img> / SF Symbol with size. Write "—" if none.
SPACING RULE — only literal values (.padding(16), gap: 8). Otherwise "not specified".
ROW RULE — every visible element gets one row. Never leave a cell blank — write "not in code".
CONTRAST RULE — if any row sets a foreground color, add a contrast note in Notes: e.g. "#1C1C1E on #FFFFFF = 15.8:1 (AA pass)".

Then produce a Markdown layout table:
| Region | Position | Elements | What a Sighted User Sees |
Only name a region if the source defines it (TabView, NavigationStack, <nav>, <header>, etc.).

```
{content}
```{trunc_note}{_spec_suffix(spec_text)}"""


def build_html_prompt(content: str, path: Path, file_type: str,
                       spec_text: str | None, truncated: bool,
                       api_ref: str = '', contrast: str | None = None) -> str:
    trunc_note = (
        "\n[Source truncated — only the first portion shown.]\n" if truncated else ""
    )
    extras = ''
    if api_ref:
        extras += api_ref + '\n\n'
    if contrast:
        extras += contrast + '\n\n'

    return f"""File: {path.name} ({file_type})

{extras}Analyse the source code below and write a complete HTML5 document.

Start with a single <h1> that names the screen or page (e.g. <h1>Settings Screen</h1>). This is the first thing VoiceOver announces — make it descriptive.

Immediately after the <h1>, write one <details class="tldr" open> element. Its child <summary class="tldr-summary"> must read exactly: "TL;DR — Key findings". Inside a <div class="tldr-body"><p> write 3-5 sentences covering: (1) most important visual characteristic grounded in the source, (2) professional quality verdict (Polished / Mostly Polished / Needs Polish) with strongest reason, (3) most important accessibility finding, (4) what cannot be determined from this file alone.

PART 1 — Write five <section> elements each with an <h2> and aria-labelledby pointing to that <h2>:
IDs and headings: h-visual "Visual Appearance", h-usability "Ease of Use for Sighted Users", h-quality "Professional Quality", h-a11y "Accessibility", h-other "Other Important Details".
Each section: one <p> with 2-4 real sentences drawn from the code only. In Visual Appearance, name the text color, background color, and their WCAG contrast ratio.

PART 2 — Write <h2 id="h-elements">UI Elements</h2> then an accessible table:
• table must have aria-labelledby="h-elements"
• <caption> inside the <table> naming the screen
• Every column header: <th scope="col">
• First cell of every data row: <th scope="row">
• Columns: Element, Label/Text, Color Name, Hex, Position, Font (family/weight/size), Image/Icon, Spacing/Size, Notes
• For light/dark mode files use Color-Light, Hex-Light, Color-Dark, Hex-Dark columns instead
• COLOR RULE: never invent hex. Write literal hex or "No literal color in source".
• FONT RULE: only write a font if explicitly set; otherwise "not specified".
• IMAGE RULE: list every image/icon reference with size. Write "—" if no image.
• CONTRAST RULE: if a row sets a foreground color, add a contrast note in Notes.
• After the table, write one <p> WCAG summary: list any failing pairs or "All foreground/background pairs pass WCAG AA (4.5:1)."

PART 3 — Write <h2 id="h-layout">Screen Layout</h2> then a table with aria-labelledby="h-layout":
• Columns: Region, Position, Elements, What a Sighted User Sees
• Region column: <th scope="row"> in every data row
• Only name a region if the source defines it (TabView, NavigationStack, <nav>, <header>, etc.)

Include this <style> in <head>:
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-size:14px;line-height:1.6;color:#1c1c1e;background:#fff;margin:16px}}
h1{{font-size:18px;font-weight:700;margin:0 0 16px;color:#1c1c1e}}
h2{{font-size:16px;font-weight:700;margin:24px 0 8px;color:#1c1c1e;border-bottom:1px solid #8e8e93;padding-bottom:4px}}
section{{margin-bottom:4px}}p{{margin:0 0 8px}}
table{{border-collapse:collapse;width:100%;margin-bottom:28px}}
caption{{text-align:left;font-weight:600;font-size:13px;padding:0 0 6px;color:#3a3a3c}}
th{{background:#f2f2f7;font-weight:600;text-align:left;padding:8px 12px;border:1px solid #8e8e93;color:#1c1c1e}}
td{{padding:8px 12px;border:1px solid #8e8e93;vertical-align:top;color:#1c1c1e}}
tr:nth-child(even) td{{background:#ededf0}}
details.tldr{{border:1px solid #d2d2d7;border-radius:10px;margin-bottom:20px}}
details.tldr[open]{{padding-bottom:8px}}
summary.tldr-summary{{font-weight:600;font-size:15px;padding:12px 14px;cursor:pointer;list-style:none;display:flex;align-items:center;gap:8px;border-radius:10px}}
summary.tldr-summary::before{{content:"▶";font-size:10px;transition:transform .15s;flex-shrink:0}}
details.tldr[open] summary.tldr-summary::before{{transform:rotate(90deg)}}
summary.tldr-summary:focus-visible{{outline:3px solid Highlight;outline-offset:2px;border-radius:8px}}
.tldr-body{{padding:4px 14px 6px}}
a:focus-visible{{outline:3px solid Highlight;outline-offset:2px}}
@media(prefers-color-scheme:dark){{body{{color:#f2f2f7;background:#1c1c1e}}h1,h2{{color:#f2f2f7}}h2{{border-bottom-color:#8e8e93}}caption{{color:#ebebf5}}th{{background:#2c2c2e;border-color:#8e8e93;color:#f2f2f7}}td{{border-color:#8e8e93;color:#f2f2f7}}tr:nth-child(even) td{{background:#38383a}}details.tldr{{border-color:#38383a}}}}
@media(prefers-contrast:more){{body{{color:#000;background:#fff}}h2{{border-bottom-color:#000}}th{{background:#fff;border-color:#000;border-width:2px;color:#000}}td{{border-color:#000;border-width:2px;color:#000}}tr:nth-child(even) td{{background:#fff}}details.tldr{{border-color:currentColor;border-width:2px}}}}

Start with <!DOCTYPE html>. Output ONLY the HTML — nothing before the doctype, nothing after </html>.

```
{content}
```{trunc_note}{_spec_suffix(spec_text)}"""


# ── Ollama backend ───────────────────────────────────────────────────────────
def ollama_probe(base_url: str) -> list[str] | None:
    """Returns installed model names, or None if Ollama is unreachable.
    Retries against 127.0.0.1 if localhost fails — macOS resolves localhost
    to ::1 (IPv6) first but Ollama typically only binds to 127.0.0.1 (IPv4)."""
    if not _HAS_HTTPX:
        return None

    def _probe_once(url: str) -> list[str] | None:
        try:
            r = httpx.get(f"{url}/api/tags", timeout=3)
            r.raise_for_status()
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return None

    result = _probe_once(base_url)
    if result is not None:
        return result
    if 'localhost' in base_url:
        ipv4_url = base_url.replace('localhost', '127.0.0.1')
        return _probe_once(ipv4_url)
    return None


def ollama_stream(base_url: str, model: str, system: str, user: str):
    if not _HAS_HTTPX:
        raise RuntimeError("httpx not installed. Run: pip install httpx")
    payload = {
        "model": model,
        "stream": True,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    }
    with httpx.stream("POST", f"{base_url}/api/chat", json=payload, timeout=120) as resp:
        if resp.status_code != 200:
            raise RuntimeError(
                f"Ollama returned HTTP {resp.status_code}. "
                "Check model name and that Ollama is running."
            )
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
                text = chunk.get("message", {}).get("content", "")
                if text:
                    yield text
                if chunk.get("done"):
                    break
            except json.JSONDecodeError:
                continue


# ── OpenAI-compatible backend ─────────────────────────────────────────────────

def openai_stream(base_url: str, model: str, api_key: str, system: str, user: str):
    """Stream from any OpenAI-compatible /v1/chat/completions endpoint.
    Works with OpenAI, Codex, LM Studio, LocalAI, Ollama /v1, and more.
    api_key may be empty for local servers that require no authentication."""
    if not _HAS_HTTPX:
        raise RuntimeError("httpx not installed. Run: pip install httpx")
    url = base_url.rstrip('/') + '/chat/completions'
    headers: dict[str, str] = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    payload = {
        'model': model,
        'stream': True,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user',   'content': user},
        ],
    }
    with httpx.stream('POST', url, headers=headers, json=payload, timeout=300) as resp:
        if resp.status_code != 200:
            raise RuntimeError(
                f"OpenAI-compatible API returned HTTP {resp.status_code}. "
                "Check --openai-url, API key, and model name."
            )
        for line in resp.iter_lines():
            if not line or not line.startswith('data: '):
                continue
            payload_str = line[6:]
            if payload_str.strip() == '[DONE]':
                break
            try:
                chunk = json.loads(payload_str)
                text = (chunk.get('choices', [{}])[0]
                             .get('delta', {})
                             .get('content', ''))
                if text:
                    yield text
            except json.JSONDecodeError:
                continue


# ── Claude API backend ───────────────────────────────────────────────────────
def claude_stream(model: str, api_key: str, system: str, user: str):
    if not _HAS_ANTHROPIC:
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic")
    client = _anthropic.Anthropic(api_key=api_key)
    with client.messages.stream(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        for text in stream.text_stream:
            yield text


# ── Figma support ─────────────────────────────────────────────────────────────

def is_figma_url(s: str) -> bool:
    """Returns True when the string is a Figma design/file/proto URL."""
    lower = s.lower()
    return ('figma.com/design/' in lower or
            'figma.com/file/'   in lower or
            'figma.com/proto/'  in lower)


def figma_fetch(url_str: str, token: str) -> str:
    """Fetch a Figma design file via REST API and return descriptive text.
    Raises RuntimeError with a user-friendly message on failure."""
    if not _HAS_HTTPX:
        raise RuntimeError("httpx not installed. Run: pip install httpx")

    match = re.search(r'figma\.com/(?:design|file|proto)/([A-Za-z0-9_-]+)', url_str)
    if not match:
        raise RuntimeError(f"Cannot extract Figma file key from: {url_str}")
    file_key = match.group(1)

    resp = httpx.get(
        f"https://api.figma.com/v1/files/{file_key}",
        headers={"X-Figma-Token": token},
        timeout=30
    )
    if resp.status_code == 403:
        raise RuntimeError(
            "Figma returned 403 Forbidden. "
            "Check your --figma-token or FIGMA_TOKEN value."
        )
    if resp.status_code == 404:
        raise RuntimeError(
            "Figma file not found. "
            "Verify the URL and that your token has access to this file."
        )
    resp.raise_for_status()
    return _figma_to_text(resp.json())


def _figma_to_text(data: dict) -> str:
    """Convert Figma API JSON to a descriptive text summary for the model."""
    lines: list[str] = []
    name = data.get('name', 'Unknown')
    lines.append(f"Figma File: {name}")

    components = data.get('components', {})
    if components:
        lines.append(f"\nComponent library: {len(components)} components")
        for cid, comp in list(components.items())[:20]:
            desc = comp.get('description', '').strip()
            lines.append(f"  - {comp.get('name', cid)}" + (f": {desc}" if desc else ""))

    styles = data.get('styles', {})
    if styles:
        lines.append(f"\nStyles: {len(styles)} named styles")
        for sid, style in list(styles.items())[:20]:
            lines.append(f"  - {style.get('name', sid)} ({style.get('styleType', '')})")

    doc = data.get('document', {})
    pages = doc.get('children', [])
    lines.append(f"\nPages: {len(pages)}")
    for page in pages[:10]:
        page_name = page.get('name', 'Unnamed')
        frames = [c for c in page.get('children', []) if c.get('type') == 'FRAME']
        lines.append(f"\n  Page: {page_name} ({len(frames)} frames)")
        for frame in frames[:10]:
            children = frame.get('children', [])
            lines.append(f"    Frame: {frame.get('name', 'Unnamed')} ({len(children)} children)")
            for child in children[:12]:
                ctype = child.get('type', '')
                cname = child.get('name', '')
                chars = child.get('characters', '')
                detail = f" — \"{chars[:60]}\"" if chars else ""
                lines.append(f"      {ctype}: {cname}{detail}")

    return '\n'.join(lines)


def build_figma_prompt(content: str) -> str:
    """Analysis prompt for Figma design files."""
    return f"""This is a Figma design file summary (extracted via the Figma REST API).

Analyse it using these five sections — ignore the default prose format:

## 1. Overview
Describe the product, how many pages/screens it has, and its overall design direction.

## 2. Visual Language
Describe the color palette (every color name + hex if present), typography system \
(font families, sizes, weights), and spacing/layout approach.

## 3. Screen-by-Screen Description
For each page and frame: what the screen does, what a sighted user sees, \
how it connects to other screens.

## 4. Component Library
Describe the component library: how many components, key patterns, naming conventions.

## 5. Accessibility Assessment
Based on color names, component structure, and naming conventions: \
likely contrast quality, whether components appear keyboard-accessible, \
red flags (color-only indicators, icon-only buttons without names, \
missing alt text patterns).

Figma file data:
{content}"""


# ── Main ─────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ui-analyzer",
        description="Describe a UI source file, screenshot, or Figma URL for a blind developer.",
        epilog=(
            "Analysis goes to stdout; progress goes to stderr.\n"
            "Pipe stdout to capture only the analysis.\n\n"
            "Backends: auto (default), ollama, openai, claude\n"
            "Output modes: prose (default), table, html\n\n"
            "Exit codes: 0=success  1=analysis error  2=bad args/file  3=backend unavailable"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path",
        help="UI source file, screenshot, or Figma URL to analyze.",
    )
    parser.add_argument(
        "--backend", choices=["auto", "ollama", "openai", "claude"], default="auto",
        help="AI backend: auto (default), ollama, openai, claude.",
    )
    parser.add_argument(
        "--model", default="",
        help=(
            f"Model name. Ollama: e.g. minimax-m3:cloud, gemma4. "
            f"OpenAI: e.g. gpt-4o. Claude: e.g. claude-sonnet-4-6. "
            f"Defaults per backend are set automatically."
        ),
    )
    parser.add_argument(
        "--ollama-url", default=DEFAULT_OLLAMA_URL, metavar="URL",
        help=f"Ollama base URL. (default: {DEFAULT_OLLAMA_URL})",
    )
    parser.add_argument(
        "--openai-url", default=DEFAULT_OPENAI_URL, metavar="URL",
        help=f"Base URL for OpenAI-compatible API. (default: {DEFAULT_OPENAI_URL})",
    )
    parser.add_argument(
        "--openai-key", default="", metavar="KEY",
        help="OpenAI-compatible API key. Also reads OPENAI_API_KEY env var.",
    )
    parser.add_argument(
        "--claude-key", default="", metavar="KEY",
        help="Anthropic API key. Also reads ANTHROPIC_API_KEY env var.",
    )
    parser.add_argument(
        "--output-mode", choices=["prose", "table", "html"], default="prose",
        help="Output format: prose (default), table (Markdown), html (accessible HTML5).",
    )
    parser.add_argument(
        "--figma-token", default="", metavar="TOKEN",
        help="Figma Personal Access Token. Also reads FIGMA_TOKEN env var.",
    )
    parser.add_argument(
        "--spec", default=None, metavar="FILE",
        help="Visual standards spec file (Markdown). Rules are checked against the UI file.",
    )
    parser.add_argument(
        "--output", "-o", default=None, metavar="FILE",
        help="Write analysis to FILE instead of stdout.",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress [ui-analyzer] progress lines on stderr.",
    )
    parser.add_argument(
        "--list-models", action="store_true",
        help="List installed Ollama models and exit.",
    )

    args = parser.parse_args(argv)
    quiet: bool = args.quiet

    def info(msg: str) -> None:
        _progress(msg, quiet)

    # ── --list-models ────────────────────────────────────────────────────────
    if args.list_models:
        models = ollama_probe(args.ollama_url)
        if models is None:
            _err(f"Ollama not available at {args.ollama_url}")
            _err("Start Ollama with: ollama serve")
            return 3
        if models:
            print("\n".join(models))
        else:
            print("No models installed.")
        return 0

    path_str: str    = args.path
    output_mode: str = args.output_mode
    figma_token: str = args.figma_token or os.environ.get("FIGMA_TOKEN", "")
    openai_key: str  = args.openai_key  or os.environ.get("OPENAI_API_KEY", "")
    claude_key: str  = args.claude_key  or os.environ.get("ANTHROPIC_API_KEY", "")

    spec_text: str | None = None
    content: str          = ""
    file_type: str        = ""
    truncated: bool       = False
    api_ref: str          = ""
    contrast: str | None  = None
    path: Path            = Path(".")

    # ── Figma URL path ────────────────────────────────────────────────────────
    if is_figma_url(path_str):
        if not figma_token:
            _err("Figma token required.")
            _err("  Pass it:  --figma-token figd_...")
            _err("  Or set:   export FIGMA_TOKEN=figd_...")
            return 3
        info(f"Figma: {path_str}")
        info("Fetching design file…")
        try:
            content = figma_fetch(path_str, figma_token)
        except RuntimeError as e:
            _err(str(e))
            return 1
        info(f"Figma file fetched ({len(content)} chars)")
        file_type = 'figma'
        path      = Path("figma_file.txt")

    else:
        # ── Local file path ───────────────────────────────────────────────────
        path = Path(path_str)
        if not path.exists():
            _err(f"File not found: {path}")
            return 2
        if path.is_dir():
            _err("Path is a directory. Pass a specific file, not a folder.")
            return 2

        ext = path.suffix.lower()
        if ext in IMAGE_EXTS:
            file_type = "image"
            content, truncated = load_content(path, "image")
        else:
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                _err(f"Cannot read {path}: {e}")
                return 2
            file_type = detect_file_type(path, raw)
            content, truncated = truncate(raw, CONTENT_LIMIT)

        info(f"File: {path.name} ({file_type})")
        if truncated:
            info("Large file — source truncated to first portion.")

        # ── Load spec ────────────────────────────────────────────────────────
        if args.spec:
            spec_path = Path(args.spec)
            if not spec_path.exists():
                _err(f"Spec file not found: {args.spec}")
                return 2
            spec_text = spec_path.read_text(encoding="utf-8", errors="replace")
            rule_count = sum(1 for line in spec_text.splitlines() if line.strip().startswith("- "))
            info(f"Spec: {spec_path.name} ({rule_count} rules)")

        skip_extras = file_type == 'image'
        api_ref  = '' if skip_extras else framework_api_ref(content, file_type)
        contrast = None if skip_extras else contrast_report(content)

    # ── Build prompt ─────────────────────────────────────────────────────────
    if file_type == 'figma':
        user_prompt = build_figma_prompt(content)
    elif output_mode == "table":
        user_prompt = build_table_prompt(content, path, file_type, spec_text, truncated,
                                          api_ref=api_ref, contrast=contrast)
    elif output_mode == "html":
        user_prompt = build_html_prompt(content, path, file_type, spec_text, truncated,
                                         api_ref=api_ref, contrast=contrast)
    else:
        user_prompt = build_user_prompt(content, path, file_type, spec_text, truncated,
                                         api_ref=api_ref, contrast=contrast)

    # ── Resolve backend ──────────────────────────────────────────────────────
    backend: str = args.backend
    if backend == "auto":
        if ollama_probe(args.ollama_url) is not None:
            backend = "ollama"
        elif openai_key:
            backend = "openai"
            info("Ollama not available — using OpenAI-compatible API.")
        elif claude_key:
            backend = "claude"
            info("Ollama not available — using Claude API.")
        else:
            _err("No backend available.")
            _err("  Start Ollama:  ollama serve")
            _err("  Or set key:    export OPENAI_API_KEY=sk-...  (or ANTHROPIC_API_KEY)")
            return 3

    model: str = args.model or {
        "ollama": DEFAULT_OLLAMA_MODEL,
        "openai": DEFAULT_OPENAI_MODEL,
        "claude": DEFAULT_CLAUDE_MODEL,
    }.get(backend, "")
    info(f"Backend: {backend} ({model})")
    info("Analyzing…")

    # ── Stream output ────────────────────────────────────────────────────────
    collected_parts: list[str] = []
    write_to_file = args.output is not None

    try:
        if backend == "ollama":
            stream = ollama_stream(args.ollama_url, model, _SYSTEM_PROMPT, user_prompt)
        elif backend == "openai":
            stream = openai_stream(args.openai_url, model, openai_key,
                                   _SYSTEM_PROMPT, user_prompt)
        else:  # claude
            if not claude_key:
                _err("ANTHROPIC_API_KEY not set.")
                _err("  Mac/Linux: export ANTHROPIC_API_KEY=sk-ant-...")
                _err("  Or pass:   --claude-key sk-ant-...")
                return 3
            stream = claude_stream(model, claude_key, _SYSTEM_PROMPT, user_prompt)

        for chunk in stream:
            collected_parts.append(chunk)
            if not write_to_file:
                print(chunk, end="", flush=True)

        if not write_to_file:
            print()

    except RuntimeError as e:
        _err(str(e))
        return 3
    except KeyboardInterrupt:
        if not write_to_file:
            print()
        _err("Interrupted.")
        return 1
    except Exception as e:
        _err(f"Analysis failed: {e}")
        return 1

    # ── Write output file ────────────────────────────────────────────────────
    if write_to_file:
        full = "".join(collected_parts)
        out_path = Path(args.output)
        try:
            out_path.write_text(full, encoding="utf-8")
            info(f"Written to {args.output}")
        except OSError as e:
            _err(f"Cannot write {args.output}: {e}")
            return 1

    info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
