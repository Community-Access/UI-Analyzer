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
    ) -> None:
        super().__init__(parent)
        self._on_select             = on_select
        self._on_open_folder        = on_open_folder
        self._on_attachment_changed = on_attachment_changed
        self._on_activate           = on_activate   # Enter / double-click → analyze
        self._files: list[UIFile]   = []

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

    def _refresh_hint(self) -> None:
        has_files = bool(self._files)
        self._list.Show(has_files)
        self._hint.Show(not has_files)
        self.Layout()
