from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from gui.main_window import create_window
from gui.single_instance import SingleInstanceGuard


GUI_SCALE_FACTOR = "1.0"


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
    os.environ["QT_SCALE_FACTOR"] = GUI_SCALE_FACTOR
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("百度数据自动化控制台")
    instance_guard = SingleInstanceGuard()
    if not instance_guard.acquire():
        instance_guard.notify_existing()
        return 0
    icon = root / "assets" / "app_icon.png"
    if not icon.exists():
        icon = root / "assets" / "app_icon.ico"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = create_window(root)
    instance_guard.activate_requested.connect(window.show_console)
    app.aboutToQuit.connect(instance_guard.close)
    window.raise_()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
