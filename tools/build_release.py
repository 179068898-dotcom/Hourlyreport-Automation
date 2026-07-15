from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

DEFAULT_VERSION = "hermes_20260710"
EXCLUDE_DIRS = {".venv", ".git", ".claude", "browser_profile", "runtime", "__pycache__", ".pytest_cache", "build", "cloud"}
DESKTOP_EXE = "百度数据自动化控制台.exe"
EXCLUDE_RUNTIME_DIRS = {"reports", "logs", "backups"}
RUNTIME_KEEP_DIRS = {"kst_exports"}
EXCLUDE_SUFFIXES = {".pyc", ".tmp", ".bak", ".spec"}
EXCLUDE_FILES = {
    "config.json",
    "credentials.local.json",
    ".ignore",
    "nul",
    "_verify_excel.py",
    "build_desktop_exe.bat",
    "requirements-dev.txt",
    "design-qa.md",
}
EXCLUDE_REPORT_FILES = {"menu_task_status.json", "browser_login_state.json", "unknown_baidu_accounts.json"}
LEGACY_ROOT_FILES = {
    "create_config.bat",
    "run_11.bat",
    "run_15.bat",
    "run_18.bat",
    "run_fetch_baidu.bat",
    "run_fetch_baidu_15.bat",
    "run_inspect.bat",
    "run_mock_write.bat",
    "run_parse_kst_export_15.bat",
    "run_test_browser_connect.bat",
    "setup_env.bat",
    "START_HERE.bat",
}

REQUIRED_INTERNAL_PROFILES = [
    "kunming_niu_baidu",
    "nanjing_niu_baidu",
    "ningbo_niu_baidu",
    "changsha_niu_baidu",
    "shenyang_niu_zhongya_baidu",
    "shenyang_niu_yinkang_baidu",
    "qingdao_bai_baidu",
    "shenyang_bai_source_a_baidu",
    "shenyang_bai_source_b_baidu",
]

ONLINE_VERSION_PATTERN = re.compile(r"^v?(\d{4})\.(\d{1,2})\.(\d{1,2})\.(\d+)$")


def validate_online_version(version: str) -> str:
    raw = str(version or "").strip()
    match = ONLINE_VERSION_PATTERN.fullmatch(raw)
    if not match:
        raise ValueError("在线版本号必须使用 YYYY.M.D.NNN 格式")

    year, month, day, counter = (int(part) for part in match.groups())
    try:
        date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"在线版本号日期无效：{year}.{month}.{day}") from exc
    if counter < 100:
        raise ValueError("在线版本号的永久累计序号必须从 100 起")
    return f"{year}.{month}.{day}.{counter}"


def next_online_version(latest_version: str, release_date: date | None = None) -> str:
    current = validate_online_version(latest_version)
    counter = int(current.rsplit(".", 1)[1]) + 1
    target_date = release_date or date.today()
    return f"{target_date.year}.{target_date.month}.{target_date.day}.{counter}"


def normalize_version(version: str | None) -> str:
    raw = (version or DEFAULT_VERSION).strip()
    if not raw:
        raw = DEFAULT_VERSION
    if raw.startswith("v") or not re.fullmatch(r"\d+(?:\.\d+)*", raw):
        return raw
    return f"v{raw}"


def release_name(version: str | None = None, internal: bool = False, online_update: bool = False) -> str:
    if internal and online_update:
        raise ValueError("内部包与在线更新包不能同时生成")
    if online_update:
        clean_version = validate_online_version(version or "")
        return f"baidu_data_automation_update_{clean_version}.zip"
    prefix = "hourly_report_bot_internal" if internal else "hourly_report_bot_release"
    return f"{prefix}_{normalize_version(version)}.zip"


