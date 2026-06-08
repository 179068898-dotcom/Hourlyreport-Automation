from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


REQUIRED_IMPORTS = ["openpyxl", "pandas", "xlrd", "dateutil", "playwright", "rich"]
RUNTIME_DIRS = ["logs", "reports", "backups", "kst_exports"]


def _check(name: str, passed: bool, severity: str, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "severity": severity, "detail": detail}


def _python_path(root: Path) -> Path:
    return root / ".venv" / "Scripts" / "python.exe"


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
            ["cmd.exe", "/d", "/c", str(installer)],
            cwd=root_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
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
