import base64
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional


ACCESS_TOKEN_URL = "https://u.baidu.com/oauth/accessToken"
REFRESH_TOKEN_URL = "https://u.baidu.com/oauth/refreshToken"
USER_INFO_URL = "https://u.baidu.com/oauth/getUserInfo"
EXPORT_FORMAT = "baidu-oauth-export-v1"
TOKEN_STORE_FORMAT = "baidu-token-store-v1"
TOKEN_PROFILE_FORMAT = "baidu-token-profile-v1"
REQUIRED_QUERY_FIELDS = ("appId", "authCode", "state", "userId", "timestamp", "signature")
REFRESH_REQUEST_FIELDS = frozenset(("appId", "userId", "refreshToken"))
REFRESH_TIMESTAMP_HEADER = "X-Baidu-Refresh-Timestamp"
REFRESH_SIGNATURE_HEADER = "X-Baidu-Refresh-Signature"
PROFILE_PATTERN = re.compile(r"^[a-z0-9_]{3,80}$")
TOKEN_REFRESH_WINDOW_SECONDS = 600
BAIDU_TIMEZONE = timezone(timedelta(hours=8))


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
        "token_store_bucket": os.environ.get("BAIDU_TOKEN_STORE_BUCKET", "").strip(),
        "token_store_region": os.environ.get("BAIDU_TOKEN_STORE_REGION", "").strip(),
        "token_store_key": os.environ.get(
            "BAIDU_TOKEN_STORE_KEY",
            "baidu-oauth/token-store/baidu_oauth_tokens.json",
        ).strip(),
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


def _cos_authorization(
    method: str,
    bucket: str,
    region: str,
    key: str,
    headers: Dict[str, str],
    secret_id: str,
    secret_key: str,
    now_timestamp: Optional[int] = None,
) -> str:
    start = int(time.time()) if now_timestamp is None else int(now_timestamp)
    end = start + 600
    key_time = "%d;%d" % (start, end)
    sign_time = key_time
    signed_headers = sorted(key.lower() for key in headers)
    header_string = "&".join(
        "%s=%s" % (
            name,
            urllib.parse.quote(str(headers[name]), safe="-_.~").lower(),
        )
        for name in signed_headers
    )
    path = "/" + key.lstrip("/")
    http_string = "%s\n%s\n\n%s\n" % (
        method.lower(),
        urllib.parse.quote(path, safe="/-_.~"),
        header_string,
    )
    sign_key = hmac.new(secret_key.encode("utf-8"), key_time.encode("utf-8"), hashlib.sha1).hexdigest()
    string_to_sign = "sha1\n%s\n%s\n" % (
        sign_time,
        hashlib.sha1(http_string.encode("utf-8")).hexdigest(),
    )
    signature = hmac.new(sign_key.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).hexdigest()
    return (
        "q-sign-algorithm=sha1"
        "&q-ak=%s"
        "&q-sign-time=%s"
        "&q-key-time=%s"
        "&q-header-list=%s"
        "&q-url-param-list="
        "&q-signature=%s"
    ) % (secret_id, sign_time, key_time, ";".join(signed_headers), signature)


def _cos_transport(
    method: str,
    bucket: str,
    region: str,
    key: str,
    body: Optional[str] = None,
) -> Dict[str, Any]:
    secret_id = os.environ.get("TENCENT_SECRET_ID", "").strip()
    secret_key = os.environ.get("TENCENT_SECRET_KEY", "").strip()
    token = os.environ.get("TENCENT_TOKEN", "").strip()
    if not secret_id or not secret_key:
        raise OAuthCallbackError("cos_config_missing", "cos secret config missing", 500)
    method = method.upper()
    host = "%s.cos.%s.myqcloud.com" % (bucket, region)
    signed_headers = {"host": host}
    if token:
        signed_headers["x-cos-security-token"] = token
    headers = {
        "Host": host,
        "Authorization": _cos_authorization(method, bucket, region, key, signed_headers, secret_id, secret_key),
    }
    if token:
        headers["x-cos-security-token"] = token
    data = None
    if method == "PUT":
        data = str(body or "").encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    url = "https://%s/%s" % (host, urllib.parse.quote(key.lstrip("/"), safe="/-_.~"))
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8")
            if method == "GET":
                return json.loads(response_body or "{}")
            return {"ok": True}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise OAuthCallbackError("token_store_not_found", "token store not found", 404) from exc
        raise OAuthCallbackError("cos_http_error", "cos http error %s" % exc.code, 502) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OAuthCallbackError("cos_network_error", "cos network error", 502) from exc
    except json.JSONDecodeError as exc:
        raise OAuthCallbackError("token_store_invalid", "token store json invalid", 500) from exc


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


