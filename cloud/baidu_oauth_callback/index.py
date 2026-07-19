import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


ACCESS_TOKEN_URL = "https://u.baidu.com/oauth/accessToken"
REFRESH_TOKEN_URL = "https://u.baidu.com/oauth/refreshToken"
USER_INFO_URL = "https://u.baidu.com/oauth/getUserInfo"
EXPORT_FORMAT = "baidu-oauth-export-v1"
REQUIRED_QUERY_FIELDS = ("appId", "authCode", "state", "userId", "timestamp", "signature")
REFRESH_REQUEST_FIELDS = frozenset(("appId", "userId", "refreshToken"))
REFRESH_TIMESTAMP_HEADER = "X-Baidu-Refresh-Timestamp"
REFRESH_SIGNATURE_HEADER = "X-Baidu-Refresh-Signature"


class OAuthCallbackError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _load_config() -> Dict[str, Any]:
    allowed_states = {
        value.strip()
        for value in os.environ.get("BAIDU_ALLOWED_STATES", "").split(",")
        if value.strip()
    }
    return {
        "app_id": os.environ.get("BAIDU_APP_ID", "").strip(),
        "secret_key": os.environ.get("BAIDU_SECRET_KEY", "").strip(),
        "allowed_states": allowed_states,
        "max_timestamp_skew_seconds": int(os.environ.get("BAIDU_MAX_TIMESTAMP_SKEW_SECONDS", "600")),
        "refresh_client_key": os.environ.get("BAIDU_REFRESH_CLIENT_KEY", "").strip(),
        "refresh_max_timestamp_skew_seconds": int(
            os.environ.get("BAIDU_REFRESH_MAX_TIMESTAMP_SKEW_SECONDS", "300")
        ),
    }


def _extract_query(event: Dict[str, Any]) -> Dict[str, str]:
    raw = event.get("queryStringParameters") or event.get("queryString") or {}
    if isinstance(raw, str):
        raw = urllib.parse.parse_qs(raw, keep_blank_values=True)
    if not isinstance(raw, dict):
        return {}
    result = {}  # type: Dict[str, str]
    for key, value in raw.items():
        if isinstance(value, list):
            value = value[0] if value else ""
        result[str(key)] = str(value or "")
    return result


