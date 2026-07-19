from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from modules.baidu_multi_source import build_source_runtime_config, resolve_baidu_sources
from modules.baidu_report_api import (
    ATTEMPT_ERROR_SUMMARIES,
    BaiduReportApiError,
    fetch_baidu_api_hourly,
)
from modules.config_manager import load_config
from modules.project_config import (
    build_runtime_config_from_project,
    list_projects,
    load_project_config,
)


EXPECTED_PROFILES_BY_PROJECT: dict[str, frozenset[str]] = {
    "changsha_niu": frozenset({"changsha_niu_baidu"}),
    "kunming_niu": frozenset({"kunming_niu_baidu"}),
    "nanjing_bai": frozenset({"nanjing_bai_baidu"}),
    "nanjing_niu": frozenset({"nanjing_niu_baidu"}),
    "ningbo_niu": frozenset({"ningbo_niu_baidu"}),
    "qingdao_bai": frozenset({"qingdao_bai_baidu"}),
    "shenyang_bai": frozenset(
        {"shenyang_bai_source_a_baidu", "shenyang_bai_source_b_baidu"}
    ),
    "shenyang_niu": frozenset(
        {"shenyang_niu_zhongya_baidu", "shenyang_niu_yinkang_baidu"}
    ),
    "shenzhen_bai": frozenset({"shenzhen_bai_baidu"}),
}
EXPECTED_PROJECT_COUNT = 9
EXPECTED_PROFILE_COUNT = 11
VALID_PERIODS = frozenset({"11点", "15点", "18点"})
SAFE_ERROR_CATEGORIES = frozenset(ATTEMPT_ERROR_SUMMARIES)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _default_target_date() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
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


def _inventory_error(summary: str, project_id: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "error_category": "configuration_error",
        "summary": summary,
    }
    if project_id:
        item["project_id"] = project_id
    return item


def _safe_category(exc: BaseException) -> str:
    if isinstance(exc, BaiduReportApiError):
        category = str(exc.category or "api_error")
        if category in SAFE_ERROR_CATEGORIES:
            return category
    return "api_error"


def _safe_summary(category: str) -> str:
    return ATTEMPT_ERROR_SUMMARIES.get(category, ATTEMPT_ERROR_SUMMARIES["api_error"])


def _single_source_entry(runtime: dict[str, Any]) -> dict[str, Any]:
    project_id = str(runtime.get("project_id") or "")
    project_name = str(runtime.get("project_name") or project_id)
    baidu = runtime.get("baidu") if isinstance(runtime.get("baidu"), dict) else {}
    return {
        "project_id": project_id,
        "project_name": project_name,
        "source_id": "default",
        "source_name": project_name,
        "api_profile": str(baidu.get("api_profile") or ""),
        "runtime": runtime,
    }


def _project_entries(runtime: dict[str, Any]) -> list[dict[str, Any]]:
    sources = resolve_baidu_sources(runtime)
    if len(sources) <= 1:
        return [_single_source_entry(runtime)]

    project_id = str(runtime.get("project_id") or "")
    project_name = str(runtime.get("project_name") or project_id)
    entries: list[dict[str, Any]] = []
    for source in sources:
        source_runtime = build_source_runtime_config(runtime, source, task="hourly")
        source_info = source_runtime.get("baidu_source") or {}
        baidu = source_runtime.get("baidu") or {}
        entries.append(
            {
                "project_id": project_id,
                "project_name": project_name,
                "source_id": str(source_info.get("source_id") or "default"),
                "source_name": str(source_info.get("source_name") or project_name),
                "api_profile": str(baidu.get("api_profile") or ""),
                "runtime": source_runtime,
            }
        )
    return entries


