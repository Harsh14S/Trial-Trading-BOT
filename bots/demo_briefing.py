"""
Demo Morning Briefing Bot
Uses sample portfolio data to test the full Gemini AI analysis pipeline.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from core.analysis import analyze, save_report

# ── Sample Portfolio Data ─────────────────────────────────────────────────────

DEMO_SESSION = {"name": "SAVALIYA HARSH FALGUNBHAI (DEMO)"}

DEMO_HOLDINGS = [
    {"tradingsymbol": "RELIANCE",   "quantity": 10, "averageprice": 2850.00, "ltp": 2920.50, "pnl":  705.00},
    {"tradingsymbol": "HDFCBANK",   "quantity": 15, "averageprice": 1680.00, "ltp": 1645.30, "pnl": -520.50},
    {"tradingsymbol": "TCS",        "quantity":  5, "averageprice": 3900.00, "ltp": 4120.00, "pnl": 1100.00},
    {"tradingsymbol": "INFY",       "quantity": 20, "averageprice": 1420.00, "ltp": 1398.75, "pnl": -425.00},
    {"tradingsymbol": "BHARTIARTL", "quantity": 25, "averageprice": 1050.00, "ltp": 1189.60, "pnl": 3490.00},
    {"tradingsymbol": "SBIN",       "quantity": 50, "averageprice":  780.00, "ltp":  762.40, "pnl": -880.00},
    {"tradingsymbol": "WIPRO",      "quantity": 30, "averageprice":  480.00, "ltp":  502.15, "pnl":  664.50},
    {"tradingsymbol": "ADANIENT",   "quantity":  8, "averageprice": 2650.00, "ltp": 2480.00, "pnl":-1360.00},
]

DEMO_POSITIONS = [
    {"tradingsymbol": "NIFTY24NOV23500CE", "netqty":  50, "netprice": 120.00, "ltp": 145.00, "pnl": 1250.00},
    {"tradingsymbol": "BANKNIFTY24NOV CE", "netqty": -25, "netprice": 210.00, "ltp": 198.50, "pnl":  287.50},
]

# ── Format Demo Portfolio ─────────────────────────────────────────────────────

def format_demo_portfolio():
    lines = []
    lines.append(f"DEMO PORTFOLIO REPORT")
    lines.append(f"Date : {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    lines.append(f"Name : {DEMO_SESSION['name']}")
    lines.append("")

    lines.append("HOLDINGS (Long-term):")
    total_invested = total_current = 0
    for h in DEMO_HOLDINGS:
        symbol   = h["tradingsymbol"]
        qty      = h["quantity"]
        avg      = h["averageprice"]
        ltp      = h["ltp"]
        pnl      = h["pnl"]
        pct      = ((ltp - avg) / avg * 100)
        total_invested += avg * qty
        total_current  += ltp * qty
        lines.append(f"  {symbol:<20} Qty:{qty:<5} Avg:₹{avg:<10.2f} LTP:₹{ltp:<10.2f} P&L:₹{pnl:<10.2f} ({pct:+.1f}%)")

    overall_pnl = total_current - total_invested
    overall_pct = (overall_pnl / total_invested * 100)
    lines.append(f"\n  Invested : ₹{total_invested:,.2f}")
    lines.append(f"  Current  : ₹{total_current:,.2f}")
    lines.append(f"  Overall  : ₹{overall_pnl:,.2f} ({overall_pct:+.1f}%)")
    lines.append("")

    lines.append("OPEN POSITIONS (F&O):")
    for p in DEMO_POSITIONS:
        symbol = p["tradingsymbol"]
        qty    = p["netqty"]
        avg    = p["netprice"]
        ltp    = p["ltp"]
        pnl    = p["pnl"]
        lines.append(f"  {symbol:<30} Qty:{qty:<6} Avg:₹{avg:<8.2f} LTP:₹{ltp:<8.2f} P&L:₹{pnl:.2f}")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("=" * 55)
    print("   MORNING BRIEFING BOT — DEMO MODE")
    print(f"   {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    print("=" * 55)
    print("⚠️  Using sample portfolio data (not your real account)\n")

    portfolio_text = format_demo_portfolio()
    print(portfolio_text)

    print("\n" + "=" * 55)
    print("🤖 GEMINI AI ANALYSIS")
    print("=" * 55 + "\n")

    try:
        mode, result = analyze(portfolio_text)

        if mode == "gemini":
            print(result)
            report_file = save_report("demo_briefing", portfolio_text, result)
            print(f"\n✅ Full report saved: {report_file}")
        else:
            print(f"📋 Saved for manual Claude.ai review: {result}")

    except Exception as e:
        print(f"❌ Gemini error: {e}")
        print("\n💡 Falling back to manual mode...")
        _, filepath = "manual", None
        from core.analysis import _save_for_manual, PROMPT
        filepath = _save_for_manual(portfolio_text, PROMPT)
        print(f"📋 Saved: {filepath}")
        print("   Open the file → copy → paste into claude.ai")

    print("\n" + "=" * 55)


if __name__ == "__main__":
    run()
