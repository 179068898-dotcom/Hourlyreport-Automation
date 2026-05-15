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


# ── 百度退出登录（跨 frame 探测 + 候选 dump） ──────────────

CANDIDATE_KEYWORDS = [
    "百度管家", "账号", "用户", "退出", "退出登录", "管家", "BDCC",
    "登录", "安全退出", "注销", "登出",
]

ACCOUNT_KEYWORDS = ["百度管家", "账号", "用户", "管家", "BDCC"]

LOGOUT_KEYWORDS = ["退出", "退出登录", "安全退出", "注销", "登出"]


def _find_clickable_in_frame(frame, page) -> list[dict[str, Any]]:
    """在指定 frame 中收集所有可点击元素信息。"""
    items = []
    try:
        loc = frame.locator("a, button, span, div, li, [role='button'], [role='menuitem']")
        count = loc.count()
        for i in range(min(count, 200)):
            try:
                el = loc.nth(i)
                if not el.is_visible():
                    continue
                text = el.inner_text(timeout=200).strip()[:100] if el.count() > 0 else ""
                if not text:
                    continue
                box = el.bounding_box()
                info = {
                    "text": text,
                    "tag": el.evaluate("el => el.tagName") if hasattr(el, 'evaluate') else "?",
                    "class": el.get_attribute("class") or "",
                    "id": el.get_attribute("id") or "",
                    "title": el.get_attribute("title") or "",
                    "aria_label": el.get_attribute("aria-label") or "",
                    "visible": True,
                    "box": {"x": box["x"], "y": box["y"]} if box else None,
                    "frame_url": (frame.url or "")[:120],
                }
                items.append(info)
            except Exception:
                continue
    except Exception:
        pass
    return items


def _dump_candidates_to(page, root: str | Path, filename: str) -> list[dict[str, Any]]:
    """收集候选并写入指定文件。同时保存截图。"""
    all_items = []
    try:
        for frame in page.frames:
            items = _find_clickable_in_frame(frame, page)
            all_items.extend(items)
    except Exception:
        pass

    reports_dir = Path(root) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / filename
    out.write_text(json.dumps({"frames_checked": len(page.frames), "candidates": all_items},
                              ensure_ascii=False, indent=2), encoding="utf-8")

    # 保存截图
    png_name = filename.replace(".json", ".png")
    try:
        page.screenshot(path=str(reports_dir / png_name), full_page=False)
    except Exception:
        pass

    return all_items


def dump_baidu_logout_candidates(page, root: str | Path = ".") -> list[dict[str, Any]]:
    """兼容旧接口。"""
    return _dump_candidates_to(page, root, "baidu_logout_candidates.json")


def _click_element_center(page, box: dict) -> bool:
    """点击元素中心点，先 hover 再 click。"""
    try:
        cx = box["x"] + box.get("width", 40) / 2
        cy = box["y"] + box.get("height", 24) / 2
        page.mouse.move(cx, cy)
        page.wait_for_timeout(300)
        page.mouse.click(cx, cy)
        return True
    except Exception:
        return False


def wait_until_cas_login_page(page, timeout_ms: int = 5000) -> bool:
    """等待页面进入 CAS 登录页（URL 必须含 cas.baidu.com）。"""
    if page is None:
        return True
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        if "cas.baidu.com" in (page.url or ""):
            return True
        page.wait_for_timeout(500)
    return False


