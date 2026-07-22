# Cloud Centralized Baidu Token Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Baidu OAuth refresh-token rotation from each desktop client into one SCF + COS centralized token service.

**Architecture:** Tencent SCF owns the latest OAuth records in COS and exposes signed endpoints for desktop clients to fetch short-lived access tokens and for admins to store newly authorized profiles. The desktop app uses the cloud token provider for normal API reads and keeps browser fallback unchanged.

**Tech Stack:** Python 3.6-compatible SCF code, Python 3.14 desktop code, Tencent COS XML API via standard-library HTTP signing, existing HMAC request signing, pytest.

## Global Constraints

- COS bucket: `hourlyreport-1300869225`
- COS region: `ap-nanjing`
- COS object key: `baidu-oauth/token-store/baidu_oauth_tokens.json`
- Existing SCF callback path `/baidu/oauth/callback` must remain compatible.
- Existing refresh path `/baidu/oauth/refresh` must remain compatible during rollout.
- No logs, reports, tests, release packages, or docs may contain real access tokens, refresh tokens, secretKey, COS secret key, or HMAC client key.
- Desktop production API mode must use cloud token provider first once configured.
- Browser fallback must remain available and unchanged when cloud token acquisition fails.
- `secrets/secrets.json`, `.baidu-secrets`, backups, logs, reports, diagnostics, and auth files must not be committed.
- Implement with TDD: failing tests before production code for each behavior change.

---

## File Structure

- Modify: `cloud/baidu_oauth_callback/index.py`
  - Add COS-backed token store helpers.
  - Add `/baidu/oauth/token` processing.
  - Add `/baidu/oauth/store-profile` processing.
  - Keep current OAuth callback and legacy refresh endpoint.
- Modify: `cloud/baidu_oauth_callback/app.py`
  - Route new web paths to SCF handlers.
- Modify: `cloud/baidu_oauth_callback/README.md`
  - Document COS environment variables and deployment steps.
- Modify: `modules/baidu_token_manager.py`
  - Add cloud token provider while keeping local refresh provider for compatibility.
- Modify: `modules/baidu_report_api.py`
  - Default production fetches to cloud token provider when configured.
- Modify: `modules/baidu_oauth_bundle.py`
  - Add optional cloud profile upload after local OAuth import.
- Modify: `main.py`
  - Add explicit CLI for cloud profile upload or extend `import-baidu-oauth`.
- Modify: `modules/preflight.py`
  - Treat cloud token gateway as valid API profile availability.
- Modify: `tests/test_basic.py`
  - Add focused tests for cloud token store, cloud token provider, import sync, and fallback behavior.
- Modify: `tools/build_baidu_oauth_scf.py`
  - Ensure new SCF files are packaged.

---

### Task 1: SCF COS Token Store Helpers

**Files:**
- Modify: `tests/test_basic.py`
- Modify: `cloud/baidu_oauth_callback/index.py`

**Interfaces:**
- Produces:
  - `load_token_store(config, cos_transport=None) -> dict`
  - `save_token_store(config, store, cos_transport=None) -> None`
  - `get_token_profile(store, api_profile) -> dict`
  - `upsert_token_profile(store, api_profile, authorization, app_id) -> dict`

- [ ] **Step 1: Write failing tests**

Add tests that load the SCF module with fake COS transports:

