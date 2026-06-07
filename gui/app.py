from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from gui.main_window import create_window


def resolve_app_root() -> Path:
    candidates: list[Path] = []
    candidates.append(Path.cwd())
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
        candidates.append(Path(sys.executable).resolve().parent.parent)
    candidates.append(Path(__file__).resolve().parents[1])

    for base in candidates:
        for path in [base, *base.parents]:
            if (path / "main.py").exists() and (path / "configs").exists():
                return path
    return candidates[0]


def main() -> int:
    root = resolve_app_root()
    app = QApplication(sys.argv)
    app.setApplicationName("百度日报小时报控制台")
    window = create_window(root)
    window.raise_()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
