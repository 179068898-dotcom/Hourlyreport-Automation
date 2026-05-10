from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from modules.chrome_debug import ensure_chrome_debug_ready
from modules.config_manager import load_config
from modules.console_ui import print_final_failure, print_final_success, print_header, print_project_summary
from modules.doctor import print_doctor_report, run_doctor
from modules.logger import setup_logger
from modules.project_config import (
    build_runtime_config_from_project,
    get_current_project,
    get_excel_path,
    list_projects,
    load_project_config,
    set_current_project,
)
from modules.run_pipeline import run_daily_pipeline, run_half_auto_pipeline


ROOT = Path(__file__).resolve().parent


MENU_TEXT = """
1. 运行日报
2. 运行小时报
3. 切换项目
4. 刷新当前项目
5. 检查运行环境
0. 退出
"""

HOURLY_MENU_TEXT = """
请选择小时报时段：
1. 11点
2. 3点
3. 6点
0. 返回主菜单
"""


def _resolve(root: Path, value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _default_daily_date(today: date | None = None) -> str:
    base = today or date.today()
    return (base - timedelta(days=1)).isoformat()


def build_runtime_config(project: dict[str, Any], base_config: dict[str, Any]) -> dict[str, Any]:
    return build_runtime_config_from_project(project, base_config)


def build_menu_header(root: Path, project: dict[str, Any]) -> str:
    excel_path = get_excel_path(project, root)
    config_path = project.get("_config_path") or ""
    return (
        "百度竞价日报 / 小时报自动化工具\n"
        f"项目：{project.get('project_name', '')}  |  "
        f"Excel：{excel_path}"
    )


def _latest_kst_export(root: Path, project: dict[str, Any]) -> Path | None:
    export_path = _resolve(root, project.get("kst", {}).get("export_dir"))
    if not export_path or not export_path.exists():
        return None
    if export_path.is_file():
        return export_path if export_path.suffix.lower() in {".xlsx", ".xls", ".csv"} else None
    export_dir = export_path
    files = [
        path for path in export_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".xlsx", ".xls", ".csv"}
    ]
    return max(files, key=lambda path: path.stat().st_mtime) if files else None


def _condition_lines(root: Path, project: dict[str, Any], latest: Path | None) -> list[str]:
    excel = project.get("excel", {}) if isinstance(project.get("excel"), dict) else {}
    excel_path = _resolve(root, excel.get("path") or project.get("excel_path"))
    kst_path = _resolve(root, project.get("kst", {}).get("export_dir"))
    return [
        "条件检查：",
        f"- 目标 Excel：{'通过' if excel_path and excel_path.exists() else '未找到'}",
        f"- 商务通导出目录/文件：{'通过' if kst_path and kst_path.exists() else '未找到'}",
        f"- 商务通导出文件：{'通过' if latest else '未找到'}",
    ]


def build_confirmation_lines(
    root: Path,
    project: dict[str, Any],
    task_name: str,
    *,
    target_date: str | None = None,
    period: str | None = None,
    sheet: str | None = None,
) -> list[str]:
    latest = _latest_kst_export(root, project)
    excel = project.get("excel", {}) if isinstance(project.get("excel"), dict) else {}
    sheet_name = sheet or excel.get("hourly_sheet") or project.get("sheets", {}).get("hourly", "时段数据")
    lines = [
        "",
        "执行确认",
        f"  项目：{project.get('project_name', '')}",
        f"  任务：{task_name}",
        f"  Excel：{excel.get('path') or project.get('excel_path', '')}",
        f"  sheet：{sheet_name}",
        f"  日期：{target_date or '无'}  /  时段：{period or '无'}",
        f"  快商通文件：{latest if latest else '未找到'}",
    ]
    lines.append("按 Enter 执行；输入 q 退出。")
    return lines


def _print_lines(lines: list[str], output_func: Callable[[str], None]) -> None:
    for line in lines:
        output_func(line)


def _recent_reports(root: Path, limit: int = 10) -> list[Path]:
    reports_dir = root / "reports"
    if not reports_dir.exists():
        return []
    files = [path for path in reports_dir.iterdir() if path.is_file()]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]


def dispatch_menu_task(
    choice: str,
    *,
    config: dict[str, Any],
    root: Path,
    logger,
    target_date: str | None = None,
    kst_file: str | Path | None = None,
    runners: dict[str, Callable[..., Any]] | None = None,
    output_func: Callable[[str], None] = print,
) -> Any:
    runners = runners or {}
    if choice == "1":
        return runners.get("run_daily", run_daily_pipeline)(
            config=config, root=root, logger=logger, target_date=target_date, kst_file=kst_file
        )
    if choice.startswith("hourly:"):
        period = choice.split(":", 1)[1]
        return runners.get("run_hourly", run_half_auto_pipeline)(
            config=config,
            root=root,
            logger=logger,
            period=period,
            kst_file=kst_file,
            assume_yes=True,
            confirm_before_run=False,
        )
    if choice == "5":
        report = runners.get("doctor", run_doctor)(root, config)
        if output_func is print:
            print_doctor_report(report)
        else:
            output_func(f"运行环境检查完成：{report.get('summary', {}).get('passed', 0)}/{report.get('summary', {}).get('total', 0)} 项通过")
        return report
    raise ValueError(f"不支持的菜单选项：{choice}")


