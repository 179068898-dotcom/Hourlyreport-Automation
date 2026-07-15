# Windows Tray Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让控制台主窗口在任务栏显示应用图标，右上角 `X` 永远只隐藏窗口，并由常驻托盘或系统配置菜单负责真正退出。

**Architecture:** `MainWindow` 创建并持有一个 `QSystemTrayIcon`，托盘菜单复用现有 `show_console()` 和 `exit_application()`。普通关闭路径只隐藏窗口，真正退出路径统一清理宠物、托盘和待保存设置后退出 Qt 应用。

**Tech Stack:** Python 3.11、PySide6、pytest、PyInstaller、Windows 10/11。

## Global Constraints

- 托盘左键只显示主窗口，不切换为隐藏。
- 右上角 `X` 在宠物显示或隐藏时都只隐藏主窗口。
- 真正退出只允许从托盘右键“退出程序”和系统配置菜单“退出程序”触发。
- 正在运行的后台任务不因主窗口隐藏而停止。
- 不修改日报、小时报、Excel 写入、浏览器、自动更新和唯一实例业务逻辑。
- 不生成内部发布包，不改版本号 `2026.7.15.101`。

---

### Task 1: 托盘与关闭行为测试

**Files:**
- Modify: `tests/test_basic.py`

**Interfaces:**
- Consumes: `MainWindow.request_console_close()`、`MainWindow.closeEvent()`、`MainWindow.show_console()`、`MainWindow.exit_application()`。
- Produces: 对 `tray_icon`、`tray_menu`、`tray_open_action`、`tray_exit_action` 和关闭生命周期的回归约束。

- [ ] **Step 1: 写托盘结构和左键恢复的失败测试**

```python
def test_desktop_gui_tray_icon_opens_console_and_exposes_exit(monkeypatch):
    window = build_offscreen_main_window(monkeypatch)
    assert not window.tray_icon.icon().isNull()
    assert [action.text() for action in window.tray_menu.actions()] == ["打开控制台", "退出程序"]
    window.hide()
    window.on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert window.isVisible()
```

- [ ] **Step 2: 写 `X` 在两种宠物模式下都只隐藏的失败测试**

```python
@pytest.mark.parametrize("pet_mode", [PET_CLAWD, PET_HIDDEN])
def test_desktop_gui_close_only_hides_for_every_pet_mode(monkeypatch, pet_mode):
    window = build_offscreen_main_window(monkeypatch, pet_mode)
    window.show()
    window.close()
    assert not window.isVisible()
    assert window._quitting is False
    assert window.tray_icon.isVisible()
```

- [ ] **Step 3: 写真正退出会清理托盘与宠物的失败测试**

```python
def test_desktop_gui_exit_application_cleans_tray_and_pet(monkeypatch):
    window = build_offscreen_main_window(monkeypatch)
    window.exit_application()
    assert window._quitting is True
    assert not window.tray_icon.isVisible()
    assert not window.desktop_pet.isVisible()
```

- [ ] **Step 4: 运行定向测试并确认红灯原因**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "tray_icon or close_only_hides or exit_application_cleans" -q`

Expected: FAIL，原因是 `MainWindow` 尚无托盘成员，且隐藏宠物时 `X` 仍进入退出路径。

---

### Task 2: 实现原生托盘与统一关闭生命周期

**Files:**
- Modify: `gui/main_window.py`

**Interfaces:**
- Consumes: `app_icon_path(root) -> Path`、`show_console() -> None`、`exit_application() -> None`。
- Produces: `_build_tray() -> None`、`on_tray_activated(reason) -> None`，以及 `tray_icon`、`tray_menu`、`tray_open_action`、`tray_exit_action`。

- [ ] **Step 1: 导入并创建 `QSystemTrayIcon`**

```python
from PySide6.QtWidgets import QSystemTrayIcon

def _build_tray(self) -> None:
    self.tray_menu = QMenu(self)
    self.tray_open_action = QAction("打开控制台", self.tray_menu)
    self.tray_exit_action = QAction("退出程序", self.tray_menu)
    self.tray_open_action.triggered.connect(self.show_console)
    self.tray_exit_action.triggered.connect(self.exit_application)
    self.tray_menu.addAction(self.tray_open_action)
    self.tray_menu.addAction(self.tray_exit_action)
    self.tray_icon = QSystemTrayIcon(self.windowIcon(), self)
    self.tray_icon.setToolTip("百度数据自动化控制台")
    self.tray_icon.setContextMenu(self.tray_menu)
    self.tray_icon.activated.connect(self.on_tray_activated)
    self.tray_icon.show()
```

- [ ] **Step 2: 实现托盘左键仅显示窗口**

```python
def on_tray_activated(self, reason) -> None:
    if reason == QSystemTrayIcon.ActivationReason.Trigger:
        self.show_console()
```

- [ ] **Step 3: 统一 `X` 为只隐藏**

```python
def request_console_close(self) -> None:
    self.hide()
    if self.pet_mode == PET_CLAWD and self.desktop_pet.is_enabled():
        self.desktop_pet.announce("我会留在这里。点我可以重新打开控制台。", "waving", 5200)

def closeEvent(self, event) -> None:
    if self._quitting:
        event.accept()
        return
    event.ignore()
    self.request_console_close()
```

- [ ] **Step 4: 真正退出时移除托盘**

```python
def exit_application(self) -> None:
    # 保留现有宠物设置落盘逻辑。
    self._quitting = True
    self.tray_icon.hide()
    self.tray_icon.setContextMenu(None)
    self.desktop_pet.close_pet()
    QApplication.instance().quit()
```

- [ ] **Step 5: 运行定向测试并确认绿灯**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "tray_icon or close_only_hides or exit_application_cleans or pet_keeps_running" -q`

Expected: PASS。

---

### Task 3: 回归、构建与 Windows 盐雾测试

**Files:**
- Modify: `README_同事使用说明.md`
- Build output: `dist/百度数据自动化控制台.exe`

**Interfaces:**
- Consumes: Task 2 的托盘和关闭生命周期。
- Produces: 可供本机检查的最终 EXE，不生成 ZIP。

- [ ] **Step 1: 同步用户说明**

在 `README_同事使用说明.md` 中写明：右上角 `X` 只隐藏程序；托盘左键恢复；真正退出使用托盘右键或系统配置菜单。

- [ ] **Step 2: 运行全量基础测试**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py`

Expected: 全部通过。

- [ ] **Step 3: 重建窗口模式 EXE**

Run: `build_desktop_exe.bat`

Expected: `dist\百度数据自动化控制台.exe` 存在且大小非 0，不出现控制台黑窗。

- [ ] **Step 4: 执行非破坏性 Windows 盐雾测试**

验证：任务栏显示应用小图标；`X` 后主窗口消失但托盘仍在；托盘左键恢复；第二次启动仍只有一个主窗口；不运行日报/小时报，不导入配置，不写 Excel。

- [ ] **Step 5: 提交实现**

```cmd
git add gui/main_window.py tests/test_basic.py README_同事使用说明.md
git commit -m "Keep desktop app available from system tray"
```
