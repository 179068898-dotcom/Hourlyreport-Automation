from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from modules.baidu_parser import extract_baidu_rows_from_visible_text, parse_baidu_table
from modules.browser_manager import BrowserLaunchError, launch_chrome_context
from modules.validators import get_required_accounts, validate_baidu_report


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _empty_report(config: dict[str, Any], period: str | None) -> dict[str, Any]:
    return {
        "date": date.today().isoformat(),
        "period": period or "15点",
        "accounts": {},
        "exceptions": [],
        "errors": [],
        "self_check": {
            "playwright_available": False,
            "browser_opened": False,
            "manual_enter_received": False,
            "parsed_three_accounts": False,
            "all_fields_numeric": False,
            "wrote_excel": False,
        },
        "expected_accounts": list(config.get("accounts", {}).keys()),
    }


def _extract_table_rows(page) -> list[dict[str, Any]]:
    return page.evaluate(
        """
        () => {
          const tables = Array.from(document.querySelectorAll('table'));
          const result = [];
          for (const table of tables) {
            const headerCells = Array.from(table.querySelectorAll('thead tr:last-child th'));
            const fallbackHeaderCells = Array.from(table.querySelectorAll('tr:first-child th, tr:first-child td'));
            const headers = (headerCells.length ? headerCells : fallbackHeaderCells)
              .map(cell => (cell.innerText || cell.textContent || '').trim());
            if (!headers.length) continue;
            const bodyRows = Array.from(table.querySelectorAll('tbody tr'));
            const rows = bodyRows.length ? bodyRows : Array.from(table.querySelectorAll('tr')).slice(1);
            for (const tr of rows) {
              const cells = Array.from(tr.querySelectorAll('td, th'))
                .map(cell => (cell.innerText || cell.textContent || '').trim());
              if (!cells.some(Boolean)) continue;
              const row = {};
              headers.forEach((header, index) => {
                row[header || `列${index + 1}`] = cells[index] || '';
              });
              result.push(row);
            }
          }
          const grids = Array.from(document.querySelectorAll('[role="table"], [role="grid"]'));
          for (const grid of grids) {
            const headerNodes = Array.from(grid.querySelectorAll('[role="columnheader"]'));
            const headers = headerNodes.map(cell => (cell.innerText || cell.textContent || '').trim());
            if (!headers.length) continue;
            const rows = Array.from(grid.querySelectorAll('[role="row"]'));
            for (const rowNode of rows) {
              const cells = Array.from(rowNode.querySelectorAll('[role="gridcell"], [role="cell"], td'))
                .map(cell => (cell.innerText || cell.textContent || '').trim());
              if (!cells.some(Boolean) || cells.length < 2) continue;
              const row = {};
              headers.forEach((header, index) => {
                row[header || `列${index + 1}`] = cells[index] || '';
              });
              result.push(row);
            }
          }
          return result;
        }
        """
    )


def _dump_visible_text(root: Path, page) -> Path:
    out = root / "reports" / "baidu_page_text_dump.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = _read_visible_text(page)
    out.write_text(text, encoding="utf-8")
    return out


def _read_visible_text(page) -> str:
    return page.locator("body").inner_text(timeout=10000)


def _extract_selected_date_from_text(text: str) -> str | None:
    match = re.search(r"\b(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\b", text)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _write_debug_artifacts(root: Path, page, report: dict[str, Any], include_screenshot: bool = False) -> None:
    html_path = root / "reports" / "baidu_debug.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    png_path = root / "reports" / "baidu_debug.png"
    html_path.write_text(page.content(), encoding="utf-8")
    report["exceptions"].append({"type": "debug_html", "path": str(html_path)})
    if include_screenshot:
        page.screenshot(path=str(png_path), full_page=True)
        report["exceptions"].append({"type": "debug_png", "path": str(png_path)})


