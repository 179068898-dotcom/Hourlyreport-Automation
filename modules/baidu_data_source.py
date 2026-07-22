from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from modules.baidu_auto import fetch_baidu_auto
from modules.baidu_daily import fetch_baidu_daily
from modules.baidu_multi_source import (
    aggregate_baidu_source_reports,
    build_cost_validation,
    build_source_runtime_config,
    resolve_baidu_sources,
)
from modules.baidu_report_api import (
    BaiduReportApiError,
    fetch_baidu_api_daily,
    fetch_baidu_api_hourly,
)


API_REPAIR_BUDGET_SECONDS = 20.0
SAFE_FAILURE_CATEGORIES = {
    "api_error",
    "api_timeout",
    "authorization_error",
    "integrity_error",
    "network_error",
    "reauthorization_required",
}
API_RETRY_LIMITS = {"network_error": 3, "integrity_error": 2}


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


def _log(logger, level: str, message: str, *args: Any) -> None:
    method = getattr(logger, level, None)
    if callable(method):
        method(message, *args)


def _mode(config: dict[str, Any]) -> str:
    value = str(config.get("baidu", {}).get("data_source_mode") or "browser").strip().lower()
    return value if value in {"browser", "api_shadow", "api_preferred"} else "browser"


def _mode_label(mode: str) -> str:
    if mode == "api_preferred":
        return "API 优先"
    if mode == "api_shadow":
        return "API 影子（浏览器为准）"
    return "浏览器"


def _actual_source_label(data_source: str) -> str:
    labels = {
        "api": "API",
        "browser": "浏览器",
        "browser_fallback": "浏览器降级",
        "browser_shadow": "浏览器（影子模式）",
    }
    return labels.get(data_source, "无（读取失败）")


def _log_actual_source(logger, data_source: str) -> None:
    _log(logger, "info", "[实际来源] %s", _actual_source_label(data_source))


def _failure_category(exc: Exception) -> str:
    category = str(getattr(exc, "category", "api_error") or "api_error")
    return category if category in SAFE_FAILURE_CATEGORIES else "api_error"


def _successful(report: Any) -> bool:
    return isinstance(report, dict) and not report.get("errors")


def _api_attempts(
    *,
    api_fetcher: Callable[..., dict[str, Any]],
    api_kwargs: dict[str, Any],
    commit_standard_report: bool,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    logger,
    started: float | None = None,
    deadline: float | None = None,
) -> tuple[dict[str, Any] | None, int, list[str], str | None]:
    started_at = clock() if started is None else started
    deadline_at = started_at + API_REPAIR_BUDGET_SECONDS if deadline is None else deadline
    attempts = 0
    actions: list[str] = []
    task_context: dict[str, Any] = {
        "refresh_attempted": False,
        "report_request_count": 0,
        "self_heal_actions": actions,
    }
    last_category: str | None = None

    def measured_attempts() -> int:
        request_count = int(task_context.get("report_request_count") or 0)
        return request_count or attempts

    while True:
        attempts += 1
        try:
            report = api_fetcher(
                **api_kwargs,
                commit_standard_report=commit_standard_report,
                task_context=task_context,
                deadline=deadline_at,
                clock=clock,
            )
            if not _successful(report):
                category = str((report or {}).get("error_category") or "integrity_error")
                raise BaiduReportApiError("百度 API 返回未通过完整性校验", category=category)
            if clock() >= deadline_at:
                _log(logger, "warning", "百度 API 成功返回时已超过项目自修复预算")
                return None, measured_attempts(), actions, "api_budget_exhausted"
            return report, measured_attempts(), actions, None
        except Exception as exc:
            last_category = _failure_category(exc)
            retry_limit = API_RETRY_LIMITS.get(last_category, 1)
            if attempts >= retry_limit or clock() >= deadline_at:
                _log(logger, "warning", "百度 API 通道失败：%s", last_category)
                return None, measured_attempts(), actions, last_category
            action = "network_retry" if last_category == "network_error" else "integrity_retry"
            actions.append(action)
            _log(logger, "warning", "百度 API 自修复：%s（第 %s 次）", action, attempts)
            remaining = deadline_at - clock()
            if remaining <= 0:
                return None, measured_attempts(), actions, last_category
            sleep(min(1.0, remaining))


