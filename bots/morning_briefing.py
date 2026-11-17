"""
Morning Briefing Bot
Run every weekday at 9:15 AM.
Fetches portfolio from Angel One and analyzes with Gemini (or saves for Claude.ai).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from core.angel import connect, get_holdings, get_positions, format_portfolio_text
from core.analysis import analyze, save_report


def run():
    print("=" * 50)
    print("   MORNING BRIEFING BOT")
    print(f"   {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    print("=" * 50)

    # Connect
    print("\n📡 Connecting to Angel One...")
    angel, session_data = connect()
    print(f"✅ Connected: {session_data.get('name')}")

    # Fetch data
    print("\n📊 Fetching portfolio...")
    holdings  = get_holdings(angel)
    positions = get_positions(angel)
    portfolio_text = format_portfolio_text(session_data, holdings, positions)
    print(portfolio_text)

    # Check if portfolio is empty
    if not holdings and not positions:
        print("\n⚠️  No holdings or positions found in your account.")
        print("   Your Angel One account may not have any trades yet.")
        print("   Add stocks to your portfolio and run again.\n")
        return

    # Analyze
    print("\n" + "=" * 50)
    mode, result = analyze(portfolio_text)

    if mode == "gemini":
        print("🤖 GEMINI AI ANALYSIS")
        print("=" * 50)
        print(result)
        report_file = save_report("morning_briefing", portfolio_text, result)
        print(f"\n✅ Report saved: {report_file}")

    else:
        print("📋 MANUAL MODE — No Gemini key detected")
        print("=" * 50)
        print(f"✅ File saved: {result}")
        print("\n   Steps:")
        print("   1. Open the file above")
        print("   2. Select all (Ctrl+A) → Copy (Ctrl+C)")
        print("   3. Paste into claude.ai")
        print("   4. Hit Enter for full analysis")

    print("\n" + "=" * 50)


if __name__ == "__main__":
    run()
