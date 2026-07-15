# 百度数据自动化工具

内部同步标记：`HERMES-20260710`

Windows 本地运行的百度竞价日报/小时报工具。程序读取百度营销后台数据、解析人工导出的快商通 Excel/CSV，并在备份后写入各项目现有 Excel。

## 使用入口

普通同事优先双击发布包根目录：

```text
百度数据自动化控制台.exe
```

命令行菜单：

```cmd
run_menu.bat
```

HERMES（夏思道）固定入口：

```cmd
run_hermes_hourly.bat 11点
run_hermes_hourly.bat 15点
run_hermes_hourly.bat 18点
run_hermes_daily.bat
run_hermes_daily.bat 2026-07-09
```

自动代执行统一使用 `run_hermes_*.bat` 固定入口。

## 首次环境

GUI、HERMES BAT 和 `run_menu.bat` 都会检查 `.venv`。缺少系统 Python 时，`install_env.bat` 调用 `tools/bootstrap_python.ps1`：

1. 从 Python 官方地址下载固定的 64 位安装器。
2. 校验固定 SHA-256。
3. 静默安装到项目 `runtime/python`，不修改系统 PATH。
4. 创建 `.venv`。
5. 安装 `requirements-runtime.txt` 中的运行依赖。

开发/测试/打包依赖单独位于 `requirements-dev.txt`。

## 当前项目

正式项目共九个：昆明牛、南京牛、宁波牛、长沙牛、沈阳牛、青岛白、深圳白、南京白、沈阳白。

- 双百度来源：沈阳牛、沈阳白。
- 默认项目：昆明牛。
- 南京牛包含 `baidu-华厦npx6`，推广 ID `85492975`。

项目配置位于 `configs/projects/*.json`，当前项目和凭据文件位置由 `configs/app_config.json` 指定。真实账号密码只放在 `secrets/secrets.json`，不得提交或公开发送。

## 数据规则

- 快商通仍由人工导出，不调用收费 API，不操作桌面客户端。
- 自动选择时只接受 30 分钟内的最新快商通文件；没有时按 0 对话继续，不中断任务。
- 百度日报必须连续快照稳定，并在可识别总计行时校验账户求和。
- 双百度来源必须全部成功，不写部分结果。
- 成功完成日报/小时报后，GUI 自动打开当前项目 Excel。

## Excel 边界

- 写入前必须备份原文件。
- 不重建工作簿。
- 通过表头、账户和字段动态识别写入位置，不写死坐标。
- 不修改无关 sheet、公式区、汇总区、截图区或“每日时段统计数据”。
- 结构不明确时中断并输出诊断，不猜测写入。

## Chrome

- 只连接或启动 Google Chrome 调试端口 `9222`，不自动降级到 Edge。
- 已有调试 Chrome 优先复用，未启动时 preflight 自动尝试启动项目专用实例。
- 自动登录、清 cookie 和账号切换默认静默；验证码、滑块或安全校验才要求人工处理。

## 验证

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py
```

禁止在未获用户明确授权时运行真实 `run` / `run-daily` 或写入目标 Excel。

## 构建

```cmd
build_desktop_exe.bat
.venv\Scripts\python.exe tools\build_release.py --internal
```

GUI 使用 PyInstaller `onefile + windowed`，发布 ZIP 将 `百度数据自动化控制台.exe` 放在根目录。内部包包含本机 secrets，只能内部传递。

## 文档

- `AGENTS.md`：所有 AI Agent 的硬规则。
- `xia_sidao使用说明.md`：HERMES / 夏思道操作说明。
- `docs/hermes_hourly_sop.md`：小时报 SOP。
- `docs/hermes_daily_sop.md`：日报 SOP。
- `README_同事使用说明.md`：普通同事快速使用说明。
