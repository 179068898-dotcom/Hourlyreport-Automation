from __future__ import annotations

from typing import Any

from modules.text_normalizer import normalize_text
from modules.validators import get_required_accounts, validate_baidu_report
import re


ACCOUNT_KEYS = ["账户", "账户名称", "推广账户", "账户名"]
FIELD_ALIASES = {
    "展现": ["展现", "展现量", "展现（次）", "展现(次)"],
    "点击": ["点击", "点击量", "点击（次）", "点击(次)"],
    "消费": ["消费", "消费（元）", "消费(元)", "花费", "消耗"],
}


def _parse_number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return value
    text = str(value).strip().replace(",", "").replace("￥", "").replace("元", "")
    if not text or text in {"-", "--"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number.is_integer():
        return int(number)
    return number


def _pick_value(row: dict[str, Any], aliases: list[str]) -> Any:
    normalized = {normalize_text(k): v for k, v in row.items()}
    for alias in aliases:
        key = normalize_text(alias)
        if key in normalized:
            return normalized[key]
    for key, value in normalized.items():
        if any(_alias_matches_key(normalize_text(alias), key) for alias in aliases):
            return value
    return None


def _alias_matches_key(alias: str, key: str) -> bool:
    if not alias or alias not in key:
        return False
    if alias == "点击" and any(blocked in key for blocked in ["点击率", "平均点击价格"]):
        return False
    return True


def _build_account_map(config: dict[str, Any]) -> dict[str, str]:
    account_map: dict[str, str] = {}
    for standard_name, info in config.get("accounts", {}).items():
        names = [standard_name, info.get("baidu_name", ""), info.get("excel_name", "")]
        names.extend(info.get("aliases", []))
        for name in names:
            normalized = normalize_text(name)
            if normalized:
                account_map[normalized] = standard_name
    return account_map


def _map_account(raw_account: Any, account_map: dict[str, str]) -> str | None:
    raw = normalize_text(raw_account)
    if not raw:
        return None
    if raw in account_map:
        return account_map[raw]
    for alias, standard_name in account_map.items():
        if alias and alias in raw:
            return standard_name
    return None


def extract_baidu_rows_from_visible_text(text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n") if line.strip()]
    total_match = [l for l in lines if re.match(r'^总计-\d+$', l)]
    if not total_match:
        return []
    total_index = lines.index(total_match[0])
    header_start = None
    for idx in range(total_index - 1, -1, -1):
        if normalize_text(lines[idx]) == "账户":
            header_start = idx
            break
    if header_start is None:
        return []

    headers = lines[header_start:total_index]
    if len(headers) < 3:
        return []
    end_index = len(lines)
    for idx in range(total_index + 1, len(lines)):
        if "条/页" in lines[idx] or normalize_text(lines[idx]) == "确定":
            end_index = idx
            break
    values = lines[total_index:end_index]
    rows = []
    width = len(headers)
    for start in range(0, len(values), width):
        chunk = values[start:start + width]
        if len(chunk) != width:
            continue
        row = {header: chunk[index] for index, header in enumerate(headers)}
        row["__source__"] = "visible_text"
        rows.append(row)
    return rows


def _parse_baidu_metrics(row: dict[str, Any]) -> dict[str, int | float | None]:
    """从解析行中提取展现/点击/消费三项指标。"""
    metrics: dict[str, int | float | None] = {}
    for field, aliases in FIELD_ALIASES.items():
        metrics[field] = _parse_number(_pick_value(row, aliases))
    return metrics


def _is_zero_baidu_metrics(metrics: dict[str, int | float | None]) -> bool:
    """展现=0 且 点击=0 且 消费=0。"""
    return (
        (metrics.get("展现") or 0) == 0
        and (metrics.get("点击") or 0) == 0
        and (metrics.get("消费") or 0) == 0
    )


def parse_baidu_table(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "accounts": {},
        "unknown_accounts": [],
        "ignored_unknown_accounts": [],
        "exceptions": [],
        "errors": [],
    }
    account_map = _build_account_map(config)

    for idx, row in enumerate(rows, start=1):
        raw_account = _pick_value(row, ACCOUNT_KEYS)
        standard_account = _map_account(raw_account, account_map)
        if not standard_account:
            metrics = _parse_baidu_metrics(row)
            account_name = str(raw_account) if raw_account else f"未知账户#{idx}"
            if _is_zero_baidu_metrics(metrics):
                result["ignored_unknown_accounts"].append({
                    "account_name": account_name,
                    "展现": metrics.get("展现", 0) or 0,
                    "点击": metrics.get("点击", 0) or 0,
                    "消费": metrics.get("消费", 0) or 0,
                    "reason": "未知账户但三项数据均为 0，已忽略",
                })
            else:
                result["unknown_accounts"].append({
                    "account_name": account_name,
                    "展现": metrics.get("展现", 0) or 0,
                    "点击": metrics.get("点击", 0) or 0,
                    "消费": metrics.get("消费", 0) or 0,
                    "reason": "百度后台抓到该账户，但当前项目配置 accounts 中未配置",
                })
            continue
        parsed_row: dict[str, Any] = {"source_account": raw_account}
        row_errors = []
        for field, aliases in FIELD_ALIASES.items():
            value = _parse_number(_pick_value(row, aliases))
            if value is None:
                row_errors.append(f"账户 {standard_account} 字段 {field} 不是数字或不存在")
            else:
                parsed_row[field] = value
        if row_errors:
            result["errors"].extend(row_errors)
        if isinstance(parsed_row.get("消费"), int | float) and parsed_row["消费"] < 0:
            result["errors"].append(f"账户 {standard_account} 消费不能为负数")
            continue
        if standard_account in result["accounts"]:
            result["errors"].append(f"重复账户：{standard_account}")
            continue
        result["accounts"][standard_account] = parsed_row

    result["errors"].extend(validate_baidu_report(result, get_required_accounts(config)))
    return result