def _aes_cbc_encrypt(payload: bytes, key: bytes) -> bytes:
    from Crypto.Cipher import AES

    padded_size = ((len(payload) + 15) // 16) * 16
    padded = payload.ljust(padded_size, b"\0")
    return AES.new(key, AES.MODE_CBC, iv=b"\0" * 16).encrypt(padded)


def _expected_signature(query: Dict[str, str], secret_key: str) -> str:
    source = {
        key: query[key]
        for key in sorted(query)
        if key != "signature"
    }
    compact_json = json.dumps(source, ensure_ascii=False, separators=(",", ":"))
    encoded = base64.b64encode(compact_json.encode("utf-8"))
    encrypted = _aes_cbc_encrypt(encoded, secret_key[:16].encode("utf-8"))
    return encrypted.hex().upper()


def _verify_signature(query: Dict[str, str], secret_key: str) -> bool:
    if len(secret_key.encode("utf-8")) < 16:
        raise OAuthCallbackError("server_config_error", "服务端 secretKey 配置无效", 500)
    expected = _expected_signature(query, secret_key)
    return hmac.compare_digest(expected.lower(), query.get("signature", "").lower())


def _post_json(url: str, payload: Dict[str, Any], timeout_seconds: int = 20) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json;charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise OAuthCallbackError("oauth_http_error", f"百度 OAuth 服务返回 HTTP {exc.code}", 502) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OAuthCallbackError("oauth_network_error", "无法连接百度 OAuth 服务", 502) from exc
    except json.JSONDecodeError as exc:
        raise OAuthCallbackError("oauth_invalid_response", "百度 OAuth 服务返回内容异常", 502) from exc


def _refresh_signature(timestamp: str, payload: Dict[str, Any], client_key: str) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    message = "%s\n%s" % (timestamp, canonical)
    return hmac.new(
        client_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _header_value(headers: Dict[str, Any], name: str) -> str:
    wanted = name.lower()
    for key, value in (headers or {}).items():
        if str(key).lower() == wanted:
            return str(value or "").strip()
    return ""


def process_refresh_request(
    payload: Dict[str, Any],
    headers: Dict[str, Any],
    config: Dict[str, Any],
    transport: Callable[[str, Dict[str, Any], int], Dict[str, Any]] = _post_json,
    now_timestamp: Optional[int] = None,
) -> Dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != REFRESH_REQUEST_FIELDS:
        raise OAuthCallbackError("invalid_refresh_request", "刷新请求参数不完整")
    if not config.get("app_id") or not config.get("secret_key") or not config.get("refresh_client_key"):
        raise OAuthCallbackError("server_config_error", "云函数刷新配置未完成", 500)
    if str(payload.get("appId") or "") != str(config["app_id"]):
        raise OAuthCallbackError("app_id_mismatch", "应用 ID 不匹配")
    try:
        user_id = int(payload.get("userId"))
    except (TypeError, ValueError) as exc:
        raise OAuthCallbackError("invalid_refresh_request", "刷新请求用户 ID 无效") from exc
    refresh_token = str(payload.get("refreshToken") or "").strip()
    if user_id <= 0 or not refresh_token:
        raise OAuthCallbackError("invalid_refresh_request", "刷新请求参数不完整")

    timestamp = _header_value(headers, REFRESH_TIMESTAMP_HEADER)
    signature = _header_value(headers, REFRESH_SIGNATURE_HEADER)
    if not timestamp or not signature:
        raise OAuthCallbackError("missing_refresh_signature", "刷新请求签名不完整")
    try:
        request_timestamp = int(timestamp)
    except ValueError as exc:
        raise OAuthCallbackError("invalid_refresh_timestamp", "刷新请求时间戳无效") from exc
    current_timestamp = int(time.time()) if now_timestamp is None else int(now_timestamp)
    max_skew = int(config.get("refresh_max_timestamp_skew_seconds", 300))
    if abs(current_timestamp - request_timestamp) > max_skew:
        raise OAuthCallbackError("expired_refresh_request", "刷新请求已过期")
    expected = _refresh_signature(timestamp, payload, str(config["refresh_client_key"]))
    if not hmac.compare_digest(expected.lower(), signature.lower()):
        raise OAuthCallbackError("refresh_signature_mismatch", "刷新请求签名校验失败")

    response = transport(
        REFRESH_TOKEN_URL,
        {
            "appId": config["app_id"],
            "refreshToken": refresh_token,
            "secretKey": config["secret_key"],
            "userId": user_id,
        },
        20,
    )
    if str(response.get("code")) != "0" or not isinstance(response.get("data"), dict):
        raise OAuthCallbackError("reauthorization_required", "更新授权令牌失败，需要重新授权", 401)
    data = response["data"]
    if not data.get("accessToken") or not data.get("refreshToken"):
        raise OAuthCallbackError("refresh_incomplete", "更新授权令牌返回不完整", 502)
    return {
        "access_token": data["accessToken"],
        "refresh_token": data["refreshToken"],
        "open_id": data.get("openId"),
        "expires_time": data.get("expiresTime"),
        "refresh_expires_time": data.get("refreshExpiresTime"),
        "expires_in": data.get("expiresIn"),
        "refresh_expires_in": data.get("refreshExpiresIn"),
    }


def _validate_callback(query: Dict[str, str], config: Dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_QUERY_FIELDS if not query.get(field)]
    if missing:
        raise OAuthCallbackError("missing_parameters", "授权回调参数不完整")
    if not config.get("app_id") or not config.get("secret_key") or not config.get("allowed_states"):
        raise OAuthCallbackError("server_config_error", "云函数环境变量未配置完整", 500)
    if query["appId"] != config["app_id"]:
        raise OAuthCallbackError("app_id_mismatch", "应用 ID 不匹配")
    if query["state"] not in config["allowed_states"]:
        raise OAuthCallbackError("state_mismatch", "state 校验失败")
    try:
        timestamp_ms = int(query["timestamp"])
    except ValueError as exc:
        raise OAuthCallbackError("invalid_timestamp", "时间戳格式无效") from exc
    skew = abs(time.time() - timestamp_ms / 1000)
    if skew > int(config.get("max_timestamp_skew_seconds", 600)):
        raise OAuthCallbackError("expired_callback", "授权回调已过期，请重新授权")
    if not _verify_signature(query, config["secret_key"]):
        raise OAuthCallbackError("signature_mismatch", "百度回调签名校验失败")


def _token_data(response: Dict[str, Any]) -> Dict[str, Any]:
    if str(response.get("code")) != "0" or not isinstance(response.get("data"), dict):
        raise OAuthCallbackError("token_exchange_failed", "临时授权码换取令牌失败", 502)
    data = response["data"]
    for key in ("accessToken", "refreshToken", "openId", "userId"):
        if data.get(key) in (None, ""):
            raise OAuthCallbackError("token_exchange_incomplete", "百度返回的授权令牌信息不完整", 502)
    return data


def _fetch_user_info(
    token: Dict[str, Any],
    transport: Callable[[str, Dict[str, Any], int], Dict[str, Any]],
) -> Dict[str, Any]:
    sub_users = []  # type: List[Dict[str, Any]]
    last_user_id = 1
    master_data = {}  # type: Dict[str, Any]
    for _ in range(100):
        payload = {
            "openId": token["openId"],
            "accessToken": token["accessToken"],
            "userId": token["userId"],
            "needSubList": True,
            "pageSize": 500,
            "lastPageMaxUcId": last_user_id,
        }
        response = transport(USER_INFO_URL, payload, 20)
        if str(response.get("code")) != "0" or not isinstance(response.get("data"), dict):
            raise OAuthCallbackError("user_info_failed", "授权账户信息查询失败", 502)
        data = response["data"]
        if not master_data:
            master_data = {
                "masterUid": data.get("masterUid"),
                "masterName": data.get("masterName"),
                "userAcctType": data.get("userAcctType"),
            }
        page = [item for item in (data.get("subUserList") or []) if isinstance(item, dict)]
        sub_users.extend(page)
        if not data.get("hasNext"):
            break
        page_ids = [int(item["ucId"]) for item in page if str(item.get("ucId") or "").isdigit()]
        if not page_ids or max(page_ids) <= last_user_id:
            raise OAuthCallbackError("sub_account_pagination_error", "子账户列表分页异常", 502)
        last_user_id = max(page_ids)
    else:
        raise OAuthCallbackError("sub_account_pagination_limit", "子账户列表分页超过安全上限", 502)
    master_data["subUserList"] = sub_users
    return master_data


def process_oauth_callback(
    query: Dict[str, str],
    config: Dict[str, Any],
    transport: Callable[[str, Dict[str, Any], int], Dict[str, Any]] = _post_json,
) -> Dict[str, Any]:
    _validate_callback(query, config)
    user_id = int(query["userId"])
    token_response = transport(
        ACCESS_TOKEN_URL,
        {
            "appId": config["app_id"],
            "authCode": query["authCode"],
            "secretKey": config["secret_key"],
            "grantType": "auth_code",
            "userId": user_id,
        },
        20,
    )
    token = _token_data(token_response)
    user_info = _fetch_user_info(token, transport)
    return {
        "format": EXPORT_FORMAT,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app_id": config["app_id"],
        "authorization": {
            "access_token": token["accessToken"],
            "refresh_token": token["refreshToken"],
            "open_id": token["openId"],
            "user_id": token["userId"],
            "expires_time": token.get("expiresTime"),
            "refresh_expires_time": token.get("refreshExpiresTime"),
            "expires_in": token.get("expiresIn"),
            "refresh_expires_in": token.get("refreshExpiresIn"),
            "scope": token.get("scope"),
            "master_uid": user_info.get("masterUid"),
            "master_name": user_info.get("masterName"),
            "user_account_type": user_info.get("userAcctType"),
            "sub_accounts": [
                {"user_id": item.get("ucId"), "user_name": item.get("ucName")}
                for item in user_info.get("subUserList") or []
            ],
        },
    }


def _response(status_code: int, payload: Dict[str, Any], filename: Optional[str] = None) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    }
    if filename:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return {
        "isBase64Encoded": False,
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }


def _extract_json_body(event: Dict[str, Any]) -> Dict[str, Any]:
    raw_body = event.get("body", "")
    if event.get("isBase64Encoded"):
        try:
            raw_body = base64.b64decode(str(raw_body)).decode("utf-8")
        except Exception as exc:
            raise OAuthCallbackError("invalid_json_body", "刷新请求正文无效") from exc
    if isinstance(raw_body, dict):
        return raw_body
    try:
        payload = json.loads(str(raw_body or ""))
    except (TypeError, ValueError) as exc:
        raise OAuthCallbackError("invalid_json_body", "刷新请求正文无效") from exc
    if not isinstance(payload, dict):
        raise OAuthCallbackError("invalid_json_body", "刷新请求正文无效")
    return payload


def refresh_handler(event, context):
    event = event or {}
    method = str(event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method") or "POST")
    if method.upper() != "POST":
        return _response(405, {"status": "error", "code": "method_not_allowed"})
    try:
        payload = _extract_json_body(event)
        result = process_refresh_request(payload, event.get("headers") or {}, _load_config())
        return _response(200, {"status": "ok", "authorization": result})
    except OAuthCallbackError as exc:
        return _response(exc.status_code, {"status": "error", "code": exc.code, "message": str(exc)})
    except Exception:
        return _response(500, {"status": "error", "code": "internal_error", "message": "更新授权令牌失败"})


def main_handler(event, context):
    event = event or {}
    path = str(event.get("path") or event.get("rawPath") or "")
    if path.rstrip("/") == "/baidu/oauth/refresh":
        return refresh_handler(event, context)
    query = _extract_query(event or {})
    if not query:
        return _response(200, {"status": "ready", "service": "baidu-oauth-callback"})
    try:
        bundle = process_oauth_callback(query, _load_config())
        user_id = bundle["authorization"]["user_id"]
        return _response(200, bundle, f"baidu_oauth_{user_id}.baidu-auth")
    except OAuthCallbackError as exc:
        return _response(exc.status_code, {"status": "error", "code": exc.code, "message": str(exc)})
    except Exception:
        return _response(500, {"status": "error", "code": "internal_error", "message": "授权处理失败，请检查云函数日志"})
