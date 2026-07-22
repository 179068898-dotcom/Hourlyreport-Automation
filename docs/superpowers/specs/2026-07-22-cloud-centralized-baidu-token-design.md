# SCF + COS 百度 Token 集中管理设计

## 背景

当前桌面端每台电脑都保存同一套百度 OAuth `refresh_token`。当 A 电脑刷新某个项目的 token 后，百度会返回新的 `refresh_token`，旧 token 随即失效；B 电脑仍拿旧 token 刷新时，就会被判定为 `reauthorization_required`，导致 API 自动降级浏览器。

宁波牛本次故障就是这个模式：`access_token` 已过期，`refresh_token` 表面未到期，但刷新接口返回“需要重新授权”。短期可通过重新授权并分发配置包修复，长期应将 token 刷新集中到云端。

## 目标

- 让所有电脑共用云端唯一最新 `refresh_token`，避免多电脑互相踢旧 token。
- 桌面端默认通过云函数获取短期 `access_token`，不再本地轮换 `refresh_token`。
- 保留现有 API 优先、浏览器降级机制；云端 token 服务异常时只影响对应项目，不拖死其他项目。
- 保持当前 `.baidu-auth` 授权导入流程可用，并新增“同步到云端 token 仓库”的能力。
- 不把百度 `secretKey`、OAuth token、COS 密钥写入日志、报告、Git 或发布包。

## 非目标

- 不做多项目并行执行。
- 不迁移到数据库。
- 不引入完整后台网站或管理页面。
- 不改变百度报表数据解析与 Excel 写入逻辑。

## 推荐架构

采用 `腾讯云 SCF + COS 对象存储`：

```text
桌面端
  │  signed POST /baidu/oauth/token { apiProfile }
  ▼
腾讯云 SCF
  │  读写 COS 中的 baidu_oauth_tokens.json
  │  必要时调用百度 refreshToken
  ▼
百度 OAuth
```

COS 中保存一个加密或最小权限保护的 JSON 对象，按 `api_profile` 存储 11 套授权记录。SCF 是唯一允许刷新并写回 `refresh_token` 的地方。

## 云端 Token Store

COS 对象建议路径：

```text
baidu-oauth/token-store/baidu_oauth_tokens.json
```

结构：

```json
{
  "format": "baidu-token-store-v1",
  "updated_at": "2026-07-22T12:00:00+08:00",
  "profiles": {
    "ningbo_niu_baidu": {
      "app_id": "百度应用ID",
      "access_token": "...",
      "refresh_token": "...",
      "open_id": "...",
      "user_id": 45187067,
      "expires_time": "2026-07-23 11:17:33",
      "refresh_expires_time": "2026-08-21 11:17:33",
      "master_name": "BDCC-...",
      "sub_accounts": []
    }
  }
}
```

云函数日志只允许记录 `api_profile`、是否刷新、错误类别、耗时；不得记录 token、secret、签名正文。

## SCF 新增接口

### `POST /baidu/oauth/token`

桌面端生产任务使用。

请求：

```json
{
  "apiProfile": "ningbo_niu_baidu",
  "forceRefresh": false
}
```

响应：

```json
{
  "status": "ok",
  "authorization": {
    "access_token": "...",
    "expires_time": "2026-07-23 11:17:33",
    "token_refresh": "not_needed|refreshed"
  }
}
```

行为：

- 校验 HMAC 签名。
- 从 COS 读取对应 `apiProfile`。
- 如果 `access_token` 距过期超过 10 分钟，直接返回。
- 如果临近过期或 `forceRefresh=true`，由 SCF 调用百度刷新接口。
- 刷新成功后，将新的 `access_token` 和 `refresh_token` 原子写回 COS。
- 多个请求同时刷新同一个 `apiProfile` 时，必须用 profile 级锁或乐观版本检查，保证只保留最新 token。

### `POST /baidu/oauth/store-profile`

管理员导入授权后同步云端使用。

请求：

```json
{
  "apiProfile": "ningbo_niu_baidu",
  "authorization": {
    "access_token": "...",
    "refresh_token": "...",
    "open_id": "...",
    "user_id": 45187067,
    "expires_time": "...",
    "refresh_expires_time": "...",
    "master_name": "...",
    "sub_accounts": []
  }
}
```

行为：

