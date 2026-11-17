"""
Connection test — run this to verify Angel One API is working.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.angel import connect, get_holdings, get_positions

def main():
    print("Testing Angel One connection...")
    try:
        angel, session_data = connect()
        print(f"✅ Connected: {session_data.get('name')}")
        print(f"   Client ID : {session_data.get('clientcode')}")
        print(f"   Exchanges : {session_data.get('exchanges', [])}")

        holdings = get_holdings(angel)
        print(f"\n📊 Holdings  : {len(holdings)} stocks")

        positions = get_positions(angel)
        print(f"📈 Positions : {len(positions)} open")

        print("\n✅ All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")

if __name__ == "__main__":
    main()
