from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtGui import QFontDatabase


VISTA_YAHEI_BOLD_FILE_NAMES = (
    "microsoft_yahei_vista_bold.ttf",
    "微软vista雅黑Bold.ttf",
)
VISTA_YAHEI_FAMILY = "Microsoft YaHei"


def private_font_candidates(root: str | Path) -> list[Path]:
    root_path = Path(root).resolve()
    candidates = [
        root_path / "assets" / "fonts" / file_name
        for file_name in VISTA_YAHEI_BOLD_FILE_NAMES
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        user_fonts = Path(local_app_data) / "Microsoft" / "Windows" / "Fonts"
        candidates.extend(user_fonts / file_name for file_name in VISTA_YAHEI_BOLD_FILE_NAMES)
    return candidates


def load_private_ui_font(root: str | Path) -> Path | None:
    """Load the approved Vista YaHei face before any UI fonts are created."""
    for candidate in private_font_candidates(root):
        if not candidate.is_file():
            continue
        try:
            font_data = candidate.read_bytes()
        except OSError:
            continue
        # Qt on Windows can reject a valid font when any parent path contains
        # non-ASCII characters. Loading from memory also keeps packaged builds
        # independent from their extraction directory.
        font_id = QFontDatabase.addApplicationFontFromData(font_data)
        if font_id < 0:
            font_id = QFontDatabase.addApplicationFont(str(candidate))
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if VISTA_YAHEI_FAMILY in families or families:
            return candidate
    return None
