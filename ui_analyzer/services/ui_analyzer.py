"""UI analysis engine — prompt building, session management, streaming."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Generator, Optional

import base64
import json

from ui_analyzer.models.ui_file import (
    UIFile, UIFileType, UIAnalysis, OutputMode, TableFormat,
    VisionMode, ValidationResult, ValidationClaim, ValidationRetraction,
)
from ui_analyzer.services.ai_client import AIClient
from ui_analyzer.services.contrast_advisor import contrast_report

# ── Image OCR (optional — degrades gracefully if not installed) ───────────────
try:
    from PIL import Image as PILImage
    import pytesseract
    _HAS_OCR = True
except ImportError:
    _HAS_OCR = False


# ── Framework accessibility API references ────────────────────────────────────

_SWIFTUI_APIS = """
SWIFTUI 6.2 ACCESSIBILITY API REFERENCE — suggest specific fixes in the Accessibility section:
• .accessibilityLabel("name") — sets the VoiceOver name for any view
• .accessibilityHint("action") — describes what happens when activated
• .accessibilityHidden(true) — hides decorative views from VoiceOver
• .accessibilityAddTraits(.isHeader / .isButton / .isSelected / .isImage)
• .accessibilityElement(children: .combine) — merges children into one VoiceOver element
• @AccessibilityFocusState var focused: Bool — programmatic focus control
• .focusable() + .onKeyPress(.return) { action() } — keyboard activation (macOS)
• Image(decorative: name) or .accessibilityHidden(true) — decorative images
• .accessibilityValue("text") — current value for sliders, steppers, progress
• .frame(minWidth: 44, minHeight: 44) — minimum touch/click target (WCAG 2.5.5)
• AccessibilityNotification.Announcement("text").post() — announce dynamic changes
""".strip()

_REACT_APIS = """
REACT / JSX ACCESSIBILITY API REFERENCE — suggest specific fixes in the Accessibility section:
• <button> not <div onClick> — use semantic HTML elements first (WCAG 4.1.2)
• aria-label="name" — sets the accessible name when visible text is absent
• aria-describedby="id" — links an element to its description
• aria-hidden="true" — hides decorative elements from screen readers
• role="heading" aria-level="2" — mark headings when not using <h2>
• aria-expanded / aria-selected / aria-checked — interactive state
• tabIndex={0} — makes a non-interactive element focusable
• useRef + ref.current.focus() — programmatic focus management
• aria-live="polite" — announce dynamic content changes
• <label htmlFor="id"> — always link labels to inputs
• <img alt="description"> or alt="" for decorative images
• onKeyDown + event.key — handle keyboard alongside onClick
• min-width: 44px; min-height: 44px — WCAG 2.5.5 touch target
""".strip()

_REACT_NATIVE_APIS = """
REACT NATIVE ACCESSIBILITY API REFERENCE — suggest specific fixes in the Accessibility section:
• accessible={true} — marks a view as an accessibility element
• accessibilityLabel="name" — VoiceOver / TalkBack readable name
• accessibilityHint="action description" — what happens when activated
• accessibilityRole="button" / "header" / "image" / "link"
• accessibilityState={{ disabled, selected, checked }}
• accessibilityValue={{ min, max, now, text }} — for sliders and progress
• importantForAccessibility="no" — hides from TalkBack (Android)
• accessibilityElementsHidden={true} — hides from VoiceOver (iOS)
• AccessibilityInfo.announceForAccessibility("message") — programmatic announce
• hitSlop={{ top:10, bottom:10, left:10, right:10 }} — expand touch target
• min-width: 44, min-height: 44 — WCAG 2.5.5 minimum touch target
""".strip()

_VUE_APIS = """
VUE.JS ACCESSIBILITY API REFERENCE — suggest specific fixes in the Accessibility section:
• Use semantic HTML in <template>: <button>, <a>, <label>, <nav>, <main>, <header>
• :aria-label="label" or aria-label="text" — dynamic/static accessible names
• :aria-expanded="isOpen" — update ARIA state dynamically with v-bind
• ref="el" + this.$refs.el.focus() — programmatic focus management
• <label :for="inputId"><input :id="inputId"> — always link labels to inputs
• aria-live="polite" wrapper + v-model — announce dynamic content
• @media (prefers-reduced-motion: reduce) — disable transitions/animations
• min-width: 44px; min-height: 44px — WCAG 2.5.5 touch target size
• :focus-visible { outline: 2px solid; } — never remove focus ring
""".strip()

_HTML_CSS_APIS = """
HTML / CSS ACCESSIBILITY CHECKLIST — suggest specific fixes in the Accessibility section:
• Use semantic elements: <button>, <a href>, <nav>, <main>, <header>, <footer>
• <img alt="description"> for meaningful images; alt="" for decorative
• <label for="inputId"> linked to every <input id="inputId">
• aria-label or aria-labelledby for elements without visible text
• role="alert" or aria-live="polite" — announce dynamic content updates
• tabindex="0" makes custom elements keyboard-focusable
• :focus-visible { outline: 2px solid; } — visible keyboard focus indicator
• color contrast: text 4.5:1, UI components 3:1 (WCAG 1.4.3/1.4.11)
• min-width: 44px; min-height: 44px — WCAG 2.5.5 touch target
• @media (prefers-reduced-motion: reduce) — disable animations for motion sensitivity
• @media (prefers-color-scheme: dark) — support system dark mode
• <dialog showModal()> — native modal with automatic focus trap
""".strip()

_PYQT_APIS = """
PYQT6 / PYSIDE6 ACCESSIBILITY API REFERENCE — suggest specific fixes in the Accessibility section:
• widget.setAccessibleName("name") — sets the AT-SPI / MSAA accessible name
• widget.setAccessibleDescription("hint") — accessible description
• QLabel with setBuddy(widget) — links label to input for screen readers
• widget.setFocusPolicy(Qt.FocusPolicy.TabFocus) — enable keyboard focus
• widget.setTabOrder(first, second) — set keyboard tab order explicitly
• QShortcut / QAction.setShortcut() — keyboard shortcuts for actions
• setStyleSheet with min-width/min-height >= 44px — touch target size
""".strip()

_TKINTER_APIS = """
TKINTER ACCESSIBILITY NOTES — suggest specific improvements in the Accessibility section:
• widget.configure(takefocus=True) — enable keyboard Tab focus
• Label(text="...").pack() before Entry() — always provide visible labels
• widget.bind("<Return>", handler) — handle keyboard activation
• widget.bind("<space>", handler) — space bar activation for button-like widgets
• messagebox.showinfo() — announce status changes
• ttk.Combobox / ttk.Spinbox — prefer ttk widgets (better platform accessibility)
• focus_set() — programmatic keyboard focus management
""".strip()

_WXPYTHON_APIS = """
WXPYTHON ACCESSIBILITY API REFERENCE — suggest specific fixes in the Accessibility section:
• widget.SetLabel("descriptive name") — accessible name for buttons and controls
• widget.SetName("name") — additional accessible identifier
• widget.SetToolTip("hint") — hover/screen reader hint
• wx.StaticText label placed before wx.TextCtrl — screen readers announce label+field together
• wx.Button — always provide a descriptive label, not just an icon
• widget.SetFocusFromKbd() — programmatic keyboard focus
• wx.AcceleratorTable — define keyboard shortcuts for the frame
• wx.StatusBar.SetStatusText() — status updates read by some screen readers
• wx.EVT_CHAR / wx.EVT_KEY_DOWN — handle keyboard interaction on custom controls
• Subclass wx.Accessible — implement custom accessibility for custom-drawn controls
• Minimum button size: at least 44×44 logical pixels (WCAG 2.5.5)
""".strip()


_WINFORMS_APIS = """
WINFORMS (.NET) ACCESSIBILITY API REFERENCE — suggest specific fixes in the Accessibility section:
• control.AccessibleName = "name" — sets the UIA accessible name (read by Narrator / NVDA)
• control.AccessibleDescription = "hint" — accessible description
• control.AccessibleRole = AccessibleRole.Button / Text / … — UIA role hint
• control.TabIndex = 0 — keyboard tab order
• control.TabStop = true — include in tab sequence
• control.IsAccessible = true (default true) — expose to assistive technology
• Label + associate with input: label.UseCompatibleTextRendering + focus-on-click → TextBox
• control.MinimumSize = new Size(44, 44) — minimum touch/click target (WCAG 2.5.5)
• ToolTip control — hover hint (also announced by screen readers in scan mode)
• KeyDown / KeyPress events — handle keyboard activation alongside Click
• Use AccessibleObject on the form — provide a custom IAccessible for custom-drawn controls
• Prefer System.Windows.Forms.Button over a clickable Panel/TableLayoutPanel
""".strip()


_WPF_APIS = """
WPF (.NET) ACCESSIBILITY API REFERENCE — suggest specific fixes in the Accessibility section:
• AutomationProperties.Name="name" — sets the UIA accessible name
• AutomationProperties.HelpText="hint" — accessible description (announced on focus)
• AutomationProperties.LabeledBy="{Binding ElementName=label}" — link label to input
• AutomationProperties.HeadingLevel="2" — mark headings for screen-reader heading nav
• KeyboardNavigation.TabNavigation="Cycle" / "Continue" — explicit tab order
• FocusManager.FocusedElement="{Binding ElementName=input}" — programmatic focus
• ToolTipService.SetToolTip(control, "hint") — tooltip (also screen-reader-accessible)
• control.MinHeight / MinWidth = 44 (or use AutomationProperties) — touch/click target size
• Use Button / TextBox / ComboBox — not a clickable Border/Grid
• Use AutomationId="unique-id" for testability and reliable AT identification
• Handle PreviewKeyDown for keyboard activation (Space / Enter on Button is built-in)
• Subclass AutomationPeer — implement custom UIA for custom-drawn visuals
""".strip()


_MAUI_APIS = """
.NET MAUI ACCESSIBILITY API REFERENCE — suggest specific fixes in the Accessibility section:
• SemanticProperties.Description="hint" — read by TalkBack / VoiceOver
• SemanticProperties.HeadingLevel="2" — mark as heading for screen-reader navigation
• SemanticProperties.Hint="action description" — what happens on activation
• SemanticProperties.ScreenReaderFocus="True" — explicit focus target
• AutomationId="unique-id" — for AT identification
• ImportantForAccessibility="Auto" / "Yes" / "No" / "NoHideDescendants"
• MinimumSizeRequest = new Size(44, 44) — WCAG 2.5.5 touch target
• Always pair Entry/Editor with a visible Label (or use Title="…" on the input)
• Use Button — not a clickable Frame / Border / BoxView
• Use Shell.Title or NavigationPage.Title — not a custom header label
• SemanticProperties.SetScreenReaderFocusTo(view) — programmatic focus
""".strip()


_AVALONIA_APIS = """
AVALONIA (.NET) ACCESSIBILITY API REFERENCE — suggest specific fixes in the Accessibility section:
• AutomationProperties.Name="name" — UIA accessible name
• AutomationProperties.HelpText="hint" — accessible description
• AutomationProperties.LabeledBy — link label to input control
• KeyboardNavigation.TabIndex="0" / IsTabStop="True" — tab order
• Use Button / TextBox / ComboBox — not a clickable Border / Panel
• MinHeight / MinWidth = 44 (or styles applied via :pointerover) — touch target size
• Subclass AutomationPeer — custom UIA for custom-drawn controls
• Use INameScope / IEmbeddedParentProvider when composing custom controls
• PseudoClasses :pointerover / :pressed / :disabled — visual + AT state hooks
• ToolTip.Tip="hint" (or Set ToolTip.Tip attached) — screen-reader-accessible hint
• Implement OnKeyDown for keyboard activation alongside Click
""".strip()


def _framework_api_ref(content: str, file_type: UIFileType) -> str:
    # Content-first: probe the file's actual imports/namespaces so a .py file
    # with `import tkinter` gets the tkinter reference (with its "limited
    # screen reader support" warning) instead of the wxPython one, and so a
    # .xaml file with a WPF xmlns gets the WPF reference rather than guessing
    # from the extension.
    if "import SwiftUI" in content:                                  return _SWIFTUI_APIS
    if "react-native" in content:                                    return _REACT_NATIVE_APIS
    if "from 'react'" in content or "import React" in content:      return _REACT_APIS
    if 'from "react"' in content:                                    return _REACT_APIS
    if "from 'vue'" in content or "import Vue" in content:          return _VUE_APIS
    if 'from "vue"' in content:                                      return _VUE_APIS
    # WPF and WinForms share "using System.Windows" but only WinForms uses
    # `using System.Windows.Forms`; check that namespace first.
    if "using System.Windows.Forms" in content:                      return _WINFORMS_APIS
    # WPF XAML carries the WPF XML namespace; we look for the specific URL
    # in either markup or a .cs code-behind.
    if "schemas.microsoft.com/winfx/2006/xaml/presentation" in content:  return _WPF_APIS
    if "schemas.microsoft.com/winfx/2006/xaml" in content:           return _WPF_APIS
    # .NET MAUI uses a different XML namespace; distinguishing from WPF by
    # the year token in the URL.
    if "schemas.microsoft.com/dotnet/2021/maui" in content:          return _MAUI_APIS
    if "schemas.microsoft.com/dotnet/maui/global" in content:        return _MAUI_APIS
    # Avalonia is identified by its GitHub-hosted XML namespace.
    if "github.com/avaloniaui" in content:                           return _AVALONIA_APIS
    if "from PyQt6" in content or "from PySide6" in content:        return _PYQT_APIS
    if "import tkinter" in content or "from tkinter" in content:     return _TKINTER_APIS
    if "import wx" in content or "from wx" in content:              return _WXPYTHON_APIS
    # Fall back to file type / extension
    if file_type in (UIFileType.VUE, UIFileType.SVELTE):            return _VUE_APIS
    if file_type in (UIFileType.HTML, UIFileType.CSS):              return _HTML_CSS_APIS
    if file_type in (UIFileType.REACT_JSX, UIFileType.JAVASCRIPT,
                     UIFileType.TYPESCRIPT):                         return _REACT_APIS
    # File extension fallback for .NET files: .xaml is ambiguous
    # between WPF and MAUI; we already content-probed for the namespace,
    # so by this point the user probably has a non-XAML .cs file. Without
    # a content probe, default to WPF — MAUI's namespace string is more
    # distinctive and is caught earlier.
    return ""


# ── System instructions ────────────────────────────────────────────────────────

_SYSTEM_INSTRUCTIONS = """You are a UI accessibility and visual design expert helping a blind developer \
understand what their UI looks like to sighted users.

