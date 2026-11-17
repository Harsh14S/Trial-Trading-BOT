"""
Price Alert Agent
Monitor specific stocks and alert when they hit your target or stop-loss prices.
Run continuously (every 5 minutes) during market hours, or run once for a spot check.
"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from core.angel import connect, get_ltp

# ── Configure your alerts here ────────────────────────────────────────────────
# Format: (exchange, symbol, token, buy_below, sell_above)
# token: find it on Angel One's symbol search API or SmartAPI symbol list
# Set buy_below=None or sell_above=None to skip that direction.
ALERTS = [
    # Exchange    Symbol          Token     Buy below   Sell above
    ("NSE",      "RELIANCE-EQ",  "2885",   2800.0,     3000.0),
    ("NSE",      "TCS-EQ",       "11536",  3850.0,     4200.0),
    ("NSE",      "HDFCBANK-EQ",  "1333",   1600.0,     1720.0),
    ("NSE",      "BHARTIARTL-EQ","10604",  1100.0,     1250.0),
    ("NSE",      "INFY-EQ",      "1594",   1350.0,     1450.0),
]

SCAN_INTERVAL_MINUTES = 5  # how often to re-check prices


def _now():
    return datetime.now().strftime("%I:%M %p")


def _is_market_hours():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    return (now.hour, now.minute) >= (9, 15) and (now.hour, now.minute) < (15, 30)


def check_alerts(angel):
    """Check all configured alerts once and print triggered ones."""
    triggered = []
    not_triggered = []

    for exchange, symbol, token, buy_below, sell_above in ALERTS:
        try:
            ltp = get_ltp(angel, exchange, symbol, token)
        except Exception as e:
            print(f"  ⚠️  {symbol}: could not fetch price — {e}")
            continue

        alerts_hit = []
        if buy_below is not None and ltp <= buy_below:
            alerts_hit.append(f"BUY signal  — LTP ₹{ltp:.2f} ≤ target ₹{buy_below:.2f}")
        if sell_above is not None and ltp >= sell_above:
            alerts_hit.append(f"SELL signal — LTP ₹{ltp:.2f} ≥ target ₹{sell_above:.2f}")

        if alerts_hit:
            triggered.append((symbol, ltp, alerts_hit))
        else:
            not_triggered.append((symbol, ltp, buy_below, sell_above))

    return triggered, not_triggered


def run(loop=False):
    print("=" * 55)
    print("   PRICE ALERT AGENT")
    print(f"   {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    print("=" * 55)

    if not ALERTS:
        print("\n⚠️  No alerts configured.")
        print("   Edit the ALERTS list in bots/price_alert.py")
        return

    print("\n📡 Connecting to Angel One...")
    angel, session_data = connect()
    print(f"✅ Connected: {session_data.get('name')}")

    print(f"\n📋 Watching {len(ALERTS)} stocks\n")

    while True:
        if not _is_market_hours() and loop:
            print(f"[{_now()}] Market closed. Sleeping until 9:15 AM...")
            time.sleep(60 * 15)
            continue

        triggered, not_triggered = check_alerts(angel)

        print(f"\n[{_now()}] SCAN RESULTS")
        print("-" * 45)

        if triggered:
            print("🔔 ALERTS TRIGGERED:")
            for symbol, ltp, signals in triggered:
                for sig in signals:
                    print(f"   ⚡ {symbol:<20} {sig}")
        else:
            print("   No alerts triggered.")

        print("\n📊 Current prices (no alert):")
        for symbol, ltp, buy_below, sell_above in not_triggered:
            buy_str  = f"buy<₹{buy_below:.0f}"   if buy_below  else "no buy"
            sell_str = f"sell>₹{sell_above:.0f}"  if sell_above else "no sell"
            print(f"   {symbol:<22} ₹{ltp:<10.2f} [{buy_str} | {sell_str}]")

        if not loop:
            break

        print(f"\n   Next scan in {SCAN_INTERVAL_MINUTES} min...")
        time.sleep(SCAN_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Price Alert Agent")
    parser.add_argument("--loop", action="store_true", help="Run continuously every 5 minutes")
    args = parser.parse_args()
    run(loop=args.loop)
