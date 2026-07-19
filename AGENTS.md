# AGENTS.md

本文件给所有参与本仓库开发的 AI Agent / 自动化助手使用。无论使用 Codex、Claude、HERMES（夏思道）或其他平台，都必须优先遵守本文件。

## 基本约定

- 全程使用中文回复。
- 当前产品名为“蚁之力 · 竞价数据自动化”，是 Windows 本地运行的百度竞价日报/小时报自动化工具。
- 当前版本只做百度数据读取、快商通人工导出文件解析、本地 Excel 写入、日志和报告输出。
- 当前版本不做 QQ、不做截图、不自动发送任何消息。
- 不要向用户索要真实百度密码，不要输出、记录或提交 secrets。

## 最高优先级硬规则

1. 分阶段开发，不允许一次性做全流程。
2. Excel 写入前必须先备份原文件。
3. 不允许重建 Excel 文件。
4. 不允许修改无关 sheet。
5. 不允许修改“每日时段统计数据 / 汇总区域 / 截图区域 / 公式区域”。
6. Excel 区域识别必须通过扫描表头、账户区域和字段名称完成，不允许写死固定坐标。
7. 遇到不确定的 Excel 结构，不要猜测写入，必须中断并输出诊断信息。
8. 浏览器自动化不允许依赖绝对屏幕坐标，优先使用 URL、文本、表头、表格结构、选择器。
9. 浏览器自动化必须优先使用 Google Chrome，不允许默认启动 Edge。
10. Chrome 启动失败时必须输出明确错误并等待人工确认，不允许静默降级到 Edge。
11. 每次修改后必须说明修改了哪些文件、修改了什么。
12. 每次运行后必须输出日志和自检结果。
13. 不要运行真实 `run` / `run-daily` 或写 Excel，除非用户明确要求。
14. 不要回滚用户或其他 Agent 的已有改动；如果工作区已有无关改动，只忽略，不要清理。

## 开发流程与 Superpowers 使用优先级

- 默认采用轻量开发流程，不要把完整 Superpowers 流程机械套用到每次修改。
- 用户在当前任务中明确要求“使用 Superpowers”或“不要使用 Superpowers”时，优先遵从；若与系统级强制规则或本文件安全硬规则冲突，则执行更高优先级规则。
- 微小修改：文案、字号、间距、颜色、单个明确条件、局部配置或说明文档等低风险且易回退的改动，直接做最小修改，只检查 diff 并运行最相关测试。
- 普通修改：先做简短分析，再实施并运行相关测试；不强制 brainstorming、书面实施计划、TDD 仪式或独立代码评审。
- 高风险修改：启用完整 Superpowers，包括必要的诊断、需求澄清、计划、测试驱动、代码审查和完成前验证。
- 无论代码量大小，涉及安全、权限、账号授权、secrets、数据迁移、支付、并发、破坏性文件操作、Excel 写入保护边界、在线更新或发布包覆盖规则时，都按高风险修改处理。
- 新功能、复杂 Bug、跨模块重构、公共接口变化、架构调整或难以回退的行为变化，默认按高风险修改处理。
- 轻量任务实施中一旦发现会影响多个模块、公共接口、用户数据、安全或发布兼容性，必须停止扩张修改范围，向用户说明并升级为完整流程。
- 不使用完整 Superpowers 不等于降低质量：所有修改仍必须保持最小 diff、不回滚无关改动、查看最终差异、运行与风险匹配的验证，并明确说明修改文件和验证结果。

## 版本与在线更新规则

