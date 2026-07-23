# Cloud Token Refresh Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 SCF 将百度无时区到期时间误当作 UTC 的故障，并加固 COS 集中 Token 存储在并发刷新、配置异常和敏感信息处理方面的行为。

**Architecture:** 保留现有桌面端 → SCF `/baidu/oauth/token` → COS Token Store 链路。SCF 统一将百度无时区时间解释为北京时间；旧单对象 store 保留只读兼容，新同步或刷新的授权按 profile 写入独立 COS 对象，使不同 profile 并发刷新不会互相覆盖；同 profile 的竞争失败会重新读取云端最新记录，避免把正常并发误报为必须重新授权。

**Tech Stack:** Python 3.6 兼容 SCF、标准库 `datetime`/`urllib`/`hmac`、腾讯云 COS XML API、pytest。

## Global Constraints

- 不输出、记录、提交真实 access token、refresh token、客户端密钥、百度 secretKey 或 COS 密钥。
- 不运行真实 `run` / `run-daily`，不启动 Chrome，不读写业务 Excel。
- 保持 `/baidu/oauth/callback`、`/refresh`、`/token`、`/store-profile` 公共路径兼容。
- 只修改云端 Token 模块、对应测试、部署文档和 SCF 构建产物。
- Python 代码必须兼容腾讯云现有 Python 3.6 SCF。

---

### Task 1: 北京时间到期判断

**Files:**
- Modify: `cloud/baidu_oauth_callback/index.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: COS record 的 `expires_time` / `refresh_expires_time`
- Produces: `_parse_baidu_time(value) -> Optional[datetime]`，无时区值按 UTC+08:00 解释并转换为 UTC

- [ ] **Step 1: 写失败测试**

```python
def test_cloud_token_naive_baidu_expiry_uses_china_standard_time():
    callback = _load_baidu_oauth_callback_module("baidu_oauth_china_expiry_test")
    expires = callback._parse_baidu_time("2026-07-23 12:25:35")
    assert expires.isoformat() == "2026-07-23T04:25:35+00:00"
    assert callback._cloud_token_needs_refresh(
        {"access_token": "old", "refresh_token": "refresh", "expires_time": "2026-07-23 12:25:35"},
        int(datetime(2026, 7, 23, 7, 20, tzinfo=timezone.utc).timestamp()),
    )
```

- [ ] **Step 2: 运行测试并确认因当前 UTC 解释失败**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "cloud_token_naive_baidu_expiry" -q`

Expected: FAIL，实际结果仍为 `2026-07-23T12:25:35+00:00`。

- [ ] **Step 3: 最小实现**

```python
BAIDU_TIMEZONE = timezone(timedelta(hours=8))

def _parse_baidu_time(value: Any) -> Optional[datetime]:
    ...
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BAIDU_TIMEZONE)
    return parsed.astimezone(timezone.utc)
```

- [ ] **Step 4: 复测通过**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "cloud_token_naive_baidu_expiry or cloud_token_endpoint" -q`

Expected: PASS。

### Task 2: Profile 独立 COS 对象与并发隔离

**Files:**
- Modify: `cloud/baidu_oauth_callback/index.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: 旧单对象 `baidu_oauth_tokens.json`
- Produces: `.../profiles/<api_profile>.json` 独立对象；旧 store 只读回退；同 profile 刷新竞争恢复

- [ ] **Step 1: 写失败测试**

```python
def test_cloud_token_profile_objects_isolate_concurrent_updates():
    # 两个 profile 写入不同对象键，不再共同覆盖一个 JSON。
    ...
    assert set(objects) == {profile_a_key, profile_b_key}
```

- [ ] **Step 2: 运行测试并确认当前最后写入覆盖并发更新**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "concurrent_profile_updates" -q`

Expected: FAIL，当前尚无 `save_token_profile`。

- [ ] **Step 3: 最小实现**

```python
TOKEN_PROFILE_FORMAT = "baidu-token-profile-v1"

def _token_profile_key(config, api_profile):
    return "<base>/profiles/%s.json" % api_profile

def load_token_profile(config, api_profile, cos_transport):
    # 优先独立对象，不存在时回退旧总 store。
    ...

def save_token_profile(config, api_profile, record, cos_transport):
    # 只覆盖该 profile 自己的对象。
    ...
```

腾讯云 COS 普通 `PUT Object` 官方不提供 `If-Match` 条件覆盖，因此不依赖未受支持的 ETag CAS；按 profile 分对象消除多项目之间的共享写热点。

- [ ] **Step 4: 覆盖同 profile 竞争恢复**

```python
def test_cloud_token_refresh_failure_uses_newer_concurrent_record():
    # 上游刷新失败后重新读取 COS；若 refresh_token/expiry 已变化，
    # 返回并发请求刚写入的新 access token，而不是 reauthorization_required。
    ...
```

- [ ] **Step 5: 运行并发专项测试**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "cloud_token and (concurrent or profile or endpoint)" -q`

Expected: PASS。

### Task 3: 配置和数据完整性加固

**Files:**
- Modify: `cloud/baidu_oauth_callback/index.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Produces: 缺少 `app_id` 的 store-profile 请求返回 `server_config_error`；损坏的 `profiles` 不再静默清空

- [ ] **Step 1: 写失败测试**

```python
def test_store_profile_rejects_missing_server_app_id():
    with pytest.raises(callback.OAuthCallbackError) as exc_info:
        callback.process_store_profile_request(payload, headers, config_without_app_id, fake_cos, now)
    assert exc_info.value.code == "server_config_error"

def test_token_store_rejects_non_mapping_profiles():
    with pytest.raises(callback.OAuthCallbackError) as exc_info:
        callback._normalize_token_store({"profiles": []})
    assert exc_info.value.code == "token_store_invalid"
```

- [ ] **Step 2: 运行并确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "missing_server_app_id or non_mapping_profiles" -q`

Expected: FAIL。

- [ ] **Step 3: 增加最小校验并复测**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "cloud_token_store or store_profile" -q`

Expected: PASS。

### Task 4: 文档、构建和验证

**Files:**
- Modify: `docs/baidu_cloud_token_store.md`
- Modify: `cloud/baidu_oauth_callback/README.md`
- Regenerate: `cloud/baidu_oauth_callback/dist/baidu_oauth_callback_scf.zip`

**Interfaces:**
- Consumes: `tools/build_baidu_oauth_scf.py`
- Produces: 可部署的修复版 SCF ZIP

- [ ] **Step 1: 文档说明**

记录百度无时区时间按 UTC+08:00 解释、profile 独立 COS 对象、旧 store 兼容、所需 COS 前缀权限和部署后 readiness 验收步骤。

- [ ] **Step 2: 运行专项测试**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "baidu_oauth_refresh or cloud_token or token_manager" -q`

Expected: PASS。

- [ ] **Step 3: 重建 SCF 包并审计内容**

Run: `.venv\Scripts\python.exe tools\build_baidu_oauth_scf.py`

Expected: ZIP 生成成功；包内不含 secrets、日志、报告或真实 Token。

- [ ] **Step 4: 运行完整基础测试**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py`

Expected: 全部 PASS。

- [ ] **Step 5: 本地敏感信息和差异检查**

Run: `git diff --check`

Expected: 无补丁格式错误；差异中无真实 Token/密钥。

- [ ] **Step 6: 部署后只读验收**

Run: `.venv\Scripts\python.exe main.py --mode test-baidu-api-readiness`

Expected: 9 项目、11 授权全部通过；不启动 Chrome、不读写 Excel。
