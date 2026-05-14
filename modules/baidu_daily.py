from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from modules.baidu_browser import _extract_selected_date_from_text, _write_debug_artifacts
from modules.baidu_overview import (
    CC_REPORT_URL,
    _auto_login_if_needed,
    _click_by_text_or_role,
    _goto_report_page,
    _read_page_text,
    is_search_promotion_overview,
    overview_text_has_account_table,
)
from modules.baidu_detector import classify_baidu_page
from modules.baidu_parser import extract_baidu_rows_from_visible_text, parse_baidu_table
from modules.browser_manager import BrowserLaunchError, launch_chrome_context
from modules.credential_manager import build_login_failure_message
from modules.text_normalizer import normalize_text
from modules.validators import get_required_accounts, validate_baidu_report


def default_daily_date(today: date | None = None) -> str:
    base = today or date.today()
    return (base - timedelta(days=1)).isoformat()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_baidu_daily_report_from_visible_text(
    visible_text: str,
    config: dict[str, Any],
    target_date: str,
    visible_text_path: str | None = None,
) -> dict[str, Any]:
    normalized_text = normalize_text(visible_text)
    rows = extract_baidu_rows_from_visible_text(visible_text)
    parsed = parse_baidu_table(rows, config)
    selected_date = _extract_selected_date_from_text(visible_text)
    report: dict[str, Any] = {
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "date": target_date,
        "target_date": target_date,
        "page_selected_date": selected_date,
        "source": "baidu_daily_report",
        "parse_source": "visible_text",
        "text_table_row_count": len(rows),
        "accounts": parsed.get("accounts", {}),
        "exceptions": parsed.get("exceptions", []),
        "errors": parsed.get("errors", []),
        "self_check": {
            "date_found": bool(selected_date),
            "selected_date_matches_target": selected_date == target_date,
            "is_search_promotion": "搜索推广" in normalized_text,
            "parsed_three_accounts": len(parsed.get("accounts", {})) == len(config.get("accounts", {})),
            "all_fields_numeric": not parsed.get("errors") and bool(parsed.get("accounts")),
            "wrote_excel": False,
        },
    }
    if visible_text_path:
        report["exceptions"].append({"type": "visible_text_dump", "path": visible_text_path})
    if selected_date != target_date:
        report["errors"].append(f"百度日报页面日期不匹配：目标 {target_date}，页面 {selected_date or '未识别'}")
    if "搜索推广" not in normalized_text:
        report["errors"].append("当前百度日报页面不是搜索推广数据，禁止作为日报百度数据使用")
    if not rows:
        report["errors"].append("未能从百度日报页面可见文本中识别账户表格")
    report["errors"].extend(error for error in validate_baidu_report(report, get_required_accounts(config)) if error not in report["errors"])
    return report


