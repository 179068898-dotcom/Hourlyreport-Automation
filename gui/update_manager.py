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
    "https://api.github.com/repos/179068898-dotcom/Hourlyreport-Automation/releases/latest"
)
UPDATE_ASSET_PATTERN = re.compile(r"^Hourlyreport_automation_v(\d+(?:\.\d+){3})\.zip$")
RELEASE_TAG_PATTERN = re.compile(r"^(?:Hourlyreport_)?v(\d+(?:\.\d+){3})$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
APP_EXE_NAME = "hourlyreport_automation.exe"
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
WINDOWS_RESERVED_PATH_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


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


def parse_release_version(tag_name: str) -> str:
    match = RELEASE_TAG_PATTERN.fullmatch(str(tag_name or "").strip())
    if not match:
        raise ValueError(f"无效 Release tag：{tag_name}")
    version = match.group(1)
    parse_version(version)
    return version


def select_release_update(payload: dict[str, Any], current_version: str) -> ReleaseUpdate | None:
    if payload.get("draft") or payload.get("prerelease"):
        return None
    try:
        release_version = parse_release_version(str(payload.get("tag_name") or ""))
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
        if not SHA256_PATTERN.fullmatch(sha256):
            continue
        if size <= 0 or size > 500 * 1024 * 1024:
            continue
        return ReleaseUpdate(release_version, download_url, name, sha256, size)
    return None


def _validated_update_member(filename: str, protected_roots: set[str]) -> PurePosixPath:
    normalized = str(filename).replace("\\", "/")
    raw_parts = normalized.split("/")
    if not normalized or normalized.startswith("/") or any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError(f"更新包包含不安全路径：{filename}")
    for part in raw_parts:
        if part.endswith((" ", ".")) or ":" in part or any(ord(char) < 32 for char in part):
            raise ValueError(f"更新包包含不安全的 Windows 路径：{filename}")
        device_name = part.split(".", 1)[0].casefold()
        if device_name in WINDOWS_RESERVED_PATH_NAMES:
            raise ValueError(f"更新包包含不安全的 Windows 设备名：{filename}")
    member = PurePosixPath(*raw_parts)
    if member.parts[0].casefold() in protected_roots:
        raise ValueError(f"更新包试图覆盖受保护目录：{filename}")
    return member


def validate_update_archive(path: str | Path) -> list[str]:
    archive_path = Path(path)
    safe_names: list[str] = []
    windows_names: set[str] = set()
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            member = _validated_update_member(info.filename, PROTECTED_UPDATE_ROOTS)
            windows_name = "/".join(part.casefold() for part in member.parts)
            if windows_name in windows_names:
                raise ValueError(f"更新包包含重复的 Windows 路径：{info.filename}")
            windows_names.add(windows_name)
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
    path = base / "HourlyreportAutomation" / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


class GitHubUpdateManager(QObject):
    checking = Signal()
    available = Signal(object)
    download_progress = Signal(int)
    ready = Signal(str, str)
    up_to_date = Signal()
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._check_thread: threading.Thread | None = None
        self._download_thread: threading.Thread | None = None

    def start(self) -> None:
        if self._check_thread is not None and self._check_thread.is_alive():
            return
        self.checking.emit()
        self._check_thread = threading.Thread(
            target=self._check_for_update,
            daemon=True,
            name="github-update-check",
        )
        self._check_thread.start()

    def _check_for_update(self) -> None:
        try:
            request = urllib.request.Request(
                GITHUB_LATEST_RELEASE_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"HourlyreportAutomation/{CURRENT_VERSION}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            with urllib.request.urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
            update = select_release_update(payload, CURRENT_VERSION)
            if update is None:
                self.up_to_date.emit()
                return
            self.available.emit(update)
        except Exception as exc:
            self.failed.emit(str(exc))

    def start_download(self, update: ReleaseUpdate) -> bool:
        if self._download_thread is not None and self._download_thread.is_alive():
            return False
        self._download_thread = threading.Thread(
            target=self._download_and_prepare,
            args=(update,),
            daemon=True,
            name="github-update-download",
        )
        self._download_thread.start()
        return True

    def _download_and_prepare(self, update: ReleaseUpdate) -> None:
        try:
            archive_path = self._download(update)
            validate_update_archive(archive_path)
            self.ready.emit(update.version, str(archive_path))
        except Exception as exc:
            self.failed.emit(str(exc))

    def _download(self, update: ReleaseUpdate) -> Path:
        target = _update_storage_dir() / update.asset_name
        if (
            target.is_file()
            and target.stat().st_size == update.size
            and _sha256(target) == update.sha256
        ):
            self.download_progress.emit(100)
            return target

        partial = target.with_suffix(target.suffix + ".part")
        partial.unlink(missing_ok=True)
        request = urllib.request.Request(
            update.download_url,
            headers={"User-Agent": f"HourlyreportAutomation/{CURRENT_VERSION}"},
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
        if downloaded != update.size:
            partial.unlink(missing_ok=True)
            raise ValueError(f"更新包大小校验失败：期望 {update.size}，实际 {downloaded}")
        if _sha256(partial) != update.sha256:
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
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

ROOT_ARG = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
if str(ROOT_ARG) not in sys.path:
    sys.path.insert(0, str(ROOT_ARG))

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from gui.update_dialog import UpdateInstallDialog


PROTECTED = {"configs", "secrets", "logs", "reports", "backups", "browser_profile", "kst_exports", "samples", ".venv", "runtime"}
CANONICAL_EXE = "hourlyreport_automation.exe"
WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class UpdateSignals(QObject):
    progress = Signal(int, str)
    completed = Signal(bool, str, str)


def wait_for_exit(pid: int) -> None:
    for _ in range(180):
        try:
            os.kill(pid, 0)
        except OSError:
            time.sleep(0.5)
            return
        time.sleep(0.5)
    raise RuntimeError("旧程序未能及时退出")


def safe_member_path(filename: str) -> PurePosixPath:
    normalized = str(filename).replace("\\", "/")
    raw_parts = normalized.split("/")
    if not normalized or normalized.startswith("/") or any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("更新包路径不安全")
    for part in raw_parts:
        if part.endswith((" ", ".")) or ":" in part or any(ord(char) < 32 for char in part):
            raise ValueError("更新包包含不安全的 Windows 路径")
        if part.split(".", 1)[0].casefold() in WINDOWS_RESERVED:
            raise ValueError("更新包包含不安全的 Windows 设备名")
    member = PurePosixPath(*raw_parts)
    if member.parts[0].casefold() in PROTECTED:
        raise ValueError("更新包包含受保护目录")
    return member


def safe_members(archive: zipfile.ZipFile):
    windows_names: set[str] = set()
    for info in archive.infolist():
        if info.is_dir():
            continue
        member = safe_member_path(info.filename)
        windows_name = "/".join(part.casefold() for part in member.parts)
        if windows_name in windows_names:
            raise ValueError("更新包包含重复的 Windows 路径")
        windows_names.add(windows_name)
        yield info, member


def replace_with_retry(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_name(target.name + ".update-new")
    staged.unlink(missing_ok=True)
    shutil.copy2(source, staged)
    for attempt in range(60):
        try:
            os.replace(staged, target)
            return
        except PermissionError:
            if attempt == 59:
                staged.unlink(missing_ok=True)
                raise
            time.sleep(0.5)


def backup_target(root: Path, backup: Path, target: Path, backed_up: set[Path]) -> bool:
    relative = target.relative_to(root)
    if relative in backed_up:
        return target.exists()
    backed_up.add(relative)
    if not target.exists():
        return False
    destination = backup / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, destination)
    return True


def rollback(root: Path, backup: Path, created: set[Path], backed_up: set[Path]) -> None:
    errors: list[str] = []
    for relative in sorted(created, key=lambda item: len(item.parts), reverse=True):
        try:
            (root / relative).unlink(missing_ok=True)
        except OSError as exc:
            errors.append(f"删除 {relative} 失败：{exc}")
    for relative in sorted(backed_up, key=lambda item: item.as_posix().casefold()):
        source = backup / relative
        if source.is_file():
            try:
                replace_with_retry(source, root / relative)
            except OSError as exc:
                errors.append(f"恢复 {relative} 失败：{exc}")
    if errors:
        raise RuntimeError("；".join(errors))


def apply_update(
    root: Path,
    package: Path,
    version: str,
    pid: int,
    storage: Path,
    signals: UpdateSignals,
) -> tuple[bool, str, Path | None]:
    log_path = storage / "update_apply.log"
    backup = storage / "backups" / (version + "_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    backed_up: set[Path] = set()
    created: set[Path] = set()
    try:
        signals.progress.emit(8, "正在关闭旧程序…")
        wait_for_exit(pid)
        signals.progress.emit(18, "正在校验更新包…")
        with tempfile.TemporaryDirectory(prefix="hourlyreport-update-") as temp_dir:
            temp = Path(temp_dir)
            with zipfile.ZipFile(package) as archive:
                members = list(safe_members(archive))
                archive.extractall(temp, [info for info, _member in members])
            if not any(member.as_posix().casefold() == CANONICAL_EXE.casefold() for _info, member in members):
                raise ValueError("更新包缺少主程序")
            total = max(1, len(members))
            for index, (_info, member) in enumerate(members, start=1):
                source = temp.joinpath(*member.parts)
                target = root.joinpath(*member.parts)
                existed = backup_target(root, backup, target, backed_up)
                if not existed:
                    created.add(target.relative_to(root))
                replace_with_retry(source, target)
                signals.progress.emit(20 + int(index * 65 / total), "正在安装程序文件…")

        canonical = root / CANONICAL_EXE
        signals.progress.emit(96, "正在完成更新…")
        log_path.write_text(f"updated={version}\n", encoding="utf-8")
        return True, "", canonical
    except Exception as exc:
        rollback_error = None
        try:
            rollback(root, backup, created, backed_up)
            rollback_result = "rollback=ok"
        except Exception as rollback_exc:
            rollback_error = rollback_exc
            rollback_result = f"rollback=failed:{rollback_exc}"
        log_path.write_text(f"failed={exc}\n{rollback_result}\n", encoding="utf-8")
        if rollback_error is not None:
            message = f"{exc}；自动恢复未完全成功：{rollback_error}。请保留更新备份并联系管理员。"
            return False, message, None
        return False, str(exc), root / CANONICAL_EXE


def run_update_install_dialog(
    root: Path,
    package: Path,
    version: str,
    pid: int,
    storage: Path,
) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    dialog = UpdateInstallDialog(version)
    signals = UpdateSignals()
    result = {"ok": False}

    def finished(ok: bool, message: str, launcher: str) -> None:
        result["ok"] = ok
        if ok:
            dialog.set_progress(100, "更新完成，正在重启…")
            QApplication.processEvents()
            subprocess.Popen([launcher], cwd=str(root))
        else:
            dialog.hide()
            QMessageBox.critical(None, "更新失败", f"程序已尝试恢复原版本。\n\n失败原因：{message}")
            if launcher and Path(launcher).is_file():
                subprocess.Popen([launcher], cwd=str(root))
        app.quit()

    signals.progress.connect(dialog.set_progress)
    signals.completed.connect(finished)
    dialog.show()

    def worker() -> None:
        ok, message, launcher = apply_update(root, package, version, pid, storage, signals)
        signals.completed.emit(ok, message, str(launcher) if launcher else "")

    threading.Thread(target=worker, daemon=True, name="hourlyreport-update-apply").start()
    app.exec()
    return 0 if result["ok"] else 1


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    package = Path(sys.argv[2]).resolve()
    version = sys.argv[3]
    pid = int(sys.argv[5])
    storage = Path(sys.argv[6]).resolve()
    return run_update_install_dialog(root, package, version, pid, storage)


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
