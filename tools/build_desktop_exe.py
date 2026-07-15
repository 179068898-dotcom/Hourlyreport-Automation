from __future__ import annotations

import subprocess
import sys
from pathlib import Path


APP_NAME = "百度数据自动化控制台"


def build_desktop_exe(root: str | Path) -> int:
    root_path = Path(root)
    python = root_path / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        print("[失败] 缺少 .venv\\Scripts\\python.exe，请先运行 install_env.bat")
        return 1
    icon = root_path / "assets" / "app_icon.ico"
    command = [
        str(python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--clean",
        "--icon",
        str(icon),
        "--name",
        APP_NAME,
        str(root_path / "gui" / "app.py"),
    ]
    result = subprocess.run(command, cwd=root_path)
    if result.returncode != 0:
        return int(result.returncode)
    output = root_path / "dist" / f"{APP_NAME}.exe"
    if not output.exists() or output.stat().st_size == 0:
        print(f"[失败] PyInstaller 未生成预期文件：{output}")
        return 1
    print(f"[完成] 单文件 GUI：{output}")
    return 0


def main() -> int:
    return build_desktop_exe(Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    raise SystemExit(main())
