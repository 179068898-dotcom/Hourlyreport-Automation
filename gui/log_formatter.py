from __future__ import annotations

import html
import re


PROJECT_NAMES = [
    "昆明牛",
    "南京牛",
    "宁波牛",
    "长沙牛",
    "沈阳牛",
    "合肥白",
    "青岛白",
    "沈阳白",
    "南京白",
    "深圳白",
]


PATH_PATTERN = re.compile(r"([A-Za-z]:\\[^\s，。；;]+|(?:reports|logs|configs|dist|backups|kst_exports)/[^\s，。；;]+|[^\s，。；;]+\.xlsx)")


STYLE_BY_CLASS = {
    "log-path": "color:#93c5fd;",
    "log-pass": "color:#86efac;",
    "log-error": "color:#fca5a5;",
    "log-project": "color:#fcd34d;",
    "log-excel": "color:#c4b5fd;",
}


def _wrap(text: str, class_name: str) -> str:
    return f'<span class="{class_name}" style="{STYLE_BY_CLASS[class_name]}">{text}</span>'


def format_log_html(line: str) -> str:
    escaped = html.escape(str(line or ""))

    escaped = PATH_PATTERN.sub(lambda match: _wrap(match.group(0), "log-path"), escaped)
    for project_name in PROJECT_NAMES:
        escaped = escaped.replace(html.escape(project_name), _wrap(html.escape(project_name), "log-project"))
    for word in ["通过", "成功", "完成", "OK", "passed"]:
        escaped = escaped.replace(html.escape(word), _wrap(html.escape(word), "log-pass"))
    for word in ["失败", "错误", "ERROR", "failed"]:
        escaped = escaped.replace(html.escape(word), _wrap(html.escape(word), "log-error"))
    for word in ["Excel", ".xlsx"]:
        escaped = escaped.replace(html.escape(word), _wrap(html.escape(word), "log-excel"))

    return f"<div>{escaped}</div>"
