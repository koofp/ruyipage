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


def _make_proxy_provider():
    """Return a fresh-proxy callable and its source label.

    Kookeey API creation is deferred until after pending files are discovered;
    importing this script therefore remains safe when no credentials are set.
    """
    access_id = os.environ.get("KOOKEY_ACCESS_ID", "").strip()
    token = os.environ.get("KOOKEY_TOKEN", "").strip()
    country = os.environ.get("AUTO_COUNTRY", "JP").strip().upper()
    fallback = os.environ.get("CLASH_PROXY", DEFAULT_PROXY).strip() or DEFAULT_PROXY

    api = None
    if access_id and token:
        try:
            from common.kookeey_api import KookeeyAPI

            api = KookeeyAPI(access_id, token)
        except Exception as exc:
            print("[revive] Kookeey unavailable: {}: {}".format(type(exc).__name__, exc))

    def fresh_proxy():
        if api is not None:
            try:
                generated = api.generate_extraction_proxies(
                    count=1,
                    country_code=country,
                    sticky=True,
                    protocol="http",
                )
                if generated:
                    return generated[0], "kookeey"
            except Exception as exc:
                print("[revive] Kookeey proxy generation failed: {}: {}".format(
                    type(exc).__name__, exc
                ))
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

        if _finish_existing_pending(path, email, password):
            return "recovered-existing"

        proxy, proxy_source = fresh_proxy()
        print("[revive] HTTP attempt {}/{}: {} via {}".format(
            attempts + 1, MAX_ATTEMPTS, email, proxy_source
        ))
        graph = _extract_graph_via_http(email, password, proxy=proxy)
        if not graph or not graph.get("refresh_token"):
            raise RuntimeError("HTTP extractor returned no refresh_token")

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
    counts = {"success": 0, "failed": 0, "exhausted": 0, "recovered-existing": 0}
    for path in paths:
        outcome = _revive_one(path, fresh_proxy)
        counts[outcome] = counts.get(outcome, 0) + 1

    print("[revive] summary: {}".format(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
