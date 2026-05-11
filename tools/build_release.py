from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


DEFAULT_VERSION = "0.4.4"
EXCLUDE_DIRS = {".venv", ".git", ".claude", "browser_profile", "__pycache__", ".pytest_cache", "dist"}
RUNTIME_KEEP_DIRS = {"reports", "logs", "backups", "kst_exports"}
EXCLUDE_SUFFIXES = {".pyc", ".tmp", ".bak"}
EXCLUDE_FILES = {"config.json", "credentials.local.json"}
EXCLUDE_REPORT_FILES = {"menu_task_status.json", "browser_login_state.json"}


def normalize_version(version: str | None) -> str:
    raw = (version or DEFAULT_VERSION).strip()
    if not raw:
        raw = DEFAULT_VERSION
    return raw if raw.startswith("v") else f"v{raw}"


def release_name(version: str | None = None, internal: bool = False) -> str:
    prefix = "hourly_report_bot_internal" if internal else "hourly_report_bot_release"
    return f"{prefix}_{normalize_version(version)}.zip"


def should_include_file(path: Path, internal: bool = False) -> bool:
    parts = path.parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return False
    if path.name in EXCLUDE_FILES:
        return False
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    # secrets: 普通包排除 secrets.json，内部包包含
    if len(parts) >= 2 and parts[0] == "secrets":
        if path.name == "secrets.example.json":
            return True
        if path.name == "secrets.json":
            return internal
        return False
    # 运行时目录只保留 .gitkeep
    if parts and parts[0] in RUNTIME_KEEP_DIRS:
        if path.name in EXCLUDE_REPORT_FILES:
            return False
        return path.name == ".gitkeep"
    # samples 只保留 .gitkeep
    if parts and parts[0] == "samples":
        return path.name == ".gitkeep"
    return True


def build_release(root: str | Path, version: str | None = None, internal: bool = False) -> Path:
    root_path = Path(root)
    dist_dir = root_path / "dist"
    dist_dir.mkdir(exist_ok=True)
    release_path = dist_dir / release_name(version, internal=internal)
    if release_path.exists():
        release_path.unlink()

    with zipfile.ZipFile(release_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in root_path.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(root_path)
            if should_include_file(rel, internal=internal):
                archive.write(path, rel.as_posix())
    return release_path


def main() -> None:
    parser = argparse.ArgumentParser(description="构建百度竞价日报/小时报自动化工具发布包")
    parser.add_argument("--version", default=DEFAULT_VERSION, help="发布版本号，例如 0.4.4 或 v0.4.4")
    parser.add_argument("--internal", action="store_true", help="构建内部包（包含 secrets/secrets.json）")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    release_path = build_release(root, version=args.version, internal=args.internal)
    size_mb = release_path.stat().st_size / 1024 / 1024
    pkg_type = "内部包" if args.internal else "普通包"
    print(f"{pkg_type}已生成：{release_path}")
    print(f"大小：{size_mb:.2f} MB")


if __name__ == "__main__":
    main()
