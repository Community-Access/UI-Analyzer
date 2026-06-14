"""Sidebar — file list with keyboard navigation and drag-and-drop folder support."""

from __future__ import annotations

import shutil
import wx
from pathlib import Path
from typing import Callable, Optional

from ui_analyzer.models.ui_file import UIFile, UIFileType
from ui_analyzer.services.attachment_store import attachment_filename, set_attachment

# File type → short badge shown in the list
_TYPE_BADGE: dict[UIFileType, str] = {
    UIFileType.SWIFT_UI:   "Swift",
    UIFileType.STORYBOARD: "Storyboard",
    UIFileType.XIB:        "XIB",
    UIFileType.HTML:       "HTML",
    UIFileType.CSS:        "CSS",
    UIFileType.REACT_JSX:  "JSX",
    UIFileType.VUE:        "Vue",
    UIFileType.SVELTE:     "Svelte",
    UIFileType.PYTHON:     "Python",
    UIFileType.JAVASCRIPT: "JS",
    UIFileType.TYPESCRIPT: "TS",
    UIFileType.MARKDOWN:   "Markdown",
    UIFileType.IMAGE:      "Image",
}

# Status badge shown after the file name
_STATUS_SUFFIX = {
    "analyzed":  " ✓",
    "analyzing": " …",
    "error":     " ✗",
    "ready":     "",
}


class FolderDropTarget(wx.FileDropTarget):
    """Accepts a dropped folder and calls on_folder with the Path."""

    def __init__(self, on_folder: Callable[[Path], None]) -> None:
        super().__init__()
        self._on_folder = on_folder

    def OnDropFiles(self, x: int, y: int, filenames: list[str]) -> bool:
        for name in filenames:
            p = Path(name)
            if p.is_dir():
                self._on_folder(p)
                return True
        return False


