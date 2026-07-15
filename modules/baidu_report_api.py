from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from modules.validators import get_required_accounts, validate_baidu_report


REPORT_API_URL = "https://api.baidu.com/json/sms/service/OpenApiReportService/getReportData"
ACCOUNT_REPORT_TYPE = 2208157
REPORT_COLUMNS = ["date", "userName", "userId", "impression", "click", "cost"]


class BaiduReportApiError(RuntimeError):
    pass


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _number(value: Any, *, integer: bool = False) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    if integer:
        return int(parsed) if parsed.is_integer() else None
    return round(parsed, 2)


def _account_user_ids(config: dict[str, Any]) -> tuple[list[int], dict[int, str]]:
    user_ids: list[int] = []
    account_by_id: dict[int, str] = {}
    for standard_name, account in (config.get("accounts") or {}).items():
        candidates = account.get("baidu_user_ids") or account.get("kst_ids") or []
        if not candidates:
            raise BaiduReportApiError(f"账户 {standard_name} 未配置百度推广 ID")
        raw_id = str(candidates[0]).strip()
        if not raw_id.isdigit():
            raise BaiduReportApiError(f"账户 {standard_name} 的百度推广 ID 不是纯数字")
        user_id = int(raw_id)
        if user_id in account_by_id:
            raise BaiduReportApiError(f"百度推广 ID 重复：{user_id}")
        user_ids.append(user_id)
        account_by_id[user_id] = str(standard_name)
    if not user_ids:
        raise BaiduReportApiError("当前项目没有可用于 API 报表的账户 ID")
    return user_ids, account_by_id


def _load_api_auth(root: Path, config: dict[str, Any]) -> tuple[str, str, str]:
    secrets_path = _resolve_path(root, config.get("credentials_path", "secrets/secrets.json"))
    if not secrets_path.exists():
        raise BaiduReportApiError(f"找不到凭据文件：{secrets_path}")
    secrets = _read_json(secrets_path)

    credential_profile = str(
        config.get("baidu", {}).get("credential_profile")
        or config.get("baidu", {}).get("credential_project")
        or ""
    )
    api_profile = str(config.get("baidu", {}).get("api_profile") or "")
    if not credential_profile:
        raise BaiduReportApiError("当前项目未配置百度登录 profile")
    if not api_profile:
        raise BaiduReportApiError("当前项目未配置 baidu.api_profile，API 通道尚未启用")

    username = str((secrets.get("baidu", {}).get(credential_profile) or {}).get("username") or "").strip()
    token = str((secrets.get("baidu_api", {}).get(api_profile) or {}).get("access_token") or "").strip()
    if not username:
        raise BaiduReportApiError(f"百度凭据 profile 缺少 username：{credential_profile}")
    if not token:
        raise BaiduReportApiError(f"百度 API profile 缺少 access_token：{api_profile}")
    if token.count(".") != 2:
        raise BaiduReportApiError(f"百度 API profile 的 access_token 格式无效：{api_profile}")
    return username, token, api_profile


