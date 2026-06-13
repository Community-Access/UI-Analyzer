"""Detail panel — shows analysis output and follow-up chat bar."""

from __future__ import annotations

import threading
import wx
import wx.html2
from typing import Callable, Optional

from ui_analyzer.models.ui_file import (
    UIFile, UIAnalysis, OutputMode, TableFormat, ValidationResult,
)

# Import the accessible webview library
try:
    from wx_accessible_webview import AccessibleWebView
    _HAS_ACCESSIBLE_WV = True
except ImportError:
    _HAS_ACCESSIBLE_WV = False

# Markdown → HTML (simple, no external dep needed for basic output)
try:
    import markdown
    def _md_to_html(text: str) -> str:
        body = markdown.markdown(text, extensions=["tables", "fenced_code"])
        return _wrap_html(body)
except ImportError:
    def _md_to_html(text: str) -> str:  # type: ignore[misc]
        # Minimal fallback: wrap paragraphs
        paras = "\n".join(f"<p>{line}</p>" for line in text.split("\n\n") if line.strip())
        return _wrap_html(paras)


_KEY_BRIDGE_JS = """
<script>
document.addEventListener('keydown', function(e) {
  if (e.ctrlKey && !e.shiftKey && e.key === 'r') {
    e.preventDefault();
    if (window.wx) window.wx.postMessage('analyze');
  } else if (e.ctrlKey && e.shiftKey && (e.key === 'V' || e.key === 'v')) {
    e.preventDefault();
    if (window.wx) window.wx.postMessage('validate');
  }
});
</script>
"""


