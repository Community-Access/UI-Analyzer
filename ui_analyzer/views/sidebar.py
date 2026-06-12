"""Sidebar — file list with keyboard navigation and drag-and-drop folder support."""

from __future__ import annotations

import wx
from pathlib import Path
from typing import Callable, Optional

from ui_analyzer.models.ui_file import UIFile, UIFileType

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
    ) -> None:
        super().__init__(parent)
        self._on_select       = on_select
        self._on_open_folder  = on_open_folder
        self._files: list[UIFile] = []

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

        sizer.Add(self._list, 1, wx.EXPAND)

        # ── Drop hint shown when list is empty
        self._hint = wx.StaticText(
            self,
            label="Drop a folder here\nor click Open Folder",
            style=wx.ALIGN_CENTER,
        )
        self._hint.SetForegroundColour(wx.Colour(120, 120, 120))
        sizer.Add(self._hint, 0, wx.ALIGN_CENTER | wx.ALL, 16)

        self.SetSizer(sizer)
        self._refresh_hint()

    # ── Public API ────────────────────────────────────────────────────────────

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
        # Enter key / double-click — same as select
        self._on_item_selected(event)

    def _on_key(self, event: wx.KeyEvent) -> None:
        # Ctrl+O → open folder
        if event.GetKeyCode() == ord("O") and event.ControlDown():
            self._on_open_folder()
        else:
            event.Skip()

    def _refresh_hint(self) -> None:
        has_files = bool(self._files)
        self._list.Show(has_files)
        self._hint.Show(not has_files)
        self.Layout()