def _post_json(url: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json;charset=UTF-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise BaiduReportApiError(f"百度 API HTTP 请求失败：{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise BaiduReportApiError("百度 API 网络连接失败") from exc
    except TimeoutError as exc:
        raise BaiduReportApiError("百度 API 请求超时") from exc
    except json.JSONDecodeError as exc:
        raise BaiduReportApiError("百度 API 返回内容不是合法 JSON") from exc


def _build_payload(username: str, token: str, user_ids: list[int], target_date: str) -> dict[str, Any]:
    return {
        "header": {"userName": username, "accessToken": token},
        "body": {
            "reportType": ACCOUNT_REPORT_TYPE,
            "userIds": user_ids,
            "startDate": target_date,
            "endDate": target_date,
            "timeUnit": "DAY",
            "columns": REPORT_COLUMNS,
            "sorts": [],
            "filters": [],
            "startRow": 0,
            "rowCount": max(20, len(user_ids)),
            "needSum": True,
        },
    }


def _parse_api_response(
    response: dict[str, Any],
    *,
    config: dict[str, Any],
    account_by_id: dict[int, str],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    errors: list[str] = []
    header = response.get("header") or {}
    failures = header.get("failures") or []
    if header.get("status") != 0 or str(header.get("desc") or "").lower() != "success" or failures:
        codes = ", ".join(str(item.get("code") or "unknown") for item in failures)
        detail = f"，错误码：{codes}" if codes else ""
        errors.append(f"百度 API 返回失败：{header.get('desc') or 'unknown'}{detail}")

    data = (response.get("body") or {}).get("data") or []
    wrapper = data[0] if data and isinstance(data[0], dict) else {}
    rows = wrapper.get("rows") or []
    summary = wrapper.get("summary") or {}
    accounts: dict[str, Any] = {}
    unknown_rows: list[dict[str, Any]] = []

    for row in rows:
        raw_id = row.get("userId")
        try:
            user_id = int(raw_id)
        except (TypeError, ValueError):
            errors.append("百度 API 返回了无效的 userId")
            continue
        standard_name = account_by_id.get(user_id)
        metrics = {
            "展现": _number(row.get("impression"), integer=True),
            "点击": _number(row.get("click"), integer=True),
            "消费": _number(row.get("cost")),
        }
        if not standard_name:
            unknown_rows.append({"userId": user_id, "userName": row.get("userName"), **metrics})
            continue
        if standard_name in accounts:
            errors.append(f"百度 API 返回重复账户：{standard_name}")
            continue
        accounts[standard_name] = {
            "source_account": row.get("userName") or standard_name,
            "source_user_id": user_id,
            **metrics,
        }

    account_report = {"accounts": accounts}
    errors.extend(error for error in validate_baidu_report(account_report, get_required_accounts(config)) if error not in errors)

    account_totals = {
        "impression": sum(row.get("展现") or 0 for row in accounts.values()),
        "click": sum(row.get("点击") or 0 for row in accounts.values()),
        "cost": round(sum(row.get("消费") or 0 for row in accounts.values()), 2),
    }
    summary_metrics = {
        "impression": _number(summary.get("impression"), integer=True),
        "click": _number(summary.get("click"), integer=True),
        "cost": _number(summary.get("cost")),
    }
    if rows and all(value is not None for value in summary_metrics.values()):
        for field, tolerance in (("impression", 0), ("click", 0), ("cost", 0.01)):
            diff = round(float(summary_metrics[field]) - float(account_totals[field]), 2)
            if abs(diff) > tolerance:
                errors.append(f"百度 API 汇总校验失败：{field} 差额 {diff}")
    elif rows:
        errors.append("百度 API 未返回完整汇总指标")

    diagnostics = {
        "api_status": header.get("status"),
        "api_desc": header.get("desc"),
        "failure_codes": [item.get("code") for item in failures],
        "row_count": len(rows),
        "total_row_count": wrapper.get("totalRowCount"),
        "requested_account_count": len(account_by_id),
        "summary": summary_metrics,
        "account_totals": account_totals,
        "unknown_rows": unknown_rows,
    }
    return accounts, diagnostics, errors


def fetch_baidu_api_probe(
    config: dict[str, Any],
    root: Path,
    logger,
    target_date: str | None = None,
    period: str | None = None,
    transport: Callable[[str, dict[str, Any], int], dict[str, Any]] = _post_json,
) -> dict[str, Any]:
    report_path = root / "reports" / "baidu_api_probe_report.json"
    selected_date = target_date or date.today().isoformat()
    started_at = datetime.now().isoformat(timespec="seconds")
    report: dict[str, Any] = {
        "project_id": config.get("project_id"),
        "project_name": config.get("project_name"),
        "date": selected_date,
        "period": period,
        "source": "baidu_open_api_probe",
        "accounts": {},
        "diagnostics": {},
        "errors": [],
        "self_check": {"wrote_excel": False, "production_output_replaced": False},
        "started_at": started_at,
        "finished_at": None,
        "outputs": {"probe_report": str(report_path)},
    }

    try:
        username, token, api_profile = _load_api_auth(root, config)
        user_ids, account_by_id = _account_user_ids(config)
        payload = _build_payload(username, token, user_ids, selected_date)
        response = transport(
            REPORT_API_URL,
            payload,
            int(config.get("baidu", {}).get("api_timeout_seconds", 30)),
        )
        accounts, diagnostics, errors = _parse_api_response(
            response,
            config=config,
            account_by_id=account_by_id,
        )
        report["accounts"] = accounts
        report["diagnostics"] = diagnostics
        report["diagnostics"]["api_profile"] = api_profile
        report["errors"].extend(errors)
    except BaiduReportApiError as exc:
        report["errors"].append(str(exc))
    except Exception as exc:
        report["errors"].append(f"百度 API 探测异常：{type(exc).__name__}")

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    report["self_check"]["passed"] = not report["errors"]
    _write_json(report_path, report)
    logger.info("百度 API 只读探测完成：%s；结果：%s", report_path, "通过" if not report["errors"] else "失败")
    return report