def _browser_result(
    *,
    config: dict[str, Any],
    root: Path,
    task: str,
    browser_fetcher: Callable[..., dict[str, Any]],
    browser_kwargs: dict[str, Any],
) -> dict[str, Any]:
    canonical_path = _standard_report_path(root, task, config)
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    staged_path = canonical_path.with_name(
        f".{canonical_path.stem}.browser-{uuid4().hex}.tmp.json"
    )
    staged_config = deepcopy(config)
    baidu = dict(staged_config.get("baidu") or {})
    output_key = "daily_output_path" if task == "daily" else "output_path"
    baidu[output_key] = str(staged_path)
    staged_config["baidu"] = baidu
    staged_kwargs = dict(browser_kwargs)
    staged_kwargs["config"] = staged_config
    try:
        report = browser_fetcher(**staged_kwargs)
    except Exception:
        return {"accounts": {}, "errors": ["浏览器百度数据读取失败"], "source": "browser"}
    finally:
        try:
            staged_path.unlink(missing_ok=True)
        except OSError:
            pass
    if isinstance(report, dict):
        return report
    return {"accounts": {}, "errors": ["浏览器百度数据读取结果无效"], "source": "browser"}


def _with_route_metadata(
    report: dict[str, Any],
    *,
    data_source: str,
    api_attempts: int,
    actions: list[str],
    fallback_reason: str | None,
) -> dict[str, Any]:
    result = dict(report)
    result["data_source"] = data_source
    result["api_attempts"] = api_attempts
    result["self_heal_actions"] = list(actions)
    result["fallback_reason"] = fallback_reason
    return result


def _standard_report_path(
    root: Path,
    task: str,
    config: dict[str, Any] | None = None,
) -> Path:
    baidu = (config or {}).get("baidu")
    baidu = baidu if isinstance(baidu, dict) else {}
    output_key = "daily_output_path" if task == "daily" else "output_path"
    default_path = "reports/baidu_daily_data.json" if task == "daily" else "reports/baidu_account_data.json"
    path = Path(baidu.get(output_key, default_path))
    return path if path.is_absolute() else root / path


def _commit_routed_report(
    root: Path,
    task: str,
    config: dict[str, Any],
    report: dict[str, Any],
) -> None:
    canonical_path = _standard_report_path(root, task, config)
    outputs = report.get("outputs")
    if isinstance(outputs, dict):
        output_key = "daily_data" if task == "daily" else "account_data"
        report = dict(report)
        report["outputs"] = {**outputs, output_key: str(canonical_path)}
    _write_json_atomic(canonical_path, report)


