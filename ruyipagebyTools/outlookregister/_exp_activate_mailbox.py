# -*- coding: utf-8 -*-
"""Experiment: activate Outlook mailbox, then use browser cookies for HTTP OAuth token extraction.

This script does not modify pending/pool records and never prints password, cookie, or token values.
"""

import json
import os
import re
import sys
import time
import types
import urllib.parse
from pathlib import Path


class _RedactingWriter:
    """Redact proxy credentials from stdout/stderr as a final safety net."""

    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        safe = re.sub(r"://[^@\s]+@", "://***@", str(text))
        return self.stream.write(safe)

    def flush(self):
        return self.stream.flush()

    def reconfigure(self, *args, **kwargs):
        method = getattr(self.stream, "reconfigure", None)
        if method:
            return method(*args, **kwargs)
        return None

    def __getattr__(self, name):
        return getattr(self.stream, name)


sys.stdout = _RedactingWriter(sys.stdout)
sys.stderr = _RedactingWriter(sys.stderr)

from config import Settings, create_page
import getAccountData as gad
from extract_graph_tokens import get_graph_token, reg_factory_module


SCRIPT_DIR = Path(__file__).resolve().parent
PENDING_FILE = SCRIPT_DIR / "_outlook_pool" / ".pending" / "uwjc2qhwljtk_at_outlook.com.json"
ENV_LOCAL = SCRIPT_DIR / ".env.local"
MAIL_URL = "https://outlook.live.com/mail/0/"


def _load_env_file(path):
    values = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _safe_url(url):
    try:
        parsed = urllib.parse.urlsplit(str(url or ""))
        return "{}://{}{}".format(parsed.scheme, parsed.netloc, parsed.path)
    except Exception:
        return "(unknown-url)"


def _page_snapshot(page, label):
    try:
        url = page.url or ""
    except Exception:
        url = ""
    try:
        title = page.title or ""
    except Exception:
        title = ""
    print("[exp] {}: url={} title={!r}".format(label, _safe_url(url), str(title)[:100]))
    return url, str(title)


def _click_first(page, selectors):
    for selector in selectors:
        try:
            element = page.ele(selector, timeout=1)
            if element:
                element.click_self()
                page.wait(2)
                return selector
        except Exception:
            continue
    return None


def _type_secret(page, selectors, value):
    for selector in selectors:
        try:
            element = page.ele(selector, timeout=1)
            if not element:
                continue
            page.actions.human_move(element, algorithm="windmouse").human_click().human_type(
                value
            ).perform()
            page.wait(1)
            return selector
        except Exception:
            continue
    return None


def _mailbox_ready(page):
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    if "outlook.live.com/mail" not in url:
        return False
    try:
        state = page.run_js(
            """
            var text = String(document.body ? document.body.innerText : '').toLowerCase();
            return {
              ready: document.readyState,
              mailbox: !!document.querySelector('[role="main"], [aria-label*="Inbox"], [aria-label*="\u6536\u4ef6\u7bb1"]')
                       || text.indexOf('inbox') >= 0 || text.indexOf('\u6536\u4ef6\u7bb1') >= 0
            };
            """,
            as_expr=False,
        )
        return bool(state and state.get("mailbox"))
    except Exception:
        return "/mail/0" in url


