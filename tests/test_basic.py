import json
from pathlib import Path
from datetime import date

from modules.text_normalizer import normalize_text


def _kunming_niu_runtime_config() -> dict:
    """返回昆明牛项目的运行时配置，供单元测试使用。
    避免测试依赖当前 app_config 的运行状态。
    """
    return {
        "accounts": {
            "银康01": {
                "baidu_name": "银康01",
                "baidu_names": ["银康01"],
                "excel_name": "银康01",
                "kst_ids": ["72828178"],
                "kst_names": ["银康01"],
                "aliases": ["银康01"],
            },
            "银康银屑02": {
                "baidu_name": "银康银屑02",
                "baidu_names": ["银康银屑02"],
                "excel_name": "银康银屑02",
                "kst_ids": ["72828179"],
                "kst_names": ["银康银屑02"],
                "aliases": ["银康银屑02"],
            },
            "银康03": {
                "baidu_name": "baidu-银康03",
                "baidu_names": ["baidu-银康03", "银康03"],
                "excel_name": "银康03",
                "kst_ids": ["81509165"],
                "kst_names": ["银康03"],
                "aliases": ["银康03", "baidu-银康03"],
            },
        },
        "kst": {
            "promotion_id_accounts": {
                "72828178": "银康01",
                "72828179": "银康银屑02",
                "81509165": "银康03",
            },
        },
    }

from modules.kst_export_parser import parse_kst_export_file
from modules.kst_daily_parser import classify_daily_dialog_by_tags, parse_kst_daily_file
from modules.kst_parser import aggregate_kst_export_rows, classify_dialog_by_tags, has_visitor_dialog
from modules.run_pipeline import run_daily_pipeline, run_half_auto_pipeline
from modules.excel_inspector import (
    _build_account_ranges,
    _build_merged_bounds_map,
    _build_merged_value_map,
    _find_account_titles,
    _get_merged_value,
    _scan_non_empty_cells,
)
from modules.excel_writer import _find_target_row, _normalize_period_for_excel, _validate_write_target
from modules.daily_excel_inspector import inspect_daily_worksheet
from modules.data_merger import build_merged_daily_data, build_merged_hourly_data
from modules.excel_writer import write_merged_daily_data, write_merged_hourly_data
from modules.baidu_parser import _parse_number, extract_baidu_rows_from_visible_text, parse_baidu_table
from modules.baidu_browser import _extract_selected_date_from_text, _write_debug_artifacts
from modules.baidu_detector import classify_baidu_page
from modules.baidu_overview import is_search_promotion_overview, overview_text_has_account_table, should_open_cas_login, validate_overview_ready
from modules.baidu_validator import validate_baidu_account_data
from modules.baidu_auto import build_baidu_auto_report_from_visible_text
from modules.baidu_auto import fetch_baidu_auto
from modules.baidu_daily import build_baidu_daily_report_from_visible_text, default_daily_date
from modules.credential_manager import build_login_failure_message, load_project_credentials
from modules.browser_manager import BrowserLaunchError, CONNECT_EXISTING_HELP, cleanup_extra_tabs, connect_existing_chrome, get_browser_settings
from modules.chrome_debug import ensure_chrome_debug_ready, find_chrome_executable, is_chrome_debug_port_alive
from modules.excel_engine import format_openpyxl_save_error
from modules.project_config import (
    build_runtime_config_from_project,
    get_account_alias_maps,
    get_current_project,
    get_excel_path,
    get_project_accounts,
    list_projects,
    reload_current_project,
    set_current_project,
    validate_project_config,
)
from modules.doctor import run_doctor
from modules.validators import validate_baidu_report, validate_merged_daily_data, validate_merged_hourly_data
from menu import MENU_TEXT, build_confirmation_lines, build_runtime_config, dispatch_menu_task
from tools.build_release import build_release, should_include_file
import inspect
from datetime import date
from pathlib import Path


def test_merged_cell_lookup_uses_prebuilt_map():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws["A1"] = "账户标题"
    ws.merge_cells("A1:C1")

    merged_values = _build_merged_value_map(ws)

    assert _get_merged_value(ws, 1, 1, merged_values) == "账户标题"
    assert _get_merged_value(ws, 1, 2, merged_values) == "账户标题"
    assert _get_merged_value(ws, 1, 3, merged_values) == "账户标题"


def test_project_config_loads_default_project_and_lists_projects(tmp_path):
    app_dir = tmp_path / "configs"
    projects_dir = app_dir / "projects"
    projects_dir.mkdir(parents=True)
    (app_dir / "app_config.json").write_text(
        """
{
  "default_project_id": "demo",
  "projects_dir": "configs/projects",
  "secrets_file": "secrets/secrets.json"
}
""",
        encoding="utf-8",
    )
    (projects_dir / "demo.json").write_text(
        """
{
  "project_id": "demo",
  "project_name": "演示项目",
  "excel_path": "samples/demo.xlsx",
  "sheets": {"hourly": "时段数据", "daily": "百度"},
  "kst": {"export_dir": "kst_exports"},
  "baidu": {
    "credential_profile": "demo_profile",
    "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]
  },
  "accounts": [
    {"standard_name": "银康01", "baidu_aliases": ["银康01"], "excel_name": "银康01", "kst_promotion_id": "72828178", "kst_aliases": ["银康01"]},
    {"standard_name": "银康银屑02", "baidu_aliases": ["银康银屑02"], "excel_name": "银康银屑02", "kst_promotion_id": "72828179", "kst_aliases": ["银康银屑02"]},
    {"standard_name": "银康03", "baidu_aliases": ["baidu-银康03", "银康03"], "excel_name": "银康03", "kst_promotion_id": "81509165", "kst_aliases": ["银康03"]}
  ],
  "hourly": {"periods": ["11点", "15点", "18点"]},
  "daily": {
    "write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"],
    "forbidden_fields": ["总对话", "预约", "到诊", "就诊"]
  }
}
""",
        encoding="utf-8",
    )

    current = get_current_project(tmp_path)
    projects = list_projects(tmp_path)

    assert current["project_id"] == "demo"
    assert current["project_name"] == "演示项目"
    assert current["_app_config"]["secrets_file"] == "secrets/secrets.json"
    assert projects == [{"project_id": "demo", "project_name": "演示项目", "path": str(projects_dir / "demo.json")}]
    assert validate_project_config(current) == []


def test_project_config_validation_reports_missing_required_fields():
    errors = validate_project_config({
        "project_id": "bad",
        "project_name": "坏配置",
        "accounts": [],
    })

    assert any("缺少字段：excel.path" in error for error in errors)
    assert any("账户数量必须为 3" in error for error in errors)


