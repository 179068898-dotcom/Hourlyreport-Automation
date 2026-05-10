from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.validators import get_required_accounts


EXPECTED_ACCOUNTS: list[str] = []
REQUIRED_FIELDS = ["展现", "点击", "消费"]


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _extract_date_from_text(text: str) -> str | None:
    match = re.search(r"\b(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\b", text)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _find_visible_dump_date(source: dict[str, Any]) -> tuple[str | None, str | None]:
    for item in source.get("exceptions", []):
        if item.get("type") != "visible_text_dump":
            continue
        path_text = item.get("path")
        if not path_text:
            continue
        path = Path(path_text)
        if not path.exists():
            return None, str(path)
        return _extract_date_from_text(path.read_text(encoding="utf-8", errors="ignore")), str(path)
    return None, None


def validate_baidu_account_data(source_path: Path, output_path: Path, expected_accounts: list[str] | None = None) -> dict[str, Any]:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    accounts = source.get("accounts", {})
    actual_accounts = list(accounts.keys())
    errors: list[str] = []
    warnings: list[str] = []
    expected = expected_accounts or list(source.get("expected_accounts") or get_required_accounts())

    missing_accounts = [name for name in expected if name not in accounts]
    extra_accounts = [name for name in actual_accounts if name not in expected]
    if missing_accounts:
        errors.append(f"缺少标准账户：{', '.join(missing_accounts)}")
    if extra_accounts:
        errors.append(f"存在非标准账户：{', '.join(extra_accounts)}")

    account_checks: dict[str, Any] = {}
    for account_name in expected:
        data = accounts.get(account_name, {})
        item: dict[str, Any] = {
            "exists": account_name in accounts,
            "source_account": data.get("source_account"),
            "fields_present": {},
            "field_types": {},
            "field_values": {},
            "errors": [],
        }

        for field in REQUIRED_FIELDS:
            value = data.get(field)
            present = field in data and value not in (None, "")
            item["fields_present"][field] = present
            item["field_values"][field] = value

            if not present:
                message = f"账户 {account_name} 缺少字段或字段为空：{field}"
                item["field_types"][field] = type(value).__name__
                item["errors"].append(message)
                errors.append(message)
                continue

            if field in ["展现", "点击"]:
                item["field_types"][field] = "integer" if _is_integer(value) else type(value).__name__
                if not _is_integer(value):
                    message = f"账户 {account_name} 字段 {field} 不是整数：{value!r}"
                    item["errors"].append(message)
                    errors.append(message)
                    continue
            else:
                item["field_types"][field] = "number" if _is_number(value) else type(value).__name__
                if not _is_number(value):
                    message = f"账户 {account_name} 字段 {field} 不是数字：{value!r}"
                    item["errors"].append(message)
                    errors.append(message)
                    continue

            if value < 0:
                message = f"账户 {account_name} 字段 {field} 为负数：{value}"
                item["errors"].append(message)
                errors.append(message)

        account_checks[account_name] = item

    source_errors = source.get("errors") or []
    if source_errors:
        errors.extend(f"源报告已有错误：{error}" for error in source_errors)

    visible_dump_date, visible_dump_path = _find_visible_dump_date(source)
    if visible_dump_date and source.get("date") != visible_dump_date:
        errors.append(f"百度页面实际日期与源报告日期不一致：页面实际日期 {visible_dump_date}，源报告日期 {source.get('date')}")

    ignored_summary_rows = [
        item for item in source.get("exceptions", [])
        if item.get("reason") == "无法映射账户" and item.get("row", {}).get("账户") == "总计-3"
    ]
    if ignored_summary_rows:
        warnings.append("源报告包含总计行，总计-3 已作为非账户行忽略，不影响三个账户校验。")

    checks = {
        "exactly_three_standard_accounts": not missing_accounts and not extra_accounts and len(actual_accounts) == 3,
        "all_source_accounts_present": all(
            bool(accounts.get(name, {}).get("source_account"))
            for name in expected
        ),
        "all_required_fields_present": all(
            account_checks[name]["fields_present"].get(field)
            for name in expected
            for field in REQUIRED_FIELDS
        ),
        "impressions_and_clicks_are_integers": all(
            _is_integer(accounts.get(name, {}).get(field))
            for name in expected
            for field in ["展现", "点击"]
        ),
        "costs_are_numbers": all(
            _is_number(accounts.get(name, {}).get("消费"))
            for name in expected
        ),
        "no_empty_non_numeric_or_negative_values": not any(
            account_checks[name]["errors"]
            for name in expected
        ),
        "source_report_has_no_errors": not source_errors,
        "source_date_matches_visible_dump": not visible_dump_date or source.get("date") == visible_dump_date,
    }

    validate_report = {
        "validated_at": datetime.now().isoformat(timespec="seconds"),
        "source_path": str(source_path),
        "source_date": source.get("date"),
        "visible_dump_date": visible_dump_date,
        "visible_dump_path": visible_dump_path,
        "source_period": source.get("period"),
        "passed": len(errors) == 0,
        "checks": checks,
        "expected_accounts": expected,
        "actual_accounts": actual_accounts,
        "account_checks": account_checks,
        "warnings": warnings,
        "errors": errors,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(validate_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return validate_report


def print_baidu_validate_summary(validate_report: dict[str, Any]) -> None:
    print("百度数据自检完成")
    print(f"总体结果：{'通过' if validate_report.get('passed') else '失败'}")
    print(f"报告日期：{validate_report.get('source_date')}，时段：{validate_report.get('source_period')}")
    print(f"账户数量：{len(validate_report.get('actual_accounts', []))} 个")
    for account_name in validate_report.get("expected_accounts", EXPECTED_ACCOUNTS):
        item = validate_report["account_checks"].get(account_name, {})
        values = item.get("field_values", {})
        print(
            f"{account_name}：展现={values.get('展现')}，"
            f"点击={values.get('点击')}，消费={values.get('消费')}，"
            f"来源账户={item.get('source_account')}"
        )
    for warning in validate_report.get("warnings", []):
        print(f"提示：{warning}")
    for error in validate_report.get("errors", []):
        print(f"错误：{error}")
