# -*- coding: utf-8 -*-
"""Experiment: OAuth session cookies -> HTTP OAuth token (skip login/proofs)."""

import json
import re
import sys
import time
import types
import urllib.parse
from pathlib import Path


class _RedactingWriter(object):
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

from extract_graph_tokens import reg_factory_module  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
PENDING_DIR = SCRIPT_DIR / "_outlook_pool" / ".pending"
ENV_LOCAL = SCRIPT_DIR / ".env.local"
CLIENT_ID = reg_factory_module.CLIENT_ID
REDIRECT_URI = reg_factory_module.REDIRECT_URI
SCOPE = reg_factory_module.SCOPE
AUTH_URL = (
    "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
    "?client_id={}&response_type=code"
    "&redirect_uri={}&scope={}&response_mode=query"
).format(
    CLIENT_ID,
    urllib.parse.quote(REDIRECT_URI, safe=""),
    urllib.parse.quote(SCOPE, safe=""),
)


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


def _read_pending(email_slug):
    path = PENDING_DIR / "{}.json".format(email_slug)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_url(url):
    try:
        parsed = urllib.parse.urlsplit(str(url or ""))
        return "{}://{}{}".format(parsed.scheme, parsed.netloc, parsed.path)
    except Exception:
        return "(unknown-url)"


def _oauth_state(url, text=""):
    url = str(url or "").lower()
    text = str(text or "").lower()
    combined = url + " " + text
    if "localhost" in combined and "code=" in combined:
        return "authorization-code"
    if "localhost" in combined and "error=" in combined:
        return "oauth-error"
    if "consent" in combined or "appconsentprimarybutton" in text:
        return "consent"
    if "proofs/add" in combined:
        return "proofs-add"
    if "ppft" in text or "login.live.com" in url:
        return "login"
    return "other"


def _probe_proxy(proxy):
    import requests

    try:
        r = requests.get(
            "https://api.ipify.org?format=json",
            proxies={"http": proxy, "https": proxy},
            timeout=10,
        )
        r.raise_for_status()
        return bool(r.json().get("ip"))
    except Exception:
        return False


