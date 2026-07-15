from __future__ import annotations

import argparse
import json
from pathlib import Path

from modules.config_manager import load_config
from modules.console_ui import (
    print_error,
    print_final_failure,
    print_final_success,
    print_quiet_line,
    print_success,
    print_warning,
    set_verbose,
    verbose_print,
)
from modules.baidu_browser import fetch_baidu_account_report
from modules.baidu_auto import fetch_baidu_auto
from modules.baidu_daily import fetch_baidu_daily
from modules.baidu_detector import baidu_detect
from modules.baidu_overview import baidu_open_overview, baidu_prepare_overview
from modules.baidu_validator import print_baidu_validate_summary, validate_baidu_account_data
from modules.baidu_report_api import fetch_baidu_api_probe
from modules.baidu_api_simulation import simulate_baidu_api_hourly
from modules.baidu_oauth_bundle import BaiduOAuthImportError, import_baidu_oauth_bundle
from modules.browser_manager import test_browser_connect, test_browser_launch
from modules.data_merger import merge_daily_files, merge_data_files
from modules.daily_excel_inspector import inspect_daily_excel_structure
from modules.doctor import print_doctor_report, run_doctor
from modules.excel_inspector import inspect_excel_structure, dump_sheet_text
from modules.excel_writer import mock_write_excel, write_merged_daily_data, write_merged_hourly_data
from modules.kst_export_parser import find_latest_kst_export, parse_kst_export_file, write_empty_kst_export_result
from modules.kst_daily_parser import parse_kst_daily_file, write_empty_kst_daily_result
from modules.logger import setup_logger
from modules.project_config import build_runtime_config_from_project, get_current_project, list_projects, load_project_config, validate_project_config
from modules.preflight import check_baidu_credentials, print_credential_report, print_preflight_report, run_preflight
from modules.validators import get_required_accounts
from modules.run_pipeline import run_daily_pipeline, run_half_auto_pipeline

ROOT = Path(__file__).resolve().parent


def ensure_runtime_dirs() -> None:
    for name in ["reports", "logs", "backups", "samples", "browser_profile", "kst_exports"]:
        (ROOT / name).mkdir(exist_ok=True)


