from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from modules.baidu_browser import _write_debug_artifacts
from modules.baidu_detector import classify_baidu_page
from modules.browser_manager import BrowserLaunchError, get_browser_settings, launch_chrome_context
from modules.credential_manager import build_login_failure_message, load_project_credentials
from modules.text_normalizer import normalize_text

CC_REPORT_URL = "https://cc.baidu.com/report"
QINGGE_LOGIN_URL = "https://qingge.baidu.com/login"
CAS_LOGIN_URL = "https://cas.baidu.com/?tpl=www2&fromu=https%3A%2F%2Fcc.baidu.com%2Freport"


def is_search_promotion_overview(classification: dict[str, Any]) -> bool:
    if classification.get("login_status") == "not_logged_in":
        return False
    if "cc.baidu.com/report" not in str(classification.get("url", "")).lower():
        return False
    signals = classification.get("signals", {})
    return bool(
        signals.get("has_search_promotion")
        and (
            signals.get("has_data_overview")
            or (signals.get("has_data_report") and signals.get("has_table_fields"))
        )
    )


def should_open_cas_login(url: str) -> bool:
    normalized_url = (url or "").lower()
    if "cas.baidu.com" in normalized_url:
        return False
    return any(domain in normalized_url for domain in ["qingge.baidu.com", "yingxiao.baidu.com"])


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _extract_dates(text: str) -> list[str]:
    dates = []
    for match in re.finditer(r"\b(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\b", text):
        year, month, day = match.groups()
        dates.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")
    return dates


def validate_overview_ready(visible_text: str, target_date: str, config: dict[str, Any]) -> dict[str, Any]:
    normalized_text = normalize_text(visible_text)
    dates = _extract_dates(visible_text)
    accounts: dict[str, bool] = {}
    for account, info in config.get("accounts", {}).items():
        aliases = [account, info.get("baidu_name", ""), info.get("excel_name", "")]
        aliases.extend(info.get("aliases", []))
        accounts[account] = any(normalize_text(alias) and normalize_text(alias) in normalized_text for alias in aliases)

    fields = {
        "账户": "账户" in normalized_text,
        "展现": any(key in normalized_text for key in ["展现", "展现量"]),
        "点击": "点击" in normalized_text,
        "消费": any(key in normalized_text for key in ["消费", "花费"]),
    }
    checks = {
        "is_search_promotion": "搜索推广" in normalized_text,
        "date_is_today": target_date in dates,
        "all_accounts_visible": all(accounts.values()) if accounts else False,
        "required_fields_visible": all(fields.values()),
    }
    errors: list[str] = []
    if not checks["is_search_promotion"]:
        errors.append("当前页面不是搜索推广数据页")
    if not checks["date_is_today"]:
        errors.append(f"页面日期不是今天：目标 {target_date}，页面日期 {dates or '未识别'}")
    for account, found in accounts.items():
        if not found:
            errors.append(f"页面未看到目标账户：{account}")
    for field, found in fields.items():
        if not found:
            errors.append(f"页面未看到必要表头：{field}")
    return {
        "passed": not errors,
        "target_date": target_date,
        "dates_found": dates,
        "checks": checks,
        "accounts": accounts,
        "fields": fields,
        "errors": errors,
    }


def overview_text_has_account_table(visible_text: str, config: dict[str, Any]) -> bool:
    normalized_text = normalize_text(visible_text)
    required_headers = ["账户", "展现", "点击", "消费"]
    if not all(header in normalized_text for header in required_headers):
        return False
    for account, info in config.get("accounts", {}).items():
        aliases = [account, info.get("baidu_name", ""), info.get("excel_name", "")]
        aliases.extend(info.get("aliases", []))
        if any(normalize_text(alias) and normalize_text(alias) in normalized_text for alias in aliases):
            return True
    return False


def _read_page_text(page) -> str:
    deadline = datetime.now().timestamp() + 12
    last_text = ""
    while datetime.now().timestamp() < deadline:
        try:
            last_text = page.locator("body").inner_text(timeout=3000)
        except Exception:
            last_text = ""
        if last_text.strip():
            return last_text
        try:
            page.wait_for_timeout(600)
        except Exception:
            break
    return last_text


