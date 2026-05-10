from __future__ import annotations

import re
from typing import Any

_FULL_WIDTH_SPACE = "\u3000"


def normalize_text(value: Any) -> str:
    """用于 Excel / 后台文本匹配的标准化。"""
    if value is None:
        return ""
    text = str(value)
    text = text.replace(_FULL_WIDTH_SPACE, " ")
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = re.sub(r"\s+", "", text.strip())
    return text.lower()


def normalize_for_display(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()
