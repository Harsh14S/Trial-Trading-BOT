"""
F&O Position Tracker
Live monitor of all your open Futures & Options positions.
Shows P&L, days to expiry, lot value, and Gemini AI analysis on your F&O book.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date
from core.angel import connect, get_positions
from core.analysis import analyze, save_report

FO_PROMPT = """You are a senior F&O (Futures & Options) trader and risk manager.

Analyze this F&O position book:

1. **Overall Risk Assessment**
   - Net delta exposure (bullish or bearish bias)
   - Theta decay risk (which positions are losing value daily)
   - Vega exposure (volatility risk)

2. **Positions to Close Immediately**
   - Near-expiry positions with time decay accelerating
   - Losing positions where thesis has changed
   - Recommend: close at market or set limit

3. **Positions to Hold / Roll**
   - Which to hold till expiry
   - Which to roll to next month (and suggested strike/contract)

4. **Overnight Risk**
   - What global events (US market, OPEC, Fed) could gap this portfolio

5. **One-line action for each position**

Use ₹ for all values. Be specific about strike prices, expiry dates."""


def parse_expiry(symbol):
    """Try to extract expiry date from F&O symbol string."""
    import re
    # Format examples: NIFTY23NOV26FUT, BANKNIFTY17NOV2624000CE, CRUDEOIL19NOV26FUT
    months = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
               "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
    m = re.search(r"(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})", symbol.upper())
    if m:
        day, mon, yr = int(m.group(1)), months[m.group(2)], 2000 + int(m.group(3))
        try:
            exp = date(yr, mon, day)
            dte = (exp - date.today()).days
            return exp.strftime("%d %b %Y"), dte
        except Exception:
            pass
    return None, None


def classify_instrument(symbol):
    sym = symbol.upper()
    if sym.endswith("FUT"):
        return "FUT"
    if sym.endswith("CE"):
        return "CE"
    if sym.endswith("PE"):
        return "PE"
    return "?"


def run():
    print("=" * 60)
    print("   F&O POSITION TRACKER")
    print(f"   {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    print("=" * 60)

    print("\n📡 Connecting to Angel One...")
    angel, session_data = connect()
    print(f"✅ Connected: {session_data.get('name')}")

    print("\n📊 Fetching F&O positions...")
    positions = get_positions(angel)

    # Filter to F&O only (NFO + MCX futures/options)
    fo_pos = [p for p in positions if p.get("exchange") in ("NFO", "MCX", "BFO", "CDS")]
    if not fo_pos:
        fo_pos = positions  # show all if no exchange filter matches

    if not fo_pos:
        print("\n⚠️  No open F&O positions found.")
        print("   Buy/sell a futures or options contract to track it here.")
        return

    # ── Display ──────────────────────────────────────────────────────────────
    print(f"\nOpen F&O positions: {len(fo_pos)}\n")
    print(f"{'Symbol':<30} {'Type':<4} {'Qty':>6} {'Avg':>10} {'LTP':>10} {'P&L':>12} {'Expiry':<15} {'DTE':>5}")
    print("-" * 100)

    total_pnl = 0
    lines_for_ai = []

    for p in fo_pos:
        symbol = p.get("tradingsymbol", "")
        qty    = int(p.get("netqty", 0))
        avg    = float(p.get("netprice", 0))
        ltp    = float(p.get("ltp", 0))
        pnl    = float(p.get("pnl", 0))
        inst   = classify_instrument(symbol)
        expiry_str, dte = parse_expiry(symbol)

        total_pnl += pnl
        exp_disp = expiry_str or "?"
        dte_disp = str(dte) if dte is not None else "?"

        pnl_str = f"₹{pnl:>+,.0f}"
        print(f"{symbol:<30} {inst:<4} {qty:>6} ₹{avg:>9,.2f} ₹{ltp:>9,.2f} {pnl_str:>12} {exp_disp:<15} {dte_disp:>5}d")

        lines_for_ai.append(
            f"  {symbol}  Type:{inst}  Qty:{qty}  Avg:₹{avg:.2f}  LTP:₹{ltp:.2f}  "
            f"P&L:₹{pnl:+,.0f}  Expiry:{exp_disp}  DTE:{dte_disp}d"
        )

    print("-" * 100)
    pnl_color = "PROFIT" if total_pnl >= 0 else "LOSS"
    print(f"{'TOTAL F&O P&L':<52} ₹{total_pnl:>+,.0f}  ({pnl_color})")

    # ── AI analysis ──────────────────────────────────────────────────────────
    fo_text = f"F&O POSITION BOOK — {datetime.now().strftime('%d %b %Y, %I:%M %p')}\n"
    fo_text += f"Account: {session_data.get('name')}\n"
    fo_text += f"Total positions: {len(fo_pos)}\n"
    fo_text += f"Total P&L: ₹{total_pnl:+,.0f}\n\n"
    fo_text += "Positions:\n" + "\n".join(lines_for_ai)

    print("\n" + "=" * 60)
    print("🤖 GEMINI F&O ANALYSIS")
    print("=" * 60 + "\n")

    mode, result = analyze(fo_text, prompt=FO_PROMPT)
    if mode == "gemini":
        print(result)
        report_file = save_report("fo_positions", fo_text, result)
        print(f"\n✅ Report saved: {report_file}")
    else:
        print(f"📋 Saved for manual review: {result}")

    print("\n" + "=" * 60)
    print("⚠️  F&O positions carry leverage risk. Always maintain sufficient margin.")


if __name__ == "__main__":
    run()
