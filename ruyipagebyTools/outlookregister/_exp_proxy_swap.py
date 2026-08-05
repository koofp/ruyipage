# -*- coding: utf-8 -*-
"""A/B proxy swap experiment for pending Outlook Graph token extraction.

This script never modifies pending records and never prints passwords or full proxy URLs.
"""

import contextlib
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests


class _RedactingWriter:
    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        safe = re.sub(r"://[^@\s]+@", "://***@", str(text))
        return self.stream.write(safe)

    def flush(self):
        return self.stream.flush()

    def reconfigure(self, *args, **kwargs):
        method = getattr(self.stream, "reconfigure", None)
        return method(*args, **kwargs) if method else None

    def __getattr__(self, name):
        return getattr(self.stream, name)


sys.stdout = _RedactingWriter(sys.stdout)
sys.stderr = _RedactingWriter(sys.stderr)

from common.kookeey_api import KookeeyAPI
import getAccountData as gad


SCRIPT_DIR = Path(__file__).resolve().parent
PENDING_DIR = SCRIPT_DIR / "_outlook_pool" / ".pending"
CHECKPOINT = SCRIPT_DIR / "_logs" / "exp_proxy_swap_results.json"
CANDIDATES = [
    "bwnhawqyavdez1",
    "bxxvzialadruh7",
    "ptkkb5aejf6t8a",
    "qvohiyiwd2ipyt",
    "qyzpnsdkwjabvr",
    "raqeshavucyyxe",
    "uwjc2qhwljtk",
    "dijzg4tandbo",
]


def _load_env(path):
    values = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        comment = value.rfind(" #")
        if comment >= 0:
            value = value[:comment].strip()
        values[key.strip()] = value.strip('"').strip("'")
    return values


def _pending_path(stem):
    matches = sorted(PENDING_DIR.glob(stem + "*_at_outlook.com.json"))
    if not matches:
        matches = sorted(PENDING_DIR.glob(stem + "*.json"))
    return matches[0] if matches else None


def _proxy_session(proxy):
    try:
        password = urllib.parse.urlsplit(str(proxy)).password or ""
        session = password.rsplit("-", 1)[-1]
        return session[-6:] if session else "??????"
    except Exception:
        return "??????"


def _probe_exit(proxy):
    for _ in range(2):
        try:
            response = requests.get(
                "https://api.ipify.org?format=json",
                proxies={"http": proxy, "https": proxy},
                timeout=20,
            )
            response.raise_for_status()
            ip = str(response.json().get("ip", "")).strip()
            if ip:
                return ip
        except Exception:
            time.sleep(1)
    return ""


def _exit_fingerprint(ip):
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:8] if ip else "unhealthy"


def _fresh_distinct_pair(api, country):
    last = None
    for generation in range(1, 4):
        proxies = api.generate_extraction_proxies(
            count=2,
            country_code=country,
            sticky=False,
            protocol="socks5h",
        )
        if len(proxies) < 2:
            continue
        proxy_a, proxy_b = proxies[:2]
        ip_a = _probe_exit(proxy_a)
        ip_b = _probe_exit(proxy_b)
        last = (proxy_a, proxy_b, ip_a, ip_b)
        if ip_a and ip_b and ip_a != ip_b:
            return last
        print("[exp] pair generation {} not distinct/healthy; regenerating".format(generation))
    return last


def _round_result(graph, classification):
    if graph and graph.get("refresh_token"):
        return "success"
    denied = int(classification.get("denied_count", 0) or 0)
    net = int(classification.get("net_streak", 0) or 0)
    ctype = str(classification.get("type") or "")
    if ctype == "abuse":
        return "abuse"
    if denied:
        return "denied({})".format(denied)
    if ctype == "dead-line" or net:
        return "net-error({})".format(net)
    if ctype == "retryable":
        return "none/retryable"
    return ctype or "none"


def _run_round(email, password, proxy):
    captured = []
    original_observe = gad._observe_log

    def observe(line):
        safe = re.sub(r"://[^@\s]+@", "://***@", str(line))
        if "attempt " in safe and ("result:" in safe or " error:" in safe):
            captured.append(safe[-240:])
        elif "terminal:" in safe:
            captured.append(safe[-240:])

    try:
        gad._observe_log = observe
        hidden_stdout = io.StringIO()
        with contextlib.redirect_stdout(hidden_stdout), contextlib.redirect_stderr(hidden_stdout):
            graph = gad._extract_graph_via_http(email, password, proxy=proxy)
        classification = dict(gad.get_last_classification() or {})
        result = _round_result(graph, classification)
        return {
            "result": result,
            "success": bool(graph and graph.get("refresh_token")),
            "classification": classification,
            "trace": captured[-4:],
        }
    except Exception as exc:
        return {
            "result": "exception:{}".format(type(exc).__name__),
            "success": False,
            "classification": dict(gad.get_last_classification() or {}),
            "trace": captured[-4:],
        }
    finally:
        gad._observe_log = original_observe


