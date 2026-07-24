import random
import time
from ruyipage import FirefoxOptions, FirefoxPage
from utils import generate_strong_password,random_email,randomDayAndMonthAndYear,generate_name
# proxies = [
# "gate.kookeey.info:1000:9309087-e0061b49f2:e954d2bfe3-GB-17303897",
# "gate.kookeey.info:1000:9309087-e0061b49f2:e954d2bfe3-GB-01631188",
# "gate.kookeey.info:1000:9309087-e0061b49f2:e954d2bfe3-GB-73014452"
# ]

# 这个 API 就是帮你把代理 IP、时区、语言、屏幕、硬件指纹、地理位置全部对齐到同一个国家，减少被微软风控识别的概率。 做 Outlook 注册的话强烈建议用上。
# ctx = opts.smart_fingerprint(
#     proxy_host="gate.kookeey.info",
#     proxy_port=1000,
#     proxy_user="9309087-e0061b49f2",
#     proxy_pwd="e954d2bfe3-JP-55450647-20m",
#     require_country="JP",         # kookeey 后缀是 JP，要求日本
#     logger=print,
# )

# page = FirefoxPage(opts)
# ctx.apply_emulation(page)
# page.get("https://signup.live.com/")

REG_EMAIL = f"{random_email()}@outlook.com"
REG_PASSWORD = generate_strong_password()
PROXY = "http://127.0.0.1:7897"  # 注册与 Graph token 提取共用代理

opts = FirefoxOptions()

# 链式调用，逐个配置
opts.set_browser_path(r"D:\EXED\10_brower\firefox\firefox.exe")
opts.set_port(12000)
opts.headless(False)
opts.set_window_size(1440, 900)
opts.set_human_algorithm("windmouse")
opts.set_proxy(PROXY)

opts.private_mode(False)
opts.close_on_exit(False)
# opts.enable_xpath_picker(True)
opts.enable_action_visual(True)
# 动态住宅代理
# opts.set_per_tab_proxies(proxies, exhausted="wrap")

page = FirefoxPage(opts)
page.get("https://signup.live.com/", wait="complete")
page.wait(0.8)

# 输入邮箱
page.actions.human_move(page.ele("#floatingLabelInput4"), algorithm="windmouse").human_click().human_type(REG_EMAIL).perform()
page.wait(0.6)

# 账号点击下一步
# page 已经是 FirefoxPage / FirefoxTab 实例
accountNext = page.ele("xpath://button[@data-testid=\"primaryButton\"]")
# CSS 备选: button[data-testid="primaryButton"]
page.actions.human_move(accountNext, algorithm="windmouse").human_click().perform()
page.wait(0.7)

# password 密码
# page 已经是 FirefoxPage / FirefoxTab 实例
passwordBtn = page.ele("xpath://*[@id=\"floatingLabelInput13\"]")
# CSS 备选: #floatingLabelInput13
page.actions.human_move(passwordBtn, algorithm="windmouse").human_click().human_type(REG_PASSWORD).perform()
page.wait(0.8)

# password点击下一步
# page 已经是 FirefoxPage / FirefoxTab 实例
accountNext = page.ele("xpath://button[@data-testid=\"primaryButton\"]")
# CSS 备选: button[data-testid="primaryButton"]
page.actions.human_move(accountNext, algorithm="windmouse").human_click().perform()
page.wait(0.6)

# 月 mouth
# ruyiPage generated snippet
# page 已经是 FirefoxPage / FirefoxTab 实例
mouth = page.ele("xpath://*[@id=\"BirthMonthDropdown\"]")
# CSS 备选: #BirthMonthDropdown
page.actions.human_move(mouth, algorithm="windmouse").human_click().perform()
page.wait(0.6)

roleMouth = page.eles("xpath://div[@role=\"option\"]")
page.actions.human_move(roleMouth[randomDayAndMonthAndYear("month")], algorithm="windmouse").human_click().perform()
page.wait(0.5)


# 日
day = page.ele("xpath://*[@id=\"BirthDayDropdown\"]")
# CSS 备选: #BirthDayDropdown
page.actions.human_move(day, algorithm="windmouse").human_click().perform()
page.wait(0.7)
roleMouth = page.eles("xpath://div[@role=\"option\"]")
page.actions.human_move(roleMouth[randomDayAndMonthAndYear("day")], algorithm="windmouse").human_click().perform()
page.wait(0.6)

