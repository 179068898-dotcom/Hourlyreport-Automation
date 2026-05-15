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
                locator.first.click(timeout=8000)
                logger.info("百度概览路径点击：%s", label)
                _safe_wait_after_click(page, logger)
                return label
            except Exception:
                continue
    return None


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
    """打开百度搜索推广数据页。

    - 已在 report 页且非 noauth → 直接通过
    - 不在 report 页 → 直接 goto；goto 后仍在 homepage 或 noauth → 走菜单路径
    - 菜单路径：首页 → 数据报告 → 数据概览 → 搜索推广
    """
    from modules.baidu_session import is_baidu_noauth_page, force_relogin_current_project

    # 已在 report 页且可用 → 直接通过
    if page.url.rstrip("/").startswith(CC_REPORT_URL) and not is_baidu_noauth_page(page):
        return True

    # 尝试直接 goto report 页
    if not page.url.rstrip("/").startswith(CC_REPORT_URL):
        logger.info("直接打开百度数据报告页：%s", CC_REPORT_URL)
        try:
            page.goto(CC_REPORT_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            logger.error("进入百度报告页异常")
        _safe_wait_after_click(page, logger)
        # 验证确实进入了 report 页（非 homepage）
        if page.url.rstrip("/").startswith(CC_REPORT_URL) and not is_baidu_noauth_page(page):
            return True

    # goto 失败 / 停在 homepage / noauth → 菜单路径进入
    if root is not None and config is not None:
        logger.info("通过菜单路径进入搜索推广数据页")
        # 如果不在首页，先渲染首页
        _ensure_baidu_home_rendered(page, config, logger)
        _safe_wait_after_click(page, logger)
        for label in ["数据报告", "数据概览", "搜索推广"]:
            if not _click_by_text_or_role(page, [label], logger):
                logger.error("菜单路径点击失败：%s", label)
                return False
            _safe_wait_after_click(page, logger)
        # 验证结果
        if is_baidu_noauth_page(page):
            logger.error("菜单路径后仍为 noauth 页")
            return False
        from modules.baidu_detector import classify_baidu_page
        text = _read_page_text(page)
        cls = classify_baidu_page(page.url, text)
        if not cls.get("signals", {}).get("has_search_promotion"):
            logger.error("菜单路径后不是搜索推广数据页")
            return False
        return True

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
                report["errors"].append(f"输出百度诊断文件失败：{exc}")
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        _write_json(report_path, report)
        logger.info("baidu-open-overview 报告已输出：%s；错误数：%s", report_path, len(report["errors"]))
        return report

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        report["errors"].append(f"Playwright 未安装，无法打开百度概览页：{exc}")
        return finish()

    with sync_playwright() as playwright:
        try:
            context, page = launch_chrome_context(playwright, config, root)
        except BrowserLaunchError as exc:
            report["errors"].append(str(exc))
            logger.error("baidu-open-overview 连接 Chrome 失败：%s", exc)
            return finish()

        report["connected"] = True
        page.bring_to_front()
        report["initial_url"] = page.url
        try:
            page.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception:
            logger.info("baidu-open-overview 等待 domcontentloaded 超时，继续读取当前页面。")

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

        # 百度登录状态守卫：确保当前浏览器登录的是本项目账号
        from modules.baidu_session import ensure_baidu_profile_session
        if not ensure_baidu_profile_session(root, config, page, logger, task="fetch-baidu-auto",
                                            input_func=input_func):
            report["errors"].append("百度账号切换未完成或用户取消")
            return finish(page)

        if is_search_promotion_overview(classification):
            visible_text = _refresh_report_and_wait_for_data(page, config, logger)
            classification = classify_baidu_page(page.url, visible_text)
            report["already_on_target"] = True
            report["final_url"] = page.url
            report["final_page_type"] = classification["page_type"]
            return finish(page)

        if not _goto_report_page(page, logger, root=root, config=config):
            report["errors"].append("百度报告页打开失败，请检查网络或百度页面状态")
            return finish(page)
        report["clicked_steps"].append({"step": "打开数据报告页", "clicked_text": CC_REPORT_URL})
        visible_text = _refresh_report_and_wait_for_data(page, config, logger)
        classification = classify_baidu_page(page.url, visible_text)
        report["login_status"] = classification["login_status"]
        if classification["login_status"] == "not_logged_in" or "login" in page.url:
            if not _auto_login_if_needed(page, root, config, logger):
                report["errors"].append(build_login_failure_message(config))
                return finish(page)
            if not _goto_report_page(page, logger, root=root, config=config):
                report["errors"].append("百度报告页打开失败，请检查网络或百度页面状态")
                return finish(page)
            visible_text = _refresh_report_and_wait_for_data(page, config, logger)
            classification = classify_baidu_page(page.url, visible_text)
            report["login_status"] = classification["login_status"]
        if is_search_promotion_overview(classification):
            report["final_url"] = page.url
            report["final_page_type"] = classification["page_type"]
            return finish(page)

        if page.url.rstrip("/").startswith(CC_REPORT_URL):
            visible_text = _refresh_report_and_wait_for_data(page, config, logger)
            classification = classify_baidu_page(page.url, visible_text)
            if is_search_promotion_overview(classification):
                report["final_url"] = page.url
                report["final_page_type"] = classification["page_type"]
                return finish(page)

        steps = [
            ("搜索推广", ["搜索推广"]),
        ]
        for step_name, labels in steps:
            visible_text = _read_page_text(page)
            classification = classify_baidu_page(page.url, visible_text)
            if step_name == "数据报告" and classification["signals"].get("has_data_report"):
                logger.info("百度概览路径已处于或可见数据报告区域，跳过重复点击：%s", step_name)
                continue
            if step_name == "数据概览" and classification["signals"].get("has_data_overview"):
                logger.info("百度概览路径已处于数据概览，跳过重复点击：%s", step_name)
                continue
            if step_name == "搜索推广" and classification["signals"].get("has_search_promotion"):
                logger.info("百度概览路径已处于搜索推广，跳过重复点击：%s", step_name)
                continue

            clicked = _click_by_text_or_role(page, labels, logger)
            if not clicked:
                report["errors"].append(f"找不到可点击入口：{step_name}")
                return finish(page)
            report["clicked_steps"].append({"step": step_name, "clicked_text": clicked})

        visible_text = _read_page_text(page)
        final_classification = classify_baidu_page(page.url, visible_text)
        report["final_url"] = page.url
        report["final_page_type"] = final_classification["page_type"]
        if not is_search_promotion_overview(final_classification):
            report["errors"].append("未能进入 数据报告 → 数据概览 → 搜索推广 页面")
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

    # 项目账户复核通过 → 写 browser_login_state
    if ready.get("passed"):
        from modules.baidu_session import mark_browser_login_success
        profile = config.get("baidu", {}).get("credential_profile") or config.get("baidu", {}).get("credential_project", "")
        if profile:
            mark_browser_login_success(root, profile, project_id=config.get("project_id"),
                                       project_name=config.get("project_name"), task="fetch-baidu-auto")

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    _write_json(report_path, report)
    logger.info("baidu-prepare-overview 报告已输出：%s；错误数：%s", report_path, len(report["errors"]))
    return report
