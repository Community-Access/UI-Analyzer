"""CrawlDialog — enter a localhost URL and configure crawler settings."""

from __future__ import annotations

import wx

from ui_analyzer.services.localhost_crawler import CrawlConfig


class CrawlDialog(wx.Dialog):
    """Modal dialog that lets the user enter a localhost URL and tune crawl limits.

    Usage:
        dlg = CrawlDialog(parent, config)
        if dlg.ShowModal() == wx.ID_OK:
            url = dlg.url
            cfg = dlg.config
    """

    def __init__(self, parent: wx.Window, config: CrawlConfig) -> None:
        super().__init__(
            parent,
            title="Crawl Localhost Site",
            size=(480, 340),
            style=wx.DEFAULT_DIALOG_STYLE,
        )
        self._config = CrawlConfig(
            max_pages=config.max_pages,
            max_depth=config.max_depth,
            wait_seconds=config.wait_seconds,
            timeout=config.timeout,
        )
        self._build_ui()
        self.CentreOnParent()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ── Heading
        heading = wx.StaticText(panel, label="Crawl a running local web app")
        heading.SetFont(heading.GetFont().Scaled(1.1).Bold())
        sizer.Add(heading, 0, wx.ALL, 12)

        desc = wx.StaticText(
            panel,
            label=(
                "Enter the start URL of your local dev server. "
                "UI Analyzer will follow links and add each page to the sidebar for analysis."
            ),
        )
        desc.Wrap(440)
        sizer.Add(desc, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # ── URL field
        grid = wx.FlexGridSizer(cols=2, vgap=10, hgap=12)
        grid.AddGrowableCol(1, 1)

        url_lbl = wx.StaticText(panel, label="Start URL:")
        self._url_field = wx.TextCtrl(panel, value="http://localhost:3000", size=(280, -1))
        self._url_field.SetName("Start URL")
        self._url_field.SetToolTip(
            "Full URL of the first page to crawl, e.g. http://localhost:3000"
        )
        grid.Add(url_lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._url_field, 1, wx.EXPAND)

        # ── Max pages
        pages_lbl = wx.StaticText(panel, label="Max pages:")
        self._pages_spin = wx.SpinCtrl(
            panel, value=str(self._config.max_pages),
            min=1, max=200, size=(80, -1),
        )
        self._pages_spin.SetName("Maximum pages to crawl")
        self._pages_spin.SetToolTip("Stop after visiting this many pages (1–200)")
        grid.Add(pages_lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._pages_spin, 0)

        # ── Max depth
        depth_lbl = wx.StaticText(panel, label="Max depth:")
        self._depth_spin = wx.SpinCtrl(
            panel, value=str(self._config.max_depth),
            min=1, max=5, size=(80, -1),
        )
        self._depth_spin.SetName("Maximum crawl depth")
        self._depth_spin.SetToolTip(
            "How many links deep to follow from the start page (1–5)"
        )
        grid.Add(depth_lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._depth_spin, 0)

        # ── Pause between pages
        wait_lbl = wx.StaticText(panel, label="Pause between pages (s):")
        self._wait_spin = wx.SpinCtrlDouble(
            panel, value=str(self._config.wait_seconds),
            min=0.0, max=5.0, inc=0.5, size=(80, -1),
        )
        self._wait_spin.SetDigits(1)
        self._wait_spin.SetName("Pause between pages in seconds")
        self._wait_spin.SetToolTip(
            "Brief pause after each page load — increase for slow servers (0–5 s)"
        )
        grid.Add(wait_lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._wait_spin, 0)

        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 12)

        # ── Note
        note = wx.StaticText(
            panel,
            label=(
                "Note: this crawler uses static HTTP fetching. "
                "For JS-rendered pages (React SPA, Vue SPA) "
                "analysis runs on the source HTML — results may be less detailed than with a "
                "vision-capable model and a screenshot attached."
            ),
        )
        note.Wrap(440)
        note.SetForegroundColour(wx.Colour(100, 100, 100))
        sizer.Add(note, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # ── Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, "Cancel", size=(-1, 44))
        ok_btn = wx.Button(panel, wx.ID_OK, "Start Crawl", size=(-1, 44))
        ok_btn.SetDefault()
        ok_btn.SetName("Start crawl")
        cancel_btn.SetName("Cancel")
        btn_sizer.Add(cancel_btn, 0, wx.RIGHT, 8)
        btn_sizer.Add(ok_btn, 0, wx.RIGHT, 12)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.BOTTOM, 12)

        panel.SetSizer(sizer)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    def _on_ok(self, event: wx.CommandEvent) -> None:
        url = self._url_field.GetValue().strip()
        if not url.startswith(("http://localhost", "http://127.0.0.1",
                                "http://0.0.0.0", "https://localhost")):
            wx.MessageBox(
                "Please enter a localhost URL, e.g. http://localhost:3000",
                "Invalid URL",
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return
        self._config.max_pages    = self._pages_spin.GetValue()
        self._config.max_depth    = self._depth_spin.GetValue()
        self._config.wait_seconds = self._wait_spin.GetValue()
        event.Skip()

    # ── Properties accessed after ShowModal() ─────────────────────────────────

    @property
    def url(self) -> str:
        return self._url_field.GetValue().strip()

    @property
    def config(self) -> CrawlConfig:
        return self._config
