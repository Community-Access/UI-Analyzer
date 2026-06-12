# UI Analyzer

Cross-platform UI accessibility analyzer. Drop a folder of UI source files in, get a structured description of what the UI looks like to sighted people, ask follow-up questions, and build a project-wide summary for cross-screen questions.

Built for blind developers who need to understand their UI without seeing it. All analysis runs locally on your machine through [Ollama](https://ollama.com) — your code never leaves your computer.

## Features

- **Local AI** — works with any Ollama model; choose per-file-type recommendations or pick your own
- **Multi-framework** — SwiftUI, Storyboard / XIB, HTML / CSS, React / React Native, Vue, Svelte, Python (tkinter / PyQt / wxPython), JavaScript, TypeScript, Markdown design specs, and image screenshots
- **Three output modes** — Prose (5 sections), Markdown table, fully accessible HTML5 table
- **Follow-up questions** — persistent per-file conversation with rolling context
- **Project context** — summarize the whole project and ask cross-screen questions
- **Accessible to NVDA, JAWS, Narrator, VoiceOver** — every screen, every dialog, every control
- **Drag and drop** — drop a folder from File Explorer / Finder onto the sidebar

## Quick start

### 1. Install Ollama and pull a model

Download Ollama from [ollama.com/download](https://ollama.com/download), then:

```bash
ollama serve            # if not already running
ollama pull qwen2.5-coder:7b
```

### 2. Install Python dependencies

```bash
cd path/to/UI-Analyzer
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. (Optional) Install Tesseract for screenshot analysis

- **Windows:** download the installer from [github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki) and make sure `tesseract` is on your `PATH`.
- **macOS:** `brew install tesseract`

### 4. Run

```bash
python main.py
```

## Keyboard shortcuts

| Action | Shortcut |
| --- | --- |
| Open Folder | `Ctrl+O` |
| Analyze / Re-analyze | `Ctrl+R` |
| Build Project Context | `Ctrl+Shift+A` |
| Ask Project Question | `Ctrl+Shift+I` |
| Copy Output | `Ctrl+Shift+C` |
| Save Output | `Ctrl+S` |
| Choose AI Model | `Ctrl+M` |
| Quit | `Ctrl+Q` |

On macOS, `Ctrl` is `Cmd`. Standard Tab / arrow / Enter / Space / Esc work as expected. The follow-up question field is reached with `Tab` from the result view.

## Accessibility

UI Analyzer is built WCAG 2.2 AA accessible end to end. Highlights:

- Every interactive control has an accessible name (NVDA / JAWS / Narrator / VoiceOver announce it on focus)
- Every button is at least 44 × 44 pixels (WCAG 2.5.5)
- Every dialog is fully keyboard-operable; Escape closes dialogs
- Analysis output uses an `AccessibleWebView` with ARIA live regions for screen-reader heading navigation
- Project Q&A uses HTML fragment output with `<h2>Question</h2>` / `<h2>Answer</h2>` structure so the heading rotor jumps between Q&A pairs
- HTML table output starts with a `<details class="tldr" open>` block — a 3–5 sentence TL;DR you can read first
- Status bar updates are live-region announcements on every state change

## Documentation

- [docs/user-guide.html](docs/user-guide.html) — plain-language user guide
- [docs/developer-guide.html](docs/developer-guide.html) — architecture, APIs, threading model, accessibility patterns, gotchas

Both docs are accessible HTML pages and can be opened in any browser.

## Requirements

- Windows 10/11, macOS 14+, or Linux (untested)
- Python 3.10+
- Ollama (running locally, with at least one model pulled)
- Edge WebView2 Runtime (ships with Windows 11; install from [Microsoft](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) for Windows 10)
- Tesseract (only for screenshot analysis)

## License

To be determined.
