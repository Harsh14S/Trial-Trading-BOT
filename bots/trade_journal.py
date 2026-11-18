"""
Trade Journal — daily trading records built from Angel One's trade book.

Files (journal/ is gitignored — personal P&L stays on this PC):
  journal/trades.csv          one row per closed round-trip trade (FIFO-matched fills)
  journal/daily/YYYY-MM-DD.md auto summary + your notes (notes section is preserved on re-sync)

Commands:
  python bots/trade_journal.py sync                  # pull today's fills → trades.csv + daily page
  python bots/trade_journal.py sync --date 2026-11-16
  python bots/trade_journal.py note T20261116-1 --setup "PE on lower-high rejection" \
        --exit "target limit" --notes "..." [--charges 63.5]   # charges from contract note
  python bots/trade_journal.py stats                 # all-time stats
  python bots/trade_journal.py stats --month 2026-11
  python bots/trade_journal.py stats --by-setup       # win rate / P&L per setup tag
  python bots/trade_journal.py note <ID> --tag breakout   # tags: see SETUP_TAGS
  python bots/trade_journal.py excel                 # rebuild journal/Trading_Journal.xlsx only

Run `sync` once at the end of each trading day (safe to re-run — rows are de-duplicated).
Charges are ESTIMATES until you enter the actual figure from the contract note with --charges.
"""
import argparse
import csv
import io
import contextlib
import os
import sys
from collections import defaultdict, deque
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import BASE_DIR

JOURNAL_DIR = os.path.join(BASE_DIR, "journal")
DAILY_DIR = os.path.join(JOURNAL_DIR, "daily")
TRADES_CSV = os.path.join(JOURNAL_DIR, "trades.csv")
XLSX = os.path.join(JOURNAL_DIR, "Trading_Journal.xlsx")

RULES = [
    "Trade MCX crude oil only.",
    "LIMIT orders only — never MARKET on options (one market order cost ~₹500 on 16 Nov).",
    "Enter on a 5-minute candle CLOSE beyond the level, not on the first tick.",
    "Place the stop-loss order immediately after the entry fills.",
    "Trail the stop to entry once the option premium is up ₹10–15; book partial at +15–20% on expiring options.",
    "Decide target vs stop before entry — never leave a position without protection.",
    "No new entries after 10:15 PM; exit everything by 11:00 PM.",
    "Do not trade options on expiry day or carry them overnight into expiry.",
    "Max 1 lot per trade until the journal shows a positive expectancy over 20+ trades.",
    "Run `python bots/trade_journal.py sync` at the end of every session and fill the daily notes.",
]

FIELDS = [
    "trade_id", "date", "symbol", "segment", "side", "qty",
    "entry_time", "entry_price", "exit_time", "exit_price", "product",
    "gross_pnl", "charges", "charges_source", "net_pnl",
    "entry_order", "exit_order", "setup", "exit_reason", "notes", "tag",
]

# Setup tags for `stats --by-setup`. Untagged trades are auto-classified from the setup/notes text.
SETUP_TAGS = {
    "breakout": "5m close through a key level / range edge (with volume)",
    "retest":   "entry on a pullback retest of a broken level",
    "rejection": "fade at a level that held (lower high / ceiling / floor)",
    "reversal": "counter-trend turn after a stretch from the EMA",
    "chase":    "late entry after the move / at an extreme / MARKET chase",
    "other":    "anything else",
}
_TAG_KEYWORDS = [            # first match wins: order matters
    ("chase", ("chase", "late", "after the move", "at the low", "near day low", "at/near the day low")),
    ("retest", ("retest", "pullback")),
    ("rejection", ("rejection", "ceiling", "lower-high", "lower high", "held")),
    ("reversal", ("reversal", "bounce", "stretched")),
    ("breakout", ("breakdown", "breakout", "break", "close below", "close above")),
]


def setup_tag(r):
    """Explicit tag if set, else a keyword guess from setup + notes (marked with '~')."""
    if (r.get("tag") or "").strip():
        return r["tag"].strip()
    text = f"{r.get('setup', '')} {r.get('notes', '')}".lower()
    if not text.strip():
        return "untagged"
    for tag, words in _TAG_KEYWORDS:
        if any(w in text for w in words):
            return "~" + tag
    return "~other"

