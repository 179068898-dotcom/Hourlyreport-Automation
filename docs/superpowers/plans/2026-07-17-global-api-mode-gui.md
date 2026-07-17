# 全局 API 模式与 GUI 流式状态 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将九个项目统一切换为默认 API 优先、失败自动降级浏览器，并在 GUI 提供全局 B/A 开关、流式日志和新产品名称。

**Architecture:** 在应用配置中持久化全局数据源偏好，并在项目运行配置加载时计算生产任务的有效模式。单来源复用现有 API 路由器；双来源按来源依次 API 读取、统一校验后原子提交，任一来源失败则整项目调用现有浏览器流程。GUI 只管理应用级偏好，所有完整任务入口共享同一配置。

**Tech Stack:** Python 3.11+、PySide6、QProcess、pytest、现有百度 API/Playwright/OpenPyXL pipeline、PyInstaller。

## Global Constraints

- 全程保留现有 `百度数据自动化控制台.exe`、更新包名、GitHub Release tag 和安装目录名。
- 用户可见产品名称使用“蚁之力 · 竞价数据自动化”。
- `A` 默认 API 优先并自动降级；`B` 强制浏览器。
- API 自修复总预算 20 秒，Token 最多刷新一次，网络额外重试两次，完整性额外读取一次。
- 双来源任一 API 来源失败时整项目降级，禁止 API/浏览器混合来源。
- API 与浏览器均失败时停止，不解析、合并或写 Excel。
- 不修改快商通人工导出流程和 Excel 写入边界。
- 不在日志、报告、测试、文档或提交中包含 Token、密钥、密码和完整授权 URL。
- 真实验收只读取 API，不运行真实 `run`、`run-daily`，不写 Excel。
- 用户确认 EXE 效果前不生成内部发布包。

---

### Task 1: 应用级数据源偏好与运行配置覆盖

**Files:**
- Modify: `modules/project_config.py`
- Modify: `configs/app_config.json`
- Test: `tests/test_basic.py`

**Interfaces:**
- Produces: `normalize_data_source_preference(value: Any) -> str`
- Produces: `get_data_source_preference(root: str | Path) -> str`
- Produces: `set_data_source_preference(root: str | Path, preference: str) -> str`
- Produces: 运行配置字段 `baidu.data_source_preference`、`baidu.configured_data_source_mode`、`baidu.data_source_mode`

- [ ] **Step 1: 写入默认值、规范化和持久化失败测试**

在 `tests/test_basic.py` 增加：

```python
def test_global_data_source_preference_defaults_to_api_and_persists(tmp_path):
    from modules.project_config import get_data_source_preference, set_data_source_preference

    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "app_config.json").write_text(
        json.dumps({
            "default_project_id": "demo",
            "projects_dir": "configs/projects",
            "secrets_file": "secrets/secrets.json",
        }),
        encoding="utf-8",
    )

    assert get_data_source_preference(tmp_path) == "api"
    assert set_data_source_preference(tmp_path, "browser") == "browser"
    saved = json.loads((config_dir / "app_config.json").read_text("utf-8"))
    assert saved["baidu_data_source_preference"] == "browser"
    assert saved["default_project_id"] == "demo"
```

再增加运行配置覆盖测试：

```python
def test_runtime_config_uses_global_preference_without_destroying_project_mode():
    from modules.project_config import build_runtime_config_from_project

    project = make_valid_project_config()
    project["baidu"]["data_source_mode"] = "api_shadow"
    project["_app_config"] = {
        "secrets_file": "secrets/secrets.json",
        "baidu_data_source_preference": "browser",
    }
    runtime = build_runtime_config_from_project(project, {})

    assert runtime["baidu"]["data_source_preference"] == "browser"
    assert runtime["baidu"]["configured_data_source_mode"] == "api_shadow"
    assert runtime["baidu"]["data_source_mode"] == "browser"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "global_data_source_preference or runtime_config_uses_global_preference" -q
```

