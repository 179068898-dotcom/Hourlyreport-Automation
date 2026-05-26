from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from modules.baidu_multi_source import resolve_baidu_sources
from modules.browser_manager import get_browser_settings
from modules.chrome_debug import is_chrome_debug_port_alive
from modules.excel_inspector import inspect_excel_structure
from modules.project_config import validate_project_config


def _resolve(root: Path, value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(value)
    return path if path.is_absolute() else root / path


def _profiles_for_config(config: dict[str, Any]) -> list[str]:
    profiles: list[str] = []
    for source in resolve_baidu_sources(config):
        profile = str(source.get("credential_profile") or "").strip()
        if profile and profile not in profiles:
            profiles.append(profile)
    return profiles


def check_baidu_credentials(root: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    root_path = Path(root)
    credentials_path = _resolve(root_path, config.get("credentials_path", "secrets/secrets.json"))
    required_profiles = _profiles_for_config(config)
    report: dict[str, Any] = {
        "passed": False,
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "credentials_path": str(credentials_path or ""),
        "required_profiles": required_profiles,
        "profiles": [],
        "json_valid": False,
        "errors": [],
    }
    if not credentials_path or not credentials_path.exists():
        report["errors"].append("凭据文件不存在：secrets/secrets.json")
        return report
    try:
        data = json.loads(credentials_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        report["errors"].append(
            f"secrets/secrets.json 不是合法 JSON：line {exc.lineno} column {exc.colno}"
        )
        return report
    except Exception as exc:
        report["errors"].append(f"secrets/secrets.json 无法读取：{exc}")
        return report

    report["json_valid"] = True
    baidu = data.get("baidu") if isinstance(data, dict) else {}
    baidu = baidu if isinstance(baidu, dict) else {}
    if not required_profiles:
        report["errors"].append("当前项目未配置 credential_profile")
        return report
    for profile in required_profiles:
        item = baidu.get(profile)
        exists = isinstance(item, dict)
        username_nonempty = bool(exists and str(item.get("username") or "").strip())
        password_nonempty = bool(exists and str(item.get("password") or "").strip())
        report["profiles"].append({
            "credential_profile": profile,
            "exists": exists,
            "username_nonempty": username_nonempty,
            "password_nonempty": password_nonempty,
        })
        if not exists:
            report["errors"].append(f"缺少 credential_profile：{profile}")
            continue
        if not username_nonempty:
            report["errors"].append(f"profile {profile} 的 username 为空")
        if not password_nonempty:
            report["errors"].append(f"profile {profile} 的 password 为空")
    report["passed"] = not report["errors"]
    return report


def print_credential_report(report: dict[str, Any], output_func: Callable[[str], None] = print) -> None:
    output_func(f"当前项目：{report.get('project_name') or report.get('project_id') or '未知'}")
    required = report.get("required_profiles") or []
    output_func(f"需要的 credential_profile：{', '.join(required) if required else '无'}")
    for item in report.get("profiles") or []:
        status = "通过" if item.get("exists") and item.get("username_nonempty") and item.get("password_nonempty") else "失败"
        username = "非空" if item.get("username_nonempty") else "为空"
        password = "非空" if item.get("password_nonempty") else "为空"
        output_func(
            f"[{status}] credential_profile: {item.get('credential_profile')} "
            f"username{username} password{password}"
        )
    for error in report.get("errors") or []:
        output_func(f"[失败] {error}")


class _SilentLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None


def run_preflight(
    root: str | Path,
    project: dict[str, Any],
    config: dict[str, Any],
    *,
    chrome_check_func: Callable[..., bool] = is_chrome_debug_port_alive,
) -> dict[str, Any]:
    root_path = Path(root)
    checks: list[dict[str, Any]] = []

    def add(passed: bool, message: str) -> None:
        checks.append({"passed": passed, "message": message})

    add((root_path / "main.py").exists(), "项目根目录已识别" if (root_path / "main.py").exists() else "项目根目录无法识别")

    settings = get_browser_settings(config)
    host = settings.get("remote_debugging_host", "127.0.0.1")
    port = int(settings.get("remote_debugging_port", 9222))
    chrome_ok = chrome_check_func(host=host, port=port)
    add(chrome_ok, "Chrome 9222 已连接" if chrome_ok else f"Chrome 9222 无法连接：http://{host}:{port}")

    project_errors = validate_project_config(project)
    add(
        not project_errors,
        f"当前项目：{project.get('project_id')} - {project.get('project_name')}" if not project_errors else "项目配置校验失败：" + "；".join(project_errors),
    )

    excel_path = _resolve(root_path, config.get("excel_path"))
    add(bool(excel_path and excel_path.exists()), "Excel 路径存在" if excel_path and excel_path.exists() else f"Excel 路径不存在：{excel_path or ''}")
    if excel_path and excel_path.exists():
        try:
            structure = inspect_excel_structure(config=config, root=root_path, logger=_SilentLogger())
            errors = structure.get("errors") or []
            add(not errors, "小时报 sheet 结构可识别" if not errors else "小时报 sheet 结构识别失败：" + "；".join(errors))
        except Exception as exc:
            add(False, f"小时报 sheet 结构识别失败：{exc}")
    else:
        add(False, "小时报 sheet 结构无法检查：Excel 不存在")

    kst_dir = _resolve(root_path, config.get("kst", {}).get("export_dir"))
    add(bool(kst_dir and kst_dir.exists()), "商务通目录存在" if kst_dir and kst_dir.exists() else f"商务通目录不存在：{kst_dir or ''}")

    credentials = check_baidu_credentials(root_path, config)
    json_error = next((error for error in credentials.get("errors") or [] if "JSON" in error or "无法读取" in error), "")
    add(credentials.get("json_valid", False), "secrets JSON 合法" if credentials.get("json_valid") else (json_error or "secrets/secrets.json 无法读取"))
    add(credentials.get("passed", False), "credential_profile 检查通过" if credentials.get("passed") else "凭据预检未通过，请检查 secrets/secrets.json")

    return {
        "passed": all(item["passed"] for item in checks),
        "mode": "preflight",
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "checks": checks,
        "credentials": credentials,
    }


def print_preflight_report(report: dict[str, Any], output_func: Callable[[str], None] = print) -> None:
    for item in report.get("checks") or []:
        output_func(f"[{'通过' if item.get('passed') else '失败'}] {item.get('message')}")
    print_credential_report(report.get("credentials") or {}, output_func=output_func)
