"""统一终端输出样式，支持颜色和降级。

所有 CMD 输出都通过本模块，确保菜单、doctor、日报/小时报流程、
Chrome 检查、Excel 写入提示等输出风格一致。

颜色通过 colorama 实现；colorama 不可用时自动降级为无颜色输出。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from io import StringIO
from pathlib import Path
from typing import Any, Callable

# ── 颜色支持 ──────────────────────────────────────────────
try:
    from colorama import Fore, Style, init as _colorama_init
    _colorama_init(autoreset=True)
    _HAS_COLOR = True
except ImportError:
    _HAS_COLOR = False

    class _NoopStyle:
        """colorama 不可用时的空样式占位。"""
        RESET_ALL = ""
        BRIGHT = ""
        DIM = ""
        NORMAL = ""

    class _NoopFore:
        BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = ""
        LIGHTBLACK_EX = LIGHTRED_EX = LIGHTGREEN_EX = LIGHTYELLOW_EX = ""
        LIGHTBLUE_EX = LIGHTMAGENTA_EX = LIGHTCYAN_EX = LIGHTWHITE_EX = ""

    Fore = _NoopFore()
    Style = _NoopStyle()

# ── Rich 可选展示 ──────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False


# ── 内部状态 ──────────────────────────────────────────────
_verbose = False
_output_func: Callable[[str], None] = print


def set_verbose(enabled: bool) -> None:
    """开启/关闭详细输出模式（--verbose）。"""
    global _verbose
    _verbose = enabled


def is_verbose() -> bool:
    """返回当前是否为详细输出模式。"""
    return _verbose


def set_output_func(func: Callable[[str], None]) -> None:
    """替换输出函数（测试时可用 StringIO 捕获输出）。"""
    global _output_func
    _output_func = func


def _emit(text: str) -> None:
    _output_func(text)


def _emit_rich(renderable: Any) -> bool:
    """渲染 Rich 组件；依赖不可用时由调用方输出纯文本。"""
    if not _HAS_RICH:
        return False
    stream = StringIO()
    terminal_output = _output_func is print
    console = Console(
        file=stream,
        force_terminal=terminal_output,
        color_system="auto" if terminal_output else None,
        width=76,
    )
    console.print(renderable)
    for line in stream.getvalue().rstrip("\n").splitlines():
        _emit(line)
    return True


# ── 颜色快捷方式 ──────────────────────────────────────────
def _green(text: str) -> str:
    return f"{Fore.GREEN}{text}{Style.RESET_ALL}" if _HAS_COLOR else text


def _red(text: str) -> str:
    return f"{Fore.RED}{text}{Style.RESET_ALL}" if _HAS_COLOR else text


def _yellow(text: str) -> str:
    return f"{Fore.YELLOW}{text}{Style.RESET_ALL}" if _HAS_COLOR else text


def _cyan(text: str) -> str:
    return f"{Fore.CYAN}{text}{Style.RESET_ALL}" if _HAS_COLOR else text


def _bright(text: str) -> str:
    return f"{Style.BRIGHT}{text}{Style.RESET_ALL}" if _HAS_COLOR else text


def _dim(text: str) -> str:
    return f"{Style.DIM}{text}{Style.RESET_ALL}" if _HAS_COLOR else text


# ── 通用工具 ──────────────────────────────────────────────
def _shorten_path(path: str | Path, max_len: int = 68) -> str:
    """超长路径中间缩略，保留首尾可识别部分。"""
    s = str(path)
    if len(s) <= max_len:
        return s
    head = s[:24]
    tail = s[-(max_len - 27):]
    return f"{head}...{tail}"


def _get_version(root: Path | None = None) -> str:
    """读取版本号：优先 VERSION 文件，其次 git tag，兜底 v0.4.8。"""
    if root and (root / "VERSION").exists():
        return (root / "VERSION").read_text(encoding="utf-8").strip()
    try:
        import subprocess
        result = subprocess.run(
            ["git", "tag", "--sort=-v:refname"],
            capture_output=True, text=True, timeout=3,
            cwd=str(root) if root else None,
        )
        if result.returncode == 0 and result.stdout.strip():
            first_tag = result.stdout.strip().splitlines()[0]
            return first_tag.lstrip("v")
    except Exception:
        pass
    return "2.0"


def _truncate_excel_name(path: str) -> str:
    """从完整 Excel 路径中提取文件名。"""
    return Path(path).name


def get_condition_status(root: Path | None, project_id: str) -> str:
    """从当前项目最近一次检查报告读取首页提示状态，不触发实际检查。"""
    if not root or not project_id:
        return "未检查"
    report_dir = Path(root) / "reports"
    candidates = [report_dir / "doctor_report.json", report_dir / "preflight_report.json"]
    candidates = [path for path in candidates if path.exists()]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            report = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if report.get("project_id") != project_id:
            continue
        if report.get("mode") == "preflight":
            return "通过" if report.get("passed") else "未通过"
        checks = list((report.get("checks") or {}).values())
        if report.get("summary", {}).get("all_passed"):
            return "通过"
        failures = [item for item in checks if not item.get("passed")]
        if failures and all(item.get("level") == "warning" for item in failures):
            return "注意"
        return "未通过"
    return "未检查"


def _status_text(value: str) -> Text:
    styles = {"通过": "green", "已完成": "green", "注意": "yellow", "未通过": "red", "未完成": "red", "未检查": "dim"}
    return Text(value, style=styles.get(value, "dim"))


# ── 时间格式化 ──────────────────────────────────────────────
def format_done_time(value: str | None) -> str:
    """从 last_success_time 提取 HH:mm 格式。

    支持：2026-05-10 10:02:33 / 2026-05-10T10:02:33 / 10:02
    异常或为空时返回空字符串。
    """
    if not value:
        return ""
    try:
        if " " in value:
            parts = value.split(" ")
            if len(parts) >= 2 and ":" in parts[1]:
                return parts[1][:5]
        if "T" in value:
            time_part = value.split("T")[1]
            if ":" in time_part:
                return time_part[:5]
        if ":" in value and len(value) <= 5:
            return value
    except Exception:
        pass
    return ""


# ── 屏幕控制 ──────────────────────────────────────────────
def clear_screen() -> None:
    """清屏（跨平台）。"""
    if sys.platform == "win32":
        os.system("cls")
    else:
        os.system("clear")


# ── 标题和横幅 ────────────────────────────────────────────
def print_banner(project: dict[str, Any] | None = None,
                 version: str | None = None,
                 root: Path | None = None) -> None:
    """打印启动横幅：工具名、版本、当前项目、目标 Excel。"""
    ver = version or _get_version(root)
    width = 60
    term_width = shutil.get_terminal_size().columns
    if term_width < width:
        width = term_width - 2

    excel = {}
    if project:
        excel = project.get("excel", {}) if isinstance(project.get("excel"), dict) else {}
    excel_path = excel.get("path") or (project or {}).get("excel_path", "")

    if _HAS_RICH:
        body = Text()
        body.append("百度竞价自动化控制台", style="bold cyan")
        body.append(f"  v{ver}", style="dim")
        if project:
            body.append(f"\n当前项目：{project.get('project_name', '')}", style="bold")
            if excel_path:
                body.append(f"\nExcel：{_truncate_excel_name(excel_path)}", style="dim")
        body.append("\n日志：logs/run.log", style="dim")
        if _emit_rich(Panel(body, border_style="cyan")):
            _emit("")
            return

    sep = _bright("  " + "=" * (width - 4))
    _emit("")
    _emit(sep)
    _emit(_bright(f"   百度竞价自动化控制台  v{ver}"))
    _emit(sep)
    if project:
        _emit(f"   项目：{_cyan(project.get('project_name', ''))}")
        if excel_path:
            _emit(f"   Excel：{_dim(_truncate_excel_name(excel_path))}")
    _emit(f"   日志：{_dim('logs/run.log')}")
    _emit(sep)
    _emit("")


def print_main_menu(project: dict[str, Any] | None = None,
                    root: Path | None = None) -> None:
    """打印仅包含导航入口的首页菜单。"""
    _emit("  1. 小时报")
    _emit("  2. 日报")
    _emit("  3. 切换项目")
    _emit("  4. 检查条件项")
    _emit("  5. 更多功能")
    _emit("  0. 退出")
    _emit(_dim("  R. 刷新状态"))
    _emit("")


def print_sub_menu_hourly(root: Path | None = None, project_id: str = "") -> None:
    """打印小时报时段子菜单，含完成状态和时间。"""
    from modules.task_status import get_project_task_status

    _emit("")
    _emit(_bright("  小时报"))
    _emit("  " + "-" * 40)
    for idx, period in enumerate(["11点", "15点", "18点"], start=1):
        done = False
        time_str = ""
        if root and project_id:
            try:
                st = get_project_task_status(root, project_id)
                h = st.get("hourly", {}).get(period, {})
                done = h.get("done", False)
                if done:
                    time_str = format_done_time(h.get("last_success_time"))
            except Exception:
                pass
        if done and time_str:
            status = f"{_green('[已完成]')} (完成于：{time_str})"
        elif done:
            status = _green("[已完成]")
        else:
            status = _red("[未完成]")
        _emit(f"  {idx}. {period}    {status}")
    _emit("  " + "-" * 40)
    _emit("  0. 返回")
    _emit("")


def print_project_list(projects: list[dict[str, str]],
                       root: Path | None = None) -> None:
    """打印项目列表供用户选择。"""
    from modules.task_status import get_project_task_status

    _emit("")
    _emit(_bright("  项目列表"))
    _emit("  " + "-" * 58)
    if not projects:
        _emit("  没有可用的项目。")
        _emit("  " + "-" * 58)
        _emit("  0. 返回")
        _emit("")
        return
    for idx, proj in enumerate(projects, start=1):
        pid = proj.get("project_id", "")
        pname = proj.get("project_name", "")
        status_str = ""
        if root:
            try:
                st = get_project_task_status(root, pid)
                # 日报
                daily = st.get("daily", {})
                if daily.get("done"):
                    dt = format_done_time(daily.get("last_success_time"))
                    daily_tag = f"{_green(dt)}" if dt else _green("已完成")
                else:
                    daily_tag = _dim("未完成")
                # 小时报各时段
                hourly_parts = []
                for period in ["11点", "15点", "18点"]:
                    h = st.get("hourly", {}).get(period, {})
                    if h.get("done"):
                        ht = format_done_time(h.get("last_success_time"))
                        h_tag = f"{_green(ht)}" if ht else _green("已完成")
                    else:
                        h_tag = _dim("未完成")
                    hourly_parts.append(f"[{period}: {h_tag}]")
                status_str = f" [日报: {daily_tag}] " + " ".join(hourly_parts)
            except Exception:
                pass
        _emit(f"  {idx}. {pname}{status_str}")
    _emit("  " + "-" * 58)
    _emit("  0. 返回")
    _emit("")


def print_task_status_header(project: dict[str, Any], root: Path | None = None) -> None:
    """在主菜单顶部打印当前项目今日任务完成状态。"""
    from modules.task_status import get_project_task_status

    project_id = project.get("project_id", "")
    if not project_id or not root:
        return
    try:
        st = get_project_task_status(root, project_id)
    except Exception:
        return

    daily = st.get("daily", {})
    if daily.get("done"):
        dt = format_done_time(daily.get("last_success_time"))
        daily_status = "已完成"
    else:
        dt = ""
        daily_status = "未完成"
    rows = [("日报", daily_status, dt or "-")]
    for period in ["11点", "15点", "18点"]:
        h = st.get("hourly", {}).get(period, {})
        if h.get("done"):
            ht = format_done_time(h.get("last_success_time"))
            status = "已完成"
        else:
            ht = ""
            status = "未完成"
        rows.append((period, status, ht or "-"))

    if _HAS_RICH:
        table = Table(title="今日任务", header_style="bold", show_header=True, box=None)
        table.add_column("任务")
        table.add_column("状态")
        table.add_column("完成时间")
        for label, status, time_str in rows:
            table.add_row(label, _status_text(status), time_str)
        if _emit_rich(table):
            _emit("")
            return

    _emit("  今日任务")
    for label, status, time_str in rows:
        styled = _green(status) if status == "已完成" else _red(status)
        _emit(f"    {label}：{styled}  {time_str}")
    _emit("")


def print_console_context(project: dict[str, Any], root: Path | None = None) -> None:
    """打印首页当前项目摘要，不执行任何检查或外部动作。"""
    excel = project.get("excel", {}) if isinstance(project.get("excel"), dict) else {}
    excel_path = excel.get("path") or project.get("excel_path", "")
    sources = project.get("baidu_sources")
    source_count = len(sources) if isinstance(sources, list) else 1
    if isinstance(sources, list) and len(sources) > 1:
        project_type = f"多百度来源 x{len(sources)}"
    else:
        project_type = "单百度来源"
    accounts = project.get("excel_accounts", []) or project.get("accounts", [])
    account_count = len([item for item in accounts if isinstance(item, dict) and item.get("standard_name")])
    condition_status = get_condition_status(root, str(project.get("project_id") or ""))

    if _HAS_RICH:
        body = Text()
        body.append("当前项目：", style="bold")
        body.append(str(project.get("project_name", "")), style="bold")
        body.append(f"    类型：{project_type}")
        if source_count > 1:
            body.append(f"    写入账户：{account_count} 个")
        body.append(f"\n项目 ID：{project.get('project_id', '')}", style="dim")
        body.append(f"\nExcel：{_truncate_excel_name(excel_path) if excel_path else '未配置'}", style="dim")
        body.append("\n条件项：")
        body.append_text(_status_text(condition_status))
        if _emit_rich(Panel(body, title="百度竞价自动化控制台", border_style="dim")):
            _emit("")
            return

    _emit("")
    _emit("  百度竞价自动化控制台")
    _emit(
        f"  当前项目：{project.get('project_name', '')}    类型：{project_type}"
    )
    if source_count > 1:
        _emit(f"  写入账户：{account_count} 个")
    _emit(f"  项目 ID：{project.get('project_id', '')}")
    _emit(f"  Excel：{_truncate_excel_name(excel_path) if excel_path else '未配置'}")
    _emit(f"  条件项：{condition_status}")
    _emit("")


def print_project_info(project: dict[str, Any]) -> None:
    """打印当前项目的简洁摘要 — 只显示同事需要关注的字段。"""
    excel = project.get("excel", {}) if isinstance(project.get("excel"), dict) else {}
    sheets = project.get("sheets", {}) or {}
    kst = project.get("kst", {}) or {}
    baidu_cfg = project.get("baidu", {}) or {}

    excel_path = excel.get("path") or project.get("excel_path", "")
    kst_dir = kst.get("export_dir", "")

    _emit("")
    _emit(_bright("  项目信息"))
    _emit("  " + "-" * 58)
    _emit(f"  项目：{project.get('project_name', '')}")
    _emit(f"  Excel：{_truncate_excel_name(excel_path) if excel_path else '未配置'}")
    _emit(f"  日报 sheet：{_dim(excel.get('daily_sheet') or sheets.get('daily', ''))}")
    _emit(f"  小时报 sheet：{_dim(excel.get('hourly_sheet') or sheets.get('hourly', ''))}")
    _emit(f"  商务通目录：{kst_dir if kst_dir else '未配置'}")
    _emit(f"  凭据：{_dim(baidu_cfg.get('credential_profile', ''))}")
    _emit("  " + "-" * 58)
    _emit("  0. 返回")
    _emit("")


def print_header(title: str) -> None:
    """打印加粗标题头。"""
    _emit("")
    _emit(_bright(title))


def print_project_summary(project: dict[str, Any]) -> None:
    """打印项目摘要（旧接口，保持兼容）。"""
    excel = project.get("excel", {}) if isinstance(project.get("excel"), dict) else {}
    _emit(f"  项目：{project.get('project_name', '')}")
    _emit(f"  配置：{_shorten_path(project.get('_config_path', ''))}")
    _emit(f"  Excel：{excel.get('path') or project.get('excel_path', '')}")


# ── 确认面板 ──────────────────────────────────────────────
def print_confirm_panel(task_info: dict[str, Any]) -> None:
    """打印确认清单面板。

    task_info 应包含：
    - task_name: 任务名称
    - project_name: 项目名称
    - date: 目标日期
    - period: 时段
    - sheet: 目标 sheet
    - excel_path: Excel 路径
    - kst_file: 快商通文件路径
    - kst_is_stale: 是否过期（可选）
    """
    _emit("")
    _emit(_bright("  执行确认"))
    _emit("  " + "-" * 58)
    lines = []
    if task_info.get("task_name"):
        lines.append(f"  任务：{_cyan(task_info['task_name'])}")
    if task_info.get("project_name"):
        lines.append(f"  项目：{task_info['project_name']}")
    if task_info.get("date"):
        label = f"  日期：{task_info['date']}"
        if task_info.get("period"):
            label += f"    时段：{task_info['period']}"
        lines.append(label)
    elif task_info.get("period"):
        lines.append(f"  时段：{task_info['period']}")
    if task_info.get("excel_path"):
        lines.append(f"  Excel：{_truncate_excel_name(task_info['excel_path'])}")
    if task_info.get("kst_file"):
        lines.append(f"  商务通：{_truncate_excel_name(task_info['kst_file'])}")
        if task_info.get("kst_is_stale"):
            lines.append(f"    {_yellow('[注意] 导出文件已超过 30 分钟，自动发现时会按 0 对话处理')}")
    if task_info.get("already_done"):
        lines.append(f"    {_yellow('[注意] 今天已成功写入过，仍可继续执行')}")
    _emit("\n".join(lines))
    _emit("  " + "-" * 58)
    _emit("")
    _emit("  回车执行  /  0 返回")


# ── 检查表格 ──────────────────────────────────────────────
def print_check_table(title: str, checks: list[dict[str, Any]]) -> None:
    """以紧凑表格形式打印检查结果。

    每项格式：[状态] 检查项  说明
    状态通过=绿色通过，失败=红色失败，注意=黄色注意
    """
    _emit("")
    _emit(_bright(f"  {title}"))
    _emit("  " + "-" * 58)
    passed = 0
    failed = 0
    warned = 0
    for item in checks:
        name = item.get("name", "")
        status = item.get("status", "warn")
        message = item.get("message", "")
        if status == "pass":
            prefix = _green("[通过]")
            passed += 1
        elif status == "fail":
            prefix = _red("[失败]")
            failed += 1
        else:
            prefix = _yellow("[注意]")
            warned += 1
        _emit(f"  {prefix} {_dim(name + '：') if message else name}{message}")
    _emit("  " + "-" * 58)
    total = passed + failed + warned
    summary_parts = [f"{total}/{total} 通过" if failed + warned == 0
                     else f"{passed}/{total} 通过"]
    if failed:
        summary_parts.append(f"{failed} 失败")
    if warned:
        summary_parts.append(f"{warned} 需关注")
    _emit(f"  结果：{', '.join(summary_parts)}")
    _emit("")


# ── 检查单行（旧接口兼容）──────────────────────────────────
def print_check_result(name: str, status: str, message: str) -> None:
    """打印单行检查结果（旧接口，保持兼容）。"""
    if status == "pass":
        prefix = _green("[通过]")
    elif status == "fail":
        prefix = _red("[失败]")
    elif status == "skip":
        prefix = _dim("[跳过]")
    else:
        prefix = _yellow("[注意]")
    _emit(f"  {prefix} {name}：{message}")


# ── 步骤输出 ──────────────────────────────────────────────
def print_step(step_no: int, total: int, title: str) -> None:
    """打印步骤标题：[1/4] 步骤名称"""
    _emit("")
    _emit(_bright(f"  [{step_no}/{total}] {title}"))


def print_step_success(message: str) -> None:
    """打印步骤成功消息。"""
    _emit(f"  {_green('[通过]')} {message}")


def print_step_failure(message: str, suggestion: str | None = None,
                       report_path: str | None = None,
                       log_path: str | None = None) -> None:
    """打印步骤失败消息，含建议、报告路径、日志路径。"""
    _emit("")
    _emit(f"  {_red('[失败]')} {message}")
    if suggestion:
        _emit(f"  {_dim('原因：')}{suggestion}")
    if report_path:
        _emit(f"  {_dim('报告：')}{report_path}")
    if log_path:
        _emit(f"  {_dim('日志：')}{log_path}")


# ── 最终总结 ──────────────────────────────────────────────
def print_final_success(summary: str) -> None:
    """打印最终成功信息。"""
    _emit("")
    _emit(_green(f"  {summary}"))


def print_final_failure(summary: str) -> None:
    """打印最终失败信息。"""
    _emit("")
    _emit(_red(f"  {summary}"))


def print_final_summary(summary: dict[str, Any]) -> None:
    """以紧凑格式打印最终执行摘要。"""
    _emit("")
    _emit(_bright("  执行摘要"))
    _emit("  " + "-" * 58)
    for key, value in summary.items():
        if value is not None and value != "":
            _emit(f"  {_dim(str(key) + '：')}{value}")
    _emit("  " + "-" * 58)
    _emit("")


# ── 键值表 ────────────────────────────────────────────────
def print_key_value_table(title: str, rows: list[tuple[str, Any]]) -> None:
    """打印键值对表格。"""
    _emit("")
    _emit(_bright(f"  {title}"))
    _emit("  " + "-" * 58)
    for label, value in rows:
        _emit(f"  {_dim(str(label) + '：')}{value}")
    _emit("  " + "-" * 58)
    _emit("")


def print_write_summary(write_count: int, overwrite_count: int,
                        verification_passed: bool) -> None:
    """打印写入总结。"""
    status = _green("复核通过") if verification_passed else _red("复核未通过")
    _emit(f"  {_green('[通过]')} 写入完成：{write_count} 个单元格，覆盖 {overwrite_count} 个，{status}")


def print_report_paths(paths: dict[str, str]) -> None:
    """打印报告文件路径列表。"""
    for label, path in paths.items():
        _emit(f"  {_dim(label + '：')}{path}")


# ── 确认 ──────────────────────────────────────────────────
def confirm_action(message: str) -> bool:
    """交互式确认：按 Enter 继续，q 退出。"""
    try:
        answer = input(f"{message} 按 Enter 继续；输入 q 退出：").strip().lower()
        return answer != "q"
    except (EOFError, KeyboardInterrupt):
        return False


# ── 安静行和调试输出 ──────────────────────────────────────
def print_quiet_line(message: str) -> None:
    """始终输出的简洁单行消息。"""
    _emit(f"  {message}")


def verbose_print(text: str) -> None:
    """仅在 --verbose 模式下输出。"""
    if _verbose:
        _emit(f"  {_dim(text)}")


# ── 兼容旧入口 ────────────────────────────────────────────
def print_success(message: str) -> None:
    """打印成功消息（绿色）。"""
    _emit(f"  {_green('[通过]')} {message}")


def print_warning(message: str) -> None:
    """打印警告消息（黄色）。"""
    _emit(f"  {_yellow('[注意]')} {message}")


def print_error(message: str) -> None:
    """打印错误消息（红色）。"""
    _emit(f"  {_red('[失败]')} {message}")


# ── 自动打开 Excel ─────────────────────────────────────────
def try_open_excel(excel_path: str | Path) -> bool:
    """尝试用系统默认程序打开 Excel 文件（仅 Windows）。

    返回 True 表示打开成功或已跳过，False 表示打开失败。
    """
    path_str = str(excel_path)
    if not path_str:
        return False
    if not Path(path_str).exists():
        return False
    if sys.platform != "win32":
        return False
    try:
        os.startfile(path_str)
        return True
    except Exception:
        return False


def print_auto_open_result(opened: bool) -> None:
    """打印 Excel 自动打开结果。"""
    if opened:
        _emit(f"  {_green('[通过]')} 已打开 Excel 文件，请检查数据")
    else:
        _emit(f"  {_yellow('[注意]')} Excel 文件自动打开失败，请手动打开查看")
