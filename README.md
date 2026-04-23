[![Tests](https://github.com/thedavidwhiteside/claude-code-tokenbudget/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/thedavidwhiteside/claude-code-tokenbudget/actions/workflows/test.yml)

# Claude Code Daily Token Quota Plugin

Enforces a daily token budget for Claude Code using its native hook system.
Works with **any backend** — Bedrock, Vertex, direct API, or subscription.

## How it works

| Hook | Event | Action |
|------|-------|--------|
| `enforce_quota.py` | `UserPromptSubmit` | Blocks the prompt if today's usage ≥ limit |
| `track_tokens.py` | `Stop` | Records token usage after each turn |

Usage is stored in `~/.claude-token-quota/YYYY-MM-DD.json` and resets automatically each day.

---

## Installation

```bash
claude plugin marketplace add thedavidwhiteside/claude-code-tokenbudget
claude plugin install tokenbudget@claude-code-tokenbudget
```

This permanently installs the plugin. It will be active in all future Claude Code sessions without any extra flags.

### Try before installing

To test without installing permanently:

```bash
claude --plugin-dir /path/to/claude-code-tokenbudget
```

### Configuration

Override any of these in your `~/.claude/settings.json`:

```json
{
  "env": {
    "TOKEN_QUOTA_DAILY": "1000000",
    "TOKEN_QUOTA_DIR": "~/.claude-token-quota",
    "TOKEN_QUOTA_RETAIN_DAYS": "30"
  }
}
```

| Variable | Default | Description |
|---|---|---|
| `TOKEN_QUOTA_DAILY` | `1000000` | Daily token limit |
| `TOKEN_QUOTA_DIR` | `~/.claude-token-quota` | Where ledger files are stored |
| `TOKEN_QUOTA_RETAIN_DAYS` | `30` | How many days of usage history to keep |

**Rough token budgets by spend goal — Claude Sonnet 4.6 on AWS Bedrock:**

> **Note:** Prices below are examples only and will change. Always check the [AWS Bedrock pricing page](https://aws.amazon.com/bedrock/pricing/) for current rates.

Sonnet 4.6 standard pricing: ~$3.00 / 1M input tokens, ~$15.00 / 1M output tokens.
Assuming a ~4:1 input-to-output ratio, blended cost is roughly $5.40 / 1M tokens.

| Daily spend goal | ~Token budget |
|---|---|
| ~$5/day | 925,000 |
| ~$10/day | 1,850,000 |
| ~$20/day | 3,700,000 |

The default is 1,000,000 tokens/day (~$5.40/day at the example rates).

---

## Check status

Run `/tokenbudget:status` inside any Claude Code session to see today's usage.

![Status output](img/status.png)

When your quota is exceeded:

![Limit reached](img/limit.png)

---

## Caveats

- Token counts are read from the session transcript after each turn. They should be accurate but may differ slightly from your AWS bill due to rounding.
- The enforcer checks usage *before* a turn starts, so the very last turn before the limit may slightly exceed it (same behavior as Anthropic's own quota system).
- Requires Python 3.10+ (no external dependencies).

### Running tests

```bash
python3 -m unittest tests/test_plugin.py -v
```

### Contribution Guide

- Branch off `develop`
- Open a PR targeting `develop`

For bug fixes or new features, please include or update tests in `tests/test_plugin.py`.

