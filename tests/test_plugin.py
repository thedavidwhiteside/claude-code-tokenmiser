#!/usr/bin/env python3
"""
Unit tests for claude-code-tokenmiser plugin hooks.
Run with: python3 -m pytest tests/ or python3 -m unittest tests/test_plugin.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
ENFORCE  = HOOKS_DIR / "enforce_quota.py"
TRACK    = HOOKS_DIR / "track_tokens.py"
STATUS   = HOOKS_DIR / "quota_status.py"


def run_script(script: Path, stdin: str = "", env_overrides: dict = None) -> subprocess.CompletedProcess:
    env = {**os.environ, **(env_overrides or {})}
    return subprocess.run(
        [sys.executable, str(script)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
    )


def make_ledger(ledger_dir: Path, total_tokens: int, days_ago: int = 0, sessions: list = None) -> Path:
    target_date = date.today() - timedelta(days=days_ago)
    ledger_file = ledger_dir / f"{target_date.isoformat()}.json"
    ledger_file.write_text(json.dumps({
        "date": target_date.isoformat(),
        "total_tokens": total_tokens,
        "sessions": sessions or [],
    }))
    return ledger_file


def make_transcript(tmp_dir: Path, usage: dict) -> Path:
    transcript = tmp_dir / "session.jsonl"
    entry = {
        "parentUuid": "abc123",
        "isSidechain": False,
        "message": {
            "role": "assistant",
            "usage": usage,
        }
    }
    transcript.write_text(json.dumps(entry) + "\n")
    return transcript


class TestEnforceQuota(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger_dir = Path(self.tmp.name)
        self.env = {"TOKEN_QUOTA_DIR": self.tmp.name, "TOKEN_QUOTA_DAILY": "1000000"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_allows_when_no_ledger(self):
        result = run_script(ENFORCE, stdin="{}", env_overrides=self.env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_allows_when_under_limit(self):
        make_ledger(self.ledger_dir, total_tokens=500_000)
        result = run_script(ENFORCE, stdin="{}", env_overrides=self.env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_blocks_when_at_limit(self):
        make_ledger(self.ledger_dir, total_tokens=1_000_000)
        result = run_script(ENFORCE, stdin="{}", env_overrides=self.env)
        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        self.assertEqual(output["decision"], "block")
        self.assertIn("exceeded", output["reason"])

    def test_blocks_when_over_limit(self):
        make_ledger(self.ledger_dir, total_tokens=1_200_000)
        result = run_script(ENFORCE, stdin="{}", env_overrides=self.env)
        output = json.loads(result.stdout)
        self.assertEqual(output["decision"], "block")

    def test_warns_at_95_percent(self):
        make_ledger(self.ledger_dir, total_tokens=960_000)
        result = run_script(ENFORCE, stdin="{}", env_overrides=self.env)
        output = json.loads(result.stdout)
        self.assertEqual(output["decision"], "allow")
        self.assertIn("Nearly exhausted", output["reason"])

    def test_warns_to_stderr_at_85_percent(self):
        make_ledger(self.ledger_dir, total_tokens=860_000)
        result = run_script(ENFORCE, stdin="{}", env_overrides=self.env)
        self.assertEqual(result.stdout.strip(), "")
        self.assertIn("token-quota", result.stderr)

    def test_respects_custom_limit(self):
        make_ledger(self.ledger_dir, total_tokens=500_000)
        env = {**self.env, "TOKEN_QUOTA_DAILY": "500000"}
        result = run_script(ENFORCE, stdin="{}", env_overrides=env)
        output = json.loads(result.stdout)
        self.assertEqual(output["decision"], "block")

    def test_handles_empty_stdin(self):
        result = run_script(ENFORCE, stdin="", env_overrides=self.env)
        self.assertEqual(result.returncode, 0)

    def test_handles_corrupt_ledger(self):
        (self.ledger_dir / f"{date.today().isoformat()}.json").write_text("not json")
        result = run_script(ENFORCE, stdin="{}", env_overrides=self.env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")


class TestTrackTokens(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger_dir = Path(self.tmp.name)
        self.env = {"TOKEN_QUOTA_DIR": self.tmp.name, "TOKEN_QUOTA_DAILY": "1000000"}

    def tearDown(self):
        self.tmp.cleanup()

    def _stop_hook_input(self, transcript_path: str) -> str:
        return json.dumps({
            "session_id": "test-session",
            "transcript_path": transcript_path,
            "hook_event_name": "Stop",
        })

    def test_records_tokens_from_transcript(self):
        transcript = make_transcript(self.ledger_dir, {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        })
        stdin = self._stop_hook_input(str(transcript))
        result = run_script(TRACK, stdin=stdin, env_overrides=self.env)
        self.assertEqual(result.returncode, 0)

        ledger = json.loads((self.ledger_dir / f"{date.today().isoformat()}.json").read_text())
        self.assertEqual(ledger["total_tokens"], 150)
        self.assertEqual(len(ledger["sessions"]), 1)

    def test_records_cache_tokens(self):
        transcript = make_transcript(self.ledger_dir, {
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_creation_input_tokens": 500,
            "cache_read_input_tokens": 1000,
        })
        stdin = self._stop_hook_input(str(transcript))
        run_script(TRACK, stdin=stdin, env_overrides=self.env)

        ledger = json.loads((self.ledger_dir / f"{date.today().isoformat()}.json").read_text())
        self.assertEqual(ledger["total_tokens"], 1530)

    def test_accumulates_across_turns(self):
        transcript = make_transcript(self.ledger_dir, {
            "input_tokens": 100, "output_tokens": 50,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
        })
        stdin = self._stop_hook_input(str(transcript))
        run_script(TRACK, stdin=stdin, env_overrides=self.env)
        run_script(TRACK, stdin=stdin, env_overrides=self.env)

        ledger = json.loads((self.ledger_dir / f"{date.today().isoformat()}.json").read_text())
        self.assertEqual(ledger["total_tokens"], 300)
        self.assertEqual(len(ledger["sessions"]), 2)

    def test_handles_empty_stdin(self):
        result = run_script(TRACK, stdin="", env_overrides=self.env)
        self.assertEqual(result.returncode, 0)

    def test_handles_missing_transcript(self):
        stdin = self._stop_hook_input("/nonexistent/path.jsonl")
        result = run_script(TRACK, stdin=stdin, env_overrides=self.env)
        self.assertEqual(result.returncode, 0)

    def test_handles_transcript_with_no_usage(self):
        transcript = self.ledger_dir / "empty.jsonl"
        transcript.write_text(json.dumps({"role": "user", "content": "hello"}) + "\n")
        stdin = self._stop_hook_input(str(transcript))
        result = run_script(TRACK, stdin=stdin, env_overrides=self.env)
        self.assertEqual(result.returncode, 0)
        self.assertFalse((self.ledger_dir / f"{date.today().isoformat()}.json").exists())

    def test_cleans_up_old_ledgers(self):
        old_file = make_ledger(self.ledger_dir, total_tokens=1000, days_ago=35)
        recent_file = make_ledger(self.ledger_dir, total_tokens=1000, days_ago=5)

        transcript = make_transcript(self.ledger_dir, {
            "input_tokens": 10, "output_tokens": 10,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
        })
        stdin = self._stop_hook_input(str(transcript))
        env = {**self.env, "TOKEN_QUOTA_RETAIN_DAYS": "30"}
        run_script(TRACK, stdin=stdin, env_overrides=env)

        self.assertFalse(old_file.exists())
        self.assertTrue(recent_file.exists())

    def test_retains_files_within_window(self):
        recent_file = make_ledger(self.ledger_dir, total_tokens=1000, days_ago=10)
        transcript = make_transcript(self.ledger_dir, {
            "input_tokens": 10, "output_tokens": 10,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
        })
        stdin = self._stop_hook_input(str(transcript))
        env = {**self.env, "TOKEN_QUOTA_RETAIN_DAYS": "30"}
        run_script(TRACK, stdin=stdin, env_overrides=env)

        self.assertTrue(recent_file.exists())

    def test_stderr_reports_usage(self):
        transcript = make_transcript(self.ledger_dir, {
            "input_tokens": 100, "output_tokens": 50,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
        })
        stdin = self._stop_hook_input(str(transcript))
        result = run_script(TRACK, stdin=stdin, env_overrides=self.env)
        self.assertIn("token-quota", result.stderr)
        self.assertIn("150", result.stderr)


class TestQuotaStatus(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger_dir = Path(self.tmp.name)
        self.env = {"TOKEN_QUOTA_DIR": self.tmp.name, "TOKEN_QUOTA_DAILY": "1000000"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_reports_no_usage_when_no_ledger(self):
        result = run_script(STATUS, env_overrides=self.env)
        self.assertEqual(result.returncode, 0)
        self.assertIn("No usage recorded", result.stdout)

    def test_shows_usage_stats(self):
        make_ledger(self.ledger_dir, total_tokens=250_000, sessions=[
            {"timestamp": "2026-04-17T10:00:00", "input_tokens": 200_000, "output_tokens": 50_000}
        ])
        result = run_script(STATUS, env_overrides=self.env)
        self.assertIn("250,000", result.stdout)
        self.assertIn("750,000", result.stdout)

    def test_shows_ok_status_when_under_80_percent(self):
        make_ledger(self.ledger_dir, total_tokens=500_000)
        result = run_script(STATUS, env_overrides=self.env)
        self.assertIn("OK", result.stdout)

    def test_shows_warning_status_at_85_percent(self):
        make_ledger(self.ledger_dir, total_tokens=870_000)
        result = run_script(STATUS, env_overrides=self.env)
        self.assertIn("WARNING", result.stdout)

    def test_shows_exceeded_status_at_100_percent(self):
        make_ledger(self.ledger_dir, total_tokens=1_000_000)
        result = run_script(STATUS, env_overrides=self.env)
        self.assertIn("EXCEEDED", result.stdout)

    def test_shows_turn_count(self):
        make_ledger(self.ledger_dir, total_tokens=100_000, sessions=[
            {"timestamp": "2026-04-17T10:00:00"},
            {"timestamp": "2026-04-17T11:00:00"},
            {"timestamp": "2026-04-17T12:00:00"},
        ])
        result = run_script(STATUS, env_overrides=self.env)
        self.assertIn("3", result.stdout)


if __name__ == "__main__":
    unittest.main()