# year
year = page.ele("xpath://*[@id=\"floatingLabelInput24\"]")
# CSS 备选: #floatingLabelInput24
page.actions.human_move(year, algorithm="windmouse").human_click().human_type(randomDayAndMonthAndYear("year")).perform()
page.wait(0.8)

# 角色信息下一步
roleProfileNext = page.ele("xpath://button[@data-testid=\"primaryButton\"]")
# CSS 备选: button[data-testid="primaryButton"]
page.actions.human_move(roleProfileNext, algorithm="windmouse").human_click().perform()
page.wait(0.6)


first_name, last_name = generate_name()
# first name
firstName = page.ele("xpath://*[@id=\"firstNameInput\"]")
# CSS 备选: #firstNameInput
page.actions.human_move(firstName, algorithm="windmouse").human_click().human_type(first_name).perform()
page.wait(0.8)

# last name
lastname = page.ele("xpath://div[1]/div[2]/div[1]/span[1]")
# CSS 备选: div[data-testid="lastNameInput"] > div.fui-Field.___1noo6zn > span.fui-Input.r1oeeo9n
page.actions.human_move(lastname, algorithm="windmouse").human_click().human_type(last_name).perform()

# name点击下一步
nameNext = page.ele("xpath://button[@data-testid=\"primaryButton\"]")
# CSS 备选: button[data-testid="primaryButton"]
page.actions.human_move(nameNext, algorithm="windmouse").human_click().perform()
page.wait(2)





iframe_visible = False
for _ in range(35):
    iframe_visible = page.run_js("""
    var p = document.getElementById('human');
    var f = p ? p.querySelector('iframe') : null;
    return f && f.style.display !== 'none';
""", as_expr=False)
    if iframe_visible:
        break
    print("等待 iframe 显示...")
    time.sleep(1)

if not iframe_visible:
    print("❌ iframe 35 秒后仍未显示，脚本终止")
    exit(1)


# ── 诊断：ifram 到底在不在 ──

# 1. 看看 #human 本身存在吗
captcha = page.ele("#human", timeout=5)
if captcha:
    print(f"#human 存在")

    # 2. 看看里面有没有 iframe
    iframe_count = page.run_js("""
        var p = document.getElementById('human');
        return p ? p.querySelectorAll('iframe').length : -1;
    """, as_expr=False)
    print(f"#human 内含 iframe 数量: {iframe_count}")

    # 3. 看看 iframe 的 display 状态和 title 属性
    iframe_info = page.run_js("""
        var p = document.getElementById('human');
        var f = p ? p.querySelector('iframe') : null;
        if (!f) return 'not found';
        return {
            display: f.style.display,
            title: f.title || '(no title)',
            token: f.getAttribute('token') ? 'yes' : 'no',
        };
    """, as_expr=False)
    print(f"iframe 信息: {iframe_info}")
else:
    print("#human 不存在，当前页面结构：")
    print(page.run_js("return document.body.innerHTML.substring(0, 500)"))
    print("❌ #human 不存在，脚本终止")
    exit(1)




# ── 1. 通过 #human 找到 iframe，用 get_frame 切换上下文 ──
humanCaptchaIframe = page.get_frame("css:#human iframe[data-testid='humanCaptchaIframe']")
if not humanCaptchaIframe:
    print("❌ get_frame() 返回 None，无法获取 iframe 上下文，脚本终止")
    exit(1)




btnIframe_visible = False
for _ in range(35):
    btnIframe_visible = humanCaptchaIframe.run_js("""
        var p = document.getElementById('px-captcha');
        var f = p ? p.querySelector('iframe') : null;                                 
        if (!f) return false;
        var display = window.getComputedStyle(f).display;
        return display !== 'none';
    """, as_expr=False)
    if btnIframe_visible:
        break
    print("等待 btnIframe_visible 显示...")
    time.sleep(1)

if not btnIframe_visible:
    print("❌ btnIframe_visible 35 秒后仍未显示，脚本终止")
    exit(1)


page.wait(2)


# 看看 #px-captcha 是什么标签，里面有什么
px_info = humanCaptchaIframe.run_js("""
    var px = document.getElementById('px-captcha');
    if (!px) return 'not found';
    return {
        tag: px.tagName,
        children: px.children.length,
        childTags: Array.from(px.children).map(function(c) { 
            return {tag: c.tagName, id: c.id || '', role: c.getAttribute('role') || ''}; 
        }),
        hasShadowRoot: !!px.shadowRoot,
        innerHTML_size: px.innerHTML.length,
    };
""", as_expr=False)
print(f"#px-captcha 结构: {px_info}")


