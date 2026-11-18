"""
Backtester: test intraday strategies on historical candles from Angel One (futures, with costs).

    python bots/backtester.py                         # compare the default strategy set, last 120 days
    python bots/backtester.py --days 150 --mini       # Crude Mini (10 units) instead of standard (100)
    python bots/backtester.py --strategy ma --fast 9 --slow 21 --filter ema50 --monthly --trades
    python bots/backtester.py --strategy breakout --lookback 24 --vol-mult 1.5 --stop 25 --rr 2
    python bots/backtester.py --no-rules              # ignore the 3-trades / 2-losses daily limits
    python bots/backtester.py nifty --days 90         # other instruments (same aliases as quick_check)

Strategies
  ma        EMA fast/slow crossover. Enter on a closed-candle cross, exit on the opposite cross
            (reverse if allowed), optional stop. Optional trend filter: only trade in the direction
            of EMA50 / EMA200.
  breakout  Your "range break" setup: a 5m close beyond the prior N-bar high/low with volume
            ≥ vol-mult × the 20-bar average. Fixed stop, target = rr × stop.

Assumptions (conservative, stated in the report)
  - Signals are computed on the candle close; fills at the NEXT candle's open ± slippage.
  - Stop and target are checked on each candle's high/low; if both are hit in one candle, the stop wins.
  - Intraday only: no entries outside the entry window, and everything is flat at the day's last candle.
  - Costs = brokerage, exchange charges, CTT, stamp, SEBI and GST (same model as the journal) + slippage.
  - Daily rules (default ON): max 3 trades and stop after 2 losses per day, the same as the Day Guard.
Data is cached in .cache/bt_<token>_<interval>.csv and only missing days are downloaded.
Read-only: never places orders.
"""
import argparse
import contextlib
import csv
import io
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bots.quick_check import INSTRUMENTS, load_instruments, pick   # noqa: E402
from bots.trade_journal import estimate_charges                    # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
CHUNK_DAYS = 30


# ── data ──────────────────────────────────────────────────────────────────────

def fetch_candles(token, exchange, days, interval="FIVE_MINUTE"):
    """Cached + incremental download. Returns [(dt, o, h, l, c, v), ...] sorted."""
    path = os.path.join(ROOT, ".cache", f"bt_{token}_{interval}.csv")
    bars = {}
    if os.path.exists(path):
        with open(path, newline="") as f:
            for r in csv.reader(f):
                bars[r[0]] = tuple(float(x) for x in r[1:])
    end = datetime.now()
    start = end - timedelta(days=days)
    have_days = {k[:10] for k in bars}
    # (re)fetch chunks that contain missing days, plus always the last 2 days (today may be partial)
    need, d = [], start
    while d <= end:
        day = d.strftime("%Y-%m-%d")
        if day not in have_days or d >= end - timedelta(days=2):
            need.append(d)
        d += timedelta(days=1)
    if need:
        from core.angel import connect
        with contextlib.redirect_stdout(io.StringIO()):
            angel, _ = connect()
        s = need[0]
        while s <= end:
            e = min(s + timedelta(days=CHUNK_DAYS), end)
            if any(s <= x <= e for x in need):
                for attempt in range(3):
                    try:
                        res = angel.getCandleData({"exchange": exchange, "symboltoken": token, "interval": interval,
                                                   "fromdate": s.strftime("%Y-%m-%d 00:00"),
                                                   "todate": e.strftime("%Y-%m-%d 23:59")})
                        for r in res.get("data") or []:
                            bars[r[0][:16]] = tuple(float(x) for x in r[1:6])
                        break
                    except Exception as ex:                      # rate limit / network: back off, retry
                        print(f"  fetch retry {attempt + 1}: {str(ex)[:60]}", file=sys.stderr)
                        time.sleep(2 + attempt * 2)
                time.sleep(0.45)
            s = e + timedelta(minutes=1)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            for k in sorted(bars):
                w.writerow([k, *bars[k]])
    cut = start.strftime("%Y-%m-%dT%H:%M")
    return [(k, *bars[k]) for k in sorted(bars) if k >= cut]


# ── indicators ────────────────────────────────────────────────────────────────

def ema(vals, n):
    k, out = 2 / (n + 1), []
    for v in vals:
        out.append(v if not out else v * k + out[-1] * (1 - k))
    return out