def _validate_signed_payload(
    payload: Dict[str, Any],
    headers: Dict[str, Any],
    config: Dict[str, Any],
    now_timestamp: Optional[int] = None,
) -> None:
    if not config.get("refresh_client_key"):
        raise OAuthCallbackError("server_config_error", "refresh client config missing", 500)
    timestamp = _header_value(headers, REFRESH_TIMESTAMP_HEADER)
    signature = _header_value(headers, REFRESH_SIGNATURE_HEADER)
    if not timestamp or not signature:
        raise OAuthCallbackError("missing_refresh_signature", "refresh signature missing")
    try:
        request_timestamp = int(timestamp)
    except ValueError as exc:
        raise OAuthCallbackError("invalid_refresh_timestamp", "refresh timestamp invalid") from exc
    current_timestamp = int(time.time()) if now_timestamp is None else int(now_timestamp)
    max_skew = int(config.get("refresh_max_timestamp_skew_seconds", 300))
    if abs(current_timestamp - request_timestamp) > max_skew:
        raise OAuthCallbackError("expired_refresh_request", "refresh request expired")
    expected = _refresh_signature(timestamp, payload, str(config["refresh_client_key"]))
    if not hmac.compare_digest(expected.lower(), signature.lower()):
        raise OAuthCallbackError("refresh_signature_mismatch", "refresh signature mismatch")


def _token_store_location(config: Dict[str, Any]) -> tuple:
    bucket = str(config.get("token_store_bucket") or "").strip()
    region = str(config.get("token_store_region") or "").strip()
    key = str(config.get("token_store_key") or "").strip()
    if not bucket or not region or not key:
        raise OAuthCallbackError("token_store_config_missing", "token store config missing", 500)
    return bucket, region, key


def _empty_token_store() -> Dict[str, Any]:
    return {
        "format": TOKEN_STORE_FORMAT,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "profiles": {},
    }


