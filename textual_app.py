from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Static

from modules.console_ui import format_done_time, get_condition_status
from modules.project_config import get_current_project
from modules.task_status import get_project_task_status, mark_daily_done, mark_hourly_done


ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

HOURLY_COMMANDS = {
    period: ("cmd.exe", "/c", str(ROOT / "run_openclaw_hourly.bat"), period)
    for period in ("11点", "15点", "18点")
}
DAILY_COMMAND = ("cmd.exe", "/c", str(ROOT / "run_openclaw_daily.bat"))
CHECK_COMMANDS = {
    "hourly-preflight": (str(PYTHON), "main.py", "--mode", "preflight", "--task", "hourly"),
    "daily-preflight": (str(PYTHON), "main.py", "--mode", "preflight", "--task", "daily"),
    "credentials": (str(PYTHON), "main.py", "--mode", "test-baidu-credentials"),
    "doctor": (str(PYTHON), "main.py", "--mode", "doctor"),
    "validate-project": (str(PYTHON), "main.py", "--mode", "validate-project"),
}


def _task_status_text(done: bool, completed_at: str | None) -> tuple[str, str]:
    return ("已完成", format_done_time(completed_at) or "-") if done else ("未完成", "-")


def mark_completed_report(root: Path, report_name: str, period: str | None = None) -> bool:
    """按既有菜单成功口径，用最终报告更新轻量任务完成状态。"""
    try:
        report = json.loads((root / "reports" / report_name).read_text(encoding="utf-8"))
        write_count = int(report.get("write_summary", {}).get("write_count", 0) or 0)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False

    project_id = str(report.get("project_id") or "")
    write_summary = report.get("write_summary", {})
    if (
        not report.get("passed")
        or not project_id
        or not write_summary.get("verification_passed")
        or write_count <= 0
    ):
        return False

    if period is None:
        mark_daily_done(root, project_id)
    elif period in HOURLY_COMMANDS:
        mark_hourly_done(root, project_id, period)
    else:
        return False
    return True


def build_status_renderable(root: Path = ROOT) -> Text:
    """读取首页摘要，不执行命令或修改任何配置。"""
    try:
        project = get_current_project(root)
    except Exception as exc:
        return Text(f"当前项目无法读取：{exc}", style="bold red")

    project_id = str(project.get("project_id") or "")
    project_name = str(project.get("project_name") or "未配置")
    excel = project.get("excel") if isinstance(project.get("excel"), dict) else {}
    excel_path = excel.get("path") or project.get("excel_path") or ""
    source_items = project.get("baidu_sources")
    source_count = len(source_items) if isinstance(source_items, list) and source_items else 1
    source_type = f"多百度来源 x{source_count}" if source_count > 1 else "单百度来源"
    accounts = project.get("excel_accounts", []) or project.get("accounts", [])
    account_count = len([
        item for item in accounts
        if isinstance(item, dict) and item.get("standard_name")
    ])
    condition_status = get_condition_status(root, project_id)
    status_styles = {"通过": "green", "注意": "yellow", "未通过": "red", "未检查": "dim"}

    status = get_project_task_status(root, project_id) if project_id else {}
    daily = status.get("daily", {})
    daily_text, daily_time = _task_status_text(bool(daily.get("done")), daily.get("last_success_time"))
    hourly = status.get("hourly", {})

    output = Text()
    output.append("当前项目：", style="bold")
    output.append(project_name, style="bold cyan")
    output.append(f"    项目ID：{project_id}\n", style="dim")
    output.append(f"来源类型：{source_type}    百度来源：{source_count} 个    写入账户：{account_count} 个\n")
    output.append(f"Excel：{Path(str(excel_path)).name if excel_path else '未配置'}\n", style="dim")
    output.append("条件项：")
    output.append(condition_status, style=status_styles.get(condition_status, "dim"))
    output.append("\n\n任务状态\n", style="bold")
    output.append(f"日报：{daily_text}  {daily_time}\n", style="green" if daily_text == "已完成" else "red")
    for period in ("11点", "15点", "18点"):
        item = hourly.get(period, {})
        label, completed_at = _task_status_text(bool(item.get("done")), item.get("last_success_time"))
        output.append(f"{period}：{label}  {completed_at}\n", style="green" if label == "已完成" else "red")
    return output


