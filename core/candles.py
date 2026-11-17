"""
Candle data + rule-based momentum read.

Uses Angel One getCandleData. Replaces "reading momentum from LTP snapshots"
with explicit rules on closed candles:
  - structure : higher highs/lows vs lower highs/lows over the last N candles
  - EMA20     : close above/below, and EMA slope
  - volume    : volume on the latest swing vs the prior swing
"""
from datetime import datetime, timedelta

INTERVAL_MINUTES = {
    "ONE_MINUTE": 1, "THREE_MINUTE": 3, "FIVE_MINUTE": 5, "TEN_MINUTE": 10,
    "FIFTEEN_MINUTE": 15, "THIRTY_MINUTE": 30, "ONE_HOUR": 60,
}


def get_candles(angel, exchange, token, interval="FIVE_MINUTE", lookback_minutes=240, closed_only=True):
    """Return candles oldest→newest as dicts: ts, open, high, low, close, volume.

    closed_only=True drops the candle that is still forming.
    """
    now = datetime.now()
    params = {
        "exchange": exchange,
        "symboltoken": str(token),
        "interval": interval,
        "fromdate": (now - timedelta(minutes=lookback_minutes)).strftime("%Y-%m-%d %H:%M"),
        "todate": now.strftime("%Y-%m-%d %H:%M"),
    }
    resp = angel.getCandleData(params)
    if not resp or not resp.get("status"):
        raise RuntimeError(f"getCandleData failed: {resp.get('message') if resp else 'no response'}")
    candles = []
    for row in resp.get("data") or []:
        ts = datetime.fromisoformat(row[0]).replace(tzinfo=None)
        candles.append({"ts": ts, "open": row[1], "high": row[2], "low": row[3], "close": row[4], "volume": row[5]})
    if closed_only and candles:
        step = timedelta(minutes=INTERVAL_MINUTES.get(interval, 5))
        if candles[-1]["ts"] + step > now:
            candles = candles[:-1]
    return candles


def ema(values, period=20):
    """Exponential moving average series (same length as values; seeded with SMA)."""
    if len(values) < period:
        period = max(1, len(values))
    k = 2 / (period + 1)
    out = [None] * (period - 1)
    seed = sum(values[:period]) / period
    out.append(seed)
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def momentum(candles, lookback=6):
    """Rule-based momentum read on closed candles. Returns a dict with a verdict and the evidence."""
    if len(candles) < lookback + 2:
        return {"verdict": "INSUFFICIENT DATA", "reasons": [f"need {lookback + 2}+ candles, have {len(candles)}"]}

    closes = [c["close"] for c in candles]
    e = ema(closes, 20)
    recent = candles[-lookback:]
    first, second = recent[: lookback // 2], recent[lookback // 2:]

    hh = max(c["high"] for c in second) > max(c["high"] for c in first)
    hl = min(c["low"] for c in second) > min(c["low"] for c in first)
    lh = max(c["high"] for c in second) < max(c["high"] for c in first)
    ll = min(c["low"] for c in second) < min(c["low"] for c in first)

    last = candles[-1]
    ema_now, ema_prev = e[-1], e[-4] if len(e) >= 4 and e[-4] is not None else e[-1]
    above_ema = last["close"] > ema_now
    ema_slope = ema_now - ema_prev

    vol_first = sum(c["volume"] for c in first) / len(first)
    vol_second = sum(c["volume"] for c in second) / len(second)

    score, reasons = 0, []
    if hh and hl:
        score += 2; reasons.append("higher highs + higher lows (uptrend structure)")
    elif lh and ll:
        score -= 2; reasons.append("lower highs + lower lows (downtrend structure)")
    elif hl and not ll:
        score += 1; reasons.append("higher lows — selling pressure fading")
    elif lh and not hh:
        score -= 1; reasons.append("lower highs — buying pressure fading")
    else:
        reasons.append("mixed structure (range)")

    band = ema_now * 0.001  # within 0.1% of EMA = "at EMA", no score
    if abs(last["close"] - ema_now) <= band:
        reasons.append(f"close {last['close']:.0f} at EMA20 {ema_now:.0f} (within 0.1%)")
    elif above_ema:
        score += 1; reasons.append(f"close {last['close']:.0f} above EMA20 {ema_now:.0f}")
    else:
        score -= 1; reasons.append(f"close {last['close']:.0f} below EMA20 {ema_now:.0f}")
    reasons.append(f"EMA20 slope {ema_slope:+.1f} over 3 candles")

    vol_note = f"avg volume {vol_first:.0f} → {vol_second:.0f}"
    if vol_second > vol_first * 1.2:
        reasons.append(vol_note + " (rising — move has participation)")
    elif vol_second < vol_first * 0.8:
        reasons.append(vol_note + " (falling — move is weak)")
    else:
        reasons.append(vol_note + " (flat)")

    verdict = {2: "BULLISH", 3: "BULLISH", 1: "LEANING BULLISH", 0: "NEUTRAL / RANGE",
               -1: "LEANING BEARISH", -2: "BEARISH", -3: "BEARISH"}[max(-3, min(3, score))]
    return {
        "verdict": verdict, "score": score, "reasons": reasons,
        "last_close": last["close"], "last_ts": last["ts"], "ema20": ema_now,
        "range_high": max(c["high"] for c in recent), "range_low": min(c["low"] for c in recent),
    }


def format_momentum(m, label=""):
    if "score" not in m:
        return f"Momentum {label}: {m['verdict']} ({'; '.join(m['reasons'])})"
    lines = [f"Momentum {label}: {m['verdict']}  (score {m['score']:+d}, last close {m['last_close']:.0f} @ {m['last_ts']:%H:%M})"]
    lines += [f"  • {r}" for r in m["reasons"]]
    lines.append(f"  • recent range {m['range_low']:.0f} – {m['range_high']:.0f}")
    return "\n".join(lines)