def sma(vals, n):
    out, s = [], 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        out.append(s / min(i + 1, n))
    return out


# ── engine ────────────────────────────────────────────────────────────────────

def backtest(bars, cfg):
    o = [b[1] for b in bars]; h = [b[2] for b in bars]; l = [b[3] for b in bars]
    c = [b[4] for b in bars]; v = [b[5] for b in bars]
    day = [b[0][:10] for b in bars]; hm = [b[0][11:16] for b in bars]
    n = len(bars)
    last_of_day = [i == n - 1 or day[i + 1] != day[i] for i in range(n)]
    lot, slip = cfg["lot"], cfg["slip"]

    # signals: +1 long, -1 short, 0 none, evaluated at the close of bar i
    sig = [0] * n
    if cfg["strategy"] == "ma":
        ef, es = ema(c, cfg["fast"]), ema(c, cfg["slow"])
        trend = ema(c, 50) if cfg["filter"] == "ema50" else ema(c, 200) if cfg["filter"] == "ema200" else None
        for i in range(1, n):
            if ef[i] > es[i] and ef[i - 1] <= es[i - 1]:
                sig[i] = 1
            elif ef[i] < es[i] and ef[i - 1] >= es[i - 1]:
                sig[i] = -1
        warm = cfg["slow"] * 3
    else:
        lb = cfg["lookback"]; vavg = sma(v, 20)
        trend = None
        for i in range(lb, n):
            hh, ll = max(h[i - lb:i]), min(l[i - lb:i])
            strong = v[i] >= cfg["vol_mult"] * vavg[i - 1]
            if c[i] > hh and strong:
                sig[i] = 1
            elif c[i] < ll and strong:
                sig[i] = -1
        warm = lb + 20

    trades, pos, cur_day = [], None, None
    day_trades = day_losses = 0

    def close_pos(i, px, why):
        nonlocal pos, day_losses
        side, qty = pos["side"], lot
        exit_px = px - slip * side
        buy, sell = (pos["px"], exit_px) if side == 1 else (exit_px, pos["px"])
        gross = (sell - buy) * qty
        cost = estimate_charges("FUT", buy * qty, sell * qty, orders=2)
        net = gross - cost
        trades.append({"day": day[pos["i"]], "entry": bars[pos["i"]][0][11:16], "exit": bars[i][0][11:16],
                       "side": "LONG" if side == 1 else "SHORT", "entry_px": round(pos["px"], 2),
                       "exit_px": round(exit_px, 2), "pts": round((sell - buy), 2), "net": round(net, 2),
                       "why": why})
        if net <= 0:
            day_losses += 1
        pos = None

    for i in range(warm, n):
        if day[i] != cur_day:
            cur_day, day_trades, day_losses = day[i], 0, 0
        # 1) stop / target inside this bar (position opened at this bar's open or earlier)
        if pos and i >= pos["i"]:
            side = pos["side"]
            if pos["stop"] is not None and ((side == 1 and l[i] <= pos["stop"]) or (side == -1 and h[i] >= pos["stop"])):
                px = pos["stop"] if (side == 1 and o[i] > pos["stop"]) or (side == -1 and o[i] < pos["stop"]) else o[i]
                close_pos(i, px, "stop")
            elif pos["tgt"] is not None and ((side == 1 and h[i] >= pos["tgt"]) or (side == -1 and l[i] <= pos["tgt"])):
                px = pos["tgt"] if (side == 1 and o[i] < pos["tgt"]) or (side == -1 and o[i] > pos["tgt"]) else o[i]
                close_pos(i, px, "target")
        # 2) end of day: flat at this bar's close
        if last_of_day[i]:
            if pos:
                close_pos(i, c[i], "eod")
            continue
        s = sig[i]
        # 3) opposite signal exits (MA) at next open
        if pos and s and s != pos["side"] and cfg["strategy"] == "ma":
            close_pos(i + 1, o[i + 1], "cross")
        # 4) entries at next open
        if pos is None and s:
            if not (cfg["entry_from"] <= hm[i] <= cfg["entry_to"]):
                continue
            if trend is not None and ((s == 1 and c[i] < trend[i]) or (s == -1 and c[i] > trend[i])):
                continue
            if cfg["rules"] and (day_trades >= 3 or day_losses >= 2):
                continue
            px = o[i + 1] + slip * s
            stop = px - cfg["stop"] * s if cfg["stop"] else None
            tgt = px + cfg["stop"] * cfg["rr"] * s if (cfg["stop"] and cfg["rr"]) else None
            pos = {"side": s, "px": px, "i": i + 1, "stop": stop, "tgt": tgt}
            day_trades += 1
    return trades


