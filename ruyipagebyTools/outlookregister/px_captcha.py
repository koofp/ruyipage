# -*- coding: utf-8 -*-
"""PX captcha handler: orchestrate full press-and-hold verification flow"""

import ctypes
import time

from ruyipage import FirefoxPage

user32 = ctypes.windll.user32

from waits import (wait_for_human_iframe, get_human_iframe_context,
                   wait_for_px_captcha_iframe, get_visible_px_iframe,
                   poll_px_result, is_px_done)
from px_probe import probe_context, get_hitbox
from win32_mouse import screen_coords, native_hold


def _get_offsets(page, humanCaptchaIframe) -> tuple[dict, dict, dict]:
    """取 PX iframe 偏移、#human iframe 偏移、mozInnerScreen 位置。"""
    px_off = humanCaptchaIframe.run_js("""
    var px = document.getElementById('px-captcha');
    var frame = px ? px.querySelector('iframe') : null;
    if (!frame) return {x: 0, y: 0};
    var rect = frame.getBoundingClientRect();
    return {x: rect.x, y: rect.y};
    """, as_expr=False)
    hu_off = page.run_js("""
    var human = document.getElementById('human');
    var frame = human ? human.querySelector('iframe') : null;
    if (!frame) return {x: 0, y: 0};
    var rect = frame.getBoundingClientRect();
    return {x: rect.x, y: rect.y};
    """, as_expr=False)
    vs = page.run_js(
        "return {x: window.mozInnerScreenX, y: window.mozInnerScreenY}",
        as_expr=False)
    return px_off, hu_off, vs


def handle_captcha(page: FirefoxPage) -> bool:
    """完整 PX 验证流程（含重试）。返回 True=通过, False=失败。"""

    # ── 1. wait for #human iframe ──
    if not wait_for_human_iframe(page):
        print("❌ #human iframe 未在 35 秒内显示")
        return False

    humanCaptchaIframe = get_human_iframe_context(page)
    if not humanCaptchaIframe:
        return False

    # ── 2. wait for #px-captcha iframe ──
    if not wait_for_px_captcha_iframe(humanCaptchaIframe):
        print("❌ #px-captcha iframe 未在 35 秒内加载")
        return False

    page.wait(1)

    # 诊断 #px-captcha 结构
    px_info = humanCaptchaIframe.run_js("""
    var px = document.getElementById('px-captcha');
    if (!px) return 'not found';
    return {tag: px.tagName, children: px.children.length,
            hasShadowRoot: !!px.shadowRoot, inner_size: px.innerHTML.length};
    """, as_expr=False)
    print("#px-captcha: {}".format(px_info))

    # ── 3. get visible PX iframe（3 次重试，等待瞬态重建）──
    btnIframe = None
    vis_idx = -1
    for _get_retry in range(3):
        btnIframe, vis_idx = get_visible_px_iframe(humanCaptchaIframe)
        if btnIframe:
            break
        print("PX iframe not visible (attempt {}/3), retrying...".format(_get_retry + 1))
        time.sleep(2)
    if not btnIframe:
        return False
    print("btnIframe {} (visible_idx={})".format(btnIframe, vis_idx))

    # ── 4. probe PX context ──
    probe = probe_context(btnIframe)
    candidates = probe.get("challengeCandidates") or []
    if not candidates:
        print("No PX challenge candidates found; stopping.")
        return False
    top = candidates[0]
    print("PX probe: {} elements, top score={} id={} text={!r}".format(
        probe.get("elementCount", 0), top.get("score"), top.get("id"),
        (top.get("text") or "")[:50]))

    # ── 5. pre-hover cursor into #px-captcha area ──
    _, hu_off, vs = _get_offsets(page, humanCaptchaIframe)
    pre_hitbox = get_hitbox(humanCaptchaIframe)
    if pre_hitbox:
        pre_sx = int(vs["x"] + pre_hitbox["cx"] + hu_off["x"])
        pre_sy = int(vs["y"] + pre_hitbox["cy"] + hu_off["y"])
        print("Pre-hover PX at screen ({}, {})".format(pre_sx, pre_sy))
        user32.SetCursorPos(pre_sx, pre_sy)
        time.sleep(2)

    # ── 6-8. press + poll + retry loop ──
    for attempt in range(3):
        hitbox = get_hitbox(humanCaptchaIframe)
        if not hitbox:
            print("PX hitbox unavailable (attempt {}/3)".format(attempt + 1))
            time.sleep(3)
            continue

        btn_cx, btn_cy = hitbox["cx"], hitbox["cy"]
        print("attempt {}/3: hitbox center=({}, {})".format(
            attempt + 1, btn_cx, btn_cy))

        px_off, hu_off, vs = _get_offsets(page, humanCaptchaIframe)
        sx, sy = screen_coords(btn_cx, btn_cy, px_off, hu_off, vs, skip_px_offset=True)
        print("screen=({}, {})".format(sx, sy))

        # Capture the current btnIframe reference before pressing.
        # PX may recreate the iframe after each attempt, so we also
        # re-fetch it *after* the hold when polling.
        _current_btnIframe = btnIframe
        native_hold(sx, sy, min_seconds=12.0, max_seconds=15.0,
                    is_done=lambda: is_px_done(_current_btnIframe))

        try:
            result = poll_px_result(page, humanCaptchaIframe)
        except Exception as _poll_err:
            _msg = str(_poll_err)
            print("PX poll failed: {}: {}".format(type(_poll_err).__name__, _msg[:120]))
            # no such frame = PX iframe temporarily gone during rebuild — retriable
            if "no such frame" in _msg:
                result = "retry"
            else:
                result = "timeout"
        print("PX result: {}".format(result))
        if result in ("passed", "loading"):
            return True
        if result == "retry":
            print("PX requested retry ({}/3), waiting 3s...".format(attempt + 1))
            time.sleep(3)
            # Before the next attempt, refresh the PX iframe reference.
            # 3 retries, then clean failure if still no frame available.
            new_btn = None
            for _retry in range(3):
                new_btn, _ = get_visible_px_iframe(humanCaptchaIframe)
                if new_btn:
                    btnIframe = new_btn
                    print("btnIframe refreshed for retry: {}".format(btnIframe))
                    break
                print("PX iframe refresh (attempt {}/3), retrying...".format(_retry + 1))
                time.sleep(2)
            if not new_btn:
                print("PX iframe still unavailable after refresh — aborting this attempt")
                return False
        return False

    print("PX failed after 3 attempts")
    return False