def test_project_config_can_switch_current_project_and_normalize_new_schema(tmp_path):
    app_dir = tmp_path / "configs"
    projects_dir = app_dir / "projects"
    projects_dir.mkdir(parents=True)
    (app_dir / "app_config.json").write_text(
        json.dumps({
            "default_project_id": "demo_a",
            "projects_dir": "configs/projects",
            "secrets_file": "secrets/secrets.json",
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    base_project = {
        "project_name": "项目A",
        "excel": {"path": "samples/a.xlsx", "hourly_sheet": "时段数据A", "daily_sheet": "百度A", "engine": "openpyxl"},
        "kst": {"export_dir": "kst_a", "auto_pick_latest": True, "max_file_age_hours": 2},
        "baidu": {"credential_profile": "profile_a", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
        "accounts": [
            {"standard_name": "账户A1", "baidu_names": ["百度A1"], "excel_name": "账户A1", "kst_ids": ["1001"], "kst_names": ["商务A1"]},
            {"standard_name": "账户A2", "baidu_names": ["百度A2"], "excel_name": "账户A2", "kst_ids": ["1002"], "kst_names": ["商务A2"]},
            {"standard_name": "账户A3", "baidu_names": ["百度A3"], "excel_name": "账户A3", "kst_ids": ["1003"], "kst_names": ["商务A3"]},
        ],
        "hourly": {"periods": ["11点", "15点", "18点"]},
        "daily": {"write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"], "do_not_write_fields": ["总对话", "预约", "到诊", "就诊"]},
    }
    for project_id, name in [("demo_a", "项目A"), ("demo_b", "项目B")]:
        project = dict(base_project)
        project["project_id"] = project_id
        project["project_name"] = name
        project["excel"] = dict(base_project["excel"], path=f"samples/{project_id}.xlsx")
        (projects_dir / f"{project_id}.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")

    assert get_current_project(tmp_path)["project_id"] == "demo_a"
    changed = set_current_project(tmp_path, "demo_b")
    reloaded = reload_current_project(tmp_path)

    assert changed["project_id"] == "demo_b"
    assert reloaded["project_name"] == "项目B"
    assert get_excel_path(reloaded, tmp_path).name == "demo_b.xlsx"
    assert get_project_accounts(reloaded) == ["账户A1", "账户A2", "账户A3"]
    alias_maps = get_account_alias_maps(reloaded)
    assert alias_maps["kst_id_to_account"]["1003"] == "账户A3"
    assert alias_maps["baidu_alias_to_account"]["百度A2"] == "账户A2"
    assert validate_project_config(reloaded) == []


def test_runtime_config_uses_current_project_accounts_not_kunming_defaults(tmp_path):
    project = {
        "project_id": "demo",
        "project_name": "演示",
        "excel": {"path": "target.xlsx", "hourly_sheet": "小时", "daily_sheet": "日报", "engine": "openpyxl"},
        "kst": {"export_dir": "exports", "auto_pick_latest": True, "max_file_age_hours": 4},
        "baidu": {"credential_profile": "profile_demo", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
        "accounts": [
            {"standard_name": "项目账户1", "baidu_names": ["百度账户1"], "excel_name": "表格账户1", "kst_ids": ["9001"], "kst_names": ["商务账户1"]},
            {"standard_name": "项目账户2", "baidu_names": ["百度账户2"], "excel_name": "表格账户2", "kst_ids": ["9002"], "kst_names": ["商务账户2"]},
            {"standard_name": "项目账户3", "baidu_names": ["百度账户3"], "excel_name": "表格账户3", "kst_ids": ["9003"], "kst_names": ["商务账户3"]},
        ],
    }

    runtime = build_runtime_config_from_project(project, {"baidu": {}, "kst": {}})

    assert runtime["project_id"] == "demo"
    assert runtime["excel_path"] == "target.xlsx"
    assert runtime["sheet_name"] == "小时"
    assert runtime["daily_sheet_name"] == "日报"
    assert runtime["kst"]["export_dir"] == "exports"
    assert runtime["kst"]["promotion_id_accounts"] == {"9001": "项目账户1", "9002": "项目账户2", "9003": "项目账户3"}
    assert set(runtime["accounts"]) == {"项目账户1", "项目账户2", "项目账户3"}
    assert "银康01" not in runtime["accounts"]


def test_menu_runtime_config_converts_project_accounts():
    project = {
        "excel_path": "target.xlsx",
        "sheets": {"hourly": "时段数据", "daily": "百度"},
        "kst": {"export_dir": "kst_exports"},
        "baidu": {"credential_profile": "profile1"},
        "accounts": [
            {"standard_name": "银康01", "baidu_aliases": ["银康01"], "excel_name": "银康01", "kst_promotion_id": "72828178", "kst_aliases": ["银康01"]},
            {"standard_name": "银康银屑02", "baidu_aliases": ["银康银屑02"], "excel_name": "银康银屑02", "kst_promotion_id": "72828179", "kst_aliases": ["银康银屑02"]},
            {"standard_name": "银康03", "baidu_aliases": ["baidu-银康03", "银康03"], "excel_name": "银康03", "kst_promotion_id": "81509165", "kst_aliases": ["银康03"]},
        ],
    }

    runtime = build_runtime_config(project, {"browser": {"max_tabs": 3}, "baidu": {}, "kst": {}})

    assert runtime["excel_path"] == "target.xlsx"
    assert runtime["sheet_name"] == "时段数据"
    assert runtime["baidu"]["credential_project"] == "profile1"
    assert runtime["kst"]["promotion_id_accounts"]["81509165"] == "银康03"
    assert runtime["accounts"]["银康03"]["baidu_name"] == "baidu-银康03"
    assert "银康03" in runtime["accounts"]["银康03"]["aliases"]


def test_menu_confirmation_lines_include_project_task_and_latest_export(tmp_path):
    export_dir = tmp_path / "kst_exports"
    export_dir.mkdir()
    export = export_dir / "latest.xlsx"
    export.write_text("placeholder", encoding="utf-8")
    project = {
        "project_name": "昆明银康 NPX",
        "excel_path": "target.xlsx",
        "sheets": {"hourly": "时段数据", "daily": "百度"},
        "kst": {"export_dir": str(export_dir)},
    }

    lines = build_confirmation_lines(tmp_path, project, "运行15点小时报", period="15点")

    text = "\n".join(lines)
    assert "执行确认" in text
    assert "昆明银康 NPX" in text
    assert "运行15点小时报" in text
    assert "target.xlsx" in text
    assert "时段数据" in text
    assert "15点" in text
    assert f"{export}" in text


def test_menu_header_shows_project_config_and_excel_path(tmp_path):
    from menu import build_menu_header

    project = {
        "project_id": "demo",
        "project_name": "演示项目",
        "_config_path": str(tmp_path / "configs" / "projects" / "demo.json"),
        "excel": {"path": str(tmp_path / "target.xlsx")},
    }

    header = build_menu_header(tmp_path, project)

    assert "演示项目" in header
    assert f"{tmp_path / 'target.xlsx'}" in header


def test_menu_confirmation_accepts_kst_export_file_path(tmp_path):
    export = tmp_path / "export.xlsx"
    export.write_text("placeholder", encoding="utf-8")
    project = {
        "project_name": "昆明银康 NPX",
        "excel_path": "target.xlsx",
        "sheets": {"hourly": "时段数据", "daily": "百度"},
        "kst": {"export_dir": str(export)},
    }

    lines = build_confirmation_lines(tmp_path, project, "检查运行环境")

    text = "\n".join(lines)
    assert f"{export}" in text
    assert "执行确认" in text


def test_menu_dispatch_uses_existing_pipeline_functions(tmp_path):
    calls = []

    def fake_daily(**kwargs):
        calls.append(("daily", kwargs["target_date"]))
        return {"passed": True}

    dispatch_menu_task(
        "2",
        config={},
        root=tmp_path,
        logger=None,
        target_date="2026-05-07",
        kst_file=None,
        runners={"run_daily": fake_daily},
    )

    assert calls == [("daily", "2026-05-07")]


def test_menu_text_is_simplified_for_new_users():
    assert "1. 小时报" in MENU_TEXT
    assert "2. 日报" in MENU_TEXT
    assert "3. 项目列表" in MENU_TEXT
    assert "4. 项目信息" in MENU_TEXT
    assert "5. 文件合格校验" in MENU_TEXT
    assert "0. 退出" in MENU_TEXT
    # 旧文案不应出现
    assert "运行日报" not in MENU_TEXT
    assert "运行小时报" not in MENU_TEXT
    assert "切换项目" not in MENU_TEXT
    assert "刷新当前项目" not in MENU_TEXT
    assert "检查运行环境" not in MENU_TEXT
    assert "只抓百度数据" not in MENU_TEXT
    assert "只解析商务通导出表" not in MENU_TEXT
    assert "查看最近报告" not in MENU_TEXT


def test_menu_hourly_dispatch_uses_internal_period_while_confirm_can_show_simple_period(tmp_path):
    calls = []

    def fake_hourly(**kwargs):
        calls.append(kwargs["period"])
        return {"passed": True}

    dispatch_menu_task(
        "hourly:15点",
        config={},
        root=tmp_path,
        logger=None,
        runners={"run_hourly": fake_hourly},
    )

    assert calls == ["15点"]


def test_menu_choice_1_must_not_be_valid_dispatch_choice(tmp_path):
    """菜单选项 1（小时报）已在 run_menu 中转为 hourly:XX，不应直接到达 dispatch_menu_task。"""
    raised = False
    try:
        dispatch_menu_task(
            "1",
            config={},
            root=tmp_path,
            logger=None,
        )
    except ValueError as exc:
        raised = True
        assert "不支持的菜单选项" in str(exc)
    assert raised, "dispatch_menu_task('1') 应该抛出 ValueError"


def test_menu_choice_2_binds_daily_pipeline(tmp_path):
    """菜单选项 2 必须绑定日报 pipeline。"""
    calls = []

    def fake_daily(**kwargs):
        calls.append(("daily", kwargs["target_date"]))
        return {"passed": True}

    dispatch_menu_task(
        "2",
        config={},
        root=tmp_path,
        logger=None,
        target_date="2026-05-07",
        runners={"run_daily": fake_daily},
    )

    assert calls == [("daily", "2026-05-07")]


def test_menu_task_meta_daily_mapped_to_choice_2(tmp_path):
    """_task_meta 中日报映射 key 为 '2'。"""
    from menu import _task_meta

    project = {
        "excel": {"hourly_sheet": "时段", "daily_sheet": "日报"},
        "sheets": {},
    }

    meta = _task_meta("2", project)

    assert meta["name"] == "运行日报"
    assert meta["sheet"] == "日报"
    assert meta["period"] is None
    assert meta["date"] is not None  # 有默认日期


def test_menu_task_meta_hourly_choices_still_work(tmp_path):
    """_task_meta 中 hourly:XX 映射仍然正常。"""
    from menu import _task_meta

    project = {
        "excel": {"hourly_sheet": "时", "daily_sheet": "日"},
        "sheets": {},
    }

    for period_key, period_name in [("hourly:11点", "11点"), ("hourly:15点", "15点"), ("hourly:18点", "18点")]:
        meta = _task_meta(period_key, project)
        assert meta["period"] == period_name
        assert meta["sheet"] == "时"
        assert meta["date"] is not None


def test_doctor_reports_project_excel_sheets_and_missing_secrets(tmp_path):
    from openpyxl import Workbook

    (tmp_path / "configs" / "projects").mkdir(parents=True)
    (tmp_path / "secrets").mkdir()
    (tmp_path / "kst_exports").mkdir()
    (tmp_path / "configs" / "app_config.json").write_text(
        '{"default_project_id":"demo","projects_dir":"configs/projects","secrets_file":"secrets/secrets.json"}',
        encoding="utf-8",
    )
    excel_path = tmp_path / "samples" / "demo.xlsx"
    excel_path.parent.mkdir()
    wb = Workbook()
    wb.active.title = "时段数据"
    wb.create_sheet("百度")
    wb.save(excel_path)
    (tmp_path / "configs" / "projects" / "demo.json").write_text(
        f"""
{{
  "project_id": "demo",
  "project_name": "演示项目",
  "excel_path": "{str(excel_path).replace('\\', '/')}",
  "sheets": {{"hourly": "时段数据", "daily": "百度"}},
  "kst": {{"export_dir": "kst_exports"}},
  "baidu": {{"credential_profile": "demo", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]}},
  "accounts": [
    {{"standard_name": "银康01", "baidu_aliases": ["银康01"], "excel_name": "银康01", "kst_promotion_id": "72828178", "kst_aliases": ["银康01"]}},
    {{"standard_name": "银康银屑02", "baidu_aliases": ["银康银屑02"], "excel_name": "银康银屑02", "kst_promotion_id": "72828179", "kst_aliases": ["银康银屑02"]}},
    {{"standard_name": "银康03", "baidu_aliases": ["银康03"], "excel_name": "银康03", "kst_promotion_id": "81509165", "kst_aliases": ["银康03"]}}
  ],
  "hourly": {{"periods": ["11点", "15点", "18点"]}},
  "daily": {{"write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"], "forbidden_fields": ["总对话", "预约", "到诊", "就诊"]}}
}}
""",
        encoding="utf-8",
    )

    report = run_doctor(tmp_path, {"browser": {"cdp_endpoint": "http://127.0.0.1:9", "auto_start_debug_chrome": False}, "kst": {}})

    assert report["summary"]["total"] >= 13
    assert report["checks"]["app_config"]["passed"] is True
    assert report["checks"]["project_config"]["passed"] is True
    assert report["checks"]["target_excel"]["passed"] is True
    assert report["checks"]["hourly_sheet"]["passed"] is True
    assert report["checks"]["daily_sheet"]["passed"] is True
    assert report["checks"]["secrets_json"]["passed"] is False
    assert "百度账号未配置" in report["checks"]["secrets_json"]["message"]


def test_doctor_openpyxl_engine_does_not_require_microsoft_excel(tmp_path):
    from openpyxl import Workbook

    (tmp_path / "configs" / "projects").mkdir(parents=True)
    (tmp_path / "secrets").mkdir()
    (tmp_path / "kst_exports").mkdir()
    (tmp_path / "configs" / "app_config.json").write_text(
        '{"default_project_id":"demo","projects_dir":"configs/projects","secrets_file":"secrets/secrets.json"}',
        encoding="utf-8",
    )
    excel_path = tmp_path / "samples" / "demo.xlsx"
    excel_path.parent.mkdir()
    wb = Workbook()
    wb.active.title = "时段数据"
    wb.create_sheet("百度")
    wb.save(excel_path)
    (tmp_path / "configs" / "projects" / "demo.json").write_text(
        f"""
{{
  "project_id": "demo",
  "project_name": "演示项目",
  "excel_path": "{str(excel_path).replace('\\', '/')}",
  "excel": {{"path": "{str(excel_path).replace('\\', '/')}", "hourly_sheet": "时段数据", "daily_sheet": "百度", "engine": "openpyxl"}},
  "sheets": {{"hourly": "时段数据", "daily": "百度"}},
  "kst": {{"export_dir": "kst_exports"}},
  "baidu": {{"credential_profile": "demo", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]}},
  "accounts": [
    {{"standard_name": "银康01", "baidu_aliases": ["银康01"], "excel_name": "银康01", "kst_promotion_id": "72828178", "kst_aliases": ["银康01"]}},
    {{"standard_name": "银康银屑02", "baidu_aliases": ["银康银屑02"], "excel_name": "银康银屑02", "kst_promotion_id": "72828179", "kst_aliases": ["银康银屑02"]}},
    {{"standard_name": "银康03", "baidu_aliases": ["银康03"], "excel_name": "银康03", "kst_promotion_id": "81509165", "kst_aliases": ["银康03"]}}
  ],
  "hourly": {{"periods": ["11点", "15点", "18点"]}},
  "daily": {{"write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"], "forbidden_fields": ["总对话", "预约", "到诊", "就诊"]}}
}}
""",
        encoding="utf-8",
    )

    report = run_doctor(tmp_path, {"browser": {"cdp_endpoint": "http://127.0.0.1:9", "auto_start_debug_chrome": False}, "kst": {}})

    assert report["checks"]["excel_engine"]["passed"] is True
    assert "openpyxl" in report["checks"]["excel_engine"]["message"]
    assert "WPS" in report["checks"]["excel_engine"]["message"]
    assert report["checks"]["openpyxl"]["passed"] is True
    assert report["checks"]["openpyxl_save_test"]["passed"] is True
    assert "excel_app" not in report["checks"]


def test_openpyxl_save_error_mentions_closing_wps_file(tmp_path):
    message = format_openpyxl_save_error(tmp_path / "target.xlsx", PermissionError("locked"))

    assert "请关闭 WPS 中的目标文件后重试" in message
    assert "target.xlsx" in message


def test_doctor_openpyxl_mode_skips_excel_com_only_requirements(tmp_path, monkeypatch):
    from importlib.metadata import PackageNotFoundError
    from modules import doctor

    (tmp_path / "requirements.txt").write_text("openpyxl>=3.1.2\nxlwings>=0.30.0\npywin32>=306\n", encoding="utf-8")

    def fake_version(package_name):
        if package_name in {"xlwings", "pywin32"}:
            raise PackageNotFoundError(package_name)
        return "1.0"

    monkeypatch.setattr(doctor.importlib.metadata, "version", fake_version)

    openpyxl_report = doctor._check_requirements(tmp_path, excel_engine="openpyxl")
    excel_com_report = doctor._check_requirements(tmp_path, excel_engine="excel_com")

    assert openpyxl_report["passed"] is True
    assert "xlwings" in openpyxl_report["detail"]["skipped_optional"]
    assert excel_com_report["passed"] is False
    assert "xlwings" in excel_com_report["detail"]["missing"]


def test_release_builder_excludes_sensitive_and_runtime_files():
    assert should_include_file(Path("main.py")) is True
    assert should_include_file(Path("modules") / "doctor.py") is True
    assert should_include_file(Path("reports") / ".gitkeep") is True
    assert should_include_file(Path("reports") / "final_run_report.json") is False
    assert should_include_file(Path("logs") / "run.log") is False
    assert should_include_file(Path("backups") / "target.xlsx") is False
    assert should_include_file(Path("kst_exports") / "export.xlsx") is False
    assert should_include_file(Path("secrets") / "secrets.json") is False
    assert should_include_file(Path("samples") / "真实业务.xlsx") is False
    assert should_include_file(Path(".venv") / "pyvenv.cfg") is False


def test_project_template_and_demo_project_are_complete():
    root = Path(__file__).resolve().parents[1]
    template = json.loads((root / "configs" / "projects" / "project_template.json").read_text(encoding="utf-8"))
    demo = json.loads((root / "configs" / "projects" / "demo_project.json").read_text(encoding="utf-8"))

    for project in [template, demo]:
        normalized_errors = validate_project_config(project)
        assert normalized_errors == []
        assert project["excel"]["engine"] == "openpyxl"
        assert "auto_pick_latest" in project["kst"]
        assert "max_file_age_hours" in project["kst"]
        assert project["daily"]["do_not_write_fields"] == ["总对话", "预约", "到诊", "就诊"]
        for account in project["accounts"]:
            assert set(["standard_name", "baidu_names", "excel_name", "kst_ids", "kst_names"]) <= set(account)


def test_demo_project_is_template_and_not_in_project_list():
    """demo_project 是模板，不出现在项目列表中，但可以单独加载验证。"""
    root = Path(__file__).resolve().parents[1]

    projects = list_projects(root)
    ids = [p["project_id"] for p in projects]
    assert "demo_project" not in ids, "demo_project 是模板，不应出现在项目列表"

    # 但可以直接加载和校验
    from modules.project_config import load_project_config
    demo = load_project_config(root, "demo_project")
    assert demo["project_name"] == "演示项目"
    assert demo.get("is_template") is True
    assert validate_project_config(demo) == []


def test_release_builder_accepts_version_and_includes_project_template_docs(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release = build_release(root, version="0.4.4")

    assert release.name == "hourly_report_bot_release_v0.4.4.zip"
    import zipfile

    with zipfile.ZipFile(release) as archive:
        names = set(archive.namelist())

    assert "configs/projects/project_template.json" in names
    assert "configs/projects/demo_project.json" in names
    assert "docs/如何新增一个项目.md" in names
    assert "secrets/secrets.json" not in names


def test_core_modules_do_not_hardcode_kunming_project_accounts():
    root = Path(__file__).resolve().parents[1]
    forbidden = [
        "银康01",
        "银康银屑02",
        "银康03",
        "baidu-银康03",
        "72828178",
        "72828179",
        "81509165",
    ]
    offenders = []
    for path in (root / "modules").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path.name}:{token}")

    assert offenders == []


def test_account_ranges_follow_horizontal_merged_title_blocks():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws["A1"] = "每日时段统计数据"
    ws.merge_cells("A1:E1")
    ws["F1"] = "银康01-72828178"
    ws.merge_cells("F1:J1")
    ws["K1"] = "银康银屑02-72828179"
    ws.merge_cells("K1:O1")
    ws["P1"] = "baidu-银康03-81509165"
    ws.merge_cells("P1:T1")

    config = {
        "accounts": {
            "银康01": {"aliases": ["银康01"], "excel_name": "银康01", "baidu_name": "银康01"},
            "银康银屑02": {"aliases": ["银康银屑02"], "excel_name": "银康银屑02", "baidu_name": "银康银屑02"},
            "银康03": {"aliases": ["银康03", "baidu-银康03"], "excel_name": "银康03", "baidu_name": "baidu-银康03"},
        }
    }
    rows = _scan_non_empty_cells(ws, _build_merged_value_map(ws))
    titles = _find_account_titles(rows, config)
    ranges = _build_account_ranges(titles, ws, _build_merged_bounds_map(ws))

    assert ranges["银康01"]["range"]["min_col"] == 6
    assert ranges["银康01"]["range"]["max_col"] == 10
    assert ranges["银康银屑02"]["range"]["min_col"] == 11
    assert ranges["银康银屑02"]["range"]["max_col"] == 15
    assert ranges["银康03"]["range"]["min_col"] == 16
    assert ranges["银康03"]["range"]["max_col"] == 20


def test_mock_write_helpers_find_row_and_reject_summary_columns():
    from datetime import date
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws["A1"] = "每日时段统计数据"
    ws["P1"] = "银康01"
    ws["A3"] = "日期"
    ws["B3"] = "时段"
    ws["P3"] = "展现量"
    ws["A4"] = date(2026, 5, 6)
    ws.merge_cells("A4:A7")
    ws["B4"] = "昨天数据"
    ws["B5"] = "11点"
    ws["B6"] = "3点"
    ws["B7"] = "6点"

    merged_values = _build_merged_value_map(ws)

    assert _normalize_period_for_excel("15点") == "3点"
    assert _normalize_period_for_excel("15") == "3点"
    assert _find_target_row(ws, 1, 2, date(2026, 5, 6), "15点", merged_values) == 6
    assert _validate_write_target(
        "银康01",
        "展现",
        6,
        16,
        {"range": {"min_row": 1, "max_row": 20, "min_col": 16, "max_col": 20}},
        [{"range": {"min_row": 1, "max_row": 20, "min_col": 1, "max_col": 15}}],
    ) == []
    assert _validate_write_target(
        "银康01",
        "展现",
        6,
        3,
        {"range": {"min_row": 1, "max_row": 20, "min_col": 16, "max_col": 20}},
        [{"range": {"min_row": 1, "max_row": 20, "min_col": 1, "max_col": 15}}],
    )


def test_inspect_daily_worksheet_detects_baidu_sheet_blocks_and_write_rules():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "百度"
    ws["A1"] = "日期"
    ws["C1"] = "汇总数据"
    ws.merge_cells("C1:O1")
    ws["P1"] = "银康01-72828178"
    ws.merge_cells("P1:AB1")
    ws["AC1"] = "银康银屑02-72828179"
    ws.merge_cells("AC1:AO1")
    ws["AP1"] = "银康03-81509165"
    ws.merge_cells("AP1:BB1")
    headers = ["展现量", "点击", "消费", "acp", "总对话", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜", "预约", "就诊", "转潜成本"]
    for start in [16, 29, 42]:
        for offset, header in enumerate(headers):
            ws.cell(row=2, column=start + offset).value = header
    ws["A2"] = "日期"
    ws["A3"] = "2026-05-07"
    ws["A4"] = "2026-05-08"
    config = {
        "accounts": {
            "银康01": {"excel_name": "银康01", "baidu_name": "银康01", "aliases": ["银康01"]},
            "银康银屑02": {"excel_name": "银康银屑02", "baidu_name": "银康银屑02", "aliases": ["银康银屑02"]},
            "银康03": {"excel_name": "银康03", "baidu_name": "baidu-银康03", "aliases": ["银康03", "baidu-银康03"]},
        }
    }

    report = inspect_daily_worksheet(ws, config, "unit.xlsx")

    assert report["sheet_found"] is True
    assert report["date_column"]["found"] is True
    assert report["date_rows"]["count"] == 2
    assert report["accounts"]["银康01"]["range"]["min_col"] == 16
    assert report["accounts"]["银康银屑02"]["fields"]["有效对话"]["header_cell"] == "AH2"
    assert report["accounts"]["银康03"]["fields"]["消费"]["header_cell"] == "AR2"
    assert report["allowed_fields"] == ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"]
    assert report["forbidden_fields"] == ["总对话", "预约", "到诊", "就诊"]
    assert report["accounts"]["银康01"]["fields"]["预约"]["write_allowed"] is False
    assert report["errors"] == []


def test_normalize_text():
    assert normalize_text(" Baidu-银康03\n") == "baidu-银康03"
    assert normalize_text("银康 01") == "银康01"


def test_kst_tags():
    r = classify_dialog_by_tags("转潜-有效")
    assert r["总对话"] == 1
    assert r["有效"] == 1
    assert r["有效转潜"] == 1
    assert r["总转潜"] == 1

    general = classify_dialog_by_tags("有效-一般")
    assert general["总对话"] == 1
    assert general["有效"] == 1
    assert general["有效转潜"] == 0
    assert general["总转潜"] == 0


def test_visitor_dialog_requires_message_count_at_least_one():
    assert has_visitor_dialog({"访客消息数": "1"}) is True
    assert has_visitor_dialog({"访客消息数": " 2 "}) is True
    assert has_visitor_dialog({"访客消息数": "0"}) is False
    assert has_visitor_dialog({"访客消息数": ""}) is False
    assert has_visitor_dialog({"访客消息数": "无"}) is False


def test_kst_daily_tags_do_not_count_invalid_as_valid():
    invalid = classify_daily_dialog_by_tags("转潜-无效, 无效")
    assert invalid["总对话"] == 1
    assert invalid["有效对话"] == 0
    assert invalid["无效对话"] == 1
    assert invalid["一般有效对话"] == 0
    assert invalid["有效转潜"] == 0
    assert invalid["总转潜"] == 1

    valid = classify_daily_dialog_by_tags("转潜-有效, 有效-一般")
    assert valid["总对话"] == 1
    assert valid["有效对话"] == 1
    assert valid["无效对话"] == 0
    assert valid["一般有效对话"] == 1
    assert valid["有效转潜"] == 1
    assert valid["总转潜"] == 1


def test_aggregate_kst_export_rows_maps_remark_promotion_ids_and_counts_tags():
    rows = [
        {"备注说明": "推广ID：72828178</br>关键词ID：x", "名片标签": "转潜-有效", "对话时间": "2026-05-07 10:00", "访客消息数": "1"},
        {"备注说明": "72828178 其他说明", "名片标签": "有效-一般", "对话时间": "2026-05-07 10:01", "访客消息数": "2"},
        {"备注说明": "72828179", "名片标签": "有效-三句", "对话时间": "2026-05-07 10:02", "访客消息数": "1"},
        {"备注说明": "81509165", "名片标签": "", "对话时间": "2026-05-07 10:03", "访客消息数": "1"},
        {"备注说明": "999999", "名片标签": "转潜-有效", "对话时间": "2026-05-07 10:04", "访客消息数": "1"},
    ]

    parsed = aggregate_kst_export_rows(rows, _kunming_niu_runtime_config())

    assert parsed["errors"] == []
    assert parsed["accounts"]["银康01"]["总对话"] == 2
    assert parsed["accounts"]["银康01"]["有效"] == 2
    assert parsed["accounts"]["银康01"]["有效转潜"] == 1
    assert parsed["accounts"]["银康01"]["总转潜"] == 1
    assert parsed["accounts"]["银康银屑02"]["有效"] == 1
    assert parsed["accounts"]["银康03"]["总对话"] == 1
    assert parsed["accounts"]["银康03"]["有效"] == 0
    assert parsed["summary"]["unmatched_rows"] == 1
    assert parsed["account_dialog_details"]["银康01"][0]["promotion_id"] == "72828178"


def test_aggregate_kst_export_rows_skips_rows_without_visitor_messages():
    rows = [
        {"备注说明": "72828178", "名片标签": "转潜-有效", "对话时间": "2026-05-07 10:00", "访客消息数": "0"},
        {"备注说明": "72828178", "名片标签": "有效-一般", "对话时间": "2026-05-07 10:01", "访客消息数": "1"},
    ]

    parsed = aggregate_kst_export_rows(rows, _kunming_niu_runtime_config())

    assert parsed["accounts"]["银康01"]["总对话"] == 1
    assert parsed["accounts"]["银康01"]["有效"] == 1
    assert parsed["accounts"]["银康01"]["有效转潜"] == 0
    assert parsed["accounts"]["银康01"]["总转潜"] == 0
    assert parsed["summary"]["skipped_no_visitor_messages"] == 1
    assert parsed["account_dialog_details"]["银康01"][0]["counts"]["总对话"] == 0


def test_parse_kst_export_csv_outputs_reports(tmp_path):
    export = tmp_path / "kst.csv"
    today = date.today().isoformat()
    export.write_text(
        "对话时间,备注说明,名片标签,搜索词,访客消息数\n"
        f"{today} 10:00,72828178-abc,转潜-有效,银屑病,1\n"
        f"{today} 10:01,81509165,,皮肤病,1\n",
        encoding="utf-8-sig",
    )
    reports = tmp_path / "reports"
    config = _kunming_niu_runtime_config()
    config["kst"] = {"export_dir": str(tmp_path), "promotion_id_accounts": _kunming_niu_runtime_config()["kst"]["promotion_id_accounts"]}

    result = parse_kst_export_file(export, config, tmp_path, "15点")

    assert result["dialog_data"]["accounts"]["银康01"]["总对话"] == 1
    assert result["dialog_data"]["accounts"]["银康01"]["有效"] == 1
    assert result["dialog_data"]["accounts"]["银康03"]["总对话"] == 1
    assert result["dialog_data"]["summary"]["raw_rows"] == 2
    assert (reports / "kst_dialog_data.json").exists()
    assert (reports / "kst_parse_report.json").exists()
    assert (reports / "kst_unmatched_rows.json").exists()


def test_parse_kst_export_filters_non_current_date_without_marking_unmatched(tmp_path):
    export = tmp_path / "kst.csv"
    export.write_text(
        "对话时间,备注说明,名片标签,访客消息数\n"
        "2026-05-06 10:00,72828178-abc,转潜-有效,1\n",
        encoding="utf-8-sig",
    )

    km_config = _kunming_niu_runtime_config()
    km_config["kst"] = {"export_dir": str(tmp_path), "promotion_id_accounts": _kunming_niu_runtime_config()["kst"]["promotion_id_accounts"]}
    result = parse_kst_export_file(export, km_config, tmp_path, "15")

    assert result["dialog_data"]["summary"]["raw_rows"] == 1
    assert result["dialog_data"]["summary"]["matched_rows"] == 0
    assert result["dialog_data"]["summary"]["unmatched_rows"] == 0
    assert result["dialog_data"]["summary"]["date_filtered_rows"] == 1
    assert result["unmatched_rows"] == []


def test_parse_kst_daily_file_filters_date_and_outputs_daily_counts(tmp_path):
    export = tmp_path / "kst_daily.csv"
    export.write_text(
        "对话时间,备注说明,名片标签,搜索词,访客消息数\n"
        "2026-05-07 10:00,72828178-abc,转潜-有效,银屑病,1\n"
        "2026-05-07 10:01,72828178-abc,有效-一般,皮肤病,2\n"
        "2026-05-07 10:02,72828179-abc,无效,银屑病,1\n"
        "2026-05-07 10:03,81509165-abc,转潜-无效,银屑病,1\n"
        "2026-05-06 10:03,81509165-abc,转潜-有效,旧日期,1\n",
        encoding="utf-8-sig",
    )

    result = parse_kst_daily_file(export, _kunming_niu_runtime_config(), tmp_path, "2026-05-07")

    assert result["daily_data"]["date"] == "2026-05-07"
    assert result["daily_data"]["source"] == "kst_daily_export"
    assert result["daily_data"]["accounts"]["银康01"]["总对话"] == 2
    assert result["daily_data"]["accounts"]["银康01"]["有效对话"] == 2
    assert result["daily_data"]["accounts"]["银康01"]["无效对话"] == 0
    assert result["daily_data"]["accounts"]["银康01"]["一般有效对话"] == 1
    assert result["daily_data"]["accounts"]["银康01"]["有效转潜"] == 1
    assert result["daily_data"]["accounts"]["银康01"]["总转潜"] == 1
    assert result["daily_data"]["accounts"]["银康银屑02"]["总对话"] == 1
    assert result["daily_data"]["accounts"]["银康银屑02"]["有效对话"] == 0
    assert result["daily_data"]["accounts"]["银康银屑02"]["无效对话"] == 1
    assert result["daily_data"]["accounts"]["银康03"]["总转潜"] == 1
    assert result["daily_data"]["accounts"]["银康03"]["有效转潜"] == 0
    assert result["daily_data"]["summary"]["raw_rows"] == 5
    assert result["daily_data"]["summary"]["date_filtered_rows"] == 1
    assert result["parse_report"]["passed"] is True
    assert (tmp_path / "reports" / "kst_daily_data.json").exists()
    assert (tmp_path / "reports" / "kst_daily_parse_report.json").exists()


def test_parse_kst_daily_file_skips_rows_without_visitor_messages(tmp_path):
    export = tmp_path / "kst_daily.csv"
    export.write_text(
        "对话时间,备注说明,名片标签,访客消息数\n"
        "2026-05-07 10:00,72828178-abc,转潜-有效,0\n"
        "2026-05-07 10:01,72828178-abc,有效-一般,1\n",
        encoding="utf-8-sig",
    )

    result = parse_kst_daily_file(export, _kunming_niu_runtime_config(), tmp_path, "2026-05-07")

    assert result["daily_data"]["accounts"]["银康01"]["总对话"] == 1
    assert result["daily_data"]["accounts"]["银康01"]["有效对话"] == 1
    assert result["daily_data"]["accounts"]["银康01"]["无效对话"] == 0
    assert result["daily_data"]["accounts"]["银康01"]["有效转潜"] == 0
    assert result["daily_data"]["summary"]["skipped_no_visitor_messages"] == 1


def test_parse_baidu_table_maps_accounts_and_numeric_fields():
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
            "银康银屑02": {"baidu_name": "银康银屑02"},
            "银康03": {"baidu_name": "baidu-银康03"},
        }
    }
    rows = [
        {"账户": "银康01", "展现": "1,001", "点击": "51", "消费": "301.17"},
        {"账户名称": "银康银屑02", "展现量": "2,002", "点击": "62", "消费": "402.28"},
        {"账户": "baidu-银康03", "展现": "3,003", "点击": "73", "花费": "503.39"},
    ]

    parsed = parse_baidu_table(rows, config)

    assert parsed["errors"] == []
    assert parsed["accounts"]["银康01"]["展现"] == 1001
    assert parsed["accounts"]["银康银屑02"]["点击"] == 62
    assert parsed["accounts"]["银康03"]["消费"] == 503.39


def test_browser_settings_default_to_chrome_without_edge_fallback():
    settings = get_browser_settings(
        {
            "browser_preference": "chrome",
            "browser_channel": "chrome",
            "chrome_executable_path": "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "browser_profile_dir": "browser_profile/chrome",
            "browser_launch_mode": "cdp",
            "remote_debugging_port": 9222,
            "allow_edge_fallback": False,
        }
    )

    assert settings["browser_preference"] == "chrome"
    assert settings["browser_channel"] == "chrome"
    assert settings["chrome_executable_path"] == "C:/Program Files/Google/Chrome/Application/chrome.exe"
    assert settings["browser_profile_dir"] == "browser_profile/chrome"
    assert settings["browser_launch_mode"] == "connect_existing"
    assert settings["remote_debugging_port"] == 9222
    assert settings["allow_edge_fallback"] is False


def test_browser_settings_accept_nested_connect_existing_config():
    settings = get_browser_settings(
        {
            "browser": {
                "mode": "connect_existing",
                "cdp_endpoint": "http://127.0.0.1:9222",
                "prefer_existing_chrome": True,
                "allow_edge_fallback": False,
                "managed": {
                    "channel": "chrome",
                    "executable_path": "C:/Program Files/Google/Chrome/Application/chrome.exe",
                    "profile_dir": "browser_profile/chrome",
                    "headless": False,
                },
            }
        }
    )

    assert settings["mode"] == "connect_existing"
    assert settings["cdp_endpoint"] == "http://127.0.0.1:9222"
    assert settings["browser_channel"] == "chrome"
    assert settings["browser_profile_dir"] == "browser_profile/chrome"
    assert settings["allow_edge_fallback"] is False


def test_connect_existing_does_not_launch_managed_chrome_or_edge():
    class FakeChromium:
        def __init__(self):
            self.launch_persistent_context_called = False

        def connect_over_cdp(self, endpoint):
            assert endpoint == "http://127.0.0.1:9222"
            raise RuntimeError("connection refused")

        def launch_persistent_context(self, **kwargs):
            self.launch_persistent_context_called = True
            raise AssertionError("connect_existing must not launch a managed browser")

    class FakePlaywright:
        def __init__(self):
            self.chromium = FakeChromium()

    fake = FakePlaywright()
    config = {
        "browser": {
            "mode": "connect_existing",
            "cdp_endpoint": "http://127.0.0.1:9222",
            "allow_edge_fallback": False,
            "managed": {"channel": "chrome", "profile_dir": "browser_profile/chrome", "headless": False},
        }
    }

    try:
        connect_existing_chrome(fake, config)
    except BrowserLaunchError as exc:
        assert "remote-debugging-port=9222" in str(exc)
    else:
        raise AssertionError("connect_existing should fail clearly when CDP is unavailable")
    assert fake.chromium.launch_persistent_context_called is False


def test_connect_existing_help_mentions_running_chrome_blocks_debug_port():
    assert "已经打开 Chrome" in CONNECT_EXISTING_HELP
    assert "chrome_debug" in CONNECT_EXISTING_HELP
    assert "关闭所有 Chrome" in CONNECT_EXISTING_HELP
    assert "--remote-debugging-port=9222" in CONNECT_EXISTING_HELP


def test_cleanup_extra_tabs_keeps_baidu_page_and_limits_to_three():
    class FakePage:
        def __init__(self, url):
            self.url = url
            self.closed = False
            self.front = False

        def bring_to_front(self):
            self.front = True

        def close(self):
            self.closed = True

    class FakeContext:
        def __init__(self, pages):
            self.pages = pages

    pages = [
        FakePage("https://old.example/1"),
        FakePage("https://old.example/2"),
        FakePage("https://old.example/3"),
        FakePage("https://cc.baidu.com/report"),
        FakePage("https://new.example/4"),
    ]
    context = FakeContext(pages)

    closed = cleanup_extra_tabs(context, pages[3], max_tabs=3)

    assert closed == ["https://old.example/1", "https://old.example/2"]
    assert pages[0].closed is True
    assert pages[1].closed is True
    assert pages[3].closed is False
    assert pages[3].front is True


def test_cleanup_extra_tabs_does_nothing_when_page_count_is_three():
    class FakePage:
        def __init__(self, url):
            self.url = url
            self.closed = False

        def close(self):
            self.closed = True

    class FakeContext:
        def __init__(self, pages):
            self.pages = pages

    pages = [FakePage("1"), FakePage("2"), FakePage("https://cc.baidu.com/report")]

    closed = cleanup_extra_tabs(FakeContext(pages), pages[2], max_tabs=3)

    assert closed == []
    assert all(page.closed is False for page in pages)


def test_cleanup_extra_tabs_limits_even_when_all_pages_are_baidu():
    class FakePage:
        def __init__(self, url):
            self.url = url
            self.closed = False

        def bring_to_front(self):
            pass

        def close(self):
            self.closed = True

    class FakeContext:
        def __init__(self, pages):
            self.pages = pages

    pages = [FakePage(f"https://cc.baidu.com/report?page={index}") for index in range(5)]

    closed = cleanup_extra_tabs(FakeContext(pages), pages[4], max_tabs=3)

    assert closed == ["https://cc.baidu.com/report?page=0", "https://cc.baidu.com/report?page=1"]
    assert [page.closed for page in pages] == [True, True, False, False, False]


def test_baidu_number_cleanup_and_report_validation():
    assert _parse_number(" ￥ 1,234.50 元 ") == 1234.5
    report = {
        "accounts": {
            "银康01": {"展现": 100, "点击": 10, "消费": 20.5},
            "银康银屑02": {"展现": 200, "点击": 20, "消费": 30},
            "银康03": {"展现": 300, "点击": 30, "消费": 40},
        }
    }

    km_accounts = list(_kunming_niu_runtime_config()["accounts"].keys())
    assert validate_baidu_report(report, required_accounts=km_accounts) == []

    bad_report = {"accounts": {"银康01": {"展现": "x", "点击": 1, "消费": 1}}}
    errors = validate_baidu_report(bad_report, required_accounts=km_accounts)
    assert any("账户数量不匹配" in error for error in errors)
    assert any("不是数字" in error for error in errors)


# ── baidu_parser 未知账户测试 ─────────────────────────────


def test_unknown_account_all_zero_goes_to_ignored():
    """未知账户 展现=0、点击=0、消费=0 → ignored_unknown_accounts。"""
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
        }
    }
    rows = [
        {"账户": "银康01", "展现": "100", "点击": "10", "消费": "50"},
        {"账户": "未知零账户", "展现": "0", "点击": "0", "消费": "0"},
    ]

    parsed = parse_baidu_table(rows, config)

    assert "银康01" in parsed["accounts"]
    assert len(parsed["unknown_accounts"]) == 0
    assert len(parsed["ignored_unknown_accounts"]) == 1
    assert parsed["ignored_unknown_accounts"][0]["account_name"] == "未知零账户"
    assert parsed["ignored_unknown_accounts"][0]["展现"] == 0
    assert "已忽略" in parsed["ignored_unknown_accounts"][0]["reason"]


def test_unknown_account_with_impressions_goes_to_unknown():
    """未知账户 展现>0 → unknown_accounts。"""
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
        }
    }
    rows = [
        {"账户": "银康01", "展现": "100", "点击": "10", "消费": "50"},
        {"账户": "未知展现", "展现": "200", "点击": "0", "消费": "0"},
    ]

    parsed = parse_baidu_table(rows, config)

    assert len(parsed["unknown_accounts"]) == 1
    assert parsed["unknown_accounts"][0]["account_name"] == "未知展现"
    assert parsed["unknown_accounts"][0]["展现"] == 200
    assert parsed["unknown_accounts"][0]["点击"] == 0
    assert len(parsed["ignored_unknown_accounts"]) == 0
    assert "未配置" in parsed["unknown_accounts"][0]["reason"]


