# Implementation Plan: Attach Screenshot & Validation Feature

This plan describes the implementation of the "Attach Screenshot" feature, allowing users to associate a screenshot with a UI source file and validate the AI's code analysis against the actual visual output.

## 1. Requirements Overview
- **Attachment**: Shift+F10 in sidebar $\rightarrow$ "Attach Screenshot" $\rightarrow$ File Dialog $\rightarrow$ Persist mapping.
- **Detachment**: Shift+F10 in sidebar $\rightarrow$ "Detach Screenshot".
- **Validation**: Shift+F10 in sidebar $\rightarrow$ "Validate Screenshot" $\rightarrow$ AI comparison $\rightarrow$ Results Dialog.
- **Results**: Dialog showing claims that Stand, should be Retracted, and new Additions.
- **Re-validation**: Ability to re-run validation if the screenshot or code changes.

## 2. Architectural Design

### 2.1 Model Extensions (`ui_analyzer/models/ui_file.py`)
- **`UIFile`**: Add `attached_image: Optional[Path] = None`.
- **`ValidationResult`**: New dataclass:
  - `stands: list[str]`
  - `retract: list[str]`
  - `additions: list[str]`
- **`UIAnalysis`**: Add `validation: Optional[ValidationResult] = None`.

### 2.2 Persistence: `AttachmentManager` (`ui_analyzer/services/attachment_manager.py`)
A new service to manage the mapping between `UIFile.id` and image paths.
- **Storage**: JSON file in the application config directory (e.g., `~/.ui_analyzer/attachments.json`).
- **API**:
  - `load_attachments() -> dict[str, str]`: Loads the mapping from disk.
  - `save_attachment(file_id: str, image_path: Path)`: Updates and persists the mapping.
  - `remove_attachment(file_id: str)`: Removes the mapping and persists.
  - `get_attachment(file_id: str) -> Optional[Path]`: Returns the path for a given file ID.

### 2.3 AI Validation Logic (`ui_analyzer/services/ui_analyzer.py`)
Add a `validate_screenshot` method to `UIAnalyzer`.
- **Input**: `UIFile`, `UIAnalysis`, `image_path`.
- **Process**:
  1. Extract image content (using existing `_extract_image_content` OCR logic).
  2. Construct a validation prompt:
     - Provide the original `UIAnalysis.content`.
     - Provide the extracted image content.
     - Instruct the model to compare the two and categorize findings into `stands`, `retract`, and `additions`.
  3. Parse the AI response (requested as JSON) into a `ValidationResult` object.
- **Multimodal Support**: If the `AIClient` supports images (e.g., Claude 3.5), send the image file directly instead of just OCR text.

### 2.4 UI Implementation

#### 2.4.1 `SidebarPanel` (`ui_analyzer/views/sidebar.py`)
- Implement a context menu for the `ListCtrl`.
- Bind `Shift+F10` to trigger the context menu.
- Menu items:
  - "Attach Screenshot" (enabled if no attachment exists).
  - "Detach Screenshot" (enabled if attachment exists).
  - "Validate Screenshot" (enabled if attachment exists AND analysis exists).

#### 2.4.2 `MainFrame` (`ui_analyzer/views/main_frame.py`)
- Initialize `AttachmentManager` and load attachments into `UIFile` objects on startup/folder load.
- Implement event handlers:
  - `_on_attach_screenshot()`: Open `wx.FileDialog` $\rightarrow$ `AttachmentManager.save_attachment` $\rightarrow$ update `UIFile` $\rightarrow$ refresh sidebar.
  - `_on_detach_screenshot()`: `AttachmentManager.remove_attachment` $\rightarrow$ update `UIFile` $\rightarrow$ refresh sidebar.
  - `_on_validate_screenshot()`: 
    - Call `UIAnalyzer.validate_screenshot` in a background thread.
    - On completion, update `UIAnalysis.validation`.
    - Show `ValidationDialog`.

#### 2.4.3 `ValidationDialog` (New view in `ui_analyzer/views/`)
A modal dialog to display the `ValidationResult`.
- Three sections (each with a header and list/text area):
  - **Confirmed (Stands)**: Green-themed, claims the AI got right.
  - **Contradicted (Retract)**: Red-themed, claims the AI got wrong.
  - **New Insights (Additions)**: Blue-themed, details missed by the initial analysis.
- "Close" button.

## 3. Implementation Steps

1. **Models**: Update `ui_file.py` with `attached_image`, `ValidationResult`, and `UIAnalysis` extension.
2. **Service**: Implement `AttachmentManager` for JSON persistence.
3. **Service**: Implement `UIAnalyzer.validate_screenshot` with the comparison prompt.
4. **View**: Implement `ValidationDialog` for displaying results.
5. **View**: Update `SidebarPanel` to add the context menu and `Shift+F10` binding.
6. **View**: Update `MainFrame` to orchestrate the flow and handle events.
7. **Integration**: Ensure attachments are loaded when a folder is scanned.

## 4. Verification Plan

- **Attachment Test**:
  - Select a file $\rightarrow$ Shift+F10 $\rightarrow$ "Attach Screenshot" $\rightarrow$ Select PNG $\rightarrow$ Verify "Attach" is now disabled and "Detach/Validate" are enabled.
  - Restart app $\rightarrow$ Verify attachment persists.
- **Detachment Test**:
  - Select file with attachment $\rightarrow$ Shift+F10 $\rightarrow$ "Detach Screenshot" $\rightarrow$ Verify attachment is gone and persistence is updated.
- **Validation Test**:
  - Analyze a file $\rightarrow$ Attach a screenshot $\rightarrow$ Shift+F10 $\rightarrow$ "Validate Screenshot" $\rightarrow$ Verify `ValidationDialog` appears with plausible results.
- **Re-validation Test**:
  - Replace the screenshot file with a different one $\rightarrow$ "Validate Screenshot" $\rightarrow$ Verify results change.

## 5. Critical Files for Implementation
- `ui_analyzer/models/ui_file.py`
- `ui_analyzer/services/attachment_manager.py` (New)
- `ui_analyzer/services/ui_analyzer.py`
- `ui_analyzer/views/sidebar.py`
- `ui_analyzer/views/main_frame.py`
- `ui_analyzer/views/validation_dialog.py` (New)
