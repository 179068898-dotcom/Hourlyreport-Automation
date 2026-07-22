<h1 align="center">🐜 蚁之力 · 竞价数据自动化</h1>

<p align="center">
  <sub><code>H O U R L Y _ R E P O R T _ B O T</code> &nbsp; · &nbsp; v2026.7.22.107</sub>
</p>

<p align="center">
  <strong>Windows 本地运行的百度竞价日报/小时报全自动化工具</strong><br>
  从百度营销后台读取投放数据，解析快商通对话转化文件，自动写入项目 Excel — 零手工误差
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/GUI-PySide6-41CD52?logo=qt&logoColor=white" alt="PySide6">
  <img src="https://img.shields.io/badge/browser-Chrome%20CDP-4285F4?logo=googlechrome&logoColor=white" alt="Chrome CDP">
  <img src="https://img.shields.io/badge/version-2026.7.22.107-667eea" alt="Version">
  <img src="https://img.shields.io/badge/build-Inno%20Setup-225588?logo=windows&logoColor=white" alt="Inno Setup">
  <img src="https://img.shields.io/badge/commits-133-4B8BBE" alt="Commits">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/正式项目-9个-success" alt="9 projects">
  <img src="https://img.shields.io/badge/百度授权-11路-success" alt="11 grants">
  <img src="https://img.shields.io/badge/源码-~110K行-informational" alt="~110K lines">
  <img src="https://img.shields.io/badge/测试-~15K行-informational" alt="~15K test lines">
</p>

---

## 🎯 为什么需要这个工具

竞价广告优化师每天面临重复性数据工作：

| 人工流程 | 本工具替代方案 |
|:--|:--|
| 登录百度营销后台，逐账户抄录展现/点击/消费 | 百度 API 自动拉取（OAuth），失败自动降级 Chrome CDP 浏览器抓取 |
| 登录快商通，手动导出 Excel/CSV | 直接解析同事导出到 `kst_exports/` 的文件，表头动态识别 |
| 逐行对照两个数据源，手工 VLOOKUP 合并 | `data_merger.py` 按账户+时段自动对齐合并，未知行输出报告 |
| 找到 Excel 对应 sheet/区域/格子逐格粘贴 | `excel_inspector.py` 扫描表头 → 定位写入 → 自检复核 |
| 写错格子后手动回退、反复检查 | 写入前自动备份，复核不通过不提交 |

**最终效果**：11点/15点/18点准时出小时报、次日早晨出日报，每次运行 2-5 分钟完成原来 20-40 分钟的机械操作。

---

## 🚀 核心能力

### 📊 数据采集

- **百度营销 API**：OAuth 2.0 服务商应用，9 项目 11 授权已就绪
- **Chrome CDP 回退**：API 失败时自动降级 Playwright 浏览器抓取
- **快商通解析**：表头驱动解析人工导出的 Excel/CSV 对话转化文件
- **多来源协调**：支持双百度来源账户体系，提供别名映射与未识别账户报告

### 🖥️ 用户界面

- **桌面 GUI**（PySide6）：项目切换、日报/小时报一键执行、控制台实时日志
- **交互式菜单**（rich CLI）：面向非技术同事的中文菜单
- **HERMES 固定入口**：11 个 BAT 脚本供 Windows 计划任务/自动代执行
- **在线更新**：GUI 内置 GitHub Release 检测 → 下载 → 安装 → 重启

### 🛡️ 安全与容错

- **Excel 三重保护**：写入前备份 → 定位写入 → 写入后复核
- **表头驱动定位**：扫描表头/账户/字段名动态识别写入位置，不写死坐标
- **API 自修复**：Token 刷新 + 网络重试（20s 预算），失败整项目降级
- **凭据隔离**：`secrets/secrets.json` 永不提交、不打入发布包

### 🔧 工程化

- **预检系统**：快速预检（秒级）用于排队任务，完整预检用于新项目上线
- **任务状态追踪**：日报/小时报是否已跑的持久化状态
- **环境自包含**：`install_env.bat` 自动下载隔离的 Python NuGet 运行时、校验 SHA-256、创建 venv，不依赖或修改系统 Python
- **多项目管理**：CRUD + 校验的配置系统，单实例切换 9 个项目

---

## 🏗️ 架构总览

