from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from PySide6.QtCore import QObject, Signal

from gui.version import CURRENT_VERSION


GITHUB_LATEST_RELEASE_URL = (
    "https://api.github.com/repos/179068898-dotcom/baidu-automation-releases/releases/latest"
)
UPDATE_ASSET_PATTERN = re.compile(r"^baidu_data_automation_update_(\d+(?:\.\d+){3})\.zip$")
APP_EXE_NAME = "百度数据自动化控制台.exe"
PROTECTED_UPDATE_ROOTS = {
    "configs",
    "secrets",
    "logs",
    "reports",
    "backups",
    "browser_profile",
    "kst_exports",
    "samples",
    ".venv",
    "runtime",
}
REQUIRED_UPDATE_FILES = {APP_EXE_NAME, "main.py", "gui/version.py"}


@dataclass(frozen=True)
class ReleaseUpdate:
    version: str
    download_url: str
    asset_name: str
    sha256: str
    size: int


def parse_version(value: str) -> tuple[int, int, int, int]:
    text = str(value or "").strip().removeprefix("v")
    parts = text.split(".")
    if len(parts) != 4 or any(not part.isdigit() for part in parts):
        raise ValueError(f"无效版本号：{value}")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def select_release_update(payload: dict[str, Any], current_version: str) -> ReleaseUpdate | None:
    tag_name = str(payload.get("tag_name") or "")
    try:
        release_version = tag_name.removeprefix("v")
        if parse_version(release_version) <= parse_version(current_version):
            return None
    except ValueError:
        return None

    for asset in payload.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        match = UPDATE_ASSET_PATTERN.fullmatch(name)
        if not match or match.group(1) != release_version:
            continue
        download_url = str(asset.get("browser_download_url") or "")
        if not download_url.startswith("https://"):
            continue
        digest = str(asset.get("digest") or "")
        sha256 = digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else ""
        size = int(asset.get("size") or 0)
        if size < 0 or size > 500 * 1024 * 1024:
            continue
        return ReleaseUpdate(release_version, download_url, name, sha256, size)
    return None