btnIframe111_visible = False
for _ in range(30):
    btnIframe111_visible = humanCaptchaIframe.run_js("""
    var px = document.getElementById('px-captcha');
    var f = px ? px.querySelector('iframe') : null;
    return f && f.contentWindow !== null;
""", as_expr=False)
    if btnIframe111_visible:
        break
    print("等待 #px-captcha iframe 加载完成...")
    time.sleep(1)
if not btnIframe111_visible:
    print("❌ btnIframe111_visible 35 秒后仍未显示，脚本终止")
    exit(1)

# 循环通过后，额外等 1 秒让 BiDi context tree 同步
page.wait(3)

# 先在 humanCaptchaIframe 里找哪个 iframe 是可见的
visible_idx = humanCaptchaIframe.run_js("""
    var iframes = document.querySelectorAll('#px-captcha iframe');
    for (var i = 0; i < iframes.length; i++) {
        var display = window.getComputedStyle(iframes[i]).display;
        if (display !== 'none') {
            return i;
        }
    }
    // Fallback: use the last iframe if none has a visible display value.
    return iframes.length - 1;
""", as_expr=False)

btnIframe = humanCaptchaIframe.get_frame(index=visible_idx)
if not btnIframe:
    print("❌ get_frame(index=" + str(visible_idx) + ") 返回 None，脚本终止")
    exit(1)

print(f"btnIframe {btnIframe} (visible_idx={visible_idx})")


# 看看这个 PerimeterX iframe 里面有什么按钮
px_inner = btnIframe.run_js("""
    var btns = document.querySelectorAll('div[role="button"], button, [aria-label*="hold"], [aria-label*="press"], [aria-label*="Hold"], [aria-label*="Press"]');
    var result = [];
    for (var i = 0; i < btns.length; i++) {
        result.push({
            tag: btns[i].tagName,
            role: btns[i].getAttribute('role') || '',
            ariaLabel: btns[i].getAttribute('aria-label') || '',
            text: btns[i].textContent.trim().substring(0, 50),
            display: window.getComputedStyle(btns[i]).display,
        });
    }
    return result;
""", as_expr=False)
print(f"PerimeterX 内部按钮: {px_inner}")

