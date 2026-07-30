# -*- coding: utf-8 -*-
"""ifram / element wait helpers"""
import time


def wait_for_human_iframe(page, timeout: int = 35) -> bool:
    """等待 #human 里的验证 iframe 变为可见。"""
    for _ in range(timeout):
        visible = page.run_js("""
        var p = document.getElementById('human');
        var f = p ? p.querySelector('iframe') : null;
        return f && f.style.display !== 'none';
        """, as_expr=False)
        if visible:
            return True
        print("等待 iframe 显示...")
        time.sleep(1)
    return False


def get_human_iframe_context(page):
    """拿到 #human iframe 的 FirefoxFrame 上下文。失败返回 None。"""
    captcha = page.ele("#human", timeout=5)
    if not captcha:
        print("❌ #human 不存在")
        return None
    iframe_count = page.run_js("""
        var p = document.getElementById('human');
        return p ? p.querySelectorAll('iframe').length : -1;
    """, as_expr=False)
    if not iframe_count:
        print("❌ #human 内无 iframe")
        return None
    frame = page.get_frame("css:#human iframe[data-testid='humanCaptchaIframe']")
    if not frame:
        print("❌ get_frame 返回 None")
    return frame


def wait_for_px_captcha_iframe(humanCaptchaIframe, timeout: int = 35) -> bool:
    """在 humanCaptchaIframe 内等 #px-captcha iframe 加载完成。"""
    for _ in range(timeout):
        ready = humanCaptchaIframe.run_js("""
        var px = document.getElementById('px-captcha');
        var f = px ? px.querySelector('iframe') : null;
        return f && f.contentWindow !== null;
        """, as_expr=False)
        if ready:
            return True
        print("等待 btnIframe_visible 显示...")
        time.sleep(1)
    return False


def get_visible_px_iframe(humanCaptchaIframe):
    """取 humanCaptchaIframe 下第一个可见的 PX child context，返回 (frame, idx)。

    iframe 不存在、不可见或 context 瞬态重建时返回 (None, -1)，不抛异常。"""
    try:
        visible_idx = humanCaptchaIframe.run_js("""
        var iframes = document.querySelectorAll('#px-captcha iframe');
        for (var i = 0; i < iframes.length; i++) {
            var display = window.getComputedStyle(iframes[i]).display;
            if (display !== 'none') return i;
        }
        return -1;
        """, as_expr=False)
    except Exception:
        return None, -1

    if visible_idx is None or visible_idx < 0:
        return None, visible_idx if visible_idx is not None else -1

    try:
        frame = humanCaptchaIframe.get_frame(index=visible_idx)
    except Exception:
        return None, visible_idx

    if not frame:
        print("❌ get_frame(index=" + str(visible_idx) + ") 返回 None")
        return None, visible_idx
    return frame, visible_idx


def poll_px_result(page, humanCaptchaIframe, rounds: int = 6) -> str:
    """轮询 PX 验证结果。PX 可能在按压后销毁/重建 iframe，此函数自行刷新引用。
       返回 "passed" / "loading" / "retry" / "timeout"。
       传入 page 和 #human 层的 humanCaptchaIframe（不直接传 btnIframe）。"""
    btnIframe = None
    consecutive_miss = 0
    for rnd in range(rounds):
        time.sleep(3)
        try:
            btnIframe, _ = get_visible_px_iframe(humanCaptchaIframe)
            if not btnIframe:
                consecutive_miss += 1
                print("r{}: cannot re-get visible PX iframe (miss {}/{})".format(
                    rnd + 1, consecutive_miss, rounds))
                if consecutive_miss >= 3:
                    # Waited ~12s without frame — check if #human itself is gone
                    try:
                        human_present = bool(page.ele("#human", timeout=2))
                    except Exception:
                        human_present = False
                    if not human_present:
                        return "passed"
                    time.sleep(5)
                continue
            consecutive_miss = 0
            st = btnIframe.run_js("""
            var b = document.querySelector("[role='button']");
            var ld = document.querySelector(".fetching-volume.draw, [role='status'], .draw");
            var ag = document.querySelector("[aria-label*='again'], [aria-label*='Again']");
            return {p: !!b, t: b ? String(b.textContent || '').trim().slice(0, 80) : '',
                    l: !!ld, a: !!ag};
            """, as_expr=False)
        except Exception:
            try:
                human_present = bool(page.ele("#human", timeout=2))
            except Exception:
                human_present = False
            if not human_present:
                return "passed"
            print("r{}: frame unavailable, retrying".format(rnd + 1))
            continue

        if st.get("l"):
            time.sleep(8)
            return "loading"
        if st.get("a"):
            return "retry"
        if st.get("p"):
            # PX button is still present without loading/retry hints —
            # treat as implicit retry: PX reset the button, wants another press.
            return "retry"
        print("r{}: pressed={} loading={} retry={}".format(
            rnd + 1, st.get("p"), st.get("l"), st.get("a")))
    return "timeout"


def is_px_done(btnIframe) -> bool:
    """检查 PX 验证是否完成（loading/draw 动画出现 = 进度条走满）。"""
    try:
        result = btnIframe.run_js("""
        var ld = document.querySelector(".fetching-volume.draw, .draw");
        return !!ld;
        """, as_expr=False)
        return bool(result)
    except Exception:
        return True  # frame 消失 = 验证通过


def px_btn_visible(btnIframe) -> bool:
    """检查 PX 按压按钮是否仍在页面上。"""
    try:
        result = btnIframe.run_js("""
        var btn = document.querySelector("[role='button']");
        return !!btn;
        """, as_expr=False)
        return bool(result)
    except Exception:
        return False