For EVERY initial analysis, always cover all six sections — do not skip any:

## 1. Visual Appearance
Describe exactly what a sighted person sees: colors (plain English name + hex), \
layout, typography (font name, size, weight), spacing values (exact pt/px from the code), \
icons, images, and overall visual composition.

## 2. Ease of Use for Sighted Users
Is the interface clear and easy to navigate visually? Are interactive elements \
obvious? Is there enough visual feedback? Would a sighted user know what to do?

## 3. Professional Quality
Does this look polished and professional? Give a clear verdict (Polished / Mostly Polished / \
Needs Polish) with specific reasons — typography consistency, color harmony, spacing rhythm, \
alignment, visual weight, and overall finish.

## 4. Accessibility
Is this accessible to disabled users? Check: color contrast (WCAG AA requires 4.5:1 for text, \
3:1 for UI components), minimum touch/click target sizes (44×44pt), keyboard navigability, \
and presence of accessibility labels. Suggest specific API fixes using any reference provided.

## 5. Other Important Details
Note any animations, error states, empty states, conditional UI, platform-specific behaviors, \
or anything else a developer should know.

## 6. Screen Layout
Describe the spatial layout region by region, top to bottom. Name each zone (e.g. Navigation Bar, \
Content Area, Tab Bar), its position and size, elements it contains, and what a sighted user sees.

