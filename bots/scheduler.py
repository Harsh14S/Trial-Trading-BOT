"""
Scheduler Agent
Runs all bots automatically on a schedule during market hours.
Run this once and leave it running — it manages everything else.

Schedule:
  09:15  Morning Briefing (portfolio summary + AI analysis)
  10:00  Watchlist Scanner (trading signals)
  12:00  Watchlist Scanner (midday scan)
  14:00  Watchlist Scanner (afternoon scan)
  15:00  Portfolio Analyst (closing review — deep analysis)
"""
import sys
import os
import schedule
import time
import traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

# ── Task registry ──────────────────────────────────────────────────────────────

def _run_safely(name, fn):
    """Run a bot function and catch errors so scheduler keeps going."""
    print(f"\n[{datetime.now().strftime('%H:%M')}] ▶  Starting: {name}")
    try:
        fn()
        print(f"[{datetime.now().strftime('%H:%M')}] ✅  Done: {name}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M')}] ❌  {name} failed: {e}")
        traceback.print_exc()


def task_morning():
    from bots.morning_briefing import run
    _run_safely("Morning Briefing", run)


def task_watchlist():
    from bots.watchlist_scanner import run
    _run_safely("Watchlist Scanner", run)


def task_deep_analysis():
    from bots.portfolio_analyst import run
    _run_safely("Portfolio Analyst", run)


# ── Schedule ───────────────────────────────────────────────────────────────────

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]

for day in WEEKDAYS:
    getattr(schedule.every(), day).at("09:15").do(task_morning)
    getattr(schedule.every(), day).at("10:00").do(task_watchlist)
    getattr(schedule.every(), day).at("12:00").do(task_watchlist)
    getattr(schedule.every(), day).at("14:00").do(task_watchlist)
    getattr(schedule.every(), day).at("15:00").do(task_deep_analysis)


# ── Main loop ──────────────────────────────────────────────────────────────────

def run():
    print("=" * 55)
    print("   SCHEDULER AGENT — RUNNING")
    print(f"   Started: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    print("=" * 55)
    print("\nScheduled tasks:")
    print("  09:15  Morning Briefing")
    print("  10:00  Watchlist Scanner")
    print("  12:00  Watchlist Scanner")
    print("  14:00  Watchlist Scanner")
    print("  15:00  Portfolio Analyst (deep)")
    print("\nPress Ctrl+C to stop.\n")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run()
