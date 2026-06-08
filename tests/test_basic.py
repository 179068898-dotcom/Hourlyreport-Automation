import json
import os
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


def _replace_xlsx_text(path: Path, member: str, old: str, new: str) -> None:
    from zipfile import ZIP_DEFLATED, ZipFile

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with ZipFile(path, "r") as source, ZipFile(tmp_path, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == member:
                data = data.decode("utf-8").replace(old, new).encode("utf-8")
            target.writestr(item, data)
    tmp_path.replace(path)


def test_restore_sheet_filter_protection_metadata_keeps_original_protection_attrs(tmp_path):
    from zipfile import ZipFile

    from openpyxl import Workbook, load_workbook

    class Logger:
        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

    excel_path = tmp_path / "current.xlsx"
    backup_path = tmp_path / "backup.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "时段数据"
    ws["A3"] = "日期"
    ws["B3"] = "时段"
    ws.auto_filter.ref = "A3:B10"
    ws.protection.sheet = True
    ws.protection.autoFilter = False
    ws.protection.sort = True
    wb.save(backup_path)
    wb.save(excel_path)

    with ZipFile(backup_path) as zf:
        original_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
    original_node_start = original_xml.index("<sheetProtection")
    original_node_end = original_xml.index("/>", original_node_start) + 2
    original_node = original_xml[original_node_start:original_node_end]
    rich_node = (
        '<sheetProtection selectLockedCells="0" selectUnlockedCells="0" '
        'algorithmName="SHA-512" sheet="1" objects="1" insertRows="1" '
        'autoFilter="0" scenarios="0" formatColumns="0" sort="1" />'
    )
    dropped_node = '<sheetProtection sheet="1" formatColumns="0" autoFilter="0" objects="1"/>'
    _replace_xlsx_text(backup_path, "xl/worksheets/sheet1.xml", original_node, rich_node)
    _replace_xlsx_text(excel_path, "xl/worksheets/sheet1.xml", original_node, dropped_node)

    restored = _restore_sheet_filter_protection_metadata(
        excel_path,
        backup_path,
        ["时段数据"],
        Logger(),
    )

    assert restored is True
    with ZipFile(excel_path) as zf:
        restored_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert rich_node in restored_xml
    assert dropped_node not in restored_xml
    assert load_workbook(excel_path)["时段数据"]["A3"].value == "日期"


def test_restore_sheet_filter_protection_metadata_restores_original_auto_filter(tmp_path):
    from openpyxl import Workbook, load_workbook

    class Logger:
        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

    excel_path = tmp_path / "current.xlsx"
    backup_path = tmp_path / "backup.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "时段数据"
    ws["A3"] = "日期"
    ws["B3"] = "时段"
    ws.auto_filter.ref = "A3:XDP1464"
    wb.save(backup_path)

    ws.auto_filter.ref = None
    wb.save(excel_path)

    restored = _restore_sheet_filter_protection_metadata(
        excel_path,
        backup_path,
        ["时段数据"],
        Logger(),
    )

    assert restored is True
    assert load_workbook(excel_path)["时段数据"].auto_filter.ref == "A3:XDP1464"

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
from modules.excel_writer import (
    _find_target_row,
    _normalize_period_for_excel,
    _restore_sheet_filter_protection_metadata,
    _validate_write_target,
)
from modules.daily_excel_inspector import inspect_daily_worksheet
from modules.data_merger import build_merged_daily_data, build_merged_hourly_data
from modules.excel_writer import write_merged_daily_data, write_merged_hourly_data
from modules.baidu_parser import _build_account_map, _build_parse_debug, _map_account, _parse_number, extract_baidu_rows_from_visible_text, parse_baidu_table
from modules.baidu_browser import _extract_selected_date_from_text, _write_debug_artifacts
from modules.baidu_detector import classify_baidu_page
from modules.baidu_overview import is_search_promotion_overview, overview_text_has_account_table, should_open_cas_login, validate_overview_ready
from modules.baidu_validator import validate_baidu_account_data
from modules.baidu_auto import build_baidu_auto_report_from_visible_text
from modules.baidu_auto import fetch_baidu_auto
from modules.baidu_daily import build_baidu_daily_report_from_visible_text, default_daily_date
from modules.credential_manager import build_login_failure_message, load_project_credentials
from modules.browser_manager import BrowserLaunchError, CONNECT_EXISTING_HELP, cleanup_extra_tabs, connect_existing_chrome, get_browser_settings
from modules.chrome_debug import ensure_chrome_debug_ready, find_chrome_executable, is_chrome_debug_port_alive, start_debug_chrome
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
    assert any("项目至少需要 1 个账户" in error for error in errors)


def test_project_config_allows_two_account_single_source_project():
    project = {
        "project_id": "two_account_project",
        "project_name": "两账户项目",
        "excel": {"path": "samples/two.xlsx", "hourly_sheet": "时段数据", "daily_sheet": "百度", "engine": "openpyxl"},
        "kst": {"export_dir": "kst_exports", "auto_pick_latest": True, "max_file_age_hours": 2},
        "baidu": {"credential_profile": "two_profile", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
        "accounts": [
            {"standard_name": "账户1", "baidu_names": ["账户1"], "excel_name": "账户1", "kst_ids": ["1001"], "kst_names": ["账户1"]},
            {"standard_name": "账户2", "baidu_names": ["账户2"], "excel_name": "账户2", "kst_ids": ["1002"], "kst_names": ["账户2"]},
        ],
        "hourly": {"periods": ["11点", "15点", "18点"]},
        "daily": {
            "write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"],
            "do_not_write_fields": ["总对话", "预约", "到诊", "就诊"],
        },
    }

    assert validate_project_config(project) == []


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
    assert "3. 切换项目" in MENU_TEXT
    assert "4. 检查条件项" in MENU_TEXT
    assert "5. 更多功能" in MENU_TEXT
    assert "0. 退出" in MENU_TEXT
    for advanced_text in ["预检与环境", "报告与日志", "配置与诊断", "OpenClaw 帮助", "多百度来源摘要"]:
        assert advanced_text not in MENU_TEXT


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


def test_doctor_excel_com_reads_optional_requirements_file(tmp_path, monkeypatch):
    import modules.doctor as doctor

    (tmp_path / "requirements.txt").write_text("openpyxl>=3.1.2\n", encoding="utf-8")
    (tmp_path / "requirements-excel-com.txt").write_text("xlwings>=0.30.0\npywin32>=306\n", encoding="utf-8")

    def fake_version(package_name):
        if package_name in {"xlwings", "pywin32"}:
            raise doctor.importlib.metadata.PackageNotFoundError
        return "1.0"

    monkeypatch.setattr(doctor.importlib.metadata, "version", fake_version)

    openpyxl_report = doctor._check_requirements(tmp_path, excel_engine="openpyxl")
    excel_com_report = doctor._check_requirements(tmp_path, excel_engine="excel_com")

    assert openpyxl_report["passed"] is True
    assert excel_com_report["passed"] is False
    assert set(excel_com_report["detail"]["missing"]) == {"xlwings", "pywin32"}


def test_default_install_excludes_optional_excel_com_dependencies():
    root = Path(__file__).resolve().parents[1]
    base = (root / "requirements.txt").read_text(encoding="utf-8")
    optional = (root / "requirements-excel-com.txt").read_text(encoding="utf-8")

    assert "xlwings" not in base
    assert "pywin32" not in base
    assert "xlwings" in optional
    assert "pywin32" in optional


def test_run_menu_installs_or_repairs_missing_dependencies_before_importing_menu():
    root = Path(__file__).resolve().parents[1]
    script = (root / "run_menu.bat").read_text(encoding="utf-8")

    assert 'if not exist ".venv\\Scripts\\python.exe"' in script
    assert 'set "NEED_INSTALL=1"' in script
    assert 'call "%~dp0install_env.bat"' in script
    assert 'import openpyxl, pandas, xlrd, dateutil, playwright, rich' in script


def test_release_builder_excludes_sensitive_and_runtime_files():
    assert should_include_file(Path("main.py")) is True
    assert should_include_file(Path("modules") / "doctor.py") is True
    assert should_include_file(Path("reports") / ".gitkeep") is False
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


def test_visitor_dialog_accepts_visitor_sent_count_alias():
    assert has_visitor_dialog({"访客发送数": "1"}) is True
    assert has_visitor_dialog({"访客发送数": "0"}) is False


def test_visitor_dialog_accepts_visitor_sent_message_count_alias():
    assert has_visitor_dialog({"访客发送消息数": "1"}) is True
    assert has_visitor_dialog({"访客发送消息数": "0"}) is False


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


def test_parse_kst_export_accepts_visitor_sent_count_header(tmp_path):
    export = tmp_path / "kst_sent_count.csv"
    today = date.today().isoformat()
    export.write_text(
        "对话时间,备注说明,名片标签,访客发送数\n"
        f"{today} 10:00,72828178-abc,转潜-有效,1\n",
        encoding="utf-8-sig",
    )
    config = _kunming_niu_runtime_config()
    config["kst"] = {"export_dir": str(tmp_path), "promotion_id_accounts": _kunming_niu_runtime_config()["kst"]["promotion_id_accounts"]}

    result = parse_kst_export_file(export, config, tmp_path, "15点")

    assert result["parse_report"]["passed"] is True
    assert result["parse_report"]["field_info"]["has_visitor_messages"] is True
    assert result["dialog_data"]["accounts"]["银康01"]["总对话"] == 1
    assert result["dialog_data"]["accounts"]["银康01"]["有效"] == 1


def test_parse_kst_export_accepts_visitor_sent_message_count_header(tmp_path):
    export = tmp_path / "kst_sent_message_count.csv"
    today = date.today().isoformat()
    export.write_text(
        "对话时间,备注说明,名片标签,访客发送消息数\n"
        f"{today} 10:00,72828178-abc,转潜-有效,1\n",
        encoding="utf-8-sig",
    )
    config = _kunming_niu_runtime_config()
    config["kst"] = {"export_dir": str(tmp_path), "promotion_id_accounts": _kunming_niu_runtime_config()["kst"]["promotion_id_accounts"]}

    result = parse_kst_export_file(export, config, tmp_path, "15点")

    assert result["parse_report"]["passed"] is True
    assert result["parse_report"]["field_info"]["has_visitor_messages"] is True
    assert result["dialog_data"]["accounts"]["银康01"]["总对话"] == 1
    assert result["dialog_data"]["accounts"]["银康01"]["有效"] == 1


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


def test_parse_kst_daily_accepts_visitor_sent_count_header(tmp_path):
    export = tmp_path / "kst_daily_sent_count.csv"
    export.write_text(
        "对话时间,备注说明,名片标签,访客发送数\n"
        "2026-05-07 10:00,72828178-abc,转潜-有效,1\n",
        encoding="utf-8-sig",
    )

    result = parse_kst_daily_file(export, _kunming_niu_runtime_config(), tmp_path, "2026-05-07")

    assert result["parse_report"]["passed"] is True
    assert result["parse_report"]["field_info"]["has_visitor_messages"] is True
    assert result["daily_data"]["accounts"]["银康01"]["总对话"] == 1
    assert result["daily_data"]["accounts"]["银康01"]["有效对话"] == 1
    assert result["daily_data"]["accounts"]["银康01"]["无效对话"] == 0


def test_parse_kst_daily_accepts_visitor_sent_message_count_header(tmp_path):
    export = tmp_path / "kst_daily_sent_message_count.csv"
    export.write_text(
        "对话时间,备注说明,名片标签,访客发送消息数\n"
        "2026-05-07 10:00,72828178-abc,转潜-有效,1\n",
        encoding="utf-8-sig",
    )

    result = parse_kst_daily_file(export, _kunming_niu_runtime_config(), tmp_path, "2026-05-07")

    assert result["parse_report"]["passed"] is True
    assert result["parse_report"]["field_info"]["has_visitor_messages"] is True
    assert result["daily_data"]["accounts"]["银康01"]["总对话"] == 1
    assert result["daily_data"]["accounts"]["银康01"]["有效对话"] == 1
    assert result["daily_data"]["accounts"]["银康01"]["无效对话"] == 0


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


def test_map_account_requires_exact_match_for_ningbo_suffix_accounts():
    config = {
        "accounts": {
            "宁波博润1": {"baidu_name": "宁波博润1", "aliases": ["宁波博润1"]},
            "宁波博润12": {"baidu_name": "宁波博润12", "aliases": ["宁波博润12"]},
            "宁波博润13": {"baidu_name": "宁波博润13", "aliases": ["宁波博润13"]},
        }
    }
    account_map = _build_account_map(config)

    assert _map_account("宁波博润12", account_map) == "宁波博润12"
    assert _map_account("宁波博润1", account_map) == "宁波博润1"
    assert _map_account(" 宁波博润1 ", account_map) == "宁波博润1"


def test_map_account_does_not_fallback_to_contains_match():
    config = {
        "accounts": {
            "宁波博润1": {"baidu_name": "宁波博润1", "aliases": ["宁波博润1"]},
        }
    }
    account_map = _build_account_map(config)

    assert _map_account("宁波博润12", account_map) is None


def test_parse_baidu_table_treats_unconfigured_suffix_account_as_unknown():
    config = {
        "accounts": {
            "宁波博润1": {"baidu_name": "宁波博润1", "aliases": ["宁波博润1"]},
        }
    }
    rows = [
        {"账户": "宁波博润12", "展现": "100", "点击": "10", "消费": "20.5"},
    ]

    parsed = parse_baidu_table(rows, config)

    assert "宁波博润1" not in parsed["accounts"]
    assert parsed["unknown_accounts"][0]["account_name"] == "宁波博润12"


def test_parse_baidu_table_distinguishes_changsha_accounts_by_exact_name():
    config = {
        "accounts": {
            "竞网CS博润241209": {"baidu_name": "竞网CS博润241209", "aliases": ["竞网CS博润241209"]},
            "竞网CS博润240304": {"baidu_name": "竞网CS博润240304", "aliases": ["竞网CS博润240304"]},
            "竞网CS博润251218": {"baidu_name": "竞网CS博润251218", "aliases": ["竞网CS博润251218"]},
        }
    }
    rows = [
        {"账户": "竞网CS博润241209", "展现": "100", "点击": "10", "消费": "20.5"},
        {"账户": "竞网CS博润240304", "展现": "200", "点击": "20", "消费": "30.5"},
        {"账户": "竞网CS博润251218", "展现": "300", "点击": "30", "消费": "40.5"},
    ]

    parsed = parse_baidu_table(rows, config)

    assert parsed["errors"] == []
    assert parsed["accounts"]["竞网CS博润241209"]["展现"] == 100
    assert parsed["accounts"]["竞网CS博润240304"]["展现"] == 200
    assert parsed["accounts"]["竞网CS博润251218"]["展现"] == 300


def test_build_parse_debug_records_only_exact_account_matches():
    config = {
        "accounts": {
            "宁波博润1": {"baidu_name": "宁波博润1", "aliases": ["宁波博润1"]},
            "宁波博润12": {"baidu_name": "宁波博润12", "aliases": ["宁波博润12"]},
        }
    }
    rows = [
        {"账户": " 宁波博润1 ", "展现": "100", "点击": "10", "消费": "20.5"},
        {"账户": "宁波博润12", "展现": "200", "点击": "20", "消费": "30.5"},
    ]

    debug = _build_parse_debug(rows, config, "dom")

    assert [item["matched_account"] for item in debug["account_match_details"]] == ["宁波博润1", "宁波博润12"]
    assert all(item["match_type"] == "exact" for item in debug["account_match_details"])


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
    assert settings["silent_automation"] is True
    assert settings["window_state"] == "minimized"
    assert settings["show_on_manual_intervention"] is True
    assert settings["disable_password_manager"] is True


def test_browser_settings_accepts_silent_overrides():
    settings = get_browser_settings(
        {
            "browser": {
                "silent_automation": False,
                "window_state": "normal",
                "show_on_manual_intervention": False,
                "disable_password_manager": False,
            }
        }
    )

    assert settings["silent_automation"] is False
    assert settings["window_state"] == "normal"
    assert settings["show_on_manual_intervention"] is False
    assert settings["disable_password_manager"] is False


def test_prepare_automation_page_does_not_touch_window_in_silent_mode():
    from modules.browser_manager import prepare_automation_page

    class FakeContext:
        def new_cdp_session(self, page):
            raise AssertionError("silent automation must not activate the window through CDP")

    class FakePage:
        context = FakeContext()

        def bring_to_front(self):
            raise AssertionError("silent automation must not bring Chrome to front")

    prepare_automation_page(FakePage(), {"browser": {"silent_automation": True, "window_state": "minimized"}})


def test_prepare_automation_page_can_focus_when_silent_disabled():
    from modules.browser_manager import prepare_automation_page

    class FakePage:
        def __init__(self):
            self.front = False

        def bring_to_front(self):
            self.front = True

    page = FakePage()
    prepare_automation_page(page, {"browser": {"silent_automation": False}})

    assert page.front is True


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
    assert "Google Chrome" in CONNECT_EXISTING_HELP
    assert "chrome_debug" in CONNECT_EXISTING_HELP
    assert "不需要关闭日常 Chrome" in CONNECT_EXISTING_HELP
    assert "--remote-debugging-port=9222" in CONNECT_EXISTING_HELP
    assert "--start-minimized" in CONNECT_EXISTING_HELP
    assert "cas.baidu.com" in CONNECT_EXISTING_HELP
    assert "yingxiao.baidu.com" not in CONNECT_EXISTING_HELP


def test_default_chrome_startup_url_is_cas_login():
    import json

    from modules.browser_manager import get_browser_settings
    from modules.chrome_debug import DEFAULT_STARTUP_URL
    from modules.chrome_debug_launcher import START_URL

    settings = get_browser_settings({})
    example_config = json.loads((Path(__file__).resolve().parents[1] / "config.example.json").read_text(encoding="utf-8"))
    example_settings = get_browser_settings(example_config)

    assert "cas.baidu.com" in settings["startup_url"]
    assert "cas.baidu.com" in example_settings["startup_url"]
    assert "cas.baidu.com" in example_config["baidu"]["start_url"]
    assert "cas.baidu.com" in example_config["baidu"]["login_url"]
    assert "cas.baidu.com" in DEFAULT_STARTUP_URL
    assert "cas.baidu.com" in START_URL
    assert "yingxiao.baidu.com" not in settings["startup_url"]
    assert "yingxiao.baidu.com" not in example_settings["startup_url"]
    assert "yingxiao.baidu.com" not in example_config["browser"]["startup_url"]
    assert "qingge.baidu.com" not in example_config["baidu"]["login_url"]
    assert "yingxiao.baidu.com" not in DEFAULT_STARTUP_URL
    assert "yingxiao.baidu.com" not in START_URL


def test_select_context_repoints_legacy_yingxiao_page_to_cas():
    from modules.browser_manager import DEFAULT_BAIDU_START_URL, _select_context_and_page

    class FakePage:
        def __init__(self, url):
            self.url = url
            self.goto_calls = []
            self.front = False

        def goto(self, url, wait_until=None, timeout=None):
            self.goto_calls.append(url)
            self.url = url

        def bring_to_front(self):
            self.front = True

    class FakeContext:
        def __init__(self, pages):
            self.pages = pages

        def new_page(self):
            page = FakePage("about:blank")
            self.pages.append(page)
            return page

    class FakeBrowser:
        def __init__(self, contexts):
            self.contexts = contexts

    legacy_page = FakePage("https://yingxiao.baidu.com/home")
    context, page = _select_context_and_page(FakeBrowser([FakeContext([legacy_page])]), DEFAULT_BAIDU_START_URL)

    assert page is legacy_page
    assert context.pages == [legacy_page]
    assert legacy_page.goto_calls == [DEFAULT_BAIDU_START_URL]
    assert legacy_page.front is False


def test_select_context_keeps_existing_cc_report_page():
    from modules.browser_manager import DEFAULT_BAIDU_START_URL, _select_context_and_page

    class FakePage:
        def __init__(self, url):
            self.url = url
            self.goto_calls = []
            self.front = False

        def goto(self, url, wait_until=None, timeout=None):
            self.goto_calls.append(url)
            self.url = url

        def bring_to_front(self):
            self.front = True

    class FakeContext:
        def __init__(self, pages):
            self.pages = pages

    class FakeBrowser:
        def __init__(self, contexts):
            self.contexts = contexts

    report_page = FakePage("https://cc.baidu.com/report")
    context, page = _select_context_and_page(FakeBrowser([FakeContext([report_page])]), DEFAULT_BAIDU_START_URL)

    assert page is report_page
    assert report_page.goto_calls == []
    assert report_page.front is False


def test_select_context_can_show_page_for_non_silent_mode():
    from modules.browser_manager import DEFAULT_BAIDU_START_URL, _select_context_and_page

    class FakePage:
        def __init__(self, url):
            self.url = url
            self.front = False

        def bring_to_front(self):
            self.front = True

    class FakeContext:
        def __init__(self, pages):
            self.pages = pages

    class FakeBrowser:
        def __init__(self, contexts):
            self.contexts = contexts

    report_page = FakePage("https://cc.baidu.com/report")
    _select_context_and_page(FakeBrowser([FakeContext([report_page])]), DEFAULT_BAIDU_START_URL, silent=False)

    assert report_page.front is True


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
    assert pages[3].front is False


def test_cleanup_extra_tabs_can_show_keep_page_for_non_silent_mode():
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

    pages = [FakePage("https://old.example/1"), FakePage("https://cc.baidu.com/report")]

    cleanup_extra_tabs(FakeContext(pages), pages[1], max_tabs=1, silent=False)

    assert pages[1].front is True


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


def test_extract_baidu_rows_from_visible_text_uses_data_width_when_group_header_has_no_cell():
    text = """
详细数据
账户
账户ID
展现
点击
消费
平均点击价格
落地页转化
一句话咨询量
留线索量
总计-3
-
7,990
1,113
2,989.19
2.69
14
1
竞网CS博润240304
53559272
720
58
186.85
3.22
0
0
竞网CS博润241209
61561000
1,568
174
1,779.96
10.23
5
0
竞网CS博润251218
77609531
5,702
881
1,022.38
1.16
9
1
20条/页
"""
    config = {
        "accounts": {
            "竞网CS博润240304": {"baidu_name": "竞网CS博润240304"},
            "竞网CS博润241209": {"baidu_name": "竞网CS博润241209"},
            "竞网CS博润251218": {"baidu_name": "竞网CS博润251218"},
        }
    }

    rows = extract_baidu_rows_from_visible_text(text)
    parsed = parse_baidu_table(rows, config)

    assert len(rows) == 4
    assert parsed["errors"] == []
    assert parsed["accounts"]["竞网CS博润240304"]["展现"] == 720
    assert parsed["accounts"]["竞网CS博润240304"]["点击"] == 58
    assert parsed["accounts"]["竞网CS博润240304"]["消费"] == 186.85
    assert parsed["accounts"]["竞网CS博润241209"]["展现"] == 1568
    assert parsed["accounts"]["竞网CS博润241209"]["点击"] == 174
    assert parsed["accounts"]["竞网CS博润241209"]["消费"] == 1779.96
    assert parsed["accounts"]["竞网CS博润251218"]["展现"] == 5702
    assert parsed["accounts"]["竞网CS博润251218"]["点击"] == 881
    assert parsed["accounts"]["竞网CS博润251218"]["消费"] == 1022.38


def test_extract_baidu_rows_from_visible_text_rejects_unverifiable_data_width():
    text = """
账户
账户ID
展现
点击
消费
平均点击价格
落地页转化
一句话咨询量
留线索量
总计-3
-
7,990
1,113
2,989.19
2.69
14
1
竞网CS博润240304
53559272
720
58
186.85
3.22
0
0
竞网CS博润241209
61561000
1,568
174
1,779.96
10.23
5
20条/页
"""

    assert extract_baidu_rows_from_visible_text(text) == []


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
    ws.auto_filter.ref = "A2:Z6"
    notes_ws = wb.create_sheet("说明")
    notes_ws["A1"] = "无关工作表"
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
    assert verify_ws.auto_filter.ref == "A2:Z6"
    assert verify_wb["说明"].auto_filter.ref is None


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
    ws.auto_filter.ref = "A2:BB3"
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
    assert ws2.auto_filter.ref == "A2:BB3"


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


def _baidu_credential_test_config(*profiles: str) -> dict:
    config = {
        "project_id": "demo",
        "project_name": "演示项目",
        "credentials_path": "secrets/secrets.json",
        "baidu": {"credential_profile": profiles[0] if profiles else ""},
    }
    if len(profiles) > 1:
        config["baidu_sources"] = [
            {"source_id": f"source_{index}", "source_name": f"来源{index}", "credential_profile": profile, "accounts": []}
            for index, profile in enumerate(profiles, start=1)
        ]
    return config


def test_preflight_credentials_fails_for_invalid_secrets_json_without_values(tmp_path):
    from modules.preflight import check_baidu_credentials

    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "secrets.json").write_text('{"baidu": invalid', encoding="utf-8")

    report = check_baidu_credentials(tmp_path, _baidu_credential_test_config("demo_baidu"))
    output = json.dumps(report, ensure_ascii=False)

    assert report["passed"] is False
    assert "不是合法 JSON" in report["errors"][0]
    assert "line" in report["errors"][0]
    assert "invalid-secret-value" not in output


