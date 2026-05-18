from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from modules.baidu_browser import _write_debug_artifacts
from modules.baidu_detector import classify_baidu_page
from modules.baidu_parser import extract_baidu_rows_from_page
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
        and (signals.get("has_data_overview") or (signals.get("has_data_report") and signals.get("has_table_fields")))
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


def _table_parse_debug_path(root: Path) -> Path:
    return root / "reports" / "baidu_table_parse_debug.json"


def _table_candidates_path(root: Path) -> Path:
    return root / "reports" / "baidu_table_candidates.json"


def _timestamped_report_path(root: Path, stem: str, project_id: str | None) -> Path:
    safe_project_id = re.sub(r"[^0-9a-zA-Z_-]+", "_", str(project_id or "unknown"))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return root / "reports" / f"{stem}_{safe_project_id}_{timestamp}.json"


def _write_table_parse_artifacts(root: Path, extraction: dict[str, Any]) -> None:
    debug_data = extraction.get("debug", {})
    candidate_data = {
        "source": extraction.get("extraction_method"),
        "rows": extraction.get("rows", []),
        "row_count": len(extraction.get("rows", [])),
        "detected_headers": extraction.get("detected_headers", []),
    }
    project_id = debug_data.get("project_id")

    _write_json(_table_parse_debug_path(root), debug_data)
    _write_json(root / "reports" / "baidu_table_parse_debug_latest.json", debug_data)
    _write_json(_timestamped_report_path(root, "baidu_table_parse_debug", project_id), debug_data)

    _write_json(_table_candidates_path(root), candidate_data)
    _write_json(root / "reports" / "baidu_table_candidates_latest.json", candidate_data)
    _write_json(_timestamped_report_path(root, "baidu_table_candidates", project_id), candidate_data)


