"""
Fast one-shot market check (about 3–5 s once the token cache is built).

    python bots/quick_check.py                  # CRUDEOIL (default), ATM ±2 strikes
    python bots/quick_check.py crudem           # CRUDEOILM (Crude Mini)
    python bots/quick_check.py nifty            # NIFTY (NFO, nearest expiry)
    python bots/quick_check.py banknifty        # BANKNIFTY (NFO)
    python bots/quick_check.py nifty --strikes 3

Instrument aliases: crude/crudeoil · crudem/mini/crudeoilm · nifty · banknifty/bnf ·
finnifty · midcpnifty · naturalgas/ng · naturalgasm/ngm. Unknown extra words are ignored,
so slash-command arguments like "nifty pe" work.

Contracts are chosen from the live expiries in Angel's instrument master every day,
never from hardcoded months:
  - Options: the nearest expiry that is still trading (an expiry is done after that
    day's close: 15:30 NFO; MCX 23:30 in US summer time, 23:55 in US winter time).
  - MCX options are on futures, so the future shown is the one those options are
    priced on (the first future expiring on/after the option expiry). Between the
    option expiry and the old future's expiry this is next month's future.
  - NFO index options settle to the spot index, so the ATM strike is centred on spot;
    the candles come from the near-month future (rolled on its expiry day).
  - The ATM is cross-checked with put-call parity (strike + CE − PE), and any
    mismatch or upcoming expiry is printed as a ⚠️ line.
Candles start from earlier sessions, so EMA20 is valid from the open, and the EMA
and the trend read use closed candles only.

The first run each day downloads the instrument master (about 10 s) and caches
the futures, options and spot-index tokens in .cache/instruments.json.
After that, each check makes 5 API calls: profile check, positions, order book,
candles, and one batched quote. There's no searchScrip and no long sleeps.
Read-only: never places orders.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.angel import connect                  # noqa: E402
from core.candles import ema, momentum          # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
CACHE = os.path.join(ROOT, ".cache", "instruments.json")
CACHE_VERSION = 2                               # bump when the cached row set changes

# alias → (master name, exchange, future type, option type)
INSTRUMENTS = {
    "crude": ("CRUDEOIL", "MCX", "FUTCOM", "OPTFUT"), "crudeoil": ("CRUDEOIL", "MCX", "FUTCOM", "OPTFUT"),
    "crudem": ("CRUDEOILM", "MCX", "FUTCOM", "OPTFUT"), "crudeoilm": ("CRUDEOILM", "MCX", "FUTCOM", "OPTFUT"),
    "mini": ("CRUDEOILM", "MCX", "FUTCOM", "OPTFUT"),
    "naturalgas": ("NATURALGAS", "MCX", "FUTCOM", "OPTFUT"), "ng": ("NATURALGAS", "MCX", "FUTCOM", "OPTFUT"),
    "naturalgasm": ("NATGASMINI", "MCX", "FUTCOM", "OPTFUT"), "ngm": ("NATGASMINI", "MCX", "FUTCOM", "OPTFUT"),
    "nifty": ("NIFTY", "NFO", "FUTIDX", "OPTIDX"),
    "banknifty": ("BANKNIFTY", "NFO", "FUTIDX", "OPTIDX"), "bnf": ("BANKNIFTY", "NFO", "FUTIDX", "OPTIDX"),
    "finnifty": ("FINNIFTY", "NFO", "FUTIDX", "OPTIDX"),
    "midcpnifty": ("MIDCPNIFTY", "NFO", "FUTIDX", "OPTIDX"),
}
WANTED = {(v[0], v[1]) for v in INSTRUMENTS.values()}
SPOT_NAMES = {v[0] for v in INSTRUMENTS.values() if v[1] == "NFO"}   # index options → spot index on NSE
MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
PAUSE = 0.35
MAX_QUOTE_TOKENS = 50                           # Angel's per-request limit for getMarketData


# ── calendar helpers ─────────────────────────────────────────────────────────

def _expiry(s):
    return datetime.strptime(s, "%d%b%Y").date()


def us_dst(d):
    """True while US daylight saving time is on (2nd Sunday of March → 1st Sunday of November)."""
    mar8, nov1 = date(d.year, 3, 8), date(d.year, 11, 1)
    start = mar8 + timedelta(days=(6 - mar8.weekday()) % 7)
    end = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    return start <= d < end


def market_close(exch, d=None):
    """Session close (IST, HH:MM). MCX energy follows US time: 23:30 in US summer, 23:55 in US winter."""
    d = d or date.today()
    if exch == "NFO":
        return "15:30"
    return "23:30" if us_dst(d) else "23:55"


def eia_time(d=None):
    """EIA weekly petroleum report: Wednesday 10:30 New York time, in IST."""
    return "20:00" if us_dst(d or date.today()) else "21:00"


def is_live(expiry, exch, now):
    """A contract trades until the close of its expiry day."""
    e = _expiry(expiry)
    return e > now.date() or (e == now.date() and now.strftime("%H:%M") < market_close(exch, e))


def days_to(expiry, now):
    return (_expiry(expiry) - now.date()).days


def _when(expiry, now):
    n = days_to(expiry, now)
    return "TODAY" if n == 0 else "tomorrow" if n == 1 else f"in {n} days"


# ── instrument master ────────────────────────────────────────────────────────

def load_instruments():
    """Today's futures, options and spot-index rows for all INSTRUMENTS (cached daily)."""
    today = date.today().isoformat()
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("date") == today and c.get("v") == CACHE_VERSION:
            return c["rows"]
    print("Building today's token cache (one-time, ~10 s)...", file=sys.stderr)
    with urllib.request.urlopen(MASTER_URL, timeout=60) as r:
        master = json.load(r)
    rows = [{"token": m["token"], "symbol": m["symbol"], "name": m["name"], "exch": m["exch_seg"],
             "type": m["instrumenttype"], "expiry": m["expiry"],
             "strike": float(m["strike"]) / 100, "lot": m["lotsize"]}
            for m in master
            if ((m.get("name"), m.get("exch_seg")) in WANTED
                and m.get("instrumenttype") in ("FUTCOM", "OPTFUT", "FUTIDX", "OPTIDX"))
            or (m.get("instrumenttype") == "AMXIDX" and m.get("exch_seg") == "NSE"
                and m.get("name") in SPOT_NAMES)]
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"date": today, "v": CACHE_VERSION, "rows": rows}, f)
    return rows