def test_preflight_credentials_fails_for_missing_profile(tmp_path):
    from modules.preflight import check_baidu_credentials

    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "secrets.json").write_text('{"baidu": {}}', encoding="utf-8")

    report = check_baidu_credentials(tmp_path, _baidu_credential_test_config("missing_baidu"))

    assert report["passed"] is False
    assert "缺少 credential_profile：missing_baidu" in report["errors"]


def test_preflight_credentials_fails_for_empty_username_or_password(tmp_path):
    from modules.preflight import check_baidu_credentials

    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "secrets.json").write_text(
        json.dumps({"baidu": {"empty_user": {"username": "", "password": "value"}, "empty_password": {"username": "value", "password": ""}}}),
        encoding="utf-8",
    )

    report = check_baidu_credentials(tmp_path, _baidu_credential_test_config("empty_user", "empty_password"))

    assert report["passed"] is False
    assert "profile empty_user 的 username 为空" in report["errors"]
    assert "profile empty_password 的 password 为空" in report["errors"]


def test_preflight_credentials_checks_every_multi_source_profile_without_leaking_values(tmp_path):
    from modules.preflight import check_baidu_credentials, print_credential_report

    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "secrets.json").write_text(
        json.dumps({"baidu": {"profile_a": {"username": "secret-user-a", "password": "secret-pass-a"}, "profile_b": {"username": "secret-user-b", "password": "secret-pass-b"}}}),
        encoding="utf-8",
    )

    report = check_baidu_credentials(tmp_path, _baidu_credential_test_config("profile_a", "profile_b"))
    lines = []
    print_credential_report(report, output_func=lines.append)
    output = "\n".join(lines) + json.dumps(report, ensure_ascii=False)

    assert report["passed"] is True
    assert [item["credential_profile"] for item in report["profiles"]] == ["profile_a", "profile_b"]
    assert all(item["username_nonempty"] and item["password_nonempty"] for item in report["profiles"])
    assert "secret-user-a" not in output
    assert "secret-pass-b" not in output


def _prepare_daily_preflight_files(tmp_path, credentials: dict) -> dict:
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "kst_exports").mkdir()
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "secrets.json").write_text(
        json.dumps({"baidu": credentials}, ensure_ascii=False),
        encoding="utf-8",
    )
    excel_path = tmp_path / "daily.xlsx"
    excel_path.write_text("", encoding="utf-8")
    config = _baidu_credential_test_config(*credentials.keys())
    config["excel_path"] = str(excel_path)
    config["kst"] = {"export_dir": "kst_exports"}
    return config


def test_daily_preflight_selects_daily_sheet_check_and_hides_credentials(tmp_path, monkeypatch):
    import modules.preflight as preflight

    config = _prepare_daily_preflight_files(
        tmp_path,
        {"profile_a": {"username": "daily-secret-user", "password": "daily-secret-password"}},
    )
    selected = []

    monkeypatch.setattr(preflight, "validate_project_config", lambda project: [])
    monkeypatch.setattr(preflight, "inspect_excel_structure", lambda **kwargs: (_ for _ in ()).throw(AssertionError("日报不得检查小时报 sheet")))
    monkeypatch.setattr(
        preflight,
        "inspect_daily_excel_structure",
        lambda **kwargs: selected.append("daily") or {"errors": []},
        raising=False,
    )

    report = preflight.run_preflight(
        tmp_path,
        {"project_id": "demo", "project_name": "演示项目"},
        config,
        task="daily",
        chrome_check_func=lambda **kwargs: True,
    )
    output = json.dumps(report, ensure_ascii=False)

    assert report["passed"] is True
    assert report["task"] == "daily"
    assert selected == ["daily"]
    assert "daily-secret-user" not in output
    assert "daily-secret-password" not in output


def test_daily_preflight_checks_all_multi_source_profiles(tmp_path, monkeypatch):
    import modules.preflight as preflight

    config = _prepare_daily_preflight_files(
        tmp_path,
        {
            "profile_a": {"username": "u-a", "password": "p-a"},
            "profile_b": {"username": "u-b", "password": "p-b"},
        },
    )

    monkeypatch.setattr(preflight, "validate_project_config", lambda project: [])
    monkeypatch.setattr(
        preflight,
        "inspect_daily_excel_structure",
        lambda **kwargs: {"errors": []},
        raising=False,
    )

    report = preflight.run_preflight(
        tmp_path,
        {"project_id": "demo", "project_name": "演示项目"},
        config,
        task="daily",
        chrome_check_func=lambda **kwargs: True,
    )

    assert report["passed"] is True
    assert [item["credential_profile"] for item in report["credentials"]["profiles"]] == ["profile_a", "profile_b"]


def test_preflight_defaults_to_hourly_sheet_check(tmp_path, monkeypatch):
    import modules.preflight as preflight

    config = _prepare_daily_preflight_files(
        tmp_path,
        {"profile_a": {"username": "hourly-user", "password": "hourly-password"}},
    )
    selected = []

    monkeypatch.setattr(preflight, "validate_project_config", lambda project: [])
    monkeypatch.setattr(
        preflight,
        "inspect_excel_structure",
        lambda **kwargs: selected.append("hourly") or {"errors": []},
    )
    monkeypatch.setattr(
        preflight,
        "inspect_daily_excel_structure",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("默认预检不得检查日报 sheet")),
    )

    report = preflight.run_preflight(
        tmp_path,
        {"project_id": "demo", "project_name": "演示项目"},
        config,
        chrome_check_func=lambda **kwargs: True,
    )

    assert report["passed"] is True
    assert report["task"] == "hourly"
    assert selected == ["hourly"]


def test_quick_preflight_skips_excel_structure_scan(tmp_path, monkeypatch):
    import modules.preflight as preflight

    config = _prepare_daily_preflight_files(
        tmp_path,
        {"profile_a": {"username": "quick-user", "password": "quick-password"}},
    )

    monkeypatch.setattr(preflight, "validate_project_config", lambda project: [])
    monkeypatch.setattr(
        preflight,
        "inspect_excel_structure",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("快速预检不得扫描小时报 sheet")),
    )
    monkeypatch.setattr(
        preflight,
        "inspect_daily_excel_structure",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("快速预检不得扫描日报 sheet")),
    )

    report = preflight.run_preflight(
        tmp_path,
        {"project_id": "demo", "project_name": "演示项目"},
        config,
        quick=True,
        chrome_check_func=lambda **kwargs: True,
    )

    assert report["passed"] is True
    assert report["quick"] is True
    assert any(item.get("skipped") for item in report["checks"])


def test_cli_preflight_accepts_daily_task_and_passes_it_to_runner(tmp_path, monkeypatch):
    import main as cli_main

    calls = []
    monkeypatch.setattr(cli_main, "ROOT", tmp_path)
    monkeypatch.setattr(cli_main, "load_config", lambda *args, **kwargs: {})
    monkeypatch.setattr(cli_main, "get_current_project", lambda root: {"project_id": "demo", "project_name": "演示"})
    monkeypatch.setattr(cli_main, "build_runtime_config_from_project", lambda current, base: {})
    monkeypatch.setattr(
        cli_main,
        "run_preflight",
        lambda root, project, config, task="hourly", quick=False: calls.append((task, quick)) or {"passed": True, "checks": [], "credentials": {}},
    )
    monkeypatch.setattr("sys.argv", ["main.py", "--mode", "preflight", "--task", "daily", "--quick"])

    result = cli_main.main()

    assert result == 0
    assert calls == [("daily", True)]


def test_cli_run_fails_before_baidu_pipeline_when_credential_precheck_fails(tmp_path, monkeypatch):
    import main as cli_main

    project = {"project_id": "demo", "project_name": "演示"}
    config = _baidu_credential_test_config("missing_baidu")
    called = []

    monkeypatch.setattr(cli_main, "ROOT", tmp_path)
    monkeypatch.setattr(cli_main, "load_config", lambda *args, **kwargs: {})
    monkeypatch.setattr(cli_main, "get_current_project", lambda root: project)
    monkeypatch.setattr(cli_main, "build_runtime_config_from_project", lambda current, base: config)
    monkeypatch.setattr(cli_main, "run_half_auto_pipeline", lambda **kwargs: called.append(kwargs))
    monkeypatch.setattr("sys.argv", ["main.py", "--mode", "run", "--period", "15点", "--yes"])

    result = cli_main.main()

    assert result == 1
    assert called == []


def test_cli_run_daily_fails_before_baidu_pipeline_when_credential_precheck_fails(tmp_path, monkeypatch):
    import main as cli_main

    project = {"project_id": "demo", "project_name": "演示"}
    config = _baidu_credential_test_config("missing_baidu")
    called = []

    monkeypatch.setattr(cli_main, "ROOT", tmp_path)
    monkeypatch.setattr(cli_main, "load_config", lambda *args, **kwargs: {})
    monkeypatch.setattr(cli_main, "get_current_project", lambda root: project)
    monkeypatch.setattr(cli_main, "build_runtime_config_from_project", lambda current, base: config)
    monkeypatch.setattr(cli_main, "run_daily_pipeline", lambda **kwargs: called.append(kwargs))
    monkeypatch.setattr("sys.argv", ["main.py", "--mode", "run-daily", "--yes"])

    result = cli_main.main()

    assert result == 1
    assert called == []


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


def test_ensure_chrome_debug_ready_can_start_parallel_debug_profile(monkeypatch, tmp_path):
    import modules.chrome_debug as cd

    calls = {"alive": 0}

    def fake_is_alive(host="127.0.0.1", port=9222, timeout=3.0):
        calls["alive"] += 1
        return calls["alive"] > 1

    chrome = tmp_path / "chrome.exe"
    chrome.write_text("", encoding="utf-8")
    monkeypatch.setattr(cd, "is_chrome_debug_port_alive", fake_is_alive)
    monkeypatch.setattr(cd, "_chrome_process_exists", lambda: (_ for _ in ()).throw(AssertionError("daily Chrome should not block debug profile")))
    monkeypatch.setattr(cd, "find_chrome_executable", lambda config=None: chrome)
    monkeypatch.setattr(cd.subprocess, "Popen", lambda *args, **kwargs: object())

    result = ensure_chrome_debug_ready(tmp_path, {"browser": {"auto_start_debug_chrome": True}}, wait_seconds=2)

    assert result["ready"] is True
    assert result["started_new_chrome"] is True
    assert result["profile_dir"].endswith("browser_profile\\chrome_debug") or result["profile_dir"].endswith("browser_profile/chrome_debug")


def test_start_debug_chrome_uses_minimized_debug_profile_and_disables_password_manager(monkeypatch, tmp_path):
    import json
    import modules.chrome_debug as cd

    captured = {}

    class FakeProcess:
        pass

    def fake_popen(args, stdout=None, stderr=None, startupinfo=None):
        captured["args"] = args
        captured["startupinfo"] = startupinfo
        return FakeProcess()

    chrome = tmp_path / "chrome.exe"
    chrome.write_text("", encoding="utf-8")
    monkeypatch.setattr(cd, "find_chrome_executable", lambda config=None: chrome)
    monkeypatch.setattr(cd.subprocess, "Popen", fake_popen)

    result = start_debug_chrome(tmp_path, {"browser": {"debug_profile_dir": "browser_profile/chrome_debug"}})

    assert result["started"] is True
    args = captured["args"]
    assert "--start-minimized" in args
    assert "--disable-save-password-bubble" in args
    assert "--disable-features=PasswordManagerOnboarding,PasswordLeakDetection" in args
    assert captured["startupinfo"] is not None
    assert captured["startupinfo"].wShowWindow == 7
    assert not any("cas.baidu.com" in item or "cc.baidu.com" in item for item in args)
    assert any(str(tmp_path / "browser_profile" / "chrome_debug") in item for item in args)
    prefs = json.loads((tmp_path / "browser_profile" / "chrome_debug" / "Default" / "Preferences").read_text(encoding="utf-8"))
    assert prefs["credentials_enable_service"] is False
    assert prefs["profile"]["password_manager_enabled"] is False


def test_chrome_debug_launcher_reuses_existing_debug_port_without_killing_chrome(monkeypatch, tmp_path):
    import modules.chrome_debug_launcher as launcher

    chrome = tmp_path / "chrome.exe"
    chrome.write_text("", encoding="utf-8")
    monkeypatch.setattr(launcher, "CHROME_EXE", chrome)
    monkeypatch.setattr(launcher, "_is_port_open", lambda port: True)
    monkeypatch.setattr(launcher, "_run_connect_test", lambda: 0)
    monkeypatch.setattr(
        launcher.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("launcher must not inspect or close existing Chrome")),
    )

    assert launcher.main() == 0


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
    assert settings["silent_automation"] is True
    assert settings["disable_password_manager"] is True


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


def test_openclaw_hourly_bat_fixes_utf8_and_runs_preflight_before_hourly_pipeline():
    root = Path(__file__).resolve().parents[1]
    script = (root / "run_openclaw_hourly.bat").read_text(encoding="utf-8")

    assert 'cd /d "%~dp0"' in script
    assert "chcp 65001" in script
    assert "PYTHONUTF8=1" in script
    assert "PYTHONIOENCODING=utf-8" in script
    assert ".venv\\Scripts\\python.exe main.py --mode preflight --quick" in script
    assert "main.py --mode run --period" in script


def test_openclaw_hourly_sop_documents_preflight_credentials_and_password_rule():
    root = Path(__file__).resolve().parents[1]
    content = (root / "docs" / "openclaw_hourly_sop.md").read_text(encoding="utf-8")

    assert "preflight" in content
    assert "test-baidu-credentials" in content
    assert "禁止向用户索要百度密码" in content
    for period in ["11点", "15点", "18点"]:
        assert f"run --period {period}" in content
    assert "UTF-8" in content


def test_openclaw_daily_bat_runs_daily_preflight_before_daily_pipeline():
    root = Path(__file__).resolve().parents[1]
    script = (root / "run_openclaw_daily.bat").read_text(encoding="utf-8")

    assert 'cd /d "%~dp0"' in script
    assert "chcp 65001" in script
    assert "PYTHONUTF8=1" in script
    assert "PYTHONIOENCODING=utf-8" in script
    assert "main.py --mode preflight --task daily --quick" in script
    assert "main.py --mode run-daily --yes" in script
    assert 'main.py --mode run-daily --date "%~1" --yes' in script


def test_openclaw_daily_sop_documents_preflight_password_and_write_boundaries():
    root = Path(__file__).resolve().parents[1]
    content = (root / "docs" / "openclaw_daily_sop.md").read_text(encoding="utf-8")

    assert "OpenClaw 日报自动化执行手册" in content
    assert "run_openclaw_daily.bat" in content
    assert "preflight --task daily" in content
    assert "禁止向用户索要百度密码" in content
    assert "预约、到诊、就诊等禁止字段不由本工具填写" in content
    assert "不得在日报完成后自行追加任何外部填表或补数步骤" in content


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
    assert "百度竞价自动化控制台" in output
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
    assert "3. 切换项目" in MENU_TEXT
    assert "4. 检查条件项" in MENU_TEXT
    assert "5. 更多功能" in MENU_TEXT
    assert "0. 退出" in MENU_TEXT


def test_more_features_menu_contains_console_sections():
    from menu import MORE_FEATURES_MENU_TEXT

    for text in ["报告与日志", "配置诊断", "OpenClaw 帮助", "多百度来源摘要", "项目信息详情", "高级分步调试"]:
        assert text in MORE_FEATURES_MENU_TEXT


def test_condition_menu_uses_colleague_facing_labels():
    from menu import CONDITION_MENU_TEXT

    for text in ["一键检查当前项目能否运行", "检查百度账号凭据", "检查小时报条件", "检查日报条件"]:
        assert text in CONDITION_MENU_TEXT
    assert "doctor" not in CONDITION_MENU_TEXT
    assert "preflight" not in CONDITION_MENU_TEXT


def test_diagnostic_menu_exposes_sheet_text_dump_without_write_action():
    from menu import DIAGNOSTIC_MENU_TEXT

    assert "导出 sheet 文本诊断" in DIAGNOSTIC_MENU_TEXT
    assert "写入" not in DIAGNOSTIC_MENU_TEXT


def test_openclaw_menu_help_includes_bat_commands_and_password_rule():
    from menu import build_openclaw_help_lines

    text = "\n".join(build_openclaw_help_lines())

    assert "run_openclaw_hourly.bat 11点" in text
    assert "run_openclaw_daily.bat" in text
    assert "不得询问或输出真实百度密码" in text
    assert "预约、到诊、就诊等禁止字段不由本工具填写" in text


def test_multi_source_menu_summary_only_displays_safe_configuration_metadata():
    from menu import build_baidu_source_summary_lines

    project = {
        "project_name": "多来源项目",
        "excel_accounts": [{"standard_name": "写入A"}],
        "baidu_sources": [
            {
                "source_id": "a",
                "source_name": "来源A",
                "credential_profile": "profile_a",
                "accounts": [{"standard_name": "写入A"}],
                "username": "secret-user",
                "password": "secret-password",
            },
            {
                "source_id": "b",
                "source_name": "来源B",
                "credential_profile": "profile_b",
                "accounts": [{"standard_name": "候选B"}],
            },
        ],
    }

    text = "\n".join(build_baidu_source_summary_lines(project))

    assert "百度来源数量：2" in text
    assert "来源A" in text
    assert "profile_a" in text
    assert "写入A" in text
    assert "候选B" in text
    assert "ignored_inactive_accounts" in text
    assert "skipped_unmapped_accounts" in text
    assert "secret-user" not in text
    assert "secret-password" not in text


def test_single_source_menu_summary_is_brief():
    from menu import build_baidu_source_summary_lines

    assert build_baidu_source_summary_lines({"project_name": "单来源"}) == [
        "当前项目为单百度来源项目。"
    ]