```
                        用户入口层
                   GUI / menu / HERMES BAT
                            │
                        编排与预检层
                  run_pipeline / preflight
                            │
          ┌──────────────┬──┴──────────┬──────────────┐
          │              │             │              │
    百度数据采集层   快商通解析层   Excel 读写层   数据合并层
    · baidu_auto    · kst_export   · excel_insp   · data_merger
    · baidu_daily   · kst_daily    · excel_writer  · validators
    · baidu_api_*   · kst_parser   · excel_engine
    · baidu_browser
    · baidu_session
    · baidu_multi_*
                            │
                     持久化与基础设施
              configs/  secrets/  logs/
              backups/  reports/  kst_exports/
```

### 模块矩阵

| 层级 | 模块数 | 核心文件 | 关键职责 |
|:--|:--|:--|:--|
| 百度采集 | 14 | `baidu_auto.py`, `baidu_api_client.py`, `baidu_browser.py` | API + CDP 双通道数据获取 |
| 快商通 | 3 | `kst_export_parser.py`, `kst_daily_parser.py`, `kst_parser.py` | 导出文件解析，字段口径统一 |
| Excel | 4 | `excel_inspector.py`, `excel_writer.py`, `excel_engine.py` | 表头扫描 → 定位写入 → 备份复核 |
| 编排 | 3 | `run_pipeline.py`, `preflight.py`, `doctor.py` | 一键流调度、预检、自检 |
| 配置 | 2 | `project_config.py`, `config_manager.py` | 多项目 CRUD、运行时配置构建 |
| GUI | 7 | `gui/app.py`, `gui/main_window.py`, `gui/task_runner.py` | PySide6 桌面应用 |
| 基础设施 | 10+ | `logger.py`, `validators.py`, `credential_manager.py` | 日志、校验、凭据、UI |

---

## 🛠️ 技术栈

| 类别 | 技术选型 | 说明 |
|:--|:--|:--|
| 语言 | Python 3.11+ | 64-bit，项目自包含 runtime，不污染系统 PATH |
| 桌面 GUI | PySide6 + Qt 6 | 项目切换、任务执行、控制台日志、系统托盘 |
| 终端 UI | Rich | 交互式菜单、彩色表格、状态 banner |
| 浏览器自动化 | Playwright (Chrome CDP) | 仅连接/启动 Google Chrome 调试端口 9222 |
| 百度 API | OAuth 2.0 + HMAC | 服务商应用 openBD，Token 自动刷新 |
| Excel 读写 | openpyxl + xlrd | 不重建工作簿，表头驱动定位写入 |
| 打包 | PyInstaller + Inno Setup | onefile windowed EXE + 完整 Windows 安装器 |
| 更新分发 | GitHub Releases API | GUI 自动检测 → 下载 → 静默安装 → 重启 |
| CLI 路由 | argparse | 30+ 独立 `--mode` 入口，统一路由到模块函数 |
| 测试 | pytest | 覆盖配置、Excel、百度、快商通、合并、编排、GUI、发布包 |

---

## ⚡ 快速开始

### 新电脑首次安装

下载并运行最新安装器，其余自动完成：

```text
Hourlyreport_automation_setup_v2026.7.22.107.exe
```

安装器会：创建程序目录 → 注册快捷方式 → 部署默认项目配置。

### 开发环境

```cmd
:: 1. 克隆仓库
git clone <repo-url>
cd hourly_report_bot

:: 2. 安装运行环境（自动下载隔离的项目专用 Python 3.14.5 64-bit，校验 SHA-256）
install_env.bat

:: 3. 补充开发依赖
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

:: 4. 运行自检
.venv\Scripts\python.exe main.py --mode doctor

:: 5. 运行全量测试
.venv\Scripts\python.exe -m pytest tests\test_basic.py -v
```

### 三行跑通小时报

```cmd
:: 快速预检
.venv\Scripts\python.exe main.py --mode preflight --quick

:: 一站式：下载百度 + 解析快商通 + 合并 + 写入 Excel
.venv\Scripts\python.exe main.py --mode run --period 15点 --yes

:: 日报同理
.venv\Scripts\python.exe main.py --mode run-daily --date 2026-07-19 --yes
```

---

## 📁 项目结构

