# -*- coding: utf-8 -*-
"""PX captcha handler: orchestrate full press-and-hold verification flow"""

import time
import sys

from ruyipage import FirefoxPage

from waits import (wait_for_human_iframe, get_human_iframe_context,
                   wait_for_px_captcha_iframe, get_visible_px_iframe,
                   poll_px_result)
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
    """完整 PX 验证流程。返回 True=通过, False=失败。"""

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

    # ── 3. get visible PX iframe ──
    btnIframe, vis_idx = get_visible_px_iframe(humanCaptchaIframe)
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
    print("PX probe: {} elements, top candidate score={} id={} text={!r}".format(
        probe.get("elementCount", 0), top.get("score"), top.get("id"),
        (top.get("text") or "")[:50]))

    # ── 5. get hitbox from #px-captcha container ──
    hitbox = get_hitbox(humanCaptchaIframe)
    if not hitbox:
        print("No PX hitbox available; stopping.")
        return False

    btn_cx, btn_cy = hitbox["cx"], hitbox["cy"]
    print("PX hitbox center=({}, {}), rect=({}, {}, {}x{})".format(
        btn_cx, btn_cy, hitbox["x"], hitbox["y"], hitbox["w"], hitbox["h"]))

    # ── 6. coordinates → screen absolute ──
    px_off, hu_off, vs = _get_offsets(page, humanCaptchaIframe)
    sx, sy = screen_coords(btn_cx, btn_cy, px_off, hu_off, vs, skip_px_offset=True)
    print("viewport=({:.1f}, {:.1f}) screen=({}, {})".format(
        btn_cx + hu_off["x"], btn_cy + hu_off["y"], sx, sy))

    # ── 7. native mouse hold ──
    print("LEFTDOWN (native hold 11s)")
    native_hold(sx, sy, hold_seconds=11.0)

    # ── 8. poll result ──
    result = poll_px_result(page, btnIframe)
    print("PX result: {}".format(result))
    return result in ("passed", "loading")
