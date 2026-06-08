from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from modules.baidu_browser import _extract_selected_date_from_text, _write_debug_artifacts
from modules.baidu_overview import (
    _auto_login_if_needed,
    _click_by_text_or_role,
    _goto_report_page,
    _read_page_text,
    is_search_promotion_overview,
    overview_text_has_account_table,
)
from modules.baidu_detector import classify_baidu_page
from modules.baidu_parser import extract_baidu_rows_from_visible_text, parse_baidu_table
from modules.browser_manager import BrowserLaunchError, launch_chrome_context, prepare_automation_page
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


def _metric_value(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return value
    text = str(value).strip()
    if text in {"", "-", "--"}:
        return 0
    cleaned = (
        text.replace(",", "")
        .replace("¥", "")
        .replace("￥", "")
        .replace("元", "")
        .replace("次", "")
        .replace(" ", "")
    )
    if "%" in cleaned:
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _field_from_header(header: Any) -> str | None:
    normalized = normalize_text(str(header or ""))
    if not normalized:
        return None
    if "占比" in normalized or "比例" in normalized or "%" in normalized:
        return None
    if "展现" in normalized:
        return "展现"
    if "点击" in normalized and "点击率" not in normalized:
        return "点击"
    if ("消费" in normalized or "花费" in normalized) and "消费占比" not in normalized:
        return "消费"
    return None


def _account_from_row(row: dict[str, Any]) -> str:
    for key, value in row.items():
        if str(key).startswith("__"):
            continue
        if "账户" in normalize_text(str(key)):
            return str(value or "").strip()
    return ""


def _total_metrics_from_rows(rows: list[dict[str, Any]]) -> dict[str, int | float]:
    for row in rows:
        account = normalize_text(_account_from_row(row))
        if account.startswith(normalize_text("总计-")):
            metrics: dict[str, int | float] = {}
            for key, value in row.items():
                field = _field_from_header(key)
                if not field:
                    continue
                number = _metric_value(value)
                if number is not None:
                    metrics[field] = number
            return metrics
    return {}


def _sum_account_metrics(accounts: dict[str, Any]) -> dict[str, int | float]:
    totals = {"展现": 0, "点击": 0, "消费": 0.0}
    for row in accounts.values():
        if not isinstance(row, dict):
            continue
        for field in totals:
            value = row.get(field)
            if isinstance(value, int | float) and not isinstance(value, bool):
                totals[field] += value
    return {
        "展现": int(totals["展现"]),
        "点击": int(totals["点击"]),
        "消费": round(float(totals["消费"]), 2),
    }


def _daily_report_signature(report: dict[str, Any], required_accounts: list[str]) -> tuple:
    accounts = report.get("accounts") or {}
    signature = []
    for account in required_accounts:
        row = accounts.get(account) or {}
        signature.append((
            account,
            row.get("展现"),
            row.get("点击"),
            round(float(row.get("消费")), 2) if isinstance(row.get("消费"), int | float) and not isinstance(row.get("消费"), bool) else row.get("消费"),
        ))
    return tuple(signature)


def validate_daily_baidu_snapshot(report: dict[str, Any], rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    required_accounts = get_required_accounts(config)
    errors = list(validate_baidu_report(report, required_accounts))
    total_metrics = _total_metrics_from_rows(rows)
    account_totals = _sum_account_metrics(report.get("accounts") or {})
    total_diff: dict[str, Any] = {}

    for field, total_value in total_metrics.items():
        account_value = account_totals.get(field)
        if account_value is None:
            continue
        tolerance = 0.01 if field == "消费" else 0
        diff = round(float(total_value) - float(account_value), 2)
        total_diff[field] = {
            "total_row": total_value,
            "account_sum": account_value,
            "diff": diff,
        }
        if abs(diff) > tolerance:
            errors.append(f"百度日报表格总计校验失败：{field} 总计行 {total_value}，账户合计 {account_value}，差额 {diff}")

    return {
        "passed": not errors,
        "errors": errors,
        "required_accounts": required_accounts,
        "actual_accounts": list((report.get("accounts") or {}).keys()),
        "signature": _daily_report_signature(report, required_accounts),
        "total_metrics": total_metrics,
        "account_totals": account_totals,
        "total_diff": total_diff,
    }


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
        "unknown_accounts": parsed.get("unknown_accounts", []),
        "ignored_unknown_accounts": parsed.get("ignored_unknown_accounts", []),
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
    if not config.get("baidu", {}).get("allow_missing_candidate_accounts"):
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


def _wait_stable_daily_report_snapshot(page, config: dict[str, Any], target_date: str, logger) -> dict[str, Any]:
    wait_seconds = int(config.get("baidu", {}).get("report_table_wait_seconds", 30))
    interval_ms = int(config.get("baidu", {}).get("daily_stability_interval_ms", 3000))
    required_accounts = get_required_accounts(config)
    deadline = datetime.now().timestamp() + wait_seconds
    last_signature = None
    last_snapshot: dict[str, Any] | None = None
    valid_snapshots: dict[tuple, dict[str, Any]] = {}
    attempts: list[dict[str, Any]] = []

    while datetime.now().timestamp() < deadline:
        visible_text = _read_page_text(page)
        rows = extract_baidu_rows_from_visible_text(visible_text)
        parsed_report = build_baidu_daily_report_from_visible_text(visible_text, config, target_date)
        validation = validate_daily_baidu_snapshot(parsed_report, rows, config)
        signature = validation["signature"]
        attempt = {
            "attempt": len(attempts) + 1,
            "row_count": len(rows),
            "signature": signature,
            "passed": validation["passed"],
            "errors": validation["errors"],
            "total_diff": validation["total_diff"],
        }
        attempts.append(attempt)

        repeated_snapshot = valid_snapshots.get(signature)
        if validation["passed"] and repeated_snapshot:
            logger.info("百度日报 report 表格数据已稳定：attempts=%s", len(attempts))
            return {
                **repeated_snapshot,
                "visible_text": visible_text,
                "rows": rows,
                "report": parsed_report,
                "validation": validation,
                "attempts": attempts,
                "stable": True,
            }

        if validation["passed"]:
            last_signature = signature
            last_snapshot = {
                "visible_text": visible_text,
                "rows": rows,
                "report": parsed_report,
                "validation": validation,
            }
            valid_snapshots.setdefault(signature, last_snapshot)
            logger.info("百度日报 report 首次读到有效快照，等待再次确认：accounts=%s", ",".join(required_accounts))
        else:
            last_signature = None
            last_snapshot = None
            logger.info("百度日报 report 快照未通过完整性校验：%s", "；".join(validation["errors"][:3]))

        try:
            page.wait_for_timeout(interval_ms)
        except Exception:
            break

    fallback = last_snapshot or {
        "visible_text": _read_page_text(page),
        "rows": [],
        "report": {
            "date": target_date,
            "target_date": target_date,
            "source": "baidu_daily_report",
            "accounts": {},
            "errors": ["百度日报表格数据未稳定"],
        },
        "validation": {"passed": False, "errors": ["百度日报表格数据未稳定"]},
    }
    return {
        **fallback,
        "attempts": attempts,
        "stable": False,
        "errors": ["百度日报表格数据在等待时间内未连续两次保持一致，已中断以避免写入未加载完整的数据"],
    }


def _ensure_search_promotion_before_daily_date(page, config: dict[str, Any], logger, root=None) -> tuple[bool, str]:
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


def _is_baidu_login_page(page) -> bool:
    url = (getattr(page, "url", "") or "").lower()
    return "login" in url or "cas.baidu.com" in url or "qingge.baidu.com" in url


def _prepare_baidu_daily_report_page(
    page,
    config: dict[str, Any],
    root: Path,
    logger,
    report: dict[str, Any],
) -> bool:
    # 日报通常在隔夜 session 下运行，进入报表页前先确认当前 Chrome 是本项目账号。
    from modules.baidu_session import ensure_baidu_profile_session

    session_result = ensure_baidu_profile_session(root, config, page, logger, task="run-daily")
    report["session_check"] = {
        "passed": session_result.get("passed"),
        "decision": session_result.get("decision"),
        "reason": session_result.get("reason"),
    }
    if not session_result.get("passed"):
        report["errors"].append("百度账号切换未完成或用户取消")
        return False

    if _goto_report_page(page, logger, root=root, config=config):
        return True

    if _is_baidu_login_page(page):
        logger.info("百度日报打开 report 后进入登录页，尝试自动登录后重试 report")
        if not _auto_login_if_needed(page, root, config, logger):
            report["errors"].append(build_login_failure_message(config))
            return False
        if _goto_report_page(page, logger, root=root, config=config):
            return True

    report["errors"].append("百度报告页打开失败，请检查网络或百度页面状态")
    return False


def _fetch_baidu_daily_single(
    config: dict[str, Any],
    root: Path,
    logger,
    target_date: str | None = None,
) -> dict[str, Any]:
    target_date = target_date or default_daily_date()
    started_at = datetime.now().isoformat(timespec="seconds")
    baidu_config = config.get("baidu", {})
    output_path = root / baidu_config.get("daily_output_path", "reports/baidu_daily_data.json")
    validate_path = root / baidu_config.get("daily_validate_output_path", "reports/baidu_daily_validate_report.json")
    text_path = root / baidu_config.get("daily_text_output_path", "reports/baidu_daily_page_text_dump.txt")
    candidates_path = root / baidu_config.get("daily_candidates_output_path", "reports/baidu_daily_table_candidates.json")

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
        prepare_automation_page(page, config)
        if not _prepare_baidu_daily_report_page(page, config, root, logger, report):
            _write_debug_artifacts(root, page, report, include_screenshot=bool(baidu_config.get("debug_screenshot", False)))
            report["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _write_json(output_path, report)
            return report
        ready_for_date, visible_text = _ensure_search_promotion_before_daily_date(page, config, logger, root=root)
        if not ready_for_date:
            report["errors"].append("百度日报未能进入搜索推广数据页，已中断日期筛选和抓数")
            _write_text(text_path, visible_text)
            _write_debug_artifacts(root, page, report, include_screenshot=bool(baidu_config.get("debug_screenshot", False)))
            report["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _write_json(output_path, report)
            return report
        if not _select_report_date(page, target_date, logger):
            report["errors"].append(f"百度日报日期选择失败：{target_date}")
        stable_snapshot = _wait_stable_daily_report_snapshot(page, config, target_date, logger)
        visible_text = stable_snapshot.get("visible_text", "")
        _write_text(text_path, visible_text)
        rows = stable_snapshot.get("rows") or extract_baidu_rows_from_visible_text(visible_text)
        _write_json(candidates_path, {"source": "visible_text", "rows": rows, "row_count": len(rows)})
        parsed_report = stable_snapshot.get("report") or build_baidu_daily_report_from_visible_text(visible_text, config, target_date, str(text_path))
        parsed_report.setdefault("exceptions", [])
        parsed_report["exceptions"].append({"type": "visible_text_dump", "path": str(text_path)})
        parsed_report["daily_stability_check"] = {
            "stable": bool(stable_snapshot.get("stable")),
            "attempts": stable_snapshot.get("attempts", []),
            "validation": stable_snapshot.get("validation", {}),
        }
        if not stable_snapshot.get("stable"):
            parsed_report.setdefault("errors", [])
            for error in stable_snapshot.get("errors", []):
                if error not in parsed_report["errors"]:
                    parsed_report["errors"].append(error)
        report.update(parsed_report)

        # 日报页面复核通过 → 写 browser_login_state
        if not report.get("errors") and len(report.get("accounts", {})) >= 1:
            from modules.baidu_session import mark_browser_login_success
            profile = config.get("baidu", {}).get("credential_profile") or config.get("baidu", {}).get("credential_project", "")
            if profile:
                mark_browser_login_success(root, profile, project_id=config.get("project_id"),
                                           project_name=config.get("project_name"), task="fetch-baidu-daily")

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

        # 写入未知百度账户报告
        from modules.baidu_unknown_accounts import build_unknown_baidu_accounts_report, write_unknown_baidu_accounts_report
        unknown_report = build_unknown_baidu_accounts_report(
            config, report, task="daily",
            date=report.get("date"), period=None,
        )
        unknown_path = write_unknown_baidu_accounts_report(root, unknown_report)
        if unknown_path:
            report["unknown_accounts_report"] = unknown_path

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


def fetch_baidu_daily(
    config: dict[str, Any],
    root: Path,
    logger,
    target_date: str | None = None,
) -> dict[str, Any]:
    from modules.baidu_multi_source import fetch_baidu_multi_source, is_multi_baidu_source

    if is_multi_baidu_source(config):
        return fetch_baidu_multi_source(
            config=config,
            root=root,
            logger=logger,
            task="daily",
            target_date=target_date or default_daily_date(),
            fetch_source_func=_fetch_baidu_daily_single,
        )
    return _fetch_baidu_daily_single(config=config, root=root, logger=logger, target_date=target_date)
