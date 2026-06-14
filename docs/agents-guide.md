# Agents Guide: UI-Analyzer

This guide provides the necessary technical context for AI agents (e.g., Hermes, Claude) to interact with the UI-Analyzer project. It describes the tool's capabilities, file structure, and the CLI interface, enabling an agent to "see" and audit user interfaces through the tool.

## 1. Tool Overview
UI-Analyzer is a specialized utility that describes UI source code (SwiftUI, React, HTML, etc.) or screenshots for blind developers. For an AI agent, this tool serves as a **visual proxy**. Instead of guessing how code renders, the agent can run UI-Analyzer to get a structured, expert description of the visual layout, colors, and accessibility.

### Primary Capabilities
- **Source Analysis**: Converts UI code into prose or tables describing the visual appearance.
- **Visual Validation**: Compares source code analysis against a real screenshot to identify discrepancies.
- **Accessibility Auditing**: Automatically computes WCAG contrast ratios and identifies missing labels or small touch targets.
- **Design Spec Review**: Analyzes design token files (Markdown) to ensure consistency.

## 2. The CLI Interface (The Agent's Primary Entry Point)
The CLI is the preferred way for agents to interact with the project. It is a standalone Python script located at the project root: `ui_analyzer.py`.

### Execution Command
```bash
python ui_analyzer.py <path_to_file_or_url> [options]
```

### Critical Options for Agents
| Option | Purpose | Recommended Use for Agents |
| :--- | :--- | :--- |
| `--output-mode prose` | Returns a 6-section Markdown report. | Use for general understanding and high-level audits. |
| `--output-mode table` | Returns a structured Markdown table of all elements. | Use for precise mapping of labels, colors, and positions. |
| `--output-mode html` | Generates a full accessible HTML5 document. | Use when generating reports for human review. |
| `--spec <file>` | Checks the UI against a visual standards spec. | Use to verify if a UI matches a project's design system. |
| `--backend <name>` | Selects the AI engine (`ollama`, `openai`, `claude`). | Use `auto` unless a specific model is required for vision. |
| `--output <file>` | Writes results to a file. | Use to avoid flooding the agent's context window. |

### Example Agent Workflow: "Audit Accessibility"
1. **Scan**: Agent identifies a UI file (e.g., `LoginView.swift`).
2. **Analyze**: Agent runs `python ui_analyzer.py LoginView.swift --output-mode prose`.
3. **Review**: Agent reads the "Accessibility" section of the output.
4. **Fix**: Agent applies the suggested code fixes provided in the output to the source file.

## 3. Project Architecture
To understand how the tool works or to extend it, agents should reference the following structure:

### Core Logic (`ui_analyzer/services/`)
- `ui_analyzer.py`: The brain. Contains all prompt templates and session management.
- `ollama_client.py`: Handles communication with the local AI server.
- `contrast_advisor.py`: The automated WCAG contrast engine.
- `localhost_crawler.py`: Logic for fetching local web pages for analysis.

### Data Models (`ui_analyzer/models/`)
- `ui_file.py`: Defines `UIFile` (metadata) and `UIFileType` (supported extensions).

### GUI Layer (`ui_analyzer/views/`)
- `main_frame.py`: The primary window and wiring.
- `detail_panel.py`: Handles the display of analysis results and follow-up questions.

## 4. File Type Support
Agents can target any of the following files for analysis:
- **iOS**: `.swift` (SwiftUI), `.storyboard`, `.xib`.
- **Web**: `.html`, `.htm`, `.css`, `.jsx`, `.tsx`, `.vue`, `.svelte`.
- **Desktop**: `.py` (wxPython, PyQt, tkinter), `.js`, `.ts`.
- **Design**: `.md` (if not a README/Changelog, it is treated as a Design Spec).
- **Images**: `.png`, `.jpg`, `.heic`, `.webp`, etc. (Processed via OCR).

## 5. Platform Compatibility
The project is cross-platform. Agents should provide instructions compatible with both:
- **Windows**: Use `python` and Windows-style paths.
- **macOS**: Use `python3` and POSIX paths.
- **Dependencies**: All are listed in `requirements.txt`. Tesseract OCR is an external binary requirement for image analysis.

## 6. Integration Tips for Agents
- **Context Management**: When analyzing multiple files, use the CLI's `--output` flag to save results to temporary files, then read only the sections needed.
- **Vision-Capable Models**: If the agent has access to a vision model, it should encourage the use of `llama3.2-vision` via Ollama for the `Validate` feature.
- **Verification Loop**: After applying a fix based on a UI-Analyzer report, the agent should re-run the tool to verify the "Accessibility" section now shows a "PASS".