def resolve(rows, inst, now=None):
    """Pick the contracts to analyse from the live expiries. Returns a dict:
    fut   – future to chart/trade (MCX: the options' underlying; NFO: near month, rolled on expiry day)
    near  – nearest live future (differs from fut around expiries)
    exp   – nearest live option expiry, opts – its option rows, next_exp – the expiry after it
    spot  – spot-index row for NFO index options (None for MCX)
    """
    name, exch, ftype, otype = inst
    now = now or datetime.now()
    mine = [r for r in rows if r["name"] == name and r["exch"] == exch]
    futs = sorted((r for r in mine if r["type"] == ftype and is_live(r["expiry"], exch, now)),
                  key=lambda r: _expiry(r["expiry"]))
    if not futs:
        raise SystemExit(f"No live {name} futures in the instrument master. Delete {CACHE} and retry.")
    opts_all = [r for r in mine if r["type"] == otype and is_live(r["expiry"], exch, now)]
    exps = sorted({r["expiry"] for r in opts_all}, key=_expiry)
    exp = exps[0] if exps else None
    opts = [r for r in opts_all if r["expiry"] == exp]
    near = futs[0]
    if exch == "MCX" and exp:
        # options on futures: priced on the first future that expires on/after the option expiry
        fut = next((f for f in futs if _expiry(f["expiry"]) >= _expiry(exp)), near)
    else:
        # index options settle to spot; volume moves to the next future on the near month's expiry day
        fut = futs[1] if len(futs) > 1 and days_to(near["expiry"], now) == 0 else near
    spot = next((r for r in rows if r["type"] == "AMXIDX" and r["name"] == name), None) if exch == "NFO" else None
    return {"fut": fut, "near": near, "exp": exp, "opts": opts,
            "next_exp": exps[1] if len(exps) > 1 else None, "spot": spot}


def pick(rows, inst):
    """Backward-compatible wrapper: (future, option expiry, option rows)."""
    c = resolve(rows, inst)
    return c["fut"], c["exp"], c["opts"]


# ── quote helpers ────────────────────────────────────────────────────────────

def _px(x):
    """Best option price: bid/ask mid when both sides exist, else LTP."""
    d = x.get("depth", {})
    b = (d.get("buy") or [{}])[0].get("price") or 0
    a = (d.get("sell") or [{}])[0].get("price") or 0
    if b > 0 and a > 0:
        return (b + a) / 2
    return x.get("ltp")


def synthetic(strikes, chain, q, ref):
    """Underlying implied by the options (put-call parity at the strike nearest ref): K + CE − PE."""
    for k in sorted(strikes, key=lambda s: abs(s - ref))[:3]:
        ce, pe = chain.get((k, "CE")), chain.get((k, "PE"))
        if ce and pe:
            c, p = _px(q.get(ce["token"], {})), _px(q.get(pe["token"], {}))
            if c and p:
                return k + c - p, k
    return None, None




