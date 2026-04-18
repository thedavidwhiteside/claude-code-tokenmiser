#!/usr/bin/env python3
"""
enforce_quota.py — UserPromptSubmit hook
Reads today's token ledger and blocks the prompt if the daily limit is exceeded.

Set your daily limit via environment variable:
  TOKEN_QUOTA_DAILY=500000   (default: 500,000 tokens)
  TOKEN_QUOTA_DIR=~/.claude-token-quota  (default ledger location)
"""

import json
import sys
import os
from datetime import date
from pathlib import Path

LEDGER_DIR = Path(os.environ.get("TOKEN_QUOTA_DIR", Path.home() / ".claude-token-quota"))
DAILY_LIMIT = int(os.environ.get("TOKEN_QUOTA_DAILY", 500_000))

def today_ledger() -> Path:
    return LEDGER_DIR / f"{date.today().isoformat()}.json"

def get_today_total() -> int:
    p = today_ledger()
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text())
        return data.get("total_tokens", 0)
    except Exception:
        return 0

def main():
    # Read the hook input (we don't need it, but consume stdin cleanly)
    try:
        sys.stdin.read()
    except Exception:
        pass

    used = get_today_total()
    remaining = DAILY_LIMIT - used
    pct = (used / DAILY_LIMIT) * 100 if DAILY_LIMIT > 0 else 0

    if used >= DAILY_LIMIT:
        # Block the prompt by returning a decision=block JSON
        result = {
            "decision": "block",
            "reason": (
                f"Daily token quota exceeded.\n"
                f"Used:  {used:,} / {DAILY_LIMIT:,} tokens ({pct:.1f}%)\n"
                f"Quota resets at midnight. Edit TOKEN_QUOTA_DAILY to change the limit."
            )
        }
        print(json.dumps(result))
        sys.exit(0)

    # Warn at 80% and 95%
    if pct >= 95:
        warning = f"Token quota at {pct:.1f}% ({used:,} / {DAILY_LIMIT:,}). Nearly exhausted."
        result = {"decision": "allow", "reason": warning}
        print(json.dumps(result))
    elif pct >= 85:
        print(f"[token-quota] {pct:.1f}% of daily quota used ({remaining:,} tokens remaining)", file=sys.stderr)

    sys.exit(0)

if __name__ == "__main__":
    main()
