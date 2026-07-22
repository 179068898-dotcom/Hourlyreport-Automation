# 百度 API 云端集中 Token 存储

本文说明“SCF + COS 集中刷新百度 OAuth token”的部署和使用方式。

## 目标

- 桌面端默认从云端获取百度 `access_token`。
- `refresh_token` 只保存在腾讯云 COS 内，不再依赖每台同事电脑各自刷新。
- 云函数统一使用百度 `secretKey` 刷新 token，并把新 token 原子写回 COS。
- 云端失败时，桌面端 API 流程仍会按现有策略失败后降级浏览器抓数。

## SCF 接口

现有回调函数新增两个内部签名接口：

```text
POST /baidu/oauth/token
POST /baidu/oauth/store-profile
```

`/token` 用于桌面端取可用 `access_token`。  
`/store-profile` 用于本机导入 `.baidu-auth` 后，把该授权同步写入云端 COS。

两个接口均使用现有 HMAC 请求头：

```text
X-Baidu-Refresh-Timestamp
X-Baidu-Refresh-Signature
```

## 腾讯云环境变量

在 SCF 函数中保留原有变量，并新增：

```text
BAIDU_TOKEN_STORE_BUCKET=hourlyreport-1300869225
BAIDU_TOKEN_STORE_REGION=ap-nanjing
BAIDU_TOKEN_STORE_KEY=baidu-oauth/token-store/baidu_oauth_tokens.json
TENCENT_SECRET_ID=腾讯云访问密钥 SecretId
TENCENT_SECRET_KEY=腾讯云访问密钥 SecretKey
TENCENT_TOKEN=临时密钥 token（仅临时密钥需要）
```

COS 存储桶必须保持私有读写。

## 桌面端网关配置

每台电脑的 `secrets/secrets.json` 中，`baidu_api_gateway` 需要包含：

```json
{
  "app_id": "百度应用 appId",
  "client_key": "桌面端与 SCF 共享的 HMAC 密钥",
  "refresh_url": "https://.../baidu/oauth/refresh",
  "token_url": "https://.../baidu/oauth/token",
  "store_profile_url": "https://.../baidu/oauth/store-profile"
}
```

如果暂时没有 `token_url`，程序会继续使用旧的本地刷新逻辑。

## 导入并同步授权

本机拿到 `.baidu-auth` 文件后执行：

```cmd
.venv\Scripts\python.exe main.py --mode import-baidu-oauth --file "D:\Downloads\baidu_oauth_xxx.baidu-auth" --api-profile auto --sync-cloud-token-store
```

成功后会同时完成两件事：

1. 写入本机 `secrets/secrets.json`。
2. 上传对应 `api_profile` 到 COS 集中 token store。

导入完成后立即人工删除下载目录中的 `.baidu-auth` 文件。

## 敏感信息边界

- `.baidu-auth`、`secrets/secrets.json`、COS 中的 `baidu_oauth_tokens.json` 都是敏感文件。
- 不得提交 Git，不得写入日志，不得打入发布包。
- `/token` 返回给桌面端的结果只包含 `access_token`，不会返回 `refresh_token`。
