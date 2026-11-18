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
3. **Check today's events.** For crude: the EIA inventory report is on Wednesday; take its IST time from the snapshot's Session line (9:00 PM in US winter, 8:00 PM in US summer). For NIFTY and BANKNIFTY: weekly or monthly expiry, RBI and US data, the opening gap. Expiries come from the snapshot's Contracts and ⚠️ lines.
4. **Reply in this decorated format:**
   - `## 🗺 PLAN · <INSTRUMENT>: <date>`, followed by a one-line bias.
   - 🧱 Levels table: R3 to S3.
   - 🟢 Long setup and 🔴 short setup: trigger, instrument (nearest-expiry option or fut of that instrument), entry, stop, T1/T2.
   - ⏰ Time windows to trade and to avoid.
   - 🚫 Rules reminder: 3 trades max · stop after 2 losses · LIMIT only · stop placed straight after the fill.

**Contracts and expiries (from the snapshot, never from memory):**
- Use the fut and options named on the `Contracts:` line. For MCX that fut is the one the options are priced on; for NIFTY/BANKNIFTY the ATM is centred on spot.
- A future marked "not used" on a ⚠️ line is a different contract: don't take levels, trend or prices from it.
- Mention every ⚠️ line (expiry today/tomorrow, roll, options-vs-fut mismatch, stale data) in the reply.
- Take the session close and the EIA time from the `Session:` line.
- The `Trend (closed 5m, last 6):` line is the rule-based read on closed candles; base 📈 Trend on it.