def _activate_mailbox(page, email, password, saved_cookies):
    """Load cookies, fall back to one form login, and try to skip security-info enrollment."""
    if saved_cookies:
        try:
            page.set_cookies(saved_cookies)
            print("[exp] Browser cookies injected: {} (values hidden)".format(len(saved_cookies)))
        except Exception as exc:
            print("[exp] Bulk cookie injection failed: {}; retrying one by one".format(type(exc).__name__))
            loaded = 0
            for cookie in saved_cookies:
                try:
                    page.set_cookies(cookie)
                    loaded += 1
                except Exception:
                    pass
            print("[exp] Cookie injection completed: {}/{}".format(loaded, len(saved_cookies)))

    page.get(MAIL_URL, wait="complete", timeout=45)
    page.wait(3)
    forced_mail_retry = False

    for round_no in range(10):
        url, _ = _page_snapshot(page, "mailbox check r{}".format(round_no + 1))
        if _mailbox_ready(page):
            print("[exp] Mailbox home confirmed")
            return True

        skip_selector = _click_first(
            page,
            [
                "#iShowSkip",
                "css:input#iShowSkip",
                "xpath://button[contains(., 'Skip') or contains(., '\u8df3\u8fc7')]",
                "xpath://input[contains(@value, 'Skip') or contains(@value, '\u8df3\u8fc7')]",
                "xpath://button[contains(., 'No thanks') or contains(., '\u6682\u65f6\u4e0d\u8981')]",
            ],
        )
        if skip_selector:
            print("[exp] Security-info skip clicked: {}".format(skip_selector))
            continue

        # If cookies did not restore login state, perform one form login without printing inputs.
        if _type_secret(page, ["#i0116", "css:input[type='email']"], email):
            print("[exp] Account field submitted")
            _click_first(page, ["#idSIButton9", "css:button[type='submit']", "css:input[type='submit']"])
            continue
        if _type_secret(page, ["#i0118", "css:input[type='password']"], password):
            print("[exp] Password field submitted")
            _click_first(page, ["#idSIButton9", "css:button[type='submit']", "css:input[type='submit']"])
            continue

        # Stay-signed-in or generic continue button.
        if _click_first(page, ["#idSIButton9", "css:button[type='submit']"]):
            print("[exp] Login-flow continue button clicked")
            continue

        lower_url = (url or "").lower()
        protect_page = any(token in lower_url for token in ("proofs", "protect", "identity/confirm"))
        if protect_page and not forced_mail_retry:
            print("[exp] No skip button; navigating directly to mailbox URL once")
            page.get(MAIL_URL, wait="complete", timeout=45)
            page.wait(3)
            forced_mail_retry = True
            continue

        page.wait(3)

    print("[exp] Mailbox home not reached")
    return False


def _seed_requests_cookies(session, cookies):
    loaded = 0
    for cookie in cookies or []:
        try:
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            if not name:
                continue
            kwargs = {"path": cookie.get("path") or "/"}
            domain = cookie.get("domain")
            if domain:
                kwargs["domain"] = domain
            session.cookies.set(name, value, **kwargs)
            loaded += 1
        except Exception:
            continue
    return loaded


def _oauth_state(response):
    if response is None:
        return "no-response"
    url = str(getattr(response, "url", "") or "")
    location = str(getattr(response, "headers", {}).get("Location", "") or "")
    text = str(getattr(response, "text", "") or "")
    combined = (url + " " + location).lower()
    if "localhost" in combined and "code=" in combined:
        return "authorization-code"
    if "localhost" in combined and "error=" in combined:
        return "oauth-error"
    if "consent" in combined or "appconsentprimarybutton" in text.lower():
        return "consent"
    if "proofs/add" in combined:
        return "proofs-add"
    if "ppft" in text.lower() or "login.live.com" in combined:
        return "login"
    return "other"


def _response_from_localhost(url):
    return types.SimpleNamespace(url=url, text="", status_code=200, headers={})


def _follow_redirects(session, response):
    current = response
    while getattr(current, "status_code", 0) in (301, 302, 303, 307, 308):
        location = current.headers.get("Location", "")
        if not location:
            break
        if "localhost" in location:
            return _response_from_localhost(location)
        current = session.get(location, timeout=30, allow_redirects=False)
    return current


def _extract_code(response):
    url = str(getattr(response, "url", "") or "")
    location = str(getattr(response, "headers", {}).get("Location", "") or "")
    candidate = location if "localhost" in location else url
    if "localhost" not in candidate:
        return None, None
    params = urllib.parse.parse_qs(urllib.parse.urlparse(candidate).query)
    return (params.get("code", [None])[0], params.get("error", [None])[0])


