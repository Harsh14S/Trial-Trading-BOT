"""
Day Guard: live daily risk limits, computed from today's Angel trade book (all instruments).

    python bots/day_guard.py                     # status (same as `status`)
    python bots/day_guard.py lock "called it a day"
    python bots/day_guard.py unlock              # discouraged; asks you to type a reason

LOCKED when any of these is true:
  - closed trades today  >= MAX_TRADES
  - losing trades today  >= MAX_LOSSES
  - net P&L today        <= -MAX_DAY_LOSS (estimated charges)
  - the day was called manually (`lock`; /eod does this automatically)
PROTECT (warning only) when net P&L >= PROFIT_PROTECT: the day is green, so only A+ setups.

The lock file is journal/day_lock.json and only applies to today's date.
Read-only towards Angel: it never places or cancels orders.
"""
import contextlib
import io
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bots.trade_journal import JOURNAL_DIR, match_round_trips   # noqa: E402

MAX_TRADES = 3
MAX_LOSSES = 2
MAX_DAY_LOSS = 1500      # ₹, net
PROFIT_PROTECT = 500     # ₹, net: warning only

LOCK_FILE = os.path.join(JOURNAL_DIR, "day_lock.json")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def read_lock():
    try:
        with open(LOCK_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if d.get("date") == _today() else None
    except (OSError, ValueError):
        return None


def set_lock(reason):
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    d = {"date": _today(), "time": datetime.now().strftime("%H:%M"), "reason": reason}
    with open(LOCK_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f)
    return d


def compute(angel=None):
    """Return a dict with today's guard state. Pass an existing `angel` session to save a login check."""
    if angel is None:
        from core.angel import connect
        with contextlib.redirect_stdout(io.StringIO()):
            angel, _ = connect()
    fills = (angel.tradeBook() or {}).get("data") or []
    trips, leftovers = match_round_trips(fills, _today())
    nets = [float(t["net_pnl"]) for t in trips]
    s = {
        "trades": len(trips),
        "losses": sum(1 for n in nets if n <= 0),
        "wins": sum(1 for n in nets if n > 0),
        "gross": sum(float(t["gross_pnl"]) for t in trips),
        "net": sum(nets),
        "open_lots": len(leftovers),
        "lock": read_lock(),
    }
    reasons = []
    if s["trades"] >= MAX_TRADES:
        reasons.append(f"{s['trades']}/{MAX_TRADES} trades")
    if s["losses"] >= MAX_LOSSES:
        reasons.append(f"{s['losses']}/{MAX_LOSSES} losses")
    if s["net"] <= -MAX_DAY_LOSS:
        reasons.append(f"day loss ₹{s['net']:,.0f} ≤ −₹{MAX_DAY_LOSS:,}")
    if s["lock"]:
        reasons.append(f"day called {s['lock']['time']} ({s['lock']['reason']})")
    s["reasons"] = reasons
    if reasons:
        s["state"] = "LOCKED"
    elif s["net"] >= PROFIT_PROTECT:
        s["state"] = "PROTECT"
    else:
        s["state"] = "OK"
    return s


def format_status(s):
    icon = {"LOCKED": "🚫 LOCKED", "PROTECT": "🟡 PROTECT", "OK": "✅ OK"}[s["state"]]
    head = f"DAY GUARD {_today()} {datetime.now():%H:%M} → {icon}"
    if s["reasons"]:
        head += "  (" + "; ".join(s["reasons"]) + ")"
    elif s["state"] == "PROTECT":
        head += f"  (net ≥ ₹{PROFIT_PROTECT}: green day, A+ setups only)"
    left = MAX_DAY_LOSS + s["net"]
    body = (f"Trades {s['trades']}/{MAX_TRADES} · Losses {s['losses']}/{MAX_LOSSES} · "
            f"Net ≈ ₹{s['net']:+,.0f} (est. charges) · Open lots {s['open_lots']} · "
            f"Loss room ₹{max(left, 0):,.0f}")
    if s["state"] == "LOCKED":
        body += "\nNo new entries today. Managing or exiting an open position is still allowed."
    return head + "\n" + body


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "status"
    if cmd == "lock":
        d = set_lock(" ".join(args[1:]) or "called it a day")
        print(f"🔒 Day locked at {d['time']}: {d['reason']}")
    elif cmd == "unlock":
        if not read_lock():
            print("No manual lock set for today.")
            return
        reason = " ".join(args[1:]).strip()
        if not reason:
            print("Unlocking is discouraged. If you really mean it, run:\n"
                  "  python bots/day_guard.py unlock <reason why this is not a revenge trade>")
            return
        os.remove(LOCK_FILE)
        print(f"🔓 Manual lock removed ({reason}). Trade/loss limits still apply.")
    print(format_status(compute()))


if __name__ == "__main__":
    main()
