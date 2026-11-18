---
description: "Call it a day (all instruments: crude, crudem, nifty, banknifty...). Sync the journal, annotate trades, write the review, show stats"
allowed-tools: Bash(python bots/trade_journal.py:*), Bash(python bots/quick_check.py:*), Bash(python bots/day_guard.py:*), Read, Edit, Write
---
The day is over. Treat this as final: no more trade ideas today.

Lock the day (the guard will block new-entry ideas for the rest of today):

!`python bots/day_guard.py lock "eod" 2>&1 | grep -v "smartConnect\|in pool"`

Journal sync (Excel must be closed):

!`python bots/trade_journal.py sync 2>&1 | grep -v "smartConnect\|in pool"`

1. **Stop any running `trade_alert.py` background tasks.**
2. **Read today's `journal/daily/<today>.md`** and `journal/trades.csv`.
3. **Annotate each trade that has an empty setup.** Use what happened in this conversation:
   `python bots/trade_journal.py note <ID> --setup "..." --exit "..." --notes "..." --tag <breakout|retest|rejection|reversal|chase|other>`
4. **Fill in the notes section of the daily page**, below the NOTES marker:
   - Market context (key levels and moves, with times).
   - What went well.
   - What to improve: rule breaks such as MARKET orders, size, a missing SL, overtrading, chasing.
   - Plan for the next session: levels, events such as the EIA report on Wednesday (time from the snapshot's Session line: 9:00 PM IST in US winter, 8:00 PM in US summer), instruments.
5. **Re-run** `python bots/trade_journal.py sync`, then `python bots/trade_journal.py stats` and `python bots/trade_journal.py stats --by-setup`.
6. **Reply in the 🌙 DAY CLOSED format:**
   - Trades table with times.
   - Gross, charges, net.
   - Best and worst trade.
   - Key lesson.
   - Running totals.
   - Tomorrow's 3–4 bullet plan.
