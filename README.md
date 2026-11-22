# Angel One + AI Trading Bot
**Account:** Harsh (<YOUR_CLIENT_ID>) | **Setup Date:** 14 Nov 2026

---

> 📘 **Daily usage guide:** [docs/USER_GUIDE.md](docs/USER_GUIDE.md): routine, slash commands, Day Guard, journal, best practices.

## Overview

This project connects **Angel One SmartAPI** with **Google Gemini AI** to build intelligent trading tools for the Indian stock and commodity markets. The AI reads live prices, options chains, and portfolio data, then gives plain-English insights and trade strategies. You always approve before any order is placed.

---

## Project Structure

```
A:\Project\Tr\
├── .env                        ← All credentials (never commit)
├── .gitignore                  ← Protects credentials & junk
├── README.md                   ← This file
├── Credentials.md              ← Human-readable credential reference
├── requirements.txt            ← All Python dependencies
├── lib_manager.py              ← Interactive package manager
│
├── .claude/commands/           ← Claude Code slash commands (/check /trade /bought /watch /plan /eod)
├── .cache/                     ← Angel session + daily instrument-token cache (auto)
│
├── config/
│   └── settings.py             ← Central config (loads from .env)
│
├── core/
│   ├── angel.py                ← Angel One connection (cached daily session) & data fetching
│   ├── candles.py              ← 5m/30m/1h candles, EMA20, rule-based momentum
│   └── analysis.py             ← Gemini AI or manual Claude.ai fallback
│
├── bots/
│   ├── morning_briefing.py     ← Daily 9:15 AM portfolio summary (live)
│   ├── demo_briefing.py        ← Demo mode with sample portfolio data
│   ├── portfolio_analyst.py    ← Deep on-demand portfolio review
│   ├── news_signal.py          ← News impact on watchlist stocks
│   ├── watchlist_scanner.py    ← Scan watchlist for live buy/sell signals
│   ├── price_alert.py          ← Alert when stocks hit your target prices
│   ├── gtt_manager.py          ← Create/list/cancel GTT orders via API
│   ├── fo_tracker.py           ← Live F&O positions monitor with AI analysis
│   ├── options_chain.py        ← NIFTY/BANKNIFTY/Crude options chain viewer
│   ├── crude_oil_tracker.py    ← MCX crude vs NYMEX WTI + USD/INR + AI call
│   ├── mf_tracker.py           ← Mutual fund P&L via AMFI NAV + Gemini AI
│   ├── backtester.py           ← 🧪 Strategy backtests (MA crossover, breakout) with costs
│   ├── day_guard.py            ← 🔒 Live daily limits (3 trades / 2 losses / ₹1,500 / day called)
│   ├── quick_check.py          ← ⚡ Fast one-shot market check (crude/nifty/banknifty…, ~5 s)
│   ├── trade_alert.py          ← Candle-close breakout + open-position SL/target alerts
│   ├── trade_journal.py        ← Daily trade journal from Angel trade book (+ Excel)
│   ├── journal_excel.py        ← Excel workbook builder for the journal
│   └── scheduler.py            ← Runs all bots automatically on schedule
│
├── journal/                    ← trades.csv, daily/YYYY-MM-DD.md, Trading_Journal.xlsx (gitignored)
├── reports/                    ← Auto-saved analysis reports
├── logs/                       ← Bot activity logs
└── tests/
    └── test_connection.py      ← Angel One connection test
```

---

## Credentials

Stored in `.env` (loaded automatically). Reference copy in `Credentials.md`. Never share or push to GitHub.

| Variable | Description |
|----------|-------------|
| `ANGEL_API_KEY` | Angel One SmartAPI key |
| `ANGEL_CLIENT_ID` | Angel One login ID (<YOUR_CLIENT_ID>) |
| `ANGEL_PASSWORD` | 4-digit MPIN |
| `ANGEL_TOTP_KEY` | 16-char TOTP secret for Google Authenticator |
| `GEMINI_API_KEY` | Google Gemini API key (starts with `AQ.`) |

---

## Setup

### Step 1 — Install Dependencies

