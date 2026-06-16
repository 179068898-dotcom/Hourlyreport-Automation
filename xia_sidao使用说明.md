# 夏思道使用说明书

版本：`v1.0 内部发布版`

适用对象：负责代执行百度竞价日报/小时报的夏思道、OpenClaw 或内部同事。

本说明仅记录当前可执行流程。命令、项目和安全规则以当前发布包内容为准。

## 1. 当前能力

本工具读取百度营销后台的展现、点击、消费数据，读取人工导出的商务通 Excel/CSV 转化数据，合并后写入各项目 Excel。

- 小时报：写入 `时段数据` sheet，时段为 `11点`、`15点`、`18点`。
- 日报：写入 `百度` sheet；不指定日期时默认处理昨天。
- 人工入口：Rich 控制台菜单 `run_menu.bat`。
- 自动执行入口：固定 BAT 命令，不依赖菜单布局或菜单名称。
- 当前支持十个正式项目：昆明牛、南京牛、宁波牛、长沙牛、沈阳牛、合肥白、青岛白、深圳白、南京白、沈阳白。
- 双百度来源项目：沈阳牛、合肥白、沈阳白；任一来源读取失败时，不继续写入 Excel。

当前版本不做 QQ、不做截图、不自动发送消息，不从商务通网页或客户端自动取数。

## 2. 不可违反的规则

1. 商务通数据只能读取人工导出的文件。
2. 目标 Excel 写入前必须关闭 WPS/Excel。
3. 小时报和日报均在写入前先备份目标 Excel。
4. 写入仅落在已识别的目标字段与账户区域，不修改无关 sheet、汇总区域、截图区域或公式区域。
5. 写入保存后，从本次写入前备份恢复目标 sheet 的筛选/保护元数据，防止 Excel/WPS 的筛选按钮失效。
6. Excel 表结构不能识别时立即停止，不猜测单元格位置。
7. 百度使用本机已配置凭据与 Chrome 登录态，不向用户索要真实密码，不输出或提交 secrets。
8. OpenClaw 自动执行必须调用固定 BAT 入口，不通过点击 Rich 菜单完成自动任务。
9. Chrome 自动化默认使用项目专用调试目录静默最小化运行；自动切换账号、自动清 cookie、自动 CAS 登录不应抢前台，只有验证码、安全校验、滑块或人工确认等确实需要人工介入的场景才显示窗口。

## 3. 执行前检查

| 检查项 | 要求 | 不通过时处理 |
|---|---|---|
| 当前项目 | 与本次任务一致 | 人工通过菜单切换项目后再执行 |
| Chrome | 调试端口 `9222` 可连接，未启动时自动准备项目专用调试 Chrome | 自动准备失败时再运行 `start_chrome_debug.bat` 排障 |
| 百度状态 | 当前项目凭据完整，可进入后台 | 停止并报告本地条件项异常 |
| 商务通文件 | 已人工导出正确项目、日期/时段的数据 | 等待导出文件 |
| 目标 Excel | 文件存在且未被打开 | 关闭文件后重试 |
| 任务时间 | 小时报已到对应时段；日报日期明确 | 不提前执行或猜日期 |

人工入口首页可选择 `4. 检查条件项` 查看状态。OpenClaw 调用 BAT 时会先运行预检，预检失败就停止。

### 3.1 Chrome 静默自动化说明

- 调试 Chrome 使用项目专用目录 `browser_profile/chrome_debug`，不使用同事日常 Chrome 的个人资料目录。
- preflight / run 会先复用 `9222`；未就绪时自动以最小化方式启动项目专用调试 Chrome。`start_chrome_debug.bat` 仅作为人工排障入口，不会关闭老 Chrome，通常不需要关闭日常 Chrome。
- 自动拉起调试 Chrome 时，不把百度 URL 直接作为 Chrome 启动参数传入，避免启动失败时 URL 被日常 Chrome 接管开新标签。
- 自动读取百度数据时，程序默认不把 Chrome 抢到前台，也不会在连接后用 CDP 强制最小化窗口；窗口状态主要依赖启动时的 `--start-minimized`。
- 自动切换百度账号时，程序会先尝试页面退出；如果百度页面 dropdown 没弹出导致退出失败，会自动清理当前浏览器上下文 cookie / storage / 本地登录状态，再跳 CAS 登录当前项目账号。
- 遇到验证码、安全校验、滑块或人工确认时，程序才会显示 Chrome 窗口并等待人工处理。
- Chrome 保存密码提示已通过启动参数和 profile 偏好禁用；不要尝试通过页面脚本点击浏览器气泡。
- 如果旧调试 profile 仍残留保存密码提示状态，可先关闭调试 Chrome，再清理 `browser_profile/chrome_debug` 后重新运行 `start_chrome_debug.bat`。

## 4. 人工菜单

双击执行：

```cmd
run_menu.bat
```

首次运行时会自动安装或修复运行环境。Rich 控制台首页主入口固定为：

```text
1. 小时报
2. 日报
3. 切换项目
4. 检查条件项
5. 更多功能
0. 退出

R. 刷新状态
```

首页用于同事操作与查看状态；更多诊断入口位于 `5. 更多功能`。

