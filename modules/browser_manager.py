from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class BrowserLaunchError(RuntimeError):
    pass


DEFAULT_BAIDU_START_URL = "https://cas.baidu.com/?tpl=www2&fromu=https%3A%2F%2Fcc.baidu.com%2Freport"


CONNECT_EXISTING_HELP = (
    "请先启动 Google Chrome 远程调试端口。\n"
    "项目会使用 browser_profile/chrome_debug 作为调试专用目录，通常不需要关闭日常 Chrome。\n"
    "如果 9222 已被其他 Chrome 调试实例占用，请关闭占用该端口的调试 Chrome，或运行项目里的 start_chrome_debug.bat。\n"
    "手动启动命令：\n"
    '"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
    "--remote-debugging-port=9222 --user-data-dir=browser_profile/chrome_debug --start-minimized "
    f'{DEFAULT_BAIDU_START_URL}'
)


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def get_browser_settings(config: dict[str, Any]) -> dict[str, Any]:
    browser = config.get("browser") if isinstance(config.get("browser"), dict) else {}
    managed = browser.get("managed") if isinstance(browser.get("managed"), dict) else {}

    legacy_port = config.get("remote_debugging_port", 9222)
    cdp_endpoint = browser.get("cdp_endpoint")
    if not cdp_endpoint:
        cdp_endpoint = f"http://127.0.0.1:{int(legacy_port)}"

    mode = browser.get("mode", config.get("browser_launch_mode", "connect_existing"))
    if mode == "cdp":
        mode = "connect_existing"

    profile_dir = managed.get("profile_dir", config.get("browser_profile_dir", "browser_profile/chrome"))
    channel = managed.get("channel", config.get("browser_channel", "chrome"))
    executable_path = managed.get("executable_path", config.get("chrome_executable_path", ""))

    auto_start = browser.get("auto_start_debug_chrome", True)
    remote_debugging_host = browser.get("remote_debugging_host", "127.0.0.1")
    remote_debugging_port = int(browser.get("remote_debugging_port", legacy_port))
    startup_url = browser.get(
        "startup_url",
        config.get("baidu", {}).get("start_url", DEFAULT_BAIDU_START_URL)
        if isinstance(config.get("baidu"), dict)
        else DEFAULT_BAIDU_START_URL,
    )
    allow_kill = bool(browser.get("allow_kill_existing_chrome", False))

    return {
        "mode": mode,
        "cdp_endpoint": cdp_endpoint,
        "prefer_existing_chrome": bool(browser.get("prefer_existing_chrome", True)),
        "debug_profile_dir": browser.get("debug_profile_dir", "browser_profile/chrome_debug"),
        "browser_preference": config.get("browser_preference", "chrome"),
        "browser_channel": channel,
        "chrome_executable_path": executable_path,
        "browser_profile_dir": profile_dir,
        "browser_launch_mode": mode,
        "remote_debugging_port": int(str(cdp_endpoint).rstrip("/").split(":")[-1]),
        "remote_debugging_host": remote_debugging_host,
        "startup_url": startup_url,
        "allow_edge_fallback": bool(browser.get("allow_edge_fallback", config.get("allow_edge_fallback", False))),
        "headless": bool(managed.get("headless", False)),
        "max_tabs": int(browser.get("max_tabs", config.get("browser_max_tabs", 3))),
        "auto_start_debug_chrome": auto_start,
        "allow_kill_existing_chrome": allow_kill,
        "silent_automation": bool(browser.get("silent_automation", True)),
        "window_state": str(browser.get("window_state", "minimized") or "normal"),
        "show_on_manual_intervention": bool(browser.get("show_on_manual_intervention", True)),
        "disable_password_manager": bool(browser.get("disable_password_manager", True)),
    }


def _ensure_chrome_only(settings: dict[str, Any]) -> None:
    if settings["browser_channel"] != "chrome":
        raise BrowserLaunchError(f"浏览器 channel 必须为 chrome，当前为：{settings['browser_channel']}")
    if settings["allow_edge_fallback"]:
        raise BrowserLaunchError("当前阶段禁止自动降级到 Edge；请将 allow_edge_fallback 设为 false。")


def _all_pages(browser) -> list:
    pages = []
    for context in browser.contexts:
        pages.extend(context.pages)
    return pages