def _normalize_token_store(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise OAuthCallbackError("token_store_invalid", "token store content invalid", 500)
    store = dict(raw)
    store["format"] = TOKEN_STORE_FORMAT
    profiles = store.get("profiles")
    if profiles is None:
        profiles = {}
    elif not isinstance(profiles, dict):
        raise OAuthCallbackError("token_store_invalid", "token store profiles invalid", 500)
    store["profiles"] = profiles
    return store


def load_token_store(
    config: Dict[str, Any],
    cos_transport: Callable[[str, str, str, str, Optional[str]], Dict[str, Any]],
) -> Dict[str, Any]:
    bucket, region, key = _token_store_location(config)
    try:
        return _normalize_token_store(cos_transport("GET", bucket, region, key, None))
    except OAuthCallbackError as exc:
        if exc.status_code == 404 or exc.code == "token_store_not_found":
            return _empty_token_store()
        raise


def save_token_store(
    config: Dict[str, Any],
    store: Dict[str, Any],
    cos_transport: Callable[..., Dict[str, Any]],
) -> None:
    bucket, region, key = _token_store_location(config)
    store["format"] = TOKEN_STORE_FORMAT
    store["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    body = json.dumps(store, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    cos_transport("PUT", bucket, region, key, body)


def _validate_profile_name(api_profile: Any) -> str:
    profile = str(api_profile or "").strip()
    if not PROFILE_PATTERN.match(profile):
        raise OAuthCallbackError("invalid_api_profile", "api profile invalid")
    return profile


def _validate_authorization_record(record: Any) -> Dict[str, Any]:
    if not isinstance(record, dict):
        raise OAuthCallbackError("invalid_authorization", "authorization invalid")
    required = ("access_token", "refresh_token", "open_id", "user_id")
    if any(record.get(key) in (None, "") for key in required):
        raise OAuthCallbackError("invalid_authorization", "authorization incomplete")
    normalized = dict(record)
    try:
        normalized["user_id"] = int(normalized["user_id"])
    except (TypeError, ValueError) as exc:
        raise OAuthCallbackError("invalid_authorization", "authorization user_id invalid") from exc
    return normalized


def get_token_profile(store: Dict[str, Any], api_profile: str) -> Dict[str, Any]:
    profile = _validate_profile_name(api_profile)
    record = store.get("profiles", {}).get(profile)
    if not isinstance(record, dict):
        raise OAuthCallbackError("token_profile_missing", "api authorization profile missing", 401)
    return record


def upsert_token_profile(
    store: Dict[str, Any],
    api_profile: str,
    authorization: Dict[str, Any],
    app_id: str,
) -> Dict[str, Any]:
    profile = _validate_profile_name(api_profile)
    record = _validate_authorization_record(authorization)
    record["app_id"] = app_id
    record["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if isinstance(record.get("sub_accounts"), list):
        record["sub_account_count"] = len(record["sub_accounts"])
    store.setdefault("profiles", {})[profile] = record
    return record


def _token_profile_key(config: Dict[str, Any], api_profile: str) -> str:
    profile = _validate_profile_name(api_profile)
    _bucket, _region, store_key = _token_store_location(config)
    base = store_key[:-5] if store_key.lower().endswith(".json") else store_key.rstrip("/")
    return "%s/profiles/%s.json" % (base, profile)


def load_token_profile(
    config: Dict[str, Any],
    api_profile: str,
    cos_transport: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    profile = _validate_profile_name(api_profile)
    bucket, region, _store_key = _token_store_location(config)
    profile_key = _token_profile_key(config, profile)
    try:
        payload = cos_transport("GET", bucket, region, profile_key, None)
    except OAuthCallbackError as exc:
        if exc.status_code != 404 and exc.code != "token_store_not_found":
            raise
    else:
        if not isinstance(payload, dict) or not isinstance(payload.get("authorization"), dict):
            raise OAuthCallbackError("token_store_invalid", "token profile content invalid", 500)
        if payload.get("format") not in (None, TOKEN_PROFILE_FORMAT):
            raise OAuthCallbackError("token_store_invalid", "token profile format invalid", 500)
        if payload.get("api_profile") not in (None, profile):
            raise OAuthCallbackError("token_store_invalid", "token profile name mismatch", 500)
        return _validate_authorization_record(payload["authorization"])
    return _validate_authorization_record(
        get_token_profile(load_token_store(config, cos_transport), profile)
    )


def save_token_profile(
    config: Dict[str, Any],
    api_profile: str,
    record: Dict[str, Any],
    cos_transport: Callable[..., Dict[str, Any]],
) -> None:
    profile = _validate_profile_name(api_profile)
    authorization = _validate_authorization_record(record)
    bucket, region, _store_key = _token_store_location(config)
    payload = {
        "format": TOKEN_PROFILE_FORMAT,
        "api_profile": profile,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "authorization": authorization,
    }
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    cos_transport("PUT", bucket, region, _token_profile_key(config, profile), body)


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


def _parse_baidu_time(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    normalized = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", text.replace("Z", "+0000"))
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ):
        try:
            parsed = datetime.strptime(normalized, fmt)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=BAIDU_TIMEZONE).astimezone(timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _cloud_token_needs_refresh(record: Dict[str, Any], now_timestamp: Optional[int] = None) -> bool:
    if not record.get("access_token"):
        return True
    if not record.get("refresh_token"):
        raise OAuthCallbackError("reauthorization_required", "refresh token missing", 401)
    expires_at = _parse_baidu_time(record.get("expires_time"))
    if expires_at is None:
        return True
    now = datetime.fromtimestamp(int(time.time()) if now_timestamp is None else int(now_timestamp), timezone.utc)
    return expires_at <= now + timedelta(seconds=TOKEN_REFRESH_WINDOW_SECONDS)


def _refresh_record(
    record: Dict[str, Any],
    config: Dict[str, Any],
    transport: Callable[[str, Dict[str, Any], int], Dict[str, Any]],
) -> Dict[str, Any]:
    if not config.get("app_id") or not config.get("secret_key"):
        raise OAuthCallbackError("server_config_error", "baidu app config missing", 500)
    response = transport(
        REFRESH_TOKEN_URL,
        {
            "appId": config["app_id"],
            "refreshToken": str(record.get("refresh_token") or ""),
            "secretKey": config["secret_key"],
            "userId": int(record.get("user_id")),
        },
        20,
    )
    if str(response.get("code")) != "0" or not isinstance(response.get("data"), dict):
        raise OAuthCallbackError("reauthorization_required", "cloud token refresh failed", 401)
    data = response["data"]
    if not data.get("accessToken") or not data.get("refreshToken"):
        raise OAuthCallbackError("refresh_incomplete", "cloud token refresh response incomplete", 502)
    updated = dict(record)
    updated.update({
        "access_token": data["accessToken"],
        "refresh_token": data["refreshToken"],
        "open_id": data.get("openId") or record.get("open_id"),
        "expires_time": data.get("expiresTime") or record.get("expires_time"),
        "refresh_expires_time": data.get("refreshExpiresTime") or record.get("refresh_expires_time"),
        "expires_in": data.get("expiresIn"),
        "refresh_expires_in": data.get("refreshExpiresIn"),
    })
    return updated


def _token_record_version(record: Dict[str, Any]) -> tuple:
    return (
        str(record.get("access_token") or ""),
        str(record.get("refresh_token") or ""),
        str(record.get("expires_time") or ""),
        str(record.get("refresh_expires_time") or ""),
    )


def process_cloud_token_request(
    payload: Dict[str, Any],
    headers: Dict[str, Any],
    config: Dict[str, Any],
    cos_transport: Callable[[str, str, str, str, Optional[str]], Dict[str, Any]] = _cos_transport,
    oauth_transport: Callable[[str, Dict[str, Any], int], Dict[str, Any]] = _post_json,
    now_timestamp: Optional[int] = None,
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise OAuthCallbackError("invalid_token_request", "token request invalid")
    api_profile = _validate_profile_name(payload.get("apiProfile"))
    if set(payload) - {"apiProfile", "forceRefresh"}:
        raise OAuthCallbackError("invalid_token_request", "token request has unsupported fields")
    _validate_signed_payload(payload, headers, config, now_timestamp)
    record = load_token_profile(config, api_profile, cos_transport)
    if config.get("app_id") and str(record.get("app_id") or "") != str(config["app_id"]):
        raise OAuthCallbackError("app_id_mismatch", "stored authorization app id mismatch", 401)
    refreshed = False
    if bool(payload.get("forceRefresh")) or _cloud_token_needs_refresh(record, now_timestamp):
        previous_record = dict(record)
        try:
            refreshed_record = _refresh_record(record, config, oauth_transport)
        except OAuthCallbackError as exc:
            if exc.code != "reauthorization_required":
                raise
            latest_record = load_token_profile(config, api_profile, cos_transport)
            if (
                _token_record_version(latest_record) == _token_record_version(previous_record)
                or _cloud_token_needs_refresh(latest_record, now_timestamp)
            ):
                raise
            record = latest_record
            refreshed = "concurrent_refresh"
        else:
            latest_record = load_token_profile(config, api_profile, cos_transport)
            if _token_record_version(latest_record) != _token_record_version(previous_record):
                if _cloud_token_needs_refresh(latest_record, now_timestamp):
                    raise OAuthCallbackError("token_store_conflict", "concurrent token refresh incomplete", 409)
                record = latest_record
                refreshed = "concurrent_refresh"
            else:
                save_token_profile(config, api_profile, refreshed_record, cos_transport)
                record = refreshed_record
                refreshed = "refreshed"
    return {
        "api_profile": api_profile,
        "access_token": record["access_token"],
        "open_id": record.get("open_id"),
        "user_id": record.get("user_id"),
        "expires_time": record.get("expires_time"),
        "token_refresh": refreshed if refreshed else "not_needed",
    }


def process_store_profile_request(
    payload: Dict[str, Any],
    headers: Dict[str, Any],
    config: Dict[str, Any],
    cos_transport: Callable[[str, str, str, str, Optional[str]], Dict[str, Any]] = _cos_transport,
    now_timestamp: Optional[int] = None,
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise OAuthCallbackError("invalid_store_profile_request", "store profile request invalid")
    if set(payload) != {"apiProfile", "authorization"}:
        raise OAuthCallbackError("invalid_store_profile_request", "store profile request incomplete")
    if not str(config.get("app_id") or "").strip():
        raise OAuthCallbackError("server_config_error", "baidu app config missing", 500)
    _validate_signed_payload(payload, headers, config, now_timestamp)
    api_profile = _validate_profile_name(payload.get("apiProfile"))
    record = _validate_authorization_record(payload.get("authorization"))
    record["app_id"] = str(config.get("app_id") or "")
    record["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if isinstance(record.get("sub_accounts"), list):
        record["sub_account_count"] = len(record["sub_accounts"])
    save_token_profile(config, api_profile, record, cos_transport)
    return {
        "api_profile": api_profile,
        "user_id": record.get("user_id"),
        "master_name": record.get("master_name"),
        "sub_account_count": int(record.get("sub_account_count") or len(record.get("sub_accounts") or [])),
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


def token_handler(event, context):
    event = event or {}
    method = str(event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method") or "POST")
    if method.upper() != "POST":
        return _response(405, {"status": "error", "code": "method_not_allowed"})
    try:
        payload = _extract_json_body(event)
        result = process_cloud_token_request(payload, event.get("headers") or {}, _load_config())
        return _response(200, {"status": "ok", "authorization": result})
    except OAuthCallbackError as exc:
        return _response(exc.status_code, {"status": "error", "code": exc.code, "message": str(exc)})
    except Exception:
        return _response(500, {"status": "error", "code": "internal_error", "message": "cloud token request failed"})


def store_profile_handler(event, context):
    event = event or {}
    method = str(event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method") or "POST")
    if method.upper() != "POST":
        return _response(405, {"status": "error", "code": "method_not_allowed"})
    try:
        payload = _extract_json_body(event)
        result = process_store_profile_request(payload, event.get("headers") or {}, _load_config())
        return _response(200, {"status": "ok", "profile": result})
    except OAuthCallbackError as exc:
        return _response(exc.status_code, {"status": "error", "code": exc.code, "message": str(exc)})
    except Exception:
        return _response(500, {"status": "error", "code": "internal_error", "message": "store profile request failed"})


def main_handler(event, context):
    event = event or {}
    path = str(event.get("path") or event.get("rawPath") or "")
    if path.rstrip("/") == "/baidu/oauth/refresh":
        return refresh_handler(event, context)
    if path.rstrip("/") == "/baidu/oauth/token":
        return token_handler(event, context)
    if path.rstrip("/") == "/baidu/oauth/store-profile":
        return store_profile_handler(event, context)
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