# PX probe, hover activation, hitbox discovery, native hold, and status polling.
probe_js = r"""
(function() {
    "use strict";
    var isElement = function(el) { return !!el && el.nodeType === 1; };
    var normalizeText = function(value) {
        var s = String(value || ''), out = '', pending = false, i, ch, white;
        for (i = 0; i < s.length; i += 1) {
            ch = s.charAt(i);
            white = ch === ' ' || ch === '\t' || ch === '\r' || ch === '\n' || ch === '\f';
            if (white) pending = out.length > 0;
            else { if (pending) out += ' '; out += ch; pending = false; }
        }
        return out;
    };
    var hasAny = function(value, words) {
        var text = String(value || '').toLowerCase(), i;
        for (i = 0; i < words.length; i += 1) {
            if (text.indexOf(words[i]) !== -1) return true;
        }
        return false;
    };
    var byIdXPath = function(el) {
        return isElement(el) && el.id ? "//*[@id=" + JSON.stringify(el.id) + "]" : '';
    };
    var absoluteXPath = function(el) {
        if (!isElement(el)) return '';
        var parts = [], cur = el, tag, index, sibling;
        while (isElement(cur)) {
            tag = String(cur.tagName || '').toLowerCase();
            if (!tag) break;
            index = 1; sibling = cur.previousElementSibling;
            while (sibling) {
                if (String(sibling.tagName || '').toLowerCase() === tag) index += 1;
                sibling = sibling.previousElementSibling;
            }
            parts.unshift(tag + '[' + index + ']');
            cur = cur.parentElement;
        }
        return parts.length ? '/' + parts.join('/') : '';
    };
    var cssOf = function(el) {
        if (!isElement(el)) return '';
        if (el.id) return '[id=' + JSON.stringify(String(el.id)) + ']';
        var parts = [], cur = el, tag, index, sibling;
        while (isElement(cur)) {
            tag = String(cur.tagName || '').toLowerCase();
            if (!tag) return '';
            index = 1; sibling = cur.previousElementSibling;
            while (sibling) {
                if (String(sibling.tagName || '').toLowerCase() === tag) index += 1;
                sibling = sibling.previousElementSibling;
            }
            parts.unshift(tag + ':nth-of-type(' + index + ')');
            if (tag === 'html') break;
            cur = cur.parentElement;
        }
        return parts.join(' > ');
    };
    var challengeLike = function(el) {
        if (!isElement(el)) return false;
        var tag = String(el.tagName || '').toLowerCase();
        var role = String(el.getAttribute('role') || '').toLowerCase();
        var identity = String(el.id || '') + ' ' + String(el.className || '') + ' ' + String(el.getAttribute('name') || '');
        if (['button', 'input', 'textarea', 'select', 'canvas', 'svg'].indexOf(tag) !== -1) return true;
        if (['button', 'checkbox', 'switch', 'slider'].indexOf(role) !== -1) return true;
        if (el.hasAttribute('tabindex')) return true;
        return hasAny(normalizeText(el.textContent || ''), ['press', 'hold', 'verify', 'challenge', 'human', 'captcha']) ||
            hasAny(identity, ['press', 'hold', 'verify', 'challenge', 'captcha', 'human', 'checkbox', 'slider', 'button']);
    };
    var score = function(el) {
        var tag = String(el.tagName || '').toLowerCase();
        var role = String(el.getAttribute('role') || '').toLowerCase();
        var text = normalizeText(el.textContent || '');
        var value = 0;
        if (['button', 'input'].indexOf(tag) !== -1) value += 50;
        if (tag === 'canvas') value += 30;
        if (role === 'button') value += 25;
        if (el.hasAttribute('tabindex')) value += 10;
        if (hasAny(text, ['press'])) value += 35;
        if (hasAny(text, ['hold'])) value += 25;
        if (hasAny(text, ['verify', 'challenge', 'human', 'captcha'])) value += 15;
        if (el.id) value += 6;
        return value;
    };
    var candidates = function() {
        var all = document.querySelectorAll('*'), result = [], i, el, tag;
        for (i = 0; i < all.length; i += 1) {
            el = all[i];
            if (!challengeLike(el)) continue;
            tag = String(el.tagName || '').toLowerCase();
            result.push({
                score: score(el), targetType: tag === 'canvas' ? 'canvas-host' : 'dom',
                tag: tag, id: el.id || '', className: typeof el.className === 'string' ? el.className : '',
                role: el.getAttribute('role') || '', text: normalizeText(el.textContent || '').slice(0, 160),
                css: cssOf(el), relativeXPath: byIdXPath(el), absoluteXPath: absoluteXPath(el)
            });
        }
        result.sort(function(a, b) { return b.score - a.score; });
        return result.slice(0, 12);
    };
    var centerHit = function() {
        var x = Math.max(1, Math.floor(window.innerWidth / 2));
        var y = Math.max(1, Math.floor(window.innerHeight / 2));
        var list = typeof document.elementsFromPoint === 'function' ? document.elementsFromPoint(x, y) : [];
        var el = list.length ? list[0] : document.elementFromPoint(x, y);
        if (!isElement(el)) return {targetType: 'none', point: {x: x, y: y}};
        var tag = String(el.tagName || '').toLowerCase();
        return {targetType: tag === 'canvas' ? 'canvas-host' : 'dom', point: {x: x, y: y}, tag: tag,
            id: el.id || '', className: typeof el.className === 'string' ? el.className : '',
            role: el.getAttribute('role') || '', text: normalizeText(el.textContent || '').slice(0, 120),
            css: cssOf(el), absoluteXPath: absoluteXPath(el)};
    };
    var all = document.querySelectorAll('*');
    return {locationHref: location.href, locationOrigin: location.origin, title: document.title,
        readyState: document.readyState, elementCount: all.length,
        iframeCount: document.querySelectorAll('iframe').length, buttonCount: document.querySelectorAll('button').length,
        inputCount: document.querySelectorAll('input').length, canvasCount: document.querySelectorAll('canvas').length,
        centerHit: centerHit(), challengeCandidates: candidates()};
})()
"""
probe_result = btnIframe.run_js(probe_js, as_expr=True)
print("=== PX context probe ===")
print("url={} origin={} title={!r} readyState={}".format(probe_result.get("locationHref", ""), probe_result.get("locationOrigin", ""), probe_result.get("title", ""), probe_result.get("readyState", "")))
print("elements={} iframes={} buttons={} inputs={} canvas={}".format(probe_result.get("elementCount", 0), probe_result.get("iframeCount", 0), probe_result.get("buttonCount", 0), probe_result.get("inputCount", 0), probe_result.get("canvasCount", 0)))
center_hit = probe_result.get("centerHit") or {}
print("centerHit: tag={} role={} id={} text={!r} point={}".format(center_hit.get("tag", ""), center_hit.get("role", ""), center_hit.get("id", ""), center_hit.get("text", ""), center_hit.get("point", {})))
candidates = probe_result.get("challengeCandidates") or []
for i, candidate in enumerate(candidates[:8]):
    print("  {}. score={} tag={} role={} id={} text={!r} css={}".format(i + 1, candidate.get("score"), candidate.get("tag"), candidate.get("role"), candidate.get("id"), candidate.get("text"), candidate.get("css")))
