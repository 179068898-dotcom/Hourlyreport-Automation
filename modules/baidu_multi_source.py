from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from modules.validators import BAIDU_ACCOUNT_FIELDS, get_required_accounts, validate_baidu_report


FetchSourceFunc = Callable[..., dict[str, Any]]


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_baidu_sources(config: dict[str, Any]) -> list[dict[str, Any]]:
    sources = config.get("baidu_sources")
    if isinstance(sources, list) and sources:
        resolved: list[dict[str, Any]] = []
        for source in sources:
            item = dict(source)
            item.setdefault("required", True)
            item["accounts"] = list(item.get("accounts") or [])
            resolved.append(item)
        return resolved

    baidu = config.get("baidu") if isinstance(config.get("baidu"), dict) else {}
    profile = (
        baidu.get("credential_profile")
        or baidu.get("credential_project")
        or config.get("credential_profile")
        or ""
    )
    return [
        {
            "source_id": "default",
            "source_name": str(config.get("project_name") or config.get("project_id") or "default"),
            "credential_profile": str(profile),
            "accounts": list(config.get("accounts") or []),
            "required": True,
        }
    ]


def is_multi_baidu_source(config: dict[str, Any]) -> bool:
    return len(resolve_baidu_sources(config)) > 1


def build_source_runtime_config(config: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    source_config = deepcopy(config)
    source_id = str(source.get("source_id") or "default")
    profile = str(source.get("credential_profile") or "")
    accounts: dict[str, Any] = {}
    for account in source.get("accounts") or []:
        standard_name = str(account.get("standard_name") or "")
        if not standard_name:
            continue
        baidu_names = list(account.get("baidu_names") or [])
        aliases = []
        aliases.extend(baidu_names)
        aliases.append(account.get("excel_name", ""))
        aliases.append(standard_name)
        accounts[standard_name] = {
            "baidu_name": baidu_names[0] if baidu_names else standard_name,
            "baidu_names": baidu_names,
            "excel_name": account.get("excel_name", standard_name),
            "kst_ids": [str(item) for item in account.get("kst_ids", [])],
            "kst_names": list(account.get("kst_names", [])),
            "aliases": [str(alias) for alias in dict.fromkeys(aliases) if alias],
        }

    source_config["accounts"] = accounts
    source_config["baidu_source"] = {
        "source_id": source_id,
        "source_name": source.get("source_name") or source_id,
    }
    baidu = dict(source_config.get("baidu") or {})
    baidu["credential_profile"] = profile
    baidu["credential_project"] = profile
    baidu["output_path"] = f"reports/baidu_account_data_{source_id}.json"
    source_config["baidu"] = baidu
    return source_config


def _source_errors(source_id: str, report: dict[str, Any]) -> list[str]:
    errors = report.get("errors") or []
    if isinstance(errors, list):
        return [f"{source_id}: {error}" for error in errors]
    return [f"{source_id}: {errors}"]


def _with_source(item: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    result = dict(item)
    result["source_id"] = str(source.get("source_id") or "")
    result["source_name"] = str(source.get("source_name") or source.get("source_id") or "")
    return result


def _is_zero_metrics(row: dict[str, Any]) -> bool:
    for field in BAIDU_ACCOUNT_FIELDS:
        value = row.get(field, 0)
        if not isinstance(value, int | float) or isinstance(value, bool) or value != 0:
            return False
    return True


def aggregate_baidu_source_reports(
    config: dict[str, Any],
    source_reports: list[dict[str, Any]],
    period: str | None = None,
    target_date: str | None = None,
    output_source: str = "baidu_multi_source",
) -> dict[str, Any]:
    started_at = datetime.now().isoformat(timespec="seconds")
    required_accounts = get_required_accounts(config)
    accounts: dict[str, dict[str, int | float]] = {}
    errors: list[str] = []
    unknown_accounts: list[dict[str, Any]] = []
    ignored_unknown_accounts: list[dict[str, Any]] = []
    ignored_inactive_accounts: list[dict[str, Any]] = []
    skipped_unmapped_accounts: list[dict[str, Any]] = []

    for item in source_reports:
        source = {
            "source_id": item.get("source_id"),
            "source_name": item.get("source_name"),
        }
        report = item.get("report") or {}
        if report.get("errors"):
            errors.extend(_source_errors(str(item.get("source_id") or ""), report))
        for unknown in report.get("unknown_accounts") or []:
            unknown_accounts.append(_with_source(unknown, source))
        for ignored in report.get("ignored_unknown_accounts") or []:
            ignored_unknown_accounts.append(_with_source(ignored, source))

    if errors:
        return {
            "project_id": config.get("project_id"),
            "project_name": config.get("project_name"),
            "date": target_date or date.today().isoformat(),
            "period": period or "15点",
            "source": output_source,
            "accounts": {},
            "source_reports": source_reports,
            "unknown_accounts": unknown_accounts,
            "ignored_unknown_accounts": ignored_unknown_accounts,
            "ignored_inactive_accounts": ignored_inactive_accounts,
            "skipped_unmapped_accounts": skipped_unmapped_accounts,
            "errors": errors,
            "self_check": {"all_sources_passed": False, "wrote_excel": False},
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }

    report_date = target_date or ""
    for item in source_reports:
        report = item.get("report") or {}
        report_date = report_date or str(report.get("date") or "")
        for account, row in (report.get("accounts") or {}).items():
            if account not in required_accounts:
                detail = {
                    "account_name": account,
                    "展现": row.get("展现", 0) or 0,
                    "点击": row.get("点击", 0) or 0,
                    "消费": row.get("消费", 0) or 0,
                    "source_id": str(item.get("source_id") or ""),
                    "source_name": str(item.get("source_name") or item.get("source_id") or ""),
                    "reason": "候选账户不属于 Excel 实际写入账户",
                }
                if _is_zero_metrics(row):
                    ignored_inactive_accounts.append({**detail, "reason": "候选账户展点消均为 0，视为未启用"})
                else:
                    skipped_unmapped_accounts.append(detail)
                continue
            target = accounts.setdefault(account, {field: 0 for field in BAIDU_ACCOUNT_FIELDS})
            for field in BAIDU_ACCOUNT_FIELDS:
                value = row.get(field, 0)
                if isinstance(value, int | float) and not isinstance(value, bool):
                    target[field] += value

    result = {
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "date": report_date or date.today().isoformat(),
        "period": period or "15点",
        "source": output_source,
        "parse_source": "multi_source",
        "accounts": accounts,
        "source_reports": source_reports,
        "unknown_accounts": unknown_accounts,
        "ignored_unknown_accounts": ignored_unknown_accounts,
        "ignored_inactive_accounts": ignored_inactive_accounts,
        "skipped_unmapped_accounts": skipped_unmapped_accounts,
        "exceptions": [],
        "errors": [],
        "self_check": {
            "all_sources_passed": True,
            "source_count": len(source_reports),
            "parsed_accounts": len(accounts),
            "wrote_excel": False,
        },
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    result["errors"].extend(validate_baidu_report(result, required_accounts))
    return result


def fetch_baidu_multi_source(
    config: dict[str, Any],
    root: Path,
    logger,
    period: str | None,
    fetch_source_func: FetchSourceFunc,
) -> dict[str, Any]:
    sources = resolve_baidu_sources(config)
    source_reports: list[dict[str, Any]] = []
    for source in sources:
        source_id = str(source.get("source_id") or "default")
        logger.info("开始读取百度来源：%s", source_id)
        source_config = build_source_runtime_config(config, source)
        try:
            report = fetch_source_func(config=source_config, root=root, logger=logger, period=period)
        except Exception as exc:
            report = {"accounts": {}, "errors": [str(exc)]}
        source_reports.append(
            {
                "source_id": source_id,
                "source_name": str(source.get("source_name") or source_id),
                "credential_profile": str(source.get("credential_profile") or ""),
                "accounts": [str(item.get("standard_name") or "") for item in source.get("accounts") or []],
                "report": report,
            }
        )

    report = aggregate_baidu_source_reports(config, source_reports, period=period)
    multi_path = root / "reports" / "baidu_multi_source_report.json"
    account_path = root / "reports" / "baidu_account_data.json"
    report["outputs"] = {
        "multi_source_report": str(multi_path),
        "account_data": str(account_path),
    }
    _write_json(multi_path, report)
    _write_json(account_path, report)
    logger.info("多百度来源聚合已输出：%s；统一百度报告：%s", multi_path, account_path)
    return report