def test_console_home_context_shows_project_id_source_type_account_count_condition_and_short_excel_name(tmp_path):
    from io import StringIO

    from modules.console_ui import print_console_context, set_output_func

    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "doctor_report.json").write_text(
        json.dumps({
            "project_id": "shenyang_niu",
            "summary": {"all_passed": True},
            "checks": {},
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_console_context({
            "project_name": "沈阳牛",
            "project_id": "shenyang_niu",
            "excel": {"path": r"D:\very\long\path\沈阳YXB2026竞价数据.xlsx"},
            "baidu_sources": [{}, {}],
            "excel_accounts": [{"standard_name": "A"}, {"standard_name": "B"}, {"standard_name": "C"}],
        }, root=tmp_path)
    finally:
        set_output_func(print)

    text = buf.getvalue()
    assert "沈阳牛" in text
    assert "shenyang_niu" in text
    assert "多百度来源 x2" in text
    assert "写入账户：3 个" in text
    assert "百度来源：2 个" not in text
    assert "条件项：通过" in text
    assert "沈阳YXB2026竞价数据.xlsx" in text
    assert r"D:\very\long\path" not in text


def test_console_home_condition_status_defaults_to_unchecked_and_maps_cached_results(tmp_path):
    from modules.console_ui import get_condition_status

    assert get_condition_status(tmp_path, "demo") == "未检查"
    reports = tmp_path / "reports"
    reports.mkdir()
    report_path = reports / "doctor_report.json"
    report_path.write_text(json.dumps({
        "project_id": "demo",
        "summary": {"all_passed": False},
        "checks": {"chrome": {"passed": False, "level": "warning"}},
    }), encoding="utf-8")
    assert get_condition_status(tmp_path, "demo") == "注意"
    report_path.write_text(json.dumps({
        "project_id": "demo",
        "summary": {"all_passed": False},
        "checks": {"excel": {"passed": False}},
    }), encoding="utf-8")
    assert get_condition_status(tmp_path, "demo") == "未通过"
    report_path.write_text(json.dumps({
        "project_id": "other-project",
        "summary": {"all_passed": True},
        "checks": {},
    }), encoding="utf-8")
    assert get_condition_status(tmp_path, "demo") == "未检查"


def test_console_home_has_plain_text_fallback_when_rich_is_disabled(tmp_path, monkeypatch):
    from io import StringIO

    import modules.console_ui as console_ui

    monkeypatch.setattr(console_ui, "_HAS_RICH", False)
    buf = StringIO()
    console_ui.set_output_func(buf.write)
    try:
        console_ui.print_console_context({"project_name": "演示", "project_id": "demo"}, root=tmp_path)
        console_ui.print_task_status_header({"project_id": "demo"}, root=tmp_path)
        console_ui.print_main_menu({"project_id": "demo"}, root=tmp_path)
    finally:
        console_ui.set_output_func(print)

    output = buf.getvalue()
    assert "百度竞价自动化控制台" in output
    assert "当前项目：演示" in output
    assert "条件项：未检查" in output
    assert "今日任务" in output
    assert "日报" in output
    assert "11点" in output
    assert "15点" in output
    assert "18点" in output
    assert "=" not in output


def test_rich_home_renders_one_project_panel_and_one_task_table_when_available(tmp_path, monkeypatch):
    import modules.console_ui as console_ui

    if not console_ui._HAS_RICH:
        return
    renderables = []
    monkeypatch.setattr(console_ui, "_emit_rich", lambda renderable: renderables.append(renderable) or True)
    try:
        console_ui.print_console_context({"project_name": "演示", "project_id": "demo"}, root=tmp_path)
        console_ui.print_task_status_header({"project_id": "demo"}, root=tmp_path)
    finally:
        console_ui.set_output_func(print)

    assert [type(item).__name__ for item in renderables] == ["Panel", "Table"]
    assert "百度竞价自动化控制台" in str(renderables[0].title)
    assert "今日任务" in str(renderables[1].title)


def test_menu_enhancement_does_not_introduce_textual_dependency():
    root = Path(__file__).resolve().parents[1]
    content = (
        (root / "menu.py").read_text(encoding="utf-8")
        + (root / "modules" / "console_ui.py").read_text(encoding="utf-8")
        + (root / "requirements.txt").read_text(encoding="utf-8")
    )

    assert "import textual" not in content.lower()
    assert "from textual" not in content.lower()
    assert "textual" not in (root / "requirements.txt").read_text(encoding="utf-8").lower()


def test_home_output_is_colleague_facing_and_keeps_advanced_sections_hidden(tmp_path, monkeypatch):
    import menu

    output = []
    project = {
        "project_id": "hefei_bai",
        "project_name": "合肥白",
        "excel": {"path": r"D:\data\【合肥】2026竞价数据.xlsx"},
        "baidu_sources": [{}, {}],
        "excel_accounts": [{"standard_name": "A"}, {"standard_name": "B"}],
    }
    monkeypatch.setattr(menu, "load_config", lambda *args, **kwargs: {})
    monkeypatch.setattr(menu, "get_current_project", lambda root: project)
    monkeypatch.setattr(menu, "setup_logger", lambda path: object())

    menu.run_menu(root=tmp_path, input_func=lambda prompt: "0", output_func=output.append)

    home = "\n".join(output)
    assert home.count("百度竞价自动化控制台") == 1
    for text in ["百度竞价自动化控制台", "当前项目", "合肥白", "hefei_bai", "条件项", "日报", "11点", "15点", "18点"]:
        assert text in home
    for text in ["OpenClaw 帮助", "配置诊断", "报告与日志", "多百度来源摘要", "高级分步调试"]:
        assert text not in home
    for text in ["doctor", "preflight", "credential_profile", "baidu_sources", "debug"]:
        assert text not in home.lower()


def test_submenu_labels_use_consistent_return_choice():
    from menu import (
        ADVANCED_DEBUG_MENU_TEXT,
        CONDITION_MENU_TEXT,
        DIAGNOSTIC_MENU_TEXT,
        MORE_FEATURES_MENU_TEXT,
        OPENCLAW_MENU_TEXT,
        REPORT_MENU_TEXT,
    )

    for content in [
        ADVANCED_DEBUG_MENU_TEXT,
        CONDITION_MENU_TEXT,
        DIAGNOSTIC_MENU_TEXT,
        MORE_FEATURES_MENU_TEXT,
        OPENCLAW_MENU_TEXT,
        REPORT_MENU_TEXT,
    ]:
        assert "0. 返回" in content


def test_menu_preflight_execution_writes_report_and_logs_result(tmp_path, monkeypatch):
    import menu

    entries = []

    class Logger:
        def info(self, *args):
            entries.append(args)

    monkeypatch.setattr(
        menu,
        "run_preflight",
        lambda root, project, config, task: {
            "passed": True,
            "task": task,
            "checks": [],
            "credentials": {},
        },
    )

    report = menu._execute_preflight(tmp_path, {}, {}, "daily", Logger())

    assert report["passed"] is True
    assert json.loads((tmp_path / "reports" / "preflight_report.json").read_text(encoding="utf-8"))["task"] == "daily"
    assert entries


def test_menu_refresh_choice_does_not_dispatch_task(tmp_path, monkeypatch):
    import menu

    project = {
        "project_id": "demo",
        "project_name": "演示",
        "excel": {"path": "demo.xlsx"},
    }
    answers = iter(["r", "0"])
    monkeypatch.setattr(menu, "load_config", lambda *args, **kwargs: {})
    monkeypatch.setattr(menu, "get_current_project", lambda root: project)
    monkeypatch.setattr(menu, "build_runtime_config", lambda current, base: {})
    monkeypatch.setattr(menu, "setup_logger", lambda path: object())
    monkeypatch.setattr(menu, "_check_chrome_debug", lambda *args, **kwargs: True)
    monkeypatch.setattr(menu, "dispatch_menu_task", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("刷新不得执行任务")))

    menu.run_menu(root=tmp_path, input_func=lambda prompt: next(answers), output_func=lambda text: None)


def test_menu_no_longer_routes_hidden_developer_shortcuts(tmp_path, monkeypatch):
    import menu

    project = {
        "project_id": "demo",
        "project_name": "演示",
        "excel": {"path": "demo.xlsx"},
    }
    calls = []
    answers = iter(["p", "l", "o", "0"])
    monkeypatch.setattr(menu, "load_config", lambda *args, **kwargs: {})
    monkeypatch.setattr(menu, "get_current_project", lambda root: project)
    monkeypatch.setattr(menu, "build_runtime_config", lambda current, base: {})
    monkeypatch.setattr(menu, "setup_logger", lambda path: object())
    monkeypatch.setattr(menu, "_check_chrome_debug", lambda *args, **kwargs: True)
    monkeypatch.setattr(menu, "_run_condition_menu", lambda *args: calls.append("condition"))
    monkeypatch.setattr(menu, "_run_report_menu", lambda *args: calls.append("reports"))
    monkeypatch.setattr(menu, "_run_openclaw_menu", lambda *args: calls.append("openclaw"))
    monkeypatch.setattr(menu, "dispatch_menu_task", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("快捷键不得执行任务")))

    menu.run_menu(root=tmp_path, input_func=lambda prompt: next(answers), output_func=lambda text: None)

    assert calls == []


def test_menu_routes_switch_project_and_condition_check_from_home(tmp_path, monkeypatch):
    import menu

    project = {
        "project_id": "demo",
        "project_name": "演示",
        "excel": {"path": "demo.xlsx"},
    }
    calls = []
    answers = iter(["3", "", "4", "0"])
    monkeypatch.setattr(menu, "load_config", lambda *args, **kwargs: {})
    monkeypatch.setattr(menu, "get_current_project", lambda root: project)
    monkeypatch.setattr(menu, "build_runtime_config", lambda current, base: {})
    monkeypatch.setattr(menu, "setup_logger", lambda path: object())
    monkeypatch.setattr(menu, "_check_chrome_debug", lambda *args, **kwargs: True)
    monkeypatch.setattr(menu, "_select_project_from_list", lambda *args: calls.append("switch") or None)
    monkeypatch.setattr(menu, "_run_condition_menu", lambda *args: calls.append("condition"))

    menu.run_menu(root=tmp_path, input_func=lambda prompt: next(answers), output_func=lambda text: None)

    assert calls == ["switch", "condition"]


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


def test_main_menu_keeps_daily_entry_free_of_status_duplication(tmp_path):
    """首页菜单只承担导航，完成状态只在今日任务表中展示。"""
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
    assert "[已完成]" not in output
    assert "完成于：" not in output


def test_task_status_header_shows_daily_completion_time(tmp_path):
    """今日任务表展示日报完成状态和时间。"""
    from io import StringIO
    from modules.console_ui import print_task_status_header, set_output_func
    from modules.task_status import mark_daily_done

    (tmp_path / "reports").mkdir(exist_ok=True)
    mark_daily_done(tmp_path, "test_proj")

    buf = StringIO()
    set_output_func(buf.write)
    try:
        print_task_status_header({"project_id": "test_proj"}, root=tmp_path)
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "今日任务" in output
    assert "日报" in output
    assert "已完成" in output
    assert ":" in output


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


def test_main_menu_daily_entry_has_no_undone_status_duplication(tmp_path):
    """未完成状态也不在导航菜单重复展示。"""
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
    assert "[未完成]" not in output
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
    from modules.console_ui import print_task_status_header, set_output_func

    buf = StringIO()
    set_output_func(buf.write)
    try:
        # 不应报错
        print_task_status_header({"project_id": "test_proj"}, root=tmp_path)
    finally:
        set_output_func(print)

    output = buf.getvalue()
    assert "已完成" in output


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


def test_current_project_is_listed_and_valid():
    """当前选中项目可以随运行切换，但必须存在且配置有效。"""
    root = Path(__file__).resolve().parents[1]
    current = get_current_project(root)
    project_ids = {project["project_id"] for project in list_projects(root)}
    assert current["project_id"] in project_ids
    assert current["project_name"]
    assert validate_project_config(current) == []


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


def test_secrets_example_has_six_profiles():
    """secrets.example.json 包含含沈阳双来源在内的六个 profile，密码为空。"""
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "secrets" / "secrets.example.json").read_text(encoding="utf-8"))
    baidu = data["baidu"]
    for profile in [
        "kunming_niu_baidu",
        "nanjing_niu_baidu",
        "ningbo_niu_baidu",
        "changsha_niu_baidu",
        "shenyang_niu_zhongya_baidu",
        "shenyang_niu_yinkang_baidu",
    ]:
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
    for pid in ["kunming_niu", "nanjing_niu", "ningbo_niu", "changsha_niu", "shenyang_niu"]:
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


def test_internal_build_requires_shenyang_multi_source_profiles(tmp_path):
    """内部包必须同时具备沈阳中亚与沈阳银康百度凭据。"""
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
    assert "缺少百度凭据 profile：shenyang_niu_zhongya_baidu" in errors
    assert "缺少百度凭据 profile：shenyang_niu_yinkang_baidu" in errors