## 5. OpenClaw 执行命令与固定入口

菜单布局调整不影响 OpenClaw 固定入口。自动执行只使用下列命令。OpenClaw 必须继续走 `run_openclaw_hourly.bat` / `run_openclaw_daily.bat` 专用窗口，不要绕过 BAT 自己拼 `main.py`，不要跳过 preflight，不要在失败后手工补 Excel 数字。

OpenClaw 专用 BAT 默认执行快速预检：小时报使用 `main.py --mode preflight --quick`，日报使用 `main.py --mode preflight --task daily --quick`。快速预检跳过耗时的 Excel sheet 结构扫描，只保留路径、Chrome、项目配置、商务通目录和凭据等低成本检查；如果 9222 未启动，会自动尝试启动项目专用调试 Chrome；完整 preflight 仅用于新项目、Excel 模板变更、结构识别异常或排障。

进入项目目录：

```cmd
cd /d D:\自动化脚本\hourly_report_bot_release_v2.0
```

### 5.1 小时报

```cmd
run_openclaw_hourly.bat 11点
run_openclaw_hourly.bat 15点
run_openclaw_hourly.bat 18点
```

该入口先执行小时报预检，通过后才执行对应时段的完整流程。
专用窗口标题应显示 `OpenClaw Hourly - fixed entry`，窗口会输出固定入口提示、当前工作目录和 preflight 结果。

### 5.2 日报

```cmd
run_openclaw_daily.bat
run_openclaw_daily.bat 2026-05-26
```

- 不带日期：处理昨天。
- 带日期：处理指定日期。
- 该入口先执行日报预检，通过后才执行完整日报。
专用窗口标题应显示 `OpenClaw Daily - fixed entry`，窗口会输出固定入口提示、当前工作目录和 preflight 结果。

OpenClaw 不得绕过预检直接启动完整写入任务，不得在失败后手工补 Excel 数字。

## 6. 标准操作流程

### 6.1 小时报 SOP

1. 确认当前项目与目标时段。
2. 确认商务通已导出该时段对应文件。
3. 确认目标 Excel 已关闭。
4. 通过人工菜单运行小时报，或通过固定 BAT 执行对应时段。
5. 完成后核对写入报告、运行日志和 Excel 对应日期/时段行。

输出重点：

```text
reports/final_run_report.json
reports/write_report.json
logs/run.log
```

### 6.2 日报 SOP

1. 确认当前项目和目标日期；通常处理昨天。
2. 确认商务通已导出对应日期文件。
3. 确认目标 Excel 已关闭。
4. 通过人工菜单运行日报，或通过固定 BAT 执行日报。
5. 完成后核对写入报告、运行日志和 `百度` sheet 对应日期行。

输出重点：

```text
reports/daily_final_run_report.json
reports/daily_write_report.json
logs/run.log
```

日报写入范围由程序限定，不写入预约、到诊、就诊等禁止字段。

## 7. 多百度来源项目

| 项目 | 百度来源类型 | Excel 写入账户数量 |
|---|---|---:|
| 沈阳牛 | 多百度来源 x2：沈阳中亚、沈阳银康 | 3 |
| 合肥白 | 多百度来源 x2：合肥华夏、合肥新华夏 | 3 |
| 沈阳白 | 多百度来源 x2：沈阳白来源A、沈阳白来源B | 6 |

执行规则：

1. 每个百度来源分别读取并验证。
2. 仅聚合项目配置中允许写入 Excel 的账户。
3. 任一来源失败时，本次百度步骤失败，不写入部分数据。
4. 需要排查时查看：

```text
reports/baidu_multi_source_report.md
reports/baidu_multi_source_report.json
reports/baidu_account_data.json
reports/baidu_daily_data.json
logs/run.log
```

## 8. 项目一览

| 项目 ID | 项目名 | 来源类型 | Excel 文件名 | 小时报 sheet | 日报 sheet |
|---|---|---|---|---|---|
| `kunming_niu` | 昆明牛 | 单百度来源 | `【昆明npx】2026竞价数据.xlsx` | `时段数据` | `百度` |
| `nanjing_niu` | 南京牛 | 单百度来源 | `【南京华厦yxb】2026竞价数据.xlsx` | `时段数据` | `百度` |
| `ningbo_niu` | 宁波牛 | 单百度来源 | `【宁波YXB】2026竞价数据.xlsx` | `时段数据` | `百度` |
| `changsha_niu` | 长沙牛 | 单百度来源 | `【长沙】2026竞价数据.xlsx` | `时段数据` | `百度` |
| `shenyang_niu` | 沈阳牛 | 多百度来源 x2 | `【沈阳YXB】2026竞价数据.xlsx` | `时段数据` | `百度` |
| `hefei_bai` | 合肥白 | 多百度来源 x2 | `【合肥】2026竞价数据.xlsx` | `时段数据` | `百度` |
| `qingdao_bai` | 青岛白 | 单百度来源 | `【青岛白】2026竞价数据.xlsx` | `时段数据` | `百度` |
| `shenzhen_bai` | 深圳白 | 单百度来源 | `【深圳白】2026竞价数据.xlsx` | `时段数据` | `百度` |
| `nanjing_bai` | 南京白 | 单百度来源 | `【南京白】2026竞价数据.xlsx` | `时段数据` | `百度` |
| `shenyang_bai` | 沈阳白 | 多百度来源 x2 | `【沈阳白】2026竞价数据.xlsx` | `时段数据` | `百度` |