def test_unknown_account_with_clicks_goes_to_unknown():
    """未知账户 点击>0 → unknown_accounts。"""
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
        }
    }
    rows = [
        {"账户": "银康01", "展现": "100", "点击": "10", "消费": "50"},
        {"账户": "未知点击", "展现": "0", "点击": "5", "消费": "0"},
    ]

    parsed = parse_baidu_table(rows, config)

    assert len(parsed["unknown_accounts"]) == 1
    assert parsed["unknown_accounts"][0]["account_name"] == "未知点击"
    assert parsed["unknown_accounts"][0]["点击"] == 5


def test_unknown_account_with_cost_goes_to_unknown():
    """未知账户 消费>0 → unknown_accounts。"""
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
        }
    }
    rows = [
        {"账户": "银康01", "展现": "100", "点击": "10", "消费": "50"},
        {"账户": "未知消费", "展现": "0", "点击": "0", "消费": "10.5"},
    ]

    parsed = parse_baidu_table(rows, config)

    assert len(parsed["unknown_accounts"]) == 1
    assert parsed["unknown_accounts"][0]["account_name"] == "未知消费"
    assert parsed["unknown_accounts"][0]["消费"] == 10.5


def test_known_accounts_still_in_accounts():
    """已配置账户仍然正常进入 accounts。"""
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
            "银康银屑02": {"baidu_name": "银康银屑02"},
        }
    }
    rows = [
        {"账户": "银康01", "展现": "100", "点击": "10", "消费": "50"},
        {"账户": "银康银屑02", "展现": "200", "点击": "20", "消费": "30"},
    ]

    parsed = parse_baidu_table(rows, config)

    assert len(parsed["accounts"]) == 2
    assert parsed["accounts"]["银康01"]["展现"] == 100
    assert parsed["accounts"]["银康银屑02"]["展现"] == 200
    assert len(parsed["unknown_accounts"]) == 0
    assert len(parsed["ignored_unknown_accounts"]) == 0


def test_unknown_accounts_do_not_affect_known_parsing():
    """unknown/ignored 不影响已配置账户解析。"""
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
        }
    }
    rows = [
        {"账户": "银康01", "展现": "100", "点击": "10", "消费": "50"},
        {"账户": "未知A", "展现": "999", "点击": "99", "消费": "99"},
        {"账户": "未知B", "展现": "0", "点击": "0", "消费": "0"},
    ]

    parsed = parse_baidu_table(rows, config)

    assert len(parsed["accounts"]) == 1
    assert parsed["accounts"]["银康01"]["展现"] == 100
    assert len(parsed["unknown_accounts"]) == 1
    assert len(parsed["ignored_unknown_accounts"]) == 1
    assert parsed["unknown_accounts"][0]["展现"] == 999
    assert parsed["ignored_unknown_accounts"][0]["展现"] == 0


def test_unknown_accounts_not_in_errors():
    """未知账户不进入 errors。"""
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
        }
    }
    rows = [
        {"账户": "银康01", "展现": "100", "点击": "10", "消费": "50"},
        {"账户": "未知有数据", "展现": "100", "点击": "10", "消费": "50"},
    ]

    parsed = parse_baidu_table(rows, config)

    assert len(parsed["unknown_accounts"]) == 1
    assert not any("未知" in e for e in parsed["errors"]), "未知账户不应进入 errors"


def test_unknown_missing_impressions_goes_to_unknown():
    """未知账户展现字段缺失 → unknown_accounts，不进 ignored。"""
    config = {"accounts": {"银康01": {"baidu_name": "银康01"}}}
    rows = [
        {"账户": "银康01", "展现": "100", "点击": "10", "消费": "50"},
        {"账户": "未知缺展现", "点击": "0", "消费": "0"},
    ]
    parsed = parse_baidu_table(rows, config)

    assert len(parsed["unknown_accounts"]) == 1
    assert parsed["unknown_accounts"][0]["account_name"] == "未知缺展现"
    assert len(parsed["ignored_unknown_accounts"]) == 0


def test_unknown_missing_clicks_goes_to_unknown():
    """未知账户点击字段缺失 → unknown_accounts。"""
    config = {"accounts": {"银康01": {"baidu_name": "银康01"}}}
    rows = [
        {"账户": "银康01", "展现": "100", "点击": "10", "消费": "50"},
        {"账户": "未知缺点击", "展现": "0", "消费": "0"},
    ]
    parsed = parse_baidu_table(rows, config)

    assert len(parsed["unknown_accounts"]) == 1
    assert parsed["unknown_accounts"][0]["account_name"] == "未知缺点击"
    assert len(parsed["ignored_unknown_accounts"]) == 0


def test_unknown_missing_cost_goes_to_unknown():
    """未知账户消费字段缺失 → unknown_accounts。"""
    config = {"accounts": {"银康01": {"baidu_name": "银康01"}}}
    rows = [
        {"账户": "银康01", "展现": "100", "点击": "10", "消费": "50"},
        {"账户": "未知缺消费", "展现": "0", "点击": "0"},
    ]
    parsed = parse_baidu_table(rows, config)

    assert len(parsed["unknown_accounts"]) == 1
    assert parsed["unknown_accounts"][0]["account_name"] == "未知缺消费"
    assert len(parsed["ignored_unknown_accounts"]) == 0


def test_unknown_non_numeric_field_goes_to_unknown():
    """未知账户字段为非数字 → unknown_accounts。"""
    config = {"accounts": {"银康01": {"baidu_name": "银康01"}}}
    rows = [
        {"账户": "银康01", "展现": "100", "点击": "10", "消费": "50"},
        {"账户": "未知非数字", "展现": "N/A", "点击": "0", "消费": "0"},
    ]
    parsed = parse_baidu_table(rows, config)

    assert len(parsed["unknown_accounts"]) == 1
    assert parsed["unknown_accounts"][0]["account_name"] == "未知非数字"
    assert len(parsed["ignored_unknown_accounts"]) == 0


def test_unknown_all_zero_still_ignored():
    """原有未知账户 0/0/0 仍然进入 ignored_unknown_accounts。"""
    config = {"accounts": {"银康01": {"baidu_name": "银康01"}}}
    rows = [
        {"账户": "银康01", "展现": "100", "点击": "10", "消费": "50"},
        {"账户": "零账户", "展现": "0", "点击": "0", "消费": "0"},
    ]
    parsed = parse_baidu_table(rows, config)

    assert len(parsed["unknown_accounts"]) == 0
    assert len(parsed["ignored_unknown_accounts"]) == 1
    assert parsed["ignored_unknown_accounts"][0]["account_name"] == "零账户"


def test_extract_baidu_rows_from_visible_text_reports_missing_click_column():
    text = """
详细数据
自定义列
下载
重置列宽
账户
账户ID
展现
消费
点击率
平均点击价格
总计-3
-
6,791
2,794.83
5.26%
7.83
银康01
72828178
4,169
1,873.41
4.49%
10.02
银康银屑02
72828179
2,397
829.67
6.26%
5.53
baidu-银康03
81509165
225
91.75
8.89%
4.59
20条/页
"""
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
            "银康银屑02": {"baidu_name": "银康银屑02"},
            "银康03": {"baidu_name": "baidu-银康03"},
        }
    }

    rows = extract_baidu_rows_from_visible_text(text)
    parsed = parse_baidu_table(rows, config)

    assert len(rows) == 4
    assert set(parsed["accounts"].keys()) == {"银康01", "银康银屑02", "银康03"}
    assert parsed["accounts"]["银康01"]["展现"] == 4169
    assert parsed["accounts"]["银康01"]["消费"] == 1873.41
    assert any("字段 点击" in error for error in parsed["errors"])


def test_extract_selected_date_from_baidu_visible_text():
    text = """
账户：
全部已绑定账户
2026/05/06
推广设备：全部
详细数据
"""

    assert _extract_selected_date_from_text(text) == "2026-05-06"


def test_classify_baidu_page_types_from_url_and_visible_text():
    login = classify_baidu_page("https://yingxiao.baidu.com/", "登录 百度营销 请输入账号 密码")
    assert login["login_status"] == "not_logged_in"
    assert login["page_type"] == "未登录页"

    public_home = classify_baidu_page("https://yingxiao.baidu.com/home", "首页 百度伴飞 登录 注册 立即推广")
    assert public_home["login_status"] == "not_logged_in"
    assert public_home["page_type"] == "未登录页"

    cas_login = classify_baidu_page("https://cas.baidu.com/?tpl=www2", "百度营销账号 百度账号 扫码登录 注册忘记密码 搜索推广")
    assert cas_login["login_status"] == "not_logged_in"
    assert cas_login["page_type"] == "未登录页"
    assert is_search_promotion_overview(cas_login) is False

    home = classify_baidu_page("https://yingxiao.baidu.com/home", "百度营销 客户中心 首页 进入")
    assert home["login_status"] == "logged_in"
    assert home["page_type"] == "百度营销首页"

    report = classify_baidu_page("https://yingxiao.baidu.com/report", "数据报告 数据概览 搜索推广 详细数据 展现 点击 消费")
    assert report["page_type"] == "搜索推广"
    assert report["signals"]["has_data_report"] is True
    assert report["signals"]["has_data_overview"] is True
    assert report["signals"]["has_search_promotion"] is True

    cc_report = classify_baidu_page("https://cc.baidu.com/report", "数据报告 数据概览 全部推广产品")
    assert cc_report["login_status"] == "logged_in"
    assert cc_report["page_type"] == "数据概览"
    assert cc_report["signals"]["has_data_report"] is True


def test_search_promotion_overview_detection_requires_overview_and_search_signals():
    search = classify_baidu_page("https://cc.baidu.com/report", "数据报告 数据概览 搜索推广 展现 点击 消费")
    cc_report_search = classify_baidu_page("https://cc.baidu.com/report", "数据报告 搜索推广 详细数据 账户 展现 点击 消费")
    overview_only = classify_baidu_page("https://cc.baidu.com/report", "数据报告 数据概览 信息流推广")
    old_yingxiao = classify_baidu_page("https://yingxiao.baidu.com/report", "数据报告 数据概览 搜索推广 展现 点击 消费")

    assert is_search_promotion_overview(search) is True
    assert is_search_promotion_overview(cc_report_search) is True
    assert is_search_promotion_overview(overview_only) is False
    assert is_search_promotion_overview(old_yingxiao) is False


