"""
Mutual Fund Tracker
Tracks your MF portfolio using AMFI NAV data (free, works for all platforms).
Add your holdings to MY_PORTFOLIO below, then run.

Usage:
  python bots/mf_tracker.py            # full analysis with Gemini AI
  python bots/mf_tracker.py --no-ai    # just show NAV + P&L, skip Gemini

How to find your AMFI scheme code:
  Visit: https://www.amfiindia.com/nav-history-download
  Or search at: https://www.amfiindia.com/research-information/other-data/scheme-performance-details
  The code is the 6-digit number before the scheme name in NAVAll.txt
"""
import sys
import os
import requests
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from core.analysis import analyze, save_report

# ── YOUR PORTFOLIO ─────────────────────────────────────────────────────────────
# Add your funds here. Find scheme_code at amfiindia.com or use the search below.
# avg_nav = your average purchase NAV (check your CAMS/Kfintech statement)
# units   = total units held

MY_PORTFOLIO = [
    # Examples — replace with your actual holdings:
    # {"name": "Mirae Asset Large Cap Fund - Direct Plan",  "scheme_code": "118989", "units": 150.234, "avg_nav": 95.50},
    # {"name": "Parag Parikh Flexi Cap Fund - Direct Plan", "scheme_code": "122639", "units": 85.012,  "avg_nav": 48.75},
    # {"name": "HDFC Mid-Cap Opportunities - Direct Plan",  "scheme_code": "118825", "units": 120.500, "avg_nav": 110.20},
    # {"name": "SBI Small Cap Fund - Direct Plan",          "scheme_code": "125497", "units": 60.000,  "avg_nav": 130.00},
    # {"name": "ICICI Pru Short Term Fund - Direct Plan",   "scheme_code": "120594", "units": 500.000, "avg_nav": 48.00},
]

AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"

MF_PROMPT = """You are an expert mutual fund advisor for Indian retail investors.

Analyze this mutual fund portfolio and provide:

1. **Portfolio Overview**
   - Total invested vs current value, overall gain/loss %
   - Asset allocation (equity / debt / hybrid — infer from fund names)

2. **Fund-wise Assessment**
   For each fund:
   - Performance rating: Good / Average / Poor (based on gain %)
   - Action: Hold / Accumulate / Redeem / Switch
   - Brief reason

3. **Concentration Risk**
   - Any over-exposure to one fund house, category, or theme?
   - Overlap between equity funds?

4. **SIP Guidance**
   - Which funds to continue SIP in?
   - Any fund to stop SIP in?

5. **Rebalancing Suggestion**
   - Target allocation vs current
   - Any specific switch recommendations

6. **Tax Note**
   - Equity LTCG: gains above ₹1 lakh after 1 year taxed at 10%
   - Debt LTCG: after 3 years taxed at 20% with indexation
   - Flag any positions close to the 1-year / 3-year mark if dates available

Use ₹ for all values. Be specific and actionable."""


def fetch_all_navs():
    """Download NAVAll.txt from AMFI and return {scheme_code: (name, nav, date)}."""
    print("   Downloading NAVs from AMFI India...")
    try:
        resp = requests.get(AMFI_NAV_URL, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"   ❌ Could not reach AMFI: {e}")
        return {}

    # Format: code;ISIN;ISIN2;scheme_name;plan;option;nav;date
    nav_map = {}
    for line in resp.text.splitlines():
        parts = line.strip().split(";")
        if len(parts) >= 7 and parts[0].strip().isdigit():
            code = parts[0].strip()
            name = f"{parts[3].strip()} - {parts[4].strip()} - {parts[5].strip()}"
            nav  = parts[6].strip()
            date = parts[7].strip() if len(parts) > 7 else ""
            try:
                nav_map[code] = (name, float(nav), date)
            except ValueError:
                pass
    return nav_map


def search_fund(query, nav_map, limit=5):
    """Search funds by name keyword. Used when user doesn't know scheme code."""
    q = query.lower()
    matches = [(code, name, nav, date)
               for code, (name, nav, date) in nav_map.items()
               if q in name.lower()]
    return matches[:limit]


def build_portfolio(nav_map):
    """Combine MY_PORTFOLIO with live NAV data."""
    rows = []
    for fund in MY_PORTFOLIO:
        code = str(fund["scheme_code"])
        if code not in nav_map:
            print(f"   ⚠️  Scheme code {code} not found in AMFI. Check the code.")
            cur_nav  = fund["avg_nav"]
            nav_date = "N/A"
            nav_name = fund["name"]
        else:
            nav_name, cur_nav, nav_date = nav_map[code]

        units    = fund["units"]
        avg_nav  = fund["avg_nav"]
        invested = units * avg_nav
        current  = units * cur_nav
        gain     = current - invested
        gain_pct = (gain / invested * 100) if invested else 0

        rows.append({
            "name":      fund.get("name") or nav_name,
            "code":      code,
            "units":     units,
            "avg_nav":   avg_nav,
            "cur_nav":   cur_nav,
            "nav_date":  nav_date,
            "invested":  invested,
            "current":   current,
            "gain":      gain,
            "gain_pct":  gain_pct,
        })
    return rows


