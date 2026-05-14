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

    # 终端：不输出 logger 内容，终端只走 console_ui
    # logger 详细错误仅保留在 logs/run.log

    # 抑制 openpyxl 日志
    logging.getLogger("openpyxl").setLevel(logging.ERROR)

    # 抑制 openpyxl 默认样式 warning（warnings 模块层面）
    warnings.filterwarnings(
        "ignore",
        message="Workbook contains no default style, apply openpyxl's default",
    )

    return logger
