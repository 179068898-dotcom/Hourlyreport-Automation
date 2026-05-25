# 百度竞价日报/小时报自动化工具框架

当前内部试用发布版：v0.4.4

本包是给 Codex 桌面版 / Codex CLI 读取的项目框架，不是最终完成版程序。它已经包含：

- 项目目录结构；
- 开发阶段设计；
- Excel 识别规则；
- 百度后台抓数规则；
- 快商通统计口径；
- 写入边界；
- 自检与异常处理；
- 第一阶段 Excel 结构识别代码壳。

## 当前版本范围

当前版本删除 QQ 和截图功能，只做：

1. 百度营销后台：读取 `银康01`、`银康银屑02`、`baidu-银康03` 的展现、点击、消费；
2. 快商通数据：读取用户从快商通软件手动导出的 Excel/CSV，统计总对话、有效、有效转潜、总转潜；
3. 写入本地 Excel 文件的 `时段数据` sheet；
4. 保存 Excel；
5. 输出日志和自检报告。

## v0.4 项目配置化

项目配置从开发脚本中拆出来，放到 `configs/` 和 `secrets/`：

```text
configs/app_config.json
configs/projects/kunming_npx.json
secrets/secrets.example.json
```

`configs/app_config.json` 保存默认项目和配置目录：

```json
{
  "default_project_id": "kunming_npx",
  "projects_dir": "configs/projects",
  "secrets_file": "secrets/secrets.json"
}
```

`configs/projects/kunming_npx.json` 保存项目级配置，包括 Excel 路径、小时报/日报 sheet、Excel 写入引擎、商务通导出目录、百度凭据 profile、账户映射、小时报时段、日报允许/禁止写入字段。

每个项目一个 JSON 文件，放在 `configs/projects/`。`configs/app_config.json` 里的 `default_project_id` 决定当前项目；菜单里的“切换项目”会修改这个值，“刷新当前项目”只会重新读取当前项目配置。

项目配置里的账户字段使用：

```json
{
  "standard_name": "银康03",
  "baidu_names": ["baidu-银康03", "Baidu-银康03", "银康03"],
  "excel_name": "银康03",
  "kst_ids": ["81509165"],
  "kst_names": ["银康03", "baidu-银康03"]
}
```

新增第二个项目时，复制 `configs/projects/kunming_npx.json` 为新的 `project_id.json`，修改 `project_id`、`project_name`、`excel.path`、`kst.export_dir`、`baidu.credential_profile` 和 `accounts`，再用菜单切换项目。

当前默认 Excel 写入引擎是 `openpyxl`，适合公司电脑只安装 WPS 的环境，不要求安装 Microsoft Excel。程序直接读写 `.xlsx` 文件，写入前会备份，写入后会重新读取目标单元格复核。运行写入前请关闭 WPS 或 Excel 中已经打开的目标文件，否则保存失败时会提示关闭目标文件后重试。

真实密码放到 `secrets/secrets.json`，不要提交。仓库只提供 `secrets/secrets.example.json` 作为模板。

查看项目列表：

```cmd
.venv\Scripts\python.exe main.py --mode list-projects
```

查看当前默认项目：

```cmd
.venv\Scripts\python.exe main.py --mode show-project
```

校验当前默认项目配置：

```cmd
.venv\Scripts\python.exe main.py --mode validate-project
```

## v0.4 新手菜单入口

新手可以直接运行中文菜单：

```cmd
.venv\Scripts\python.exe menu.py
```

发布包给同事使用时，优先双击：

```text
START_HERE.bat
```

它会在第一次运行时自动调用 `install_env.bat`，安装完成后打开菜单。

菜单提供：

- 运行日报；
- 运行小时报，进入后选择 11点 / 3点 / 6点；
- 切换项目；
- 刷新当前项目；
- 检查运行环境；
- 退出。

菜单顶部会始终显示当前项目、当前配置文件和目标 Excel，不需要手动刷新才能看到当前执行项目。

运行日报或小时报前都会显示确认清单，包括当前项目、目标 Excel、目标 sheet、当前任务、目标日期或时段、商务通导出目录、自动选中的最新商务通导出文件，以及关键执行条件是否具备。按 Enter 继续，输入 `q` 退出。

