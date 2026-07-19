# Hourlyreport 更新与命名统一设计

## 目标

将桌面程序、在线更新资产、GitHub Release 和本地开发目录统一到 `hourlyreport_automation` 命名体系，同时升级为可验证、可回退且有明确进度反馈的自动更新流程。

产品界面名称继续使用“蚁之力 · 竞价数据自动化”，本次只统一技术文件名与发布入口。

## 统一命名

- GitHub 仓库：`179068898-dotcom/Hourlyreport-Automation`
- Release tag：`v2026.7.19.104` 形式
- Release 资产：`Hourlyreport_automation_v2026.7.19.104.zip` 形式
- 主程序：`hourlyreport_automation.exe`
- 本地开发目录：`hourlyreport_automation`
- 版本号仍遵循 `年.月.日.永久累计序号`，累计序号跨日期递增。

## 更新检索

每次启动后台请求公开仓库的 GitHub REST API `releases/latest`。不抓取 HTML，不使用个人 Token。

更新候选必须同时满足：

1. Release 不是 draft 或 prerelease。
2. tag 精确符合 `v<版本>`；解析器兼容一次旧的 `Hourlyreport_v<版本>` 标签，便于当前 104 Release 验证。
3. 版本严格大于本机版本。
4. 资产名精确为 `Hourlyreport_automation_v<版本>.zip`。
5. 下载链接使用 HTTPS，资产大小大于 0 且不超过 500 MB。
6. GitHub 返回合法 SHA-256 digest；缺失或非法摘要时拒绝自动安装。

下载继续使用 `.part` 临时文件。完成后校验实际字节数、SHA-256、ZIP 路径安全、受保护目录和必需程序文件。任一步失败都丢弃临时包，不改变现有安装。

## 客户端迁移

现有 104 客户端仍访问旧仓库，无法自行发现只发布在新仓库的版本。因此首个迁移版本必须作为桥接版同时发布到：

- 旧仓库 `baidu-automation-releases`
- 新仓库 `Hourlyreport-Automation`

桥接版安装后只访问新仓库。确认公司电脑均升级后，后续版本只在新仓库发布。

## EXE 兼容

更新包只包含新的 `hourlyreport_automation.exe`，避免包体重复。更新助手安装后把同一成品同步为旧文件名兼容副本，使已有桌面快捷方式继续可用；程序重启和新建快捷方式始终优先指向 `hourlyreport_automation.exe`。

旧兼容副本只用于迁移，不作为发布资产名称或后续主入口。

## 更新界面

顶部更新控件参考 Codex 桌面应用，使用同一位置的状态变化：

- 检查中：蓝色圆形循环箭头，仅短暂显示。
- 下载中：蓝色圆形下载箭头，按钮悬浮提示显示百分比。
- 可安装：蓝色胶囊按钮“更新”。
- 无更新或检查失败：控件隐藏，不打断日报/小时报。

点击“更新”后启动独立白色圆角安装浮层，显示“正在安装更新”、阶段说明和进度条。更新助手负责等待旧进程退出、备份、解压、覆盖、兼容 EXE 同步和重启。失败时保留旧文件并写入本地更新日志。

日报或小时报运行期间禁用安装，后台检查和下载可以继续，不中断业务任务。

## 菜单间距

“系统配置”和“数据模式”继续使用微软雅黑 Light。两个按钮的左右内边距和固定宽度同时缩减，布局间距从 5 px 缩减到 2 px，使文字视觉间隔约减半，悬浮底色仍完整包裹文字。

## 安全边界

在线更新不得覆盖 `configs/`、`secrets/`、`logs/`、`reports/`、`backups/`、`browser_profile/`、`kst_exports/`、`samples/`、`.venv/` 或 `runtime/`。

更新前保留被替换程序文件的本地备份。API 检查、下载或安装失败不得影响当前版本继续运行。

## 验收

- 使用新仓库真实 `releases/latest` 响应可识别版本和资产。
- 非标准 tag、错误资产名、缺失 digest、大小不符和危险 ZIP 均被拒绝。
- 顶部控件四种状态与安装浮层可通过 GUI 测试和实际截图确认。
- 旧 EXE 入口在桥接更新后仍可启动，新 EXE 为主入口。
- 更新包不含用户配置或敏感文件。
- 完整基础测试、EXE 构建和发布包审计全部通过。
