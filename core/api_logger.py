"""
API call logger — records every outbound API call so rate limits can be measured.

Each call is appended as one JSON line to logs/api_calls/YYYY-MM-DD.jsonl:
  {"ts": ..., "service": "angel", "endpoint": "/rest/.../getLtpData",
   "ok": true, "http": 200, "ms": 143, "err": "", "pid": 1234, "script": "crude_exit_alert.py"}

Coverage:
  - Everything that goes through `requests` (Angel One SmartAPI, Yahoo Finance, AMFI)
    is captured automatically once this module is imported (core/__init__.py does that).
  - Gemini (google-genai uses httpx) is logged explicitly via log_call() in core/analysis.py.

Only the URL path is logged — never query strings, headers, or bodies (no secrets).

Summary:
  python api_usage.py              # today
  python api_usage.py 2026-11-16   # a specific day
"""
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import urlparse

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "api_calls")

_SERVICES = {
    "angelbroking.com": "angel",
    "angelone.in": "angel",
    "finance.yahoo.com": "yahoo",
    "amfiindia.com": "amfi",
    "googleapis.com": "gemini",
    "ipify.org": "ipify",  # SmartApi looks up public IP on every login
}

_RATE_LIMIT_HINTS = ("exceeding access rate", "rate limit", "too many requests", "quota", "ab1004")


def _service_for(host):
    for suffix, name in _SERVICES.items():
        if host.endswith(suffix):
            return name
    return host or "unknown"


def log_call(service, endpoint, ok, ms, http=None, err=""):
    """Append one API call record. Never raises."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        rec = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "service": service,
            "endpoint": endpoint,
            "ok": bool(ok),
            "http": http,
            "ms": int(ms),
            "err": (err or "")[:160],
            "pid": os.getpid(),
            "script": os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else "",
        }
        path = os.path.join(LOG_DIR, datetime.now().strftime("%Y-%m-%d") + ".jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def _inspect_response(resp):
    """Return (ok, err) — Angel returns HTTP 200 with status=false on logical errors."""
    ok = resp.status_code < 400
    err = "" if ok else f"HTTP {resp.status_code}"
    try:
        if "json" in resp.headers.get("Content-Type", ""):
            body = resp.json()
            # Angel uses both shapes: {"status": false, "errorcode"} and {"success": false, "errorCode"}
            if isinstance(body, dict) and (body.get("status") is False or body.get("success") is False):
                ok = False
                code = body.get("errorcode") or body.get("errorCode") or ""
                err = f"{code} {body.get('message', '')}".strip()
    except Exception:
        pass
    if not ok and (not err or err.startswith("HTTP ")):
        body = (resp.text or "").strip()[:140]
        err = f"{err} {body}".strip()
    return ok, err


def _install_requests_hook():
    try:
        import requests
    except ImportError:
        return
    Session = requests.sessions.Session
    if getattr(Session.request, "_api_logged", False):
        return
    original = Session.request

    def logged_request(self, method, url, *args, **kwargs):
        parsed = urlparse(url)
        service = _service_for(parsed.hostname or "")
        start = time.perf_counter()
        try:
            resp = original(self, method, url, *args, **kwargs)
        except Exception as e:
            log_call(service, parsed.path, False, (time.perf_counter() - start) * 1000, err=type(e).__name__ + ": " + str(e))
            raise
        ok, err = _inspect_response(resp)
        log_call(service, parsed.path, ok, (time.perf_counter() - start) * 1000, http=resp.status_code, err=err)
        return resp

    logged_request._api_logged = True
    Session.request = logged_request


_install_requests_hook()


# ── Summary ───────────────────────────────────────────────────────────────────

def summarize(day=None):
    day = day or datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(LOG_DIR, day + ".jsonl")
    if not os.path.exists(path):
        print(f"No API calls logged for {day} ({path})")
        return
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                recs.append(json.loads(line))
            except Exception:
                pass

    print(f"API CALLS — {day}   ({len(recs)} total)\n")
    by_service = defaultdict(list)
    for r in recs:
        by_service[r["service"]].append(r)

    for service, rows in sorted(by_service.items()):
        errors = [r for r in rows if not r["ok"]]
        rate_hits = [r for r in errors if any(h in r["err"].lower() for h in _RATE_LIMIT_HINTS)]
        per_sec = Counter(r["ts"][:19] for r in rows)
        per_min = Counter(r["ts"][:16] for r in rows)
        avg_ms = sum(r["ms"] for r in rows) / len(rows)
        peak_s, peak_s_n = per_sec.most_common(1)[0]
        peak_m, peak_m_n = per_min.most_common(1)[0]
        print(f"■ {service.upper()}  calls={len(rows)}  errors={len(errors)}  rate-limit hits={len(rate_hits)}  avg={avg_ms:.0f}ms")
        print(f"    peak/sec : {peak_s_n}  at {peak_s[11:]}")
        print(f"    peak/min : {peak_m_n}  at {peak_m[11:]}")
        for ep, n in Counter(r["endpoint"].rsplit("/", 1)[-1] or r["endpoint"] for r in rows).most_common(8):
            print(f"    {ep:<28} {n}")
        for script, n in Counter(r.get("script", "") for r in rows).most_common(5):
            print(f"    by {script or '(interactive)':<25} {n}")
        for r in errors[-5:]:
            print(f"    ✗ {r['ts'][11:19]} {r['endpoint'].rsplit('/', 1)[-1]}: {r['err']}")
        print()


if __name__ == "__main__":
    summarize(sys.argv[1] if len(sys.argv) > 1 else None)
