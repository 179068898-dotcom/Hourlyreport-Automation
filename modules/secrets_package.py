from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


PACKAGE_FORMAT = "baidu-secrets-package-v1"


class SecretsPackageError(RuntimeError):
    pass


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise SecretsPackageError(f"找不到{label}：{path}") from exc
    except (OSError, UnicodeError) as exc:
        raise SecretsPackageError(f"无法读取{label}：{path}") from exc
    except json.JSONDecodeError as exc:
        raise SecretsPackageError(f"{label}不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise SecretsPackageError(f"{label}根节点必须是对象")
    return value


def _validate_secrets(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SecretsPackageError("授权配置根节点必须是对象")
    if not isinstance(payload.get("baidu"), dict):
        raise SecretsPackageError("授权配置缺少有效的 baidu 配置")
    if "baidu_api" in payload and not isinstance(payload["baidu_api"], dict):
        raise SecretsPackageError("授权配置中的 baidu_api 结构无效")
    return payload


def _payload_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_payload_bytes(payload)).hexdigest()


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=path.name + ".",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    except OSError as exc:
        raise SecretsPackageError(f"无法写入授权配置：{path}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _profile_counts(payload: dict[str, Any]) -> tuple[int, int]:
    baidu = payload.get("baidu") or {}
    baidu_api = payload.get("baidu_api") or {}
    return len(baidu), len(baidu_api)


def _next_backup_path(backup_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = backup_dir / f"secrets_before_package_import_{timestamp}.json"
    index = 1
    while candidate.exists():
        candidate = backup_dir / f"secrets_before_package_import_{timestamp}_{index}.json"
        index += 1
    return candidate


def export_secrets_package(
    secrets_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    source = Path(secrets_path)
    destination = Path(output_path)
    payload = _validate_secrets(_read_json(source, "账号授权配置"))
    exported_at = datetime.now().isoformat(timespec="seconds")
    wrapper = {
        "format": PACKAGE_FORMAT,
        "exported_at": exported_at,
        "payload_sha256": _payload_sha256(payload),
        "secrets": payload,
    }
    _atomic_write_json(destination, wrapper)
    baidu_count, api_count = _profile_counts(payload)
    return {
        "passed": True,
        "package_path": str(destination),
        "exported_at": exported_at,
        "baidu_profile_count": baidu_count,
        "api_profile_count": api_count,
    }


def import_secrets_package(
    package_path: str | Path,
    secrets_path: str | Path,
    backup_dir: str | Path,
) -> dict[str, Any]:
    source = Path(package_path)
    target = Path(secrets_path)
    backups = Path(backup_dir)
    wrapper = _read_json(source, "授权配置包")
    if wrapper.get("format") != PACKAGE_FORMAT:
        raise SecretsPackageError("授权配置包格式或版本不受支持")
    payload = _validate_secrets(wrapper.get("secrets"))
    expected_hash = str(wrapper.get("payload_sha256") or "").strip().lower()
    actual_hash = _payload_sha256(payload)
    if len(expected_hash) != 64 or expected_hash != actual_hash:
        raise SecretsPackageError("授权配置包校验失败，文件可能损坏或被修改")

    backup_path: Path | None = None
    if target.exists():
        try:
            backups.mkdir(parents=True, exist_ok=True)
            backup_path = _next_backup_path(backups)
            shutil.copy2(target, backup_path)
        except OSError as exc:
            raise SecretsPackageError("无法备份本机原账号授权配置，导入已停止") from exc

    _atomic_write_json(target, payload)
    baidu_count, api_count = _profile_counts(payload)
    return {
        "passed": True,
        "package_path": str(source),
        "secrets_path": str(target),
        "backup_path": str(backup_path) if backup_path else None,
        "baidu_profile_count": baidu_count,
        "api_profile_count": api_count,
    }