When answering follow-up questions: answer directly from the code, use exact values (pt/px/hex), \
never speculate — say "not visible in the code" if something is unclear."""


# ── Image content extraction ───────────────────────────────────────────────────

def _extract_image_content(path: Path) -> str:
    lines = [f"UI Screenshot: {path.name}"]

    # Dimensions via Pillow
    if _HAS_OCR:
        try:
            img = PILImage.open(path)
            w, h = img.size
            lines.append(f"Pixel dimensions: {w}×{h}")
        except Exception:
            pass

        # OCR
        try:
            img = PILImage.open(path)
            text = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            words = []
            n = len(text["text"])
            for i in range(n):
                word = text["text"][i].strip()
                if not word or int(text["conf"][i]) < 30:
                    continue
                # Normalise position
                left = text["left"][i]; top = text["top"][i]
                img_w = img.width or 1; img_h = img.height or 1
                x_rel = left / img_w; y_rel = top / img_h
                vert  = "top" if y_rel < 0.2 else ("upper" if y_rel < 0.45 else
                        ("middle" if y_rel < 0.55 else ("lower" if y_rel < 0.8 else "bottom")))
                horiz = "left" if x_rel < 0.3 else ("center" if x_rel < 0.7 else "right")
                words.append(f"  [{vert}, {horiz}] \"{word}\"")
            if words:
                lines.append("\nDetected text elements (position: [vertical, horizontal]):")
                lines.extend(words[:80])
            else:
                lines.append("\nNo text detected (possibly a graphic or icon-heavy screen).")
        except Exception as e:
            lines.append(f"\nOCR unavailable: {e}")
    else:
        lines.append("\nOCR not available — install pytesseract and Tesseract for text extraction.")

    lines.append(
        "\nAnalyse this screenshot as a UI designer would. Use text positions to infer layout: "
        "top area = navigation bar / header, middle = main content, bottom = tab bar or actions."
    )
    return "\n".join(lines)


def _build_ocr_suffix(png_data: bytes) -> str:
    """Return a text block describing the screenshot for text-only models.

    Writes png_data to a temp file, runs OCR via _extract_image_content, then
    deletes the temp file. If OCR is unavailable the suffix is an empty string
    (the analysis will proceed without screenshot information).
    """
    if not _HAS_OCR:
        return ""
    import os, tempfile
    try:
        fd, tmp = tempfile.mkstemp(suffix=".png")
        with os.fdopen(fd, "wb") as f:
            f.write(png_data)
        ocr = _extract_image_content(Path(tmp))
        return (
            "\n\nOCR text extracted from the attached screenshot "
            "(model does not support images — text approximation only):\n"
            "---\n" + ocr + "\n---"
        )
    except Exception:
        return ""
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ── UIAnalyzer ────────────────────────────────────────────────────────────────

class FileSession:
    """Per-file conversation state."""
    def __init__(self, file_id: str, file_name: str, file_type: UIFileType,
                 content_prefix: str, mode: OutputMode, table_format: TableFormat) -> None:
        self.file_id       = file_id
        self.file_name     = file_name
        self.file_type     = file_type
        self.content_prefix = content_prefix  # first 2,000 chars for re-anchoring
        self.mode          = mode
        self.table_format  = table_format
        self.messages: list[dict] = []        # full chat history
        self.chars_exchanged = 0
        self.roll_count    = 0

    def add_system(self, instructions: str) -> None:
        self.messages = [{"role": "system", "content": instructions}]

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def add_assistant(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})


CONTEXT_BUDGET = 12_000  # chars before rolling


class UIAnalyzer:
    def __init__(self, client: AIClient, model: str) -> None:
        self._client         = client
        self.model           = model
        self._sessions: dict[str, FileSession] = {}
        self.project_context: Optional[str]    = None
        self._project_messages: list[dict]     = []

    # ── Model switch ──────────────────────────────────────────────────────────

    def set_model(self, model: str) -> None:
        self.model = model

    # ── Analyse a file ────────────────────────────────────────────────────────

    def analyze(
        self,
        file: UIFile,
        mode: OutputMode,
        table_format: TableFormat,
        on_chunk: Callable[[str], None],
    ) -> UIAnalysis:
        if file.file_type.is_image:
            content = _extract_image_content(file.path)
        else:
            content = file.path.read_text(encoding="utf-8", errors="ignore")

        # Load attached screenshot if present
        screenshot_data: Optional[bytes] = None
        if file.screenshot_abs_path and file.screenshot_abs_path.is_file():
            try:
                screenshot_data = file.screenshot_abs_path.read_bytes()
            except OSError:
                pass

        return self._run_analysis(
            file_id=file.id,
            file_name=file.name,
            file_type=file.file_type,
            content=content,
            mode=mode,
            table_format=table_format,
            on_chunk=on_chunk,
            screenshot_data=screenshot_data,
        )

    def validate_against_screenshot(
        self,
        file: UIFile,
        prior_analysis: UIAnalysis,
    ) -> ValidationResult:
        """Send the prior analysis + attached screenshot to the model.

        Returns a `ValidationResult` with three lists:
        - stands_by  — claims the model still believes after seeing the image
        - retracts   — claims the model wants to take back
        - additions  — new claims grounded in the screenshot
        """
        screenshot_abs = file.screenshot_abs_path
        if screenshot_abs is None or not screenshot_abs.is_file():
            raise RuntimeError(
                "No screenshot is attached to this file. "
                "Right-click the file in the sidebar to attach one."
            )

        png_data = screenshot_abs.read_bytes()
        prompt = _build_validation_prompt(prior_analysis.content, prior_analysis.is_html)

        # Try multimodal first; fall back to OCR text if rejected
        raw_response = self._run_validation(prompt, png_data)
        return _parse_validation_json(raw_response)

    def _run_validation(self, prompt: str, png_data: bytes) -> str:
        """Send validation prompt with image to the model."""
        b64 = base64.b64encode(png_data).decode()

        # Build a multimodal user message (Ollama / OpenAI vision format)
        # For text-only models the image part is silently ignored or causes a
        # 400; in that case we fall back to OCR text injection below.
        try:
            messages: list[dict] = [
                {"role": "system", "content": _VALIDATION_SYSTEM_PROMPT},
                {"role": "user",   "content": prompt, "images": [b64]},
            ]
            accumulated = ""
            for chunk in self._client.stream_chat(self.model, messages):
                accumulated += chunk
            if accumulated.strip():
                return accumulated
        except Exception:
            pass

        # OCR fallback for text-only backends
        ocr_text = ""
        if _HAS_OCR:
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(png_data)
                tmp_path = tmp.name
            try:
                from pathlib import Path as _P
                ocr_text = _extract_image_content(_P(tmp_path))
            finally:
                os.unlink(tmp_path)

        augmented = (
            prompt
            + "\n\nOCR transcription of the attached screenshot "
            + "(text-only, layout approximate):\n---\n"
            + ocr_text
            + "\n---\n"
        )
        messages = [
            {"role": "system", "content": _VALIDATION_SYSTEM_PROMPT},
            {"role": "user",   "content": augmented},
        ]
        accumulated = ""
        for chunk in self._client.stream_chat(self.model, messages):
            accumulated += chunk
        return accumulated

    def _run_analysis(
        self,
        file_id: str,
        file_name: str,
        file_type: UIFileType,
        content: str,
        mode: OutputMode,
        table_format: TableFormat,
        on_chunk: Callable[[str], None],
        screenshot_data: Optional[bytes] = None,
    ) -> UIAnalysis:
        is_html = mode == OutputMode.TABLE and table_format == TableFormat.HTML

        # Build system instructions
        if is_html:
            sys_instructions = _HTML_SESSION_INSTRUCTIONS
        else:
            sys_instructions = _SYSTEM_INSTRUCTIONS
        if self.project_context:
            sys_instructions += f"\n\n{self.project_context}"

        session = FileSession(
            file_id=file_id, file_name=file_name, file_type=file_type,
            content_prefix=content[:2_000],
            mode=mode, table_format=table_format,
        )
        session.add_system(sys_instructions)
        self._sessions[file_id] = session

        prompt = self._build_prompt(file_name, file_type, content, mode, table_format)

        # Attach screenshot to the user turn when present
        vision_mode = VisionMode.NOT_ATTACHED
        if screenshot_data:
            b64 = base64.b64encode(screenshot_data).decode()
            multimodal_msg = {
                "role": "user",
                "content": prompt + "\n\nA screenshot of this UI is attached for visual reference.",
                "images": [b64],
            }
            session.messages.append(multimodal_msg)
            vision_mode = VisionMode.MULTIMODAL
        else:
            session.add_user(prompt)

        accumulated = ""
        try:
            for chunk in self._client.stream_chat(self.model, session.messages):
                accumulated += chunk
                on_chunk(accumulated)
        except Exception as exc:
            # Model rejected the images array (not vision-capable → 400).
            # Strip the image and retry with OCR text injected instead.
            if screenshot_data and vision_mode == VisionMode.MULTIMODAL and (
                "400" in str(exc) or "images" in str(exc).lower()
            ):
                accumulated = ""
                # Replace multimodal message with plain prompt + OCR text
                session.messages = [m for m in session.messages if m.get("images") is None]
                ocr_suffix = _build_ocr_suffix(screenshot_data)
                session.add_user(prompt + ocr_suffix)
                vision_mode = VisionMode.OCR_TEXT
                for chunk in self._client.stream_chat(self.model, session.messages):
                    accumulated += chunk
                    on_chunk(accumulated)
            else:
                raise

        if is_html:
            result = _extract_html(accumulated)
        else:
            result = accumulated

        session.add_assistant(result)
        session.chars_exchanged += len(prompt) + len(result)

        return UIAnalysis(
            content=result,
            mode=mode,
            table_format=table_format if mode == OutputMode.TABLE else None,
            is_html=is_html,
            vision_mode=vision_mode,
        )

    # ── Follow-up ─────────────────────────────────────────────────────────────

    def ask_follow_up(
        self,
        file_id: str,
        question: str,
        on_chunk: Callable[[str], None],
    ) -> str:
        if file_id in self._sessions:
            s = self._sessions[file_id]
            if s.chars_exchanged >= CONTEXT_BUDGET:
                self._roll_context(file_id)

        session = self._sessions.get(file_id)
        if session is None:
            raise RuntimeError("No session — analyze the file first.")

        session.add_user(question)
        accumulated = ""
        for chunk in self._client.stream_chat(self.model, session.messages):
            accumulated += chunk
            on_chunk(accumulated)

        session.add_assistant(accumulated)
        session.chars_exchanged += len(question) + len(accumulated)
        return accumulated

    def _roll_context(self, file_id: str) -> None:
        s = self._sessions[file_id]
        summary_prompt = (
            "Summarise the key facts from our conversation about this UI in 4–6 sentences: "
            "screen name/purpose, UI elements and labels, colours (name + hex), layout, "
            "professional quality verdict, accessibility notes, and follow-up findings."
        )
        s.add_user(summary_prompt)
        summary = self._client.respond(self.model, s.messages)

        sys_instructions = _SYSTEM_INSTRUCTIONS
        if self.project_context:
            sys_instructions += f"\n\n{self.project_context}"
        sys_instructions += f"\n\nCONTEXT FROM EARLIER:\n{summary}\n\nFile: {s.file_name}"

        s.messages = [
            {"role": "system", "content": sys_instructions},
            {"role": "user",   "content": f"Continue our discussion of {s.file_name}. "
                                           f"Here are the opening lines as reference:\n"
                                           f"```\n{s.content_prefix}\n```"},
            {"role": "assistant", "content": "Understood — continuing from where we left off."},
        ]
        s.chars_exchanged = len(summary)
        s.roll_count += 1

    # ── Project context ───────────────────────────────────────────────────────

    def build_project_context(
        self,
        files: list[UIFile],
        on_progress: Callable[[int, int], None],
    ) -> None:
        summaries: list[str] = []
        total = len(files)

        for i, file in enumerate(files):
            on_progress(i + 1, total)
            if file.file_type.is_image:
                content = _extract_image_content(file.path)
            else:
                try:
                    content = file.path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue

            messages = [
                {"role": "system", "content": _PROJECT_MINI_SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"File: {file.name} ({file.file_type.value})\n"
                    f"```\n{content[:4_000]}\n```\n"
                    "Write the 4-line SCREEN/VISUALS/QUALITY/ISSUES note."
                )},
            ]
            summary = self._client.respond(self.model, messages)
            summaries.append(f"[{file.name}]\n{summary}")

        self.project_context = (
            f"PROJECT UI CONTEXT — {len(files)} screen(s) analysed:\n\n"
            + "\n\n".join(summaries)
            + "\n\nUse this context for direct, specific answers about design quality, "
              "consistency, colour harmony, and accessibility issues. "
              "When asked about professionalism, cite specific screens and issues by name."
        )
        self._project_messages = [
            {"role": "system", "content": _make_project_system_prompt(self.project_context)}
        ]

    def clear_project_context(self) -> None:
        self.project_context = None
        self._project_messages = []

    def ask_project_question(
        self,
        question: str,
        on_chunk: Callable[[str], None],
    ) -> str:
        if not self._project_messages:
            raise RuntimeError("No project context — build it first.")
        self._project_messages.append({"role": "user", "content": question})
        accumulated = ""
        for chunk in self._client.stream_chat(self.model, self._project_messages):
            accumulated += chunk
            on_chunk(accumulated)
        self._project_messages.append({"role": "assistant", "content": accumulated})
        return accumulated

    # ── Prompt builder ────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        file_name: str,
        file_type: UIFileType,
        content: str,
        mode: OutputMode,
        table_format: TableFormat,
    ) -> str:
        header = f"File: {file_name} ({file_type.value})"
        source = f"```\n{content[:10_000]}\n```"

        # Build extra context: framework API ref + contrast report
        extra = ""
        api_ref = _framework_api_ref(content, file_type)
        if api_ref:
            extra += api_ref + "\n\n"
        cr = contrast_report(content)
        if cr:
            extra += cr + "\n\n"

        if file_type == UIFileType.IMAGE:
            return _image_prompt(header, source, mode, table_format, extra)

        if _is_design_spec(file_name, file_type):
            return _design_spec_prompt(header, source, mode, table_format, extra)

        if mode == OutputMode.PROSE:
            return _prose_prompt(header, source, extra)
        else:
            if table_format == TableFormat.MARKDOWN:
                return _markdown_table_prompt(header, source, extra)
            else:
                return _html_table_prompt(header, source, extra)


# ── Prompt templates ──────────────────────────────────────────────────────────

def _is_design_spec(file_name: str, file_type: UIFileType) -> bool:
    if file_type != UIFileType.MARKDOWN:
        return False
    skip = ("readme", "changelog", "contributing", "license", "history", "authors")
    return not any(file_name.lower().startswith(s) for s in skip)


def _prose_prompt(header: str, source: str, extra: str) -> str:
    return f"""{header}