Using the Library Manager (recommended):
```bash
python lib_manager.py
# Choose [2] Install missing packages
# Choose [1] to verify all packages
```

Or directly:
```bash
python -m pip install -r requirements.txt
```

#### Library Manager Options

| Option | Action |
|--------|--------|
| `[1]` | Check status of all packages (version + installed/missing) |
| `[2]` | Install only missing packages |
| `[3]` | Install all project packages fresh |
| `[4]` | Update all packages to latest versions |
| `[5]` | Install a new package + auto-add to requirements.txt |
| `[6]` | Uninstall a package (with confirmation) |
| `[7]` | Export exact versions of all installed packages to requirements.txt |
| `[8]` | Upgrade pip itself |

### Step 2 — Configure Credentials

Copy the template to `.env` and fill in your values. The template has instructions for where to find each key.
```powershell
Copy-Item .env.example .env      # PowerShell
cp .env.example .env             # Git Bash / macOS / Linux
```
```
ANGEL_API_KEY=your_api_key_here       # SmartAPI → My Apps → API Key
ANGEL_CLIENT_ID=your_client_id_here   # Angel One login ID
ANGEL_PASSWORD=your_mpin_here         # login MPIN
ANGEL_TOTP_KEY=your_totp_secret_here  # TOTP secret (base32), not the 6-digit code
GEMINI_API_KEY=your_gemini_api_key_here   # optional
```
`.env` is gitignored, so only `.env.example` (placeholders) is committed.
On a new PC, also register that PC's public IP in SmartAPI if you want API orders (error AG7002 otherwise).

### Step 3 — Test Connection

```bash
python tests/test_connection.py
```

Expected output:
```
✅ Connected: SAVALIYA HARSH FALGUNBHAI
   Holdings : X stocks
   Positions: X open
✅ All tests passed!
```

---

## Analysis Modes

This project supports two analysis modes. It auto-detects which to use based on `.env`.

| Mode | When | How |
|------|------|-----|
| **Manual** | No Gemini key set | Bot saves a `.txt` file → you paste into claude.ai |
| **Gemini Auto** | Gemini key set in `.env` | Bot auto-analyzes with AI and saves full report |

To switch modes, simply add or remove `GEMINI_API_KEY` in `.env` — no code changes needed.

### Get Free Gemini API Key
1. Go to **aistudio.google.com/api-keys**
2. Sign in with Google → **"+ Create API key"**
3. Select a project → **"Create API key"**
4. Copy the key (starts with `AQ.`)
5. Add to `.env`: `GEMINI_API_KEY=AQ.xxxxxxxx`
- Free tier: **1,500 requests/day**, no credit card needed

> **Note:** Newer Gemini API keys start with `AQ.` (not `AIza`). Both are valid formats.

### Available Gemini Models (confirmed working)

| Model | Speed | Use for |
|-------|-------|---------|
| `gemini-2.5-flash-lite` | Fastest | Quick analysis (default first try) |
| `gemini-2.5-flash` | Fast | Balanced analysis |
| `gemini-3.5-flash-lite` | Fast | Fallback |
| `gemini-3.8-flash` | Capable | Deep analysis fallback |

The bot tries models in order and uses the first one that responds.

---

## Running the Bots

### Morning Briefing Bot (Live)
Fetches your real portfolio from Angel One + Gemini AI analysis.
```bash
python bots/morning_briefing.py
```
> Requires stocks in your Angel One account.

### Demo Briefing Bot
Tests the full Gemini AI pipeline with sample portfolio data.
```bash
python bots/demo_briefing.py
```

### Portfolio Analyst Bot
Deep on-demand portfolio review — sector risk, stop-loss levels, profit targets.
```bash
python bots/portfolio_analyst.py
```

### News Signal Bot
Paste a headline → find which watchlist stocks are impacted.
```bash
python bots/news_signal.py
```

### Watchlist Scanner
Fetches live prices for all watchlist stocks + Gemini AI signals.
```bash
python bots/watchlist_scanner.py
```
Edit `WATCHLIST` in the file to match your stocks and avg cost.

