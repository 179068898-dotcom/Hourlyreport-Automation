from __future__ import annotations

import os
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QPoint, QRectF, QSize, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCalendarWidget,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QProgressBar,
    QSizeGrip,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.command_builder import build_daily_command, build_hourly_command, build_preflight_command
from gui.environment_check import run_environment_check
from gui.log_formatter import format_log_html
from gui.project_store import ProjectSummary, load_project_summaries
from gui.task_runner import QtTaskRunner
from modules.project_config import get_excel_path, load_project_config


STAGES = [
    ("environment", "环境检测", "shield"),
    ("config", "项目配置", "gear"),
    ("preflight", "快速自检", "stethoscope"),
    ("login", "登录账号", "login"),
    ("baidu", "百度数据", "paw"),
    ("kst", "快商通数据", "chat"),
    ("excel", "Excel写入", "sheet"),
    ("done", "报告输出", "report"),
]
MAIN_FONT_PT = 8
SUB_FONT_PT = 7


def make_line_icon(kind: str, color: str = "#087a46", size: int = 24) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color), max(1.6, size / 13), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    s = float(size)

    if kind == "shield":
        points = [
            QPoint(round(s * 0.50), round(s * 0.12)),
            QPoint(round(s * 0.82), round(s * 0.25)),
            QPoint(round(s * 0.76), round(s * 0.66)),
            QPoint(round(s * 0.50), round(s * 0.88)),
            QPoint(round(s * 0.24), round(s * 0.66)),
            QPoint(round(s * 0.18), round(s * 0.25)),
        ]
        painter.drawPolygon(points)
        painter.drawLine(round(s * 0.36), round(s * 0.50), round(s * 0.46), round(s * 0.61))
        painter.drawLine(round(s * 0.46), round(s * 0.61), round(s * 0.66), round(s * 0.39))
    elif kind == "gear":
        painter.drawEllipse(QRectF(s * 0.34, s * 0.34, s * 0.32, s * 0.32))
        for x1, y1, x2, y2 in [(0.50, 0.10, 0.50, 0.24), (0.50, 0.76, 0.50, 0.90), (0.10, 0.50, 0.24, 0.50), (0.76, 0.50, 0.90, 0.50), (0.22, 0.22, 0.32, 0.32), (0.68, 0.68, 0.78, 0.78), (0.78, 0.22, 0.68, 0.32), (0.32, 0.68, 0.22, 0.78)]:
            painter.drawLine(round(s * x1), round(s * y1), round(s * x2), round(s * y2))
    elif kind == "stethoscope":
        painter.drawArc(QRectF(s * 0.18, s * 0.16, s * 0.36, s * 0.42), 180 * 16, 180 * 16)
        painter.drawLine(round(s * 0.18), round(s * 0.36), round(s * 0.18), round(s * 0.54))
        painter.drawLine(round(s * 0.54), round(s * 0.36), round(s * 0.54), round(s * 0.54))
        painter.drawLine(round(s * 0.36), round(s * 0.58), round(s * 0.36), round(s * 0.72))
        painter.drawLine(round(s * 0.36), round(s * 0.72), round(s * 0.68), round(s * 0.72))
        painter.drawEllipse(QRectF(s * 0.66, s * 0.64, s * 0.16, s * 0.16))
    elif kind == "login":
        painter.drawEllipse(QRectF(s * 0.18, s * 0.15, s * 0.28, s * 0.28))
        painter.drawArc(QRectF(s * 0.10, s * 0.48, s * 0.44, s * 0.34), 25 * 16, 130 * 16)
        painter.drawLine(round(s * 0.58), round(s * 0.50), round(s * 0.88), round(s * 0.50))
        painter.drawLine(round(s * 0.76), round(s * 0.38), round(s * 0.88), round(s * 0.50))
        painter.drawLine(round(s * 0.76), round(s * 0.62), round(s * 0.88), round(s * 0.50))
    elif kind == "paw":
        painter.drawEllipse(QRectF(s * 0.34, s * 0.42, s * 0.32, s * 0.34))
        for x, y in [(0.22, 0.24), (0.40, 0.16), (0.58, 0.16), (0.76, 0.24)]:
            painter.drawEllipse(QRectF(s * x - s * 0.055, s * y, s * 0.11, s * 0.16))
    elif kind == "chat":
        painter.drawRoundedRect(QRectF(s * 0.15, s * 0.22, s * 0.70, s * 0.48), s * 0.10, s * 0.10)
        painter.drawLine(round(s * 0.36), round(s * 0.70), round(s * 0.25), round(s * 0.84))
        for x in [0.34, 0.50, 0.66]:
            painter.drawPoint(round(s * x), round(s * 0.47))
    elif kind == "sheet":
        painter.drawRect(QRectF(s * 0.22, s * 0.14, s * 0.56, s * 0.72))
        painter.drawLine(round(s * 0.38), round(s * 0.34), round(s * 0.62), round(s * 0.66))
        painter.drawLine(round(s * 0.62), round(s * 0.34), round(s * 0.38), round(s * 0.66))
    elif kind == "report":
        painter.drawRect(QRectF(s * 0.24, s * 0.12, s * 0.52, s * 0.74))
        for y in [0.36, 0.52, 0.68]:
            painter.drawLine(round(s * 0.36), round(s * y), round(s * 0.64), round(s * y))
    elif kind == "clock":
        painter.drawEllipse(QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64))
        painter.drawLine(round(s * 0.50), round(s * 0.50), round(s * 0.50), round(s * 0.30))
        painter.drawLine(round(s * 0.50), round(s * 0.50), round(s * 0.64), round(s * 0.58))
    elif kind == "calendar":
        painter.drawRoundedRect(QRectF(s * 0.18, s * 0.22, s * 0.64, s * 0.58), s * 0.06, s * 0.06)
        painter.drawLine(round(s * 0.18), round(s * 0.38), round(s * 0.82), round(s * 0.38))
        painter.drawLine(round(s * 0.34), round(s * 0.14), round(s * 0.34), round(s * 0.28))
        painter.drawLine(round(s * 0.66), round(s * 0.14), round(s * 0.66), round(s * 0.28))
    elif kind == "play":
        painter.setBrush(QColor(color))
        points = [
            QPoint(round(s * 0.36), round(s * 0.24)),
            QPoint(round(s * 0.36), round(s * 0.76)),
            QPoint(round(s * 0.78), round(s * 0.50)),
        ]
        painter.drawPolygon(points)
    elif kind == "task":
        painter.drawRoundedRect(QRectF(s * 0.25, s * 0.16, s * 0.50, s * 0.68), s * 0.06, s * 0.06)
        painter.drawLine(round(s * 0.36), round(s * 0.42), round(s * 0.64), round(s * 0.42))
        painter.drawLine(round(s * 0.36), round(s * 0.58), round(s * 0.58), round(s * 0.58))
    else:
        painter.drawEllipse(QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56))

    painter.end()
    return QIcon(pixmap)