```
hourly_report_bot/
│
├── main.py                        # CLI 入口 — argparse 路由 30+ --mode
├── menu.py                        # 交互式中文菜单（非技术同事）
├── run_menu.bat                   # 菜单启动脚本
│
├── install_env.bat                # 一键环境安装（下载 Python + 创建 venv）
├── requirements-runtime.txt       # 生产运行依赖
├── requirements-dev.txt           # 开发/测试/打包依赖
│
├── run_hermes_hourly.bat          # HERMES 小时报固定入口 x3 时段
├── run_hermes_daily.bat           # HERMES 日报固定入口
├── start_chrome_debug.bat         # 人工启动调试 Chrome（排障）
│
├── build_desktop_exe.bat          # PyInstaller 构建桌面 EXE
├── run_desktop_gui.bat            # 开发版 GUI 启动
│
│   # === 核心业务模块（89 个 .py，~110K 行）===
│
├── baidu_auto.py                  # 百度小时报自动读取
├── baidu_daily.py                 # 百度日报数据读取
├── baidu_api_client.py            # 百度 OAuth API 客户端
├── baidu_browser.py               # Playwright Chrome CDP 管理
├── baidu_parser.py                # 百度页面表格解析
├── baidu_validator.py             # 百度数据自检校验
├── baidu_session.py               # 百度登录态维护
├── baidu_multi_source.py          # 多来源百度数据协调
├── baidu_unknown_accounts.py      # 未识别账户处理
├── baidu_detector.py              # 百度页面类型检测
├── baidu_overview.py              # 百度概览页导航
│
├── kst_export_parser.py           # 快商通小时报导出文件解析
├── kst_daily_parser.py            # 快商通日报导出文件解析
├── kst_parser.py                  # 快商通字段口径逻辑
│
├── excel_inspector.py             # Excel 结构扫描（小时报）
├── daily_excel_inspector.py       # Excel 结构扫描（日报）
├── excel_writer.py                # Excel 写入（备份→写入→复核）
├── excel_engine.py                # 引擎抽象（openpyxl / excel_com）
│
├── data_merger.py                 # 百度 + 快商通数据合并
├── run_pipeline.py                # 一键流编排
├── preflight.py                   # 运行前预检
├── doctor.py                      # 运行环境自检
│
├── project_config.py              # 多项目配置 CRUD + 标准化
├── config_manager.py              # 简单 JSON 配置读取
├── credential_manager.py          # 凭据读取
├── validators.py                  # 通用数据校验
│
├── browser_manager.py             # 浏览器启动/连接测试
├── browser_login_state.py         # 浏览器登录状态检测
├── chrome_debug.py                # Chrome 调试端口管理
├── chrome_debug_launcher.py       # Chrome 调试实例启动
│
├── console_ui.py                  # Rich 终端 UI
├── logger.py                      # 日志配置
├── text_normalizer.py             # 文本标准化
├── task_status.py                 # 任务完成状态追踪
│
│   # === GUI 模块（PySide6）===
│
├── gui/
│   ├── app.py                     # QApplication 入口
│   ├── main_window.py             # 主窗口布局
│   ├── project_store.py           # 项目列表管理
│   ├── command_builder.py         # CLI 命令组装
│   ├── task_runner.py             # QProcess 子进程执行
│   ├── log_formatter.py           # 日志高亮格式化
│   └── environment_check.py       # GUI 启动环境检查
│
│   # === 工具与构建 ===
│
├── tools/
│   ├── bootstrap_python.ps1       # 自动下载安装项目专用 Python
│   ├── build_release.py           # 发布包构建
│   ├── build_windows_installer.py # Inno Setup 安装器构建
│   └── ...
│
│   # === 配置与数据 ===
│
├── configs/
│   ├── app_config.json            # 默认项目 + 配置目录路径
│   └── projects/                  # 每项目一个 JSON（12 个文件）
├── secrets/                       # 凭据文件（.gitignore）
├── tests/                         # pytest 测试（~15K 行）
├── docs/                          # 技术文档
├── reports/                       # 输出报告目录
├── logs/                          # 运行日志
├── backups/                       # Excel 写入前自动备份
└── kst_exports/                   # 快商通人工导出文件
```

---

## 🎮 使用方式

### 方式一：桌面 GUI（推荐同事使用）

```
双击 hourlyreport_automation.exe
或 run_desktop_gui.bat
```

- 下拉切换 9 个正式项目
- 点"小时报"选时段（11点/15点/18点）→ 自动执行完整管道
- 点"日报" → 自动处理昨日数据
- 控制台实时彩色日志
- 任务完成后自动打开当前项目 Excel

