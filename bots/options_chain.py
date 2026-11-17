"""
Options Chain Viewer
Displays live options chain for NIFTY, BANKNIFTY, or MCX Crude Oil.
Shows CE/PE prices around ATM with Gemini AI analysis on key strikes.

Usage:
  python bots/options_chain.py                        # NIFTY default
  python bots/options_chain.py --index BANKNIFTY
  python bots/options_chain.py --index CRUDE
  python bots/options_chain.py --index NIFTY --expiry 23NOV26 --strikes 10
"""
import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from core.angel import connect, get_ltp
from core.analysis import analyze, save_report

# ── Index config ───────────────────────────────────────────────────────────────
INDICES = {
    "NIFTY": {
        "exchange":     "NSE",
        "symbol":       "Nifty 50",
        "token":        "26000",
        "nfo_exchange": "NFO",
        "prefix":       "NIFTY",
        "step":         50,       # strike interval
        "lot_size":     75,
        "currency":     "₹",
    },
    "BANKNIFTY": {
        "exchange":     "NSE",
        "symbol":       "Nifty Bank",
        "token":        "26009",
        "nfo_exchange": "NFO",
        "prefix":       "BANKNIFTY",
        "step":         100,
        "lot_size":     30,
        "currency":     "₹",
    },
    "CRUDE": {
        "exchange":     "MCX",
        "symbol":       "CRUDEOIL19NOV26FUT",
        "token":        "573422",
        "nfo_exchange": "MCX",
        "prefix":       "CRUDEOIL",
        "step":         50,       # crude options in ₹50 intervals
        "lot_size":     100,
        "currency":     "₹",
    },
}

CHAIN_PROMPT = """You are an experienced options trader specializing in Indian markets (NIFTY/BANKNIFTY/MCX).

Analyze this live options chain data:

1. **Market Bias** (from put-call ratio and OI distribution)
   - PCR > 1 = bullish, PCR < 0.8 = bearish
   - Where is max pain (highest combined OI)?

2. **Key Strikes to Watch**
   - Strongest call resistance (highest CE OI)
   - Strongest put support (highest PE OI)
   - Expected range for this expiry

3. **Options Strategy Recommendation**
   Choose one:
   - Bull Call Spread (buy lower CE, sell higher CE)
   - Bear Put Spread (buy higher PE, sell lower PE)
   - Short Straddle/Strangle (if range-bound)
   - Buy ATM CE/PE (if directional)

   Include: buy/sell strike, premium, max profit, max loss, breakeven

4. **Theta Warning**
   Days to expiry impact — is premium overpriced or underpriced?

Use ₹ for all values. Be specific with strike prices."""


def round_to_step(value, step):
    return round(value / step) * step


def build_option_symbol(prefix, expiry_str, strike, opt_type):
    """Build NFO/MCX option symbol. expiry_str like '23NOV26'."""
    return f"{prefix}{expiry_str}{int(strike)}{opt_type}"


def find_available_expiries(angel, exchange, prefix, sample_strike, opt_type="CE"):
    """Search for available expiry dates by sampling one strike."""
    result = angel.searchScrip(exchange=exchange, searchscrip=f"{prefix}")
    contracts = result.get("data", [])
    opts = [c for c in contracts
            if c.get("tradingsymbol","").startswith(prefix)
            and c.get("tradingsymbol","").endswith(opt_type)
            and str(int(sample_strike)) in c.get("tradingsymbol","")]

    expiry_map = {}
    for c in opts:
        sym = c.get("tradingsymbol","")
        m = re.search(r"(\d{2}[A-Z]{3}\d{2})", sym)
        if m:
            exp = m.group(1)
            if exp not in expiry_map:
                expiry_map[exp] = c.get("symboltoken")
    today = datetime.now().date()
    return sorted((e for e in expiry_map if _expiry_date(e) >= today), key=_expiry_date)


def _expiry_date(e):
    return datetime.strptime(e, "%d%b%y").date()


