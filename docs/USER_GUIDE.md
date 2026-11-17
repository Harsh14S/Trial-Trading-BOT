# Trading Toolkit: User Guide

_Last updated: 17 Nov 2026_

## 1. Overview

The toolkit is a set of Python bots plus Claude Code slash commands for trading **MCX CRUDEOIL** options and futures on Angel One. NIFTY, BANKNIFTY and a few others are supported for checks and plans.

- **What it does:** fast live market checks, trade plans with entry, stop and targets, breakout and position alerts, daily risk limits, and a journal with P&L, charges and setup statistics.
- **What it never does:** place, modify or cancel orders. You place every order yourself in the Angel app.
- **Core idea:** plan the levels once, let alerts watch the market, act only on a clean setup, and stop when the Day Guard says so.

---

## 2. Daily routine

The evening runs on six commands: plan once, set alerts, wait for the beep, then act.

| Time (IST) | Command | Why |
|---|---|---|
| About 9:00 AM (optional) | `/plan` | Overnight move, bias and levels. No trading |
| About 7:45 PM | `/plan` | Tonight's levels plus long and short setups, prepared in advance |
| About 7:50 PM | `/watch` | Breakout alerts on the key levels. **Close the chart** |
| When an alert beeps | `/check` (or Claude re-checks automatically) | A BUY SIGNAL, or a WARNING that the breakout candle is extended and a retest entry is needed |
| Right after buying in the app | `/bought 8100PE 31.5`, then **place the stop in the app** | Starts the stop and target alerts, and warns if no stop order is pending |
| While in a trade | `/check` once per 5-minute candle | Decides hold, trail or exit |
| When finished | `/eod` | Locks the day, syncs the journal, writes the review, shows setup stats |

```
/plan → /watch → (wait for the beep) → /check → /bought … → /check → /eod
```

- **EIA Wednesdays:** the US inventory report lands at about 8:30 PM IST. Have nothing open into it. Run `/watch` after the release and trade the first clean 5-minute close.
- **Expiry nights:** after about 9:30 PM, expiring options lose value too fast for buyers. Stop by 9:30 PM, or use the future or next month's options.

---

## 3. Slash commands

The commands live in `.claude/commands/`. They're plain Markdown, so you can edit them to change behaviour. `/check`, `/trade`, `/bought`, `/watch` and `/plan` fetch live data with `bots/quick_check.py` **before** Claude starts, so replies come back in about 10–20 seconds.

| Command | What it does | Examples |
|---|---|---|
| `/check` | Live market check, ending with an action (WAIT, BUY SIGNAL, HOLD, EXIT and so on) | `/check` · `/check crudem` · `/check nifty` |
| `/trade` | Finds a trade. It runs the rule check first, then gives a LIMIT entry, stop, T1/T2, exit-by time and risk to reward | `/trade` · `/trade pe` · `/trade banknifty ce` · `/trade fut` |
| `/bought` | Logs your fill, sets the stop and targets, starts the position alert, and warns if no stop is in place | `/bought 8100PE 31.8` · `/bought nifty 25400CE 120` |
| `/watch` | Sets 5-minute close breakout alerts on key levels and plans both sides. You trade only when it beeps | `/watch` · `/watch below 8061 above 8110` · `/watch nifty` |
| `/plan` | Pre-session plan: bias, levels R3–S3, long and short setups, events and time windows | `/plan` · `/plan nifty` |
| `/eod` | Ends the day: locks it, syncs the journal, writes trade notes and the review, shows stats | `/eod` (close Excel first) |

### Instruments

The default is **CRUDEOIL**. Add the instrument name as the first word.

