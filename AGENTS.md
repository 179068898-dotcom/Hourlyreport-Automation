# 项目规则：百度竞价日报/小时报自动化工具

你必须全程用中文回复。

本项目是 Windows 本地运行的百度竞价日报/小时报自动化工具。当前版本不做 QQ、不做截图，只做：

1. 从百度营销后台读取账户展现、点击、消费；
2. 从快商通人工导出的 Excel/CSV 读取账户对话转化数据；
3. 写入本地 Excel 的 `时段数据` sheet；
4. 保存 Excel；
5. 输出日志、自检报告、异常报告。

## 最高优先级硬规则

1. **分阶段开发，不允许一次性做全流程。**
2. **第一阶段必须先跑通 Excel 表结构识别。**
3. **不允许重建 Excel 文件。**
4. **不允许修改无关 sheet。**
5. **不允许修改“每日时段统计数据 / 汇总区域 / 截图区域 / 公式区域”。**
6. **Excel 写入必须先备份原文件。**
7. **Excel 区域识别必须通过扫描表头、账户区域和字段名称完成，不允许写死固定坐标。**
8. **浏览器自动化不允许依赖绝对屏幕坐标，优先使用 URL、文本、表头、表格结构、选择器。**
9. **当前版本不做截图，不操作 QQ，不自动发送任何消息。**
10. **每次修改代码后必须说明修改了哪些文件、修改了什么。**
11. **每次运行后必须输出日志和自检结果。**
12. **遇到不确定的 Excel 结构，不要猜测写入，必须中断并输出诊断信息。**
13. **浏览器自动化必须优先使用 Google Chrome，不允许默认启动 Edge。**
14. **Chrome 启动失败时必须输出明确错误并等待人工确认，不允许静默降级到 Edge。**

## 浏览器启动规则

默认配置：

- `browser.mode = "connect_existing"`
- `browser.cdp_endpoint = "http://127.0.0.1:9222"`
- `browser.prefer_existing_chrome = true`
- `browser.allow_edge_fallback = false`
- `browser.max_tabs = 3`
- `browser.managed.channel = "chrome"`
- `browser.managed.profile_dir = "browser_profile/chrome"`
- `browser.managed.headless = false`

当前默认必须使用 Playwright 的 `chromium.connect_over_cdp("http://127.0.0.1:9222")` 连接用户已经打开的常用 Google Chrome。连接后优先复用当前 Chrome 中已有的 `cc.baidu.com` 百度投放后台页面；没有后台页面时，优先打开 `https://cc.baidu.com/report`。未登录时允许使用本地 `credentials.local.json` 自动填写百度账号密码登录；若页面要求验证码或额外校验，则等待人工处理。

如果连接失败，必须提示人工先执行：

```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --profile-directory="Default" https://cc.baidu.com/report
```

备用模式 `launch_managed` 才允许使用：

```python
chromium.launch_persistent_context(
    channel="chrome",
    user_data_dir="browser_profile/chrome",
    headless=False,
)
```

当前阶段只使用单个 Chrome 浏览器实例。禁止自动启动 Edge，禁止在 `connect_existing` 模式下启动项目专用 Chrome。以后升级到两个以上项目时，再考虑多浏览器或多 profile 并发读取。

每次连接已有 Chrome 后，程序会清理多余标签页：默认最多保留 3 个标签页，优先保留百度后台相关页面和当前工作页，避免多项目长期运行后标签页堆积造成卡顿。

## 固定账户映射

| 标准账户 | 百度后台名称 | Excel 区域名称 |
|---|---|---|
| 银康01 | 银康01 | 银康01 |
| 银康银屑02 | 银康银屑02 | 银康银屑02 |
| 银康03 | baidu-银康03 | 银康03 |

账户别名必须支持：

- 银康01：`银康01`、`yk01`
- 银康银屑02：`银康银屑02`、`银屑02`、`yk银屑02`
- 银康03：`银康03`、`baidu-银康03`、`Baidu-银康03`、`baidu银康03`

## 快商通字段口径

当前不走 API，不做网页读取，不做桌面控件读取，不做 OCR，不自动操作快商通软件。

快商通数据只从用户手动导出的 Excel/CSV 文件读取，文件放入 `kst_exports/`，或通过 `--file` 指定。

命令：

```cmd
python main.py --mode parse-kst-export --period 15点 --file "导出文件路径"
python main.py --mode parse-kst-export --period 15点
```

不指定 `--file` 时读取 `kst_exports/` 下最新的 `.xlsx` / `.xls` / `.csv` 文件。

必须通过表头识别字段，不允许写死列号。无法归属账户的行必须输出到 `reports/kst_unmatched_rows.json`。

归户优先级：

1. `备注说明` 开头推广 ID：
   - `72828178` → `银康01`
   - `72828179` → `银康银屑02`
   - `81509165` → `银康03`
2. 账户名称字段：`账户`、`推广账户`、`来源账户`、`项目`、`来源`。

- 总对话：当前账户、当前日期、当前时段下 `访客消息数 >= 1` 的全部对话数。
- 有效：名片标签包含 `转潜-有效`、`有效-一般`、`有效-三句` 的对话。
- 有效转潜：名片标签包含 `转潜-有效` 的对话。
- 总转潜：名片标签包含 `转潜-` 的对话，包含 `转潜-有效` 和 `转潜-无效`。

## 开发阶段

1. `inspect-excel`：只识别 Excel 结构，不写入。
2. `mock-write`：使用模拟数据写入测试副本，不连接后台。
3. `fetch-baidu-auto`：自动打开/刷新 `https://cc.baidu.com/report`，读取百度搜索推广账户数据，输出 JSON，不写 Excel。`fetch-baidu` 仅作为历史半自动备用命令保留。
4. `parse-kst-export`：只读取快商通人工导出文件，输出 JSON，不写 Excel。
5. `run`：读取百度 + 快商通并写入 Excel。

## 日报独立阶段

日报不得破坏小时报 `run` 流程，按独立模式推进：

1. `inspect-daily-excel`：识别 `百度` sheet 结构，不写入。
2. `fetch-baidu-daily --date YYYY-MM-DD`：选择指定日期读取百度三户展现、点击、消费，输出 `reports/baidu_daily_data.json`。
3. `parse-kst-daily --date YYYY-MM-DD --file "导出文件路径"`：读取商务通日报导出 Excel/CSV，输出 `reports/kst_daily_data.json`，不写 Excel。
4. `merge-daily --date YYYY-MM-DD`：合并百度日报与商务通日报，输出 `reports/merged_daily_data.json`，不写 Excel。
5. `write-daily --date YYYY-MM-DD`：写入 `百度` sheet，输出 `reports/daily_write_report.json`。
6. `run-daily --date YYYY-MM-DD`：完整执行日报流程；不传 `--date` 时默认处理昨天，输出 `reports/daily_final_run_report.json`。

日报商务通口径：

- `总对话`：目标日期、能归属账户且 `访客消息数 >= 1` 的全部对话行数。
- `有效对话`：仅命中 `转潜-有效`、`有效-一般`、`有效-三句`，不得把 `无效` 误算为有效。
- `无效对话`：`总对话 - 有效对话`。
- `一般有效对话`：命中 `有效-一般`。
- `有效转潜`：命中 `转潜-有效`。
- `总转潜`：命中 `转潜-`。

## 运行和输出

所有阶段必须输出：

- `logs/run.log`
- `reports/*.json`
- 必要时输出 `reports/sheet_text_dump.csv`、页面 debug 截图或 HTML。
