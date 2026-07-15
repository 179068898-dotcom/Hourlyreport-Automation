from __future__ import annotations

import json
import os
import subprocess
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from modules.chrome_debug import ensure_chrome_debug_ready
from modules.config_manager import load_config
from modules.console_ui import (
    clear_screen,
    print_check_result,
    print_error,
    print_final_failure,
    print_final_success,
    print_key_value_table,
    print_console_context,
    print_main_menu,
    print_project_info,
    print_quiet_line,
    print_sub_menu_hourly,
    print_success,
    print_warning,
)
from modules.doctor import print_doctor_report, run_doctor
from modules.logger import setup_logger
from modules.preflight import check_baidu_credentials, print_credential_report, print_preflight_report, run_preflight
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

# 主菜单文案（旧接口保留给测试和外部引用）
MENU_TEXT = """
1. 小时报
2. 日报
3. 切换项目
4. 检查条件项
5. 更多功能
0. 退出
"""

HOURLY_MENU_TEXT = """
请选择小时报时段：
1. 11点
2. 15点
3. 18点
0. 返回
"""

MORE_FEATURES_MENU_TEXT = """
更多功能
1. 报告与日志
2. 配置诊断
3. HERMES / 夏思道帮助
4. 多百度来源摘要
5. 项目信息详情
6. 高级分步调试
0. 返回
"""

CONDITION_MENU_TEXT = """
检查条件项
1. 一键检查当前项目能否运行
2. 检查百度账号凭据
3. 检查小时报条件
4. 检查日报条件
0. 返回
"""

REPORT_MENU_TEXT = """
报告与日志
1. 查看最终运行报告摘要
2. 查看百度多来源 Markdown 报告
3. 查看百度账户数据路径
4. 查看写入报告路径
5. 查看 run.log 末尾 80 行
6. 打开 reports 文件夹
7. 打开 logs 文件夹
0. 返回
"""

DIAGNOSTIC_MENU_TEXT = """
配置诊断
1. 扫描小时报 Excel 结构
2. 扫描日报 Excel 结构
3. 导出 sheet 文本诊断
0. 返回
"""

ADVANCED_DEBUG_MENU_TEXT = """
高级分步调试
普通同事不要随意执行，遇到异常时按指导使用。
1. 只抓百度小时报数据
2. 只抓百度日报数据
3. 只解析商务通小时报文件
4. 只解析商务通日报文件
5. 百度页面状态检测
6. 百度退出诊断
0. 返回
"""