def _is_baidu_backend_url(url: str) -> bool:
    normalized = (url or "").lower()
    return any(domain in normalized for domain in ["cc.baidu.com", "yingxiao.baidu.com", "qingge.baidu.com", "cas.baidu.com"])


def _is_legacy_baidu_login_entry(url: str) -> bool:
    normalized = (url or "").lower()
    return "yingxiao.baidu.com" in normalized or "qingge.baidu.com" in normalized


def _should_repoint_legacy_baidu_page(url: str, start_url: str) -> bool:
    return _is_legacy_baidu_login_entry(url) and "cas.baidu.com" in (start_url or "").lower()


def set_browser_window_state(page, state: str) -> bool:
    """通过 CDP 设置 Chrome 窗口状态；失败不影响自动化流程。"""
    if state not in {"normal", "minimized", "maximized", "fullscreen"}:
        return False
    try:
        session = page.context.new_cdp_session(page)
        window = session.send("Browser.getWindowForTarget")
        session.send("Browser.setWindowBounds", {
            "windowId": window["windowId"],
            "bounds": {"windowState": state},
        })
        return True
    except Exception:
        return False


def prepare_automation_page(page, config: dict[str, Any] | None = None) -> None:
    settings = get_browser_settings(config or {})
    if settings["silent_automation"]:
        return
    try:
        page.bring_to_front()
    except Exception:
        pass


def show_browser_page_for_manual_intervention(page, config: dict[str, Any] | None = None) -> bool:
    settings = get_browser_settings(config or {})
    if not settings["show_on_manual_intervention"]:
        return False
    set_browser_window_state(page, "normal")
    try:
        page.bring_to_front()
        return True
    except Exception:
        return False


def _maybe_focus_page(page, *, silent: bool) -> None:
    if silent:
        return
    try:
        page.bring_to_front()
    except Exception:
        pass


def _open_start_url(page, start_url: str, *, silent: bool = True):
    if _should_repoint_legacy_baidu_page(getattr(page, "url", ""), start_url):
        page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
    _maybe_focus_page(page, silent=silent)
    return page


def find_baidu_page(context, start_url: str, *, silent: bool = True):
    legacy_page = None
    for page in context.pages:
        if not _is_baidu_backend_url(page.url):
            continue
        if not _is_legacy_baidu_login_entry(page.url):
            _maybe_focus_page(page, silent=silent)
            return page
        legacy_page = legacy_page or page
    if legacy_page:
        return _open_start_url(legacy_page, start_url, silent=silent)
    page = context.new_page()
    page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
    _maybe_focus_page(page, silent=silent)
    return page


def _select_context_and_page(browser, start_url: str, *, silent: bool = True):
    contexts = list(browser.contexts)
    if not contexts:
        contexts = [browser.new_context()]

    legacy_candidate = None
    for context in contexts:
        for page in context.pages:
            if not _is_baidu_backend_url(page.url):
                continue
            if not _is_legacy_baidu_login_entry(page.url):
                _maybe_focus_page(page, silent=silent)
                return context, page
            legacy_candidate = legacy_candidate or (context, page)

    if legacy_candidate:
        context, page = legacy_candidate
        return context, _open_start_url(page, start_url, silent=silent)

    context = contexts[0]
    page = context.new_page()
    page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
    _maybe_focus_page(page, silent=silent)
    return context, page


def cleanup_extra_tabs(context, keep_page, max_tabs: int = 3, *, silent: bool = True) -> list[str]:
    try:
        pages = list(context.pages)
    except Exception:
        return []
    max_tabs = max(1, int(max_tabs or 3))
    if len(pages) <= max_tabs:
        return []

    keep_set = {keep_page}
    keep_slots_left = max_tabs - 1
    for page in reversed(pages):
        if keep_slots_left <= 0:
            break
        if page in keep_set or not _is_baidu_backend_url(getattr(page, "url", "")):
            continue
        keep_set.add(page)
        keep_slots_left -= 1

    for page in reversed(pages):
        if keep_slots_left <= 0:
            break
        if page in keep_set:
            continue
        keep_set.add(page)
        keep_slots_left -= 1

    closed_urls: list[str] = []
    for page in pages:
        if page in keep_set:
            continue
        try:
            closed_urls.append(getattr(page, "url", ""))
            page.close()
        except Exception:
            continue
    _maybe_focus_page(keep_page, silent=silent)
    return closed_urls