### Price Alert Agent
Runs once (spot check) or continuously every 5 minutes to alert on price targets.
```bash
python bots/price_alert.py          # one-time check
python bots/price_alert.py --loop   # continuous monitoring
```
Edit `ALERTS` in the file: set `buy_below` and `sell_above` per stock.

### Crude Oil Tracker
Live MCX crude price vs NYMEX WTI + USD/INR rate + premium calculation + Gemini direction call.
```bash
python bots/crude_oil_tracker.py              # front-month contract
python bots/crude_oil_tracker.py --mini       # crude mini (lot: 10 barrels)
python bots/crude_oil_tracker.py --contract CRUDEOIL19DEC26FUT
```
Key levels output: BUY above / SELL below + expected range.

### F&O Position Tracker
Monitors all open futures & options positions with P&L, days-to-expiry, and AI analysis.
```bash
python bots/fo_tracker.py
```

### Options Chain Viewer
Live options chain for NIFTY, BANKNIFTY, or MCX Crude Oil — CE/PE prices + AI strategy.
```bash
python bots/options_chain.py                              # NIFTY (default)
python bots/options_chain.py --index BANKNIFTY
python bots/options_chain.py --index CRUDE
python bots/options_chain.py --index NIFTY --expiry 23NOV26 --strikes 10
python bots/options_chain.py --index CRUDE --strikes 5    # tighter chain
```

### Mutual Fund Tracker
Tracks your MF portfolio using live NAV data from AMFI India — works for all platforms (Angel One, Zerodha, Groww, CAMS, etc.).
```bash
python bots/mf_tracker.py                        # full portfolio + Gemini AI
python bots/mf_tracker.py --no-ai                # just show NAV + P&L
python bots/mf_tracker.py --search "mirae"       # find scheme codes by name
python bots/mf_tracker.py --search "parag parikh flexi"
```
Edit `MY_PORTFOLIO` in the file: add `scheme_code`, `units`, and `avg_nav` per fund.  
Use `--search` to find the 6-digit scheme code for any fund.

### GTT Order Manager
Create, list, or cancel Good Till Triggered orders without keeping your computer on.
```bash
python bots/gtt_manager.py                       # list active GTT orders
python bots/gtt_manager.py --mode create         # create from GTT_TEMPLATES
python bots/gtt_manager.py --mode cancel:12345   # cancel rule ID 12345
```
Edit `GTT_TEMPLATES` in the file before running `--mode create`.

### ⚡ Quick Check (fast live snapshot)
One script with one batched quote call. It shows:
- The future's LTP and bid/ask.
- 5m candles with EMA20.
- The option chain at ATM ±N strikes for the nearest expiry.
- Open positions, and pending or rejected orders.

It takes about 5 s per run. The first run each day takes about 20 s longer, because it builds the token cache from Angel's instrument master. It's read-only and never places orders.
```bash
python bots/quick_check.py                   # CRUDEOIL (default)
python bots/quick_check.py crudem            # Crude Mini
python bots/quick_check.py nifty             # NIFTY (NFO)
python bots/quick_check.py banknifty --strikes 3 --candles 10
```
Instruments: `crude` · `crudem`/`mini` · `ng` · `ngm` · `nifty` · `banknifty`/`bnf` · `finnifty` · `midcpnifty`.
Lot sizes and expiries come from the instrument master every day, never hardcoded. An expiry rolls after that day's close (3:30 PM NFO; MCX 11:30 PM in US summer, 11:55 PM in US winter). MCX options are shown with the future they are priced on (next month's future once the options have expired), NIFTY/BANKNIFTY ATM is centred on spot, and the ATM is cross-checked from the options' own prices. Expiry and roll warnings print as ⚠️ lines; The trend table covers 1H, 30m and 5m (built from 5 days of 5m candles, closed candles only, identical to Angel's own 30m/1H bars), and the option chain shows OI, with the top CE/PE OI strikes, PCR and the most traded strike, from ±8 strikes. Still one candle call and one quote call, about 3–4 s.

