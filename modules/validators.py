from __future__ import annotations

from typing import Any


REQUIRED_ACCOUNTS: list[str] = []
REQUIRED_BAIDU_FIELDS = ["日期", "时段", "展现", "点击", "消费"]
KST_FIELDS = ["总对话", "有效对话", "一般有效", "有效转潜", "总转潜"]
DAILY_KST_FIELDS = ["总对话", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"]
BAIDU_ACCOUNT_FIELDS = ["展现", "点击", "消费"]
MERGED_FIELDS = BAIDU_ACCOUNT_FIELDS + KST_FIELDS
MERGED_DAILY_FIELDS = BAIDU_ACCOUNT_FIELDS + DAILY_KST_FIELDS


def get_required_accounts(config: dict[str, Any] | None = None, fallback_accounts: list[str] | None = None) -> list[str]:
    accounts = (config or {}).get("accounts")
    if isinstance(accounts, dict) and accounts:
        return list(accounts.keys())
    if isinstance(accounts, list) and accounts:
        return [str(account.get("standard_name")) for account in accounts if account.get("standard_name")]
    try:
        from modules.project_config import load_default_runtime_config

        runtime = load_default_runtime_config()
        runtime_accounts = runtime.get("accounts")
        if isinstance(runtime_accounts, dict) and runtime_accounts:
            return list(runtime_accounts.keys())
    except Exception:
        pass
    if fallback_accounts:
        return list(fallback_accounts)
    return list(REQUIRED_ACCOUNTS)


def validate_excel_report(report: dict[str, Any], required_accounts: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    if not report.get("sheet_found"):
        errors.append("未找到目标 sheet")
        return errors

    accounts = report.get("accounts", {})
    for account in (required_accounts or REQUIRED_ACCOUNTS):
        if account not in accounts or not accounts[account].get("found"):
            errors.append(f"未识别到账户区域：{account}")
            continue
        fields = accounts[account].get("fields", {})
        for field in REQUIRED_BAIDU_FIELDS:
            if field not in fields or not fields[field].get("found"):
                errors.append(f"账户 {account} 未找到字段：{field}")
    return errors


def validate_excel_report_v2(report: dict[str, Any], required_accounts: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    if not report.get("sheet_found"):
        errors.append("未找到目标 sheet")
        return errors

    global_fields = report.get("global_fields", {})
    for field in ["日期", "时段"]:
        if field not in global_fields or not global_fields[field].get("found"):
            errors.append(f"未找到全局字段：{field}")

    accounts = report.get("accounts", {})
    for account in (required_accounts or REQUIRED_ACCOUNTS):
        if account not in accounts or not accounts[account].get("found"):
            errors.append(f"未识别到账户区域：{account}")
            continue
        fields = accounts[account].get("fields", {})
        for field in BAIDU_ACCOUNT_FIELDS:
            if field not in fields or not fields[field].get("found"):
                errors.append(f"账户 {account} 未找到字段：{field}")
    return errors


def validate_kst_counts(row: dict[str, int]) -> list[str]:
    errors = []
    total = int(row.get("总对话", 0) or 0)
    valid = int(row.get("有效对话", 0) or 0)
    general_valid = int(row.get("一般有效", 0) or 0)
    valid_lead = int(row.get("有效转潜", 0) or 0)
    total_lead = int(row.get("总转潜", 0) or 0)
    if valid > total:
        errors.append("有效对话不能大于总对话")
    if general_valid > total:
        errors.append("一般有效不能大于总对话")
    if valid_lead > valid:
        errors.append("有效转潜不能大于有效对话")
    if total_lead > total:
        errors.append("总转潜不能大于总对话")
    return errors


def validate_kst_report(report: dict[str, Any], required_accounts: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    accounts = report.get("accounts", {})
    found = set(accounts.keys())
    expected = required_accounts or get_required_accounts(fallback_accounts=list(accounts.keys()))
    required = set(expected)
    missing = sorted(required - found)
    extra = sorted(found - required)
    if missing:
        errors.append(f"快商通账户不足 3 个，缺少：{', '.join(missing)}")
    if extra:
        errors.append(f"快商通账户多于 3 个：{', '.join(extra)}")

    for account in expected:
        row = accounts.get(account, {})
        for field in KST_FIELDS:
            value = row.get(field)
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"账户 {account} 字段 {field} 不是整数")
            elif value < 0:
                errors.append(f"账户 {account} 字段 {field} 为负数")
        errors.extend(f"账户 {account} {error}" for error in validate_kst_counts(row))
    return errors


def validate_baidu_report(report: dict[str, Any], required_accounts: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    accounts = report.get("accounts", {})
    found = set(accounts.keys())
    expected = required_accounts or get_required_accounts(fallback_accounts=list(accounts.keys()))
    required = set(expected)
    missing = sorted(required - found)
    extra = sorted(found - required)

    if len(found) != len(required):
        errors.append(f"百度后台账户数量不匹配：读取 {len(found)} 个，要求 {len(required)} 个")
    if missing:
        errors.append(f"百度后台账户不足 3 个，缺少：{', '.join(missing)}")
    if extra:
        errors.append(f"百度后台账户多于 3 个：{', '.join(extra)}")

    for account, row in accounts.items():
        for field in BAIDU_ACCOUNT_FIELDS:
            value = row.get(field)
            if not isinstance(value, int | float):
                errors.append(f"账户 {account} 字段 {field} 不是数字")
        cost = row.get("消费")
        if isinstance(cost, int | float) and cost < 0:
            errors.append(f"账户 {account} 消费不能为负数")
    return errors


def _validate_exact_accounts(label: str, report: dict[str, Any], required_accounts: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    accounts = report.get("accounts", {})
    found = set(accounts.keys())
    expected = required_accounts or get_required_accounts(
        fallback_accounts=list((merged.get("accounts") or {}).keys())
    )
    required = set(expected)
    missing = sorted(required - found)
    extra = sorted(found - required)
    if len(found) != len(required):
        errors.append(f"{label}账户数量不匹配：读取 {len(found)} 个，要求 {len(required)} 个")
    if missing:
        errors.append(f"{label}缺少账户：{', '.join(missing)}")
    if extra:
        errors.append(f"{label}存在多余账户：{', '.join(extra)}")
    return errors


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_merged_hourly_data(
    merged: dict[str, Any],
    baidu_report: dict[str, Any] | None = None,
    kst_report: dict[str, Any] | None = None,
    required_accounts: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    expected = required_accounts or get_required_accounts(
        fallback_accounts=list((merged.get("accounts") or {}).keys())
    )
    if baidu_report is not None:
        errors.extend(_validate_exact_accounts("百度数据", baidu_report, expected))
    if kst_report is not None:
        errors.extend(_validate_exact_accounts("快商通数据", kst_report, expected))

    errors.extend(_validate_exact_accounts("合并数据", merged, expected))

    if baidu_report and kst_report:
        baidu_date = baidu_report.get("date")
        kst_date = kst_report.get("date")
        if baidu_date and kst_date and baidu_date != kst_date:
            errors.append(f"百度日期与快商通日期不一致：{baidu_date} != {kst_date}")

    for account in expected:
        row = merged.get("accounts", {}).get(account, {})
        for field in MERGED_FIELDS:
            if field not in row:
                errors.append(f"账户 {account} 缺少字段 {field}")

        for field in ["展现", "点击"]:
            value = row.get(field)
            if not _is_int(value):
                errors.append(f"账户 {account} 字段 {field} 必须是整数")
            elif value < 0:
                errors.append(f"账户 {account} 字段 {field} 不能为负数")

        cost = row.get("消费")
        if not _is_number(cost):
            errors.append(f"账户 {account} 字段 消费 必须是数字")
        elif cost < 0:
            errors.append(f"账户 {account} 字段 消费 不能为负数")

        for field in KST_FIELDS:
            value = row.get(field)
            if not _is_int(value):
                errors.append(f"账户 {account} 字段 {field} 必须是整数")
            elif value < 0:
                errors.append(f"账户 {account} 字段 {field} 不能为负数")

        if all(_is_int(row.get(field)) for field in KST_FIELDS):
            errors.extend(f"账户 {account} {error}" for error in validate_kst_counts(row))
    return errors


def validate_daily_kst_counts(row: dict[str, int]) -> list[str]:
    errors = []
    total = int(row.get("总对话", 0) or 0)
    valid = int(row.get("有效对话", 0) or 0)
    invalid = int(row.get("无效对话", 0) or 0)
    general_valid = int(row.get("一般有效对话", 0) or 0)
    valid_lead = int(row.get("有效转潜", 0) or 0)
    total_lead = int(row.get("总转潜", 0) or 0)
    if valid > total:
        errors.append("有效对话不能大于总对话")
    if valid + general_valid + invalid < total:
        errors.append("有效、一般与无效对话未覆盖总对话")
    if max(valid, general_valid) + invalid > total:
        errors.append("无效对话与有效或一般对话存在重复")
    if valid_lead > valid:
        errors.append("有效转潜不能大于有效对话")
    if total_lead > total:
        errors.append("总转潜不能大于总对话")
    return errors


def validate_merged_daily_data(
    merged: dict[str, Any],
    baidu_report: dict[str, Any] | None = None,
    kst_report: dict[str, Any] | None = None,
    required_accounts: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    expected = required_accounts or get_required_accounts(
        fallback_accounts=list((merged.get("accounts") or {}).keys())
    )
    if baidu_report is not None:
        errors.extend(_validate_exact_accounts("百度日报数据", baidu_report, expected))
    if kst_report is not None:
        errors.extend(_validate_exact_accounts("商务通日报数据", kst_report, expected))
    errors.extend(_validate_exact_accounts("日报合并数据", merged, expected))

    if baidu_report and kst_report:
        baidu_date = baidu_report.get("date")
        kst_date = kst_report.get("date")
        if baidu_date and kst_date and baidu_date != kst_date:
            errors.append(f"百度日报日期与商务通日报日期不一致：{baidu_date} != {kst_date}")

    for account in expected:
        row = merged.get("accounts", {}).get(account, {})
        for field in MERGED_DAILY_FIELDS:
            if field not in row:
                errors.append(f"账户 {account} 缺少字段 {field}")

        for field in ["展现", "点击"]:
            value = row.get(field)
            if not _is_int(value):
                errors.append(f"账户 {account} 字段 {field} 必须是整数")
            elif value < 0:
                errors.append(f"账户 {account} 字段 {field} 不能为负数")

        cost = row.get("消费")
        if not _is_number(cost):
            errors.append(f"账户 {account} 字段 消费 必须是数字")
        elif cost < 0:
            errors.append(f"账户 {account} 字段 消费 不能为负数")

        for field in DAILY_KST_FIELDS:
            value = row.get(field)
            if not _is_int(value):
                errors.append(f"账户 {account} 字段 {field} 必须是整数")
            elif value < 0:
                errors.append(f"账户 {account} 字段 {field} 不能为负数")

        if all(_is_int(row.get(field)) for field in DAILY_KST_FIELDS):
            errors.extend(f"账户 {account} {error}" for error in validate_daily_kst_counts(row))
    return errors
