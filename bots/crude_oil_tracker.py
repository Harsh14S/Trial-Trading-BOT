"""
Crude Oil Tracker Bot
Tracks MCX Crude Oil futures with live price, NYMEX comparison, INR/USD spread,
and Gemini AI analysis on direction and key levels.

MCX Crude Oil contracts (auto-detected, or override below):
  CRUDEOIL19NOV26FUT  token=573422   (front month, expires 19 Nov 2026)
  CRUDEOIL18DEC26FUT  token=576264   (next month)
  CRUDEOILM19NOV26FUT token=573423   (mini lot — 10 barrels)

Lot sizes:
  Standard : 100 barrels  (~₹5-6 lakh margin per lot)
  Mini      : 10 barrels  (~₹50-60k margin per lot)
"""
import sys
import os
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from core.angel import connect, get_ltp
from core.analysis import analyze, save_report
from core.candles import get_candles, momentum, format_momentum

# ── Contract map — update each month when front-month rolls ───────────────────
CONTRACTS = {
    "NOV26": {"symbol": "CRUDEOIL19NOV26FUT",  "token": "573422", "expiry": "19 Nov 2026"},
    "DEC26": {"symbol": "CRUDEOIL18DEC26FUT",  "token": "576264", "expiry": "18 Dec 2026"},
    "JAN27": {"symbol": "CRUDEOIL19JAN27FUT",  "token": "580377", "expiry": "19 Jan 2027"},
    "FEB27": {"symbol": "CRUDEOIL19FEB27FUT",  "token": "582828", "expiry": "19 Feb 2027"},
}

MINI_CONTRACTS = {
    "NOV26": {"symbol": "CRUDEOILM19NOV26FUT", "token": "573423", "expiry": "19 Nov 2026"},
    "DEC26": {"symbol": "CRUDEOILM18DEC26FUT", "token": "576265", "expiry": "18 Dec 2026"},
}

ROLL_DAYS = 3  # move to next month when the front month has this many days or fewer left


def front_contract(roll_days=ROLL_DAYS):
    """Key of the nearest contract with more than `roll_days` days to expiry."""
    today = datetime.now().date()
    by_expiry = sorted(CONTRACTS.items(), key=lambda kv: datetime.strptime(kv[1]["expiry"], "%d %b %Y"))
    for key, c in by_expiry:
        if (datetime.strptime(c["expiry"], "%d %b %Y").date() - today).days > roll_days:
            return key
    return by_expiry[-1][0]

CRUDE_PROMPT = """You are an expert crude oil and energy market analyst with deep knowledge of MCX and global commodity markets.

Based on current price data provided:

1. **MCX Crude Oil Outlook (1-3 days)**
   - Key support levels (₹/barrel)
   - Key resistance levels (₹/barrel)
   - Short-term trend: Bullish / Bearish / Sideways

2. **Global Factors to Watch**
   - OPEC+ production decisions
   - US EIA inventory (Wednesday 8:30 PM IST)
   - USD/INR movement impact on MCX

3. **Trading Recommendation**
   - BUY above: ₹____ with target ₹____ and stop-loss ₹____
   - SELL below: ₹____ with target ₹____ and stop-loss ₹____

4. **Risk Warning**
   - One specific risk for today

Use ₹ for MCX prices and $ for NYMEX. Be concise and actionable."""


# ── NYMEX WTI price from Yahoo Finance (free, no key) ─────────────────────────