def _save_checkpoint(rows):
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now().astimezone().isoformat(),
        "rows": rows,
    }
    CHECKPOINT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_checkpoint():
    if not CHECKPOINT.is_file():
        return []
    try:
        data = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        return list(data.get("rows") or [])
    except Exception:
        return []


def _print_table(rows):
    print("\naccount          | A result          | B result          | swap effective")
    print("-----------------+-------------------+-------------------+---------------")
    for row in rows:
        print("{:<16} | {:<17} | {:<17} | {}".format(
            row["account"], row["round_a"]["result"], row["round_b"]["result"],
            "YES" if row["swap_effective"] else "no",
        ))


def main():
    env = _load_env(SCRIPT_DIR / ".env")
    access_id = env.get("KOOKEY_ACCESS_ID", "")
    token = env.get("KOOKEY_TOKEN", "")
    country = env.get("AUTO_COUNTRY", "JP").strip().upper() or "JP"
    if not access_id or not token:
        print("[exp] Missing KOOKEY_ACCESS_ID/KOOKEY_TOKEN in local .env")
        return 2

    api = KookeeyAPI(access_id, token)
    rows = _load_checkpoint()
    completed = {row.get("account") for row in rows}

    for stem in CANDIDATES:
        if stem in completed:
            print("[exp] resume: {} already completed".format(stem))
            continue
        path = _pending_path(stem)
        if path is None:
            print("[exp] skip {}: pending file missing".format(stem))
            continue
        pending = json.loads(path.read_text(encoding="utf-8"))
        if pending.get("_terminal") is True:
            print("[exp] skip {}: terminal=true".format(stem))
            continue
        email = str(pending.get("email", "")).strip()
        password = str(pending.get("password", ""))
        if not email or not password:
            print("[exp] skip {}: missing credentials".format(stem))
            continue

        pair = _fresh_distinct_pair(api, country)
        if not pair:
            print("[exp] abort {}: no proxy pair".format(stem))
            continue
        proxy_a, proxy_b, ip_a, ip_b = pair
        print("\n[exp] {} A=session:{} exit:{} B=session:{} exit:{}".format(
            stem, _proxy_session(proxy_a), _exit_fingerprint(ip_a),
            _proxy_session(proxy_b), _exit_fingerprint(ip_b),
        ))

        round_a = _run_round(email, password, proxy_a)
        print("[exp] {} round A => {} classification={}".format(
            stem, round_a["result"], round_a["classification"]))
        time.sleep(4)
        round_b = _run_round(email, password, proxy_b)
        print("[exp] {} round B => {} classification={}".format(
            stem, round_b["result"], round_b["classification"]))

        a_network_or_none = (
            round_a["result"].startswith("net-error")
            or round_a["result"] == "none/retryable"
        )
        row = {
            "account": stem,
            "baseline_classification": pending.get("_classification") or {},
            "proxy_a": {
                "session": _proxy_session(proxy_a),
                "exit_fingerprint": _exit_fingerprint(ip_a),
            },
            "proxy_b": {
                "session": _proxy_session(proxy_b),
                "exit_fingerprint": _exit_fingerprint(ip_b),
            },
            "round_a": round_a,
            "round_b": round_b,
            "swap_effective": bool(a_network_or_none and round_b["success"]),
        }
        rows.append(row)
        _save_checkpoint(rows)
        time.sleep(3)

    _print_table(rows)
    total = len(rows)
    success_a = sum(1 for r in rows if r["round_a"]["success"])
    success_b = sum(1 for r in rows if r["round_b"]["success"])
    rescued = sum(1 for r in rows if r["swap_effective"])
    denied_both = sum(
        1 for r in rows
        if r["round_a"]["result"].startswith("denied")
        and r["round_b"]["result"].startswith("denied")
    )
    uplift = ((success_b - success_a) * 100.0 / total) if total else 0.0
    print("\n[exp] total={} A_success={} B_success={} network_fail_to_B_success={}".format(
        total, success_a, success_b, rescued))
    print("[exp] denied_both={} B-vs-A success uplift={:+.1f} percentage points".format(
        denied_both, uplift))
    print("[exp] checkpoint={}".format(CHECKPOINT.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