def validate_update_archive(path: str | Path) -> list[str]:
    archive_path = Path(path)
    safe_names: list[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            normalized = info.filename.replace("\\", "/")
            member = PurePosixPath(normalized)
            if member.is_absolute() or not member.parts or ".." in member.parts:
                raise ValueError(f"更新包包含不安全路径：{info.filename}")
            if member.parts[0].casefold() in PROTECTED_UPDATE_ROOTS:
                raise ValueError(f"更新包试图覆盖受保护目录：{info.filename}")
            safe_names.append(member.as_posix())
    missing = sorted(REQUIRED_UPDATE_FILES.difference(safe_names))
    if missing:
        raise ValueError("更新包缺少必要文件：" + ", ".join(missing))
    return safe_names


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _update_storage_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    path = base / "BaiduDataAutomation" / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


class GitHubUpdateManager(QObject):
    download_progress = Signal(int)
    ready = Signal(str, str)
    up_to_date = Signal()
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._check_and_download, daemon=True, name="github-update-check")
        self._thread.start()

    def _check_and_download(self) -> None:
        try:
            request = urllib.request.Request(
                GITHUB_LATEST_RELEASE_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"BaiduDataAutomation/{CURRENT_VERSION}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            with urllib.request.urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
            update = select_release_update(payload, CURRENT_VERSION)
            if update is None:
                self.up_to_date.emit()
                return
            archive_path = self._download(update)
            validate_update_archive(archive_path)
            self.ready.emit(update.version, str(archive_path))
        except Exception as exc:
            self.failed.emit(str(exc))

    def _download(self, update: ReleaseUpdate) -> Path:
        target = _update_storage_dir() / update.asset_name
        if target.is_file() and (not update.sha256 or _sha256(target) == update.sha256):
            self.download_progress.emit(100)
            return target

        partial = target.with_suffix(target.suffix + ".part")
        partial.unlink(missing_ok=True)
        request = urllib.request.Request(
            update.download_url,
            headers={"User-Agent": f"BaiduDataAutomation/{CURRENT_VERSION}"},
        )
        downloaded = 0
        with urllib.request.urlopen(request, timeout=20) as response, partial.open("wb") as output:
            total = update.size or int(response.headers.get("Content-Length") or 0)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    self.download_progress.emit(min(99, int(downloaded * 100 / total)))
        if update.sha256 and _sha256(partial) != update.sha256:
            partial.unlink(missing_ok=True)
            raise ValueError("更新包 SHA-256 校验失败")
        partial.replace(target)
        self.download_progress.emit(100)
        return target


UPDATE_HELPER_SOURCE = r'''from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath


PROTECTED = {"configs", "secrets", "logs", "reports", "backups", "browser_profile", "kst_exports", "samples", ".venv", "runtime"}


def wait_for_exit(pid: int) -> None:
    for _ in range(180):
        try:
            os.kill(pid, 0)
        except OSError:
            time.sleep(1.0)
            return
        time.sleep(0.5)
    raise RuntimeError("旧程序未能及时退出")


def safe_members(archive: zipfile.ZipFile):
    for info in archive.infolist():
        if info.is_dir():
            continue
        member = PurePosixPath(info.filename.replace("\\", "/"))
        if member.is_absolute() or ".." in member.parts or not member.parts:
            raise ValueError("更新包路径不安全")
        if member.parts[0].casefold() in PROTECTED:
            raise ValueError("更新包包含受保护目录")
        yield info, member


def replace_with_retry(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_name(target.name + ".update-new")
    shutil.copy2(source, staged)
    for attempt in range(60):
        try:
            os.replace(staged, target)
            return
        except PermissionError:
            if attempt == 59:
                raise
            time.sleep(0.5)


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    package = Path(sys.argv[2]).resolve()
    version = sys.argv[3]
    launcher = Path(sys.argv[4]).resolve()
    pid = int(sys.argv[5])
    storage = Path(sys.argv[6]).resolve()
    log_path = storage / "update_apply.log"
    try:
        wait_for_exit(pid)
        backup = storage / "backups" / (version + "_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        with tempfile.TemporaryDirectory(prefix="baidu-update-") as temp_dir:
            temp = Path(temp_dir)
            with zipfile.ZipFile(package) as archive:
                members = list(safe_members(archive))
                archive.extractall(temp, [info for info, _member in members])
            for _info, member in members:
                source = temp.joinpath(*member.parts)
                target = root.joinpath(*member.parts)
                if target.exists():
                    backup_target = backup.joinpath(*member.parts)
                    backup_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup_target)
                replace_with_retry(source, target)
        subprocess.Popen([str(launcher)], cwd=str(root))
        log_path.write_text(f"updated={version}\n", encoding="utf-8")
        return 0
    except Exception as exc:
        log_path.write_text(f"failed={exc}\n", encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def launch_update_helper(
    root: str | Path,
    archive_path: str | Path,
    version: str,
    launcher_path: str | Path | None = None,
) -> None:
    root_path = Path(root).resolve()
    archive = Path(archive_path).resolve()
    validate_update_archive(archive)
    pythonw = root_path / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw.exists():
        pythonw = root_path / ".venv" / "Scripts" / "python.exe"
    if not pythonw.exists():
        raise FileNotFoundError("缺少项目 Python，无法启动更新程序")

    launcher = root_path / APP_EXE_NAME
    if not launcher.exists() and launcher_path:
        launcher = Path(launcher_path).resolve()
    if not launcher.exists():
        raise FileNotFoundError("找不到更新后需要重启的 GUI 程序")

    storage = _update_storage_dir()
    helper = storage / "apply_update.py"
    helper.write_text(UPDATE_HELPER_SOURCE, encoding="utf-8")
    flags = 0
    if os.name == "nt":
        flags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    subprocess.Popen(
        [
            str(pythonw),
            str(helper),
            str(root_path),
            str(archive),
            version,
            str(launcher),
            str(os.getpid()),
            str(storage),
        ],
        cwd=str(root_path),
        close_fds=True,
        creationflags=flags,
    )