### 🧪 Backtester
Tests intraday strategies on Angel 5m futures history, including costs, slippage and the daily rules. Data is cached in `.cache/`, so re-runs take seconds.
```bash
python bots/backtester.py                       # compare 10 preset strategies, last 120 days
python bots/backtester.py --days 150 --mini --monthly
python bots/backtester.py --strategy ma --fast 20 --slow 50 --filter ema200 --mini --trades
python bots/backtester.py --strategy breakout --lookback 24 --vol-mult 1.5 --stop 25 --rr 2
python bots/backtester.py --no-rules --slip 3   # stress tests
```
Reports trades, win %, net ₹, profit factor, expectancy, max drawdown, losing streak, % green days, worst day, and per-month P&L.
Fills happen at the next candle's open. If a stop and a target are hit in the same candle, the stop wins. Positions are flat at day end.

### 🔒 Day Guard (daily risk limits)
Computed live from today's Angel trade book, across all instruments. `quick_check.py` prints it on every run, so `/check`, `/trade` and `/watch` respect it.
```bash
python bots/day_guard.py                      # status
python bots/day_guard.py lock "called it a day"   # /eod does this automatically
python bots/day_guard.py unlock <reason>      # discouraged; a reason is required
```
| State | When | Effect |
|---|---|---|
| 🚫 LOCKED | trades ≥ 3, losses ≥ 2, net ≤ −₹1,500, or the day was called | No new entry ideas. Managing an open position is still allowed |
| 🟡 PROTECT | net ≥ +₹500 | Green day: A+ setups only |
| ✅ OK | otherwise | Normal |

Limits are constants at the top of `bots/day_guard.py`. The lock file is `journal/day_lock.json` and applies to today only.

### Trade Alert (breakout & position alerts)
Popup + beep on this PC. Never places orders. Exits after the alert fires.
```bash
# Breakout: beep when a CLOSED 5m candle breaks a level
python bots/trade_alert.py breakout --token 573422 --symbol CRUDEOIL19NOV26FUT \
    --below 8110 --above 8175 --until 22:15

# Position: watch an open option — SL / T1 / T2 / fut fail-level
python bots/trade_alert.py position --symbol CRUDEOIL17NOV268050PE --entry 25.1 --qty 100 \
    --sl 19 --t1 33 --t2 40 --until 21:40 \
    --fut-token 573422 --fut-symbol CRUDEOIL19NOV26FUT --fail-above 8082
```
Add `--exchange NFO` for NIFTY / BANKNIFTY contracts.

### Trade Journal
Builds closed round-trip trades (FIFO) from Angel's trade book. **Close Excel before syncing.**
```bash
python bots/trade_journal.py sync                       # today → trades.csv + daily page + Excel
python bots/trade_journal.py sync --date 2026-11-16
python bots/trade_journal.py note T20261117-2 --setup "PE on break of 8110" \
    --exit "target limit" --notes "..." --charges 63.5   # real charges from contract note
python bots/trade_journal.py stats                      # all-time
python bots/trade_journal.py stats --month 2026-11
python bots/trade_journal.py stats --by-setup          # win rate / P&L per setup tag
python bots/trade_journal.py note T20261117-4 --tag chase   # breakout|retest|rejection|reversal|chase|other
python bots/trade_journal.py excel                      # rebuild Trading_Journal.xlsx only
```
Each daily page (`journal/daily/YYYY-MM-DD.md`) starts with a **Day Summary**:
- **P&L:** verdict, gross profit and loss, gross P&L, total charges, net P&L, and charges as a share of profit.
- **Charges breakdown:** brokerage, exchange charges, CTT, stamp duty, SEBI fees and GST.
- **Activity:** trades and win rate, units traded, turnover, largest capital used in one trade, and best and worst trade.
- **Running totals:** month to date and all time.
- **Expiry day:** whether contracts you traded expired that day, and when the next expiry is.

Below that come the trades table and per-trade notes. Your own notes (market context, what went well, what to improve, plan) are kept on every re-sync.
Charges are estimates until you enter contract-note figures with `--charges`.

### Scheduler (All-in-One)
Runs all bots automatically at the right times — leave it running in background.
```bash
python bots/scheduler.py
```
Auto-schedule: 9:15 briefing → 10:00/12:00/14:00 watchlist scans → 15:00 deep analysis.

