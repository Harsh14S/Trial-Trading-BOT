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

The first run each day downloads Angel's instrument master (about 10 s) and caches
the futures and options tokens in .cache/instruments.json.
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
from datetime import datetime, date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.angel import connect          # noqa: E402
from core.candles import ema            # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
CACHE = os.path.join(ROOT, ".cache", "instruments.json")

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
MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
PAUSE = 0.35


def _expiry(s):
    return datetime.strptime(s, "%d%b%Y").date()


def load_instruments():
    """Today's futures and options for all INSTRUMENTS from the instrument master (cached daily)."""
    today = date.today().isoformat()
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("date") == today:
            return c["rows"]
    print("Building today's token cache (one-time, ~10 s)...", file=sys.stderr)
    with urllib.request.urlopen(MASTER_URL, timeout=60) as r:
        master = json.load(r)
    rows = [{"token": m["token"], "symbol": m["symbol"], "name": m["name"], "exch": m["exch_seg"],
             "type": m["instrumenttype"], "expiry": m["expiry"],
             "strike": float(m["strike"]) / 100, "lot": m["lotsize"]}
            for m in master
            if (m.get("name"), m.get("exch_seg")) in WANTED
            and m.get("instrumenttype") in ("FUTCOM", "OPTFUT", "FUTIDX", "OPTIDX")]
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"date": today, "rows": rows}, f)
    return rows


def pick(rows, inst):
    name, exch, ftype, otype = inst
    today = date.today()
    live = [r for r in rows if r["name"] == name and r["exch"] == exch and _expiry(r["expiry"]) >= today]
    fut = min((r for r in live if r["type"] == ftype), key=lambda r: _expiry(r["expiry"]))
    opts = [r for r in live if r["type"] == otype]
    close_t = "15:30" if exch == "NFO" else "23:30"
    if datetime.now().strftime("%H:%M") >= close_t:      # today's expiry is done after the close
        opts = [r for r in opts if _expiry(r["expiry"]) > today] or opts
    exp = min({r["expiry"] for r in opts}, key=_expiry)
    opts = [r for r in opts if r["expiry"] == exp]
    return fut, exp, opts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("words", nargs="*", help="instrument alias (default crude); other words ignored")
    ap.add_argument("--strikes", type=int, default=2, help="strikes each side of ATM")
    ap.add_argument("--mini", action="store_true", help="same as 'crudem'")
    ap.add_argument("--candles", type=int, default=8)
    ap.add_argument("--no-guard", action="store_true", help="skip the day-guard line")
    a, _ = ap.parse_known_args()

    alias = next((w.lower() for w in a.words if w.lower() in INSTRUMENTS), "crudem" if a.mini else "crude")
    inst = INSTRUMENTS[alias]
    EX = inst[1]
    rows = load_instruments()
    fut, exp, opts = pick(rows, inst)

    angel, _ = connect()
    now = datetime.now()

    # 1) candles (5m, today)
    time.sleep(PAUSE)
    c = angel.getCandleData({"exchange": EX, "symboltoken": fut["token"], "interval": "FIVE_MINUTE",
                             "fromdate": now.strftime("%Y-%m-%d 09:00"),
                             "todate": now.strftime("%Y-%m-%d %H:%M")}).get("data") or []
    closes = [r[4] for r in c]
    e20 = ema(closes, 20) if len(closes) >= 20 else None
    e20 = e20[-1] if isinstance(e20, list) else e20
    last = closes[-1] if closes else None

    # 2) choose strikes around ATM, then one batched quote for fut + options
    strikes = sorted({r["strike"] for r in opts})
    atm = min(strikes, key=lambda s: abs(s - last)) if last and strikes else None
    near = []
    if atm is not None:
        i = strikes.index(atm)
        near = strikes[max(0, i - a.strikes): i + a.strikes + 1]
    chain = {(r["strike"], r["symbol"][-2:]): r for r in opts if r["strike"] in near}
    toks = [fut["token"]] + [r["token"] for r in chain.values()]
    time.sleep(PAUSE)
    q = {x["symbolToken"]: x for x in
         (angel.getMarketData("FULL", {EX: toks}).get("data") or {}).get("fetched", [])}

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
    f = q.get(fut["token"], {})
    d = f.get("depth", {})
    bid = d.get("buy", [{}])[0].get("price"); ask = d.get("sell", [{}])[0].get("price")
    print(f"[{inst[0]} · {EX}]  token {fut['token']}")
    print(f"{now:%H:%M:%S}  {fut['symbol']}  LTP {f.get('ltp')}  bid/ask {bid}/{ask}  "
          f"day H {f.get('high')} L {f.get('low')}  5m EMA20 {round(e20, 1) if e20 else '—'}")
    print("5m  time   open   high    low  close  vol")
    for r in c[-a.candles:]:
        flag = "  (forming)" if r is c[-1] else ""
        print(f"    {r[0][11:16]}  {r[1]:.0f}  {r[2]:.0f}  {r[3]:.0f}  {r[4]:.0f}  {r[5]}{flag}")

    print(f"Options {exp} (lot {opts[0]['lot'] if opts else '?'}), ATM {atm:.0f}" if atm else "Options: —")
    if atm is not None:
        ce, pe = chain.get((atm, "CE")), chain.get((atm, "PE"))
        print(f"    ATM symbols: {ce['symbol'] if ce else '—'} ({ce['token'] if ce else ''}) · "
              f"{pe['symbol'] if pe else '—'} ({pe['token'] if pe else ''})")
    print("    strike      CE ltp (bid/ask)       PE ltp (bid/ask)")
    for s in near:
        cells = []
        for side in ("CE", "PE"):
            r = chain.get((s, side)); x = q.get(r["token"], {}) if r else {}
            dd = x.get("depth", {})
            cells.append(f"{x.get('ltp', '—'):>7} ({dd.get('buy', [{}])[0].get('price', '—')}/"
                         f"{dd.get('sell', [{}])[0].get('price', '—')})")
        print(f"    {s:>6.0f}{' *' if s == atm else '  '}  {cells[0]:<22} {cells[1]}")

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
