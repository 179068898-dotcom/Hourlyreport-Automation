from __future__ import annotations

import re
from typing import Any

from modules.text_normalizer import normalize_text
from modules.validators import get_required_accounts, validate_baidu_report


ACCOUNT_KEYS = ["账户", "账户名称", "推广账户", "账户名"]
FIELD_ALIASES = {
    "展现": ["展现", "展现量", "展现(次)", "展现（次）"],
    "点击": ["点击", "点击量", "点击(次)", "点击（次）"],
    "消费": ["消费", "消费(元)", "消费（元）", "花费", "消费金额"],
}
REQUIRED_HEADER_FIELDS = ["账户", "展现", "点击", "消费"]
ZERO_TOKENS = {"", "-", "--", "—", "——", "暂无", "无"}


def _is_percentage_text(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return "%" in text or "％" in text


def _parse_number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if text in ZERO_TOKENS:
        return 0
    cleaned = (
        text.replace(",", "")
        .replace("￥", "")
        .replace("¥", "")
        .replace("元", "")
        .replace("块", "")
        .replace(" ", "")
    )
    if _is_percentage_text(cleaned):
        return None
    if cleaned in ZERO_TOKENS:
        return 0
    try:
        number = float(cleaned)
    except ValueError:
        return None
    if number.is_integer():
        return int(number)
    return number


def _alias_matches_key(alias: str, key: str) -> bool:
    if not alias or alias not in key:
        return False
    if alias == normalize_text("点击") and any(
        blocked in key for blocked in [normalize_text("点击率"), normalize_text("平均点击价格")]
    ):
        return False
    return True


def _pick_value(row: dict[str, Any], aliases: list[str]) -> Any:
    normalized = {normalize_text(k): v for k, v in row.items() if not str(k).startswith("__")}
    for alias in aliases:
        key = normalize_text(alias)
        if key in normalized:
            return normalized[key]
    for key, value in normalized.items():
        if any(_alias_matches_key(normalize_text(alias), key) for alias in aliases):
            return value
    return None


def _build_account_map(config: dict[str, Any]) -> dict[str, str]:
    account_map: dict[str, str] = {}
    accounts = config.get("accounts", {})
    if isinstance(accounts, list):
        for item in accounts:
            standard_name = str(item.get("standard_name") or "")
            aliases = [standard_name, item.get("excel_name", ""), *(item.get("baidu_names") or []), *(item.get("aliases") or [])]
            for alias in aliases:
                normalized = normalize_text(alias)
                if normalized:
                    account_map[normalized] = standard_name
        return account_map

    for standard_name, info in accounts.items():
        aliases = [standard_name, info.get("baidu_name", ""), info.get("excel_name", "")]
        aliases.extend(info.get("baidu_names", []))
        aliases.extend(info.get("aliases", []))
        for alias in aliases:
            normalized = normalize_text(alias)
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


def _normalize_row(row: dict[str, Any], source: str, row_index: int) -> dict[str, Any]:
    normalized = dict(row)
    normalized.setdefault("__source__", source)
    normalized.setdefault("__row_sample_id__", f"{source}-row-{row_index}")
    return normalized


def _match_header(header: str, aliases: list[str]) -> bool:
    norm = normalize_text(header)
    if not norm:
        return False
    return any(_alias_matches_key(normalize_text(alias), norm) for alias in aliases)


def _detect_headers(rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, str]]:
    header_names: list[str] = []
    normalized_seen: set[str] = set()
    for row in rows[:5]:
        for key in row.keys():
            if str(key).startswith("__"):
                continue
            norm = normalize_text(key)
            if not norm or norm in normalized_seen:
                continue
            normalized_seen.add(norm)
            header_names.append(str(key))

    header_map: dict[str, str] = {}
    for header in header_names:
        if _match_header(header, ACCOUNT_KEYS):
            header_map.setdefault("账户", header)
        for field, aliases in FIELD_ALIASES.items():
            if _match_header(header, aliases):
                header_map.setdefault(field, header)
    return header_names, header_map


