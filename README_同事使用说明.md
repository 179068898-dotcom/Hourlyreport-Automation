# 同事使用说明

版本：v0.4.4 内部试用发布版

这是百度竞价日报/小时报自动化工具的本地发布包。

## 第一次使用

1. 解压发布包到一个固定目录，例如 `D:\hourly_report_bot`。
2. 优先双击 `START_HERE.bat`。它会自动安装环境并打开菜单。
3. 把项目 Excel 放到项目配置里指定的位置，或修改 `configs/projects/kunming_npx.json` 里的 `excel_path`。
4. 从 `secrets/secrets.example.json` 复制一份为 `secrets/secrets.json`，填写百度账号密码。
5. 双击 `run_menu.bat` 打开中文菜单。程序会自动检测并启动项目专用 Chrome 调试窗口。
6. 先选择”检查运行环境”，确认关键项通过。
7. 每天先把商务通导出 Excel/CSV 放到 `kst_exports/` 目录，再运行日报或小时报。
8. 如果 Chrome 自动启动失败，可以使用备用脚本 `start_chrome_debug.bat` 手动启动。

## 配置 Excel 和商务通路径

打开：

```text
configs/projects/kunming_npx.json
```

目标 Excel 路径改这里：

```json
"excel": {
  "path": "D:/你的文件夹/2026竞价数据.xlsx",
  "hourly_sheet": "时段数据",
  "daily_sheet": "百度",
  "engine": "openpyxl"
}
```

`engine` 默认是 `openpyxl`，适合 WPS 环境，不需要安装 Microsoft Excel。写入前请关闭 WPS 中打开的目标表格，否则程序会提示“请关闭 WPS 中的目标文件后重试”。

如果以后新增第二个项目，复制 `configs/projects/kunming_npx.json`，改成新的项目文件，例如 `configs/projects/new_project.json`，然后修改里面的 `project_id`、`project_name`、`excel.path`、`kst.export_dir`、`baidu.credential_profile` 和 `accounts`。菜单里的“切换项目”会立即切到新项目。

商务通导出可以填“目录”，程序会自动选最新文件：

```json
"kst": {
  "export_dir": "D:/kstfiles"
}
```

也可以直接填某一个导出文件：

```json
"kst": {
  "export_dir": "D:/kstfiles/数据统计_网页记录_20260508154158-0.xlsx"
}
```

注意：JSON 里建议用 `/`，不要用单个 `\`。

## 常用菜单

- `运行日报`：默认处理昨天，写入 `百度` sheet；执行前会显示条件检查，确认后才开始。
- `运行小时报`：进入后选择 `11点`、`3点` 或 `6点`，写入 `时段数据` sheet；执行前会显示条件检查，确认后才开始。
- `切换项目`：以后有多个项目时使用。
- `刷新当前项目`：修改配置文件后重新读取当前项目。
- `检查运行环境`：检查 Python、依赖、Chrome、Excel 写入引擎、项目配置、商务通导出等。默认 `openpyxl` 模式不会要求安装 Microsoft Excel。

## 注意事项

- 不要把 `secrets/secrets.json` 发给别人。
- 运行写入前请关闭目标 WPS/Excel 文件，否则可能保存失败。
- 发布包不会包含真实 Excel、日志、报告、备份和商务通导出文件。
- 如果 Chrome 调试端口不可用，先运行 `start_chrome_debug.bat`。

## 双击没有反应怎么办

1. 确认已经先“解压全部”，不要在压缩包预览窗口里直接双击。
2. 优先双击 `START_HERE.bat`，不要先点其他文件。
3. 如果仍然没有窗口，右键 `START_HERE.bat`，选择“解除锁定”（如果有），再双击。
4. 如果还是没有窗口，在当前文件夹地址栏输入 `cmd` 回车，然后运行：

```cmd
START_HERE.bat
```

5. 把黑色窗口里的报错截图发回来。