```python
def test_cloud_token_store_loads_missing_store_as_empty_and_upserts_profile():
    callback = _load_baidu_oauth_callback_module("baidu_oauth_cloud_store_test")
    objects = {}
    config = {
        "app_id": "app-1",
        "token_store_bucket": "hourlyreport-1300869225",
        "token_store_region": "ap-nanjing",
        "token_store_key": "baidu-oauth/token-store/baidu_oauth_tokens.json",
    }

    def fake_cos(method, bucket, region, key, body=None):
        if method == "GET":
            if key not in objects:
                raise callback.OAuthCallbackError("token_store_not_found", "missing", 404)
            return json.loads(objects[key])
        if method == "PUT":
            objects[key] = body
            return {"ok": True}
        raise AssertionError(method)

    store = callback.load_token_store(config, fake_cos)
    assert store["format"] == "baidu-token-store-v1"
    callback.upsert_token_profile(
        store,
        "ningbo_niu_baidu",
        {
            "access_token": "a.b.c",
            "refresh_token": "d.e.f",
            "open_id": "open",
            "user_id": 45187067,
            "expires_time": "2026-07-23 11:17:33",
            "refresh_expires_time": "2026-08-21 11:17:33",
        },
        "app-1",
    )
    callback.save_token_store(config, store, fake_cos)
    saved = json.loads(objects["baidu-oauth/token-store/baidu_oauth_tokens.json"])
    assert saved["profiles"]["ningbo_niu_baidu"]["user_id"] == 45187067
```

- [ ] **Step 2: Run failing test**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "cloud_token_store_loads_missing_store" -q
```

Expected: FAIL because helpers do not exist.

- [ ] **Step 3: Implement minimal helpers**

In `cloud/baidu_oauth_callback/index.py`, add:

- environment config keys:
  - `BAIDU_TOKEN_STORE_BUCKET`
  - `BAIDU_TOKEN_STORE_REGION`
  - `BAIDU_TOKEN_STORE_KEY`
- JSON store normalization.
- profile validation:
  - profile regex `^[a-z0-9][a-z0-9_-]{1,79}$`
  - required token fields
  - token format contains two dots
  - app id matches.

- [ ] **Step 4: Verify test passes**

Run the same pytest command. Expected: PASS.

- [ ] **Step 5: Commit**

```cmd
git add tests\test_basic.py cloud\baidu_oauth_callback\index.py
git commit -m "Add cloud Baidu token store helpers"
```

---

### Task 2: SCF `/baidu/oauth/token` Endpoint

**Files:**
- Modify: `tests/test_basic.py`
- Modify: `cloud/baidu_oauth_callback/index.py`
- Modify: `cloud/baidu_oauth_callback/app.py`

**Interfaces:**
- Consumes: token store helpers from Task 1.
- Produces:
  - `process_cloud_token_request(payload, headers, config, cos_transport=None, oauth_transport=_post_json, now=None) -> dict`

- [ ] **Step 1: Write failing tests**

Add tests:

```python
def test_cloud_token_endpoint_returns_cached_access_token_without_refresh():
    callback = _load_baidu_oauth_callback_module("baidu_oauth_cloud_token_cached_test")
    now = 1784700000
    payload = {"apiProfile": "ningbo_niu_baidu", "forceRefresh": False}
    headers = _signed_refresh_headers(callback, payload, "client-key", now)
    store = {
        "format": "baidu-token-store-v1",
        "profiles": {
            "ningbo_niu_baidu": {
                "app_id": "app-1",
                "access_token": "cached.access.token",
                "refresh_token": "cached.refresh.token",
                "open_id": "open",
                "user_id": 45187067,
                "expires_time": "2026-07-23 11:17:33",
                "refresh_expires_time": "2026-08-21 11:17:33",
            }
        },
    }

    def fake_cos(method, bucket, region, key, body=None):
        assert method == "GET"
        return store

    def fail_oauth(*_args):
        raise AssertionError("should not refresh")

    result = callback.process_cloud_token_request(
        payload,
        headers,
        {
            "app_id": "app-1",
            "secret_key": "secret",
            "refresh_client_key": "client-key",
            "refresh_max_timestamp_skew_seconds": 300,
            "token_store_bucket": "hourlyreport-1300869225",
            "token_store_region": "ap-nanjing",
            "token_store_key": "baidu-oauth/token-store/baidu_oauth_tokens.json",
        },
        fake_cos,
        fail_oauth,
        now,
    )
    assert result["access_token"] == "cached.access.token"
    assert result["token_refresh"] == "not_needed"
    assert "refresh_token" not in json.dumps(result)