if not candidates:
    print("No PX challenge candidates were found; stopping.")
    exit(1)
top_candidate = candidates[0]
btn_css = top_candidate.get("css") or ""
if not btn_css:
    print("The best PX candidate has no usable CSS selector; stopping.")
    exit(1)

import ctypes
from ctypes import wintypes
user32 = ctypes.windll.user32
class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

# Move the OS pointer into the outer PX iframe to allow genuine hover-driven layout.
center_is_control = center_hit.get("tag") in ("button", "input", "canvas") or center_hit.get("role") in ("button", "checkbox", "switch", "slider")
px_outer = humanCaptchaIframe.run_js("""
var px = document.getElementById('px-captcha');
var frame = px ? px.querySelector('iframe') : null;
if (!frame) return null;
var rect = frame.getBoundingClientRect();
return {x: rect.x, y: rect.y, w: rect.width, h: rect.height};
""", as_expr=False)
hu_off = page.run_js("""
var human = document.getElementById('human');
var frame = human ? human.querySelector('iframe') : null;
if (!frame) return null;
var rect = frame.getBoundingClientRect();
return {x: rect.x, y: rect.y};
""", as_expr=False)
vs = page.run_js("return {x: window.mozInnerScreenX, y: window.mozInnerScreenY}", as_expr=False)
if not center_is_control and px_outer and px_outer.get("w", 0) > 0 and px_outer.get("h", 0) > 0 and hu_off:
    old_point = POINT()
    user32.GetCursorPos(ctypes.byref(old_point))
    hover_sx = vs["x"] + px_outer["x"] + px_outer["w"] / 2 + hu_off["x"]
    hover_sy = vs["y"] + px_outer["y"] + px_outer["h"] / 2 + hu_off["y"]
    print("Pre-hovering PX iframe at screen ({}, {})".format(int(hover_sx), int(hover_sy)))
    user32.SetCursorPos(int(hover_sx), int(hover_sy))
    time.sleep(2)
    user32.SetCursorPos(int(old_point.x), int(old_point.y))

# Poll candidate and ancestors for the first visible, hit-tested non-root interaction box.
safe_btn_css = btn_css.replace('\\', '\\\\').replace("'", "\\'")
hitbox = None
for attempt in range(60):
    hitbox = btnIframe.run_js("""
var selector = '""" + safe_btn_css + """';
var el = document.querySelector(selector);
if (!el) return null;
var current = el;
var level = 0;
while (current && current.nodeType === 1) {
    var tag = String(current.tagName || '').toLowerCase();
    var style = window.getComputedStyle(current);
    var rect = current.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden' && style.pointerEvents !== 'none') {
        var cx = rect.x + rect.width / 2;
        var cy = rect.y + rect.height / 2;
        var hits = typeof document.elementsFromPoint === 'function' ? document.elementsFromPoint(cx, cy) : [];
        var verified = false;
        var i;
        for (i = 0; i < hits.length; i += 1) {
            var hit = hits[i];
            if (hit === el || hit === current || el.contains(hit) || hit.contains(el)) { verified = true; break; }
        }
        if (verified) return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, cx: cx, cy: cy, level: level, tag: tag};
    }
    current = current.parentElement;
    level += 1;
}
return null;
""", as_expr=False)
    if hitbox and hitbox.get("w", 0) > 0 and hitbox.get("h", 0) > 0:
        break
    time.sleep(0.5)
