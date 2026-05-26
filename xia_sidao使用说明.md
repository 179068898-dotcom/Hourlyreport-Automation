# 夏思道脚本操作手册

## 1. 系统概述：1 分钟搞懂

一句话：自动读取百度消费、展现、点击，解析商务通导出文件，合并后写入对应项目 Excel。

- 当前版本：`v0.4.21 内部修复版（含沈阳双百度来源日报、自动安装修复与商务通表头兼容）`
- 项目路径：`D:\自动化脚本\hourly_report_bot_release_v0.4.4`
- 核心依赖：
  - Python 虚拟环境：`.venv`
  - Chrome 调试端口：`9222`
  - 百度营销后台登录态
  - 商务通导出文件
  - 各项目目标 Excel
  - `configs/projects/*.json` 项目配置
- 支持任务：
  - 小时报：`11点`、`15点`、`18点`
  - 日报：默认昨天，也可指定日期
  - 沈阳牛双百度来源：小时报和日报均会依次读取沈阳中亚、沈阳银康并聚合后写入
  - 文件合格校验 / `doctor`
  - 项目切换 / 项目查看
  - Excel 结构扫描
  - 百度退出诊断

## 2. 执行前检查清单

| 序号 | 检查项 | 判定标准 | 不通过怎么办 |
|---|---|---|---|
| 1 | Chrome 调试端口 `9222` | 已启动，可连接 | 运行 `start_chrome_debug.bat`，或重新打开 Chrome 调试模式 |
| 2 | 当前项目是否正确 | `configs/app_config.json` 的 `default_project_id` 是目标项目 | 用菜单切换项目，或按配置规则修改 `default_project_id` |
| 3 | 商务通数据是否已导出 | 对应项目 `kst.export_dir` 下有最新导出文件 | 先让人工从商务通导出，不要自己乱找文件 |
| 4 | 目标 Excel 是否关闭 | WPS / Excel 没有打开目标文件 | 关闭目标 Excel 后重跑 |
| 5 | 百度账号是否匹配项目 | 程序会自动判断；账号不匹配会尝试退出重登 | 若提示无法自动退出旧账号，需要人工手动退出后重试 |
| 6 | 当前时段是否可执行 | 日报通常做昨天；小时报只做已经到点的时段 | 不要提前跑未来时段 |

## 2.1 OpenClaw 定时任务同步记录

以下是给 OpenClaw 执行小时报自动化定时任务时需要同步的局部行为变化：

1. Chrome 调试浏览器首次打开页已改为 CAS 登录页。
   - 默认启动 URL：`https://cas.baidu.com/?tpl=www2&fromu=https%3A%2F%2Fcc.baidu.com%2Freport`
   - 影响入口：`start_chrome_debug.bat`、自动启动调试 Chrome、连接已有 Chrome 时新建百度页。
   - 目的：绕过 `yingxiao.baidu.com` / `qingge.baidu.com` 再点击登录的等待，首次未登录时直接进入账号密码页。
   - 注意：如果项目配置里显式写了 `browser.startup_url` 或 `baidu.start_url`，仍按配置优先；不要误判为代码未生效。

2. 日报登录守卫已恢复，但流程已去重。
   - 现在顺序是：先确认当前 Chrome 是否为本项目百度账号，再进入 `cc.baidu.com/report`。
   - 如果进入 report 后跳到 CAS 登录页，才自动登录并重试一次 report。
   - 后续“搜索推广”检查不再重复调用 `_goto_report_page`，避免日期筛选前页面被重新打开导致流程断裂。
   - 这主要影响日报；小时报仍按原一键流执行。

3. Excel 写入后会恢复筛选/保护 UI 元数据。
   - 小时报和日报写入前仍会先备份 Excel。
   - 写入保存后会从备份恢复目标 sheet 的筛选/保护元数据，避免 openpyxl 保存后让 WPS/Excel 的筛选状态异常。
   - 这一步不改单元格值、公式和无关 sheet；如果恢复失败，会写入报告字段 `filter_ui_metadata_restored=false`，需要人工检查目标 Excel。