def main() -> int | None:
    ensure_runtime_dirs()
    parser = argparse.ArgumentParser(description="百度竞价日报/小时报自动化工具")
    parser.add_argument("--mode", required=True, choices=[
        "inspect-excel",
        "inspect-daily-excel",
        "dump-sheet-text",
        "mock-write",
        "test-browser",
        "test-browser-connect",
        "test-baidu-logout",
        "fetch-baidu",
        "fetch-baidu-auto",
        "fetch-baidu-daily",
        "test-baidu-api",
        "simulate-baidu-api-hourly",
        "import-baidu-oauth",
        "baidu-detect",
        "baidu-open-overview",
        "baidu-prepare-overview",
        "validate-baidu",
        "parse-kst-export",
        "parse-kst-daily",
        "merge-data",
        "merge-daily",
        "write-excel",
        "write-daily",
        "run",
        "run-daily",
        "list-projects",
        "show-project",
        "validate-project",
        "doctor",
        "preflight",
        "test-baidu-credentials",
    ])
    parser.add_argument("--period", default=None, help="时段，例如：11点 / 15点 / 18点")
    parser.add_argument("--file", default=None, help="快商通人工导出的 Excel/CSV 文件路径")
    parser.add_argument("--kst-file", dest="file", default=None, help="同 --file，快商通人工导出的 Excel/CSV 文件路径")
    parser.add_argument("--yes", action="store_true", help="run 模式跳过运行前确认清单")
    parser.add_argument("--date", default=None, help="日报日期，例如：2026-05-07；不传则默认昨天")
    parser.add_argument("--project", default=None, help="临时指定项目 ID，不修改 configs/app_config.json")
    parser.add_argument("--task", choices=["hourly", "daily"], default="hourly", help="preflight 任务类型，默认检查小时报")
    parser.add_argument("--quick", action="store_true", help="preflight 快速模式：跳过耗时的 Excel sheet 结构扫描")
    parser.add_argument("--config", default=str(ROOT / "config.json"), help="配置文件路径")
    parser.add_argument("--verbose", action="store_true", help="启用详细终端输出")
    parser.add_argument("--api-profile", default=None, help="百度 OAuth 授权导入使用的本地 API profile")
    args = parser.parse_args()

    if args.verbose:
        set_verbose(True)

    logger = setup_logger(ROOT / "logs" / "run.log")
    base_config = load_config(args.config, fallback_path=ROOT / "config.example.json")
    config_error: Exception | None = None
    try:
        current_project = load_project_config(ROOT, args.project) if args.project else get_current_project(ROOT)
        config = build_runtime_config_from_project(current_project, base_config)
    except Exception as exc:
        config_error = exc
        current_project = {}
        config = base_config

    if args.mode == "list-projects":
        projects = list_projects(ROOT)
        print("项目列表：")
        if not projects:
            print("- 未找到项目配置")
        for project in projects:
            print(f"- {project['project_id']}：{project['project_name']}（{project['path']}）")
        return

    if args.mode == "show-project":
        project = get_current_project(ROOT)
        from modules.console_ui import print_project_info
        print_project_info(project)
        return

    if args.mode == "validate-project":
        project = get_current_project(ROOT)
        errors = validate_project_config(project)
        if errors:
            print_error(f"项目配置校验失败：{project.get('project_id')}")
            for error in errors:
                print_quiet_line(f"  - {error}")
        else:
            print_success(f"项目配置校验通过：{project.get('project_id')} - {project.get('project_name')}")
        return

    if args.mode == "doctor":
        report = run_doctor(ROOT, config)
        print_doctor_report(report)
        verbose_print(f"详细报告：reports/doctor_report.json")
        return

    if args.mode in {"preflight", "test-baidu-credentials"} and config_error:
        print_error(f"当前项目配置无法读取：{config_error}")
        return 1

    if args.mode == "test-baidu-credentials":
        report = check_baidu_credentials(ROOT, config)
        print_credential_report(report)
        return 0 if report.get("passed") else 1

    if args.mode == "preflight":
        report = run_preflight(ROOT, current_project, config, task=args.task, quick=args.quick)
        out = ROOT / "reports" / "preflight_report.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print_preflight_report(report)
        logger.info("preflight 结果：%s；报告：%s", "通过" if report.get("passed") else "失败", out)
        return 0 if report.get("passed") else 1

    if args.mode == "inspect-excel":
        report = inspect_excel_structure(config=config, root=ROOT, logger=logger)
        out = ROOT / "reports" / "excel_structure_report.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Excel 结构识别报告已输出：%s", out)
        print_success(f"Excel 结构识别完成：reports/excel_structure_report.json")
        return

    if args.mode == "inspect-daily-excel":
        report = inspect_daily_excel_structure(config=config, root=ROOT, logger=logger)
        out = ROOT / "reports" / "daily_excel_structure_report.json"
        if report.get("errors"):
            print_error(f"日报 Excel 结构识别存在问题，已输出报告：reports/daily_excel_structure_report.json")
        else:
            print_success(f"日报 Excel 结构识别完成：reports/daily_excel_structure_report.json")
        return

    if args.mode == "dump-sheet-text":
        out = dump_sheet_text(config=config, root=ROOT, logger=logger)
        print_quiet_line(f"sheet 文本扫描结果已输出：{out}")
        return

    if args.mode == "mock-write":
        report = mock_write_excel(config=config, root=ROOT, logger=logger, period=args.period)
        out = ROOT / "reports" / "mock_write_report.json"
        if report.get("errors"):
            print_error(f"Excel 模拟写入中断：reports/mock_write_report.json")
        else:
            print_success(f"Excel 模拟写入完成：reports/mock_write_report.json")
        return
    if args.mode == "test-browser":
        report = test_browser_launch(config=config, root=ROOT, logger=logger)
        out = ROOT / "reports" / "browser_test_report.json"
        if report.get("errors"):
            print_error(f"Chrome 浏览器启动测试失败，已输出报告：reports/browser_test_report.json")
        else:
            print_success(f"Chrome 浏览器启动测试完成：reports/browser_test_report.json")
        return
    if args.mode == "test-browser-connect":
        report = test_browser_connect(config=config, root=ROOT, logger=logger)
        out = ROOT / "reports" / "browser_connect_report.json"
        if report.get("errors"):
            print_error(f"连接已有 Chrome 测试失败，已输出报告：reports/browser_connect_report.json")
        else:
            print_success(f"连接已有 Chrome 测试完成：reports/browser_connect_report.json")
        return
    if args.mode == "test-baidu-logout":
        from modules.browser_manager import connect_existing_chrome, show_browser_page_for_manual_intervention
        from modules.baidu_session import logout_baidu_account
        from modules.chrome_debug import ensure_chrome_debug_ready

        if not ensure_chrome_debug_ready(ROOT, config).get("ready"):
            print_error("Chrome 调试端口未就绪，请先启动 Chrome")
            return
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                context, page = connect_existing_chrome(pw, config)
                show_browser_page_for_manual_intervention(page, config)
                result = logout_baidu_account(page, root=ROOT)
                if result.get("success"):
                    print_success("已自动退出百度账号")
                    verbose_print("候选文件：reports/baidu_logout_candidates.json")
                else:
                    print_error("未能自动退出百度账号")
                    verbose_print("请查看 reports/baidu_logout_candidates.json 分析失败原因")
        except Exception as exc:
            print_error(f"退出登录测试异常：{exc}")
        return
    if args.mode == "fetch-baidu":
        report = fetch_baidu_account_report(config=config, root=ROOT, logger=logger, period=args.period)
        out = ROOT / config.get("baidu", {}).get("output_path", "reports/baidu_account_data.json")
        if report.get("errors"):
            print_error(f"百度数据读取未完成，已输出诊断报告：{out}")
        else:
            print_success(f"百度数据读取完成：{out}")
        return
    if args.mode == "fetch-baidu-auto":
        report = fetch_baidu_auto(config=config, root=ROOT, logger=logger, period=args.period)
        out = ROOT / config.get("baidu", {}).get("output_path", "reports/baidu_account_data.json")
        validate_out = ROOT / "reports" / "baidu_validate_report.json"
        if report.get("errors"):
            print_error(f"百度自动读取失败，已输出诊断报告：reports/baidu_account_data.json")
        else:
            print_success(f"百度自动读取完成：reports/baidu_account_data.json")
            verbose_print(f"自检报告：reports/baidu_validate_report.json")
        return
    if args.mode == "fetch-baidu-daily":
        report = fetch_baidu_daily(config=config, root=ROOT, logger=logger, target_date=args.date)
        out = ROOT / "reports" / "baidu_daily_data.json"
        validate_out = ROOT / "reports" / "baidu_daily_validate_report.json"
        if report.get("errors"):
            print_error(f"百度日报读取失败，已输出诊断报告：reports/baidu_daily_data.json")
        else:
            print_success(f"百度日报读取完成：reports/baidu_daily_data.json")
            verbose_print(f"自检报告：reports/baidu_daily_validate_report.json")
        return
    if args.mode == "test-baidu-api":
        report = fetch_baidu_api_probe(
            config=config,
            root=ROOT,
            logger=logger,
            target_date=args.date,
            period=args.period,
        )
        if report.get("errors"):
            print_error("百度 API 只读探测失败，已输出报告：reports/baidu_api_probe_report.json")
            return 1
        print_success("百度 API 只读探测通过：reports/baidu_api_probe_report.json")
        return 0
    if args.mode == "simulate-baidu-api-hourly":
        report = simulate_baidu_api_hourly(
            config=config,
            root=ROOT,
            logger=logger,
            period=args.period,
            target_date=args.date,
        )
        if report.get("errors"):
            print_error("百度 API 小时报模拟失败：reports/baidu_api_hourly_simulation_report.json")
            return 1
        print_success("百度 API 小时报模拟通过：reports/baidu_api_hourly_simulation_report.json")
        print_quiet_line(f"仅预览 {len(report.get('planned_writes') or [])} 个写入单元格，未修改 Excel")
        return 0
    if args.mode == "import-baidu-oauth":
        if not args.file or not args.api_profile:
            print_error("导入授权需要同时提供 --file 和 --api-profile")
            return 1
        try:
            report = import_baidu_oauth_bundle(ROOT, args.file, args.api_profile)
        except BaiduOAuthImportError as exc:
            print_error(f"百度 OAuth 授权导入失败：{exc}")
            return 1
        print_success(f"百度 OAuth 授权已导入：{report['api_profile']}")
        print_quiet_line(f"识别子账户 {report['sub_account_count']} 个；授权文件请立即人工删除")
        return 0
    if args.mode == "baidu-detect":
        report = baidu_detect(config=config, root=ROOT, logger=logger)
        out = ROOT / "reports" / "baidu_detect_report.json"
        if report.get("errors"):
            print_error(f"百度页面检测失败，已输出报告：reports/baidu_detect_report.json")
        else:
            print_success(f"百度页面检测完成：reports/baidu_detect_report.json")
            print_quiet_line(f"登录状态：{report.get('login_status')}；页面类型：{report.get('page_type')}")
        return
    if args.mode == "baidu-open-overview":
        report = baidu_open_overview(config=config, root=ROOT, logger=logger)
        out = ROOT / "reports" / "baidu_open_overview_report.json"
        if report.get("errors"):
            print_error(f"百度数据概览搜索推广打开失败，已输出报告：reports/baidu_open_overview_report.json")
        else:
            print_success(f"百度数据概览搜索推广打开完成：reports/baidu_open_overview_report.json")
            print_quiet_line(f"最终页面类型：{report.get('final_page_type')}；点击步骤：{report.get('clicked_steps')}")
        return
    if args.mode == "baidu-prepare-overview":
        report = baidu_prepare_overview(config=config, root=ROOT, logger=logger)
        out = ROOT / "reports" / "baidu_prepare_overview_report.json"
        if report.get("errors"):
            print_error(f"百度搜索推广数据页复核未通过，已输出报告：reports/baidu_prepare_overview_report.json")
        else:
            print_success(f"百度搜索推广数据页复核通过：reports/baidu_prepare_overview_report.json")
        return
    if args.mode == "validate-baidu":
        source = ROOT / config.get("baidu", {}).get("output_path", "reports/baidu_account_data.json")
        out = ROOT / "reports" / "baidu_validate_report.json"
        report = validate_baidu_account_data(source, out, get_required_accounts(config))
        logger.info("百度数据自检报告已输出：%s；结果：%s", out, "通过" if report.get("passed") else "失败")
        print_baidu_validate_summary(report)
        verbose_print(f"百度数据自检报告已输出：reports/baidu_validate_report.json")
        return
    if args.mode == "parse-kst-export":
        export_file = Path(args.file) if args.file else find_latest_kst_export(ROOT, config)
        if export_file is None:
            result = write_empty_kst_export_result(config, ROOT, args.period, "未找到 30 分钟内的快商通导出文件，按 0 对话处理")
            logger.info("快商通导出解析未发现新文件，已按 0 对话输出：%s", result["outputs"]["parse_report"])
            print_success("未找到 30 分钟内的快商通导出文件，已按 0 对话处理")
            return
        result = parse_kst_export_file(export_file, config, ROOT, args.period)
        logger.info(
            "快商通导出解析报告已输出：%s；结果：%s",
            result["outputs"]["parse_report"],
            "通过" if result["parse_report"].get("passed") else "失败",
        )
        if result["parse_report"].get("passed"):
            print_success("商务通数据解析完成")
            verbose_print(f"报告：{result['outputs']['dialog_data']}")
        else:
            print_error("商务通数据解析失败")
            verbose_print(f"报告：{result['outputs']['parse_report']}")
        return
    if args.mode == "parse-kst-daily":
        export_file = Path(args.file) if args.file else find_latest_kst_export(ROOT, config)
        out = ROOT / "reports" / "kst_daily_parse_report.json"
        if export_file is None:
            result = write_empty_kst_daily_result(config, ROOT, args.date, "未找到 30 分钟内的商务通日报导出文件，按 0 对话处理")
            logger.info("商务通日报导出解析未发现新文件，已按 0 对话输出：%s", result["outputs"]["parse_report"])
            print_success("未找到 30 分钟内的商务通日报导出文件，已按 0 对话处理")
            return
        result = parse_kst_daily_file(export_file, config, ROOT, args.date)
        logger.info(
            "商务通日报导出解析报告已输出：%s；结果：%s",
            result["outputs"]["parse_report"],
            "通过" if result["parse_report"].get("passed") else "失败",
        )
        if result["parse_report"].get("passed"):
            print_success("商务通日报数据解析完成")
            verbose_print(f"报告：{result['outputs']['daily_data']}")
        else:
            print_error("商务通日报数据解析失败")
            verbose_print(f"报告：{result['outputs']['parse_report']}")
        return
    if args.mode == "merge-data":
        result = merge_data_files(config=config, root=ROOT, logger=logger, period=args.period)
        if result["validate_report"].get("passed"):
            print_success(f"数据合并完成：{result['outputs']['merged']}")
            print_quiet_line(f"合并自检通过：{result['outputs']['validate_report']}")
        else:
            print_error(f"数据合并失败，已输出自检报告：{result['outputs']['validate_report']}")
        return
    if args.mode == "merge-daily":
        result = merge_daily_files(config=config, root=ROOT, logger=logger, target_date=args.date)
        if result["validate_report"].get("passed"):
            print_success(f"日报数据合并完成：{result['outputs']['merged']}")
            print_quiet_line(f"日报合并自检通过：{result['outputs']['validate_report']}")
        else:
            print_error(f"日报数据合并失败，已输出自检报告：{result['outputs']['validate_report']}")
        return
    if args.mode == "write-excel":
        report = write_merged_hourly_data(config=config, root=ROOT, logger=logger, period=args.period)
        out = ROOT / "reports" / "write_report.json"
        if report.get("errors"):
            print_error(f"Excel 正式写入中断，已输出报告：reports/write_report.json")
        else:
            print_success(f"Excel 正式写入完成并复核通过：reports/write_report.json")
        return
    if args.mode == "write-daily":
        report = write_merged_daily_data(config=config, root=ROOT, logger=logger, target_date=args.date)
        out = ROOT / "reports" / "daily_write_report.json"
        if report.get("errors"):
            print_error(f"日报 Excel 写入中断，已输出报告：reports/daily_write_report.json")
        else:
            print_success(f"日报 Excel 写入完成并复核通过：reports/daily_write_report.json")
        return
    if args.mode == "run":
        credential_report = check_baidu_credentials(ROOT, config)
        if not credential_report.get("passed"):
            print_credential_report(credential_report)
            print_error("凭据预检未通过，请检查 secrets/secrets.json")
            return 1
        report = run_half_auto_pipeline(
            config=config,
            root=ROOT,
            logger=logger,
            period=args.period,
            kst_file=args.file,
            assume_yes=args.yes,
            confirm_before_run=True,
        )
        out = ROOT / "reports" / "final_run_report.json"
        if report.get("passed"):
            print_final_success(f"半自动一键流完成：reports/final_run_report.json")
        else:
            print_final_failure(f"半自动一键流中断，失败步骤：{report.get('failed_step')}，报告：reports/final_run_report.json")
        return 0 if report.get("passed") else 1
    if args.mode == "run-daily":
        credential_report = check_baidu_credentials(ROOT, config)
        if not credential_report.get("passed"):
            print_credential_report(credential_report)
            print_error("凭据预检未通过，请检查 secrets/secrets.json")
            return 1
        report = run_daily_pipeline(
            config=config,
            root=ROOT,
            logger=logger,
            target_date=args.date,
            kst_file=args.file,
        )
        out = ROOT / "reports" / "daily_final_run_report.json"
        if report.get("passed"):
            print_final_success(f"日报一键流完成：reports/daily_final_run_report.json")
        else:
            print_final_failure(f"日报一键流中断，失败步骤：{report.get('failed_step')}，报告：reports/daily_final_run_report.json")
        return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main() or 0)