def connect_existing_chrome(playwright, config: dict[str, Any]):
    settings = get_browser_settings(config)
    _ensure_chrome_only(settings)
    endpoint = settings["cdp_endpoint"]
    start_url = config.get("baidu", {}).get("start_url", settings["startup_url"])

    try:
        browser = playwright.chromium.connect_over_cdp(endpoint)
    except Exception as exc:
        raise BrowserLaunchError(f"连接已有 Chrome 失败：{endpoint}\n{CONNECT_EXISTING_HELP}\n原始错误：{exc}") from exc

    context, page = _select_context_and_page(browser, start_url, silent=settings["silent_automation"])
    prepare_automation_page(page, config)
    cleanup_extra_tabs(context, page, settings["max_tabs"], silent=settings["silent_automation"])
    return context, page


def launch_managed_chrome_context(playwright, config: dict[str, Any], root: Path):
    settings = get_browser_settings(config)
    _ensure_chrome_only(settings)
    profile_dir = _resolve_path(root, settings["browser_profile_dir"])
    profile_dir.mkdir(parents=True, exist_ok=True)

    launch_options: dict[str, Any] = {
        "user_data_dir": str(profile_dir),
        "headless": settings["headless"],
        "viewport": {"width": 1440, "height": 900},
    }
    args: list[str] = []
    if settings["silent_automation"] and settings["window_state"] == "minimized":
        args.append("--start-minimized")
    if settings["disable_password_manager"]:
        args.extend([
            "--disable-save-password-bubble",
            "--disable-features=PasswordManagerOnboarding,PasswordLeakDetection",
        ])
        from modules.chrome_debug import write_chrome_preferences

        write_chrome_preferences(profile_dir, disable_password_manager=True)
    if args:
        launch_options["args"] = args
    executable_path = settings["chrome_executable_path"]
    if executable_path:
        if not Path(executable_path).exists():
            raise BrowserLaunchError(f"配置的 Chrome 路径不存在：{executable_path}")
        launch_options["executable_path"] = executable_path
    else:
        launch_options["channel"] = "chrome"

    try:
        context = playwright.chromium.launch_persistent_context(**launch_options)
    except Exception as exc:
        raise BrowserLaunchError(
            "项目专用 Google Chrome 启动失败。本程序不会自动改用 Edge；"
            f"请确认本机已安装 Chrome 或配置 Chrome 路径。原始错误：{exc}"
        ) from exc
    page = context.pages[0] if context.pages else context.new_page()
    prepare_automation_page(page, config)
    return context, page


def launch_chrome_context(playwright, config: dict[str, Any], root: Path):
    settings = get_browser_settings(config)
    if settings["mode"] == "connect_existing":
        from modules.chrome_debug import ensure_chrome_debug_ready

        host = settings.get("remote_debugging_host", "127.0.0.1")
        port = settings.get("remote_debugging_port", 9222)
        auto_start = settings.get("auto_start_debug_chrome", True)
        wait_seconds = int(config.get("browser", {}).get("debug_startup_wait_seconds", 15)
                           if isinstance(config.get("browser"), dict) else 15)
        ready = ensure_chrome_debug_ready(root, config, host=host, port=port,
                                          wait_seconds=wait_seconds, auto_start=auto_start)
        if not ready.get("ready"):
            from modules.chrome_debug import DEFAULT_PORT as chrome_default_port

            port_used = port if port != chrome_default_port else None
            extra = []
            if not ready.get("port_already_open"):
                extra.append("检测到 Chrome 9222 调试端口未就绪，且自动启动也未成功。")
            if ready.get("error"):
                extra.append(ready["error"])
            if port_used and port_used != chrome_default_port:
                extra.append("当前项目使用了非默认端口，请检查 browser.remote_debugging_port 配置。")
            raise BrowserLaunchError("\n".join(extra) if extra else f"Chrome 调试端口未就绪：{ready['debug_endpoint']}")
        return connect_existing_chrome(playwright, config)
    if settings["mode"] == "launch_managed":
        return launch_managed_chrome_context(playwright, config, root)
    raise BrowserLaunchError(f"未知浏览器模式：{settings['mode']}，只支持 connect_existing / launch_managed。")


