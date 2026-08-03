"""Revive pending Outlook accounts through the pure-HTTP Graph extractor.

This script intentionally does not start a browser. It retries each pending
account at most three times, using a fresh Kookeey sticky extraction proxy when
available and the configured Clash proxy as a fallback.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
POOL_DIR = SCRIPT_DIR / "_outlook_pool"
PENDING_DIR = POOL_DIR / ".pending"
EMAILS_FILE = SCRIPT_DIR / "emails.txt"
PROXY_FILE = SCRIPT_DIR / "proxies_ok.txt"  # 本地代理文件 fallback（同 run_batch）
DEFAULT_PROXY = "http://127.0.0.1:7897"
MAX_ATTEMPTS = 3

# Keep imports local to this script's repository layout. These helpers already
# implement the reg-factory loader, proxy environment handling, atomic writes,
# and email deduplication used by the registration flow.
from getAccountData import (  # noqa: E402
    _append_dedup_txt,
    _extract_graph_via_http,
    _safe_filename,
    _write_json_atomic,
    get_last_classification,
)


def _load_env(path: Path) -> None:
    """Load simple KEY=value entries without adding a dotenv dependency."""
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            hash_pos = value.rfind(" #")
            if hash_pos >= 0:
                value = value[:hash_pos].strip()
            os.environ.setdefault(key, value.strip('"').strip("'"))


def _load_local_proxies():
    """读 proxies_ok.txt 的本地代理列表（PROXY_MODEL=false 时 run_batch 用同一个）。

    用于 revive 的代理 fallback：Kookeey API 失败/不稳时，优先用本地代理，
    再退到 Clash 直连。空文件/不存在返回 []。
    """
    proxies = []
    if not PROXY_FILE.is_file():
        return proxies
    try:
        with PROXY_FILE.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    proxies.append(line)
    except OSError:
        pass
    return proxies


def _make_proxy_provider():
    """Return a fresh-proxy callable and its source label.

    优先级：Kookeey 提取代理 > 本地 proxies_ok.txt（轮转） > Clash 直连。
    Kookeey API creation is deferred until after pending files are discovered;
    importing this script therefore remains safe when no credentials are set.
    本地代理 fallback 绕开 Kookeey 站点不稳/SSL 失败（W4）。
    """
    access_id = os.environ.get("KOOKEY_ACCESS_ID", "").strip()
    token = os.environ.get("KOOKEY_TOKEN", "").strip()
    country = os.environ.get("AUTO_COUNTRY", "JP").strip().upper()
    fallback = os.environ.get("CLASH_PROXY", DEFAULT_PROXY).strip() or DEFAULT_PROXY
    local_proxies = _load_local_proxies()

    api = None
    if access_id and token:
        try:
            from common.kookeey_api import KookeeyAPI

            api = KookeeyAPI(access_id, token)
        except Exception as exc:
            print("[revive] Kookeey unavailable: {}: {}".format(type(exc).__name__, exc))

    # 本地代理轮转游标（只在 fallback 时用，非线程安全；revive 是串行）
    _local_idx = [0]

    def fresh_proxy():
        if api is not None:
            try:
                generated = api.generate_extraction_proxies(
                    count=1,
                    country_code=country,
                    sticky=True,
                    protocol="socks5h",
                )
                if generated:
                    return generated[0], "kookeey"
            except Exception as exc:
                print("[revive] Kookeey proxy generation failed: {}: {}".format(
                    type(exc).__name__, exc
                ))
        # fallback 1：本地 proxies_ok.txt（若有）
        if local_proxies:
            p = local_proxies[_local_idx[0] % len(local_proxies)]
            _local_idx[0] += 1
            return p, "local-file"
        # fallback 2：Clash 直连
        return fallback, "clash-fallback"

    return fresh_proxy


def _read_json(path: Path):
    with path.open(encoding="utf-8") as record_file:
        return json.load(record_file)


def _find_existing_success(email: str):
    """Find an already-written pool record for idempotent reruns."""
    if not POOL_DIR.is_dir():
        return None
    for candidate in POOL_DIR.glob("*.json"):
        try:
            record = _read_json(candidate)
        except (OSError, ValueError):
            continue
        if record.get("email", "").strip().lower() == email.strip().lower() and record.get(
            "refresh_token"
        ):
            return candidate, record
    return None


def _finish_existing_pending(pending_path: Path, email: str, password: str) -> bool:
    """Complete a prior partial success without creating a duplicate record."""
    existing = _find_existing_success(email)
    if not existing:
        return False
    _, record = existing
    line = "{}----{}----{}----{}".format(
        email,
        password,
        record.get("refresh_token", ""),
        record.get("client_id", ""),
    )
    _append_dedup_txt(str(EMAILS_FILE), line)
    pending_path.unlink(missing_ok=True)
    print("[revive] {} already in pool; cleaned pending record".format(email))
    return True


def _mark_failure(path: Path, record: dict, method: str, error: str) -> None:
    attempts = int(record.get("_revive_attempts", 0) or 0) + 1
    now = datetime.now(timezone.utc).astimezone().isoformat()
    updated = dict(record)
    updated["_revive_attempts"] = attempts
    updated["_last_revive_at"] = now
    updated["_last_revive_method"] = method
    updated["_last_revive_error"] = error[:1000]
    _write_json_atomic(str(path), updated)


def _revive_one(path: Path, fresh_proxy) -> str:
    try:
        pending = _read_json(path)
        email = str(pending.get("email", "")).strip()
        password = str(pending.get("password", ""))
        if not email or not password:
            raise ValueError("pending record missing email or password")

        attempts = int(pending.get("_revive_attempts", 0) or 0)
        if attempts >= MAX_ATTEMPTS:
            print("[revive] {} exhausted ({}/{})".format(email, attempts, MAX_ATTEMPTS))
            return "exhausted"

        # 方案A 终态止损：若上次已判定 terminal（denied×3 或 abuse），
        # 微软账号态决定的不可救失败，跳过不再重试，省代理/时间。
        if pending.get("_terminal"):
            ctype = (pending.get("_classification") or {}).get("type", "?")
            print("[revive] {} SKIP: terminal={}（微软账号态，不再重试）".format(email, ctype))
            return "terminal-skip"

        if _finish_existing_pending(path, email, password):
            return "recovered-existing"

        proxy, proxy_source = fresh_proxy()
        print("[revive] HTTP attempt {}/{}: {} via {}".format(
            attempts + 1, MAX_ATTEMPTS, email, proxy_source
        ))
        graph = _extract_graph_via_http(email, password, proxy=proxy)
        if not graph or not graph.get("refresh_token"):
            # 读终态分类（方案A）：terminal 的不再计 attempts（下次会 terminal-skip）
            classification = get_last_classification() or {}
            terminal = classification.get("terminal", False)
            raise RuntimeError(
                "HTTP extractor returned no refresh_token"
                + (" (terminal:{})".format(classification.get("type")) if terminal else "")
            )

        now = datetime.now(timezone.utc).astimezone()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        destination = POOL_DIR / "{}_{}.json".format(timestamp, _safe_filename(email))
        if destination.exists():
            destination = POOL_DIR / "{}_{}_{}.json".format(
                timestamp, now.strftime("%f"), _safe_filename(email)
            )
        revived = dict(pending)
        revived.update({
            "email": email,
            "password": password,
            "refresh_token": graph.get("refresh_token", ""),
            "client_id": graph.get("client_id", ""),
            "graph": graph,
            "outlook_cookies": pending.get("outlook_cookies", []),
            "source": "ruyipage-revive",
            "registration_proxy_strategy": pending.get(
                "registration_proxy_strategy", ""
            ),
            "ts": pending.get("ts", now.isoformat()),
            "_revived_at": now.isoformat(),
            "_revive_method": "HTTP",
            "_revive_proxy": proxy,
        })
        _write_json_atomic(str(destination), revived)
        line = "{}----{}----{}----{}".format(
            email, password, revived["refresh_token"], revived["client_id"]
        )
        _append_dedup_txt(str(EMAILS_FILE), line)
        path.unlink(missing_ok=True)
        print("[revive] SUCCESS: {} -> {}".format(email, destination.name))
        return "success"
    except Exception as exc:
        try:
            record = locals().get("pending") or _read_json(path)
            # 方案A：terminal 的不增 _revive_attempts（下次直接 terminal-skip）
            classification = get_last_classification() or {}
            terminal = classification.get("terminal", False)
            if terminal:
                record["_terminal"] = True
                record["_classification"] = classification
                record["_no_token_reason"] = "terminal: {} (微软账号态，不可重试)".format(
                    classification.get("type"))
                _write_json_atomic(str(path), record)
                print("[revive] FAILED(terminal) {}: {} [已标记不再重试]".format(
                    path.name, exc))
                return "terminal"
            _mark_failure(path, record, "HTTP", "{}: {}".format(type(exc).__name__, exc))
        except Exception as mark_exc:
            print("[revive] failed to update {}: {}".format(path.name, mark_exc))
        print("[revive] FAILED {}: {}: {}".format(path.name, type(exc).__name__, exc))
        return "failed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Revive pending Outlook Graph tokens")
    parser.add_argument("--limit", type=int, default=None, help="process at most N pending records")
    args = parser.parse_args()

    _load_env(SCRIPT_DIR / ".env")
    paths = sorted(PENDING_DIR.glob("*.json"))
    if args.limit is not None:
        if args.limit < 0:
            parser.error("--limit must be non-negative")
        paths = paths[:args.limit]
    if not paths:
        print("[revive] no pending records")
        return 0

    fresh_proxy = _make_proxy_provider()
    counts = {
        "success": 0, "failed": 0, "exhausted": 0,
        "recovered-existing": 0, "terminal-skip": 0, "terminal": 0,
    }
    for path in paths:
        outcome = _revive_one(path, fresh_proxy)
        counts[outcome] = counts.get(outcome, 0) + 1

    print("[revive] summary: {}".format(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