4. `inspect-excel` 已修复局部导入导致的终端退出错误。
   - OpenClaw 定时任务异常时，可以先跑：
     ` .venv\Scripts\python.exe main.py --mode inspect-excel`
   - 该命令只识别结构，不写入 Excel。

5. 沈阳牛现已支持双百度来源的小时报和日报。
   - `shenyang_niu` 会分别使用 `shenyang_niu_zhongya_baidu`、`shenyang_niu_yinkang_baidu` 登录读取，然后只聚合 Excel 实际账户。
   - 日报最终百度输入文件仍为 `reports/baidu_daily_data.json`，不会改变 `merge-daily` 和 Excel 写入入口。
   - 任一来源读取失败时，百度步骤立即失败，日报不会继续写 Excel。
   - 未知账户、候选未启用账户及候选有量但未映射账户可在 `reports/baidu_multi_source_report.json` / `.md` 中按来源排查。

6. 内部包首次运行入口已改为自动安装和自动修复依赖。
   - 同事直接双击 `run_menu.bat` 即可；没有 `.venv` 或核心依赖不完整时，会先调用 `install_env.bat`。
   - 内置项目全部使用 `openpyxl`，默认安装不再要求 `xlwings` / `pywin32`，避免 Python 3.14 环境因 Excel COM 备用依赖失败而无法打开菜单。
   - `xlwings` / `pywin32` 仅在未来将项目配置为 `excel_com` 时按 `requirements-excel-com.txt` 单独安装。

7. 商务通导出文件已兼容 `访客发送消息数` 与 `访客发送数` 表头。
   - 小时报 `parse-kst-export` 与日报 `parse-kst-daily` 均支持 `访客消息数`、`访客发送消息数`、`访客发送数` 三种表头。
   - 三种表头按同一口径统计：字段值 `>= 1` 才计入总对话及其标签分类。
   - 如果三种表头都未识别，程序仍会中断并输出解析报告，不猜测写入。

## 2.2 多百度来源项目操作 SOP

适用于沈阳牛，以及以后使用 `baidu_sources` 配置的沈阳白、合肥白等项目。

1. 先跑 `doctor`，确认项目配置、Excel、商务通目录、百度凭据 profile 和浏览器状态可用。
2. 查看当前项目配置中的 `baidu_sources` 数量，确认应读取的百度来源完整。
3. 确认 `excel_accounts` 是目标 Excel 中实际存在、允许写入的账户，不要把全部百度候选账户直接当成写入账户。
4. 先跑 `fetch-baidu-auto`，只抓取百度数据并输出诊断报告，不要直接写 Excel。
5. 检查 `reports/baidu_multi_source_report.md`，确认每个来源读取成功，并核对被忽略、被跳过或 unknown 的候选账户。
6. 检查 `reports/baidu_account_data.json`，确认小时报聚合结果只包含 Excel 实际写入账户。
7. 百度抓数结果确认无误后，再运行完整小时报流程写入 Excel。
8. 日报同理：先确认多来源读取及 `reports/baidu_daily_data.json`，再执行完整日报流程。
9. 出错时优先查看以下文件，不要手工补数据或绕过失败步骤：

```text
reports/baidu_multi_source_report.md
reports/baidu_multi_source_report.json
reports/baidu_account_data.json
logs/run.log
```

说明：候选账户展现、点击、消费全为 `0` 且不属于 Excel 写入范围时，会记录为 `ignored_inactive_accounts`；存在数据但不写入 Excel 时，会记录为 `skipped_unmapped_accounts`，必须人工核对。百度账户名必须完整匹配，禁止模糊匹配。

## 2.3 OpenClaw 小时报自动执行规范

OpenClaw 执行小时报必须优先使用 `run_openclaw_hourly.bat 11点|15点|18点`，由脚本先固定目录与 UTF-8 环境，再运行 `preflight`，通过后才执行小时报。不得直接在 CAS 登录页向用户索要百度密码，也不得用 ANSI/GBK 覆盖写回中文配置或说明文件。

