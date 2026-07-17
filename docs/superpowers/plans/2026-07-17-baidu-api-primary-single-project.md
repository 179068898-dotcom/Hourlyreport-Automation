# 百度 API 单项目主通道实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为单项目小时报和日报实现可自动刷新、可自修复、可影子对账、失败时自动降级浏览器的百度 API 主通道，并提供剩余授权文件的自动 profile 匹配能力。

**Architecture:** 在现有 pipeline 的 `fetch_baidu_func` 边界前增加数据源路由器。SCF 保存百度 secretKey 并代理 refreshToken 刷新；桌面端使用独立 HMAC 客户端密钥调用刷新接口，原子更新单个 API profile。API 成功后生成现有标准百度报告，失败时调用原浏览器抓数函数，Excel 后半段不改。

**Tech Stack:** Python 3.11 desktop runtime、Python 3.6 SCF runtime、标准库 `urllib`/`hmac`/`hashlib`/`msvcrt`、pytest、现有百度 API 与 Playwright 模块。

## Global Constraints

- 默认项目模式必须保持 `browser`，升级程序不得自动切换现有项目的数据源。
- 只有 `api_shadow` 和 `api_preferred` 可以调用生产 API 路由。
- API 自修复总预算固定为 20 秒。
- accessToken 安全刷新窗口固定为到期前 10 分钟。
- 网络或 HTTP 5xx 最多额外重试两次；完整性错误最多额外读取一次；Token 刷新最多一次。
- SCF 刷新路径固定为 `/baidu/oauth/refresh`，百度上游地址固定为 `https://u.baidu.com/oauth/refreshToken`。
- 百度 secretKey 只能存在于 SCF 环境变量，不得写入桌面 secrets、日志、报告、测试样例或发布包。
- API 与浏览器都失败时必须停止，不得调用 Excel 写入。
- API 临时失败结果不得覆盖上一次成功的标准报告。
- 沈阳双来源与多项目并行不在本计划投入生产；它们在单项目验收后使用独立计划推进。
- 不得回滚当前工作区已有 GUI、图标、Excel metadata 或测试改动。

---

### Task 1: SCF 安全刷新接口

**Files:**
- Modify: `cloud/baidu_oauth_callback/index.py`
- Modify: `cloud/baidu_oauth_callback/app.py`
- Modify: `cloud/baidu_oauth_callback/README.md`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: `BAIDU_APP_ID`、`BAIDU_SECRET_KEY`、`BAIDU_REFRESH_CLIENT_KEY`、HTTP JSON body。
- Produces: `process_refresh_request(payload, headers, config, transport=_post_json) -> dict` 和 `refresh_handler(event, context) -> SCF response`。

- [ ] **Step 1: 写 SCF 刷新失败测试**

在 `tests/test_basic.py` 增加以下行为测试：

```python
def test_baidu_oauth_refresh_requires_valid_hmac_and_never_returns_secret_key(monkeypatch):
    callback = load_callback_module()
    config = {
        "app_id": "app-1",
        "secret_key": "server-secret-key-123456",
        "refresh_client_key": "client-key",
        "refresh_max_timestamp_skew_seconds": 300,
    }
    payload = {"appId": "app-1", "userId": 123, "refreshToken": "old.refresh.token"}
    headers = signed_refresh_headers(payload, "client-key", timestamp=1_800_000_000)
    result = callback.process_refresh_request(
        payload,
        headers,
        config,
        transport=lambda url, body, timeout: {
            "code": 0,
            "message": "success",
            "data": {
                "accessToken": "new.access.token",
                "refreshToken": "new.refresh.token",
                "expiresTime": "2026-07-18 09:00:00",
                "refreshExpiresTime": "2026-08-16 09:00:00",
                "expiresIn": 86400,
                "refreshExpiresIn": 2592000,
            },
        },
        now_timestamp=1_800_000_000,
    )
    assert result["access_token"] == "new.access.token"
    assert "secret_key" not in json.dumps(result)
```

另测缺失签名、过期时间戳、错误 appId、上游非零 code、GET 刷新路径和未知路径均返回安全错误。

