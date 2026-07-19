# Hourlyreport 更新与命名统一实施计划

## 文件职责

- `gui/update_manager.py`：Release 解析、下载校验、更新助手和 EXE 迁移。
- `gui/update_dialog.py`：独立更新安装进度浮层。
- `gui/main_window.py`：顶部更新状态控件、菜单间距和安装入口。
- `gui/app.py`：更新目录识别和应用身份。
- `tools/build_desktop_exe.py`：生成 `hourlyreport_automation.exe`。
- `tools/build_release.py`：生成统一命名的在线包与首次安装包。
- `tests/test_basic.py`：更新协议、安全边界、GUI 状态、构建命名和兼容迁移回归测试。
- `docs/online_update_sop.md`、`README.md`、`AGENTS.md`：发布与桥接说明。

## 任务一：锁定新发布协议

先在 `tests/test_basic.py` 增加失败测试：

- 新 GitHub API 地址。
- `v<版本>` 与一次旧标签兼容解析。
- `Hourlyreport_automation_v<版本>.zip` 精确匹配。
- draft、prerelease、缺失或错误 digest、零大小资产被拒绝。
- 当前新仓库 104 响应可解析但不会覆盖同版本。

运行相关测试确认失败，再修改 `gui/update_manager.py` 使其通过。

## 任务二：统一构建与 EXE 兼容

先增加失败测试：

- `APP_EXE_NAME == "hourlyreport_automation.exe"`。
- 发布包名为 `Hourlyreport_automation_v<版本>.zip`。
- 包内必需主程序使用新文件名。
- 更新助手会生成旧文件名兼容副本并优先重启新 EXE。

再修改构建、发布和更新助手。保持受保护目录规则不变。

## 任务三：实现 Codex 风格更新状态

先增加 GUI 失败测试，覆盖 checking、downloading、ready、installing、hidden 状态及对应图标、文字、颜色和可用性。

新增 `gui/update_dialog.py`，由更新助手显示圆角白色进度浮层。`gui/main_window.py` 只负责状态切换和发起安装，不模拟虚假完成进度。

## 任务四：收紧菜单间距

更新 GUI 测试，要求标题布局间距为 2 px，系统配置与数据模式按钮宽度仅比文字宽 10 px 左右。修改按钮固定尺寸与样式内边距，保持悬浮区域居中且不裁字。

## 任务五：同步文档与桥接发布规则

更新 `AGENTS.md`、`README.md` 和 `docs/online_update_sop.md`：

- 新仓库、新 tag、新资产与新 EXE 名称。
- 首个迁移版本必须同时上传新旧仓库。
- 后续只发布新仓库。
- 真实 secrets 和用户配置继续禁止进入任何发布包。

## 任务六：验证、提交与目录迁移

依次运行：

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py
.venv\Scripts\python.exe tools\build_desktop_exe.py
.venv\Scripts\python.exe tools\build_release.py --version 2026.7.19.105 --online-update
```

额外执行真实新仓库只读检查、ZIP 内容审计、SHA-256 计算和 EXE 视觉验收。提交代码后将 Git remote 更新到 `Hourlyreport-Automation`。

最后关闭由验收启动的本项目进程，在父目录把开发目录迁移为 `hourlyreport_automation`。迁移前验证源路径和目标路径，若目标已存在则停止，不覆盖。