def get_nymex_price():
    """Fetch NYMEX WTI Crude Oil front-month price in USD."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/CL=F"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        price  = meta.get("regularMarketPrice")
        prev   = meta.get("chartPreviousClose") or meta.get("previousClose")
        change = price - prev if price and prev else None
        pct    = (change / prev * 100) if change and prev else None
        return {"price": price, "prev": prev, "change": change, "pct": pct}
    except Exception as e:
        return {"price": None, "error": str(e)}


def get_usdinr():
    """Fetch USD/INR rate from Yahoo Finance."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/USDINR=X"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        data = r.json()
        rate = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return rate
    except Exception:
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def run(contract_key="auto", mini=False):
    print("=" * 60)
    print("   MCX CRUDE OIL TRACKER")
    print(f"   {datetime.now().strftime('%d %b %Y, %I:%M %p IST')}")
    print("=" * 60)

    if contract_key.lower() == "auto":
        contract_key = front_contract()
    contract = MINI_CONTRACTS.get(contract_key) if mini else CONTRACTS.get(contract_key)
    if not contract:
        print(f"❌ Unknown contract key: {contract_key}")
        print(f"   Available: {list(CONTRACTS.keys())}")
        return

    lot_size = 10 if mini else 100
    label    = "MINI" if mini else "STANDARD"

    print(f"\n📋 Contract : {contract['symbol']}  [{label}, {lot_size} bbl/lot]")
    print(f"   Expiry   : {contract['expiry']}")

    # Angel One live price
    print("\n📡 Connecting to Angel One...")
    angel, session_data = connect()
    print(f"✅ Connected: {session_data.get('name')}")

    print("\n📊 Fetching live prices...\n")

    try:
        mcx_price = get_ltp(angel, "MCX", contract["symbol"], contract["token"])
    except Exception as e:
        print(f"❌ MCX price fetch failed: {e}")
        print("   The contract may have expired. Update ACTIVE contract in the bot.")
        return

    # NYMEX and INR/USD
    nymex   = get_nymex_price()
    usdinr  = get_usdinr()

    # ── Display ──────────────────────────────────────────────────────────────
    print("┌─────────────────────────────────────────────────┐")
    print(f"│  MCX CRUDE OIL  ({contract['symbol'][:20]})")
    print("├─────────────────────────────────────────────────┤")
    print(f"│  LTP (MCX)     :  ₹{mcx_price:>10,.2f} / barrel")

    if nymex.get("price"):
        chg_str = f"({nymex['pct']:+.2f}%)" if nymex.get("pct") else ""
        print(f"│  NYMEX WTI     :  ${nymex['price']:>10,.2f} / barrel  {chg_str}")
    else:
        print(f"│  NYMEX WTI     :  Unavailable ({nymex.get('error', '')})")

    if usdinr:
        print(f"│  USD/INR       :  ₹{usdinr:>10,.2f}")
        if nymex.get("price"):
            implied_mcx = nymex["price"] * usdinr
            spread      = mcx_price - implied_mcx
            print(f"│  Implied MCX   :  ₹{implied_mcx:>10,.2f}  (NYMEX × INR)")
            print(f"│  MCX Premium   :  ₹{spread:>+10,.2f}  vs implied")
    else:
        print(f"│  USD/INR       :  Unavailable")

    print(f"│")
    print(f"│  Lot size      :  {lot_size} barrels")
    if nymex.get("price") and usdinr:
        lot_value = mcx_price * lot_size
        margin_est = lot_value * 0.08
        print(f"│  Lot value     :  ₹{lot_value:>10,.0f}  ({lot_size} × ₹{mcx_price:,.0f})")
        print(f"│  Est. margin   :  ₹{margin_est:>10,.0f}  (~8% of lot value)")
    print("└─────────────────────────────────────────────────┘")

    # ── Momentum from closed candles (rule-based, not AI) ────────────────────
    mom_blocks = []
    for interval, label in (("FIFTEEN_MINUTE", "15m"), ("FIVE_MINUTE", "5m")):
        try:
            candles = get_candles(angel, "MCX", contract["token"], interval, lookback_minutes=600)
            mom_blocks.append(format_momentum(momentum(candles), label))
        except Exception as e:
            mom_blocks.append(f"Momentum {label}: unavailable ({e})")
    mom_text = "\n".join(mom_blocks)
    print("\n📈 " + mom_text.replace("\n", "\n   "))

    # ── Build text for AI ─────────────────────────────────────────────────────
    lines = []
    lines.append(f"MCX CRUDE OIL MARKET DATA")
    lines.append(f"Time     : {datetime.now().strftime('%d %b %Y, %I:%M %p IST')}")
    lines.append(f"Contract : {contract['symbol']}  (Expiry: {contract['expiry']})")
    lines.append(f"MCX LTP  : ₹{mcx_price:,.2f} per barrel")
    if nymex.get("price"):
        lines.append(f"NYMEX WTI: ${nymex['price']:,.2f} per barrel  ({nymex.get('pct', 0):+.2f}% today)")
    if usdinr:
        lines.append(f"USD/INR  : ₹{usdinr:,.2f}")
        if nymex.get("price"):
            implied = nymex["price"] * usdinr
            lines.append(f"MCX vs NYMEX premium: ₹{mcx_price - implied:+,.2f}")
    lines.append(f"Lot size : {lot_size} barrels")
    lines.append("")
    lines.append(mom_text)
    market_text = "\n".join(lines)

    # ── AI Analysis ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("🤖 GEMINI AI ANALYSIS")
    print("=" * 60 + "\n")

    mode, result = analyze(market_text, prompt=CRUDE_PROMPT)

    if mode == "gemini":
        print(result)
        report_file = save_report("crude_oil", market_text, result)
        print(f"\n✅ Report saved: {report_file}")
    else:
        print(f"📋 Saved for manual Claude.ai review: {result}")

    print("\n" + "=" * 60)
    print("⚠️  MCX trades 9 AM – 11:30 PM IST. Crude is highly volatile.")
    print("   Always use stop-loss. 1 lot = 100 barrels = high exposure.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MCX Crude Oil Tracker")
    parser.add_argument("--contract", default="auto",
                        help="auto (rolls 3 days before expiry), NOV26, DEC26, JAN27, FEB27")
    parser.add_argument("--mini", action="store_true",
                        help="Use mini contract (10 barrels/lot instead of 100)")
    args = parser.parse_args()
    run(contract_key=args.contract, mini=args.mini)