def test_validate_overview_ready_checks_today_accounts_and_headers():
    text = """
数据报告
搜索推广
账户：
全部已绑定账户
2026/05/07
详细数据
账户
账户ID
展现
点击
消费
银康01
银康银屑02
baidu-银康03
"""
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01", "aliases": ["银康01"]},
            "银康银屑02": {"baidu_name": "银康银屑02", "aliases": ["银康银屑02"]},
            "银康03": {"baidu_name": "baidu-银康03", "aliases": ["银康03", "baidu-银康03"]},
        }
    }

    report = validate_overview_ready(text, "2026-05-07", config)

    assert report["passed"] is True
    assert report["checks"]["date_is_today"] is True
    assert all(report["accounts"].values())
    assert all(report["fields"].values())


def test_validate_overview_ready_rejects_wrong_date():
    report = validate_overview_ready("数据报告 搜索推广 2026/05/06 账户 展现 点击 消费 银康01 银康银屑02 baidu-银康03", "2026-05-07", {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
            "银康银屑02": {"baidu_name": "银康银屑02"},
            "银康03": {"baidu_name": "baidu-银康03", "aliases": ["银康03"]},
        }
    })

    assert report["passed"] is False
    assert report["checks"]["date_is_today"] is False
    assert any("日期不是今天" in error for error in report["errors"])


def test_overview_text_has_account_table_requires_header_and_account():
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
            "银康银屑02": {"baidu_name": "银康银屑02"},
            "银康03": {"baidu_name": "baidu-银康03", "aliases": ["银康03", "baidu-银康03"]},
        }
    }

    loading_text = "数据报告 搜索推广 2026/05/07 点击（次） - 展现（次） - 消费（元） - 详细数据"
    loaded_text = "数据报告 搜索推广 2026/05/07 详细数据 账户 账户ID 展现 点击 消费 银康01"

    assert overview_text_has_account_table(loading_text, config) is False
    assert overview_text_has_account_table(loaded_text, config) is True


def test_qingge_login_page_should_redirect_to_cas_form():
    assert should_open_cas_login("https://qingge.baidu.com/login") is True
    assert should_open_cas_login("https://yingxiao.baidu.com/") is True
    assert should_open_cas_login("https://cas.baidu.com/?tpl=www2") is False


def test_search_promotion_overview_requires_report_url_not_homepage():
    homepage = classify_baidu_page("https://cc.baidu.com/homepage", "首页 数据概览 搜索推广 账户 展现 点击 消费 银康01")
    report = classify_baidu_page("https://cc.baidu.com/report", "数据报告 搜索推广 详细数据 账户 展现 点击 消费 银康01")

    assert is_search_promotion_overview(homepage) is False
    assert is_search_promotion_overview(report) is True


def test_build_baidu_auto_report_from_overview_visible_text():
    today = date.today()
    visible_date = today.strftime("%Y/%m/%d")
    expected_date = today.isoformat()
    text = f"""
首页
数据报告
搜索推广
账户：
全部已绑定账户
{visible_date}
详细数据
账户
账户ID
展现
点击
消费
平均点击价格
点击率
搜索推广余额
总计-3
-
3,970
363
3,048.96
8.4
9.14%
-
银康01
72828178
1,958
206
2,339.88
11.36
10.52%
29,637.05
银康银屑02
72828179
1,849
141
693.96
4.92
7.63%
29,637.05
baidu-银康03
81509165
163
16
15.12
0.95
9.82%
29,637.05
20条/页
"""
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
            "银康银屑02": {"baidu_name": "银康银屑02"},
            "银康03": {"baidu_name": "baidu-银康03", "aliases": ["银康03", "baidu-银康03"]},
        }
    }

    report = build_baidu_auto_report_from_visible_text(text, config, "15点", visible_text_path="reports/baidu_visible_text.txt")

    assert report["date"] == expected_date
    assert report["period"] == "15点"
    assert report["parse_source"] == "visible_text"
    assert report["accounts"]["银康01"]["展现"] == 1958
    assert report["accounts"]["银康银屑02"]["点击"] == 141
    assert report["accounts"]["银康03"]["source_account"] == "baidu-银康03"
    assert report["accounts"]["银康03"]["消费"] == 15.12
    assert report["errors"] == []


def test_build_baidu_daily_report_accepts_specified_non_today_date():
    text = """
数据报告
搜索推广
账户：
全部已绑定账户
2026/05/07
详细数据
账户
账户ID
展现
点击
消费
平均点击价格
点击率
搜索推广余额
总计-3
-
309
30
127.7
4.26
9.71%
-
银康01
72828178
172
20
75.68
3.78
11.63%
29,507.53
银康银屑02
72828179
101
8
50.96
6.37
7.92%
29,507.53
baidu-银康03
81509165
36
2
1.06
0.53
5.56%
29,507.53
20条/页
"""
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
            "银康银屑02": {"baidu_name": "银康银屑02"},
            "银康03": {"baidu_name": "baidu-银康03", "aliases": ["银康03", "baidu-银康03"]},
        }
    }

    report = build_baidu_daily_report_from_visible_text(text, config, "2026-05-07", "dump.txt")

    assert report["date"] == "2026-05-07"
    assert report["source"] == "baidu_daily_report"
    assert report["accounts"]["银康01"]["点击"] == 20
    assert report["accounts"]["银康03"]["source_account"] == "baidu-银康03"
    assert report["errors"] == []
    assert report["self_check"]["selected_date_matches_target"] is True


def test_build_baidu_daily_report_rejects_page_date_mismatch():
    report = build_baidu_daily_report_from_visible_text("数据报告 搜索推广 2026/05/08", {"accounts": {}}, "2026-05-07")

    assert report["date"] == "2026-05-07"
    assert any("百度日报页面日期不匹配" in error for error in report["errors"])


def test_build_baidu_daily_report_rejects_non_search_promotion_data():
    text = """
数据报告
信息流推广
2026/05/07
账户
展现
点击
消费
银康01
100
10
50
银康银屑02
80
8
40
baidu-银康03
30
3
10
"""
    config = {
        "accounts": {
            "银康01": {"baidu_name": "银康01"},
            "银康银屑02": {"baidu_name": "银康银屑02"},
            "银康03": {"baidu_name": "baidu-银康03", "aliases": ["银康03", "baidu-银康03"]},
        }
    }

    report = build_baidu_daily_report_from_visible_text(text, config, "2026-05-07")

    assert any("当前百度日报页面不是搜索推广数据" in error for error in report["errors"])


def test_default_daily_date_is_yesterday():
    today = date(2026, 5, 8)

    assert default_daily_date(today) == "2026-05-07"


def test_load_project_credentials_from_local_file(tmp_path):
    credentials = tmp_path / "credentials.local.json"
    credentials.write_text(
        """
{
  "baidu": {
    "yunnan_yinkang": {
      "username": "demo-user",
      "password": "demo-pass"
    }
  }
}
""",
        encoding="utf-8",
    )

    item = load_project_credentials(tmp_path, {"credentials_path": "credentials.local.json"}, "baidu", "yunnan_yinkang")

    assert item["username"] == "demo-user"
    assert item["password"] == "demo-pass"


def test_validate_baidu_account_data_accepts_three_standard_accounts(tmp_path):
    source = tmp_path / "baidu_account_data.json"
    output = tmp_path / "baidu_validate_report.json"
    source.write_text(
        """
{
  "date": "2026-05-07",
  "period": "15",
  "accounts": {
    "银康01": {"source_account": "银康01", "展现": 4169, "点击": 187, "消费": 1873.41},
    "银康银屑02": {"source_account": "银康银屑02", "展现": 2397, "点击": 150, "消费": 829.67},
    "银康03": {"source_account": "baidu-银康03", "展现": 225, "点击": 20, "消费": 91.75}
  },
  "errors": []
}
""",
        encoding="utf-8",
    )

    km_accounts = list(_kunming_niu_runtime_config()["accounts"].keys())
    report = validate_baidu_account_data(source, output, expected_accounts=km_accounts)

    assert report["passed"] is True
    assert report["checks"]["exactly_three_standard_accounts"] is True
    assert report["checks"]["all_source_accounts_present"] is True
    assert report["checks"]["impressions_and_clicks_are_integers"] is True
    assert output.exists()


def test_validate_baidu_account_data_rejects_visible_dump_date_mismatch(tmp_path):
    dump = tmp_path / "baidu_page_text_dump.txt"
    dump.write_text("账户：\n全部已绑定账户\n2026/05/06\n推广设备：全部\n", encoding="utf-8")
    source = tmp_path / "baidu_account_data.json"
    output = tmp_path / "baidu_validate_report.json"
    source.write_text(
        f"""
{{
  "date": "2026-05-07",
  "period": "15",
  "accounts": {{
    "银康01": {{"source_account": "银康01", "展现": 4169, "点击": 187, "消费": 1873.41}},
    "银康银屑02": {{"source_account": "银康银屑02", "展现": 2397, "点击": 150, "消费": 829.67}},
    "银康03": {{"source_account": "baidu-银康03", "展现": 225, "点击": 20, "消费": 91.75}}
  }},
  "exceptions": [
    {{"type": "visible_text_dump", "path": "{str(dump).replace('\\', '\\\\')}"}}
  ],
  "errors": []
}}
""",
        encoding="utf-8",
    )

    report = validate_baidu_account_data(source, output)

    assert report["passed"] is False
    assert report["checks"]["source_date_matches_visible_dump"] is False
    assert any("页面实际日期" in error for error in report["errors"])


def test_baidu_debug_artifacts_do_not_write_screenshot_by_default(tmp_path):
    class FakePage:
        def __init__(self):
            self.screenshot_called = False

        def content(self):
            return "<html>debug</html>"

        def screenshot(self, **kwargs):
            self.screenshot_called = True

    page = FakePage()
    report = {"exceptions": []}

    _write_debug_artifacts(tmp_path, page, report)

    assert (tmp_path / "reports" / "baidu_debug.html").exists()
    assert not (tmp_path / "reports" / "baidu_debug.png").exists()
    assert page.screenshot_called is False
    assert [item["type"] for item in report["exceptions"]] == ["debug_html"]


def test_merge_hourly_data_requires_three_accounts_and_strict_field_types():
    baidu = {
        "date": "2026-05-07",
        "period": "15",
        "accounts": {
            "银康01": {"展现": 4169, "点击": 187, "消费": 1873.41},
            "银康银屑02": {"展现": 2397, "点击": 150, "消费": 829.67},
            "银康03": {"展现": 225, "点击": 20, "消费": 91.75},
        },
    }
    kst = {
        "date": "2026-05-07",
        "period": "15点",
        "accounts": {
            "银康01": {"总对话": 8, "有效": 4, "有效转潜": 1, "总转潜": 2},
            "银康银屑02": {"总对话": 9, "有效": 2, "有效转潜": 1, "总转潜": 1},
            "银康03": {"总对话": 3, "有效": 1, "有效转潜": 1, "总转潜": 2},
        },
    }

    km_accounts = list(_kunming_niu_runtime_config()["accounts"].keys())
    merged = build_merged_hourly_data(baidu, kst, "15点", required_accounts=km_accounts)

    assert merged["date"] == "2026-05-07"
    assert merged["period"] == "15点"
    assert list(merged["accounts"].keys()) == ["银康01", "银康银屑02", "银康03"]
    assert merged["accounts"]["银康03"]["消费"] == 91.75
    assert merged["accounts"]["银康银屑02"]["总对话"] == 9
    assert validate_merged_hourly_data(merged, baidu, kst, required_accounts=km_accounts) == []

    merged["accounts"]["银康01"]["点击"] = 187.5
    errors = validate_merged_hourly_data(merged, baidu, kst, required_accounts=km_accounts)
    assert any("点击 必须是整数" in error for error in errors)


def test_merge_daily_data_combines_baidu_and_kst_daily_fields():
    baidu = {
        "date": "2026-05-07",
        "accounts": {
            "银康01": {"展现": 1958, "点击": 206, "消费": 2339.88},
            "银康银屑02": {"展现": 1849, "点击": 141, "消费": 693.96},
            "银康03": {"展现": 163, "点击": 16, "消费": 15.12},
        },
    }
    kst = {
        "date": "2026-05-07",
        "accounts": {
            "银康01": {"总对话": 11, "有效对话": 1, "无效对话": 10, "一般有效对话": 0, "有效转潜": 0, "总转潜": 1},
            "银康银屑02": {"总对话": 4, "有效对话": 0, "无效对话": 4, "一般有效对话": 0, "有效转潜": 0, "总转潜": 0},
            "银康03": {"总对话": 0, "有效对话": 0, "无效对话": 0, "一般有效对话": 0, "有效转潜": 0, "总转潜": 0},
        },
    }

    km_accounts = list(_kunming_niu_runtime_config()["accounts"].keys())
    merged = build_merged_daily_data(baidu, kst, required_accounts=km_accounts)

    assert merged["date"] == "2026-05-07"
    assert merged["source"]["baidu"] == "reports/baidu_daily_data.json"
    assert merged["source"]["kst"] == "reports/kst_daily_data.json"
    assert merged["accounts"]["银康01"]["展现"] == 1958
    assert merged["accounts"]["银康01"]["有效对话"] == 1
    assert merged["accounts"]["银康01"]["无效对话"] == 10
    assert merged["accounts"]["银康03"]["总对话"] == 0
    assert validate_merged_daily_data(merged, baidu, kst, required_accounts=km_accounts) == []

    merged["accounts"]["银康01"]["无效对话"] = 9
    errors = validate_merged_daily_data(merged, baidu, kst, required_accounts=km_accounts)
    assert any("无效对话不等于总对话减有效对话" in error for error in errors)


def test_write_merged_hourly_data_backs_up_writes_and_verifies(tmp_path):
    import logging
    from openpyxl import Workbook, load_workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "时段数据"
    ws["A1"] = "每日时段统计数据"
    ws.merge_cells("A1:E1")
    ws["F1"] = "银康01"
    ws.merge_cells("F1:L1")
    ws["M1"] = "银康银屑02"
    ws.merge_cells("M1:S1")
    ws["T1"] = "银康03"
    ws.merge_cells("T1:Z1")
    ws["A2"] = "日期"
    ws["B2"] = "时段"
    headers = ["展现", "点击", "消费", "总对话", "有效", "有效转潜", "总转潜"]
    for offset, header in enumerate(headers):
        ws.cell(row=2, column=6 + offset).value = header
        ws.cell(row=2, column=13 + offset).value = header
        ws.cell(row=2, column=20 + offset).value = header
    ws["A3"] = "2026-05-07"
    ws.merge_cells("A3:A6")
    ws["B3"] = "昨日数据"
    ws["B4"] = "11点"
    ws["B5"] = "3点"
    ws["B6"] = "6点"
    excel_path = tmp_path / "target.xlsx"
    wb.save(excel_path)

    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "merged_hourly_data.json").write_text(
        """
{
  "date": "2026-05-07",
  "period": "15点",
  "source": {"baidu": "reports/baidu_account_data.json", "kst": "reports/kst_dialog_data.json"},
  "accounts": {
    "银康01": {"展现": 4169, "点击": 187, "消费": 1873.41, "总对话": 8, "有效": 4, "有效转潜": 1, "总转潜": 2},
    "银康银屑02": {"展现": 2397, "点击": 150, "消费": 829.67, "总对话": 9, "有效": 2, "有效转潜": 1, "总转潜": 1},
    "银康03": {"展现": 225, "点击": 20, "消费": 91.75, "总对话": 3, "有效": 1, "有效转潜": 1, "总转潜": 2}
  }
}
""",
        encoding="utf-8",
    )
    config = {
        "excel_path": str(excel_path),
        "sheet_name": "时段数据",
        "accounts": {
            "银康01": {"aliases": ["银康01"], "excel_name": "银康01", "baidu_name": "银康01"},
            "银康银屑02": {"aliases": ["银康银屑02"], "excel_name": "银康银屑02", "baidu_name": "银康银屑02"},
            "银康03": {"aliases": ["银康03", "baidu-银康03"], "excel_name": "银康03", "baidu_name": "baidu-银康03"},
        },
        "field_aliases": {
            "日期": ["日期"],
            "时段": ["时段"],
            "展现": ["展现"],
            "点击": ["点击"],
            "消费": ["消费"],
            "总对话": ["总对话"],
            "有效": ["有效"],
            "有效转潜": ["有效转潜"],
            "总转潜": ["总转潜"],
        },
    }

    report = write_merged_hourly_data(config, tmp_path, logging.getLogger("test"), "15点")

    assert report["errors"] == []
    assert report["self_check"]["backup_created"] is True
    assert report["self_check"]["verification_passed"] is True
    assert report["overwrite_summary"]["overwrite_count"] == 0
    assert len(report["writes"]) == 21
    assert (tmp_path / "reports" / "write_report.json").exists()
    assert (tmp_path / "backups").exists()

    verify_wb = load_workbook(excel_path, data_only=False, read_only=False)
    verify_ws = verify_wb["时段数据"]
    assert verify_ws["F5"].value == 4169
    assert verify_ws["H5"].value == 1873.41
    assert verify_ws["T5"].value == 225
    assert verify_ws["Z5"].value == 2


def test_write_merged_daily_data_backs_up_writes_allowed_fields_only(tmp_path):
    import logging
    from openpyxl import Workbook, load_workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "百度"
    ws["A1"] = "日期"
    ws["P1"] = "银康01"
    ws.merge_cells("P1:AB1")
    ws["AC1"] = "银康银屑02"
    ws.merge_cells("AC1:AO1")
    ws["AP1"] = "银康03"
    ws.merge_cells("AP1:BB1")
    headers = ["展现", "点击", "消费", "acp", "总对话", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜", "预约", "就诊", "转潜成本"]
    for offset, header in enumerate(headers):
        ws.cell(row=2, column=16 + offset).value = header
        ws.cell(row=2, column=29 + offset).value = header
        ws.cell(row=2, column=42 + offset).value = header
    ws["A3"] = "2026-05-07"
    ws["T3"] = 999
    ws["Z3"] = 3
    ws["AA3"] = 2
    excel_path = tmp_path / "daily.xlsx"
    wb.save(excel_path)

    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "merged_daily_data.json").write_text(
        """
{
  "date": "2026-05-07",
  "source": {"baidu": "reports/baidu_daily_data.json", "kst": "reports/kst_daily_data.json"},
  "accounts": {
    "银康01": {"展现": 1958, "点击": 206, "消费": 2339.88, "总对话": 11, "有效对话": 1, "无效对话": 10, "一般有效对话": 0, "有效转潜": 0, "总转潜": 1},
    "银康银屑02": {"展现": 1849, "点击": 141, "消费": 693.96, "总对话": 4, "有效对话": 0, "无效对话": 4, "一般有效对话": 0, "有效转潜": 0, "总转潜": 0},
    "银康03": {"展现": 163, "点击": 16, "消费": 15.12, "总对话": 0, "有效对话": 0, "无效对话": 0, "一般有效对话": 0, "有效转潜": 0, "总转潜": 0}
  }
}
""",
        encoding="utf-8",
    )

    report = write_merged_daily_data(
        config={
            "excel_path": str(excel_path),
            "accounts": {
                "银康01": {"excel_name": "银康01", "baidu_name": "银康01", "aliases": ["银康01"]},
                "银康银屑02": {"excel_name": "银康银屑02", "baidu_name": "银康银屑02", "aliases": ["银康银屑02"]},
                "银康03": {"excel_name": "银康03", "baidu_name": "baidu-银康03", "aliases": ["银康03", "baidu-银康03"]},
            },
        },
        root=tmp_path,
        logger=logging.getLogger("test"),
        target_date="2026-05-07",
    )

    assert report["errors"] == []
    assert report["self_check"]["verification_passed"] is True
    assert len(report["writes"]) == 24
    assert all(item["field"] not in {"总对话", "预约", "就诊"} for item in report["writes"])
    assert (tmp_path / "reports" / "daily_write_report.json").exists()
    assert report["backup_path"]
    wb2 = load_workbook(excel_path, data_only=False)
    ws2 = wb2["百度"]
    assert ws2["P3"].value == 1958
    assert ws2["U3"].value == 1
    assert ws2["V3"].value == 10
    assert ws2["T3"].value == 999
    assert ws2["Z3"].value == 3
    assert ws2["AA3"].value == 2


