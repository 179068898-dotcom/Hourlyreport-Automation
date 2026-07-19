# GUI Data Mode And Safe Stop Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 A/B 数据源切换迁移到独立标题栏菜单，并为小时报、日报增加进入 Excel 前可直接停止的 7:3 斜切组合按钮，同时建立微软雅黑标题/正文层级。

**Architecture:** 在 `gui/main_window.py` 内新增两个边界清晰的 Qt 控件：独立的数据模式浮层和运行/停止组合控件。主窗口维护停止请求及 Excel 阶段锁定状态，复用现有 `QtTaskRunner.stop()`，不改变业务 pipeline、命令参数或 Excel 写入代码。

**Tech Stack:** Python 3.14、PySide6、QProcess、pytest。

## Global Constraints

- 不执行真实 `run` / `run-daily`，不写 Excel。
- 不改变窗口尺寸、现有业务命令、API/浏览器持久化格式或在线更新文件名。
- 停止按钮只在当前小时报/日报任务开始后、进入 `excel` 阶段前可用。
- 点击停止不弹确认；进入 Excel 阶段后按钮必须灰掉且不可点击。
- 不回滚或清理当前工作区已有改动。

---

### Task 1: 独立数据模式菜单

**Files:**
- Modify: `gui/main_window.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: `DataSourceModeControl.set_preference(preference, animate, emit)`、`MainWindow.set_global_data_source_preference()`。
- Produces: `InlineDataModeMenu.data_source_control`、`MainWindow.data_mode_button`、`MainWindow.show_data_mode_menu()`。

- [ ] **Step 1: 写失败测试**

新增断言：数据控件尺寸为 `106 x 29`；标题栏存在“数据模式”按钮；系统配置浮层不含数据控件；数据模式浮层只承载 A/B 控件；两个菜单互斥；任务锁定作用于新浮层控件。

- [ ] **Step 2: 运行测试并确认按预期失败**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -q -k "data_source_control or data_mode_menu"
```

预期：缺少 `data_mode_button` / `InlineDataModeMenu`，尺寸仍为 `210 x 32`。

- [ ] **Step 3: 最小实现**

将 `DataSourceModeControl` 固定尺寸改为 `106 x 29`，按钮文案保持 `B 浏览器`、`A API`；新增独立 Popup 浮层并在标题栏“系统配置”后加入“数据模式”按钮；迁移 sync、锁定和回滚引用，系统配置浮层删除 A/B 控件。

- [ ] **Step 4: 运行聚焦测试**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -q -k "data_source_control or data_mode_menu"
```

预期：全部通过。

### Task 2: 7:3 斜切运行/停止控件

**Files:**
- Modify: `gui/main_window.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Produces: `RunStopSplitControl.run_button`、`RunStopSplitControl.stop_button`、`RunStopSplitControl.set_stop_enabled(bool)`。
- Consumes: 现有 `MainWindow.run_hourly()`、`MainWindow.run_daily()`。

- [ ] **Step 1: 写失败测试**

测试组合控件整体宽度保持原网格宽度；运行区约占 70%，停止区约占 30%；停止区 `y=2` 且左移 2 像素；分割线由控件 paint event 绘制；空闲停止按钮禁用。

- [ ] **Step 2: 运行测试并确认失败**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -q -k "run_stop_split or period_selection"
```

预期：不存在 `RunStopSplitControl` 和停止按钮。

- [ ] **Step 3: 最小实现**

新增固定高度组合控件，左侧运行按钮和右侧停止按钮使用绝对几何布局；父控件绘制蓝色圆角底、禁用停止区灰底及 2 像素白色斜线；小时报与日报布局替换原单按钮，但保留 `hourly_button` / `daily_button` 指向运行区以兼容调用代码。

- [ ] **Step 4: 运行聚焦测试**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -q -k "run_stop_split or period_selection"
```

预期：全部通过。

### Task 3: 安全停止状态机

**Files:**
- Modify: `gui/main_window.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: `QtTaskRunner.is_running()`、`QtTaskRunner.stop()`、`mark_stage(stage)`。
- Produces: `MainWindow.stop_current_task()`、`MainWindow.set_stop_controls()`。

- [ ] **Step 1: 写失败测试**

覆盖：空闲不可停止；小时报启动只启用小时报停止；日报启动只启用日报停止；项目配置检查不启用停止；点击后直接调用一次 runner.stop 并立即禁用；收到 `excel` 后禁用且后续点击无效；用户停止完成后显示“已停止”、不打开 Excel；普通失败仍显示失败。

- [ ] **Step 2: 运行测试并确认失败**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -q -k "safe_stop or stopped_task"
```

预期：缺少停止状态和用户停止结果分支。

- [ ] **Step 3: 最小实现**

主窗口新增 `_task_stop_requested`、`_task_stop_locked`；任务开始时按任务类型启用对应停止区；`mark_stage("excel")` 先锁定停止；`stop_current_task()` 无确认直接调用 runner.stop；`on_task_finished()` 为用户停止提供独立状态分支并阻止打开 Excel。

- [ ] **Step 4: 运行聚焦测试**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -q -k "safe_stop or stopped_task"
```

预期：全部通过。

### Task 4: 字体层级、回归与 EXE

**Files:**
- Modify: `gui/main_window.py`
- Modify: `tests/test_basic.py`
- Build: `dist/百度数据自动化控制台.exe`

**Interfaces:**
- Produces: `FONT_LIGHT_FAMILY`、`FONT_REGULAR_FAMILY`、`FONT_TITLE_FAMILY` 及对应 stylesheet 字体栈。

- [ ] **Step 1: 写失败测试**

断言主窗口基础字体为 `Microsoft YaHei Light`；产品标题、卡片标题和流程/日志标题使用 `Microsoft YaHei UI` 且 DemiBold；标题栏低频菜单使用 Light；日志仍为 Consolas/Cascadia Mono。

- [ ] **Step 2: 运行并确认失败**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -q -k "font and desktop_gui"
```

预期：当前全局字体仍为 `Microsoft YaHei UI`。

- [ ] **Step 3: 实现字体层级并运行 GUI 聚焦测试**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -q -k "desktop_gui or data_mode_menu or run_stop_split or safe_stop or stopped_task"
```

预期：全部通过。

- [ ] **Step 4: 全量验证**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py
git diff --check
```

预期：589 项既有测试加新增测试全部通过；diff check 退出码 0。

- [ ] **Step 5: 重建并烟雾检查 EXE**

```cmd
build_desktop_exe.bat
```

启动 `dist/百度数据自动化控制台.exe`，确认唯一实例、无黑窗、标题栏“数据模式”、斜切停止区和字体层级；不执行真实业务任务。
