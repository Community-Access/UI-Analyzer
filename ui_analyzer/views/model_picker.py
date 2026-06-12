"""Model selection dialog — lists installed Ollama models with capability descriptions."""

from __future__ import annotations

import wx
from typing import Optional

from ui_analyzer.services.ollama_client import OllamaClient, best_model_for_filetype


class ModelPickerDialog(wx.Dialog):
    """Accessible dialog for choosing an Ollama model.

    Accessibility: uses wx.ListCtrl (virtual list accessible to NVDA/JAWS),
    column headers announced by screen readers, keyboard navigation built in.
    """

    def __init__(self, parent: wx.Window, client: OllamaClient,
                 current_model: str, file_type_label: str = "") -> None:
        super().__init__(parent, title="Choose AI Model",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
                         size=(680, 480))
        self._client         = client
        self._models: list[dict] = []
        self._selected_model: Optional[str] = current_model
        self._file_type_label = file_type_label

        self._build_ui()
        self._load_models()
        self.CentreOnParent()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ── Header label
        header = wx.StaticText(
            panel,
            label="Select the model that best fits your project. "
                  "Recommended models for the current file type are marked ★."
        )
        header.Wrap(620)
        sizer.Add(header, 0, wx.ALL, 12)

        # ── Model list
        self._list = wx.ListCtrl(
            panel,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SIMPLE,
        )
        self._list.SetName("Available models")  # screen reader label
        self._list.InsertColumn(0, "Model",       width=200)
        self._list.InsertColumn(1, "Best for",    width=210)
        self._list.InsertColumn(2, "Min RAM",     width=80)
        self._list.InsertColumn(3, "Size on disk",width=100)
        self._list.InsertColumn(4, "Description", width=280)
        sizer.Add(self._list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        # ── Status / refresh row
        row = wx.BoxSizer(wx.HORIZONTAL)
        self._status = wx.StaticText(panel, label="")
        row.Add(self._status, 1, wx.ALIGN_CENTER_VERTICAL)
        refresh_btn = wx.Button(panel, label="Refresh list", size=(110, 44))
        # SetName is the accessible name (what NVDA/JAWS/Narrator/VoiceOver
        # announce). SetToolTip is the description on hover/focus.
        refresh_btn.SetName("Refresh model list")
        refresh_btn.SetToolTip("Re-query Ollama for installed models")
        refresh_btn.Bind(wx.EVT_BUTTON, self._on_refresh)
        row.Add(refresh_btn, 0, wx.LEFT, 8)
        sizer.Add(row, 0, wx.EXPAND | wx.ALL, 12)

        # ── Ollama info link text
        info = wx.StaticText(
            panel,
            label="Models are installed via Ollama (ollama.com). "
                  "Run: ollama pull qwen2.5-coder:7b"
        )
        sizer.Add(info, 0, wx.LEFT | wx.BOTTOM, 12)

        # ── Dialog buttons
        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(sizer)

        # Events
        self._list.Bind(wx.EVT_LIST_ITEM_SELECTED,   self._on_select)
        self._list.Bind(wx.EVT_LIST_ITEM_ACTIVATED,  self._on_activate)
        self._list.SetFocus()

    # ── Load / refresh ────────────────────────────────────────────────────────

    def _load_models(self) -> None:
        self._status.SetLabel("Querying Ollama…")
        wx.SafeYield()

        if not self._client.is_available():
            self._status.SetLabel(
                "Ollama is not running. Start it with: ollama serve"
            )
            return

        self._models = self._client.list_models()
        self._list.DeleteAllItems()

        if not self._models:
            self._status.SetLabel("No models installed. Run: ollama pull qwen2.5-coder:7b")
            return

        best = best_model_for_filetype(
            [m["name"] for m in self._models], self._file_type_label
        )

        for i, m in enumerate(self._models):
            name = m["name"]
            # Use "(recommended)" text not "★" symbol — screen readers pronounce
            # "recommended" clearly; star character may be read as "star" or skipped
            display_name = f"{name} (recommended)" if name == best else name
            self._list.InsertItem(i, display_name)
            self._list.SetItem(i, 1, ", ".join(m["best_for"]))
            self._list.SetItem(i, 2, f"{m['min_ram_gb']} GB")
            self._list.SetItem(i, 3, f"{m['size_gb']} GB" if m['size_gb'] else "—")
            self._list.SetItem(i, 4, m["description"])

            if name == self._selected_model or (not self._selected_model and name == best):
                self._list.Select(i)
                self._list.EnsureVisible(i)

        count = len(self._models)
        self._status.SetLabel(f"{count} model{'s' if count != 1 else ''} installed.")

    def _on_refresh(self, _event: wx.CommandEvent) -> None:
        self._load_models()

    # ── Selection ─────────────────────────────────────────────────────────────

    def _on_select(self, event: wx.ListEvent) -> None:
        idx = event.GetIndex()
        if 0 <= idx < len(self._models):
            self._selected_model = self._models[idx]["name"]

    def _on_activate(self, _event: wx.ListEvent) -> None:
        self.EndModal(wx.ID_OK)

    @property
    def selected_model(self) -> Optional[str]:
        return self._selected_model