def resample(cs, minutes):
    """Build higher-timeframe candles from 5m ones, anchored at each session's first candle
    (MCX 09:00, NFO 09:15), the same way Angel aligns its 30m/1H bars."""
    starts, out = {}, []
    for c in cs:
        day_start = starts.setdefault(c["ts"].date(), c["ts"])
        k = day_start + timedelta(minutes=int((c["ts"] - day_start).total_seconds() // 60) // minutes * minutes)
        if out and out[-1]["ts"] == k:
            b = out[-1]
            b["high"] = max(b["high"], c["high"]); b["low"] = min(b["low"], c["low"])
            b["close"] = c["close"]; b["volume"] += c["volume"]
        else:
            out.append({**c, "ts": k})
    return out


def _oi(n):
    n = n or 0
    return f"{n / 1e5:.2f}L" if n >= 1e5 else f"{n / 1e3:.1f}k" if n >= 1e3 else f"{n:.0f}"


def _print_candles(title, rows, n, forming_last):
    print(f"{title}   time   open   high    low  close    vol")
    for c in rows[-n:]:
        flag = "  (forming)" if forming_last and c is rows[-1] else ""
        print(f"   {c['ts']:%d %H:%M}  {c['open']:.0f}  {c['high']:.0f}  {c['low']:.0f}  {c['close']:.0f}  {c['volume']:>5}{flag}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("words", nargs="*", help="instrument alias (default crude); other words ignored")
    ap.add_argument("--strikes", type=int, default=2, help="strikes each side of ATM in the price table")
    ap.add_argument("--mini", action="store_true", help="same as 'crudem'")
    ap.add_argument("--candles", type=int, default=12, help="5m candles to print")
    ap.add_argument("--no-guard", action="store_true", help="skip the day-guard line")
    a, _ = ap.parse_known_args()

    alias = next((w.lower() for w in a.words if w.lower() in INSTRUMENTS), "crudem" if a.mini else "crude")
    inst = INSTRUMENTS[alias]
    EX = inst[1]
    now = datetime.now()
    ctx = resolve(load_instruments(), inst, now)
    fut, near_fut, exp, opts, spot = ctx["fut"], ctx["near"], ctx["exp"], ctx["opts"], ctx["spot"]

    angel, _ = connect()

    # 1) one candle call: 5 days of 5m. 30m and 1H are built from it (no extra API calls)
    time.sleep(PAUSE)
    raw = angel.getCandleData({"exchange": EX, "symboltoken": fut["token"], "interval": "FIVE_MINUTE",
                               "fromdate": (now - timedelta(days=5)).strftime("%Y-%m-%d 09:00"),
                               "todate": now.strftime("%Y-%m-%d %H:%M")}).get("data") or []
    cs = [{"ts": datetime.fromisoformat(r[0]).replace(tzinfo=None), "open": r[1], "high": r[2],
           "low": r[3], "close": r[4], "volume": r[5]} for r in raw]
    tf = {}
    for label, mins in (("1H", 60), ("30m", 30), ("5m", 5)):
        rows = cs if mins == 5 else resample(cs, mins)
        forming = bool(rows) and rows[-1]["ts"] + timedelta(minutes=mins) > now
        closed = rows[:-1] if forming else rows
        e = ema([c["close"] for c in closed], 20)[-1] if len(closed) >= 20 else None
        tf[label] = {"rows": rows, "forming": forming, "closed": closed, "ema": e,
                     "mom": momentum(closed, lookback=6) if len(closed) >= 8 else None}
    sessions = sorted({c["ts"].date() for c in cs})
    cur_day = sessions[-1] if sessions else now.date()
    prev_day = sessions[-2] if len(sessions) > 1 else None
    prev = [c for c in cs if c["ts"].date() == prev_day] if prev_day else []
    rough = cs[-1]["close"] if cs else None

    # 2) one batched quote: future (+ near future, spot) + a wide strike window (prices, OI, volume)
    strikes = sorted({r["strike"] for r in opts})
    extra = [near_fut["token"]] if near_fut["token"] != fut["token"] else []
    per_side = min(max(a.strikes, 8), (MAX_QUOTE_TOKENS - 2 - len(extra)) // 4)
    window = []
    if rough and strikes:
        i = strikes.index(min(strikes, key=lambda s: abs(s - rough)))
        window = strikes[max(0, i - per_side): i + per_side + 1]
    chain = {(r["strike"], r["symbol"][-2:]): r for r in opts if r["strike"] in window}
    req = {EX: [fut["token"]] + extra + [r["token"] for r in chain.values()]}
    if spot:
        req["NSE"] = [spot["token"]]
    time.sleep(PAUSE)
    q = {x["symbolToken"]: x for x in (angel.getMarketData("FULL", req).get("data") or {}).get("fetched", [])}

    f = q.get(fut["token"], {})
    s_ltp = q.get(spot["token"], {}).get("ltp") if spot else None
    ref = s_ltp or f.get("ltp") or rough              # NFO: spot; MCX: the options' underlying future
    syn, syn_k = synthetic(window, chain, q, ref) if ref else (None, None)
    centre = syn or ref
    atm = min(window, key=lambda s: abs(s - centre)) if centre and window else None
    near = []
    if atm is not None:
        i = window.index(atm)
        near = window[max(0, i - a.strikes): i + a.strikes + 1]
    step = min((b - a_ for a_, b in zip(strikes, strikes[1:]) if b > a_), default=0)

    # 3) positions + order book
    time.sleep(PAUSE)
    pos = (angel.position() or {}).get("data") or []
    time.sleep(PAUSE)
    ords = (angel.orderBook() or {}).get("data") or []
    guard = None
    if not a.no_guard:
        try:
            from bots.day_guard import compute, format_status
            time.sleep(PAUSE)
            guard = format_status(compute(angel))
        except Exception as e:                     # never let the guard break a market check
            guard = f"DAY GUARD unavailable: {e}"

    # ── output ──
    d = f.get("depth", {})
    bid = (d.get("buy") or [{}])[0].get("price"); ask = (d.get("sell") or [{}])[0].get("price")
    lot = opts[0]["lot"] if opts else fut["lot"]
    e5 = tf["5m"]["ema"]
    print(f"[{inst[0]} · {EX}]  token {fut['token']}")
    print(f"{now:%H:%M:%S}  {fut['symbol']}  LTP {f.get('ltp')}  bid/ask {bid}/{ask}  "
          f"day H {f.get('high')} L {f.get('low')}  5m EMA20 {round(e5, 1) if e5 else '—'}")

    # contracts: one line, plus one short line per warning
    line = f"Contracts: fut {fut['expiry']} ({_when(fut['expiry'], now)})"
    if exp:
        line += f" · options {exp} ({_when(exp, now)}, lot {lot})"
    if spot and s_ltp:
        line += f" · spot {s_ltp} (fut {(f.get('ltp') or 0) - s_ltp:+.0f})"
    print(line)
    if near_fut["token"] != fut["token"]:
        nq = q.get(near_fut["token"], {}).get("ltp")
        print(f"    ⚠️ {near_fut['symbol']} {nq} expires {_when(near_fut['expiry'], now)}. Not used (different price).")
    if exp and days_to(exp, now) <= 1:
        print(f"    ⚠️ Options expire {_when(exp, now)}: fast time decay"
              + (f". Next expiry {ctx['next_exp']}" if ctx["next_exp"] else ""))
    if days_to(fut["expiry"], now) <= 3:
        print(f"    ⚠️ {fut['symbol']} expires {_when(fut['expiry'], now)}")
    if syn and step and abs(syn - ref) > step:
        print(f"    ⚠️ Options imply {syn:.0f}, {syn - ref:+.0f} from {ref}. Check the contract")
    if cs and not tf["5m"]["forming"] and (now - cs[-1]["ts"]) > timedelta(minutes=15):
        print(f"    ⚠️ Last candle {cs[-1]['ts']:%d %b %H:%M}: market closed or data delayed")
    sess = f"Session: closes {market_close(EX)} IST"
    if EX == "MCX" and inst[0].startswith("CRUDE"):
        sess += f" · EIA Wed {eia_time()} IST" + (" (TODAY)" if now.weekday() == 2 else "")
    if prev:
        sess += (f" · prev day {prev_day:%d %b}: H {max(c['high'] for c in prev):.0f} "
                 f"L {min(c['low'] for c in prev):.0f} C {prev[-1]['close']:.0f}")
    print(sess)

    # trend by timeframe (closed candles only)
    print("Trend      verdict              close   EMA20   vs EMA   structure")
    for label in ("1H", "30m", "5m"):
        t = tf[label]; m = t["mom"]
        if not m or "score" not in m:
            print(f"   {label:<4}    not enough candles"); continue
        dist = m["last_close"] - m["ema20"]
        print(f"   {label:<4}    {m['verdict']:<18} {m['last_close']:>7.0f} {m['ema20']:>7.0f}   {dist:>+6.0f}   {m['reasons'][0]}")

    _print_candles("1H ", tf["1H"]["rows"], 8, tf["1H"]["forming"])
    _print_candles("30m", tf["30m"]["rows"], 10, tf["30m"]["forming"])
    today_5m = [c for c in cs if c["ts"].date() == cur_day]
    _print_candles("5m ", today_5m, a.candles, tf["5m"]["forming"])

    # options: price table around ATM, then OI over the wide window
    if atm is not None:
        how = f"options imply {syn:.0f}" if syn else ("centred on spot" if s_ltp else "centred on fut")
        print(f"Options {exp} (lot {lot}), ATM {atm:.0f} ({how})")
        ce, pe = chain.get((atm, "CE")), chain.get((atm, "PE"))
        print(f"    ATM symbols: {ce['symbol'] if ce else '—'} ({ce['token'] if ce else ''}) · "
              f"{pe['symbol'] if pe else '—'} ({pe['token'] if pe else ''})")
        print("    strike   CE ltp (bid/ask)          OI   |  PE ltp (bid/ask)          OI")
        for s in near:
            cells = []
            for side in ("CE", "PE"):
                r = chain.get((s, side)); x = q.get(r["token"], {}) if r else {}
                dd = x.get("depth", {})
                px = f"{x.get('ltp', '—')} ({(dd.get('buy') or [{}])[0].get('price', '—')}/{(dd.get('sell') or [{}])[0].get('price', '—')})"
                cells.append(f"{px:<24} {_oi(x.get('opnInterest')):>6}")
            print(f"    {s:>6.0f}{'*' if s == atm else ' '}  {cells[0]}   |  {cells[1]}")
        oi = {(k, side): q.get(r["token"], {}).get("opnInterest") or 0 for (k, side), r in chain.items()}
        vol = {(k, side): q.get(r["token"], {}).get("tradeVolume") or 0 for (k, side), r in chain.items()}
        ce_oi = {k: v for (k, sd), v in oi.items() if sd == "CE"}
        pe_oi = {k: v for (k, sd), v in oi.items() if sd == "PE"}
        if sum(ce_oi.values()) and sum(pe_oi.values()):
            above = {k: v for k, v in ce_oi.items() if k >= centre} or ce_oi
            below = {k: v for k, v in pe_oi.items() if k <= centre} or pe_oi
            r1 = sorted(above, key=above.get, reverse=True)[:2]
            s1 = sorted(below, key=below.get, reverse=True)[:2]
            pcr = sum(pe_oi.values()) / sum(ce_oi.values())
            busiest = max(vol, key=vol.get)
            print(f"OI ({window[0]:.0f}–{window[-1]:.0f}): resistance (CE OI) "
                  + ", ".join(f"{k:.0f} {_oi(ce_oi[k])}" for k in r1)
                  + " · support (PE OI) " + ", ".join(f"{k:.0f} {_oi(pe_oi[k])}" for k in s1)
                  + f" · PCR {pcr:.2f} · most traded {busiest[0]:.0f}{busiest[1]} ({vol[busiest]:,})")
    else:
        print("Options: —")

    open_pos = [p for p in pos if int(float(p.get("netqty") or 0)) != 0]
    day_pnl = sum(float(p.get("pnl") or 0) for p in pos)
    print(f"Positions: {len(open_pos)} open | day gross P&L ₹{day_pnl:+,.0f}")
    for p in open_pos:
        print(f"    OPEN {p['tradingsymbol']} net {p['netqty']} buyavg {p.get('buyavgprice')} "
              f"sellavg {p.get('sellavgprice')} ltp {p.get('ltp')} pnl ₹{float(p.get('pnl') or 0):+,.0f}")
    pending = [o for o in ords if (o.get("status") or "").lower() in ("open", "trigger pending", "pending")]
    print(f"Pending orders: {len(pending)}")
    for o in pending:
        print(f"    {o.get('updatetime')} {o['tradingsymbol']} {o['transactiontype']} {o['ordertype']} "
              f"{o['quantity']} px {o.get('price')} trg {o.get('triggerprice')} [{o.get('status')}] {o.get('orderid')}")
    rejected = [o for o in ords if (o.get("status") or "").lower() == "rejected"][-2:]
    for o in rejected:
        print(f"    REJECTED {o.get('updatetime')} {o['tradingsymbol']} {o.get('text', '')[:80]}")
    if guard:
        print(guard)


if __name__ == "__main__":
    main()
