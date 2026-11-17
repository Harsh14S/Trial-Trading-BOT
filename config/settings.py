import os
from dotenv import load_dotenv

load_dotenv()

# Angel One
ANGEL_API_KEY   = os.getenv("ANGEL_API_KEY")
ANGEL_CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
ANGEL_PASSWORD  = os.getenv("ANGEL_PASSWORD")
ANGEL_TOTP_KEY  = os.getenv("ANGEL_TOTP_KEY")

# Gemini
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
GEMINI_READY    = bool(GEMINI_API_KEY and GEMINI_API_KEY not in ("your_gemini_api_key_here", "", None))

# Paths
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
LOGS_DIR    = os.path.join(BASE_DIR, "logs")
