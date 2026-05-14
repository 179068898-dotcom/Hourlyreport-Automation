"""百度登录状态守卫。

执行日报 / 小时报百度抓数前：
1. 统一进入 www2.baidu.com 稳定入口
2. 识别当前登录用户名，与项目期望账号比较
3. 不一致则退出重登，一致则直接通过
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

STATE_FILE = "reports/browser_login_state.json"
ENTRY_URL = "https://www2.baidu.com/"


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
    """从当前项目 credential_profile 读取对应的 username，仅用于比较。"""
    try:
        from modules.credential_manager import load_project_credentials
        creds = load_project_credentials(root, config, "baidu", get_current_project_credential_profile(config))
        if creds and creds.get("username", "").strip():
            return creds["username"].strip()
    except Exception:
        pass
    return None


# ── 百度入口页 ────────────────────────────────────────────

def ensure_baidu_entry_page(page, url: str = ENTRY_URL) -> dict[str, Any]:
    """导航到百度稳定入口页，避免依赖浏览器历史页。"""
    if page is None:
        return {"success": False, "message": "page 对象为空"}
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        return {"success": True, "url": page.url}
    except Exception as exc:
        return {"success": False, "message": f"导航到 {url} 失败：{exc}"}


# ── 当前登录用户名检测 ────────────────────────────────────

def detect_current_baidu_username(page) -> str | None:
    """尝试从当前页面识别已登录用户名。不输出到日志。"""
    if page is None:
        return None
    try:
        text = page.locator("body").inner_text(timeout=2000) or ""

        # 常见百度登录后用户名区域
        patterns = [
            r"欢迎[，,\s]*(\S+)",          # "欢迎，xxx"
            r"你好[，,\s]*(\S+)",          # "你好xxx"
            r"Hi[,，\s]*(\S+)",            # "Hi, xxx"
            r"您好[，,\s]*(\S+)",          # "您好，xxx"
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1).rstrip("，,。.")

        # 尝试从用户菜单区域获取
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
    """如果能识别当前登录用户名，且与项目账号一致，返回 True。"""
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
        classification = classify_baidu_page(page.url, text)
        return classification.get("login_status") != "not_logged_in"
    except Exception:
        return True


def is_baidu_logged_out_or_login_page(page) -> bool:
    if page is None:
        return True
    try:
        from modules.baidu_detector import classify_baidu_page
        text = _safe_text(page)
        classification = classify_baidu_page(page.url, text)
        if classification.get("login_status") == "not_logged_in":
            return True
        if "login" in (page.url or "").lower():
            return True
        if "登录" in (text or ""):
            try:
                pw = page.locator("input[type='password']").first
                if pw.count() > 0:
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False


def wait_until_logged_out(page, timeout_ms: int = 5000) -> bool:
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
    "a:has-text('退出')", "a:has-text('退出登录')", "a:has-text('安全退出')",
    "a:has-text('注销')", "a:has-text('登出')",
    "span:has-text('退出')", "span:has-text('退出登录')",
    "div:has-text('退出')", "div:has-text('退出登录')",
    "button:has-text('退出')", "button:has-text('退出登录')",
    "[title='退出']", "[title='退出登录']",
    ".logout", ".logout-btn", "#logout",
]
LOGOUT_TEXT_CANDIDATES = ["退出", "退出登录", "安全退出", "注销", "登出"]


def _try_click_logout(page) -> bool:
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
    if page is None:
        return {"success": False, "message": "page 对象为空"}
    clicked = _try_click_logout(page)
    if not clicked:
        return {"success": False, "message": "未找到退出登录入口，请手动退出当前百度账号"}
    verified = wait_until_logged_out(page, timeout_ms=5000)
    if verified:
        return {"success": True, "message": "已退出百度账号"}
    return {"success": False, "message": "点击退出后仍未确认退出成功，请手动退出当前百度账号"}


# ── 内部辅助函数 ──────────────────────────────────────────

def _do_logout_flow(page, output_func, input_func, logger) -> bool:
    """执行退出+验证流程，返回是否已确认退出。"""
    logout_result = logout_baidu_account(page)
    if logout_result.get("success"):
        return True
    output_func(f"    {logout_result.get('message', '')}")
    output_func("  请在 Chrome 中手动退出当前百度账号后按回车继续，或输入 0 返回。")
    answer = input_func("  > ").strip()
    if answer == "0":
        logger.info("用户取消百度账号切换")
        return False
    output_func("  正在确认是否已退出...")
    if wait_until_logged_out(page, timeout_ms=10000):
        return True
    output_func("  [注意] 无法确认是否已退出百度账号，请确认退出后重新运行。")
    return False


def _do_login_flow(root, config, page, logger, project_id, project_name, task, output_func) -> bool:
    """调用 _auto_login_if_needed，成功后写状态。"""
    try:
        from modules.baidu_overview import _auto_login_if_needed
        if not _auto_login_if_needed(page, root, config, logger):
            logger.error("百度重新登录失败")
            return False
    except Exception as exc:
        logger.error("百度重新登录异常")
        return False
    mark_browser_login_success(root, get_current_project_credential_profile(config),
                               project_id=project_id, project_name=project_name,
                               task=task, url=_safe_url(page))
    output_func("  [通过] 已切换到当前项目百度账号")
    return True


# ── noauth 检测 ───────────────────────────────────────────

def is_baidu_noauth_page(page) -> bool:
    """判断当前页面是否是百度无权限页。"""
    if page is None:
        return False
    try:
        url = page.url or ""
        if "noauth" in url.lower():
            return True
        text = _safe_text(page)
        if any(kw in text for kw in ["无权限", "暂无权限", "没有权限", "noauth"]):
            return True
    except Exception:
        pass
    return False


# ── 强制退出重登（noauth 用） ─────────────────────────────

def force_relogin_current_project(
    root: Path, config: dict[str, Any], page, logger,
    task: str | None = None,
    input_func: Any = None, output_func: Any = None,
) -> bool:
    """不考虑 browser_login_state，直接退出当前账号并登录当前项目。

    用于 noauth / 明确账号不匹配场景。
    """
    import builtins
    if input_func is None:
        input_func = builtins.input
    if output_func is None:
        output_func = builtins.print

    profile = get_current_project_credential_profile(config)
    if not profile:
        return False

    project_id = config.get("project_id", "")
    project_name = config.get("project_name", "")

    output_func("  [注意] 当前百度账号无当前项目权限，正在重新登录当前项目账号")
    logger.info("noauth 场景触发强制重登")

    if not _do_logout_flow(page, output_func, input_func, logger):
        return False

    if _do_login_flow(root, config, page, logger, project_id, project_name, task, output_func):
        output_func("  [通过] 百度账号已切换，重新进入报告页")
        return True

    output_func("  [失败] 当前百度账号可能无项目报告权限，请检查项目配置或百度账号权限")
    return False


# ── Profile 一致性守卫（主入口） ──────────────────────────

def ensure_baidu_profile_session(
    root: Path, config: dict[str, Any], page, logger,
    task: str | None = None,
    input_func: Any = None, output_func: Any = None,
) -> bool:
    """执行百度抓数前调用，确保当前浏览器登录的是本项目的百度账号。

    判断顺序（按优先级）：
    1. 入口页导航 → 失败则直接返回
    2. 页面用户名匹配 → 直接通过
    3. 页面用户名明确不匹配 → 强制退出重登（无论 last_profile 如何）
    4. 无法识别用户名 → 参考 last_profile 决定
    """
    import builtins
    if input_func is None:
        input_func = builtins.input
    if output_func is None:
        output_func = builtins.print

    profile = get_current_project_credential_profile(config)
    if not profile:
        return True

    # 1. 先进入百度稳定入口
    entry_result = ensure_baidu_entry_page(page)
    if not entry_result.get("success"):
        output_func(f"  [注意] 百度入口页打开失败：{entry_result.get('message', '')}")
        return False

    # 2. 检测页面状态
    logged_in = is_baidu_logged_in(page)
    expected_user = get_expected_baidu_username(root, config)
    detected_user = detect_current_baidu_username(page)
    last_profile = get_browser_login_profile(root)

    project_id = config.get("project_id", "")
    project_name = config.get("project_name", "")

    # ── 页面实际账号检测优先于 browser_login_state ──────────

    if logged_in and detected_user and expected_user:
        if detected_user.strip() == expected_user:
            # 分支 A：已登录正确账号 → 直接通过
            logger.info("当前百度账号已确认匹配项目账号")
            mark_browser_login_success(root, profile, project_id=project_id, project_name=project_name,
                                       task=task, url=_safe_url(page))
            return True
        else:
            # 分支 B：已登录其他账号 → 强制退出重登，不管 last_profile
            output_func("  [注意] 当前浏览器登录的是其他百度账号，正在切换")
            logger.info("当前百度账号与项目账号不匹配，准备切换账号")
            if not _do_logout_flow(page, output_func, input_func, logger):
                return False
            return _do_login_flow(root, config, page, logger, project_id, project_name, task, output_func)

    # ── 无法识别用户名时，参考 last_profile ──────────────────

    # 分支 C：last_profile 一致且页面已登录 → 信任历史记录
    if last_profile == profile:
        if not logged_in:
            logger.info("页面未登录，调用自动登录")
            return _do_login_flow(root, config, page, logger, project_id, project_name, task, output_func)
        # 已登录但无法识别用户名，信任 last_profile
        return True

    # 分支 D/E：无法识别用户名且 last_profile 不一致或未知 → 退出重登
    if last_profile is None:
        output_func("  [注意] 当前浏览器百度登录状态未知，正在确认当前项目账号")
        logger.info("登录状态未知，准备切换账号")
    else:
        output_func("  [注意] 当前浏览器可能仍登录其他项目账号，正在切换到当前项目账号")
        logger.info("未能识别当前百度账号，改用登录状态记录判断，准备切换")

    if not _do_logout_flow(page, output_func, input_func, logger):
        return False
    return _do_login_flow(root, config, page, logger, project_id, project_name, task, output_func)


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
