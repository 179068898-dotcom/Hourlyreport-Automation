from __future__ import annotations

import csv
import importlib.metadata
import json
import os
import platform
import re
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from gui.log_history import redact_history_text


LOCK_FILE_NAME = "requirements-runtime.lock.txt"
RUNTIME_REQUIREMENT_FILES = ("requirements-runtime.txt",)
RUNTIME_TRANSITIVE_PACKAGES = {
    "colorama",
    "et_xmlfile",
    "greenlet",
    "linkify-it-py",
    "markdown-it-py",
    "mdit-py-plugins",
    "mdurl",
    "numpy",
    "openpyxl",
    "packaging",
    "pandas",
    "playwright",
    "pyee",
    "pygments",
    "python-dateutil",
    "rich",
    "six",
    "typing-extensions",
    "tzdata",
    "uc-micro-py",
    "xlrd",
}

SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|passwd|pwd|token|secret|authorization|authcode|cookie|hmac|"
    r"client[_-]?key|access[_-]?token|refresh[_-]?token)",
    re.IGNORECASE,
)
DIAGNOSTIC_INCLUDE_DIRS = ("configs", "reports", "logs")
DIAGNOSTIC_TEXT_SUFFIXES = {".json", ".log", ".txt", ".md", ".csv"}
DIAGNOSTIC_EXCLUDED_PARTS = {
    "secrets",
    "backups",
    "browser_profile",
    "kst_exports",
    ".venv",
    "runtime",
    "dist",
    ".git",
}


def _normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", str(name or "").strip()).lower()


def _requirement_names(root: Path) -> set[str]:
    names: set[str] = set()
    for file_name in RUNTIME_REQUIREMENT_FILES:
        path = root / file_name
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            match = re.match(r"([A-Za-z0-9_.-]+)", line)
            if match:
                names.add(_normalize_package_name(match.group(1)))
    return names


def _installed_packages() -> dict[str, str]:
    packages: dict[str, str] = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name")
        if name:
            packages[_normalize_package_name(name)] = dist.version
    return packages


def build_runtime_dependency_lock(
    root: str | Path,
    *,
    installed_packages: dict[str, str] | None = None,
) -> Path:
    root_path = Path(root)
    installed = {
        _normalize_package_name(name): str(version)
        for name, version in (installed_packages or _installed_packages()).items()
    }
    selected_names = (_requirement_names(root_path) | RUNTIME_TRANSITIVE_PACKAGES) & set(installed)

    lines = [
        "# Runtime dependency lock for 蚁之力 · 竞价数据自动化",
        "# Generated from the local verified environment. Keep requirements-runtime.txt as the readable source list.",
    ]
    for package_name in sorted(selected_names):
        lines.append(f"{package_name}=={installed[package_name]}")

    lock_path = root_path / LOCK_FILE_NAME
    lock_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lock_path


def _redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if SENSITIVE_KEY_PATTERN.search(str(key)):
                redacted[key] = "***"
            else:
                redacted[key] = _redact_json(item)
        return redacted
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    if isinstance(value, str):
        return redact_history_text(value)
    return value


def _redact_file_content(path: Path) -> str:
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return json.dumps(_redact_json(data), ensure_ascii=False, indent=2) + "\n"
        except (OSError, json.JSONDecodeError):
            pass
    return redact_history_text(path.read_text(encoding="utf-8", errors="replace")) + "\n"


def _diagnostic_candidates(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for folder_name in DIAGNOSTIC_INCLUDE_DIRS:
        folder = root / folder_name
        if folder.is_dir():
            candidates.extend(path for path in folder.rglob("*") if path.is_file())
    return sorted(candidates, key=lambda path: path.relative_to(root).as_posix())


def create_diagnostic_bundle(
    root: str | Path,
    *,
    now_label: str | None = None,
) -> Path:
    root_path = Path(root)
    label = now_label or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = root_path / "diagnostics"
    out_dir.mkdir(exist_ok=True)
    bundle_path = out_dir / f"diagnostic_{label}.zip"
    if bundle_path.exists():
        bundle_path.unlink()

    included: list[str] = []
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        manifest = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "python": sys.version,
            "platform": platform.platform(),
            "redacted": True,
            "excluded": sorted(DIAGNOSTIC_EXCLUDED_PARTS),
        }
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

        for path in _diagnostic_candidates(root_path):
            rel = path.relative_to(root_path)
            if any(part in DIAGNOSTIC_EXCLUDED_PARTS for part in rel.parts):
                continue
            if path.suffix.lower() not in DIAGNOSTIC_TEXT_SUFFIXES:
                continue
            arcname = rel.as_posix()
            try:
                content = _redact_file_content(path)
            except FileNotFoundError:
                continue
            archive.writestr(arcname, content)
            included.append(arcname)

        archive.writestr("included_files.csv", _csv_single_column("path", included))
    return bundle_path


def _csv_single_column(header: str, rows: list[str]) -> str:
    from io import StringIO

    stream = StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow([header])
    for row in rows:
        writer.writerow([row])
    return stream.getvalue()


def archive_logs(
    root: str | Path,
    *,
    older_than_days: int = 14,
    now: datetime | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    logs_dir = root_path / "logs"
    archive_dir = logs_dir / "archive"
    current_time = now or datetime.now()
    cutoff = current_time - timedelta(days=max(0, int(older_than_days)))
    candidates: list[Path] = []
    if logs_dir.is_dir():
        for path in logs_dir.glob("*.log"):
            modified = datetime.fromtimestamp(path.stat().st_mtime)
            if modified < cutoff:
                candidates.append(path)

    archive_path = archive_dir / f"logs_{current_time.strftime('%Y%m%d_%H%M%S')}.zip"
    if not candidates:
        return {"archive_path": None, "archived_count": 0, "archived_files": []}

    archive_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(candidates, key=lambda item: item.name):
            archive.write(path, path.name)

    archived_files: list[str] = []
    for path in candidates:
        archived_files.append(path.name)
        os.remove(path)

    return {
        "archive_path": str(archive_path),
        "archived_count": len(archived_files),
        "archived_files": archived_files,
    }
