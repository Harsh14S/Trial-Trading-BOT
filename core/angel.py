import json
import os
import time
from datetime import datetime

import pyotp
from SmartApi import SmartConnect
from config.settings import ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_KEY, BASE_DIR

# Session cache — reuse one login across scripts instead of logging in on every run.
# Holds live tokens: the .cache/ folder is gitignored. Delete the file to force a fresh login.
CACHE_DIR    = os.path.join(BASE_DIR, ".cache")
SESSION_FILE = os.path.join(CACHE_DIR, "angel_session.json")
LOCK_FILE    = os.path.join(CACHE_DIR, "angel_login.lock")
MAX_AGE_HRS  = 12


def connect(retries=3, fresh=False):
    """Return (angel, session_data), reusing today's cached session when it is still valid.

    Flow: cached tokens → 1 getProfile call to validate → done.
    Falls back to a full login (login + getProfile) only when the cache is missing,
    from an earlier day, older than MAX_AGE_HRS, or rejected by Angel.
    A lock file ensures that scripts starting together log in once and share it.
    """
    if not fresh:
        cached = _from_cache()
        if cached:
            return cached

    with _login_lock():
        if not fresh:
            cached = _from_cache()          # another script may have logged in while we waited
            if cached:
                return cached
        angel, data = _login(retries)
        _save_cache(angel, data)
        return angel, data


def _login(retries):
    """Full login with backoff on Angel's login rate limit."""
    totp = pyotp.TOTP(ANGEL_TOTP_KEY)
    for attempt in range(retries + 1):
        angel = SmartConnect(api_key=ANGEL_API_KEY)
        try:
            session = angel.generateSession(ANGEL_CLIENT_ID, ANGEL_PASSWORD, totp.now())
        except Exception as e:
            if "access rate" in str(e).lower() and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise
        if session["status"]:
            return angel, session["data"]
        raise Exception(f"Angel One login failed: {session['message']}")


def _from_cache():
    """Rebuild a client from cached tokens and validate with one getProfile call."""
    try:
        with open(SESSION_FILE, encoding="utf-8") as f:
            c = json.load(f)
        created = datetime.fromisoformat(c["created"])
        if created.date() != datetime.now().date() or (datetime.now() - created).total_seconds() > MAX_AGE_HRS * 3600:
            return None
        if c.get("client_id") != ANGEL_CLIENT_ID:
            return None
        angel = SmartConnect(api_key=ANGEL_API_KEY, access_token=c["jwt"],
                             refresh_token=c["refresh"], feed_token=c["feed"], userId=c["client_id"])
        profile = angel.getProfile(c["refresh"])
        if not profile or not profile.get("status"):
            return None
        return angel, profile["data"]
    except Exception:
        return None


def _save_cache(angel, data):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = SESSION_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({
                "created": datetime.now().isoformat(timespec="seconds"),
                "client_id": ANGEL_CLIENT_ID,
                "jwt": angel.access_token,
                "refresh": angel.refresh_token,
                "feed": angel.feed_token,
            }, f)
        os.replace(tmp, SESSION_FILE)
    except Exception:
        pass  # cache is an optimisation — never fail a login because of it


class _login_lock:
    """Cross-process lock via an exclusive lock file. Stale locks (>30s) are broken."""
    def __enter__(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        deadline = time.time() + 30
        while True:
            try:
                self.fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(LOCK_FILE) > 30:
                        os.remove(LOCK_FILE)
                        continue
                except OSError:
                    continue
                if time.time() > deadline:
                    self.fd = None
                    return self
                time.sleep(0.3)

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
            try:
                os.remove(LOCK_FILE)
            except OSError:
                pass


def get_holdings(angel):
    """Return list of holdings or empty list."""
    try:
        return angel.holding().get("data") or []
    except Exception:
        return []


def get_positions(angel):
    """Return list of open positions or empty list."""
    try:
        all_pos = angel.position().get("data") or []
        return [p for p in all_pos if int(p.get("netqty", 0)) != 0]
    except Exception:
        return []


def get_ltp(angel, exchange, symbol, token):
    """Return last traded price for a symbol."""
    data = angel.ltpData(exchange, symbol, token)
    return data["data"]["ltp"]


def format_portfolio_text(session_data, holdings, positions):
    """Format portfolio data as readable text for AI analysis."""
    lines = []
    lines.append(f"Name : {session_data.get('name', ANGEL_CLIENT_ID)}")
    lines.append("")

    if holdings:
        lines.append("HOLDINGS:")
        total_invested = total_current = 0
        for h in holdings:
            symbol   = h.get("tradingsymbol", "")
            qty      = h.get("quantity", 0)
            avg      = float(h.get("averageprice", 0))
            ltp      = float(h.get("ltp", 0))
            pnl      = float(h.get("pnl", 0))
            pct      = ((ltp - avg) / avg * 100) if avg else 0
            total_invested += avg * qty
            total_current  += ltp * qty
            lines.append(f"  {symbol:<20} Qty:{qty:<5} Avg:₹{avg:<10.2f} LTP:₹{ltp:<10.2f} P&L:₹{pnl:<10.2f} ({pct:+.1f}%)")
        overall_pnl = total_current - total_invested
        overall_pct = (overall_pnl / total_invested * 100) if total_invested else 0
        lines.append(f"\n  Invested: ₹{total_invested:,.2f}  |  Current: ₹{total_current:,.2f}  |  P&L: ₹{overall_pnl:,.2f} ({overall_pct:+.1f}%)")
    else:
        lines.append("HOLDINGS: None.")

    lines.append("")

    if positions:
        lines.append("OPEN POSITIONS:")
        for p in positions:
            symbol = p.get("tradingsymbol", "")
            qty    = p.get("netqty", 0)
            avg    = float(p.get("netprice", 0))
            ltp    = float(p.get("ltp", 0))
            pnl    = float(p.get("pnl", 0))
            lines.append(f"  {symbol:<20} Qty:{qty:<5} Avg:₹{avg:<10.2f} LTP:₹{ltp:<10.2f} P&L:₹{pnl:.2f}")
    else:
        lines.append("OPEN POSITIONS: None.")

    return "\n".join(lines)
