# OpenClaw 小时报自动化执行手册

目标读者：OpenClaw、夏思道，以及任何负责代执行小时报的自动化助手。

## 系统一句话说明

自动读取当前项目百度展现/点击/消费，解析商务通导出文件，合并后写入项目 Excel 的小时报时段数据。

## 固定项目目录与编码规则

固定目录：

```cmd
D:\自动化脚本\hourly_report_bot_release_v0.4.4
```

OpenClaw 执行任何命令前必须先进入该目录：

```cmd
cd /d D:\自动化脚本\hourly_report_bot_release_v0.4.4
```

禁止从其他目录直接运行 `main.py`。中文 JSON、Markdown 和日志文件统一按 `UTF-8` 读取和写入；禁止使用系统默认 ANSI/GBK 编码读取 UTF-8 文件后再覆盖保存，否则会造成中文乱码。优先调用 `run_openclaw_hourly.bat`，该入口已固定 `chcp 65001`、`PYTHONUTF8=1` 与 `PYTHONIOENCODING=utf-8`。

OpenClaw 必须继续走 `run_openclaw_hourly.bat` 这个专用窗口入口。不要绕过 BAT 自己拼 `main.py --mode run`，不要跳过 preflight，不要在失败后手工补 Excel 数字。

## 执行前检查清单

| 检查项 | 必须满足 | 不满足时怎么做 |
|---|---|---|
| Chrome `9222` 调试端口 | 已启动且可连接 | 运行 `start_chrome_debug.bat`，再重跑预检 |
| 当前项目 | 项目名与本次任务一致 | 停止，交由人工在菜单中切换项目；不要提交 `app_config.json` |
| `secrets/secrets.json` | 是合法 JSON | 停止，报告 JSON 错误位置 |
| 当前项目 credential profile | 每个所需 profile 存在，且 `username` / `password` 非空 | 停止，联系本机管理员检查 secrets；禁止向用户索要百度密码 |
| 商务通最新导出文件 | 当前项目目录中存在本时段可用文件 | 停止并提醒用户先导出商务通文件 |
| 目标 Excel | 文件存在，且写入前已关闭 | 停止并提醒用户关闭 WPS/Excel |
| 目标时段 | `11点`、`15点` 或 `18点` 已到点 | 停止，不提前执行 |
| 凭据沟通 | 不允许 OpenClaw 向用户索要百度账号密码 | 只报告本地 profile 缺失或为空 |

## 命令白名单

OpenClaw 优先调用：

```cmd
run_openclaw_hourly.bat 11点
run_openclaw_hourly.bat 15点
run_openclaw_hourly.bat 18点
```

专用窗口规则：

- 窗口标题应显示 `OpenClaw Hourly - fixed entry`。
- 窗口会先输出固定入口提示和当前工作目录。
- 窗口会先执行 `main.py --mode preflight --quick`，失败则停止。
- 只有 preflight 通过后，才会继续执行对应时段 `run`。
- OpenClaw 不要自行拆分为 `fetch-baidu-auto`、`parse-kst-export`、`merge-data`、`write-excel` 去跑完整小时报。

诊断或人工确认时，只允许按需执行：

```cmd
cd /d D:\自动化脚本\hourly_report_bot_release_v0.4.4
.venv\Scripts\python.exe main.py --mode preflight --quick
.venv\Scripts\python.exe main.py --mode test-baidu-credentials
.venv\Scripts\python.exe main.py --mode show-project
.venv\Scripts\python.exe main.py --mode doctor
.venv\Scripts\python.exe main.py --mode run --period 11点 --yes
.venv\Scripts\python.exe main.py --mode run --period 15点 --yes
.venv\Scripts\python.exe main.py --mode run --period 18点 --yes
```

## 小时报标准 SOP

1. 进入目录：

```cmd
cd /d D:\自动化脚本\hourly_report_bot_release_v0.4.4
```

2. 运行预检：

```cmd
.venv\Scripts\python.exe main.py --mode preflight --quick
```

OpenClaw 默认使用快速预检：检查运行条件、Excel 路径、商务通目录、Chrome 9222 与凭据状态，但跳过耗时的小时报 sheet 结构扫描。完整预检命令 `.venv\Scripts\python.exe main.py --mode preflight` 仅用于新项目上线、Excel 模板变更、结构识别异常或排障。

3. 如果 `preflight` 失败，停止，不要执行小时报；只按错误提示修复本地环境。
4. 运行完整诊断：

```cmd
.venv\Scripts\python.exe main.py --mode doctor
```