- 校验 HMAC 签名。
- 校验 `apiProfile` 命名。
- 校验授权字段完整、token 格式合法、`app_id` 匹配。
- 读取 COS store，备份旧 profile 元信息，覆盖该 profile。
- 返回安全摘要：profile、user_id、sub_account_count、updated_at。

第一版只允许桌面端通过显式命令/GUI 操作上传，不在 OAuth callback 中自动猜 profile，避免云端没有项目映射时写错。

## 桌面端改造

新增云端 token provider：

```python
ensure_cloud_access_token(config, root, api_profile, force_refresh=False) -> tuple[str, dict]
```

读取 `secrets/secrets.json` 中的：

```json
{
  "baidu_api_gateway": {
    "token_url": "https://.../baidu/oauth/token",
    "store_profile_url": "https://.../baidu/oauth/store-profile",
    "client_key": "...",
    "app_id": "..."
  }
}
```

生产 API 取数优先使用云端 token provider。云端不可用时：

- 不再尝试用本地旧 `refresh_token` 刷新。
- 直接按现有策略整项目降级浏览器。
- 错误报告显示安全类别，例如 `cloud_token_unavailable`、`reauthorization_required`、`configuration_error`。

保留本地 `ensure_valid_access_token` 作为兼容/测试入口，但普通 GUI 不再使用本地刷新。

## 授权导入流程

短期流程：

1. 管理员重新授权，得到 `.baidu-auth`。
2. 本地执行现有导入，自动匹配 `api_profile`。
3. 导入成功后调用云端 `store-profile`，把该 profile 上传到 COS。
4. 其他电脑无需导入完整 token，只要配置了同一个云端网关和客户端密钥，就能获取最新 access token。

GUI 后续可增加“同步授权到云端”提示，但第一版可以先用 CLI 开发入口验证。

## 配置与部署

SCF 环境变量新增：

```text
BAIDU_TOKEN_STORE_BACKEND=cos
BAIDU_TOKEN_STORE_BUCKET=<bucket-appid>
BAIDU_TOKEN_STORE_REGION=<ap-shanghai>
BAIDU_TOKEN_STORE_KEY=baidu-oauth/token-store/baidu_oauth_tokens.json
BAIDU_TOKEN_STORE_LOCK_PREFIX=baidu-oauth/locks/
TENCENT_SECRET_ID=<建议使用子账号/角色>
TENCENT_SECRET_KEY=<建议使用子账号/角色>
```

若 SCF 绑定运行角色可直接访问 COS，优先使用角色临时凭证，减少静态密钥暴露。

COS 权限建议：

- 只允许该 SCF 函数读写指定对象前缀。
- 不允许公开访问。
- 不开启完整请求正文日志。

## 错误处理

- COS 读取失败：返回 `token_store_unavailable`，桌面端降级浏览器。
- profile 不存在：返回 `profile_not_found`，桌面端提示授权未同步并降级浏览器。
- 百度刷新返回失效：返回 `reauthorization_required`，桌面端降级浏览器并提示需重新授权。
- 并发锁失败：短暂重试一次；仍失败返回 `token_store_busy`。
- 写回 COS 失败：不得返回新 token，避免云端状态与客户端状态不一致。

## 测试计划

- 云函数单元测试：
  - 签名错误、过期时间戳、错误 app_id 均拒绝。
  - `access_token` 未临近过期时不调用百度刷新。
  - 临近过期时只刷新一次并写回 store。
  - 百度刷新失败时不覆盖 COS store。
  - `store-profile` 能新增和覆盖指定 profile，且响应不泄露 token。
- 桌面端单元测试：
  - API fetcher 使用云端 token provider。
  - 云端 token 服务失败时触发浏览器降级。
  - 本地报告和日志不包含 access/refresh token。
- 集成验收：
  - 宁波牛只读 API 通过。
  - 两个模拟客户端连续请求同一 profile，第二个客户端不因旧 token 失效。
  - 批量 readiness 中，单个失效 profile 不影响其他 profile 判断。

## 分阶段实施

1. 云函数 token store 抽象与 COS 实现。
2. 新增 `/baidu/oauth/token` 与 `/baidu/oauth/store-profile`。
3. 桌面端新增云端 token provider，并接入 API 取数。
4. 扩展 OAuth 导入：导入成功后可同步到云端。
5. 更新文档、测试和 SCF 发布包。

