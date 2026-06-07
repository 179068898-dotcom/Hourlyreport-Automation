from __future__ import annotations

import subprocess
import sys
from pathlib import Path


APP_NAME = "百度日报小时报控制台"


def build_desktop_exe(root: str | Path) -> int:
    root_path = Path(root)
    python = root_path / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        print("[失败] 缺少 .venv\\Scripts\\python.exe，请先运行 install_env.bat")
        return 1
    command = [
        str(python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name",
        APP_NAME,
        str(root_path / "gui" / "app.py"),
    ]
    result = subprocess.run(command, cwd=root_path)
    return int(result.returncode)


def main() -> int:
    return build_desktop_exe(Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    raise SystemExit(main())