skip_px_offset = False
if not hitbox or hitbox.get("w", 0) <= 0 or hitbox.get("h", 0) <= 0:
    # Fallback: use the #px-captcha DIV container rect (in humanCaptchaIframe).
    px_div = humanCaptchaIframe.run_js("""
        var el = document.getElementById('px-captcha');
        if (!el) return null;
        var r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) return null;
        return {x: r.x, y: r.y, w: r.width, h: r.height};
    """, as_expr=False)
    if px_div and px_div.get("w", 0) > 0 and px_div.get("h", 0) > 0:
        hitbox = {
            "x": px_div["x"],
            "y": px_div["y"] + px_div["h"] * 0.48,
            "w": px_div["w"],
            "h": px_div["h"] * 0.12,
            "cx": px_div["x"] + px_div["w"] / 2,
            "cy": px_div["y"] + px_div["h"] * 0.54,
        }
        skip_px_offset = True
        print("PX hitbox: fallback #px-captcha DIV container rect=({},{},{}x{})".format(
            px_div["x"], px_div["y"], px_div["w"], px_div["h"]))
    else:
        print("No verified PX hitbox appeared within 30 seconds; stopping.")
        exit(1)
btn_cx, btn_cy = hitbox["cx"], hitbox["cy"]
print("PX hitbox: tag={} level={} rect=({}, {}, {}x{}) center=({}, {})".format(hitbox.get("tag"), hitbox.get("level"), hitbox["x"], hitbox["y"], hitbox["w"], hitbox["h"], btn_cx, btn_cy))

# Re-read offsets after the hover wait, then form the absolute OS screen target.
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
vs = page.run_js("return {x: window.mozInnerScreenX, y: window.mozInnerScreenY}", as_expr=False)
if skip_px_offset:
    vx = btn_cx + hu_off["x"]
    vy = btn_cy + hu_off["y"]
else:
    vx = btn_cx + px_off["x"] + hu_off["x"]
    vy = btn_cy + px_off["y"] + hu_off["y"]

sx = vs["x"] + vx
sy = vs["y"] + vy
print("viewport=({}, {}), screen=({}, {})".format(vx, vy, int(sx), int(sy)))

INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]
class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]
class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]
def send_mouse(flags):
    event = INPUT()
    event.type = INPUT_MOUSE
    event.union.mi = MOUSEINPUT(0, 0, 0, flags, 0, 0)
    return user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
if not user32.SetCursorPos(int(sx), int(sy)):
    raise ctypes.WinError(ctypes.get_last_error())
time.sleep(0.15)
if send_mouse(MOUSEEVENTF_LEFTDOWN) != 1:
    raise ctypes.WinError(ctypes.get_last_error())
print("LEFTDOWN")
try:
    hold_until = time.time() + 11.0
    while time.time() < hold_until:
        user32.SetCursorPos(int(sx) + random.randint(-2, 2), int(sy) + random.randint(-2, 2))
        time.sleep(random.uniform(0.08, 0.35))
finally:
    send_mouse(MOUSEEVENTF_LEFTUP)
    print("LEFTUP")

print("Polling PX result...")
page.wait(5)
for rnd in range(6):
    page.wait(3)
    try:
        status = btnIframe.run_js("""
var button = document.querySelector("[role='button']");
var loading = document.querySelector(".fetching-volume.draw, [role='status'], .draw");
var retry = document.querySelector("[aria-label*='again'], [aria-label*='Again'], [aria-label*='retry'], [aria-label*='Retry'], [aria-label*='?']");
return {buttonPresent: !!button, buttonText: button ? String(button.textContent || '').trim().slice(0, 120) : '', loading: !!loading, retry: !!retry};
""", as_expr=False)
    except Exception as exc:
        print("round {}: PX frame unavailable ({})".format(rnd + 1, exc))
        try:
            human_present = bool(page.ele("#human", timeout=2))
        except Exception:
            human_present = False
        if not human_present:
            print("PX frame and #human disappeared; challenge likely passed.")
            break
        continue
    print("round {}: button={} loading={} retry={} text={!r}".format(rnd + 1, status.get("buttonPresent"), status.get("loading"), status.get("retry"), status.get("buttonText")))
    if status.get("loading"):
        print("PX is processing; waiting for registration flow.")
        page.wait(8)
        break
    if status.get("retry"):
        print("PX requested a retry.")
        break
print("PX verification handling complete; continuing registration flow...")
# ── 保存注册结果 ──
from getAccountData import save_account_data
try:
    result = save_account_data(page, REG_EMAIL, REG_PASSWORD, proxy=PROXY)
    print(f"[FirefoxOptions] 账号保存结果: {result}")
finally:
    try:
        page.quit()
    except Exception as exc:
        print(f"[FirefoxOptions] page.quit failed: {type(exc).__name__}: {exc}")