# Approximate MCX charges (Angel One). Check against your contract note and adjust.
CHARGES = {
    "brokerage_per_order": 20.0,
    "OPT": {"txn": 0.0005, "ctt_sell": 0.0005, "stamp_buy": 0.00003},
    "FUT": {"txn": 0.000021, "ctt_sell": 0.0001, "stamp_buy": 0.00002},
    "sebi": 0.000001,   # ₹10 per crore
    "gst": 0.18,        # on brokerage + exchange txn + SEBI
}

NOTES_START = "<!-- NOTES: everything below this line is yours and is kept on re-sync -->"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _segment(symbol):
    return "OPT" if symbol.endswith(("CE", "PE")) else "FUT"


def charges_breakdown(segment, buy_value, sell_value, orders):
    r = CHARGES[segment]
    b = {"brokerage": CHARGES["brokerage_per_order"] * orders,
         "exchange_txn": (buy_value + sell_value) * r["txn"],
         "sebi": (buy_value + sell_value) * CHARGES["sebi"],
         "ctt": sell_value * r["ctt_sell"],
         "stamp": buy_value * r["stamp_buy"]}
    b["gst"] = (b["brokerage"] + b["exchange_txn"] + b["sebi"]) * CHARGES["gst"]
    return b


def estimate_charges(segment, buy_value, sell_value, orders):
    return round(sum(charges_breakdown(segment, buy_value, sell_value, orders).values()), 2)


def load_trades():
    if not os.path.exists(TRADES_CSV):
        return []
    with open(TRADES_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_trades(rows):
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    rows.sort(key=lambda r: (r["date"], r["entry_time"]))
    tmp = TRADES_CSV + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, TRADES_CSV)


def fetch_fills():
    from core.angel import connect
    with contextlib.redirect_stdout(io.StringIO()):
        angel, _ = connect()
    data = angel.tradeBook().get("data") or []
    open_pos = [p for p in (angel.position().get("data") or []) if int(p.get("netqty", 0)) != 0]
    return data, open_pos


def match_round_trips(fills, date):
    """FIFO-match fills per (symbol, product) into closed round trips."""
    groups = defaultdict(list)
    for f in fills:
        groups[(f["tradingsymbol"], f.get("producttype", ""))].append(f)

    trips, leftovers = [], []
    for (symbol, product), fs in groups.items():
        fs.sort(key=lambda f: f["filltime"])
        book = deque()   # open lots: [side, qty_left, price, time, order]
        for f in fs:
            side = "BUY" if f["transactiontype"] == "BUY" else "SELL"
            qty, price = int(f["fillsize"]), float(f["fillprice"])
            while qty and book and book[0][0] != side:
                lot = book[0]
                take = min(qty, lot[1])
                long_trade = lot[0] == "BUY"
                trips.append({
                    "symbol": symbol, "product": product, "qty": take,
                    "side": "LONG" if long_trade else "SHORT",
                    "entry_time": lot[3], "entry_price": lot[2], "entry_order": lot[4],
                    "exit_time": f["filltime"], "exit_price": price, "exit_order": f["orderid"],
                })
                lot[1] -= take
                qty -= take
                if lot[1] == 0:
                    book.popleft()
            if qty:
                book.append([side, qty, price, f["filltime"], f["orderid"]])
        leftovers += [(symbol, product, lot[0], lot[1]) for lot in book]

    rows = []
    for t in trips:
        seg = _segment(t["symbol"])
        buy_px, sell_px = (t["entry_price"], t["exit_price"]) if t["side"] == "LONG" else (t["exit_price"], t["entry_price"])
        gross = round((sell_px - buy_px) * t["qty"], 2)
        charges = estimate_charges(seg, buy_px * t["qty"], sell_px * t["qty"], orders=2)
        rows.append({
            "trade_id": "", "date": date, "symbol": t["symbol"], "segment": seg, "side": t["side"],
            "qty": t["qty"], "entry_time": t["entry_time"], "entry_price": t["entry_price"],
            "exit_time": t["exit_time"], "exit_price": t["exit_price"], "product": t["product"],
            "gross_pnl": gross, "charges": charges, "charges_source": "estimate",
            "net_pnl": round(gross - charges, 2),
            "entry_order": t["entry_order"], "exit_order": t["exit_order"],
            "setup": "", "exit_reason": "", "notes": "",
        })
    return rows, leftovers


