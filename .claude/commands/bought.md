---
description: "Log an entry and start the position alert, for any instrument (crude, crudem, nifty, banknifty...). Usage /bought [instrument] <strike+CE/PE> <price> [qty]"
argument-hint: "[crude|crudem|nifty|banknifty] <8100PE> <price> [qty=1 lot]"
allowed-tools: Bash(python bots/quick_check.py:*), Bash(python bots/trade_alert.py:*), Read
---
The user just bought: $ARGUMENTS

Current state:

!`python bots/quick_check.py $ARGUMENTS --candles 4 2>&1 | grep -v "smartConnect\|in pool"`

0. **Check the DAY GUARD line.** If it was already 🚫 LOCKED before this entry, the fill breaks the rules. Still set the stop and alert (protect the position first), then add a one-line 🚫 note: "this trade broke the day lock". Ask the user for the setup tag (breakout, retest, rejection, reversal, chase or other) so it can go in the journal.
1. **Resolve the full trading symbol.** The instrument is in the snapshot's first line, e.g. `[NIFTY · NFO]`, and defaults to CRUDEOIL on MCX. Short forms like `8100PE` or `25400 CE` mean that instrument's nearest-expiry option shown above. Default qty is 1 lot (the lot size shown above). Confirm the fill against the open positions (average price).
2. **Set the stop:**
   - About ₹700 risk per lot, or the level from the plan given earlier in this conversation.
   - Tie it to a fut level beyond the nearest support or resistance.
   - Set T1 and T2 at fut levels.
3. **Start the alert in the background** (`run_in_background`). It never places orders:
   `python bots/trade_alert.py position --exchange <MCX|NFO> --symbol <SYM> --entry <px> --qty <qty> --sl <sl> --t1 <t1> --t2 <t2> --until <HH:MM> --fut-token <fut token> --fut-symbol <fut symbol>`
   For a PE, add `--fail-above <fut level>`.
4. **Reply as 🔵 IN TRADE:**
   - Entry, LTP, P&L.
   - **⚠️ If no stop order is pending, put this first, in bold:** "Place SL now: SELL <qty> <SYM> SL-LIMIT trigger ₹X / limit ₹X-1".
   - The table: stop / T1 / T2 / fut / exit-by.
   - What to do at T1: book it, or trail the stop to entry.

**Contracts and expiries (from the snapshot, never from memory):**
- Use the fut and options named on the `Contracts:` line. For MCX that fut is the one the options are priced on; for NIFTY/BANKNIFTY the ATM is centred on spot.
- A future marked "not used" on a ⚠️ line is a different contract: don't take levels, trend or prices from it.
- Mention every ⚠️ line (expiry today/tomorrow, roll, options-vs-fut mismatch, stale data) in the reply.
- Take the session close and the EIA time from the `Session:` line.
- The `Trend (closed 5m, last 6):` line is the rule-based read on closed candles; base 📈 Trend on it.
