"""统一终端输出样式，支持颜色和降级。

所有 CMD 输出都通过本模块，确保菜单、doctor、日报/小时报流程、
Chrome 检查、Excel 写入提示等输出风格一致。

颜色通过 colorama 实现；colorama 不可用时自动降级为无颜色输出。
"""

from __future__ import annotations

import os
import shutil
import sys
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
    return "0.4.8"


def _truncate_excel_name(path: str) -> str:
    """从完整 Excel 路径中提取文件名。"""
    return Path(path).name


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

    _emit("")
    _emit(_bright("  " + "=" * (width - 4)))
    _emit(_bright(f"   百度竞价日报 / 小时报自动化助手  v{ver}"))
    _emit(_bright("  " + "=" * (width - 4)))
    if project:
        _emit(f"   当前项目：{_cyan(project.get('project_name', ''))}")
        if excel_path:
            _emit(f"   目标表格：{_dim(_truncate_excel_name(excel_path))}")
    _emit(f"   详细日志：{_dim('logs/run.log')}")
    _emit(_bright("  " + "=" * (width - 4)))
    _emit("")


def print_main_menu(project: dict[str, Any] | None = None) -> None:
    """打印主菜单。"""
    _emit("  1. 小时报")
    _emit("  2. 日报")
    _emit("  3. 下一个项目")
    _emit("  4. 项目信息")
    _emit("  5. 文件合格校验")
    _emit("  0. 退出")
    _emit("")


def print_sub_menu_hourly() -> None:
    """打印小时报时段子菜单。"""
    _emit("")
    _emit("  请选择小时报时段：")
    _emit("  1. 11点")
    _emit("  2. 15点")
    _emit("  3. 18点")
    _emit("  0. 返回主菜单")
    _emit("")


def print_project_info(project: dict[str, Any]) -> None:
    """打印当前项目的简洁摘要。"""
    excel = project.get("excel", {}) if isinstance(project.get("excel"), dict) else {}
    sheets = project.get("sheets", {}) or {}
    kst = project.get("kst", {}) or {}
    baidu_cfg = project.get("baidu", {}) or {}

    _emit("")
    _emit(_bright("  项目信息"))
    _emit("  " + "-" * 58)
    rows = [
        ("项目名称", project.get("project_name", "")),
        ("项目 ID", project.get("project_id", "")),
        ("配置文件", _shorten_path(project.get("_config_path", ""))),
        ("目标 Excel", excel.get("path") or project.get("excel_path", "")),
        ("小时报 sheet", excel.get("hourly_sheet") or sheets.get("hourly", "")),
        ("日报 sheet", excel.get("daily_sheet") or sheets.get("daily", "")),
        ("商务通目录", kst.get("export_dir", "")),
        ("百度凭据 profile", baidu_cfg.get("credential_profile", "")),
    ]
    for label, value in rows:
        if value:
            _emit(f"  {_dim(label + '：')}{value}")
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
    if task_info.get("project_name"):
        lines.append(f"  项目：{task_info['project_name']}")
    if task_info.get("task_name"):
        lines.append(f"  任务：{_cyan(task_info['task_name'])}")
    if task_info.get("excel_path"):
        lines.append(f"  目标表格：{_truncate_excel_name(task_info['excel_path'])}")
    if task_info.get("sheet"):
        lines.append(f"  目标 sheet：{task_info['sheet']}")
    if task_info.get("date"):
        label = f"  日期：{task_info['date']}"
        if task_info.get("period"):
            label += f"  /  时段：{task_info['period']}"
        lines.append(label)
    elif task_info.get("period"):
        lines.append(f"  时段：{task_info['period']}")
    if task_info.get("kst_file"):
        lines.append(f"  商务通文件：{_truncate_excel_name(task_info['kst_file'])}")
        if task_info.get("kst_is_stale"):
            lines.append(f"    {_yellow('[注意] 快商通导出文件已超过 2 小时，请确认是否继续')}")
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