def _ensure_baidu_home_rendered(page, config: dict[str, Any], logger) -> str:
    visible_text = _read_page_text(page)
    if visible_text.strip():
        return visible_text
    start_url = config.get("baidu", {}).get("start_url", "https://yingxiao.baidu.com/")
    home_url = start_url.rstrip("/") + "/home" if start_url.rstrip("/") == "https://yingxiao.baidu.com" else start_url
    logger.info("当前百度页面可见文本为空，尝试打开首页：%s", home_url)
    try:
        page.goto(home_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        logger.info("打开百度首页或等待 networkidle 超时，继续读取当前页面。")
    return _read_page_text(page)


def _safe_wait_after_click(page, logger) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        logger.info("点击后 networkidle 等待超时，继续短暂等待当前页面状态。")
    try:
        page.wait_for_timeout(1200)
    except Exception:
        pass


def _fill_first_available(page, selectors: list[str], value: str, logger, field_name: str) -> bool:
    deadline = datetime.now().timestamp() + 15
    while datetime.now().timestamp() < deadline:
        for selector in selectors:
            try:
                locator = page.locator(selector)
                if locator.count() <= 0:
                    continue
                locator.first.fill(value, timeout=5000)
                logger.info("已填写百度登录字段：%s", field_name)
                return True
            except Exception:
                continue
        try:
            page.wait_for_timeout(500)
        except Exception:
            break
    return False


def _click_login_submit(page, logger) -> bool:
    for selector in ['#submit-form', 'input[type="submit"]']:
        try:
            locator = page.locator(selector)
            if locator.count() > 0:
                locator.first.click(timeout=5000)
                logger.info("已点击百度登录提交按钮：%s", selector)
                _safe_wait_after_click(page, logger)
                return True
        except Exception:
            continue
    labels = ["登录", "立即登录", "登 录", "立即登陆", "登陆"]
    return _click_by_text_or_role(page, labels, logger) is not None


def _auto_login_if_needed(page, root: Path, config: dict[str, Any], logger) -> bool:
    text = _read_page_text(page)
    classification = classify_baidu_page(page.url, text)
    if (
        classification["login_status"] != "not_logged_in"
        and "login" not in page.url
        and not should_open_cas_login(page.url)
    ):
        return True

    credentials = load_project_credentials(root, config, "baidu", config.get("baidu", {}).get("credential_project", "yunnan_yinkang"))
    if not credentials:
        logger.warning("未找到百度本地凭据文件，无法自动登录。")
        return False

    if "cas.baidu.com" not in page.url:
        logger.info("打开百度登录页：%s", CAS_LOGIN_URL)
        page.goto(CAS_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        _safe_wait_after_click(page, logger)
    elif should_open_cas_login(page.url):
        logger.info("当前是百度营销展示登录页，切换到 CAS 登录表单：%s", CAS_LOGIN_URL)
        page.goto(CAS_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        _safe_wait_after_click(page, logger)

    username_ok = _fill_first_available(
        page,
        [
            '#uc-common-account',
            'input[name="username"]',
            'input[name="userName"]',
            'input[name="account"]',
            'input[name="entered_login"]',
            'input[type="text"]',
            'input[placeholder*="账号"]',
            'input[placeholder*="用户名"]',
            'input[placeholder*="手机号"]',
        ],
        credentials["username"],
        logger,
        "username",
    )
    password_ok = _fill_first_available(
        page,
        [
            '#ucsl-password-edit',
            'input[type="password"]',
            'input[name="password"]',
            'input[placeholder*="密码"]',
        ],
        credentials["password"],
        logger,
        "password",
    )
    if not username_ok or not password_ok:
        logger.error("百度登录页字段识别失败：username=%s password=%s", username_ok, password_ok)
        return False
    try:
        checkbox = page.locator("#privacy-agreement")
        if checkbox.count() > 0 and not checkbox.first.is_checked():
            checkbox.first.check(timeout=5000)
            logger.info("已勾选百度营销服务协议。")
    except Exception:
        logger.info("百度营销服务协议勾选状态不可读，继续尝试登录。")
    if not _click_login_submit(page, logger):
        logger.error("百度登录按钮识别失败。")
        return False
    try:
        page.wait_for_url(lambda url: "login" not in url, timeout=30000)
    except Exception:
        logger.info("等待登录 URL 跳转超时，继续读取页面状态。")
    _safe_wait_after_click(page, logger)
    text = _read_page_text(page)
    classification = classify_baidu_page(page.url, text)
    return classification["login_status"] != "not_logged_in" and "login" not in page.url


def _click_by_text_or_role(page, labels: list[str], logger) -> str | None:
    for label in labels:
        pattern = re.compile(re.escape(label), re.I)
        candidates = [
            lambda: page.get_by_role("link", name=pattern),
            lambda: page.get_by_role("button", name=pattern),
            lambda: page.get_by_role("tab", name=pattern),
            lambda: page.get_by_role("menuitem", name=pattern),
            lambda: page.get_by_text(pattern).first,
        ]
        for locator_factory in candidates:
            try:
                locator = locator_factory()
                if locator.count() <= 0:
                    continue
                target = locator.first
                try:
                    target.hover(timeout=3000)
                    page.wait_for_timeout(300)
                except Exception:
                    pass
                target.click(timeout=8000)
                logger.info("clicked baidu menu label: %s", label)
                _safe_wait_after_click(page, logger)
                return label
            except Exception:
                continue
    return None


def _is_report_page_ready_for_parse(page, config: dict[str, Any], visible_text: str | None = None) -> bool:
    text = visible_text if visible_text is not None else _read_page_text(page)
    classification = classify_baidu_page(page.url, text)
    if not is_search_promotion_overview(classification):
        return False
    if not overview_text_has_account_table(text, config):
        return False
    return True

def _select_backend_page(context, current_page, logger):
    backend_pages = [
        page for page in context.pages
        if "cc.baidu.com" in page.url or "yingxiao.baidu.com" in page.url
    ]
    for page in backend_pages:
        if "cc.baidu.com" in page.url:
            try:
                page.bring_to_front()
            except Exception:
                pass
            logger.info("已切换到百度投放后台页面：%s", page.url)
            return page
    return current_page


def _goto_report_page(page, logger, root=None, config=None) -> bool:
    from modules.baidu_session import is_baidu_noauth_page
    from modules.baidu_detector import classify_baidu_page as detector_classify_baidu_page

    current_text = _read_page_text(page)
    current_cls = detector_classify_baidu_page(page.url, current_text)
    if page.url.rstrip("/").startswith(CC_REPORT_URL) and not is_baidu_noauth_page(page):
        if current_cls.get("signals", {}).get("has_search_promotion") or root is None or config is None:
            return True

    if not page.url.rstrip("/").startswith(CC_REPORT_URL):
        logger.info("open baidu report url directly: %s", CC_REPORT_URL)
        try:
            page.goto(CC_REPORT_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            logger.error("open baidu report page failed")
        _safe_wait_after_click(page, logger)
        current_text = _read_page_text(page)
        current_cls = detector_classify_baidu_page(page.url, current_text)
        if page.url.rstrip("/").startswith(CC_REPORT_URL) and not is_baidu_noauth_page(page):
            if current_cls.get("signals", {}).get("has_search_promotion"):
                return True

    if root is None or config is None:
        return False

    for attempt in range(2):
        logger.info("navigate to search promotion via menu, attempt=%s", attempt + 1)
        _ensure_baidu_home_rendered(page, config, logger)
        page.wait_for_timeout(1500)
        menu_ok = True
        for label in ["\u6570\u636e\u62a5\u544a", "\u6570\u636e\u6982\u89c8", "\u641c\u7d22\u63a8\u5e7f"]:
            if not _click_by_text_or_role(page, [label], logger):
                logger.error("menu path click failed: %s", label)
                menu_ok = False
                break
            page.wait_for_timeout(1200)
        if not menu_ok:
            if attempt == 0:
                page.wait_for_timeout(2000)
                continue
            return False
        _wait_for_search_promotion_content(page, logger)
        current_text = _read_page_text(page)
        current_cls = detector_classify_baidu_page(page.url, current_text)
        if is_baidu_noauth_page(page):
            logger.error("menu path still on noauth page")
            if attempt == 0:
                page.wait_for_timeout(2000)
                continue
            return False
        if current_cls.get("signals", {}).get("has_search_promotion"):
            return True
        logger.error("menu path did not reach search promotion page, attempt=%s", attempt + 1)
        if attempt == 0:
            page.wait_for_timeout(2000)
    return False

def _wait_for_search_promotion_content(page, logger, timeout_ms: int = 10000) -> bool:
    """等待页面出现搜索推广特征（表头关键词）。"""
    keywords = ["展现", "点击", "消费", "账户"]
    deadline = __import__("time").time() + timeout_ms / 1000.0
    while __import__("time").time() < deadline:
        try:
            text = page.locator("body").inner_text(timeout=2000) or ""
            if all(kw in text for kw in keywords[:2]):
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    logger.info("等待搜索推广内容超时")
    return False


def _refresh_report_and_wait_for_data(page, config: dict[str, Any], logger) -> str:
    logger.info("抓取前刷新百度 report 页面，避免读取非实时或未加载数据。")
    try:
        page.reload(wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        logger.info("刷新百度 report 页面异常，继续等待当前页面数据：%s", exc)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        logger.info("刷新后 networkidle 等待超时，继续轮询账户表格。")

    deadline = datetime.now().timestamp() + int(config.get("baidu", {}).get("report_table_wait_seconds", 30))
    last_text = ""
    while datetime.now().timestamp() < deadline:
        last_text = _read_page_text(page)
        if overview_text_has_account_table(last_text, config):
            logger.info("百度 report 页面账户表格已加载。")
            return last_text
        try:
            page.wait_for_timeout(1000)
        except Exception:
            break
    logger.info("百度 report 页面账户表格等待结束，但未看到完整账户行。")
    return last_text


def _dump_open_overview_artifacts(root: Path, page, report: dict[str, Any], include_screenshot: bool) -> None:
    text_path = root / "reports" / "baidu_visible_text.txt"
    visible_text = _read_page_text(page)
    _write_text(text_path, visible_text)
    _write_debug_artifacts(root, page, {"exceptions": []}, include_screenshot=include_screenshot)
    report["outputs"]["visible_text"] = str(text_path)
    report["outputs"]["debug_html"] = str(root / "reports" / "baidu_debug.html")


def baidu_open_overview(
    config: dict[str, Any],
    root: Path,
    logger,
    input_func: Callable[[str], str] = input,
) -> dict[str, Any]:
    settings = get_browser_settings(config)
    report_path = root / "reports" / "baidu_open_overview_report.json"
    baidu_config = config.get("baidu", {})
    report: dict[str, Any] = {
        "mode": "baidu-open-overview",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": None,
        "browser": {
            "mode": settings["mode"],
            "cdp_endpoint": settings["cdp_endpoint"],
            "allow_edge_fallback": settings["allow_edge_fallback"],
            "headless": settings["headless"],
        },
        "connected": False,
        "initial_url": None,
        "final_url": None,
        "initial_page_type": None,
        "final_page_type": None,
        "login_status": "unknown",
        "already_on_target": False,
        "clicked_steps": [],
        "outputs": {
            "report": str(report_path),
            "visible_text": str(root / "reports" / "baidu_visible_text.txt"),
            "debug_html": str(root / "reports" / "baidu_debug.html"),
        },
        "errors": [],
    }

    def finish(page=None) -> dict[str, Any]:
        if page is not None:
            try:
                _dump_open_overview_artifacts(root, page, report, bool(baidu_config.get("debug_screenshot", False)))
            except Exception as exc:
                report["errors"].append(f"output debug artifacts failed: {exc}")
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        _write_json(report_path, report)
        logger.info("baidu-open-overview report saved: %s; errors=%s", report_path, len(report["errors"]))
        return report

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        report["errors"].append(f"Playwright import failed: {exc}")
        return finish()

    with sync_playwright() as playwright:
        try:
            context, page = launch_chrome_context(playwright, config, root)
        except BrowserLaunchError as exc:
            report["errors"].append(str(exc))
            logger.error("baidu-open-overview connect chrome failed: %s", exc)
            return finish()

        report["connected"] = True
        page.bring_to_front()
        report["initial_url"] = page.url
        try:
            page.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception:
            logger.info("baidu-open-overview wait domcontentloaded timed out")

        visible_text = _ensure_baidu_home_rendered(page, config, logger)
        classification = classify_baidu_page(page.url, visible_text)
        report["initial_page_type"] = classification["page_type"]
        report["login_status"] = classification["login_status"]

        if classification["login_status"] == "not_logged_in":
            if not _auto_login_if_needed(page, root, config, logger):
                report["errors"].append(build_login_failure_message(config))
                return finish(page)
            visible_text = _read_page_text(page)
            classification = classify_baidu_page(page.url, visible_text)
            report["login_status"] = classification["login_status"]

        from modules.baidu_session import ensure_baidu_profile_session
        session_result = ensure_baidu_profile_session(
            root, config, page, logger, task="fetch-baidu-auto", input_func=input_func
        )
        report["session_check"] = {
            "passed": session_result.get("passed"),
            "decision": session_result.get("decision"),
            "reason": session_result.get("reason"),
        }
        if not session_result.get("passed"):
            report["errors"].append("account switch failed or cancelled")
            return finish(page)

        visible_text = _read_page_text(page)
        classification = classify_baidu_page(page.url, visible_text)
        report["login_status"] = classification["login_status"]
        if _is_report_page_ready_for_parse(page, config, visible_text):
            visible_text = _refresh_report_and_wait_for_data(page, config, logger)
            classification = classify_baidu_page(page.url, visible_text)
            if _is_report_page_ready_for_parse(page, config, visible_text):
                report["already_on_target"] = True
                report["final_url"] = page.url
                report["final_page_type"] = classification["page_type"]
                return finish(page)

        if not _goto_report_page(page, logger, root=root, config=config):
            report["errors"].append("\u767e\u5ea6\u641c\u7d22\u63a8\u5e7f\u6570\u636e\u9875\u6253\u5f00\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u767e\u5ea6\u540e\u53f0\u9875\u9762\u72b6\u6001")
            return finish(page)

        visible_text = _refresh_report_and_wait_for_data(page, config, logger)
        classification = classify_baidu_page(page.url, visible_text)
        report["login_status"] = classification["login_status"]
        report["final_url"] = page.url
        report["final_page_type"] = classification["page_type"]
        if not _is_report_page_ready_for_parse(page, config, visible_text):
            report["errors"].append("\u767e\u5ea6\u641c\u7d22\u63a8\u5e7f\u6570\u636e\u9875\u6253\u5f00\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u767e\u5ea6\u540e\u53f0\u9875\u9762\u72b6\u6001")
            return finish(page)
        return finish(page)


def baidu_prepare_overview(config: dict[str, Any], root: Path, logger) -> dict[str, Any]:
    report_path = root / "reports" / "baidu_prepare_overview_report.json"
    report: dict[str, Any] = {
        "mode": "baidu-prepare-overview",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": None,
        "target_date": date.today().isoformat(),
        "open_report": None,
        "ready_check": None,
        "outputs": {
            "report": str(report_path),
            "visible_text": str(root / "reports" / "baidu_visible_text.txt"),
            "debug_html": str(root / "reports" / "baidu_debug.html"),
        },
        "errors": [],
    }
    open_report = baidu_open_overview(config, root, logger)
    report["open_report"] = {
        "final_url": open_report.get("final_url"),
        "final_page_type": open_report.get("final_page_type"),
        "errors": open_report.get("errors", []),
    }
    if open_report.get("errors"):
        report["errors"].extend(open_report["errors"])
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        _write_json(report_path, report)
        logger.error("baidu-prepare-overview 中断：搜索推广页打开失败。")
        return report

    text_path = root / "reports" / "baidu_visible_text.txt"
    visible_text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
    ready = validate_overview_ready(visible_text, report["target_date"], config)
    report["ready_check"] = ready
    report["errors"].extend(error for error in ready["errors"] if error not in report["errors"])

    session_decision = (open_report.get("session_check") or {}).get("decision", "")
    has_missing_accounts = any(
        "\u7f3a\u5931" in e or "\u7f3a\u5c11" in e or "\u672a\u770b\u5230" in e
        for e in ready.get("errors", [])
    )
    if not ready.get("passed") and session_decision == "tentative_bypass" and has_missing_accounts:
        from modules.baidu_session import clear_browser_login_state
        report["validation_retry_triggered"] = True
        report["validation_retry_reason"] = "tentative_bypass_after_missing_accounts"
        clear_browser_login_state(root)
        logger.info("tentative bypass failed account validation, retry with relogin")
        retry_open = baidu_open_overview(config, root, logger)
        report["errors"] = []
        if not retry_open.get("errors"):
            retry_text_path = root / "reports" / "baidu_visible_text.txt"
            retry_text = retry_text_path.read_text(encoding="utf-8") if retry_text_path.exists() else ""
            ready = validate_overview_ready(retry_text, report["target_date"], config)
            report["ready_check"] = ready
            if ready.get("passed"):
                report["relogin_after_validation_failed"] = True
                report["validation_retry_passed"] = True
            else:
                report["errors"] = [
                    "\u767e\u5ea6\u8d26\u53f7\u5207\u6362\u540e\u4ecd\u672a\u770b\u5230\u5f53\u524d\u9879\u76ee\u8d26\u6237\uff0c\u8bf7\u68c0\u67e5\u767e\u5ea6\u8d26\u53f7\u6216\u9879\u76ee\u914d\u7f6e"
                ]
        else:
            report["errors"] = [
                "\u767e\u5ea6\u8d26\u53f7\u5207\u6362\u540e\u4ecd\u672a\u770b\u5230\u5f53\u524d\u9879\u76ee\u8d26\u6237\uff0c\u8bf7\u68c0\u67e5\u767e\u5ea6\u8d26\u53f7\u6216\u9879\u76ee\u914d\u7f6e"
            ]

    if ready.get("passed"):
        from modules.baidu_session import mark_browser_login_success
        profile = config.get("baidu", {}).get("credential_profile") or config.get("baidu", {}).get("credential_project", "")
        if profile:
            mark_browser_login_success(
                root,
                profile,
                project_id=config.get("project_id"),
                project_name=config.get("project_name"),
                task="fetch-baidu-auto",
            )

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    _write_json(report_path, report)
    logger.info("baidu-prepare-overview report saved: %s; errors=%s", report_path, len(report["errors"]))
    return report