---

## Claude Code Slash Commands

Defined in `.claude/commands/`. They're plain Markdown, so edit them to change behaviour.
`/check`, `/trade`, `/bought` and `/plan` fetch live data with `quick_check.py` **before** Claude starts, so replies are fast (about 10–20 s).
Replies use a decorated format: header `## 🟡 WAIT · CRUDEOIL: …`, then trend, volume, levels table, ATM CE/PE, scenarios, day status and 🎯 action.

| Command | Instruments (default **CRUDEOIL**) | What it does | Example |
|---|---|---|---|
| `/check` | crude · crudem · nifty · banknifty · finnifty · ng | Live market check + action (WAIT / BUY SIGNAL / HOLD / EXIT…) | `/check` · `/check nifty` |
| `/trade` | same, plus `ce` / `pe` / `fut` | Finds a trade: rule check first, then entry LIMIT, SL, T1/T2, exit-by, risk:reward | `/trade pe` · `/trade banknifty ce` |
| `/bought` | same | Logs your fill, sets SL and targets, starts `trade_alert.py`, warns if there's no SL | `/bought 8100PE 31.8` · `/bought nifty 25400CE 120` |
| `/watch` | same | Alert-driven trading: sets 5m-close breakout alerts on key levels (with the ATM CE/PE quoted) and pre-plans both sides. You trade only when it beeps | `/watch` · `/watch below 8061 above 8110` |
| `/plan` | same | Pre-session plan: bias, levels R3–S3, long and short setups, events, time windows | `/plan` · `/plan nifty` |
| `/eod` | all | Ends the day: journal sync, trade notes, daily review, stats | `/eod` |

Built-in trading rules, enforced by the Day Guard: **1 lot · LIMIT orders only · SL placed straight after the fill · max 3 trades · stop after 2 losses · once the day is called, no more trades.**
None of the commands place orders. Orders are placed by hand in the Angel app (see the API IP note under Important Limits).

### Typical crude evening session
```
/plan                 → levels and setups (before 8 PM; EIA report on Wednesday at 9 PM in US winter, 8 PM in US summer)
/watch                → set breakout alerts, close the chart, wait for the beep
/check                → when an alert fires (or occasionally)
/trade                → when looking for an entry
/bought 8100PE 31     → after buying in the app; place the SL in the app right away
/check                → manage the trade (hold, trail, exit)
/eod                  → journal sync and review (close Excel first)
```

---

## Crude Oil — Monday Morning Checklist

Run these in order at the MCX open (9:00 AM):

```bash
# 1. Check overnight NYMEX move + MCX implied open
python bots/crude_oil_tracker.py

# 2. Fresh options chain around ATM
python bots/options_chain.py --index CRUDE --strikes 5
```

**Key levels to watch (as of 14 Nov 2026):**

| Level | Signal |
|-------|--------|
| Below ₹8,270 | Bearish confirmed → Bear Put Spread or standalone PE |
| ₹8,270 – ₹8,460 | Range-bound → sell options (Short Strangle) |
| Above ₹8,460 | Bullish breakout → watch ₹8,500 resistance |

**Bear Put Spread (current setup):**
- Buy ₹8,350 PE @ ₹719.60 | Sell ₹8,200 PE @ ₹634.80
- Net debit: ₹8,480 | Max profit: ₹6,520 | Breakeven: ₹8,265
- Stop-loss: ₹150/unit (₹15,000 per lot)

> Overnight NYMEX move (9 PM – 9 AM IST) is the biggest early signal. A drop >$1 on NYMEX = bearish MCX open.

---

## Sample AI Analysis Output

From `demo_briefing.py` — Gemini analyzed a sample portfolio of 8 stocks + 2 F&O positions:

