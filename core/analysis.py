import os
import time
from datetime import datetime
from core.api_logger import log_call
from config.settings import GEMINI_API_KEY, GEMINI_READY, REPORTS_DIR

PROMPT = """You are an expert Indian stock market analyst.
Analyze this portfolio and give me:
1. Overall portfolio health (score out of 10)
2. Top 3 risks or warnings
3. Top 3 profit-booking opportunities
4. Stocks to watch closely today
5. One-line action for each holding
Be concise, specific, and practical. Use INR (₹) for values."""


def analyze(portfolio_text, prompt=PROMPT):
    """
    Analyze portfolio text.
    Uses Gemini if key is set, otherwise saves file for manual Claude.ai use.
    Returns (mode, result) where mode is 'gemini' or 'manual'.
    """
    if GEMINI_READY:
        try:
            return "gemini", _gemini_analysis(portfolio_text, prompt)
        except Exception as e:
            # All models failed (retired / overloaded / quota) — don't crash the bot
            print(f"⚠️  Gemini unavailable ({str(e)[:90]}) — saving for manual review instead.")
    return "manual", _save_for_manual(portfolio_text, prompt)


def _gemini_analysis(portfolio_text, prompt):
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    # Try models in order until one works
    # 2.5 models return 404 "no longer available to new users" for this key — kept last as fallback
    models = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-2.5-flash-lite", "gemini-2.5-flash"]
    last_error = None
    for model in models:
        start = time.perf_counter()
        try:
            response = client.models.generate_content(
                model=model,
                contents=f"{prompt}\n\n{portfolio_text}"
            )
            log_call("gemini", model, True, (time.perf_counter() - start) * 1000)
            return response.text
        except Exception as e:
            log_call("gemini", model, False, (time.perf_counter() - start) * 1000, err=str(e))
            last_error = e
            continue
    raise last_error


def _save_for_manual(portfolio_text, prompt):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = os.path.join(
        REPORTS_DIR,
        f"portfolio_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    )
    with open(filename, "w", encoding="utf-8") as f:
        f.write("=== PASTE THIS ENTIRE FILE INTO CLAUDE.AI ===\n\n")
        f.write(prompt)
        f.write("\n\n")
        f.write(portfolio_text)
        f.write("\n\n=== END ===\n")
    return filename


def save_report(title, portfolio_text, analysis_text):
    """Save a full report (portfolio + analysis) to the reports folder."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = os.path.join(
        REPORTS_DIR,
        f"{title}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    )
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"=== {title.upper()} ===\n")
        f.write(f"Date: {datetime.now().strftime('%d %b %Y, %I:%M %p')}\n\n")
        f.write(portfolio_text)
        f.write("\n\n--- AI ANALYSIS ---\n\n")
        f.write(analysis_text)
    return filename