完整路径与账户映射以 `configs/projects/*.json` 为准。不得在说明书中记录真实密码。

## 9. 检查与诊断命令参数表

日常执行优先使用菜单或固定 BAT。以下命令仅用于检查或明确的分步排查。

```cmd
.venv\Scripts\python.exe main.py --mode doctor
.venv\Scripts\python.exe main.py --mode validate-project
.venv\Scripts\python.exe main.py --mode list-projects
.venv\Scripts\python.exe main.py --mode show-project
.venv\Scripts\python.exe main.py --mode inspect-excel
.venv\Scripts\python.exe main.py --mode inspect-daily-excel
.venv\Scripts\python.exe main.py --mode test-baidu-credentials
```

分步诊断：

```cmd
.venv\Scripts\python.exe main.py --mode fetch-baidu-auto --period 15点
.venv\Scripts\python.exe main.py --mode parse-kst-export --period 15点
.venv\Scripts\python.exe main.py --mode fetch-baidu-daily --date 2026-05-26
.venv\Scripts\python.exe main.py --mode parse-kst-daily --date 2026-05-26
```

未经明确确认，不应直接使用写入类分步命令。

## 10. Excel 写入与筛选保护

小时报与日报都遵守同一写入保护顺序：

1. 识别目标工作表结构与允许写入区域。
2. 在写入前创建原 Excel 备份。
3. 仅写入目标字段。
4. 保存 Excel。
5. 从本次写入前备份恢复目标 sheet 的筛选/保护元数据。
6. 回读验证写入值并输出报告。

筛选按钮说明：

- 程序会保留写入前已有的筛选状态与范围。
- 若写入前的原文件本身已没有正确筛选元数据，程序不会猜测历史范围，应从确认正常的历史备份人工恢复后再继续执行。
- 写入报告中的 `filter_ui_metadata_restored` 用于确认本次元数据恢复步骤是否执行成功。

## 11. 输出与验证标准

### 小时报验证标准

- 最终报告显示流程通过。
- `write_report.json` 显示已创建备份并通过写入复核。
- Excel 对应日期、对应时段的数据已写入。
- Excel 原有筛选按钮仍可使用。

### 日报验证标准

- 最终报告显示流程通过。
- `daily_write_report.json` 显示已创建备份并通过写入复核。
- Excel `百度` sheet 对应日期的数据已写入。
- Excel 原有筛选按钮仍可使用。
- 不出现禁止写入字段被程序填写的情况。

## 12. 常见问题

| 现象 | 处理方式 |
|---|---|
| 当前项目不正确 | 使用 `3. 切换项目` 切换后重新检查条件项 |
| Chrome `9222` 无法连接 | preflight 会自动准备项目专用调试 Chrome；若仍失败，再运行 `start_chrome_debug.bat` 排障并重新预检 |
| Chrome 自动化窗口打断当前操作 | 确认配置保持 `silent_automation=true`、`window_state=minimized`，并通过 `start_chrome_debug.bat` 启动 |
| Chrome 提示是否保存账号密码 | 调试 profile 默认禁用密码管理器；如旧状态残留，关闭调试 Chrome 后清理 `browser_profile/chrome_debug` 再重启 |
| 旧百度账号自动退出失败 | 程序会自动清 cookie 后重登；仍失败时查看 `reports/baidu_session_check_report.json` 和 `logs/run.log`，不要手工补 Excel |
| 百度需要验证码或安全校验 | 停止自动执行，等待人工处理 |
| 商务通文件找不到 | 先人工导出正确日期/时段文件 |
| Excel 写入失败 | 关闭 WPS/Excel 中打开的目标文件后重跑 |
| 多百度来源任一来源失败 | 查看多来源报告，修正后整次重跑，不写部分结果 |
| 百度日报表格数据未稳定 | 程序已阻止写入，等待页面/API 加载稳定后整次重跑，不手工补 Excel |
| Excel 筛选按钮异常 | 停止继续覆盖写入，查看写入前备份及写入报告 |
| 结构识别失败 | 查看结构报告，不猜测单元格写入 |

## 13. 禁止事项

- 不操作 QQ，不截图，不自动发送消息。
- 不通过网页或桌面控件自动读取商务通。
- 不手工编造百度或商务通数据。
- 不在 Excel 打开状态下强行写入。
- 不修改无关 sheet、汇总区域、截图区域或公式区域。
- 不将 secrets、运行报告、日志、备份或本地项目选择状态提交到代码仓库。
- 不向用户索要百度账号密码，不在消息或文档中泄露凭据。

## 14. 相关文档

```text
README_同事使用说明.md
docs/openclaw_hourly_sop.md
docs/openclaw_daily_sop.md
docs/multi_source_project_config.md
docs/Excel识别与写入规则.md
```