# ── report ────────────────────────────────────────────────────────────────────

def metrics(trades):
    if not trades:
        return None
    nets = [t["net"] for t in trades]
    wins, losses = [x for x in nets if x > 0], [x for x in nets if x <= 0]
    eq = peak = dd = 0.0
    streak = worst_streak = 0
    for x in nets:
        eq += x; peak = max(peak, eq); dd = min(dd, eq - peak)
        streak = streak + 1 if x <= 0 else 0
        worst_streak = max(worst_streak, streak)
    by_day = defaultdict(float); by_month = defaultdict(float)
    for t in trades:
        by_day[t["day"]] += t["net"]; by_month[t["day"][:7]] += t["net"]
    return {
        "trades": len(nets), "win": len(wins) / len(nets) * 100, "net": sum(nets),
        "pts": sum(t["pts"] for t in trades),
        "avg_win": sum(wins) / len(wins) if wins else 0, "avg_loss": sum(losses) / len(losses) if losses else 0,
        "pf": sum(wins) / abs(sum(losses)) if losses and sum(losses) else float("inf"),
        "exp": sum(nets) / len(nets), "dd": dd, "streak": worst_streak,
        "days": len(by_day), "green_days": sum(1 for x in by_day.values() if x > 0) / len(by_day) * 100,
        "worst_day": min(by_day.values()), "months": dict(sorted(by_month.items())),
    }


def label(cfg):
    if cfg["strategy"] == "ma":
        f = f" +{cfg['filter']}" if cfg["filter"] else ""
        st = f" SL{cfg['stop']:g}" if cfg["stop"] else ""
        return f"EMA {cfg['fast']}/{cfg['slow']}{f}{st}"
    return f"Breakout {cfg['lookback']}b v×{cfg['vol_mult']:g} SL{cfg['stop']:g} {cfg['rr']:g}R"