def update_excel(rows=None, read_back=True):
    """Pull yellow-cell edits from the workbook into trades.csv, then rebuild the workbook."""
    from bots.journal_excel import build_workbook, parse_daily_notes, read_back_edits
    rows = rows if rows is not None else load_trades()
    if read_back:
        changed = read_back_edits(XLSX, rows)
        if changed:
            save_trades(rows)
            print(f"Saved {changed} edit(s) made in Excel back to trades.csv")
    try:
        build_workbook(XLSX, rows, parse_daily_notes(DAILY_DIR, NOTES_START), RULES, CHARGES)
        print(f"Excel workbook: {XLSX}")
    except PermissionError:
        print(f"⚠️  {XLSX} is open in Excel — close it and run `python bots/trade_journal.py excel`.")
    return rows


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_sync(date):
    today = datetime.now().strftime("%Y-%m-%d")
    if date != today:
        print(f"Angel's trade book only holds today's fills ({today}); re-rendering {date} from trades.csv.")
        write_daily(date)
        update_excel()
        return
    fills, open_pos = fetch_fills()
    new_rows, leftovers = match_round_trips(fills, date)

    existing = load_trades()
    try:
        from bots.journal_excel import read_back_edits
        if read_back_edits(XLSX, existing):
            save_trades(existing)
            print("Saved edits made in Excel back to trades.csv")
    except Exception as e:
        print(f"(could not read Excel edits: {e})")
    seen = {(r["entry_order"], r["exit_order"], r["symbol"]) for r in existing}
    day_count = sum(1 for r in existing if r["date"] == date)
    added = 0
    for r in sorted(new_rows, key=lambda r: r["entry_time"]):
        key = (r["entry_order"], r["exit_order"], r["symbol"])
        if key in seen:
            continue
        day_count += 1
        r["trade_id"] = f"T{date.replace('-', '')}-{day_count}"
        existing.append(r)
        seen.add(key)
        added += 1
    save_trades(existing)
    print(f"Synced {len(fills)} fills → {added} new trade(s). Total in journal: {len(existing)}")
    if leftovers or open_pos:
        print("⚠️  Unmatched / open quantity (not recorded until closed):")
        for s, p, side, q in leftovers:
            print(f"   {s} [{p}] {side} {q}")
    write_daily(date, open_pos=open_pos)
    update_excel(read_back=False)


def cmd_note(trade_id, setup, exit_reason, notes, charges, tag=None):
    rows = load_trades()
    for r in rows:
        if r["trade_id"] == trade_id:
            if setup is not None: r["setup"] = setup
            if exit_reason is not None: r["exit_reason"] = exit_reason
            if notes is not None: r["notes"] = notes
            if tag is not None:
                if tag not in SETUP_TAGS:
                    print(f"Unknown tag '{tag}'. Use one of: {', '.join(SETUP_TAGS)}"); return
                r["tag"] = tag
            if charges is not None:
                r["charges"], r["charges_source"] = round(charges, 2), "contract note"
                r["net_pnl"] = round(float(r["gross_pnl"]) - charges, 2)
            save_trades(rows)
            write_daily(r["date"])
            update_excel(read_back=False)
            print(f"Updated {trade_id}")
            return
    raise SystemExit(f"Trade {trade_id} not found")


def _stats(rows):
    if not rows:
        return None
    nets = [float(r["net_pnl"]) for r in rows]
    wins, losses = [n for n in nets if n > 0], [n for n in nets if n <= 0]
    return {
        "trades": len(rows), "net": sum(nets), "gross": sum(float(r["gross_pnl"]) for r in rows),
        "charges": sum(float(r["charges"]) for r in rows),
        "wins": len(wins), "losses": len(losses),
        "win_rate": len(wins) / len(rows) * 100,
        "avg_win": sum(wins) / len(wins) if wins else 0,
        "avg_loss": sum(losses) / len(losses) if losses else 0,
        "best": max(nets), "worst": min(nets),
        "profit_factor": (sum(wins) / abs(sum(losses))) if losses and sum(losses) else float("inf"),
        "expectancy": sum(nets) / len(rows),
    }