- `2026.7.19.106` 是当前标准安装器基线；新电脑只分发 `Hourlyreport_automation_setup_v2026.7.19.106.exe`，不再要求先解压旧版再覆盖更新包。
- 在线版本号固定为 `发布年.月.日.永久累计序号`，累计序号从 `100` 起并跨日期永久递增，不得按天归零。
- 示例：`2026.7.15.101` 的下一次发布若发生在 2026-07-16，版本号必须是 `2026.7.16.102`；同日再次发布则为 `2026.7.16.103`。
- GitHub Release 仓库固定为 `179068898-dotcom/Hourlyreport-Automation`，tag 使用 `v<版本号>`，在线更新 ZIP 使用 `Hourlyreport_automation_v<版本号>.zip`。
- 每次发布必须同时生成一份与版本号对应的中文更新说明，至少列出用户可感知改动、稳定性修复和兼容性注意事项，供 GitHub Release 正文直接复制使用。
- 发布前必须用上一正式版本号验证最新 Release 元数据可被更新器识别；只看到 GitHub 页面存在资源不算完成验证。
- 104 及后续版本只访问新仓库；现有 104/105 可以在线升级，但新部署统一从 106 标准安装器开始。
- 在线更新包只能包含程序文件，不得覆盖 `configs/`、`secrets/`、日志、报告、备份、快商通导出目录或浏览器数据。
- `.baidu-secrets` 是包含完整账号密码和 OAuth Token 的明文授权配置包，禁止提交 Git、写入日志或打入任何发布包。
- 普通包、内部包和在线更新包都不得包含 `secrets/secrets.json`；真实凭据只能通过独立 `.baidu-secrets` 配置包传递。
- 桌面主程序统一命名为 `hourlyreport_automation.exe`，不再生成旧中文 EXE 副本。
- 完整安装器使用 Inno Setup 构建，必须允许选择安装目录、创建快捷方式，并在重复安装时保留已有 `configs/`、`secrets/`、日志、报告和备份。

## 百度 API 开发边界

- 服务商应用 `openBD` 已审核通过，九个项目、十一个授权已导入。正式发布前必须显式运行只读验收：`.venv\Scripts\python.exe main.py --mode test-baidu-api-readiness`。
- 生产任务统一读取应用级 `baidu_data_source_preference`。缺失或无效时按 `api`；`A` / `api` 表示 API 优先，`B` / `browser` 表示强制浏览器。
- `A` 模式默认先走 API；配置、授权、Token、网络或完整性失败时，先执行有限自修复，再自动整项目降级浏览器。`B` 模式不得发起 API 请求，是生产异常时的紧急回退入口。
- 项目 JSON 中的 `api_profile` 只负责授权映射；旧 `data_source_mode`、`api_shadow`、`api_preferred` 仅保留给兼容测试和显式开发入口，不再决定普通生产任务的有效通道。
- API 主通道先执行有限自修复：Token 最多刷新一次，网络错误最多额外重试两次，完整性错误最多额外读取一次，总预算 20 秒；仍失败时自动降级现有浏览器抓数。
- API 与浏览器均失败时必须停止，不得继续解析、合并或写 Excel。
- 百度应用 secretKey 只允许保存在腾讯云 SCF 环境变量；桌面端只保存独立 HMAC 客户端密钥和 OAuth Token，日志、报告不得包含任何令牌或密钥。
- `test-baidu-api`、`test-baidu-api-readiness`、`simulate-baidu-api-hourly` 和 OAuth 导入属于显式开发入口，普通 GUI 不得自动调用。
- `test-baidu-api-readiness` 只读百度数据，不读写 Excel，也不启动 Chrome。Token 过期时允许按生产自修复规则备份并原子更新 `secrets/secrets.json`；原文件及备份均为敏感文件，不得提交、打包或写入日志。
- OAuth 自动匹配优先要求推广 ID 集合完全一致；超管包含停用户时，仅允许授权集合完整覆盖单一项目/来源的唯一超集匹配，并必须报告被忽略 ID。若同时覆盖多个候选，必须拒绝导入。
- 沈阳牛、沈阳白必须两路 API 全部成功后才合并；任一路失败或合并校验异常时，丢弃本次 API 临时结果并整项目降级浏览器，禁止混合 API 与浏览器的部分数据。
- 多项目并行尚未投入生产；不得因为全局 API 模式而提前启用多项目并行。

## 固定运行入口