完整执行手册见：`docs/openclaw_hourly_sop.md`。

## 3. 完整命令速查表

以下内容就是夏思道日常最常用的执行命令速查表，也可以视为命令行参数表。

所有命令都先进入项目目录：

```cmd
cd /d D:\自动化脚本\hourly_report_bot_release_v0.4.4
```

### 3.1 诊断命令

```cmd
.venv\Scripts\python.exe main.py --mode doctor
```

说明：全量环境自检，检查 Chrome、项目配置、Excel 路径、sheet、快商通目录等。

```cmd
.venv\Scripts\python.exe main.py --mode validate-project
```

说明：校验当前项目配置是否完整。

```cmd
.venv\Scripts\python.exe main.py --mode list-projects
```

说明：列出当前内置项目。

```cmd
.venv\Scripts\python.exe main.py --mode show-project
```

说明：查看当前项目详情。

```cmd
.venv\Scripts\python.exe main.py --mode inspect-excel
```

说明：扫描当前项目小时报 Excel 结构。

```cmd
.venv\Scripts\python.exe main.py --mode inspect-daily-excel
```

说明：扫描当前项目日报 Excel 结构。

```cmd
.venv\Scripts\python.exe main.py --mode test-baidu-logout
```

说明：手动打开百度搜索推广页并保持登录后，用它诊断是否能自动退出百度账号。

### 3.2 小时报一键流

```cmd
.venv\Scripts\python.exe main.py --mode run --period 11点 --yes
```

说明：执行 `11点` 小时报。

```cmd
.venv\Scripts\python.exe main.py --mode run --period 15点 --yes
```

说明：执行 `15点` 小时报。

```cmd
.venv\Scripts\python.exe main.py --mode run --period 18点 --yes
```

说明：执行 `18点` 小时报。

```cmd
.venv\Scripts\python.exe main.py --mode run --period 15点 --file "D:\某个商务通导出文件.xlsx" --yes
```

说明：当自动识别最新商务通导出文件不准确时，用 `--file` 指定。

### 3.3 日报一键流

```cmd
.venv\Scripts\python.exe main.py --mode run-daily
```

说明：默认执行昨天日报。

```cmd
.venv\Scripts\python.exe main.py --mode run-daily --date 2026-05-14
```

说明：执行指定日期日报。

```cmd
.venv\Scripts\python.exe main.py --mode run-daily --date 2026-05-14 --yes
```

说明：命令行接受该参数；当前日报流程本身没有运行前确认，因此加不加 `--yes` 结果一致，可统一保留。

### 3.4 菜单入口

```cmd
run_menu.bat
```

说明：人工操作时用菜单入口；首次运行或依赖安装不完整时，该入口会自动安装/修复环境后再打开菜单。AI / 夏思道自动执行时优先用命令行。

### 3.5 分步调试

当前版本支持以下分步命令。

小时报分步：

```cmd
.venv\Scripts\python.exe main.py --mode fetch-baidu-auto --period 15点
.venv\Scripts\python.exe main.py --mode parse-kst-export --period 15点
.venv\Scripts\python.exe main.py --mode merge-data --period 15点
.venv\Scripts\python.exe main.py --mode write-excel --period 15点
```

日报分步：

```cmd
.venv\Scripts\python.exe main.py --mode fetch-baidu-daily --date 2026-05-14
.venv\Scripts\python.exe main.py --mode parse-kst-daily --date 2026-05-14
.venv\Scripts\python.exe main.py --mode merge-daily --date 2026-05-14
.venv\Scripts\python.exe main.py --mode write-daily --date 2026-05-14
```

## 4. 日报 SOP

1. 确认 Chrome `9222` 已启动。
2. 确认当前项目正确。
3. 确认目标 Excel 已关闭。
4. 进入项目目录：

```cmd
cd /d D:\自动化脚本\hourly_report_bot_release_v0.4.4
```

