from __future__ import annotations

import html
import re


PROJECT_NAMES = [
    "昆明牛",
    "南京牛",
    "宁波牛",
    "长沙牛",
    "沈阳牛",
    "青岛白",
    "沈阳白",
    "南京白",
    "深圳白",
]


PATH_PATTERN = re.compile(
    r"([A-Za-z]:\\[^\s，。；;]+|(?:reports|logs|configs|dist|backups|kst_exports)/[^\s，。；;]+|[^\s，。；;]+\.xlsx)"
)


STYLE_BY_CLASS = {
    "log-path": "color:#38d7ff;",
    "log-pass": "color:#56e58f;",
    "log-warn": "color:#facc15;",
    "log-error": "color:#fca5a5;",
    "log-project": "color:#fcd34d;",
    "log-excel": "color:#c4b5fd;",
}


def _wrap(text: str, class_name: str) -> str:
    return f'<span class="{class_name}" style="{STYLE_BY_CLASS[class_name]}">{text}</span>'


def _replace_words(escaped: str, words: list[str], class_name: str) -> str:
    for word in words:
        escaped = escaped.replace(html.escape(word), _wrap(html.escape(word), class_name))
    return escaped


def format_log_fragment(line: str) -> str:
    escaped = html.escape(str(line or ""))

    escaped = PATH_PATTERN.sub(lambda match: _wrap(match.group(0), "log-path"), escaped)
    for project_name in PROJECT_NAMES:
        escaped = escaped.replace(html.escape(project_name), _wrap(html.escape(project_name), "log-project"))

    escaped = _replace_words(escaped, ["[通知]", "通过", "成功", "完成", "复核通过", "OK", "passed"], "log-pass")
    escaped = _replace_words(escaped, ["[注意]", "注意", "覆盖"], "log-warn")
    escaped = _replace_words(escaped, ["失败", "错误", "ERROR", "failed"], "log-error")
    escaped = _replace_words(escaped, ["Excel", ".xlsx"], "log-excel")

    return escaped


def format_log_html(line: str) -> str:
    return f"<div>{format_log_fragment(line)}</div>"