```

Add a second test that sets `expires_time` within 10 minutes, fakes Baidu refresh response, asserts:

- OAuth transport called once.
- COS PUT happened.
- response contains new access token.
- response does not contain refresh token.

- [ ] **Step 2: Run failing tests**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "cloud_token_endpoint" -q
```

Expected: FAIL because endpoint does not exist.

- [ ] **Step 3: Implement endpoint**

Implementation requirements:

- Reuse existing HMAC headers:
  - `X-Baidu-Refresh-Timestamp`
  - `X-Baidu-Refresh-Signature`
- Payload shape:
  - `apiProfile: str`
  - optional `forceRefresh: bool`
- Return only:
  - `access_token`
  - `expires_time`
  - `token_refresh`
  - `api_profile`
- Never return refresh token.
- Add path routing for `/baidu/oauth/token` in both event and WSGI handlers.

- [ ] **Step 4: Verify tests pass**

Run same pytest command. Expected: PASS.

- [ ] **Step 5: Commit**

```cmd
git add tests\test_basic.py cloud\baidu_oauth_callback\index.py cloud\baidu_oauth_callback\app.py
git commit -m "Add cloud Baidu token endpoint"
```

---

### Task 3: SCF `/baidu/oauth/store-profile` Endpoint

**Files:**
- Modify: `tests/test_basic.py`
- Modify: `cloud/baidu_oauth_callback/index.py`
- Modify: `cloud/baidu_oauth_callback/app.py`

**Interfaces:**
- Consumes: token store helpers from Task 1.
- Produces:
  - `process_store_profile_request(payload, headers, config, cos_transport=None, now_timestamp=None) -> dict`

- [ ] **Step 1: Write failing tests**

Add a test that signs:

```json
{
  "apiProfile": "ningbo_niu_baidu",
  "authorization": {
    "access_token": "new.access.token",
    "refresh_token": "new.refresh.token",
    "open_id": "open",
    "user_id": 45187067,
    "expires_time": "2026-07-23 11:17:33",
    "refresh_expires_time": "2026-08-21 11:17:33",
    "master_name": "BDCC-test",
    "sub_accounts": [{"user_id": 45144300, "user_name": "宁波博润1"}]
  }
}
```

Assert:

- COS PUT contains the profile.
- response contains profile, user id, sub account count.
- response JSON does not contain `access_token` or `refresh_token`.

- [ ] **Step 2: Run failing test**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "store_profile" -q
```

Expected: FAIL.

- [ ] **Step 3: Implement endpoint**

Requirements:

- Signed request only.
- App id comes from SCF env, not desktop payload.
- Upsert profile atomically into COS store.
- Response is safe summary only.
- Route `/baidu/oauth/store-profile` in event and WSGI handlers.

- [ ] **Step 4: Verify tests pass**

Run same pytest command. Expected: PASS.

- [ ] **Step 5: Commit**

```cmd
git add tests\test_basic.py cloud\baidu_oauth_callback\index.py cloud\baidu_oauth_callback\app.py
git commit -m "Add cloud Baidu profile storage endpoint"
```

---

### Task 4: Desktop Cloud Token Provider

**Files:**
- Modify: `tests/test_basic.py`
- Modify: `modules/baidu_token_manager.py`
- Modify: `modules/baidu_report_api.py`

**Interfaces:**
- Produces:
  - `ensure_cloud_access_token(config, root, api_profile, force_refresh=False, timeout_seconds=None, clock=time.monotonic) -> tuple[str, dict[str, Any]]`
  - `select_access_token_provider(config) -> Callable`

- [ ] **Step 1: Write failing tests**

Add tests:

```python
def test_cloud_token_provider_requests_access_token_without_sending_refresh_token(tmp_path):
    from modules.baidu_token_manager import ensure_cloud_access_token

    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "secrets.json").write_text(json.dumps({
        "baidu_api_gateway": {
            "app_id": "app-1",
            "token_url": "https://example.invalid/baidu/oauth/token",
            "client_key": "client-key"
        },
        "baidu_api": {"ningbo_niu_baidu": {"master_name": "BDCC-test"}}
    }), encoding="utf-8")
    calls = []

    def fake_post(url, payload, headers, timeout):
        calls.append((url, payload, headers))
        return {
            "status": "ok",
            "authorization": {
                "access_token": "cloud.access.token",
                "expires_time": "2026-07-23 11:17:33",
                "token_refresh": "not_needed",
            },
        }

    token, metadata = ensure_cloud_access_token(
        {"credentials_path": "secrets/secrets.json"},
        tmp_path,
        "ningbo_niu_baidu",
        transport=fake_post,
    )
    assert token == "cloud.access.token"
    assert metadata["token_refresh"] == "not_needed"
    assert calls[0][1] == {"apiProfile": "ningbo_niu_baidu", "forceRefresh": False}
    assert "refresh" not in json.dumps(calls[0][1]).lower()
