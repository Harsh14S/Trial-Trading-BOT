"""
Portfolio Analyst Bot
On-demand deep analysis of your holdings and positions.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.angel import connect, get_holdings, get_positions, format_portfolio_text
from core.analysis import analyze, save_report

PROMPT = """You are a senior Indian stock market portfolio manager.
Do a deep analysis of this portfolio:
1. Portfolio health score (1-10) with reasons
2. Sector-wise concentration risk
3. Stocks with high risk — suggest stop-loss levels
4. Stocks ready for profit booking — suggest target prices
5. Underperforming stocks — hold or exit?
6. Overall portfolio rebalancing suggestions
Use ₹ for all values. Be specific with price levels."""


def run():
    print("=" * 50)
    print("   PORTFOLIO ANALYST BOT")
    print("=" * 50)

    print("\n📡 Connecting to Angel One...")
    angel, session_data = connect()
    print(f"✅ Connected: {session_data.get('name')}")

    print("\n📊 Fetching portfolio...")
    holdings  = get_holdings(angel)
    positions = get_positions(angel)
    portfolio_text = format_portfolio_text(session_data, holdings, positions)
    print(portfolio_text)

    print("\n🔍 Running deep analysis...")
    mode, result = analyze(portfolio_text, prompt=PROMPT)

    if mode == "gemini":
        print("\n" + "=" * 50)
        print("🤖 DEEP ANALYSIS REPORT")
        print("=" * 50)
        print(result)
        report_file = save_report("portfolio_analysis", portfolio_text, result)
        print(f"\n✅ Report saved: {report_file}")
    else:
        print(f"\n📋 Saved for manual analysis: {result}")
        print("   Paste into claude.ai for deep portfolio review.")


if __name__ == "__main__":
    run()