Expected: FAIL，提示偏好函数不存在或运行模式仍来自项目 JSON。

- [ ] **Step 3: 实现最小应用级偏好 API**

在 `modules/project_config.py` 增加：

```python
DATA_SOURCE_PREFERENCES = {"api", "browser"}


def normalize_data_source_preference(value: Any) -> str:
    normalized = str(value or "api").strip().lower()
    return normalized if normalized in DATA_SOURCE_PREFERENCES else "api"


def get_data_source_preference(root: str | Path) -> str:
    return normalize_data_source_preference(
        load_app_config(root).get("baidu_data_source_preference")
    )


def set_data_source_preference(root: str | Path, preference: str) -> str:
    root_path = Path(root)
    app_config = load_app_config(root_path)
    normalized = normalize_data_source_preference(preference)
    app_config["baidu_data_source_preference"] = normalized
    _write_json(root_path / APP_CONFIG_PATH, app_config)
    return normalized
```

在 `build_runtime_config_from_project` 中保留项目原模式并应用全局偏好：

```python
configured_mode = str(project_baidu.get("data_source_mode") or "browser")
preference = normalize_data_source_preference(
    project.get("_app_config", {}).get("baidu_data_source_preference")
)
baidu["configured_data_source_mode"] = configured_mode
baidu["data_source_preference"] = preference
baidu["data_source_mode"] = "api_preferred" if preference == "api" else "browser"
```

在 `configs/app_config.json` 增加：

```json
"baidu_data_source_preference": "api"
```

- [ ] **Step 4: 运行 Task 1 测试**

Run: 同 Step 2。

Expected: PASS。

- [ ] **Step 5: 审查差异并提交 Task 1**

```cmd
git diff --check -- modules/project_config.py configs/app_config.json tests/test_basic.py
git add modules/project_config.py configs/app_config.json tests/test_basic.py
git commit -m "feat: add global Baidu data source preference"
```

---

### Task 2: API 模式预检跳过 Chrome 并检查授权可用性

**Files:**
- Modify: `modules/preflight.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: `config["baidu"]["data_source_preference"]`
- Produces: `check_baidu_api_profiles(root, config) -> dict[str, Any]`
- Produces: 预检报告字段 `api_profiles`

- [ ] **Step 1: 写入 A/B Chrome 行为测试**

```python
def test_preflight_api_preference_skips_chrome_start(tmp_path, monkeypatch):
    from modules.preflight import run_preflight

    project, runtime = make_preflight_project(tmp_path)
    runtime["baidu"]["data_source_preference"] = "api"
    called = []

    def forbidden(*args, **kwargs):
        called.append(True)
        raise AssertionError("A 模式不应提前启动 Chrome")

    report = run_preflight(
        tmp_path,
        project,
        runtime,
        quick=True,
        chrome_ready_func=forbidden,
    )
    assert called == []
    assert any(item.get("skipped") and "API" in item["message"] for item in report["checks"])


def test_preflight_browser_preference_checks_chrome(tmp_path):
    from modules.preflight import run_preflight

    project, runtime = make_preflight_project(tmp_path)
    runtime["baidu"]["data_source_preference"] = "browser"
    called = []

    def ready(*args, **kwargs):
        called.append(True)
        return {"ready": True, "started_new_chrome": False}

    run_preflight(tmp_path, project, runtime, quick=True, chrome_ready_func=ready)
    assert called == [True]
