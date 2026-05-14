"""百度登录状态守卫。

执行日报 / 小时报百度抓数前，确认当前项目 credential_profile
与最近成功登录的 profile 是否一致。不一致时先退出验证再重新登录。

退出动作和退出结果验证分离：只有验证退出成功才能继续登录。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

STATE_FILE = "reports/browser_login_state.json"


# ── 状态文件读写 ──────────────────────────────────────────

def _state_path(root: str | Path) -> Path:
    return Path(root) / STATE_FILE


def load_browser_login_state(root: str | Path) -> dict[str, Any]:
    """读取状态文件；不存在时返回空状态。"""
    path = _state_path(root)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
    return {"last_profile": None}


def save_browser_login_state(root: str | Path, state: dict[str, Any]) -> None:
    """保存状态文件。自动剔除 username/password。"""
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {
        k: v for k, v in state.items()
        if k not in ("username", "password")
    }
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")


def get_browser_login_profile(root: str | Path) -> str | None:
    """读取最近成功登录的 profile。"""
    state = load_browser_login_state(root)
    return state.get("last_profile")


def mark_browser_login_success(
    root: str | Path,
    credential_profile: str,
    project_id: str | None = None,
    project_name: str | None = None,
    task: str | None = None,
    url: str | None = None,
) -> None:
    """确认登录成功后写入状态。"""
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
    """退出登录后清空状态。"""
    save_browser_login_state(root, {"last_profile": None})


# ── 项目 credential_profile ────────────────────────────────

def get_current_project_credential_profile(config: dict[str, Any]) -> str:
    """从运行配置中读取 baidu.credential_profile。"""
    baidu = config.get("baidu", {}) if isinstance(config.get("baidu"), dict) else {}
    return str(baidu.get("credential_project") or baidu.get("credential_profile", ""))


# ── 百度登录状态检测 ──────────────────────────────────────

def is_baidu_logged_in(page) -> bool:
    """判断当前页面是否显示已登录状态。

    返回 True 表示页面看起来已登录（不能可靠断定具体账号）。
    """
    if page is None:
        return False
    try:
        from modules.baidu_detector import classify_baidu_page
        text = _safe_text(page)
        classification = classify_baidu_page(page.url, text)
        return classification.get("login_status") != "not_logged_in"
    except Exception:
        return True  # 不确定时保守假设已登录


def is_baidu_logged_out_or_login_page(page) -> bool:
    """判断当前页面是否已进入登录页或未登录状态。"""
    if page is None:
        return True  # 没有页面视为安全
    try:
        from modules.baidu_detector import classify_baidu_page
        text = _safe_text(page)
        classification = classify_baidu_page(page.url, text)
        if classification.get("login_status") == "not_logged_in":
            return True
        # 辅助判断：页面文本或 URL 包含登录特征
        if "login" in (page.url or "").lower():
            return True
        if "登录" in (text or ""):
            # 检查是否存在账号/密码输入框
            try:
                pw = page.locator("input[type='password']").first
                if pw.count() > 0:
                    return True
            except Exception:
                pass
            try:
                account = page.locator("#uc-common-account, input[name='username'], input[name='loginName']").first
                if account.count() > 0:
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False


def wait_until_logged_out(page, timeout_ms: int = 5000) -> bool:
    """等待页面变为未登录状态。返回 True/False，不抛 traceback。"""
    if page is None:
        return True
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        if is_baidu_logged_out_or_login_page(page):
            return True
        page.wait_for_timeout(500)
    return False


# ── 百度退出登录 ──────────────────────────────────────────

LOGOUT_SELECTORS = [
    "a:has-text('退出')",
    "a:has-text('退出登录')",
    "a:has-text('安全退出')",
    "a:has-text('注销')",
    "a:has-text('登出')",
    "span:has-text('退出')",
    "span:has-text('退出登录')",
    "div:has-text('退出')",
    "div:has-text('退出登录')",
    "button:has-text('退出')",
    "button:has-text('退出登录')",
    "[title='退出']",
    "[title='退出登录']",
    ".logout",
    ".logout-btn",
    "#logout",
]

LOGOUT_TEXT_CANDIDATES = ["退出", "退出登录", "安全退出", "注销", "登出"]


def _try_click_logout(page) -> bool:
    """尝试点击退出入口，返回是否点到了东西。"""
    for selector in LOGOUT_SELECTORS:
        try:
            el = page.locator(selector).first
            if el.count() > 0 and el.is_visible():
                el.click(timeout=3000)
                return True
        except Exception:
            continue
    for label in LOGOUT_TEXT_CANDIDATES:
        try:
            el = page.get_by_text(label, exact=False).first
            if el.count() > 0 and el.is_visible():
                el.click(timeout=3000)
                return True
        except Exception:
            continue
    return False


def logout_baidu_account(page) -> dict[str, Any]:
    """尝试退出百度账号并验证退出结果。

    1. 点击退出入口
    2. 等待页面变为未登录状态
    3. 验证成功才返回 success=True

    成功 {"success": True, "message": "..."}
    失败 {"success": False, "message": "..."}
    """
    if page is None:
        return {"success": False, "message": "page 对象为空"}

    clicked = _try_click_logout(page)
    if not clicked:
        return {"success": False, "message": "未找到退出登录入口，请手动退出当前百度账号"}

    # 等待退出生效
    verified = wait_until_logged_out(page, timeout_ms=5000)
    if verified:
        return {"success": True, "message": "已退出百度账号"}
    return {"success": False, "message": "点击退出后仍未确认退出成功，请手动退出当前百度账号"}


# ── Profile 一致性守卫 ────────────────────────────────────

def ensure_baidu_profile_session(
    root: Path,
    config: dict[str, Any],
    page,
    logger,
    task: str | None = None,
    input_func: Any = None,
    output_func: Any = None,
) -> bool:
    """执行百度抓数前调用，确保当前浏览器登录的是本项目的百度账号。

    返回 True 表示可以继续抓数，False 表示需要中断。
    """
    if input_func is None:
        import builtins
        input_func = builtins.input
    if output_func is None:
        import builtins
        output_func = builtins.print

    profile = get_current_project_credential_profile(config)
    if not profile:
        # 没有配置 profile，不做检查
        return True

    last_profile = get_browser_login_profile(root)
    if last_profile == profile:
        # profile 一致，无需切换
        return True

    # 需要切换：last_profile 为 None（未知状态）或不一致
    project_id = config.get("project_id", "")
    project_name = config.get("project_name", "")
    if last_profile is None:
        output_func("  [注意] 当前浏览器百度登录状态未知，正在确认当前项目账号")
        logger.info("登录状态未知，强制用当前 profile=%s 重新登录确认", profile)
    else:
        output_func("  [注意] 当前浏览器可能仍登录其他项目账号，正在切换到当前项目账号")
        logger.info("profile 不一致：上次=%s 当前=%s，尝试退出重登", last_profile, profile)

    # 退出并验证
    logout_result = logout_baidu_account(page)
    if logout_result.get("success"):
        verified_logged_out = True
    else:
        # 自动退出失败，提示手动退出
        output_func(f"    {logout_result.get('message', '')}")
        output_func("  请在 Chrome 中手动退出当前百度账号后按回车继续，或输入 0 返回。")
        answer = input_func("  > ").strip()
        if answer == "0":
            logger.info("用户取消百度账号切换")
            return False
        # 用户按回车 → 验证是否已手动退出
        output_func("  正在确认是否已退出...")
        verified_logged_out = wait_until_logged_out(page, timeout_ms=10000)
        if not verified_logged_out:
            output_func("  [注意] 无法确认是否已退出百度账号，请确认退出后重新运行。")
            return False

    # 确认已退出或已进入登录页，才调用登录
    if not verified_logged_out:
        output_func("  [注意] 无法确认是否已退出百度账号，请确认退出后重新运行。")
        return False

    # 用当前项目 profile 重新登录
    try:
        from modules.baidu_overview import _auto_login_if_needed
        logged_in = _auto_login_if_needed(page, root, config, logger)
        if not logged_in:
            logger.error("百度重新登录失败：profile=%s", profile)
            return False
    except Exception as exc:
        logger.error("百度重新登录异常：%s", exc)
        return False

    # 只有登录真正成功后才写入状态
    mark_browser_login_success(
        root,
        credential_profile=profile,
        project_id=project_id,
        project_name=project_name,
        task=task,
        url=_safe_url(page),
    )
    output_func("  [通过] 已切换到当前项目百度账号")
    return True


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