## 浏览器规则

浏览器自动化默认连接你已经打开的常用 Google Chrome，不默认启动项目专用浏览器，也不会自动切换 Edge：

```json
"browser": {
  "mode": "connect_existing",
  "cdp_endpoint": "http://127.0.0.1:9222",
  "prefer_existing_chrome": true,
  "allow_edge_fallback": false,
  "max_tabs": 3,
  "managed": {
    "channel": "chrome",
    "executable_path": "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "profile_dir": "browser_profile/chrome",
    "headless": false
  }
}
```

使用前先在 CMD 中启动常用 Chrome 的调试端口：

```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --profile-directory="Default" https://cc.baidu.com/report
```

如果你已经打开过 Chrome，上面的命令可能只会复用旧窗口，导致 `9222` 端口没有真正开启。新版 Chrome 也可能禁止在默认个人资料目录上开启远程调试，即使进程命令行里看到了 `--remote-debugging-port=9222`，端口也不监听。此时请关闭所有 Chrome 后再运行，或直接双击项目里的：

```text
start_chrome_debug.bat
```

这个脚本会先检查 `9222` 端口；如果发现 Chrome 已在运行，会询问是否关闭所有 Chrome 并重新用调试端口打开。为兼容新版 Chrome 的安全限制，脚本会使用项目内 `browser_profile/chrome_debug` 作为调试专用用户目录。

`connect_existing` 会复用这个 Chrome 里的登录态、书签、插件和已打开页面。如果没有找到百度投放后台页面，程序优先打开 `https://cc.baidu.com/report`；不会自动切 Edge，也不会无头运行。

每次连接已有 Chrome 后，程序会清理多余标签页：默认最多保留 3 个标签页，优先保留百度后台相关页面和当前工作页，减少多项目长期运行后的卡顿。

百度自动登录凭据放在项目根目录的 `credentials.local.json`，该文件已被 `.gitignore` 忽略，只在本机使用。示例结构如下，真实账号密码不要写入 README 或提交到仓库：

```json
{
  "baidu": {
    "yunnan_yinkang": {
      "username": "你的百度账号",
      "password": "你的百度密码"
    }
  }
}
```

`launch_managed` 仍保留为备用模式，它会使用项目内 `browser_profile/chrome`，但不是默认模式。只有配置中明确把 `browser.mode` 改成 `launch_managed` 时才会启动项目专用 Chrome。

浏览器启动测试：

```cmd
.venv\Scripts\python.exe main.py --mode test-browser
```

连接已有 Chrome 测试：

```cmd
.venv\Scripts\python.exe main.py --mode test-browser-connect
```

该命令只连接 `http://127.0.0.1:9222`，列出当前 Chrome 页面 URL，不读取后台数据，不写 Excel，不关闭你的 Chrome。

## 第三阶段：百度读取

v0.3 优先走 `https://cc.baidu.com/report`。未登录时程序会打开百度 CAS 登录页，读取本机 `credentials.local.json` 自动填写账号密码；如果页面出现验证码或额外安全校验，则需要人工处理。

搜索推广概览页准备检查：

```cmd
.venv\Scripts\python.exe main.py --mode baidu-prepare-overview
```

该命令会复核当前页面是否为今天、是否能看到三个账户、是否能看到 `账户 / 展现 / 点击 / 消费` 表头，并输出 `reports/baidu_prepare_overview_report.json`。

百度自动读取：

```cmd
.venv\Scripts\python.exe main.py --mode fetch-baidu-auto --period 15点
```

流程：

1. 程序连接已开启调试端口的常用 Google Chrome；
2. 直接打开或复用 `https://cc.baidu.com/report`；
3. 未登录时读取本机 `credentials.local.json` 自动填写账号密码登录；
4. 抓取前刷新 report 页面，避免读取旧数据或未加载数据；
5. 等待搜索推广账户表格加载完成；
6. 解析三个账户的展现、点击、消费，输出 `reports/baidu_account_data.json`；
7. 同时输出 `reports/baidu_validate_report.json` 和 `reports/baidu_page_text_dump.txt`；
8. 如果读取失败，额外输出 `reports/baidu_debug.html` 和可见文本 dump；默认不截图。