| Name | Instrument | Exchange | Lot |
|---|---|---|---|
| `crude` (default) | CRUDEOIL | MCX | 100 |
| `crudem` / `mini` | CRUDEOILM (Crude Mini) | MCX | 10 |
| `ng` / `ngm` | Natural Gas / NG Mini | MCX | as per contract |
| `nifty` | NIFTY | NFO | 65 |
| `banknifty` / `bnf` | BANKNIFTY | NFO | 30 |
| `finnifty`, `midcpnifty` | FINNIFTY, MIDCPNIFTY | NFO | as per contract |

Lot sizes and expiries are read from Angel's instrument master every day. After the market closes (3:30 PM for NFO, 11:30 PM for MCX), the next expiry is used automatically.

---

## 4. Day Guard (daily risk limits)

`bots/day_guard.py` reads today's Angel trade book live, across all instruments. Every `/check` shows its status at the bottom.

| State | When | Effect |
|---|---|---|
| **LOCKED** | 3 trades, or 2 losses, or net loss of ₹1,500 or more, or the day was called | No new entry ideas. Managing or exiting an open position is still allowed |
| **PROTECT** | Net profit of ₹500 or more | Green day: A+ setups only |
| **OK** | Otherwise | Normal |

```bash
python bots/day_guard.py                          # status
python bots/day_guard.py lock "called it a day"   # /eod does this automatically
python bots/day_guard.py unlock <reason>          # discouraged; a written reason is required
```

- The limits are constants at the top of `bots/day_guard.py`.
- The lock file is `journal/day_lock.json` and applies to today only.

---

## 5. Journal and setup stats

`bots/trade_journal.py` builds closed trades from Angel's trade book. **Close Excel before syncing.**

```bash
python bots/trade_journal.py sync                        # today → trades.csv + daily page + Excel
python bots/trade_journal.py note T20261117-2 --setup "PE on break of 8110" \
    --exit "target limit" --notes "..." --tag breakout --charges 63.5
python bots/trade_journal.py stats                       # all-time stats
python bots/trade_journal.py stats --month 2026-11
python bots/trade_journal.py stats --by-setup            # win rate and P&L per setup tag
```

### Daily page

Each `journal/daily/YYYY-MM-DD.md` page starts with a **Day Summary**:

- **P&L:** gross profit and loss, gross P&L, total charges, net P&L, and charges as a share of profit.
- **Charges breakdown:** brokerage, exchange charges, CTT, stamp duty, SEBI fees and GST.
- **Activity:** trades and win rate, units traded, turnover, largest capital used in one trade, and best and worst trade.
- **Running totals:** month to date and all time.

Your own notes are kept on every re-sync: market context, what went well, what to improve, and the plan for the next session. Charges are estimates until you enter the real figures from the contract note with `--charges`.

### Setup tags

| Tag | Meaning |
|---|---|
| `breakout` | 5-minute close through a key level or range edge, with volume |
| `retest` | Entry on a pullback retest of a broken level |
| `rejection` | Fade at a level that held (lower high, ceiling, floor) |
| `reversal` | Counter-trend turn after a stretch away from the EMA |
| `chase` | Late entry after the move, at an extreme, or a MARKET chase |
| `other` | Anything else |

**Results after 6 trades (16–17 Nov):**

| Setup | Trades | Win % | Net |
|---|---|---|---|
| breakout | 2 | 50% | +₹1,901 |
| rejection | 2 | 50% | −₹325 |
| chase | 2 | 0% | −₹1,638 |

Treat these as early signals until each setup has 10 or more trades.

---

## 6. Response types

Every reply starts with a header such as `## WAIT · CRUDEOIL: chop above support`. After that come trend, volume, a levels table, ATM CE/PE prices, scenarios, day status and an action line.

