from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from modules.kst_export_parser import (
    SUPPORTED_SUFFIXES,
    _field_present,
    _parse_row_date,
    _resolve_path,
    read_export_rows,
)
from modules.kst_parser import (
    ACCOUNT_KEYS,
    REMARK_KEYS,
    SEARCH_WORD_KEYS,
    TAG_KEYS,
    TIME_KEYS,
    VISITOR_MESSAGE_KEYS,
    has_visitor_dialog,
    _effective_config,
    map_account_from_row,
    pick_value,
)
from modules.text_normalizer import normalize_for_display
from modules.validators import get_required_accounts


DAILY_KST_METRICS = ["总对话", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"]


def default_daily_kst_date(today: date | None = None) -> str:
    base = today or date.today()
    return (base - timedelta(days=1)).isoformat()


def classify_daily_dialog_by_tags(tags: str | None) -> dict[str, int]:
    text = normalize_for_display(tags)
    is_valid = any(key in text for key in ["转潜-有效", "有效-三句"])
    is_general = "有效-一般" in text
    return {
        "总对话": 1,
        "有效对话": 1 if is_valid else 0,
        "无效对话": 0 if is_valid or is_general else 1,
        "一般有效对话": 1 if is_general else 0,
        "有效转潜": 1 if "转潜-有效" in text else 0,
        "总转潜": 1 if "转潜-" in text else 0,
    }


def empty_daily_kst_account_row() -> dict[str, int]:
    return {metric: 0 for metric in DAILY_KST_METRICS}


def empty_daily_kst_accounts(accounts: list[str] | None = None) -> dict[str, dict[str, int]]:
    return {account: empty_daily_kst_account_row() for account in (accounts or [])}


def write_empty_kst_daily_result(
    config: dict[str, Any],
    root: Path,
    target_date: str | None = None,
    reason: str = "未找到 30 分钟内的商务通日报导出文件，按 0 对话处理",
) -> dict[str, Any]:
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    daily_out = reports_dir / "kst_daily_data.json"
    parse_out = reports_dir / "kst_daily_parse_report.json"
    unmatched_out = reports_dir / "kst_daily_unmatched_rows.json"
    details_out = reports_dir / "kst_daily_account_dialog_details.json"
    target = target_date or default_daily_kst_date()
    accounts = empty_daily_kst_accounts(get_required_accounts(config))
    summary = {
        "raw_rows": 0,
        "matched_rows": 0,
        "unmatched_rows": 0,
        "date_filtered_rows": 0,
        "skipped_no_visitor_messages": 0,
        "no_export_file": True,
    }
    daily_data = {
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "date": target,
        "source": "kst_daily_export",
        "export_file": "",
        "accounts": accounts,
        "summary": summary,
    }
    parse_report = {
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "date": target,
        "source": "kst_daily_export",
        "export_file": "",
        "passed": True,
        "field_info": {"headers": []},
        "supported_suffixes": sorted(SUPPORTED_SUFFIXES),
        "summary": summary,
        "date_filtered_rows": [],
        "warnings": [reason],
        "errors": [],
    }
    daily_out.write_text(json.dumps(daily_data, ensure_ascii=False, indent=2), encoding="utf-8")
    parse_out.write_text(json.dumps(parse_report, ensure_ascii=False, indent=2), encoding="utf-8")
    unmatched_out.write_text("[]", encoding="utf-8")
    details_out.write_text("{}", encoding="utf-8")
    return {
        "daily_data": daily_data,
        "parse_report": parse_report,
        "unmatched_rows": [],
        "account_dialog_details": {},
        "outputs": {
            "daily_data": str(daily_out),
            "parse_report": str(parse_out),
            "unmatched_rows": str(unmatched_out),
            "account_dialog_details": str(details_out),
        },
    }


def _inspect_daily_fields(rows: list[dict[str, Any]]) -> dict[str, Any]:
    headers = list(rows[0].keys()) if rows else []
    return {
        "headers": headers,
        "has_dialog_time": _field_present(headers, TIME_KEYS),
        "has_tag": _field_present(headers, TAG_KEYS),
        "has_remark": _field_present(headers, REMARK_KEYS),
        "has_account": _field_present(headers, ACCOUNT_KEYS),
        "has_search_word": _field_present(headers, SEARCH_WORD_KEYS),
        "has_visitor_messages": _field_present(headers, VISITOR_MESSAGE_KEYS),
    }


def _filter_rows_by_date(rows: list[dict[str, Any]], target_date: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    included = []
    excluded = []
    for index, row in enumerate(rows, start=1):
        row_date = _parse_row_date(pick_value(row, TIME_KEYS))
        if row_date == target_date:
            included.append(row)
        else:
            excluded.append({"row_index": index, "reason": f"非目标日报日期或日期无法识别：{row_date}", "row": row})
    return included, excluded


def _validate_daily_accounts(accounts: dict[str, dict[str, int]], expected_accounts: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    expected_list = expected_accounts or list(accounts.keys())
    actual = set(accounts)
    expected = set(expected_list)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"日报商务通账户不足 3 个，缺少：{', '.join(missing)}")
    if extra:
        errors.append(f"日报商务通账户多于 3 个：{', '.join(extra)}")
    for account in expected_list:
        row = accounts.get(account, {})
        for field in DAILY_KST_METRICS:
            value = row.get(field)
            if not isinstance(value, int) or value < 0:
                errors.append(f"账户 {account} 字段 {field} 不是非负整数：{value!r}")
        total = row.get("总对话", 0)
        valid = row.get("有效对话", 0)
        invalid = row.get("无效对话", 0)
        general_valid = row.get("一般有效对话", 0)
        valid_qian = row.get("有效转潜", 0)
        total_qian = row.get("总转潜", 0)
        if valid > total:
            errors.append(f"账户 {account} 有效对话大于总对话")
        if valid + general_valid + invalid < total:
            errors.append(f"账户 {account} 有效、一般与无效对话未覆盖总对话")
        if max(valid, general_valid) + invalid > total:
            errors.append(f"账户 {account} 无效对话与有效或一般对话存在重复")
        if valid_qian > valid:
            errors.append(f"账户 {account} 有效转潜大于有效对话")
        if total_qian > total:
            errors.append(f"账户 {account} 总转潜大于总对话")
    return errors


def aggregate_kst_daily_rows(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    config = _effective_config(config)
    expected_accounts = get_required_accounts(config)
    accounts = empty_daily_kst_accounts(expected_accounts)
    account_dialog_details: dict[str, list[dict[str, Any]]] = {account: [] for account in expected_accounts}
    unmatched_rows: list[dict[str, Any]] = []
    matched_rows = 0
    skipped_no_visitor_messages = 0

    for index, row in enumerate(rows, start=1):
        account, source = map_account_from_row(row, config)
        if not account:
            unmatched_rows.append({"row_index": index, "reason": source.get("reason", "无法归属账户"), "row": row, "source": source})
            continue
        tags = pick_value(row, TAG_KEYS)
        if has_visitor_dialog(row):
            counts = classify_daily_dialog_by_tags(None if tags is None else str(tags))
        else:
            counts = empty_daily_kst_account_row()
            skipped_no_visitor_messages += 1
        for metric, value in counts.items():
            accounts[account][metric] += value
        account_dialog_details[account].append({
            "row_index": index,
            "dialog_time": pick_value(row, TIME_KEYS),
            "promotion_id": source.get("promotion_id"),
            "source_type": source.get("source_type"),
            "tag": tags,
            "search_word": pick_value(row, SEARCH_WORD_KEYS),
            "visitor_messages": pick_value(row, VISITOR_MESSAGE_KEYS),
            "counts": counts,
        })
        matched_rows += 1

    errors = _validate_daily_accounts(accounts, expected_accounts)
    return {
        "accounts": accounts,
        "account_dialog_details": account_dialog_details,
        "summary": {
            "raw_rows": len(rows),
            "matched_rows": matched_rows,
            "unmatched_rows": len(unmatched_rows),
            "skipped_no_visitor_messages": skipped_no_visitor_messages,
        },
        "unmatched_rows": unmatched_rows,
        "errors": errors,
    }


def parse_kst_daily_file(file_path: str | Path, config: dict[str, Any], root: Path, target_date: str | None = None) -> dict[str, Any]:
    path = _resolve_path(root, file_path)
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    daily_out = reports_dir / "kst_daily_data.json"
    parse_out = reports_dir / "kst_daily_parse_report.json"
    unmatched_out = reports_dir / "kst_daily_unmatched_rows.json"
    details_out = reports_dir / "kst_daily_account_dialog_details.json"

    target = target_date or default_daily_kst_date()
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    field_info: dict[str, Any] = {"headers": []}
    date_filtered_rows: list[dict[str, Any]] = []

    if not path.exists():
        errors.append(f"商务通日报导出文件不存在：{path}")
    elif path.suffix.lower() not in SUPPORTED_SUFFIXES:
        errors.append(f"不支持的商务通日报导出文件类型：{path.suffix}")
    else:
        rows = read_export_rows(path)
        if not rows:
            errors.append("商务通日报导出文件为空")
        field_info = _inspect_daily_fields(rows)
        if rows and not field_info["has_dialog_time"]:
            errors.append("未识别到对话时间字段，无法按日报日期统计")
        if rows and not field_info["has_tag"]:
            errors.append("未识别到名片标签字段")
        if rows and not field_info["has_visitor_messages"]:
            errors.append("未识别到访客消息数/访客发送消息数/访客发送数字段，无法按访客发送数量大于等于 1 统计总对话")
        if rows and not (field_info["has_remark"] or field_info["has_account"]):
            errors.append("未识别到账户归属字段或备注说明推广 ID 字段")
        if rows and field_info["has_dialog_time"]:
            rows, date_filtered_rows = _filter_rows_by_date(rows, target)

    if errors:
        aggregate = {
            "accounts": empty_daily_kst_accounts(get_required_accounts(config)),
            "account_dialog_details": {},
            "summary": {
                "raw_rows": len(rows),
                "matched_rows": 0,
                "unmatched_rows": len(rows),
                "date_filtered_rows": len(date_filtered_rows),
                "skipped_no_visitor_messages": 0,
            },
            "unmatched_rows": [{"row_index": index, "reason": "解析前置校验失败", "row": row} for index, row in enumerate(rows, start=1)],
            "errors": errors,
        }
    else:
        aggregate = aggregate_kst_daily_rows(rows, config)
        aggregate["summary"]["raw_rows"] += len(date_filtered_rows)
        aggregate["summary"]["date_filtered_rows"] = len(date_filtered_rows)
        errors = aggregate.get("errors", [])

    daily_data = {
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "date": target,
        "source": "kst_daily_export",
        "export_file": str(path),
        "accounts": aggregate["accounts"],
        "summary": aggregate["summary"],
    }
    parse_report = {
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "date": target,
        "source": "kst_daily_export",
        "export_file": str(path),
        "passed": not errors,
        "field_info": field_info,
        "supported_suffixes": sorted(SUPPORTED_SUFFIXES),
        "summary": aggregate["summary"],
        "date_filtered_rows": date_filtered_rows,
        "errors": errors,
    }

    daily_out.write_text(json.dumps(daily_data, ensure_ascii=False, indent=2), encoding="utf-8")
    parse_out.write_text(json.dumps(parse_report, ensure_ascii=False, indent=2), encoding="utf-8")
    unmatched_out.write_text(json.dumps(aggregate.get("unmatched_rows", []), ensure_ascii=False, indent=2), encoding="utf-8")
    details_out.write_text(json.dumps(aggregate.get("account_dialog_details", {}), ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "daily_data": daily_data,
        "parse_report": parse_report,
        "unmatched_rows": aggregate.get("unmatched_rows", []),
        "account_dialog_details": aggregate.get("account_dialog_details", {}),
        "outputs": {
            "daily_data": str(daily_out),
            "parse_report": str(parse_out),
            "unmatched_rows": str(unmatched_out),
            "account_dialog_details": str(details_out),
        },
    }