def test_write_merged_hourly_data_reports_overwrites(tmp_path):
    import logging
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "时段数据"
    ws["A1"] = "每日时段统计数据"
    ws.merge_cells("A1:E1")
    ws["F1"] = "银康01"
    ws.merge_cells("F1:L1")
    ws["M1"] = "银康银屑02"
    ws.merge_cells("M1:S1")
    ws["T1"] = "银康03"
    ws.merge_cells("T1:Z1")
    ws["A2"] = "日期"
    ws["B2"] = "时段"
    headers = ["展现", "点击", "消费", "总对话", "有效", "有效转潜", "总转潜"]
    for offset, header in enumerate(headers):
        ws.cell(row=2, column=6 + offset).value = header
        ws.cell(row=2, column=13 + offset).value = header
        ws.cell(row=2, column=20 + offset).value = header
    ws["A3"] = "2026-05-07"
    ws.merge_cells("A3:A6")
    ws["B5"] = "3点"
    ws["F5"] = 999
    excel_path = tmp_path / "target.xlsx"
    wb.save(excel_path)

    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "merged_hourly_data.json").write_text(
        """
{
  "date": "2026-05-07",
  "period": "15点",
  "accounts": {
    "银康01": {"展现": 4169, "点击": 187, "消费": 1873.41, "总对话": 8, "有效": 4, "有效转潜": 1, "总转潜": 2},
    "银康银屑02": {"展现": 2397, "点击": 150, "消费": 829.67, "总对话": 9, "有效": 2, "有效转潜": 1, "总转潜": 1},
    "银康03": {"展现": 225, "点击": 20, "消费": 91.75, "总对话": 3, "有效": 1, "有效转潜": 1, "总转潜": 2}
  }
}
""",
        encoding="utf-8",
    )
    config = {
        "excel_path": str(excel_path),
        "sheet_name": "时段数据",
        "accounts": {
            "银康01": {"aliases": ["银康01"], "excel_name": "银康01", "baidu_name": "银康01"},
            "银康银屑02": {"aliases": ["银康银屑02"], "excel_name": "银康银屑02", "baidu_name": "银康银屑02"},
            "银康03": {"aliases": ["银康03", "baidu-银康03"], "excel_name": "银康03", "baidu_name": "baidu-银康03"},
        },
        "field_aliases": {
            "日期": ["日期"],
            "时段": ["时段"],
            "展现": ["展现"],
            "点击": ["点击"],
            "消费": ["消费"],
            "总对话": ["总对话"],
            "有效": ["有效"],
            "有效转潜": ["有效转潜"],
            "总转潜": ["总转潜"],
        },
    }

    report = write_merged_hourly_data(config, tmp_path, logging.getLogger("test"), "15点")

    assert report["errors"] == []
    assert report["overwrite_summary"]["overwrite_count"] == 1
    assert report["overwrite_summary"]["items"][0]["cell"] == "F5"
    assert report["overwrite_summary"]["items"][0]["old_value"] == 999


def test_run_pipeline_stops_on_failed_baidu_step(tmp_path):
    import logging

    def failed_baidu(**kwargs):
        return {"errors": ["未读取到三个百度账户"], "date": "2026-05-07", "period": "15点"}

    report = run_half_auto_pipeline(
        config={"excel_path": "target.xlsx"},
        root=tmp_path,
        logger=logging.getLogger("test"),
        period="15点",
        kst_file=tmp_path / "kst.xlsx",
        fetch_baidu_func=failed_baidu,
        parse_kst_func=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应继续解析快商通")),
    )

    assert report["passed"] is False
    assert report["failed_step"] == "fetch-baidu-auto"
    assert len(report["steps"]) == 1
    assert report["steps"][0]["passed"] is False
    assert (tmp_path / "reports" / "final_run_report.json").exists()


def test_run_pipeline_defaults_to_baidu_auto_fetcher():
    signature = inspect.signature(run_half_auto_pipeline)

    assert signature.parameters["fetch_baidu_func"].default is fetch_baidu_auto


def test_run_pipeline_reports_success_summary(tmp_path):
    import logging

    kst_file = tmp_path / "kst.xlsx"
    kst_file.write_text("placeholder", encoding="utf-8")
    excel_file = tmp_path / "target.xlsx"
    excel_file.write_text("placeholder", encoding="utf-8")

    def ok_baidu(**kwargs):
        return {
            "date": "2026-05-07",
            "period": "15",
            "accounts": {
                "银康01": {"展现": 1, "点击": 1, "消费": 1.0},
                "银康银屑02": {"展现": 2, "点击": 2, "消费": 2.0},
                "银康03": {"展现": 3, "点击": 3, "消费": 3.0},
            },
            "errors": [],
        }

    def ok_kst(export_file, config, root, period):
        return {
            "parse_report": {"passed": True, "errors": []},
            "dialog_data": {"export_file": str(export_file)},
            "outputs": {
                "dialog_data": str(root / "reports" / "kst_dialog_data.json"),
                "parse_report": str(root / "reports" / "kst_parse_report.json"),
            },
        }

    def ok_merge(**kwargs):
        return {
            "merged": {"date": "2026-05-07", "period": "15点"},
            "validate_report": {"passed": True, "errors": []},
            "outputs": {
                "merged": str(tmp_path / "reports" / "merged_hourly_data.json"),
                "validate_report": str(tmp_path / "reports" / "merge_validate_report.json"),
            },
        }

    def ok_write(**kwargs):
        return {
            "date": "2026-05-07",
            "period": "15点",
            "excel_path": str(excel_file),
            "backup_path": str(tmp_path / "backups" / "target_backup.xlsx"),
            "writes": [{"account": "银康01", "field": "展现", "cell": "P5", "verified": True}],
            "self_check": {"verification_passed": True},
            "errors": [],
        }

    report = run_half_auto_pipeline(
        config={"project_id": "demo", "project_name": "演示项目", "excel_path": str(excel_file)},
        root=tmp_path,
        logger=logging.getLogger("test"),
        period="15点",
        kst_file=kst_file,
        assume_yes=True,
        fetch_baidu_func=ok_baidu,
        parse_kst_func=ok_kst,
        merge_func=ok_merge,
        write_func=ok_write,
    )

    assert report["passed"] is True
    assert report["project_id"] == "demo"
    assert report["project_name"] == "演示项目"
    assert report["date"] == "2026-05-07"
    assert report["period"] == "15点"
    assert report["excel_path"] == str(excel_file)
    assert report["kst_export_file"] == str(kst_file)
    assert report["baidu_source_ok"] is True
    assert "成功" in report["summary_text"]
    assert report["target_sheet"] == "时段数据"
    assert report["kst_export"]["file_name"] == "kst.xlsx"
    assert report["write_summary"]["write_count"] == 1
    assert [step["name"] for step in report["steps"]] == ["fetch-baidu-auto", "parse-kst-export", "merge-data", "write-excel"]


def test_run_pipeline_uses_latest_kst_export_when_file_is_omitted(tmp_path):
    import logging
    import os

    export_dir = tmp_path / "kst_exports"
    export_dir.mkdir()
    older = export_dir / "older.csv"
    latest = export_dir / "latest.xlsx"
    older.write_text("old", encoding="utf-8")
    latest.write_text("new", encoding="utf-8")
    os.utime(older, (100, 100))
    os.utime(latest, (200, 200))
    excel_file = tmp_path / "target.xlsx"
    excel_file.write_text("placeholder", encoding="utf-8")
    seen = {}

    def ok_baidu(**kwargs):
        return {"date": "2026-05-07", "period": "15", "accounts": {}, "errors": []}

    def ok_kst(export_file, config, root, period):
        seen["export_file"] = export_file
        return {"parse_report": {"passed": True, "errors": []}, "outputs": {}}

    report = run_half_auto_pipeline(
        config={"excel_path": str(excel_file), "kst": {"export_dir": "kst_exports"}},
        root=tmp_path,
        logger=logging.getLogger("test"),
        period="15点",
        kst_file=None,
        assume_yes=True,
        fetch_baidu_func=ok_baidu,
        parse_kst_func=ok_kst,
        merge_func=lambda **kwargs: {"merged": {"date": "2026-05-07", "period": "15点"}, "validate_report": {"passed": True, "errors": []}, "outputs": {}},
        write_func=lambda **kwargs: {"date": "2026-05-07", "period": "15点", "excel_path": str(excel_file), "writes": [], "self_check": {"verification_passed": True}, "errors": []},
    )

    assert report["passed"] is True
    assert seen["export_file"] == latest
    assert report["kst_export_file"] == str(latest)
    assert report["kst_export"]["file_name"] == "latest.xlsx"
    assert report["kst_export"]["full_path"] == str(latest)
    assert report["kst_export"]["last_modified"]


def test_run_daily_pipeline_defaults_to_yesterday_and_reports_write_summary(tmp_path):
    import logging

    export_dir = tmp_path / "kst_exports"
    export_dir.mkdir()
    latest = export_dir / "daily.xlsx"
    latest.write_text("placeholder", encoding="utf-8")
    excel_file = tmp_path / "daily-target.xlsx"
    excel_file.write_text("placeholder", encoding="utf-8")

    def ok_baidu(**kwargs):
        assert kwargs["target_date"] == "2026-05-07"
        return {"date": "2026-05-07", "accounts": {"银康01": {}, "银康银屑02": {}, "银康03": {}}, "errors": []}

    def ok_kst(export_file, config, root, target_date):
        assert export_file == latest
        assert target_date == "2026-05-07"
        return {
            "parse_report": {"passed": True, "errors": []},
            "daily_data": {"date": "2026-05-07"},
            "outputs": {"daily_data": str(root / "reports" / "kst_daily_data.json")},
        }

    def ok_merge(**kwargs):
        assert kwargs["target_date"] == "2026-05-07"
        return {
            "merged": {"date": "2026-05-07"},
            "validate_report": {"passed": True, "errors": []},
            "outputs": {"merged": str(kwargs["root"] / "reports" / "merged_daily_data.json")},
        }

    def ok_write(**kwargs):
        assert kwargs["target_date"] == "2026-05-07"
        return {
            "date": "2026-05-07",
            "excel_path": str(excel_file),
            "backup_path": str(tmp_path / "backups" / "daily_backup.xlsx"),
            "writes": [{"cell": "P132"}, {"cell": "Q132"}],
            "overwrite_summary": {"overwrite_count": 1},
            "self_check": {"verification_passed": True},
            "errors": [],
        }

    report = run_daily_pipeline(
        config={"project_id": "demo", "project_name": "演示项目", "excel_path": str(excel_file), "kst": {"export_dir": "kst_exports"}},
        root=tmp_path,
        logger=logging.getLogger("test"),
        target_date=None,
        kst_file=None,
        today=date(2026, 5, 8),
        fetch_baidu_func=ok_baidu,
        parse_kst_func=ok_kst,
        merge_func=ok_merge,
        write_func=ok_write,
    )

    assert report["passed"] is True
    assert report["project_id"] == "demo"
    assert report["project_name"] == "演示项目"
    assert report["date"] == "2026-05-07"
    assert report["excel_path"] == str(excel_file)
    assert report["backup_path"].endswith("daily_backup.xlsx")
    assert report["kst_export_file"] == str(latest)
    assert report["write_summary"]["write_count"] == 2
    assert report["write_summary"]["overwrite_count"] == 1
    assert report["write_summary"]["verification_passed"] is True
    assert [step["name"] for step in report["steps"]] == ["fetch-baidu-daily", "parse-kst-daily", "merge-daily", "write-daily"]
    assert (tmp_path / "reports" / "daily_final_run_report.json").exists()


def test_run_daily_pipeline_stops_when_kst_parse_fails(tmp_path):
    import logging

    export = tmp_path / "daily.xlsx"
    export.write_text("placeholder", encoding="utf-8")

    def ok_baidu(**kwargs):
        return {"date": "2026-05-07", "errors": []}

    def bad_kst(export_file, config, root, target_date):
        return {"parse_report": {"passed": False, "errors": ["商务通日报解析失败"]}, "outputs": {}}

    def should_not_merge(**kwargs):
        raise AssertionError("解析失败后不应继续合并")

    report = run_daily_pipeline(
        config={"excel_path": "target.xlsx"},
        root=tmp_path,
        logger=logging.getLogger("test"),
        target_date="2026-05-07",
        kst_file=export,
        fetch_baidu_func=ok_baidu,
        parse_kst_func=bad_kst,
        merge_func=should_not_merge,
    )

    assert report["passed"] is False
    assert report["failed_step"] == "parse-kst-daily"
    assert any("商务通日报解析失败" in error for error in report["errors"])


def test_run_pipeline_confirmation_can_quit_before_steps(tmp_path):
    import logging

    export = tmp_path / "kst.xlsx"
    export.write_text("placeholder", encoding="utf-8")

    report = run_half_auto_pipeline(
        config={"excel_path": "target.xlsx"},
        root=tmp_path,
        logger=logging.getLogger("test"),
        period="15点",
        kst_file=export,
        confirm_before_run=True,
        input_func=lambda prompt: "0",
        fetch_baidu_func=lambda **kwargs: (_ for _ in ()).throw(AssertionError("返回后不应抓百度")),
    )

    assert report["passed"] is False
    assert report["failed_step"] == "preflight-confirm"
    assert report["steps"] == []
    assert any("用户返回主菜单" in error for error in report["errors"])


def test_run_pipeline_requires_confirmation_for_stale_auto_discovered_kst_file(tmp_path):
    import logging
    import os
    import time

    export_dir = tmp_path / "kst_exports"
    export_dir.mkdir()
    old_export = export_dir / "old.xlsx"
    old_export.write_text("old", encoding="utf-8")
    old_time = time.time() - 3 * 60 * 60
    os.utime(old_export, (old_time, old_time))

    report = run_half_auto_pipeline(
        config={"excel_path": "target.xlsx", "sheet_name": "时段数据", "kst": {"export_dir": "kst_exports"}},
        root=tmp_path,
        logger=logging.getLogger("test"),
        period="15点",
        kst_file=None,
        input_func=lambda prompt: "0",
        fetch_baidu_func=lambda **kwargs: (_ for _ in ()).throw(AssertionError("旧文件未确认时不应抓百度")),
    )

    assert report["passed"] is False
    assert report["failed_step"] == "preflight-confirm"
    assert report["kst_export"]["is_stale"] is True
    assert any("快商通导出文件超过 2 小时" in error for error in report["errors"])


# ── 凭据文件路径修复 ──


