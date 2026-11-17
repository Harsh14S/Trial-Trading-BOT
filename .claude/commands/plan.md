---
description: "Pre-session plan: CRUDEOIL by default, or crudem / nifty / banknifty / finnifty / ng. Levels, bias, events, trade setups"
argument-hint: "[crude | crudem | nifty | banknifty | finnifty | ng]"
allowed-tools: Bash(python bots/quick_check.py:*), Bash(python bots/crude_oil_tracker.py:*), Bash(python:*), Read
---
Current snapshot:

!`python bots/quick_check.py $ARGUMENTS --candles 12 --strikes 3 2>&1 | grep -v "smartConnect\|in pool"`

Build today's plan for the instrument in the snapshot's first line (default CRUDEOIL on MCX):
1. **Read the previous session's review:** the latest `journal/daily/*.md`, especially "Plan for next session" and "What to improve".
2. **Use 5m, 30m and 1h candles** to set the bias and key levels. Use `core.candles.get_candles` if more history is needed. Include the previous day's high, low and close and the overnight move.
3. **Check today's events.** For crude: the EIA inventory report is on Wednesday at about 8:30 PM IST. For NIFTY and BANKNIFTY: weekly or monthly expiry, RBI and US data, the opening gap. Also check the expiry dates of the nearest contracts.
4. **Reply in this decorated format:**
   - `## 🗺 PLAN · <INSTRUMENT>: <date>`, followed by a one-line bias.
   - 🧱 Levels table: R3 to S3.
   - 🟢 Long setup and 🔴 short setup: trigger, instrument (nearest-expiry option or fut of that instrument), entry, stop, T1/T2.
   - ⏰ Time windows to trade and to avoid.
   - 🚫 Rules reminder: 3 trades max · stop after 2 losses · LIMIT only · stop placed straight after the fill.