def _task_meta(choice: str, project: dict[str, Any]) -> dict[str, str | None]:
    daily_date = _default_daily_date()
    excel = project.get("excel", {}) if isinstance(project.get("excel"), dict) else {}
    hourly_sheet = excel.get("hourly_sheet") or project.get("sheets", {}).get("hourly", "时段数据")
    daily_sheet = excel.get("daily_sheet") or project.get("sheets", {}).get("daily", "百度")
    mapping = {
        "1": {"name": "运行日报", "sheet": daily_sheet, "date": daily_date, "period": None},
        "hourly:11点": {"name": "运行11点小时报", "sheet": hourly_sheet, "date": date.today().isoformat(), "period": "11点"},
        "hourly:15点": {"name": "运行3点小时报", "sheet": hourly_sheet, "date": date.today().isoformat(), "period": "3点"},
        "hourly:18点": {"name": "运行6点小时报", "sheet": hourly_sheet, "date": date.today().isoformat(), "period": "6点"},
    }
    return mapping[choice]


def _check_chrome_debug(root: Path, config: dict[str, Any], output_func: Callable[[str], None]) -> bool:
    from modules.console_ui import print_check_result

    settings = config.get("browser") if isinstance(config.get("browser"), dict) else {}
    auto_start = settings.get("auto_start_debug_chrome", True)
    host = settings.get("remote_debugging_host", "127.0.0.1")
    port = int(settings.get("remote_debugging_port", 9222))

    result = ensure_chrome_debug_ready(root, config, host=host, port=port, auto_start=auto_start)
    if result["ready"]:
        if result.get("port_already_open"):
            output_func(f"[通过] Chrome 调试端口已就绪：http://{host}:{port}")
        else:
            output_func(f"[通过] 已启动项目专用 Chrome 调试端口：http://{host}:{port}")
        return True
    else:
        output_func(f"[注意] Chrome 调试端口未就绪：http://{host}:{port}")
        if result.get("error"):
            output_func(f"  {result['error']}")
        return False


def _select_hourly_period(input_func: Callable[[str], str], output_func: Callable[[str], None]) -> str | None:
    output_func(HOURLY_MENU_TEXT)
    answer = input_func("请选择小时报时段：").strip()
    return {"1": "11点", "2": "15点", "3": "18点"}.get(answer)


def _select_project(root: Path, input_func: Callable[[str], str], output_func: Callable[[str], None]) -> dict[str, Any] | None:
    projects = list_projects(root)
    output_func("可切换项目：")
    for index, project in enumerate(projects, start=1):
        output_func(f"{index}. {project['project_id']} - {project['project_name']}")
    answer = input_func("请输入项目序号或 project_id，直接回车取消：").strip()
    if not answer:
        return None
    for index, item in enumerate(projects, start=1):
        if answer == str(index) or answer == item["project_id"]:
            return set_current_project(root, item["project_id"])
    output_func("未找到该项目。")
    return None


def run_menu(
    root: Path = ROOT,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> None:
    logger = setup_logger(root / "logs" / "run.log")
    base_config = load_config(str(root / "config.json"), fallback_path=root / "config.example.json")
    project = get_current_project(root)
    menu_config = build_runtime_config(project, base_config)
    _check_chrome_debug(root, menu_config, output_func)

    while True:
        project = get_current_project(root)
        output_func(build_menu_header(root, project))
        output_func(MENU_TEXT)
        choice = input_func("请选择：").strip()
        if choice == "0":
            output_func("已退出。")
            return
        if choice == "3":
            selected = _select_project(root, input_func, output_func)
            if selected:
                project = selected
                output_func(f"已切换到项目：{project['project_name']}")
            continue
        if choice == "4":
            project = load_project_config(root, project["project_id"])
            output_func(f"已刷新当前项目：{project['project_name']}")
            continue
        if choice == "5":
            config = build_runtime_config(project, base_config)
            dispatch_menu_task("5", config=config, root=root, logger=logger, output_func=output_func)
            continue
        if choice not in {"1", "2"}:
            output_func("无效选项，请重新选择。")
            continue

        dispatch_choice = choice
        if choice == "2":
            period = _select_hourly_period(input_func, output_func)
            if not period:
                output_func("已返回主菜单。")
                continue
            dispatch_choice = f"hourly:{period}"

        meta = _task_meta(dispatch_choice, project)
        _print_lines(build_confirmation_lines(
            root,
            project,
            str(meta["name"]),
            target_date=meta.get("date"),
            period=meta.get("period"),
            sheet=meta.get("sheet") or None,
        ), output_func)
        answer = input_func("> ").strip().lower()
        if answer == "q":
            output_func("已退出。")
            return
        config = build_runtime_config(project, base_config)
        if not _check_chrome_debug(root, config, output_func):
            output_func("Chrome 调试端口未就绪，将跳过百度抓数，仅执行后续步骤（如有快商通文件仍可解析写入）。")
        result = dispatch_menu_task(
            dispatch_choice,
            config=config,
            root=root,
            logger=logger,
            target_date=meta.get("date"),
            kst_file=None,
            output_func=output_func,
        )
        if isinstance(result, dict) and "passed" in result:
            if result.get("passed"):
                print_final_success("任务完成")
            else:
                print_final_failure(f"失败步骤：{result.get('failed_step') or '未知'}，原因：{result.get('errors') or '未知错误'}")
                output_func("  详细日志：logs/run.log")
        else:
            output_func("任务已执行。")


if __name__ == "__main__":
    run_menu()