class PixelSnakeSpinner(QWidget):
    def __init__(self, parent=None, size: int = 22):
        super().__init__(parent)
        self.setObjectName("pixelSnakeSpinner")
        self.setFixedSize(size, size)
        self._size = size
        self._tick = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(120)

    def _advance(self) -> None:
        self._tick = (self._tick + 1) % 8
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        scale = self._size / 22
        points = [(9, 2), (14, 4), (18, 9), (16, 16), (9, 19), (4, 16), (2, 9), (4, 4)]
        colors = ["#1f9b61", "#38ad73", "#62c68c", "#8addaa", "#b2ecc8", "#d4f6e1", "#e9faf0", "#f2fbf6"]
        block = max(3, round(4 * scale))
        for offset in range(8):
            index = (self._tick - offset) % 8
            x, y = points[index]
            painter.fillRect(round(x * scale), round(y * scale), block, block, QColor(colors[offset]))


class HoverMenuButton(QPushButton):
    def enterEvent(self, event) -> None:
        menu = self.menu()
        if menu:
            menu.popup(self.mapToGlobal(QPoint(0, self.height())))
        super().enterEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, root: str | Path):
        super().__init__()
        self.root = Path(root)
        self.projects: list[ProjectSummary] = []
        self.stage_labels: dict[str, QPushButton] = {}
        self.stage_buttons: list[QPushButton] = []
        self.period_values = ["11点", "15点", "18点"]
        self.current_task_type = ""
        self.current_project_name = ""
        self.current_hour = ""
        self.current_daily_date_text = ""
        self.current_status = "idle"
        self.current_start_time = ""

        self.runner = QtTaskRunner(self)
        self.runner.output.connect(self.append_log)
        self.runner.stage_changed.connect(self.mark_stage)
        self.runner.started.connect(self.on_task_started)
        self.runner.finished.connect(self.on_task_finished)
        self.runner.failed_to_start.connect(self.show_task_error)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setWindowIcon(QIcon())
        self.setWindowTitle("百度数据自动化控制台")
        self.setFont(QFont("Microsoft YaHei UI", MAIN_FONT_PT))
        self.resize(1120, 740)
        self.setMinimumSize(960, 640)
        self._drag_offset = None
        self._build_ui()
        self._apply_style()
        self.refresh_projects()
        self.set_current_flow_idle()
        self.run_startup_check()

    def _make_card(self, object_name: str = "dashboardCard") -> QFrame:
        card = QFrame()
        card.setObjectName(object_name)
        return card

    def _make_icon_label(self, text: str, name: str = "cardIcon") -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFixedSize(28, 28)
        return label

    def _make_icon_box(self, kind: str, color: str = "#2f80ed") -> QLabel:
        label = QLabel()
        label.setObjectName("cardIcon")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFixedSize(28, 28)
        label.setPixmap(make_line_icon(kind, color, 20).pixmap(20, 20))
        return label

    def _make_primary_button(self, text: str, icon: str = "play") -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("primaryActionButton")
        button.setIcon(make_line_icon(icon, "#ffffff", 20))
        button.setIconSize(QSize(18, 18))
        button.setMinimumHeight(42)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def _make_secondary_button(self, text: str, icon: str = "") -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("secondaryActionButton")
        if icon:
            button.setIcon(make_line_icon(icon, "#2f80ed", 20))
            button.setIconSize(QSize(18, 18))
        button.setMinimumHeight(40)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def _build_ui(self) -> None:
        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        root_layout = QVBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.title_bar = QFrame()
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setFixedHeight(54)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(22, 0, 14, 0)
        title_layout.setSpacing(12)
        self.spinner = PixelSnakeSpinner(self.title_bar, size=26)
        title_layout.addWidget(self.spinner)
        self.title_label = QLabel("百度数据自动化控制台")
        self.title_label.setObjectName("windowTitleLabel")
        self.title_label.setFont(QFont("Microsoft YaHei UI", MAIN_FONT_PT + 2))
        title_layout.addWidget(self.title_label)

        self.system_config_button = HoverMenuButton("系统配置  ▾")
        self.system_config_button.setObjectName("systemConfigButton")
        self.system_config_menu = QMenu(self.system_config_button)
        update_path_action = QAction("更新路径", self.system_config_menu)
        update_credentials_action = QAction("更新账号密码", self.system_config_menu)
        restore_backup_action = QAction("恢复备份", self.system_config_menu)
        update_path_action.triggered.connect(self.open_selected_project_config)
        update_credentials_action.triggered.connect(self.open_credentials_config)
        restore_backup_action.triggered.connect(self.restore_backup)
        self.system_config_menu.addAction(update_path_action)
        self.system_config_menu.addAction(update_credentials_action)
        self.system_config_menu.addAction(restore_backup_action)
        self.system_config_button.setMenu(self.system_config_menu)
        title_layout.addWidget(self.system_config_button)
        title_layout.addStretch(1)

        self.minimize_button = QPushButton("—")
        self.maximize_button = QPushButton("□")
        self.close_button = QPushButton("×")
        self.minimize_button.setObjectName("windowControlButton")
        self.maximize_button.setObjectName("windowControlButton")
        self.close_button.setObjectName("windowCloseButton")
        for button in [self.minimize_button, self.maximize_button, self.close_button]:
            button.setFixedSize(36, 30)
            title_layout.addWidget(button)
        self.minimize_button.clicked.connect(self.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(self.close)
        root_layout.addWidget(self.title_bar)

        shell = QHBoxLayout()
        shell.setContentsMargins(18, 4, 18, 18)
        shell.setSpacing(14)
        root_layout.addLayout(shell, 1)

        self.left_panel = QFrame()
        self.left_panel.setObjectName("leftRail")
        self.left_panel.setMinimumWidth(390)
        self.left_panel.setMaximumWidth(390)
        self.left_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)
        self._build_left_panel(left_layout)

        self.content_panel = QFrame()
        self.content_panel.setObjectName("contentPanel")
        content_layout = QVBoxLayout(self.content_panel)
        content_layout.setContentsMargins(24, 18, 24, 18)
        content_layout.setSpacing(14)
        self._build_right_panel(content_layout)

        shell.addWidget(self.left_panel)
        shell.addWidget(self.content_panel, 1)
        self.size_grip = QSizeGrip(root_widget)
        self.size_grip.setObjectName("sizeGrip")
        root_layout.addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

    def _build_left_panel(self, left_layout: QVBoxLayout) -> None:
        self.task_control_card = self._make_card()
        self.task_control_card.setMinimumHeight(214)
        task_layout = QVBoxLayout(self.task_control_card)
        task_layout.setContentsMargins(20, 18, 20, 18)
        task_layout.setSpacing(9)

        title_row = QHBoxLayout()
        title_row.setSpacing(14)
        title_row.addWidget(self._make_icon_box("task"))
        task_title = QLabel("任务控制台")
        task_title.setObjectName("cardTitle")
        title_row.addWidget(task_title)
        title_row.addStretch(1)
        task_layout.addLayout(title_row)

        subtitle = QLabel("选择项目和任务，执行过程会实时显示。")
        subtitle.setObjectName("mutedText")
        subtitle.setWordWrap(True)
        task_layout.addWidget(subtitle)

        project_title_row = QHBoxLayout()
        project_label = QLabel("项目")
        project_label.setObjectName("sectionTitle")
        project_hint = QLabel("当前任务")
        project_hint.setObjectName("pillHint")
        project_title_row.addWidget(project_label)
        project_title_row.addStretch(1)
        project_title_row.addWidget(project_hint)
        task_layout.addLayout(project_title_row)

        self.project_combo = QComboBox()
        self.project_combo.setObjectName("projectCombo")
        self.project_combo.setMinimumHeight(40)
        task_layout.addWidget(self.project_combo)

        self.progress_text = QLabel("项目就绪后会显示任务进度")
        self.progress_text.setObjectName("taskProgressText")
        self.progress_text.setFont(QFont("Microsoft YaHei UI", SUB_FONT_PT))
        self.progress_text.setWordWrap(True)
        task_layout.addWidget(self.progress_text)
        self.progress = QProgressBar()
        self.progress.setObjectName("taskProgress")
        self.progress.setRange(0, len(STAGES))
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        task_layout.addWidget(self.progress)
        left_layout.addWidget(self.task_control_card)

        self.hourly_card = self._make_card()
        self.hourly_card.setMinimumHeight(198)
        hourly_layout = QVBoxLayout(self.hourly_card)
        hourly_layout.setContentsMargins(20, 18, 20, 18)
        hourly_layout.setSpacing(12)
        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(self._make_icon_box("clock"))
        hourly_title = QLabel("小时报")
        hourly_title.setObjectName("cardTitle")
        header.addWidget(hourly_title)
        header.addStretch(1)
        hourly_layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(16)
        button_col = QVBoxLayout()
        button_col.setSpacing(12)
        self.hourly_button = self._make_primary_button("运行小时报")
        self.environment_check_button = self._make_secondary_button("执行环境自检", "shield")
        button_col.addWidget(self.hourly_button)
        button_col.addWidget(self.environment_check_button)
        button_col.addStretch(1)
        body.addLayout(button_col, 3)

        divider = QFrame()
        divider.setObjectName("verticalDivider")
        divider.setFixedWidth(1)
        body.addWidget(divider)

        period_column = QVBoxLayout()
        period_column.setSpacing(10)
        period_label = QLabel("小时段")
        period_label.setObjectName("sectionTitle")
        period_column.addWidget(period_label)
        self.period_group = QButtonGroup(self)
        self.period_group.setExclusive(True)
        self.period_buttons: list[QPushButton] = []
        for text in self.period_values:
            button = QPushButton(text)
            button.setProperty("periodValue", text)
            button.setObjectName("periodButton")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setMinimumSize(116, 32)
            button.toggled.connect(self.update_period_button_texts)
            self.period_group.addButton(button)
            self.period_buttons.append(button)
            period_column.addWidget(button)
        self.period_buttons[1].setChecked(True)
        self.update_period_button_texts()
        body.addLayout(period_column, 2)
        hourly_layout.addLayout(body)
        left_layout.addWidget(self.hourly_card)

        self.daily_card = self._make_card()
        self.date_card = self.daily_card
        self.daily_card.setMinimumHeight(202)
        daily_layout = QVBoxLayout(self.daily_card)
        daily_layout.setContentsMargins(20, 18, 20, 18)
        daily_layout.setSpacing(11)
        daily_header = QHBoxLayout()
        daily_header.setSpacing(14)
        daily_header.addWidget(self._make_icon_box("calendar"))
        daily_title = QLabel("日报")
        daily_title.setObjectName("cardTitle")
        daily_header.addWidget(daily_title)
        daily_header.addStretch(1)
        daily_layout.addLayout(daily_header)

        daily_button_row = QHBoxLayout()
        daily_button_row.setSpacing(14)
        self.daily_button = self._make_primary_button("运行日报")
        self.default_yesterday_button = self._make_secondary_button("默认昨天")
        self.default_yesterday_button.setObjectName("dateHintButton")
        self.default_yesterday_button.clicked.connect(self.reset_daily_date_to_yesterday)
        daily_button_row.addWidget(self.daily_button, 3)
        daily_button_row.addWidget(self.default_yesterday_button, 1)
        daily_layout.addLayout(daily_button_row)

        date_title = QLabel("日报日期")
        date_title.setObjectName("sectionTitle")
        daily_layout.addWidget(date_title)
        yesterday = date.today() - timedelta(days=1)
        self.current_daily_date = yesterday
        self.date_button = QPushButton(yesterday.isoformat())
        self.date_button.setObjectName("datePickerButton")
        self.date_button.setIcon(make_line_icon("calendar", "#2f80ed", 20))
        self.date_button.setIconSize(QSize(18, 18))
        self.date_button.setMinimumHeight(40)
        self.date_button.clicked.connect(self.pick_daily_date)
        daily_layout.addWidget(self.date_button)
        left_layout.addWidget(self.daily_card)
        left_layout.addStretch(1)

        self.hourly_button.clicked.connect(self.run_hourly)
        self.daily_button.clicked.connect(self.run_daily)
        self.environment_check_button.clicked.connect(self.run_environment_preflight)

    def _build_right_panel(self, content_layout: QVBoxLayout) -> None:
        self.status_title = QLabel("准备就绪")
        self.status_detail = QLabel("选择左侧任务开始执行。")
        self.status_title.hide()
        self.status_detail.hide()

        stage_grid = QGridLayout()
        stage_grid.setHorizontalSpacing(22)
        stage_grid.setVerticalSpacing(18)
        self.stage_labels.clear()
        self.stage_buttons.clear()
        for index, (key, label, icon) in enumerate(STAGES):
            button = QPushButton(label)
            button.setObjectName("stageActionButton")
            button.setIcon(make_line_icon(icon, "#087a46", 22))
            button.setIconSize(QSize(18, 18))
            button.setMinimumHeight(42)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.stage_labels[key] = button
            self.stage_buttons.append(button)
            stage_grid.addWidget(button, index // 4, index % 4)
        content_layout.addLayout(stage_grid)

        self.current_flow_panel = self._make_card("currentFlowPanel")
        flow_layout = QVBoxLayout(self.current_flow_panel)
        flow_layout.setContentsMargins(22, 18, 22, 18)
        flow_layout.setSpacing(14)
        flow_header = QHBoxLayout()
        flow_icon = QLabel()
        flow_icon.setObjectName("flowHeaderIcon")
        flow_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        flow_icon.setFixedSize(24, 24)
        flow_icon.setPixmap(make_line_icon("stethoscope", "#1f2a44", 20).pixmap(20, 20))
        self.current_flow_title = QLabel("当前流程")
        self.current_flow_title.setObjectName("flowTitle")
        flow_header.addWidget(flow_icon)
        flow_header.addWidget(self.current_flow_title)
        flow_header.addStretch(1)
        flow_layout.addLayout(flow_header)

        flow_card = QFrame()
        flow_card.setObjectName("flowStatusCard")
        flow_card_layout = QHBoxLayout(flow_card)
        flow_card_layout.setContentsMargins(18, 16, 22, 16)
        flow_card_layout.setSpacing(16)
        accent = QFrame()
        accent.setObjectName("flowAccent")
        accent.setFixedWidth(5)
        flow_card_layout.addWidget(accent)
        self.flow_spinner = PixelSnakeSpinner(flow_card, size=24)
        flow_card_layout.addWidget(self.flow_spinner)
        flow_text = QVBoxLayout()
        flow_text.setSpacing(4)
        self.current_task_title = QLabel("暂无运行任务")
        self.current_task_title.setObjectName("currentTaskTitle")
        self.current_task_subtitle = QLabel("请选择左侧任务开始执行")
        self.current_task_subtitle.setObjectName("currentTaskSubtitle")
        flow_text.addWidget(self.current_task_title)
        flow_text.addWidget(self.current_task_subtitle)
        flow_card_layout.addLayout(flow_text, 1)
        flow_right = QVBoxLayout()
        flow_right.setSpacing(12)
        flow_right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.current_status_badge = QLabel("空闲")
        self.current_status_badge.setObjectName("statusBadge")
        self.current_status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_start_time_label = QLabel("开始时间：--")
        self.current_start_time_label.setObjectName("startTimeText")
        self.current_start_time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        flow_right.addWidget(self.current_status_badge)
        flow_right.addWidget(self.current_start_time_label)
        flow_card_layout.addLayout(flow_right)
        flow_layout.addWidget(flow_card)
        content_layout.addWidget(self.current_flow_panel)

        log_title_row = QHBoxLayout()
        log_icon = QLabel()
        log_icon.setObjectName("logHeaderIcon")
        log_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        log_icon.setFixedSize(24, 24)
        log_icon.setPixmap(make_line_icon("report", "#1f2a44", 20).pixmap(20, 20))
        log_header = QLabel("实时日志")
        log_header.setObjectName("logTitle")
        log_title_row.addWidget(log_icon)
        log_title_row.addWidget(log_header)
        log_title_row.addStretch(1)
        content_layout.addLayout(log_title_row)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("logConsole")
        self.log_view.setFont(QFont("Consolas", MAIN_FONT_PT))
        self.log_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content_layout.addWidget(self.log_view, 1)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow {
                background: #eef3f8;
                color: #16233b;
                font-family: "Microsoft YaHei UI";
                font-size: 9pt;
            }
            QFrame#titleBar {
                background: #eef3f8;
                border: 0;
            }
            QLabel#windowTitleLabel {
                color: #0f172a;
                font-size: 10pt;
                font-weight: 600;
            }
            QPushButton#systemConfigButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 10px;
                padding: 4px 10px;
                color: #1f2a44;
                font-size: 8pt;
                text-align: left;
            }
            QPushButton#systemConfigButton:hover {
                background: #e5eef8;
                border-color: #cbd8e8;
            }
            QPushButton#windowControlButton, QPushButton#windowCloseButton {
                background: transparent;
                border: 0;
                border-radius: 8px;
                color: #12213d;
                font-size: 11pt;
                padding: 0;
            }
            QPushButton#windowControlButton:hover {
                background: #dbe6f2;
            }
            QPushButton#windowCloseButton:hover {
                background: #f3d5d8;
                color: #8f1d2c;
            }
            QFrame#leftRail {
                background: transparent;
                border: 0;
            }
            QFrame#contentPanel, QFrame#dashboardCard, QFrame#currentFlowPanel {
                background: #ffffff;
                border: 1px solid #d8e3f0;
                border-radius: 12px;
            }
            QLabel#cardIcon {
                color: #2f80ed;
                background: #eaf2ff;
                border: 1px solid #cfe1fb;
                border-radius: 9px;
            }
            QLabel#cardTitle {
                color: #0f172a;
                font-size: 12pt;
                font-weight: 600;
            }
            QLabel#sectionTitle {
                color: #111827;
                font-size: 8pt;
                font-weight: 600;
            }
            QLabel#mutedText, QLabel#taskProgressText {
                color: #53647e;
                font-size: 8pt;
            }
            QLabel#pillHint {
                color: #2f80ed;
                background: #eaf2ff;
                border: 1px solid #c7ddf4;
                border-radius: 13px;
                padding: 4px 10px;
                font-size: 8pt;
            }
            QComboBox#projectCombo, QPushButton#datePickerButton {
                min-height: 34px;
                border-radius: 10px;
                border: 1px solid #cad8ea;
                padding: 4px 12px;
                background: #ffffff;
                color: #1f2a44;
                font-size: 9pt;
                text-align: left;
            }
            QComboBox#projectCombo:hover, QPushButton#datePickerButton:hover {
                border-color: #7fb2ea;
                background: #fafdff;
            }
            QComboBox#projectCombo::drop-down {
                width: 36px;
                border: 0;
            }
            QPushButton {
                outline: 0;
            }
            QPushButton#primaryActionButton {
                background: #3b82f6;
                border: 1px solid #2f80ed;
                border-radius: 10px;
                color: #ffffff;
                padding: 6px 14px;
                font-size: 9pt;
                text-align: center;
            }
            QPushButton#primaryActionButton:hover {
                background: #2f75e8;
            }
            QPushButton#secondaryActionButton, QPushButton#dateHintButton {
                background: #ffffff;
                border: 1px solid #cad8ea;
                border-radius: 10px;
                color: #1f2a44;
                padding: 6px 14px;
                font-size: 9pt;
                text-align: center;
            }
            QPushButton#secondaryActionButton:hover, QPushButton#dateHintButton:hover {
                background: #f5f9ff;
                border-color: #9bb7dc;
            }
            QFrame#verticalDivider {
                background: #dce5ef;
                border: 0;
            }
            QPushButton#periodButton {
                background: #ffffff;
                border: 1px solid #cad8ea;
                border-radius: 10px;
                padding: 3px 10px;
                color: #1f2a44;
                text-align: center;
                font-size: 9pt;
                outline: 0;
            }
            QPushButton#periodButton:checked {
                background: #dff7ea;
                border: 1px solid #45c27a;
                color: #087a46;
            }
            QPushButton#stageActionButton {
                background: #e9f8ef;
                border: 1px solid #98ddb8;
                border-radius: 12px;
                color: #087a46;
                padding: 6px 12px;
                font-size: 9pt;
                text-align: center;
            }
            QPushButton#stageActionButton:hover {
                background: #def4e8;
                border-color: #6dcc9b;
            }
            QPushButton#stageActionButton[active="true"] {
                background: #d9ecff;
                color: #145ea8;
                border-color: #7fb2ea;
            }
            QPushButton#stageActionButton[done="true"] {
                background: #dff7ea;
                color: #087a46;
                border-color: #45c27a;
            }
            QLabel#flowHeaderIcon, QLabel#logHeaderIcon {
                color: #1f2a44;
                font-size: 11pt;
            }
            QLabel#flowTitle, QLabel#logTitle {
                color: #0f172a;
                font-size: 10pt;
                font-weight: 600;
            }
            QFrame#flowStatusCard {
                background: #fbfdff;
                border: 1px solid #d8e3f0;
                border-radius: 12px;
            }
            QFrame#flowAccent {
                background: #3b82f6;
                border: 0;
                border-radius: 2px;
            }
            QLabel#currentTaskTitle {
                color: #0f172a;
                font-size: 12pt;
                font-weight: 600;
            }
            QLabel#currentTaskSubtitle {
                color: #1f2a44;
                font-size: 9pt;
            }
            QLabel#statusBadge {
                min-width: 88px;
                min-height: 28px;
                color: #2f80ed;
                background: #eaf2ff;
                border: 1px solid #d4e6ff;
                border-radius: 14px;
                font-size: 8pt;
            }
            QLabel#statusBadge[status="idle"] {
                color: #64748b;
                background: #f1f5f9;
                border-color: #dbe5ef;
            }
            QLabel#statusBadge[status="done"] {
                color: #087a46;
                background: #dff7ea;
                border-color: #9bd8b6;
            }
            QLabel#statusBadge[status="failed"] {
                color: #9f1239;
                background: #ffe4e6;
                border-color: #fecdd3;
            }
            QLabel#startTimeText {
                color: #1f2a44;
                font-size: 8pt;
            }
            QTextEdit#logConsole {
                background: #08172b;
                color: #e6edf7;
                border-radius: 10px;
                border: 1px solid #12213d;
                padding: 16px;
            }
            QTextEdit#logConsole .log-path {
                color: #38d7ff;
            }
            QTextEdit#logConsole .log-pass {
                color: #56e58f;
            }
            QTextEdit#logConsole .log-error {
                color: #fca5a5;
            }
            QTextEdit#logConsole .log-project {
                color: #fcd34d;
            }
            QTextEdit#logConsole .log-excel {
                color: #c4b5fd;
            }
            QProgressBar#taskProgress {
                height: 10px;
                border: 0;
                border-radius: 5px;
                background: #e6edf6;
            }
            QProgressBar#taskProgress::chunk {
                border-radius: 5px;
                background: #5c9af4;
            }
        """)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= self.title_bar.height():
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def refresh_projects(self) -> None:
        self.projects = load_project_summaries(self.root)
        self.project_combo.clear()
        for project in self.projects:
            self.project_combo.addItem(project.label, project.project_id)
        has_projects = bool(self.projects)
        self.set_task_buttons_enabled(has_projects)

    def selected_project_id(self) -> str:
        return str(self.project_combo.currentData() or "")

    def selected_project_name(self) -> str:
        text = self.project_combo.currentText()
        if " (" in text:
            return text.split(" (", 1)[0]
        return text

    def selected_project_config_path(self) -> Path:
        project_id = self.selected_project_id()
        for project in self.projects:
            if project.project_id == project_id:
                return Path(project.path)
        return self.root / "configs" / "projects" / f"{project_id}.json"

    def credentials_config_path(self) -> Path:
        return self.root / "secrets" / "secrets.json"

    def selected_project_excel_path(self) -> Path:
        project_id = self.selected_project_id()
        project = load_project_config(self.root, project_id)
        return get_excel_path(project, self.root)

    def ensure_credentials_file(self) -> Path:
        path = self.credentials_config_path()
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        example = path.parent / "secrets.example.json"
        if example.exists():
            shutil.copyfile(example, path)
        else:
            path.write_text('{\n  "baidu": {}\n}\n', encoding="utf-8")
        return path

    def open_selected_project_config(self) -> None:
        path = self.selected_project_config_path()
        if path.exists():
            self.open_path(path)
            self.append_log(f"已打开当前项目配置：{path}")
        else:
            QMessageBox.warning(self, "未找到项目配置", f"没有找到项目配置文件：{path}")

    def open_credentials_config(self) -> None:
        path = self.ensure_credentials_file()
        self.open_path(path)
        self.append_log(f"已打开账号密码配置：{path}")

    def restore_backup(self) -> None:
        try:
            target_path = self.selected_project_excel_path()
        except Exception as exc:
            QMessageBox.warning(self, "无法恢复备份", f"读取当前项目 Excel 路径失败：{exc}")
            return

        backup_dir = self.root / "backups"
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择要恢复的备份",
            str(backup_dir),
            "Excel 备份 (*.xlsx *.xlsm *.xls);;所有文件 (*.*)",
        )
        if not selected:
            return

        backup_path = Path(selected)
        if not backup_path.exists():
            QMessageBox.warning(self, "无法恢复备份", f"没有找到备份文件：{backup_path}")
            return
        if not target_path.exists():
            QMessageBox.warning(self, "无法恢复备份", f"没有找到当前项目 Excel：{target_path}")
            return

        message = (
            f"当前项目：{self.project_combo.currentText()}\n\n"
            f"将被覆盖的 Excel：\n{target_path}\n\n"
            f"用于恢复的备份：\n{backup_path}\n\n"
            "确认恢复后，程序会先保存当前 Excel 的一份安全备份。"
        )
        answer = QMessageBox.question(
            self,
            "确认恢复备份",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.append_log("已取消恢复备份。")
            return

        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safety_backup = backup_dir / f"{target_path.stem}_before_manual_restore_{timestamp}{target_path.suffix}"
            shutil.copy2(target_path, safety_backup)
            shutil.copy2(backup_path, target_path)
        except Exception as exc:
            QMessageBox.warning(self, "恢复备份失败", str(exc))
            self.append_log(f"恢复备份失败：{exc}")
            return

        self.append_log(f"恢复备份完成：{backup_path} -> {target_path}")
        self.append_log(f"恢复前安全备份已保存：{safety_backup}")
        QMessageBox.information(self, "恢复完成", f"已恢复备份。\n\n恢复前安全备份：\n{safety_backup}")

    def selected_period(self) -> str:
        for button in self.period_buttons:
            if button.isChecked():
                return str(button.property("periodValue") or button.text().replace("✓", "").strip())
        return "15点"

    def update_period_button_texts(self) -> None:
        for button in self.period_buttons:
            value = str(button.property("periodValue") or button.text().replace("✓", "").strip())
            button.setText(f"{value}  ✓" if button.isChecked() else value)

    def selected_daily_date(self) -> str:
        return self.current_daily_date.isoformat()

    def reset_daily_date_to_yesterday(self) -> None:
        self.current_daily_date = date.today() - timedelta(days=1)
        self.date_button.setText(self.current_daily_date.isoformat())

    def display_daily_date(self) -> str:
        return f"{self.current_daily_date.month}月{self.current_daily_date.day}日"

    def pick_daily_date(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowFlags(Qt.WindowType.Popup)
        dialog.setWindowTitle("选择日报日期")
        layout = QVBoxLayout(dialog)
        calendar = QCalendarWidget(dialog)
        calendar.setSelectedDate(QDate(self.current_daily_date.year, self.current_daily_date.month, self.current_daily_date.day))
        layout.addWidget(calendar)
        ok_button = QPushButton("确定")
        ok_button.clicked.connect(dialog.accept)
        layout.addWidget(ok_button)
        calendar.activated.connect(lambda selected: (calendar.setSelectedDate(selected), dialog.accept()))
        dialog.adjustSize()
        top_left = self.date_button.mapToGlobal(QPoint(0, -dialog.sizeHint().height() - 6))
        dialog.move(top_left)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = calendar.selectedDate().toPython()
            self.current_daily_date = selected
            self.date_button.setText(selected.isoformat())

    def run_startup_check(self) -> None:
        self.reset_stages()
        self.progress_text.setText("正在检查环境...")
        report = run_environment_check(self.root)
        self.log_view.clear()
        self.append_log("环境检测开始")
        for item in report["checks"]:
            status = "通过" if item["passed"] else "需要处理"
            self.append_log(f"[{status}] {item['name']}: {item['detail']}")
        if report["passed"]:
            self.progress_text.setText("环境已就绪，请选择项目和任务。")
        else:
            self.progress_text.setText("环境检查未完全通过，请先看日志提示。")

    def run_hourly(self) -> None:
        project_id = self.selected_project_id()
        period = self.selected_period()
        command = build_hourly_command(self.root, period, project_id=project_id)
        self.set_current_flow("hourly", "运行小时报", f"{self.selected_project_name()} {period}", "运行中")
        self.start_command("小时报执行中", command)

    def run_daily(self) -> None:
        project_id = self.selected_project_id()
        date_text = self.selected_daily_date()
        command = build_daily_command(self.root, date_text, project_id=project_id)
        self.set_current_flow("daily", "运行日报", f"{self.selected_project_name()} {self.display_daily_date()}", "运行中")
        self.start_command("日报执行中", command)

    def run_environment_preflight(self) -> None:
        self.run_preflight("hourly")

    def run_preflight(self, task: str) -> None:
        project_id = self.selected_project_id()
        command = build_preflight_command(self.root, task, project_id=project_id)
        self.set_current_flow("preflight", "执行环境自检", self.selected_project_name(), "运行中")
        self.start_command("快速自检中", command)

    def set_current_flow(self, task_type: str, title: str, subtitle: str, status: str) -> None:
        self.current_task_type = task_type
        self.current_project_name = self.selected_project_name()
        self.current_status = status
        self.current_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.current_task_title.setText(title)
        self.current_task_subtitle.setText(subtitle)
        self.current_status_badge.setText(status)
        self.current_status_badge.setProperty("status", "running")
        self.current_start_time_label.setText(f"开始时间：{self.current_start_time}")
        self._refresh_widget_style(self.current_status_badge)

    def set_current_flow_idle(self) -> None:
        self.current_status = "idle"
        self.current_task_title.setText("暂无运行任务")
        self.current_task_subtitle.setText("请选择左侧任务开始执行")
        self.current_status_badge.setText("空闲")
        self.current_status_badge.setProperty("status", "idle")
        self.current_start_time_label.setText("开始时间：--")
        self._refresh_widget_style(self.current_status_badge)

    def start_command(self, title: str, command: list[str]) -> None:
        self.reset_stages()
        self.status_title.setText(title)
        self.status_detail.setText("任务正在运行，请不要关闭窗口。")
        self.progress_text.setText("任务已创建，等待启动...")
        self.log_view.clear()
        self.runner.start(command, self.root)

    def on_task_started(self) -> None:
        self.set_task_buttons_enabled(False)
        self.mark_stage("config")

    def on_task_finished(self, exit_code: int) -> None:
        self.set_task_buttons_enabled(True)
        if exit_code == 0:
            self.mark_stage("done")
            self.status_title.setText("任务完成")
            self.status_detail.setText("运行结束，可以打开报告或日志复核。")
            self.progress_text.setText("任务完成，可以打开报告复核。")
            self.current_status_badge.setText("已完成")
            self.current_status_badge.setProperty("status", "done")
            self.append_log("任务完成，退出码 0")
        else:
            self.status_title.setText("任务失败")
            self.status_detail.setText("请查看错误日志和 reports 目录下的报告。")
            self.progress_text.setText("任务失败，请查看实时日志和报告。")
            self.current_status_badge.setText("失败")
            self.current_status_badge.setProperty("status", "failed")
            self.append_log(f"任务失败，退出码 {exit_code}")
        self._refresh_widget_style(self.current_status_badge)

    def show_task_error(self, message: str) -> None:
        self.set_task_buttons_enabled(True)
        self.status_title.setText("任务无法启动")
        self.status_detail.setText(message)
        self.progress_text.setText("任务没有启动，请查看提示。")
        self.current_status_badge.setText("失败")
        self.current_status_badge.setProperty("status", "failed")
        self._refresh_widget_style(self.current_status_badge)
        self.append_log("任务无法启动：" + message)

    def set_task_buttons_enabled(self, enabled: bool) -> None:
        has_projects = bool(self.projects)
        for button in [self.hourly_button, self.daily_button, self.environment_check_button]:
            button.setEnabled(enabled and has_projects)

    def reset_stages(self) -> None:
        self.progress.setValue(0)
        self.progress_text.setText("项目就绪后会显示任务进度")
        for label in self.stage_labels.values():
            label.setProperty("active", False)
            label.setProperty("done", False)
            self._refresh_widget_style(label)

    def mark_stage(self, stage: str) -> None:
        keys = [item[0] for item in STAGES]
        if stage not in keys:
            return
        index = keys.index(stage)
        self.progress.setValue(index + 1)
        self.progress_text.setText(f"当前进度：{STAGES[index][1]}")
        for pos, key in enumerate(keys):
            label = self.stage_labels[key]
            label.setProperty("active", key == stage)
            label.setProperty("done", pos < index or stage == "done")
            self._refresh_widget_style(label)

    def append_log(self, text: str) -> None:
        self.log_view.append(format_log_html(text))
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def open_path(self, path: Path) -> None:
        path.mkdir(exist_ok=True) if path.suffix == "" else None
        try:
            os.startfile(str(path))
        except Exception as exc:
            QMessageBox.warning(self, "无法打开", str(exc))

    def _refresh_widget_style(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self.maximize_button.setText("□")
        else:
            self.showMaximized()
            self.maximize_button.setText("❐")


def create_window(root: str | Path) -> MainWindow:
    window = MainWindow(root)
    window.show()
    return window
