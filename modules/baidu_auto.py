from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from modules.baidu_browser import _extract_selected_date_from_text
from modules.baidu_overview import baidu_prepare_overview
from modules.baidu_parser import extract_baidu_rows_from_visible_text, parse_baidu_table
from modules.baidu_validator import validate_baidu_account_data
from modules.validators import get_required_accounts, validate_baidu_report


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_baidu_auto_report(
    *,
    visible_text: str,
    config: dict[str, Any],
    period: str | None,
    rows: list[dict[str, Any]],
    parse_source: str,
    parse_debug: dict[str, Any] | None = None,
    visible_text_path: str | None = None,
) -> dict[str, Any]:
    parsed = parse_baidu_table(rows, config)
    selected_date = _extract_selected_date_from_text(visible_text) or date.today().isoformat()
    report: dict[str, Any] = {
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "date": selected_date,
        "period": period or "15点",
        "source": "baidu_auto_overview",
        "parse_source": parse_source,
        "text_table_row_count": len(rows) if parse_source == "visible_text" else 0,
        "dom_table_row_count": len(rows) if parse_source == "dom" else 0,
        "accounts": parsed.get("accounts", {}),
        "unknown_accounts": parsed.get("unknown_accounts", []),
        "ignored_unknown_accounts": parsed.get("ignored_unknown_accounts", []),
        "exceptions": parsed.get("exceptions", []),
        "errors": parsed.get("errors", []),
        "self_check": {
            "date_found": bool(_extract_selected_date_from_text(visible_text)),
            "selected_date_is_today": selected_date == date.today().isoformat(),
            "parsed_three_accounts": len(parsed.get("accounts", {})) == len(config.get("accounts", {})),
            "all_fields_numeric": not parsed.get("errors") and bool(parsed.get("accounts")),
            "wrote_excel": False,
        },
    }
    if parse_debug is not None:
        report["table_parse_debug"] = parse_debug
    if visible_text_path:
        report["exceptions"].append({"type": "visible_text_dump", "path": visible_text_path})
    if not report["self_check"]["selected_date_is_today"]:
        report["errors"].append(f"百度页面选择日期不是今天：页面日期 {selected_date}，今天 {date.today().isoformat()}")
    if not rows:
        report["errors"].append("未能从百度搜索推广页面识别到账户表格")
    report["errors"].extend(error for error in validate_baidu_report(report, get_required_accounts(config)) if error not in report["errors"])
    return report


def build_baidu_auto_report_from_visible_text(
    visible_text: str,
    config: dict[str, Any],
    period: str | None,
    visible_text_path: str | None = None,
) -> dict[str, Any]:
    rows = extract_baidu_rows_from_visible_text(visible_text)
    return _build_baidu_auto_report(
        visible_text=visible_text,
        config=config,
        period=period,
        rows=rows,
        parse_source="visible_text",
        visible_text_path=visible_text_path,
    )


def fetch_baidu_auto(
    config: dict[str, Any],
    root: Path,
    logger,
    period: str | None = None,
) -> dict[str, Any]:
    started_at = datetime.now().isoformat(timespec="seconds")
    baidu_config = config.get("baidu", {})
    output_path = _resolve_path(root, baidu_config.get("output_path", "reports/baidu_account_data.json"))
    validate_path = root / "reports" / "baidu_validate_report.json"
    visible_text_path = root / "reports" / "baidu_visible_text.txt"
    page_dump_path = root / "reports" / "baidu_page_text_dump.txt"
    candidate_path = root / "reports" / "baidu_table_candidates.json"
    parse_debug_path = root / "reports" / "baidu_table_parse_debug.json"

    prepare_report = baidu_prepare_overview(config, root, logger)
    if prepare_report.get("errors"):
        report = {
            "project_id": config.get("project_id"),
            "project_name": config.get("project_name"),
            "date": date.today().isoformat(),
            "period": period or "15点",
            "source": "baidu_auto_overview",
            "accounts": {},
            "exceptions": [{"type": "prepare_report", "path": str(root / "reports" / "baidu_prepare_overview_report.json")}],
            "errors": prepare_report.get("errors", []),
            "self_check": {"prepare_overview_passed": False, "wrote_excel": False},
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
        _write_json(output_path, report)
        validate_baidu_account_data(output_path, validate_path, get_required_accounts(config))
        logger.error("fetch-baidu-auto 中断：baidu-prepare-overview 未通过")
        return report

    visible_text = visible_text_path.read_text(encoding="utf-8") if visible_text_path.exists() else ""
    page_dump_path.parent.mkdir(parents=True, exist_ok=True)
    page_dump_path.write_text(visible_text, encoding="utf-8")

    parse_debug: dict[str, Any] = {}
    if parse_debug_path.exists():
        try:
            parse_debug = json.loads(parse_debug_path.read_text(encoding="utf-8"))
        except Exception:
            parse_debug = {}

    rows: list[dict[str, Any]] = []
    parse_source = str(parse_debug.get("extraction_method") or "visible_text")
    if candidate_path.exists():
        try:
            candidate_data = json.loads(candidate_path.read_text(encoding="utf-8"))
            rows = list(candidate_data.get("rows") or [])
            parse_source = str(candidate_data.get("source") or parse_source)
        except Exception:
            rows = []

    if not rows:
        rows = extract_baidu_rows_from_visible_text(visible_text)
        parse_source = "visible_text"
        _write_json(candidate_path, {"source": parse_source, "rows": rows, "row_count": len(rows)})

    report = _build_baidu_auto_report(
        visible_text=visible_text,
        config=config,
        period=period,
        rows=rows,
        parse_source=parse_source,
        parse_debug=parse_debug or None,
        visible_text_path=str(page_dump_path),
    )
    report["started_at"] = started_at
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    report["prepare_report"] = {
        "path": str(root / "reports" / "baidu_prepare_overview_report.json"),
        "passed": not prepare_report.get("errors"),
        "final_url": prepare_report.get("open_report", {}).get("final_url"),
        "final_page_type": prepare_report.get("open_report", {}).get("final_page_type"),
    }
    report["outputs"] = {
        "account_data": str(output_path),
        "validate_report": str(validate_path),
        "visible_text": str(visible_text_path),
        "page_text_dump": str(page_dump_path),
        "debug_html": str(root / "reports" / "baidu_debug.html"),
        "table_candidates": str(candidate_path),
        "table_parse_debug": str(parse_debug_path),
    }
    if candidate_path.exists() and report.get("errors"):
        report["exceptions"].append({"type": "table_candidates", "path": str(candidate_path)})

    from modules.baidu_unknown_accounts import build_unknown_baidu_accounts_report, write_unknown_baidu_accounts_report

    unknown_report = build_unknown_baidu_accounts_report(
        config,
        report,
        task="hourly",
        date=report.get("date"),
        period=report.get("period"),
    )
    unknown_path = write_unknown_baidu_accounts_report(root, unknown_report)
    if unknown_path:
        report["unknown_accounts_report"] = unknown_path

    _write_json(output_path, report)
    validate_report = validate_baidu_account_data(output_path, validate_path, get_required_accounts(config))
    logger.info(
        "fetch-baidu-auto 已输出：%s；百度自检：%s",
        output_path,
        "通过" if validate_report.get("passed") else "失败",
    )
    return report