def crude_future_for(expiry_str):
    """MCX crude options settle into the same-month future — return that contract dict."""
    from bots.crude_oil_tracker import CONTRACTS
    return CONTRACTS.get(expiry_str[2:].upper())


def build_token_map(angel, exchange, prefix, expiry_str):
    """
    Search once for all contracts of a given expiry and return
    {strike: {"CE": (symbol, token), "PE": (symbol, token)}}
    """
    result = angel.searchScrip(exchange=exchange, searchscrip=f"{prefix}{expiry_str}")
    contracts = result.get("data", [])

    token_map = {}
    for c in contracts:
        sym = c.get("tradingsymbol","")
        tok = c.get("symboltoken","")
        m   = re.search(r"(\d{2}[A-Z]{3}\d{2})(\d+)(CE|PE)$", sym)
        if m:
            strike   = int(m.group(2))
            opt_type = m.group(3)
            if strike not in token_map:
                token_map[strike] = {}
            token_map[strike][opt_type] = (sym, tok)
    return token_map


def fetch_chain(angel, cfg, expiry_str, atm, num_strikes):
    """Fetch CE and PE prices for strikes around ATM using pre-built token map."""
    step     = cfg["step"]
    exchange = cfg["nfo_exchange"]
    prefix   = cfg["prefix"]

    print("   Building token map (1 API call)...")
    token_map = build_token_map(angel, exchange, prefix, expiry_str)

    strikes = [atm + (i * step) for i in range(-num_strikes, num_strikes + 1)]

    # If token_map is empty, the step size or expiry might be wrong — auto-adjust
    if not token_map:
        print("   ⚠️  No tokens found. Trying prefix-only search...")
        return []

    rows = []
    for strike in strikes:
        ce_ltp = pe_ltp = None

        if strike in token_map:
            if "CE" in token_map[strike]:
                ce_sym, ce_tok = token_map[strike]["CE"]
                try:
                    ce_ltp = get_ltp(angel, exchange, ce_sym, ce_tok)
                except Exception:
                    pass

            if "PE" in token_map[strike]:
                pe_sym, pe_tok = token_map[strike]["PE"]
                try:
                    pe_ltp = get_ltp(angel, exchange, pe_sym, pe_tok)
                except Exception:
                    pass

        rows.append({
            "strike": strike,
            "ce_ltp": ce_ltp,
            "pe_ltp": pe_ltp,
            "atm":    (strike == atm),
        })

    return rows


def format_chain(rows, spot, lot_size):
    """Format options chain as readable text."""
    lines = []
    lines.append(f"{'CE Prem':>10}  {'Strike':>8}  {'PE Prem':>10}  {'Note'}")
    lines.append("-" * 50)

    total_ce = total_pe = 0
    for r in rows:
        ce  = r["ce_ltp"]
        pe  = r["pe_ltp"]
        atm = " ◄ ATM" if r["atm"] else ""

        ce_str = f"₹{ce:>8.2f}" if ce else "    N/A "
        pe_str = f"₹{pe:>8.2f}" if pe else "    N/A "

        lines.append(f"{ce_str}  {r['strike']:>8,}  {pe_str}{atm}")

        if ce: total_ce += 1
        if pe: total_pe += 1

    lines.append("-" * 50)
    return "\n".join(lines), total_ce, total_pe