历史备用半自动命令仍保留：

```cmd
.venv\Scripts\python.exe main.py --mode fetch-baidu --period 15点
```

本阶段不写 Excel，不打开快商通，不自动切 Edge。

## 第六阶段：半自动一键流

半自动一键流会串联已经跑通的单项模块：

1. 自动打开/刷新百度 `https://cc.baidu.com/report` 并读取搜索推广账户表格；
2. 解析快商通人工导出的 Excel/CSV；
3. 合并百度和快商通数据；
4. 写入目标 Excel 的 `时段数据` sheet；
5. 写入后复核；
6. 输出 `reports/final_run_report.json`。

指定快商通导出文件：

```cmd
.venv\Scripts\python.exe main.py --mode run --period 15点 --file "E:\导出\快商通导出.xlsx"
```

`--kst-file` 也可以使用，等同于 `--file`：

```cmd
.venv\Scripts\python.exe main.py --mode run --period 15点 --kst-file "E:\导出\快商通导出.xlsx"
```

不指定文件时，程序会自动读取 `kst_exports` 目录下最新的 `.xlsx` / `.xls` / `.csv`：

```cmd
.venv\Scripts\python.exe main.py --mode run --period 15点
```

运行前会显示确认清单，按 Enter 继续，输入 `q` 退出。确认清单会提示：

- 百度 report 页面会自动刷新并复核今天、三个账户和表头；
- 快商通导出文件路径；
- 目标 Excel 路径；
- 写入时段；
- 本流程不会自动点击百度菜单、不会操作快商通软件、不做 QQ、不截图。

如果已经确认无误，可以用 `--yes` 跳过确认：

```cmd
.venv\Scripts\python.exe main.py --mode run --period 15点 --yes
```

双击脚本：

```text
run_11.bat
run_15.bat
run_18.bat
```

直接双击时，会自动从 `kst_exports` 目录选择最新导出文件。也可以把快商通导出 Excel/CSV 文件拖到对应 bat 上运行，脚本会把该文件作为 `--file` 传入。

任何步骤失败都会中断，不继续写 Excel，并在 `reports/final_run_report.json` 里记录失败步骤和原因。

## 第四阶段：快商通导出文件解析

快商通不走 API，不做网页读取，不做桌面控件读取，不做 OCR，也不自动操作快商通软件。

当前方案是：人工从快商通软件导出 Excel/CSV 文件，放到 `kst_exports` 目录，然后程序读取导出文件并统计。

指定文件：

```cmd
.venv\Scripts\python.exe main.py --mode parse-kst-export --period 15点 --file "E:\导出\快商通导出.xlsx"
```

不指定文件时，自动读取 `kst_exports` 目录下最新的 `.xlsx` / `.xls` / `.csv`：

```cmd
.venv\Scripts\python.exe main.py --mode parse-kst-export --period 15点
```

也可以运行：

```cmd
run_parse_kst_export_15.bat
```

输出：

- `reports/kst_dialog_data.json`
- `reports/kst_parse_report.json`
- `reports/kst_unmatched_rows.json`
- `logs/run.log`

归户规则：

- 优先读取 `备注说明` 开头的推广 ID；
- `72828178` → `银康01`
- `72828179` → `银康银屑02`
- `81509165` → `银康03`
- 无法归户的行输出到 `reports/kst_unmatched_rows.json`，不猜测。

统计口径：

- `总对话`：当前日期、能归属到账户且导出字段 `访客消息数 >= 1`、`访客发送消息数 >= 1` 或 `访客发送数 >= 1` 的对话行数；
- `有效`：名片标签包含 `转潜-有效`、`有效-一般`、`有效-三句`；
- `有效转潜`：名片标签包含 `转潜-有效`；
- `总转潜`：名片标签包含 `转潜-`；
- 标签为空但能归户的行计入 `总对话`，不计入其他转化字段。

## 日报开发命令

日报是独立流程，不影响小时报 `run`。当前已支持日报 Excel 结构识别、百度日报抓数、商务通日报导出解析。

识别 `百度` sheet 结构：