```

- [ ] **Step 2: 写入 API profile 检查测试**

```python
def test_check_baidu_api_profiles_supports_single_and_multi_source(tmp_path):
    from modules.preflight import check_baidu_api_profiles

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "secrets.json").write_text(json.dumps({
        "baidu_api": {
            "source_a": {"access_token": "token-a", "refresh_token": "refresh-a"},
            "source_b": {"access_token": "token-b", "refresh_token": "refresh-b"},
        }
    }), encoding="utf-8")
    config = {
        "credentials_path": "secrets/secrets.json",
        "baidu": {"data_source_preference": "api"},
        "baidu_sources": [
            {"source_id": "a", "api_profile": "source_a"},
            {"source_id": "b", "api_profile": "source_b"},
        ],
    }
    report = check_baidu_api_profiles(tmp_path, config)
    assert report["passed"] is True
    assert report["required_profiles"] == ["source_a", "source_b"]
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "preflight_api_preference or preflight_browser_preference or check_baidu_api_profiles" -q
```

Expected: FAIL，A 模式仍调用 Chrome，API profile 检查函数不存在。

- [ ] **Step 4: 实现模式感知预检**

在 `modules/preflight.py`：

```python
def _api_profiles_for_config(config: dict[str, Any]) -> list[str]:
    sources = config.get("baidu_sources") or []
    if sources:
        return list(dict.fromkeys(
            str(source.get("api_profile") or "").strip()
            for source in sources
            if str(source.get("api_profile") or "").strip()
        ))
    profile = str(config.get("baidu", {}).get("api_profile") or "").strip()
    return [profile] if profile else []
```

`check_baidu_api_profiles` 只返回安全布尔字段，不返回 Token。`run_preflight` 在 `api` 时添加通过且 `skipped=True` 的 Chrome 检查项，并附加 API profile 检查。API profile 缺失时记录“本次将使用浏览器降级”，但不让预检失败；浏览器用户名密码检查仍保持硬校验，确保降级通道可用。

- [ ] **Step 5: 运行 Task 2 测试**

Run: 同 Step 3。

Expected: PASS。

- [ ] **Step 6: 审查差异并提交 Task 2**

```cmd
git diff --check -- modules/preflight.py tests/test_basic.py
git add modules/preflight.py tests/test_basic.py
git commit -m "feat: defer Chrome preflight for API mode"
```

---

### Task 3: 双来源 API 原子合并与整项目浏览器降级

**Files:**
- Modify: `modules/baidu_multi_source.py`
- Modify: `modules/baidu_data_source.py`
- Modify: `modules/project_config.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: `resolve_baidu_sources(config)`、`aggregate_baidu_source_reports(config, source_reports, period, target_date, output_source, task)`
- Produces: `fetch_baidu_multi_source_api(config, root, logger, api_fetcher, task, period, target_date, clock, sleep) -> tuple[dict[str, Any] | None, int, list[str], str | None]`
- Produces: 来源运行配置中的 `baidu.api_profile`

- [ ] **Step 1: 写入来源 profile 注入测试**

```python
def test_source_runtime_config_copies_api_profile():
    from modules.baidu_multi_source import build_source_runtime_config

    runtime = build_source_runtime_config(
        {"baidu": {}, "accounts": {}},
        {
            "source_id": "a",
            "credential_profile": "browser_a",
            "api_profile": "api_a",
            "accounts": [{
                "standard_name": "账户A",
                "baidu_names": ["账户A"],
                "excel_name": "账户A",
                "kst_ids": ["1"],
                "kst_names": ["账户A"],
            }],
        },
    )
    assert runtime["baidu"]["credential_profile"] == "browser_a"
    assert runtime["baidu"]["api_profile"] == "api_a"
```

- [ ] **Step 2: 写入双来源成功和失败原子性测试**

```python
def test_api_preferred_multi_source_commits_only_after_all_sources_pass(tmp_path):
    from modules.baidu_data_source import fetch_baidu_resilient_hourly

    config = make_two_source_runtime_config()
    calls = []

    def api_fetcher(*, config, commit_standard_report, **kwargs):
        calls.append((config["baidu_source"]["source_id"], commit_standard_report))
        account = next(iter(config["accounts"]))
        return {
            "date": "2026-07-17",
            "period": "18点",
            "accounts": {account: {"展现": 1, "点击": 1, "消费": 1.0}},
            "errors": [],
        }

    result = fetch_baidu_resilient_hourly(
        config, tmp_path, NullLogger(), "18点",
        api_fetcher=api_fetcher,
        browser_fetcher=lambda **kwargs: pytest.fail("API 成功不应调用浏览器"),
    )
    assert calls == [("a", False), ("b", False)]
    assert result["data_source"] == "api"
    assert (tmp_path / "reports" / "baidu_account_data.json").exists()
```

