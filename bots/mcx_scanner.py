"""
MCX Momentum Scanner — ranks front-month MCX futures by rule-based momentum
(15m + 5m closed candles). Throttled to stay under Angel One rate limits.

Usage:
  python bots/mcx_scanner.py
  python bots/mcx_scanner.py --symbols CRUDEOIL SILVERM NATURALGAS
"""
import argparse
import contextlib
import io
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.angel import connect, get_ltp
from core.candles import get_candles, momentum

DEFAULT_SYMBOLS = ["CRUDEOIL", "NATURALGAS", "GOLDM", "SILVERM", "COPPER", "ZINC"]
CALL_GAP = 0.6   # seconds between API calls (candle API blocks ~3 calls in 200ms)
ROLL_DAYS = 3


def throttled(fn, *args, **kwargs):
    for attempt in range(4):
        try:
            result = fn(*args, **kwargs)
            time.sleep(CALL_GAP)
            return result
        except Exception as e:
            if "access rate" in str(e).lower():
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise RuntimeError("rate limited after retries")


def front_future(angel, name):
    with contextlib.redirect_stdout(io.StringIO()):
        res = throttled(angel.searchScrip, exchange="MCX", searchscrip=name)
    futs = []
    for c in res.get("data") or []:
        m = re.fullmatch(name + r"(\d{2}[A-Z]{3}\d{2})FUT", c["tradingsymbol"])
        if m:
            d = datetime.strptime(m.group(1), "%d%b%y")
            if (d - datetime.now()).days > ROLL_DAYS:
                futs.append((d, c["tradingsymbol"], c["symboltoken"]))
    return sorted(futs)[0] if futs else None


def scan(symbols):
    with contextlib.redirect_stdout(io.StringIO()):
        angel, _ = connect()
    rows = []
    for name in symbols:
        try:
            f = front_future(angel, name)
            if not f:
                print(f"{name:<12} no contract found"); continue
            _, sym, tok = f
            ltp = throttled(get_ltp, angel, "MCX", sym, tok)
            c15 = throttled(get_candles, angel, "MCX", tok, "FIFTEEN_MINUTE", 900)
            c5 = throttled(get_candles, angel, "MCX", tok, "FIVE_MINUTE", 300)
            m15, m5 = momentum(c15), momentum(c5)
            today = [c for c in c15 if c["ts"].date() == datetime.now().date()]
            day_open = today[0]["open"] if today else ltp
            rows.append({
                "sym": sym, "tok": tok, "ltp": ltp,
                "chg": (ltp - day_open) / day_open * 100,
                "dl": min(c["low"] for c in today) if today else None,
                "dh": max(c["high"] for c in today) if today else None,
                "m15": m15, "m5": m5, "c5": c5,
                "aligned": (m15.get("score", 0) * m5.get("score", 0)) > 0,
                "strength": m15.get("score", 0) + m5.get("score", 0),
            })
        except Exception as e:
            print(f"{name:<12} ERR {e}")

    rows.sort(key=lambda r: (not r["aligned"], -abs(r["strength"])))
    print(f"\nMCX MOMENTUM SCAN — {datetime.now():%d %b %Y %H:%M:%S}\n")
    print(f"{'CONTRACT':<22} {'LTP':>11} {'DAY':>7}  {'15m':<16} {'5m':<16} SIGNAL")
    for r in rows:
        sig = ("ALIGNED " + ("SHORT" if r["strength"] < 0 else "LONG")) if r["aligned"] else "mixed — skip"
        print(f"{r['sym']:<22} {r['ltp']:>11} {r['chg']:>+6.2f}%  "
              f"{r['m15']['verdict']:<16} {r['m5']['verdict']:<16} {sig}")
    print()
    for r in rows:
        if not r["aligned"]:
            continue
        print(f"■ {r['sym']}  (token {r['tok']})  day range {r['dl']} – {r['dh']}")
        print("   15m: " + " | ".join(r["m15"]["reasons"]))
        print("   5m : " + " | ".join(r["m5"]["reasons"]))
        last = [(c["ts"].strftime("%H:%M"), c["high"], c["low"], c["close"], c["volume"]) for c in r["c5"][-4:]]
        print(f"   last 5m (time, H, L, C, vol): {last}\n")
    if not any(r["aligned"] for r in rows):
        print("No aligned setups — 15m and 5m disagree everywhere. Best trade is no trade.")
    return rows


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="MCX momentum scanner")
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    scan(p.parse_args().symbols)
