#!/usr/bin/env python3
"""
quota_status.py — run manually to check today's token usage
Usage:  python3 quota_status.py
        TOKEN_QUOTA_DAILY=1000000 python3 quota_status.py
"""

import json
import os
from datetime import date
from pathlib import Path

LEDGER_DIR = Path(os.environ.get("TOKEN_QUOTA_DIR", Path.home() / ".claude-token-quota"))
DAILY_LIMIT = int(os.environ.get("TOKEN_QUOTA_DAILY", 500_000))

def main():
    ledger_file = LEDGER_DIR / f"{date.today().isoformat()}.json"

    if not ledger_file.exists():
        print(f"No usage recorded today ({date.today().isoformat()}).")
        print(f"Daily limit: {DAILY_LIMIT:,} tokens")
        return

    data = json.loads(ledger_file.read_text())
    used = data.get("total_tokens", 0)
    remaining = max(0, DAILY_LIMIT - used)
    pct = (used / DAILY_LIMIT) * 100 if DAILY_LIMIT > 0 else 0
    sessions = data.get("sessions", [])

    bar_width = 30
    filled = int(bar_width * pct / 100)
    bar = "█" * filled + "░" * (bar_width - filled)

    status = "✅ OK" if pct < 80 else ("⚠️  WARNING" if pct < 100 else "🚫 EXCEEDED")

    print(f"\n{'─'*50}")
    print(f"  Claude Code Token Quota — {date.today().isoformat()}")
    print(f"{'─'*50}")
    print(f"  [{bar}] {pct:.1f}%")
    print(f"  Used:      {used:>12,} tokens")
    print(f"  Remaining: {remaining:>12,} tokens")
    print(f"  Limit:     {DAILY_LIMIT:>12,} tokens")
    print(f"  Status:    {status}")
    print(f"  Turns:     {len(sessions)}")
    if sessions:
        print(f"  Last turn: {sessions[-1]['timestamp']}")
    print(f"{'─'*50}\n")

if __name__ == "__main__":
    main()