```python
def test_api_preferred_multi_source_failure_discards_partial_and_falls_back(tmp_path):
    from modules.baidu_data_source import fetch_baidu_resilient_hourly

    standard = tmp_path / "reports" / "baidu_account_data.json"
    standard.parent.mkdir()
    standard.write_text('{"sentinel": true}', encoding="utf-8")
    browser_calls = []

    def api_fetcher(*, config, **kwargs):
        if config["baidu_source"]["source_id"] == "b":
            raise RuntimeError("source b failed")
        account = next(iter(config["accounts"]))
        return {"accounts": {account: {"展现": 1, "点击": 1, "消费": 1.0}}, "errors": []}

    def browser_fetcher(**kwargs):
        browser_calls.append(True)
        return {"accounts": {"全部": {"展现": 2, "点击": 2, "消费": 2.0}}, "errors": []}

    result = fetch_baidu_resilient_hourly(
        make_two_source_runtime_config(), tmp_path, NullLogger(), "18点",
        api_fetcher=api_fetcher,
        browser_fetcher=browser_fetcher,
        sleep=lambda _: None,
    )
    assert browser_calls == [True]
    assert result["data_source"] == "browser_fallback"
    assert "sentinel" not in standard.read_text("utf-8")
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "source_runtime_config_copies_api_profile or api_preferred_multi_source" -q
```

Expected: FAIL，来源没有 API profile，路由器仍触发 `multi_source_api_guard`。

- [ ] **Step 4: 实现共享截止时间和双来源 API 收集**

在 `modules/baidu_data_source.py` 重构 `_api_attempts`，允许传入整个项目共享的 `started` 和 `deadline`。每个来源使用独立 `task_context`，但共享截止时间：

```python
def _api_attempts(
    *,
    api_fetcher: Callable[..., dict[str, Any]],
    api_kwargs: dict[str, Any],
    commit_standard_report: bool,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    logger,
    started: float | None = None,
    deadline: float | None = None,
) -> tuple[dict[str, Any] | None, int, list[str], str | None]:
    started_at = clock() if started is None else started
    deadline_at = started_at + API_REPAIR_BUDGET_SECONDS if deadline is None else deadline
```

新增双来源收集函数：

```python
def fetch_baidu_multi_source_api(
    *,
    config: dict[str, Any],
    root: Path,
    logger,
    api_fetcher: Callable[..., dict[str, Any]],
    task: str,
    period: str | None,
    target_date: str | None,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> tuple[dict[str, Any] | None, int, list[str], str | None]:
    started = clock()
    deadline = started + API_REPAIR_BUDGET_SECONDS
    source_reports = []
    total_attempts = 0
    all_actions = []
    for source in resolve_baidu_sources(config):
        source_config = build_source_runtime_config(config, source, task=task)
        report, attempts, actions, failure = _api_attempts(
            api_fetcher=api_fetcher,
            api_kwargs=source_kwargs,
            commit_standard_report=False,
            started=started,
            deadline=deadline,
            clock=clock,
            sleep=sleep,
            logger=logger,
        )
        total_attempts += attempts
        all_actions.extend(actions)
        if report is None:
            return None, total_attempts, list(dict.fromkeys(all_actions)), failure
        source_reports.append({"source_id": source["source_id"], "source_name": source["source_name"], "report": report})
    aggregated = aggregate_baidu_source_reports(
        config,
        source_reports,
        period=period,
        target_date=target_date,
        output_source="baidu_open_api_multi_source",
        task=task,
    )
    if aggregated.get("errors"):
        return None, total_attempts, list(dict.fromkeys(all_actions)), "integrity_error"
    _write_json_atomic(standard_path, aggregated)
    return aggregated, total_attempts, list(dict.fromkeys(all_actions)), None
```