- [ ] **Step 2: 运行测试并确认 RED**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "oauth_refresh" -q
```

预期：因 `process_refresh_request` 或刷新路由不存在而失败。

- [ ] **Step 3: 实现固定刷新协议**

在 `index.py` 中加入：

```python
REFRESH_TOKEN_URL = "https://u.baidu.com/oauth/refreshToken"

def _refresh_signature(timestamp: str, payload: dict, client_key: str) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    message = f"{timestamp}\n{canonical}".encode("utf-8")
    return hmac.new(client_key.encode("utf-8"), message, hashlib.sha256).hexdigest()
```

`process_refresh_request` 必须验证：body 为对象、字段集合完整、appId 匹配、userId 为正整数、Token 非空、时间戳在 300 秒内、HMAC 使用 `compare_digest`。上游请求必须精确为：

```python
{
    "appId": config["app_id"],
    "refreshToken": payload["refreshToken"],
    "secretKey": config["secret_key"],
    "userId": int(payload["userId"]),
}
```

只返回新的令牌和有效期字段，不回显 secretKey、客户端密钥或原始请求。

客户端请求头固定为 `X-Baidu-Refresh-Timestamp` 和 `X-Baidu-Refresh-Signature`。Web 函数和普通事件函数都必须把这两个请求头、POST body 和路径传入同一刷新处理函数。

在 `app.py` 中只允许 `POST /baidu/oauth/refresh`，限制 JSON body 为 64 KiB，并继续支持原健康检查与 OAuth callback GET。

- [ ] **Step 4: 运行 SCF 测试并确认 GREEN**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "oauth_refresh or oauth_callback" -q
```

预期：刷新与既有回调测试全部通过。

- [ ] **Step 5: 同步 SCF 文档**

在 README 增加环境变量：

```text
BAIDU_REFRESH_CLIENT_KEY=由管理员生成的独立随机密钥，不得等于 BAIDU_SECRET_KEY
BAIDU_REFRESH_MAX_TIMESTAMP_SKEW_SECONDS=300
```

明确 API 网关不得记录请求 body 和刷新请求头。

- [ ] **Step 6: 提交 Task 1**

```cmd
git add cloud/baidu_oauth_callback/index.py cloud/baidu_oauth_callback/app.py cloud/baidu_oauth_callback/README.md tests/test_basic.py
git commit -m "Add secure Baidu token refresh endpoint"
```

---

### Task 2: 本地 Token 管理器与原子 profile 更新

**Files:**
- Create: `modules/baidu_token_manager.py`
- Modify: `secrets/secrets.example.json`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: runtime config、`secrets/secrets.json` 中的 `baidu_api_gateway` 和目标 `baidu_api` profile。
- Produces: `ensure_valid_access_token(config, root, api_profile, now=None, transport=None, force_refresh=False) -> tuple[str, dict]`。

- [ ] **Step 1: 写 Token 管理器失败测试**

覆盖六个独立测试，测试名和断言固定如下：

- `test_token_manager_keeps_valid_token_without_refresh`：到期时间晚于当前时间 10 分钟以上，transport 一旦调用就抛出 AssertionError，函数返回原 accessToken 和 `token_refresh=not_needed`。
- `test_token_manager_refreshes_within_ten_minute_window`：到期时间只剩 5 分钟，断言 transport 收到 refresh URL、appId、userId、refreshToken 及 HMAC 请求头，函数返回新 accessToken。
- `test_token_manager_rotates_both_tokens_atomically`：刷新响应同时包含新 accessToken 和 refreshToken，重新读取 secrets 后两个字段都已更新，且生成一份刷新前备份。
- `test_token_manager_refresh_failure_preserves_original_secrets`：transport 抛出网络错误，断言 secrets 原始字节完全不变且没有遗留 `.tmp` 文件。
- `test_token_manager_merge_update_preserves_other_profiles`：目标 profile 更新期间模拟另一个 profile 已变更，断言最终文件同时保留另一个 profile 的新值和目标 profile 的刷新值。
- `test_token_manager_report_never_contains_credentials`：序列化返回 metadata 和异常文本，断言不包含 accessToken、refreshToken、client key 或密码假值。

测试 secrets 结构固定为：