def logout_baidu_account(page, root: str | Path = ".") -> dict[str, Any]:
    """真实人工路径：hover 右上角账号 → click → 等菜单 → 点退出 → 验证 CAS。

    生成 before/after candidates 和截图。
    """
    if page is None:
        return {"success": False, "message": "page 对象为空"}

    # ── Before dump ──
    _dump_candidates_to(page, root, "baidu_logout_candidates_before.json")

    # ── 1. 找右上角账号区域并 hover + click ──
    viewport = page.viewport_size or {"width": 1920, "height": 1080}
    vw = viewport["width"]

    def _is_top_right(box: dict) -> bool:
        return box.get("y", 999) < 140 and box.get("x", 0) > vw * 0.55

    clicked_account = False
    # 先尝试直接用 account trigger 选择器（优先右上角）
    account_sel = ".uc-cc-nav_trigger, .one-dropdown-trigger, [class*='nav-trigger'], [class*='profile']"
    for sel in [account_sel, "[class*='user']", "[class*='account']", "[class*='avatar']"]:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                box = el.bounding_box()
                if box and _is_top_right(box):
                    _click_element_center(page, box)
                    page.wait_for_timeout(2500)
                    clicked_account = True
                    break
        except Exception:
            continue

    # 候选兜底：遍历 candidates，右上角优先
    if not clicked_account:
        before = _dump_candidates_to(page, root, "baidu_logout_candidates_before.json")
        # 排序：越靠右越优先
        top_right_items = []
        top_items = []
        for item in before:
            text = item.get("text", "")
            cls = item.get("class", "")
            if any(kw in text + cls for kw in ACCOUNT_KEYWORDS):
                box = item.get("box")
                if box and _is_top_right(box):
                    top_right_items.append(item)
                elif box and box.get("y", 999) < 140:
                    top_items.append(item)
        # 右上角按 x 降序（最靠右优先）
        top_right_items.sort(key=lambda i: i["box"]["x"], reverse=True)
        for item in top_right_items + top_items:
            if _click_element_center(page, item["box"]):
                page.wait_for_timeout(2500)
                clicked_account = True
                break

    # ── After account click dump ──
    page.wait_for_timeout(1000)
    _dump_candidates_to(page, root, "baidu_logout_candidates_after_account_click.json")

    # ── 2. 在 after candidates 中找"退出"并点击 ──
    after = _dump_candidates_to(page, root, "baidu_logout_candidates_after_account_click.json")
    clicked_logout = False
    for item in after:
        text = item.get("text", "")
        if any(kw in text for kw in LOGOUT_KEYWORDS):
            box = item.get("box")
            if box:
                if _click_element_center(page, box):
                    page.wait_for_timeout(2000)
                    clicked_logout = True
                    break

    # 兜底：选择器搜索退出
    if not clicked_logout:
        for sel in LOGOUT_SELECTORS:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible():
                    el.click(timeout=3000)
                    page.wait_for_timeout(2000)
                    clicked_logout = True
                    break
            except Exception:
                continue

    # ── 3. 验证退出 ──
    if clicked_logout and wait_until_cas_login_page(page, timeout_ms=6000):
        return {"success": True, "message": "已通过页面点击退出百度账号"}

    # 最后兜底
    for sel in LOGOUT_SELECTORS:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                el.click(timeout=3000)
                if wait_until_cas_login_page(page, timeout_ms=6000):
                    return {"success": True, "message": "已退出百度账号"}
        except Exception:
            continue

    return {"success": False, "message": "未找到退出登录入口"}


# Keep selectors for fallback use
LOGOUT_SELECTORS = [
    "a:has-text('退出')", "a:has-text('退出登录')", "a:has-text('安全退出')",
    "span:has-text('退出')", "span:has-text('退出登录')",
    "div:has-text('退出')", "div:has-text('退出登录')",
    "button:has-text('退出')", "button:has-text('退出登录')",
    ".logout", ".logout-btn", "#logout",
]


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
    """优先点击退出 → CAS 登录当前项目。"""
    import builtins
    if input_func is None:
        input_func = builtins.input
    if output_func is None:
        output_func = builtins.print

    if not get_current_project_credential_profile(config):
        return False

    project_id = config.get("project_id", "")
    project_name = config.get("project_name", "")

    # 1. 尝试页面点击退出
    logout_result = logout_baidu_account(page)
    if logout_result.get("success"):
        output_func("  [通过] 已退出旧百度账号，正在登录当前项目账号")
    else:
        output_func("  [注意] 未能自动点击退出，正在使用登录页兜底")
    logger.info("账号切换：退出结果=%s", logout_result.get("success"))

    # 2. 进入 CAS 登录页
    entry = goto_baidu_login_page(page)
    if not entry.get("success"):
        output_func("  [失败] 百度登录页打开失败")
        return False

    # 3. 登录 + 复核
    if not _do_login_flow(root, config, page, logger, project_id, project_name, task, output_func):
        return False

    return True


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

    if _page_is_usable_search_promotion(page, root, config):
        return True

    # 需要切换 → 退出 + CAS 登录
    output_func("  [注意] 正在切换到当前项目百度账号")
    if not force_relogin_current_project(root, config, page, logger, task=task,
                                         input_func=input_func, output_func=output_func):
        return False

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