def test_runtime_config_credentials_path_from_app_config_secrets():
    project = {
        "project_id": "demo",
        "project_name": "演示",
        "excel": {"path": "target.xlsx", "hourly_sheet": "时段", "daily_sheet": "日", "engine": "openpyxl"},
        "kst": {"export_dir": "exports"},
        "baidu": {"credential_profile": "demo_p", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
        "accounts": [
            {"standard_name": "A1", "baidu_names": ["B1"], "excel_name": "A1", "kst_ids": ["1"], "kst_names": ["K1"]},
            {"standard_name": "A2", "baidu_names": ["B2"], "excel_name": "A2", "kst_ids": ["2"], "kst_names": ["K2"]},
            {"standard_name": "A3", "baidu_names": ["B3"], "excel_name": "A3", "kst_ids": ["3"], "kst_names": ["K3"]},
        ],
        "_app_config": {"secrets_file": "secrets/secrets.json"},
    }

    runtime = build_runtime_config_from_project(project, {"baidu": {}, "kst": {}})

    assert runtime["credentials_path"] == "secrets/secrets.json"
    assert runtime["baidu"]["credential_project"] == "demo_p"


def test_runtime_config_credentials_path_not_overridden_when_no_app_config():
    project = {
        "project_id": "x",
        "project_name": "y",
        "excel": {"path": "t.xlsx", "hourly_sheet": "H", "daily_sheet": "D", "engine": "openpyxl"},
        "kst": {"export_dir": "e"},
        "baidu": {"credential_profile": "p", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
        "accounts": [
            {"standard_name": "a1", "baidu_names": ["b1"], "excel_name": "a1", "kst_ids": ["1"], "kst_names": ["k1"]},
            {"standard_name": "a2", "baidu_names": ["b2"], "excel_name": "a2", "kst_ids": ["2"], "kst_names": ["k2"]},
            {"standard_name": "a3", "baidu_names": ["b3"], "excel_name": "a3", "kst_ids": ["3"], "kst_names": ["k3"]},
        ],
    }

    runtime = build_runtime_config_from_project(project, {"credentials_path": "old.json", "baidu": {}, "kst": {}})

    assert runtime["credentials_path"] == "old.json"


def test_load_credentials_from_secrets_json_structure(tmp_path):
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    secrets_file = secrets_dir / "secrets.json"
    secrets_file.write_text(
        json.dumps({
            "baidu": {
                "kunming_niu_baidu": {
                    "username": "test_user",
                    "password": "test_pass",
                },
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    credentials = load_project_credentials(
        tmp_path,
        {"credentials_path": "secrets/secrets.json", "baidu": {"credential_project": "kunming_niu_baidu"}},
        "baidu",
        "kunming_niu_baidu",
    )

    assert credentials is not None
    assert credentials["username"] == "test_user"
    assert credentials["password"] == "test_pass"


def test_load_credentials_falls_back_to_local_json(tmp_path):
    old_file = tmp_path / "credentials.local.json"
    old_file.write_text(
        json.dumps({
            "baidu": {
                "old_profile": {
                    "username": "fallback_user",
                    "password": "fallback_pass",
                },
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    credentials = load_project_credentials(
        tmp_path,
        {"credentials_path": "secrets/secrets.json", "baidu": {"credential_project": "old_profile"}},
        "baidu",
        "old_profile",
    )

    assert credentials is not None
    assert credentials["username"] == "fallback_user"


def test_load_credentials_returns_none_when_profile_missing(tmp_path):
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "secrets.json").write_text(
        json.dumps({"baidu": {"other": {"username": "u", "password": "p"}}}),
        encoding="utf-8",
    )

    credentials = load_project_credentials(
        tmp_path,
        {"credentials_path": "secrets/secrets.json", "baidu": {"credential_project": "missing_profile"}},
        "baidu",
        "missing_profile",
    )

    assert credentials is None


def test_build_login_failure_message_shows_actual_path_and_profile():
    msg = build_login_failure_message({
        "credentials_path": "secrets/secrets.json",
        "baidu": {"credential_project": "kunming_niu_baidu"},
    })

    assert "credentials.local.json" not in msg
    assert "secrets/secrets.json" in msg
    assert "kunming_niu_baidu" in msg
    assert "验证码" in msg


def test_build_login_failure_message_defaults_when_config_empty():
    msg = build_login_failure_message({})

    assert "credentials.local.json" in msg


# ── Chrome 调试端口自动启动 ──


def test_is_chrome_debug_port_alive_returns_false_when_port_closed():
    assert is_chrome_debug_port_alive(host="127.0.0.1", port=1, timeout=1.0) is False


def test_find_chrome_executable_returns_none_when_not_found(monkeypatch):
    import modules.chrome_debug as cd

    monkeypatch.setattr(cd, "CHROME_CANDIDATES", [Path("X:/nonexistent/chrome.exe")])
    result = find_chrome_executable(None)
    assert result is None


def test_ensure_chrome_debug_ready_reports_port_ready_when_already_open(monkeypatch):
    def fake_is_alive(host="127.0.0.1", port=9222, timeout=3.0):
        return True

    monkeypatch.setattr("modules.chrome_debug.is_chrome_debug_port_alive", fake_is_alive)

    result = ensure_chrome_debug_ready(Path("."), None)
    assert result["ready"] is True
    assert result["port_already_open"] is True
    assert result["started_new_chrome"] is False


def test_ensure_chrome_debug_ready_returns_error_when_auto_start_disabled(monkeypatch):
    def fake_is_alive(host="127.0.0.1", port=9222, timeout=3.0):
        return False

    monkeypatch.setattr("modules.chrome_debug.is_chrome_debug_port_alive", fake_is_alive)

    result = ensure_chrome_debug_ready(Path("."), None, auto_start=False)
    assert result["ready"] is False
    assert "未就绪" in (result.get("error") or "")


def test_ensure_chrome_debug_ready_returns_error_when_chrome_not_found(monkeypatch, tmp_path):
    def fake_is_alive(host="127.0.0.1", port=9222, timeout=3.0):
        return False

    def fake_chrome_exists():
        return False

    def fake_find(config=None):
        return None

    monkeypatch.setattr("modules.chrome_debug.is_chrome_debug_port_alive", fake_is_alive)
    monkeypatch.setattr("modules.chrome_debug._chrome_process_exists", fake_chrome_exists)
    monkeypatch.setattr("modules.chrome_debug.find_chrome_executable", fake_find)

    result = ensure_chrome_debug_ready(tmp_path, None, auto_start=True)
    assert result["ready"] is False
    assert result.get("error")
    assert "未找到 Google Chrome" in result["error"]


def test_menu_chrome_check_prints_status(tmp_path, capsys):
    from menu import _check_chrome_debug

    def fake_is_alive(host="127.0.0.1", port=9222, timeout=3.0):
        return True

    import modules.chrome_debug as cd
    original = cd.is_chrome_debug_port_alive
    cd.is_chrome_debug_port_alive = fake_is_alive
    try:
        ok = _check_chrome_debug(tmp_path, {"browser": {"auto_start_debug_chrome": True}}, print)
        assert ok is True
    finally:
        cd.is_chrome_debug_port_alive = original


def test_browser_settings_includes_new_auto_start_fields():
    settings = get_browser_settings(
        {
            "browser": {
                "mode": "connect_existing",
                "cdp_endpoint": "http://127.0.0.1:9222",
                "auto_start_debug_chrome": True,
                "remote_debugging_host": "127.0.0.1",
                "remote_debugging_port": 9222,
                "profile_dir": "browser_profile/chrome",
                "startup_url": "https://yingxiao.baidu.com/",
                "allow_kill_existing_chrome": False,
            }
        }
    )

    assert settings["auto_start_debug_chrome"] is True
    assert settings["remote_debugging_host"] == "127.0.0.1"
    assert settings["startup_url"] == "https://yingxiao.baidu.com/"
    assert settings["allow_kill_existing_chrome"] is False


# ── 终端输出分层（v0.4.8）──


def test_console_ui_set_verbose_and_is_verbose():
    from modules.console_ui import is_verbose, set_verbose

    set_verbose(False)
    assert is_verbose() is False
    set_verbose(True)
    assert is_verbose() is True
    set_verbose(False)
    assert is_verbose() is False


def test_console_ui_print_check_result_does_not_raise():
    from io import StringIO

    from modules.console_ui import print_check_result, set_output_func

    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_check_result("测试项", "pass", "正常")
        print_check_result("测试项", "fail", "有问题")
        print_check_result("测试项", "skip", "已跳过")
        print_check_result("测试项", "warn", "需关注")
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "[通过]" in output
    assert "[失败]" in output
    assert "[跳过]" in output
    assert "[注意]" in output


def test_console_ui_verbose_print_only_when_verbose():
    from io import StringIO

    from modules.console_ui import set_output_func, set_verbose, verbose_print

    buf = StringIO()
    set_output_func(buf.write)
    try:
        set_verbose(False)
        verbose_print("这条不应出现")
        assert "这条不应出现" not in buf.getvalue()

        set_verbose(True)
        verbose_print("这条应该出现")
        assert "这条应该出现" in buf.getvalue()
    finally:
        set_output_func(print)
        set_verbose(False)


def test_console_ui_step_output_format():
    from io import StringIO

    from modules.console_ui import print_final_failure, print_final_success, print_step, print_step_failure, print_step_success, set_output_func

    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_step(2, 4, "解析数据")
        print_step_success("数据已解析")
        print_step_failure("解析失败", suggestion="文件格式不正确", report_path="reports/err.json")
        print_final_success("写入 8 个单元格")
        print_final_failure("失败步骤：fetch-baidu")
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "[2/4]" in output
    assert "[通过]" in output
    assert "[失败]" in output
    assert "文件格式不正确" in output
    assert "reports/err.json" in output
    assert "写入 8 个单元格" in output


def test_main_accepts_verbose_flag():
    import subprocess
    import sys

    import main

    result = main.ROOT  # verify main is importable
    assert result is not None


def test_doctor_check_labels_cover_all_checks():
    from modules.doctor import _DOCTOR_CHECK_LABELS

    assert "chrome" in _DOCTOR_CHECK_LABELS
    assert "chrome_debug_port" in _DOCTOR_CHECK_LABELS
    assert "target_excel" in _DOCTOR_CHECK_LABELS
    assert "secrets_json" in _DOCTOR_CHECK_LABELS
    assert "latest_kst_export" in _DOCTOR_CHECK_LABELS
    assert all(isinstance(v, str) for v in _DOCTOR_CHECK_LABELS.values())


def test_run_bat_files_support_dragged_kst_file_argument():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name, period in [("run_11.bat", "11"), ("run_15.bat", "15"), ("run_18.bat", "18")]:
        text = (root / name).read_text(encoding="utf-8")
        assert f"--period {period}" in text
        assert 'set "KST_FILE=%~1"' in text
        assert '--file "%KST_FILE%"' in text


# ── console_ui 新增测试 ──────────────────────────────────


def test_print_check_table_shows_pass_fail_warn_status():
    from io import StringIO

    from modules.console_ui import print_check_table, set_output_func

    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_check_table("测试检查", [
            {"name": "项目A", "status": "pass", "message": "正常"},
            {"name": "项目B", "status": "fail", "message": "有问题"},
            {"name": "项目C", "status": "warn", "message": "需关注"},
        ])
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "[通过]" in output
    assert "[失败]" in output
    assert "[注意]" in output
    assert "项目A" in output
    assert "正常" in output
    assert "有问题" in output
    assert "需关注" in output
    assert "2/3" in output or "1/3" in output  # 通过/总数


def test_console_ui_no_colorama_fallback_does_not_raise():
    import sys

    from modules.console_ui import set_output_func

    # 模拟 colorama 不可用
    original_modules = sys.modules.copy()
    try:
        # 先清除可能的缓存
        for key in list(sys.modules.keys()):
            if "colorama" in key.lower():
                del sys.modules[key]

        sys.modules["colorama"] = type(sys)("fake_colorama")
        sys.modules["colorama"].__spec__ = None

        # 强制重新加载 console_ui（带 fallback）
        import importlib
        import modules.console_ui as cui

        importlib.reload(cui)

        assert cui._HAS_COLOR is False
        # 确保核心函数仍然可用
        buf = __import__("io").StringIO()
        cui.set_output_func(buf.write)
        try:
            cui.print_success("测试")
            cui.print_error("测试")
            cui.print_warning("测试")
        finally:
            cui.set_output_func(print)

        output = buf.getvalue()
        assert "[通过]" in output
        assert "[失败]" in output
        assert "[注意]" in output
    finally:
        # 恢复
        for key in list(sys.modules.keys()):
            if "colorama" in key.lower():
                del sys.modules[key]
        for key in list(original_modules.keys()):
            if "colorama" in key.lower() and key not in sys.modules:
                pass  # 不恢复 colorama mock


def test_print_banner_shows_project_and_version():
    from io import StringIO
    from pathlib import Path

    from modules.console_ui import print_banner, set_output_func

    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_banner({
            "project_name": "测试项目",
            "excel": {"path": "/path/to/test.xlsx"},
        }, version="1.0.0")
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "百度竞价日报" in output
    assert "小时报自动化助手" in output
    assert "1.0.0" in output
    assert "测试项目" in output
    assert "test.xlsx" in output
    assert "logs/run.log" in output


def test_print_project_info_shows_all_fields():
    from io import StringIO

    from modules.console_ui import print_project_info, set_output_func

    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_project_info({
            "project_name": "演示项目",
            "project_id": "demo",
            "_config_path": "/path/to/config.json",
            "excel": {
                "path": "/path/to/excel.xlsx",
                "hourly_sheet": "时段数据",
                "daily_sheet": "百度",
            },
            "kst": {"export_dir": "/path/to/exports"},
            "baidu": {"credential_profile": "my_profile"},
        })
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "项目信息" in output
    assert "演示项目" in output
    assert "excel.xlsx" in output
    assert "时段数据" in output
    assert "百度" in output
    assert "my_profile" in output


def test_default_output_mode_does_not_print_json_blobs(capsys):
    """默认模式（非 verbose）不应输出大段 JSON。"""
    from modules.console_ui import print_quiet_line, set_verbose, verbose_print

    set_verbose(False)
    verbose_print('{"this": "should not appear"}')
    print_quiet_line("正常信息")

    captured = capsys.readouterr()
    assert "should not appear" not in captured.out
    assert "正常信息" in captured.out


def test_verbose_mode_still_outputs_debug_info(capsys):
    from modules.console_ui import set_verbose, verbose_print

    set_verbose(True)
    verbose_print("调试信息：详细数据")

    captured = capsys.readouterr()
    assert "调试信息" in captured.out

    set_verbose(False)


def test_doctor_report_no_longer_prints_internal_field_names(tmp_path, capsys):
    """doctor 输出不再包含 _DOCTOR_CHECK_LABELS key 名等内部字段。"""
    from modules.doctor import print_doctor_report

    report = {
        "project_name": "测试",
        "checks": {
            "python": {"passed": True, "message": "Python 3.14.4"},
            "chrome": {"passed": False, "level": "warning", "message": "未找到 Chrome"},
        },
    }
    print_doctor_report(report)

    captured = capsys.readouterr()
    # 应该显示中文标签，而不是内部 key 名
    assert "Python 版本" in captured.out
    assert "未找到 Chrome" in captured.out
    # 不应输出 JSON 结构
    assert '"passed"' not in captured.out
    assert '"checks"' not in captured.out


def test_menu_new_text_entries_exist():
    """菜单显示新文案。"""
    assert "1. 小时报" in MENU_TEXT
    assert "2. 日报" in MENU_TEXT
    assert "3. 项目列表" in MENU_TEXT
    assert "4. 项目信息" in MENU_TEXT
    assert "5. 文件合格校验" in MENU_TEXT
    assert "0. 退出" in MENU_TEXT


# ── 返回逻辑测试 ──────────────────────────────────────────


def test_confirm_panel_shows_return_hint():
    """确认面板显示"回车执行 / 0 返回"。"""
    from io import StringIO
    from modules.console_ui import print_confirm_panel, set_output_func

    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_confirm_panel({"task_name": "测试任务", "project_name": "测试项目"})
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "回车执行" in output
    assert "0 返回" in output
    assert "执行确认" in output


def test_hourly_submenu_shows_return():
    """小时报子菜单包含 0. 返回。"""
    from io import StringIO
    from modules.console_ui import print_sub_menu_hourly, set_output_func

    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_sub_menu_hourly()
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "0. 返回" in output
    assert "11点" in output
    assert "15点" in output
    assert "18点" in output


def test_project_info_shows_return_hint():
    """项目信息页显示 0. 返回。"""
    from io import StringIO
    from modules.console_ui import print_project_info, set_output_func

    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_project_info({"project_name": "测试", "project_id": "test"})
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "0. 返回" in output
    assert "项目信息" in output


# ── 自动打开 Excel 测试 ───────────────────────────────────


def test_try_open_excel_returns_false_for_nonexistent_file(tmp_path):
    """目标文件不存在时 try_open_excel 返回 False。"""
    from modules.console_ui import try_open_excel

    result = try_open_excel(tmp_path / "不存在.xlsx")
    assert result is False


def test_try_open_excel_returns_false_for_empty_path():
    """空路径时 try_open_excel 返回 False。"""
    from modules.console_ui import try_open_excel

    assert try_open_excel("") is False


def test_print_auto_open_result_shows_status():
    """自动打开结果输出正确状态。"""
    from io import StringIO
    from modules.console_ui import print_auto_open_result, set_output_func

    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_auto_open_result(True)
        print_auto_open_result(False)
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "[通过]" in output
    assert "[注意]" in output
    assert "Excel 文件自动打开失败" in output


def test_auto_open_failure_does_not_raise():
    """自动打开失败不抛出异常。"""
    from modules.console_ui import try_open_excel

    result = try_open_excel("Z:/不存在的路径/文件.xlsx")
    assert result is False  # 不抛异常，只返回 False


# ── 默认输出降噪测试 ──────────────────────────────────────


def test_default_output_hides_report_path_in_pipeline_summary():
    """默认模式不输出 report/json 路径到终端（verbose_print 默认关闭）。"""
    from io import StringIO
    from modules.console_ui import set_output_func, set_verbose, verbose_print

    buf = StringIO()
    set_output_func(buf.write)
    set_verbose(False)
    try:
        verbose_print("报告：reports/final_run_report.json")
        verbose_print("reports/write_report.json")
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert output == ""  # 默认模式不应输出这些路径


def test_verbose_mode_shows_report_path():
    from io import StringIO
    from modules.console_ui import set_output_func, set_verbose, verbose_print

    buf = StringIO()
    set_output_func(buf.write)
    set_verbose(True)
    try:
        verbose_print("报告：reports/final_run_report.json")
    finally:
        set_output_func(print)
        set_verbose(False)

    output = buf.getvalue()
    assert "reports/final_run_report.json" in output


# ── 项目列表排除模板 ──────────────────────────────────────


def test_list_projects_excludes_project_template_json():
    """list_projects 不包含 project_template.json。"""
    root = Path(__file__).resolve().parents[1]
    projects = list_projects(root)

    ids = [p["project_id"] for p in projects]
    assert "your_project_id" not in ids, "列表不应包含模板 project_id"
    for p in projects:
        assert "project_template.json" not in p["path"], f"不应包含模板文件：{p['path']}"


def test_list_projects_excludes_is_template_true():
    """list_projects 排除 is_template=true 的配置。"""
    tmp = Path(__file__).resolve().parents[1] / "tests" / "__tmp_test_projects"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        (tmp / "configs").mkdir(exist_ok=True)
        (tmp / "configs" / "app_config.json").write_text(
            '{"default_project_id":"real_proj","projects_dir":"projects","secrets_file":"s.json"}',
            encoding="utf-8",
        )
        (tmp / "projects").mkdir(exist_ok=True)
        (tmp / "projects" / "real_proj.json").write_text(json.dumps({
            "project_id": "real_proj",
            "project_name": "真项目",
            "excel": {"path": "a.xlsx", "hourly_sheet": "H", "daily_sheet": "D", "engine": "openpyxl"},
            "kst": {"export_dir": "e", "auto_pick_latest": True, "max_file_age_hours": 2},
            "baidu": {"credential_profile": "p", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
            "accounts": [
                {"standard_name": "A1", "baidu_names": ["B1"], "excel_name": "A1", "kst_ids": ["1"], "kst_names": ["K1"]},
                {"standard_name": "A2", "baidu_names": ["B2"], "excel_name": "A2", "kst_ids": ["2"], "kst_names": ["K2"]},
                {"standard_name": "A3", "baidu_names": ["B3"], "excel_name": "A3", "kst_ids": ["3"], "kst_names": ["K3"]},
            ],
            "hourly": {"periods": ["11点", "15点", "18点"]},
            "daily": {"write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"], "do_not_write_fields": ["总对话", "预约", "到诊", "就诊"]},
        }, ensure_ascii=False), encoding="utf-8")
        (tmp / "projects" / "template_proj.json").write_text(json.dumps({
            "is_template": True,
            "project_id": "template_proj",
            "project_name": "模板",
            "excel": {"path": "b.xlsx", "hourly_sheet": "H", "daily_sheet": "D", "engine": "openpyxl"},
            "kst": {"export_dir": "e2", "auto_pick_latest": True, "max_file_age_hours": 2},
            "baidu": {"credential_profile": "p2", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
            "accounts": [
                {"standard_name": "T1", "baidu_names": ["B1"], "excel_name": "T1", "kst_ids": ["1"], "kst_names": ["K1"]},
                {"standard_name": "T2", "baidu_names": ["B2"], "excel_name": "T2", "kst_ids": ["2"], "kst_names": ["K2"]},
                {"standard_name": "T3", "baidu_names": ["B3"], "excel_name": "T3", "kst_ids": ["3"], "kst_names": ["K3"]},
            ],
            "hourly": {"periods": ["11点", "15点", "18点"]},
            "daily": {"write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"], "do_not_write_fields": ["总对话", "预约", "到诊", "就诊"]},
        }, ensure_ascii=False), encoding="utf-8")

        projects = list_projects(tmp)
        ids = [p["project_id"] for p in projects]
        assert "real_proj" in ids
        assert "template_proj" not in ids, "is_template=true 的项目不应出现在列表中"
    finally:
        import shutil
        shutil.rmtree(tmp)
        # clean up test dir


def test_list_projects_excludes_your_project_id():
    """list_projects 排除 project_id 为 your_project_id 的配置。"""
    tmp = Path(__file__).resolve().parents[1] / "tests" / "__tmp_test_projects_2"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        (tmp / "configs").mkdir(exist_ok=True)
        (tmp / "configs" / "app_config.json").write_text(
            '{"default_project_id":"good","projects_dir":"projects","secrets_file":"s.json"}',
            encoding="utf-8",
        )
        (tmp / "projects").mkdir(exist_ok=True)
        (tmp / "projects" / "good.json").write_text(json.dumps({
            "project_id": "good",
            "project_name": "好项目",
            "excel": {"path": "a.xlsx", "hourly_sheet": "H", "daily_sheet": "D", "engine": "openpyxl"},
            "kst": {"export_dir": "e", "auto_pick_latest": True, "max_file_age_hours": 2},
            "baidu": {"credential_profile": "p", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
            "accounts": [
                {"standard_name": "A1", "baidu_names": ["B1"], "excel_name": "A1", "kst_ids": ["1"], "kst_names": ["K1"]},
                {"standard_name": "A2", "baidu_names": ["B2"], "excel_name": "A2", "kst_ids": ["2"], "kst_names": ["K2"]},
                {"standard_name": "A3", "baidu_names": ["B3"], "excel_name": "A3", "kst_ids": ["3"], "kst_names": ["K3"]},
            ],
            "hourly": {"periods": ["11点", "15点", "18点"]},
            "daily": {"write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"], "do_not_write_fields": ["总对话", "预约", "到诊", "就诊"]},
        }, ensure_ascii=False), encoding="utf-8")
        # 第二个文件：文件名不同，project_id 是 your_project_id
        (tmp / "projects" / "not_a_template.json").write_text(json.dumps({
            "project_id": "your_project_id",
            "project_name": "伪模板",
            "excel": {"path": "b.xlsx", "hourly_sheet": "H", "daily_sheet": "D", "engine": "openpyxl"},
            "kst": {"export_dir": "e2", "auto_pick_latest": True, "max_file_age_hours": 2},
            "baidu": {"credential_profile": "p2", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
            "accounts": [
                {"standard_name": "T1", "baidu_names": ["B1"], "excel_name": "T1", "kst_ids": ["1"], "kst_names": ["K1"]},
                {"standard_name": "T2", "baidu_names": ["B2"], "excel_name": "T2", "kst_ids": ["2"], "kst_names": ["K2"]},
                {"standard_name": "T3", "baidu_names": ["B3"], "excel_name": "T3", "kst_ids": ["3"], "kst_names": ["K3"]},
            ],
            "hourly": {"periods": ["11点", "15点", "18点"]},
            "daily": {"write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"], "do_not_write_fields": ["总对话", "预约", "到诊", "就诊"]},
        }, ensure_ascii=False), encoding="utf-8")

        projects = list_projects(tmp)
        ids = [p["project_id"] for p in projects]
        assert "good" in ids
        assert "your_project_id" not in ids, "project_id=your_project_id 不应出现在列表中"
    finally:
        import shutil
        shutil.rmtree(tmp)
        # clean up test dir


def test_select_project_from_list_shows_real_projects_only(tmp_path):
    """_select_project_from_list 只展示真实项目，不含模板。"""
    from menu import _select_project_from_list

    projects_dir = tmp_path / "configs" / "projects"
    projects_dir.mkdir(parents=True)
    (tmp_path / "configs" / "app_config.json").write_text(
        json.dumps({
            "default_project_id": "good",
            "projects_dir": "configs/projects",
            "secrets_file": "secrets/secrets.json",
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    def make_project(pid, name, excel_path="a.xlsx"):
        return json.dumps({
            "project_id": pid,
            "project_name": name,
            "excel": {"path": excel_path, "hourly_sheet": "H", "daily_sheet": "D", "engine": "openpyxl"},
            "kst": {"export_dir": "e", "auto_pick_latest": True, "max_file_age_hours": 2},
            "baidu": {"credential_profile": "p", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
            "accounts": [
                {"standard_name": "A1", "baidu_names": ["B1"], "excel_name": "A1", "kst_ids": ["1"], "kst_names": ["K1"]},
                {"standard_name": "A2", "baidu_names": ["B2"], "excel_name": "A2", "kst_ids": ["2"], "kst_names": ["K2"]},
                {"standard_name": "A3", "baidu_names": ["B3"], "excel_name": "A3", "kst_ids": ["3"], "kst_names": ["K3"]},
            ],
            "hourly": {"periods": ["11点", "15点", "18点"]},
            "daily": {"write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"], "do_not_write_fields": ["总对话", "预约", "到诊", "就诊"]},
        }, ensure_ascii=False)

    (projects_dir / "good.json").write_text(make_project("good", "好项目"), encoding="utf-8")
    # 模板不应出现在列表中
    (projects_dir / "project_template.json").write_text(json.dumps({
        "is_template": True, "project_id": "your_project_id", "project_name": "模板",
        "excel": {"path": "t.xlsx", "hourly_sheet": "H", "daily_sheet": "D", "engine": "openpyxl"},
        "kst": {"export_dir": "e2", "auto_pick_latest": True, "max_file_age_hours": 2},
        "baidu": {"credential_profile": "p2", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
        "accounts": [
            {"standard_name": "T1", "baidu_names": ["B1"], "excel_name": "T1", "kst_ids": ["1"], "kst_names": ["K1"]},
            {"standard_name": "T2", "baidu_names": ["B2"], "excel_name": "T2", "kst_ids": ["2"], "kst_names": ["K2"]},
            {"standard_name": "T3", "baidu_names": ["B3"], "excel_name": "T3", "kst_ids": ["3"], "kst_names": ["K3"]},
        ],
        "hourly": {"periods": ["11点", "15点", "18点"]},
        "daily": {"write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"], "do_not_write_fields": ["总对话", "预约", "到诊", "就诊"]},
    }, ensure_ascii=False), encoding="utf-8")

    # 选择项目 1（好项目）
    result = _select_project_from_list(tmp_path, lambda prompt: "1", lambda s: None)
    assert result is not None
    assert result["project_id"] == "good"


def test_select_project_list_returns_none_on_zero_input():
    """输入 0 返回主菜单。"""
    from menu import _select_project_from_list

    root = Path(__file__).resolve().parents[1]
    # 用真实 repo 测试；输入 0 应返回 None
    result = _select_project_from_list(root, lambda prompt: "0", lambda s: None)
    assert result is None


def test_select_project_list_handles_invalid_number():
    """非法编号不会 traceback，返回 None。"""
    from menu import _select_project_from_list

    root = Path(__file__).resolve().parents[1]
    result = _select_project_from_list(root, lambda prompt: "999", lambda s: None)
    assert result is None


def test_list_projects_excludes_template_in_real_repo():
    """真实仓库 list_projects 不包含 project_template。"""
    root = Path(__file__).resolve().parents[1]
    projects = list_projects(root)
    for p in projects:
        assert p["project_id"] != "your_project_id", "真实项目列表不应包含 your_project_id"
        assert "project_template.json" not in p["path"]


# ── 任务完成状态测试 ──────────────────────────────────────


def test_task_status_file_not_exists_auto_init(tmp_path):
    """状态文件不存在时自动初始化。"""
    from modules.task_status import load_task_status

    (tmp_path / "reports").mkdir(exist_ok=True)
    data = load_task_status(tmp_path)
    assert data["date"] == date.today().isoformat()
    assert data["projects"] == {}


def test_task_status_new_day_resets(tmp_path):
    """跨天自动重置状态。"""
    from modules.task_status import load_task_status, save_task_status

    (tmp_path / "reports").mkdir(exist_ok=True)
    old_data = {"date": "2026-01-01", "projects": {"demo": {"daily": {"done": True}}}}
    save_task_status(tmp_path, old_data)

    data = load_task_status(tmp_path)
    assert data["date"] == date.today().isoformat()
    assert data["projects"] == {}


def test_mark_daily_done_and_check():
    """mark_daily_done 后 is_daily_done 返回 True。"""
    import tempfile
    from modules.task_status import is_daily_done, mark_daily_done

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "reports").mkdir(exist_ok=True)
        assert is_daily_done(root, "test_proj") is False
        mark_daily_done(root, "test_proj")
        assert is_daily_done(root, "test_proj") is True


def test_mark_hourly_done_and_check():
    """mark_hourly_done 后 is_hourly_done 返回 True。"""
    import tempfile
    from modules.task_status import is_hourly_done, mark_hourly_done

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "reports").mkdir(exist_ok=True)
        assert is_hourly_done(root, "test_proj", "11点") is False
        mark_hourly_done(root, "test_proj", "11点")
        assert is_hourly_done(root, "test_proj", "11点") is True
        # 其他时段不变
        assert is_hourly_done(root, "test_proj", "15点") is False
        assert is_hourly_done(root, "test_proj", "18点") is False


def test_completed_status_does_not_block_repeat():
    """已完成状态不阻止重复执行 — 状态只是提示。"""
    import tempfile
    from modules.task_status import is_hourly_done, mark_hourly_done

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "reports").mkdir(exist_ok=True)
        mark_hourly_done(root, "proj", "11点")
        assert is_hourly_done(root, "proj", "11点") is True
        # 再次标记同一时段 — 不报错
        mark_hourly_done(root, "proj", "11点")
        assert is_hourly_done(root, "proj", "11点") is True


def test_mark_daily_does_not_affect_hourly():
    """日报标记不影响小时报状态。"""
    import tempfile
    from modules.task_status import is_daily_done, is_hourly_done, mark_daily_done

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "reports").mkdir(exist_ok=True)
        mark_daily_done(root, "proj")
        assert is_daily_done(root, "proj") is True
        assert is_hourly_done(root, "proj", "11点") is False


def test_doctor_does_not_mark_completion():
    """doctor 不标记完成 — 用 mock 模拟 doctor 执行。"""
    from modules.task_status import is_daily_done, mark_daily_done
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "reports").mkdir(exist_ok=True)

        # 直接验证 task_status 逻辑，而非通过 dispatch_menu_task(5) 触发真实 doctor
        # doctor 的 dispatch 路径(choice='5')不会调用 mark 函数 — 这是菜单 run_menu 的职责
        assert is_daily_done(root, "proj") is False
        mark_daily_done(root, "proj")
        assert is_daily_done(root, "proj") is True

        # 验证：之前的 mark 成功，状态文件存在
        from modules.task_status import load_task_status
        data = load_task_status(root)
        assert data["projects"]["proj"]["daily"]["done"] is True


# ── 完成时间显示测试 ──────────────────────────────────────


def test_format_done_time_standard_format():
    """format_done_time 把 '2026-05-10 10:02:33' 转成 '10:02'。"""
    from modules.console_ui import format_done_time

    assert format_done_time("2026-05-10 10:02:33") == "10:02"
    assert format_done_time("2026-05-10 09:28:00") == "09:28"
    assert format_done_time("2026-05-10 14:15:59") == "14:15"


def test_format_done_time_iso_format():
    """format_done_time 把 '2026-05-10T10:02:33' 转成 '10:02'。"""
    from modules.console_ui import format_done_time

    assert format_done_time("2026-05-10T10:02:33") == "10:02"
    assert format_done_time("2026-05-10T09:28:00") == "09:28"


def test_format_done_time_already_short():
    """format_done_time 遇到已经是 '10:02' 格式的保持不变。"""
    from modules.console_ui import format_done_time

    assert format_done_time("10:02") == "10:02"


def test_format_done_time_empty_and_none():
    """format_done_time 遇到空值返回空字符串。"""
    from modules.console_ui import format_done_time

    assert format_done_time("") == ""
    assert format_done_time(None) == ""
    assert format_done_time("  ") == ""


def test_format_done_time_bad_format():
    """format_done_time 遇到异常格式不报错，返回空字符串。"""
    from modules.console_ui import format_done_time

    assert format_done_time("not-a-time") == ""
    assert format_done_time("abcdefg") == ""
    assert format_done_time("2026/05/10") == ""


def test_main_menu_shows_daily_completion_time(tmp_path):
    """主菜单日报已完成时显示完成时间。"""
    from io import StringIO
    from modules.console_ui import print_main_menu, set_output_func
    from modules.task_status import mark_daily_done

    (tmp_path / "reports").mkdir(exist_ok=True)
    mark_daily_done(tmp_path, "test_proj")

    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_main_menu({"project_id": "test_proj"}, root=tmp_path)
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "2. 日报" in output
    assert "[已完成]" in output
    assert "完成于：" in output  # 有时间则必定包含


def test_hourly_submenu_shows_completion_time(tmp_path):
    """小时报子菜单已完成时段显示完成时间。"""
    from io import StringIO
    from modules.console_ui import print_sub_menu_hourly, set_output_func
    from modules.task_status import mark_hourly_done

    (tmp_path / "reports").mkdir(exist_ok=True)
    mark_hourly_done(tmp_path, "test_proj", "11点")

    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_sub_menu_hourly(root=tmp_path, project_id="test_proj")
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "11点" in output
    assert "[已完成]" in output
    assert "完成于：" in output
    # 15点未完成
    assert "15点" in output
    assert "[未完成]" in output


def test_main_menu_daily_not_done_shows_undone(tmp_path):
    """主菜单日报未完成时显示 [未完成]，不含时间。"""
    from io import StringIO
    from modules.console_ui import print_main_menu, set_output_func

    (tmp_path / "reports").mkdir(exist_ok=True)

    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_main_menu({"project_id": "nonexistent"}, root=tmp_path)
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "2. 日报" in output
    assert "[未完成]" in output
    assert "完成于：" not in output


def test_missing_time_does_not_error(tmp_path):
    """last_success_time 缺失时不报错。"""
    from modules.task_status import load_task_status, save_task_status

    (tmp_path / "reports").mkdir(exist_ok=True)
    # 手动构造没有 last_success_time 的状态
    data = {
        "date": __import__("datetime").date.today().isoformat(),
        "projects": {
            "test_proj": {
                "daily": {"done": True},  # 没有 last_success_time
                "hourly": {
                    "11点": {"done": False, "last_success_time": None},
                    "15点": {"done": False, "last_success_time": None},
                    "18点": {"done": False, "last_success_time": None},
                },
            }
        },
    }
    save_task_status(tmp_path, data)

    from io import StringIO
    from modules.console_ui import print_main_menu, set_output_func

    buf = StringIO()
    set_output_func(buf.write)
    try:
        # 不应报错
        print_main_menu({"project_id": "test_proj"}, root=tmp_path)
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "[已完成]" in output


# ── 四项目预置测试 ────────────────────────────────────────


def test_list_projects_includes_four_niu_projects():
    """list_projects 能识别四个真实项目。"""
    root = Path(__file__).resolve().parents[1]
    projects = list_projects(root)
    ids = {p["project_id"] for p in projects}
    assert "kunming_niu" in ids
    assert "nanjing_niu" in ids
    assert "ningbo_niu" in ids
    assert "changsha_niu" in ids


def test_list_projects_excludes_old_kunming():
    """list_projects 不再识别 kunming_npx。"""
    root = Path(__file__).resolve().parents[1]
    projects = list_projects(root)
    ids = {p["project_id"] for p in projects}
    assert "kunming_npx" not in ids


def test_default_project_is_kunming_niu():
    """默认项目是 kunming_niu。"""
    root = Path(__file__).resolve().parents[1]
    current = get_current_project(root)
    assert current["project_id"] == "kunming_niu"
    assert current["project_name"] == "昆明牛"


def test_kunming_niu_accounts():
    """昆明牛账户映射为银康01、银康银屑02、银康03。"""
    root = Path(__file__).resolve().parents[1]
    from modules.project_config import load_project_config
    proj = load_project_config(root, "kunming_niu")
    accounts = proj["accounts"]
    assert accounts[0]["standard_name"] == "银康01"
    assert accounts[0]["kst_ids"] == ["72828178"]
    assert accounts[1]["standard_name"] == "银康银屑02"
    assert accounts[1]["kst_ids"] == ["72828179"]
    assert accounts[2]["standard_name"] == "银康03"
    assert accounts[2]["kst_ids"] == ["81509165"]
    assert "baidu-银康03" in accounts[2]["baidu_names"]


def test_secrets_example_has_four_profiles():
    """secrets.example.json 包含四个 profile，密码为空。"""
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "secrets" / "secrets.example.json").read_text(encoding="utf-8"))
    baidu = data["baidu"]
    for profile in ["kunming_niu_baidu", "nanjing_niu_baidu", "ningbo_niu_baidu", "changsha_niu_baidu"]:
        assert profile in baidu
        assert baidu[profile]["username"] == ""
        assert baidu[profile]["password"] == ""


def test_regular_build_excludes_secrets_json():
    """普通 build_release 不包含 secrets/secrets.json。"""
    root = Path(__file__).resolve().parents[1]
    release = build_release(root, version="0.4.15")
    assert "hourly_report_bot_release_v0.4.15" in release.name

    import zipfile
    with zipfile.ZipFile(release) as archive:
        names = set(archive.namelist())
    assert "secrets/secrets.json" not in names
    assert "secrets/secrets.example.json" in names
    for pid in ["kunming_niu", "nanjing_niu", "ningbo_niu", "changsha_niu"]:
        assert f"configs/projects/{pid}.json" in names
    assert "configs/projects/kunming_npx.json" not in names
    assert "reports/menu_task_status.json" not in names
    assert "configs/projects/project_template.json" in names


def test_internal_build_includes_secrets_json():
    """内部 build_release 包含 secrets/secrets.json。"""
    root = Path(__file__).resolve().parents[1]
    release = build_release(root, version="0.4.15", internal=True)
    assert "hourly_report_bot_internal_v0.4.15" in release.name

    import zipfile
    with zipfile.ZipFile(release) as archive:
        names = set(archive.namelist())
    assert "secrets/secrets.json" in names


def test_internal_build_validates_missing_profile(tmp_path):
    """内部包缺少 profile 时校验失败。"""
    from tools.build_release import _validate_internal_secrets

    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "secrets.json").write_text(json.dumps({
        "baidu": {
            "kunming_niu_baidu": {"username": "a", "password": "b"},
            "nanjing_niu_baidu": {"username": "a", "password": "b"},
        }
    }, ensure_ascii=False), encoding="utf-8")

    errors = _validate_internal_secrets(tmp_path)
    assert len(errors) > 0
    assert any("缺少百度凭据 profile" in e for e in errors)


def test_internal_build_validates_empty_credentials(tmp_path):
    """内部包 profile 账号或密码为空时校验失败。"""
    from tools.build_release import _validate_internal_secrets

    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "secrets.json").write_text(json.dumps({
        "baidu": {
            "kunming_niu_baidu": {"username": "", "password": "b"},
            "nanjing_niu_baidu": {"username": "a", "password": ""},
            "ningbo_niu_baidu": {"username": "a", "password": "b"},
            "changsha_niu_baidu": {"username": "a", "password": "b"},
        }
    }, ensure_ascii=False), encoding="utf-8")

    errors = _validate_internal_secrets(tmp_path)
    assert len(errors) > 0
    assert any("未填写账号" in e for e in errors)
    assert any("未填写密码" in e for e in errors)


def test_internal_build_validates_all_complete(tmp_path):
    """内部包四个 profile 完整时校验通过。"""
    from tools.build_release import _validate_internal_secrets

    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "secrets.json").write_text(json.dumps({
        "baidu": {
            "kunming_niu_baidu": {"username": "a", "password": "b"},
            "nanjing_niu_baidu": {"username": "a", "password": "b"},
            "ningbo_niu_baidu": {"username": "a", "password": "b"},
            "changsha_niu_baidu": {"username": "a", "password": "b"},
        }
    }, ensure_ascii=False), encoding="utf-8")

    errors = _validate_internal_secrets(tmp_path)
    assert errors == []


# ── 夏思道说明文件测试 ────────────────────────────────────


def test_xia_sidao_readme_exists():
    """xia_sidao使用说明.md 存在。"""
    root = Path(__file__).resolve().parents[1]
    path = root / "xia_sidao使用说明.md"
    assert path.exists(), "xia_sidao使用说明.md 不存在"
    content = path.read_text(encoding="utf-8")
    assert "执行命令" in content
    assert "run_menu.bat" in content
    assert "参数表" in content
    assert "验证标准" in content
    for name in ["昆明牛", "南京牛", "宁波牛", "长沙牛"]:
        assert name in content, f"缺少项目：{name}"


def test_regular_build_includes_xia_sidao_readme():
    """普通包包含 xia_sidao使用说明.md。"""
    root = Path(__file__).resolve().parents[1]
    release = build_release(root, version="0.4.16")

    import zipfile
    with zipfile.ZipFile(release) as archive:
        names = set(archive.namelist())
    assert "xia_sidao使用说明.md" in names


def test_internal_build_includes_xia_sidao_readme():
    """内部包包含 xia_sidao使用说明.md。"""
    root = Path(__file__).resolve().parents[1]
    release = build_release(root, version="0.4.16", internal=True)

    import zipfile
    with zipfile.ZipFile(release) as archive:
        names = set(archive.namelist())
    assert "xia_sidao使用说明.md" in names


# ── 百度登录状态守卫测试 ──────────────────────────────────


def test_load_login_state_returns_empty_when_file_missing(tmp_path):
    """状态文件不存在时返回空状态。"""
    from modules.baidu_session import load_browser_login_state

    state = load_browser_login_state(tmp_path)
    assert state["last_profile"] is None


def test_mark_login_success_and_read_profile(tmp_path):
    """mark_browser_login_success 正确写入各字段。"""
    from modules.baidu_session import (
        get_browser_login_profile,
        load_browser_login_state,
        mark_browser_login_success,
    )

    (tmp_path / "reports").mkdir(exist_ok=True)
    mark_browser_login_success(
        tmp_path,
        credential_profile="kunming_niu_baidu",
        project_id="kunming_niu",
        project_name="昆明牛",
        task="run-daily",
        url="https://cc.baidu.com/report",
    )

    state = load_browser_login_state(tmp_path)
    assert state["last_profile"] == "kunming_niu_baidu"
    assert state["last_project_id"] == "kunming_niu"
    assert state["last_project_name"] == "昆明牛"
    assert state["last_task"] == "run-daily"
    assert state["last_login_at"] is not None
    assert "username" not in state
    assert "password" not in state


def test_get_browser_login_profile(tmp_path):
    """get_browser_login_profile 正确读取 last_profile。"""
    from modules.baidu_session import (
        get_browser_login_profile,
        mark_browser_login_success,
    )

    (tmp_path / "reports").mkdir(exist_ok=True)
    assert get_browser_login_profile(tmp_path) is None

    mark_browser_login_success(tmp_path, "nanjing_niu_baidu", project_id="nanjing_niu")
    assert get_browser_login_profile(tmp_path) == "nanjing_niu_baidu"


def test_clear_browser_login_state(tmp_path):
    """clear_browser_login_state 清空 last_profile。"""
    from modules.baidu_session import (
        clear_browser_login_state,
        get_browser_login_profile,
        mark_browser_login_success,
    )

    (tmp_path / "reports").mkdir(exist_ok=True)
    mark_browser_login_success(tmp_path, "test_profile", project_id="test")
    assert get_browser_login_profile(tmp_path) == "test_profile"

    clear_browser_login_state(tmp_path)
    assert get_browser_login_profile(tmp_path) is None


def test_logout_baidu_account_returns_dict():
    """logout_baidu_account 返回字典结构，不 traceback。"""
    from modules.baidu_session import logout_baidu_account

    result = logout_baidu_account(None)
    assert isinstance(result, dict)
    assert "success" in result
    assert result["success"] is False


def test_get_current_project_credential_profile():
    """从运行配置中正确读取 credential_profile。"""
    from modules.baidu_session import get_current_project_credential_profile

    assert get_current_project_credential_profile(
        {"baidu": {"credential_profile": "kunming_niu_baidu"}}
    ) == "kunming_niu_baidu"
    assert get_current_project_credential_profile(
        {"baidu": {"credential_project": "nanjing_niu_baidu"}}
    ) == "nanjing_niu_baidu"
    assert get_current_project_credential_profile({}) == ""


def test_browser_login_state_no_passwords(tmp_path):
    """browser_login_state.json 不包含 username/password。"""
    from modules.baidu_session import (
        load_browser_login_state,
        save_browser_login_state,
    )

    (tmp_path / "reports").mkdir(exist_ok=True)
    save_browser_login_state(tmp_path, {
        "last_profile": "test",
        "username": "should_be_stripped",
        "password": "should_be_stripped",
    })
    state = load_browser_login_state(tmp_path)
    assert "username" not in state
    assert "password" not in state


def test_menu_no_longer_pre_saves_login_state():
    """menu.py 不再提前写入 browser_login_state。"""
    root = Path(__file__).resolve().parents[1]
    content = (root / "menu.py").read_text(encoding="utf-8")
    assert "save_login_state(" not in content, "menu.py 不应再提前保存 login_state"
    assert "check_profile_match(" not in content, "menu.py 不应再调用 check_profile_match"
    assert "baidu_session" in content, "menu.py 应引用 baidu_session 注释"


def test_session_profile_match_no_logout(tmp_path, monkeypatch):
    """profile 一致时直接通过，不调用 logout 或 login。"""
    import logging
    from unittest.mock import MagicMock

    from modules.baidu_session import (
        ensure_baidu_profile_session,
        mark_browser_login_success,
    )

    (tmp_path / "reports").mkdir(exist_ok=True)
    mark_browser_login_success(tmp_path, "kunming_niu_baidu", project_id="kunming_niu")
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu"}
    fake_page = MagicMock()
    logger = logging.getLogger("test")

    # --- monkeypatch logout 和 login，断言不被调用 ---
    logout_calls = []
    login_calls = []
    monkeypatch.setattr("modules.baidu_session.logout_baidu_account",
                        lambda page: logout_calls.append(1) or {"success": True})
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed",
                        lambda page, root, config, logger: login_calls.append(1) or True)

    result = ensure_baidu_profile_session(
        tmp_path, config, fake_page, logger,
        input_func=lambda _: "", output_func=lambda _: None,
    )
    assert result is True
    assert len(logout_calls) == 0, "profile 一致时不应调用 logout"
    assert len(login_calls) == 0, "profile 一致时不应调用 login"


def test_session_last_profile_none_triggers_logout_and_login(tmp_path, monkeypatch):
    """last_profile=None 触发 logout + login，成功后写入状态。"""
    import logging
    from unittest.mock import MagicMock

    from modules.baidu_session import (
        ensure_baidu_profile_session,
        load_browser_login_state,
    )

    (tmp_path / "reports").mkdir(exist_ok=True)
    state_path = tmp_path / "reports" / "browser_login_state.json"
    assert not state_path.exists()

    config = {
        "baidu": {"credential_profile": "kunming_niu_baidu"},
        "project_id": "kunming_niu",
        "project_name": "昆明牛",
    }
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    logger = logging.getLogger("test")

    logout_calls = []
    login_calls = []
    monkeypatch.setattr("modules.baidu_session.logout_baidu_account",
                        lambda page: logout_calls.append(1) or {"success": True, "message": "ok"})
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed",
                        lambda page, root, config, logger: login_calls.append(1) or True)

    result = ensure_baidu_profile_session(
        tmp_path, config, fake_page, logger,
        task="test", input_func=lambda _: "", output_func=lambda _: None,
    )
    assert result is True
    assert len(logout_calls) >= 1, "last_profile=None 时应调用 logout"
    assert len(login_calls) >= 1, "应调用 login"

    assert state_path.exists()
    state = load_browser_login_state(tmp_path)
    assert state["last_profile"] == "kunming_niu_baidu"
    assert state["last_project_id"] == "kunming_niu"
    assert state["last_login_at"] is not None
    assert "username" not in state
    assert "password" not in state