替换 `_fetch_resilient` 中的 `multi_source_api_guard`。API 双来源失败后只调用一次顶层 `browser_fetcher`，由现有 `fetch_baidu_auto` / `fetch_baidu_daily` 完成双来源浏览器读取和聚合。

- [ ] **Step 5: 放开已经实现的双来源开发模式校验**

删除 `validate_project_config` 中“双来源必须 browser”的旧保护，但继续校验每个来源的 `source_id`、`credential_profile`、`api_profile` 和账户配置。项目 JSON 仍可保留原 `browser` 值，因为生产有效模式来自应用级偏好。

- [ ] **Step 6: 运行 Task 3 测试和既有双来源测试**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "multi_source or baidu_resilient or api_preferred" -q
```

Expected: PASS。

- [ ] **Step 7: 审查差异并提交 Task 3**

```cmd
git diff --check -- modules/baidu_multi_source.py modules/baidu_data_source.py modules/project_config.py tests/test_basic.py
git add modules/baidu_multi_source.py modules/baidu_data_source.py modules/project_config.py tests/test_basic.py
git commit -m "feat: add atomic multi-source API fallback"
```

---

### Task 4: 无缓冲逐行日志和 API 阶段事件

**Files:**
- Modify: `gui/command_builder.py`
- Modify: `gui/task_runner.py`
- Modify: `gui/main_window.py`
- Modify: `modules/baidu_data_source.py`
- Modify: `modules/baidu_report_api.py`
- Modify: `modules/run_pipeline.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Produces: `split_stream_output(pending: str, chunk: str, final: bool = False) -> tuple[list[str], str]`
- Produces: 安全阶段日志 `[数据源]`、`[API]`、`[降级]`、`[浏览器]`

- [ ] **Step 1: 写入命令、环境和分块测试**

```python
def test_gui_commands_use_unbuffered_python(tmp_path):
    from gui.command_builder import build_hourly_command

    command = build_hourly_command(tmp_path, "18点", project_id="kunming_niu")
    assert command[1] == "-u"


def test_stream_output_buffers_partial_utf8_lines():
    from gui.task_runner import split_stream_output

    lines, pending = split_stream_output("", "[API] 正在读")
    assert lines == []
    assert pending == "[API] 正在读"
    lines, pending = split_stream_output(pending, "取数据\n[通过] 完成\n")
    assert lines == ["[API] 正在读取数据", "[通过] 完成"]
    assert pending == ""
    lines, pending = split_stream_output("末行", "", final=True)
    assert lines == ["末行"]
    assert pending == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "unbuffered_python or stream_output_buffers" -q
```

Expected: FAIL。

- [ ] **Step 3: 实现无缓冲命令和完整行缓冲**

`gui/command_builder.py` 的三个 Python 命令均使用：

```python
command = [
    str(python_exe(root)),
    "-u",
    str(_main_py(root)),
    "--mode",
    "run",
]
```

`gui/task_runner.py` 增加：

```python
def split_stream_output(pending: str, chunk: str, final: bool = False) -> tuple[list[str], str]:
    text = pending + chunk
    parts = text.splitlines(keepends=True)
    lines = [part.rstrip("\r\n") for part in parts if part.endswith(("\n", "\r"))]
    remainder = "" if not parts or parts[-1].endswith(("\n", "\r")) else parts[-1]
    if final and remainder:
        lines.append(remainder)
        remainder = ""
    return lines, remainder
```

`build_process_environment` 增加 `PYTHONUNBUFFERED=1`。`QtTaskRunner` 保存 `_pending_output`，`_read_output` 只发送完整行，`_handle_finished` 先冲刷末行再发 `finished`。

- [ ] **Step 4: 增加数据源安全阶段日志**

在路由器中输出：

