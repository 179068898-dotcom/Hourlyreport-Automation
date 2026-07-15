# 授权配置包导入导出设计

## 目标

在 GUI“系统配置”菜单增加“导入授权配置”和“导出授权配置”。管理员在已完成百度账号及 OAuth 授权的电脑上导出一份明文配置包，同事选择该文件后，程序自动将完整配置写入本机正确的 `secrets/secrets.json`，无需手工寻找目录或编辑 JSON。

本功能只处理授权和账号配置，不修改项目配置、Excel、浏览器数据，也不改变日报或小时报执行流程。

## 用户流程

### 导出

1. 用户点击“系统配置 > 导出授权配置”。
2. 用户选择保存位置，默认文件名为 `百度授权配置_YYYYMMDD_HHMMSS.baidu-secrets`。
3. 程序读取当前根目录下的 `secrets/secrets.json`，校验为合法 JSON 后生成配置包。
4. 导出成功后提示保存路径，并明确提醒该文件是包含账号密码和 OAuth Token 的明文敏感文件。

### 导入

1. 用户点击“系统配置 > 导入授权配置”。
2. 用户选择 `.baidu-secrets` 配置包。
3. 程序自动校验并导入，不显示账号数量、目标路径或覆盖确认步骤。
4. 导入成功后关闭导入流程，并自动运行现有“项目配置检查”。
5. 导入失败时显示具体失败原因，并提供“重新选择”和“取消”；选择“重新选择”后重新打开文件选择框。

用户流程中不显示备份和原子替换步骤，但程序内部必须执行这些保护措施。

## 配置包格式

配置包使用 UTF-8 明文 JSON，扩展名为 `.baidu-secrets`：

```json
{
  "format": "baidu-secrets-package-v1",
  "exported_at": "2026-07-15T15:30:00",
  "payload_sha256": "64位小写SHA-256",
  "secrets": {
    "baidu": {},
    "baidu_api": {}
  }
}
```

`secrets` 保存导出电脑上的完整 `secrets.json` 内容，包括所有顶层扩展字段。`payload_sha256` 对规范化后的 `secrets` 对象计算：`json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))` 编码为 UTF-8 后取 SHA-256。

校验和用于发现误选文件、传输损坏或手工误改，不提供防篡改或保密能力。

## 导出规则

- 找不到 `secrets/secrets.json` 时停止并说明路径。
- JSON 无法解析、根节点不是对象、`baidu` 不是对象时停止导出。
- `baidu_api` 可以为空或不存在，以便服务商审核前测试导入导出流程。
- 不打印、记录或弹窗展示任何账号、密码、access token、refresh token 的具体值。
- 不自动把导出文件放进项目根目录，默认打开用户文档目录或上次选择目录。

## 导入规则

- 只接受 `format` 为 `baidu-secrets-package-v1` 的对象。
- `secrets` 必须是对象，`baidu` 必须是对象；存在 `baidu_api` 时也必须是对象。
- 重新计算并严格比对 `payload_sha256`，不一致时拒绝导入。
- 完整覆盖本机 `secrets/secrets.json`，不做字段合并。
- 目标路径固定通过 GUI 的 `credentials_config_path()` 获取，当前为项目根目录下的 `secrets/secrets.json`。
- 目标文件存在时，先静默备份到 `backups/secrets_before_package_import_YYYYMMDD_HHMMSS.json`。
- 先将新配置写入同目录临时文件，刷新并关闭文件后使用 `os.replace()` 原子替换目标文件。
- 任一步骤失败时不得改变原目标文件；错误消息包含可操作原因，不包含敏感值。
- 导入成功后调用现有 `run_environment_preflight()`，由项目配置检查报告缺失或不匹配的账号配置。
- 程序不自动删除用户选择的配置包。导入成功后不显示独立成功弹窗，只写入不含敏感值的日志并立即运行项目配置检查。

## GUI 集成

两个入口同时加入现有标准 `QMenu` 和 `InlineConfigMenu`，菜单顺序为：

1. 项目配置检查
2. 分隔线
3. 导入授权配置
4. 导出授权配置
5. 恢复备份
6. 分隔线
7. 桌面宠物
8. 退出程序

入口沿用当前白色浮层菜单样式，不增加图标、不增加二级菜单。文件选择使用 `QFileDialog`，结果使用现有 `QMessageBox` 风格。

## 模块边界

新增独立模块 `modules/secrets_package.py`：

- `export_secrets_package(secrets_path, output_path) -> dict`
- `import_secrets_package(package_path, secrets_path, backup_dir) -> dict`
- `SecretsPackageError`：所有可展示给用户的预期错误。

模块不依赖 Qt，负责格式、校验、备份和原子覆盖。`gui/main_window.py` 只负责菜单、文件选择、成功提示、失败重试及触发项目配置检查。

## 发布边界

- `.baidu-secrets` 必须加入发布包排除后缀，普通包、内部包和在线更新包都不得意外携带用户导出的配置包。
- 在线更新仍保护 `secrets/`，不会覆盖已经导入的本机配置。
- 配置包不得提交 Git，不得上传 GitHub Release。

## 测试

模块测试覆盖：

- 完整 secrets 导出后可原样导入。
- 导入会完整覆盖而不是合并旧字段。
- 导入前生成备份，备份内容等于原文件。
- 格式错误、JSON 损坏、校验和不一致、`baidu` 结构错误时拒绝导入且目标文件不变。
- 缺少目标文件时能够创建正确目录和文件。
- 导出内容和错误日志不泄露敏感值。
- 发布包过滤器排除 `.baidu-secrets`。

GUI 测试覆盖：

- 标准菜单和内联菜单均出现导入、导出入口。
- 导入成功后调用项目配置检查。
- 导入失败显示原因；选择重新导入会再次打开文件选择框。
- 用户取消文件选择时不修改配置、不启动项目配置检查。

最终运行 `tests/test_basic.py` 全量基础测试，并重新构建 EXE 供用户检查；未经用户确认不生成新的内部发布包。
