"""
Trade Alert Bot — candle-close breakout alerts and position exit alerts (MCX/NFO).

Alerts are popups + beeps on this PC. This bot NEVER places orders.

Breakout mode — beep when a closed candle breaks a level:
  python bots/trade_alert.py breakout --token 573422 --symbol CRUDEOIL19NOV26FUT \
      --below 8110 --above 8175 --until 22:15 \
      --watch CRUDEOIL17NOV268150PE --watch CRUDEOIL17NOV268150CE

Position mode — watch an open option position:
  python bots/trade_alert.py position --symbol CRUDEOIL17NOV268200PE --entry 124.3 \
      --sl 110 --t1 150 --t2 175 --until 23:00 \
      --fut-token 573422 --fut-symbol CRUDEOIL19NOV26FUT --fail-above 8175
"""
import argparse
import contextlib
import io
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.angel import connect, get_ltp
from core.candles import get_candles, momentum, format_momentum, INTERVAL_MINUTES


def _now():
    return datetime.now().strftime("%H:%M:%S")


def _log(msg):
    print(f"[{_now()}] {msg}", flush=True)


def popup(title, msg):
    """Beep + Windows message box (non-blocking)."""
    safe = msg.replace("'", "")
    ps = ("[console]::beep(1000,600);[console]::beep(1300,600);"
          "Add-Type -AssemblyName PresentationFramework;"
          f"[System.Windows.MessageBox]::Show('{safe}','{title}')")
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps])
    except Exception:
        pass


QUIET = False  # --quiet: print only, no beep/popup (for testing)


def fire(tag, msg):
    print(f"{tag}: {msg}", flush=True)
    if not QUIET:
        popup(f"TRADE ALERT - {tag}", msg)


def _past(until):
    h, m = map(int, until.split(":"))
    now = datetime.now()
    return (now.hour, now.minute) >= (h, m)


def _token_map(angel, exchange, symbols):
    """Resolve option symbols to tokens via one searchScrip per prefix."""
    out = {}
    prefixes = {s[:-7] if s[-2:] in ("CE", "PE") else s for s in symbols}
    for p in prefixes:
        with contextlib.redirect_stdout(io.StringIO()):
            res = angel.searchScrip(exchange=exchange, searchscrip=p)
        for c in res.get("data") or []:
            if c.get("tradingsymbol") in symbols:
                out[c["tradingsymbol"]] = c["symboltoken"]
    return out


def _quote_watch(angel, exchange, tokens):
    parts = []
    for sym, tok in tokens.items():
        try:
            parts.append(f"{sym[-7:]} {get_ltp(angel, exchange, sym, tok)}")
        except Exception:
            parts.append(f"{sym[-7:]} n/a")
    return ", ".join(parts)


# ── Breakout mode ─────────────────────────────────────────────────────────────

def run_breakout(a):
    with contextlib.redirect_stdout(io.StringIO()):
        angel, _ = connect()
    watch_tokens = _token_map(angel, a.exchange, set(a.watch)) if a.watch else {}
    step = INTERVAL_MINUTES[a.interval]
    _log(f"Breakout watch {a.symbol}: close below {a.below} / above {a.above} on {a.interval}, until {a.until}")
    last_seen = None
    while not _past(a.until):
        try:
            candles = get_candles(angel, a.exchange, a.token, a.interval, lookback_minutes=step * 40)
        except Exception as e:
            _log(f"candle fetch error: {e}"); time.sleep(20); continue
        if candles and candles[-1]["ts"] != last_seen:
            c = candles[-1]
            last_seen = c["ts"]
            m = momentum(candles)
            _log(f"closed {c['ts']:%H:%M} O{c['open']:.0f} H{c['high']:.0f} L{c['low']:.0f} C{c['close']:.0f} V{c['volume']}  | {m['verdict']}")
            side = None
            if a.below is not None and c["close"] < a.below:
                side = "BEARISH BREAK"
            elif a.above is not None and c["close"] > a.above:
                side = "BULLISH BREAK"
            if side:
                quotes = _quote_watch(angel, a.exchange, watch_tokens)
                fire(side, f"{a.symbol} {a.interval} close {c['close']:.0f} at {c['ts']:%H:%M}. "
                           f"Momentum: {m['verdict']}. {quotes}")
                print(format_momentum(m, a.symbol), flush=True)
                return
        time.sleep(15)
    _log(f"Window ended at {a.until} — no breakout. No trade.")