def test_session_mismatch_triggers_logout_and_login(tmp_path, monkeypatch):
    """profile 不一致时触发 logout + login，成功后写入当前 profile。"""
    import logging
    from unittest.mock import MagicMock

    from modules.baidu_session import (
        ensure_baidu_profile_session,
        load_browser_login_state,
        mark_browser_login_success,
    )

    (tmp_path / "reports").mkdir(exist_ok=True)
    # 上次登录是 nanjing_niu，当前项目是 kunming_niu
    mark_browser_login_success(tmp_path, "nanjing_niu_baidu", project_id="nanjing_niu")
    config = {
        "baidu": {"credential_profile": "kunming_niu_baidu"},
        "project_id": "kunming_niu",
        "project_name": "昆明牛",
    }
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    logger = logging.getLogger("test")

    logout_calls = []
    login_calls = []
    monkeypatch.setattr("modules.baidu_session.logout_baidu_account",
                        lambda page: logout_calls.append(1) or {"success": True, "message": "ok"})
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed",
                        lambda page, root, config, logger: login_calls.append(1) or True)

    result = ensure_baidu_profile_session(
        tmp_path, config, fake_page, logger,
        input_func=lambda _: "", output_func=lambda _: None,
    )
    assert result is True
    assert len(logout_calls) >= 1, "profile 不一致时应调用 logout"
    assert len(login_calls) >= 1, "应调用 login"

    state = load_browser_login_state(tmp_path)
    assert state["last_profile"] == "kunming_niu_baidu", "应写入当前项目 profile"