5. 执行日报：

```cmd
.venv\Scripts\python.exe main.py --mode run-daily --yes
```

6. 等待程序完成。
7. 确认终端显示通过，Excel 自动弹出或目标文件已保存。
8. 查看 `reports/daily_final_run_report.json` 和 `logs/run.log` 是否显示成功。
9. 记录三个账户消费合计。
10. 告知姜老师消费总数，询问当天到诊数。
11. 如果存在外部脚本 `D:\xia_sidao\tools\fill_daily_visit.py`，则执行：

```cmd
python D:\xia_sidao\tools\fill_daily_visit.py <总消费> <到诊数>
```

说明：这是外部工具，不是本项目内置脚本，需确认存在后再执行。

12. 在 `memory/当天日期.md` 或用户指定记录位置，记录日报结果。
13. 如果姜老师未给到诊数，不要乱填，先等待确认。

## 5. 小时报 SOP

1. 确认 Chrome `9222` 已启动。
2. 确认当前项目正确。
3. 确认商务通已导出最新文件。
4. 确认目标 Excel 已关闭。
5. 进入项目目录：

```cmd
cd /d D:\自动化脚本\hourly_report_bot_release_v0.4.4
```

6. 按时段执行：

`11点`

```cmd
.venv\Scripts\python.exe main.py --mode run --period 11点 --yes
```

`15点`

```cmd
.venv\Scripts\python.exe main.py --mode run --period 15点 --yes
```

`18点`

```cmd
.venv\Scripts\python.exe main.py --mode run --period 18点 --yes
```

7. 等待完成。
8. 检查终端是否显示通过。
9. 检查 Excel 对应日期、对应时段是否写入。
10. 如果提示覆盖旧值，确认是用户允许重跑该时段后再执行。
11. 小时报完成后通常无需额外操作。

## 6. 项目配置一览表

| 项目ID | 项目名 | 百度账户 | Excel 文件 | 小时报 sheet | 日报 sheet | 商务通目录 | credential_profile |
|---|---|---|---|---|---|---|---|
| `kunming_niu` | 昆明牛 | `银康01 / 银康银屑02 / baidu-银康03 / 银康03` | `D:\Seafile\【竞价】\【❤昆明牛】\【2026年】【昆明牛】竞价数据\【昆明npx】2026竞价数据.xlsx` | `时段数据` | `百度` | `D:\商务通数据\昆明牛` | `kunming_niu_baidu` |
| `nanjing_niu` | 南京牛 | `华厦npx1 / 华厦npx3 / 华厦npx5` | `D:\Seafile\【竞价】\【❤南京牛】\【2026年】【南京牛】竞价数据\【南京华夏yxb】2026竞价数据.xlsx` | `时段数据` | `百度` | `D:\商务通数据\南京牛` | `nanjing_niu_baidu` |
| `ningbo_niu` | 宁波牛 | `宁波博润1 / 宁波博润2 / 宁波博润12` | `D:\Seafile\【竞价】\【❤宁波牛】\【2026年】【宁波牛】竞价数据\【宁波YXB】2026竞价数据.xlsx` | `时段数据` | `百度` | `D:\商务通数据\宁波牛` | `ningbo_niu_baidu` |
| `changsha_niu` | 长沙牛 | `竞网CS博润241209 / 竞网CS博润240304 / 竞网CS博润251218` | `D:\Seafile\【竞价】\【❤长沙牛】\【2026年】【长沙牛】竞价数据\【长沙】2026竞价数据.xlsx` | `时段数据` | `百度` | `D:\商务通数据\长沙牛` | `changsha_niu_baidu` |
| `shenyang_niu` | 沈阳牛 | Excel 写入：`沈阳中亚02 / 沈阳银康01 / 沈阳中亚01`；双百度来源抓取 | `D:\Seafile\【竞价】\【❤沈阳牛】\【2026年】【沈阳牛】竞价数据\【沈阳YXB】2026竞价数据.xlsx` | `时段数据` | `百度` | `D:\商务通数据\沈阳牛` | `shenyang_niu_zhongya_baidu` / `shenyang_niu_yinkang_baidu` |

