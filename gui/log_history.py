from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


HISTORY_LOG_NAME = "gui_history.log"
MAX_TYPEWRITER_BATCH = 96

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|pwd|access[_-]?token|refresh[_-]?token|authorization|"
    r"secret[_-]?key|hmac[_-]?client[_-]?key|authcode)\b(\s*[:=]\s*)([^\s,;，；]+)"
)
_JWT_TOKEN = re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]{10,})?\b")


def redact_history_text(text: str) -> str:
    clean = str(text or "").replace("\r", " ").replace("\n", " ")
    clean = _SENSITIVE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}***", clean)
    return _JWT_TOKEN.sub("***", clean)


def append_history_line(
    root: str | Path,
    text: str,
    *,
    now: datetime | None = None,
) -> Path:
    history_path = Path(root) / "logs" / HISTORY_LOG_NAME
    history_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    with history_path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(f"[{timestamp}] {redact_history_text(text)}\n")
    return history_path


def typewriter_batch_size(pending_chars: int) -> int:
    pending = max(0, int(pending_chars))
    if pending == 0:
        return 0
    return min(MAX_TYPEWRITER_BATCH, max(2, (pending + 11) // 12))
