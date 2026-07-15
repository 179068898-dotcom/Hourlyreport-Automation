# HERMES 小时报自动化执行手册

同步标记：`HERMES-20260710`

适用对象：HERMES（夏思道）及负责代执行小时报的内部同事。

## 固定入口

```cmd
run_hermes_hourly.bat 11点
run_hermes_hourly.bat 15点
run_hermes_hourly.bat 18点
```

不得直接拼接 `main.py --mode run`。BAT 会固定根目录和 UTF-8 环境；缺少 `.venv` 时先自动安装；随后运行快速 preflight，通过后才执行完整小时报。

## 执行顺序

1. 确认 GUI/菜单中的当前项目。
2. 确认目标 Excel 已关闭。
3. 确认快商通已导出本次文件；没有 30 分钟内文件时程序按 0 对话继续。
4. 调用对应时段的固定 BAT。
5. 仅退出码 `0` 视为完成。
6. 核对 `reports/final_run_report.json`、`reports/write_report.json` 和 `logs/run.log`。

## 快速预检

入口内部执行：

```cmd
.venv\Scripts\python.exe main.py --mode preflight --quick
```

快速预检检查项目配置、Excel 路径、快商通目录、Chrome 9222 和当前项目凭据，不执行耗时的 Excel 全结构扫描。新项目、模板变化或结构异常才使用完整 preflight。

## 安全边界

- Excel 写前先备份，不重建工作簿。
- 只写扫描识别出的目标账户/字段，不改无关区域。
- 只使用 Chrome，不自动降级 Edge。
- 不索要或输出密码。
- 双百度来源必须全部成功；不写部分数据。
- 失败后不手工补 Excel。

## 需要人工介入

遇到验证码、滑块、安全校验、Excel 占用或结构无法识别时停止，报告原因，处理后整次重跑。