```
Portfolio Health: 6.5 / 10

Top Risks:
1. F&O overnight exposure adds speculative risk
2. IT sector over-concentrated (TCS + INFY + WIPRO)
3. ADANIENT showing weakness at -6.4%

Profit Booking Opportunities:
1. BHARTIARTL +13.3% → book partial profits
2. TCS +5.6% → trim to reduce IT weight
3. NIFTY Call +20.8% → exit at market open

Actions per stock:
RELIANCE    → Hold, accumulate on dips near ₹2,850
HDFCBANK    → Hold, average gradually on weakness
TCS         → Book partial profits, hold rest
BHARTIARTL  → Book partial profits on strong gains
ADANIENT    → Set stop-loss at ₹2,400
```

From `options_chain.py --index CRUDE` — Gemini analyzed MCX Crude 15 JAN 2027 chain:

```
Market Bias: Mildly bearish (PE premiums > CE premiums)
Support    : ₹8,200  |  Resistance: ₹8,500
Strategy   : Bear Put Spread
  Buy  ₹8,350 PE @ ₹719.60
  Sell ₹8,200 PE @ ₹634.80
  Max profit: ₹6,520  |  Max loss: ₹8,480  |  Breakeven: ₹8,265
```

---

## Scheduling (Run Automatically)

### Option A — Python Schedule Library

```python
import schedule, time, sys
sys.path.insert(0, r"A:\Project\Tr")
from bots.morning_briefing import run

schedule.every().monday.at("09:15").do(run)
schedule.every().tuesday.at("09:15").do(run)
schedule.every().wednesday.at("09:15").do(run)
schedule.every().thursday.at("09:15").do(run)
schedule.every().friday.at("09:15").do(run)

while True:
    schedule.run_pending()
    time.sleep(30)
```

### Option B — Windows Task Scheduler
1. Open **Task Scheduler** → Create Basic Task
2. Trigger: Daily at **9:15 AM**, repeat weekdays
3. Action: `python A:\Project\Tr\bots\morning_briefing.py`

---

## Exchanges Available

| Code | Market |
|------|--------|
| `NSE` | NSE Cash (Stocks) |
| `BSE` | BSE Cash (Stocks) |
| `NFO` | NSE Futures & Options |
| `BFO` | BSE Futures & Options |
| `CDS` | Currency Derivatives |
| `MCX` | MCX Commodities (Crude Oil, Gold, Silver) |

### MCX Crude Oil Contract Details

| Item | Detail |
|------|--------|
| Symbol prefix | `CRUDEOIL` |
| Exchange | `MCX` |
| Lot size | 100 barrels (Crude) / 10 barrels (CrudeMini) |
| Strike interval | ₹50 |
| Trading hours | 9:00 AM – 11:30 PM IST |
| Expiry | 3rd Monday of contract month |
| Settlement | Cash (USD/INR rate) |

---

## Core Module Reference

### `core/angel.py`

| Function | Description |
|----------|-------------|
| `connect(fresh=False)` | Login to Angel One, returns `(angel, session_data)`. Reuses today's cached session (`.cache/angel_session.json`); `fresh=True` forces a new login |
| `get_holdings(angel)` | Fetch long-term holdings |
| `get_positions(angel)` | Fetch open intraday / F&O positions |
| `get_ltp(angel, exchange, symbol, token)` | Get live price of a stock/contract |
| `format_portfolio_text(session, holdings, positions)` | Format data as readable text for AI |

### `core/analysis.py`

| Function | Description |
|----------|-------------|
| `analyze(portfolio_text, prompt)` | Auto-picks Gemini or manual mode, tries multiple models |
| `save_report(title, portfolio, analysis)` | Save full report to `reports/` folder |

### `core/candles.py`

| Function | Description |
|----------|-------------|
| `get_candles(angel, exchange, token, interval="FIVE_MINUTE", lookback_minutes=240, closed_only=True)` | Candles from `getCandleData` (1m–1h), closed candles only by default |
| `ema(values, period=20)` | Exponential moving average series |
| `momentum(candles, lookback=6)` | Rule-based read: HH/HL vs LH/LL structure, EMA20 position/slope, swing volume |
| `format_momentum(m, label="")` | One-line text for a momentum result |

---

## Installed Package Versions

Last verified: 14 Nov 2026