```python
_log(logger, "info", "[数据源] 当前模式：%s", "API 优先" if mode == "api_preferred" else "浏览器")
_log(logger, "info", "[API] 正在读取%s百度数据", config.get("project_name") or config.get("project_id"))
_log(logger, "warning", "[降级] API 读取仍未完成，准备切换浏览器：%s", api_failure)
_log(logger, "info", "[浏览器] 正在启动浏览器降级流程")
```

双来源输出 `[API 1/2]`、`[API 2/2]`。`run_pipeline.py` 成功后输出实际来源。所有错误只记录类别和安全摘要，不记录请求参数。

- [ ] **Step 5: 更新 GUI 阶段与宠物事件识别**

`infer_stage` 和 `infer_pet_event` 识别 `[API]`、`[降级]`、`[浏览器]`。API 成功直接进入 `baidu_ready`；只有出现 `[浏览器]` 后才显示账号切换提示。

- [ ] **Step 6: 运行 Task 4 测试**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "task_runner or command_builder or infer_stage or infer_pet_event or resilient" -q
```

Expected: PASS。

- [ ] **Step 7: 审查差异并提交 Task 4**

```cmd
git diff --check -- gui/command_builder.py gui/task_runner.py gui/main_window.py modules/baidu_data_source.py modules/baidu_report_api.py modules/run_pipeline.py tests/test_basic.py
git add gui/command_builder.py gui/task_runner.py gui/main_window.py modules/baidu_data_source.py modules/baidu_report_api.py modules/run_pipeline.py tests/test_basic.py
git commit -m "feat: stream API routing progress to GUI"
```

---

### Task 5: B/A 滑动开关、产品更名和板块文案

**Files:**
- Modify: `gui/main_window.py`
- Modify: `gui/app.py`
- Modify: `gui/desktop_pet.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: `get_data_source_preference`、`set_data_source_preference`
- Produces: `DataSourceModeControl.preference_changed(str)`
- Produces: `InlineConfigMenu.data_source_preference_requested(str)`

- [ ] **Step 1: 写入 GUI 状态和更名测试**

```python
def test_gui_uses_new_visible_product_name_and_short_section_titles(gui_window):
    window = gui_window
    assert window.windowTitle() == "蚁之力 · 竞价数据自动化"
    assert window.title_label.text() == "蚁之力 · 竞价数据自动化"
    assert window.hourly_title.text() == "小时报"
    assert window.daily_title.text() == "日报"


def test_data_source_control_defaults_to_api_and_emits_browser(qtbot):
    from gui.main_window import DataSourceModeControl

    control = DataSourceModeControl()
    qtbot.addWidget(control)
    assert control.preference() == "api"
    with qtbot.waitSignal(control.preference_changed) as signal:
        control.set_preference("browser")
    assert signal.args == ["browser"]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "new_visible_product_name or data_source_control" -q
```

Expected: FAIL。

- [ ] **Step 3: 实现紧凑 B/A 分段滑动控件**

在 `gui/main_window.py` 增加独立 `DataSourceModeControl`，复用 `SlidingProjectModeControl` 的 `QPropertyAnimation` 模式：

```python
class DataSourceModeControl(QFrame):
    preference_changed = Signal(str)

    def preference(self) -> str:
        return self._preference

    def set_preference(self, preference: str, animate: bool = True, emit: bool = True) -> None:
        normalized = "browser" if preference == "browser" else "api"
        changed = normalized != self._preference
        self._preference = normalized
        self.browser_button.setChecked(normalized == "browser")
        self.api_button.setChecked(normalized == "api")
        self.animation.stop()
        target = self._target_geometry(normalized)
        if animate and self.isVisible():
            self.animation.setStartValue(self.indicator.geometry())
            self.animation.setEndValue(target)
            self.animation.start()
        else:
            self.indicator.setGeometry(target)
        if emit and changed:
            self.preference_changed.emit(normalized)
```

控件左侧 `B`、右侧 `A`，固定高度与菜单行一致。`InlineConfigMenu` 顶部加入控件，`sync` 签名改为：