```json
{
  "baidu_api_gateway": {
    "refresh_url": "https://example.invalid/baidu/oauth/refresh",
    "client_key": "fake-client-key",
    "app_id": "app-1"
  },
  "baidu_api": {
    "kunming_niu_baidu": {
      "app_id": "app-1",
      "user_id": 123,
      "access_token": "old.access.token",
      "refresh_token": "old.refresh.token",
      "expires_time": "2026-07-17 09:05:00",
      "refresh_expires_time": "2026-08-16 09:00:00"
    }
  }
}
```

- [ ] **Step 2: 运行测试并确认 RED**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "token_manager" -q
```

- [ ] **Step 3: 实现 TokenManager**

`modules/baidu_token_manager.py` 必须定义 `BaiduTokenError(category: str, message: str, reauthorization_required: bool = False)`，并实现接口 `ensure_valid_access_token(config: dict[str, Any], root: Path, api_profile: str, now: datetime | None = None, transport: Callable | None = None, force_refresh: bool = False) -> tuple[str, dict[str, Any]]`。`force_refresh=True` 时忽略 accessToken 的本地到期时间并刷新一次，用于处理百度错误码 `894061`。

使用 HMAC-SHA256 调用 SCF。先以 `a+b` 打开 `secrets.json.lock`，文件为空时写入一个字节并 flush，再使用 `msvcrt.locking` 锁定第一个字节；获得锁后重新读取 secrets，只合并目标 profile，备份名固定为 `backups/secrets_before_token_refresh_{profile}_{timestamp}.json`，临时文件写完后 `os.replace`。异常时删除临时文件并保留原文件，finally 中解锁并关闭句柄。

返回 metadata 只允许包含 `api_profile`、`token_refresh`、`expires_time` 和安全错误分类。

- [ ] **Step 4: 运行 Token 测试并确认 GREEN**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "token_manager" -q
```

- [ ] **Step 5: 更新示例配置并提交**

示例中只放空值，不放真实 URL 或密钥：

```json
"baidu_api_gateway": {"refresh_url": "", "client_key": "", "app_id": ""}
```

```cmd
git add modules/baidu_token_manager.py secrets/secrets.example.json tests/test_basic.py
git commit -m "Add atomic Baidu OAuth token manager"
```

---

### Task 3: API 生产读取适配器

**Files:**
- Modify: `modules/baidu_report_api.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: `ensure_valid_access_token`、项目账户配置、日期和时段。
- Produces: `fetch_baidu_api_hourly(config, root, logger, period, token_provider=ensure_valid_access_token, commit_standard_report=True)`、`fetch_baidu_api_daily(config, root, logger, target_date, token_provider=ensure_valid_access_token, commit_standard_report=True)`，返回与浏览器读取器兼容的报告。

- [ ] **Step 1: 写标准输出失败测试**

新增测试证明：

```python
hourly = fetch_baidu_api_hourly(config, tmp_path, logger, "15点", token_provider=fake_token)
assert hourly["source"] == "baidu_open_api"
assert hourly["period"] == "15点"
assert hourly["accounts"]["银康01"]["消费"] == 50.0
assert json.loads((tmp_path / "reports/baidu_account_data.json").read_text("utf-8"))["accounts"] == hourly["accounts"]

daily = fetch_baidu_api_daily(config, tmp_path, logger, "2026-07-16", token_provider=fake_token)
assert daily["date"] == "2026-07-16"
assert (tmp_path / "reports/baidu_daily_data.json").exists()
```

另测日期不一致、缺失账户、未知账户、重复推广 ID、负数、非有限数、汇总差异和完整全零账户。

增加错误码分类测试：`894061` 必须使用 `force_refresh=True` 刷新一次并重试；`894062`、`894063`、`894064` 必须返回 `reauthorization_required`；`89405`、`89406`、`89407` 必须返回安全的 `authorization_error`，不得输出百度原始 Token。

- [ ] **Step 2: 运行测试并确认 RED**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "api_hourly or api_daily or api_integrity" -q
```

- [ ] **Step 3: 重构 probe 公共核心**