普通用户优先运行菜单：

```cmd
.venv\Scripts\python.exe menu.py
```

HERMES（夏思道）/ 自动代执行必须走 2026-07-10 更新的固定 BAT 入口，不要绕过 BAT 自己拼 `main.py`：

```cmd
run_hermes_hourly.bat 11点
run_hermes_hourly.bat 15点
run_hermes_hourly.bat 18点
run_hermes_daily.bat
run_hermes_daily.bat 2026-07-09
```

固定窗口规则：

- 小时报窗口标题应为 `HERMES Hourly - fixed entry - 20260710`。
- 日报窗口标题应为 `HERMES Daily - fixed entry - 20260710`。
- BAT 会固定工作目录、UTF-8 环境和 `.venv` Python。
- BAT 会先跑 preflight，失败则停止，不得继续写 Excel。
- 不要自行拆分 `fetch/parse/merge/write` 去代替完整任务。
- 失败后不要手工补 Excel 数字。

## Preflight 规则

HERMES 默认使用快速预检以减少多项目排队耗时：

```cmd
.venv\Scripts\python.exe main.py --mode preflight --quick
.venv\Scripts\python.exe main.py --mode preflight --task daily --quick
```

快速预检会检查：

- 项目根目录。
- `A` / API 模式的 preflight 不提前启动 Chrome；只有 API 最终失败、实际降级时才延迟启动并检查项目专用调试 Chrome。
- `B` / 强制浏览器模式继续检查 Chrome 9222；未启动时会自动尝试启动项目专用调试 Chrome。
- 当前项目配置是否合法。
- Excel 路径是否存在。
- 快商通导出目录是否存在。
- `secrets/secrets.json` 是否是合法 JSON。
- 当前项目所需 `credential_profile` 是否存在，且 `username` / `password` 非空。

快速预检会跳过耗时的 Excel sheet 结构扫描。完整预检仍保留：

```cmd
.venv\Scripts\python.exe main.py --mode preflight
.venv\Scripts\python.exe main.py --mode preflight --task daily
```

完整预检只用于新项目上线、Excel 模板变更、结构识别异常或排障。

## Chrome 与登录态规则

默认只连接 Chrome 调试端口：

```cmd
http://127.0.0.1:9222
```

优先使用：

```python
chromium.connect_over_cdp("http://127.0.0.1:9222")
```

禁止默认启动 Edge。`connect_existing` 模式下不要另起普通 Chrome。Chrome 连接失败时，提示人工先运行：

```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --profile-directory="Default" https://cc.baidu.com/report
```

`start_chrome_debug.bat` 用于人工准备项目专用调试 Chrome。`B` 模式的 preflight / run 会先复用 9222；`A` 模式仅在实际降级时延迟执行同一套 Chrome 就绪逻辑。不要关闭老 Chrome。

静默规则：

- 自动切换百度账号、自动清 cookie、自动 CAS 登录不应把 Chrome 抢到前台。
- 只有验证码、安全校验、滑块或人工确认等确实需要人工介入的场景，才显示 Chrome。
- 旧百度账号退出失败时，程序应降级为清理当前上下文 cookie / storage / 本地登录状态，再跳 CAS 登录当前项目账号。
- 不要手动删除 `browser_profile/chrome_debug` 作为常规处理；只有明确排障时才允许人工清理。

## 百度日报数据稳定性

日报抓取不能把“DOM 元素出现”当成“数据已加载完成”。

`fetch-baidu-daily` 必须等表格快照稳定后才允许输出可写入数据：

- 连续两次读取的账号指标签名一致。
- 读取后做基础完整性校验。
- 能识别“总计-N”行时，必须校验总计展现、点击、消费与账户求和一致。
- `networkidle` 超时后不得静默使用早期残值。
- 数据不稳定时必须中断，写入错误报告，不得继续写 Excel。

遇到“百度日报表格数据未稳定”，正确处理方式是等待页面/API 加载稳定后整次重跑，不手工补 Excel。

