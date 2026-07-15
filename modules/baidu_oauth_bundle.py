from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


EXPORT_FORMAT = "baidu-oauth-export-v1"
PROFILE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,79}$")


class BaiduOAuthImportError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise BaiduOAuthImportError(f"找不到授权文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise BaiduOAuthImportError("授权文件不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise BaiduOAuthImportError("授权文件结构无效")
    return data


def _validate_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    if bundle.get("format") != EXPORT_FORMAT:
        raise BaiduOAuthImportError("授权文件格式或版本不受支持")
    app_id = str(bundle.get("app_id") or "").strip()
    authorization = bundle.get("authorization")
    if not app_id or not isinstance(authorization, dict):
        raise BaiduOAuthImportError("授权文件缺少应用或授权信息")
    required = ("access_token", "refresh_token", "open_id", "user_id")
    missing = [key for key in required if authorization.get(key) in (None, "")]
    if missing:
        raise BaiduOAuthImportError("授权文件缺少必要令牌字段")
    if str(authorization.get("access_token")).count(".") != 2:
        raise BaiduOAuthImportError("accessToken 格式无效")
    if str(authorization.get("refresh_token")).count(".") != 2:
        raise BaiduOAuthImportError("refreshToken 格式无效")
    return authorization


def _expected_app_ids(secrets: dict[str, Any]) -> set[str]:
    return {
        str(item.get("app_id") or "").strip()
        for item in (secrets.get("baidu_api") or {}).values()
        if isinstance(item, dict) and item.get("app_id")
    }


def import_baidu_oauth_bundle(
    root: Path,
    source_path: str | Path,
    api_profile: str,
) -> dict[str, Any]:
    profile = str(api_profile or "").strip()
    if not PROFILE_PATTERN.fullmatch(profile):
        raise BaiduOAuthImportError("API profile 只允许小写字母、数字、下划线和短横线")

    source = Path(source_path)
    bundle = _read_json(source)
    authorization = _validate_bundle(bundle)
    app_id = str(bundle["app_id"]).strip()
    secrets_path = root / "secrets" / "secrets.json"
    secrets = _read_json(secrets_path)
    expected_ids = _expected_app_ids(secrets)
    if expected_ids and app_id not in expected_ids:
        raise BaiduOAuthImportError("授权文件的应用 ID 与本机已配置应用不一致")

    backup_dir = root / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"secrets_before_oauth_{profile}_{timestamp}.json"
    shutil.copy2(secrets_path, backup_path)

    record = {
        "access_token": authorization["access_token"],
        "refresh_token": authorization["refresh_token"],
        "open_id": authorization["open_id"],
        "user_id": authorization["user_id"],
        "app_id": app_id,
        "expires_time": authorization.get("expires_time"),
        "refresh_expires_time": authorization.get("refresh_expires_time"),
        "expires_in": authorization.get("expires_in"),
        "refresh_expires_in": authorization.get("refresh_expires_in"),
        "scope": authorization.get("scope"),
        "master_uid": authorization.get("master_uid"),
        "master_name": authorization.get("master_name"),
        "user_account_type": authorization.get("user_account_type"),
        "sub_accounts": authorization.get("sub_accounts") or [],
        "token_type": "standard_oauth",
        "imported_at": datetime.now().isoformat(timespec="seconds"),
    }
    secrets.setdefault("baidu_api", {})[profile] = record
    temp_path = secrets_path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(secrets, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, secrets_path)

    return {
        "passed": True,
        "api_profile": profile,
        "authorized_user_id": record["user_id"],
        "user_account_type": record["user_account_type"],
        "sub_account_count": len(record["sub_accounts"]),
        "backup_path": str(backup_path),
        "source_path": str(source),
        "source_should_be_deleted": True,
    }