def _deduplicate(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _source_account_conflicts(source_reports: list[dict[str, Any]]) -> list[str]:
    owners: dict[str, str] = {}
    conflicts: list[str] = []
    for item in source_reports:
        source_id = str(item.get("source_id") or "")
        for account in (item.get("report") or {}).get("accounts") or {}:
            owner = owners.get(account)
            if owner is not None and owner != source_id:
                conflicts.append(f"百度 API 多来源账户冲突：{account}")
            else:
                owners[account] = source_id
    return conflicts


def _source_total_cost(source_reports: list[dict[str, Any]]) -> float | None:
    total = 0.0
    for item in source_reports:
        for row in ((item.get("report") or {}).get("accounts") or {}).values():
            value = row.get("消费") if isinstance(row, dict) else None
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return None
            total += float(value)
    return total


def _collect_baidu_multi_source_api(
    *,
    config: dict[str, Any],
    root: Path,
    logger,
    api_fetcher: Callable[..., dict[str, Any]],
    task: str,
    period: str | None,
    target_date: str | None,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    commit_standard_report: bool,
    commit_attempt_report: bool = True,
) -> tuple[dict[str, Any] | None, int, list[str], str | None]:
    sources = resolve_baidu_sources(config)
    started = clock()
    deadline = started + API_REPAIR_BUDGET_SECONDS
    source_reports: list[dict[str, Any]] = []
    total_attempts = 0
    all_actions: list[str] = []

    for index, source in enumerate(sources):
        if index > 0 and clock() >= deadline:
            return None, total_attempts, _deduplicate(all_actions), "api_budget_exhausted"
        source_id = str(source.get("source_id") or "default")
        source_name = str(source.get("source_name") or source_id)
        _log(logger, "info", "[API %s/%s] 正在读取%s", index + 1, len(sources), source_name)
        source_config = build_source_runtime_config(config, source, task=task)
        api_kwargs: dict[str, Any] = {
            "config": source_config,
            "root": root,
            "logger": logger,
            "commit_attempt_report": commit_attempt_report,
        }
        if task == "daily":
            api_kwargs["target_date"] = target_date
        else:
            api_kwargs["period"] = period
        report, attempts, actions, failure = _api_attempts(
            api_fetcher=api_fetcher,
            api_kwargs=api_kwargs,
            commit_standard_report=False,
            started=started,
            deadline=deadline,
            clock=clock,
            sleep=sleep,
            logger=logger,
        )
        total_attempts += attempts
        all_actions.extend(actions)
        if report is None:
            return None, total_attempts, _deduplicate(all_actions), failure
        source_reports.append({
            "source_id": source_id,
            "source_name": source_name,
            "report": report,
        })

    if _source_account_conflicts(source_reports):
        return None, total_attempts, _deduplicate(all_actions), "integrity_error"

    aggregated = aggregate_baidu_source_reports(
        config,
        source_reports,
        period=period,
        target_date=target_date,
        output_source="baidu_open_api_multi_source",
        task=task,
    )
    source_total = _source_total_cost(source_reports)
    if source_total is None:
        return None, total_attempts, _deduplicate(all_actions), "integrity_error"
    cost_validation = build_cost_validation(source_total, aggregated.get("final_total_cost", 0))
    if aggregated.get("errors") or not cost_validation["passed"]:
        return None, total_attempts, _deduplicate(all_actions), "integrity_error"
    if clock() >= deadline:
        return None, total_attempts, _deduplicate(all_actions), "api_budget_exhausted"

    actions = _deduplicate(all_actions)
    aggregated = _with_route_metadata(
        aggregated,
        data_source="api",
        api_attempts=total_attempts,
        actions=actions,
        fallback_reason=None,
    )
    aggregated["source_count"] = len(source_reports)
    aggregated["source_validation"] = {
        "all_sources_passed": True,
        "account_conflicts": [],
        "cost_validation_passed": True,
    }
    if commit_standard_report:
        _write_json_atomic(_standard_report_path(root, task, config), aggregated)
    _log(logger, "info", "[API] 多来源已合并，完整性校验通过")
    return aggregated, total_attempts, actions, None


def fetch_baidu_multi_source_api(
    *,
    config: dict[str, Any],
    root: Path,
    logger,
    api_fetcher: Callable[..., dict[str, Any]],
    task: str,
    period: str | None,
    target_date: str | None,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> tuple[dict[str, Any] | None, int, list[str], str | None]:
    return _collect_baidu_multi_source_api(
        config=config,
        root=root,
        logger=logger,
        api_fetcher=api_fetcher,
        task=task,
        period=period,
        target_date=target_date,
        clock=clock,
        sleep=sleep,
        commit_standard_report=True,
    )


def _fetch_baidu_api_only(
    *,
    config: dict[str, Any],
    root: Path,
    logger,
    api_fetcher: Callable[..., dict[str, Any]],
    task: str,
    period: str | None,
    target_date: str | None,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    if len(resolve_baidu_sources(config)) > 1:
        report, attempts, actions, failure = _collect_baidu_multi_source_api(
            config=config,
            root=root,
            logger=logger,
            api_fetcher=api_fetcher,
            task=task,
            period=period,
            target_date=target_date,
            clock=clock,
            sleep=sleep,
            commit_standard_report=True,
            commit_attempt_report=False,
        )
    else:
        api_kwargs: dict[str, Any] = {
            "config": config,
            "root": root,
            "logger": logger,
            "commit_attempt_report": False,
        }
        if task == "daily":
            api_kwargs["target_date"] = target_date
        else:
            api_kwargs["period"] = period
        report, attempts, actions, failure = _api_attempts(
            api_fetcher=api_fetcher,
            api_kwargs=api_kwargs,
            commit_standard_report=True,
            clock=clock,
            sleep=sleep,
            logger=logger,
        )

    if report is None:
        return {
            "project_id": config.get("project_id"),
            "project_name": config.get("project_name"),
            "date": target_date,
            "period": None if task == "daily" else period,
            "accounts": {},
            "errors": [f"百度 API 读取失败：{failure or 'api_error'}"],
            "data_source": "failed",
            "api_attempts": attempts,
            "self_heal_actions": list(actions),
            "fallback_reason": failure or "api_error",
        }

    routed = _with_route_metadata(
        report,
        data_source="api",
        api_attempts=attempts,
        actions=actions,
        fallback_reason=None,
    )
    _commit_routed_report(root, task, config, routed)
    _log_actual_source(logger, "api")
    return routed


def fetch_baidu_api_only_hourly(
    config: dict[str, Any],
    root: Path,
    logger,
    period: str | None = None,
    *,
    api_fetcher: Callable[..., dict[str, Any]] = fetch_baidu_api_hourly,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    return _fetch_baidu_api_only(
        config=config,
        root=root,
        logger=logger,
        api_fetcher=api_fetcher,
        task="hourly",
        period=period,
        target_date=None,
        clock=clock,
        sleep=sleep,
    )


def fetch_baidu_api_only_daily(
    config: dict[str, Any],
    root: Path,
    logger,
    target_date: str | None = None,
    *,
    api_fetcher: Callable[..., dict[str, Any]] = fetch_baidu_api_daily,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    return _fetch_baidu_api_only(
        config=config,
        root=root,
        logger=logger,
        api_fetcher=api_fetcher,
        task="daily",
        period=None,
        target_date=target_date,
        clock=clock,
        sleep=sleep,
    )


def _compare_reports(api_report: dict[str, Any] | None, browser_report: dict[str, Any]) -> dict[str, Any]:
    differences: list[dict[str, Any]] = []
    if api_report is None:
        differences.append({"type": "api_unavailable"})
    else:
        api_accounts = api_report.get("accounts") or {}
        browser_accounts = browser_report.get("accounts") or {}
        for account in sorted(set(api_accounts) | set(browser_accounts)):
            api_row = api_accounts.get(account)
            browser_row = browser_accounts.get(account)
            if not isinstance(api_row, dict) or not isinstance(browser_row, dict):
                differences.append({"account": account, "field": "account", "api": bool(api_row), "browser": bool(browser_row)})
                continue
            for field in ("source_user_id", "展现", "点击", "消费"):
                api_value = api_row.get(field)
                browser_value = browser_row.get(field)
                if field == "source_user_id" and browser_value is None:
                    continue
                if field == "source_user_id":
                    matches = str(api_value).strip() == str(browser_value).strip()
                elif field == "消费" and isinstance(api_value, (int, float)) and isinstance(browser_value, (int, float)):
                    matches = abs(float(api_value) - float(browser_value)) <= 0.01
                else:
                    matches = api_value == browser_value
                if not matches:
                    differences.append(
                        {"account": account, "field": field, "api": api_value, "browser": browser_value}
                    )
    return {
        "passed": not differences and _successful(browser_report),
        "date": browser_report.get("date"),
        "period": browser_report.get("period"),
        "differences": differences,
    }


def _fetch_resilient(
    *,
    config: dict[str, Any],
    root: Path,
    logger,
    api_fetcher: Callable[..., dict[str, Any]],
    browser_fetcher: Callable[..., dict[str, Any]],
    api_kwargs: dict[str, Any],
    browser_kwargs: dict[str, Any],
    task: str,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    mode = _mode(config)
    project_name = config.get("project_name") or config.get("project_id") or "当前项目"
    _log(logger, "info", "[数据源] 当前模式：%s", _mode_label(mode))
    if mode == "browser":
        _log(logger, "info", "[浏览器] 正在启动浏览器读取流程")
        browser_report = _browser_result(
            config=config,
            root=root,
            task=task,
            browser_fetcher=browser_fetcher,
            browser_kwargs=browser_kwargs,
        )
        source = "browser" if _successful(browser_report) else "failed"
        result = _with_route_metadata(
            browser_report,
            data_source=source,
            api_attempts=0,
            actions=[],
            fallback_reason=None,
        )
        if source == "browser":
            _commit_routed_report(root, task, config, result)
        _log_actual_source(logger, source)
        return result

    if len(resolve_baidu_sources(config)) > 1:
        api_report, attempts, actions, api_failure = _collect_baidu_multi_source_api(
            config=config,
            root=root,
            logger=logger,
            api_fetcher=api_fetcher,
            task=task,
            period=api_kwargs.get("period"),
            target_date=api_kwargs.get("target_date"),
            clock=clock,
            sleep=sleep,
            commit_standard_report=mode == "api_preferred",
        )
        if mode == "api_preferred" and api_report is not None:
            _log_actual_source(logger, "api")
            return api_report

        if api_failure:
            _log(logger, "warning", "[降级] API 读取仍未完成，准备切换浏览器：%s", api_failure)
        _log(logger, "info", "[浏览器] 正在启动浏览器降级流程")

        browser_report = _browser_result(
            config=config,
            root=root,
            task=task,
            browser_fetcher=browser_fetcher,
            browser_kwargs=browser_kwargs,
        )
        if mode == "api_shadow":
            comparison = _compare_reports(api_report, browser_report)
            comparison["api_attempts"] = attempts
            comparison["api_failure"] = api_failure
            _write_json_atomic(root / "reports" / "baidu_api_shadow_comparison.json", comparison)
            source = "browser_shadow" if _successful(browser_report) else "failed"
            result = _with_route_metadata(
                browser_report,
                data_source=source,
                api_attempts=attempts,
                actions=actions,
                fallback_reason=api_failure,
            )
            if source == "browser_shadow":
                _commit_routed_report(root, task, config, result)
            _log_actual_source(logger, source)
            return result
        if _successful(browser_report):
            result = _with_route_metadata(
                browser_report,
                data_source="browser_fallback",
                api_attempts=attempts,
                actions=actions,
                fallback_reason=api_failure,
            )
            _commit_routed_report(root, task, config, result)
            _log_actual_source(logger, "browser_fallback")
            return result

        failed = dict(browser_report)
        errors = list(failed.get("errors") or [])
        errors.insert(0, "百度 API 多来源通道失败，浏览器整项目降级也未成功")
        failed["errors"] = errors
        result = _with_route_metadata(
            failed,
            data_source="failed",
            api_attempts=attempts,
            actions=actions,
            fallback_reason=api_failure,
        )
        _log_actual_source(logger, "failed")
        return result

    _log(logger, "info", "[API] 正在读取%s百度数据", project_name)
    api_report, attempts, actions, api_failure = _api_attempts(
        api_fetcher=api_fetcher,
        api_kwargs=api_kwargs,
        commit_standard_report=mode == "api_preferred",
        clock=clock,
        sleep=sleep,
        logger=logger,
    )
    if mode == "api_preferred" and api_report is not None:
        result = _with_route_metadata(
            api_report,
            data_source="api",
            api_attempts=attempts,
            actions=actions,
            fallback_reason=None,
        )
        _log_actual_source(logger, "api")
        return result

    if api_failure:
        _log(logger, "warning", "[降级] API 读取仍未完成，准备切换浏览器：%s", api_failure)
    _log(logger, "info", "[浏览器] 正在启动浏览器降级流程")

    browser_report = _browser_result(
        config=config,
        root=root,
        task=task,
        browser_fetcher=browser_fetcher,
        browser_kwargs=browser_kwargs,
    )
    if mode == "api_shadow":
        comparison = _compare_reports(api_report, browser_report)
        comparison["api_attempts"] = attempts
        comparison["api_failure"] = api_failure
        _write_json_atomic(root / "reports" / "baidu_api_shadow_comparison.json", comparison)
        source = "browser_shadow" if _successful(browser_report) else "failed"
        result = _with_route_metadata(
            browser_report,
            data_source=source,
            api_attempts=attempts,
            actions=actions,
            fallback_reason=api_failure,
        )
        if source == "browser_shadow":
            _commit_routed_report(root, task, config, result)
        _log_actual_source(logger, source)
        return result

    if _successful(browser_report):
        result = _with_route_metadata(
            browser_report,
            data_source="browser_fallback",
            api_attempts=attempts,
            actions=actions,
            fallback_reason=api_failure,
        )
        _commit_routed_report(root, task, config, result)
        _log_actual_source(logger, "browser_fallback")
        return result

    failed = dict(browser_report)
    errors = list(failed.get("errors") or [])
    errors.insert(0, "百度 API 通道失败，浏览器降级也未成功")
    failed["errors"] = errors
    result = _with_route_metadata(
        failed,
        data_source="failed",
        api_attempts=attempts,
        actions=actions,
        fallback_reason=api_failure,
    )
    _log_actual_source(logger, "failed")
    return result


def fetch_baidu_resilient_hourly(
    config: dict[str, Any],
    root: Path,
    logger,
    period: str | None = None,
    *,
    api_fetcher: Callable[..., dict[str, Any]] = fetch_baidu_api_hourly,
    browser_fetcher: Callable[..., dict[str, Any]] = fetch_baidu_auto,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    common = {"config": config, "root": root, "logger": logger, "period": period}
    return _fetch_resilient(
        config=config,
        root=root,
        logger=logger,
        api_fetcher=api_fetcher,
        browser_fetcher=browser_fetcher,
        api_kwargs=common,
        browser_kwargs=common,
        task="hourly",
        clock=clock,
        sleep=sleep,
    )


def fetch_baidu_resilient_daily(
    config: dict[str, Any],
    root: Path,
    logger,
    target_date: str | None = None,
    *,
    api_fetcher: Callable[..., dict[str, Any]] = fetch_baidu_api_daily,
    browser_fetcher: Callable[..., dict[str, Any]] = fetch_baidu_daily,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    common = {"config": config, "root": root, "logger": logger, "target_date": target_date}
    return _fetch_resilient(
        config=config,
        root=root,
        logger=logger,
        api_fetcher=api_fetcher,
        browser_fetcher=browser_fetcher,
        api_kwargs=common,
        browser_kwargs=common,
        task="daily",
        clock=clock,
        sleep=sleep,
    )