```cmd
.venv\Scripts\python.exe main.py --mode inspect-daily-excel
```

抓取指定日期百度日报数据：

```cmd
.venv\Scripts\python.exe main.py --mode fetch-baidu-daily --date 2026-05-07
```

解析指定日期商务通日报导出文件：

```cmd
.venv\Scripts\python.exe main.py --mode parse-kst-daily --date 2026-05-07 --file "E:\导出\商务通导出.xlsx"
```

不指定 `--file` 时，会读取 `kst_exports` 目录下最新的 Excel/CSV 文件：

```cmd
.venv\Scripts\python.exe main.py --mode parse-kst-daily --date 2026-05-07
```

合并百度日报与商务通日报数据：

```cmd
.venv\Scripts\python.exe main.py --mode merge-daily --date 2026-05-07
```

写入日报 Excel：

```cmd
.venv\Scripts\python.exe main.py --mode write-daily --date 2026-05-07
```

日报一键流，未传 `--date` 时默认处理昨天：

```cmd
.venv\Scripts\python.exe main.py --mode run-daily
.venv\Scripts\python.exe main.py --mode run-daily --date 2026-05-07
.venv\Scripts\python.exe main.py --mode run-daily --date 2026-05-07 --file "E:\导出\商务通导出.xlsx"
```

商务通日报输出：

- `reports/kst_daily_data.json`
- `reports/kst_daily_parse_report.json`
- `reports/kst_daily_unmatched_rows.json`
- `reports/kst_daily_account_dialog_details.json`

日报合并输出：

- `reports/merged_daily_data.json`
- `reports/daily_merge_validate_report.json`

日报一键流输出：

- `reports/daily_final_run_report.json`

商务通日报口径：

- `总对话`：目标日期、能归属到账户且导出字段 `访客消息数 >= 1`、`访客发送消息数 >= 1` 或 `访客发送数 >= 1` 的全部对话行数；
- `有效对话`：名片标签命中 `转潜-有效`、`有效-一般`、`有效-三句`，不会把 `无效` 误算为有效；
- `无效对话`：`总对话 - 有效对话`；
- `一般有效对话`：名片标签包含 `有效-一般`；
- `有效转潜`：名片标签包含 `转潜-有效`；
- `总转潜`：名片标签包含 `转潜-`。

## 第一阶段先做什么

第一阶段只做 Excel 表结构识别：

```cmd
python main.py --mode inspect-excel
```

它会读取 `config.json` 中的 Excel 路径，打开 `时段数据` sheet，扫描所有非空单元格，识别：

- 每日时段统计数据 / 汇总区域；
- 银康01 区域；
- 银康银屑02 区域；
- 银康03 区域；
- 日期列、时段列、展现列、点击列、消费列、总对话列、有效列、有效转潜列、总转潜列。

输出：

- `reports/excel_structure_report.json`
- `reports/sheet_text_dump.csv`
- `logs/run.log`

## 安装依赖

建议在 CMD 中运行，不要用 PowerShell，避免执行策略拦截。

```cmd
cd /d D:\自动化工具\hourly_report_bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py --mode inspect-excel
```

如果 `python` 不可用，尝试：

```cmd
py -m venv .venv
.venv\Scripts\activate
py main.py --mode inspect-excel
```

## 配置方法

复制：

```text
config.example.json -> config.json
```

修改 `excel_path` 为测试 Excel 副本路径，例如：

```json
"excel_path": "D:/自动化工具/hourly_report_bot/samples/【昆明npx】2026竞价数据_测试副本.xlsx"
```

## 给 Codex 的工作方式

让 Codex 读取：

- `AGENTS.md`
- `docs/完整需求说明.md`
- `docs/阶段开发计划.md`
- 当前代码

然后按阶段开发，不要一上来做全流程。

建议给 Codex 的第一句话：

```text
请读取 AGENTS.md、README.md 和 docs 目录下的规则。当前只做第一阶段 Excel 表结构识别。不要连接百度后台，不要连接快商通，不要写入 Excel。请先运行 python main.py --mode inspect-excel，根据 reports/excel_structure_report.json 和 reports/sheet_text_dump.csv 修正识别逻辑。
```
