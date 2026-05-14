"""未知百度账户报告生成。

负责把 parse_baidu_table 返回的 unknown_accounts 结构化保存到
reports/unknown_baidu_accounts.json。

同时提供终端简洁提醒函数，不阻断主流程。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OUTPUT_FILE = "reports/unknown_baidu_accounts.json"


def build_unknown_baidu_accounts_report(
    config: dict[str, Any],
    parsed: dict[str, Any],
    task: str,
    date: str | None = None,
    period: str | None = None,
) -> dict[str, Any]:
    """构建未知百度账户报告结构。"""
    pid = config.get("project_id", "")
    pname = config.get("project_name", "")

    unknown_list = parsed.get("unknown_accounts", []) or []
    # 加上 suggestion 字段
    enriched: list[dict[str, Any]] = []
    for item in unknown_list:
        entry = dict(item)
        if "suggestion" not in entry:
            entry["suggestion"] = (
                f"请在 configs/projects/{pid}.json 和 Excel 中补充账户区域"
                if pid else "请在项目配置和 Excel 中补充账户区域"
            )
        enriched.append(entry)

    return {
        "date": date,
        "task": task,
        "period": period,
        "project_id": pid,
        "project_name": pname,
        "unknown_accounts": enriched,
    }


def write_unknown_baidu_accounts_report(root: str | Path, report: dict[str, Any]) -> str | None:
    """写入未知百度账户报告。

    如果 unknown_accounts 为空，不写文件，返回 None。
    如果有未知账户，写入 reports/unknown_baidu_accounts.json。
    """
    unknown_list = report.get("unknown_accounts", []) or []
    if not unknown_list:
        return None

    root_path = Path(root)
    out_path = root_path / OUTPUT_FILE
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out_path)


# ── 终端提醒 ──────────────────────────────────────────────

def has_unknown_baidu_accounts(baidu_report: dict[str, Any]) -> bool:
    """百度报告中是否存在有数据的未知账户。"""
    unknown = baidu_report.get("unknown_accounts", []) or []
    return len(unknown) > 0


def format_unknown_baidu_accounts_notice(baidu_report: dict[str, Any]) -> list[str]:
    """生成终端简洁提醒行列表。"""
    unknown = baidu_report.get("unknown_accounts", []) or []
    if not unknown:
        return []

    lines = ["发现未配置百度账户，已单独隔离，不影响本次写入"]
    for item in unknown:
        name = item.get("account_name", "?")
        imp = item.get("展现", 0) or 0
        click = item.get("点击", 0) or 0
        cost = item.get("消费", 0) or 0
        lines.append(f"账户名：{name}，展现：{imp}，点击：{click}，消费：{cost}")
    return lines


def print_unknown_baidu_accounts_notice(baidu_report: dict[str, Any]) -> None:
    """使用 console_ui 输出未知账户提醒。"""
    lines = format_unknown_baidu_accounts_notice(baidu_report)
    if not lines:
        return

    from modules.console_ui import print_warning, print_quiet_line, verbose_print

    print_warning(lines[0])
    for line in lines[1:]:
        print_quiet_line(f"  {line}")

    unknown_path = baidu_report.get("unknown_accounts_report")
    if unknown_path:
        verbose_print(f"未知账户报告已保存：{unknown_path}")