# ── Position mode ─────────────────────────────────────────────────────────────

def run_position(a):
    with contextlib.redirect_stdout(io.StringIO()):
        angel, _ = connect()
    tok = a.token or _token_map(angel, a.exchange, {a.symbol}).get(a.symbol)
    if not tok:
        raise SystemExit(f"Could not resolve token for {a.symbol}")
    sl, t1_done, last_print, last_bucket, warned = a.sl, False, 0, None, False
    _log(f"Position watch {a.symbol} entry {a.entry} SL {sl} T1 {a.t1} T2 {a.t2} until {a.until}")
    while True:
        if _past(a.until):
            try: px = get_ltp(angel, a.exchange, a.symbol, tok)
            except Exception: px = None
            fire("TIME", f"{a.until} - EXIT NOW. {a.symbol} {px}" + (f", P&L Rs {(px - a.entry) * a.qty:+.0f}" if px else ""))
            return
        try:
            px = get_ltp(angel, a.exchange, a.symbol, tok)
            fut = get_ltp(angel, a.exchange, a.fut_symbol, a.fut_token) if a.fut_token else None
        except Exception as e:
            _log(f"fetch error: {e}"); time.sleep(15); continue
        pnl = (px - a.entry) * a.qty
        if time.time() - last_print > 300:
            _log(f"{a.symbol} {px}  FUT {fut}  P&L {pnl:+.0f}"); last_print = time.time()
        if fut is not None and a.fail_above is not None:
            bucket = (datetime.now().hour, datetime.now().minute // 5)
            if last_bucket is not None and bucket != last_bucket and not warned and fut > a.fail_above:
                fire("FAILED", f"5-min close above {a.fail_above:.0f} (FUT {fut}). Consider exit. {a.symbol} {px}, P&L Rs {pnl:+.0f}")
                warned = True
            last_bucket = bucket
        if px <= sl:
            fire("STOP", f"STOP {sl} HIT - EXIT. {a.symbol} {px}, P&L Rs {pnl:+.0f}"); return
        if a.t2 and px >= a.t2:
            fire("T2", f"TARGET 2 HIT - EXIT. {a.symbol} {px}, P&L Rs {pnl:+.0f}"); return
        if a.t1 and px >= a.t1 and not t1_done:
            fire("T1", f"TARGET 1 HIT. {a.symbol} {px}, P&L Rs {pnl:+.0f}. Book part / move SL to entry")
            t1_done, sl = True, max(sl, a.entry)
        time.sleep(10)


def main():
    global QUIET
    p = argparse.ArgumentParser(description="Trade alert bot (never places orders)")
    p.add_argument("--quiet", action="store_true", help="no beep/popup, print only")
    sub = p.add_subparsers(dest="mode", required=True)

    b = sub.add_parser("breakout")
    b.add_argument("--exchange", default="MCX")
    b.add_argument("--symbol", required=True)
    b.add_argument("--token", required=True)
    b.add_argument("--interval", default="FIVE_MINUTE", choices=list(INTERVAL_MINUTES))
    b.add_argument("--below", type=float)
    b.add_argument("--above", type=float)
    b.add_argument("--until", default="23:00")
    b.add_argument("--watch", action="append", default=[], help="option symbol to quote when firing (repeatable)")

    q = sub.add_parser("position")
    q.add_argument("--exchange", default="MCX")
    q.add_argument("--symbol", required=True)
    q.add_argument("--token")
    q.add_argument("--entry", type=float, required=True)
    q.add_argument("--qty", type=int, default=100)
    q.add_argument("--sl", type=float, required=True)
    q.add_argument("--t1", type=float)
    q.add_argument("--t2", type=float)
    q.add_argument("--until", default="23:00")
    q.add_argument("--fut-symbol")
    q.add_argument("--fut-token")
    q.add_argument("--fail-above", type=float, help="warn on 5-min close of futures above this (long PE)")

    a = p.parse_args()
    QUIET = a.quiet
    run_breakout(a) if a.mode == "breakout" else run_position(a)


if __name__ == "__main__":
    main()
