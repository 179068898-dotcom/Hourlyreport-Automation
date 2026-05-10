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
    if path.is_absolute():
        return path
    return root / path


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_baidu_auto_report_from_visible_text(
    visible_text: str,
    config: dict[str, Any],
    period: str | None,
    visible_text_path: str | None = None,
) -> dict[str, Any]:
    rows = extract_baidu_rows_from_visible_text(visible_text)
    parsed = parse_baidu_table(rows, config)
    selected_date = _extract_selected_date_from_text(visible_text) or date.today().isoformat()
    report: dict[str, Any] = {
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "date": selected_date,
        "period": period or "15点",
        "source": "baidu_auto_overview",
        "parse_source": "visible_text",
        "text_table_row_count": len(rows),
        "accounts": parsed.get("accounts", {}),
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
    if visible_text_path:
        report["exceptions"].append({"type": "visible_text_dump", "path": visible_text_path})
    if not report["self_check"]["selected_date_is_today"]:
        report["errors"].append(f"百度页面选择日期不是今天：页面日期 {selected_date}，今天 {date.today().isoformat()}")
    if not rows:
        report["errors"].append("未能从百度搜索推广页面可见文本中识别账户表格")
    report["errors"].extend(error for error in validate_baidu_report(report, get_required_accounts(config)) if error not in report["errors"])
    return report


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

    prepare_report = baidu_prepare_overview(config, root, logger)
    if prepare_report.get("errors"):
        report = {
            "project_id": config.get("project_id"),
            "project_name": config.get("project_name"),
            "date": date.today().isoformat(),
            "period": period or "15点",
            "source": "baidu_auto_overview",
            "accounts": {},
            "exceptions": [
                {"type": "prepare_report", "path": str(root / "reports" / "baidu_prepare_overview_report.json")}
            ],
            "errors": prepare_report.get("errors", []),
            "self_check": {"prepare_overview_passed": False, "wrote_excel": False},
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
        _write_json(output_path, report)
        validate_baidu_account_data(output_path, validate_path, get_required_accounts(config))
        logger.error("fetch-baidu-auto 中断：baidu-prepare-overview 未通过。")
        return report

    visible_text = visible_text_path.read_text(encoding="utf-8") if visible_text_path.exists() else ""
    page_dump_path.parent.mkdir(parents=True, exist_ok=True)
    page_dump_path.write_text(visible_text, encoding="utf-8")
    rows = extract_baidu_rows_from_visible_text(visible_text)
    _write_json(candidate_path, {"source": "visible_text", "rows": rows, "row_count": len(rows)})

    report = build_baidu_auto_report_from_visible_text(
        visible_text,
        config,
        period,
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
    }
    if candidate_path.exists() and report.get("errors"):
        report["exceptions"].append({"type": "table_candidates", "path": str(candidate_path)})
    _write_json(output_path, report)
    validate_report = validate_baidu_account_data(output_path, validate_path, get_required_accounts(config))
    logger.info(
        "fetch-baidu-auto 已输出：%s；百度自检：%s",
        output_path,
        "通过" if validate_report.get("passed") else "失败",
    )
    return report
