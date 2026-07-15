# HERMES 日报自动化执行手册

同步标记：`HERMES-20260710`

适用对象：HERMES（夏思道）及负责代执行日报的内部同事。

## 固定入口

```cmd
run_hermes_daily.bat
run_hermes_daily.bat 2026-07-09
```

不传日期时处理昨天。不得直接拼接 `main.py --mode run-daily`。BAT 会固定根目录和 UTF-8 环境；缺少 `.venv` 时先自动安装；随后运行日报快速 preflight，通过后才执行完整日报。

## 执行顺序

1. 确认 GUI/菜单中的当前项目和目标日期。
2. 确认目标 Excel 已关闭。
3. 确认快商通日报已导出；没有 30 分钟内文件时程序按 0 对话继续。
4. 调用固定 BAT；指定日期时必须使用 `YYYY-MM-DD`。
5. 仅退出码 `0` 视为完成。
6. 核对 `reports/daily_final_run_report.json`、`reports/daily_write_report.json` 和 `logs/run.log`。

## 快速预检

入口内部执行：

```cmd
.venv\Scripts\python.exe main.py --mode preflight --task daily --quick
```

快速预检不扫描整张日报 Excel。新项目、模板变化、结构识别异常或排障时才运行完整日报 preflight。

## 百度稳定性

- 不把表格 DOM 出现当作数据就绪。
- 连续快照的账号集合和指标必须稳定。
- 可识别总计行时，展现、点击、消费必须与账户求和一致。
- `networkidle` 超时后不得使用早期残值。
- 任一来源或稳定性校验失败时，不继续写 Excel。

## 安全边界

- 写入前备份，不重建工作簿。
- 只写扫描识别出的日期、账户和字段区域。
- 不改无关 sheet、公式区、汇总区或截图区。
- 不索要或输出密码。
- 失败后不手工补 Excel。