def _finish_cookie_oauth(session, response):
    """Continue from a cookie-authenticated consent/proofs page; return token metadata or None."""
    current = response
    for step in range(15):
        current = _follow_redirects(session, current)
        code, error = _extract_code(current)
        if code:
            print("[exp] Cookie OAuth obtained authorization code")
            token_response = session.post(
                "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                data={
                    "client_id": reg_factory_module.CLIENT_ID,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": reg_factory_module.REDIRECT_URI,
                    "scope": reg_factory_module.SCOPE,
                },
                timeout=30,
            )
            token_data = token_response.json()
            if token_data.get("refresh_token"):
                return {
                    "refresh_token": token_data.get("refresh_token"),
                    "client_id": reg_factory_module.CLIENT_ID,
                }
            print("[exp] Code exchange failed: {}".format(token_data.get("error", "unknown")))
            return None
        if error:
            print("[exp] Cookie OAuth returned error: {}".format(error))
            return None

        url = str(getattr(current, "url", "") or "")
        text = str(getattr(current, "text", "") or "")
        lower_url = url.lower()
        print("[exp] cookies OAuth step {}: {} state={}".format(
            step + 1, _safe_url(url), _oauth_state(current)))

        if "consent/update" in lower_url:
            server_data = re.search(r"ServerData\s*=\s*(\{.*?\});", text, re.DOTALL)
            if not server_data:
                print("[exp] Consent page missing ServerData")
                return None
            data = json.loads(server_data.group(1))
            current = session.post(
                url,
                data={
                    "ucaction": "Yes",
                    "client_id": data.get("sClientId", ""),
                    "scope": data.get("sRawInputScopes", ""),
                    "cscope": data.get("sRawInputGrantedScopes", ""),
                    "canary": data.get("sCanary", ""),
                },
                timeout=30,
                allow_redirects=False,
            )
            continue

        form = re.search(
            r'<form[^>]*action="([^"]+)"[^>]*>(.*?)</form>',
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if not form:
            print("[exp] Cookie OAuth has no submittable form; stopping")
            return None
        action = form.group(1).replace("&amp;", "&")
        body = form.group(2)
        hidden = re.findall(r'<input[^>]*name="([^"]*)"[^>]*value="([^"]*)"', body)
        form_data = {name: value for name, value in hidden}
        if "proofs/add" in lower_url:
            form_data["action"] = "Skip"
        if "consent" in action.lower() or "consent" in lower_url:
            form_data["ucaccept"] = "Yes"
        if not action.startswith("http"):
            parsed = urllib.parse.urlparse(url)
            action = "{}://{}{}".format(parsed.scheme, parsed.netloc, action)
        current = session.post(action, data=form_data, timeout=30, allow_redirects=False)

    print("[exp] Cookie OAuth exceeded maximum steps")
    return None


def _http_oauth_with_cookies(email, password, proxy, cookies):
    experiment = {"initial_state": "not-run", "initial_url": "", "token": False}
    instances = []

    class CookieSeededSession(gad.SafeRedirectSession):
        def __init__(self):
            super().__init__()
            self.trust_env = True
            loaded = _seed_requests_cookies(self, cookies)
            self.oauth_response = None
            self.oauth_cookie_count = loaded
            instances.append(self)

        def request(self, method, url, *args, **kwargs):
            response = super().request(method, url, *args, **kwargs)
            if self.oauth_response is None and "oauth2/v2.0/authorize" in str(url):
                self.oauth_response = response
                experiment["initial_state"] = _oauth_state(response)
                experiment["initial_url"] = _safe_url(getattr(response, "url", ""))
            return response

    fake_requests = gad._patched_requests_module()
    fake_requests.Session = CookieSeededSession
    original_requests = reg_factory_module.__dict__.get("requests")
    original_observe = gad._observe_log
    old_http = os.environ.get("HTTP_PROXY")
    old_https = os.environ.get("HTTPS_PROXY")

    def safe_observe(line):
        print(re.sub(r"://[^@\s]+@", "://***@", str(line)))

    try:
        gad._observe_log = safe_observe
        reg_factory_module.__dict__["requests"] = fake_requests
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        print("[exp] Starting HTTP OAuth with injected cookies (values hidden)")
        graph = get_graph_token(email, password)
        if graph and graph.get("refresh_token"):
            experiment["token"] = True
            return graph, experiment

        session = instances[-1] if instances else None
        response = getattr(session, "oauth_response", None) if session else None
        if session and response and experiment["initial_state"] in (
            "consent", "proofs-add", "authorization-code", "other"
        ):
            print("[exp] reg-factory skipped login but did not finish; continuing cookie OAuth page")
            graph = _finish_cookie_oauth(session, response)
            experiment["token"] = bool(graph and graph.get("refresh_token"))
            return graph, experiment
        return None, experiment
    finally:
        gad._observe_log = original_observe
        if original_requests is not None:
            reg_factory_module.__dict__["requests"] = original_requests
        else:
            reg_factory_module.__dict__.pop("requests", None)
        if old_http is None:
            os.environ.pop("HTTP_PROXY", None)
        else:
            os.environ["HTTP_PROXY"] = old_http
        if old_https is None:
            os.environ.pop("HTTPS_PROXY", None)
        else:
            os.environ["HTTPS_PROXY"] = old_https


def main():
    if not PENDING_FILE.is_file():
        print("[exp] Pending file not found")
        return 2
    pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    email = str(pending.get("email", "")).strip()
    password = str(pending.get("password", ""))
    saved_cookies = pending.get("outlook_cookies") or []
    proxy = _load_env_file(ENV_LOCAL).get("KOOKEY_PROXY", "").strip()
    if not email or not password or not proxy:
        print("[exp] Missing account/password or .env.local KOOKEY_PROXY")
        return 2

    print("[exp] Target account: {} (password hidden)".format(email))
    print("[exp] pending cookies: {} ?".format(len(saved_cookies)))
    print("[exp] Proxy: socks5h://***:***@gate.kookeey.info:1000")

    page = None
    mailbox_ok = False
    activated_cookies = []
    try:
        settings = Settings(proxy=proxy, headless=False, close_on_exit=False)
        page = create_page(settings)
        mailbox_ok = _activate_mailbox(page, email, password, saved_cookies)
        activated_cookies = gad._export_cookies(page)
        print("[exp] Activated cookies exported: {} (values hidden)".format(len(activated_cookies)))
    except Exception as exc:
        print("[exp] Browser stage failed: {}".format(type(exc).__name__))
    finally:
        if page is not None:
            try:
                page.quit()
            except Exception:
                pass

    graph = None
    oauth = {"initial_state": "not-run", "initial_url": "", "token": False}
    if activated_cookies:
        try:
            graph, oauth = _http_oauth_with_cookies(
                email, password, proxy, activated_cookies
            )
        except Exception as exc:
            print("[exp] HTTP OAuth stage failed: {}".format(type(exc).__name__))

    print("\n[exp] ===== RESULT =====")
    print("[exp] Mailbox entered: {}".format("yes" if mailbox_ok else "no"))
    print("[exp] Cookie OAuth initial landing: {} {}".format(
        oauth.get("initial_state"), oauth.get("initial_url")))
    skipped_login = oauth.get("initial_state") not in ("login", "not-run", "no-response")
    print("[exp] Cookies skipped login to consent/later: {}".format(
        "?" if skipped_login else "?"))
    print("[exp] Final refresh token: {} (value hidden)".format(
        "success" if graph and graph.get("refresh_token") else "failed"))
    return 0 if graph and graph.get("refresh_token") else 1


if __name__ == "__main__":
    raise SystemExit(main())
