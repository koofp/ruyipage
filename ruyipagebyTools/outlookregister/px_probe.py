# -*- coding: utf-8 -*-
"""PX probe: JS 脚本 + runner"""

# 从 42_3_debug_px_context_probe.py 改编 —— 纯 ES5 无箭头/模板/正则
PX_PROBE_JS: str = r"""
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


def probe_context(btnIframe) -> dict:
    """在 PX iframe 内执行探测脚本，返回完整的 probe result dict。"""
    return btnIframe.run_js(PX_PROBE_JS, as_expr=True)


def get_hitbox(humanCaptchaIframe) -> dict:
    """取 #px-captcha DIV 容器的 rect，返回 hitbox dict 或 None。"""
    px_div = humanCaptchaIframe.run_js("""
    var el = document.getElementById('px-captcha');
    if (!el) return null;
    var r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return null;
    return {x: r.x, y: r.y, w: r.width, h: r.height};
""", as_expr=False)

    if px_div and px_div.get("w", 0) > 0 and px_div.get("h", 0) > 0:
        return {
            "x": px_div["x"],
            "y": px_div["y"] + px_div["h"] * 0.48,
            "w": px_div["w"],
            "h": px_div["h"] * 0.12,
            "cx": px_div["x"] + px_div["w"] / 2,
            "cy": px_div["y"] + px_div["h"] * 0.54,
        }
    return None