class SidebarPanel(wx.Panel):
    """Accessible file list sidebar.

    Keyboard: Up/Down to move, Enter to open, Delete to remove selected file.
    Screen readers: ListCtrl announces item name + status on focus.
    """

    def __init__(
        self,
        parent: wx.Window,
        on_select: Callable[[UIFile], None],
        on_open_folder: Callable[[], None],
        on_drop_folder: Callable[[Path], None],
        on_attachment_changed: Optional[Callable[[UIFile], None]] = None,
        on_activate: Optional[Callable[[UIFile], None]] = None,
        on_build_context: Optional[Callable[[], None]] = None,
        on_cancel_context: Optional[Callable[[], None]] = None,
        on_clear_context: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._on_select             = on_select
        self._on_open_folder        = on_open_folder
        self._on_attachment_changed = on_attachment_changed
        self._on_activate           = on_activate
        self._on_build_context      = on_build_context
        self._on_cancel_context     = on_cancel_context
        self._on_clear_context      = on_clear_context
        self._files: list[UIFile]   = []
        self._context_state         = "hidden"  # hidden | build | building | clear

        self._build_ui()
        self.SetDropTarget(FolderDropTarget(on_drop_folder))

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ── Toolbar row
        toolbar = wx.BoxSizer(wx.HORIZONTAL)

        lbl = wx.StaticText(self, label="Files")
        lbl.SetFont(lbl.GetFont().Bold())
        toolbar.Add(lbl, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)

        # 44px minimum height satisfies WCAG 2.5.5 touch / click target
        open_btn = wx.Button(self, label="Open Folder…", size=(-1, 44))
        open_btn.SetName("Open folder")
        open_btn.SetToolTip("Open a folder of UI source files (Ctrl+O)")
        open_btn.Bind(wx.EVT_BUTTON, lambda _e: self._on_open_folder())
        toolbar.Add(open_btn, 0, wx.RIGHT | wx.TOP | wx.BOTTOM, 4)

        sizer.Add(toolbar, 0, wx.EXPAND)
        sizer.Add(wx.StaticLine(self), 0, wx.EXPAND)

        # ── File list
        self._list = wx.ListCtrl(
            self,
            # LC_NO_HEADER omitted — column headers help screen readers
            # understand what each column means (NVDA reads them on focus)
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_NONE,
        )
        self._list.SetName("UI source files")
        self._list.InsertColumn(0, "File",   width=170)
        self._list.InsertColumn(1, "Type",   width=65)
        self._list.InsertColumn(2, "Status", width=75)

        self._list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)
        self._list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_activated)
        self._list.Bind(wx.EVT_KEY_DOWN, self._on_key)
        self._list.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self._on_right_click)
        self._list.Bind(wx.EVT_CONTEXT_MENU, self._on_context_menu)

        sizer.Add(self._list, 1, wx.EXPAND)

        # ── Drop hint shown when list is empty
        self._hint = wx.StaticText(
            self,
            label="Drop a folder here\nor click Open Folder",
            style=wx.ALIGN_CENTER,
        )
        self._hint.SetForegroundColour(wx.Colour(120, 120, 120))
        sizer.Add(self._hint, 0, wx.ALIGN_CENTER | wx.ALL, 16)

        # ── Project Context strip (pinned to bottom, matches Mac sidebar) ─────
        sizer.Add(wx.StaticLine(self), 0, wx.EXPAND)

        # "Build Project Context" button — shown when files are loaded
        self._ctx_build_btn = wx.Button(self, label="Build Project Context", size=(-1, 44))
        self._ctx_build_btn.SetName("Build project context")
        self._ctx_build_btn.SetToolTip(
            "Analyse all files so you can ask cross-screen questions (Ctrl+Shift+A)"
        )
        self._ctx_build_btn.Bind(wx.EVT_BUTTON, lambda _e: self._on_build_context and self._on_build_context())
        sizer.Add(self._ctx_build_btn, 0, wx.EXPAND | wx.ALL, 4)

        # "Building…" state: progress gauge + Cancel button
        self._ctx_building_panel = wx.Panel(self)
        bp = wx.BoxSizer(wx.HORIZONTAL)
        self._ctx_gauge = wx.Gauge(self._ctx_building_panel, range=100, size=(-1, 4))
        self._ctx_gauge.SetName("Project context build progress")
        self._ctx_progress_lbl = wx.StaticText(self._ctx_building_panel, label="Analysing…")
        self._ctx_progress_lbl.SetName("Project context build status")
        self._ctx_cancel_btn = wx.Button(self._ctx_building_panel, label="Cancel", size=(-1, 36))
        self._ctx_cancel_btn.SetName("Cancel project context build")
        self._ctx_cancel_btn.SetToolTip("Stop analysing (Escape)")
        self._ctx_cancel_btn.Bind(wx.EVT_BUTTON, lambda _e: self._on_cancel_context and self._on_cancel_context())
        bp.Add(self._ctx_progress_lbl, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        bp.Add(self._ctx_cancel_btn, 0, wx.LEFT | wx.RIGHT, 4)
        self._ctx_building_panel.SetSizer(bp)
        sizer.Add(self._ctx_building_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        # "Clear Project Context" button — shown when context is ready
        self._ctx_clear_btn = wx.Button(self, label="Clear Project Context", size=(-1, 44))
        self._ctx_clear_btn.SetName("Clear project context")
        self._ctx_clear_btn.SetToolTip("Remove the project summary and enable rebuilding")
        self._ctx_clear_btn.Bind(wx.EVT_BUTTON, lambda _e: self._on_clear_context and self._on_clear_context())
        sizer.Add(self._ctx_clear_btn, 0, wx.EXPAND | wx.ALL, 4)

        self.SetSizer(sizer)
        self._refresh_hint()
        self._refresh_context_strip()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_context_state(self, state: str, progress: tuple[int, int] = (0, 0)) -> None:
        """Update the Build Context strip state.

        state: 'hidden' | 'build' | 'building' | 'clear'
        progress: (current, total) when state == 'building'
        """
        self._context_state = state
        if state == "building":
            done, total = progress
            self._ctx_gauge.SetRange(max(total, 1))
            self._ctx_gauge.SetValue(done)
            label = f"Analysing {done}/{total}…"
            self._ctx_progress_lbl.SetLabel(label)
            self._ctx_progress_lbl.SetName(label)
        self._refresh_context_strip()

    def set_files(self, files: list[UIFile]) -> None:
        self._files = files
        self._list.DeleteAllItems()
        for i, f in enumerate(files):
            # Use descriptive words (not symbols) — NVDA/JAWS read column text aloud
            status = "Ready"
            if f.is_analyzing:    status = "Analyzing"
            elif f.analyze_error: status = "Error"
            elif f.analysis:      status = "Analyzed"
            self._list.InsertItem(i, f.name)
            self._list.SetItem(i, 1, _TYPE_BADGE.get(f.file_type, f.file_type.value))
            self._list.SetItem(i, 2, status)
            self._list.SetItemData(i, i)
        self._refresh_hint()

    def update_file(self, file: UIFile) -> None:
        """Refresh a single file's status in the list."""
        for i, f in enumerate(self._files):
            if f.id == file.id:
                self._files[i] = file
                status = "Ready"
                if file.is_analyzing:    status = "Analyzing"
                elif file.analyze_error: status = "Error"
                elif file.analysis:      status = "Analyzed"
                self._list.SetItem(i, 2, status)
                return

    def select_file(self, file: UIFile) -> None:
        for i, f in enumerate(self._files):
            if f.id == file.id:
                self._list.Select(i)
                self._list.EnsureVisible(i)
                return

    @property
    def selected_file(self) -> Optional[UIFile]:
        idx = self._list.GetFirstSelected()
        if 0 <= idx < len(self._files):
            return self._files[idx]
        return None

    # ── Events ────────────────────────────────────────────────────────────────

    def _on_item_selected(self, event: wx.ListEvent) -> None:
        idx = event.GetIndex()
        if 0 <= idx < len(self._files):
            self._on_select(self._files[idx])

    def _on_item_activated(self, event: wx.ListEvent) -> None:
        # Enter key / double-click → select AND trigger analyze
        self._on_item_selected(event)
        idx = event.GetIndex()
        if 0 <= idx < len(self._files) and self._on_activate:
            self._on_activate(self._files[idx])

    def _on_key(self, event: wx.KeyEvent) -> None:
        # Ctrl+O → open folder
        if event.GetKeyCode() == ord("O") and event.ControlDown():
            self._on_open_folder()
        else:
            event.Skip()

    def _on_right_click(self, event: wx.ListEvent) -> None:
        idx = event.GetIndex()
        if 0 <= idx < len(self._files):
            self._list.Select(idx)
            self._show_context_menu(self._files[idx])

    def _on_context_menu(self, event: wx.ContextMenuEvent) -> None:
        # Fired by the keyboard context-menu key (Shift+F10 / Apps key)
        file = self.selected_file
        if file is not None:
            self._show_context_menu(file)

    def _show_context_menu(self, file: UIFile) -> None:
        menu = wx.Menu()
        has_attachment = bool(file.attached_image_path)

        attach_item = menu.Append(wx.ID_ANY, "Attach Screenshot…")
        attach_item.SetHelp("Choose a PNG screenshot to link to this file")
        self.Bind(wx.EVT_MENU, lambda _e: self._attach_screenshot(file), attach_item)

        detach_item = menu.Append(wx.ID_ANY, "Detach Screenshot")
        detach_item.SetHelp("Remove the linked screenshot and delete the sibling file")
        detach_item.Enable(has_attachment)
        self.Bind(wx.EVT_MENU, lambda _e: self._detach_screenshot(file), detach_item)

        self.PopupMenu(menu)
        menu.Destroy()

    def _attach_screenshot(self, file: UIFile) -> None:
        if file.folder_path is None:
            wx.MessageBox(
                "Cannot attach a screenshot: the file was not loaded from a scanned folder.",
                "Attach Screenshot",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        with wx.FileDialog(
            self,
            message=f"Attach screenshot to {file.name}",
            wildcard="PNG images (*.png)|*.png",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            src = Path(dlg.GetPath())

        dest_name = attachment_filename(file.name)
        dest = file.folder_path / dest_name
        try:
            shutil.copy2(src, dest)
        except OSError as exc:
            wx.MessageBox(
                f"Could not copy screenshot:\n{exc}",
                "Attach Screenshot",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        set_attachment(dest_name, file.relative_path)
        file.attached_image_path = dest_name

        if self._on_attachment_changed:
            self._on_attachment_changed(file)

    def _detach_screenshot(self, file: UIFile) -> None:
        if file.folder_path is None or not file.attached_image_path:
            return

        abs_path = file.folder_path / file.attached_image_path
        try:
            if abs_path.is_file():
                abs_path.unlink()
        except OSError as exc:
            wx.MessageBox(
                f"Could not delete screenshot file:\n{exc}",
                "Detach Screenshot",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        set_attachment(None, file.relative_path)
        file.attached_image_path = None

        if self._on_attachment_changed:
            self._on_attachment_changed(file)

    def _refresh_context_strip(self) -> None:
        s = self._context_state
        has_files = bool(self._files)
        self._ctx_build_btn.Show(has_files and s == "build")
        self._ctx_building_panel.Show(has_files and s == "building")
        self._ctx_clear_btn.Show(has_files and s == "clear")
        self.Layout()

    def _refresh_hint(self) -> None:
        has_files = bool(self._files)
        self._list.Show(has_files)
        self._hint.Show(not has_files)
        # Show Build button whenever files are present and no context yet
        if has_files and self._context_state == "hidden":
            self._context_state = "build"
        self._refresh_context_strip()
        self.Layout()
