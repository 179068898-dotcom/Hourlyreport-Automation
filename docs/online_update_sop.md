# 在线更新发布规则

## 基线

`2026.7.15.101` 是首个带在线更新器的版本。更早的同事版本必须人工完整安装一次带 `first_install` 标记的首次安装包，之后才能在 GUI 启动时自动检查 GitHub Release。

`baidu_data_automation_update_*.zip` 只用于覆盖已有安装，故意排除 `configs/` 和其他用户数据，不能作为新电脑安装包。新电脑统一使用 `baidu_data_automation_first_install_*.zip`；若误启动不完整的更新目录，GUI 应给出首次安装提示并安全退出，不显示 Python 异常堆栈。

## 版本号

格式：

```text
发布年.月.日.永久累计序号
```

累计序号从 `100` 起，只增不减，跨日期也不重置：

```text
2026.7.15.101
2026.7.16.102
2026.7.16.103
2026.7.20.104
```

构建代码提供 `next_online_version()` 计算下一序号，并拒绝无效日期、错误格式和小于 `100` 的累计序号。

## 发布步骤

1. 查询 GitHub 上一次正式 Release 的版本号。
2. 使用当天日期，并将上一次版本号最后一段加 `1`。
3. 同步更新 `gui/version.py` 中的 `CURRENT_VERSION`。
4. 重新构建 `百度数据自动化控制台.exe`。
5. 运行基础测试，不通过则停止发布。
6. 如需部署新电脑，生成包含默认配置但不含真实凭据的首次安装包：

```cmd
.venv\Scripts\python.exe tools\build_release.py --first-install --version 2026.7.17.103
```

7. 生成只含程序文件的在线更新包：

```cmd
.venv\Scripts\python.exe tools\build_release.py --online-update --version 2026.7.17.103
```

8. GitHub Release tag 使用 `v2026.7.17.103`，上传同版本 ZIP；首次安装包与在线更新包用途不同，不得混用。
9. 在一台已安装上一版本的测试电脑上验证“发现更新、下载、安装、重启、保留配置”完整流程，并在一个无配置空目录验证首次安装包可启动。

## 不得覆盖

在线更新包不得包含或覆盖：

- `configs/`
- `secrets/`
- `logs/`、`reports/`、`backups/`
- `kst_exports/`
- `browser_profile/`
- 同事本机 Excel 和其他业务数据

## API 开发关系

在线更新与百度 API 数据源是两条独立能力。昆明牛可在 `api_shadow` 中随正常任务只读对账，但正式结果仍以浏览器为准；其余未验收项目不得因发布新版本自动切换数据源。`api_preferred` 必须逐项目连续对账通过并经用户明确批准后才能启用。