def _wrap_html(body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light dark">
{_KEY_BRIDGE_JS}
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     font-size:14px;line-height:1.7;
     margin:16px;max-width:820px;
     background-color: #ffffff;
     color: #1c1c1e;}}
h2{{font-size:16px;font-weight:700;margin:24px 0 8px;
   border-bottom:1px solid #d2d2d7;padding-bottom:4px}}
h3{{font-size:14px;font-weight:600;margin:16px 0 6px}}
p{{margin:0 0 12px}}
ul{{margin:0 0 12px;padding-left:20px}}li{{margin-bottom:4px}}
code{{background:#f2f2f7;padding:2px 4px;border-radius:3px;font-size:13px}}
pre{{background:#f2f2f7;padding:12px;border-radius:6px;overflow-x:auto}}
table{{border-collapse:collapse;width:100%;margin-bottom:24px}}
caption{{text-align:left;font-weight:600;font-size:13px;padding:0 0 6px}}
th{{background:#f2f2f7;font-weight:600;text-align:left;
   padding:8px 12px;border:1px solid #c6c6c8}}
td{{padding:8px 12px;border:1px solid #c6c6c8;vertical-align:top}}
tr:nth-child(even) td{{background:#f9f9fb}}
hr{{border:none;border-top:1px solid #d2d2d7;margin:20px 0}}
@media(prefers-color-scheme:dark){{
  body{{color: #f2f2f7; background-color: #1c1c1e;}}
  h2{{border-bottom-color:#38383a}}
  code,pre{{background:#2c2c2e}}
  th{{background:#2c2c2e;border-color:#48484a}}
  td{{border-color:#48484a}}
  tr:nth-child(even) td{{background:#252527}}
  hr{{border-top-color:#38383a}}
}}
@media(forced-colors:active){{
  th{{background:ButtonFace;border-color:ButtonText}}
  td{{border-color:ButtonText}}
}}
</style>
</head>
<body>
{body}
</body>
</html>"""


class DetailPanel(wx.Panel):
    """Analysis output panel.

    States:
      empty    — no file selected
      ready    — file selected, not yet analyzed
      loading  — analysis in progress (streaming plain text)
      result   — analysis complete (AccessibleWebView / HTML)
      error    — analysis failed

    Accessibility:
      • Toolbar buttons have descriptive labels and tooltips
      • Output uses AccessibleWebView (ARIA live regions, NVDA/JAWS compatible)
      • During streaming, plain wx.TextCtrl is used (fully accessible to AT)
      • Status bar text updated on each state change
      • Follow-up bar has paired label + text field + button
    """

    def __init__(
        self,
        parent: wx.Window,
        on_analyze:     Callable[[UIFile, OutputMode, TableFormat], None],
        on_copy:        Callable[[], None],
        on_save:        Callable[[], None],
        on_follow_up:   Callable[[str], None],
        status_bar:     wx.StatusBar,
        on_validate:    Optional[Callable[[UIFile], None]] = None,
        on_detach:      Optional[Callable[[UIFile], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._on_analyze    = on_analyze
        self._on_copy       = on_copy
        self._on_save       = on_save
        self._on_follow_up  = on_follow_up
        self._on_validate   = on_validate
        self._on_detach     = on_detach
        self._status_bar    = status_bar
        self._current_file: Optional[UIFile] = None
        self._current_mode  = OutputMode.PROSE
        self._current_fmt   = TableFormat.MARKDOWN

        self._build_ui()
        self._show_state("empty")

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ── Toolbar ──────────────────────────────────────────────────────────
        tb_panel = wx.Panel(self)
        tb_panel.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE))
        tb = wx.BoxSizer(wx.HORIZONTAL)

        # File info label
        self._file_label = wx.StaticText(tb_panel, label="No file selected")
        self._file_label.SetFont(self._file_label.GetFont().Bold())
        tb.Add(self._file_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)

        # Output mode picker
        mode_lbl = wx.StaticText(tb_panel, label="Format:")
        tb.Add(mode_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self._mode_choice = wx.Choice(tb_panel, choices=["Prose", "Table"])
        self._mode_choice.SetSelection(0)
        self._mode_choice.SetName("Output format")
        self._mode_choice.SetToolTip("Switch between prose description and table view")
        self._mode_choice.Bind(wx.EVT_CHOICE, self._on_mode_change)
        tb.Add(self._mode_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)

        # Table format picker (hidden when mode=Prose)
        self._fmt_choice = wx.Choice(tb_panel, choices=["Markdown", "HTML"])
        self._fmt_choice.SetSelection(0)
        self._fmt_choice.SetName("Table format")
        self._fmt_choice.SetToolTip("Markdown table or fully accessible HTML table")
        self._fmt_choice.Bind(wx.EVT_CHOICE, self._on_fmt_change)
        tb.Add(self._fmt_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        # Disable rather than hide — hiding removes it from tab order silently,
        # which confuses screen readers that already enumerated the controls
        self._fmt_choice.Disable()

        # Action buttons
        # Minimum height 44px satisfies WCAG 2.5.5 touch target size
        self._copy_btn = wx.Button(tb_panel, label="Copy", size=(76, 44))
        self._copy_btn.SetName("Copy output")
        self._copy_btn.SetToolTip("Copy the full output to the clipboard (Ctrl+Shift+C)")
        self._copy_btn.Bind(wx.EVT_BUTTON, lambda _e: self._on_copy())
        tb.Add(self._copy_btn, 0, wx.LEFT, 6)

        self._save_btn = wx.Button(tb_panel, label="Save…", size=(76, 44))
        self._save_btn.SetName("Save output")
        self._save_btn.SetToolTip("Save the output to a file (Ctrl+S)")
        self._save_btn.Bind(wx.EVT_BUTTON, lambda _e: self._on_save())
        tb.Add(self._save_btn, 0, wx.LEFT, 4)

        self._analyze_btn = wx.Button(tb_panel, label="Analyze", size=(96, 44))
        self._analyze_btn.SetName("Analyze file")
        self._analyze_btn.SetToolTip("Run AI analysis on this file (Ctrl+R)")
        self._analyze_btn.Bind(wx.EVT_BUTTON, self._on_analyze_click)
        tb.Add(self._analyze_btn, 0, wx.LEFT, 6)

        self._validate_btn = wx.Button(tb_panel, label="Validate", size=(96, 44))
        self._validate_btn.SetName("Validate against screenshot")
        self._validate_btn.SetToolTip(
            "Compare the analysis against the attached screenshot (Ctrl+Shift+V). "
            "Requires an analysis and an attached screenshot."
        )
        self._validate_btn.Bind(wx.EVT_BUTTON, self._on_validate_click)
        self._validate_btn.Disable()
        tb.Add(self._validate_btn, 0, wx.LEFT | wx.RIGHT, 4)

        tb_panel.SetSizer(tb)
        tb_panel.SetMinSize((-1, 44))
        sizer.Add(tb_panel, 0, wx.EXPAND)
        sizer.Add(wx.StaticLine(self), 0, wx.EXPAND)

        # ── Attachment strip (shown when a screenshot is linked) ─────────────
        self._attach_panel = wx.Panel(self)
        self._attach_panel.SetBackgroundColour(wx.Colour(230, 245, 255))
        ap = wx.BoxSizer(wx.HORIZONTAL)
        self._attach_icon = wx.StaticText(self._attach_panel, label="📎")
        self._attach_icon.SetToolTip("Screenshot attached")
        ap.Add(self._attach_icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self._attach_lbl = wx.StaticText(self._attach_panel, label="")
        self._attach_lbl.SetName("Attached screenshot filename")
        ap.Add(self._attach_lbl, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        self._detach_btn = wx.Button(self._attach_panel, label="Detach", size=(-1, 32))
        self._detach_btn.SetName("Detach screenshot")
        self._detach_btn.SetToolTip(
            "Remove the linked screenshot and delete the sibling file from the project folder"
        )
        self._detach_btn.Bind(wx.EVT_BUTTON, self._on_detach_click)
        ap.Add(self._detach_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 8)
        self._attach_panel.SetSizer(ap)
        self._attach_panel.SetMinSize((-1, 36))
        self._attach_panel.Hide()
        sizer.Add(self._attach_panel, 0, wx.EXPAND)

        # ── Content area ─────────────────────────────────────────────────────

        # Empty state
        self._empty_panel = wx.Panel(self)
        ep = wx.BoxSizer(wx.VERTICAL)
        ep.AddStretchSpacer()
        empty_lbl = wx.StaticText(
            self._empty_panel,
            label="Select a file from the sidebar to analyze it.",
            style=wx.ALIGN_CENTER,
        )
        empty_lbl.SetForegroundColour(wx.Colour(120, 120, 120))
        ep.Add(empty_lbl, 0, wx.ALIGN_CENTER)
        drop_lbl = wx.StaticText(
            self._empty_panel,
            label="You can also drop a folder onto the sidebar.",
            style=wx.ALIGN_CENTER,
        )
        drop_lbl.SetForegroundColour(wx.Colour(150, 150, 150))
        ep.Add(drop_lbl, 0, wx.ALIGN_CENTER | wx.TOP, 6)
        ep.AddStretchSpacer()
        self._empty_panel.SetSizer(ep)
        sizer.Add(self._empty_panel, 1, wx.EXPAND)

        # Ready state
        self._ready_panel = wx.Panel(self)
        rp = wx.BoxSizer(wx.VERTICAL)
        rp.AddStretchSpacer()
        ready_lbl = wx.StaticText(
            self._ready_panel,
            label="Click Analyze to describe this file with AI.",
            style=wx.ALIGN_CENTER,
        )
        rp.Add(ready_lbl, 0, wx.ALIGN_CENTER)
        rp.AddStretchSpacer()
        self._ready_panel.SetSizer(rp)
        sizer.Add(self._ready_panel, 1, wx.EXPAND)

        # Loading state (streaming plain text)
        self._loading_panel = wx.Panel(self)
        lp = wx.BoxSizer(wx.VERTICAL)
        self._stream_text = wx.TextCtrl(
            self._loading_panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.BORDER_NONE,
        )
        self._stream_text.SetName("Analysis in progress — live output")
        # TE_READONLY TextCtrl: NVDA announces label + reads content on focus.
        # AppendText() triggers a text-change notification that AT can pick up;
        # SetValue() replaces the whole buffer and may not reliably announce.
        self._stream_gauge = wx.Gauge(self._loading_panel, range=0, size=(-1, 4))
        self._stream_gauge.SetName("Analysis progress")  # screen reader label for gauge
        self._stream_gauge.Pulse()
        lp.Add(self._stream_gauge, 0, wx.EXPAND)
        lp.Add(self._stream_text, 1, wx.EXPAND)
        self._loading_panel.SetSizer(lp)
        sizer.Add(self._loading_panel, 1, wx.EXPAND)

        # Result state — AccessibleWebView (falls back to wx.html2.WebView)
        if _HAS_ACCESSIBLE_WV:
            self._result_view = AccessibleWebView(self)
            self._result_window = self._result_view.control
        else:
            self._result_view = wx.html2.WebView.New(self)
            self._result_window = self._result_view

        if hasattr(self._result_window, "SetName"):
            self._result_window.SetName("Analysis output")

        # Register the "wx" postMessage handler so the JS key bridge can fire
        # Ctrl+R → analyze and Ctrl+Shift+V → validate even when the WebView has focus
        if hasattr(self._result_window, "AddScriptMessageHandler"):
            try:
                self._result_window.AddScriptMessageHandler("wx")
                self._result_window.Bind(
                    wx.html2.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED,
                    self._on_webview_message,
                )
            except Exception:
                pass

        sizer.Add(self._result_window, 1, wx.EXPAND)

        # Error state
        self._error_panel = wx.Panel(self)
        erp = wx.BoxSizer(wx.VERTICAL)
        erp.AddStretchSpacer()
        self._error_lbl = wx.StaticText(
            self._error_panel, label="", style=wx.ALIGN_CENTER
        )
        self._error_lbl.SetName("Analysis error details")
        self._error_lbl.SetForegroundColour(wx.Colour(200, 50, 50))
        erp.Add(self._error_lbl, 0, wx.ALIGN_CENTER | wx.ALL, 12)
        self._retry_btn = wx.Button(self._error_panel, label="Try Again")
        self._retry_btn.SetName("Retry analysis")
        self._retry_btn.SetToolTip("Retry the analysis")
        self._retry_btn.Bind(wx.EVT_BUTTON, self._on_analyze_click)
        erp.Add(self._retry_btn, 0, wx.ALIGN_CENTER)
        erp.AddStretchSpacer()
        self._error_panel.SetSizer(erp)
        sizer.Add(self._error_panel, 1, wx.EXPAND)

        # ── Validation progress panel ─────────────────────────────────────────
        self._val_progress_panel = wx.Panel(self)
        vpp = wx.BoxSizer(wx.VERTICAL)
        self._val_gauge = wx.Gauge(self._val_progress_panel, range=0, size=(-1, 4))
        self._val_gauge.SetName("Validation progress")
        self._val_gauge.Pulse()
        val_prog_lbl = wx.StaticText(
            self._val_progress_panel,
            label="Validating against screenshot…",
            style=wx.ALIGN_CENTER,
        )
        vpp.Add(self._val_gauge, 0, wx.EXPAND)
        vpp.Add(val_prog_lbl, 0, wx.ALIGN_CENTER | wx.TOP, 8)
        self._val_progress_panel.SetSizer(vpp)
        self._val_progress_panel.Hide()
        sizer.Add(self._val_progress_panel, 0, wx.EXPAND | wx.ALL, 4)

        # ── Validation error panel ────────────────────────────────────────────
        self._val_error_panel = wx.Panel(self)
        vep = wx.BoxSizer(wx.HORIZONTAL)
        self._val_error_lbl = wx.StaticText(self._val_error_panel, label="")
        self._val_error_lbl.SetName("Validation error details")
        self._val_error_lbl.SetForegroundColour(wx.Colour(200, 50, 50))
        vep.Add(self._val_error_lbl, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8)
        self._val_error_panel.SetSizer(vep)
        self._val_error_panel.Hide()
        sizer.Add(self._val_error_panel, 0, wx.EXPAND)

        # ── Validation result panel ───────────────────────────────────────────
        self._val_result_panel = wx.Panel(self)
        vrp = wx.BoxSizer(wx.VERTICAL)

        # Three groups: Stands By / Retracts / Additions
        for attr, symbol, label, color in (
            ("_val_stands_box",   "[confirmed]", "Stands By",  wx.Colour(230, 255, 230)),
            ("_val_retracts_box", "[retracted]", "Retracts",   wx.Colour(255, 235, 230)),
            ("_val_additions_box","[new]",        "Additions", wx.Colour(230, 235, 255)),
        ):
            group_panel = wx.Panel(self._val_result_panel)
            group_panel.SetBackgroundColour(color)
            gp = wx.BoxSizer(wx.VERTICAL)
            # Symbol prefix ensures meaning is conveyed by text, not color alone (WCAG 1.4.1).
            # SetName spells it out for screen readers so NVDA/JAWS read a clear label.
            hdr = wx.StaticText(group_panel, label=f"{symbol}  {label}")
            hdr.SetFont(hdr.GetFont().Bold())
            hdr.SetName(f"Validation section: {label}")
            gp.Add(hdr, 0, wx.ALL, 6)
            list_ctrl = wx.ListCtrl(
                group_panel,
                style=wx.LC_REPORT | wx.LC_NO_HEADER | wx.BORDER_NONE,
            )
            list_ctrl.SetName(f"Validation {label.lower()} list")
            list_ctrl.InsertColumn(0, label, width=400)
            gp.Add(list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
            group_panel.SetSizer(gp)
            vrp.Add(group_panel, 1, wx.EXPAND | wx.ALL, 2)
            setattr(self, attr, list_ctrl)

        self._val_result_panel.SetSizer(vrp)
        self._val_result_panel.Hide()
        sizer.Add(self._val_result_panel, 0, wx.EXPAND | wx.ALL, 4)

        # ── Follow-up bar ─────────────────────────────────────────────────────
        fu_panel = wx.Panel(self)
        fu_panel.SetBackgroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE)
        )
        fu = wx.BoxSizer(wx.HORIZONTAL)

        # The StaticText acts as the visible label for the TextCtrl
        fu_lbl = wx.StaticText(fu_panel, label="Follow-up:")
        fu.Add(fu_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)

        self._fu_field = wx.TextCtrl(
            fu_panel,
            style=wx.TE_PROCESS_ENTER,
            size=(-1, 32),
        )
        self._fu_field.SetHint("Ask a follow-up question…")
        self._fu_field.SetName("Follow-up question")
        # Pair the label with the field for screen readers
        fu_lbl.SetToolTip("Type a question and press Enter to ask")
        self._fu_field.Bind(wx.EVT_TEXT_ENTER, self._on_follow_up_submit)
        fu.Add(self._fu_field, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 8)

        self._fu_btn = wx.Button(fu_panel, label="Ask", size=(64, 44))
        self._fu_btn.SetName("Send follow-up question")
        self._fu_btn.SetToolTip("Send your follow-up question")
        self._fu_btn.Bind(wx.EVT_BUTTON, self._on_follow_up_submit)
        fu.Add(self._fu_btn, 0, wx.RIGHT, 8)

        fu_panel.SetSizer(fu)
        fu_panel.SetMinSize((-1, 48))

        self._fu_divider  = wx.StaticLine(self)
        self._fu_panel    = fu_panel

        sizer.Add(self._fu_divider, 0, wx.EXPAND)
        sizer.Add(fu_panel, 0, wx.EXPAND)

        self.SetSizer(sizer)

    # ── State machine ─────────────────────────────────────────────────────────

    def _show_state(self, state: str) -> None:
        panels = {
            "empty":   self._empty_panel,
            "ready":   self._ready_panel,
            "loading": self._loading_panel,
            "result":  self._result_window,
            "error":   self._error_panel,
        }
        for name, panel in panels.items():
            panel.Show(name == state)

        show_fu = state in ("result",)
        self._fu_panel.Show(show_fu)
        self._fu_divider.Show(show_fu)
        show_actions = state in ("result", "loading")
        self._copy_btn.Show(show_actions)
        self._save_btn.Show(show_actions)

        self.Layout()

    def set_focus(self) -> None:
        """Move keyboard focus to the analysis output view."""
        self._result_window.SetFocus()

    # ── Public API ────────────────────────────────────────────────────────────

    def show_file(self, file: UIFile) -> None:
        self._current_file = file
        self._file_label.SetLabel(file.name)
        self._analyze_btn.SetLabel("Re-analyze" if file.analysis else "Analyze")
        self._analyze_btn.SetName(
            f"Re-analyze {file.name}" if file.analysis else f"Analyze {file.name}"
        )

        # Attachment strip
        if file.attached_image_path:
            self._attach_lbl.SetLabel(file.attached_image_path)
            self._attach_panel.Show()
        else:
            self._attach_panel.Hide()

        # Validate button — enabled only when analysis exists + screenshot attached
        can_validate = bool(file.analysis and file.attached_image_path)
        self._validate_btn.Enable(can_validate)
        if not can_validate:
            reasons = []
            if not file.analysis:
                reasons.append("run an analysis first")
            if not file.attached_image_path:
                reasons.append("attach a screenshot via right-click in the sidebar")
            self._validate_btn.SetToolTip(
                "Validate against screenshot (Ctrl+Shift+V). "
                "To enable: " + " and ".join(reasons) + "."
            )
        else:
            lbl = "Re-validate" if file.analysis and file.analysis.validation else "Validate"
            self._validate_btn.SetLabel(lbl)
            self._validate_btn.SetName(f"{lbl} {file.name} against screenshot")
            self._validate_btn.SetToolTip(
                "Compare the analysis against the attached screenshot (Ctrl+Shift+V)"
            )

        if file.is_analyzing:
            self._show_state("loading")
            self._status_bar.SetStatusText(f"Analyzing {file.name}…")
        elif file.is_validating:
            self.show_validation_progress()
        elif file.validate_error:
            self.show_validation_error(file.validate_error)
        elif file.analyze_error:
            self._error_lbl.SetLabel(f"Analysis failed:\n{file.analyze_error}")
            self._show_state("error")
            self._status_bar.SetStatusText(f"Analysis failed for {file.name}")
        elif file.analysis:
            self._display_analysis(file.analysis)
            if file.analysis.validation:
                self.show_validation_result(file.analysis.validation)
        else:
            self._show_state("ready")
            self._status_bar.SetStatusText(
                f"Ready — press Ctrl+R or click Analyze to describe {file.name}"
            )

    def stream_chunk(self, text: str) -> None:
        """Called from background thread via wx.CallAfter."""
        self._show_state("loading")
        # Use SetValue only for the first chunk, then AppendText for subsequent.
        # AppendText fires EVT_TEXT which AT can monitor; SetValue replaces the
        # buffer and NVDA may not announce the change reliably.
        current = self._stream_text.GetValue()
        if not current:
            self._stream_text.SetValue(text)
        else:
            # Calculate the new suffix and append only that
            new_suffix = text[len(current):]
            if new_suffix:
                self._stream_text.AppendText(new_suffix)
        self._stream_text.SetInsertionPointEnd()

    def show_analysis_complete(self, file: UIFile) -> None:
        self._current_file = file
        self._analyze_btn.SetLabel("Re-analyze")
        self._analyze_btn.SetName(f"Re-analyze {file.name}")
        if file.analysis:
            self._display_analysis(file.analysis)
        self._status_bar.SetStatusText(f"Analysis complete — {file.name}")
        # Announce to screen reader
        if _HAS_ACCESSIBLE_WV and hasattr(self._result_view, "status"):
            self._result_view.status(f"Analysis complete for {file.name}. "
                                      "Use heading navigation to move between sections.")

    def show_error(self, file: UIFile) -> None:
        self._current_file = file
        self._error_lbl.SetLabel(
            f"Analysis failed:\n{file.analyze_error or 'Unknown error'}"
        )
        self._show_state("error")
        self._status_bar.SetStatusText(f"Analysis failed — {file.name}")
        self._retry_btn.SetFocus()  # move AT focus so screen readers announce the error state

    def show_attachment_strip(self, file: UIFile) -> None:
        """Refresh the attachment strip after an attach/detach operation."""
        self._current_file = file
        if file.attached_image_path:
            self._attach_lbl.SetLabel(file.attached_image_path)
            self._attach_panel.Show()
        else:
            self._attach_panel.Hide()
        can_validate = bool(file.analysis and file.attached_image_path)
        self._validate_btn.Enable(can_validate)
        self.Layout()

    def show_validation_progress(self) -> None:
        self._val_result_panel.Hide()
        self._val_error_panel.Hide()
        self._val_progress_panel.Show()
        self._validate_btn.SetLabel("Validating…")
        self._validate_btn.Disable()
        self._status_bar.SetStatusText("Validating against screenshot…")
        self.Layout()

    def show_validation_error(self, msg: str) -> None:
        self._val_progress_panel.Hide()
        self._val_result_panel.Hide()
        self._val_error_lbl.SetLabel(f"Validation failed: {msg}")
        self._val_error_panel.Show()
        self._validate_btn.SetLabel("Re-validate")
        self._validate_btn.Enable()
        self._status_bar.SetStatusText("Validation failed")
        self.Layout()

    def show_validation_result(self, result: ValidationResult) -> None:
        self._val_progress_panel.Hide()
        self._val_error_panel.Hide()

        def _populate(list_ctrl: wx.ListCtrl, items: list) -> None:
            list_ctrl.DeleteAllItems()
            for i, item in enumerate(items):
                list_ctrl.InsertItem(i, item.text)
            # Auto-size the column to content
            list_ctrl.SetColumnWidth(0, wx.LIST_AUTOSIZE)
            # Cap height based on item count
            row_h = list_ctrl.GetItemRect(0).height if items else 24
            list_ctrl.SetMinSize((-1, min(max(row_h * len(items), 24), 200)))

        if result.stands_by:
            _populate(self._val_stands_box, result.stands_by)
        if result.retracts:
            _populate(self._val_retracts_box, result.retracts)
        if result.additions:
            _populate(self._val_additions_box, result.additions)

        self._val_result_panel.Show()
        self._validate_btn.SetLabel("Re-validate")
        self._validate_btn.Enable()
        self._status_bar.SetStatusText("Validation complete")
        self.Layout()

        # Announce to screen reader
        total = (len(result.stands_by) + len(result.retracts) + len(result.additions))
        if _HAS_ACCESSIBLE_WV and hasattr(self._result_view, "status"):
            self._result_view.status(
                f"Validation complete. "
                f"{len(result.stands_by)} confirmed, "
                f"{len(result.retracts)} retracted, "
                f"{len(result.additions)} new additions."
            )

    def append_follow_up(self, answer: str) -> None:
        """Append follow-up answer to the output view."""
        if _HAS_ACCESSIBLE_WV and hasattr(self._result_view, "append"):
            self._result_view.append(
                f"<hr><div role='region' aria-label='Follow-up answer'>"
                f"<p>{answer}</p></div>"
            )
        elif hasattr(self._result_view, "RunScript"):
            # Fallback for plain WebView
            escaped = answer.replace("\\", "\\\\").replace("`", "\\`")
            self._result_view.RunScript(
                f"document.body.insertAdjacentHTML('beforeend', "
                f"`<hr><p>{escaped}</p>`);"
            )

    def get_output_text(self) -> str:
        """Return the current analysis text for copy/save."""
        f = self._current_file
        if f and f.analysis:
            return f.analysis.content
        return self._stream_text.GetValue()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _display_analysis(self, analysis: UIAnalysis) -> None:
        if analysis.is_html or analysis.content.lstrip().startswith("<!DOCTYPE"):
            html = analysis.content
        else:
            html = _md_to_html(analysis.content)

        if _HAS_ACCESSIBLE_WV and hasattr(self._result_view, "set_content"):
            self._result_view.set_content(html)
        elif hasattr(self._result_view, "SetPage"):
            self._result_view.SetPage(html, "about:blank")

        self._show_state("result")

    def _on_mode_change(self, _event: wx.CommandEvent) -> None:
        idx = self._mode_choice.GetSelection()
        self._current_mode = OutputMode.PROSE if idx == 0 else OutputMode.TABLE
        # Enable/disable rather than show/hide — keeps the control in the tab
        # order so screen readers don't lose their place
        if self._current_mode == OutputMode.TABLE:
            self._fmt_choice.Enable()
        else:
            self._fmt_choice.Disable()
        self.Layout()

    def _on_fmt_change(self, _event: wx.CommandEvent) -> None:
        idx = self._fmt_choice.GetSelection()
        self._current_fmt = TableFormat.MARKDOWN if idx == 0 else TableFormat.HTML

    def _on_analyze_click(self, _event: wx.CommandEvent) -> None:
        if self._current_file:
            self._analyze_btn.SetLabel("Analyzing…")
            self._analyze_btn.Disable()
            self._show_state("loading")
            self._stream_text.SetValue("")
            self._stream_text.SetFocus()  # move AT focus so screen readers announce live output
            self._on_analyze(self._current_file, self._current_mode, self._current_fmt)

    def _on_validate_click(self, _event: wx.CommandEvent) -> None:
        if self._current_file and self._on_validate:
            self._on_validate(self._current_file)

    def _on_detach_click(self, _event: wx.CommandEvent) -> None:
        if self._current_file and self._on_detach:
            self._on_detach(self._current_file)

    def _on_webview_message(self, event: wx.html2.WebViewEvent) -> None:
        msg = event.GetString()
        if msg == "analyze":
            self._on_analyze_click(event)
        elif msg == "validate":
            self._on_validate_click(event)

    def _on_follow_up_submit(self, _event: wx.CommandEvent) -> None:
        question = self._fu_field.GetValue().strip()
        if question:
            self._fu_field.SetValue("")
            self._fu_btn.Disable()
            self._on_follow_up(question)

    def enable_follow_up_btn(self) -> None:
        self._fu_btn.Enable()
        self._fu_field.SetFocus()
