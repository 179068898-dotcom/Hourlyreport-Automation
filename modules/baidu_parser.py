from __future__ import annotations

import re
from typing import Any

from modules.text_normalizer import normalize_text
from modules.validators import get_required_accounts, validate_baidu_report


ACCOUNT_KEYS = ["账户", "账户名称", "推广账户", "账户名"]
FIELD_ALIASES = {
    "展现": ["展现", "展现量", "展现(次)", "展现（次）"],
    "点击": ["点击", "点击量", "点击次数", "点击(次)", "点击（次）"],
    "消费": ["消费", "花费", "消费金额", "消费(元)", "消费（元）"],
}
REQUIRED_HEADER_FIELDS = ["账户", "展现", "点击", "消费"]
ZERO_TOKENS = {"", "-", "--", "—", "——", "暂无", "无"}
BLOCKED_METRIC_HEADERS = {
    "点击": ["点击率", "平均点击价格"],
    "消费": ["消费占比", "消费比例"],
}
PERCENT_HEADER_KEYWORDS = ["率", "占比", "比例", "%", "％"]


def _is_percentage_text(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return "%" in text or "％" in text


def _parse_number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
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
    return int(number) if number.is_integer() else number


def _normalized_aliases(values: list[str]) -> set[str]:
    return {normalize_text(value) for value in values if normalize_text(value)}


def _header_matches_account(header: Any) -> bool:
    return normalize_text(header) in _normalized_aliases(ACCOUNT_KEYS)


def _header_matches_metric(field: str, header: Any) -> bool:
    normalized = normalize_text(header)
    if not normalized:
        return False

    if normalized not in _normalized_aliases(FIELD_ALIASES[field]):
        return False

    for blocked in BLOCKED_METRIC_HEADERS.get(field, []):
        if normalized == normalize_text(blocked):
            return False
    if field in {"点击", "消费"} and any(token in normalized for token in _normalized_aliases(PERCENT_HEADER_KEYWORDS)):
        return False
    return True


def _pick_value(row: dict[str, Any], aliases: list[str], field: str | None = None) -> Any:
    for key, value in row.items():
        if str(key).startswith("__"):
            continue
        if field == "账户":
            if _header_matches_account(key):
                return value
            continue
        if field and _header_matches_metric(field, key):
            return value
            # no continue branch needed
        if not field and normalize_text(key) in _normalized_aliases(aliases):
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
    normalized = normalize_text(raw_account)
    if not normalized:
        return None
    return account_map.get(normalized)


def _normalize_row(row: dict[str, Any], source: str, row_index: int) -> dict[str, Any]:
    normalized = dict(row)
    normalized.setdefault("__source__", source)
    normalized.setdefault("__row_sample_id__", f"{source}-row-{row_index}")
    return normalized


def _detect_headers(rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, str]]:
    headers: list[str] = []
    seen: set[str] = set()
    for row in rows[:5]:
        for key in row.keys():
            if str(key).startswith("__"):
                continue
            normalized = normalize_text(key)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            headers.append(str(key))

    header_map: dict[str, str] = {}
    for header in headers:
        if _header_matches_account(header):
            header_map.setdefault("账户", header)
        for field in FIELD_ALIASES:
            if _header_matches_metric(field, header):
                header_map.setdefault(field, header)
    return headers, header_map


