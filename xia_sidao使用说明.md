# 夏思道（HERMES）使用说明

入口同步标记：`HERMES-20260710`

当前产品名为“蚁之力 · 竞价数据自动化”。夏思道使用 HERMES 固定入口执行任务，自动代执行只允许调用 `run_hermes_*.bat`。

## 当前能力

- 小时报：读取百度展现、点击、消费，读取人工导出的快商通文件，写入 `时段数据` sheet。
- 日报：读取百度日报和人工导出的快商通日报，写入 `百度` sheet；不传日期时默认昨天。
- 正式项目：昆明牛、南京牛、宁波牛、长沙牛、沈阳牛、青岛白、深圳白、南京白、沈阳白。
- 双百度来源：沈阳牛、沈阳白。
- 南京牛已包含 `baidu-华厦npx6`，推广 ID `85492975`，沿用现有 Excel 字段映射。
- 当前不做 QQ、截图、自动发消息，也不自动操作快商通客户端或网页。

## 唯一自动入口

进入本程序根目录后执行。

小时报：

```cmd
run_hermes_hourly.bat 11点
run_hermes_hourly.bat 15点
run_hermes_hourly.bat 18点
```

日报：

```cmd
run_hermes_daily.bat
run_hermes_daily.bat 2026-07-09
```

- 不带日期的日报处理昨天。
- 固定窗口标题包含 `HERMES`、任务类型和 `20260710`。
- 小时报窗口标题保持 `HERMES Hourly - fixed entry - 20260710`，日报窗口标题保持 `HERMES Daily - fixed entry - 20260710`。
- BAT 固定工作目录、UTF-8 和 `.venv` Python。
- `.venv` 不存在时，BAT 会调用 `install_env.bat` 自动准备环境。
- 小时报先执行 `preflight --quick`，日报先执行 `preflight --task daily --quick`；失败立即停止。
- 禁止绕过 BAT 自己拼 `main.py --mode run` 或拆分阶段代替完整任务。

## 百度数据源模式

HERMES 与 GUI、命令行完整任务共享同一应用级偏好 `baidu_data_source_preference`，BAT 文件名、参数和窗口规则不变：

- `A` / `api`：默认 API 优先；Token、网络或完整性异常先在 20 秒总预算内有限自修复，仍失败则自动整项目降级浏览器。
- `B` / `browser`：强制浏览器，不调用 API，是紧急回退入口。

九个项目、十一个授权已导入，正式发布前必须由开发人员显式运行 `.venv\Scripts\python.exe main.py --mode test-baidu-api-readiness`。该入口只读百度数据，不读写 Excel；Token 过期时可按生产规则备份并原子更新 `secrets/secrets.json`，原文件和备份均为敏感文件。

沈阳牛、沈阳白必须两路 API 全部成功后才合并；任一路失败时丢弃 API 临时结果并整项目降级，禁止混合 API 与浏览器的部分数据。多项目并行尚未投入生产。

API 模式的 preflight 不提前启动 Chrome；只有 API 最终失败、实际降级时才延迟启动 Chrome。普通 GUI 不得自动调用 `test-baidu-api`、`test-baidu-api-readiness`、`simulate-baidu-api-hourly` 或 OAuth 导入等开发探测入口。

## 执行前

1. 人工在 GUI 或菜单中把“当前项目”切换到本次项目。
2. 目标 Excel 必须存在，并关闭 WPS/Excel 中已打开的同一文件。
3. 快商通数据仍需人工导出到项目配置的目录。
4. 仅 30 分钟内的最新快商通文件参与本次任务；没有符合条件的文件时按 0 对话继续，不作为程序故障。
5. 不向用户索要、展示或记录真实百度账号密码；凭据只从本机 `secrets/secrets.json` 读取。

## Chrome 与登录

- 只使用 Google Chrome 调试端口 `9222`，不自动改用 Edge。
- `A` 模式预检不接触 Chrome，实际降级后才复用或延迟启动项目专用实例；`B` 模式预检继续检查 Chrome 9222。
- 自动切换账号、清 cookie 和 CAS 登录默认静默，不抢前台。
- 页面退出失败时，程序会清理当前上下文 cookie/storage 后重登当前项目账号。
- 遇到验证码、滑块、安全验证或明确要求人工确认时，停止并说明需要人工处理。

## 数据与 Excel 安全

- Excel 写入前必须备份原文件，不重建工作簿。
- 只写动态识别出的账户和字段区域，不写死单元格坐标。
- 不修改无关 sheet、公式区、汇总区、截图区或“每日时段统计数据”。
- 百度日报必须连续快照稳定且通过总计校验后才允许写入；不稳定时整次失败，不写部分结果。
- API 任一路失败先丢弃临时结果并整项目降级浏览器；仅 API 与浏览器均失败时停止，禁止写 Excel。
- 失败后禁止手工补数字。

## 成功与失败判断

小时报成功重点：

```text
reports/final_run_report.json
reports/write_report.json
logs/run.log
```

日报成功重点：

```text
reports/daily_final_run_report.json
reports/daily_write_report.json
logs/run.log
```

退出码 `0` 才算完成。GUI 成功后会自动打开当前项目 Excel。

## 常见异常

| 现象 | 处理 |
|---|---|
| 当前项目不对 | 人工先在 GUI/菜单切换项目，再重新执行固定 BAT |
| Chrome 9222 无法连接 | 等待自动启动；仍失败再运行 `start_chrome_debug.bat` 排障 |
| 百度要求验证码/滑块 | 停止，等待人工完成验证后整次重跑 |
| 快商通没有 30 分钟内文件 | 正常按 0 对话继续，不当作 BUG |
| Excel 被占用 | 关闭对应 WPS/Excel 文件后整次重跑 |
| 百度数据两次不稳定 | 等待页面/API 稳定后整次重跑，不手工补数 |
| API 多来源某一路失败 | 程序自动丢弃临时结果并整项目降级浏览器；浏览器也失败时查看 `reports/baidu_multi_source_report.json` 后整次重跑 |

## 不得做

- 不跳过 preflight。
- 不绕过固定 BAT。
- 不自动启动 Edge。
- 不删除浏览器 profile 作为常规处理。
- 不泄露或提交 `secrets/secrets.json`。
- 不在失败后手工改 Excel 数字。

## 对应 SOP

- `docs/hermes_hourly_sop.md`
- `docs/hermes_daily_sop.md`
- `AGENTS.md`
