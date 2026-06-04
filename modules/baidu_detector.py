from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.baidu_browser import _write_debug_artifacts
from modules.browser_manager import BrowserLaunchError, get_browser_settings, launch_chrome_context, prepare_automation_page
from modules.text_normalizer import normalize_text


PAGE_TYPES = ["未登录页", "百度营销首页", "数据报告", "数据概览", "搜索推广", "未知页面"]


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(normalize_text(keyword) in text for keyword in keywords)


def classify_baidu_page(url: str, visible_text: str) -> dict[str, Any]:
    text = normalize_text(visible_text)
    url_text = normalize_text(url)
    is_login_url = "cas.baidu.com" in url_text or "qingge.baidu.com/login" in url_text
    signals = {
        "has_login": _contains_any(text, ["登录", "扫码登录", "百度账号", "百度营销账号", "请输入账号", "密码", "验证码", "忘记密码"])
        or is_login_url,
        "has_register": _contains_any(text, ["注册", "立即推广", "开始推广"]),
        "has_home": _contains_any(text, ["首页", "客户中心", "进入"]) or "home" in url_text,
        "has_data_report": _contains_any(text, ["数据报告", "账户报告", "报告"]) or "report" in url_text,
        "has_data_overview": _contains_any(text, ["数据概览", "概览"]),
        "has_search_promotion": _contains_any(text, ["搜索推广", "详细数据"]),
        "has_table_fields": _contains_any(text, ["展现", "点击", "消费", "花费"]),
    }

    public_marketing_home = (
        (signals["has_login"] or signals["has_register"])
        and not (signals["has_data_report"] or signals["has_data_overview"] or signals["has_search_promotion"] or signals["has_table_fields"])
    )
    if is_login_url or public_marketing_home or (signals["has_login"] and not (signals["has_data_report"] or signals["has_home"])):
        page_type = "未登录页"
        login_status = "not_logged_in"
    else:
        login_status = "logged_in"
        if signals["has_search_promotion"]:
            page_type = "搜索推广"
        elif signals["has_data_overview"]:
            page_type = "数据概览"
        elif signals["has_data_report"]:
            page_type = "数据报告"
        elif signals["has_home"]:
            page_type = "百度营销首页"
        else:
            page_type = "未知页面"

    return {
        "url": url,
        "login_status": login_status,
        "page_type": page_type,
        "signals": signals,
    }


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def baidu_detect(config: dict[str, Any], root: Path, logger) -> dict[str, Any]:
    settings = get_browser_settings(config)
    reports_dir = root / "reports"
    report_path = reports_dir / "baidu_detect_report.json"
    text_path = reports_dir / "baidu_visible_text.txt"
    html_path = reports_dir / "baidu_debug.html"
    baidu_config = config.get("baidu", {})
    report: dict[str, Any] = {
        "mode": "baidu-detect",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": None,
        "browser": {
            "mode": settings["mode"],
            "cdp_endpoint": settings["cdp_endpoint"],
            "allow_edge_fallback": settings["allow_edge_fallback"],
            "headless": settings["headless"],
        },
        "connected": False,
        "url": None,
        "login_status": "unknown",
        "page_type": "未知页面",
        "signals": {},
        "outputs": {
            "report": str(report_path),
            "visible_text": str(text_path),
            "debug_html": str(html_path),
        },
        "errors": [],
    }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        report["errors"].append(f"Playwright 未安装，无法检测百度页面：{exc}")
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        _write_json(report_path, report)
        return report

    with sync_playwright() as playwright:
        try:
            context, page = launch_chrome_context(playwright, config, root)
        except BrowserLaunchError as exc:
            report["errors"].append(str(exc))
            report["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _write_json(report_path, report)
            logger.error("baidu-detect 连接 Chrome 失败：%s", exc)
            return report

        report["connected"] = True
        prepare_automation_page(page, config)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception:
            logger.warning("baidu-detect 等待 domcontentloaded 超时，继续读取当前页面。")
        url = page.url
        visible_text = page.locator("body").inner_text(timeout=10000)
        _write_text(text_path, visible_text)
        _write_debug_artifacts(
            root,
            page,
            {"exceptions": []},
            include_screenshot=bool(baidu_config.get("debug_screenshot", False)),
        )
        classification = classify_baidu_page(url, visible_text)
        report.update({
            "url": url,
            "login_status": classification["login_status"],
            "page_type": classification["page_type"],
            "signals": classification["signals"],
        })
        logger.info("baidu-detect 页面类型：%s，登录状态：%s，url=%s", report["page_type"], report["login_status"], url)

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    _write_json(report_path, report)
    return report
