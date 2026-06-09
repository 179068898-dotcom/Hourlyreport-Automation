from __future__ import annotations

import json
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
DEFAULT_PROFILE_DIR = "browser_profile/chrome_debug"

CHROME_CANDIDATES = [
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
]


PASSWORD_MANAGER_DISABLED_PREFS = {
    "credentials_enable_service": False,
    "profile": {
        "password_manager_enabled": False,
    },
}


SW_SHOWMINNOACTIVE = 7


def build_chrome_startupinfo(*, start_minimized: bool = True):
    if not start_minimized or not hasattr(subprocess, "STARTUPINFO"):
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = SW_SHOWMINNOACTIVE
    return startupinfo


def _deep_update(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def write_chrome_preferences(profile_dir: Path, *, disable_password_manager: bool = True) -> Path | None:
    """写入 Chrome profile 偏好，避免自动化登录后弹出保存密码气泡。"""
    if not disable_password_manager:
        return None
    preferences = profile_dir / "Default" / "Preferences"
    preferences.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if preferences.exists():
        try:
            data = json.loads(preferences.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    _deep_update(data, PASSWORD_MANAGER_DISABLED_PREFS)
    preferences.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return preferences


def build_chrome_debug_args(
    chrome_exe: Path,
    *,
    host: str,
    port: int,
    profile_dir: Path,
    startup_url: str | None = None,
    start_minimized: bool = True,
    disable_password_manager: bool = True,
) -> list[str]:
    args = [
        str(chrome_exe),
        f"--remote-debugging-port={port}",
        f"--remote-debugging-address={host}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if start_minimized:
        args.append("--start-minimized")
    if disable_password_manager:
        args.extend([
            "--disable-save-password-bubble",
            "--disable-features=PasswordManagerOnboarding,PasswordLeakDetection",
        ])
    if startup_url:
        args.append(startup_url)
    return args


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
        profile_dir = browser_cfg.get("debug_profile_dir", browser_cfg.get("profile_dir", profile_dir))
    resolved_profile = root / profile_dir if not Path(profile_dir).is_absolute() else Path(profile_dir)
    resolved_profile.mkdir(parents=True, exist_ok=True)
    result["profile_dir"] = str(resolved_profile)
    browser_cfg = config.get("browser") if isinstance(config, dict) and isinstance(config.get("browser"), dict) else {}
    silent_automation = bool(browser_cfg.get("silent_automation", True))
    window_state = str(browser_cfg.get("window_state", "minimized") or "normal")
    disable_password_manager = bool(browser_cfg.get("disable_password_manager", True))
    write_chrome_preferences(resolved_profile, disable_password_manager=disable_password_manager)

    try:
        start_minimized = silent_automation and window_state == "minimized"
        subprocess.Popen(
            build_chrome_debug_args(
                chrome_exe,
                host=host,
                port=port,
                profile_dir=resolved_profile,
                startup_url=None if silent_automation else startup_url,
                start_minimized=start_minimized,
                disable_password_manager=disable_password_manager,
            ),
            startupinfo=build_chrome_startupinfo(start_minimized=start_minimized),
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
    configured_profile = browser_cfg.get("debug_profile_dir", browser_cfg.get("profile_dir", DEFAULT_PROFILE_DIR))
    use_debug_profile = str(configured_profile).replace("\\", "/").endswith(DEFAULT_PROFILE_DIR)
    can_parallel_debug_chrome = bool(browser_cfg.get("silent_automation", True)) and use_debug_profile

    if not allow_kill and not can_parallel_debug_chrome:
        chrome_running = _chrome_process_exists()
        if chrome_running:
            if not _chrome_is_debug_port_listening(host=host, port=port):
                result["error"] = (
                    "检测到已有 Chrome 进程在运行，但未监听 9222 调试端口。\n"
                    "请先关闭所有 Chrome 进程，或运行 start_chrome_debug.bat 启动项目专用调试 Chrome。\n"
                    "（普通 Chrome 不监听调试端口，项目需要 9222 端口才能连接。）"
                )
                return result
            # Chrome 正在运行且端口被监听，但 HTTP 端点不可用（json/version 不通）。
            # 可能是端口被非 Chrome 进程占用。尝试关闭旧 Chrome 重新启动。
            result["error"] = (
                "Chrome 9222 端口被占用但无法连接。\n"
                "请关闭所有 Chrome 进程后重新运行，或运行 start_chrome_debug.bat。"
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


def _chrome_is_debug_port_listening(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    """检查是否已有 Chrome 进程监听目标调试端口。"""
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="ignore",
            check=False,
            timeout=10,
        )
        port_token = f":{port}"
        listening_lines = [
            line for line in proc.stdout.splitlines()
            if port_token in line and "LISTENING" in line.upper()
        ]
        return len(listening_lines) > 0
    except Exception:
        return False
