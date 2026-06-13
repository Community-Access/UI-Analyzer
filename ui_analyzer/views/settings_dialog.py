"""Settings dialog for AI provider and model configuration."""

from __future__ import annotations
import wx
from typing import Optional

from ui_analyzer.services.config_manager import ConfigManager
from ui_analyzer.services.ollama_client import OllamaClient

class SettingsDialog(wx.Dialog):
    """Dialog for managing AI provider settings and API keys."""

    def __init__(self, parent: wx.Frame, config: ConfigManager) -> None:
        super().__init__(
            parent,
            title="Settings",
            size=(480, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._config = config
        self._build_ui()
        self._update_model_list()
        self.CentreOnParent()

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Notebook for tabbed settings
        self._notebook = wx.Notebook(panel)

        # Tab 1: General
        self._tab_general = self._build_general_tab()
        self._notebook.AddPage(self._tab_general, "General")

        # Tab 2: Ollama
        self._tab_ollama = self._build_ollama_tab()
        self._notebook.AddPage(self._tab_ollama, "Ollama")

        # Tab 3: Cloud Providers
        self._tab_cloud = self._build_cloud_tab()
        self._notebook.AddPage(self._tab_cloud, "Cloud Providers")

        sizer.Add(self._notebook, 1, wx.EXPAND | wx.ALL, 12)

        # Standard Dialog Buttons (OK/Cancel)
        try:
            btn_sizer = wx.Sizer.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        except AttributeError:
            # Fallback for versions where this method is not available on the Sizer class
            btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
            btn_sizer.AddStretchSpacer()
            ok_btn = wx.Button(panel, wx.ID_OK, "OK")
            cancel_btn = wx.Button(panel, wx.ID_CANCEL, "Cancel")
            btn_sizer.Add(ok_btn, 0, wx.RIGHT, 12)
            btn_sizer.Add(cancel_btn, 0, wx.BOTTOM | wx.RIGHT, 12)

        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.BOTTOM | wx.LEFT | wx.RIGHT, 12)

        panel.SetSizer(sizer)

    def _build_general_tab(self) -> wx.Panel:
        panel = wx.Panel(self._notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        header = wx.StaticText(panel, label="AI Provider")
        header.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        sizer.Add(header, 0, wx.TOP, 12)

        providers = ["ollama", "anthropic", "openai"]
        labels = {"ollama": "Ollama (Local)", "anthropic": "Anthropic (Cloud)", "openai": "OpenAI (Cloud)"}

        self._provider_choice = wx.Choice(
            panel,
            choices=[labels[p] for p in providers]
        )
        self._provider_choice.SetName("AI Provider")
        self._provider_choice.SetToolTip(
            "Choose whether to use a local Ollama model or a cloud API provider"
        )

        # Set current value
        current_provider = self._config.get("provider", "ollama")
        try:
            self._provider_choice.SetSelection(providers.index(current_provider))
        except ValueError:
            self._provider_choice.SetSelection(0)

        self._provider_choice.Bind(wx.EVT_CHOICE, self._on_provider_changed)
        sizer.Add(self._provider_choice, 0, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(sizer)
        return panel

    def _build_ollama_tab(self) -> wx.Panel:
        panel = wx.Panel(self._notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # URL Section
        url_row = wx.BoxSizer(wx.HORIZONTAL)
        url_row.Add(wx.StaticText(panel, label="Base URL:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self._url_field = wx.TextCtrl(panel)
        self._url_field.SetValue(self._config.get("ollama_url", "http://localhost:11434"))
        self._url_field.SetName("Ollama Base URL")
        url_row.Add(self._url_field, 1, wx.EXPAND)
        sizer.Add(url_row, 0, wx.EXPAND | wx.ALL, 12)

        # Test Connection
        self._test_btn = wx.Button(panel, label="Test Connection")
        self._test_btn.SetName("Test Ollama Connection")
        self._test_btn.SetToolTip("Check that Ollama is reachable at the URL above")
        self._test_btn.Bind(wx.EVT_BUTTON, self._on_test_ollama)
        sizer.Add(self._test_btn, 0, wx.LEFT | wx.BOTTOM, 12)

        # Models Section
        model_label = wx.StaticText(panel, label="Available Models:")
        sizer.Add(model_label, 0, wx.TOP | wx.LEFT, 12)

        model_row = wx.BoxSizer(wx.HORIZONTAL)
        self._model_choice = wx.Choice(panel)
        self._model_choice.SetName("Available Models")
        model_row.Add(self._model_choice, 1, wx.EXPAND | wx.RIGHT, 8)

        refresh_btn = wx.Button(panel, label="Refresh")
        refresh_btn.SetName("Refresh Ollama Models")
        refresh_btn.Bind(wx.EVT_BUTTON, self._on_refresh_models)
        model_row.Add(refresh_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer.Add(model_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self._model_choice.Bind(wx.EVT_CHOICE, self._on_model_changed)

        panel.SetSizer(sizer)
        return panel

    def _build_cloud_tab(self) -> wx.Panel:
        panel = wx.Panel(self._notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Anthropic
        sizer.Add(wx.StaticText(panel, label="Anthropic API Key"), 0, wx.TOP | wx.LEFT, 12)
        self._anthropic_key = wx.TextCtrl(panel, style=wx.TE_PASSWORD)
        self._anthropic_key.SetValue(self._config.get_api_key("anthropic") or "")
        self._anthropic_key.SetName("Anthropic API Key")
        sizer.Add(self._anthropic_key, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        anth_btn = wx.Button(panel, label="Save Anthropic Key")
        anth_btn.SetName("Save Anthropic API key")
        anth_btn.SetToolTip("Securely store your Anthropic API key in the system keychain")
        anth_btn.Bind(wx.EVT_BUTTON, lambda _e: self._save_key("anthropic", self._anthropic_key.GetValue()))
        sizer.Add(anth_btn, 0, wx.LEFT | wx.BOTTOM, 12)

        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 12)

        # OpenAI
        sizer.Add(wx.StaticText(panel, label="OpenAI API Key"), 0, wx.TOP | wx.LEFT, 12)
        self._openai_key = wx.TextCtrl(panel, style=wx.TE_PASSWORD)
        self._openai_key.SetValue(self._config.get_api_key("openai") or "")
        self._openai_key.SetName("OpenAI API Key")
        sizer.Add(self._openai_key, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        open_btn = wx.Button(panel, label="Save OpenAI Key")
        open_btn.SetName("Save OpenAI API key")
        open_btn.SetToolTip("Securely store your OpenAI API key in the system keychain")
        open_btn.Bind(wx.EVT_BUTTON, lambda _e: self._save_key("openai", self._openai_key.GetValue()))
        sizer.Add(open_btn, 0, wx.LEFT | wx.BOTTOM, 12)

        panel.SetSizer(sizer)
        return panel

    def _on_provider_changed(self, _e) -> None:
        idx = self._provider_choice.GetSelection()
        providers = ["ollama", "anthropic", "openai"]
        selected = providers[idx]
        self._config.set("provider", selected)
        # Note: We don't restart the app here; MainFrame will handle it on dialog close or via event

    def _on_model_changed(self, _e) -> None:
        model = self._model_choice.GetStringSelection()
        if model:
            self._config.set("model", model)

    def _on_refresh_models(self, _e) -> None:
        self._update_model_list()
        wx.MessageBox("The available models list has been updated.",
                      "Refresh Complete", wx.OK | wx.ICON_INFORMATION, self)

    def _update_model_list(self) -> None:
        url = self._url_field.GetValue().strip()
        client = OllamaClient(base_url=url)
        models = client.list_models()

        if not models:
            self._model_choice.Clear()
            return

        model_names = [m["name"] for m in models]
        self._model_choice.SetItems(model_names)

        # Set current selected model from config
        current_model = self._config.get("model", "")
        if current_model in model_names:
            self._model_choice.SetStringSelection(current_model)

    def _save_key(self, provider: str, key: str) -> None:
        try:
            self._config.set_api_key(provider, key)
            wx.MessageBox(f"Successfully saved {provider} API key.", "Saved", wx.OK | wx.ICON_INFORMATION, self)
        except Exception as e:
            wx.MessageBox(str(e), "Error", wx.OK | wx.ICON_ERROR, self)

    def _on_test_ollama(self, _e) -> None:
        url = self._url_field.GetValue().strip()
        if not url:
            wx.MessageBox("Please enter a URL.", "Missing URL", wx.OK | wx.ICON_WARNING, self)
            return

        client = OllamaClient(base_url=url)
        if client.is_available():
            self._update_model_list()
            wx.MessageBox("Connection successful! The available models list has been updated.",
                          "Success", wx.OK | wx.ICON_INFORMATION, self)
        else:
            wx.MessageBox("Could not connect to Ollama. Please check the URL and ensure Ollama is running.",
                          "Connection Failed", wx.OK | wx.ICON_ERROR, self)

        # Update config if URL changed
        self._config.set("ollama_url", url)