def run(index="NIFTY", expiry_str=None, num_strikes=8, min_days=2):
    index = index.upper()
    cfg   = INDICES.get(index)
    if not cfg:
        print(f"❌ Unknown index: {index}. Use: {list(INDICES.keys())}")
        return

    print("=" * 60)
    print(f"   OPTIONS CHAIN — {index}")
    print(f"   {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    print("=" * 60)

    print("\n📡 Connecting to Angel One...")
    angel, session_data = connect()
    print(f"✅ Connected: {session_data.get('name')}")

    # Get spot price
    spot = get_ltp(angel, cfg["exchange"], cfg["symbol"], cfg["token"])
    atm  = round_to_step(spot, cfg["step"])
    print(f"\n📈 {index} Spot : ₹{spot:,.2f}  |  ATM strike: ₹{atm:,.0f}")

    # Find expiry
    if not expiry_str:
        print("   Searching available expiries...")
        expiries = find_available_expiries(angel, cfg["nfo_exchange"], cfg["prefix"], atm)
        today = datetime.now().date()
        tradable = [e for e in expiries if (_expiry_date(e) - today).days >= min_days] or expiries
        skipped = [e for e in expiries if e not in tradable]
        if skipped:
            print(f"   Skipping expiry within {min_days} day(s): {', '.join(skipped)}  (use --expiry to force)")
        expiries = tradable
        if expiries:
            expiry_str = expiries[0]
            print(f"   Using nearest expiry: {expiry_str}")
            if len(expiries) > 1:
                print(f"   Other available: {', '.join(expiries[1:5])}")
        else:
            print("❌ Could not find options expiry. Try --expiry DDMMMYY manually.")
            return

    # Crude options settle into the same-month future — price ATM off that contract
    if index == "CRUDE":
        fut = crude_future_for(expiry_str)
        if fut and fut["symbol"] != cfg["symbol"]:
            spot = get_ltp(angel, cfg["exchange"], fut["symbol"], fut["token"])
            atm  = round_to_step(spot, cfg["step"])
            print(f"   Underlying for {expiry_str}: {fut['symbol']} ₹{spot:,.2f}  |  ATM ₹{atm:,.0f}")

    print(f"\n📊 Fetching chain: {cfg['prefix']} {expiry_str}  (±{num_strikes} strikes from ATM)\n")

    rows = fetch_chain(angel, cfg, expiry_str, atm, num_strikes)
    chain_text, ce_count, pe_count = format_chain(rows, spot, cfg["lot_size"])

    print(f"{'':>10}  {'STRIKE':>8}  {'PE PREM':>10}")
    print(f"{'CE PREM':>10}  {'':>8}  {'':>10}")
    print(chain_text)

    # Build AI text
    ai_lines = [
        f"OPTIONS CHAIN — {index}",
        f"Date     : {datetime.now().strftime('%d %b %Y, %I:%M %p')}",
        f"Spot     : ₹{spot:,.2f}",
        f"ATM      : ₹{atm:,.0f}",
        f"Expiry   : {expiry_str}",
        f"Lot size : {cfg['lot_size']}",
        "",
        "CHAIN DATA (CE Premium | Strike | PE Premium):",
        chain_text,
    ]
    ai_text = "\n".join(ai_lines)

    print("\n" + "=" * 60)
    print("🤖 GEMINI OPTIONS ANALYSIS")
    print("=" * 60 + "\n")

    mode, result = analyze(ai_text, prompt=CHAIN_PROMPT)
    if mode == "gemini":
        print(result)
        report_file = save_report(f"options_chain_{index.lower()}", ai_text, result)
        print(f"\n✅ Report saved: {report_file}")
    else:
        print(f"📋 Saved for manual review: {result}")

    print("\n" + "=" * 60)
    print(f"⚠️  Lot size: {cfg['lot_size']} units. Options can expire worthless.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Options Chain Viewer")
    parser.add_argument("--index",   default="NIFTY",
                        help="Index to view: NIFTY, BANKNIFTY, CRUDE (default: NIFTY)")
    parser.add_argument("--expiry",  default=None,
                        help="Expiry string e.g. 23NOV26 (auto-detected if omitted)")
    parser.add_argument("--strikes", type=int, default=8,
                        help="Number of strikes above and below ATM (default: 8)")
    parser.add_argument("--min-days", type=int, default=2,
                        help="Auto-pick skips expiries closer than this many days (default: 2)")
    args = parser.parse_args()
    run(index=args.index, expiry_str=args.expiry, num_strikes=args.strikes, min_days=args.min_days)