def _build_inventory(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    errors: list[dict[str, Any]] = []
    try:
        project_summaries = list_projects(root)
    except Exception:
        return [], [_inventory_error("无法读取生产项目清单")], 0

    project_count = len(project_summaries)
    project_ids = [str(item.get("project_id") or "") for item in project_summaries]
    expected_project_ids = set(EXPECTED_PROFILES_BY_PROJECT)
    if project_count != EXPECTED_PROJECT_COUNT or set(project_ids) != expected_project_ids:
        errors.append(_inventory_error("生产项目清单必须恰好包含九个指定项目"))
    if len(set(project_ids)) != len(project_ids):
        errors.append(_inventory_error("生产项目清单存在重复项目"))

    try:
        base_config = load_config(
            root / "config.json",
            fallback_path=root / "config.example.json",
        )
    except Exception:
        return [], errors + [_inventory_error("无法读取基础运行配置")], project_count

    entries: list[dict[str, Any]] = []
    for project_id in project_ids:
        try:
            project = load_project_config(root, project_id)
            runtime = build_runtime_config_from_project(project, base_config)
            project_entries = _project_entries(runtime)
        except Exception:
            errors.append(_inventory_error("项目 API 映射无法读取", project_id))
            continue
        entries.extend(project_entries)
        actual_profiles = {
            str(entry.get("api_profile") or "")
            for entry in project_entries
            if str(entry.get("api_profile") or "")
        }
        expected_profiles = EXPECTED_PROFILES_BY_PROJECT.get(project_id)
        if expected_profiles is None or actual_profiles != set(expected_profiles):
            errors.append(_inventory_error("项目 API profile 清单与生产基线不一致", project_id))

    profiles = [str(entry.get("api_profile") or "") for entry in entries]
    nonempty_profiles = [profile for profile in profiles if profile]
    if len(nonempty_profiles) != EXPECTED_PROFILE_COUNT:
        errors.append(_inventory_error("生产 API profile 数量必须恰好为十一个"))
    if len(set(nonempty_profiles)) != len(nonempty_profiles):
        errors.append(_inventory_error("生产 API profile 必须保持唯一"))
    expected_profiles = set().union(*EXPECTED_PROFILES_BY_PROJECT.values())
    if set(nonempty_profiles) != expected_profiles:
        errors.append(_inventory_error("生产 API profile 清单与授权基线不一致"))

    unique_errors: list[dict[str, Any]] = []
    seen_errors: set[tuple[str, str, str]] = set()
    for item in errors:
        key = (
            str(item.get("project_id") or ""),
            str(item.get("error_category") or ""),
            str(item.get("summary") or ""),
        )
        if key not in seen_errors:
            seen_errors.add(key)
            unique_errors.append(item)
    return entries, unique_errors, project_count


def run_baidu_api_readiness(
    root: str | Path,
    logger,
    fetch_func: Callable[..., dict[str, Any]] = fetch_baidu_api_hourly,
    *,
    target_date: str | None = None,
    period: str | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    selected_date = str(target_date or _default_target_date())
    selected_period = str(period or "15点")
    started_at = _now()
    report_path = root_path / "reports" / "baidu_api_readiness_report.json"

    input_errors: list[dict[str, Any]] = []
    try:
        date.fromisoformat(selected_date)
    except ValueError:
        input_errors.append(_inventory_error("只读检查日期格式无效"))
    if selected_period not in VALID_PERIODS:
        input_errors.append(_inventory_error("只读检查时段无效"))

    entries, inventory_errors, project_count = _build_inventory(root_path)
    inventory_errors = input_errors + inventory_errors
    profiles = [str(entry.get("api_profile") or "") for entry in entries if entry.get("api_profile")]
    report: dict[str, Any] = {
        "started_at": started_at,
        "finished_at": "",
        "target_date": selected_date,
        "period": selected_period,
        "expected_project_count": EXPECTED_PROJECT_COUNT,
        "project_count": project_count,
        "expected_profile_count": EXPECTED_PROFILE_COUNT,
        "profile_count": len(profiles),
        "unique_profile_count": len(set(profiles)),
        "passed": False,
        "inventory_errors": inventory_errors,
        "results": [],
    }

    if not inventory_errors:
        for entry in entries:
            checked_at = _now()
            result: dict[str, Any] = {
                "project_id": entry["project_id"],
                "project_name": entry["project_name"],
                "source_id": entry["source_id"],
                "source_name": entry["source_name"],
                "api_profile": entry["api_profile"],
                "account_count": 0,
                "passed": False,
                "error_category": None,
                "summary": "",
                "started_at": checked_at,
                "finished_at": "",
            }
            try:
                api_report = fetch_func(
                    config=entry["runtime"],
                    root=root_path,
                    logger=logger,
                    period=selected_period,
                    target_date=selected_date,
                    commit_standard_report=False,
                    commit_attempt_report=False,
                    task_context={},
                )
                expected_accounts = entry["runtime"].get("accounts")
                accounts = api_report.get("accounts") if isinstance(api_report, dict) else None
                errors = api_report.get("errors") if isinstance(api_report, dict) else None
                if (
                    not isinstance(api_report, dict)
                    or "errors" not in api_report
                    or type(errors) is not list
                    or bool(errors)
                    or not isinstance(accounts, dict)
                    or not accounts
                    or not isinstance(expected_accounts, dict)
                    or set(accounts) != set(expected_accounts)
                ):
                    raise BaiduReportApiError(
                        "百度 API 返回数据未通过完整性校验",
                        category="integrity_error",
                    )
                result["account_count"] = len(accounts)
                result["passed"] = True
                result["summary"] = "百度 API 只读检查通过"
                logger.info(
                    "百度 API 只读检查通过：项目=%s；来源=%s；profile=%s；账户数=%s",
                    entry["project_id"],
                    entry["source_id"],
                    entry["api_profile"],
                    len(accounts),
                )
            except Exception as exc:
                category = _safe_category(exc)
                result["error_category"] = category
                result["summary"] = _safe_summary(category)
                logger.warning(
                    "百度 API 只读检查失败：项目=%s；来源=%s；profile=%s；类别=%s",
                    entry["project_id"],
                    entry["source_id"],
                    entry["api_profile"],
                    category,
                )
            result["finished_at"] = _now()
            report["results"].append(result)
        report["passed"] = bool(report["results"]) and all(
            item.get("passed") is True for item in report["results"]
        )

    report["finished_at"] = _now()
    _write_json_atomic(report_path, report)
    return report