def main():
    email_slug = sys.argv[1] if len(sys.argv) > 1 else "uwjc2qhwljtk_at_outlook.com"
    pending = _read_pending(email_slug)
    if not pending:
        print("[exp] no pending record for {}".format(email_slug))
        return 1
    email = pending.get("email", "")
    password = pending.get("password", "")
    saved_cookies = pending.get("outlook_cookies", [])
    env = _load_env_file(ENV_LOCAL)
    proxy = env.get("KOOKEY_PROXY", "")

    print("[exp] email={} saved_cookies={} proxy_set={} (password/token hidden)".format(
        email, len(saved_cookies), bool(proxy)))

    if proxy and not _probe_proxy(proxy):
        print("[exp] fallback proxy dead; exit")
        return 1

    # Phase 1: walk authorize in browser, capture OAuth session cookies.
    from config import Settings, create_page

    settings = Settings(proxy=proxy or "http://127.0.0.1:7897")
    page = create_page(settings)
    landed_state = None
    oauth_cookies = []
    try:
        if saved_cookies:
            try:
                page.set_cookies(saved_cookies)
                print("[exp] injected {} saved cookies".format(len(saved_cookies)))
            except Exception:
                print("[exp] saved cookie injection failed; continuing")
        page.get(AUTH_URL, wait="none", timeout=30)
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                url = page.url or ""
            except Exception:
                url = ""
            state = _oauth_state(url, "")
            if state not in ("other", "") and state != landed_state:
                print("[exp] browser authorize landed: {}".format(state))
                landed_state = state
            if state == "consent":
                try:
                    oauth_cookies = page.get_cookies(all_info=True)
                except Exception as exc:
                    print("[exp] consent cookie export failed: {}".format(type(exc).__name__))
                print("[exp] CONSENT reached; exported {} oauth cookies".format(len(oauth_cookies)))
                break
            if state in ("authorization-code", "oauth-error"):
                print("[exp] browser authorize ended: {}".format(state))
                break
            if state == "proofs-add":
                try:
                    skip = page.ele("#iShowSkip", timeout=1)
                    if skip:
                        skip.click_self()
                        page.wait(2)
                        print("[exp] proofs skip clicked")
                        continue
                except Exception:
                    pass
                try:
                    oauth_cookies = page.get_cookies(all_info=True)
                except Exception:
                    pass
                print("[exp] proofs/Add (no skip) exported {} cookies anyway".format(
                    len(oauth_cookies)))
                break
            page.wait(1)
        if not oauth_cookies and landed_state != "consent":
            try:
                oauth_cookies = page.get_cookies(all_info=True)
            except Exception:
                pass
    finally:
        try:
            page.quit()
        except Exception:
            pass

    print("[exp] phase1 done: landed_state={} oauth_cookies={}".format(
        landed_state, len(oauth_cookies)))

    if not oauth_cookies:
        print("[exp] no OAuth cookies to test; done")
        return 1

    # Phase 2: feed OAuth cookies into pure HTTP OAuth.
    import requests

    session = requests.Session()
    session.trust_env = True
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    loaded = 0
    for cookie in oauth_cookies:
        try:
            if isinstance(cookie, dict):
                name = cookie.get("name", "")
                value = cookie.get("value", "")
                path = cookie.get("path") or "/"
                domain = cookie.get("domain")
            else:
                name = getattr(cookie, "name", "") or ""
                value = getattr(cookie, "value", "") or ""
                path = getattr(cookie, "path", "/") or "/"
                domain = getattr(cookie, "domain", None)
            if not name:
                continue
            kwargs = {"path": path}
            if domain:
                kwargs["domain"] = domain
            session.cookies.set(name, value, **kwargs)
            loaded += 1
        except Exception:
            continue
    print("[exp] seeded {} oauth cookies into requests session".format(loaded))

    response = session.get(AUTH_URL, timeout=30, allow_redirects=False)
    state = _oauth_state(response.url, response.text)
    print("[exp] HTTP authorize (cookies) landed: {} (url={})".format(
        state, _safe_url(response.url)))

    current = response
    final = None
    for step in range(15):
        while getattr(current, "status_code", 0) in (301, 302, 303, 307, 308):
            location = current.headers.get("Location", "")
            if "localhost" in location:
                current = types.SimpleNamespace(url=location, text="", status_code=200, headers={})
                break
            current = session.get(location, timeout=30, allow_redirects=False)
        url = str(getattr(current, "url", "") or "")
        text = str(getattr(current, "text", "") or "")
        st = _oauth_state(url, text)
        print("[exp] HTTP OAuth step {}: state={} url={}".format(
            step + 1, st, _safe_url(url)))

        if "localhost" in url.lower() and "code=" in url.lower():
            params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            code = params.get("code", [None])[0]
            print("[exp] got authorization code")
            token_resp = session.post(
                "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                data={
                    "client_id": CLIENT_ID,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                    "scope": SCOPE,
                },
                timeout=30,
            )
            token_data = token_resp.json()
            if token_data.get("refresh_token"):
                final = "success"
                print("[exp] TOKEN SUCCESS")
            else:
                final = "token-error"
                print("[exp] token exchange error: {}".format(
                    token_data.get("error_description", token_data.get("error", "?"))[:150]))
            break
        if "localhost" in url.lower() and "error=" in url.lower():
            params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            final = "oauth-error:" + str(params.get("error", [""])[0])
            print("[exp] oauth error: {}".format(final))
            break
        if "consent/update" in url.lower():
            server_data = re.search(r"ServerData\s*=\s*(\{.*?\});", text, re.DOTALL)
            if not server_data:
                final = "consent-no-serverdata"
                print("[exp] consent page missing ServerData")
                break
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
        if "proofs/add" in url.lower():
            form = re.search(
                r"<form[^>]*action=\"([^\"]+)\"[^>]*>(.*?)</form>",
                text,
                re.DOTALL | re.IGNORECASE,
            )
            if form:
                form_action = form.group(1).replace("&amp;", "&")
                form_body = form.group(2)
                hidden = re.findall(r"<input[^>]*name=\"([^\"]*)\"[^>]*value=\"([^\"]*)\"", form_body)
                form_data = {n: v for n, v in hidden}
                form_data["action"] = "Skip"
                if not form_action.startswith("http"):
                    base = urllib.parse.urlparse(url)
                    form_action = "{}://{}{}".format(base.scheme, base.netloc, form_action)
                current = session.post(form_action, data=form_data, timeout=30, allow_redirects=False)
                continue
            final = "proofs-no-form"
            print("[exp] proofs/Add with no form (stuck)")
            break
        form = re.search(
            r"<form[^>]*action=\"([^\"]+)\"[^>]*>(.*?)</form>",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if form:
            form_action = form.group(1).replace("&amp;", "&")
            form_body = form.group(2)
            hidden = re.findall(r"<input[^>]*name=\"([^\"]*)\"[^>]*value=\"([^\"]*)\"", form_body)
            form_data = {n: v for n, v in hidden}
            if not form_action.startswith("http"):
                base = urllib.parse.urlparse(url)
                form_action = "{}://{}{}".format(base.scheme, base.netloc, form_action)
            current = session.post(form_action, data=form_data, timeout=30, allow_redirects=False)
            continue
        final = "stuck:" + st
        break

    print("[exp] FINAL: {}".format(final))
    return 0 if final == "success" else 2


if __name__ == "__main__":
    sys.exit(main())