5. 确认商务通已导出；没有导出文件则停止，并提醒用户导出。
6. 执行对应时段：

```cmd
.venv\Scripts\python.exe main.py --mode run --period 11点 --yes
.venv\Scripts\python.exe main.py --mode run --period 15点 --yes
.venv\Scripts\python.exe main.py --mode run --period 18点 --yes
```

7. 执行完成后查看：

- `reports/final_run_report.json`
- `reports/write_report.json`
- `logs/run.log` 末尾
- Excel 是否写入对应时段

## 登录页卡住时的处理规则

- 禁止向用户索要百度密码。
- 不要让用户重新提供凭证；凭证应已存在于本机 `secrets/secrets.json`。
- 如果凭据读取失败，运行 `.venv\Scripts\python.exe main.py --mode test-baidu-credentials`。
- 如果自动退出旧账号失败，程序会自动清理当前浏览器上下文 cookie / storage / 本地登录状态，再跳 CAS 登录当前项目账号；仍失败时查看 `reports/baidu_session_check_report.json` 和 `logs/run.log`，不要手工补 Excel。
- 如果出现验证码、安全验证或滑块，停止并报告，不要继续盲点。
- 如果卡在 CAS 登录页，先看 `preflight` 与 `test-baidu-credentials` 的结果，不要反复重跑 `run`。

## Chrome 与静默规则

- 自动化只连接 Chrome 调试端口 `9222`，不使用 Edge。
- `start_chrome_debug.bat` 用于准备项目专用调试 Chrome；如果 `9222` 已经可连接，会复用现有实例，不会关闭老 Chrome。
- 静默模式默认不把 Chrome 拉到前台；自动切换百度账号、自动清 cookie、自动 CAS 登录都应在后台完成。
- 只有验证码、安全校验、滑块、人工确认等确实需要人处理的场景，才允许把 Chrome 窗口显示到前台。
- 禁止关闭旧 Chrome 后新开一个普通 Chrome 窗口来跑小时报；应复用或启动项目专用调试 Chrome。

## 常见错误与处理

| 现象 | 原因 | OpenClaw 应该怎么做 |
|---|---|---|
| 卡在 CAS 登录页 | 凭据预检未做、页面需校验或登录态异常 | 先跑 `preflight` 和 `test-baidu-credentials`；验证码/滑块时停止 |
| 反复要求凭证 | 未遵守本地 secrets 流程 | 停止询问；只报告 profile 状态 |
| secrets JSON 不合法 | 文件格式损坏或编码被错误写回 | 停止；报告行列位置；以 UTF-8 修正 |
| 缺少 credential_profile | 当前项目本地凭据未配置 | 停止；报告缺少的 profile 名 |
| `username/password` 为空 | profile 存在但未填写 | 停止；报告哪个字段为空，不显示值 |
| Chrome `9222` 连接失败 | 调试 Chrome 未启动 | 运行 `start_chrome_debug.bat` 后重跑预检 |
| 当前项目不对 | 本地项目选择状态错误 | 停止，要求人工切换到目标项目 |
| 商务通文件未找到 | 尚未导出或目录配置不对 | 停止并提醒导出/核对目录 |
| Excel 被打开导致写入失败 | WPS/Excel 文件锁定 | 关闭目标文件后重跑 |
| 百度账号不匹配 | 当前登录的是其他项目账号 | 让程序按现有规则自动切换；失败时查看会话报告 |
| 自动退出失败 | 页面 dropdown 未弹出或页面状态无法自动操作 | 程序会自动清 cookie 后重登；仍失败时停止并报告 |
| Chrome 自动化窗口跳前台 | 静默配置异常或页面需要人工处理 | 确认 `silent_automation=true`、`window_state=minimized`；验证码/安全校验才前台处理 |
| report 表格解析异常 | 百度页面表格加载或结构变化 | 停止，查看 reports 与日志，不手改数据 |
| 多 source 某个 source 失败 | 任一百度来源未能完成读取 | 整步失败，禁止继续写部分数据 |

## 禁止行为

OpenClaw 禁止：

- 询问用户真实百度密码，禁止向用户索要百度密码。
- 把密码写到聊天输出、日志、测试或说明文件。
- 在 `secrets.example.json` 填写真实密码。
- 提交 `secrets/secrets.json`。
- 提交 `configs/app_config.json` 的本地状态。
- 在错误项目上继续运行小时报。
- `preflight` 失败后继续运行 `run`。
- Excel 打开时强行写入。
- 百度 source 失败时继续写入部分数据。
- 使用 ANSI/GBK 方式读取 UTF-8 中文配置或文档后覆盖写回。