def should_include_file(path: Path, internal: bool = False, online_update: bool = False) -> bool:
    parts = path.parts
    if online_update and parts and parts[0] in {
        "configs", "secrets", "reports", "logs", "backups", "browser_profile", "kst_exports", "samples", ".venv", "runtime"
    }:
        return False
    if any(part in EXCLUDE_DIRS for part in parts):
        return False
    if parts and parts[0] == "dist":
        return (internal or online_update) and len(parts) == 2 and parts[1] == DESKTOP_EXE
    if parts and parts[0] == "tests":
        return False
    if len(parts) >= 2 and parts[0] == "docs" and parts[1] == "superpowers":
        return False
    if parts and parts[0] == "tools" and path.name != "bootstrap_python.ps1":
        return False
    if len(parts) == 1 and path.name in LEGACY_ROOT_FILES:
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
    if parts and parts[0] in EXCLUDE_RUNTIME_DIRS:
        return path.name == ".gitkeep"
    # 运行时目录只保留 .gitkeep
    if parts and parts[0] in RUNTIME_KEEP_DIRS:
        if path.name in EXCLUDE_REPORT_FILES:
            return False
        return path.name == ".gitkeep"
    # samples 只保留 .gitkeep
    if parts and parts[0] == "samples":
        return path.name == ".gitkeep"
    return True


def _validate_internal_secrets(root: Path) -> list[str]:
    """校验内部包所需的百度凭据 profile 是否完整。返回错误列表。"""
    secrets_path = root / "secrets" / "secrets.json"
    errors: list[str] = []
    if not secrets_path.exists():
        errors.append("缺少 secrets/secrets.json")
        return errors
    try:
        data = json.loads(secrets_path.read_text(encoding="utf-8"))
    except Exception:
        errors.append("secrets/secrets.json 无法解析")
        return errors
    baidu = data.get("baidu", {})
    for profile in REQUIRED_INTERNAL_PROFILES:
        item = baidu.get(profile)
        if not isinstance(item, dict):
            errors.append(f"缺少百度凭据 profile：{profile}")
            continue
        if not item.get("username", "").strip():
            errors.append(f"未填写账号：{profile}")
        if not item.get("password", "").strip():
            errors.append(f"未填写密码：{profile}")
    return errors


def build_release(
    root: str | Path,
    version: str | None = None,
    internal: bool = False,
    online_update: bool = False,
) -> Path:
    if internal and online_update:
        raise ValueError("内部包与在线更新包不能同时生成")
    root_path = Path(root)
    dist_dir = root_path / "dist"
    dist_dir.mkdir(exist_ok=True)
    release_path = dist_dir / release_name(version, internal=internal, online_update=online_update)
    if release_path.exists():
        release_path.unlink()

    with zipfile.ZipFile(release_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in root_path.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(root_path)
            if should_include_file(rel, internal=internal, online_update=online_update):
                archive_name = DESKTOP_EXE if rel.parts == ("dist", DESKTOP_EXE) else rel.as_posix()
                if rel.as_posix() == "configs/app_config.json":
                    app_config = json.loads(path.read_text(encoding="utf-8"))
                    app_config.pop("desktop_pet_position", None)
                    app_config["desktop_pet"] = "clawd"
                    app_config["desktop_pet_scale"] = 1.0
                    archive.writestr(archive_name, json.dumps(app_config, ensure_ascii=False, indent=2) + "\n")
                else:
                    archive.write(path, archive_name)
    return release_path


def main() -> None:
    parser = argparse.ArgumentParser(description="构建百度竞价日报/小时报自动化工具发布包")
    parser.add_argument("--version", default=DEFAULT_VERSION, help="发布版本号，例如 2.0 或 v2.0")
    parser.add_argument("--internal", action="store_true", help="构建内部包（包含 secrets/secrets.json）")
    parser.add_argument("--online-update", action="store_true", help="构建在线更新包（包含 GUI，排除所有用户配置）")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]

    if args.internal:
        errors = _validate_internal_secrets(root)
        if errors:
            for err in errors:
                print(f"[失败] {err}")
            sys.exit(1)

    release_path = build_release(
        root,
        version=args.version,
        internal=args.internal,
        online_update=args.online_update,
    )
    size_mb = release_path.stat().st_size / 1024 / 1024
    pkg_type = "在线更新包" if args.online_update else ("内部包" if args.internal else "普通包")
    print(f"{pkg_type}已生成：{release_path}")
    print(f"大小：{size_mb:.2f} MB")


if __name__ == "__main__":
    main()