DEFAULT_SET = [
    {"strategy": "ma", "fast": 5, "slow": 13, "filter": None, "stop": 0},
    {"strategy": "ma", "fast": 9, "slow": 21, "filter": None, "stop": 0},
    {"strategy": "ma", "fast": 9, "slow": 21, "filter": "ema50", "stop": 0},
    {"strategy": "ma", "fast": 9, "slow": 21, "filter": None, "stop": 30},
    {"strategy": "ma", "fast": 20, "slow": 50, "filter": None, "stop": 0},
    {"strategy": "ma", "fast": 20, "slow": 50, "filter": "ema200", "stop": 0},
    {"strategy": "breakout", "lookback": 24, "vol_mult": 1.5, "stop": 25, "rr": 2},
    {"strategy": "breakout", "lookback": 24, "vol_mult": 1.5, "stop": 25, "rr": 1.5},
    {"strategy": "breakout", "lookback": 12, "vol_mult": 2.0, "stop": 20, "rr": 2},
    {"strategy": "breakout", "lookback": 48, "vol_mult": 1.5, "stop": 30, "rr": 2},
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("words", nargs="*", help="instrument alias (default crude)")
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--token", help="override the futures token")
    ap.add_argument("--mini", action="store_true", help="10-unit lot (Crude Mini) for ₹ figures")
    ap.add_argument("--lot", type=int, help="units per trade (default: contract lot)")
    ap.add_argument("--slip", type=float, default=1.0, help="slippage in points per side (default 1)")
    ap.add_argument("--strategy", choices=["ma", "breakout"])
    ap.add_argument("--fast", type=int, default=9); ap.add_argument("--slow", type=int, default=21)
    ap.add_argument("--filter", choices=["ema50", "ema200"])
    ap.add_argument("--lookback", type=int, default=24); ap.add_argument("--vol-mult", type=float, default=1.5)
    ap.add_argument("--stop", type=float, help="stop in points (0 = none)"); ap.add_argument("--rr", type=float, default=2)
    ap.add_argument("--entry-from", default="10:00"); ap.add_argument("--entry-to", default="22:30")
    ap.add_argument("--no-rules", action="store_true", help="ignore the 3-trades / 2-losses daily limits")
    ap.add_argument("--monthly", action="store_true"); ap.add_argument("--trades", action="store_true")
    a = ap.parse_args()

    alias = next((w.lower() for w in a.words if w.lower() in INSTRUMENTS), "crudem" if a.mini else "crude")
    inst = INSTRUMENTS[alias]
    fut, _, _ = pick(load_instruments(), inst)
    token = a.token or fut["token"]
    lot = a.lot or int(fut["lot"])
    print(f"Loading {a.days} days of 5m candles for {fut['symbol']} (token {token}, {inst[1]})...", file=sys.stderr)
    bars = fetch_candles(token, inst[1], a.days)
    if len(bars) < 200:
        print(f"Only {len(bars)} candles available, not enough to backtest."); return
    days = sorted({b[0][:10] for b in bars})

    base = {"lot": lot, "slip": a.slip, "entry_from": a.entry_from, "entry_to": a.entry_to,
            "rules": not a.no_rules, "rr": a.rr}
    if a.strategy:
        stop = a.stop if a.stop is not None else (25 if a.strategy == "breakout" else 0)
        configs = [{**base, "strategy": a.strategy, "fast": a.fast, "slow": a.slow, "filter": a.filter,
                    "lookback": a.lookback, "vol_mult": a.vol_mult, "stop": stop}]
    else:
        configs = [{**base, **c} for c in DEFAULT_SET]

    print(f"\nBACKTEST · {fut['symbol']} · {days[0]} → {days[-1]} ({len(days)} trading days, {len(bars):,} candles)")
    print(f"Lot {lot} units (₹{lot}/point) · slippage {a.slip:g} pt/side · costs incl. · entries "
          f"{a.entry_from}–{a.entry_to} · flat at day end · daily rules {'ON (3 trades / 2 losses)' if not a.no_rules else 'OFF'}")
    print("Fills at next candle open. Stop beats target in the same candle.\n")
    hdr = f"{'strategy':<32}{'trades':>7}{'win%':>6}{'net ₹':>11}{'PF':>6}{'exp ₹':>8}{'maxDD ₹':>10}{'L-streak':>9}{'green d%':>9}{'worst day':>11}"
    print(hdr); print("─" * len(hdr))
    results = []
    for cfg in configs:
        tr = backtest(bars, cfg); m = metrics(tr)
        results.append((cfg, tr, m))
    results.sort(key=lambda x: -(x[2]["net"] if x[2] else -1e12))
    for cfg, tr, m in results:
        if not m:
            print(f"{label(cfg):<32}{'0':>7}  no trades"); continue
        pf = "∞" if m["pf"] == float("inf") else f"{m['pf']:.2f}"
        print(f"{label(cfg):<32}{m['trades']:>7}{m['win']:>5.0f}%{m['net']:>+11,.0f}{pf:>6}{m['exp']:>+8,.0f}"
              f"{m['dd']:>+10,.0f}{m['streak']:>9}{m['green_days']:>8.0f}%{m['worst_day']:>+11,.0f}")
    if a.monthly or a.strategy:
        print("\nBy month (net ₹):")
        months = sorted({k for _, _, m in results if m for k in m["months"]})
        print(f"{'strategy':<32}" + "".join(f"{k:>10}" for k in months))
        for cfg, _, m in results:
            if m:
                print(f"{label(cfg):<32}" + "".join(f"{m['months'].get(k, 0):>+10,.0f}" for k in months))
    if a.trades and a.strategy:
        print("\nTrades:")
        for t in results[0][1]:
            print(f"  {t['day']} {t['entry']}→{t['exit']} {t['side']:<5} {t['entry_px']:>8} → {t['exit_px']:>8} "
                  f"{t['pts']:>+7.1f} pts  ₹{t['net']:>+8,.0f}  {t['why']}")
    print("\nPF = profit factor · exp = average net per trade · maxDD = worst peak-to-trough equity drop · "
          "L-streak = longest run of losing trades.")
    print("Past results on one contract's history are not a guarantee. Paper-trade a strategy before using real money.")


if __name__ == "__main__":
    main()