def _fmt_stats(s):
    pf = "∞" if s["profit_factor"] == float("inf") else f"{s['profit_factor']:.2f}"
    return (f"Trades {s['trades']} | Wins {s['wins']} / Losses {s['losses']} ({s['win_rate']:.0f}% win)\n"
            f"Gross ₹{s['gross']:+,.0f} | Charges ₹{s['charges']:,.0f} | Net ₹{s['net']:+,.0f}\n"
            f"Avg win ₹{s['avg_win']:+,.0f} | Avg loss ₹{s['avg_loss']:+,.0f} | Expectancy ₹{s['expectancy']:+,.0f}/trade\n"
            f"Best ₹{s['best']:+,.0f} | Worst ₹{s['worst']:+,.0f} | Profit factor {pf}")


def cmd_stats_by_setup(rows, label):
    groups = defaultdict(list)
    for r in rows:
        groups[setup_tag(r)].append(r)
    print(f"STATS BY SETUP {label}   (~ = auto-classified; fix with `note <ID> --tag <tag>`)")
    print(f"{'setup':<12}{'trades':>7}{'win%':>7}{'net ₹':>10}{'avg ₹':>9}{'best ₹':>9}{'worst ₹':>9}")
    order = sorted(groups, key=lambda k: -sum(float(r["net_pnl"]) for r in groups[k]))
    for k in order:
        st = _stats(groups[k])
        print(f"{k:<12}{st['trades']:>7}{st['win_rate']:>6.0f}%{st['net']:>+10,.0f}"
              f"{st['expectancy']:>+9,.0f}{st['best']:>+9,.0f}{st['worst']:>+9,.0f}")
    print("\nTags: " + " · ".join(f"{k} = {v}" for k, v in SETUP_TAGS.items()))
    small = [k for k in groups if len(groups[k]) < 10]
    if small:
        print(f"⚠️  Fewer than 10 trades in: {', '.join(small)}. Treat these numbers as early signals, not proof.")


def cmd_stats(month, by_setup=False):
    rows = load_trades()
    if month:
        rows = [r for r in rows if r["date"].startswith(month)]
    s = _stats(rows)
    if not s:
        print("No trades recorded yet."); return
    if by_setup:
        cmd_stats_by_setup(rows, f"— {month}" if month else "(all time)"); return
    print(f"JOURNAL STATS {'— ' + month if month else '(all time)'}\n" + _fmt_stats(s))
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(float(r["net_pnl"]))
    print("\nBy day:")
    running = 0
    for d in sorted(by_day):
        running += sum(by_day[d])
        print(f"  {d}  {len(by_day[d])} trade(s)  net ₹{sum(by_day[d]):+,.0f}   cumulative ₹{running:+,.0f}")


_SYM_RE = __import__("re").compile(r"^([A-Z]+?)(\d{2}[A-Z]{3}\d{2})(?:\d+(?:CE|PE)|FUT)$")


def _sym_parts(symbol):
    """'CRUDEOIL17NOV268050PE' → ('CRUDEOIL', date(2026, 11, 17)); None if not parseable."""
    m = _SYM_RE.match(symbol or "")
    if not m:
        return None
    try:
        return m.group(1), datetime.strptime(m.group(2), "%d%b%y").date()
    except ValueError:
        return None


def expiry_info(date, rows):
    """Is `date` an expiry day for the instruments traded (default CRUDEOIL)? Returns markdown lines."""
    import json
    d = datetime.strptime(date, "%Y-%m-%d").date()
    names = sorted({p[0] for p in (_sym_parts(r["symbol"]) for r in rows) if p}) or ["CRUDEOIL"]
    # expiries known from the traded symbols themselves (works for past dates)
    known = defaultdict(set)
    for r in rows:
        p = _sym_parts(r["symbol"])
        if p:
            kind = "FUT" if r["symbol"].endswith("FUT") else "options"
            known[(p[0], kind)].add(p[1])
    # plus the instrument cache built by quick_check.py (live contracts)
    cache = os.path.join(BASE_DIR, ".cache", "instruments.json")
    try:
        with open(cache, encoding="utf-8") as f:
            for m in json.load(f)["rows"]:
                if m["name"] in names and m.get("expiry"):     # spot-index rows have no expiry
                    kind = "FUT" if m["type"].startswith("FUT") else "options"
                    known[(m["name"], kind)].add(datetime.strptime(m["expiry"], "%d%b%Y").date())
    except (OSError, ValueError, KeyError):
        pass
    today_hits, upcoming = [], []
    for name in names:
        for kind in ("options", "FUT"):
            dates = sorted(known.get((name, kind), ()))
            if d in dates:
                today_hits.append(f"{name} {kind}")
            nxt = next((x for x in dates if x > d), None)
            if nxt:
                upcoming.append(f"{name} {kind} {nxt:%d %b} (in {(nxt - d).days} d)")
    expiring_trades = sum(1 for r in rows if (_sym_parts(r["symbol"]) or (None, None))[1] == d)
    if today_hits:
        line = f"**📅 Expiry day: YES**: {', '.join(today_hits)} expire today"
        if expiring_trades:
            line += f" · {expiring_trades} of {len(rows)} trades were in contracts expiring today (fast time decay)"
    else:
        line = "**📅 Expiry day: No**"
    if upcoming:
        line += f" · next: {', '.join(upcoming[:3])}"
    return [line, ""]