Analyse this UI file using Markdown headings. Write all six sections:

## 1. Visual Appearance
Colors (name + hex), layout, typography (family/weight/size in pt), exact spacing values from the code, icons, overall visual composition.

## 2. Ease of Use for Sighted Users
Is the hierarchy clear? Are interactive elements obvious? Is there enough visual feedback?

## 3. Professional Quality
Give a direct verdict (Polished / Mostly Polished / Needs Polish) with specific reasons.

## 4. Accessibility
WCAG AA contrast (4.5:1 text, 3:1 UI), touch target sizes (44×44pt min), keyboard nav, accessibility labels present or missing. Use the API reference below to suggest specific fixes.

## 5. Other Important Details
Animations, dark/light mode variants, error states, empty states, conditional UI, platform-specific behaviors.

## 6. Screen Layout
Describe the spatial layout region by region, top to bottom. Name each zone, give its position and approximate size, list elements, describe what a sighted user sees.

{extra}{source}"""


def _markdown_table_prompt(header: str, source: str, extra: str) -> str:
    return f"""{header}

First write a brief summary paragraph covering visual appearance, sighted usability, professional quality, accessibility, and other important details.

Then produce a Markdown elements table for every UI element.
If the file defines ONLY ONE color scheme use:
| Element | Label / Text | Color Name | Hex | Position | Interactive? | Spacing / Size | Notes |
If the file defines multiple color schemes (light/dark mode, named themes):
| Element | Label / Text | Color — Light | Hex — Light | Color — Dark | Hex — Dark | Position | Interactive? | Spacing / Size | Notes |
Skip columns with no data. Skip rows where all cells are empty.

