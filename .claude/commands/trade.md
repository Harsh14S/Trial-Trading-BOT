---
description: "Find a trade now: CRUDEOIL by default, or crudem / nifty / banknifty / finnifty / ng (CE/PE or futures) with entry, stop and targets"
argument-hint: "[crude | crudem | nifty | banknifty | finnifty | ng] [ce|pe|fut]"
allowed-tools: Bash(python bots/quick_check.py:*), Bash(python bots/trade_journal.py stats:*), Bash(python bots/day_guard.py:*), Read
---
Live market snapshot:

!`python bots/quick_check.py $ARGUMENTS --candles 10 --strikes 3 2>&1 | grep -v "smartConnect\|in pool"`

Preference from the user (may be empty): $ARGUMENTS

The snapshot's first line shows the instrument and exchange, e.g. `[CRUDEOIL · MCX]`. The default is CRUDEOIL, the user's main market. Find the best trade in **that instrument** right now, if there is one: nearest-expiry options of the instrument, unless the user said fut. Put the instrument in the header, e.g. `## 🟢 BUY SIGNAL · NIFTY`. Use the lot size shown in the snapshot for ₹ risk and reward.

1. **🚫 Rule check first. Use the DAY GUARD line at the end of the snapshot** (it's computed live from the trade book):
   - **🚫 LOCKED:** reply with the 🚫 RULE CHECK table and the reasons. Give a short market read, but **no entry plan**. Point out that `python bots/day_guard.py unlock <reason>` exists, but advise against using it.
   - **🟡 PROTECT:** the day is green. Only suggest an A+ setup (a clean breakout, or a retest, with volume). Otherwise say WAIT.
   - **Use setup history:** run `python bots/trade_journal.py stats --by-setup` if it's not already in context. Prefer setups with a positive record. **Never suggest a `chase`-type entry.**
2. **If there's no clean setup:** reply as a 🟡 WAIT with the exact trigger levels that would create one.
3. **If there is a setup:** reply as a 🟢 BUY SIGNAL:
   - Trend, volume and levels.
   - The table: entry **LIMIT** range, 🛑 SL trigger/limit (with the fut level), 🎯 T1 / 🎯 T2 (₹ and fut level), ⏳ exit-by time.
   - ⚖️ Risk to reward in ₹. Aim for about ₹700–1,000 risk on 1 lot.
   - ⚠️ Skip-if: a fail level and a don't-chase price.
   - ✅ Checklist: 1 lot · LIMIT · SL placed right after the fill.
4. **Wording:** never say "buy now at market". Never place orders: the user places them in the Angel app (the API IP isn't whitelisted).

**Contracts and expiries (from the snapshot, never from memory):**
- Use the fut and options named on the `Contracts:` line. For MCX that fut is the one the options are priced on; for NIFTY/BANKNIFTY the ATM is centred on spot.
- A future marked "not used" on a ⚠️ line is a different contract: don't take levels, trend or prices from it.
- Mention every ⚠️ line (expiry today/tomorrow, roll, options-vs-fut mismatch, stale data) in the reply.
- Take the session close and the EIA time from the `Session:` line.
- The `Trend (closed 5m, last 6):` line is the rule-based read on closed candles; base 📈 Trend on it.