```python
def sync(self, pet_mode: str, pet_scale: float, data_source_preference: str) -> None:
```

主窗口在初始化时读取偏好，连接保存函数。任务运行时禁用，结束后恢复；切换只影响下一次任务。

- [ ] **Step 4: 完成用户可见更名**

替换窗口标题、QApplication 名称、托盘提示、桌面宠物提示、启动错误标题和左侧板块标题。不得替换 `APP_EXE_NAME`、构建脚本中的 EXE 名或更新资产名。

- [ ] **Step 5: 运行 GUI 相关测试**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "desktop_gui or main_window or data_source_control or application_name" -q
```

Expected: PASS。

- [ ] **Step 6: 审查差异并提交 Task 5**

```cmd
git diff --check -- gui/main_window.py gui/app.py gui/desktop_pet.py tests/test_basic.py
git add gui/main_window.py gui/app.py gui/desktop_pet.py tests/test_basic.py
git commit -m "feat: add global API browser switch to GUI"
```

---

### Task 6: 十一个授权的批量只读就绪检查

**Files:**
- Create: `modules/baidu_api_readiness.py`
- Modify: `main.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Produces: `run_baidu_api_readiness(root, logger, fetch_func=fetch_baidu_api_hourly) -> dict[str, Any]`
- Produces: 显式开发入口 `main.py --mode test-baidu-api-readiness`
- Produces: `reports/baidu_api_readiness_report.json`

- [ ] **Step 1: 写入九项目十一 profile 枚举测试**

```python
def test_api_readiness_checks_every_single_and_multi_source(tmp_path, monkeypatch):
    from modules.baidu_api_readiness import run_baidu_api_readiness

    write_readiness_project_fixtures(tmp_path)
    seen = []

    def fetch_func(*, config, commit_standard_report, **kwargs):
        seen.append(config["baidu"]["api_profile"])
        assert commit_standard_report is False
        account = next(iter(config["accounts"]))
        return {"accounts": {account: {"展现": 0, "点击": 0, "消费": 0.0}}, "errors": []}

    report = run_baidu_api_readiness(tmp_path, NullLogger(), fetch_func=fetch_func)
    assert report["passed"] is True
    assert report["profile_count"] == 11
    assert len(seen) == 11
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "api_readiness" -q
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现只读批量检查**

`run_baidu_api_readiness`：

1. 使用 `list_projects` 排除模板和演示项目。
2. 对单来源直接构建 runtime；对双来源使用 `resolve_baidu_sources` 和 `build_source_runtime_config`。
3. 每个 profile 调用生产 API 读取器，但固定 `commit_standard_report=False`。
4. 记录项目、来源、profile、账户数、通过状态和安全错误类别。
5. 报告原子写入 `reports/baidu_api_readiness_report.json`。
6. 不调用浏览器、不调用快商通、不调用 Excel。

`main.py` 增加显式模式，并在失败时返回退出码 1。

- [ ] **Step 4: 运行 Task 6 测试**

Run: 同 Step 2。

Expected: PASS。

- [ ] **Step 5: 审查差异并提交 Task 6**

```cmd
git diff --check -- modules/baidu_api_readiness.py main.py tests/test_basic.py
git add modules/baidu_api_readiness.py main.py tests/test_basic.py
git commit -m "feat: add read-only API readiness audit"
```

---

### Task 7: 文档与固定入口规则同步

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `xia_sidao使用说明.md`
- Modify: `docs/hermes_hourly_sop.md`
- Modify: `docs/hermes_daily_sop.md`
- Test: `tests/test_basic.py`

**Interfaces:**
- Documents: 全局 A/B 语义、默认 A、HERMES 共享偏好、双来源原子降级、显式就绪检查命令

- [ ] **Step 1: 更新旧断言测试**

把“昆明 `api_shadow`、其余项目 browser 决定生产通道”的断言改为：项目配置保留兼容值，但完整生产任务的有效通道由 `configs/app_config.json` 的全局偏好决定。增加文档必须包含以下词组的断言：

```python
for text in [
    "蚁之力 · 竞价数据自动化",
    "baidu_data_source_preference",
    "API 优先",
    "强制浏览器",
    "整项目降级",
    "test-baidu-api-readiness",
]:
    assert text in combined_docs
