from __future__ import annotations

import sys
from typing import Any, Callable

_verbose = False
_output_func: Callable[[str], None] = print


def set_verbose(enabled: bool) -> None:
    global _verbose
    _verbose = enabled


def is_verbose() -> bool:
    return _verbose


def set_output_func(func: Callable[[str], None]) -> None:
    global _output_func
    _output_func = func


def _emit(text: str) -> None:
    _output_func(text)


def verbose_print(text: str) -> None:
    if _verbose:
        _emit(text)


def print_header(title: str) -> None:
    _emit("")
    _emit(title)


def print_project_summary(project: dict[str, Any]) -> None:
    _emit(f"项目：{project.get('project_name', '')}")
    _emit(f"配置：{project.get('_config_path', '')}")
    _emit(f"Excel：{project.get('excel_path', '') or project.get('excel', {}).get('path', '')}")


def print_check_result(name: str, status: str, message: str) -> None:
    if status == "pass":
        _emit(f"  [通过] {name}：{message}")
    elif status == "fail":
        _emit(f"  [失败] {name}：{message}")
    elif status == "skip":
        _emit(f"  [跳过] {name}：{message}")
    else:
        _emit(f"  [注意] {name}：{message}")


def print_step(index: int, total: int, title: str) -> None:
    _emit(f"  [{index}/{total}] {title}")


def print_step_success(message: str) -> None:
    _emit(f"    [通过] {message}")


def print_step_failure(message: str, suggestion: str | None = None, report_path: str | None = None, log_path: str | None = None) -> None:
    _emit(f"    [失败] {message}")
    if suggestion:
        _emit(f"    建议：{suggestion}")
    if report_path:
        _emit(f"    报告：{report_path}")
    if log_path:
        _emit(f"    日志：{log_path}")

    if _verbose:
        return
    if not any(kw in (message or "").lower() for kw in ["json", "structure", "table", "row", "cell", "merge", "openpyxl", "traceback"]):
        return


def print_final_success(summary: str) -> None:
    _emit("")
    _emit(f"任务完成：{summary}")


def print_final_failure(summary: str) -> None:
    _emit("")
    _emit(f"任务失败：{summary}")


def confirm_action(message: str) -> bool:
    try:
        answer = input(f"{message} 按 Enter 继续；输入 q 退出：").strip().lower()
        return answer != "q"
    except (EOFError, KeyboardInterrupt):
        return False


def print_write_summary(write_count: int, overwrite_count: int, verification_passed: bool) -> None:
    _emit(f"  写入 {write_count} 个单元格，覆盖 {overwrite_count} 个已有值，复核{'通过' if verification_passed else '未通过'}")


def print_report_paths(paths: dict[str, str]) -> None:
    for label, path in paths.items():
        _emit(f"  {label}：{path}")
