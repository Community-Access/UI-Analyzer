"""Main application window."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

import wx

from ui_analyzer.models.ui_file import UIFile, OutputMode, TableFormat
from ui_analyzer.services.file_scanner import scan_folder
from ui_analyzer.services.ai_client import AIClient
from ui_analyzer.services.config_manager import ConfigManager
from ui_analyzer.services.ollama_client import OllamaClient
from ui_analyzer.services.anthropic_client import AnthropicClient
from ui_analyzer.services.openai_client import OpenAIClient
from ui_analyzer.services.ui_analyzer import UIAnalyzer
from ui_analyzer.views.sidebar import SidebarPanel
from ui_analyzer.views.detail_panel import DetailPanel, _HAS_ACCESSIBLE_WV
from ui_analyzer.views.model_picker import ModelPickerDialog
from ui_analyzer.views.settings_dialog import SettingsDialog

_APP_NAME    = "UI Analyzer"
_DEFAULT_W   = 1100
_DEFAULT_H   = 720
_SIDEBAR_W   = 240

# Keyboard shortcut IDs
_ID_OPEN_FOLDER   = wx.NewIdRef()
_ID_ANALYZE       = wx.NewIdRef()
_ID_BUILD_CONTEXT = wx.NewIdRef()
_ID_ASK_PROJECT   = wx.NewIdRef()
_ID_COPY          = wx.NewIdRef()
_ID_SAVE          = wx.NewIdRef()
_ID_MODEL_PICKER  = wx.NewIdRef()
_ID_SETTINGS      = wx.NewIdRef()
_ID_VALIDATE      = wx.NewIdRef()


class MainFrame(wx.Frame):
    """Top-level window.

    Accessibility highlights:
    • Menu bar with full keyboard access (Alt + menu key)
    • AcceleratorTable mirrors all menu shortcuts for direct key access
    • Status bar provides live region-style updates for AT
    • All background work posted back via wx.CallAfter (thread-safe UI updates)
    • Focus management: after analysis completes, focus moves to output view
    """

    def __init__(self) -> None:
        super().__init__(
            None,
            title=_APP_NAME,
            size=(_DEFAULT_W, _DEFAULT_H),
        )
        self._config   = ConfigManager()
        self._client   = self._init_ai_client()
        self._model: Optional[str] = None
        self._analyzer: Optional[UIAnalyzer] = None
        self._current_file: Optional[UIFile] = None
        self._files: list[UIFile] = []

        self._build_ui()
        self._build_menu()
        self._build_accelerators()
        self._auto_select_model()
        self.Centre()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Status bar — AT reads this on change
        self._status = self.CreateStatusBar(2)
        self._status.SetStatusWidths([-1, 200])
        self._status.SetStatusText("Ready", 0)
        self._status.SetStatusText("No model selected", 1)

        # Splitter
        self._splitter = wx.SplitterWindow(
            self,
            style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH,
        )
        self._splitter.SetMinimumPaneSize(160)

        self._sidebar = SidebarPanel(
            self._splitter,
            on_select=self._on_file_selected,
            on_open_folder=self._open_folder_dialog,
            on_drop_folder=self._load_folder,
            on_attachment_changed=self._on_attachment_changed,
            on_activate=self._trigger_analyze,
        )

        self._detail = DetailPanel(
            self._splitter,
            on_analyze=self._start_analyze,
            on_copy=self._copy_output,
            on_save=self._save_output,
            on_follow_up=self._send_follow_up,
            status_bar=self._status,
            on_validate=self._start_validate,
            on_detach=self._on_detail_detach,
        )

        self._splitter.SplitVertically(self._sidebar, self._detail, _SIDEBAR_W)

    def _build_menu(self) -> None:
        mb = wx.MenuBar()

        # File menu
        file_menu = wx.Menu()
        file_menu.Append(_ID_OPEN_FOLDER, "Open Folder…\tCtrl+O",
                          "Open a folder of UI source files")
        file_menu.AppendSeparator()
        file_menu.Append(_ID_MODEL_PICKER, "Choose AI Model…\tCtrl+M",
                          "Select which Ollama model to use")
        file_menu.Append(_ID_SETTINGS, "Settings…\tCtrl+,",
                          "Configure AI providers and connectivity")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "Quit\tCtrl+Q")
        mb.Append(file_menu, "&File")

        # Analysis menu
        an_menu = wx.Menu()
        an_menu.Append(_ID_ANALYZE, "Analyze / Re-analyze\tCtrl+R",
                        "Run AI analysis on the selected file")
        an_menu.AppendSeparator()
        an_menu.Append(_ID_VALIDATE, "Validate / Re-validate\tCtrl+Shift+V",
                        "Compare the analysis against the attached screenshot")
        an_menu.AppendSeparator()
        an_menu.Append(_ID_BUILD_CONTEXT, "Build Project Context\tCtrl+Shift+A",
                        "Summarise all files for cross-file questions")
        an_menu.Append(_ID_ASK_PROJECT, "Ask Project Question\tCtrl+Shift+I",
                        "Ask a question about the whole project")
        mb.Append(an_menu, "&Analysis")

        # Edit menu
        edit_menu = wx.Menu()
        edit_menu.Append(_ID_COPY, "Copy Output\tCtrl+Shift+C",
                          "Copy the analysis output to the clipboard")
        edit_menu.Append(_ID_SAVE, "Save Output…\tCtrl+S",
                          "Save the analysis to a file")
        mb.Append(edit_menu, "&Edit")

        self.SetMenuBar(mb)

        # Bind menu events
        self.Bind(wx.EVT_MENU, lambda _e: self._open_folder_dialog(),  id=_ID_OPEN_FOLDER)
        self.Bind(wx.EVT_MENU, lambda _e: self._trigger_analyze(),     id=_ID_ANALYZE)
        self.Bind(wx.EVT_MENU, lambda _e: self._trigger_validate(),   id=_ID_VALIDATE)
        self.Bind(wx.EVT_MENU, lambda _e: self._build_project_context(), id=_ID_BUILD_CONTEXT)
        self.Bind(wx.EVT_MENU, lambda _e: self._open_ask_project_dialog(), id=_ID_ASK_PROJECT)
        self.Bind(wx.EVT_MENU, lambda _e: self._copy_output(),         id=_ID_COPY)
        self.Bind(wx.EVT_MENU, lambda _e: self._save_output(),         id=_ID_SAVE)
        self.Bind(wx.EVT_MENU, lambda _e: self._open_model_picker(),   id=_ID_MODEL_PICKER)
        self.Bind(wx.EVT_MENU, lambda _e: self._open_settings_dialog(),   id=_ID_SETTINGS)
        self.Bind(wx.EVT_MENU, lambda _e: self.Close(),                id=wx.ID_EXIT)

    def _build_accelerators(self) -> None:
        # Duplicate menu shortcuts as accelerators so they work
        # even when focus is in a wx.TextCtrl or WebView
        accel_entries = [
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("O"), _ID_OPEN_FOLDER),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("R"), _ID_ANALYZE),
            wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("V"), _ID_VALIDATE),
            wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("A"), _ID_BUILD_CONTEXT),
            wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("I"), _ID_ASK_PROJECT),
            wx.AcceleratorEntry(wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("C"), _ID_COPY),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("S"), _ID_SAVE),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("M"), _ID_MODEL_PICKER),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord(","), _ID_SETTINGS),
        ]
        self.SetAcceleratorTable(wx.AcceleratorTable(accel_entries))

    def _init_ai_client(self) -> AIClient:
        """Instantiate the correct AI client based on current configuration."""
        provider = self._config.get("provider", "ollama")

        if provider == "ollama":
            url = self._config.get("ollama_url", "http://localhost:11434")
            return OllamaClient(base_url=url)
        elif provider == "anthropic":
            key = self._config.get_api_key("anthropic")
            if not key:
                return OllamaClient(base_url="http://localhost:11434") # Fallback
            return AnthropicClient(api_key=key)
        elif provider == "openai":
            key = self._config.get_api_key("openai")
            if not key:
                return OllamaClient(base_url="http://localhost:11434") # Fallback
            return OpenAIClient(api_key=key)

        return OllamaClient(base_url="http://localhost:11434")

    def _open_settings_dialog(self) -> None:
        dlg = SettingsDialog(self, self._config)
        if dlg.ShowModal() == wx.ID_OK:
            # Settings changed, re-init client and analyzer
            self._client = self._init_ai_client()
            self._model = None
            self._auto_select_model()
        dlg.Destroy()


    # ── Model selection ───────────────────────────────────────────────────────

    def _auto_select_model(self) -> None:
        """Pick the first available model, or prompt if none installed."""
        models = self._client.list_models()
        if models:
            self._model = models[0]["name"]
            self._analyzer = UIAnalyzer(self._client, self._model)
            self._status.SetStatusText(f"Model: {self._model}", 1)
        elif not self._client.is_available():
            self._status.SetStatusText("Ollama not running", 1)
            wx.MessageBox(
                "Ollama is not running.\n\n"
                "Install from ollama.com, then start it with:\n  ollama serve\n\n"
                "Then restart UI Analyzer.",
                "Ollama Required",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        else:
            self._status.SetStatusText("No models installed", 1)
            wx.MessageBox(
                "No Ollama models are installed.\n\n"
                "Run in a terminal:\n  ollama pull qwen2.5-coder:7b\n\n"
                "Then use File → Choose AI Model to select it.",
                "No Models Found",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )

    def _open_model_picker(self) -> None:
        file_type_label = (self._current_file.file_type.value
                           if self._current_file else "")
        dlg = ModelPickerDialog(
            self,
            self._client,
            current_model=self._model or "",
            file_type_label=file_type_label,
        )
        if dlg.ShowModal() == wx.ID_OK and dlg.selected_model:
            self._model = dlg.selected_model
            self._analyzer = UIAnalyzer(self._client, self._model)
            self._status.SetStatusText(f"Model: {self._model}", 1)
        dlg.Destroy()

    # ── Folder / file management ──────────────────────────────────────────────

    def _open_folder_dialog(self) -> None:
        dlg = wx.DirDialog(
            self,
            message="Choose a folder containing UI source files",
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST,
        )
        if dlg.ShowModal() == wx.ID_OK:
            self._load_folder(Path(dlg.GetPath()))
        dlg.Destroy()

    def _load_folder(self, folder: Path) -> None:
        self.SetTitle(f"{_APP_NAME} — {folder.name}")
        self._status.SetStatusText(f"Scanning {folder.name}…")
        wx.SafeYield()

        def do_scan() -> None:
            files = scan_folder(folder)
            wx.CallAfter(self._on_scan_complete, files)

        threading.Thread(target=do_scan, daemon=True).start()

    def _on_scan_complete(self, files: list[UIFile]) -> None:
        self._files = files
        self._sidebar.set_files(files)
        count = len(files)
        self._status.SetStatusText(
            f"{count} file{'s' if count != 1 else ''} found — select one to analyze"
        )
        if files:
            self._sidebar.select_file(files[0])

    def _on_file_selected(self, file: UIFile) -> None:
        self._current_file = file
        self._detail.show_file(file)
        if self._analyzer and self._model and self._config.get("provider") == "ollama":
            from ui_analyzer.services.ollama_client import best_model_for_filetype
            recommended = best_model_for_filetype(
                [m["name"] for m in self._client.list_models()],
                file.file_type.value,
            )
            if recommended and recommended != self._model:
                self._status.SetStatusText(
                    f"Tip: {recommended} is recommended for {file.file_type.value} files. "
                    f"Use Ctrl+M to switch.",
                    0,
                )

    # ── Analysis ──────────────────────────────────────────────────────────────

    def _trigger_analyze(self, file: Optional[UIFile] = None) -> None:
        if file is None:
            file = self._current_file
        if self._current_file is None and file is not None:
            self._current_file = file
        if self._current_file:
            file = self._current_file
            # Read current mode/format from detail panel's choices
            mode_idx = self._detail._mode_choice.GetSelection()
            mode = OutputMode.PROSE if mode_idx == 0 else OutputMode.TABLE
            fmt_idx = self._detail._fmt_choice.GetSelection()
            fmt = TableFormat.MARKDOWN if fmt_idx == 0 else TableFormat.HTML
            self._start_analyze(file, mode, fmt)

    def _start_analyze(self, file: UIFile, mode: OutputMode, fmt: TableFormat) -> None:
        if not self._analyzer:
            wx.MessageBox("No AI model selected. Use File → Choose AI Model.",
                          "No Model", wx.OK | wx.ICON_WARNING, self)
            return

        file.is_analyzing  = True
        file.analyze_error = None
        self._sidebar.update_file(file)
        self._detail.show_file(file)
        self._status.SetStatusText(f"Analyzing {file.name}…")

        analyzer = self._analyzer

        def do_analysis() -> None:
            try:
                def on_chunk(text: str) -> None:
                    wx.CallAfter(self._detail.stream_chunk, text)

                analysis = analyzer.analyze(file, mode, fmt, on_chunk)
                file.analysis     = analysis
                file.is_analyzing = False
                wx.CallAfter(self._on_analysis_done, file)
            except Exception as exc:
                file.is_analyzing  = False
                file.analyze_error = str(exc)
                wx.CallAfter(self._on_analysis_error, file)

        threading.Thread(target=do_analysis, daemon=True).start()

    def _on_analysis_done(self, file: UIFile) -> None:
        self._sidebar.update_file(file)
        self._detail.show_analysis_complete(file)
        self._analyze_btn_reset()
        # Move focus to the output view so screen readers immediately read the result
        # (NVDA/JAWS announce the view's accessible name + content on focus)
        self._detail.set_focus()

    def _on_analysis_error(self, file: UIFile) -> None:
        self._sidebar.update_file(file)
        self._detail.show_error(file)
        self._analyze_btn_reset()

    def _analyze_btn_reset(self) -> None:
        btn = self._detail._analyze_btn
        btn.SetLabel("Re-analyze")
        btn.Enable()

    # ── Validate ──────────────────────────────────────────────────────────────

    def _trigger_validate(self) -> None:
        if self._current_file:
            self._start_validate(self._current_file)

    def _start_validate(self, file: UIFile) -> None:
        if not self._analyzer:
            wx.MessageBox("No AI model selected. Use File → Choose AI Model.",
                          "No Model", wx.OK | wx.ICON_WARNING, self)
            return
        if not file.analysis:
            wx.MessageBox("Analyze this file first before validating.",
                          "No Analysis", wx.OK | wx.ICON_WARNING, self)
            return
        if not file.attached_image_path:
            wx.MessageBox(
                "No screenshot attached.\n\n"
                "Right-click the file in the sidebar and choose Attach Screenshot…",
                "No Screenshot", wx.OK | wx.ICON_WARNING, self,
            )
            return

        file.is_validating  = True
        file.validate_error = None
        self._detail.show_validation_progress()

        analyzer = self._analyzer
        prior    = file.analysis

        def do_validate() -> None:
            try:
                result = analyzer.validate_against_screenshot(file, prior)
                prior.validation = result
                file.is_validating = False
                wx.CallAfter(self._on_validation_done, file)
            except Exception as exc:
                file.is_validating  = False
                file.validate_error = str(exc)
                wx.CallAfter(self._on_validation_error, file)

        threading.Thread(target=do_validate, daemon=True).start()

    def _on_validation_done(self, file: UIFile) -> None:
        if file.analysis and file.analysis.validation:
            self._detail.show_validation_result(file.analysis.validation)
        self._status.SetStatusText(f"Validation complete — {file.name}")

    def _on_validation_error(self, file: UIFile) -> None:
        self._detail.show_validation_error(file.validate_error or "Unknown error")
        self._status.SetStatusText(f"Validation failed — {file.name}")

    # ── Attachment callbacks ───────────────────────────────────────────────────

    def _on_attachment_changed(self, file: UIFile) -> None:
        """Called by SidebarPanel after attach or detach."""
        self._detail.show_attachment_strip(file)
        # If this is the currently-displayed file, refresh the full panel
        if self._current_file and self._current_file.id == file.id:
            self._current_file = file
            self._detail.show_file(file)

    def _on_detail_detach(self, file: UIFile) -> None:
        """Called by the Detach button in the attachment strip."""
        self._sidebar._detach_screenshot(file)

    # ── Follow-up ─────────────────────────────────────────────────────────────

    def _send_follow_up(self, question: str) -> None:
        if not self._analyzer or not self._current_file:
            return

        analyzer  = self._analyzer
        file_id   = self._current_file.id
        self._status.SetStatusText("Thinking…")

        def do_follow_up() -> None:
            try:
                chunks: list[str] = []
                def on_chunk(text: str) -> None:
                    chunks.append(text)
                answer = analyzer.ask_follow_up(file_id, question, on_chunk)
                wx.CallAfter(self._on_follow_up_done, answer)
            except Exception as exc:
                wx.CallAfter(self._status.SetStatusText, f"Follow-up error: {exc}")
                wx.CallAfter(self._detail.enable_follow_up_btn)

        threading.Thread(target=do_follow_up, daemon=True).start()

    def _on_follow_up_done(self, answer: str) -> None:
        self._detail.append_follow_up(answer)
        self._detail.enable_follow_up_btn()
        self._status.SetStatusText("Ready")

    # ── Project context ───────────────────────────────────────────────────────

    def _build_project_context(self) -> None:
        if not self._analyzer or not self._files:
            wx.MessageBox("Open a folder first.", "No Files", wx.OK, self)
            return

        analyzer = self._analyzer
        files    = list(self._files)
        total    = len(files)
        self._status.SetStatusText(f"Building project context for {total} files…")

        def do_build() -> None:
            try:
                def on_progress(done: int, total: int) -> None:
                    wx.CallAfter(
                        self._status.SetStatusText,
                        f"Building context: {done}/{total}…"
                    )
                analyzer.build_project_context(files, on_progress)
                wx.CallAfter(self._status.SetStatusText,
                             "Project context ready — use Ctrl+Shift+I to ask a question")
            except Exception as exc:
                wx.CallAfter(self._status.SetStatusText, f"Context error: {exc}")

        threading.Thread(target=do_build, daemon=True).start()

    def _open_ask_project_dialog(self) -> None:
        if not self._analyzer or not self._analyzer.project_context:
            wx.MessageBox(
                "Build project context first (Ctrl+Shift+A).",
                "No Context", wx.OK, self,
            )
            return

        dlg = ProjectQuestionDialog(self, self._analyzer)
        dlg.ShowModal()
        dlg.Destroy()

    # ── Copy / Save ───────────────────────────────────────────────────────────

    def _copy_output(self) -> None:
        text = self._detail.get_output_text()
        if not text:
            return
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
        self._status.SetStatusText("Copied to clipboard")

    def _save_output(self) -> None:
        text = self._detail.get_output_text()
        if not text:
            return
        file = self._current_file
        is_html = file and file.analysis and file.analysis.is_html
        ext  = "html" if is_html else "md"
        name = (file.path.stem if file else "analysis") + f".{ext}"
        wildcard = "HTML files (*.html)|*.html" if is_html else "Markdown files (*.md)|*.md"

        dlg = wx.FileDialog(
            self, "Save output as", defaultFile=name,
            wildcard=wildcard, style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if dlg.ShowModal() == wx.ID_OK:
            Path(dlg.GetPath()).write_text(text, encoding="utf-8")
            self._status.SetStatusText(f"Saved to {dlg.GetPath()}")
        dlg.Destroy()


# ── Project question dialog ───────────────────────────────────────────────────

class ProjectQuestionDialog(wx.Dialog):
    """Dialog for asking project-level questions."""

    def __init__(self, parent: wx.Frame, analyzer: UIAnalyzer) -> None:
        super().__init__(parent, title="Ask About the Project",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
                         size=(640, 520))
        self._analyzer = analyzer
        self._build_ui()
        self.CentreOnParent()

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        header = wx.StaticText(
            panel,
            label="Ask any question about your project's design quality, "
                  "accessibility, or visual consistency.",
        )
        header.Wrap(580)
        sizer.Add(header, 0, wx.ALL, 12)

        if _HAS_ACCESSIBLE_WV:
            try:
                from wx_accessible_webview import AccessibleWebView  # type: ignore[import]
                self._answer_view = AccessibleWebView(panel)
                self._answer_window = self._answer_view.control
            except Exception:
                self._answer_view = wx.TextCtrl(
                    panel, style=wx.TE_MULTILINE | wx.TE_READONLY
                )
                self._answer_window = self._answer_view
        else:
            self._answer_view = wx.TextCtrl(
                panel, style=wx.TE_MULTILINE | wx.TE_READONLY
            )
            self._answer_window = self._answer_view

        if hasattr(self._answer_window, "SetName"):
            self._answer_window.SetName("Project question answers")
        sizer.Add(self._answer_window, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        # Question bar
        q_row = wx.BoxSizer(wx.HORIZONTAL)
        q_lbl = wx.StaticText(panel, label="Question:")
        q_row.Add(q_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)
        self._q_field = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self._q_field.SetHint("e.g. Is this app professional overall?")
        self._q_field.SetName("Project question")
        self._q_field.Bind(wx.EVT_TEXT_ENTER, self._on_ask)
        q_row.Add(self._q_field, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 8)
        ask_btn = wx.Button(panel, label="Ask")
        ask_btn.SetName("Send project question")
        ask_btn.Bind(wx.EVT_BUTTON, self._on_ask)
        q_row.Add(ask_btn, 0, wx.RIGHT, 12)
        sizer.Add(q_row, 0, wx.EXPAND | wx.BOTTOM, 8)

        close_btn = wx.Button(panel, wx.ID_CLOSE, "Close")
        close_btn.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE))
        sizer.Add(close_btn, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 12)

        panel.SetSizer(sizer)
        self._q_field.SetFocus()

    def _on_ask(self, _event: wx.CommandEvent) -> None:
        question = self._q_field.GetValue().strip()
        if not question:
            return
        self._q_field.SetValue("")

        analyzer = self._analyzer

        def do_ask() -> None:
            try:
                chunks: list[str] = []
                def on_chunk(text: str) -> None:
                    chunks.append(text)
                answer = analyzer.ask_project_question(question, on_chunk)
                wx.CallAfter(self._show_answer, answer)
            except Exception as exc:
                wx.CallAfter(self._show_answer, f"Error: {exc}")

        threading.Thread(target=do_ask, daemon=True).start()

    def _show_answer(self, answer: str) -> None:
        try:
            from wx_accessible_webview import AccessibleWebView  # type: ignore[import]
            if isinstance(self._answer_view, AccessibleWebView):
                self._answer_view.append(f"<p>{answer}</p><hr>")
                return
        except ImportError:
            pass
        if hasattr(self._answer_view, "AppendText"):
            self._answer_view.AppendText(f"\n{answer}\n{'—'*40}\n")
