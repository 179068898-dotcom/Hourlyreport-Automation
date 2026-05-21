from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from modules.browser_manager import DEFAULT_BAIDU_START_URL


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9222
DEFAULT_STARTUP_URL = DEFAULT_BAIDU_START_URL
DEFAULT_PROFILE_DIR = "browser_profile/chrome"

CHROME_CANDIDATES = [
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
]


def is_chrome_debug_port_alive(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 3.0) -> bool:
    try:
        url = f"http://{host}:{port}/json/version"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def find_chrome_executable(config: dict[str, Any] | None = None) -> Path | None:
    if config:
        managed = config.get("browser", {}).get("managed", {}) if isinstance(config.get("browser"), dict) else {}
        exe_path = managed.get("executable_path") or config.get("chrome_executable_path", "")
        if exe_path:
            path = Path(exe_path)
            if path.exists():
                return path

    for candidate in CHROME_CANDIDATES:
        if candidate.exists():
            return candidate

    return None


def start_debug_chrome(
    root: Path,
    config: dict[str, Any] | None = None,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    startup_url: str | None = None,
    profile_dir: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "started": False,
        "chrome_exe": None,
        "profile_dir": None,
        "startup_url": None,
        "debug_endpoint": f"http://{host}:{port}",
        "error": None,
    }

    chrome_exe = find_chrome_executable(config)
    if chrome_exe is None:
        result["error"] = (
            "未找到 Google Chrome。请确认 Chrome 已安装到以下路径之一：\n"
            + "\n".join(f"  - {path}" for path in CHROME_CANDIDATES)
            + "\n或通过 config.json 的 browser.managed.executable_path 指定 Chrome 路径。"
        )
        return result

    result["chrome_exe"] = str(chrome_exe)

    if startup_url is None:
        startup_url = DEFAULT_STARTUP_URL
    if config:
        startup_url = config.get("browser", {}).get("startup_url", startup_url) if isinstance(config.get("browser"), dict) else startup_url
    result["startup_url"] = startup_url

    if profile_dir is None:
        profile_dir = DEFAULT_PROFILE_DIR
    if config:
        browser_cfg = config.get("browser") if isinstance(config.get("browser"), dict) else {}
        profile_dir = browser_cfg.get("profile_dir", profile_dir)
    resolved_profile = root / profile_dir if not Path(profile_dir).is_absolute() else Path(profile_dir)
    resolved_profile.mkdir(parents=True, exist_ok=True)
    result["profile_dir"] = str(resolved_profile)

    try:
        subprocess.Popen(
            [
                str(chrome_exe),
                f"--remote-debugging-port={port}",
                f"--remote-debugging-address={host}",
                f"--user-data-dir={resolved_profile}",
                "--no-first-run",
                "--no-default-browser-check",
                startup_url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        result["error"] = f"Chrome 启动失败：{exc}"
        return result

    result["started"] = True
    return result


def ensure_chrome_debug_ready(
    root: Path,
    config: dict[str, Any] | None = None,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    wait_seconds: int = 10,
    auto_start: bool = True,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ready": False,
        "port_already_open": False,
        "started_new_chrome": False,
        "chrome_exe": None,
        "profile_dir": None,
        "startup_url": None,
        "debug_endpoint": f"http://{host}:{port}",
        "error": None,
    }

    if is_chrome_debug_port_alive(host=host, port=port):
        result["ready"] = True
        result["port_already_open"] = True
        return result

    if not auto_start:
        result["error"] = f"Chrome 调试端口未就绪：{result['debug_endpoint']}，且 auto_start 未开启。"
        return result

    browser_cfg = config.get("browser") if isinstance(config, dict) and config else {}
    allow_kill = browser_cfg.get("allow_kill_existing_chrome", False) if isinstance(browser_cfg, dict) else False

    if not allow_kill:
        chrome_running = _chrome_process_exists()
        if chrome_running:
            result["ready"] = False
            result["error"] = (
                "Chrome 调试端口未就绪，且检测到已有 Chrome 进程在运行。\n"
                f"请先手动启动 Chrome 调试端口：start_chrome_debug.bat\n"
                f"或关闭所有 Chrome 后重新运行。"
            )
            return result

    start_result = start_debug_chrome(root, config, host=host, port=port)
    result["chrome_exe"] = start_result.get("chrome_exe")
    result["profile_dir"] = start_result.get("profile_dir")
    result["startup_url"] = start_result.get("startup_url")

    if not start_result.get("started"):
        result["error"] = start_result.get("error") or "Chrome 启动失败，原因未知。"
        return result

    result["started_new_chrome"] = True

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if is_chrome_debug_port_alive(host=host, port=port):
            result["ready"] = True
            return result
        time.sleep(0.5)

    result["error"] = (
        f"Chrome 已启动，但 {wait_seconds} 秒后调试端口仍不可连接：{result['debug_endpoint']}。\n"
        "请确认没有安全软件拦截，或手动运行 start_chrome_debug.bat。"
    )
    return result


def _chrome_process_exists() -> bool:
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="ignore",
            check=False,
        )
        return "chrome.exe" in proc.stdout.lower()
    except Exception:
        return False