class ReportWorkbench(App[None]):
    TITLE = "百度竞价自动化工作台"
    SUB_TITLE = "独立终端入口"
    BINDINGS = [
        ("q", "quit", "退出"),
        ("r", "refresh_status", "刷新状态"),
        ("c", "clear_log", "清空日志"),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }
    #content {
        height: 1fr;
        padding: 1;
    }
    #status {
        width: 38%;
        height: 100%;
        border: round $accent;
        padding: 1 2;
    }
    #actions {
        width: 62%;
        height: 100%;
        margin-left: 1;
    }
    .action-panel {
        height: auto;
        border: round $surface-lighten-2;
        padding: 1;
        margin-bottom: 1;
    }
    .section-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    Button {
        margin: 0 1 1 0;
        min-width: 18;
    }
    #daily-date {
        width: 24;
        margin-bottom: 1;
    }
    #output {
        height: 15;
        border: round $accent;
        margin: 0 1 1 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._task_running = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="content"):
            yield Static(build_status_renderable(), id="status")
            with Vertical(id="actions"):
                with Vertical(classes="action-panel"):
                    yield Label("小时报", classes="section-title")
                    with Horizontal():
                        yield Button("运行 11点小时报", id="hourly-11", variant="primary")
                        yield Button("运行 15点小时报", id="hourly-15", variant="primary")
                        yield Button("运行 18点小时报", id="hourly-18", variant="primary")
                with Vertical(classes="action-panel"):
                    yield Label("日报", classes="section-title")
                    yield Button("运行昨日日报", id="daily-yesterday", variant="primary")
                    yield Input(placeholder="YYYY-MM-DD", id="daily-date")
                    yield Button("运行指定日期日报", id="daily-selected")
                with Vertical(classes="action-panel"):
                    yield Label("检查", classes="section-title")
                    with Horizontal():
                        yield Button("小时报预检", id="check-hourly")
                        yield Button("日报预检", id="check-daily")
                        yield Button("凭据检查", id="check-credentials")
                    with Horizontal():
                        yield Button("doctor", id="check-doctor")
                        yield Button("validate-project", id="check-project")
                with Vertical(classes="action-panel"):
                    yield Label("辅助", classes="section-title")
                    with Horizontal():
                        yield Button("打开 reports", id="open-reports")
                        yield Button("打开 logs", id="open-logs")
                        yield Button("刷新状态", id="refresh")
                        yield Button("退出", id="exit")
        yield RichLog(id="output", highlight=True, markup=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self._log("工作台已就绪，所有任务均需手动启动。")

    def _log(self, message: str) -> None:
        self.query_one("#output", RichLog).write(message)

    def _refresh_status(self) -> None:
        self.query_one("#status", Static).update(build_status_renderable())

    def action_refresh_status(self) -> None:
        self._refresh_status()
        self._log("状态已刷新。")

    def action_clear_log(self) -> None:
        self.query_one("#output", RichLog).clear()

    def _start_command(
        self,
        label: str,
        command: Iterable[str],
        completion_report: str | None = None,
        period: str | None = None,
    ) -> None:
        if self._task_running:
            self._log("已有任务运行中，请等待当前任务结束。")
            return
        self._task_running = True
        self.run_worker(
            self._execute_command(label, tuple(command), completion_report, period),
            name="command-runner",
            exclusive=False,
        )

    async def _read_output(self, stream: asyncio.StreamReader | None, prefix: str) -> None:
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                return
            self._log(prefix + line.decode("utf-8", errors="replace").rstrip())

    async def _execute_command(
        self,
        label: str,
        command: tuple[str, ...],
        completion_report: str | None = None,
        period: str | None = None,
    ) -> None:
        self._log("-" * 58)
        self._log(f"开始执行：{label}")
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(ROOT),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.gather(
                self._read_output(process.stdout, ""),
                self._read_output(process.stderr, "[stderr] "),
            )
            code = await process.wait()
            if code == 0:
                self._log(f"执行成功，返回码：{code}")
                if completion_report:
                    if mark_completed_report(ROOT, completion_report, period):
                        self._log("写入复核通过，已标记任务完成。")
                    else:
                        self._log("最终报告未满足完成标记条件，任务状态未更新。")
            else:
                self._log(f"执行失败，返回码：{code}")
        except Exception as exc:
            self._log(f"执行异常：{exc}")
        finally:
            self._task_running = False
            self._refresh_status()

    def _open_folder(self, folder_name: str) -> None:
        folder = ROOT / folder_name
        if not folder.exists():
            self._log(f"目录不存在：{folder}")
            return
        try:
            os.startfile(str(folder))
            self._log(f"已打开目录：{folder_name}")
        except OSError as exc:
            self._log(f"无法打开目录：{exc}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("hourly-"):
            period = {"hourly-11": "11点", "hourly-15": "15点", "hourly-18": "18点"}[button_id]
            self._start_command(
                f"{period}小时报",
                HOURLY_COMMANDS[period],
                completion_report="final_run_report.json",
                period=period,
            )
        elif button_id == "daily-yesterday":
            self._start_command("昨日日报", DAILY_COMMAND, completion_report="daily_final_run_report.json")
        elif button_id == "daily-selected":
            target_date = self.query_one("#daily-date", Input).value.strip()
            try:
                datetime.strptime(target_date, "%Y-%m-%d")
            except ValueError:
                self._log("请输入有效日期，格式为 YYYY-MM-DD。")
                return
            self._start_command(
                f"{target_date} 日报",
                (*DAILY_COMMAND, target_date),
                completion_report="daily_final_run_report.json",
            )
        elif button_id == "check-hourly":
            self._start_command("小时报预检", CHECK_COMMANDS["hourly-preflight"])
        elif button_id == "check-daily":
            self._start_command("日报预检", CHECK_COMMANDS["daily-preflight"])
        elif button_id == "check-credentials":
            self._start_command("凭据检查", CHECK_COMMANDS["credentials"])
        elif button_id == "check-doctor":
            self._start_command("doctor", CHECK_COMMANDS["doctor"])
        elif button_id == "check-project":
            self._start_command("validate-project", CHECK_COMMANDS["validate-project"])
        elif button_id == "open-reports":
            self._open_folder("reports")
        elif button_id == "open-logs":
            self._open_folder("logs")
        elif button_id == "refresh":
            self.action_refresh_status()
        elif button_id == "exit":
            self.exit()


if __name__ == "__main__":
    ReportWorkbench().run()