def print_portfolio(rows):
    """Print a formatted portfolio table to terminal."""
    if not rows:
        return

    print(f"\n{'Fund':<50} {'Units':>9} {'Avg NAV':>9} {'Cur NAV':>9} {'Invested':>12} {'Current':>12} {'Gain':>8}")
    print("-" * 115)

    total_inv = total_cur = 0
    for r in rows:
        name = r["name"][:49]
        arrow = "▲" if r["gain_pct"] >= 0 else "▼"
        print(
            f"{name:<50} {r['units']:>9.3f} {r['avg_nav']:>9.2f} {r['cur_nav']:>9.2f} "
            f"₹{r['invested']:>10,.0f} ₹{r['current']:>10,.0f}  {arrow}{abs(r['gain_pct']):>5.1f}%"
        )
        total_inv += r["invested"]
        total_cur += r["current"]

    print("-" * 115)
    overall_gain = total_cur - total_inv
    overall_pct  = (overall_gain / total_inv * 100) if total_inv else 0
    arrow = "▲" if overall_pct >= 0 else "▼"
    print(f"{'TOTAL':<50} {'':>9} {'':>9} {'':>9} ₹{total_inv:>10,.0f} ₹{total_cur:>10,.0f}  {arrow}{abs(overall_pct):>5.1f}%")
    print(f"\n   Invested : ₹{total_inv:,.2f}")
    print(f"   Current  : ₹{total_cur:,.2f}")
    print(f"   Gain/Loss: ₹{overall_gain:,.2f}  ({overall_pct:+.2f}%)")


def format_for_ai(rows):
    """Format portfolio data as text for Gemini."""
    if not rows:
        return "No MF portfolio data available."

    lines = [
        f"Date     : {datetime.now().strftime('%d %b %Y, %I:%M %p')}",
        f"Funds    : {len(rows)}",
        "",
        "MUTUAL FUND PORTFOLIO:",
        "-" * 90,
    ]

    total_inv = total_cur = 0
    for r in rows:
        lines.append(
            f"Fund     : {r['name']}\n"
            f"Code     : {r['code']}  |  NAV Date: {r['nav_date']}\n"
            f"Units    : {r['units']:.3f}  |  Avg NAV: ₹{r['avg_nav']:.2f}  |  Current NAV: ₹{r['cur_nav']:.2f}\n"
            f"Invested : ₹{r['invested']:,.2f}  |  Current: ₹{r['current']:,.2f}  |  Gain: ₹{r['gain']:,.2f} ({r['gain_pct']:+.2f}%)\n"
        )
        total_inv += r["invested"]
        total_cur += r["current"]

    overall_gain = total_cur - total_inv
    overall_pct  = (overall_gain / total_inv * 100) if total_inv else 0
    lines += [
        "-" * 90,
        f"TOTAL INVESTED : ₹{total_inv:,.2f}",
        f"TOTAL CURRENT  : ₹{total_cur:,.2f}",
        f"OVERALL GAIN   : ₹{overall_gain:,.2f}  ({overall_pct:+.2f}%)",
    ]
    return "\n".join(lines)


def run(ai=True):
    print("=" * 60)
    print("   MUTUAL FUND TRACKER  (via AMFI NAV)")
    print(f"   {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    print("=" * 60)

    if not MY_PORTFOLIO:
        print("\n⚠️  MY_PORTFOLIO is empty.")
        print("   Edit bots/mf_tracker.py and add your funds to MY_PORTFOLIO.")
        print("\n   Example entry:")
        print('   {"name": "Mirae Asset Large Cap - Direct", "scheme_code": "118989", "units": 150.0, "avg_nav": 95.50}')
        print("\n   To find scheme codes, run:")
        print("   python bots/mf_tracker.py --search \"mirae large cap\"")
        return

    nav_map = fetch_all_navs()
    if not nav_map:
        return

    print(f"   NAVs loaded: {len(nav_map):,} schemes")

    rows = build_portfolio(nav_map)
    print_portfolio(rows)

    if not ai:
        mf_text = format_for_ai(rows)
        report_file = save_report("mf_tracker", mf_text, "(--no-ai mode)")
        print(f"\n✅ Data saved: {report_file}")
        return

    mf_text = format_for_ai(rows)

    print("\n" + "=" * 60)
    print("🤖 GEMINI AI ANALYSIS")
    print("=" * 60 + "\n")

    mode, result = analyze(mf_text, prompt=MF_PROMPT)

    if mode == "gemini":
        print(result)
        report_file = save_report("mf_tracker", mf_text, result)
        print(f"\n✅ Report saved: {report_file}")
    else:
        print(f"📋 Saved for manual review: {result}")

    print("\n" + "=" * 60)


def search_mode(query):
    """Search AMFI for funds matching a keyword and print results."""
    print(f"\n🔍 Searching AMFI for: '{query}'")
    nav_map = fetch_all_navs()
    if not nav_map:
        return
    results = search_fund(query, nav_map, limit=15)
    if not results:
        print("   No funds found. Try a broader search term.")
        return
    print(f"\n{'Code':<10} {'Current NAV':>12}  {'Fund Name'}")
    print("-" * 80)
    for code, name, nav, date in results:
        print(f"{code:<10} ₹{nav:>10.2f}   {name}")
    print(f"\n   Copy the code into MY_PORTFOLIO in bots/mf_tracker.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mutual Fund Tracker (AMFI NAV)")
    parser.add_argument("--no-ai",  action="store_true", help="Skip Gemini, just show P&L")
    parser.add_argument("--search", type=str, default=None,
                        help="Search AMFI for a fund by name e.g. --search \"parag parikh\"")
    args = parser.parse_args()

    if args.search:
        search_mode(args.search)
    else:
        run(ai=not args.no_ai)