| Type | When | What you get |
|---|---|---|
| WAIT | No setup | Trigger levels that would create one |
| BUY SIGNAL | Clean setup | LIMIT entry, stop (trigger/limit), T1, T2, exit-by time, risk to reward, skip-if line, checklist |
| IN TRADE | Position open | Entry, LTP, P&L, stop status, targets, hold or trail |
| TARGET HIT | T1 or T2 reached | Book it, or trail the stop to entry |
| WARNING | Trade weakening | Exit rules based on the next 5-minute close |
| STOPPED OUT | Stop filled | Loss, day P&L, lesson, next step |
| RULE CHECK | Day Guard LOCKED | The broken rules, a market read only, no entry |
| DAY CLOSED | After `/eod` | Trades table, net P&L, lesson, tomorrow's plan |
| ORDER PROBLEM | API rejection | Step-by-step instructions to place the order in the app |

---

## 7. Best practices

1. **Let alerts do the watching.** `/watch` replaces checking every 2 minutes. Fewer checks mean fewer impulse trades.
2. **Trade the setup that pays you.** So far breakouts are +₹1,901 and chases are −₹1,638. Before any entry, ask yourself: is this a breakout or retest, or am I chasing?
3. **Trust the guard.** When it says LOCKED, you're done for the day.
4. **Tag every trade at `/eod`.** After about 20 trades, `stats --by-setup` shows which setups actually make money.
5. **One instrument per evening.** Crude is your market. Use NIFTY and BANKNIFTY checks for learning.
6. **Enter real charges weekly** from the contract notes, so net P&L is accurate.

### Rules

- 1 lot per trade.
- LIMIT orders only.
- Place the stop within 30 seconds of the fill.
- Max 3 trades.
- Stop after 2 losses.
- Once the day is called, it stays called.

### Avoid

| Don't | Do instead |
|---|---|
| Run `/check` every minute | Use `/watch` and wait for the beep |
| Buy at MARKET when the price is running | Use a LIMIT order, and accept a missed trade |
| Buy at the day low or high, or into resistance | Wait for a retest of the broken level |
| Re-enter on a level's third test | One trade per level |
| Buy expiring options after about 9:30 PM | Use the future or next month's options, or skip it |
| Ask for "one more trade" after calling the day | `/eod`, then close the app |

---

## 8. Weekly review (Sunday, 10 minutes)

```bash
python bots/trade_journal.py stats --month 2026-11
python bots/trade_journal.py stats --by-setup
```

Then ask Claude: **"review my week"**. It reads the daily pages and finds repeat mistakes, your best setup, and one rule to tighten.

---

## 9. Reference

### Files

| Path | Purpose |
|---|---|
| `bots/quick_check.py` | Fast live snapshot (about 5 s): fut, 5-minute candles plus EMA20, ATM chain, positions, orders, Day Guard |
| `bots/day_guard.py` | Daily limits and the lock |
| `bots/trade_alert.py` | Breakout and position alerts (popup and beep; never orders) |
| `bots/trade_journal.py` | Journal sync, notes, stats |
| `.claude/commands/*.md` | Slash command definitions |
| `journal/` | `trades.csv`, daily pages, `Trading_Journal.xlsx`, `day_lock.json` (gitignored) |
| `.cache/` | Angel session and daily instrument-token cache |

### Limits

| Item | Detail |
|---|---|
| MCX hours | 9:00 AM – 11:30 PM IST (11:55 PM during US winter time) |
| NSE hours | 9:15 AM – 3:30 PM IST |
| Angel API rate | About 3 calls per second |
| Quick check | About 5 s per run. The first run of the day takes about 20 s longer, to build the token cache |

### API static IP

Angel only accepts API orders from the IP registered in the SmartAPI portal (error **AG7002** otherwise). Your home IP is dynamic, so place orders in the app. Data, alerts and the journal work regardless.

To fix it permanently, either:
- get a static IP add-on from Airtel by calling 121 or 198, or
- run the order scripts from a small cloud server with a fixed IP.

### Next upgrades

- [ ] Static IP, so API orders and stops work
- [ ] Live terminal dashboard (WebSocket feed, refreshes every second)
- [ ] Backtester for the breakout setup
- [ ] Contract note import, for real charges
