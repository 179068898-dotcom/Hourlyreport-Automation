# OpenClaw 日报自动化执行手册

## 适用场景

OpenClaw 代执行日报，自动读取昨天或指定日期的百度数据和商务通导出数据，写入项目 Excel 的“百度”sheet。

## 固定执行目录

```cmd
D:\自动化脚本\hourly_report_bot_release_v2.0
```

OpenClaw 优先调用日报批处理入口，不直接拼接 `main.py` 执行完整日报。批处理入口已固定项目目录、`.venv` 与 UTF-8 环境。

OpenClaw 必须继续走 `run_openclaw_daily.bat` 这个专用窗口入口。不要绕过 BAT 直接执行 `run-daily`，不要自己改当前项目，不要在失败后手工补 Excel 数字。

## 标准命令

默认执行昨天日报：

```cmd
run_openclaw_daily.bat
```

执行指定日期日报：

```cmd
run_openclaw_daily.bat 2026-05-24
```

专用窗口规则：

- 窗口标题应显示 `OpenClaw Daily - fixed entry`。
- 窗口会先输出固定入口提示和当前工作目录。
- 窗口会先执行 `main.py --mode preflight --task daily --quick`，失败则停止。
- 只有 preflight 通过后，才会继续执行 `run-daily`。
- OpenClaw 不要自行拆分为 `fetch-baidu-daily`、`parse-kst-daily`、`merge-daily`、`write-daily` 去跑完整日报。

诊断或人工确认时的手动命令：

```cmd
cd /d D:\自动化脚本\hourly_report_bot_release_v2.0
.venv\Scripts\python.exe main.py --mode preflight --task daily --quick
.venv\Scripts\python.exe main.py --mode run-daily --yes
.venv\Scripts\python.exe main.py --mode run-daily --date 2026-05-24 --yes
```

## 日报执行前检查清单

- Chrome `9222` 调试端口已经启动并可连接。
- 当前项目 ID 与项目名符合本次日报任务。
- `secrets/secrets.json` 是合法 JSON，当前项目所需的每个 credential profile 均存在，且 `username` / `password` 非空。
- 商务通已人工导出日报所需文件，文件位于当前项目配置的导出目录或已明确指定。
- 目标 Excel 已关闭，避免 WPS/Excel 锁定文件导致写入失败。
- 日报日期正确，一般为昨天；补跑时必须明确指定日期。

`preflight --task daily --quick` 是 OpenClaw 默认快速预检：检查运行条件、Excel 路径、商务通目录、Chrome 9222 与凭据状态，但跳过耗时的日报 sheet 结构扫描，不打开百度页面、不写 Excel、不修改 `app_config`，也不输出真实账号或密码。

完整预检命令仍保留为 `.venv\Scripts\python.exe main.py --mode preflight --task daily`，仅用于新项目上线、Excel 模板变更、结构识别异常或排障。

## 日报执行后检查

- `reports/daily_final_run_report.json`
- `reports/baidu_daily_data.json`
- `reports/baidu_daily_validate_report.json`
- `reports/daily_merge_validate_report.json`
- `reports/daily_write_report.json`
- `logs/run.log` 末尾
- Excel “百度”sheet 对应日期是否已写入

## 日报写入范围

- 日报仅写入项目 Excel 中已允许的日报字段。
- 预约、到诊、就诊等禁止字段不由本工具填写。
- OpenClaw 不得在日报完成后自行追加任何外部填表或补数步骤。

## 禁止行为

- 禁止向用户索要百度密码。
- 不得输出真实密码。
- 不得修改 `secrets.example.json` 填真实密码。
- 不得提交 `secrets/secrets.json`。
- `preflight` 失败后不得继续 `run-daily`。
- Excel 打开时不得强行写入。
- 任一 baidu source 失败时不得继续写部分日报数据。
- 遇到验证码、安全验证或滑块时停止并报告。
- 禁止关闭旧 Chrome 后新开一个普通 Chrome 窗口来跑日报；应复用或启动项目专用调试 Chrome。
- 禁止手动删除 `browser_profile/chrome_debug` 作为常规处理；只有明确排障时才允许人工清理。

## Chrome 与登录态规则

- 自动化只连接 Chrome 调试端口 `9222`，不使用 Edge。
- `start_chrome_debug.bat` 用于准备项目专用调试 Chrome；如果 `9222` 已经可连接，会复用现有实例，不会关闭老 Chrome。
- 静默模式默认不把 Chrome 拉到前台；自动切换百度账号、自动清 cookie、自动 CAS 登录都应在后台完成。
- 当旧项目账号残留导致需要切号时，程序会先尝试页面退出；如果页面 dropdown 没弹出导致退出失败，会自动清理当前上下文 cookie / storage / 本地登录状态，再跳 CAS 登录当前项目账号。
- 只有验证码、安全校验、滑块、人工确认等确实需要人处理的场景，才允许把 Chrome 窗口显示到前台。

## 常见问题

| 现象 | 处理方式 |
|---|---|
| 卡 CAS 登录页 | 先检查 `preflight --task daily` 和凭据 profile 状态；不得反复索要凭据或盲目重跑。 |
| secrets JSON 错 | 停止执行，报告 JSON 错误位置，由本机管理员按 UTF-8 修复。 |
| profile 缺失或为空 | 停止执行，只报告缺少的 profile 或空字段，不显示真实值。 |
| 当前项目不对 | 停止日报，由人工切换当前项目后重新预检。 |
| 旧百度账号退出失败 | 程序会自动清 cookie 后重登；仍失败时查看 `reports/baidu_session_check_report.json` 和 `logs/run.log`，不要手工补 Excel。 |
| Chrome 一直跳前台 | 确认配置保持 `silent_automation=true`、`window_state=minimized`；只有验证码/安全校验才应前台处理。 |
| 商务通日报文件未找到 | 停止执行，要求先人工导出正确日期的数据。 |
| 百度日报 report 解析异常 | 停止写入，检查 `reports/baidu_daily_data.json`、自检报告与日志。 |
| 百度日报表格数据未稳定 | 程序已阻止写入，等待页面/API 加载稳定后整次重跑；不得手工补 Excel。 |
| Excel 百度 sheet 找不到日期行 | 停止写入，检查日报结构识别报告，不猜测目标单元格。 |
| 预约、到诊、就诊字段 | 不属于本工具写入范围；不得在日报任务后追加填写步骤。 |