```

- [ ] **Step 2: 同步文档**

明确写入：

- 十一个授权已导入，但发布前仍需只读就绪检查。
- `A` 缺失授权会浏览器降级，不会使用部分 API 数据。
- `B` 是紧急回退入口。
- HERMES BAT 不改名、不改调用参数，自动读取同一应用配置。
- API 模式预检不提前启动 Chrome，浏览器降级时才延迟启动。
- 不允许在普通 GUI 中调用开发探测入口。

- [ ] **Step 3: 运行文档入口测试**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "documentation or hermes or api_mode" -q
```

Expected: PASS。

- [ ] **Step 4: 审查差异并提交 Task 7**

```cmd
git diff --check -- AGENTS.md README.md xia_sidao使用说明.md docs/hermes_hourly_sop.md docs/hermes_daily_sop.md tests/test_basic.py
git add AGENTS.md README.md xia_sidao使用说明.md docs/hermes_hourly_sop.md docs/hermes_daily_sop.md tests/test_basic.py
git commit -m "docs: document global API preference and fallback"
```

---

### Task 8: 全量验证、真实只读验收和 EXE 构建

**Files:**
- Verify only: source tree and test suite
- Build output: `百度数据自动化控制台.exe`
- Runtime report: `reports/baidu_api_readiness_report.json`

**Interfaces:**
- Consumes: `test-baidu-api-readiness`
- Produces: 用户可启动检查的最新 EXE；不生成内部 ZIP

- [ ] **Step 1: 运行静态差异检查**

```cmd
git diff --check
```

Expected: 无输出，退出码 0。

- [ ] **Step 2: 运行 API/预检/GUI 重点测试**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "api or preflight or multi_source or task_runner or desktop_gui" -q
```

Expected: 全部 PASS。

- [ ] **Step 3: 运行全量基础测试**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py
```

Expected: 全部 PASS。

- [ ] **Step 4: 执行十一个授权的真实只读检查**

```cmd
.venv\Scripts\python.exe main.py --mode test-baidu-api-readiness
```

Expected:

- 退出码 0。
- `reports/baidu_api_readiness_report.json` 的 `passed` 为 `true`。
- `profile_count` 为 `11`。
- 不产生 Excel 备份，不修改任何目标 Excel。

若任一 profile 失败，只修复授权映射或 API 路由；不得通过真实小时报/日报写入来试错。

- [ ] **Step 5: 验证浏览器整项目降级**

使用测试注入让双来源第二个 API 来源失败，断言浏览器顶层 fetcher 只调用一次、最终来源为 `browser_fallback`、API 临时报告未作为标准结果提交。不得人为断网后运行真实 Excel 流程。

- [ ] **Step 6: 构建最新 EXE**

```cmd
build_desktop_exe.bat
```

Expected: 根目录或 `dist` 中生成现有兼容名称 `百度数据自动化控制台.exe`，构建过程无控制台错误。

- [ ] **Step 7: 启动 EXE 做 GUI 人工检查**

检查：

- 标题为“蚁之力 · 竞价数据自动化”。
- 左侧标题为“小时报”和“日报”。
- 系统配置 B/A 开关默认 A、可滑动、可持久化。
- 任务运行时开关禁用。
- API 日志逐行即时出现，无乱码、半行和敏感信息。
- 正常 API 路径不启动 Chrome。

- [ ] **Step 8: 汇报验证结果，等待用户确认**

列出修改文件、重点测试数量、十一授权只读检查结果和 EXE 路径。用户确认 GUI 前不运行 `tools/build_release.py --internal`，不生成内部发布包。
