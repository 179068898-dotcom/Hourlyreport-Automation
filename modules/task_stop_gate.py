from __future__ import annotations

import os
import time
from pathlib import Path


STOP_GATE_ENV = "ANTPOWER_TASK_STOP_GATE"
TASK_CANCELLED_EXIT_CODE = 130
_CANCEL = "cancel"
_EXCEL = "excel"


def resolve_task_stop_gate(root: Path) -> Path | None:
    raw_path = str(os.environ.get(STOP_GATE_ENV) or "").strip()
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    return path


def read_task_stop_decision(path: Path | None) -> str:
    if path is None:
        return ""
    for attempt in range(20):
        try:
            decision = path.read_text(encoding="ascii").strip().lower()
        except (FileNotFoundError, OSError, UnicodeError):
            return ""
        if decision in {_CANCEL, _EXCEL}:
            return decision
        if attempt < 19:
            time.sleep(0.002)
    return ""


def _claim_decision(path: Path, decision: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        return read_task_stop_decision(path)
    try:
        os.write(descriptor, decision.encode("ascii"))
    finally:
        os.close(descriptor)
    return decision


def request_task_stop(path: Path | None) -> bool:
    if path is None:
        return False
    return _claim_decision(path, _CANCEL) == _CANCEL


def task_stop_requested(root: Path) -> bool:
    return read_task_stop_decision(resolve_task_stop_gate(root)) == _CANCEL


def claim_excel_write(path_or_root: Path, *, resolve_from_environment: bool = False) -> bool:
    path = resolve_task_stop_gate(path_or_root) if resolve_from_environment else path_or_root
    if path is None:
        return True
    return _claim_decision(path, _EXCEL) == _EXCEL


def clear_task_stop_gate(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def pipeline_exit_code(report: dict) -> int:
    if report.get("passed"):
        return 0
    if report.get("cancelled"):
        return TASK_CANCELLED_EXIT_CODE
    return 1