### 方式二：HERMES（夏思道）固定入口

供 Windows 计划任务、自动代执行或运维定时调用：

```cmd
run_hermes_hourly.bat 11点
run_hermes_hourly.bat 15点
run_hermes_hourly.bat 18点
run_hermes_daily.bat
run_hermes_daily.bat 2026-07-09
```

BAT 自动完成：固定 UTF-8 环境 → 检查 `.venv` → 运行 preflight → 执行任务。Preflight 失败则停止，不写 Excel。

### 方式三：命令行

```cmd
:: 查看所有可用模式
.venv\Scripts\python.exe main.py --help

:: 分阶段调试
.venv\Scripts\python.exe main.py --mode inspect-excel
.venv\Scripts\python.exe main.py --mode fetch-baidu-auto --period 15点
.venv\Scripts\python.exe main.py --mode parse-kst-export --period 15点
.venv\Scripts\python.exe main.py --mode merge-data
.venv\Scripts\python.exe main.py --mode write-excel --period 15点

:: 或一键完成
.venv\Scripts\python.exe main.py --mode run --period 15点 --yes
```

### 方式四：交互式菜单

```cmd
run_menu.bat
```

中文菜单引导，适合不熟悉命令行的同事。

---

## 🔄 数据管道

```
百度营销后台 (API / Chrome)      快商通人工导出 (kst_exports/)
         │                                    │
         ▼                                    ▼
   baidu_auto.py                      kst_export_parser.py
   baidu_daily.py                     kst_daily_parser.py
   baidu_api_*.py
         │                                    │
         └──────────────┬────────────────────┘
                        ▼
                  data_merger.py
            按账户 + 时段对齐合并
             未知行输出报告
                        │
                        ▼
                  excel_writer.py
            备份 → 定位写入 → 自检复核
                        │
                        ▼
                     输出物
            · Excel 已更新
            · reports/*.json
            · logs/run.log
            · backups/ (时间戳备份)
```

### 小时报数据流

```
fetch_baidu_auto + parse_kst_export_file
    → merge_data_files
    → write_merged_hourly_data
```

### 日报数据流

```
fetch_baidu_daily + parse_kst_daily_file
    → merge_daily_files
    → write_merged_daily_data
```

Pipeline 在执行前强制凭据预检，失败不写 Excel。

---

## 🔌 百度 API 模式

本项目已完成百度营销开放平台服务商应用 `openBD` 的审核与授权部署。

### 数据源策略

应用级 `baidu_data_source_preference` 控制所有生产任务：

| 模式 | 配置值 | 行为 |
|:--|:--|:--|
| **API 优先** | `A` / `api` | 默认。先走 OAuth API → Token/网络/完整性失败后 20s 内自修复 → 仍失败则整项目降级 Chrome CDP |
| **强制浏览器** | `B` / `browser` | 紧急回退。不发起任何 API 请求，直接走 Playwright Chrome CDP |

### API 自修复策略

```
API 调用失败
  ├── Token 过期 → 刷新一次
  ├── 网络错误 → 额外重试两次
  ├── 完整性错误 → 额外拉取一次
  └── 总预算 20s 耗尽 → 整项目降级浏览器
```

### 验收命令

```cmd
:: 只读验收（不读写 Excel，不启动 Chrome）
.venv\Scripts\python.exe main.py --mode test-baidu-api-readiness
```

---

## ⚙️ 配置体系

```
configs/
├── app_config.json              # 应用级：默认项目 + 配置目录路径
├── projects/
│   ├── kunming_npx.json         # 昆明牛
│   ├── nanjing_npx.json         # 南京牛
│   ├── ningbo_npx.json          # 宁波牛
│   ├── changsha_npx.json        # 长沙牛
│   ├── shenyang_npx.json        # 沈阳牛（双来源）
│   ├── qingdao_bai.json         # 青岛白
│   ├── shenzhen_bai.json        # 深圳白
│   ├── nanjing_bai.json         # 南京白
│   └── shenyang_bai.json        # 沈阳白（双来源）
│
secrets/
└── secrets.json                 # 百度账号密码 + OAuth Token（不提交）

credentials.local.json           # 本机百度账号（.gitignore）
```

项目配置结构（每项目一个 JSON）：