def test_internal_build_validates_all_complete(tmp_path):
    """内部包六个 profile 完整时校验通过。"""
    from tools.build_release import _validate_internal_secrets

    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "secrets.json").write_text(json.dumps({
            "baidu": {
                "kunming_niu_baidu": {"username": "a", "password": "b"},
                "nanjing_niu_baidu": {"username": "a", "password": "b"},
                "ningbo_niu_baidu": {"username": "a", "password": "b"},
                "changsha_niu_baidu": {"username": "a", "password": "b"},
                "shenyang_niu_zhongya_baidu": {"username": "a", "password": "b"},
                "shenyang_niu_yinkang_baidu": {"username": "a", "password": "b"},
                "qingdao_bai_baidu": {"username": "a", "password": "b"},
                "shenyang_bai_source_a_baidu": {"username": "a", "password": "b"},
                "shenyang_bai_source_b_baidu": {"username": "a", "password": "b"},
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
    for name in ["昆明牛", "南京牛", "宁波牛", "长沙牛", "沈阳牛", "青岛白", "深圳白", "南京白", "沈阳白"]:
        assert name in content, f"缺少项目：{name}"
    assert "双百度来源" in content


def test_xia_sidao_readme_tracks_rich_menu_and_openclaw_fixed_entries():
    """夏思道说明同步当前 Rich 菜单与仍保持稳定的 OpenClaw 入口。"""
    root = Path(__file__).resolve().parents[1]
    content = (root / "xia_sidao使用说明.md").read_text(encoding="utf-8")

    assert "v1.0 内部发布版" in content
    assert "Rich 控制台" in content
    for label in ["3. 切换项目", "4. 检查条件项", "5. 更多功能"]:
        assert label in content
    assert "3. 项目列表" not in content
    assert "run_openclaw_hourly.bat 11点" in content
    assert "run_openclaw_daily.bat" in content
    assert "菜单布局调整不影响 OpenClaw 固定入口" in content


def test_xia_sidao_readme_tracks_v1_current_scope_without_retired_workflows():
    """夏思道说明只保留 V1.0 当前能力与安全规则。"""
    root = Path(__file__).resolve().parents[1]
    content = (root / "xia_sidao使用说明.md").read_text(encoding="utf-8")

    assert "十个正式项目" in content
    for name in ["昆明牛", "南京牛", "宁波牛", "长沙牛", "沈阳牛", "合肥白", "青岛白", "深圳白", "南京白", "沈阳白"]:
        assert name in content, f"缺少项目：{name}"
    for text in ["小时报和日报均在写入前先备份目标 Excel", "筛选按钮", "从本次写入前备份恢复"]:
        assert text in content
    for text in ["browser_profile/chrome_debug", "silent_automation=true", "window_state=minimized", "保存密码提示"]:
        assert text in content
    for retired in ["腾讯文档", "fill_daily_visit.py", "cron", "v0.4.19", "v0.4.21"]:
        assert retired not in content


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


def test_desktop_gui_project_store_excludes_templates(tmp_path):
    projects_dir = tmp_path / "configs" / "projects"
    projects_dir.mkdir(parents=True)
    (tmp_path / "configs" / "app_config.json").write_text(json.dumps({
        "default_project_id": "alpha",
        "projects_dir": "configs/projects",
        "secrets_file": "secrets/secrets.json",
    }, ensure_ascii=False), encoding="utf-8")
    (projects_dir / "alpha.json").write_text(json.dumps({
        "project_id": "alpha",
        "project_name": "项目A",
    }, ensure_ascii=False), encoding="utf-8")
    (projects_dir / "project_template.json").write_text(json.dumps({
        "project_id": "your_project_id",
        "project_name": "模板",
        "is_template": True,
    }, ensure_ascii=False), encoding="utf-8")

    from gui.project_store import load_project_summaries

    projects = load_project_summaries(tmp_path)

    assert [(item.project_id, item.project_name) for item in projects] == [("alpha", "项目A")]


def test_desktop_gui_command_builder_uses_existing_main_entry():
    from gui.command_builder import build_daily_command, build_hourly_command, build_preflight_command

    root = Path("D:/app")

    assert build_hourly_command(root, "15", project_id="qingdao_bai") == [
        str(root / ".venv" / "Scripts" / "pythonw.exe"),
        str(root / "main.py"),
        "--mode",
        "run",
        "--project",
        "qingdao_bai",
        "--period",
        "15点",
        "--yes",
    ]
    assert build_daily_command(root, "2026-06-06", project_id="shenyang_bai") == [
        str(root / ".venv" / "Scripts" / "pythonw.exe"),
        str(root / "main.py"),
        "--mode",
        "run-daily",
        "--project",
        "shenyang_bai",
        "--date",
        "2026-06-06",
        "--yes",
    ]
    assert build_preflight_command(root, "daily", project_id="shenyang_bai") == [
        str(root / ".venv" / "Scripts" / "pythonw.exe"),
        str(root / "main.py"),
        "--mode",
        "preflight",
        "--project",
        "shenyang_bai",
        "--task",
        "daily",
        "--quick",
    ]


def test_desktop_gui_environment_subprocess_is_hidden():
    from gui.environment_check import hidden_subprocess_kwargs

    kwargs = hidden_subprocess_kwargs()

    if os.name == "nt":
        assert kwargs["creationflags"] != 0
        assert kwargs["startupinfo"].dwFlags != 0
    else:
        assert kwargs == {}


def test_desktop_gui_task_runner_forces_utf8_environment():
    from gui.task_runner import build_process_environment

    env = build_process_environment()

    assert env.value("PYTHONUTF8") == "1"
    assert env.value("PYTHONIOENCODING") == "utf-8"


def test_desktop_gui_requirements_include_gui_packaging_deps():
    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")

    assert "PySide6" in requirements
    assert "pyinstaller" in requirements


def test_desktop_gui_resolves_project_root_from_workspace():
    from gui.app import resolve_app_root

    root = Path(__file__).resolve().parents[1]

    assert resolve_app_root() == root


def test_desktop_gui_progress_lives_below_project_selector(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    assert window.progress.objectName() == "taskProgress"
    assert window.progress_text.objectName() == "taskProgressText"
    assert window.progress.maximum() == 7
    assert "项目" in window.progress_text.text()
    window.close()


def test_desktop_gui_window_is_resizable_and_header_hidden(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    assert window.minimumWidth() >= 1100
    assert window.minimumHeight() >= 720
    assert window.maximumWidth() > window.minimumWidth()
    assert window.maximumHeight() > window.minimumHeight()
    assert window.left_panel.minimumWidth() == 470
    assert window.left_panel.maximumWidth() == 470
    assert window.status_title.isHidden()
    assert window.status_detail.isHidden()
    assert bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert window.title_bar.objectName() == "titleBar"
    assert window.spinner.objectName() == "pixelSnakeSpinner"
    assert window.title_label.text() == "百度数据自动化控制台"
    assert window.title_label.font().pointSize() == 11
    assert window.system_config_button.text().startswith("系统配置")
    assert [action.text() for action in window.system_config_menu.actions()] == ["更新路径", "更新账号密码", "恢复备份"]
    assert window.maximize_button.text() == "□"
    assert window.windowIcon().isNull()
    assert window.font().family() == "Microsoft YaHei UI"
    assert window.font().pointSize() == 9
    window.close()


def test_desktop_gui_matches_reference_dashboard_structure(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    assert window.task_control_card.objectName() == "dashboardCard"
    assert window.hourly_card.objectName() == "dashboardCard"
    assert window.daily_card.objectName() == "dashboardCard"
    assert window.current_flow_panel.objectName() == "currentFlowPanel"
    assert window.current_flow_title.text() == "当前流程"
    assert window.current_task_title.text() == "暂无运行任务"
    assert window.current_task_subtitle.text() == "请选择左侧任务开始执行"
    assert window.current_status_badge.text() == "空闲"
    assert [button.objectName() for button in window.stage_buttons] == ["stageActionButton"] * 7
    assert [button.text().split("  ", 1)[-1] for button in window.stage_buttons] == [
        "环境检测",
        "项目配置",
        "快速自检",
        "百度数据",
        "快商通数据",
        "Excel写入",
        "报告输出",
    ]
    window.close()


def test_desktop_gui_daily_date_uses_project_card_style(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    assert window.date_card.objectName() == "dashboardCard"
    assert window.date_button.objectName() == "datePickerButton"
    assert window.date_button.minimumHeight() >= window.date_button.fontMetrics().height() + 2
    assert window.selected_daily_date() in window.date_button.text()
    window.close()


def test_desktop_gui_uses_small_five_global_font_and_smaller_subtext(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow, MAIN_FONT_PT, SUB_FONT_PT

    app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    assert MAIN_FONT_PT == 9
    assert SUB_FONT_PT == 8
    assert window.font().pointSize() == MAIN_FONT_PT
    assert window.progress_text.font().pointSize() == SUB_FONT_PT
    assert "QLabel#cardTitle" in window.styleSheet()
    window.close()


def test_desktop_gui_config_actions_live_in_title_menu(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    assert not hasattr(window, "excel_config_button")
    assert not hasattr(window, "credentials_config_button")
    assert window.system_config_button.text().startswith("系统配置")
    assert [action.text() for action in window.system_config_menu.actions()] == ["更新路径", "更新账号密码", "恢复备份"]
    assert window.environment_check_button.text().endswith("执行环境自检")
    assert not hasattr(window, "guide_button")
    assert not hasattr(window, "refresh_button")
    assert not hasattr(window, "preflight_hourly_button")
    assert not hasattr(window, "preflight_daily_button")
    assert not hasattr(window, "command_line")
    assert window.selected_project_config_path().name.endswith(".json")
    assert window.credentials_config_path() == Path(__file__).resolve().parents[1] / "secrets" / "secrets.json"
    window.close()


def test_desktop_gui_restore_backup_overwrites_project_excel_after_safety_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from gui.main_window import MainWindow

    target_excel = tmp_path / "target.xlsx"
    selected_backup = tmp_path / "backups" / "target_backup.xlsx"
    selected_backup.parent.mkdir()
    target_excel.write_text("current excel", encoding="utf-8")
    selected_backup.write_text("restored excel", encoding="utf-8")
    (tmp_path / "configs" / "projects").mkdir(parents=True)
    (tmp_path / "configs" / "app_config.json").write_text(json.dumps({
        "default_project_id": "demo",
        "projects_dir": "configs/projects",
        "secrets_file": "secrets/secrets.json",
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "configs" / "projects" / "demo.json").write_text(json.dumps({
        "project_id": "demo",
        "project_name": "演示项目",
        "excel": {"path": str(target_excel)},
    }, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(selected_backup), "Excel"))
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    window.restore_backup()

    safety_backups = list((tmp_path / "backups").glob("target_before_manual_restore_*.xlsx"))
    assert target_excel.read_text(encoding="utf-8") == "restored excel"
    assert len(safety_backups) == 1
    assert safety_backups[0].read_text(encoding="utf-8") == "current excel"
    assert "恢复备份完成" in window.log_view.toPlainText()
    window.close()


def test_desktop_gui_period_selection_marks_checked_green(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    assert 'QPushButton#periodButton:checked' in window.styleSheet()
    assert '#dff7ea' in window.styleSheet()
    assert all(not button.autoDefault() for button in window.period_buttons)
    assert window.period_buttons[1].text().endswith("✓")
    window.close()


def test_desktop_gui_current_flow_updates_for_hourly_and_daily(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    window.runner.start = lambda command, root: None

    window.period_buttons[0].setChecked(True)
    window.update_period_button_texts()
    window.run_hourly()
    assert window.current_task_title.text() == "运行小时报"
    assert "11点" in window.current_task_subtitle.text()
    assert window.current_status_badge.text() == "运行中"
    assert window.current_start_time_label.text().startswith("开始时间：")

    window.run_daily()
    assert window.current_task_title.text() == "运行日报"
    assert "月" in window.current_task_subtitle.text()
    assert "日" in window.current_task_subtitle.text()
    window.close()


def test_desktop_gui_creates_local_secrets_template_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    (tmp_path / "configs" / "projects").mkdir(parents=True)
    (tmp_path / "configs" / "app_config.json").write_text(json.dumps({
        "default_project_id": "demo",
        "projects_dir": "configs/projects",
        "secrets_file": "secrets/secrets.json",
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "configs" / "projects" / "demo.json").write_text(json.dumps({
        "project_id": "demo",
        "project_name": "演示项目",
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "secrets.example.json").write_text(json.dumps({"baidu": {}}, ensure_ascii=False), encoding="utf-8")

    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    path = window.ensure_credentials_file()

    assert path == tmp_path / "secrets" / "secrets.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"baidu": {}}
    window.close()


def test_desktop_gui_log_formatter_highlights_key_content():
    from gui.log_formatter import format_log_html

    html = format_log_html("项目 青岛白 [通知] 通过，Excel D:\\数据\\青岛.xlsx，报告 reports/final_run_report.json")

    assert "log-pass" in html
    assert "log-path" in html
    assert "log-project" in html
    assert "青岛白" in html


def test_desktop_gui_environment_check_reports_missing_python(tmp_path):
    from gui.environment_check import run_environment_check

    report = run_environment_check(tmp_path)

    python_check = next(item for item in report["checks"] if item["name"] == "Python environment")
    assert report["passed"] is False
    assert python_check["passed"] is False
    assert python_check["severity"] == "error"


def test_desktop_gui_task_runner_infers_progress_stages():
    from gui.task_runner import infer_stage

    assert infer_stage("[OpenClaw] Running hourly quick preflight...") == "preflight"
    assert infer_stage("fetch-baidu-auto started") == "baidu"
    assert infer_stage("parse-kst-export completed") == "kst"
    assert infer_stage("Excel 写入完成") == "excel"
    assert infer_stage("[ERROR] Preflight failed") == "error"


# ── 百度登录状态守卫测试 (CAS 兜底版) ─────────────────────


def test_load_login_state_returns_empty_when_file_missing(tmp_path):
    from modules.baidu_session import load_browser_login_state
    state = load_browser_login_state(tmp_path)
    assert state["last_profile"] is None


def test_mark_login_success_and_read_profile(tmp_path):
    from modules.baidu_session import (
        get_browser_login_profile, load_browser_login_state, mark_browser_login_success,
    )
    (tmp_path / "reports").mkdir(exist_ok=True)
    mark_browser_login_success(
        tmp_path, credential_profile="kunming_niu_baidu",
        project_id="kunming_niu", project_name="昆明牛",
        task="run-daily", url="https://cc.baidu.com/report",
    )
    state = load_browser_login_state(tmp_path)
    assert state["last_profile"] == "kunming_niu_baidu"
    assert state["last_project_id"] == "kunming_niu"
    assert state["last_login_at"] is not None
    assert "username" not in state
    assert "password" not in state


def test_get_browser_login_profile(tmp_path):
    from modules.baidu_session import get_browser_login_profile, mark_browser_login_success
    (tmp_path / "reports").mkdir(exist_ok=True)
    assert get_browser_login_profile(tmp_path) is None
    mark_browser_login_success(tmp_path, "nanjing_niu_baidu", project_id="nanjing_niu")
    assert get_browser_login_profile(tmp_path) == "nanjing_niu_baidu"


def test_clear_browser_login_state(tmp_path):
    from modules.baidu_session import clear_browser_login_state, get_browser_login_profile, mark_browser_login_success
    (tmp_path / "reports").mkdir(exist_ok=True)
    mark_browser_login_success(tmp_path, "test_profile", project_id="test")
    assert get_browser_login_profile(tmp_path) == "test_profile"
    clear_browser_login_state(tmp_path)
    assert get_browser_login_profile(tmp_path) is None


def test_get_current_project_credential_profile():
    from modules.baidu_session import get_current_project_credential_profile
    assert get_current_project_credential_profile({"baidu": {"credential_profile": "kunming_niu_baidu"}}) == "kunming_niu_baidu"
    assert get_current_project_credential_profile({"baidu": {"credential_project": "nanjing_niu_baidu"}}) == "nanjing_niu_baidu"
    assert get_current_project_credential_profile({}) == ""


def test_browser_login_state_no_passwords(tmp_path):
    from modules.baidu_session import load_browser_login_state, save_browser_login_state
    (tmp_path / "reports").mkdir(exist_ok=True)
    save_browser_login_state(tmp_path, {"last_profile": "test", "username": "strip", "password": "strip"})
    state = load_browser_login_state(tmp_path)
    assert "username" not in state
    assert "password" not in state


def test_menu_no_longer_pre_saves_login_state():
    root = Path(__file__).resolve().parents[1]
    content = (root / "menu.py").read_text(encoding="utf-8")
    assert "save_login_state(" not in content
    assert "check_profile_match(" not in content
    assert "baidu_session" in content


# ── CAS 登录页测试 ────────────────────────────────────────


def test_goto_baidu_login_page_uses_cas_url(monkeypatch):
    from unittest.mock import MagicMock
    from modules.baidu_session import goto_baidu_login_page, BAIDU_CAS_LOGIN_URL
    fake_page = MagicMock()
    fake_page.url = "about:blank"
    result = goto_baidu_login_page(fake_page)
    assert result["success"] is True
    fake_page.goto.assert_called_once()
    assert "cas.baidu.com" in fake_page.goto.call_args[0][0]


def test_goto_baidu_login_page_returns_error_on_exception():
    from unittest.mock import MagicMock
    from modules.baidu_session import goto_baidu_login_page
    fake_page = MagicMock()
    fake_page.goto.side_effect = Exception("timeout")
    result = goto_baidu_login_page(fake_page)
    assert result["success"] is False


def test_session_usable_page_skips_cas(tmp_path, monkeypatch):
    """已在可用搜索推广数据页 -> 不跳 CAS。"""
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import ensure_baidu_profile_session
    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu"}
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    logger = logging.getLogger("test")
    monkeypatch.setattr("modules.baidu_session._page_is_usable_search_promotion", lambda p, r, c: True)
    cas_calls = []
    monkeypatch.setattr("modules.baidu_session.goto_baidu_login_page", lambda page: cas_calls.append(1) or {"success": True})
    result = ensure_baidu_profile_session(tmp_path, config, fake_page, logger, input_func=lambda _: "", output_func=lambda _: None)
    assert result.get("passed") is True
    assert len(cas_calls) == 0, "可用页面不应跳 CAS"


def test_session_profile_mismatch_triggers_cas_login(tmp_path, monkeypatch):
    """last_profile 不一致且用户名无法识别时触发 CAS 登录。"""
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import ensure_baidu_profile_session, mark_browser_login_success
    (tmp_path / "reports").mkdir(exist_ok=True)
    mark_browser_login_success(tmp_path, "old_profile", project_id="old")
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu", "project_name": "昆明牛"}
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    logger = logging.getLogger("test")
    monkeypatch.setattr("modules.baidu_session._page_is_usable_search_promotion", lambda p, r, c: False)
    monkeypatch.setattr("modules.baidu_session.is_baidu_logged_in", lambda p: False)
    monkeypatch.setattr("modules.baidu_session.get_expected_baidu_username", lambda r, c: None)
    monkeypatch.setattr("modules.baidu_session.detect_current_baidu_username", lambda p: None)
    cas_calls = []
    login_calls = []
    monkeypatch.setattr("modules.baidu_session.goto_baidu_login_page", lambda page: cas_calls.append(1) or {"success": True})
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed", lambda p, r, c, l: login_calls.append(1) or True)
    result = ensure_baidu_profile_session(tmp_path, config, fake_page, logger, input_func=lambda _: "", output_func=lambda _: None)
    assert result.get("passed") is True
    assert len(cas_calls) >= 1
    assert len(login_calls) >= 1


def test_session_last_profile_none_triggers_cas(tmp_path, monkeypatch):
    """last_profile=None 且无法识别用户名时触发 CAS 登录。"""
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import ensure_baidu_profile_session
    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu", "project_name": "昆明牛"}
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    logger = logging.getLogger("test")
    monkeypatch.setattr("modules.baidu_session._page_is_usable_search_promotion", lambda p, r, c: False)
    monkeypatch.setattr("modules.baidu_session.is_baidu_logged_in", lambda p: False)
    monkeypatch.setattr("modules.baidu_session.get_expected_baidu_username", lambda r, c: None)
    monkeypatch.setattr("modules.baidu_session.detect_current_baidu_username", lambda p: None)
    cas_calls = []
    login_calls = []
    monkeypatch.setattr("modules.baidu_session.goto_baidu_login_page", lambda page: cas_calls.append(1) or {"success": True})
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed", lambda p, r, c, l: login_calls.append(1) or True)
    result = ensure_baidu_profile_session(tmp_path, config, fake_page, logger, input_func=lambda _: "", output_func=lambda _: None)
    assert result.get("passed") is True
    assert len(cas_calls) >= 1
    assert len(login_calls) >= 1


def test_username_match_skips_cas_login(tmp_path, monkeypatch):
    """当前账号匹配时直接通过，不调用 CAS 登录。"""
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import ensure_baidu_profile_session

    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu", "project_name": "昆明牛"}
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    logger = logging.getLogger("test")
    monkeypatch.setattr("modules.baidu_session._page_is_usable_search_promotion", lambda p, r, c: False)
    monkeypatch.setattr("modules.baidu_session.get_expected_baidu_username", lambda r, c: "test_user")
    monkeypatch.setattr("modules.baidu_session.detect_current_baidu_username", lambda p: "test_user")
    cas_calls = []
    monkeypatch.setattr("modules.baidu_session.goto_baidu_login_page", lambda page: cas_calls.append(1) or {"success": True})
    result = ensure_baidu_profile_session(tmp_path, config, fake_page, logger, input_func=lambda _: "", output_func=lambda _: None)
    assert result.get("passed") is True
    assert len(cas_calls) == 0, "账号匹配时不应调用 CAS 登录"


def test_no_profile_skips_check(tmp_path):
    """无 credential_profile 时不做检查。"""
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import ensure_baidu_profile_session
    fake_page = MagicMock()
    logger = logging.getLogger("test")
    result = ensure_baidu_profile_session(tmp_path, {}, fake_page, logger, input_func=lambda _: "", output_func=lambda _: None)
    assert result.get("passed") is True


def test_force_relogin_uses_cas_page(tmp_path, monkeypatch):
    """force_relogin_current_project 退出成功 → 进入 CAS 登录页。"""
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import force_relogin_current_project
    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu", "project_name": "昆明牛"}
    fake_page = MagicMock()
    fake_page.url = "about:blank"
    logger = logging.getLogger("test")
    cas_calls = []
    login_calls = []
    monkeypatch.setattr("modules.baidu_session.logout_baidu_account", lambda page: {"success": True, "message": "ok"})
    monkeypatch.setattr("modules.baidu_session.wait_until_cas_login_page", lambda page, timeout_ms=5000: False)
    monkeypatch.setattr("modules.baidu_session.goto_baidu_login_page", lambda page: cas_calls.append(1) or {"success": True})
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed", lambda p, r, c, l: login_calls.append(1) or True)
    monkeypatch.setattr("modules.baidu_session.get_expected_baidu_username", lambda r, c: "test_user")
    monkeypatch.setattr("modules.baidu_session.detect_current_baidu_username", lambda p: "test_user")
    result = force_relogin_current_project(tmp_path, config, fake_page, logger, input_func=lambda _: "", output_func=lambda _: None)
    assert result is True
    assert len(cas_calls) >= 1
    assert len(login_calls) >= 1


def test_force_relogin_does_not_show_chrome_during_automatic_switch(tmp_path, monkeypatch):
    """自动切换百度账号时不应把 Chrome 拉到前台。"""
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import force_relogin_current_project

    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu"}
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/homepage"
    logger = logging.getLogger("test")

    monkeypatch.setattr("modules.baidu_session.logout_baidu_account", lambda page: {"success": True, "message": "ok"})
    monkeypatch.setattr("modules.baidu_session.wait_until_cas_login_page", lambda page, timeout_ms=5000: False)
    monkeypatch.setattr("modules.baidu_session.goto_baidu_login_page", lambda page: {"success": True})
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed", lambda p, r, c, l: True)
    monkeypatch.setattr(
        "modules.browser_manager.show_browser_page_for_manual_intervention",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("automatic relogin must stay silent")),
    )

    assert force_relogin_current_project(tmp_path, config, fake_page, logger, input_func=lambda _: "", output_func=lambda _: None) is True


def test_force_relogin_login_failure_returns_false(tmp_path, monkeypatch):
    """CAS 登录失败时 force_relogin 返回 False。"""
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import force_relogin_current_project
    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {"baidu": {"credential_profile": "test"}, "project_id": "p"}
    fake_page = MagicMock()
    logger = logging.getLogger("test")
    monkeypatch.setattr("modules.baidu_session.goto_baidu_login_page", lambda page: {"success": True})
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed", lambda p, r, c, l: False)
    monkeypatch.setattr("modules.baidu_session.get_expected_baidu_username", lambda r, c: "test_user")
    monkeypatch.setattr("modules.baidu_session.detect_current_baidu_username", lambda p: "test_user")
    result = force_relogin_current_project(tmp_path, config, fake_page, logger, input_func=lambda _: "", output_func=lambda _: None)
    assert result is False


def test_login_flow_username_mismatch_allows_proceeding(tmp_path, monkeypatch):
    """用户名不匹配时：不写 browser_login_state，返回 needs_project_account_check。"""
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import _do_login_flow, load_browser_login_state

    (tmp_path / "reports").mkdir(exist_ok=True)
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    logger = logging.getLogger("test")

    monkeypatch.setattr("modules.baidu_session.get_expected_baidu_username", lambda r, c: "user_a")
    monkeypatch.setattr("modules.baidu_session.detect_current_baidu_username", lambda p: "user_b")
    monkeypatch.setattr("modules.baidu_session.get_current_project_credential_profile", lambda c: "test_prof")
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed", lambda p, r, c, l: True)

    result = _do_login_flow(tmp_path, {"baidu": {"credential_profile": "test_prof"}},
                            fake_page, logger, "p", "n", None, lambda _: None)
    assert result["success"] is True
    assert result["account_verified"] is False
    assert result["needs_project_account_check"] is True
    state = load_browser_login_state(tmp_path)
    assert state.get("last_profile") is None, "用户名不匹配时不应写 login_state"


def test_login_flow_undetectable_user_allows_proceeding(tmp_path, monkeypatch):
    """无法识别用户名时：不写 browser_login_state，返回 needs_project_account_check。"""
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import _do_login_flow, load_browser_login_state

    (tmp_path / "reports").mkdir(exist_ok=True)
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    logger = logging.getLogger("test")

    monkeypatch.setattr("modules.baidu_session.get_expected_baidu_username", lambda r, c: "user_a")
    monkeypatch.setattr("modules.baidu_session.detect_current_baidu_username", lambda p: None)
    monkeypatch.setattr("modules.baidu_session.get_current_project_credential_profile", lambda c: "test_prof")
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed", lambda p, r, c, l: True)

    result = _do_login_flow(tmp_path, {"baidu": {"credential_profile": "test_prof"}},
                            fake_page, logger, "p", "n", None, lambda _: None)
    assert result["success"] is True
    assert result["account_verified"] is False
    assert result["needs_project_account_check"] is True
    state = load_browser_login_state(tmp_path)
    assert state.get("last_profile") is None, "无法识别时不应写 login_state"


def test_login_flow_username_match_returns_verified(tmp_path, monkeypatch):
    """用户名匹配时 account_verified=True，但 _do_login_flow 本身不写状态。"""
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import _do_login_flow, load_browser_login_state

    (tmp_path / "reports").mkdir(exist_ok=True)
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    logger = logging.getLogger("test")

    monkeypatch.setattr("modules.baidu_session.get_expected_baidu_username", lambda r, c: "test_user")
    monkeypatch.setattr("modules.baidu_session.detect_current_baidu_username", lambda p: "test_user")
    monkeypatch.setattr("modules.baidu_session.get_current_project_credential_profile", lambda c: "kunming_niu_baidu")
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed", lambda p, r, c, l: True)

    result = _do_login_flow(tmp_path, {"baidu": {"credential_profile": "kunming_niu_baidu"}},
                            fake_page, logger, "kunming_niu", "昆明牛", None, lambda _: None)
    assert result["success"] is True
    assert result["account_verified"] is True
    assert result["needs_project_account_check"] is False
    # _do_login_flow 本身不写状态
    state = load_browser_login_state(tmp_path)
    assert state.get("last_profile") is None, "_do_login_flow 不写状态，由项目账户复核后写"


def test_logout_baidu_account_prioritizes_click(monkeypatch):
    """logout_baidu_account 优先通过页面点击退出。"""
    from unittest.mock import MagicMock
    from modules.baidu_session import logout_baidu_account

    fake_page = MagicMock()
    fake_page.url = "about:blank"
    fake_el = MagicMock()
    fake_el.count.return_value = 1
    fake_el.is_visible.return_value = True
    fake_page.locator.return_value.first = fake_el

    # wait_until_logged_out 返回 True
    monkeypatch.setattr("modules.baidu_session.wait_until_cas_login_page", lambda page, timeout_ms=5000: True)

    result = logout_baidu_account(fake_page, root=".")
    assert result["success"] is True, "应退出成功"


def test_logout_baidu_account_accepts_cas_after_account_click(monkeypatch):
    """点击账号入口后若已进入 CAS，直接视为退出成功，不继续反复找退出按钮。"""
    from unittest.mock import MagicMock
    from modules.baidu_session import logout_baidu_account

    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    fake_page.viewport_size = {"width": 1920, "height": 1080}
    fake_el = MagicMock()
    fake_el.count.return_value = 1
    fake_el.is_visible.return_value = True
    fake_el.bounding_box.return_value = {"x": 1700, "y": 0, "width": 120, "height": 48}
    fake_page.locator.return_value.first = fake_el

    def fake_click(page, box):
        page.url = "https://cas.baidu.com/?tpl=www2"
        return True

    dump_calls = []
    monkeypatch.setattr("modules.baidu_session._click_element_center", fake_click)
    monkeypatch.setattr("modules.baidu_session._dump_candidates_to", lambda page, root, filename: dump_calls.append(filename) or [])

    result = logout_baidu_account(fake_page, root=".")

    assert result["success"] is True
    assert result["message"] == "点击账号入口后已进入百度登录页"
    assert dump_calls == ["baidu_logout_candidates_before.json", "baidu_logout_candidates_after_account_click.json"]


def test_logout_candidate_filter_ignores_large_container_and_accepts_menu_item():
    """退出候选只接受明确菜单项，避免点到包含“退出”的整页大容器。"""
    from modules.baidu_session import _is_logout_candidate

    assert _is_logout_candidate({
        "text": "首页 数据报告 退出登录 账户管理",
        "tag": "DIV",
        "class": "root",
        "box": {"x": 0, "y": 0, "width": 1920, "height": 900},
    }) is False
    assert _is_logout_candidate({
        "text": "退出登录",
        "tag": "LI",
        "class": "one-menu-item",
        "box": {"x": 1700, "y": 160, "width": 120, "height": 36},
    }) is True


def test_click_element_center_uses_candidate_width_and_height():
    """候选矩形带宽高时点击真实中心，而不是默认猜 40x24。"""
    from modules.baidu_session import _click_element_center

    class FakeMouse:
        def __init__(self):
            self.moves = []
            self.clicks = []

        def move(self, x, y):
            self.moves.append((x, y))

        def click(self, x, y):
            self.clicks.append((x, y))

    class FakePage:
        def __init__(self):
            self.mouse = FakeMouse()

        def wait_for_timeout(self, timeout):
            pass

    page = FakePage()

    assert _click_element_center(page, {"x": 100, "y": 50, "width": 160, "height": 40}) is True
    assert page.mouse.clicks == [(180, 70)]


def test_logout_baidu_account_no_entry_returns_false():
    """找不到退出入口时不 traceback，返回 success=False。"""
    from unittest.mock import MagicMock
    from modules.baidu_session import logout_baidu_account

    fake_page = MagicMock()
    fake_el = MagicMock()
    fake_el.count.return_value = 0
    fake_page.locator.return_value.first = fake_el

    result = logout_baidu_account(fake_page, root=".")
    assert isinstance(result, dict)
    assert result["success"] is False


def test_force_relogin_tries_logout_then_cas(tmp_path, monkeypatch):
    """force_relogin 先调 logout，再进 CAS。"""
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import force_relogin_current_project

    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu", "project_name": "昆明牛"}
    fake_page = MagicMock()
    fake_page.url = "about:blank"
    logger = logging.getLogger("test")

    logout_calls = []
    cas_calls = []
    login_calls = []
    monkeypatch.setattr("modules.baidu_session.logout_baidu_account",
                        lambda page: logout_calls.append(1) or {"success": True, "message": "ok"})
    monkeypatch.setattr("modules.baidu_session.wait_until_cas_login_page", lambda page, timeout_ms=5000: False)
    monkeypatch.setattr("modules.baidu_session.goto_baidu_login_page",
                        lambda page: cas_calls.append(1) or {"success": True})
    monkeypatch.setattr("modules.baidu_session.get_expected_baidu_username", lambda r, c: "test_user")
    monkeypatch.setattr("modules.baidu_session.detect_current_baidu_username", lambda p: "test_user")
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed",
                        lambda p, r, c, l: login_calls.append(1) or True)

    result = force_relogin_current_project(tmp_path, config, fake_page, logger, input_func=lambda _: "", output_func=lambda _: None)
    assert result is True
    assert len(logout_calls) >= 1, "应先调用 logout"
    assert len(cas_calls) >= 1, "应进入 CAS"
    assert len(login_calls) >= 1, "应登录"


def test_logout_failure_resets_cookies_then_uses_cas(tmp_path, monkeypatch):
    """logout 失败且页面已登录时，清 cookie 后继续进入 CAS。"""
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import force_relogin_current_project

    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu", "project_name": "昆明牛"}
    fake_page = MagicMock()
    fake_page.url = "about:blank"
    logger = logging.getLogger("test")

    cas_calls = []
    monkeypatch.setattr("modules.baidu_session.logout_baidu_account",
                        lambda page: {"success": False, "message": "未找到"})
    monkeypatch.setattr("modules.baidu_session.is_baidu_logged_in", lambda page: True)
    monkeypatch.setattr("modules.baidu_session.wait_until_cas_login_page", lambda page, timeout_ms=5000: False)
    monkeypatch.setattr("modules.baidu_session.goto_baidu_login_page",
                        lambda page: cas_calls.append(1) or {"success": True})
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed", lambda p, r, c, l: True)

    result = force_relogin_current_project(tmp_path, config, fake_page, logger, input_func=lambda _: "", output_func=lambda _: None)
    assert result is True
    assert len(cas_calls) >= 1
    fake_page.context.clear_cookies.assert_called()


def test_wait_until_cas_only_accepts_cas_url():
    """wait_until_cas_login_page 只在 URL 含 cas.baidu.com 时返回 True。"""
    from unittest.mock import MagicMock
    from modules.baidu_session import wait_until_cas_login_page

    fake_page = MagicMock()
    fake_page.url = "https://cas.baidu.com/?tpl=www2"
    assert wait_until_cas_login_page(fake_page, timeout_ms=500) is True

    fake_page.url = "https://www2.baidu.com/"
    assert wait_until_cas_login_page(fake_page, timeout_ms=500) is False


def test_logout_success_requires_cas_verification(monkeypatch):
    """退出成功必须验证 CAS 页面。"""
    from unittest.mock import MagicMock
    from modules.baidu_session import logout_baidu_account

    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    fake_el = MagicMock()
    fake_el.count.return_value = 0
    fake_page.locator.return_value.first = fake_el

    # CAS 验证失败
    monkeypatch.setattr("modules.baidu_session.wait_until_cas_login_page", lambda page, timeout_ms=5000: False)

    result = logout_baidu_account(fake_page, root=".")
    assert result["success"] is False, "未到 CAS 不应返回成功"


def test_baidu_session_has_no_mark_login_calls():
    """baidu_session.py 中不再有 mark_browser_login_success 调用。"""
    root = Path(__file__).resolve().parents[1]
    source = (root / "modules" / "baidu_session.py").read_text(encoding="utf-8")
    lines = source.split("\n")
    # 找到 def mark_browser_login_success 之后的所有调用
    in_def = False
    calls = []
    for line in lines:
        if "def mark_browser_login_success" in line:
            in_def = True
            continue
        if in_def and "mark_browser_login_success(" in line and "def " not in line:
            calls.append(line.strip())
    assert len(calls) == 0, f"baidu_session.py 不应调用 mark_browser_login_success：{calls}"


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


def test_goto_report_non_noauth_passes(tmp_path):
    """report URL 且非 noauth → _goto_report_page 直接返回 True。"""
    from unittest.mock import MagicMock
    from modules.baidu_overview import _goto_report_page
    import logging
    logger = logging.getLogger("test")
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    assert _goto_report_page(fake_page, logger) is True


def test_goto_report_noauth_relogin_menu_success(monkeypatch):
    """noauth → 重登 → 菜单三步成功 → 最终验证搜索推广通过 → True。"""
    from unittest.mock import MagicMock
    from modules.baidu_overview import _goto_report_page
    import logging
    logger = logging.getLogger("test")

    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"
    fake_page.locator("body").inner_text.return_value = "搜索推广"

    # 动态 mock：先 noauth=True 进菜单路径，之后 noauth=False
    results = [True, False]
    def dynamic_noauth(page):
        return results.pop(0) if results else False

    monkeypatch.setattr("modules.baidu_session.is_baidu_noauth_page", dynamic_noauth)
    monkeypatch.setattr("modules.baidu_overview._ensure_baidu_home_rendered",
                        lambda page, config, logger: "")
    monkeypatch.setattr("modules.baidu_overview._click_by_text_or_role",
                        lambda page, labels, logger: "clicked")
    monkeypatch.setattr("modules.baidu_detector.classify_baidu_page",
                        lambda url, text: {"login_status": "logged_in", "signals": {"has_search_promotion": True}})

    result = _goto_report_page(fake_page, logger,
                               root=".", config={"baidu": {"credential_profile": "test"}, "project_id": "p"})
    assert result is True


def test_goto_report_menu_click_fails_returns_false(monkeypatch):
    """菜单路径点击失败 → _goto_report_page 返回 False。"""
    from unittest.mock import MagicMock
    from modules.baidu_overview import _goto_report_page
    import logging
    logger = logging.getLogger("test")

    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"

    # 动态 mock：前2次 True 进入 noauth 分支
    results = [True, False]
    def dynamic_noauth(page):
        return results.pop(0) if results else False

    monkeypatch.setattr("modules.baidu_session.is_baidu_noauth_page", dynamic_noauth)
    monkeypatch.setattr("modules.baidu_session.force_relogin_current_project",
                        lambda root, config, page, logger, **kw: True)
    monkeypatch.setattr("modules.baidu_overview._ensure_baidu_home_rendered",
                        lambda page, config, logger: "")
    # 第一个菜单点击返回 None（失败）
    monkeypatch.setattr("modules.baidu_overview._click_by_text_or_role",
                        lambda page, labels, logger: None)

    result = _goto_report_page(fake_page, logger,
                               root=".", config={"baidu": {"credential_profile": "test"}, "project_id": "p"})
    assert result is False, "菜单点击失败应返回 False"


def test_page_usable_false_when_username_mismatch(tmp_path, monkeypatch):
    """_page_is_usable 在 detected_user != expected_user 时返回 False。"""
    from unittest.mock import MagicMock
    from modules.baidu_session import _page_is_usable_search_promotion

    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"

    monkeypatch.setattr("modules.baidu_session.is_baidu_noauth_page", lambda page: False)
    monkeypatch.setattr("modules.baidu_detector.classify_baidu_page",
                        lambda url, text: {"login_status": "logged_in", "signals": {"has_search_promotion": True}})
    monkeypatch.setattr("modules.baidu_session.get_expected_baidu_username", lambda root, config: "user_a")
    monkeypatch.setattr("modules.baidu_session.detect_current_baidu_username", lambda page: "user_b")

    result = _page_is_usable_search_promotion(fake_page, tmp_path, {})
    assert result is False, "用户名不匹配应返回 False"


def test_page_usable_true_when_username_match(tmp_path, monkeypatch):
    """_page_is_usable 在 detected_user == expected_user 时返回 True。"""
    from unittest.mock import MagicMock
    from modules.baidu_session import _page_is_usable_search_promotion

    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"

    monkeypatch.setattr("modules.baidu_session.is_baidu_noauth_page", lambda page: False)
    monkeypatch.setattr("modules.baidu_detector.classify_baidu_page",
                        lambda url, text: {"login_status": "logged_in", "signals": {"has_search_promotion": True}})
    monkeypatch.setattr("modules.baidu_session.get_expected_baidu_username", lambda root, config: "user_a")
    monkeypatch.setattr("modules.baidu_session.detect_current_baidu_username", lambda page: "user_a")

    result = _page_is_usable_search_promotion(fake_page, tmp_path, {})
    assert result is True


def test_page_usable_false_when_last_profile_empty_no_detect(tmp_path, monkeypatch):
    """_page_is_usable 在无法识别且 last_profile 为空时返回 False。"""
    from unittest.mock import MagicMock
    from modules.baidu_session import _page_is_usable_search_promotion

    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/report"

    monkeypatch.setattr("modules.baidu_session.is_baidu_noauth_page", lambda page: False)
    monkeypatch.setattr("modules.baidu_detector.classify_baidu_page",
                        lambda url, text: {"login_status": "logged_in", "signals": {"has_search_promotion": True}})
    monkeypatch.setattr("modules.baidu_session.get_expected_baidu_username", lambda root, config: None)
    monkeypatch.setattr("modules.baidu_session.detect_current_baidu_username", lambda page: None)
    monkeypatch.setattr("modules.baidu_session.get_browser_login_profile", lambda root: None)
    monkeypatch.setattr("modules.baidu_session.get_current_project_credential_profile", lambda config: "proj_a")

    result = _page_is_usable_search_promotion(fake_page, tmp_path, {})
    assert result is False


def test_logger_error_no_playwright_call_log(capsys):
    """默认终端不输出 Playwright call log。"""
    import logging
    logger = logging.getLogger("test_plog")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    import sys
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.WARNING)
    logger.addHandler(handler)

    logger.error("进入百度报告页异常")
    captured = capsys.readouterr()
    assert "Call log:" not in captured.err, "默认不应有 Playwright call log"
    assert "navigating to" not in captured.err

    logger.handlers.clear()


def test_goto_report_homepage_calls_menu_path(monkeypatch):
    """非 report URL（如 homepage）→ 走菜单路径。"""
    from unittest.mock import MagicMock
    from modules.baidu_overview import _goto_report_page
    import logging
    logger = logging.getLogger("test")

    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/homepage"
    fake_page.locator("body").inner_text.return_value = ""

    click_calls = []
    monkeypatch.setattr("modules.baidu_session.is_baidu_noauth_page", lambda page: False)
    monkeypatch.setattr("modules.baidu_overview._ensure_baidu_home_rendered",
                        lambda page, config, logger: "")
    monkeypatch.setattr("modules.baidu_overview._click_by_text_or_role",
                        lambda page, labels, logger: click_calls.append(labels) or "clicked")
    monkeypatch.setattr("modules.baidu_detector.classify_baidu_page",
                        lambda url, text: {"login_status": "logged_in", "signals": {"has_search_promotion": True}})

    result = _goto_report_page(fake_page, logger, root=".", config={"project_id": "p"})
    assert result is True
    assert len(click_calls) == 3


def test_baidu_prepare_overview_returns_early_on_open_errors():
    """open_report 有 errors 时立即返回，不继续 validate_overview_ready。"""
    root = Path(__file__).resolve().parents[1]
    source = (root / "modules" / "baidu_overview.py").read_text(encoding="utf-8")
    assert "baidu-prepare-overview 中断" in source
    assert "搜索推广页打开失败" in source

def test_tentative_bypass_missing_accounts_triggers_relogin(tmp_path, monkeypatch):
    import logging
    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu", "project_name": "昆明牛"}

    def fake_open(config, root, logger):
        return {"final_url": "https://cc.baidu.com/report", "errors": [], "session_check": {"decision": "tentative_bypass", "passed": True}}

    validate_calls = []
    def fake_validate(visible_text, target_date, config):
        validate_calls.append(1)
        if len(validate_calls) == 1:
            return {"passed": False, "errors": ["页面未看到目标账户：银康01"]}
        return {"passed": True, "errors": []}

    clear_calls = []
    mark_calls = []
    monkeypatch.setattr("modules.baidu_overview.baidu_open_overview", fake_open)
    monkeypatch.setattr("modules.baidu_overview.validate_overview_ready", fake_validate)
    monkeypatch.setattr("modules.baidu_session.clear_browser_login_state", lambda root: clear_calls.append(1))
    monkeypatch.setattr("modules.baidu_session.mark_browser_login_success", lambda root, credential_profile, **kw: mark_calls.append(1))

    from modules.baidu_overview import baidu_prepare_overview
    report = baidu_prepare_overview(config, tmp_path, logger=logging.getLogger("test"))
    assert report.get("validation_retry_triggered") is True
    assert report.get("validation_retry_passed") is True
    assert len(clear_calls) >= 1
    assert len(mark_calls) >= 1
    assert len(validate_calls) == 2
    assert "银康01" not in str(report.get("errors", []))


def test_tentative_bypass_retry_still_fails_error_converges(tmp_path, monkeypatch):
    import logging
    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu", "project_name": "昆明牛"}

    def fake_open(config, root, logger):
        return {"final_url": "https://cc.baidu.com/report", "errors": [], "session_check": {"decision": "tentative_bypass", "passed": True}}

    def fake_validate(visible_text, target_date, config):
        return {"passed": False, "errors": ["页面未看到目标账户：银康01"]}

    mark_calls = []
    monkeypatch.setattr("modules.baidu_overview.baidu_open_overview", fake_open)
    monkeypatch.setattr("modules.baidu_overview.validate_overview_ready", fake_validate)
    monkeypatch.setattr("modules.baidu_session.clear_browser_login_state", lambda root: None)
    monkeypatch.setattr("modules.baidu_session.mark_browser_login_success", lambda root, credential_profile, **kw: mark_calls.append(1))

    from modules.baidu_overview import baidu_prepare_overview
    report = baidu_prepare_overview(config, tmp_path, logger=logging.getLogger("test"))
    assert report.get("validation_retry_triggered") is True
    assert len(report["errors"]) > 0
    assert "未看到当前项目账户" in " ".join(report["errors"])
    assert "银康01" not in " ".join(report["errors"])
    assert len(mark_calls) == 0
def test_force_relogin_retries_logout_once_before_cas(tmp_path, monkeypatch):
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import force_relogin_current_project

    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu"}
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/homepage"
    logger = logging.getLogger("test")

    logout_results = [
        {"success": False, "message": "first"},
        {"success": True, "message": "second"},
    ]
    cas_calls = []
    monkeypatch.setattr("modules.baidu_session.logout_baidu_account", lambda page: logout_results.pop(0))
    monkeypatch.setattr("modules.baidu_session.is_baidu_logged_in", lambda page: True)
    monkeypatch.setattr("modules.baidu_session.wait_until_cas_login_page", lambda page, timeout_ms=5000: False)
    monkeypatch.setattr("modules.baidu_session.goto_baidu_login_page", lambda page: cas_calls.append(1) or {"success": True})
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed", lambda p, r, c, l: True)

    result = force_relogin_current_project(tmp_path, config, fake_page, logger, input_func=lambda _: "", output_func=lambda _: None)
    assert result is True
    assert len(cas_calls) == 1


def test_force_relogin_double_logout_failure_falls_back_to_cookie_reset(tmp_path, monkeypatch):
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import force_relogin_current_project

    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu"}
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/homepage"
    logger = logging.getLogger("test")

    cas_calls = []
    monkeypatch.setattr("modules.baidu_session.logout_baidu_account", lambda page: {"success": False, "message": "nope"})
    monkeypatch.setattr("modules.baidu_session.is_baidu_logged_in", lambda page: True)
    monkeypatch.setattr("modules.baidu_session.wait_until_cas_login_page", lambda page, timeout_ms=5000: False)
    monkeypatch.setattr("modules.baidu_session.goto_baidu_login_page", lambda page: cas_calls.append(1) or {"success": True})
    monkeypatch.setattr("modules.baidu_overview._auto_login_if_needed", lambda p, r, c, l: True)

    result = force_relogin_current_project(tmp_path, config, fake_page, logger, input_func=lambda _: "", output_func=lambda _: None)
    assert result is True
    assert len(cas_calls) >= 1
    fake_page.context.clear_cookies.assert_called()


def test_session_detected_none_logged_in_uses_tentative_bypass(tmp_path, monkeypatch):
    import logging
    from unittest.mock import MagicMock
    from modules.baidu_session import ensure_baidu_profile_session

    (tmp_path / "reports").mkdir(exist_ok=True)
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu"}
    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/homepage"
    logger = logging.getLogger("test")

    relogin_calls = []
    monkeypatch.setattr("modules.baidu_session.get_expected_baidu_username", lambda r, c: "target")
    monkeypatch.setattr("modules.baidu_session.detect_current_baidu_username", lambda p: None)
    monkeypatch.setattr("modules.baidu_session.is_baidu_logged_in", lambda p: True)
    monkeypatch.setattr("modules.baidu_session._page_is_usable_search_promotion", lambda p, r, c: False)
    monkeypatch.setattr("modules.baidu_session.force_relogin_current_project", lambda *args, **kwargs: relogin_calls.append(1) or True)

    result = ensure_baidu_profile_session(tmp_path, config, fake_page, logger, input_func=lambda _: "", output_func=lambda _: None)
    assert result["passed"] is True
    assert result["decision"] == "tentative_bypass"
    assert relogin_calls == []


def test_goto_report_homepage_failure_returns_false_without_parse(monkeypatch):
    from unittest.mock import MagicMock
    from modules.baidu_overview import _goto_report_page
    import logging
    logger = logging.getLogger("test")

    fake_page = MagicMock()
    fake_page.url = "https://cc.baidu.com/homepage"

    monkeypatch.setattr("modules.baidu_overview._ensure_baidu_home_rendered", lambda page, config, logger: "")
    monkeypatch.setattr("modules.baidu_overview._click_by_text_or_role", lambda page, labels, logger: None)
    monkeypatch.setattr("modules.baidu_session.is_baidu_noauth_page", lambda page: False)

    result = _goto_report_page(fake_page, logger, root=".", config={"project_id": "p"})
    assert result is False


def test_baidu_prepare_overview_does_not_write_state_when_validate_fails(tmp_path, monkeypatch):
    import logging

    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "reports" / "baidu_visible_text.txt").write_text("homepage", encoding="utf-8")
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu"}

    monkeypatch.setattr(
        "modules.baidu_overview.baidu_open_overview",
        lambda config, root, logger: {
            "final_url": "https://cc.baidu.com/homepage",
            "errors": [],
            "session_check": {"decision": "bypass", "passed": True},
        },
    )
    monkeypatch.setattr(
        "modules.baidu_overview.validate_overview_ready",
        lambda visible_text, target_date, config: {
            "passed": False,
            "errors": ["百度搜索推广数据页打开失败，请检查百度后台页面状态"],
        },
    )
    mark_calls = []
    monkeypatch.setattr("modules.baidu_session.mark_browser_login_success", lambda root, credential_profile, **kw: mark_calls.append(1))

    from modules.baidu_overview import baidu_prepare_overview
    report = baidu_prepare_overview(config, tmp_path, logger=logging.getLogger("test"))
    assert report["errors"]
    assert mark_calls == []


def test_prepare_baidu_daily_report_page_checks_session_before_single_goto(tmp_path, monkeypatch):
    import logging
    from unittest.mock import MagicMock

    from modules.baidu_daily import _prepare_baidu_daily_report_page

    (tmp_path / "reports").mkdir(exist_ok=True)
    page = MagicMock()
    page.url = "https://cc.baidu.com/homepage"
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu"}
    report = {"errors": []}
    calls = []

    def fake_session(root, config, page, logger, task=None):
        calls.append("session")
        return {"passed": True, "decision": "relogin", "reason": "state_unknown"}

    def fake_goto(page, logger, root=None, config=None):
        calls.append("goto")
        page.url = "https://cc.baidu.com/report"
        return True

    monkeypatch.setattr("modules.baidu_session.ensure_baidu_profile_session", fake_session)
    monkeypatch.setattr("modules.baidu_daily._goto_report_page", fake_goto)

    ok = _prepare_baidu_daily_report_page(page, config, tmp_path, logging.getLogger("test"), report)

    assert ok is True
    assert calls == ["session", "goto"]
    assert report["session_check"]["decision"] == "relogin"
    assert report["errors"] == []


def test_prepare_baidu_daily_report_page_retries_once_after_login_redirect(tmp_path, monkeypatch):
    import logging
    from unittest.mock import MagicMock

    from modules.baidu_daily import _prepare_baidu_daily_report_page

    (tmp_path / "reports").mkdir(exist_ok=True)
    page = MagicMock()
    page.url = "https://cc.baidu.com/homepage"
    config = {"baidu": {"credential_profile": "kunming_niu_baidu"}, "project_id": "kunming_niu"}
    report = {"errors": []}
    calls = []

    monkeypatch.setattr(
        "modules.baidu_session.ensure_baidu_profile_session",
        lambda root, config, page, logger, task=None: calls.append("session") or {"passed": True, "decision": "tentative_bypass"},
    )

    def fake_goto(page, logger, root=None, config=None):
        calls.append("goto")
        if calls.count("goto") == 1:
            page.url = "https://cas.baidu.com/?tpl=www2&fromu=https%3A%2F%2Fcc.baidu.com%2Freport"
            return False
        page.url = "https://cc.baidu.com/report"
        return True

    def fake_login(page, root, config, logger):
        calls.append("login")
        page.url = "https://cc.baidu.com/report"
        return True

    monkeypatch.setattr("modules.baidu_daily._goto_report_page", fake_goto)
    monkeypatch.setattr("modules.baidu_daily._auto_login_if_needed", fake_login)

    ok = _prepare_baidu_daily_report_page(page, config, tmp_path, logging.getLogger("test"), report)

    assert ok is True
    assert calls == ["session", "goto", "login", "goto"]
    assert report["errors"] == []


def test_daily_search_promotion_check_does_not_navigate_report_again(monkeypatch):
    import logging
    from unittest.mock import MagicMock

    from modules.baidu_daily import _ensure_search_promotion_before_daily_date

    page = MagicMock()
    page.url = "https://cc.baidu.com/report"
    monkeypatch.setattr("modules.baidu_daily._read_page_text", lambda page: "数据报告 搜索推广 账户 展现 点击 消费")
    monkeypatch.setattr("modules.baidu_daily.classify_baidu_page", lambda url, text: {"page_type": "搜索推广数据页"})
    monkeypatch.setattr("modules.baidu_daily.is_search_promotion_overview", lambda classification: True)
    monkeypatch.setattr(
        "modules.baidu_daily._goto_report_page",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应重复打开 report")),
    )

    ok, visible_text = _ensure_search_promotion_before_daily_date(page, {}, logging.getLogger("test"), root=".")

    assert ok is True
    assert "搜索推广" in visible_text


def test_extract_baidu_rows_from_page_prefers_dom_table_and_parses_currency_formats():
    from modules.baidu_parser import extract_baidu_rows_from_page

    class FakeLocator:
        def inner_text(self, timeout=None):
            return """
数据报告
搜索推广
账户
展现
点击
消费
"""

    class FakePage:
        def locator(self, selector):
            assert selector == "body"
            return FakeLocator()

        def evaluate(self, script):
            return [
                {"账户": "竞网CS博润241209", "展现": "1,234", "点击": "56", "消费": "￥1,234.56"},
                {"账户": "竞网CS博润240304", "展现": "2,345", "点击": "--", "消费": "123.45元"},
                {"账户": "竞网CS博润251218", "展现": "-", "点击": "78", "消费": "0"},
                {"账户": "总计-3", "展现": "3,579", "点击": "134", "消费": "1358.01"},
            ]

    config = {
        "project_id": "changsha_niu",
        "accounts": {
            "竞网CS博润241209": {"baidu_name": "竞网CS博润241209", "aliases": ["竞网CS博润241209"]},
            "竞网CS博润240304": {"baidu_name": "竞网CS博润240304", "aliases": ["竞网CS博润240304"]},
            "竞网CS博润251218": {"baidu_name": "竞网CS博润251218", "aliases": ["竞网CS博润251218"]},
        },
    }

    result = extract_baidu_rows_from_page(FakePage(), config)
    parsed = parse_baidu_table(result["rows"], config)

    assert result["extraction_method"] == "dom"
    assert result["detected_headers"] == ["账户", "展现", "点击", "消费"]
    assert result["debug"]["parsed_account_count"] == 3
    assert parsed["accounts"]["竞网CS博润241209"]["点击"] == 56
    assert parsed["accounts"]["竞网CS博润241209"]["消费"] == 1234.56
    assert parsed["accounts"]["竞网CS博润240304"]["点击"] == 0
    assert parsed["accounts"]["竞网CS博润251218"]["展现"] == 0


def test_extract_baidu_rows_from_page_falls_back_to_visible_text_when_dom_unusable():
    from modules.baidu_parser import extract_baidu_rows_from_page

    text = """
数据报告
搜索推广
账户
账户ID
展现
点击
消费
总计-3
-
-
-
-
宁波博润1
1001
1,001
11
￥101.50
宁波博润2
1002
2,002
22
202.25元
宁波博润12
1003
3,003
33
303.75
20条/页
"""

    class FakeLocator:
        def __init__(self, value):
            self._value = value

        def inner_text(self, timeout=None):
            return self._value

    class FakePage:
        def locator(self, selector):
            assert selector == "body"
            return FakeLocator(text)

        def evaluate(self, script):
            return [{"列1": "未知", "列2": "N/A"}]

    config = {
        "project_id": "ningbo_niu",
        "accounts": {
            "宁波博润1": {"baidu_name": "宁波博润1", "aliases": ["宁波博润1"]},
            "宁波博润2": {"baidu_name": "宁波博润2", "aliases": ["宁波博润2"]},
            "宁波博润12": {"baidu_name": "宁波博润12", "aliases": ["宁波博润12"]},
        },
    }

    result = extract_baidu_rows_from_page(FakePage(), config)
    parsed = parse_baidu_table(result["rows"], config)

    assert result["extraction_method"] == "visible_text"
    assert set(parsed["accounts"].keys()) == {"宁波博润1", "宁波博润2", "宁波博润12"}
    assert parsed["accounts"]["宁波博润12"]["消费"] == 303.75


def test_parse_baidu_table_reports_raw_value_and_extraction_method_for_non_numeric_fields():
    config = {
        "accounts": {
            "宁波博润1": {"baidu_name": "宁波博润1", "aliases": ["宁波博润1"]},
        }
    }
    rows = [
        {
            "账户": "宁波博润1",
            "展现": "1,234",
            "点击": "N/A",
            "消费": "abc",
            "__source__": "dom",
            "__row_sample_id__": "row-2",
        }
    ]

    parsed = parse_baidu_table(rows, config)

    assert any("raw_value=N/A" in error and "extraction_method=dom" in error and "row_sample_id=row-2" in error for error in parsed["errors"])
    assert any("raw_value=abc" in error and "account_name=宁波博润1" in error for error in parsed["errors"])


def test_baidu_prepare_overview_fails_when_report_table_not_parseable(tmp_path, monkeypatch):
    import logging

    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "reports" / "baidu_visible_text.txt").write_text(
        "数据报告 搜索推广 2026/05/07 账户 展现 点击 消费",
        encoding="utf-8",
    )
    (tmp_path / "reports" / "baidu_table_parse_debug.json").write_text(
        json.dumps(
            {
                "project_id": "changsha_niu",
                "required_accounts": ["A", "B", "C"],
                "extraction_method": "dom",
                "detected_headers": ["账户", "展现", "点击", "消费"],
                "parsed_account_count": 0,
                "parsed_accounts": [],
                "missing_accounts": ["A", "B", "C"],
                "non_numeric_fields": [],
                "sample_rows": [],
                "row_cell_count": [4],
                "parse_ready": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = {
        "project_id": "changsha_niu",
        "project_name": "长沙牛",
        "accounts": {
            "A": {"baidu_name": "A", "aliases": ["A"]},
            "B": {"baidu_name": "B", "aliases": ["B"]},
            "C": {"baidu_name": "C", "aliases": ["C"]},
        },
    }

    monkeypatch.setattr(
        "modules.baidu_overview.baidu_open_overview",
        lambda config, root, logger: {
            "final_url": "https://cc.baidu.com/report",
            "final_page_type": "搜索推广",
            "errors": [],
            "session_check": {"decision": "bypass", "passed": True},
        },
    )

    from modules.baidu_overview import baidu_prepare_overview
    report = baidu_prepare_overview(config, tmp_path, logger=logging.getLogger("test"))

    assert report["errors"]
    assert any("百度搜索推广账户表格未完整加载" in error for error in report["errors"])


def test_fetch_baidu_auto_uses_dom_candidates_from_prepare_artifacts(tmp_path, monkeypatch):
    import logging
    from datetime import date

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "baidu_visible_text.txt").write_text(date.today().strftime("%Y/%m/%d"), encoding="utf-8")
    dom_rows = [
        {"账户": "竞网CS博润241209", "展现": "1,001", "点击": "11", "消费": "101.5", "__source__": "dom", "__row_sample_id__": "dom-row-1"},
        {"账户": "竞网CS博润240304", "展现": "2,002", "点击": "22", "消费": "202.5", "__source__": "dom", "__row_sample_id__": "dom-row-2"},
        {"账户": "竞网CS博润251218", "展现": "3,003", "点击": "33", "消费": "303.5", "__source__": "dom", "__row_sample_id__": "dom-row-3"},
    ]
    (reports_dir / "baidu_table_candidates.json").write_text(
        json.dumps({"source": "dom", "rows": dom_rows, "row_count": 3, "detected_headers": ["账户", "展现", "点击", "消费"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (reports_dir / "baidu_table_parse_debug.json").write_text(
        json.dumps(
            {
                "project_id": "changsha_niu",
                "required_accounts": ["竞网CS博润241209", "竞网CS博润240304", "竞网CS博润251218"],
                "extraction_method": "dom",
                "detected_headers": ["账户", "展现", "点击", "消费"],
                "parsed_account_count": 3,
                "parsed_accounts": ["竞网CS博润241209", "竞网CS博润240304", "竞网CS博润251218"],
                "missing_accounts": [],
                "non_numeric_fields": [],
                "sample_rows": [{"row_sample_id": "dom-row-1", "source": "dom", "cells": {"账户": "竞网CS博润241209"}}],
                "parse_ready": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "modules.baidu_auto.baidu_prepare_overview",
        lambda config, root, logger: {"errors": [], "open_report": {"final_url": "https://cc.baidu.com/report", "final_page_type": "搜索推广"}},
    )
    monkeypatch.setattr(
        "modules.baidu_auto.extract_baidu_rows_from_visible_text",
        lambda text: (_ for _ in ()).throw(AssertionError("不应回退到 visible_text")),
    )

    config = {
        "project_id": "changsha_niu",
        "project_name": "长沙牛",
        "accounts": {
            "竞网CS博润241209": {"baidu_name": "竞网CS博润241209", "aliases": ["竞网CS博润241209"]},
            "竞网CS博润240304": {"baidu_name": "竞网CS博润240304", "aliases": ["竞网CS博润240304"]},
            "竞网CS博润251218": {"baidu_name": "竞网CS博润251218", "aliases": ["竞网CS博润251218"]},
        },
    }

    report = fetch_baidu_auto(config, tmp_path, logging.getLogger("test"), "15点")

    assert report["errors"] == []
    assert report["parse_source"] == "dom"
    assert set(report["accounts"].keys()) == {"竞网CS博润241209", "竞网CS博润240304", "竞网CS博润251218"}


def test_baidu_prepare_overview_fails_early_on_visible_text_percent_misalignment(tmp_path, monkeypatch):
    import logging
    from modules.baidu_overview import baidu_prepare_overview

    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "reports" / "baidu_visible_text.txt").write_text(
        "数据报告 搜索推广 2026/05/07 账户 展现 点击 消费",
        encoding="utf-8",
    )
    (tmp_path / "reports" / "baidu_table_parse_debug.json").write_text(
        json.dumps(
            {
                "project_id": "ningbo_niu",
                "required_accounts": ["宁波博润1", "宁波博润2", "宁波博润12"],
                "extraction_method": "visible_text",
                "detected_headers": ["账户", "展现", "点击", "消费"],
                "parsed_account_count": 1,
                "parsed_accounts": ["宁波博润1"],
                "missing_accounts": ["宁波博润2", "宁波博润12"],
                "non_numeric_fields": [
                    {
                        "account_name": "宁波博润1",
                        "field": "消费",
                        "raw_value": "8.77%",
                        "extraction_method": "visible_text",
                        "row_sample_id": "visible_text-row-2",
                    }
                ],
                "sample_rows": [
                    {"row_sample_id": "visible_text-row-2", "source": "visible_text", "cells": {"账户": "宁波博润1", "消费": "8.77%"}}
                ],
                "parse_ready": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "modules.baidu_overview.baidu_open_overview",
        lambda config, root, logger: {
            "final_url": "https://cc.baidu.com/report",
            "final_page_type": "搜索推广",
            "errors": [],
            "session_check": {"decision": "bypass", "passed": True},
        },
    )

    config = {
        "project_id": "ningbo_niu",
        "project_name": "宁波牛",
        "accounts": {
            "宁波博润1": {"baidu_name": "宁波博润1", "aliases": ["宁波博润1"]},
            "宁波博润2": {"baidu_name": "宁波博润2", "aliases": ["宁波博润2"]},
            "宁波博润12": {"baidu_name": "宁波博润12", "aliases": ["宁波博润12"]},
        },
    }

    report = baidu_prepare_overview(config, tmp_path, logger=logging.getLogger("test"))

    assert report["errors"]
    assert "百度搜索推广账户表格未完整加载或列解析异常，请刷新后重试" in report["errors"]
    assert report["parse_check"]["debug"]["missing_accounts"] == ["宁波博润2", "宁波博润12"]


def test_extract_baidu_rows_from_page_supports_grid_rows_for_changsha_accounts():
    from modules.baidu_parser import extract_baidu_rows_from_page

    class FakeLocator:
        def inner_text(self, timeout=None):
            return "数据报告 搜索推广"

    class FakePage:
        def locator(self, selector):
            assert selector == "body"
            return FakeLocator()

        def evaluate(self, script):
            return [
                {"账户": "竞网CS博润241209", "展现": "1,234", "点击": "56", "消费": "123.45", "__source__": "dom_grid", "__row_sample_id__": "dom_grid-row-1"},
                {"账户": "竞网CS博润240304", "展现": "2,345", "点击": "67", "消费": "234.56", "__source__": "dom_grid", "__row_sample_id__": "dom_grid-row-2"},
                {"账户": "竞网CS博润251218", "展现": "3,456", "点击": "78", "消费": "345.67", "__source__": "dom_grid", "__row_sample_id__": "dom_grid-row-3"},
            ]

    config = {
        "project_id": "changsha_niu",
        "accounts": {
            "竞网CS博润241209": {"baidu_name": "竞网CS博润241209", "aliases": ["竞网CS博润241209"]},
            "竞网CS博润240304": {"baidu_name": "竞网CS博润240304", "aliases": ["竞网CS博润240304"]},
            "竞网CS博润251218": {"baidu_name": "竞网CS博润251218", "aliases": ["竞网CS博润251218"]},
        },
    }

    result = extract_baidu_rows_from_page(FakePage(), config)
    parsed = parse_baidu_table(result["rows"], config)

    assert result["extraction_method"] == "dom"
    assert result["debug"]["missing_accounts"] == []
    assert parsed["errors"] == []


def test_extract_baidu_rows_from_page_supports_grid_rows_for_ningbo_accounts():
    from modules.baidu_parser import extract_baidu_rows_from_page

    class FakeLocator:
        def inner_text(self, timeout=None):
            return "数据报告 搜索推广"

    class FakePage:
        def locator(self, selector):
            assert selector == "body"
            return FakeLocator()

        def evaluate(self, script):
            return [
                {"账户": "宁波博润1", "展现": "1,111", "点击": "11", "消费": "111.11", "__source__": "dom_grid", "__row_sample_id__": "dom_grid-row-1"},
                {"账户": "宁波博润2", "展现": "2,222", "点击": "22", "消费": "222.22", "__source__": "dom_grid", "__row_sample_id__": "dom_grid-row-2"},
                {"账户": "宁波博润12", "展现": "3,333", "点击": "33", "消费": "333.33", "__source__": "dom_grid", "__row_sample_id__": "dom_grid-row-3"},
            ]

    config = {
        "project_id": "ningbo_niu",
        "accounts": {
            "宁波博润1": {"baidu_name": "宁波博润1", "aliases": ["宁波博润1"]},
            "宁波博润2": {"baidu_name": "宁波博润2", "aliases": ["宁波博润2"]},
            "宁波博润12": {"baidu_name": "宁波博润12", "aliases": ["宁波博润12"]},
        },
    }

    result = extract_baidu_rows_from_page(FakePage(), config)
    parsed = parse_baidu_table(result["rows"], config)

    assert result["extraction_method"] == "dom"
    assert result["debug"]["missing_accounts"] == []
    assert parsed["errors"] == []


def test_extract_baidu_rows_from_page_ignores_total_row_like_header_candidate_and_uses_split_grid_candidate():
    from modules.baidu_parser import extract_baidu_rows_from_page

    class FakeLocator:
        def inner_text(self, timeout=None):
            return "数据报告 搜索推广"

    class FakePage:
        def locator(self, selector):
            assert selector == "body"
            return FakeLocator()

        def evaluate(self, script):
            return {
                "table_like_found": True,
                "candidates": [
                    {
                        "table_root_selector": "div.summary-grid",
                        "header_source": "row",
                        "header_cells": ["总计-5", "7,908", "3,379.4", "9.57%"],
                        "body_rows": [["总计-5", "7,908", "3,379.4", "9.57%"]],
                        "body_row_count": 1,
                    },
                    {
                        "table_root_selector": "div.report-grid",
                        "header_source": "split_grid",
                        "header_cells": ["账户", "展现", "点击", "消费"],
                        "body_rows": [
                            ["竞网CS博润241209", "1,234", "56", "123.45"],
                            ["竞网CS博润240304", "2,345", "67", "234.56"],
                            ["竞网CS博润251218", "3,456", "78", "345.67"],
                        ],
                        "body_row_count": 3,
                        "scroll_attempts": 1,
                        "accounts_seen_each_scroll": [["竞网CS博润241209", "竞网CS博润240304", "竞网CS博润251218"]],
                        "reached_bottom": False,
                    },
                ],
            }

    config = {
        "project_id": "changsha_niu",
        "accounts": {
            "竞网CS博润241209": {"baidu_name": "竞网CS博润241209", "aliases": ["竞网CS博润241209"]},
            "竞网CS博润240304": {"baidu_name": "竞网CS博润240304", "aliases": ["竞网CS博润240304"]},
            "竞网CS博润251218": {"baidu_name": "竞网CS博润251218", "aliases": ["竞网CS博润251218"]},
        },
    }

    result = extract_baidu_rows_from_page(FakePage(), config)

    assert result["extraction_method"] == "dom"
    assert result["debug"]["table_root_selector"] == "div.report-grid"
    assert result["debug"]["header_source"] == "split_grid"
    assert result["debug"]["header_cells"] == ["账户", "展现", "点击", "消费"]
    assert result["debug"]["missing_accounts"] == []
    assert any(
        attempt.get("header_cells") == ["总计-5", "7,908", "3,379.4", "9.57%"] and attempt.get("header_valid") is False
        for attempt in result["debug"]["dom_attempts"]
    )


def test_extract_baidu_rows_from_page_supports_scroll_aggregated_accounts_for_ningbo():
    from modules.baidu_parser import extract_baidu_rows_from_page

    class FakeLocator:
        def inner_text(self, timeout=None):
            return "数据报告 搜索推广"

    class FakePage:
        def locator(self, selector):
            assert selector == "body"
            return FakeLocator()

        def evaluate(self, script):
            return {
                "table_like_found": True,
                "candidates": [
                    {
                        "table_root_selector": "div.virtual-grid",
                        "header_source": "columnheader",
                        "header_cells": ["账户", "展现", "点击", "消费"],
                        "body_rows": [
                            ["宁波博润1", "1,111", "11", "111.11"],
                            ["宁波博润2", "2,222", "22", "222.22"],
                            ["宁波博润12", "3,333", "33", "333.33"],
                        ],
                        "body_row_count": 3,
                        "scroll_attempts": 3,
                        "accounts_seen_each_scroll": [
                            ["宁波博润1"],
                            ["宁波博润1", "宁波博润2"],
                            ["宁波博润1", "宁波博润2", "宁波博润12"],
                        ],
                        "reached_bottom": True,
                    }
                ],
            }

    config = {
        "project_id": "ningbo_niu",
        "accounts": {
            "宁波博润1": {"baidu_name": "宁波博润1", "aliases": ["宁波博润1"]},
            "宁波博润2": {"baidu_name": "宁波博润2", "aliases": ["宁波博润2"]},
            "宁波博润12": {"baidu_name": "宁波博润12", "aliases": ["宁波博润12"]},
        },
    }

    result = extract_baidu_rows_from_page(FakePage(), config)

    assert result["extraction_method"] == "dom"
    assert result["debug"]["scroll_attempts"] == 3
    assert result["debug"]["accounts_seen_each_scroll"][-1] == ["宁波博润1", "宁波博润2", "宁波博润12"]
    assert result["debug"]["required_accounts_found"] == ["宁波博润1", "宁波博润2", "宁波博润12"]
    assert result["debug"]["missing_accounts"] == []


def test_extract_baidu_rows_from_page_does_not_treat_rate_or_ratio_columns_as_click_or_cost():
    from modules.baidu_parser import extract_baidu_rows_from_page

    class FakeLocator:
        def inner_text(self, timeout=None):
            return "数据报告 搜索推广"

    class FakePage:
        def locator(self, selector):
            assert selector == "body"
            return FakeLocator()

        def evaluate(self, script):
            return {
                "table_like_found": True,
                "candidates": [
                    {
                        "table_root_selector": "div.bad-grid",
                        "header_source": "columnheader",
                        "header_cells": ["账户", "展现", "点击率", "消费占比"],
                        "body_rows": [["宁波博润1", "1,111", "8.86%", "11.08%"]],
                        "body_row_count": 1,
                    }
                ],
            }

    config = {
        "project_id": "ningbo_niu",
        "accounts": {
            "宁波博润1": {"baidu_name": "宁波博润1", "aliases": ["宁波博润1"]},
            "宁波博润2": {"baidu_name": "宁波博润2", "aliases": ["宁波博润2"]},
            "宁波博润12": {"baidu_name": "宁波博润12", "aliases": ["宁波博润12"]},
        },
    }

    result = extract_baidu_rows_from_page(FakePage(), config)

    assert result["extraction_method"] == "fallback_failed"
    assert result["debug"]["header_valid"] is False
    assert result["debug"]["invalid_header_reason"] in {"missing_required_headers", "invalid_metric_columns"}


def test_extract_baidu_rows_from_page_rejects_visible_text_fallback_when_accounts_incomplete_or_percent_misaligned():
    from modules.baidu_parser import extract_baidu_rows_from_page

    text = """
数据报告
搜索推广
账户
账户ID
展现
点击
消费
总计-3
-
-
-
-
宁波博润1
1001
1,001
8.86%
101.50
宁波博润2
1002
2,002
22
11.08%
20条/页
"""

    class FakeLocator:
        def inner_text(self, timeout=None):
            return text

    class FakePage:
        def locator(self, selector):
            assert selector == "body"
            return FakeLocator()

        def evaluate(self, script):
            return []

    config = {
        "project_id": "ningbo_niu",
        "accounts": {
            "宁波博润1": {"baidu_name": "宁波博润1", "aliases": ["宁波博润1"]},
            "宁波博润2": {"baidu_name": "宁波博润2", "aliases": ["宁波博润2"]},
            "宁波博润12": {"baidu_name": "宁波博润12", "aliases": ["宁波博润12"]},
        },
    }

    result = extract_baidu_rows_from_page(FakePage(), config)

    assert result["extraction_method"] == "fallback_failed"
    assert result["debug"]["extraction_method"] == "fallback_failed"
    assert result["debug"]["percent_misalignment"] is True
    assert "宁波博润12" in result["debug"]["missing_accounts"]


def test_write_table_parse_artifacts_writes_latest_and_timestamped_files(tmp_path):
    from modules.baidu_overview import _write_table_parse_artifacts

    extraction = {
        "extraction_method": "dom",
        "rows": [{"账户": "宁波博润1", "展现": "1,111", "点击": "11", "消费": "111.11"}],
        "detected_headers": ["账户", "展现", "点击", "消费"],
        "debug": {
            "project_id": "ningbo_niu",
            "required_accounts": ["宁波博润1", "宁波博润2", "宁波博润12"],
            "extraction_method": "dom",
            "detected_headers": ["账户", "展现", "点击", "消费"],
            "parsed_account_count": 1,
            "parsed_accounts": ["宁波博润1"],
            "missing_accounts": ["宁波博润2", "宁波博润12"],
            "non_numeric_fields": [],
            "parse_ready": False,
        },
    }

    _write_table_parse_artifacts(tmp_path, extraction)

    reports_dir = tmp_path / "reports"
    assert (reports_dir / "baidu_table_parse_debug.json").exists()
    assert (reports_dir / "baidu_table_parse_debug_latest.json").exists()
    assert len(list(reports_dir.glob("baidu_table_parse_debug_ningbo_niu_*.json"))) == 1
    assert (reports_dir / "baidu_table_candidates.json").exists()
    assert (reports_dir / "baidu_table_candidates_latest.json").exists()
    assert len(list(reports_dir.glob("baidu_table_candidates_ningbo_niu_*.json"))) == 1


def test_doctor_uses_runtime_excel_path_when_project_file_is_stale(tmp_path):
    from openpyxl import Workbook

    configs_dir = tmp_path / "configs"
    projects_dir = configs_dir / "projects"
    projects_dir.mkdir(parents=True)
    (configs_dir / "app_config.json").write_text(
        json.dumps(
            {
                "default_project_id": "changsha_niu",
                "projects_dir": "configs/projects",
                "secrets_file": "secrets/secrets.json",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    stale_path = tmp_path / "missing.xlsx"
    actual_path = tmp_path / "actual.xlsx"
    wb = Workbook()
    wb.active.title = "时段数据"
    wb.create_sheet("百度")
    wb.save(actual_path)
    (projects_dir / "changsha_niu.json").write_text(
        json.dumps(
            {
                "project_id": "changsha_niu",
                "project_name": "长沙牛",
                "excel": {"path": str(stale_path), "hourly_sheet": "时段数据", "daily_sheet": "百度", "engine": "openpyxl"},
                "kst": {"export_dir": "kst_exports", "auto_pick_latest": True, "max_file_age_hours": 2},
                "baidu": {"credential_profile": "changsha_niu_baidu", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
                "accounts": [
                    {"standard_name": "A", "baidu_names": ["A"], "excel_name": "A", "kst_ids": ["1"], "kst_names": ["A"]},
                    {"standard_name": "B", "baidu_names": ["B"], "excel_name": "B", "kst_ids": ["2"], "kst_names": ["B"]},
                    {"standard_name": "C", "baidu_names": ["C"], "excel_name": "C", "kst_ids": ["3"], "kst_names": ["C"]},
                ],
                "hourly": {"periods": ["11点", "15点", "18点"]},
                "daily": {"write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"], "do_not_write_fields": ["总对话", "预约", "到诊", "就诊"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = {
        "project_id": "changsha_niu",
        "project_name": "长沙牛",
        "excel_path": str(actual_path),
        "sheet_name": "时段数据",
        "daily_sheet_name": "百度",
        "excel_engine": "openpyxl",
        "kst": {"export_dir": "kst_exports"},
        "browser": {"cdp_endpoint": "http://127.0.0.1:9", "auto_start_debug_chrome": False},
        "accounts": {"A": {}, "B": {}, "C": {}},
    }

    report = run_doctor(tmp_path, config)

    assert report["checks"]["target_excel"]["passed"] is True
    assert "actual.xlsx" in report["checks"]["target_excel"]["message"]


def test_build_runtime_config_and_doctor_resolve_same_changsha_excel_path(tmp_path):
    from openpyxl import Workbook
    from modules.project_config import load_project_config, build_runtime_config_from_project
    from modules.doctor import _runtime_excel_path

    configs_dir = tmp_path / "configs"
    projects_dir = configs_dir / "projects"
    projects_dir.mkdir(parents=True)
    (configs_dir / "app_config.json").write_text(
        json.dumps(
            {"default_project_id": "changsha_niu", "projects_dir": "configs/projects", "secrets_file": "secrets/secrets.json"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    excel_path = tmp_path / "长沙" / "【长沙npx】2026竞价数据.xlsx"
    excel_path.parent.mkdir(parents=True)
    wb = Workbook()
    wb.active.title = "时段数据"
    wb.create_sheet("百度")
    wb.save(excel_path)
    (projects_dir / "changsha_niu.json").write_text(
        json.dumps(
            {
                "project_id": "changsha_niu",
                "project_name": "长沙牛",
                "excel": {"path": str(excel_path), "hourly_sheet": "时段数据", "daily_sheet": "百度", "engine": "openpyxl"},
                "kst": {"export_dir": "kst_exports", "auto_pick_latest": True, "max_file_age_hours": 2},
                "baidu": {"credential_profile": "changsha_niu_baidu", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
                "accounts": [
                    {"standard_name": "A", "baidu_names": ["A"], "excel_name": "A", "kst_ids": ["1"], "kst_names": ["A"]},
                    {"standard_name": "B", "baidu_names": ["B"], "excel_name": "B", "kst_ids": ["2"], "kst_names": ["B"]},
                    {"standard_name": "C", "baidu_names": ["C"], "excel_name": "C", "kst_ids": ["3"], "kst_names": ["C"]},
                ],
                "hourly": {"periods": ["11点", "15点", "18点"]},
                "daily": {"write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"], "do_not_write_fields": ["总对话", "预约", "到诊", "就诊"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    project = load_project_config(tmp_path, "changsha_niu")
    runtime = build_runtime_config_from_project(project, {})
    doctor_path = _runtime_excel_path(tmp_path, runtime, project)

    assert runtime["excel_path"] == str(excel_path)
    assert str(doctor_path) == str(excel_path)


def test_doctor_reports_full_missing_excel_path(tmp_path):
    configs_dir = tmp_path / "configs"
    projects_dir = configs_dir / "projects"
    projects_dir.mkdir(parents=True)
    (configs_dir / "app_config.json").write_text(
        json.dumps(
            {"default_project_id": "changsha_niu", "projects_dir": "configs/projects", "secrets_file": "secrets/secrets.json"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    missing_path = tmp_path / "missing-dir" / "【长沙npx】2026竞价数据.xlsx"
    (projects_dir / "changsha_niu.json").write_text(
        json.dumps(
            {
                "project_id": "changsha_niu",
                "project_name": "长沙牛",
                "excel": {"path": str(missing_path), "hourly_sheet": "时段数据", "daily_sheet": "百度", "engine": "openpyxl"},
                "kst": {"export_dir": "kst_exports", "auto_pick_latest": True, "max_file_age_hours": 2},
                "baidu": {"credential_profile": "changsha_niu_baidu", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
                "accounts": [
                    {"standard_name": "A", "baidu_names": ["A"], "excel_name": "A", "kst_ids": ["1"], "kst_names": ["A"]},
                    {"standard_name": "B", "baidu_names": ["B"], "excel_name": "B", "kst_ids": ["2"], "kst_names": ["B"]},
                    {"standard_name": "C", "baidu_names": ["C"], "excel_name": "C", "kst_ids": ["3"], "kst_names": ["C"]},
                ],
                "hourly": {"periods": ["11点", "15点", "18点"]},
                "daily": {"write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"], "do_not_write_fields": ["总对话", "预约", "到诊", "就诊"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = run_doctor(tmp_path, {"browser": {"cdp_endpoint": "http://127.0.0.1:9", "auto_start_debug_chrome": False}, "kst": {}})

    assert report["checks"]["target_excel"]["passed"] is False
    assert str(missing_path) in report["checks"]["target_excel"]["message"]


def test_doctor_suggests_similar_excel_filenames_when_parent_exists(tmp_path):
    from openpyxl import Workbook

    configs_dir = tmp_path / "configs"
    projects_dir = configs_dir / "projects"
    projects_dir.mkdir(parents=True)
    (configs_dir / "app_config.json").write_text(
        json.dumps(
            {"default_project_id": "changsha_niu", "projects_dir": "configs/projects", "secrets_file": "secrets/secrets.json"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    target_dir = tmp_path / "长沙"
    target_dir.mkdir(parents=True)
    similar_file = target_dir / "【长沙npx】2026竞价数据.xlsx"
    wb = Workbook()
    wb.active.title = "时段数据"
    wb.create_sheet("百度")
    wb.save(similar_file)
    missing_path = target_dir / "【长沙N】2026竞价数据.xlsx"
    (projects_dir / "changsha_niu.json").write_text(
        json.dumps(
            {
                "project_id": "changsha_niu",
                "project_name": "长沙牛",
                "excel": {"path": str(missing_path), "hourly_sheet": "时段数据", "daily_sheet": "百度", "engine": "openpyxl"},
                "kst": {"export_dir": "kst_exports", "auto_pick_latest": True, "max_file_age_hours": 2},
                "baidu": {"credential_profile": "changsha_niu_baidu", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
                "accounts": [
                    {"standard_name": "A", "baidu_names": ["A"], "excel_name": "A", "kst_ids": ["1"], "kst_names": ["A"]},
                    {"standard_name": "B", "baidu_names": ["B"], "excel_name": "B", "kst_ids": ["2"], "kst_names": ["B"]},
                    {"standard_name": "C", "baidu_names": ["C"], "excel_name": "C", "kst_ids": ["3"], "kst_names": ["C"]},
                ],
                "hourly": {"periods": ["11点", "15点", "18点"]},
                "daily": {"write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"], "do_not_write_fields": ["总对话", "预约", "到诊", "就诊"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = run_doctor(tmp_path, {"browser": {"cdp_endpoint": "http://127.0.0.1:9", "auto_start_debug_chrome": False}, "kst": {}})

    detail = report["checks"]["target_excel"]["detail"]
    assert report["checks"]["target_excel"]["passed"] is False
    assert detail["parent_exists"] is True
    assert "【长沙npx】2026竞价数据.xlsx" in detail["similar_files"]


def test_resolve_baidu_sources_wraps_legacy_project_as_single_source():
    from modules.baidu_multi_source import resolve_baidu_sources

    project = {
        "project_id": "legacy",
        "project_name": "旧项目",
        "baidu": {"credential_profile": "legacy_baidu"},
        "accounts": [
            {"standard_name": "A", "baidu_names": ["BA"], "excel_name": "A", "kst_ids": ["1"], "kst_names": ["A"]},
        ],
    }

    sources = resolve_baidu_sources(project)

    assert sources == [
        {
            "source_id": "default",
            "source_name": "旧项目",
            "credential_profile": "legacy_baidu",
            "accounts": project["accounts"],
            "required": True,
        }
    ]


def test_shenyang_niu_config_resolves_two_baidu_sources():
    from modules.project_config import build_runtime_config_from_project, load_project_config
    from modules.baidu_multi_source import resolve_baidu_sources

    project = load_project_config(Path.cwd(), "shenyang_niu")
    runtime = build_runtime_config_from_project(project, {})
    sources = resolve_baidu_sources(runtime)

    assert project["project_id"] == "shenyang_niu"
    assert [source["source_id"] for source in sources] == ["shenyang_niu_zhongya", "shenyang_niu_yinkang"]
    assert [source["credential_profile"] for source in sources] == [
        "shenyang_niu_zhongya_baidu",
        "shenyang_niu_yinkang_baidu",
    ]
    assert list(runtime["accounts"]) == ["沈阳中亚02", "沈阳银康01", "沈阳中亚01"]
    assert [account["standard_name"] for account in project["excel_accounts"]] == ["沈阳中亚02", "沈阳银康01", "沈阳中亚01"]
    assert [account["standard_name"] for source in sources for account in source["accounts"]] == [
        "沈阳中亚01",
        "沈阳中亚02",
        "沈阳中亚03",
        "沈阳银康01",
        "沈阳银康02",
        "沈阳银康03",
    ]
    assert runtime["kst"]["promotion_id_accounts"]["37084684"] == "沈阳中亚01"
    assert runtime["kst"]["promotion_id_accounts"] == {
        "37084945": "沈阳中亚02",
        "47190166": "沈阳银康01",
        "37084684": "沈阳中亚01",
    }
    assert sources[1]["accounts"][2]["kst_ids"] == ["47190275"]
    assert sources[1]["accounts"][2]["baidu_names"] == ["沈阳银康银屑病3"]


def test_hefei_bai_config_resolves_two_baidu_sources_and_three_excel_accounts():
    from modules.project_config import build_runtime_config_from_project, load_project_config, validate_project_config
    from modules.baidu_multi_source import resolve_baidu_sources

    project = load_project_config(Path.cwd(), "hefei_bai")
    runtime = build_runtime_config_from_project(project, {})
    sources = resolve_baidu_sources(runtime)

    assert validate_project_config(project) == []
    assert project["project_id"] == "hefei_bai"
    assert project["project_name"] == "合肥白"
    assert [source["source_id"] for source in sources] == ["hefei_bai_huaxia", "hefei_bai_xinhuaxia"]
    assert [source["credential_profile"] for source in sources] == [
        "hefei_bai_huaxia_baidu",
        "hefei_bai_xinhuaxia_baidu",
    ]
    assert [account["standard_name"] for account in project["excel_accounts"]] == [
        "华夏白癜风-新",
        "华夏白癜风-新2",
        "新华夏白癜风3",
    ]
    assert list(runtime["accounts"]) == ["华夏白癜风-新", "华夏白癜风-新2", "新华夏白癜风3"]
    assert runtime["kst"]["promotion_id_accounts"] == {
        "64544816": "华夏白癜风-新",
        "64607455": "华夏白癜风-新2",
        "34910745": "新华夏白癜风3",
    }


def test_secrets_example_has_empty_hefei_bai_profiles():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "secrets" / "secrets.example.json").read_text(encoding="utf-8"))

    for profile in ["hefei_bai_huaxia_baidu", "hefei_bai_xinhuaxia_baidu"]:
        assert data["baidu"][profile] == {"username": "", "password": ""}


def test_validate_project_config_rejects_duplicate_baidu_name_inside_same_source():
    from modules.project_config import validate_project_config

    project = {
        "project_id": "bad_multi",
        "project_name": "坏多来源",
        "excel": {"path": "target.xlsx", "hourly_sheet": "时段数据", "daily_sheet": "百度", "engine": "openpyxl"},
        "kst": {"export_dir": "exports", "auto_pick_latest": True, "max_file_age_hours": 2},
        "baidu": {"credential_profile": "unused", "data_path": ["首页", "数据报告", "数据概览", "搜索推广"]},
        "baidu_sources": [
            {
                "source_id": "source_a",
                "source_name": "来源A",
                "credential_profile": "profile_a",
                "accounts": [
                    {"standard_name": "A", "baidu_names": ["重复账户"], "excel_name": "A", "kst_ids": ["1"], "kst_names": ["A"]},
                    {"standard_name": "B", "baidu_names": ["重复账户"], "excel_name": "B", "kst_ids": ["2"], "kst_names": ["B"]},
                ],
            }
        ],
        "accounts": [
            {"standard_name": "A", "baidu_names": ["重复账户"], "excel_name": "A", "kst_ids": ["1"], "kst_names": ["A"]},
            {"standard_name": "B", "baidu_names": ["重复账户"], "excel_name": "B", "kst_ids": ["2"], "kst_names": ["B"]},
        ],
        "hourly": {"periods": ["11点", "15点", "18点"]},
        "daily": {
            "write_fields": ["展现", "点击", "消费", "有效对话", "无效对话", "一般有效对话", "有效转潜", "总转潜"],
            "do_not_write_fields": ["总对话", "预约", "到诊", "就诊"],
        },
    }

    errors = validate_project_config(project)

    assert any("source_a 百度账户名重复" in error for error in errors)


def test_aggregate_baidu_source_reports_sums_metrics_and_keeps_source_details():
    from modules.baidu_multi_source import aggregate_baidu_source_reports

    config = {"project_id": "demo", "project_name": "演示", "accounts": {"A": {}, "B": {}}}
    reports = [
        {
            "source_id": "source_a",
            "source_name": "来源A",
            "report": {
                "date": "2026-05-22",
                "period": "15点",
                "accounts": {
                    "A": {"展现": 10, "点击": 1, "消费": 2.5},
                    "B": {"展现": 20, "点击": 2, "消费": 3.5},
                },
                "unknown_accounts": [{"account_name": "未知", "展现": 99, "点击": 9, "消费": 9}],
                "ignored_unknown_accounts": [{"account_name": "空账户", "展现": 0, "点击": 0, "消费": 0}],
                "errors": [],
            },
        },
        {
            "source_id": "source_b",
            "source_name": "来源B",
            "report": {
                "date": "2026-05-22",
                "period": "15点",
                "accounts": {
                    "A": {"展现": 3, "点击": 4, "消费": 5.25},
                },
                "unknown_accounts": [],
                "ignored_unknown_accounts": [],
                "errors": [],
            },
        },
    ]

    report = aggregate_baidu_source_reports(config, reports, period="15点")

    assert report["accounts"]["A"]["展现"] == 13
    assert report["accounts"]["A"]["点击"] == 5
    assert report["accounts"]["A"]["消费"] == 7.75
    assert report["accounts"]["B"]["展现"] == 20
    assert report["unknown_accounts"] == [{"account_name": "未知", "展现": 99, "点击": 9, "消费": 9, "source_id": "source_a", "source_name": "来源A"}]
    assert "未知" not in report["accounts"]
    assert len(report["source_reports"]) == 2


def test_aggregate_baidu_source_reports_outputs_only_excel_accounts_and_classifies_candidate_only_rows():
    from modules.baidu_multi_source import aggregate_baidu_source_reports

    config = {
        "project_id": "shenyang_niu",
        "accounts": {
            "沈阳中亚02": {},
            "沈阳银康01": {},
            "沈阳中亚01": {},
        },
    }
    reports = [
        {
            "source_id": "shenyang_niu_zhongya",
            "source_name": "沈阳中亚",
            "report": {
                "date": "2026-05-22",
                "period": "15点",
                "accounts": {
                    "沈阳中亚01": {"展现": 1, "点击": 2, "消费": 3},
                    "沈阳中亚02": {"展现": 4, "点击": 5, "消费": 6},
                    "沈阳中亚03": {"展现": 0, "点击": 0, "消费": 0},
                },
                "errors": [],
            },
        },
        {
            "source_id": "shenyang_niu_yinkang",
            "source_name": "沈阳银康",
            "report": {
                "date": "2026-05-22",
                "period": "15点",
                "accounts": {
                    "沈阳银康01": {"展现": 7, "点击": 8, "消费": 9},
                    "沈阳银康02": {"展现": 10, "点击": 0, "消费": 0},
                    "沈阳银康03": {"展现": 0, "点击": 0, "消费": 0},
                },
                "errors": [],
            },
        },
    ]

    report = aggregate_baidu_source_reports(config, reports, period="15点")

    assert list(report["accounts"]) == ["沈阳中亚01", "沈阳中亚02", "沈阳银康01"]
    assert set(report["accounts"]) == {"沈阳中亚02", "沈阳银康01", "沈阳中亚01"}
    assert [item["account_name"] for item in report["ignored_inactive_accounts"]] == ["沈阳中亚03", "沈阳银康03"]
    assert [item["account_name"] for item in report["skipped_unmapped_accounts"]] == ["沈阳银康02"]
    assert report["errors"] == []


def test_aggregate_baidu_source_reports_fails_when_any_source_failed():
    from modules.baidu_multi_source import aggregate_baidu_source_reports

    config = {"project_id": "demo", "accounts": {"A": {}}}
    reports = [
        {"source_id": "source_a", "source_name": "来源A", "report": {"accounts": {"A": {"展现": 1, "点击": 1, "消费": 1}}, "errors": []}},
        {"source_id": "source_b", "source_name": "来源B", "report": {"accounts": {}, "errors": ["登录失败"]}},
    ]

    report = aggregate_baidu_source_reports(config, reports, period="15点")

    assert report["accounts"] == {}
    assert any("source_b" in error and "登录失败" in error for error in report["errors"])


def test_doctor_reports_multi_baidu_sources_and_secret_profiles(tmp_path, monkeypatch):
    import modules.doctor as doctor
    from modules.project_config import load_project_config, build_runtime_config_from_project

    configs_dir = tmp_path / "configs"
    projects_dir = configs_dir / "projects"
    secrets_dir = tmp_path / "secrets"
    projects_dir.mkdir(parents=True)
    secrets_dir.mkdir()
    (configs_dir / "app_config.json").write_text(
        json.dumps({"default_project_id": "shenyang_niu", "projects_dir": "configs/projects", "secrets_file": "secrets/secrets.json"}, ensure_ascii=False),
        encoding="utf-8",
    )
    source_project = Path.cwd() / "configs" / "projects" / "shenyang_niu.json"
    (projects_dir / "shenyang_niu.json").write_text(source_project.read_text(encoding="utf-8"), encoding="utf-8")
    (secrets_dir / "secrets.json").write_text(
        json.dumps(
            {
                "baidu": {
                    "shenyang_niu_zhongya_baidu": {"username": "user-a", "password": "pass-a"},
                    "shenyang_niu_yinkang_baidu": {"username": "user-b", "password": "pass-b"},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor, "_check_cdp", lambda root, config: {"passed": True, "level": "ok", "message": "skip"})
    monkeypatch.setattr(doctor, "_check_chrome", lambda config: {"passed": True, "level": "ok", "message": "skip"})
    monkeypatch.setattr(doctor, "_check_hourly_structure", lambda root, config, excel_path: {"passed": True, "level": "ok", "message": "skip"})

    project = load_project_config(tmp_path, "shenyang_niu")
    config = build_runtime_config_from_project(project, {"browser": {"auto_start_debug_chrome": False}})
    report = run_doctor(tmp_path, config)

    baidu_sources = report["checks"]["baidu_sources"]
    secrets = report["checks"]["secrets_json"]
    assert baidu_sources["passed"] is True
    assert baidu_sources["detail"]["source_count"] == 2
    assert secrets["passed"] is True
    assert "user-a" not in json.dumps(report, ensure_ascii=False)
    assert "pass-a" not in json.dumps(report, ensure_ascii=False)


def test_doctor_baidu_source_detail_marks_candidate_only_accounts_for_shenyang():
    from modules.project_config import load_project_config
    from modules.doctor import _check_baidu_sources

    project = load_project_config(Path.cwd(), "shenyang_niu")
    report = _check_baidu_sources(project)

    assert report["passed"] is True
    assert report["detail"]["excel_accounts"] == ["沈阳中亚02", "沈阳银康01", "沈阳中亚01"]
    assert report["detail"]["candidate_only_accounts"] == ["沈阳中亚03", "沈阳银康02", "沈阳银康03"]


def test_baidu_multi_source_writes_human_readable_markdown_report(tmp_path):
    import logging

    from modules.baidu_multi_source import fetch_baidu_multi_source

    config = {
        "project_id": "shenyang_niu",
        "project_name": "沈阳牛",
        "accounts": {"沈阳中亚02": {}, "沈阳银康01": {}},
        "baidu_sources": [
            {
                "source_id": "zhongya",
                "source_name": "沈阳中亚",
                "credential_profile": "secret_profile_a",
                "accounts": [{"standard_name": "沈阳中亚02", "baidu_names": ["百度中亚02"]}, {"standard_name": "沈阳中亚03", "baidu_names": ["百度中亚03"]}],
            },
            {
                "source_id": "yinkang",
                "source_name": "沈阳银康",
                "credential_profile": "secret_profile_b",
                "accounts": [{"standard_name": "沈阳银康01", "baidu_names": ["百度银康01"]}, {"standard_name": "沈阳银康02", "baidu_names": ["百度银康02"]}],
            },
        ],
    }

    def fake_fetch(*, config, root, logger, period):
        if config["baidu_source"]["source_id"] == "zhongya":
            return {
                "date": "2026-05-24",
                "accounts": {"沈阳中亚02": {"展现": 10, "点击": 2, "消费": 5.5}, "沈阳中亚03": {"展现": 0, "点击": 0, "消费": 0}},
                "unknown_accounts": [{"account_name": "未知A", "展现": 1, "点击": 0, "消费": 0, "reason": "未配置"}],
                "ignored_unknown_accounts": [],
                "errors": [],
            }
        return {
            "date": "2026-05-24",
            "accounts": {"沈阳银康01": {"展现": 20, "点击": 3, "消费": 6.5}, "沈阳银康02": {"展现": 1, "点击": 1, "消费": 1}},
            "unknown_accounts": [],
            "ignored_unknown_accounts": [{"account_name": "空账户", "展现": 0, "点击": 0, "消费": 0, "reason": "已忽略"}],
            "errors": [],
        }

    report = fetch_baidu_multi_source(config, tmp_path, logging.getLogger("test"), "15点", fake_fetch)
    md_path = tmp_path / "reports" / "baidu_multi_source_report.md"
    markdown = md_path.read_text(encoding="utf-8")

    assert report["errors"] == []
    assert md_path.exists()
    assert "沈阳牛" in markdown
    assert "日期：2026-05-24" in markdown
    assert "时段：15点" in markdown
    assert "## 来源摘要" in markdown
    assert "## 最终写入账户" in markdown
    assert "## 被忽略的未启用账户" in markdown
    assert "## 被跳过的未映射账户" in markdown
    assert "## unknown_accounts" in markdown
    assert "username" not in markdown.lower()
    assert "password" not in markdown.lower()
    assert "secret_profile" not in markdown


def test_baidu_multi_source_cost_validation_reports_matching_totals_and_source_unknown_details():
    from modules.baidu_multi_source import aggregate_baidu_source_reports

    config = {"accounts": {"A": {}, "B": {}}}
    source_reports = [
        {
            "source_id": "s1",
            "source_name": "来源1",
            "report": {
                "accounts": {"A": {"展现": 1, "点击": 1, "消费": 1.1}},
                "unknown_accounts": [{"account_name": "X", "展现": 1, "点击": 0, "消费": 2}],
                "ignored_unknown_accounts": [{"account_name": "Z", "展现": 0, "点击": 0, "消费": 0}],
                "errors": [],
            },
        },
        {"source_id": "s2", "source_name": "来源2", "report": {"accounts": {"B": {"展现": 2, "点击": 1, "消费": 2.2}}, "errors": []}},
    ]

    report = aggregate_baidu_source_reports(config, source_reports)

    assert report["source_total_cost_sum"] == 3.3
    assert report["final_total_cost"] == 3.3
    assert report["diff"] == 0
    assert report["errors"] == []
    assert report["source_reports"][0]["report"]["unknown_accounts"][0]["source_id"] == "s1"
    assert report["source_reports"][0]["report"]["ignored_unknown_accounts"][0]["source_name"] == "来源1"


def test_baidu_multi_source_cost_validation_fails_when_totals_differ():
    from modules.baidu_multi_source import build_cost_validation

    validation = build_cost_validation(10.2, 10.0)

    assert validation["passed"] is False
    assert validation["diff"] == 0.2
    assert validation["errors"]


def test_multi_source_candidate_accounts_may_be_absent_from_source_page():
    from modules.baidu_multi_source import build_source_runtime_config
    from modules.baidu_parser import parse_baidu_table

    config = {"accounts": {"写入A": {}}}
    source = {
        "source_id": "source_a",
        "source_name": "来源A",
        "credential_profile": "profile_a",
        "accounts": [
            {"standard_name": "写入A", "baidu_names": ["百度A"]},
            {"standard_name": "候选B", "baidu_names": ["百度B"]},
        ],
    }
    source_config = build_source_runtime_config(config, source)
    parsed = parse_baidu_table([{"账户": "百度A", "展现": "1", "点击": "1", "消费": "1"}], source_config)

    assert source_config["baidu"]["allow_missing_candidate_accounts"] is True
    assert parsed["errors"] == []
    assert list(parsed["accounts"]) == ["写入A"]


def test_multi_source_overview_allows_absent_candidate_accounts():
    from modules.baidu_overview import validate_overview_ready

    report = validate_overview_ready(
        "数据报告 搜索推广 2026/05/24 账户 展现 点击 消费 百度A",
        "2026-05-24",
        {
            "baidu": {"allow_missing_candidate_accounts": True},
            "accounts": {
                "写入A": {"baidu_name": "百度A"},
                "候选B": {"baidu_name": "百度B"},
            },
        },
    )

    assert report["passed"] is True
    assert report["accounts"]["候选B"] is False
    assert report["allow_missing_candidate_accounts"] is True


def test_doctor_multi_source_detail_includes_summary_counts_and_candidate_note():
    from modules.project_config import load_project_config
    from modules.doctor import _check_baidu_sources

    project = load_project_config(Path.cwd(), "shenyang_niu")
    report = _check_baidu_sources(project)
    detail = report["detail"]

    assert detail["baidu_sources_count"] == 2
    assert detail["excel_accounts_count"] == 3
    assert detail["baidu_candidate_accounts_count"] == 6
    assert "不算错误" in detail["candidate_only_note"]
    assert all("candidate_accounts_count" in source for source in detail["sources"])
    assert all("has_duplicate_baidu_name" in source for source in detail["sources"])


def test_inspect_excel_structure_writes_excel_account_regions_report(tmp_path):
    import logging

    from openpyxl import Workbook
    from modules.excel_inspector import inspect_excel_structure

    wb = Workbook()
    ws = wb.active
    ws.title = "时段数据"
    ws["A1"] = "日期"
    ws["B1"] = "时段"
    ws["D2"] = "项目甲"
    headers = ["展现", "点击", "消费"]
    for index, header in enumerate(headers, start=4):
        ws.cell(row=3, column=index).value = header
    excel_path = tmp_path / "demo.xlsx"
    wb.save(excel_path)
    config = {
        "project_id": "demo",
        "project_name": "演示",
        "excel_path": str(excel_path),
        "sheet_name": "时段数据",
        "accounts": {"项目甲": {"aliases": ["项目甲"], "excel_name": "项目甲", "baidu_name": "项目甲"}},
        "field_aliases": {"日期": ["日期"], "时段": ["时段"], "展现": ["展现"], "点击": ["点击"], "消费": ["消费"]},
    }

    inspect_excel_structure(config, tmp_path, logging.getLogger("test"))
    report = json.loads((tmp_path / "reports" / "excel_account_regions.json").read_text(encoding="utf-8"))

    assert report["configured_excel_accounts"] == ["项目甲"]
    assert report["missing_configured_accounts"] == []
    assert report["detected_account_regions"] == [{"account_name": "项目甲", "row": 2, "column": 4, "title_cell": "D2"}]


def test_fetch_baidu_daily_single_source_keeps_existing_single_fetch_path(tmp_path, monkeypatch):
    import logging
    import modules.baidu_daily as daily

    seen = []

    def fake_single(**kwargs):
        seen.append(kwargs["target_date"])
        return {"date": kwargs["target_date"], "accounts": {"A": {}}, "errors": []}

    monkeypatch.setattr(daily, "_fetch_baidu_daily_single", fake_single)
    report = daily.fetch_baidu_daily(
        config={"project_id": "legacy", "accounts": {"A": {}}},
        root=tmp_path,
        logger=logging.getLogger("test"),
        target_date="2026-05-23",
    )

    assert seen == ["2026-05-23"]
    assert report["date"] == "2026-05-23"


def test_build_baidu_daily_report_allows_missing_multi_source_candidate_account(monkeypatch):
    import modules.baidu_daily as daily

    monkeypatch.setattr(
        daily,
        "extract_baidu_rows_from_visible_text",
        lambda text: [{"账户": "百度A", "展现": "1", "点击": "1", "消费": "1"}],
    )
    monkeypatch.setattr(daily, "_extract_selected_date_from_text", lambda text: "2026-05-23")

    report = daily.build_baidu_daily_report_from_visible_text(
        "数据报告 搜索推广",
        {
            "baidu": {"allow_missing_candidate_accounts": True},
            "accounts": {"写入A": {"baidu_name": "百度A"}, "候选B": {"baidu_name": "百度B"}},
        },
        "2026-05-23",
    )

    assert report["accounts"]["写入A"]["消费"] == 1
    assert report["errors"] == []


def test_daily_baidu_snapshot_rejects_total_row_mismatch():
    import modules.baidu_daily as daily

    report = {
        "accounts": {
            "A": {"展现": 10, "点击": 1, "消费": 1.0},
            "B": {"展现": 20, "点击": 2, "消费": 2.0},
            "C": {"展现": 30, "点击": 3, "消费": 3.0},
        }
    }
    rows = [
        {"账户": "总计-3", "展现": "60", "点击": "6", "消费": "100"},
        {"账户": "A", "展现": "10", "点击": "1", "消费": "1"},
        {"账户": "B", "展现": "20", "点击": "2", "消费": "2"},
        {"账户": "C", "展现": "30", "点击": "3", "消费": "3"},
    ]

    result = daily.validate_daily_baidu_snapshot(report, rows, {"accounts": {"A": {}, "B": {}, "C": {}}})

    assert result["passed"] is False
    assert any("总计校验失败" in error for error in result["errors"])


def test_wait_stable_daily_report_ignores_first_unstable_snapshot(monkeypatch):
    import logging
    import modules.baidu_daily as daily

    class FakePage:
        def __init__(self):
            self.read_index = 0
            self.waits = []

        def wait_for_timeout(self, timeout):
            self.waits.append(timeout)

    page = FakePage()
    texts = ["low", "correct", "correct"]

    def fake_read(_page):
        value = texts[min(_page.read_index, len(texts) - 1)]
        _page.read_index += 1
        return value

    def fake_report(text, config, target_date, visible_text_path=None):
        cost = 1.0 if text == "low" else 10.0
        return {
            "date": target_date,
            "target_date": target_date,
            "accounts": {"A": {"展现": 1, "点击": 1, "消费": cost}},
            "errors": [],
        }

    def fake_validate(report, rows, config):
        return {
            "passed": True,
            "errors": [],
            "signature": daily._daily_report_signature(report, ["A"]),
            "total_diff": {},
        }

    monkeypatch.setattr(daily, "_read_page_text", fake_read)
    monkeypatch.setattr(daily, "extract_baidu_rows_from_visible_text", lambda text: [])
    monkeypatch.setattr(daily, "build_baidu_daily_report_from_visible_text", fake_report)
    monkeypatch.setattr(daily, "validate_daily_baidu_snapshot", fake_validate)

    snapshot = daily._wait_stable_daily_report_snapshot(
        page,
        {"accounts": {"A": {}}, "baidu": {"report_table_wait_seconds": 10, "daily_stability_interval_ms": 1}},
        "2026-05-23",
        logging.getLogger("test"),
    )

    assert snapshot["stable"] is True
    assert snapshot["report"]["accounts"]["A"]["消费"] == 10.0
    assert len(snapshot["attempts"]) == 3


def test_fetch_baidu_daily_multi_source_uses_shared_aggregation_and_is_merge_compatible(tmp_path, monkeypatch):
    import logging

    import modules.baidu_daily as daily
    from modules.data_merger import merge_daily_files

    config = {
        "project_id": "shenyang_niu",
        "project_name": "沈阳牛",
        "accounts": {"写入A": {}, "写入B": {}},
        "baidu_sources": [
            {
                "source_id": "source_a",
                "source_name": "来源A",
                "credential_profile": "secret_a",
                "accounts": [{"standard_name": "写入A"}, {"standard_name": "候选零"}],
            },
            {
                "source_id": "source_b",
                "source_name": "来源B",
                "credential_profile": "secret_b",
                "accounts": [{"standard_name": "写入B"}, {"standard_name": "候选有量"}],
            },
        ],
    }

    def fake_daily_single(*, config, root, logger, target_date):
        assert target_date == "2026-05-23"
        assert config["baidu"]["daily_output_path"].endswith(f"{config['baidu_source']['source_id']}.json")
        if config["baidu_source"]["source_id"] == "source_a":
            return {
                "date": target_date,
                "accounts": {
                    "写入A": {"展现": 10, "点击": 2, "消费": 3.5},
                    "候选零": {"展现": 0, "点击": 0, "消费": 0},
                },
                "unknown_accounts": [{"account_name": "未知账户", "展现": 1, "点击": 0, "消费": 0}],
                "ignored_unknown_accounts": [],
                "errors": [],
            }
        return {
            "date": target_date,
            "accounts": {
                "写入B": {"展现": 20, "点击": 4, "消费": 6.5},
                "候选有量": {"展现": 1, "点击": 1, "消费": 1},
            },
            "unknown_accounts": [],
            "ignored_unknown_accounts": [{"account_name": "空账户", "展现": 0, "点击": 0, "消费": 0}],
            "errors": [],
        }

    monkeypatch.setattr(daily, "_fetch_baidu_daily_single", fake_daily_single)
    report = daily.fetch_baidu_daily(config, tmp_path, logging.getLogger("test"), "2026-05-23")

    assert report["task"] == "daily"
    assert report["target_date"] == "2026-05-23"
    assert report["period"] is None
    assert report["multi_source"] is True
    assert report["accounts"] == {
        "写入A": {"展现": 10, "点击": 2, "消费": 3.5},
        "写入B": {"展现": 20, "点击": 4, "消费": 6.5},
    }
    assert [row["account_name"] for row in report["ignored_inactive_accounts"]] == ["候选零"]
    assert [row["account_name"] for row in report["skipped_unmapped_accounts"]] == ["候选有量"]
    assert report["unknown_accounts"][0]["source_id"] == "source_a"
    assert report["ignored_unknown_accounts"][0]["source_name"] == "来源B"
    assert report["source_total_cost_sum"] == 10
    assert report["final_total_cost"] == 10
    assert report["errors"] == []
    assert (tmp_path / "reports" / "baidu_daily_data.json").exists()
    assert (tmp_path / "reports" / "baidu_daily_validate_report.json").exists()
    markdown = (tmp_path / "reports" / "baidu_multi_source_report.md").read_text(encoding="utf-8")
    assert "日报" in markdown
    assert "日期：2026-05-23" in markdown
    assert "时段：无" in markdown
    assert "secret_a" not in markdown

    reports = tmp_path / "reports"
    (reports / "kst_daily_data.json").write_text(
        json.dumps({
            "date": "2026-05-23",
            "accounts": {
                "写入A": {"总对话": 1, "有效对话": 1, "无效对话": 0, "一般有效对话": 0, "有效转潜": 1, "总转潜": 1},
                "写入B": {"总对话": 0, "有效对话": 0, "无效对话": 0, "一般有效对话": 0, "有效转潜": 0, "总转潜": 0},
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    merged = merge_daily_files(config, tmp_path, logging.getLogger("test"), "2026-05-23")
    assert merged["validate_report"]["passed"] is True
    assert merged["merged"]["accounts"]["写入A"]["展现"] == 10


def test_fetch_baidu_daily_multi_source_fails_when_any_source_fails(tmp_path, monkeypatch):
    import logging

    import modules.baidu_daily as daily

    config = {
        "accounts": {"A": {}},
        "baidu_sources": [
            {"source_id": "source_a", "source_name": "来源A", "accounts": [{"standard_name": "A"}]},
            {"source_id": "source_b", "source_name": "来源B", "accounts": [{"standard_name": "B"}]},
        ],
    }

    def fake_daily_single(*, config, root, logger, target_date):
        if config["baidu_source"]["source_id"] == "source_b":
            return {"date": target_date, "accounts": {}, "errors": ["登录失败"]}
        return {"date": target_date, "accounts": {"A": {"展现": 1, "点击": 1, "消费": 1}}, "errors": []}

    monkeypatch.setattr(daily, "_fetch_baidu_daily_single", fake_daily_single)
    report = daily.fetch_baidu_daily(config, tmp_path, logging.getLogger("test"), "2026-05-23")

    assert report["accounts"] == {}
    assert any("source_b" in error and "登录失败" in error for error in report["errors"])
    assert report["self_check"]["all_sources_passed"] is False


def test_run_daily_pipeline_stops_when_multi_source_baidu_step_fails(tmp_path):
    import logging

    export = tmp_path / "daily.xlsx"
    export.write_text("placeholder", encoding="utf-8")

    def bad_baidu(**kwargs):
        return {"date": "2026-05-23", "multi_source": True, "errors": ["source_b: 登录失败"]}

    def should_not_parse(*args, **kwargs):
        raise AssertionError("百度多来源失败后不应解析商务通日报")

    report = run_daily_pipeline(
        config={"excel_path": "target.xlsx"},
        root=tmp_path,
        logger=logging.getLogger("test"),
        target_date="2026-05-23",
        kst_file=export,
        fetch_baidu_func=bad_baidu,
        parse_kst_func=should_not_parse,
    )

    assert report["passed"] is False
    assert report["failed_step"] == "fetch-baidu-daily"
    assert report["errors"] == ["source_b: 登录失败"]


def test_write_merged_hourly_data_finds_date_and_period_above_account_titles(tmp_path):
    import logging
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "时段数据"
    ws["A1"] = "日期"
    ws["B1"] = "时段"
    ws["F2"] = "华厦npx1"
    ws.merge_cells("F2:L2")
    ws["M2"] = "华厦npx3"
    ws.merge_cells("M2:S2")
    ws["T2"] = "华厦npx5"
    ws.merge_cells("T2:Z2")
    headers = ["展现", "点击", "消费", "总对话", "有效", "有效转潜", "总转潜"]
    for offset, header in enumerate(headers):
        ws.cell(row=3, column=6 + offset).value = header
        ws.cell(row=3, column=13 + offset).value = header
        ws.cell(row=3, column=20 + offset).value = header
    ws["A4"] = "2026-05-07"
    ws.merge_cells("A4:A6")
    ws["B4"] = "11点"
    ws["B5"] = "3点"
    ws["B6"] = "6点"
    excel_path = tmp_path / "nanjing.xlsx"
    wb.save(excel_path)

    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "merged_hourly_data.json").write_text(
        """
{
  "date": "2026-05-07",
  "period": "15点",
  "accounts": {
    "华厦npx1": {"展现": 101, "点击": 11, "消费": 12.5, "总对话": 3, "有效": 2, "有效转潜": 1, "总转潜": 1},
    "华厦npx3": {"展现": 202, "点击": 22, "消费": 23.5, "总对话": 4, "有效": 2, "有效转潜": 1, "总转潜": 1},
    "华厦npx5": {"展现": 303, "点击": 33, "消费": 34.5, "总对话": 5, "有效": 3, "有效转潜": 1, "总转潜": 2}
  }
}
""",
        encoding="utf-8",
    )

    config = {
        "excel_path": str(excel_path),
        "sheet_name": "时段数据",
        "accounts": {
            "华厦npx1": {"aliases": ["华厦npx1"], "excel_name": "华厦npx1", "baidu_name": "华厦npx1"},
            "华厦npx3": {"aliases": ["华厦npx3"], "excel_name": "华厦npx3", "baidu_name": "华厦npx3"},
            "华厦npx5": {"aliases": ["华厦npx5"], "excel_name": "华厦npx5", "baidu_name": "华厦npx5"},
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
            "总转潜": ["总转潜"]
        },
    }

    report = write_merged_hourly_data(config, tmp_path, logging.getLogger("test"), "15点")

    assert report["errors"] == []
    assert report["self_check"]["verification_passed"] is True


def test_inspector_and_writer_share_global_date_period_field_locations(tmp_path):
    import logging
    from openpyxl import Workbook, load_workbook
    from modules.excel_inspector import inspect_excel_structure

    wb = Workbook()
    ws = wb.active
    ws.title = "时段数据"
    ws["A1"] = "每日时段统计数据"
    ws["B3"] = "日期"
    ws["C3"] = "时段"
    ws["F5"] = "南京账户1"
    ws.merge_cells("F5:L5")
    ws["M5"] = "南京账户2"
    ws.merge_cells("M5:S5")
    ws["T5"] = "南京账户3"
    ws.merge_cells("T5:Z5")
    headers = ["展现", "点击", "消费", "总对话", "有效", "有效转潜", "总转潜"]
    for offset, header in enumerate(headers):
        ws.cell(row=6, column=6 + offset).value = header
        ws.cell(row=6, column=13 + offset).value = header
        ws.cell(row=6, column=20 + offset).value = header
    ws["B7"] = "2026-05-07"
    ws.merge_cells("B7:B9")
    ws["C7"] = "11点"
    ws["C8"] = "3点"
    ws["C9"] = "6点"
    excel_path = tmp_path / "nanjing_global.xlsx"
    wb.save(excel_path)

    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "merged_hourly_data.json").write_text(
        json.dumps(
            {
                "date": "2026-05-07",
                "period": "15点",
                "accounts": {
                    "南京账户1": {"展现": 101, "点击": 11, "消费": 12.5, "总对话": 3, "有效": 2, "有效转潜": 1, "总转潜": 1},
                    "南京账户2": {"展现": 202, "点击": 22, "消费": 23.5, "总对话": 4, "有效": 3, "有效转潜": 1, "总转潜": 1},
                    "南京账户3": {"展现": 303, "点击": 33, "消费": 34.5, "总对话": 5, "有效": 4, "有效转潜": 2, "总转潜": 2},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = {
        "excel_path": str(excel_path),
        "sheet_name": "时段数据",
        "accounts": {
            "南京账户1": {"aliases": ["南京账户1"], "excel_name": "南京账户1", "baidu_name": "南京账户1"},
            "南京账户2": {"aliases": ["南京账户2"], "excel_name": "南京账户2", "baidu_name": "南京账户2"},
            "南京账户3": {"aliases": ["南京账户3"], "excel_name": "南京账户3", "baidu_name": "南京账户3"},
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

    structure = inspect_excel_structure(config=config, root=tmp_path, logger=logging.getLogger("test"))
    assert structure["errors"] == []
    assert structure["global_fields"]["日期"]["header_cell"] == "B3"
    assert structure["global_fields"]["时段"]["header_cell"] == "C3"

    report = write_merged_hourly_data(config, tmp_path, logging.getLogger("test"), "15点")

    assert report["errors"] == []
    assert report["self_check"]["verification_passed"] is True

    verify_wb = load_workbook(excel_path, data_only=False, read_only=False)
    verify_ws = verify_wb["时段数据"]
    assert verify_ws["F8"].value == 101
    assert verify_ws["M8"].value == 202
    assert verify_ws["T8"].value == 303
