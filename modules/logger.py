from __future__ import annotations

import logging
import warnings
from pathlib import Path


def setup_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("hourly_report_bot")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # 文件：完整 INFO
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)

    # 终端：只输出 WARNING 及以上
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    stream_handler.setLevel(logging.WARNING)
    logger.addHandler(stream_handler)

    # 抑制 openpyxl 日志
    logging.getLogger("openpyxl").setLevel(logging.ERROR)

    # 抑制 openpyxl 默认样式 warning（warnings 模块层面）
    warnings.filterwarnings(
        "ignore",
        message="Workbook contains no default style, apply openpyxl's default",
    )

    return logger