保留 `fetch_baidu_api_probe` 行为，提取无生产写入副作用的公共请求函数。生产适配器只有在校验全部通过且 `commit_standard_report=True` 时，才通过临时文件和 `os.replace` 更新标准报告。`api_shadow` 必须传 `commit_standard_report=False`，防止 API 临时结果覆盖浏览器正式结果。失败结果写入 `reports/baidu_api_attempt_report.json`，不得覆盖标准报告。

API 请求必须使用 Token 管理器返回的 accessToken；报告不得包含 Token。小时报仍请求当天 `DAY` 累计值并保留传入时段，日报请求目标日期完整值。

- [ ] **Step 4: 运行 API 测试并确认 GREEN**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "baidu_api" -q
```

- [ ] **Step 5: 提交 Task 3**

```cmd
git add modules/baidu_report_api.py tests/test_basic.py
git commit -m "Adapt Baidu API reports for production pipelines"
```

---

### Task 4: API 自修复、影子模式与浏览器降级路由

**Files:**
- Create: `modules/baidu_data_source.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: API 小时/日报适配器和现有 `fetch_baidu_auto`/`fetch_baidu_daily`。
- Produces: `fetch_baidu_resilient_hourly(config, root, logger, period, *, api_fetcher, browser_fetcher, clock, sleep)` 和 `fetch_baidu_resilient_daily(config, root, logger, target_date, *, api_fetcher, browser_fetcher, clock, sleep)`。

- [ ] **Step 1: 写路由失败测试**

覆盖八个独立状态机测试：

- `test_browser_mode_never_calls_api`：API fake 被调用即失败，浏览器 fake 成功，最终来源为 `browser`。
- `test_api_preferred_success_never_calls_browser`：浏览器 fake 被调用即失败，API fake 一次成功，最终来源为 `api`。
- `test_api_network_error_retries_twice_then_falls_back`：API fake 连续返回 `network_error`，断言共调用三次，随后浏览器调用一次。
- `test_api_integrity_error_retries_once_then_falls_back`：API fake 连续返回 `integrity_error`，断言共调用两次，随后浏览器调用一次。
- `test_refresh_required_falls_back_without_network_retry`：API fake 返回 `reauthorization_required`，断言 API 只调用一次并立即进入浏览器。
- `test_api_and_browser_failure_returns_errors_and_no_success_report`：两路均失败，断言返回 errors，且生产标准报告不存在或原始字节未变化。
- `test_shadow_mode_uses_browser_output_and_writes_comparison`：API 与浏览器均成功但消费不同，断言正式结果等于浏览器，比较报告标记不通过。
- `test_twenty_second_budget_stops_api_retries`：注入时钟使第一次失败后已达 20 秒，断言不再调用 API 并进入浏览器。

- [ ] **Step 2: 运行测试并确认 RED**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "data_source or api_preferred or api_shadow" -q
```

- [ ] **Step 3: 实现错误分类和状态机**

接口固定为 `fetch_baidu_resilient_hourly(config, root, logger, period, *, api_fetcher=fetch_baidu_api_hourly, browser_fetcher=fetch_baidu_auto, clock=time.monotonic, sleep=time.sleep) -> dict[str, Any]` 和 `fetch_baidu_resilient_daily(config, root, logger, target_date, *, api_fetcher=fetch_baidu_api_daily, browser_fetcher=fetch_baidu_daily, clock=time.monotonic, sleep=time.sleep) -> dict[str, Any]`。

模式从 `config["baidu"]["data_source_mode"]` 读取，无效值按 `browser`。API 错误对象必须提供 `category`，路由器按 Global Constraints 执行固定重试上限和 20 秒预算。

降级报告加入：

```python
{
    "data_source": "browser_fallback",
    "api_attempts": 3,
    "self_heal_actions": ["network_retry", "network_retry"],
    "fallback_reason": "network_error",
}
```

影子模式调用 API 时必须传 `commit_standard_report=False`，随后以浏览器结果为正式结果，比较推广 ID、展现、点击、消费和汇总，输出 `reports/baidu_api_shadow_comparison.json`。API 成功但浏览器失败时，影子任务仍判定失败，不得临时改用 API 写入。

- [ ] **Step 4: 运行路由测试并确认 GREEN**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "data_source or api_preferred or api_shadow" -q
```

