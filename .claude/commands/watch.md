---
description: "Alert-driven trading: set candle-close breakout alerts on key levels (CRUDEOIL by default, or crudem / nifty / banknifty...). Trade only when it beeps"
argument-hint: "[crude|crudem|nifty|banknifty] [below <level>] [above <level>] [until HH:MM]"
allowed-tools: Bash(python bots/quick_check.py:*), Bash(python bots/trade_alert.py:*), Read
---
User request: $ARGUMENTS

Live snapshot (includes the DAY GUARD line):

!`python bots/quick_check.py $ARGUMENTS --candles 12 --strikes 1 2>&1 | grep -v "smartConnect\|in pool"`

Set up **alert-driven trading**: the user stops watching the screen and acts only when an alert fires.

1. **Guard first.** If the DAY GUARD says 🚫 LOCKED:
   - Don't set entry alerts.
   - Reply with a 🚫 RULE CHECK. If a position is open, offer `/bought`-style position alerts instead.
   - Stop there.
2. **Levels:**
   - Use `below` and `above` from the request if given.
   - Otherwise use the most recent `/plan` levels in this conversation, or the "Plan for next session" levels in the latest `journal/daily/*.md`.
   - Failing that, use the nearest clear support and resistance from the candles: recent swing high/low and the range edges.
   - Use the levels where a **5m close** would be a real breakout, not noise inside the range.
3. **Until:**
   - Use `until` from the request if given.
   - Otherwise default to 23:00 for MCX (or 21:30 on an options expiry day) and 15:00 for NFO.
4. **Start the alert in the background** (`run_in_background: true`), using the fut symbol and token and the ATM symbols from the snapshot:
   `python bots/trade_alert.py breakout --exchange <MCX|NFO> --token <fut token> --symbol <fut symbol> --below <L> --above <H> --until <HH:MM> --watch <ATM CE symbol> --watch <ATM PE symbol>`
   It beeps and shows a popup on a closed 5m candle beyond either level, then exits. It never places orders.
5. **Reply as `## 🔔 WATCHING · <INSTRUMENT>`** with:
   - A small table: 🔻 below level → PE idea · 🔺 above level → CE idea · ⏳ until.
   - The distance of each level from the price.
   - The planned trade for each side, so the user is ready: strike, LIMIT entry zone, SL, T1/T2. This is ATM ±0–1 strike, 1 lot.
   - One line: **"Close the chart. I'll tell you when it fires."**
6. **When the background alert completes** (task notification):
   - Re-run `python bots/quick_check.py <instrument>`.
   - Reply in the `/check` format as 🟢 BUY SIGNAL, or ⚠️ if the breakout candle is overextended (fill the retest-entry plan instead of chasing).
   - Respect the DAY GUARD.

**Contracts and expiries (from the snapshot, never from memory):**
- Use the fut and options named on the `Contracts:` line. For MCX that fut is the one the options are priced on; for NIFTY/BANKNIFTY the ATM is centred on spot.
- A future marked "not used" on a ⚠️ line is a different contract: don't take levels, trend or prices from it.
- Mention every ⚠️ line (expiry today/tomorrow, roll, options-vs-fut mismatch, stale data) in the reply.
- Take the session close and the EIA time from the `Session:` line.
- **Read top-down, like a multi-timeframe check:** the `Trend` table gives 1H, 30m and 5m (closed candles). Take the bias from 1H/30m and the timing from 5m. If 5m goes against 1H/30m, call it a pullback or counter-trend and say so. Use the 1H and 30m candles for swing levels.
- **OI levels:** the `OI` line gives the strikes with the most CE OI (resistance) and PE OI (support), plus PCR and the most traded strike. Put them in the 🧱 levels table next to the candle levels.
- Keep the reply in the usual decorated format; don't paste the raw tables.
