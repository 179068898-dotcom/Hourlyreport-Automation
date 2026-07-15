from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_IMPORTS = ["openpyxl", "pandas", "xlrd", "dateutil", "playwright", "rich"]
RUNTIME_DIRS = ["logs", "reports", "backups", "kst_exports"]
KST_DATA_ROOT = Path("D:/商务通数据")
KST_PROJECT_DIR_NAMES = (
    "长沙牛",
    "昆明牛",
    "南京白",
    "南京牛",
    "宁波牛",
    "青岛白",
    "沈阳白",
    "沈阳牛",
    "深圳白",
)


def _kst_initialization_marker_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    elif os.name == "nt":
        base = Path.home() / "AppData" / "Local"
    else:
        base = Path.home() / ".local" / "share"
    return base / "BaiduDataAutomation" / "kst_directories_v1.json"


def initialize_kst_directories_once(
    data_root: str | Path = KST_DATA_ROOT,
    marker_path: str | Path | None = None,
) -> dict[str, Any]:
    root_path = Path(data_root)
    marker = Path(marker_path) if marker_path is not None else _kst_initialization_marker_path()
    if marker.is_file():
        return {
            "passed": True,
            "status": "skipped",
            "root": str(root_path),
            "marker": str(marker),
            "detail": "首次商务通目录准备已完成，本次不再检查。",
        }

    created: list[str] = []
    temporary_marker = marker.with_name(marker.name + ".tmp")
    try:
        root_path.mkdir(parents=True, exist_ok=True)
        for project_name in KST_PROJECT_DIR_NAMES:
            project_path = root_path / project_name
            if project_path.exists():
                if not project_path.is_dir():
                    raise NotADirectoryError(f"{project_path} 已存在，但不是文件夹")
                continue
            project_path.mkdir(parents=False)
            created.append(project_name)

        marker.parent.mkdir(parents=True, exist_ok=True)
        marker_payload = {
            "version": 1,
            "initialized_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "data_root": str(root_path),
            "projects": list(KST_PROJECT_DIR_NAMES),
        }
        temporary_marker.write_text(
            json.dumps(marker_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_marker.replace(marker)
    except Exception as exc:
        try:
            temporary_marker.unlink(missing_ok=True)
        except Exception:
            pass
        return {
            "passed": False,
            "status": "failed",
            "root": str(root_path),
            "marker": str(marker),
            "detail": f"首次准备商务通目录失败：{exc}",
        }

    detail = "9 个项目目录已准备完成。"
    if created:
        detail = f"已新建 {len(created)} 个项目目录：{', '.join(created)}。"
    return {
        "passed": True,
        "status": "initialized",
        "root": str(root_path),
        "marker": str(marker),
        "created": created,
        "detail": detail,
    }


def _check(name: str, passed: bool, severity: str, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "severity": severity, "detail": detail}


def _python_path(root: Path) -> Path:
    return root / ".venv" / "Scripts" / "python.exe"


def environment_repair_command(root: str | Path) -> list[str]:
    installer = Path(root) / "install_env.bat"
    return ["cmd.exe", "/d", "/c", str(installer)]


def hidden_subprocess_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "startupinfo": startupinfo,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }


def _imports_available(python: Path) -> tuple[bool, str]:
    code = "import " + ", ".join(REQUIRED_IMPORTS)
    try:
        result = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            **hidden_subprocess_kwargs(),
        )
    except Exception as exc:
        return False, str(exc)
    if result.returncode == 0:
        return True, "Required command-line dependencies are available."
    return False, (result.stderr or result.stdout or "Dependency import check failed.").strip()


def repair_environment_if_needed(root: str | Path, report: dict[str, Any]) -> dict[str, Any]:
    if report.get("passed"):
        return {"attempted": False, "reason": "environment already passed"}

    root_path = Path(root)
    installer = root_path / "install_env.bat"
    if not installer.exists():
        return {"attempted": False, "reason": f"Missing {installer}"}

    env = os.environ.copy()
    env["HURLY_REPORT_BOT_AUTO_INSTALL"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(
            environment_repair_command(root_path),
            cwd=root_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1200,
            env=env,
            **hidden_subprocess_kwargs(),
        )
    except Exception as exc:
        return {"attempted": True, "returncode": 1, "stdout": "", "stderr": str(exc)}

    return {
        "attempted": True,
        "returncode": int(result.returncode),
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
    }


def run_environment_check(root: str | Path) -> dict[str, Any]:
    root_path = Path(root)
    checks: list[dict[str, Any]] = []

    missing_dirs = []
    for dirname in RUNTIME_DIRS:
        path = root_path / dirname
        try:
            path.mkdir(exist_ok=True)
        except Exception:
            missing_dirs.append(dirname)
    checks.append(_check(
        "Runtime folders",
        not missing_dirs,
        "error" if missing_dirs else "info",
        "Missing or locked folders: " + ", ".join(missing_dirs) if missing_dirs else "Runtime folders are ready.",
    ))

    python = _python_path(root_path)
    python_ready = python.exists()
    checks.append(_check(
        "Python environment",
        python_ready,
        "error",
        f"Found {python}" if python_ready else f"Missing {python}. Run install_env.bat first.",
    ))

    if python_ready:
        imports_ok, detail = _imports_available(python)
        checks.append(_check("Command dependencies", imports_ok, "error", detail))
    else:
        checks.append(_check("Command dependencies", False, "error", "Skipped because Python environment is missing."))

    app_config = root_path / "configs" / "app_config.json"
    config_ok = False
    config_detail = f"Missing {app_config}"
    if app_config.exists():
        try:
            json.loads(app_config.read_text(encoding="utf-8"))
            config_ok = True
            config_detail = "App config is readable."
        except Exception as exc:
            config_detail = f"App config cannot be parsed: {exc}"
    checks.append(_check("Project config", config_ok, "error", config_detail))

    secrets = root_path / "secrets" / "secrets.json"
    checks.append(_check(
        "Credential file",
        secrets.exists(),
        "warning",
        "Credential file exists." if secrets.exists() else "Missing secrets/secrets.json.",
    ))

    passed = all(item["passed"] or item["severity"] != "error" for item in checks)
    return {"passed": passed, "checks": checks}
