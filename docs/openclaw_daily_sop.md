# OpenClaw 日报自动化执行手册

## 适用场景

OpenClaw 代执行日报，自动读取昨天或指定日期的百度数据和商务通导出数据，写入项目 Excel 的“百度”sheet。

## 固定执行目录

```cmd
D:\自动化脚本\hourly_report_bot_release_v0.4.4
```

OpenClaw 优先调用日报批处理入口，不直接拼接 `main.py` 执行完整日报。批处理入口已固定项目目录、`.venv` 与 UTF-8 环境。

## 标准命令

默认执行昨天日报：

```cmd
run_openclaw_daily.bat
```

执行指定日期日报：

```cmd
run_openclaw_daily.bat 2026-05-24
```

诊断或人工确认时的手动命令：

```cmd
cd /d D:\自动化脚本\hourly_report_bot_release_v0.4.4
.venv\Scripts\python.exe main.py --mode preflight --task daily
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

`preflight --task daily` 只检查运行条件、日报 sheet 结构与凭据状态，不打开百度页面、不写 Excel、不修改 `app_config`，也不输出真实账号或密码。

## 日报执行后检查

- `reports/daily_final_run_report.json`
- `reports/baidu_daily_data.json`
- `reports/baidu_daily_validate_report.json`
- `reports/daily_merge_validate_report.json`
- `reports/daily_write_report.json`
- `logs/run.log` 末尾
- Excel “百度”sheet 对应日期是否已写入

## 到诊数 / 预约数后处理

- 程序不自动乱填到诊数。
- 到诊数需要问姜老师或用户确认。
- 如存在外部脚本 `D:\xia_sidao\tools\fill_daily_visit.py`，需确认脚本存在、参数明确后再执行。
- OpenClaw 不得自行编造到诊数。

日报批处理入口不执行任何外部腾讯文档脚本，也不自动执行到诊数后处理。

## 禁止行为

- 禁止向用户索要百度密码。
- 不得输出真实密码。
- 不得修改 `secrets.example.json` 填真实密码。
- 不得提交 `secrets/secrets.json`。
- `preflight` 失败后不得继续 `run-daily`。
- Excel 打开时不得强行写入。
- 任一 baidu source 失败时不得继续写部分日报数据。
- 遇到验证码、安全验证或滑块时停止并报告。

## 常见问题

| 现象 | 处理方式 |
|---|---|
| 卡 CAS 登录页 | 先检查 `preflight --task daily` 和凭据 profile 状态；不得反复索要凭据或盲目重跑。 |
| secrets JSON 错 | 停止执行，报告 JSON 错误位置，由本机管理员按 UTF-8 修复。 |
| profile 缺失或为空 | 停止执行，只报告缺少的 profile 或空字段，不显示真实值。 |
| 当前项目不对 | 停止日报，由人工切换当前项目后重新预检。 |
| 商务通日报文件未找到 | 停止执行，要求先人工导出正确日期的数据。 |
| 百度日报 report 解析异常 | 停止写入，检查 `reports/baidu_daily_data.json`、自检报告与日志。 |
| Excel 百度 sheet 找不到日期行 | 停止写入，检查日报结构识别报告，不猜测目标单元格。 |
| 到诊数未知 | 向姜老师或用户确认；未知时不得填写。 |
