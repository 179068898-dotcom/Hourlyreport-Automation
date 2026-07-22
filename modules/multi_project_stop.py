from __future__ import annotations

import os
from pathlib import Path


MULTI_QUEUE_STOP_GATE_ENV = "ANTPOWER_MULTI_QUEUE_STOP_GATE"


def resolve_multi_queue_stop_gate(root: str | Path) -> Path | None:
    value = str(os.environ.get(MULTI_QUEUE_STOP_GATE_ENV) or "").strip()
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else Path(root) / path