```

Add a test for cloud failure mapping to `BaiduTokenError("token_refresh_error" or "reauthorization_required")`.

- [ ] **Step 2: Run failing tests**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "cloud_token_provider" -q
```

Expected: FAIL.

- [ ] **Step 3: Implement provider**

Requirements:

- Read `baidu_api_gateway.token_url`.
- If `token_url` missing, fall back to current local provider.
- Sign payload with existing HMAC logic.
- Do not read or send local refresh token.
- Response validation:
  - `status == ok`
  - `authorization.access_token` exists and JWT-like.
- Return safe metadata.

Wire `modules/baidu_report_api.py` default token provider selection:

- If gateway has `token_url`, use cloud provider.
- Else use existing local `ensure_valid_access_token`.

- [ ] **Step 4: Verify tests pass**

Run same pytest command. Expected: PASS.

- [ ] **Step 5: Commit**

```cmd
git add tests\test_basic.py modules\baidu_token_manager.py modules\baidu_report_api.py
git commit -m "Use cloud Baidu token provider"
```

---

### Task 5: OAuth Import Sync to Cloud

**Files:**
- Modify: `tests/test_basic.py`
- Modify: `modules/baidu_oauth_bundle.py`
- Modify: `main.py`

**Interfaces:**
- Produces:
  - `upload_baidu_oauth_profile(root, api_profile, authorization, transport=None) -> dict`
  - CLI flag: `--sync-cloud-token-store`

- [ ] **Step 1: Write failing tests**

Add test:

```python
def test_import_baidu_oauth_can_sync_profile_to_cloud(tmp_path):
    from modules.baidu_oauth_bundle import upload_baidu_oauth_profile

    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "secrets.json").write_text(json.dumps({
        "baidu_api_gateway": {
            "app_id": "app-1",
            "store_profile_url": "https://example.invalid/baidu/oauth/store-profile",
            "client_key": "client-key"
        }
    }), encoding="utf-8")
    calls = []

    def fake_post(url, payload, headers, timeout):
        calls.append((url, payload, headers))
        return {"status": "ok", "api_profile": "ningbo_niu_baidu", "user_id": 45187067, "sub_account_count": 5}

    report = upload_baidu_oauth_profile(
        tmp_path,
        "ningbo_niu_baidu",
        {
            "access_token": "a.b.c",
            "refresh_token": "d.e.f",
            "open_id": "open",
            "user_id": 45187067,
        },
        transport=fake_post,
    )
    assert report["api_profile"] == "ningbo_niu_baidu"
    assert calls[0][1]["apiProfile"] == "ningbo_niu_baidu"
    assert calls[0][1]["authorization"]["refresh_token"] == "d.e.f"
```