## 快商通数据规则

当前不走 API，不读网页，不读桌面控件，不做 OCR，不自动操作快商通软件。

快商通数据只从用户手动导出的 Excel/CSV 文件读取，文件放入 `kst_exports/`，或通过 `--file` 指定。

小时报：

```cmd
.venv\Scripts\python.exe main.py --mode parse-kst-export --period 15点 --file "导出文件路径"
.venv\Scripts\python.exe main.py --mode parse-kst-export --period 15点
```

日报：

```cmd
.venv\Scripts\python.exe main.py --mode parse-kst-daily --date 2026-05-26 --file "导出文件路径"
```

字段识别必须通过表头，不允许写死列号。无法归属账户的行必须输出到报告，不得静默丢弃。

## 日报独立流程

日报不得破坏小时报 `run` 流程。日报阶段如下：

```cmd
.venv\Scripts\python.exe main.py --mode inspect-daily-excel
.venv\Scripts\python.exe main.py --mode fetch-baidu-daily --date 2026-05-26
.venv\Scripts\python.exe main.py --mode parse-kst-daily --date 2026-05-26 --file "导出文件路径"
.venv\Scripts\python.exe main.py --mode merge-daily --date 2026-05-26
.venv\Scripts\python.exe main.py --mode write-daily --date 2026-05-26
.venv\Scripts\python.exe main.py --mode run-daily --date 2026-05-26 --yes
```

`run-daily` 不传 `--date` 时默认处理昨天。

## 小时报流程

小时报常用阶段如下：

```cmd
.venv\Scripts\python.exe main.py --mode inspect-excel
.venv\Scripts\python.exe main.py --mode fetch-baidu-auto --period 15点
.venv\Scripts\python.exe main.py --mode parse-kst-export --period 15点 --file "导出文件路径"
.venv\Scripts\python.exe main.py --mode merge-data
.venv\Scripts\python.exe main.py --mode write-excel --period 15点
.venv\Scripts\python.exe main.py --mode run --period 15点 --yes
```

## 输出与诊断

所有阶段必须尽量输出：

- `logs/run.log`
- `reports/*.json`
- 必要时输出 `reports/sheet_text_dump.csv`
- 必要时输出页面 debug HTML 或截图，但当前业务流程不做自动截图发送

重要报告包括：

- `reports/preflight_report.json`
- `reports/final_run_report.json`
- `reports/daily_final_run_report.json`
- `reports/baidu_account_data.json`
- `reports/baidu_daily_data.json`
- `reports/write_report.json`
- `reports/daily_write_report.json`

## 测试与验证

修改代码后优先运行相关测试；改动跨模块或入口时运行全量基础测试：

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py
```

文档或 BAT 入口变更也要确认对应测试断言。不得在未验证时声称已修复。

## 文档同步

修改固定入口、Chrome 策略、preflight、日报稳定性或 HERMES 执行方式时，至少同步检查这些文件：

- `AGENTS.md`
- `CLAUDE.md`
- `xia_sidao使用说明.md`
- `docs/hermes_hourly_sop.md`
- `docs/hermes_daily_sop.md`
- `run_hermes_hourly.bat`
- `run_hermes_daily.bat`

如果只改其中一处，必须说明为什么其他文件无需同步。

## 禁止行为清单

- 禁止自动启动 Edge。
- 禁止在 `connect_existing` 模式下另起普通 Chrome。
- 禁止关闭老 Chrome 后新开普通 Chrome 来跑任务。
- 禁止用绝对屏幕坐标操作百度页面。
- 禁止猜测 Excel 单元格坐标写入。
- 禁止重建目标 Excel。
- 禁止修改无关 sheet、公式区、汇总区、截图区。
- 禁止跳过备份直接写 Excel。
- 禁止失败后手工补 Excel 数字。
- 禁止把真实账号密码写入文档、日志、测试或示例。
- 禁止提交 `secrets/secrets.json`、本机账号密码、个人导出数据。
