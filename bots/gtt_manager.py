"""
GTT Order Manager Agent
Good Till Triggered (GTT) orders let you set buy/sell orders that execute
automatically when price conditions are met — without keeping your computer on.
This agent helps you create, list, and cancel GTT orders via Angel One API.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from core.angel import connect

# ── GTT Templates — edit these before running ─────────────────────────────────
# After reviewing your holdings, fill in the template below and run with --create

GTT_TEMPLATES = [
    # Stop-loss for RELIANCE: sell if LTP drops to ₹2750
    {
        "action":       "SELL",
        "exchange":     "NSE",
        "symbol":       "RELIANCE-EQ",
        "token":        "2885",
        "qty":          5,
        "trigger_price": 2750.0,
        "limit_price":   2740.0,
        "note":         "Stop-loss",
    },
    # Profit booking for BHARTIARTL: sell if LTP hits ₹1250
    {
        "action":       "SELL",
        "exchange":     "NSE",
        "symbol":       "BHARTIARTL-EQ",
        "token":        "10604",
        "qty":          10,
        "trigger_price": 1250.0,
        "limit_price":   1245.0,
        "note":         "Profit target",
    },
]


def list_gtt(angel):
    """List all active GTT orders."""
    try:
        response = angel.gttLists(["FORALL"], 1, 20)
        orders = response.get("data", {}).get("list", []) or []
        return orders
    except Exception as e:
        print(f"  ❌ Could not fetch GTT orders: {e}")
        return []


def create_gtt(angel, template):
    """Create a GTT order from a template dict."""
    try:
        response = angel.gttCreateRule(
            CreateRuleParams={
                "tradingsymbol":    template["symbol"],
                "symboltoken":      template["token"],
                "exchange":         template["exchange"],
                "transactiontype":  template["action"],
                "producttype":      "DELIVERY",
                "price":            template["limit_price"],
                "qty":              template["qty"],
                "disclosedqty":     template["qty"],
                "triggerprice":     template["trigger_price"],
                "timeperiod":       365,
            }
        )
        return response
    except Exception as e:
        return {"status": False, "message": str(e)}


def cancel_gtt(angel, rule_id):
    """Cancel a GTT order by rule ID."""
    try:
        response = angel.gttDeleteRule(id=rule_id, symboltoken="", exchange="")
        return response
    except Exception as e:
        return {"status": False, "message": str(e)}


def print_gtt_list(orders):
    """Print GTT orders in a readable table."""
    if not orders:
        print("   No active GTT orders.")
        return
    print(f"\n{'ID':<10} {'Symbol':<22} {'Action':<6} {'Qty':<6} {'Trigger':<12} {'Limit':<12} {'Status'}")
    print("-" * 80)
    for o in orders:
        rule_id  = o.get("id", "?")
        symbol   = o.get("tradingsymbol", "?")
        action   = o.get("transactiontype", "?")
        qty      = o.get("qty", "?")
        trigger  = o.get("triggerprice", "?")
        limit_p  = o.get("price", "?")
        status   = o.get("status", "?")
        print(f"{rule_id:<10} {symbol:<22} {action:<6} {qty:<6} ₹{trigger:<11} ₹{limit_p:<11} {status}")


def run(mode="list"):
    print("=" * 55)
    print("   GTT ORDER MANAGER")
    print(f"   {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    print("=" * 55)

    print("\n📡 Connecting to Angel One...")
    angel, session_data = connect()
    print(f"✅ Connected: {session_data.get('name')}")

    if mode == "list":
        print("\n📋 Active GTT Orders:")
        orders = list_gtt(angel)
        print_gtt_list(orders)

    elif mode == "create":
        print(f"\n📝 Creating {len(GTT_TEMPLATES)} GTT orders from templates...\n")
        for t in GTT_TEMPLATES:
            print(f"  {t['note']}: {t['action']} {t['qty']} × {t['symbol']} @ trigger ₹{t['trigger_price']}")
            resp = create_gtt(angel, t)
            if resp.get("status"):
                rule_id = resp.get("data", {}).get("id", "?")
                print(f"  ✅ Created (Rule ID: {rule_id})\n")
            else:
                print(f"  ❌ Failed: {resp.get('message', 'Unknown error')}\n")

        print("📋 Updated GTT order list:")
        print_gtt_list(list_gtt(angel))

    elif mode.startswith("cancel:"):
        rule_id = mode.split(":")[1].strip()
        print(f"\n🗑️  Cancelling GTT rule ID: {rule_id}")
        resp = cancel_gtt(angel, rule_id)
        if resp.get("status"):
            print(f"✅ Cancelled successfully.")
        else:
            print(f"❌ Failed: {resp.get('message', 'Unknown error')}")

    print("\n" + "=" * 55)
    print("⚠️  Always verify GTT orders in the Angel One app before market open.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GTT Order Manager")
    parser.add_argument("--mode", default="list",
                        help="list | create | cancel:<rule_id>")
    args = parser.parse_args()
    run(mode=args.mode)
