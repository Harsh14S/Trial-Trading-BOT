---
description: "Live market check (fast): CRUDEOIL by default, or crudem / nifty / banknifty / finnifty / ng. Decorated, detailed reply with an action"
argument-hint: "[crude | crudem | nifty | banknifty | finnifty | ng] [--strikes N]"
allowed-tools: Bash(python bots/quick_check.py:*), Bash(python bots/trade_alert.py:*), Read
---
Live market snapshot (already fetched, don't re-run unless it failed):

!`python bots/quick_check.py --candles 12 $ARGUMENTS 2>&1 | grep -v "smartConnect\|in pool"`

The first line of the snapshot shows the instrument and exchange, e.g. `[NIFTY · NFO]`. If no instrument was given, it's CRUDEOIL (MCX), which is the user's main market. Analyse that instrument and reply in the decorated, detailed check format:
- **Header:** `## <emoji> <TYPE> · <INSTRUMENT>: <short read>`, e.g. `## 🟡 WAIT · CRUDEOIL: chop above support`. TYPE is one of: WAIT, BUY SIGNAL, IN TRADE, TARGET HIT, WARNING, STOPPED OUT, RULE CHECK.
- **Quote line:** `> **⏱ time · <INSTRUMENT> <month> fut price** 🔻/🔺/➡️ distance from the 5m EMA20`.
- **📈 Trend:** higher or lower highs and lows over the last 3–4 candles, and support or resistance tests.
- **🔊 Volume:** the forming candle compared with recent candles.
- **🧱 Levels table:** R2, R1, S1, S2, each with the distance in points. Use levels from today's session context.
- **💹 ATM CE/PE table:** the change since the last check, if one exists in this conversation, plus a ⏳ time-decay note.
- **🔮 Scenarios:** up, down and sideways.
- **📒 Day:** trades out of 3, losses out of 2, day P&L. Use the journal or session context if known.
- **🎯 Action:** one clear line.

**If a position is open:**
- Show entry, LTP, P&L, the stop status (pending order or ⚠️ NONE), T1/T2 and the exit-by time.
- Say hold, exit or trail.

**For a new trade idea**, use the BUY SIGNAL table: entry LIMIT, 🛑 stop (trigger/limit), 🎯 T1, 🎯 T2, ⏳ exit by. Add ⚖️ risk to reward in ₹, a ⚠️ skip-if line, and a ✅ checklist.

**Rules:**
- Never place orders.
- **Use the DAY GUARD line at the end of the snapshot:**
  - 🚫 LOCKED → lead with the 🚫 RULE CHECK and give no entry ideas. Managing an open position is still fine.
  - 🟡 PROTECT → the day is green, so A+ setups only, and say so.
  - Use its trades, losses and net figures for the 📒 Day line.
- Keep it compact.

**Contracts and expiries (from the snapshot, never from memory):**
- Use the fut and options named on the `Contracts:` line. For MCX that fut is the one the options are priced on; for NIFTY/BANKNIFTY the ATM is centred on spot.
- A future marked "not used" on a ⚠️ line is a different contract: don't take levels, trend or prices from it.
- Mention every ⚠️ line (expiry today/tomorrow, roll, options-vs-fut mismatch, stale data) in the reply.
- Take the session close and the EIA time from the `Session:` line.
- **Read top-down, like a multi-timeframe check:** the `Trend` table gives 1H, 30m and 5m (closed candles). Take the bias from 1H/30m and the timing from 5m. If 5m goes against 1H/30m, call it a pullback or counter-trend and say so. Use the 1H and 30m candles for swing levels.
- **OI levels:** the `OI` line gives the strikes with the most CE OI (resistance) and PE OI (support), plus PCR and the most traded strike. Put them in the 🧱 levels table next to the candle levels.
- Keep the reply in the usual decorated format; don't paste the raw tables.
