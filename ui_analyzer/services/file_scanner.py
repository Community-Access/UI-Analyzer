"""Scan a folder for recognised UI source files."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from ui_analyzer.models.ui_file import UIFile, UIFileType
from ui_analyzer.services.attachment_store import looks_like_attachment, lookup_attachment

# Files/directories to always skip
_SKIP_DIRS  = {".git", ".svn", "node_modules", "__pycache__", ".venv", "venv",
               "env", ".tox", "dist", "build", ".build", "DerivedData"}
_SKIP_FILES = {"readme.md", "changelog.md", "license.md", "contributing.md",
               "code_of_conduct.md", "authors.md", "history.md"}

_TEXT_SIZE_LIMIT  = 500_000    # 500 KB
_IMAGE_SIZE_LIMIT = 10_000_000 # 10 MB


def scan_folder(
    folder: Path,
    on_progress: Optional[Callable[[int], None]] = None,
) -> list[UIFile]:
    """Walk *folder* and return all recognised UIFile objects, sorted by type then path."""
    files: list[UIFile] = []
    count = 0

    for path in _walk(folder):
        count += 1
        if on_progress and count % 20 == 0:
            on_progress(count)

        size = path.stat().st_size
        is_image = UIFileType.from_path(path) == UIFileType.IMAGE

        size_limit = _IMAGE_SIZE_LIMIT if is_image else _TEXT_SIZE_LIMIT
        if size > size_limit:
            continue

        if UIFileType.needs_content(path):
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            ft = UIFileType.from_path(path, content)
        else:
            ft = UIFileType.from_path(path)

        if ft is None:
            continue

        # Skip sibling attachment files — they belong to a source file, not the list
        if looks_like_attachment(path.name):
            continue

        rel = str(path.relative_to(folder))
        attached = lookup_attachment(rel)
        files.append(UIFile(
            path=path,
            relative_path=rel,
            file_type=ft,
            folder_path=folder,
            attached_image_path=attached,
        ))

    files.sort(key=lambda f: (f.file_type.value, f.relative_path))
    return files


def _walk(folder: Path):
    """Yield regular files, skipping hidden items and blacklisted directories."""
    try:
        entries = list(folder.iterdir())
    except PermissionError:
        return

    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            if entry.name in _SKIP_DIRS:
                continue
            yield from _walk(entry)
        elif entry.is_file():
            if entry.name.lower() in _SKIP_FILES:
                continue
            yield entry
