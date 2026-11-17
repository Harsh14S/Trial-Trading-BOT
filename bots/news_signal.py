"""
News Signal Bot
Paste a news headline → Claude/Gemini tells you which stocks in your watchlist are impacted.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.analysis import analyze

WATCHLIST = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY",
    "ICICIBANK", "SBIN", "AXISBANK", "BHARTIARTL",
]


def run():
    print("=" * 50)
    print("   NEWS SIGNAL BOT")
    print("=" * 50)
    print(f"\nWatchlist: {', '.join(WATCHLIST)}")
    print("\nPaste a news headline (or press Enter to use example):")

    headline = input("> ").strip()
    if not headline:
        headline = "RBI keeps repo rate unchanged at 6.5%, maintains withdrawal of accommodation stance"

    print(f"\n📰 Analyzing: {headline}\n")

    prompt = f"""You are an Indian stock market expert.
News headline: "{headline}"
Watchlist stocks: {', '.join(WATCHLIST)}

For each stock that is impacted by this news:
- Stock name
- Impact: POSITIVE / NEGATIVE / NEUTRAL
- Reason (1 line)
- Suggested action (BUY / SELL / HOLD / WATCH)

If no stocks are impacted, reply: "No direct impact on watchlist."
Be concise and specific."""

    mode, result = analyze(headline, prompt=prompt)

    if mode == "gemini":
        print("🤖 AI SIGNAL:")
        print("=" * 50)
        print(result)
    else:
        print(f"📋 Saved for manual review: {result}")
        print("   Paste into claude.ai to get signal analysis.")


if __name__ == "__main__":
    run()