- **基本信息**：项目 ID、显示名称、行业类型
- **账户体系**：`accounts` 数组定义百度别名→账户、商务通 ID→账户的映射
- **百度数据源**：`api_profile`（授权映射）、`baidu_data_source_preference`（A/B）
- **百度 API 参数**：推广 ID 集合、授权范围
- **Excel 定位**：目标文件路径、目标 sheet 名、预期表头列名
- **快商通设置**：导出目录、文件匹配模式
- **多来源**：双来源项目（沈阳）的两套凭据 profile

---

## 🛡️ Excel 写入安全

本工具不重建 Excel、不修改无关 sheet、不猜测坐标，执行严格的三阶段写入流程：

```
1. 自动备份              2. 定位写入              3. 自检复核
   backups/                 扫描表头 → 定位区域       校验值 ≠ 写入值
   时间戳副本               按账户+时段写入           → 中断并报告
       │ ──────────────────▶ │ ──────────────────▶ │
```

### 硬性约束

- ❌ 不重建工作簿
- ❌ 不修改无关 sheet
- ❌ 不修改公式区、汇总区、截图区、"每日时段统计数据"
- ❌ 不写死固定坐标 — 一切通过表头/账户区域/字段名动态识别
- ❌ 结构不明确时猜测写入 — 中断并输出诊断报告
- ✅ 写入前必须备份
- ✅ 单元格写入后必须回读复核

---

## 🌐 Chrome 自动化策略

| 约束 | 说明 |
|:--|:--|
| 浏览器 | 仅 Google Chrome，不自动降级 Edge |
| 连接方式 | CDP `http://127.0.0.1:9222`，复用已启动实例 |
| API 模式 | Preflight 不启动 Chrome；仅 API 实际降级时才延迟启动 |
| 浏览器模式 | Preflight 检查 9222 端口，未就绪自动启动项目专用调试 Chrome |
| 静默原则 | 自动登录、清 cookie、切换账号静默执行；仅验证码/滑块才显示窗口 |
| 连接失败 | 提示人工运行 `start_chrome_debug.bat`，不另起普通 Chrome |
| 登录态 | CAS 自动登录，旧账号退出失败时降级清理 cookie/storage 再登录 |

```cmd
:: 人工排障：手动启动调试 Chrome
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --profile-directory="Default" https://cc.baidu.com/report
```

---

## 🔄 在线更新

| 项目 | 说明 |
|:--|:--|
| 版本基线 | `2026.7.22.107`（标准安装器） |
| 仓库 | `179068898-dotcom/Hourlyreport-Automation`（GitHub Releases） |
| 检测 | GUI 启动时后台检查最新 Release |
| 下载 | 检测到新版本 → 标题栏显示更新按钮 → 点击下载增量 ZIP |
| 安装 | 下载完成 → 点击"更新" → 静默覆盖 → 自动重启 |
| 安全 | 只替换程序文件，不覆盖 `configs/` `secrets/` 日志/报告/备份/浏览器数据 |

### 版本编号规则

```
发布年.月.日.永久累计序号
2026.7.22.107
         └── 累计序号：从 100 起，永不按日期重置
```

---

## 👩‍💻 开发指南

### 开发规则（摘要自 AGENTS.md）

1. **分阶段开发**：不允许一次性做全流程
2. **Excel 安全**：写入前备份，表头驱动定位，不猜测坐标
3. **浏览器规则**：仅 Google Chrome，不依赖绝对屏幕坐标
4. **安全级修改**：涉及安全/凭据/授权/在线更新/发布包覆盖时按高风险处理
5. **禁止行为**：不启动 Edge、不重建 Excel、不跳过备份、不手工补 Excel 数字
6. **每次修改后**：说明修改了哪些文件、修改了什么、输出日志和自检结果
7. **凭据保护**：不索要密码、不输出/记录/提交 secrets

> 完整规则见 [AGENTS.md](AGENTS.md)。所有 AI Agent（Codex、Claude、HERMES 等）参与本仓库开发时必须优先遵守。

### 常用开发命令

```cmd
:: 运行环境自检
.venv\Scripts\python.exe main.py --mode doctor

:: 查看/校验项目配置
.venv\Scripts\python.exe main.py --mode list-projects
.venv\Scripts\python.exe main.py --mode show-project
.venv\Scripts\python.exe main.py --mode validate-project

:: 跑测试
.venv\Scripts\python.exe -m pytest tests\test_basic.py -v
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "test_project_config"

:: 分阶段调试
.venv\Scripts\python.exe main.py --mode inspect-excel
.venv\Scripts\python.exe main.py --mode dump-sheet-text
.venv\Scripts\python.exe main.py --mode test-browser-connect
.venv\Scripts\python.exe main.py --mode baidu-detect
```

