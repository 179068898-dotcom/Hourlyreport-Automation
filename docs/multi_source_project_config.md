# 多百度来源项目配置说明

## 适用场景

一个项目由两个或多个百度管家账号组成，小时报和日报需要依次从每个来源读取展现、点击、消费，再聚合为项目结果写入同一份 Excel。

多来源配置模板：

```text
configs/projects/project_template_multi_source.json
```

## 核心概念

| 配置或报告字段 | 含义 |
|---|---|
| `baidu_sources` | 百度抓数来源列表。每项代表一个百度登录来源。 |
| `source.accounts` | 该来源中允许读取的百度候选账户。候选账户可以多于 Excel 实际写入账户。 |
| `excel_accounts` | Excel 实际写入账户列表。聚合后的 `baidu_account_data.json` / `baidu_daily_data.json` 只保留这些账户。 |
| `accounts` | 现有小时报、日报与商务通合并流程使用的实际账户映射；应与 `excel_accounts` 对应。 |
| `ignored_inactive_accounts` | 候选账户不属于 Excel 写入范围，且展现、点击、消费均为 `0`，按未启用账户记录并忽略。 |
| `skipped_unmapped_accounts` | 候选账户不属于 Excel 写入范围，但存在展现、点击或消费，记录后跳过，不写入 Excel，需人工核对。 |

模板沿用当前运行代码识别的商务通字段名：

| 模板字段 | 业务含义 |
|---|---|
| `kst_ids` | 商务通推广备注 ID。 |
| `kst_names` | 商务通账户名或别名。 |

`baidu_names` 必须填写后台展示的完整账户名。账户匹配必须完整匹配，禁止使用模糊匹配或仅填写名称片段。

## 新增项目步骤

1. 复制 `configs/projects/project_template_multi_source.json`，重命名为新的 `project_id.json`。
2. 修改 `project_id` 与 `project_name`。
3. 填写 `excel.path`、`excel.hourly_sheet`、`excel.daily_sheet`。
4. 填写 `kst.export_dir`。
5. 在 `baidu_sources` 中配置两个或多个来源，并为每个来源填写 `source_id`、`source_name`、`credential_profile` 和候选 `accounts`。
6. 填写 `excel_accounts`，仅列出目标 Excel 中实际存在并允许写入的账户。
7. 填写顶层 `accounts`，仅保留实际写入账户的完整百度/商务通/Excel 映射。
8. 在本机 `secrets/secrets.json` 中配置各来源 `credential_profile` 对应的百度凭据；不要把该文件提交或发送给外部。
9. 先执行配置校验和 doctor。
10. 先执行 `fetch-baidu-auto`，查看多来源报告与聚合账户输出，确认后再执行完整小时报或日报。

## 检查命令

以下命令在目标项目已设为当前项目后执行：

```cmd
.venv\Scripts\python.exe main.py --mode show-project
.venv\Scripts\python.exe main.py --mode validate-project
.venv\Scripts\python.exe main.py --mode doctor
.venv\Scripts\python.exe main.py --mode fetch-baidu-auto --period 15点
.venv\Scripts\python.exe main.py --mode run --period 15点 --yes
.venv\Scripts\python.exe main.py --mode run-daily --yes
```

在运行完整小时报或日报前，至少检查：

- `reports/baidu_multi_source_report.md`
- `reports/baidu_multi_source_report.json`
- 小时报：`reports/baidu_account_data.json`
- 日报：`reports/baidu_daily_data.json`
- `logs/run.log`

## 常见错误

| 问题 | 处理方式 |
|---|---|
| `secrets` 缺少某个来源的 profile | 在本机 `secrets/secrets.json` 添加与 `credential_profile` 完全一致的配置后重新执行 doctor。 |
| `excel.path` 不存在 | 核对实际 Excel 路径后修改项目配置；不要猜测写入目标。 |
| Excel 实际账户名与配置不一致 | 先运行 Excel 结构识别，按实际账户区域修正 `excel_accounts` 与 `accounts`。 |
| 百度账户名使用了模糊名称 | 改为后台显示的完整账户名；禁止通过模糊匹配绕过配置问题。 |
| 候选账户不在 Excel 中 | 这不是配置错误。全零账户进入 `ignored_inactive_accounts`；有量账户进入 `skipped_unmapped_accounts`，需人工核对。 |
| 一个来源抓取失败 | 整个百度步骤失败并中断，不继续写 Excel；查看多来源报告和日志定位来源。 |

## 配置边界

- 模板不得填写真实账号、真实密码或真实 `secrets` 内容。
- `baidu_sources` 描述百度候选抓数范围，`excel_accounts` 描述实际写入范围，两者职责不同。
- 扩展新的多来源项目时，只新增项目配置与本地凭据，不应修改百度登录流程、Excel writer 或商务通统计口径。