Then produce a second Markdown layout table, one row per screen region (top to bottom):
| Region | Position | Elements | What a Sighted User Sees |

{extra}{source}"""


def _html_table_prompt(header: str, source: str, extra: str) -> str:
    return f"""{header}

Produce a complete HTML5 document with exactly three parts.

─── PART 1: FIVE ANALYSIS SECTIONS ───
Five <section> elements in the <body>, each with a linked <h2>:
  <section aria-labelledby="h-visual"><h2 id="h-visual">Visual Appearance</h2><p>[2–4 sentences with exact values]</p></section>
  <section aria-labelledby="h-usability"><h2 id="h-usability">Ease of Use for Sighted Users</h2><p>[2–3 sentences]</p></section>
  <section aria-labelledby="h-quality"><h2 id="h-quality">Professional Quality</h2><p>[verdict + specific reasons]</p></section>
  <section aria-labelledby="h-a11y"><h2 id="h-a11y">Accessibility</h2><p>[WCAG contrast, touch targets, keyboard nav, specific API fix suggestions]</p></section>
  <section aria-labelledby="h-other"><h2 id="h-other">Other Important Details</h2><p>[dark/light mode, animations, error states]</p></section>

─── PART 2: UI ELEMENTS TABLE ───
<h2 id="h-elements">UI Elements</h2>
<table aria-labelledby="h-elements"><caption>[Screen name] — all UI elements</caption>
<thead><tr>[th scope="col" for each populated column]</tr></thead>
<tbody>[one tr per element]</tbody></table>
Columns: Element, Label/Text, Color (split Light/Dark if multiple schemes), Position, Interactive?, Spacing/Size, Notes.