def _load_table_parse_debug(root: Path) -> dict[str, Any]:
    path = _table_parse_debug_path(root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def validate_overview_ready(visible_text: str, target_date: str, config: dict[str, Any]) -> dict[str, Any]:
    normalized_text = normalize_text(visible_text)
    dates = _extract_dates(visible_text)
    accounts: dict[str, bool] = {}
    for account, info in config.get("accounts", {}).items():
        aliases = [account, info.get("baidu_name", ""), info.get("excel_name", "")]
        aliases.extend(info.get("aliases", []))
        accounts[account] = any(normalize_text(alias) and normalize_text(alias) in normalized_text for alias in aliases)

    fields = {
        "账户": normalize_text("账户") in normalized_text,
        "展现": any(item in normalized_text for item in [normalize_text("展现"), normalize_text("展现量")]),
        "点击": normalize_text("点击") in normalized_text,
        "消费": any(item in normalized_text for item in [normalize_text("消费"), normalize_text("花费")]),
    }
    checks = {
        "is_search_promotion": normalize_text("搜索推广") in normalized_text,
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


def validate_overview_parse_ready(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    debug = _load_table_parse_debug(root)
    if not debug:
        return {
            "passed": True,
            "checks": {"debug_report_present": False},
            "debug": {},
            "errors": [],
        }
    normalized_headers = {normalize_text(item) for item in debug.get("detected_headers", [])}
    required = {name: normalize_text(name) for name in ["账户", "展现", "点击", "消费"]}
    checks = {
        "required_headers_detected": all(value in normalized_headers for value in required.values()),
        "at_least_one_required_account": int(debug.get("parsed_account_count", 0) or 0) >= 1,
        "all_required_accounts_detected": not debug.get("missing_accounts"),
    }
    errors: list[str] = []
    if not checks["required_headers_detected"]:
        for field, normalized in required.items():
            if normalized not in normalized_headers:
                errors.append(f"页面未看到必要表头：{field}")
    if not checks["at_least_one_required_account"]:
        errors.append("百度搜索推广账户表格未完整加载，请刷新或稍后重试")
    return {
        "passed": not errors,
        "checks": checks,
        "debug": debug,
        "errors": errors,
    }


def validate_overview_parse_ready_v2(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    debug = _load_table_parse_debug(root)
    if not debug:
        if not config.get("accounts"):
            return {
                "passed": True,
                "checks": {"debug_report_present": False, "skipped_without_accounts": True},
                "debug": {},
                "errors": [],
            }
        return {
            "passed": False,
            "checks": {"debug_report_present": False},
            "debug": {},
            "errors": ["百度搜索推广账户表格未完整加载或列解析异常，请刷新后重试"],
        }

    normalized_headers = {normalize_text(item) for item in debug.get("detected_headers", [])}
    required = {name: normalize_text(name) for name in ["账户", "展现", "点击", "消费"]}
    required_account_count = len(debug.get("required_accounts") or [])
    parsed_account_count = int(debug.get("parsed_account_count", 0) or 0)
    missing_accounts = list(debug.get("missing_accounts") or [])
    non_numeric_fields = list(debug.get("non_numeric_fields") or [])
    percent_misalignment = bool(debug.get("percent_misalignment"))
    extraction_method = str(debug.get("extraction_method") or "")

    checks = {
        "required_headers_detected": all(value in normalized_headers for value in required.values()),
        "parsed_account_count_matches_required": parsed_account_count >= required_account_count if required_account_count else parsed_account_count >= 1,
        "all_required_accounts_detected": not missing_accounts,
        "non_numeric_fields_empty": not non_numeric_fields,
        "visible_text_percent_misalignment": extraction_method == "visible_text" and percent_misalignment,
    }

    errors: list[str] = []
    if not checks["required_headers_detected"]:
        errors.append("百度搜索推广账户表格未完整加载或列解析异常，请刷新后重试")
    if (
        not checks["parsed_account_count_matches_required"]
        or not checks["all_required_accounts_detected"]
        or not checks["non_numeric_fields_empty"]
        or checks["visible_text_percent_misalignment"]
    ):
        if "百度搜索推广账户表格未完整加载或列解析异常，请刷新后重试" not in errors:
            errors.append("百度搜索推广账户表格未完整加载或列解析异常，请刷新后重试")
    if checks["visible_text_percent_misalignment"]:
        errors.append("百度表格列解析疑似错位，请检查 DOM 表格提取。")

    return {
        "passed": not errors,
        "checks": checks,
        "debug": debug,
        "errors": errors,
    }


def overview_text_has_account_table(visible_text: str, config: dict[str, Any]) -> bool:
    normalized_text = normalize_text(visible_text)
    required_headers = ["账户", "展现", "点击", "消费"]
    if not all(normalize_text(header) in normalized_text for header in required_headers):
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
        logger.info("打开百度首页或等待 networkidle 超时，继续读取当前页面")
    return _read_page_text(page)


def _safe_wait_after_click(page, logger) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        logger.info("点击后 networkidle 等待超时，继续短暂等待当前页面状态")
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


def _click_login_submit(page, logger) -> bool:
    for selector in ["#submit-form", 'input[type="submit"]']:
        try:
            locator = page.locator(selector)
            if locator.count() > 0:
                locator.first.click(timeout=5000)
                logger.info("已点击百度登录提交按钮：%s", selector)
                _safe_wait_after_click(page, logger)
                return True
        except Exception:
            continue
    return _click_by_text_or_role(page, ["登录", "立即登录", "登陆", "立即登陆"], logger) is not None


def _auto_login_if_needed(page, root: Path, config: dict[str, Any], logger) -> bool:
    text = _read_page_text(page)
    classification = classify_baidu_page(page.url, text)
    if classification["login_status"] != "not_logged_in" and "login" not in page.url and not should_open_cas_login(page.url):
        return True

    credentials = load_project_credentials(
        root,
        config,
        "baidu",
        config.get("baidu", {}).get("credential_project", "yunnan_yinkang"),
    )
    if not credentials:
        logger.warning("未找到百度本地凭据文件，无法自动登录")
        return False

    if "cas.baidu.com" not in page.url or should_open_cas_login(page.url):
        logger.info("打开百度登录页：%s", CAS_LOGIN_URL)
        page.goto(CAS_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        _safe_wait_after_click(page, logger)

    username_ok = _fill_first_available(
        page,
        [
            "#uc-common-account",
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
        ["#ucsl-password-edit", 'input[type="password"]', 'input[name="password"]', 'input[placeholder*="密码"]'],
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
            logger.info("已勾选百度营销服务协议")
    except Exception:
        logger.info("百度营销服务协议勾选状态不可读，继续尝试登录")

    if not _click_login_submit(page, logger):
        logger.error("百度登录按钮识别失败")
        return False

    try:
        page.wait_for_url(lambda url: "login" not in url, timeout=30000)
    except Exception:
        logger.info("等待登录 URL 跳转超时，继续读取页面状态")
    _safe_wait_after_click(page, logger)
    text = _read_page_text(page)
    classification = classify_baidu_page(page.url, text)
    return classification["login_status"] != "not_logged_in" and "login" not in page.url


def _is_report_page_ready_for_parse(page, config: dict[str, Any], visible_text: str | None = None) -> bool:
    text = visible_text if visible_text is not None else _read_page_text(page)
    classification = classify_baidu_page(page.url, text)
    if not is_search_promotion_overview(classification):
        return False
    extraction = extract_baidu_rows_from_page(page, config)
    return bool(extraction.get("debug", {}).get("parse_ready"))


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
        for label in ["数据报告", "数据概览", "搜索推广"]:
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
    keywords = ["展现", "点击", "消费", "账户"]
    deadline = __import__("time").time() + timeout_ms / 1000.0
    while __import__("time").time() < deadline:
        try:
            text = page.locator("body").inner_text(timeout=2000) or ""
            if all(keyword in text for keyword in keywords[:2]):
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    logger.info("等待搜索推广内容超时")
    return False


def _refresh_report_and_wait_for_data(page, config: dict[str, Any], logger) -> str:
    logger.info("抓取前刷新百度 report 页面，避免读取未完成加载的数据")
    try:
        page.reload(wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        logger.info("刷新百度 report 页面异常，继续等待当前页面数据：%s", exc)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        logger.info("刷新后 networkidle 等待超时，继续轮询账户表格")

    deadline = datetime.now().timestamp() + int(config.get("baidu", {}).get("report_table_wait_seconds", 30))
    last_text = ""
    while datetime.now().timestamp() < deadline:
        last_text = _read_page_text(page)
        extraction = extract_baidu_rows_from_page(page, config)
        if extraction.get("debug", {}).get("parse_ready"):
            logger.info("百度 report 页面账户表格已加载且可解析")
            return last_text
        try:
            page.wait_for_timeout(1000)
        except Exception:
            break
    logger.info("百度 report 页面账户表格等待结束，但仍不可解析")
    return last_text


def _dump_open_overview_artifacts(root: Path, page, report: dict[str, Any], include_screenshot: bool) -> None:
    text_path = root / "reports" / "baidu_visible_text.txt"
    visible_text = _read_page_text(page)
    _write_text(text_path, visible_text)
    parse_config = report.get("config_for_parse")
    if parse_config:
        extraction = extract_baidu_rows_from_page(page, parse_config)
        _write_table_parse_artifacts(root, extraction)
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
            "table_parse_debug": str(_table_parse_debug_path(root)),
            "table_candidates": str(_table_candidates_path(root)),
        },
        "errors": [],
        "config_for_parse": config,
    }

    def finish(page=None) -> dict[str, Any]:
        if page is not None:
            try:
                _dump_open_overview_artifacts(root, page, report, bool(baidu_config.get("debug_screenshot", False)))
            except Exception as exc:
                report["errors"].append(f"output debug artifacts failed: {exc}")
        report.pop("config_for_parse", None)
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
            _context, page = launch_chrome_context(playwright, config, root)
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

        session_result = ensure_baidu_profile_session(root, config, page, logger, task="fetch-baidu-auto", input_func=input_func)
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
            report["errors"].append("百度搜索推广数据页打开失败，请检查百度后台页面状态")
            return finish(page)

        visible_text = _refresh_report_and_wait_for_data(page, config, logger)
        classification = classify_baidu_page(page.url, visible_text)
        report["login_status"] = classification["login_status"]
        report["final_url"] = page.url
        report["final_page_type"] = classification["page_type"]
        if not _is_report_page_ready_for_parse(page, config, visible_text):
            report["errors"].append("百度搜索推广数据页打开失败，请检查百度后台页面状态")
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
        "parse_check": None,
        "outputs": {
            "report": str(report_path),
            "visible_text": str(root / "reports" / "baidu_visible_text.txt"),
            "debug_html": str(root / "reports" / "baidu_debug.html"),
            "table_parse_debug": str(_table_parse_debug_path(root)),
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
        logger.error("baidu-prepare-overview 中断：搜索推广页打开失败")
        return report

    text_path = root / "reports" / "baidu_visible_text.txt"
    visible_text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
    ready = validate_overview_ready(visible_text, report["target_date"], config)
    parse_ready = validate_overview_parse_ready_v2(root, config)
    report["ready_check"] = ready
    report["parse_check"] = parse_ready
    report["errors"].extend(error for error in ready["errors"] if error not in report["errors"])
    report["errors"].extend(error for error in parse_ready["errors"] if error not in report["errors"])

    session_decision = (open_report.get("session_check") or {}).get("decision", "")
    has_missing_accounts = any("缺失" in e or "缺少" in e or "未看到" in e for e in ready.get("errors", []))
    if report["errors"] and session_decision == "tentative_bypass" and has_missing_accounts:
        from modules.baidu_session import clear_browser_login_state

        report["validation_retry_triggered"] = True
        report["validation_retry_reason"] = "tentative_bypass_after_missing_accounts"
        clear_browser_login_state(root)
        logger.info("tentative bypass failed account validation, retry with relogin")
        retry_open = baidu_open_overview(config, root, logger)
        report["errors"] = []
        if not retry_open.get("errors"):
            retry_text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
            ready = validate_overview_ready(retry_text, report["target_date"], config)
            parse_ready = validate_overview_parse_ready_v2(root, config)
            report["ready_check"] = ready
            report["parse_check"] = parse_ready
            report["errors"].extend(ready.get("errors", []))
            report["errors"].extend(error for error in parse_ready.get("errors", []) if error not in report["errors"])
            if not report["errors"]:
                report["relogin_after_validation_failed"] = True
                report["validation_retry_passed"] = True
            else:
                report["errors"] = ["百度账号切换后仍未看到当前项目账户，请检查百度账号或项目配置"]
        else:
            report["errors"] = ["百度账号切换后仍未看到当前项目账户，请检查百度账号或项目配置"]

    if not report["errors"]:
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