| Package | Version | Purpose |
|---------|---------|---------|
| smartapi-python | 1.5.5 | Angel One SmartAPI client |
| pyotp | 2.10.0 | TOTP generator for 2FA login |
| python-dotenv | 1.2.4 | Load credentials from .env |
| logzero | 1.7.0 | Logging for SmartAPI |
| websocket-client | 1.9.2 | WebSocket live price feed |
| google-generativeai | 0.8.6 | Gemini AI (legacy, kept for deps) |
| google-genai | latest | Gemini AI — new SDK (active) |
| yfinance | latest | NYMEX WTI + USD/INR (free, no key) |
| flask | latest | Web server (used by live bots) |
| schedule | 1.2.2 | Bot scheduling |
| requests | 2.34.2 | HTTP requests |

Run `python lib_manager.py` → `[1]` to check current status at any time.

---

## Important Limits

| Limit | Detail |
|-------|--------|
| Gemini latency | ~2–5 sec per analysis call |
| Angel One rate limit | ~3 API calls/second |
| NSE/BSE market hours | 9:15 AM – 3:30 PM IST, weekdays |
| MCX market hours | 9:00 AM – 11:30 PM IST (11:55 PM during US winter time), weekdays |
| SmartAPI static IP | Order APIs only accept the IP registered in the SmartAPI portal (error **AG7002** otherwise). Home broadband IP is dynamic, so orders are placed in the app; data APIs work regardless |
| Quick check speed | `quick_check.py` ≈ 5 s (5 API calls, one batched quote) |
| Session expiry | Angel One token expires daily — bot re-logins each run |
| Gemini free tier | 1,500 requests/day — no credit card needed |

---

## SEBI Rules

| Action | Allowed? |
|--------|----------|
| Fetching market data via API | ✅ Yes |
| Reading portfolio via API | ✅ Yes |
| GTT orders via API | ✅ Yes |
| Bot suggests → you manually place order | ✅ Yes |
| Fully automated order placement | ⚠️ Needs SEBI algo approval from Angel One |

---

## Safety Rules

- Credentials stay in `.env` only — never hardcode in scripts
- Always review AI output before placing any order
- All bot activity is logged to `logs/`
- All reports are saved to `reports/`
- Test with small quantities (1 share / 1 lot) before scaling up
- For F&O: always set a stop-loss before entering a position

---

## Next Steps

- [x] Install Python 3.15
- [x] Set up Angel One SmartAPI app
- [x] Configure credentials in `.env`
- [x] Test Angel One connection
- [x] Install all required packages
- [x] Get Gemini API key and configure
- [x] Test full AI analysis pipeline (demo mode working)
- [x] Add Watchlist Scanner bot (live signals + Gemini AI)
- [x] Add Price Alert agent (continuous or spot-check monitoring)
- [x] Add GTT Order Manager (create/list/cancel orders via API)
- [x] Add Scheduler agent (all bots on auto-schedule)
- [x] Add F&O Tracker bot (live positions + AI analysis)
- [x] Add Options Chain viewer (NIFTY / BANKNIFTY / Crude)
- [x] Add Crude Oil Tracker (MCX vs NYMEX + USD/INR + AI direction)
- [x] Add Mutual Fund Tracker (AMFI NAV + Gemini AI rebalancing advice)
- [x] Add Trade Alert bot (candle-close breakout + position SL/target alerts)
- [x] Add Trade Journal (trade book sync, daily pages with Day Summary, Excel)
- [x] Add Quick Check (fast multi-instrument snapshot)
- [x] Add Claude Code slash commands (/check /trade /bought /plan /eod)
- [ ] Buy stocks in Angel One and run live `morning_briefing.py`
- [ ] Update watchlist tokens in `bots/watchlist_scanner.py` and `bots/price_alert.py`
- [ ] Update watchlist in `bots/news_signal.py` with your actual stocks
- [ ] Schedule `scheduler.py` via Windows Task Scheduler to auto-start on boot
- [ ] Get a static IP (ISP add-on or cloud VPS) and register it in SmartAPI, so API orders work
- [ ] Live terminal dashboard (WebSocket feed, refreshes every second)
- [x] Add historical backtester bot (MA crossover + breakout, costs, daily rules)
- [ ] Add Gold / Silver tracker (MCX)