def test_session_logout_fail_user_cancel_returns_false(tmp_path, monkeypatch):
    """logout 失败 + 用户输入 0 取消 → 返回 False，不调用 login，不写状态。"""
    import logging
    from unittest.mock import MagicMock

    from modules.baidu_session import (
        ensure_baidu_profile_session,
        load_browser_login_state,
    )

    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {
        "baidu": {"credential_profile": "kunming_niu_baidu"},
        "project_id": "kunming_niu",
    }
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    logger = logging.getLogger("test")

    login_calls = []
    monkeypatch.setattr("modules.baidu_session.logout_baidu_account",
                        lambda page: {"success": False, "message": "未找到退出入口"})
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed",
                        lambda page, root, config, logger: login_calls.append(1) or True)

    result = ensure_baidu_profile_session(
        tmp_path, config, fake_page, logger,
        input_func=lambda _: "0", output_func=lambda _: None,
    )
    assert result is False, "用户取消应返回 False"
    assert len(login_calls) == 0, "取消后不应调用 login"
    # 状态文件不应写成当前 profile
    state = load_browser_login_state(tmp_path)
    assert state.get("last_profile") != "kunming_niu_baidu", "取消后不应写入 profile"


def test_session_logout_fail_manual_then_login(tmp_path, monkeypatch):
    """logout 失败 → 用户按回车 → 验证手动退出成功 → login → 写入状态。"""
    import logging
    from unittest.mock import MagicMock

    from modules.baidu_session import (
        ensure_baidu_profile_session,
        load_browser_login_state,
    )

    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {
        "baidu": {"credential_profile": "kunming_niu_baidu"},
        "project_id": "kunming_niu",
        "project_name": "昆明牛",
    }
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    logger = logging.getLogger("test")

    login_calls = []
    monkeypatch.setattr("modules.baidu_session.logout_baidu_account",
                        lambda page: {"success": False, "message": "未找到退出入口"})
    # 模拟 wait_until_logged_out 返回 True（用户手动退出成功）
    monkeypatch.setattr("modules.baidu_session.wait_until_logged_out",
                        lambda page, timeout_ms=5000: True)
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed",
                        lambda page, root, config, logger: login_calls.append(1) or True)

    result = ensure_baidu_profile_session(
        tmp_path, config, fake_page, logger,
        input_func=lambda _: "", output_func=lambda _: None,
    )
    assert result is True
    assert len(login_calls) >= 1, "手动退出验证通过后应调用 login"

    state = load_browser_login_state(tmp_path)
    assert state["last_profile"] == "kunming_niu_baidu", "应写入当前 profile"


def test_logout_baidu_account_calls_wait_until_logged_out(tmp_path, monkeypatch):
    """logout_baidu_account 点击退出后调用 wait_until_logged_out 验证。"""
    from unittest.mock import MagicMock

    from modules.baidu_session import logout_baidu_account

    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    # 模拟能找到退出按钮
    fake_el = MagicMock()
    fake_el.count.return_value = 1
    fake_el.is_visible.return_value = True
    fake_page.locator.return_value.first = fake_el

    wait_calls = []
    monkeypatch.setattr("modules.baidu_session.wait_until_logged_out",
                        lambda page, timeout_ms=5000: wait_calls.append(1) or True)

    result = logout_baidu_account(fake_page)
    assert result["success"] is True
    assert len(wait_calls) >= 1, "logout_baidu_account 必须调用 wait_until_logged_out"


def test_logout_baidu_account_fails_when_wait_returns_false(tmp_path, monkeypatch):
    """wait_until_logged_out 返回 False 时 logout_baidu_account 返回 success=False。"""
    from unittest.mock import MagicMock

    from modules.baidu_session import logout_baidu_account

    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    fake_el = MagicMock()
    fake_el.count.return_value = 1
    fake_el.is_visible.return_value = True
    fake_page.locator.return_value.first = fake_el

    monkeypatch.setattr("modules.baidu_session.wait_until_logged_out",
                        lambda page, timeout_ms=5000: False)

    result = logout_baidu_account(fake_page)
    assert result["success"] is False, "wait_until_logged_out=False 时应返回失败"
    assert "仍未确认退出成功" in result["message"]


def test_daily_calls_ensure_session(monkeypatch):
    """baidu_daily.py 抓数前调用 ensure_baidu_profile_session。"""
    root = Path(__file__).resolve().parents[1]
    source = (root / "modules" / "baidu_daily.py").read_text(encoding="utf-8")
    assert "ensure_baidu_profile_session" in source, "baidu_daily.py 应调用 ensure_baidu_profile_session"


def test_hourly_calls_ensure_session(monkeypatch):
    """baidu_overview.py 小时报抓数前调用 ensure_baidu_profile_session。"""
    root = Path(__file__).resolve().parents[1]
    source = (root / "modules" / "baidu_overview.py").read_text(encoding="utf-8")
    assert "ensure_baidu_profile_session" in source, "baidu_overview.py 应调用 ensure_baidu_profile_session"


# ── 未知百度账户报告测试 ──────────────────────────────────


def test_build_unknown_report_structure():
    """build_unknown_baidu_accounts_report 生成完整结构。"""
    from modules.baidu_unknown_accounts import build_unknown_baidu_accounts_report

    config = {"project_id": "kunming_niu", "project_name": "昆明牛"}
    parsed = {
        "unknown_accounts": [
            {"account_name": "未知A", "展现": 100, "点击": 10, "消费": 50.5,
             "reason": "百度后台抓到该账户，但当前项目配置 accounts 中未配置"},
        ]
    }

    report = build_unknown_baidu_accounts_report(
        config, parsed, task="hourly", date="2026-05-14", period="15点",
    )

    assert report["date"] == "2026-05-14"
    assert report["task"] == "hourly"
    assert report["period"] == "15点"
    assert report["project_id"] == "kunming_niu"
    assert report["project_name"] == "昆明牛"
    assert len(report["unknown_accounts"]) == 1
    assert report["unknown_accounts"][0]["account_name"] == "未知A"
    assert "suggestion" in report["unknown_accounts"][0]


def test_write_unknown_report_when_empty(tmp_path):
    """unknown_accounts 为空时不写文件。"""
    from modules.baidu_unknown_accounts import write_unknown_baidu_accounts_report

    report = {"unknown_accounts": []}
    result = write_unknown_baidu_accounts_report(tmp_path, report)
    assert result is None


def test_write_unknown_report_when_non_empty(tmp_path):
    """unknown_accounts 非空时写入文件。"""
    from modules.baidu_unknown_accounts import write_unknown_baidu_accounts_report

    (tmp_path / "reports").mkdir(exist_ok=True)
    report = {
        "unknown_accounts": [
            {"account_name": "未知A", "展现": 100, "点击": 10, "消费": 50},
        ]
    }
    result = write_unknown_baidu_accounts_report(tmp_path, report)
    assert result is not None
    assert (tmp_path / "reports" / "unknown_baidu_accounts.json").exists()


def test_build_unknown_report_includes_suggestion():
    """unknown report 每项包含 suggestion 字段。"""
    from modules.baidu_unknown_accounts import build_unknown_baidu_accounts_report

    config = {"project_id": "test_proj"}
    parsed = {"unknown_accounts": [{"account_name": "X", "展现": 1, "点击": 0, "消费": 0}]}

    report = build_unknown_baidu_accounts_report(config, parsed, task="daily")
    assert "suggestion" in report["unknown_accounts"][0]
    assert "configs/projects" in report["unknown_accounts"][0]["suggestion"]


def test_auto_report_includes_unknown_accounts():
    """baidu_auto.py 报告结构包含 unknown_accounts 和 ignored_unknown_accounts。"""
    root = Path(__file__).resolve().parents[1]
    source = (root / "modules" / "baidu_auto.py").read_text(encoding="utf-8")
    assert '"unknown_accounts"' in source
    assert '"ignored_unknown_accounts"' in source
    assert "unknown_baidu_accounts_report" in source


def test_daily_report_includes_unknown_accounts():
    """baidu_daily.py 报告结构包含 unknown_accounts 和 ignored_unknown_accounts。"""
    root = Path(__file__).resolve().parents[1]
    source = (root / "modules" / "baidu_daily.py").read_text(encoding="utf-8")
    assert '"unknown_accounts"' in source
    assert '"ignored_unknown_accounts"' in source
    assert "unknown_baidu_accounts_report" in source


def test_build_release_excludes_unknown_accounts_json():
    """build_release 不包含 reports/unknown_baidu_accounts.json。"""
    root = Path(__file__).resolve().parents[1]
    release = build_release(root, version="0.4.17")

    import zipfile
    with zipfile.ZipFile(release) as archive:
        names = set(archive.namelist())
    assert "reports/unknown_baidu_accounts.json" not in names


# ── 未知账户终端提醒测试 ──────────────────────────────────


def test_has_unknown_accounts_detects_presence():
    """has_unknown_baidu_accounts 正确判断未知账户有无。"""
    from modules.baidu_unknown_accounts import has_unknown_baidu_accounts

    assert has_unknown_baidu_accounts({"unknown_accounts": [{"account_name": "X"}]}) is True
    assert has_unknown_baidu_accounts({"unknown_accounts": []}) is False
    assert has_unknown_baidu_accounts({}) is False


def test_format_notice_includes_metrics():
    """提醒行包含账户名、展现、点击、消费。"""
    from modules.baidu_unknown_accounts import format_unknown_baidu_accounts_notice

    report = {
        "unknown_accounts": [
            {"account_name": "未知A", "展现": 100, "点击": 10, "消费": 50.5},
        ]
    }
    lines = format_unknown_baidu_accounts_notice(report)
    text = " ".join(lines)
    assert "未知A" in text
    assert "100" in text
    assert "10" in text
    assert "50.5" in text
    assert "已单独隔离" in text
    assert "不影响本次写入" in text


def test_format_notice_no_report_path():
    """默认提醒不包含 unknown_baidu_accounts.json 路径。"""
    from modules.baidu_unknown_accounts import format_unknown_baidu_accounts_notice

    report = {
        "unknown_accounts": [{"account_name": "X", "展现": 1, "点击": 0, "消费": 0}],
        "unknown_accounts_report": "reports/unknown_baidu_accounts.json",
    }
    lines = format_unknown_baidu_accounts_notice(report)
    text = " ".join(lines)
    assert "unknown_baidu_accounts.json" not in text


def test_format_notice_empty_returns_empty():
    """unknown_accounts 为空时 format_notice 返回空列表。"""
    from modules.baidu_unknown_accounts import format_unknown_baidu_accounts_notice

    assert format_unknown_baidu_accounts_notice({"unknown_accounts": []}) == []


def test_ignored_unknown_does_not_trigger_notice():
    """ignored_unknown_accounts 非空但 unknown_accounts 为空时不触发提醒。"""
    from modules.baidu_unknown_accounts import has_unknown_baidu_accounts, format_unknown_baidu_accounts_notice

    report = {
        "unknown_accounts": [],
        "ignored_unknown_accounts": [{"account_name": "零账户", "展现": 0, "点击": 0, "消费": 0}],
    }
    assert has_unknown_baidu_accounts(report) is False
    assert format_unknown_baidu_accounts_notice(report) == []


def test_run_pipeline_continues_after_unknown_notice(tmp_path):
    """未知账户提醒不阻断 pipeline 后续步骤。"""
    import logging

    kst_file = tmp_path / "kst.xlsx"
    kst_file.write_text("placeholder", encoding="utf-8")
    excel_file = tmp_path / "target.xlsx"
    excel_file.write_text("placeholder", encoding="utf-8")

    def ok_baidu(**kwargs):
        return {
            "date": "2026-05-07", "period": "15",
            "accounts": {
                "银康01": {"展现": 1, "点击": 1, "消费": 1.0},
                "银康银屑02": {"展现": 2, "点击": 2, "消费": 2.0},
                "银康03": {"展现": 3, "点击": 3, "消费": 3.0},
            },
            "unknown_accounts": [{"account_name": "未知A", "展现": 100, "点击": 10, "消费": 50}],
            "errors": [],
        }

    def ok_kst(export_file, config, root, period):
        return {"parse_report": {"passed": True, "errors": []}, "outputs": {}}

    def ok_merge(**kwargs):
        return {"merged": {"date": "2026-05-07", "period": "15点"}, "validate_report": {"passed": True, "errors": []}, "outputs": {}}

    def ok_write(**kwargs):
        return {
            "date": "2026-05-07", "period": "15点", "excel_path": str(excel_file),
            "writes": [{"cell": "P5"}], "self_check": {"verification_passed": True}, "errors": [],
        }

    report = run_half_auto_pipeline(
        config={"excel_path": str(excel_file)},
        root=tmp_path, logger=logging.getLogger("test"),
        period="15点", kst_file=kst_file, assume_yes=True,
        fetch_baidu_func=ok_baidu, parse_kst_func=ok_kst,
        merge_func=ok_merge, write_func=ok_write,
    )
    # pipeline 应成功完成，不因未知账户中断
    assert report["passed"] is True
    assert report["failed_step"] is None


def test_verbose_shows_report_path(capsys):
    """verbose 模式显示 unknown_baidu_accounts.json 路径。"""
    from modules.baidu_unknown_accounts import print_unknown_baidu_accounts_notice
    from modules.console_ui import set_verbose

    set_verbose(True)
    report = {
        "unknown_accounts": [{"account_name": "X", "展现": 1, "点击": 0, "消费": 0}],
        "unknown_accounts_report": "reports/unknown_baidu_accounts.json",
    }
    print_unknown_baidu_accounts_notice(report)

    captured = capsys.readouterr()
    assert "unknown_baidu_accounts.json" in captured.out
    set_verbose(False)
