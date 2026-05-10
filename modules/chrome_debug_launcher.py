from __future__ import annotations

import socket
import subprocess
import sys
import time
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHROME_EXE = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
START_URL = "https://yingxiao.baidu.com/"
DEBUG_PORT = 9222


def _load_debug_user_data_dir() -> Path:
    config_path = ROOT / "config.json"
    if not config_path.exists():
        return ROOT / "browser_profile" / "chrome_debug"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ROOT / "browser_profile" / "chrome_debug"
    value = config.get("browser", {}).get("debug_profile_dir", "browser_profile/chrome_debug")
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _chrome_is_running() -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
        capture_output=True,
        text=True,
        encoding="mbcs",
        errors="ignore",
        check=False,
    )
    return "chrome.exe" in result.stdout.lower()


def _kill_chrome() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _run_connect_test() -> int:
    return subprocess.call([sys.executable, "main.py", "--mode", "test-browser-connect"], cwd=ROOT)


def _wait_for_debug_port(timeout_seconds: int = 20) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _is_port_open(DEBUG_PORT):
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    if not CHROME_EXE.exists():
        print(f"找不到 Google Chrome：{CHROME_EXE}")
        print("请确认 Chrome 安装路径，或在 config.json 里修改 browser.managed.executable_path。")
        return 1

    if _is_port_open(DEBUG_PORT):
        print("9222 调试端口已经开启，开始测试连接。", flush=True)
        return _run_connect_test()

    if _chrome_is_running():
        print("当前已经有 Chrome 在运行。", flush=True)
        print("要让 --remote-debugging-port=9222 生效，必须先关闭所有 Chrome 进程再重新启动。", flush=True)
        try:
            answer = input("是否关闭所有 Chrome 并用调试端口重新打开？输入 Y 确认：").strip().lower()
        except EOFError:
            print("当前终端无法读取输入，已取消。请双击脚本或在 CMD 中手动运行后输入 Y。", flush=True)
            return 1
        if answer != "y":
            print("已取消。请手动关闭所有 Chrome 后重新运行 start_chrome_debug.bat。")
            return 1
        _kill_chrome()
        time.sleep(2)

    debug_user_data_dir = _load_debug_user_data_dir()
    debug_user_data_dir.mkdir(parents=True, exist_ok=True)
    print("正在启动可调试 Google Chrome，并开启 9222 调试端口...", flush=True)
    print(f"调试专用用户目录：{debug_user_data_dir}", flush=True)
    subprocess.Popen(
        [
            str(CHROME_EXE),
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={debug_user_data_dir}",
            '--profile-directory=Default',
            "--no-first-run",
            "--no-default-browser-check",
            START_URL,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not _wait_for_debug_port():
        print("Chrome 已尝试启动，但 9222 调试端口仍未就绪。", flush=True)
        print("请确认没有安全软件拦截，或手动关闭所有 Chrome 后重新运行本脚本。", flush=True)
    return _run_connect_test()


if __name__ == "__main__":
    raise SystemExit(main())