- [ ] **Step 2: Run failing test**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "sync_profile_to_cloud" -q
```

Expected: FAIL.

- [ ] **Step 3: Implement upload helper and CLI flag**

Behavior:

- Existing `import-baidu-oauth` still imports locally by default.
- With `--sync-cloud-token-store`, after successful local import, upload the same profile to cloud.
- If cloud sync fails, local import remains but report warns cloud sync failed.
- Never print token contents.

- [ ] **Step 4: Verify tests pass**

Run same pytest command. Expected: PASS.

- [ ] **Step 5: Commit**

```cmd
git add tests\test_basic.py modules\baidu_oauth_bundle.py main.py
git commit -m "Sync Baidu OAuth imports to cloud store"
```

---

### Task 6: Preflight, Docs, and SCF Package

**Files:**
- Modify: `tests/test_basic.py`
- Modify: `modules/preflight.py`
- Modify: `cloud/baidu_oauth_callback/README.md`
- Modify: `docs/baidu_oauth_nine_projects.md`
- Modify: `tools/build_baidu_oauth_scf.py`

**Interfaces:**
- Consumes all earlier tasks.
- Produces updated operational docs and deployment artifact.

- [ ] **Step 1: Write or update tests**

Add tests that:

- API profile check passes when `token_url` is configured and local profile has no refresh token.
- Release/build filter excludes any generated token store files.

- [ ] **Step 2: Run failing tests**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "preflight or baidu_oauth_refresh or cloud_token" -q
```

Expected: FAIL before implementation where applicable.

- [ ] **Step 3: Implement docs and packaging updates**

Document SCF variables:

```text
BAIDU_TOKEN_STORE_BUCKET=hourlyreport-1300869225
BAIDU_TOKEN_STORE_REGION=ap-nanjing
BAIDU_TOKEN_STORE_KEY=baidu-oauth/token-store/baidu_oauth_tokens.json
```

Document desktop `secrets.json` gateway keys:

```json
{
  "baidu_api_gateway": {
    "app_id": "...",
    "token_url": "https://.../baidu/oauth/token",
    "store_profile_url": "https://.../baidu/oauth/store-profile",
    "client_key": "..."
  }
}
```

Update SCF build if needed:

```cmd
.venv\Scripts\python.exe tools\build_baidu_oauth_scf.py
```

- [ ] **Step 4: Verify focused tests pass**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "baidu_oauth_refresh or cloud_token or token_manager or preflight" -q
```

Expected: PASS.

- [ ] **Step 5: Run broader baseline**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py
```

Expected: PASS or document exact unrelated failures.

- [ ] **Step 6: Commit**

```cmd
git add tests\test_basic.py modules\preflight.py cloud\baidu_oauth_callback\README.md docs\baidu_oauth_nine_projects.md tools\build_baidu_oauth_scf.py cloud\baidu_oauth_callback\dist\baidu_oauth_callback_scf.zip
git commit -m "Document centralized Baidu token deployment"
```

---

## Deployment Checklist

After implementation:

1. Upload new `cloud/baidu_oauth_callback/dist/baidu_oauth_callback_scf.zip` to Tencent SCF.
2. Add SCF environment variables:
   - `BAIDU_TOKEN_STORE_BUCKET=hourlyreport-1300869225`
   - `BAIDU_TOKEN_STORE_REGION=ap-nanjing`
   - `BAIDU_TOKEN_STORE_KEY=baidu-oauth/token-store/baidu_oauth_tokens.json`
3. Ensure SCF has read/write permission to this COS bucket and key.
4. Re-import or sync Ningbo token:
   ```cmd
   .venv\Scripts\python.exe main.py --mode import-baidu-oauth --file "D:\Downloads\baidu_oauth_45187067.baidu-auth" --api-profile auto --sync-cloud-token-store
   ```
5. Run:
   ```cmd
   .venv\Scripts\python.exe main.py --mode test-baidu-api-readiness --project ningbo_niu --period 11点
   ```
6. Confirm Ningbo uses API without browser fallback.

## Self-Review

- Spec coverage: COS store, token endpoint, store-profile endpoint, desktop provider, import sync, docs, deployment, and fallback are all covered.
- Placeholder scan: no unfinished placeholders; all tasks have concrete files, commands, and expected results.
- Type consistency: cloud request names use `apiProfile` externally and `api_profile` internally; provider returns `(token, metadata)` like the current local provider.
