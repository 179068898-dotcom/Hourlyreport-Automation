from __future__ import annotations

import importlib.metadata
import json
import platform
import socket
import sys
from pathlib import Path
from typing import Any

from modules.browser_manager import get_browser_settings
from modules.chrome_debug import ensure_chrome_debug_ready, find_chrome_executable
from modules.excel_engine import (
    get_excel_engine,
    get_project_excel_path,
    get_project_sheet_name,
    is_openpyxl_installed,
    test_openpyxl_save_copy,
)
from modules.kst_export_parser import find_latest_kst_export
from modules.project_config import get_current_project, load_app_config, validate_project_config


REQUIREMENT_NAME_MAP = {
    "python-dateutil": "python-dateutil",
    "pywin32": "pywin32",
}
EXCEL_COM_ONLY_REQUIREMENTS = {"xlwings", "pywin32"}


def _ok(message: str, detail: Any = None) -> dict[str, Any]:
    return {"passed": True, "level": "ok", "message": message, "detail": detail}


def _warn(message: str, detail: Any = None) -> dict[str, Any]:
    return {"passed": False, "level": "warning", "message": message, "detail": detail}


def _resolve(root: Path, value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _check_python() -> dict[str, Any]:
    version = platform.python_version()
    if sys.version_info >= (3, 10):
        return _ok(f"Python 版本正常：{version}")
    return _warn(f"Python 版本偏低：{version}，建议使用 3.10 或以上")


def _parse_requirement_name(line: str) -> str | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    line = line.split(";", 1)[0].strip()
    for sep in [">=", "==", "<=", "~=", ">", "<"]:
        if sep in line:
            line = line.split(sep, 1)[0].strip()
    return line or None


def _check_requirements(root: Path, excel_engine: str = "openpyxl") -> dict[str, Any]:
    req = root / "requirements.txt"
    if not req.exists():
        return _warn("未找到 requirements.txt")
    missing = []
    checked = []
    skipped_optional = []
    for line in req.read_text(encoding="utf-8").splitlines():
        name = _parse_requirement_name(line)
        if not name:
            continue
        if excel_engine == "openpyxl" and name in EXCEL_COM_ONLY_REQUIREMENTS:
            skipped_optional.append(name)
            continue
        package_name = REQUIREMENT_NAME_MAP.get(name, name)
        try:
            importlib.metadata.version(package_name)
            checked.append(name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(name)
    if missing:
        return _warn(
            f"依赖未安装完整，缺少：{', '.join(missing)}",
            {"checked": checked, "missing": missing, "skipped_optional": skipped_optional},
        )
    message = f"requirements 依赖检查通过，共 {len(checked)} 项"
    if skipped_optional:
        message += f"；openpyxl 模式已跳过 Excel COM 备用依赖：{', '.join(skipped_optional)}"
    return _ok(message, {"checked": checked, "skipped_optional": skipped_optional})


def _check_excel_available() -> dict[str, Any]:
    if platform.system() != "Windows":
        return _warn("当前不是 Windows，无法检查 Microsoft Excel COM")
    candidates = [
        Path("C:/Program Files/Microsoft Office/root/Office16/EXCEL.EXE"),
        Path("C:/Program Files (x86)/Microsoft Office/root/Office16/EXCEL.EXE"),
        Path("C:/Program Files/Microsoft Office/Office16/EXCEL.EXE"),
        Path("C:/Program Files (x86)/Microsoft Office/Office16/EXCEL.EXE"),
    ]
    for path in candidates:
        if path.exists():
            return _ok(f"Microsoft Excel 已找到：{path}", {"path": str(path)})
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\excel.exe") as key:
            value, _ = winreg.QueryValueEx(key, None)
        if value:
            return _ok(f"Microsoft Excel 已注册：{value}", {"path": value})
    except Exception as exc:
        return _warn(f"未确认 Microsoft Excel 可用：{exc}")
    return _warn("未找到 Microsoft Excel。若使用 WPS 打开文件，写入前也必须关闭目标表格。")


def _check_excel_engine(engine: str) -> dict[str, Any]:
    if engine == "openpyxl":
        return _ok("当前 Excel 写入引擎：openpyxl，适合 WPS 环境，不要求安装 Microsoft Excel。", {"engine": engine})
    if engine == "excel_com":
        return _ok("当前 Excel 写入引擎：excel_com，需要 Microsoft Excel COM 可用。", {"engine": engine})
    return _warn(f"不支持的 Excel 写入引擎：{engine}，建议使用 openpyxl。", {"engine": engine})


def _check_openpyxl_installed() -> dict[str, Any]:
    if is_openpyxl_installed():
        return _ok("openpyxl 已安装，可直接读写 xlsx 文件。")
    return _warn("openpyxl 未安装，请先运行 install_env.bat 安装依赖。")


def _check_secret_profile(secrets_file: Path | None, project: dict[str, Any]) -> dict[str, Any]:
    profile = project.get("baidu", {}).get("credential_profile")
    if not secrets_file or not secrets_file.exists():
        return _warn(f"未找到 secrets.json：{secrets_file}；如需自动登录，请从 secrets.example.json 复制后填写")
    try:
        data = json.loads(secrets_file.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return _warn(f"secrets.json 读取失败：{exc}")
    item = data.get("baidu", {}).get(profile)
    if isinstance(item, dict) and item.get("username") and item.get("password"):
        return _ok(f"百度凭据 profile 存在：{profile}")
    return _warn(f"secrets.json 中未找到当前项目百度凭据 profile：{profile}")


def _check_chrome(config: dict[str, Any]) -> dict[str, Any]:
    chrome_exe = find_chrome_executable(config)
    if chrome_exe:
        settings = get_browser_settings(config)
        profile_dir = settings.get("browser_profile_dir", "browser_profile/chrome")
        return _ok(f"Google Chrome 已找到：{chrome_exe}；项目专用用户目录：{profile_dir}", {"path": str(chrome_exe)})
    candidates = [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    ]
    return _warn(
        "未找到 Google Chrome。请确认 Chrome 已安装到以下路径之一：\n"
        + "\n".join(f"  - {path}" for path in candidates)
        + "\n或通过项目配置 browser.managed.executable_path 指定 Chrome 路径。"
    )


def _check_cdp(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    settings = get_browser_settings(config)
    host = settings.get("remote_debugging_host", "127.0.0.1")
    port = settings.get("remote_debugging_port", 9222)
    endpoint = settings["cdp_endpoint"]
    auto_start = settings.get("auto_start_debug_chrome", True)

    result = ensure_chrome_debug_ready(root, config, host=host, port=port, auto_start=auto_start)
    if result["ready"]:
        if result.get("port_already_open"):
            return _ok(f"Chrome 调试端口已就绪：{endpoint}（已有 Chrome 实例）")
        return _ok(
            f"Chrome 调试端口已就绪：{endpoint}（自动启动了项目专用 Chrome）",
            {"profile_dir": result.get("profile_dir"), "startup_url": result.get("startup_url")},
        )
    else:
        msg = f"Chrome 调试端口未就绪：{endpoint}。"
        if result.get("error"):
            msg += f" {result['error']}"
        else:
            msg += " 请手动运行 start_chrome_debug.bat。"
        return _warn(msg)


def _project_excel_path(root: Path, project: dict[str, Any]) -> Path | None:
    return get_project_excel_path(project, root)


def _check_sheet(excel_path: Path | None, sheet_name: str, label: str) -> dict[str, Any]:
    if not excel_path or not excel_path.exists():
        return _warn(f"无法检查 {label}，因为目标 Excel 不存在")
    try:
        from openpyxl import load_workbook

        wb = load_workbook(excel_path, read_only=True, data_only=False)
        if sheet_name in wb.sheetnames:
            return _ok(f"{label} 存在：{sheet_name}")
        return _warn(f"{label} 不存在：{sheet_name}；当前 sheet：{', '.join(wb.sheetnames)}")
    except Exception as exc:
        return _warn(f"检查 {label} 失败：{exc}")


def run_doctor(root: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    root_path = Path(root)
    checks: dict[str, dict[str, Any]] = {}
    project: dict[str, Any] = {}
    app_config: dict[str, Any] = {}

    checks["python"] = _check_python()
    checks["chrome"] = _check_chrome(config)
    checks["chrome_debug_port"] = _check_cdp(root_path, config)

    try:
        app_config = load_app_config(root_path)
        checks["app_config"] = _ok("app_config.json 存在并可读取", app_config)
    except Exception as exc:
        checks["app_config"] = _warn(f"app_config 检查失败：{exc}")

    try:
        project = get_current_project(root_path)
        errors = validate_project_config(project)
        if errors:
            checks["project_config"] = _warn("当前项目配置不完整", errors)
        else:
            checks["project_config"] = _ok(f"当前项目配置完整：{project.get('project_id')} - {project.get('project_name')}")
    except Exception as exc:
        checks["project_config"] = _warn(f"项目配置读取失败：{exc}")

    excel_engine = get_excel_engine(project, config)
    checks["requirements"] = _check_requirements(root_path, excel_engine=excel_engine)
    checks["excel_engine"] = _check_excel_engine(excel_engine)
    if excel_engine == "openpyxl":
        checks["openpyxl"] = _check_openpyxl_installed()
    elif excel_engine == "excel_com":
        checks["excel_app"] = _check_excel_available()

    excel_path = _project_excel_path(root_path, project) if project else None
    if excel_path and excel_path.exists():
        checks["target_excel"] = _ok(f"目标 Excel 存在：{excel_path}")
    else:
        checks["target_excel"] = _warn(f"目标 Excel 不存在：{excel_path or '未配置'}")

    if excel_engine == "openpyxl" and checks.get("target_excel", {}).get("passed"):
        save_test = test_openpyxl_save_copy(excel_path, root_path) if excel_path else {"passed": False, "message": "目标 Excel 未配置"}
        checks["openpyxl_save_test"] = _ok(save_test["message"], save_test) if save_test.get("passed") else _warn(save_test["message"], save_test)

    checks["daily_sheet"] = _check_sheet(excel_path, get_project_sheet_name(project, "daily") if project else "百度", "日报 sheet")
    checks["hourly_sheet"] = _check_sheet(excel_path, get_project_sheet_name(project, "hourly") if project else "时段数据", "小时报 sheet")

    export_dir = _resolve(root_path, project.get("kst", {}).get("export_dir") if project else config.get("kst", {}).get("export_dir", "kst_exports"))
    if export_dir and export_dir.is_file():
        checks["kst_export_dir"] = _ok(f"商务通导出路径是具体文件：{export_dir}")
    elif export_dir and export_dir.exists():
        checks["kst_export_dir"] = _ok(f"商务通导出目录存在：{export_dir}")
    else:
        checks["kst_export_dir"] = _warn(f"商务通导出目录/文件不存在：{export_dir or '未配置'}")

    secrets_file = _resolve(root_path, app_config.get("secrets_file")) if app_config else root_path / "secrets" / "secrets.json"
    checks["secrets_json"] = _check_secret_profile(secrets_file, project)

    latest = find_latest_kst_export(root_path, {"kst": {"export_dir": str(export_dir)}}) if export_dir else None
    if latest:
        checks["latest_kst_export"] = _ok(f"已找到最新商务通导出文件：{latest}", {"path": str(latest)})
    else:
        checks["latest_kst_export"] = _warn("未找到商务通导出 Excel/CSV 文件，请先导出到 kst_exports 目录")

    passed_count = sum(1 for item in checks.values() if item.get("passed"))
    report = {
        "mode": "doctor",
        "project_id": project.get("project_id") if project else None,
        "project_name": project.get("project_name") if project else None,
        "checks": checks,
        "summary": {
            "total": len(checks),
            "passed": passed_count,
            "failed": len(checks) - passed_count,
            "all_passed": passed_count == len(checks),
        },
    }
    out = root_path / "reports" / "doctor_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def print_doctor_report(report: dict[str, Any]) -> None:
    from modules.console_ui import print_check_result, print_header

    print_header("运行环境检查结果")
    print(f"项目：{report.get('project_name') or report.get('project_id') or '未知'}")

    passed_count = 0
    failed_count = 0
    for key, item in report.get("checks", {}).items():
        if item.get("passed"):
            print_check_result(_DOCTOR_CHECK_LABELS.get(key, key), "pass", item.get("message", ""))
            passed_count += 1
        elif item.get("level") == "warning":
            print_check_result(_DOCTOR_CHECK_LABELS.get(key, key), "warn", item.get("message", ""))
            failed_count += 1
        else:
            print_check_result(_DOCTOR_CHECK_LABELS.get(key, key), "fail", item.get("message", ""))
            failed_count += 1

    total = passed_count + failed_count
    if failed_count == 0:
        print(f"\n合计：{passed_count}/{total} 项通过")
    else:
        print(f"\n合计：{passed_count}/{total} 项通过，{failed_count} 项需关注")


_DOCTOR_CHECK_LABELS = {
    "python": "Python 版本",
    "chrome": "Google Chrome",
    "chrome_debug_port": "Chrome 调试端口",
    "app_config": "应用配置",
    "project_config": "项目配置",
    "requirements": "依赖包",
    "excel_engine": "Excel 写入引擎",
    "openpyxl": "openpyxl 安装",
    "excel_app": "Microsoft Excel",
    "target_excel": "目标 Excel",
    "openpyxl_save_test": "openpyxl 保存测试",
    "daily_sheet": "日报 sheet",
    "hourly_sheet": "小时报 sheet",
    "kst_export_dir": "商务通导出目录",
    "secrets_json": "百度凭据文件",
    "latest_kst_export": "最新商务通导出文件",
}
