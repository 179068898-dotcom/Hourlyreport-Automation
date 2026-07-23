# 在线更新助手缺失模块修复计划

> 日期：2026-07-23
> 故障：已安装版本下载更新后，点击“更新并重启”出现
> `ModuleNotFoundError: No module named 'gui.update_dialog'`。

## 根因与边界

`gui/update_manager.py` 把更新助手作为字符串 `UPDATE_HELPER_SOURCE` 动态执行。该字符串内部导入
`gui.update_dialog`，PyInstaller 无法通过静态分析发现它，而
`tools/hourlyreport_automation.spec` 的 `hiddenimports` 为空，因此单文件 EXE 未包含该模块。

更新助手在解压新版本 ZIP 之前就执行此导入，所以仅替换线上 ZIP 无法修复已经安装的 109/110
程序。现有故障电脑必须先人工运行修复后的完整安装器；修复后的 EXE 才能保证后续版本继续自动更新。

## Task 1：锁定构建依赖

**修改文件：**

- `tests/test_basic.py`

**步骤：**

1. 在桌面构建 spec 测试中断言 `hiddenimports` 明确包含 `gui.update_dialog`。
2. 运行：

   ```cmd
   .venv\Scripts\python.exe -m pytest tests\test_basic.py -k "desktop_build_spec" -q
   ```

3. 预期修复前失败，失败原因是 spec 未声明动态导入。

## Task 2：最小修复 PyInstaller 配置

**修改文件：**

- `tools/hourlyreport_automation.spec`

**步骤：**

1. 将 `Analysis(..., hiddenimports=[])` 改为：

   ```python
   hiddenimports=["gui.update_dialog"],
   ```

2. 重跑 Task 1 测试，预期通过。
3. 运行完整测试：

   ```cmd
   .venv\Scripts\python.exe -m pytest tests\test_basic.py
   ```

## Task 3：构建级验证

1. 重建桌面 EXE：

   ```cmd
   .venv\Scripts\python.exe tools\build_desktop_exe.py
   ```

2. 检查 EXE 内部模块：

   ```cmd
   .venv\Scripts\python.exe -m PyInstaller.utils.cliutils.archive_viewer -r -b dist\hourlyreport_automation.exe
   ```

3. 输出必须同时包含 `gui.update_manager` 和 `gui.update_dialog`。
4. 不使用不完整参数直接启动 GUI EXE，避免 PyInstaller 异常窗口阻塞自动验证；内部模块清单是本次缺失模块故障的确定性验证入口。

## Task 4：发布可人工恢复的修复版本

现有 `110` ZIP 和安装器生成于本次修复之前，不能作为恢复包。获得发布授权后必须：

1. 版本升级为下一永久累计号 `2026.7.23.111`。
2. 更新中文发布说明及在线更新文档。
3. 重新构建 EXE、完整安装器和在线更新 ZIP。
4. 审计在线更新包的受保护目录与敏感文件。
5. 重新运行完整测试并确认新安装器晚于修复后 EXE 生成。
6. 将 `111` 完整安装器人工提供给仍在 `109/110` 的用户安装一次；不要让其继续点击旧版的“更新并重启”。
7. 人工安装 `111` 后，后续版本恢复正常在线更新。

## 完成门禁

- 回归测试经历红灯到绿灯。
- 完整测试无失败。
- PyInstaller 构建成功。
- EXE 内部模块清单存在 `gui.update_dialog`。
- 发布修复版本时使用新的累计版本号，不能覆盖或复用现有 `110` 资产。
- 不运行真实业务任务，不写 Excel，不修改或提交用户配置。