def is_expiry_day(date, rows):
    return any("YES" in l for l in expiry_info(date, rows))


def _day_summary(date, rows, all_rows):
    """Markdown block: P&L, charges breakdown, turnover, running totals."""
    gross = sum(float(r["gross_pnl"]) for r in rows)
    charges = sum(float(r["charges"]) for r in rows)
    net = gross - charges
    gross_profit = sum(float(r["gross_pnl"]) for r in rows if float(r["gross_pnl"]) > 0)
    gross_loss = sum(float(r["gross_pnl"]) for r in rows if float(r["gross_pnl"]) <= 0)
    buy_val = sum(float(r["entry_price"] if r["side"] == "LONG" else r["exit_price"]) * float(r["qty"]) for r in rows)
    sell_val = sum(float(r["exit_price"] if r["side"] == "LONG" else r["entry_price"]) * float(r["qty"]) for r in rows)
    max_cap = max(float(r["entry_price"]) * float(r["qty"]) for r in rows)
    bd = defaultdict(float)
    for r in rows:
        q = float(r["qty"])
        bv = float(r["entry_price"] if r["side"] == "LONG" else r["exit_price"]) * q
        sv = float(r["exit_price"] if r["side"] == "LONG" else r["entry_price"]) * q
        for k, v in charges_breakdown(r["segment"] or _segment(r["symbol"]), bv, sv, 2).items():
            bd[k] += v
    est = any(r["charges_source"] == "estimate" for r in rows)
    wins = sum(1 for r in rows if float(r["net_pnl"]) > 0)
    month = [r for r in all_rows if r["date"][:7] == date[:7] and r["date"] <= date]
    upto = [r for r in all_rows if r["date"] <= date]
    mtd = sum(float(r["net_pnl"]) for r in month)
    cum = sum(float(r["net_pnl"]) for r in upto)
    verdict = "🟢 PROFIT" if net > 0 else ("🔴 LOSS" if net < 0 else "⚪ FLAT")
    pct = f"{charges / gross_profit * 100:.0f}% of gross profit" if gross_profit else "—"
    L = ["## Day Summary", "",
         f"### {verdict}: Net ₹{net:+,.2f}", ""] + expiry_info(date, rows) + [
         "| P&L | Amount |", "|---|---:|",
         f"| Gross profit (winning trades) | ₹{gross_profit:+,.2f} |",
         f"| Gross loss (losing trades) | ₹{gross_loss:+,.2f} |",
         f"| **Gross P&L** | **₹{gross:+,.2f}** |",
         f"| Total charges{' (estimated)' if est else ''} | −₹{charges:,.2f} |",
         f"| **Net P&L** | **₹{net:+,.2f}** |",
         f"| Charges as share of profit | {pct} |", "",
         "| Charges breakdown (estimate) | Amount |", "|---|---:|",
         f"| Brokerage ({len(rows) * 2} orders × ₹{CHARGES['brokerage_per_order']:.0f}) | ₹{bd['brokerage']:,.2f} |",
         f"| Exchange transaction charges | ₹{bd['exchange_txn']:,.2f} |",
         f"| CTT (on sell side) | ₹{bd['ctt']:,.2f} |",
         f"| Stamp duty (on buy side) | ₹{bd['stamp']:,.2f} |",
         f"| SEBI fees | ₹{bd['sebi']:,.2f} |",
         f"| GST (18%) | ₹{bd['gst']:,.2f} |",
         f"| **Total** | **₹{sum(bd.values()):,.2f}** |", "",
         "| Activity | Value |", "|---|---:|",
         f"| Expiry day | {'Yes' if is_expiry_day(date, rows) else 'No'} |",
         f"| Trades (wins / losses) | {len(rows)} ({wins} / {len(rows) - wins}) |",
         f"| Win rate | {wins / len(rows) * 100:.0f}% |",
         f"| Units traded | {sum(int(float(r['qty'])) for r in rows):,} |",
         f"| Turnover (buy + sell value) | ₹{buy_val + sell_val:,.2f} |",
         f"| Largest capital in one trade | ₹{max_cap:,.2f} |",
         f"| Best trade (net) | ₹{max(float(r['net_pnl']) for r in rows):+,.2f} |",
         f"| Worst trade (net) | ₹{min(float(r['net_pnl']) for r in rows):+,.2f} |",
         f"| Month to date (net, {len(month)} trades) | ₹{mtd:+,.2f} |",
         f"| All time (net, {len(upto)} trades) | ₹{cum:+,.2f} |", ""]
    if est:
        L += ["_Charges are estimates until contract-note figures are entered. "
              "The breakdown is always the estimate model._", ""]
    return L