说明：`demo_project.json` 和 `project_template.json` 仅用于演示/模板，不属于正式生产项目。

## 7. 切换项目操作

方式 A：菜单切换

```cmd
run_menu.bat
```

然后选择：

`3. 项目列表`

再选择目标项目编号。

方式 B：配置切换

编辑：

`configs/app_config.json`

修改：

`default_project_id`

项目可选值：

- `kunming_niu`
- `nanjing_niu`
- `ningbo_niu`
- `changsha_niu`
- `shenyang_niu`

重要说明：

1. 切换项目后，百度账号也要匹配对应项目。
2. 程序会自动判断右上角百度管家账号。
3. 如果账号不匹配，会尝试自动退出旧账号并登录当前项目账号。
4. 如果自动退出失败，程序会停止并提示手动退出，不会强行进入 CAS。
5. 切换项目后建议先跑：

```cmd
.venv\Scripts\python.exe main.py --mode show-project
.venv\Scripts\python.exe main.py --mode doctor
```

## 8. 常见坑与修复

| 现象 | 常见原因 | 修复方式 |
|---|---|---|
| 默认项目变成宁波牛 / 长沙牛 | 菜单切换项目后 `app_config.json` 改了 `default_project_id` | 切回目标项目；提交代码前不要把 `app_config` 本地状态提交 |
| Chrome `9222` 连接失败 | Chrome 调试端口未启动 | 运行 `start_chrome_debug.bat`，或关闭旧 Chrome 后重启调试 Chrome |
| 首次双击菜单提示缺少 `openpyxl` | 旧包的 `run_menu.bat` 未自动安装，或上次安装中断 | 使用 `v0.4.21` 修复包重新解压后双击 `run_menu.bat`；新包会自动安装或修复环境 |
| 安装时提示找不到 `xlwings` | `v0.4.19` 旧包把 Excel COM 备用依赖当成默认必装项 | 使用 `v0.4.21` 修复包；当前 `openpyxl` 项目默认安装不再安装 `xlwings` |
| 百度账号不匹配 | 当前浏览器登录了其他项目百度管家账号 | 程序会自动退出重登；若提示无法退出，手动退出后重试 |
| 百度 report 页面列解析异常 | 百度虚拟 grid 表格结构变化、列顺序漂移、`visible_text` 错位 | 查看 `reports/baidu_table_parse_debug_latest.json` 和 `reports/baidu_table_candidates_latest.json` |
| 出现“读取 0 个账户 / 读取 1 个账户” | 未正确解析百度 report 表格，或账户名未完整匹配 | 先看 `baidu_table_parse_debug`；不要手动改数据 |
| 点击 / 消费不是数字，`raw_value` 是百分比 | 列错位，把点击率 / 消费占比当成点击 / 消费 | 这是 parser 问题，不要把百分比当数字写入 |
| 商务通导出文件未找到 | 商务通未导出，或导出目录不对 | 让人工导出；必要时用 `--file` 指定导出文件 |
| 商务通提示未识别到访客消息数字段 | 导出表头可能改为 `访客发送消息数` 或 `访客发送数`，或使用了更旧版本程序 | 使用当前修复包重跑；若仍失败，查看 `reports/kst_parse_report.json` 或日报解析报告中的实际表头 |
| 沈阳牛提示某个百度来源失败 | 双来源中任一账号未登录、凭据缺失或页面不可读取 | 检查 `reports/baidu_multi_source_report.json` / `.md` 和 `logs/run.log`；修复后重跑，失败时程序不会写 Excel |
| 沈阳牛出现候选账户已忽略/跳过 | 百度来源含不属于 Excel 实际写入区域的候选账户 | `展点消=0` 的未启用候选可忽略；有量但未映射时必须人工核对配置和 Excel，不要直接改表 |
| Excel 找不到目标文件 | 配置路径与真实文件名不一致 | 看 doctor 提示的相似文件名，核对 `configs/projects/*.json` 的 `excel.path` |
| Excel 打不开 / 写入失败 | WPS / Excel 正在打开目标文件 | 关闭目标 Excel 后重跑 |
| 南京牛小时报找不到账块 | 首航小时报模板没有账户名，日报模板有账户名 | 这是模板适配问题，暂时不要归因百度抓数 |
| 日报到诊数不知道 | 到诊数由姜老师确认 | 日报完成后询问姜老师，不要自己填 |
| 覆盖旧值提示 | 同一日期 / 时段已经写入过 | 确认是重跑覆盖后再继续 |