def extract_baidu_rows_from_visible_text(text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n") if line.strip()]
    total_candidates = [line for line in lines if re.match(r"^总计-\d+$", line)]
    if not total_candidates:
        return []
    total_index = lines.index(total_candidates[0])
    header_start = None
    for idx in range(total_index - 1, -1, -1):
        if normalize_text(lines[idx]) == normalize_text("账户"):
            header_start = idx
            break
    if header_start is None:
        return []

    headers = lines[header_start:total_index]
    if len(headers) < 3:
        return []

    end_index = len(lines)
    for idx in range(total_index + 1, len(lines)):
        marker = normalize_text(lines[idx])
        if "页" in marker or marker == normalize_text("确定"):
            end_index = idx
            break

    values = lines[total_index:end_index]
    width = len(headers)
    rows: list[dict[str, Any]] = []
    for start in range(0, len(values), width):
        chunk = values[start:start + width]
        if len(chunk) != width:
            continue
        row = {header: chunk[index] for index, header in enumerate(headers)}
        rows.append(_normalize_row(row, "visible_text", len(rows) + 1))
    return rows


def _extract_dom_rows_from_target(target) -> dict[str, Any]:
    snapshot = target.evaluate(
        """
        () => {
          const normalize = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const roots = [];
          const seen = new Set();
          const enqueueRoot = (root) => {
            if (!root || seen.has(root)) return;
            seen.add(root);
            roots.push(root);
          };
          enqueueRoot(document);
          for (let index = 0; index < roots.length; index += 1) {
            const root = roots[index];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
            while (walker.nextNode()) {
              const node = walker.currentNode;
              if (node && node.shadowRoot) {
                enqueueRoot(node.shadowRoot);
              }
            }
          }
          const queryAll = (selector) => {
            const nodes = [];
            for (const root of roots) {
              nodes.push(...Array.from(root.querySelectorAll(selector)));
            }
            return nodes;
          };
          const toRowObjects = (headers, bodyRows, sourcePrefix) => {
            if (!headers.length) return [];
            return bodyRows.map((cells, rowIndex) => {
              const row = {};
              headers.forEach((header, index) => {
                row[header || `列${index + 1}`] = normalize(cells[index] || "");
              });
              row.__source__ = sourcePrefix;
              row.__row_sample_id__ = `${sourcePrefix}-row-${rowIndex + 1}`;
              return row;
            }).filter((row) => Object.entries(row).some(([key, value]) => !key.startsWith("__") && value));
          };

          const results = [];
          let tableLikeFound = false;
          let headerFound = false;
          let bodyRowCount = 0;

          for (const table of queryAll("table")) {
            tableLikeFound = true;
            const headRows = Array.from(table.querySelectorAll("thead tr"));
            const lastHead = headRows.length ? headRows[headRows.length - 1] : null;
            const fallbackHead = table.querySelector("tr");
            const headerCells = Array.from((lastHead || fallbackHead || {}).querySelectorAll?.("th,td") || []);
            const headers = headerCells.map((cell) => normalize(cell.innerText || cell.textContent));
            if (headers.length) headerFound = true;
            if (!headers.length) continue;

            const bodyNodes = Array.from(table.querySelectorAll("tbody tr"));
            const bodyRows = (bodyNodes.length ? bodyNodes : Array.from(table.querySelectorAll("tr")).slice(1))
              .map((tr) => Array.from(tr.querySelectorAll("td,th")).map((cell) => normalize(cell.innerText || cell.textContent)))
              .filter((cells) => cells.some(Boolean));
            bodyRowCount += bodyRows.length;
            results.push(...toRowObjects(headers, bodyRows, "dom"));
          }

          for (const grid of queryAll('[role="table"], [role="grid"]')) {
            tableLikeFound = true;
            const headers = Array.from(grid.querySelectorAll('[role="columnheader"]'))
              .map((cell) => normalize(cell.innerText || cell.textContent))
              .filter(Boolean);
            if (headers.length) headerFound = true;
            if (!headers.length) continue;
            const bodyRows = Array.from(grid.querySelectorAll('[role="row"]'))
              .map((rowNode) => Array.from(rowNode.querySelectorAll('[role="gridcell"], [role="cell"], td'))
                .map((cell) => normalize(cell.innerText || cell.textContent)))
              .filter((cells) => cells.some(Boolean) && cells.length > 1);
            bodyRowCount += bodyRows.length;
            results.push(...toRowObjects(headers, bodyRows, "dom"));
          }

          return {
            rows: results,
            table_like_found: tableLikeFound,
            header_found: headerFound,
            body_row_count: bodyRowCount,
          };
        }
        """
    )
    if isinstance(snapshot, list):
        rows = [row for row in snapshot if isinstance(row, dict)]
        return {
            "rows": rows,
            "table_like_found": bool(rows),
            "header_found": bool(rows),
            "body_row_count": len(rows),
        }
    if not isinstance(snapshot, dict):
        return {"rows": [], "table_like_found": False, "header_found": False, "body_row_count": 0}
    snapshot["rows"] = [row for row in snapshot.get("rows", []) if isinstance(row, dict)]
    return snapshot


def _extract_dom_snapshot(page) -> dict[str, Any]:
    combined = {"rows": [], "table_like_found": False, "header_found": False, "body_row_count": 0}
    targets = [page]
    frames = getattr(page, "frames", None)
    if callable(frames):
        try:
            targets.extend(list(frames()))
        except Exception:
            pass
    for target in targets:
        try:
            snapshot = _extract_dom_rows_from_target(target)
        except Exception:
            continue
        combined["rows"].extend(snapshot.get("rows", []))
        combined["table_like_found"] = combined["table_like_found"] or bool(snapshot.get("table_like_found"))
        combined["header_found"] = combined["header_found"] or bool(snapshot.get("header_found"))
        combined["body_row_count"] += int(snapshot.get("body_row_count", 0) or 0)
    return combined


def _parse_baidu_metrics(row: dict[str, Any]) -> dict[str, int | float | None]:
    return {field: _parse_number(_pick_value(row, aliases)) for field, aliases in FIELD_ALIASES.items()}


def is_baidu_total_row(account_name: Any) -> bool:
    return bool(account_name and re.match(r"^总计-\d+$", str(account_name).strip()))


def _is_zero_baidu_metrics(metrics: dict[str, int | float | None]) -> bool:
    for field in ("展现", "点击", "消费"):
        value = metrics.get(field)
        if not isinstance(value, (int, float)):
            return False
        if value != 0:
            return False
    return True


def parse_baidu_table(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "accounts": {},
        "unknown_accounts": [],
        "ignored_unknown_accounts": [],
        "exceptions": [],
        "errors": [],
        "non_numeric_fields": [],
    }
    account_map = _build_account_map(config)

    for index, input_row in enumerate(rows, start=1):
        row = _normalize_row(input_row, str(input_row.get("__source__", "unknown")), index)
        raw_account = _pick_value(row, ACCOUNT_KEYS)
        if is_baidu_total_row(raw_account):
            continue

        standard_account = _map_account(raw_account, account_map)
        metrics = _parse_baidu_metrics(row)

        if not standard_account:
            account_name = str(raw_account) if raw_account else f"未知账户#{index}"
            target = "ignored_unknown_accounts" if _is_zero_baidu_metrics(metrics) else "unknown_accounts"
            reason = (
                "未知账户但三项数据均为 0，已忽略"
                if target == "ignored_unknown_accounts"
                else "百度后台抓到该账户，但当前项目配置 accounts 中未配置"
            )
            result[target].append(
                {
                    "account_name": account_name,
                    "展现": metrics.get("展现", 0) or 0,
                    "点击": metrics.get("点击", 0) or 0,
                    "消费": metrics.get("消费", 0) or 0,
                    "reason": reason,
                }
            )
            continue

        parsed_row: dict[str, Any] = {"source_account": raw_account}
        for field, aliases in FIELD_ALIASES.items():
            raw_value = _pick_value(row, aliases)
            value = _parse_number(raw_value)
            if value is None:
                detail = {
                    "account_name": standard_account,
                    "field": field,
                    "raw_value": "" if raw_value is None else str(raw_value),
                    "extraction_method": str(row.get("__source__", "unknown")),
                    "row_sample_id": str(row.get("__row_sample_id__", f"row-{index}")),
                }
                result["non_numeric_fields"].append(detail)
                result["errors"].append(
                    "账户 {account_name} 字段 {field} 不是数字或不存在 "
                    "(account_name={account_name}, raw_value={raw_value}, extraction_method={extraction_method}, row_sample_id={row_sample_id})".format(
                        **detail
                    )
                )
                continue
            parsed_row[field] = value

        if isinstance(parsed_row.get("消费"), (int, float)) and parsed_row["消费"] < 0:
            result["errors"].append(f"账户 {standard_account} 消费不能为负数")
            continue
        if standard_account in result["accounts"]:
            result["errors"].append(f"重复账户：{standard_account}")
            continue
        result["accounts"][standard_account] = parsed_row

    result["errors"].extend(validate_baidu_report(result, get_required_accounts(config)))
    return result


def _build_parse_debug(rows: list[dict[str, Any]], config: dict[str, Any], extraction_method: str) -> dict[str, Any]:
    parsed = parse_baidu_table(rows, config)
    required_accounts = get_required_accounts(config)
    parsed_accounts = list(parsed.get("accounts", {}).keys())
    missing_accounts = [name for name in required_accounts if name not in parsed_accounts]
    headers, header_map = _detect_headers(rows)
    has_required_headers = all(field in header_map for field in REQUIRED_HEADER_FIELDS)
    percent_misalignment = any(
        item.get("field") in {"点击", "消费"} and _is_percentage_text(item.get("raw_value"))
        for item in parsed.get("non_numeric_fields", [])
    )
    failure_reasons: list[str] = []
    if not rows:
        failure_reasons.append("no_rows")
    if rows and not headers:
        failure_reasons.append("no_header")
    if rows and not has_required_headers:
        failure_reasons.append("no_required_headers")
    if missing_accounts:
        failure_reasons.append("no_required_accounts")
    if parsed.get("non_numeric_fields"):
        failure_reasons.append("non_numeric_fields")
    if extraction_method == "dom" and not rows:
        failure_reasons.insert(0, "no_table")

    return {
        "project_id": config.get("project_id"),
        "required_accounts": required_accounts,
        "required_account_count": len(required_accounts),
        "extraction_method": extraction_method,
        "detected_headers": headers,
        "parsed_account_count": len(parsed_accounts),
        "parsed_accounts": parsed_accounts,
        "missing_accounts": missing_accounts,
        "non_numeric_fields": parsed.get("non_numeric_fields", []),
        "percent_misalignment": percent_misalignment,
        "failure_reasons": failure_reasons,
        "sample_rows": [
            {
                "row_sample_id": row.get("__row_sample_id__"),
                "source": row.get("__source__"),
                "cells": {k: v for k, v in row.items() if not str(k).startswith("__")},
            }
            for row in rows[:5]
        ],
        "raw_cell_count": sum(len([k for k in row.keys() if not str(k).startswith("__")]) for row in rows),
        "row_cell_count": [len([k for k in row.keys() if not str(k).startswith("__")]) for row in rows[:20]],
        "has_required_headers": has_required_headers,
        "parse_ready": has_required_headers and len(parsed_accounts) >= 1,
    }


def extract_baidu_rows_from_page(page, config: dict[str, Any]) -> dict[str, Any]:
    dom_snapshot = _extract_dom_snapshot(page)
    dom_rows = dom_snapshot.get("rows", [])
    dom_debug = _build_parse_debug(dom_rows, config, "dom")
    dom_debug["table_like_found"] = bool(dom_snapshot.get("table_like_found"))
    dom_debug["header_found"] = bool(dom_snapshot.get("header_found"))
    dom_debug["body_row_count"] = int(dom_snapshot.get("body_row_count", 0) or 0)

    if dom_rows and dom_debug.get("has_required_headers"):
        final_debug = dict(dom_debug)
        final_debug["attempts"] = {"dom": dom_debug}
        return {
            "rows": dom_rows,
            "extraction_method": "dom",
            "detected_headers": dom_debug["detected_headers"],
            "debug": final_debug,
        }

    visible_text = page.locator("body").inner_text(timeout=10000)
    text_rows = extract_baidu_rows_from_visible_text(visible_text)
    text_debug = _build_parse_debug(text_rows, config, "visible_text")
    if text_rows and text_debug.get("has_required_headers"):
        final_debug = dict(text_debug)
        final_debug["attempts"] = {"dom": dom_debug, "visible_text": text_debug}
        return {
            "rows": text_rows,
            "extraction_method": "visible_text",
            "detected_headers": text_debug["detected_headers"],
            "debug": final_debug,
        }

    fallback_debug = dict(dom_debug if dom_rows else text_debug)
    fallback_debug["extraction_method"] = "fallback_failed"
    fallback_debug["parse_ready"] = False
    fallback_debug["attempts"] = {"dom": dom_debug, "visible_text": text_debug}
    return {
        "rows": dom_rows or text_rows,
        "extraction_method": "fallback_failed",
        "detected_headers": fallback_debug.get("detected_headers", []),
        "debug": fallback_debug,
    }