def extract_baidu_rows_from_visible_text(text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n") if line.strip()]
    total_candidates = [line for line in lines if re.match(r"^总计-\d+$", line)]
    if not total_candidates:
        return []

    total_index = lines.index(total_candidates[0])
    header_start = None
    for index in range(total_index - 1, -1, -1):
        if normalize_text(lines[index]) == normalize_text("账户"):
            header_start = index
            break
    if header_start is None:
        return []

    headers = lines[header_start:total_index]
    if len(headers) < 4:
        return []

    end_index = len(lines)
    for index in range(total_index + 1, len(lines)):
        marker = normalize_text(lines[index])
        if "条/页" in marker or marker == normalize_text("确定"):
            end_index = index
            break

    values = lines[total_index:end_index]
    width = len(headers)
    rows: list[dict[str, Any]] = []
    for start in range(0, len(values), width):
        chunk = values[start:start + width]
        if len(chunk) != width:
            continue
        row = {headers[column_index]: chunk[column_index] for column_index in range(width)}
        rows.append(_normalize_row(row, "visible_text", len(rows) + 1))
    return rows


def _looks_like_data_value(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if re.match(r"^总计-\d+$", text):
        return True
    if _parse_number(text) is not None:
        return True
    return _is_percentage_text(text)


def _invalid_header_reason(header_cells: list[str], header_map: dict[str, int]) -> str | None:
    if not header_cells:
        return "missing_headers"
    if len(header_cells) < 4:
        return "too_few_columns"
    if any(re.match(r"^总计-\d+$", cell or "") for cell in header_cells):
        return "data_row_used_as_header"
    data_like_headers = sum(1 for cell in header_cells if _looks_like_data_value(cell))
    if data_like_headers >= max(2, len(header_cells) // 2):
        return "data_row_used_as_header"
    if any(field not in header_map for field in REQUIRED_HEADER_FIELDS):
        blocked_header_present = (
            any(normalize_text(cell) == normalize_text("点击率") for cell in header_cells)
            or any(normalize_text(cell) == normalize_text("消费占比") for cell in header_cells)
            or any(normalize_text(cell) == normalize_text("消费比例") for cell in header_cells)
        )
        return "invalid_metric_columns" if blocked_header_present else "missing_required_headers"
    return None


def _header_index_map(header_cells: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, header in enumerate(header_cells):
        if "账户" not in mapping and _header_matches_account(header):
            mapping["账户"] = index
        for field in FIELD_ALIASES:
            if field not in mapping and _header_matches_metric(field, header):
                mapping[field] = index
    return mapping


def _coerce_candidate_rows(candidate: dict[str, Any], default_source: str, candidate_index: int) -> list[dict[str, Any]]:
    if isinstance(candidate.get("rows"), list) and candidate.get("rows") and isinstance(candidate["rows"][0], dict):
        return [
            _normalize_row(row, str(row.get("__source__", default_source)), row_index + 1)
            for row_index, row in enumerate(candidate["rows"])
            if isinstance(row, dict)
        ]

    header_cells = [str(cell) for cell in candidate.get("header_cells", []) if str(cell).strip()]
    body_rows = candidate.get("body_rows") or []
    rows: list[dict[str, Any]] = []
    for row_index, cells in enumerate(body_rows, start=1):
        if not isinstance(cells, list):
            continue
        if len(cells) < len(header_cells):
            continue
        row = {header_cells[column_index]: cells[column_index] for column_index in range(len(header_cells))}
        rows.append(_normalize_row(row, default_source, row_index))
    if rows:
        return rows

    return []


def _extract_dom_rows_from_target(target) -> dict[str, Any]:
    snapshot = target.evaluate(
        """
        async () => {
          const normalize = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const roots = [];
          const seenRoots = new Set();
          const enqueueRoot = (root) => {
            if (!root || seenRoots.has(root)) return;
            seenRoots.add(root);
            roots.push(root);
          };
          enqueueRoot(document);
          for (let index = 0; index < roots.length; index += 1) {
            const root = roots[index];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
            while (walker.nextNode()) {
              const node = walker.currentNode;
              if (node && node.shadowRoot) enqueueRoot(node.shadowRoot);
            }
          }

          const queryAll = (selector) => {
            const nodes = [];
            for (const root of roots) nodes.push(...Array.from(root.querySelectorAll(selector)));
            return nodes;
          };

          const uniqueElements = (elements) => {
            const seen = new Set();
            return elements.filter((element) => {
              if (!element || seen.has(element)) return false;
              seen.add(element);
              return true;
            });
          };

          const buildSelector = (element) => {
            if (!element || element === document || element === document.body) return "body";
            const parts = [];
            let node = element;
            while (node && node.nodeType === Node.ELEMENT_NODE && parts.length < 5) {
              let part = node.tagName.toLowerCase();
              if (node.id) {
                part += `#${node.id}`;
                parts.unshift(part);
                break;
              }
              const classNames = (node.className && typeof node.className === "string")
                ? node.className.trim().split(/\\s+/).filter(Boolean).slice(0, 2)
                : [];
              if (classNames.length) {
                part += "." + classNames.join(".");
              } else if (node.parentElement) {
                const siblings = Array.from(node.parentElement.children).filter((child) => child.tagName === node.tagName);
                if (siblings.length > 1) {
                  part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
                }
              }
              parts.unshift(part);
              node = node.parentElement;
            }
            return parts.join(" > ");
          };

          const textFromNode = (node) => normalize(node?.innerText || node?.textContent || "");
          const isScrollable = (element) => {
            if (!element || !(element instanceof Element)) return false;
            const style = window.getComputedStyle(element);
            return (
              element.scrollHeight > element.clientHeight + 8 &&
              ["auto", "scroll"].includes(style.overflowY)
            );
          };

          const findScrollContainer = (root) => {
            if (isScrollable(root)) return root;
            const descendants = Array.from(root.querySelectorAll("*"));
            return descendants.find((node) => isScrollable(node)) || null;
          };

          const collectHeaderCells = (root) => {
            const groups = [
              Array.from(root.querySelectorAll("thead tr:last-child th, thead tr:last-child td")),
              Array.from(root.querySelectorAll('[role="columnheader"]')),
              Array.from(root.querySelectorAll('[class*="header"] [role="gridcell"], [class*="header"] [role="cell"], [class*="header"] div[class*="cell"], [class*="header"] th, [class*="header"] td')),
            ];
            for (const group of groups) {
              const headers = group.map(textFromNode).filter(Boolean);
              if (headers.length) return headers;
            }
            const rowCandidates = Array.from(root.querySelectorAll("tr, [role='row'], div[class*='row']"));
            for (const row of rowCandidates.slice(0, 3)) {
              const cells = Array.from(row.querySelectorAll("th, td, [role='columnheader'], [role='gridcell'], [role='cell'], div[class*='cell']"))
                .map(textFromNode)
                .filter(Boolean);
              if (cells.length) return cells;
            }
            return [];
          };

          const collectBodyRows = (root, headerCells) => {
            const rowNodes = Array.from(root.querySelectorAll("tbody tr, [role='row'], tr, div[class*='row']"));
            const rows = [];
            for (const rowNode of rowNodes) {
              const headerCellCount = rowNode.querySelectorAll('[role="columnheader"], th').length;
              if (headerCellCount) continue;
              const cells = Array.from(rowNode.querySelectorAll("td, [role='gridcell'], [role='cell'], div[class*='cell']"))
                .map(textFromNode)
                .filter((value) => value !== "");
              if (!cells.length) continue;
              if (headerCells.length && cells.join("|") === headerCells.join("|")) continue;
              rows.push(cells);
            }
            return rows;
          };

          const candidateRoots = uniqueElements([
            ...queryAll("table"),
            ...queryAll('[role="grid"]'),
            ...queryAll('[role="table"]'),
            ...queryAll('div[class*="grid"]'),
            ...queryAll('div[class*="table"]'),
          ]).filter((root) => root instanceof Element);

          const candidates = [];
          for (const root of candidateRoots) {
            const headerCells = collectHeaderCells(root);
            const scrollContainer = findScrollContainer(root);
            const bodyRows = [];
            const seenRows = new Set();
            const accountsSeenEachScroll = [];
            let scrollAttempts = 0;
            let reachedBottom = !scrollContainer;
            let consecutiveNoGrowth = 0;

            while (scrollAttempts < 5) {
              scrollAttempts += 1;
              const currentRows = collectBodyRows(root, headerCells);
              const accountSnapshot = [];
              for (const cells of currentRows) {
                const key = cells.join("\\u241f");
                if (!seenRows.has(key)) {
                  seenRows.add(key);
                  bodyRows.push(cells);
                }
                if (cells.length) accountSnapshot.push(cells[0]);
              }
              accountsSeenEachScroll.push(Array.from(new Set(accountSnapshot)));

              if (!scrollContainer) {
                reachedBottom = true;
                break;
              }

              const beforeCount = seenRows.size;
              const beforeTop = scrollContainer.scrollTop;
              const maxScrollTop = Math.max(0, scrollContainer.scrollHeight - scrollContainer.clientHeight);
              if (beforeTop >= maxScrollTop - 4) {
                reachedBottom = true;
                break;
              }

              scrollContainer.scrollTop = Math.min(maxScrollTop, beforeTop + Math.max(scrollContainer.clientHeight * 0.9, 160));
              await new Promise((resolve) => setTimeout(resolve, 450));
              if (seenRows.size === beforeCount) {
                consecutiveNoGrowth += 1;
              } else {
                consecutiveNoGrowth = 0;
              }
              if (consecutiveNoGrowth >= 2) break;
            }

            candidates.push({
              table_root_selector: buildSelector(root),
              scroll_container_selector: scrollContainer ? buildSelector(scrollContainer) : null,
              header_source: root.querySelector('[role="columnheader"]') ? "columnheader" : (root.querySelector("thead") ? "thead" : "row"),
              header_cells: headerCells,
              body_rows: bodyRows,
              body_row_count: bodyRows.length,
              scroll_attempts,
              accounts_seen_each_scroll: accountsSeenEachScroll,
              reached_bottom: reachedBottom,
            });
          }

          return {
            table_like_found: candidateRoots.length > 0,
            candidates,
          };
        }
        """
    )

    if isinstance(snapshot, list):
        rows = [row for row in snapshot if isinstance(row, dict)]
        return {
            "table_like_found": bool(rows),
            "candidates": [
                {
                    "table_root_selector": "evaluate:list",
                    "header_source": "evaluate:list",
                    "rows": rows,
                    "body_row_count": len(rows),
                    "scroll_attempts": 1,
                    "accounts_seen_each_scroll": [],
                    "reached_bottom": True,
                }
            ],
        }

    if isinstance(snapshot, dict) and "candidates" in snapshot:
        snapshot["candidates"] = [candidate for candidate in snapshot.get("candidates", []) if isinstance(candidate, dict)]
        snapshot.setdefault("table_like_found", bool(snapshot["candidates"]))
        return snapshot

    if isinstance(snapshot, dict) and isinstance(snapshot.get("rows"), list):
        rows = [row for row in snapshot.get("rows", []) if isinstance(row, dict)]
        return {
            "table_like_found": bool(rows),
            "candidates": [
                {
                    "table_root_selector": snapshot.get("table_root_selector") or "evaluate:rows",
                    "header_source": snapshot.get("header_source") or "evaluate:rows",
                    "rows": rows,
                    "body_row_count": len(rows),
                    "scroll_attempts": int(snapshot.get("scroll_attempts", 1) or 1),
                    "accounts_seen_each_scroll": snapshot.get("accounts_seen_each_scroll") or [],
                    "reached_bottom": bool(snapshot.get("reached_bottom", True)),
                }
            ],
        }

    return {"table_like_found": False, "candidates": []}


def _extract_dom_snapshot(page) -> dict[str, Any]:
    combined = {"table_like_found": False, "candidates": []}
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
        combined["table_like_found"] = combined["table_like_found"] or bool(snapshot.get("table_like_found"))
        combined["candidates"].extend(snapshot.get("candidates", []))
    return combined


def _parse_baidu_metrics(row: dict[str, Any]) -> dict[str, int | float | None]:
    return {
        "展现": _parse_number(_pick_value(row, FIELD_ALIASES["展现"], "展现")),
        "点击": _parse_number(_pick_value(row, FIELD_ALIASES["点击"], "点击")),
        "消费": _parse_number(_pick_value(row, FIELD_ALIASES["消费"], "消费")),
    }


def is_baidu_total_row(account_name: Any) -> bool:
    return bool(account_name and re.match(r"^总计-\d+$", str(account_name).strip()))


def _is_zero_baidu_metrics(metrics: dict[str, int | float | None]) -> bool:
    for field in ("展现", "点击", "消费"):
        value = metrics.get(field)
        if not isinstance(value, (int, float)) or value != 0:
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
        "account_match_details": [],
    }
    account_map = _build_account_map(config)

    for index, input_row in enumerate(rows, start=1):
        row = _normalize_row(input_row, str(input_row.get("__source__", "unknown")), index)
        raw_account = _pick_value(row, ACCOUNT_KEYS, "账户")
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

        result["account_match_details"].append(
            {
                "raw_account": "" if raw_account is None else str(raw_account),
                "normalized_account": normalize_text(raw_account),
                "matched_account": standard_account,
                "match_type": "exact",
            }
        )

        parsed_row: dict[str, Any] = {"source_account": raw_account}
        for field in ("展现", "点击", "消费"):
            raw_value = _pick_value(row, FIELD_ALIASES[field], field)
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


def _build_parse_debug(
    rows: list[dict[str, Any]],
    config: dict[str, Any],
    extraction_method: str,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parsed = parse_baidu_table(rows, config)
    required_accounts = get_required_accounts(config)
    parsed_accounts = list(parsed.get("accounts", {}).keys())
    missing_accounts = [name for name in required_accounts if name not in parsed_accounts]
    headers, header_map = _detect_headers(rows)
    has_required_headers = all(field in header_map for field in REQUIRED_HEADER_FIELDS)
    row_cell_count = [len([key for key in row.keys() if not str(key).startswith("__")]) for row in rows[:20]]
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
        failure_reasons.append("missing_required_accounts")
    if parsed.get("non_numeric_fields"):
        failure_reasons.append("non_numeric_fields")
    if percent_misalignment:
        failure_reasons.append("percent_misalignment")
    if extraction_method == "dom" and not rows:
        failure_reasons.insert(0, "no_table")

    debug = {
        "project_id": config.get("project_id"),
        "required_accounts": required_accounts,
        "required_account_count": len(required_accounts),
        "required_accounts_found": [name for name in required_accounts if name in parsed_accounts],
        "extraction_method": extraction_method,
        "detected_headers": headers,
        "parsed_account_count": len(parsed_accounts),
        "parsed_accounts": parsed_accounts,
        "missing_accounts": missing_accounts,
        "account_match_details": parsed.get("account_match_details", []),
        "non_numeric_fields": parsed.get("non_numeric_fields", []),
        "percent_misalignment": percent_misalignment,
        "column_misalignment_detected": percent_misalignment,
        "failure_reasons": failure_reasons,
        "sample_rows": [
            {
                "row_sample_id": row.get("__row_sample_id__"),
                "source": row.get("__source__"),
                "cells": {key: value for key, value in row.items() if not str(key).startswith("__")},
            }
            for row in rows[:5]
        ],
        "raw_cell_count": sum(len([key for key in row.keys() if not str(key).startswith("__")]) for row in rows),
        "row_cell_count": row_cell_count,
        "row_field_count_stable": bool(row_cell_count) and len(set(row_cell_count)) == 1,
        "has_required_headers": has_required_headers,
        "parse_ready": has_required_headers and not missing_accounts and not parsed.get("non_numeric_fields"),
    }
    if extras:
        debug.update(extras)
    return debug


def _candidate_required_accounts_found(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[str]:
    account_map = _build_account_map(config)
    required_accounts = get_required_accounts(config)
    found: list[str] = []
    for row in rows:
        mapped = _map_account(_pick_value(row, ACCOUNT_KEYS, "账户"), account_map)
        if mapped and mapped in required_accounts and mapped not in found:
            found.append(mapped)
    return found


def _analyze_dom_candidate(candidate: dict[str, Any], config: dict[str, Any], candidate_index: int) -> dict[str, Any]:
    source = f"dom_candidate_{candidate_index}"
    rows = _coerce_candidate_rows(candidate, source, candidate_index)
    header_cells = [str(cell) for cell in candidate.get("header_cells", []) if str(cell).strip()]
    if not header_cells and rows:
        header_cells, _ = _detect_headers(rows)
    header_map = _header_index_map(header_cells)
    invalid_reason = _invalid_header_reason(header_cells, header_map)
    filtered_rows = [row for row in rows if not is_baidu_total_row(_pick_value(row, ACCOUNT_KEYS, "账户"))]
    required_accounts_found = _candidate_required_accounts_found(filtered_rows, config)
    debug = _build_parse_debug(
        filtered_rows,
        config,
        "dom",
        {
            "table_root_selector": candidate.get("table_root_selector"),
            "scroll_container_selector": candidate.get("scroll_container_selector"),
            "header_source": candidate.get("header_source"),
            "header_cells": header_cells,
            "header_valid": invalid_reason is None,
            "invalid_header_reason": invalid_reason,
            "body_row_count": int(candidate.get("body_row_count", len(rows)) or 0),
            "row_count_after_filter": len(filtered_rows),
            "account_column_index": header_map.get("账户"),
            "metric_column_indexes": {field: header_map.get(field) for field in ("展现", "点击", "消费") if field in header_map},
            "scroll_attempts": int(candidate.get("scroll_attempts", 1) or 1),
            "accounts_seen_each_scroll": candidate.get("accounts_seen_each_scroll") or [],
            "reached_bottom": bool(candidate.get("reached_bottom", False)),
            "required_accounts_found": required_accounts_found,
        },
    )
    score = (
        (1000 if invalid_reason is None else 0)
        + len(required_accounts_found) * 100
        + debug["parsed_account_count"] * 50
        + len(filtered_rows)
    )
    return {"rows": filtered_rows, "debug": debug, "score": score}


def _build_dom_debug_from_candidates(dom_snapshot: dict[str, Any], config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    analyses = [_analyze_dom_candidate(candidate, config, index) for index, candidate in enumerate(dom_snapshot.get("candidates", []), start=1)]
    best = max(analyses, key=lambda item: item["score"], default=None)
    if not best:
        debug = _build_parse_debug([], config, "dom")
        debug["table_like_found"] = bool(dom_snapshot.get("table_like_found"))
        debug["dom_attempts"] = []
        return [], debug

    debug = dict(best["debug"])
    debug["table_like_found"] = bool(dom_snapshot.get("table_like_found"))
    debug["header_found"] = any(bool(item["debug"].get("header_cells")) for item in analyses)
    debug["body_row_count"] = sum(int(item["debug"].get("body_row_count", 0) or 0) for item in analyses)
    debug["dom_attempts"] = [item["debug"] for item in analyses]
    return best["rows"], debug


def _visible_text_fallback_allowed(debug: dict[str, Any]) -> bool:
    if not debug.get("has_required_headers"):
        return False
    if debug.get("missing_accounts"):
        return False
    if debug.get("non_numeric_fields"):
        return False
    if debug.get("percent_misalignment"):
        return False
    if not debug.get("row_field_count_stable"):
        return False
    if debug.get("parsed_account_count", 0) < debug.get("required_account_count", 0):
        return False
    return True


def extract_baidu_rows_from_page(page, config: dict[str, Any]) -> dict[str, Any]:
    dom_snapshot = _extract_dom_snapshot(page)
    dom_rows, dom_debug = _build_dom_debug_from_candidates(dom_snapshot, config)

    if dom_rows and dom_debug.get("parse_ready") and dom_debug.get("header_valid"):
        final_debug = dict(dom_debug)
        final_debug["attempts"] = {"dom": dom_debug}
        return {
            "rows": dom_rows,
            "extraction_method": "dom",
            "detected_headers": dom_debug.get("detected_headers", []),
            "debug": final_debug,
        }

    visible_text = page.locator("body").inner_text(timeout=10000)
    text_rows = extract_baidu_rows_from_visible_text(visible_text)
    text_debug = _build_parse_debug(text_rows, config, "visible_text")
    text_debug["header_valid"] = bool(text_debug.get("has_required_headers"))
    text_debug["invalid_header_reason"] = None if text_debug["header_valid"] else "missing_required_headers"

    if text_rows and _visible_text_fallback_allowed(text_debug):
        final_debug = dict(text_debug)
        final_debug["attempts"] = {"dom": dom_debug, "visible_text": text_debug}
        return {
            "rows": text_rows,
            "extraction_method": "visible_text",
            "detected_headers": text_debug.get("detected_headers", []),
            "debug": final_debug,
        }

    fallback_debug = dict(dom_debug if dom_rows else text_debug)
    fallback_debug["extraction_method"] = "fallback_failed"
    fallback_debug["parse_ready"] = False
    fallback_debug["attempts"] = {"dom": dom_debug, "visible_text": text_debug}
    if not dom_rows and text_rows:
        fallback_debug["percent_misalignment"] = text_debug.get("percent_misalignment", False)
        fallback_debug["missing_accounts"] = text_debug.get("missing_accounts", [])
        fallback_debug["non_numeric_fields"] = text_debug.get("non_numeric_fields", [])
        fallback_debug["detected_headers"] = text_debug.get("detected_headers", [])
    return {
        "rows": dom_rows or text_rows,
        "extraction_method": "fallback_failed",
        "detected_headers": fallback_debug.get("detected_headers", []),
        "debug": fallback_debug,
    }
