"""百度登录状态守卫。

CAS 登录页兜底方案：
https://cas.baidu.com/?tpl=www2&fromu=http%3A%2F%2Fwww2.baidu.com%2Fcommon%2Fappinit.ajax
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

STATE_FILE = "reports/browser_login_state.json"
BAIDU_CAS_LOGIN_URL = (
    "https://cas.baidu.com/"
    "?tpl=www2"
    "&fromu=http%3A%2F%2Fwww2.baidu.com%2Fcommon%2Fappinit.ajax"
)


# ── 状态文件读写 ──────────────────────────────────────────

def _state_path(root: str | Path) -> Path:
    return Path(root) / STATE_FILE


def load_browser_login_state(root: str | Path) -> dict[str, Any]:
    path = _state_path(root)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
    return {"last_profile": None}


def save_browser_login_state(root: str | Path, state: dict[str, Any]) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in state.items() if k not in ("username", "password")}
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")


def get_browser_login_profile(root: str | Path) -> str | None:
    return load_browser_login_state(root).get("last_profile")


def mark_browser_login_success(
    root: str | Path, credential_profile: str,
    project_id: str | None = None, project_name: str | None = None,
    task: str | None = None, url: str | None = None,
) -> None:
    state = {
        "last_profile": credential_profile,
        "last_project_id": project_id,
        "last_project_name": project_name,
        "last_task": task,
        "last_seen_url": url,
        "last_login_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_browser_login_state(root, state)


def clear_browser_login_state(root: str | Path) -> None:
    save_browser_login_state(root, {"last_profile": None})


# ── 项目 credential_profile ────────────────────────────────

def get_current_project_credential_profile(config: dict[str, Any]) -> str:
    baidu = config.get("baidu", {}) if isinstance(config.get("baidu"), dict) else {}
    return str(baidu.get("credential_project") or baidu.get("credential_profile", ""))


def get_expected_baidu_username(root: str | Path, config: dict[str, Any]) -> str | None:
    try:
        from modules.credential_manager import load_project_credentials
        creds = load_project_credentials(root, config, "baidu", get_current_project_credential_profile(config))
        if creds and creds.get("username", "").strip():
            return creds["username"].strip()
    except Exception:
        pass
    return None


# ── CAS 登录页入口 ─────────────────────────────────────────

def goto_baidu_login_page(page) -> dict[str, Any]:
    """进入 CAS 百度登录页。成功返回 {success: True}。"""
    if page is None:
        return {"success": False, "message": "page 对象为空"}
    try:
        page.goto(BAIDU_CAS_LOGIN_URL, wait_until="domcontentloaded", timeout=15000)
        return {"success": True}
    except Exception:
        return {"success": False, "message": "百度登录页打开失败"}


# ── 当前登录用户名检测 ────────────────────────────────────

def detect_current_baidu_username(page) -> str | None:
    if page is None:
        return None
    try:
        text = page.locator("body").inner_text(timeout=2000) or ""
        patterns = [
            r"欢迎[，,\s]*(\S+)",
            r"你好[，,\s]*(\S+)",
            r"Hi[,，\s]*(\S+)",
            r"您好[，,\s]*(\S+)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1).rstrip("，,。.")
        for sel in [".user-name", ".username", "#username", "[class*='user']", ".account-name"]:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    name = el.inner_text(timeout=1000).strip()
                    if name and len(name) < 50:
                        return name
            except Exception:
                continue
        return None
    except Exception:
        return None


def is_current_baidu_user_expected(page, root: str | Path, config: dict[str, Any]) -> bool:
    expected = get_expected_baidu_username(root, config)
    if not expected:
        return False
    detected = detect_current_baidu_username(page)
    if not detected:
        return False
    return detected.strip() == expected


# ── 百度登录状态检测 ──────────────────────────────────────

def is_baidu_logged_in(page) -> bool:
    if page is None:
        return False
    try:
        from modules.baidu_detector import classify_baidu_page
        text = _safe_text(page)
        return classify_baidu_page(page.url, text).get("login_status") != "not_logged_in"
    except Exception:
        return True


def is_baidu_logged_out_or_login_page(page) -> bool:
    if page is None:
        return True
    try:
        from modules.baidu_detector import classify_baidu_page
        text = _safe_text(page)
        cls = classify_baidu_page(page.url, text)
        if cls.get("login_status") == "not_logged_in":
            return True
        if "login" in (page.url or "").lower():
            return True
        if "登录" in (text or ""):
            try:
                if page.locator("input[type='password']").first.count() > 0:
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False


def is_baidu_noauth_page(page) -> bool:
    if page is None:
        return False
    try:
        if "noauth" in (page.url or "").lower():
            return True
        if any(kw in (_safe_text(page)) for kw in ["无权限", "暂无权限", "没有权限", "noauth"]):
            return True
    except Exception:
        pass
    return False


# ── 页面可用性判断 ────────────────────────────────────────

def _page_is_usable_search_promotion(page, root, config) -> bool:
    if page is None or root is None:
        return False
    try:
        from modules.baidu_detector import classify_baidu_page
        text = _safe_text(page)
        cls = classify_baidu_page(page.url, text)
        if cls.get("login_status") == "not_logged_in":
            return False
        if not cls.get("signals", {}).get("has_search_promotion"):
            return False
        if "cc.baidu.com/report" not in (page.url or ""):
            return False
        if is_baidu_noauth_page(page):
            return False
        expected_user = get_expected_baidu_username(root, config)
        detected_user = detect_current_baidu_username(page)
        if detected_user and expected_user:
            if detected_user.strip() != expected_user:
                return False
            return True
        last_profile = get_browser_login_profile(root)
        if last_profile == get_current_project_credential_profile(config):
            return True
        return False
    except Exception:
        return False


# ── CAS 登录当前项目 ──────────────────────────────────────

def _do_login_flow(root, config, page, logger, project_id, project_name, task, output_func) -> bool:
    try:
        from modules.baidu_overview import _auto_login_if_needed
        if not _auto_login_if_needed(page, root, config, logger):
            logger.error("百度重新登录失败")
            return False
    except Exception:
        logger.error("百度重新登录异常")
        return False

    # CAS 登录后复核：确认当前登录账号匹配当前项目账号
    expected_user = get_expected_baidu_username(root, config)
    detected_user = detect_current_baidu_username(page)
    if detected_user and expected_user:
        if detected_user.strip() != expected_user:
            logger.error("当前百度账号与项目账号不匹配")
            output_func("  [注意] 当前百度账号与项目账号不匹配，请退出后重新登录当前项目账号")
            return False
    elif not detected_user:
        logger.error("无法确认当前百度账号是否匹配")
        output_func("  [注意] 无法确认当前百度账号是否匹配项目账号，请重新登录当前项目账号")
        return False

    mark_browser_login_success(root, get_current_project_credential_profile(config),
                               project_id=project_id, project_name=project_name,
                               task=task, url=_safe_url(page))
    output_func("  [通过] 百度账号登录完成")
    return True


def force_relogin_current_project(
    root: Path, config: dict[str, Any], page, logger,
    task: str | None = None,
    input_func: Any = None, output_func: Any = None,
) -> bool:
    """CAS 登录页兜底：进 CAS 页，登录当前项目账号。"""
    import builtins
    if input_func is None:
        input_func = builtins.input
    if output_func is None:
        output_func = builtins.print

    if not get_current_project_credential_profile(config):
        return False

    project_id = config.get("project_id", "")
    project_name = config.get("project_name", "")
    output_func("  [注意] 正在登录当前项目百度账号")
    logger.info("进入 CAS 登录页兜底")

    entry = goto_baidu_login_page(page)
    if not entry.get("success"):
        output_func("  [失败] 百度登录页打开失败")
        return False

    return _do_login_flow(root, config, page, logger, project_id, project_name, task, output_func)


# ── Profile 一致性守卫（主入口） ──────────────────────────

def ensure_baidu_profile_session(
    root: Path, config: dict[str, Any], page, logger,
    task: str | None = None,
    input_func: Any = None, output_func: Any = None,
) -> bool:
    """执行百度抓数前调用。只在真正执行任务时才检查百度账号。"""
    import builtins
    if input_func is None:
        input_func = builtins.input
    if output_func is None:
        output_func = builtins.print

    profile = get_current_project_credential_profile(config)
    if not profile:
        return True

    # 已在可用搜索推广数据页且账号匹配 → 直接通过
    if _page_is_usable_search_promotion(page, root, config):
        logger.info("当前页面已是可用搜索推广数据页")
        return True

    # 需要登录 → CAS 兜底
    last_profile = get_browser_login_profile(root)
    if last_profile != profile:
        if last_profile is None:
            logger.info("登录状态未知，进入 CAS 登录")
        else:
            logger.info("profile 不一致，进入 CAS 登录")
        return force_relogin_current_project(root, config, page, logger, task=task,
                                             input_func=input_func, output_func=output_func)

    # last_profile 一致但页面不可用 → 尝试 CAS 登录刷新
    output_func("  [注意] 正在登录当前项目百度账号")
    return force_relogin_current_project(root, config, page, logger, task=task,
                                         input_func=input_func, output_func=output_func)


# ── 内部辅助 ──────────────────────────────────────────────

def _safe_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=2000) or ""
    except Exception:
        return ""


def _safe_url(page) -> str:
    try:
        return page.url or ""
    except Exception:
        return ""
