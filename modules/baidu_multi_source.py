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


def build_source_runtime_config(config: dict[str, Any], source: dict[str, Any], task: str = "hourly") -> dict[str, Any]:
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
    baidu["allow_missing_candidate_accounts"] = True
    if task == "daily":
        baidu["daily_output_path"] = f"reports/baidu_daily_data_{source_id}.json"
        baidu["daily_validate_output_path"] = f"reports/baidu_daily_validate_report_{source_id}.json"
        baidu["daily_text_output_path"] = f"reports/baidu_daily_page_text_dump_{source_id}.txt"
        baidu["daily_candidates_output_path"] = f"reports/baidu_daily_table_candidates_{source_id}.json"
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


def build_cost_validation(source_total_cost_sum: float, final_total_cost: float, tolerance: float = 0.01) -> dict[str, Any]:
    source_total = round(float(source_total_cost_sum), 2)
    final_total = round(float(final_total_cost), 2)
    diff = round(source_total - final_total, 2)
    passed = abs(diff) <= tolerance
    errors = [] if passed else [f"多百度来源聚合消费校验失败：来源合计 {source_total}，最终合计 {final_total}，差额 {diff}"]
    return {
        "passed": passed,
        "source_total_cost_sum": source_total,
        "final_total_cost": final_total,
        "diff": diff,
        "cost_validation_passed": passed,
        "errors": errors,
    }


def _metric(value: Any) -> int | float:
    return value if isinstance(value, int | float) and not isinstance(value, bool) else 0


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    if not rows:
        return ["无", ""]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("--" if index == 0 else "--:" for index in range(len(headers))) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    lines.append("")
    return lines


def build_baidu_multi_source_markdown(report: dict[str, Any]) -> str:
    required_accounts = set((report.get("accounts") or {}).keys())
    source_rows: list[list[Any]] = []
    for source in report.get("source_reports") or []:
        source_report = source.get("report") or {}
        source_id = source.get("source_id")
        write_count = sum(1 for account in source_report.get("accounts", {}) if account in required_accounts)
        source_rows.append([
            source.get("source_name") or source_id or "",
            "失败" if source_report.get("errors") else "成功",
            len(source_report.get("accounts") or {}),
            write_count,
            sum(1 for item in report.get("ignored_inactive_accounts", []) if item.get("source_id") == source_id),
            sum(1 for item in report.get("skipped_unmapped_accounts", []) if item.get("source_id") == source_id),
            len(source_report.get("unknown_accounts") or []),
        ])

    final_rows: list[list[Any]] = []
    for account, totals in (report.get("accounts") or {}).items():
        details = []
        for source in report.get("source_reports") or []:
            row = (source.get("report") or {}).get("accounts", {}).get(account)
            if row:
                details.append(
                    f"{source.get('source_name')}: 展现 {_metric(row.get('展现'))} / 点击 {_metric(row.get('点击'))} / 消费 {_metric(row.get('消费'))}"
                )
        final_rows.append([account, _metric(totals.get("展现")), _metric(totals.get("点击")), _metric(totals.get("消费")), "；".join(details) or "无"])

    def diagnostic_rows(name: str) -> list[list[Any]]:
        return [
            [item.get("source_name", ""), item.get("account_name", ""), _metric(item.get("展现")), _metric(item.get("点击")), _metric(item.get("消费")), item.get("reason", "")]
            for item in report.get(name) or []
        ]

    lines = [
        "# 多百度来源抓数报告",
        "",
        f"项目：{report.get('project_name') or report.get('project_id') or ''}",
        f"任务：{'日报' if report.get('task') == 'daily' else '小时报'}",
        f"日期：{report.get('date') or ''}",
        f"时段：{report.get('period') or '无'}",
        f"执行时间：{report.get('finished_at') or report.get('started_at') or ''}",
        f"百度来源数：{len(report.get('source_reports') or [])}",
        f"最终写入账户数：{len(report.get('accounts') or {})}",
        f"消费校验：来源合计 {report.get('source_total_cost_sum', 0)} / 最终合计 {report.get('final_total_cost', 0)} / 差额 {report.get('diff', 0)}",
        "",
        "## 来源摘要",
        "",
    ]
    lines.extend(_markdown_table(["来源", "状态", "抓到账户数", "写入账户数", "忽略未启用", "跳过未映射", "unknown"], source_rows))
    lines.extend(["## 最终写入账户", ""])
    lines.extend(_markdown_table(["账户", "展现", "点击", "消费", "来源明细"], final_rows))
    lines.extend(["## 被忽略的未启用账户", ""])
    lines.extend(_markdown_table(["来源", "账户", "展现", "点击", "消费", "原因"], diagnostic_rows("ignored_inactive_accounts")))
    lines.extend(["## 被跳过的未映射账户", ""])
    lines.extend(_markdown_table(["来源", "账户", "展现", "点击", "消费", "原因"], diagnostic_rows("skipped_unmapped_accounts")))
    lines.extend(["## unknown_accounts", ""])
    lines.extend(_markdown_table(["来源", "账户", "展现", "点击", "消费", "原因"], diagnostic_rows("unknown_accounts")))
    return "\n".join(lines).rstrip() + "\n"


