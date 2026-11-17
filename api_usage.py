"""Show today's (or a given day's) API call counts, peaks and errors.

Usage:  python api_usage.py [YYYY-MM-DD]
"""
import sys
from core.api_logger import summarize

if __name__ == "__main__":
    summarize(sys.argv[1] if len(sys.argv) > 1 else None)