HERMES_MENU_TEXT = """
HERMES / 夏思道帮助
1. 显示小时报 HERMES 命令
2. 显示日报 HERMES 命令
3. 打开小时报 SOP
4. 打开日报 SOP
5. 显示凭据与 CAS 规则
0. 返回
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


def build_hermes_help_lines() -> list[str]:
    return [
        "固定入口同步日期：2026-07-10",
        "小时报：",
        "  run_hermes_hourly.bat 11点",
        "  run_hermes_hourly.bat 15点",
        "  run_hermes_hourly.bat 18点",
        "日报：",
        "  run_hermes_daily.bat",
        "  run_hermes_daily.bat 2026-07-09",
        "规则：",
        "- HERMES（夏思道）只调用固定 bat。",
        "- preflight 失败后不得继续执行。",
        "- 不得询问或输出真实百度密码。",
        "- 遇到验证码、安全验证、滑块时停止并报告。",
        "- 预约、到诊、就诊等禁止字段不由本工具填写。",
    ]


def build_baidu_source_summary_lines(project: dict[str, Any]) -> list[str]:
    raw_sources = project.get("baidu_sources")
    if not isinstance(raw_sources, list) or len(raw_sources) <= 1:
        return ["当前项目为单百度来源项目。"]
    excel_accounts = [
        str(account.get("standard_name") or "")
        for account in project.get("excel_accounts", []) or project.get("accounts", [])
        if isinstance(account, dict) and account.get("standard_name")
    ]
    candidates: list[str] = []
    lines = [f"百度来源数量：{len(raw_sources)}"]
    for source in raw_sources:
        accounts = source.get("accounts") or []
        names = [str(item.get("standard_name") or "") for item in accounts if item.get("standard_name")]
        candidates.extend(names)
        lines.append(
            f"- {source.get('source_name') or source.get('source_id') or '未命名来源'}："
            f"profile={source.get('credential_profile') or '未配置'}；候选百度账户数量={len(names)}"
        )
    candidate_only = [name for name in dict.fromkeys(candidates) if name not in set(excel_accounts)]
    lines.append(f"Excel 实际写入账户：{', '.join(excel_accounts) if excel_accounts else '未配置'}")
    lines.append(f"candidate_only_accounts：{', '.join(candidate_only) if candidate_only else '无'}")
    lines.append("ignored_inactive_accounts：候选账户展现、点击、消费全为 0 时记录并忽略。")
    lines.append("skipped_unmapped_accounts：候选账户有量但不在 Excel 写入范围时记录，需人工核对。")
    return lines


def _pause(input_func: Callable[[str], str]) -> None:
    input_func("  按 Enter 返回：")


def _print_text_block(title: str, lines: list[str], output_func: Callable[[str], None]) -> None:
    output_func("")
    output_func(f"  {title}")
    output_func("  " + "-" * 58)
    for line in lines:
        output_func(f"  {line}")
    output_func("")


def _current_config(root: Path, base_config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    project = get_current_project(root)
    return project, build_runtime_config(project, base_config)


def _open_path(path: Path, output_func: Callable[[str], None]) -> None:
    if not path.exists():
        output_func(f"  未生成：{path}")
        return
    try:
        os.startfile(str(path))
        output_func(f"  已打开：{path}")
    except OSError as exc:
        output_func(f"  无法打开：{path}（{exc}）")


def _print_report_summary(path: Path, label: str, output_func: Callable[[str], None]) -> None:
    if not path.exists():
        output_func(f"  {label}：未生成")
        return
    try:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        output_func(f"  {label}：无法读取（{exc}）")
        return
    status = "通过" if report.get("passed") else "失败"
    detail = report.get("failed_step") or report.get("date") or report.get("period") or ""
    output_func(f"  {label}：{status}{'；' + str(detail) if detail else ''}")
    output_func(f"    路径：{path}")


def _run_cli_diagnostic(root: Path, arguments: list[str], output_func: Callable[[str], None]) -> None:
    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        output_func("  未找到 .venv\\Scripts\\python.exe")
        return
    result = subprocess.run(
        [str(python), str(root / "main.py"), *arguments],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in result.stdout.splitlines():
        output_func(f"  {line}")
    for line in result.stderr.splitlines():
        output_func(f"  {line}")
    output_func(f"  命令结束，退出码：{result.returncode}")


def _execute_preflight(
    root: Path,
    project: dict[str, Any],
    config: dict[str, Any],
    task: str,
    logger,
) -> dict[str, Any]:
    report = run_preflight(root, project, config, task=task, quick=True)
    out = root / "reports" / "preflight_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("菜单 preflight 结果：%s；任务：%s；报告：%s", "通过" if report.get("passed") else "失败", task, out)
    return report


def _run_condition_menu(
    root: Path,
    base_config: dict[str, Any],
    logger,
    input_func: Callable[[str], str],
    output_func: Callable[[str], None],
) -> None:
    while True:
        _print_text_block("检查条件项", CONDITION_MENU_TEXT.strip().splitlines()[1:], output_func)
        choice = input_func("  请选择选项：").strip()
        if choice == "0":
            return
        project, config = _current_config(root, base_config)
        if choice == "1":
            print_doctor_report(run_doctor(root, config))
        elif choice == "2":
            print_credential_report(check_baidu_credentials(root, config), output_func=output_func)
        elif choice in {"3", "4"}:
            report = _execute_preflight(root, project, config, "daily" if choice == "4" else "hourly", logger)
            print_preflight_report(report, output_func=output_func)
        else:
            output_func("  无效选项，请重新选择。")
            continue
        _pause(input_func)


def _run_report_menu(root: Path, input_func: Callable[[str], str], output_func: Callable[[str], None]) -> None:
    while True:
        _print_text_block("报告与日志", REPORT_MENU_TEXT.strip().splitlines()[1:], output_func)
        choice = input_func("  请选择选项：").strip()
        if choice == "0":
            return
        if choice == "1":
            _print_report_summary(root / "reports" / "final_run_report.json", "小时报最终报告", output_func)
            _print_report_summary(root / "reports" / "daily_final_run_report.json", "日报最终报告", output_func)
        elif choice == "2":
            _open_path(root / "reports" / "baidu_multi_source_report.md", output_func)
        elif choice == "3":
            for filename in ["baidu_account_data.json", "baidu_daily_data.json"]:
                path = root / "reports" / filename
                output_func(f"  {filename}：{path if path.exists() else '未生成'}")
        elif choice == "4":
            for filename in ["write_report.json", "daily_write_report.json"]:
                path = root / "reports" / filename
                output_func(f"  {filename}：{path if path.exists() else '未生成'}")
        elif choice == "5":
            path = root / "logs" / "run.log"
            if not path.exists():
                output_func("  run.log：未生成")
            else:
                output_func("  run.log 末尾 80 行：")
                for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[-80:]:
                    output_func(f"  {line}")
        elif choice == "6":
            _open_path(root / "reports", output_func)
        elif choice == "7":
            _open_path(root / "logs", output_func)
        else:
            output_func("  无效选项，请重新选择。")
            continue
        _pause(input_func)


def _run_diagnostic_menu(root: Path, input_func: Callable[[str], str], output_func: Callable[[str], None]) -> None:
    while True:
        _print_text_block("配置诊断", DIAGNOSTIC_MENU_TEXT.strip().splitlines()[1:], output_func)
        choice = input_func("  请选择选项：").strip()
        if choice == "0":
            return
        arguments: list[str] | None = {
            "1": ["--mode", "inspect-excel"],
            "2": ["--mode", "inspect-daily-excel"],
            "3": ["--mode", "dump-sheet-text"],
        }.get(choice)
        if arguments is None:
            output_func("  无效选项，请重新选择。")
            continue
        _run_cli_diagnostic(root, arguments, output_func)
        _pause(input_func)


def _run_advanced_debug_menu(root: Path, input_func: Callable[[str], str], output_func: Callable[[str], None]) -> None:
    while True:
        _print_text_block("高级分步调试", ADVANCED_DEBUG_MENU_TEXT.strip().splitlines()[1:], output_func)
        choice = input_func("  请选择选项：").strip()
        if choice == "0":
            return
        arguments: list[str] | None = {
            "5": ["--mode", "baidu-detect"],
            "6": ["--mode", "test-baidu-logout"],
        }.get(choice)
        if choice in {"1", "3"}:
            period = input_func("  输入小时报时段（默认 15点）：").strip() or "15点"
            arguments = ["--mode", "fetch-baidu-auto" if choice == "1" else "parse-kst-export", "--period", period]
        elif choice in {"2", "4"}:
            target_date = input_func("  输入日报日期 YYYY-MM-DD（留空为默认日期）：").strip()
            arguments = ["--mode", "fetch-baidu-daily" if choice == "2" else "parse-kst-daily"]
            if target_date:
                arguments.extend(["--date", target_date])
        if arguments is None:
            output_func("  无效选项，请重新选择。")
            continue
        _run_cli_diagnostic(root, arguments, output_func)
        _pause(input_func)


def _run_hermes_menu(root: Path, input_func: Callable[[str], str], output_func: Callable[[str], None]) -> None:
    lines = build_hermes_help_lines()
    while True:
        _print_text_block("HERMES / 夏思道帮助", HERMES_MENU_TEXT.strip().splitlines()[1:], output_func)
        choice = input_func("  请选择选项：").strip()
        if choice == "0":
            return
        if choice == "1":
            _print_text_block("HERMES 小时报命令", lines[:5], output_func)
        elif choice == "2":
            _print_text_block("HERMES 日报命令", lines[5:8], output_func)
        elif choice == "3":
            _open_path(root / "docs" / "hermes_hourly_sop.md", output_func)
        elif choice == "4":
            _open_path(root / "docs" / "hermes_daily_sop.md", output_func)
        elif choice == "5":
            _print_text_block("凭据与 CAS 规则", lines[8:], output_func)
        else:
            output_func("  无效选项，请重新选择。")
            continue
        _pause(input_func)


def _run_more_features_menu(
    root: Path,
    base_config: dict[str, Any],
    logger,
    input_func: Callable[[str], str],
    output_func: Callable[[str], None],
) -> None:
    while True:
        _print_text_block("更多功能", MORE_FEATURES_MENU_TEXT.strip().splitlines()[1:], output_func)
        choice = input_func("  请选择选项：").strip()
        if choice == "0":
            return
        if choice == "1":
            _run_report_menu(root, input_func, output_func)
        elif choice == "2":
            _run_diagnostic_menu(root, input_func, output_func)
        elif choice == "3":
            _run_hermes_menu(root, input_func, output_func)
        elif choice == "4":
            _print_text_block("多百度来源摘要", build_baidu_source_summary_lines(get_current_project(root)), output_func)
            _pause(input_func)
        elif choice == "5":
            print_project_info(get_current_project(root))
            _pause(input_func)
        elif choice == "6":
            _run_advanced_debug_menu(root, input_func, output_func)
        else:
            output_func("  无效选项，请重新选择。")


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
    if choice == "2":
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
        "2": {"name": "运行日报", "sheet": daily_sheet, "date": daily_date, "period": None},
        "hourly:11点": {"name": "运行11点小时报", "sheet": hourly_sheet, "date": date.today().isoformat(), "period": "11点"},
        "hourly:15点": {"name": "运行15点小时报", "sheet": hourly_sheet, "date": date.today().isoformat(), "period": "15点"},
        "hourly:18点": {"name": "运行18点小时报", "sheet": hourly_sheet, "date": date.today().isoformat(), "period": "18点"},
    }
    return mapping[choice]


def _check_chrome_debug(root: Path, config: dict[str, Any], output_func: Callable[[str], None]) -> bool:
    settings = config.get("browser") if isinstance(config.get("browser"), dict) else {}
    auto_start = settings.get("auto_start_debug_chrome", True)
    host = settings.get("remote_debugging_host", "127.0.0.1")
    port = int(settings.get("remote_debugging_port", 9222))

    result = ensure_chrome_debug_ready(root, config, host=host, port=port, auto_start=auto_start)
    if result["ready"]:
        if result.get("port_already_open"):
            print_success(f"Chrome 调试端口已就绪：http://{host}:{port}")
        else:
            print_success(f"已启动项目专用 Chrome 调试端口：http://{host}:{port}")
        return True
    else:
        print_warning(f"Chrome 调试端口未就绪：http://{host}:{port}")
        if result.get("error"):
            print_quiet_line(f"  {result['error']}")
        return False


def _select_hourly_period(root: Path, project_id: str, input_func: Callable[[str], str], output_func: Callable[[str], None]) -> str | None:
    print_sub_menu_hourly(root=root, project_id=project_id)
    answer = input_func("  请选择时段：").strip()
    return {"1": "11点", "2": "15点", "3": "18点"}.get(answer)


def _select_project_from_list(root: Path, input_func: Callable[[str], str], output_func: Callable[[str], None]) -> dict[str, Any] | None:
    """展示项目列表，用户按编号选择后切换。"""
    from modules.console_ui import print_project_list, print_error as cui_error

    projects = list_projects(root)
    print_project_list(projects, root=root)

    if not projects:
        output_func("")
        output_func("  按 Enter 继续...")
        input_func("")
        return None

    answer = input_func("  请输入项目编号：").strip()
    if answer == "0":
        return None

    try:
        idx = int(answer) - 1
        if 0 <= idx < len(projects):
            project_id = projects[idx]["project_id"]
            return set_current_project(root, project_id)
    except (ValueError, Exception):
        pass

    cui_error("请输入正确的项目编号")
    input_func("  按 Enter 继续...")
    return None


def run_menu(
    root: Path = ROOT,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> None:
    from modules.console_ui import set_output_func

    set_output_func(output_func)
    logger = setup_logger(root / "logs" / "run.log")
    base_config = load_config(str(root / "config.json"), fallback_path=root / "config.example.json")
    project = get_current_project(root)

    while True:
        project = get_current_project(root)
        excel = project.get("excel", {}) if isinstance(project.get("excel"), dict) else {}
        excel_path = excel.get("path") or project.get("excel_path", "")

        # 首页摘要与今日任务状态均为只读展示。
        print_console_context(project, root=root)
        from modules.console_ui import print_task_status_header
        print_task_status_header(project, root=root)

        print_main_menu(project, root=root)
        choice = input_func("  请输入选项：").strip()

        if choice == "0":
            output_func("  已退出。")
            return

        if choice.lower() == "r":
            continue

        if choice == "3":
            # 切换项目
            switched = _select_project_from_list(root, input_func, output_func)
            if switched:
                project = switched
                print_success(f"已切换到：{switched['project_name']}")
            input_func("  按 Enter 继续...")
            continue

        if choice == "4":
            _run_condition_menu(root, base_config, logger, input_func, output_func)
            continue

        if choice == "5":
            _run_more_features_menu(root, base_config, logger, input_func, output_func)
            continue

        if choice not in {"1", "2"}:
            output_func("  无效选项，请重新选择。")
            continue

        dispatch_choice = choice
        if choice == "1":
            # 小时报 → 选择时段
            period = _select_hourly_period(root, project.get("project_id", ""), input_func, output_func)
            if not period:
                output_func("  已返回主菜单。")
                continue
            dispatch_choice = f"hourly:{period}"

        meta = _task_meta(dispatch_choice, project)
        latest = _latest_kst_export(root, project)

        # 检查是否今天已完成
        from modules.task_status import is_daily_done, is_hourly_done
        from modules.console_ui import print_confirm_panel
        project_id = project.get("project_id", "")
        already_done = False
        if meta.get("period"):
            already_done = is_hourly_done(root, project_id, meta["period"])
        else:
            already_done = is_daily_done(root, project_id)

        excel = project.get("excel", {}) if isinstance(project.get("excel"), dict) else {}

        print_confirm_panel({
            "task_name": str(meta["name"]),
            "project_name": project.get("project_name", ""),
            "date": meta.get("date"),
            "period": meta.get("period"),
            "sheet": meta.get("sheet"),
            "excel_path": excel.get("path") or project.get("excel_path", ""),
            "kst_file": str(latest) if latest else "",
            "already_done": already_done,
        })

        answer = input_func("  > ").strip()
        if answer == "0":
            output_func("  已返回主菜单。")
            continue

        config = build_runtime_config(project, base_config)

        # 百度登录状态守卫：现在由 baidu_session.ensure_baidu_profile_session
        # 在 fetch_baidu_auto / fetch_baidu_daily 内部处理，
        # 菜单层不再提前写入 login_state。

        if not _check_chrome_debug(root, config, output_func):
            print_warning("Chrome 调试端口未就绪，将跳过百度抓数，仅执行后续步骤（如有快商通文件仍可解析写入）。")

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

                # 标记完成状态
                w_summary = result.get("write_summary", {})
                verified = w_summary.get("verification_passed", False)
                write_count = w_summary.get("write_count", 0)
                if verified and write_count > 0:
                    from modules.task_status import mark_daily_done, mark_hourly_done
                    if meta.get("period"):
                        mark_hourly_done(root, project_id, meta["period"])
                    else:
                        mark_daily_done(root, project_id)
                    print_success("已标记为完成")

                # 写入成功后自动打开 Excel
                from modules.console_ui import try_open_excel, print_auto_open_result, verbose_print
                excel_path = excel.get("path") or project.get("excel_path", "")
                if excel_path:
                    opened = try_open_excel(excel_path)
                    print_auto_open_result(opened)

                verbose_print(f"报告：reports/{'daily_' if choice == '2' else ''}final_run_report.json")
            else:
                print_final_failure(f"失败步骤：{result.get('failed_step') or '未知'}，原因：{result.get('errors') or '未知错误'}")
                output_func("  详细日志：logs/run.log")
        else:
            output_func("  任务已执行。")

        output_func("")
        input_func("  输入 0 返回：").strip()


if __name__ == "__main__":
    run_menu()