def aggregate_baidu_source_reports(
    config: dict[str, Any],
    source_reports: list[dict[str, Any]],
    period: str | None = None,
    target_date: str | None = None,
    output_source: str = "baidu_multi_source",
    task: str = "hourly",
) -> dict[str, Any]:
    started_at = datetime.now().isoformat(timespec="seconds")
    required_accounts = get_required_accounts(config)
    accounts: dict[str, dict[str, int | float]] = {}
    errors: list[str] = []
    unknown_accounts: list[dict[str, Any]] = []
    ignored_unknown_accounts: list[dict[str, Any]] = []
    ignored_inactive_accounts: list[dict[str, Any]] = []
    skipped_unmapped_accounts: list[dict[str, Any]] = []
    report_period = None if task == "daily" else period or "15点"
    report_date = target_date or ""

    for item in source_reports:
        source = {
            "source_id": item.get("source_id"),
            "source_name": item.get("source_name"),
        }
        report = item.get("report") or {}
        if report.get("errors"):
            errors.extend(_source_errors(str(item.get("source_id") or ""), report))
        report["unknown_accounts"] = [_with_source(unknown, source) for unknown in report.get("unknown_accounts") or []]
        report["ignored_unknown_accounts"] = [_with_source(ignored, source) for ignored in report.get("ignored_unknown_accounts") or []]
        unknown_accounts.extend(report["unknown_accounts"])
        ignored_unknown_accounts.extend(report["ignored_unknown_accounts"])

    if errors:
        return {
            "project_id": config.get("project_id"),
            "project_name": config.get("project_name"),
            "task": task,
            "multi_source": True,
            "date": target_date or date.today().isoformat(),
            **({"target_date": target_date or date.today().isoformat()} if task == "daily" else {}),
            "period": report_period,
            "source": output_source,
            "accounts": {},
            "source_reports": source_reports,
            "unknown_accounts": unknown_accounts,
            "ignored_unknown_accounts": ignored_unknown_accounts,
            "ignored_inactive_accounts": ignored_inactive_accounts,
            "skipped_unmapped_accounts": skipped_unmapped_accounts,
            "source_total_cost_sum": 0,
            "final_total_cost": 0,
            "diff": 0,
            "cost_validation_passed": False,
            "errors": errors,
            "self_check": {"all_sources_passed": False, "wrote_excel": False},
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }

    source_total_cost_sum = 0.0
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
            source_total_cost_sum += float(_metric(row.get("消费")))

    final_total_cost = sum(float(_metric(row.get("消费"))) for row in accounts.values())
    cost_validation = build_cost_validation(source_total_cost_sum, final_total_cost)
    result = {
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "task": task,
        "multi_source": True,
        "date": report_date or date.today().isoformat(),
        **({"target_date": report_date or date.today().isoformat()} if task == "daily" else {}),
        "period": report_period,
        "source": output_source,
        "parse_source": "multi_source",
        "accounts": accounts,
        "source_reports": source_reports,
        "unknown_accounts": unknown_accounts,
        "ignored_unknown_accounts": ignored_unknown_accounts,
        "ignored_inactive_accounts": ignored_inactive_accounts,
        "skipped_unmapped_accounts": skipped_unmapped_accounts,
        "source_total_cost_sum": cost_validation["source_total_cost_sum"],
        "final_total_cost": cost_validation["final_total_cost"],
        "diff": cost_validation["diff"],
        "cost_validation_passed": cost_validation["cost_validation_passed"],
        "exceptions": [],
        "errors": list(cost_validation["errors"]),
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
    period: str | None = None,
    fetch_source_func: FetchSourceFunc | None = None,
    task: str = "hourly",
    target_date: str | None = None,
) -> dict[str, Any]:
    if fetch_source_func is None:
        raise ValueError("多百度来源抓数缺少 source 抓取函数")
    sources = resolve_baidu_sources(config)
    source_reports: list[dict[str, Any]] = []
    for source in sources:
        source_id = str(source.get("source_id") or "default")
        logger.info("开始读取百度来源：%s", source_id)
        source_config = build_source_runtime_config(config, source, task=task)
        try:
            if task == "daily":
                report = fetch_source_func(config=source_config, root=root, logger=logger, target_date=target_date)
            else:
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

    output_source = "baidu_daily_report" if task == "daily" else "baidu_multi_source"
    report = aggregate_baidu_source_reports(
        config,
        source_reports,
        period=period,
        target_date=target_date,
        output_source=output_source,
        task=task,
    )
    multi_path = root / "reports" / "baidu_multi_source_report.json"
    markdown_path = root / "reports" / "baidu_multi_source_report.md"
    account_path = root / "reports" / ("baidu_daily_data.json" if task == "daily" else "baidu_account_data.json")
    report["outputs"] = {
        "multi_source_report": str(multi_path),
        "multi_source_markdown": str(markdown_path),
        "daily_data" if task == "daily" else "account_data": str(account_path),
    }
    if task == "daily":
        validate_path = root / "reports" / "baidu_daily_validate_report.json"
        report["outputs"]["validate_report"] = str(validate_path)
        _write_json(validate_path, {
            "passed": not report.get("errors"),
            "date": report.get("date"),
            "source_path": str(account_path),
            "expected_accounts": get_required_accounts(config),
            "actual_accounts": list(report.get("accounts", {}).keys()),
            "errors": report.get("errors", []),
        })
    _write_json(multi_path, report)
    _write_json(account_path, report)
    markdown_path.write_text(build_baidu_multi_source_markdown(report), encoding="utf-8")
    logger.info("多百度来源聚合已输出：%s；统一百度%s报告：%s", multi_path, "日报" if task == "daily" else "", account_path)
    return report