def _date_to_slash(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%Y/%m/%d")


def _visible_date(page) -> str | None:
    try:
        text = page.locator(".one-date-picker-title-text").first.inner_text(timeout=3000)
    except Exception:
        text = ""
    return _extract_selected_date_from_text(text)


def _select_report_date(page, target_date: str, logger) -> bool:
    current = _visible_date(page)
    if current == target_date:
        logger.info("百度日报 report 日期已是目标日期：%s", target_date)
        return True
    target_slash = _date_to_slash(target_date)
    logger.info("尝试选择百度日报日期：%s", target_date)
    try:
        page.locator(".one-date-picker-title").first.click(timeout=8000)
        page.wait_for_timeout(800)
    except Exception as exc:
        logger.error("打开百度日期选择器失败：%s", exc)
        return False

    year, month, day = target_date.split("-")
    click_result = None
    click_day_js = r"""
    ({year, month, day}) => {
      const monthText = `${year}\u5e74${Number(month)}\u6708`;
      const headers = Array.from(document.querySelectorAll('.one-date-picker-title-header-content'));
      const header = headers.find(h => (h.innerText || '').includes(monthText));
      if (!header) {
        return {ok: false, reason: 'month header not found', monthText, headers: headers.map(h => h.innerText || '')};
      }
      const panels = Array.from(document.querySelectorAll('.one-date-picker-range-item'));
      const panel = panels[headers.indexOf(header)];
      if (!panel) {
        return {ok: false, reason: 'month panel not found', monthText};
      }
      const cells = Array.from(panel.querySelectorAll('.one-date-picker-body-month-item'));
      const cell = cells.find(c => {
        const text = (c.innerText || '').trim();
        const cls = c.className || '';
        return text === String(Number(day)) && !cls.includes('read-only') && !cls.includes('disabled');
      });
      if (!cell) {
        return {ok: false, reason: 'day cell not found', monthText, day};
      }
      cell.click();
      return {
        ok: true,
        monthText,
        day,
        inputValues: Array.from(document.querySelectorAll('.one-date-picker-input input')).map(i => i.value)
      };
    }
    """
    for _ in range(2):
        try:
            click_result = page.evaluate(click_day_js, {"year": year, "month": month, "day": day})
            page.wait_for_timeout(600)
        except Exception as exc:
            click_result = {"ok": False, "reason": str(exc)}
            break
        if not click_result.get("ok"):
            break
    logger.info("百度日报日期格点击结果：%s", click_result)

    current = _visible_date(page)
    if current == target_date:
        logger.info("百度日报日期选择成功：%s", target_date)
        return True
    logger.error("百度日报日期选择后未匹配目标：目标=%s 当前=%s", target_date, current)
    return False


def _wait_report_data_without_refresh(page, config: dict[str, Any], logger) -> str:
    logger.info("等待百度日报 report 表格加载，不刷新页面以保留已选择日期。")
    deadline = datetime.now().timestamp() + int(config.get("baidu", {}).get("report_table_wait_seconds", 30))
    last_text = ""
    while datetime.now().timestamp() < deadline:
        last_text = _read_page_text(page)
        if overview_text_has_account_table(last_text, config):
            logger.info("百度日报 report 页面账户表格已加载。")
            return last_text
        try:
            page.wait_for_timeout(1000)
        except Exception:
            break
    logger.info("百度日报 report 页面账户表格等待结束，但未看到完整账户行。")
    return last_text


def _ensure_search_promotion_before_daily_date(page, config: dict[str, Any], logger) -> tuple[bool, str]:
    _goto_report_page(page, logger)
    visible_text = _read_page_text(page)
    classification = classify_baidu_page(page.url, visible_text)
    if is_search_promotion_overview(classification):
        logger.info("百度日报已处于 数据报告 → 搜索推广 页面，开始日期筛选。")
        return True, visible_text

    logger.info("百度日报当前不是搜索推广数据页，尝试切换到搜索推广。")
    clicked = _click_by_text_or_role(page, ["搜索推广"], logger)
    if not clicked:
        logger.error("百度日报未找到搜索推广入口。")
        return False, visible_text

    deadline = datetime.now().timestamp() + int(config.get("baidu", {}).get("report_table_wait_seconds", 30))
    while datetime.now().timestamp() < deadline:
        visible_text = _read_page_text(page)
        classification = classify_baidu_page(page.url, visible_text)
        if is_search_promotion_overview(classification):
            logger.info("百度日报已切换到搜索推广数据页。")
            return True, visible_text
        try:
            page.wait_for_timeout(1000)
        except Exception:
            break
    logger.error("百度日报切换搜索推广后未检测到搜索推广数据页。")
    return False, visible_text


def fetch_baidu_daily(
    config: dict[str, Any],
    root: Path,
    logger,
    target_date: str | None = None,
) -> dict[str, Any]:
    target_date = target_date or default_daily_date()
    started_at = datetime.now().isoformat(timespec="seconds")
    output_path = root / "reports" / "baidu_daily_data.json"
    validate_path = root / "reports" / "baidu_daily_validate_report.json"
    text_path = root / "reports" / "baidu_daily_page_text_dump.txt"
    candidates_path = root / "reports" / "baidu_daily_table_candidates.json"
    baidu_config = config.get("baidu", {})

    report: dict[str, Any] = {
        "date": target_date,
        "target_date": target_date,
        "source": "baidu_daily_report",
        "accounts": {},
        "exceptions": [],
        "errors": [],
        "self_check": {"wrote_excel": False},
        "started_at": started_at,
        "finished_at": None,
    }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        report["errors"].append(f"Playwright 未安装，无法抓取百度日报：{exc}")
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        _write_json(output_path, report)
        return report

    with sync_playwright() as playwright:
        try:
            context, page = launch_chrome_context(playwright, config, root)
        except BrowserLaunchError as exc:
            report["errors"].append(str(exc))
            report["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _write_json(output_path, report)
            return report
        page.bring_to_front()
        _goto_report_page(page, logger)

        # 百度登录状态守卫：确保当前浏览器登录的是本项目账号
        from modules.baidu_session import ensure_baidu_profile_session
        if not ensure_baidu_profile_session(root, config, page, logger, task="run-daily"):
            report["errors"].append("百度账号切换未完成或用户取消")
            report["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _write_json(output_path, report)
            return report

        visible_text = _read_page_text(page)
        if "login" in page.url or "cas.baidu.com" in page.url or "qingge.baidu.com" in page.url:
            if not _auto_login_if_needed(page, root, config, logger):
                report["errors"].append(build_login_failure_message(config))
                _write_debug_artifacts(root, page, report, include_screenshot=bool(baidu_config.get("debug_screenshot", False)))
                report["finished_at"] = datetime.now().isoformat(timespec="seconds")
                _write_json(output_path, report)
                return report
            _goto_report_page(page, logger)

        if not page.url.rstrip("/").startswith(CC_REPORT_URL):
            _goto_report_page(page, logger)
        ready_for_date, visible_text = _ensure_search_promotion_before_daily_date(page, config, logger)
        if not ready_for_date:
            report["errors"].append("百度日报未能进入搜索推广数据页，已中断日期筛选和抓数")
            _write_text(text_path, visible_text)
            _write_debug_artifacts(root, page, report, include_screenshot=bool(baidu_config.get("debug_screenshot", False)))
            report["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _write_json(output_path, report)
            return report
        if not _select_report_date(page, target_date, logger):
            report["errors"].append(f"百度日报日期选择失败：{target_date}")
        visible_text = _wait_report_data_without_refresh(page, config, logger)
        _write_text(text_path, visible_text)
        rows = extract_baidu_rows_from_visible_text(visible_text)
        _write_json(candidates_path, {"source": "visible_text", "rows": rows, "row_count": len(rows)})
        parsed_report = build_baidu_daily_report_from_visible_text(visible_text, config, target_date, str(text_path))
        report.update(parsed_report)
        report["started_at"] = started_at
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        report["outputs"] = {
            "daily_data": str(output_path),
            "validate_report": str(validate_path),
            "visible_text": str(text_path),
            "debug_html": str(root / "reports" / "baidu_debug.html"),
            "table_candidates": str(candidates_path),
        }
        if report.get("errors"):
            report["exceptions"].append({"type": "table_candidates", "path": str(candidates_path)})
            _write_debug_artifacts(root, page, report, include_screenshot=bool(baidu_config.get("debug_screenshot", False)))

    _write_json(output_path, report)
    validate = {
        "passed": not report.get("errors"),
        "date": target_date,
        "source_path": str(output_path),
        "expected_accounts": list(config.get("accounts", {}).keys()),
        "actual_accounts": list(report.get("accounts", {}).keys()),
        "errors": report.get("errors", []),
    }
    _write_json(validate_path, validate)
    logger.info("百度日报抓取报告已输出：%s；结果：%s", output_path, "通过" if validate["passed"] else "失败")
    return report