- [ ] **Step 5: 提交 Task 4**

```cmd
git add modules/baidu_data_source.py tests/test_basic.py
git commit -m "Add resilient API-first Baidu data routing"
```

---

### Task 5: 接入现有 pipeline 与项目配置

**Files:**
- Modify: `modules/project_config.py`
- Modify: `modules/run_pipeline.py`
- Modify: `configs/projects/project_template.json`
- Modify: `configs/projects/kunming_niu.json`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: `fetch_baidu_resilient_hourly`、`fetch_baidu_resilient_daily`。
- Produces: pipeline 默认使用路由器，但 `browser` 模式行为保持当前实现。

- [ ] **Step 1: 写集成失败测试**

新增断言：

```python
assert inspect.signature(run_half_auto_pipeline).parameters["fetch_baidu_func"].default is fetch_baidu_resilient_hourly
assert inspect.signature(run_daily_pipeline).parameters["fetch_baidu_func"].default is fetch_baidu_resilient_daily
project = load_project_config(tmp_path, "kunming_niu")
project["baidu"]["data_source_mode"] = "api_shadow"
assert build_runtime_config_from_project(project, {})["baidu"]["data_source_mode"] == "api_shadow"
```

另测缺失模式默认为 `browser`、无效模式产生配置错误、API 与浏览器双失败时 parse/merge/write 均不调用、最终报告记录实际 `data_source`。

- [ ] **Step 2: 运行集成测试并确认 RED**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "pipeline_defaults or data_source_mode or actual_data_source" -q
```

- [ ] **Step 3: 最小接入**

`project_config.py` 只允许：

```python
DATA_SOURCE_MODES = {"browser", "api_shadow", "api_preferred"}
```

模板和所有未灰度项目保持 `browser`。昆明牛在代码验收完成前也保持 `browser`；真实影子测试时再由用户明确授权切换。

pipeline 的步骤名继续兼容现有日志，但 final report 增加 `data_source`、`api_attempts`、`fallback_reason`。不得改变快商通、合并或 Excel 调用顺序。

- [ ] **Step 4: 运行 pipeline 回归测试**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "run_pipeline or run_daily_pipeline or data_source_mode" -q
```

- [ ] **Step 5: 提交 Task 5**

```cmd
git add modules/project_config.py modules/run_pipeline.py configs/projects/project_template.json configs/projects/kunming_niu.json tests/test_basic.py
git commit -m "Integrate API-first routing with report pipelines"
```

---

### Task 6: 授权文件自动 profile 匹配

**Files:**
- Modify: `modules/baidu_oauth_bundle.py`
- Modify: `main.py`
- Modify: `docs/baidu_oauth_nine_projects.md`
- Modify: `configs/projects/changsha_niu.json`
- Modify: `configs/projects/nanjing_niu.json`
- Modify: `configs/projects/ningbo_niu.json`
- Modify: `configs/projects/qingdao_bai.json`
- Modify: `configs/projects/nanjing_bai.json`
- Modify: `configs/projects/shenzhen_bai.json`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: `.baidu-auth` 文件和正式项目配置。
- Produces: `match_baidu_oauth_profile(root, bundle) -> dict`，并支持 `--api-profile auto`。

- [ ] **Step 1: 写自动匹配失败测试**

测试唯一匹配、无匹配、多匹配、错误 appId、单来源和双来源：

```python
match = match_baidu_oauth_profile(tmp_path, bundle)
assert match == {
    "api_profile": "changsha_niu_baidu",
    "project_id": "changsha_niu",
    "source_id": None,
    "promotion_ids": [111, 222, 333],
}
```

授权文件 Token 不得出现在匹配报告、异常文本或 CLI 输出。

