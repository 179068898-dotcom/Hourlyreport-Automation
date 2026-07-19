from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.baidu_token_manager import secrets_file_lock


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


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


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
    app_ids = {
        str(item.get("app_id") or "").strip()
        for item in (secrets.get("baidu_api") or {}).values()
        if isinstance(item, dict) and item.get("app_id")
    }
    gateway = secrets.get("baidu_api_gateway")
    if isinstance(gateway, dict) and gateway.get("app_id"):
        app_ids.add(str(gateway["app_id"]).strip())
    return app_ids


def _promotion_ids(accounts: Any) -> list[int]:
    result: set[int] = set()
    for account in accounts if isinstance(accounts, list) else []:
        if not isinstance(account, dict):
            continue
        values = account.get("baidu_user_ids") or account.get("kst_ids") or []
        for value in values if isinstance(values, list) else [values]:
            text = str(value or "").strip()
            if text.isdigit() and int(text) > 0:
                result.add(int(text))
    return sorted(result)


def _project_match_candidates(root: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    projects_dir = root / "configs" / "projects"
    for path in sorted(projects_dir.glob("*.json")):
        if path.name.startswith("project_template"):
            continue
        try:
            project = _read_json(path)
        except BaiduOAuthImportError:
            continue
        project_id = str(project.get("project_id") or "").strip()
        if project.get("is_template") is True or project_id == "demo_project" or project_id.startswith("demo_"):
            continue
        sources = project.get("baidu_sources")
        if isinstance(sources, list) and sources:
            for source in sources:
                if not isinstance(source, dict):
                    continue
                api_profile = str(source.get("api_profile") or "").strip()
                promotion_ids = _promotion_ids(source.get("accounts"))
                if api_profile and promotion_ids:
                    candidates.append({
                        "api_profile": api_profile,
                        "project_id": project_id,
                        "source_id": str(source.get("source_id") or "").strip() or None,
                        "promotion_ids": promotion_ids,
                    })
            continue
        baidu = project.get("baidu") if isinstance(project.get("baidu"), dict) else {}
        api_profile = str(baidu.get("api_profile") or "").strip()
        promotion_ids = _promotion_ids(project.get("accounts"))
        if api_profile and promotion_ids:
            candidates.append({
                "api_profile": api_profile,
                "project_id": project_id,
                "source_id": None,
                "promotion_ids": promotion_ids,
            })
    return candidates


def match_baidu_oauth_profile(root: Path, bundle: dict[str, Any]) -> dict[str, Any]:
    authorization = _validate_bundle(bundle)
    secrets = _read_json(Path(root) / "secrets" / "secrets.json")
    gateway = secrets.get("baidu_api_gateway")
    expected_app_id = str(gateway.get("app_id") or "").strip() if isinstance(gateway, dict) else ""
    if not expected_app_id:
        raise BaiduOAuthImportError("本机缺少百度 API 网关应用 ID，无法自动匹配授权")
    if str(bundle.get("app_id") or "").strip() != expected_app_id:
        raise BaiduOAuthImportError("授权文件的应用 ID 与本机刷新服务不一致")

    authorization_ids: set[int] = set()
    for account in authorization.get("sub_accounts") or []:
        if not isinstance(account, dict):
            continue
        raw_id = str(account.get("user_id") or "").strip()
        if raw_id.isdigit() and int(raw_id) > 0:
            authorization_ids.add(int(raw_id))
    if not authorization_ids:
        raise BaiduOAuthImportError("授权文件没有可匹配的子账户推广 ID")

    candidates = _project_match_candidates(Path(root))
    matches = [
        candidate
        for candidate in candidates
        if set(candidate["promotion_ids"]) == authorization_ids
    ]
    if not matches:
        matches = [
            candidate
            for candidate in candidates
            if set(candidate["promotion_ids"]).issubset(authorization_ids)
        ]
    if not matches:
        raise BaiduOAuthImportError("授权文件未匹配到任何项目来源，请核对登录的超管账号")
    if len(matches) > 1:
        raise BaiduOAuthImportError("授权文件同时匹配多个项目来源，已停止导入")
    match = dict(matches[0])
    ignored_ids = sorted(authorization_ids - set(match["promotion_ids"]))
    if ignored_ids:
        match["ignored_authorized_promotion_ids"] = ignored_ids
    return match


def import_baidu_oauth_bundle(
    root: Path,
    source_path: str | Path,
    api_profile: str,
) -> dict[str, Any]:
    profile = str(api_profile or "").strip()
    source = Path(source_path)
    bundle = _read_json(source)
    match: dict[str, Any] | None = None
    if profile.casefold() == "auto":
        match = match_baidu_oauth_profile(root, bundle)
        profile = str(match["api_profile"])
    if not PROFILE_PATTERN.fullmatch(profile):
        raise BaiduOAuthImportError("API profile 只允许小写字母、数字、下划线和短横线")

    authorization = _validate_bundle(bundle)
    app_id = str(bundle["app_id"]).strip()
    secrets_path = root / "secrets" / "secrets.json"
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
    with secrets_file_lock(secrets_path):
        secrets = _read_json(secrets_path)
        expected_ids = _expected_app_ids(secrets)
        if expected_ids and app_id not in expected_ids:
            raise BaiduOAuthImportError("授权文件的应用 ID 与本机已配置应用不一致")

        backup_dir = root / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = backup_dir / f"secrets_before_oauth_{profile}_{timestamp}.json"
        shutil.copy2(secrets_path, backup_path)

        secrets.setdefault("baidu_api", {})[profile] = record
        _write_json_atomic(secrets_path, secrets)

    report = {
        "passed": True,
        "api_profile": profile,
        "authorized_user_id": record["user_id"],
        "user_account_type": record["user_account_type"],
        "sub_account_count": len(record["sub_accounts"]),
        "backup_path": str(backup_path),
        "source_path": str(source),
        "source_should_be_deleted": True,
    }
    if match is not None:
        report.update({
            "matched_project_id": match["project_id"],
            "matched_source_id": match["source_id"],
            "matched_promotion_ids": match["promotion_ids"],
        })
        if match.get("ignored_authorized_promotion_ids"):
            report["ignored_authorized_promotion_ids"] = match["ignored_authorized_promotion_ids"]
    return report