def write_daily(date, open_pos=None):
    os.makedirs(DAILY_DIR, exist_ok=True)
    path = os.path.join(DAILY_DIR, f"{date}.md")
    notes = ("\n## Market context\n- \n\n## What went well\n- \n\n"
             "## What to improve\n- \n\n## Plan for next session\n- \n")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            content = f.read()
        if NOTES_START in content:
            notes = content.split(NOTES_START, 1)[1]

    all_rows = load_trades()
    rows = [r for r in all_rows if r["date"] == date]
    s = _stats(rows)
    lines = [f"# Trading Journal — {datetime.strptime(date, '%Y-%m-%d'):%A, %d %b %Y}", ""]
    if s:
        lines += _day_summary(date, rows, all_rows)
        lines += ["### Stats", "", "```", _fmt_stats(s), "```", ""]
    lines += ["## Trades", "",
              "| ID | Symbol | Side | Qty | Entry | Exit | Gross | Charges | Net | Setup | Exit reason |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        ch = f"₹{float(r['charges']):.0f}" + ("*" if r["charges_source"] == "estimate" else "")
        lines.append(f"| {r['trade_id']} | {r['symbol']} | {r['side']} | {r['qty']} | "
                     f"{r['entry_price']} @ {r['entry_time']} | {r['exit_price']} @ {r['exit_time']} | "
                     f"₹{float(r['gross_pnl']):+,.0f} | {ch} | **₹{float(r['net_pnl']):+,.0f}** | "
                     f"{r['setup'] or '—'} | {r['exit_reason'] or '—'} |")
    if not rows:
        lines.append("| — | no closed trades | | | | | | | | | |")
    lines += ["", "\\* estimated charges — replace with contract-note figure: "
              "`python bots/trade_journal.py note <ID> --charges <amount>`"]
    if open_pos:
        lines += ["", "**⚠️ Open positions at sync time:** " +
                  ", ".join(f"{p['tradingsymbol']} {p['netqty']}" for p in open_pos)]
    for r in rows:
        if r["notes"]:
            lines += ["", f"**{r['trade_id']} notes:** {r['notes']}"]
    lines += ["", f"_Auto-generated from Angel One trade book · last sync {datetime.now():%d %b %Y %H:%M}_", "",
              NOTES_START]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + notes)
    print(f"Daily page: {path}")


def main():
    p = argparse.ArgumentParser(description="Trade journal")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync"); s.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    n = sub.add_parser("note"); n.add_argument("trade_id")
    n.add_argument("--setup"); n.add_argument("--exit", dest="exit_reason"); n.add_argument("--notes")
    n.add_argument("--charges", type=float)
    n.add_argument("--tag", help="setup tag: " + ", ".join(SETUP_TAGS))
    st = sub.add_parser("stats"); st.add_argument("--month")
    st.add_argument("--by-setup", action="store_true")
    sub.add_parser("excel")
    a = p.parse_args()
    if a.cmd == "sync":
        cmd_sync(a.date)
    elif a.cmd == "note":
        cmd_note(a.trade_id, a.setup, a.exit_reason, a.notes, a.charges, a.tag)
    elif a.cmd == "excel":
        update_excel()
    else:
        cmd_stats(a.month, a.by_setup)


if __name__ == "__main__":
    main()
