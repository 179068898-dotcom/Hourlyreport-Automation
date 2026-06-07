from __future__ import annotations

import os
import shutil
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QRadioButton,
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


STAGES = [
    ("environment", "环境检测"),
    ("config", "项目配置"),
    ("preflight", "快速自检"),
    ("baidu", "百度数据"),
    ("kst", "快商通数据"),
    ("excel", "Excel 写入"),
    ("done", "报告输出"),
]
MAIN_FONT_PT = 9
SUB_FONT_PT = 8


class MainWindow(QMainWindow):
    def __init__(self, root: str | Path):
        super().__init__()
        self.root = Path(root)
        self.projects: list[ProjectSummary] = []
        self.stage_labels: dict[str, QLabel] = {}
        self.runner = QtTaskRunner(self)
        self.runner.output.connect(self.append_log)
        self.runner.stage_changed.connect(self.mark_stage)
        self.runner.started.connect(self.on_task_started)
        self.runner.finished.connect(self.on_task_finished)
        self.runner.failed_to_start.connect(self.show_task_error)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setWindowIcon(QIcon())
        self.setWindowTitle("百度日报小时报控制台")
        self.setFont(QFont("Microsoft YaHei UI", MAIN_FONT_PT))
        self.resize(1040, 700)
        self.setMinimumSize(980, 660)
        self._drag_offset = None
        self._build_ui()
        self._apply_style()
        self.refresh_projects()
        self.run_startup_check()

    def _build_ui(self) -> None:
        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        root_layout = QVBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.title_bar = QFrame()
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setFixedHeight(34)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(14, 0, 8, 0)
        title_layout.setSpacing(8)
        self.title_label = QLabel("百度日报小时报控制台")
        self.title_label.setObjectName("windowTitleLabel")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch(1)
        self.minimize_button = QPushButton("—")
        self.minimize_button.setObjectName("windowControlButton")
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("windowCloseButton")
        for button in [self.minimize_button, self.close_button]:
            button.setFixedSize(34, 28)
            title_layout.addWidget(button)
        self.minimize_button.clicked.connect(self.showMinimized)
        self.close_button.clicked.connect(self.close)
        root_layout.addWidget(self.title_bar)

        shell = QHBoxLayout()
        shell.setContentsMargins(18, 16, 18, 18)
        shell.setSpacing(14)
        root_layout.addLayout(shell, 1)

        self.left_panel = QFrame()
        left = self.left_panel
        left.setObjectName("leftRail")
        left.setMinimumWidth(300)
        left.setMaximumWidth(420)
        left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(18, 18, 18, 18)
        left_layout.setSpacing(12)

        title = QLabel("任务控制台")
        title.setObjectName("appTitle")
        subtitle = QLabel("选择项目和任务，执行过程会实时显示。")
        subtitle.setObjectName("mutedText")
        subtitle.setFont(QFont("Microsoft YaHei UI", SUB_FONT_PT))
        subtitle.setWordWrap(True)
        left_layout.addWidget(title)
        left_layout.addWidget(subtitle)

        left_layout.addSpacing(8)
        project_card = QFrame()
        project_card.setObjectName("projectCard")
        project_card.setMinimumHeight(132)
        project_layout = QVBoxLayout(project_card)
        project_layout.setContentsMargins(12, 10, 12, 10)
        project_layout.setSpacing(10)
        project_title_row = QHBoxLayout()
        project_title = QLabel("项目")
        project_title.setObjectName("sectionTitle")
        project_hint = QLabel("当前任务")
        project_hint.setObjectName("pillHint")
        project_title_row.addWidget(project_title)
        project_title_row.addStretch(1)
        project_title_row.addWidget(project_hint)
        project_layout.addLayout(project_title_row)
        self.project_combo = QComboBox()
        self.project_combo.setObjectName("projectCombo")
        self.project_combo.setMinimumHeight(self.fontMetrics().height() + 16)
        project_layout.addWidget(self.project_combo)
        self.progress_text = QLabel("项目就绪后会显示任务进度")
        self.progress_text.setObjectName("taskProgressText")
        self.progress_text.setFont(QFont("Microsoft YaHei UI", SUB_FONT_PT))
        self.progress_text.setWordWrap(True)
        project_layout.addWidget(self.progress_text)
        self.progress = QProgressBar()
        self.progress.setObjectName("taskProgress")
        self.progress.setRange(0, len(STAGES))
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        project_layout.addWidget(self.progress)
        left_layout.addWidget(project_card)

        left_layout.addSpacing(8)
        left_layout.addWidget(QLabel("小时报时段"))
        period_row = QHBoxLayout()
        self.period_buttons: list[QRadioButton] = []
        for text in ["11点", "15点", "18点"]:
            button = QRadioButton(text)
            button.setObjectName("periodButton")
            self.period_buttons.append(button)
            period_row.addWidget(button)
        self.period_buttons[1].setChecked(True)
        left_layout.addLayout(period_row)

        self.hourly_button = QPushButton("运行小时报")
        self.daily_button = QPushButton("运行日报")
        self.preflight_hourly_button = QPushButton("小时报快速自检")
        self.preflight_daily_button = QPushButton("日报快速自检")
        for button in [self.hourly_button, self.daily_button, self.preflight_hourly_button, self.preflight_daily_button]:
            button.setMinimumHeight(42)
            left_layout.addWidget(button)

        self.hourly_button.clicked.connect(self.run_hourly)
        self.daily_button.clicked.connect(self.run_daily)
        self.preflight_hourly_button.clicked.connect(lambda: self.run_preflight("hourly"))
        self.preflight_daily_button.clicked.connect(lambda: self.run_preflight("daily"))

        self.date_card = QFrame()
        self.date_card.setObjectName("projectCard")
        date_layout = QVBoxLayout(self.date_card)
        date_layout.setContentsMargins(12, 12, 12, 12)
        date_layout.setSpacing(8)
        date_title_row = QHBoxLayout()
        date_title = QLabel("日报日期")
        date_title.setObjectName("sectionTitle")
        date_hint = QLabel("默认昨天")
        date_hint.setObjectName("pillHint")
        date_title_row.addWidget(date_title)
        date_title_row.addStretch(1)
        date_title_row.addWidget(date_hint)
        date_layout.addLayout(date_title_row)
        self.date_edit = QDateEdit()
        self.date_edit.setObjectName("projectCombo")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        yesterday = date.today() - timedelta(days=1)
        self.date_edit.setDate(yesterday)
        self.date_edit.setMinimumHeight(self.fontMetrics().height() + 2)
        date_layout.addWidget(self.date_edit)
        left_layout.addWidget(self.date_card)

        left_layout.addStretch(1)
        shortcut_row = QGridLayout()
        self.excel_config_button = QPushButton("Excel路径配置")
        self.credentials_config_button = QPushButton("账号密码配置")
        self.guide_button = QPushButton("配置说明")
        self.refresh_button = QPushButton("重新检测")
        shortcut_row.addWidget(self.excel_config_button, 0, 0)
        shortcut_row.addWidget(self.credentials_config_button, 0, 1)
        shortcut_row.addWidget(self.guide_button, 1, 0)
        shortcut_row.addWidget(self.refresh_button, 1, 1)
        left_layout.addLayout(shortcut_row)
        self.excel_config_button.clicked.connect(self.open_selected_project_config)
        self.credentials_config_button.clicked.connect(self.open_credentials_config)
        self.guide_button.clicked.connect(self.open_config_guide)
        self.refresh_button.clicked.connect(self.run_startup_check)

        content = QFrame()
        content.setObjectName("contentPanel")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 18, 20, 18)
        content_layout.setSpacing(14)

        self.status_title = QLabel("准备就绪")
        self.status_title.setObjectName("statusTitle")
        self.status_detail = QLabel("先确认环境状态，再选择任务。")
        self.status_detail.setObjectName("mutedText")
        self.status_title.hide()
        self.status_detail.hide()
        header_text = QVBoxLayout()
        header_text.addWidget(self.status_title)
        header_text.addWidget(self.status_detail)
        content_layout.addLayout(header_text)

        stage_grid = QGridLayout()
        stage_grid.setHorizontalSpacing(10)
        stage_grid.setVerticalSpacing(10)
        for index, (key, label) in enumerate(STAGES):
            badge = QLabel(label)
            badge.setObjectName("stageBadge")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stage_labels[key] = badge
            stage_grid.addWidget(badge, index // 4, index % 4)
        content_layout.addLayout(stage_grid)

        self.command_line = QLineEdit()
        self.command_line.setReadOnly(True)
        self.command_line.setPlaceholderText("这里会显示即将执行的命令。")
        content_layout.addWidget(self.command_line)

        log_header = QLabel("实时日志")
        log_header.setObjectName("sectionTitle")
        content_layout.addWidget(log_header)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("logConsole")
        self.log_view.setFont(QFont("Microsoft YaHei UI", MAIN_FONT_PT))
        self.log_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content_layout.addWidget(self.log_view, 1)

        shell.addWidget(left)
        shell.addWidget(content, 1)
        self.size_grip = QSizeGrip(root_widget)
        self.size_grip.setObjectName("sizeGrip")
        root_layout.addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow {
                background: #eef2f7;
                color: #172033;
                font-family: "Microsoft YaHei UI";
                font-size: 9pt;
            }
            QFrame#titleBar {
                background: #eef2f7;
                border: 0;
            }
            QLabel#windowTitleLabel {
                color: #172033;
                font-size: 9pt;
            }
            QPushButton#windowControlButton, QPushButton#windowCloseButton {
                background: transparent;
                border: 0;
                border-radius: 6px;
                color: #334155;
                padding: 0;
            }
            QPushButton#windowControlButton:hover {
                background: #dbe6f2;
            }
            QPushButton#windowCloseButton:hover {
                background: #f3d5d8;
                color: #8f1d2c;
            }
            QFrame#leftRail, QFrame#contentPanel {
                background: #fbfcff;
                border: 1px solid #dde5f0;
                border-radius: 16px;
            }
            QFrame#projectCard {
                background: #f7faff;
                border: 1px solid #dce7f5;
                border-radius: 14px;
            }
            QLabel#appTitle {
                font-size: 10pt;
                color: #111827;
            }
            QLabel#statusTitle {
                font-size: 10pt;
            }
            QLabel#sectionTitle {
                font-size: 9pt;
            }
            QLabel#pillHint {
                color: #426985;
                background: #e5f1ff;
                border: 1px solid #c7ddf4;
                border-radius: 9px;
                padding: 3px 8px;
                font-size: 8pt;
            }
            QLabel#mutedText {
                color: #64748b;
                font-size: 8pt;
            }
            QLabel#taskProgressText {
                color: #64748b;
                font-size: 8pt;
                line-height: 16px;
            }
            QPushButton {
                background: #f2f6fb;
                border: 1px solid #d8e1ee;
                border-radius: 10px;
                padding: 8px 12px;
                color: #1f2937;
            }
            QPushButton:hover {
                background: #e8f0fb;
                border-color: #b9c9df;
            }
            QPushButton:pressed {
                background: #dbe8f7;
            }
            QPushButton:disabled {
                color: #94a3b8;
                background: #f4f6f8;
            }
            QComboBox, QDateEdit, QLineEdit {
                border: 1px solid #d8e1ee;
                border-radius: 10px;
                padding: 8px 10px;
                background: #ffffff;
            }
            QComboBox#projectCombo, QDateEdit#projectCombo {
                min-height: 30px;
                border-radius: 13px;
                border: 1px solid #b8cce4;
                padding: 6px 12px;
                background: #ffffff;
                color: #172033;
                font-size: 9pt;
            }
            QComboBox#projectCombo:hover, QDateEdit#projectCombo:hover {
                border-color: #7fb2ea;
                background: #fafdff;
            }
            QComboBox#projectCombo::drop-down {
                width: 32px;
                border: 0;
            }
            QRadioButton {
                spacing: 6px;
            }
            QLabel#stageBadge {
                min-height: 34px;
                border-radius: 10px;
                background: #eef4fb;
                color: #496176;
                border: 1px solid #d7e2ee;
            }
            QLabel#stageBadge[active="true"] {
                background: #d9ecff;
                color: #0f4c81;
                border-color: #8fc5f5;
            }
            QLabel#stageBadge[done="true"] {
                background: #ddf7ea;
                color: #17643b;
                border-color: #9dd9b7;
            }
            QTextEdit#logConsole {
                background: #101827;
                color: #dbeafe;
                border-radius: 14px;
                border: 1px solid #243247;
                padding: 12px;
            }
            QTextEdit#logConsole .log-path {
                color: #93c5fd;
            }
            QTextEdit#logConsole .log-pass {
                color: #86efac;
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
            QProgressBar {
                height: 12px;
                border: 1px solid #d7e2ee;
                border-radius: 6px;
                background: #edf2f7;
            }
            QProgressBar#taskProgress {
                height: 8px;
                border: 0;
                border-radius: 4px;
                background: #e6edf6;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background: #5ea0ef;
            }
            QProgressBar#taskProgress::chunk {
                border-radius: 4px;
                background: #5ea0ef;
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
        for button in [self.hourly_button, self.daily_button, self.preflight_hourly_button, self.preflight_daily_button]:
            button.setEnabled(has_projects)

    def selected_project_id(self) -> str:
        return str(self.project_combo.currentData() or "")

    def selected_project_config_path(self) -> Path:
        project_id = self.selected_project_id()
        for project in self.projects:
            if project.project_id == project_id:
                return Path(project.path)
        return self.root / "configs" / "projects" / f"{project_id}.json"

    def credentials_config_path(self) -> Path:
        return self.root / "secrets" / "secrets.json"

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

    def open_config_guide(self) -> None:
        candidates = [
            self.root / "docs" / "如何新增一个项目.md",
            self.root / "README_同事使用说明.md",
            self.root / "README.md",
        ]
        for path in candidates:
            if path.exists():
                self.open_path(path)
                self.append_log(f"已打开配置说明：{path}")
                return
        QMessageBox.warning(self, "未找到配置说明", "没有找到配置说明文档。")

    def selected_period(self) -> str:
        for button in self.period_buttons:
            if button.isChecked():
                return button.text()
        return "15点"

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
            self.status_title.setText("环境状态良好")
            self.status_detail.setText("可以选择项目并执行任务。")
            self.progress_text.setText("环境已就绪，请选择项目和任务。")
        else:
            self.status_title.setText("环境需要确认")
            self.status_detail.setText("请查看日志里的提示，必要时先运行安装脚本。")
            self.progress_text.setText("环境检查未完全通过，请先看日志提示。")

    def run_hourly(self) -> None:
        project_id = self.selected_project_id()
        command = build_hourly_command(self.root, self.selected_period(), project_id=project_id)
        self.start_command("小时报执行中", command)

    def run_daily(self) -> None:
        project_id = self.selected_project_id()
        date_text = self.date_edit.date().toString("yyyy-MM-dd")
        command = build_daily_command(self.root, date_text, project_id=project_id)
        self.start_command("日报执行中", command)

    def run_preflight(self, task: str) -> None:
        project_id = self.selected_project_id()
        command = build_preflight_command(self.root, task, project_id=project_id)
        self.start_command("快速自检中", command)

    def start_command(self, title: str, command: list[str]) -> None:
        self.reset_stages()
        self.status_title.setText(title)
        self.status_detail.setText("任务正在运行，请不要关闭窗口。")
        self.progress_text.setText("任务已创建，等待启动...")
        self.command_line.setText(" ".join(command))
        self.log_view.clear()
        self.append_log("启动命令：" + " ".join(command))
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
            self.append_log("任务完成，退出码 0")
        else:
            self.status_title.setText("任务失败")
            self.status_detail.setText("请查看错误日志和 reports 目录下的报告。")
            self.progress_text.setText("任务失败，请查看实时日志和报告。")
            self.append_log(f"任务失败，退出码 {exit_code}")

    def show_task_error(self, message: str) -> None:
        self.set_task_buttons_enabled(True)
        self.status_title.setText("任务无法启动")
        self.status_detail.setText(message)
        self.progress_text.setText("任务没有启动，请查看提示。")
        self.append_log("任务无法启动：" + message)

    def set_task_buttons_enabled(self, enabled: bool) -> None:
        has_projects = bool(self.projects)
        for button in [self.hourly_button, self.daily_button, self.preflight_hourly_button, self.preflight_daily_button]:
            button.setEnabled(enabled and has_projects)

    def reset_stages(self) -> None:
        self.progress.setValue(0)
        self.progress_text.setText("项目就绪后会显示任务进度")
        for label in self.stage_labels.values():
            label.setProperty("active", False)
            label.setProperty("done", False)
            label.style().unpolish(label)
            label.style().polish(label)

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
            label.style().unpolish(label)
            label.style().polish(label)

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


def create_window(root: str | Path) -> MainWindow:
    window = MainWindow(root)
    window.show()
    return window