─── PART 3: SCREEN LAYOUT TABLE ───
<h2 id="h-layout">Screen Layout</h2>
<table aria-labelledby="h-layout"><caption>Visual layout of [screen name], top to bottom</caption>
<thead><tr><th scope="col">Region</th><th scope="col">Position</th><th scope="col">Elements</th><th scope="col">What a Sighted User Sees</th></tr></thead>
<tbody>[one tr per visual region]</tbody></table>

─── STYLING ───
Include in <head>:
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-size:14px;line-height:1.6;color:#1c1c1e;background:#fff;margin:16px}}
h2{{font-size:16px;font-weight:700;margin:24px 0 8px;color:#1c1c1e;border-bottom:1px solid #d2d2d7;padding-bottom:4px}}
section{{margin-bottom:4px}}p{{margin:0 0 8px}}
table{{border-collapse:collapse;width:100%;margin-bottom:28px}}
caption{{text-align:left;font-weight:600;font-size:13px;padding:0 0 6px;color:#3a3a3c}}
th{{background:#f2f2f7;font-weight:600;text-align:left;padding:8px 12px;border:1px solid #c6c6c8}}
td{{padding:8px 12px;border:1px solid #c6c6c8;vertical-align:top}}
tr:nth-child(even) td{{background:#f9f9fb}}
@media(prefers-color-scheme:dark){{body{{color:#f2f2f7;background:#1c1c1e}}h2{{color:#f2f2f7;border-bottom-color:#38383a}}th{{background:#2c2c2e;border-color:#48484a}}td{{border-color:#48484a}}tr:nth-child(even) td{{background:#252527}}}}
</style>

Start with <!DOCTYPE html>. Output ONLY the HTML.

{extra}{source}"""


def _image_prompt(header: str, source: str, mode: OutputMode,
                  table_format: TableFormat, extra: str) -> str:
    intro = (f"{header}\n\nThis is a UI screenshot. Use text positions and UI conventions to "
             "infer layout. Follow the six-section format. Acknowledge you are working from OCR.")
    if mode == OutputMode.PROSE:
        return f"{intro}\n\n{extra}{source}"
    if table_format == TableFormat.MARKDOWN:
        return (f"{intro}\n\nThen produce a Markdown table of detected UI elements "
                f"with inferred labels, positions, and roles.\n\n{extra}{source}")
    return _html_table_prompt(header, f"{intro}\n\n{source}", extra)


def _design_spec_prompt(header: str, source: str, mode: OutputMode,
                        table_format: TableFormat, extra: str) -> str:
    intro = f"""{header}

This is a design specification document. Use these five sections:

## 1. Color System
Every color defined: name, hex, intended use. Flag any failing WCAG AA contrast.

## 2. Typography
Every type style: family, weight, size, line-height, usage.

## 3. Spacing, Layout & Grid
Spacing scale, grid system, breakpoints, layout tokens.

## 4. Components & Patterns
Every component/pattern: states (default, hover, active, disabled, error), usage rules.

## 5. Accessibility Design Decisions
Focus styles, contrast choices, touch target sizes, motion preferences, screen reader guidance."""

    if mode == OutputMode.PROSE:
        return f"{intro}\n\n{extra}{source}"
    if table_format == TableFormat.MARKDOWN:
        return (f"{intro}\n\nAfter the five sections, produce a Markdown token table:\n"
                f"| Token | Value | Type | Usage |\n\n{extra}{source}")
    return _html_table_prompt(header, source, extra)


_HTML_SESSION_INSTRUCTIONS = """You are a UI accessibility and visual design expert helping a blind developer \
understand what their UI looks like to sighted users.

Your task: produce a complete, valid HTML5 document with three parts. \
Start with a TL;DR <details> block so a blind user gets the headline first, then \
expand the five analysis <section> elements with <h2> headings, a UI elements table, \
and a screen layout table. Output ONLY the HTML — start with <!DOCTYPE html>, \
nothing before the doctype, nothing after </html>."""


_PROJECT_MINI_SYSTEM_PROMPT = """\
You are a senior UI/UX designer reviewing an app's screens to help a blind \
developer understand the visual quality of their work. \
For each file write a structured 4-line note using exactly these labels: \
SCREEN: [screen name and purpose] \
VISUALS: [primary colors (name + hex), typography, key UI elements] \
QUALITY: [Polished / Mostly Polished / Needs Polish — single most impactful reason] \
ISSUES: [comma-separated specific problems, or 'None']"""


def _make_project_system_prompt(context: str) -> str:
    """System prompt for the project-wide Q&A chat.

    The macOS app's `makeProjectSystemPrompt` (Services/UIAnalyzer.swift) requires
    fragment HTML output with <h2> structure so VoiceOver's heading rotor can
    navigate between Question/Answer pairs. The same shape works here — the
    rendering target is `wx_accessible_webview` (HTML/ARIA) on Windows, which
    exposes HTML headings as ARIA landmarks. NVDA and JAWS both honour
    `aria-level` and announce headings the same way VoiceOver does.
    """
    return f"""\
You are a senior UI/UX designer and accessibility expert helping a blind developer \
understand the real visual quality of their app. The developer cannot see the screen \
and relies entirely on your honest, direct assessment.

{context}

ANSWER RULES — follow these strictly:

• BE DIRECT. Never hedge with phrases like "it's hard to say without seeing it" \
or "based on the context." You have the context. Use it. Give a verdict.

• FOR PROFESSIONALISM/POLISH QUESTIONS: Always open with a clear verdict — \
"Yes, the app looks professional", "Mostly, with some rough edges", or \
"Not yet — here's what needs fixing." Then list specific issues by screen name \
and specific element (e.g. "LoginView: the Sign In button uses 12pt padding top \
but 20pt bottom, which looks uneven").

• FOR COLOR/TYPOGRAPHY QUESTIONS: Give exact values — hex codes, font names, \
point sizes. Note inconsistencies across screens by name.

• FOR ACCESSIBILITY QUESTIONS: Reference specific screens that have problems \
and state the WCAG criterion being violated.

• IF SOMETHING IS NOT IN THE CONTEXT: Say "I don't have detail on that screen — \
try analyzing it individually first with Cmd+R to get a full breakdown."

• NEVER invent information. Only use what is in the screen summaries above.

OUTPUT FORMAT — HTML fragment, NOT Markdown. The developer is blind and uses \
NVDA (or JAWS) on Windows to navigate the response. NVDA's heading navigation \
jumps between elements that screen readers expose as headings, which corresponds \
to <h1>–<h6> in the rendered HTML. Markdown headings (# / ##) are stripped to \
plain bold runs in a single block, which is NOT navigable. HTML headings are.

For every question-and-answer pair, emit exactly this structure:

  <h2>Question</h2>
  <p>{{restate the question briefly so the heading reads as a stand-alone label}}</p>
  <h2>Answer</h2>
  <p>{{direct opening verdict or summary sentence}}</p>
  {{<p>…</p> and <ul><li>…</li></ul> as needed for the body}}

Rules for the HTML:
  • Use only these tags: <h2>, <h3>, <p>, <ul>, <ol>, <li>, <strong>, <em>, <code>. \
No <h1> (it competes with the page heading), no <table>, no inline styles.
  • Do NOT wrap the output in <!DOCTYPE html>, <html>, <head>, <style>, or <body>. \
Emit a fragment. The renderer will compose it into the chat log.
  • Do NOT use Markdown syntax. No ** for bold, no # for headings, no - for lists. \
NVDA / JAWS cannot see Markdown structure once it's in a single block.
  • For long answers, break the body into multiple short <p> paragraphs (one \
sentence each is fine) rather than one wall of text. Screen readers read them as \
navigable stops.
  • If you are listing issues by screen, use <ul><li>Screen name: issue</li></ul> \
so each item is a separate navigation stop.
"""


_VALIDATION_SYSTEM_PROMPT = """\
You are a UI accessibility and visual design expert.
You have been shown:
1. An existing text-based analysis of a UI file
2. A real screenshot of that UI

Your job is to verify that analysis against what you can actually see in the screenshot, \
and return a JSON object with three keys:

{
  "stands_by":  ["claim still true", ...],
  "retracts":   ["claim that was wrong or misleading", ...],
  "additions":  ["new observation only visible in the screenshot", ...]
}

Rules:
- "stands_by"  — copy claims from the analysis that the screenshot confirms
- "retracts"   — copy (and briefly explain) any claim the screenshot contradicts
- "additions"  — add new observations about color, layout, imagery, or contrast \
that could not be inferred from code alone
- Return ONLY the JSON object, no markdown fences, no explanation text.
"""


def _build_validation_prompt(prior_analysis: str, is_html: bool) -> str:
    text = prior_analysis
    if is_html:
        # Strip tags for a clean text summary the model can compare against
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s{2,}", " ", text).strip()

    return (
        "Here is the existing analysis of a UI file:\n\n"
        f"---\n{text[:6_000]}\n---\n\n"
        "Now compare it against the screenshot provided. "
        "Return JSON with stands_by, retracts, and additions."
    )


def _parse_validation_json(raw: str) -> ValidationResult:
    """Parse the model's JSON response into a ValidationResult.

    Tolerates code-fenced responses and missing/extra keys.
    """
    text = raw.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to salvage a partial object by extracting the first { ... }
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

    def _claims(key: str) -> list:
        items = data.get(key, [])
        if not isinstance(items, list):
            return []
        return [str(i) for i in items if i]

    return ValidationResult(
        stands_by=[ValidationClaim(t) for t in _claims("stands_by")],
        retracts=[ValidationRetraction(t) for t in _claims("retracts")],
        additions=[ValidationClaim(t) for t in _claims("additions")],
    )


def _extract_html(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]).strip()
    for marker in ("<!DOCTYPE html", "<!doctype html", "<html"):
        idx = text.lower().find(marker.lower())
        if idx >= 0:
            return text[idx:]
    return text