## 9. 输出验证标准

日报：

- 终端显示成功
- `reports/daily_final_run_report.json` 结果为通过
- 目标 Excel 对应日期已写入
- 消费不为 `0`
- 三个账户有数据
- 有效、无效、一般有效、有效转潜、总转潜字段符合预期
- 预约 / 到诊如规则要求手动填，则不要乱填

小时报：

- 终端显示成功
- 当前时段对应行写入
- 展现 / 点击 / 消费不是空
- 商务通转化字段不是异常 `0`
- Excel 自动保存
- 如果覆盖旧值，`reports/write_report.json` 中能看到覆盖说明

## 10. 日志与回溯

- 运行日志：`logs/run.log`
- 小时报最终报告：`reports/final_run_report.json`
- 日报最终报告：`reports/daily_final_run_report.json`
- 百度抓数报告：
  - `reports/baidu_account_data.json`
  - `reports/baidu_open_overview_report.json`
  - `reports/baidu_prepare_overview_report.json`
  - `reports/baidu_daily_data.json`
  - 多来源项目：`reports/baidu_multi_source_report.json`、`reports/baidu_multi_source_report.md`
- 百度表格解析调试：
  - `reports/baidu_table_parse_debug_latest.json`
  - `reports/baidu_table_candidates_latest.json`
  - `reports/baidu_table_parse_debug_{project_id}_{timestamp}.json`
  - `reports/baidu_table_candidates_{project_id}_{timestamp}.json`
- 商务通解析报告：
  - 小时报：`reports/kst_dialog_data.json`、`reports/kst_parse_report.json`、`reports/kst_unmatched_rows.json`、`reports/kst_account_dialog_details.json`
  - 日报：`reports/kst_daily_data.json`、`reports/kst_daily_parse_report.json`、`reports/kst_daily_unmatched_rows.json`、`reports/kst_daily_account_dialog_details.json`
- 合并校验：
  - 小时报：`reports/merged_hourly_data.json`、`reports/merge_validate_report.json`
  - 日报：`reports/merged_daily_data.json`、`reports/daily_merge_validate_report.json`
- 写入报告：
  - 小时报：`reports/write_report.json`
  - 日报：`reports/daily_write_report.json`
- 其他常用报告：
  - `reports/doctor_report.json`
  - `reports/excel_structure_report.json`
  - `reports/daily_excel_structure_report.json`

## 11. 发布说明

本说明适用于：

`v0.4.21 内部修复版（含沈阳双百度来源日报、自动安装修复与商务通表头兼容）`

最近关键能力：

- 百度登录状态机闭环
- 百度 report DOM / grid 优先解析
- 账户名完整匹配，禁止模糊匹配
- 百度表格错位提前拦截
- 多项目 Excel path / doctor 诊断增强
- 南京牛日期 / 时段全局字段定位
- 夏思道命令行 SOP
- 沈阳牛双百度来源小时报 / 日报聚合，任一来源失败即中断写入
- 内部发布包校验六个百度凭据 profile，避免沈阳双来源缺凭据交付
- `run_menu.bat` 首次运行自动安装/修复依赖，默认安装移除 Excel COM 备用依赖阻断
- 商务通 `访客消息数` / `访客发送消息数` / `访客发送数` 三种导出表头统一兼容小时报和日报
