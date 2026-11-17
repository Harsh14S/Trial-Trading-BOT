"""
Watchlist Scanner Agent
Scans your watchlist stocks for trading signals using Gemini AI.
Fetches live prices, computes basic technical signals, and asks Gemini for opportunities.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from core.angel import connect, get_ltp
from core.analysis import analyze, save_report

# ── Your watchlist ─────────────────────────────────────────────────────────────
# Format: (exchange, symbol, token, avg_cost)
# avg_cost: your average buy price (for P&L calc), or None if you don't hold it.
WATCHLIST = [
    ("NSE", "RELIANCE-EQ",   "2885",  2850.0),
    ("NSE", "TCS-EQ",        "11536", 3900.0),
    ("NSE", "HDFCBANK-EQ",   "1333",  1680.0),
    ("NSE", "INFY-EQ",       "1594",  1420.0),
    ("NSE", "BHARTIARTL-EQ", "10604", 1050.0),
    ("NSE", "SBIN-EQ",       "3045",   780.0),
    ("NSE", "WIPRO-EQ",      "3787",   480.0),
    ("NSE", "ADANIENT-EQ",   "25",    2650.0),
    ("NSE", "ICICIBANK-EQ",  "4963",  None),
    ("NSE", "AXISBANK-EQ",   "5900",  None),
]

SCAN_PROMPT = """You are an experienced Indian stock market trader.
I've scanned my watchlist and fetched live prices. Based on current price levels and typical market behavior:

1. Which stocks look like BUY opportunities right now? (trading below value)
2. Which stocks should I book profits on? (trading at highs or above targets)
3. Which stocks show caution signals? (momentum reversing or risky)
4. Any specific intraday opportunities for today?

For each call, give the stock name, current price, and a one-line reason.
Be direct and actionable. Use ₹ for prices."""


def fetch_watchlist_prices(angel):
    """Fetch live prices for all watchlist stocks."""
    rows = []
    for exchange, symbol, token, avg_cost in WATCHLIST:
        try:
            ltp = get_ltp(angel, exchange, symbol, token)
            pct = ((ltp - avg_cost) / avg_cost * 100) if avg_cost else None
            rows.append({
                "symbol":   symbol.replace("-EQ", ""),
                "ltp":      ltp,
                "avg_cost": avg_cost,
                "pct":      pct,
            })
        except Exception as e:
            rows.append({
                "symbol":   symbol.replace("-EQ", ""),
                "ltp":      None,
                "avg_cost": avg_cost,
                "pct":      None,
                "error":    str(e),
            })
    return rows


def format_watchlist_text(rows):
    """Format watchlist data as readable text for AI."""
    lines = []
    lines.append(f"WATCHLIST SCAN — {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    lines.append("")
    lines.append(f"{'Stock':<20} {'LTP':>10}  {'Avg Cost':>10}  {'Change':>8}")
    lines.append("-" * 55)
    for r in rows:
        if r.get("error"):
            lines.append(f"  {r['symbol']:<18}  ERROR: {r['error']}")
            continue
        ltp_str  = f"₹{r['ltp']:,.2f}"   if r["ltp"]      else "N/A"
        avg_str  = f"₹{r['avg_cost']:,.2f}" if r["avg_cost"] else "N/A"
        pct_str  = f"{r['pct']:+.1f}%"   if r["pct"] is not None else "—"
        lines.append(f"  {r['symbol']:<18}  {ltp_str:>10}  {avg_str:>10}  {pct_str:>8}")
    return "\n".join(lines)


def run():
    print("=" * 55)
    print("   WATCHLIST SCANNER")
    print(f"   {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    print("=" * 55)

    print("\n📡 Connecting to Angel One...")
    angel, session_data = connect()
    print(f"✅ Connected: {session_data.get('name')}")

    print(f"\n📊 Scanning {len(WATCHLIST)} stocks...\n")
    rows = fetch_watchlist_prices(angel)
    watchlist_text = format_watchlist_text(rows)
    print(watchlist_text)

    print("\n" + "=" * 55)
    print("🤖 AI SIGNAL ANALYSIS")
    print("=" * 55 + "\n")

    mode, result = analyze(watchlist_text, prompt=SCAN_PROMPT)

    if mode == "gemini":
        print(result)
        report_file = save_report("watchlist_scan", watchlist_text, result)
        print(f"\n✅ Report saved: {report_file}")
    else:
        print(f"📋 Saved for manual Claude.ai review: {result}")
        print("   Paste into claude.ai to get signal analysis.")

    print("\n" + "=" * 55)


if __name__ == "__main__":
    run()