- [ ] **Step 2: 运行匹配测试并确认 RED**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "oauth_profile_match or import_baidu_oauth" -q
```

- [ ] **Step 3: 实现精确集合匹配**

扫描 `configs/projects/*.json`，排除模板和演示项目。单来源读取 `baidu.api_profile` 和项目账户推广 ID；双来源逐个读取 `baidu_sources[*].api_profile` 和来源账户推广 ID。每个账户优先读取 `baidu_user_ids`，没有时才读取 `kst_ids`。授权文件的 `sub_accounts[*].user_id` 集合必须完全相等，且 appId 必须等于 `baidu_api_gateway.app_id`。

零个或多个候选均抛出 `BaiduOAuthImportError`。CLI 使用 `--api-profile auto` 时先匹配再调用现有原子导入；显式 profile 入口继续保留。

六个单来源项目配置补充对应 `api_profile`，但 `data_source_mode` 保持 `browser`。

- [ ] **Step 4: 运行授权测试并确认 GREEN**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "oauth_profile_match or import_baidu_oauth" -q
```

- [ ] **Step 5: 同步授权 SOP 并提交**

SOP 状态更新为服务商应用已通过，固定使用 `openBD`，导入命令更新为：

```cmd
.venv\Scripts\python.exe main.py --mode import-baidu-oauth --file "D:\Downloads\baidu_oauth_xxx.baidu-auth" --api-profile auto
```

```cmd
git add modules/baidu_oauth_bundle.py main.py docs/baidu_oauth_nine_projects.md configs/projects/changsha_niu.json configs/projects/nanjing_niu.json configs/projects/ningbo_niu.json configs/projects/qingdao_bai.json configs/projects/nanjing_bai.json configs/projects/shenzhen_bai.json tests/test_basic.py
git commit -m "Match Baidu OAuth grants to project profiles"
```

---

### Task 7: 构建、回归与昆明牛只读验收

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/hermes_hourly_sop.md`
- Modify: `docs/hermes_daily_sop.md`
- Modify: `cloud/baidu_oauth_callback/README.md`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: Tasks 1-6 的全部接口。
- Produces: 可部署 SCF ZIP、通过回归的桌面代码和明确的昆明牛灰度操作清单。

- [ ] **Step 1: 运行敏感信息扫描和相关测试**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "baidu_api or oauth or data_source or run_pipeline" -q
git diff | rg -n "accessToken|refreshToken|secretKey|password"
```

第二条只允许命中字段名、空示例和测试假值，不允许出现真实值。

- [ ] **Step 2: 运行全量基础测试**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py
```

预期：全部通过。

- [ ] **Step 3: 构建并检查 SCF 包**

```cmd
.venv\Scripts\python.exe tools\build_baidu_oauth_scf.py
```

验证 ZIP 包含 `index.py`、`app.py`、`scf_bootstrap`，不包含 secrets、日志或本机配置。

- [ ] **Step 4: 更新文档**

文档必须说明：默认仍为浏览器；API 需显式灰度；自修复上限；浏览器降级；SCF 新环境变量；剩余十个授权的自动匹配命令；双来源和多项目尚未投入生产。

- [ ] **Step 5: 提交 Task 7**

```cmd
git add AGENTS.md README.md docs/hermes_hourly_sop.md docs/hermes_daily_sop.md cloud/baidu_oauth_callback/README.md tests/test_basic.py
git commit -m "Document API-first Baidu rollout safeguards"
```

- [ ] **Step 6: 昆明牛只读验收，不写 Excel**

部署 SCF 后由用户配置 `BAIDU_REFRESH_CLIENT_KEY`，并把相同客户端密钥及 refresh URL 写入本机 secrets。先执行：

```cmd
.venv\Scripts\python.exe main.py --mode test-baidu-api --project kunming_niu --date 2026-07-16
.venv\Scripts\python.exe main.py --mode simulate-baidu-api-hourly --project kunming_niu --period 18点 --date 2026-07-16
```

两个入口都不得写 Excel。随后把昆明牛临时切换 `api_shadow`，只有用户明确授权后才运行真实小时报或日报进行影子对账。对账确认前不得设置 `api_preferred`。

---

## 后续独立计划

本计划完成并通过昆明牛验收后，按以下顺序另写计划：

1. 剩余十个超管逐个授权、自动匹配和九项目影子对账。
2. 沈阳白、沈阳牛双来源 API 独立读取、整项目浏览器降级和合并验收。
3. 九项目全部稳定后，再设计最多三个项目的并行任务队列与浏览器实例调度。
