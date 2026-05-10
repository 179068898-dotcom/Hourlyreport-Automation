from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.validators import (
    BAIDU_ACCOUNT_FIELDS,
    DAILY_KST_FIELDS,
    KST_FIELDS,
    get_required_accounts,
    validate_merged_daily_data,
    validate_merged_hourly_data,
)


PERIOD_TO_REPORT = {
    "11": "11点",
    "11点": "11点",
    "11dian": "11点",
    "15": "15点",
    "15点": "15点",
    "15dian": "15点",
    "3": "15点",
    "3点": "15点",
    "18": "18点",
    "18点": "18点",
    "18dian": "18点",
    "6": "18点",
    "6点": "18点",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_report_path(root: Path, path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = root / path
    return path


def normalize_period_for_report(period: str | None) -> str:
    raw = str(period or "15点").strip().lower().replace(" ", "")
    if raw not in PERIOD_TO_REPORT:
        raise ValueError(f"不支持的时段：{period}，只支持 11点 / 15点 / 18点")
    return PERIOD_TO_REPORT[raw]


def _pick_date(baidu_report: dict[str, Any], kst_report: dict[str, Any]) -> str:
    return str(baidu_report.get("date") or kst_report.get("date") or "")


def build_merged_hourly_data(
    baidu_report: dict[str, Any],
    kst_report: dict[str, Any],
    period: str | None = None,
    baidu_source: str = "reports/baidu_account_data.json",
    kst_source: str = "reports/kst_dialog_data.json",
    required_accounts: list[str] | None = None,
) -> dict[str, Any]:
    """按固定三账户合并百度账户数据与快商通导出统计数据。"""
    report_period = normalize_period_for_report(period or baidu_report.get("period") or kst_report.get("period"))
    merged: dict[str, Any] = {
        "date": _pick_date(baidu_report, kst_report),
        "period": report_period,
        "source": {
            "baidu": baidu_source,
            "kst": kst_source,
        },
        "accounts": {},
    }

    baidu_accounts = baidu_report.get("accounts", {})
    kst_accounts = kst_report.get("accounts", {})
    inferred_accounts = list(dict.fromkeys([*baidu_accounts.keys(), *kst_accounts.keys()]))
    for account in (required_accounts or get_required_accounts(fallback_accounts=inferred_accounts)):
        row: dict[str, Any] = {}
        for field in BAIDU_ACCOUNT_FIELDS:
            row[field] = baidu_accounts.get(account, {}).get(field)
        for field in KST_FIELDS:
            row[field] = kst_accounts.get(account, {}).get(field)
        merged["accounts"][account] = row
    return merged


def build_merged_daily_data(
    baidu_report: dict[str, Any],
    kst_report: dict[str, Any],
    baidu_source: str = "reports/baidu_daily_data.json",
    kst_source: str = "reports/kst_daily_data.json",
    required_accounts: list[str] | None = None,
) -> dict[str, Any]:
    """按固定三账户合并百度日报数据与商务通日报导出统计数据。"""
    merged: dict[str, Any] = {
        "date": _pick_date(baidu_report, kst_report),
        "source": {
            "baidu": baidu_source,
            "kst": kst_source,
        },
        "accounts": {},
    }
    baidu_accounts = baidu_report.get("accounts", {})
    kst_accounts = kst_report.get("accounts", {})
    inferred_accounts = list(dict.fromkeys([*baidu_accounts.keys(), *kst_accounts.keys()]))
    for account in (required_accounts or get_required_accounts(fallback_accounts=inferred_accounts)):
        row: dict[str, Any] = {}
        for field in BAIDU_ACCOUNT_FIELDS:
            row[field] = baidu_accounts.get(account, {}).get(field)
        for field in DAILY_KST_FIELDS:
            row[field] = kst_accounts.get(account, {}).get(field)
        merged["accounts"][account] = row
    return merged


def merge_account_data(baidu_data: dict, kst_data: dict) -> dict:
    """兼容旧调用：只返回账户层合并数据。"""
    return build_merged_hourly_data(baidu_data, kst_data)["accounts"]


def merge_data_files(
    config: dict[str, Any],
    root: Path,
    logger,
    period: str | None = None,
) -> dict[str, Any]:
    reports_dir = root / "reports"
    baidu_path = _resolve_report_path(root, config.get("baidu", {}).get("output_path", "reports/baidu_account_data.json"))
    kst_path = _resolve_report_path(root, config.get("kst", {}).get("output_path", "reports/kst_dialog_data.json"))
    merged_path = reports_dir / "merged_hourly_data.json"
    validate_path = reports_dir / "merge_validate_report.json"

    errors: list[str] = []
    baidu_report: dict[str, Any] = {}
    kst_report: dict[str, Any] = {}
    if not baidu_path.exists():
        errors.append(f"找不到百度数据文件：{baidu_path}")
    else:
        baidu_report = _read_json(baidu_path)
    if not kst_path.exists():
        errors.append(f"找不到快商通数据文件：{kst_path}")
    else:
        kst_report = _read_json(kst_path)

    merged: dict[str, Any] | None = None
    if not errors:
        required_accounts = get_required_accounts(config)
        merged = build_merged_hourly_data(
            baidu_report,
            kst_report,
            period=period,
            baidu_source="reports/baidu_account_data.json",
            kst_source="reports/kst_dialog_data.json",
            required_accounts=required_accounts,
        )
        merged["project_id"] = config.get("project_id")
        merged["project_name"] = config.get("project_name")
        errors.extend(validate_merged_hourly_data(merged, baidu_report, kst_report, required_accounts))
        _write_json(merged_path, merged)

    validate_report = {
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "passed": not errors,
        "date": merged.get("date") if merged else None,
        "period": merged.get("period") if merged else normalize_period_for_report(period),
        "inputs": {
            "baidu": str(baidu_path),
            "kst": str(kst_path),
        },
        "outputs": {
            "merged": str(merged_path),
            "validate_report": str(validate_path),
        },
        "expected_accounts": get_required_accounts(config),
        "errors": errors,
    }
    _write_json(validate_path, validate_report)
    logger.info("合并校验报告已输出：%s；结果：%s", validate_path, "通过" if validate_report["passed"] else "失败")
    return {
        "merged": merged,
        "validate_report": validate_report,
        "outputs": {
            "merged": str(merged_path),
            "validate_report": str(validate_path),
        },
    }


def merge_daily_files(
    config: dict[str, Any],
    root: Path,
    logger,
    target_date: str | None = None,
) -> dict[str, Any]:
    reports_dir = root / "reports"
    baidu_path = reports_dir / "baidu_daily_data.json"
    kst_path = reports_dir / "kst_daily_data.json"
    merged_path = reports_dir / "merged_daily_data.json"
    validate_path = reports_dir / "daily_merge_validate_report.json"

    errors: list[str] = []
    baidu_report: dict[str, Any] = {}
    kst_report: dict[str, Any] = {}
    if not baidu_path.exists():
        errors.append(f"找不到百度日报数据文件：{baidu_path}")
    else:
        baidu_report = _read_json(baidu_path)
    if not kst_path.exists():
        errors.append(f"找不到商务通日报数据文件：{kst_path}")
    else:
        kst_report = _read_json(kst_path)

    if target_date:
        if baidu_report and baidu_report.get("date") != target_date:
            errors.append(f"百度日报日期不匹配：目标 {target_date}，文件 {baidu_report.get('date')}")
        if kst_report and kst_report.get("date") != target_date:
            errors.append(f"商务通日报日期不匹配：目标 {target_date}，文件 {kst_report.get('date')}")

    merged: dict[str, Any] | None = None
    if not errors:
        required_accounts = get_required_accounts(config)
        merged = build_merged_daily_data(baidu_report, kst_report, required_accounts=required_accounts)
        merged["project_id"] = config.get("project_id")
        merged["project_name"] = config.get("project_name")
        errors.extend(validate_merged_daily_data(merged, baidu_report, kst_report, required_accounts))
        _write_json(merged_path, merged)

    validate_report = {
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "passed": not errors,
        "date": merged.get("date") if merged else target_date or _pick_date(baidu_report, kst_report),
        "inputs": {
            "baidu": str(baidu_path),
            "kst": str(kst_path),
        },
        "outputs": {
            "merged": str(merged_path),
            "validate_report": str(validate_path),
        },
        "expected_accounts": get_required_accounts(config),
        "errors": errors,
    }
    _write_json(validate_path, validate_report)
    logger.info("日报合并校验报告已输出：%s；结果：%s", validate_path, "通过" if validate_report["passed"] else "失败")
    return {
        "merged": merged,
        "validate_report": validate_report,
        "outputs": {
            "merged": str(merged_path),
            "validate_report": str(validate_path),
        },
    }