---

## 📦 构建与发布

### 构建产物

| 产物 | 命令 | 说明 |
|:--|:--|:--|
| 桌面 EXE | `build_desktop_exe.bat` | PyInstaller onefile + windowed |
| 内部包 | `python tools/build_release.py --internal` | 完整发布目录 |
| 首次安装器 | `python tools/build_release.py --first-install --version X.X.X.X` | 含默认配置 |
| 在线更新包 | `python tools/build_release.py --online-update --version X.X.X.X` | 仅程序文件 |
| Windows 安装器 | `python tools/build_windows_installer.py --version X.X.X.X` | Inno Setup EXE |

### 发布检查清单

1. `test-baidu-api-readiness` 验收通过
2. 全量 `tests/test_basic.py` 通过
3. 上一版本 Release 元数据可被更新器识别
4. 在线更新包不包含 `configs/` `secrets/` 日志/报告/备份
5. `.baidu-secrets` 不出现在任何包中
6. 更新说明（中文）已准备，列出用户可感知改动、稳定性修复和兼容性注意事项

---

## 📜 版本历史

| 版本 | 日期 | 里程碑 |
|:--|:--|:--|
| `2026.7.22.107` | 2026-07-22 | 快商通统计口径修正、隔离 Python 安装修复、依赖锁定、脱敏诊断包与日志归档 |
| `2026.7.19.106` | 2026-07-19 | 标准 Windows 安装器基线（Inno Setup），持久化日志 |
| `2026.7.19.105` | 2026-07-19 | UI 细节优化 |
| ~104 | 2026-07-19 | API 优先桌面自动化，GitHub Release 在线更新 |
| ~103 | 2026-07-17 | 在线更新安装加固 |
| 更早版本 | 2026-05 起 | 浏览器自动化 → 多项目 → 多来源 → API 集成 → 在线更新 |

从 2026-05-10 至今 **133 次提交**，覆盖从浏览器自动化到 API/安装器/在线更新的完整演进。

---

## 📚 文档索引

| 文档 | 目标读者 | 内容 |
|:--|:--|:--|
| [README.md](README.md) | 所有人 | 项目概览、架构、快速开始 |
| [README_同事使用说明.md](README_同事使用说明.md) | 非技术同事 | GUI 和 HERMES 快速上手 |
| [AGENTS.md](AGENTS.md) | AI Agent | 硬规则、禁止行为、开发边界 |
| [CLAUDE.md](CLAUDE.md) | Claude Code | 项目上下文、常用命令、架构速览 |
| [xia_sidao使用说明.md](xia_sidao使用说明.md) | HERMES 使用者 | 夏思道固定入口操作说明 |
| [docs/hermes_hourly_sop.md](docs/hermes_hourly_sop.md) | 运维 | 小时报标准操作流程 |
| [docs/hermes_daily_sop.md](docs/hermes_daily_sop.md) | 运维 | 日报标准操作流程 |
| [docs/online_update_sop.md](docs/online_update_sop.md) | 发布者 | 在线更新发布与版本编号规则 |

---

## ⚠️ 行为准则

### 数据安全红线

- **凭据隔离**：`secrets/secrets.json` 和 `credentials.local.json` 均在 `.gitignore`，永不提交
- **配置包传递**：百度账号密码和 OAuth Token 仅通过 `.baidu-secrets` 在公司内部受控传递
- **日志脱敏**：`logs/` 和 `reports/` 不包含令牌、密钥或密码
- **构建排除**：所有发布包自动排除 `secrets/` 和 `.baidu-secrets`

### 运行安全红线

- 不操作 QQ、不自动发送消息、不做截图（当前版本）
- 不调用快商通收费 API、不操作桌面客户端
- 不在未获用户明确授权时运行真实 `run` / `run-daily` 或写入目标 Excel
- API 和浏览器都失败时停止，不继续解析/合并/写 Excel

---

<p align="center">
  <sub>Built with ❤️ for SEM optimizers · <code>HERMES-20260710</code> · 89 modules · ~110K lines · 133 commits</sub>
</p>