def _write_report(root: Path, config: dict[str, Any], report: dict[str, Any]) -> Path:
    output = _resolve_path(root, config.get("baidu", {}).get("output_path", "reports/baidu_account_data.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def fetch_baidu_account_report(
    config: dict[str, Any],
    root: Path,
    logger,
    period: str | None = None,
) -> dict[str, Any]:
    report = _empty_report(config, period)
    baidu_config = config.get("baidu", {})

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        report["errors"].append(f"Playwright 未安装，无法打开百度后台：{exc}")
        _write_report(root, config, report)
        logger.error("Playwright 未安装，fetch-baidu 已输出错误报告。")
        return report

    report["self_check"]["playwright_available"] = True
    start_url = baidu_config.get("start_url", "https://yingxiao.baidu.com/")

    with sync_playwright() as playwright:
        context = None
        try:
            context, page = launch_chrome_context(playwright, config, root)
        except BrowserLaunchError as exc:
            report["errors"].append(str(exc))
            _write_report(root, config, report)
            logger.error("百度 Chrome 浏览器启动失败：%s", exc)
            return report
        report["self_check"]["browser_opened"] = True
        page.bring_to_front()
        logger.info("已连接百度读取页面：%s", page.url or start_url)

        from modules.console_ui import print_quiet_line, print_warning

        print_quiet_line("")
        print_warning("请在已打开的 Chrome 中人工登录百度营销后台。")
        print_quiet_line('进入 数据 -> 账户报告，选择今天日期，并全选三个账户。')
        print_quiet_line('确认当前页面已经显示账户报告表格后，回到此终端按回车开始读取。')
        input("准备好后按回车读取当前页面 DOM 表格...")
        report["self_check"]["manual_enter_received"] = True

        text_dump = _dump_visible_text(root, page)
        report["exceptions"].append({"type": "visible_text_dump", "path": str(text_dump)})
        visible_text = text_dump.read_text(encoding="utf-8")
        selected_date = _extract_selected_date_from_text(visible_text)
        if selected_date:
            report["date"] = selected_date
            report["self_check"]["selected_date_found"] = True
            report["self_check"]["selected_date_is_today"] = selected_date == date.today().isoformat()
            if not report["self_check"]["selected_date_is_today"]:
                report["errors"].append(f"百度页面选择日期不是今天：页面日期 {selected_date}，今天 {date.today().isoformat()}")
        else:
            report["self_check"]["selected_date_found"] = False
            report["self_check"]["selected_date_is_today"] = False
            report["errors"].append("未能从百度页面识别已选择日期")
        dom_rows = _extract_table_rows(page)
        text_rows = extract_baidu_rows_from_visible_text(visible_text)
        rows = text_rows or dom_rows
        report["dom_table_row_count"] = len(dom_rows)
        report["text_table_row_count"] = len(text_rows)
        report["parse_source"] = "visible_text" if text_rows else "dom"
        parsed = parse_baidu_table(rows, config)

        report["accounts"] = parsed.get("accounts", {})
        report["exceptions"].extend(parsed.get("exceptions", []))
        report["errors"].extend(parsed.get("errors", []))
        report["self_check"]["parsed_three_accounts"] = len(report["accounts"]) == len(config.get("accounts", {}))
        report["self_check"]["all_fields_numeric"] = not parsed.get("errors") and bool(report["accounts"])
        report["errors"].extend(error for error in validate_baidu_report(report, get_required_accounts(config)) if error not in report["errors"])

        if report["errors"]:
            report["errors"].append("当前页面未读取到完整的三个百度账户报告数据，已输出 HTML 和可见文本 dump。")
            _write_debug_artifacts(root, page, report, include_screenshot=bool(baidu_config.get("debug_screenshot", False)))

        _write_report(root, config, report)
        print_quiet_line("")
        print_quiet_line("百度读取报告已输出。Chrome 会保持打开，方便你检查页面。")
        print_quiet_line("检查完成后，可以手动关闭 Chrome，再回到此终端按回车结束程序。")
        input("按回车结束 fetch-baidu...")
    logger.info("百度账户数据报告已输出：%s", baidu_config.get("output_path", "reports/baidu_account_data.json"))
    return report