def _write_json(root: Path, relative_path: str, report: dict[str, Any]) -> Path:
    out = root / relative_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def write_browser_test_report(root: Path, report: dict[str, Any]) -> Path:
    return _write_json(root, "reports/browser_test_report.json", report)


def write_browser_connect_report(root: Path, report: dict[str, Any]) -> Path:
    return _write_json(root, "reports/browser_connect_report.json", report)


def test_browser_connect(config: dict[str, Any], root: Path, logger) -> dict[str, Any]:
    settings = get_browser_settings(config)
    report: dict[str, Any] = {
        "mode": "test-browser-connect",
        "configured_browser_mode": settings["mode"],
        "browser_type": "chromium",
        "browser_version": None,
        "cdp_endpoint": settings["cdp_endpoint"],
        "allow_edge_fallback": settings["allow_edge_fallback"],
        "managed_profile_dir": str(_resolve_path(root, settings["browser_profile_dir"])),
        "debug_profile_dir": str(_resolve_path(root, settings["debug_profile_dir"])),
        "connected": False,
        "baidu_page_found": False,
        "project_managed_chrome_started": False,
        "edge_started": False,
        "page_urls": [],
        "closed_extra_tab_urls": [],
        "errors": [],
    }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        report["errors"].append(f"Playwright 未安装：{exc}")
        write_browser_connect_report(root, report)
        return report

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.connect_over_cdp(settings["cdp_endpoint"])
        except Exception as exc:
            report["errors"].append(f"连接已有 Chrome 失败：{settings['cdp_endpoint']}")
            report["errors"].append(CONNECT_EXISTING_HELP)
            report["errors"].append(f"原始错误：{exc}")
            write_browser_connect_report(root, report)
            logger.error("连接已有 Chrome 失败：%s", exc)
            return report

        report["connected"] = True
        report["browser_version"] = browser.version
        context, page = _select_context_and_page(
            browser,
            config.get("baidu", {}).get("start_url", settings["startup_url"]),
            silent=settings["silent_automation"],
        )
        prepare_automation_page(page, config)
        report["closed_extra_tab_urls"] = cleanup_extra_tabs(context, page, settings["max_tabs"], silent=settings["silent_automation"])
        pages = _all_pages(browser)
        report["page_urls"] = [page.url for page in pages]
        report["baidu_page_found"] = any(_is_baidu_backend_url(url) for url in report["page_urls"])
        logger.info("已连接已有 Chrome，页面数量：%s", len(report["page_urls"]))
        write_browser_connect_report(root, report)

    return report


def test_browser_launch(config: dict[str, Any], root: Path, logger, hold_seconds: int = 20) -> dict[str, Any]:
    settings = get_browser_settings(config)
    report: dict[str, Any] = {
        "mode": "test-browser",
        "configured_browser_mode": settings["mode"],
        "browser_type": "chromium",
        "browser_channel": settings["browser_channel"],
        "chrome_executable_path": settings["chrome_executable_path"],
        "browser_profile_dir": str(_resolve_path(root, settings["browser_profile_dir"])),
        "headless": settings["headless"],
        "allow_edge_fallback": settings["allow_edge_fallback"],
        "opened_url": None,
        "chrome_started": False,
        "edge_started": False,
        "errors": [],
    }
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        report["errors"].append(f"Playwright 未安装：{exc}")
        write_browser_test_report(root, report)
        return report

    start_url = config.get("baidu", {}).get("start_url", settings["startup_url"])
    with sync_playwright() as playwright:
        try:
            context, page = launch_chrome_context(playwright, config, root)
        except BrowserLaunchError as exc:
            report["errors"].append(str(exc))
            write_browser_test_report(root, report)
            logger.error("Chrome 浏览器测试失败：%s", exc)
            return report

        report["chrome_started"] = settings["mode"] == "launch_managed"
        try:
            if page.url != start_url:
                page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
            report["opened_url"] = page.url
            logger.info("Chrome 浏览器测试页面：%s", page.url)
            page.wait_for_timeout(max(1, hold_seconds) * 1000)
        finally:
            if settings["mode"] == "launch_managed":
                context.close()

    write_browser_test_report(root, report)
    return report
