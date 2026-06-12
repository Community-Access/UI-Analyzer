#!/usr/bin/env python3
"""UI Analyzer — cross-platform UI accessibility analyzer.

Entry point. Initialises the wx.App and shows the main window.

Requirements:
  pip install wxPython wx-accessible-webview httpx pillow pytesseract markdown

On Windows:
  • Ollama must be running (ollama.com)
  • Edge WebView2 Runtime must be installed (ships with Windows 11; installer at
    https://developer.microsoft.com/en-us/microsoft-edge/webview2/)
  • Tesseract OCR optional but recommended for screenshot analysis
    (https://github.com/UB-Mannheim/tesseract/wiki)

On macOS:
  • Ollama must be running
  • Tesseract: brew install tesseract
"""

import sys
from pathlib import Path

import wx
from ui_analyzer.views.main_frame import MainFrame

_ICON_PATH = Path(__file__).parent / "assets" / "app_icon.png"


def _set_app_icon(app: wx.App) -> None:
    """Apply the bundled app icon at startup so the window, taskbar, and
    dialogs (Windows in particular) all show the UI Analyzer icon.

    `wx.IconBundle` accepts PNGs on every platform supported by wxPython
    (Windows / macOS / GTK), so the same source file works across OSes.
    If the file is missing or unreadable, fall back silently — the
    default wx icon is acceptable; the user just doesn't get our branding.
    """
    if not _ICON_PATH.is_file():
        return
    try:
        # `wx.Image` is exposed as `wx.Bitmap` can load PNG directly too,
        # but going through Image gives us a portable path that doesn't
        # depend on wxWidgets' bundled PNG handler quirks on older
        # Windows builds.
        img = wx.Image(str(_ICON_PATH), type=wx.BITMAP_TYPE_PNG)
        if not img.IsOk():
            return
        icon = wx.Icon()
        icon.CopyFromBitmap(wx.Bitmap(img))
        if icon.IsOk():
            app.SetAppName("UI Analyzer")
            # On Windows, SetIcon on the App propagates to all top-level
            # frames + the taskbar. On macOS, the app icon is bundled in
            # the .app Info.plist, so this only affects runtime
            # wx.Frame icons in dev runs.
            app.SetIcon(icon)
    except Exception:
        # Never let a bad icon block app startup.
        pass


class UIAnalyzerApp(wx.App):
    def OnInit(self) -> bool:
        _set_app_icon(self)
        frame = MainFrame()
        # Also set the icon on the frame so Windows shows it in the
        # window's title bar and Alt-Tab switcher even before the
        # app's icon propagates through.
        if _ICON_PATH.is_file():
            try:
                img = wx.Image(str(_ICON_PATH), type=wx.BITMAP_TYPE_PNG)
                if img.IsOk():
                    frame.SetIcon(wx.Icon(wx.Bitmap(img)))
            except Exception:
                pass
        frame.Show()
        self.SetTopWindow(frame)
        return True


def main() -> None:
    app = UIAnalyzerApp(redirect=False)
    app.MainLoop()


if __name__ == "__main__":
    main()
