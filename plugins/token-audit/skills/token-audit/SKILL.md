---
name: token-audit
description: Audit the user's local Claude Code token usage and cost (by model, project, session, cache, effort, week over week) and build a self-contained HTML dashboard. Use when asked to audit token usage or spend, find where tokens go, or refresh the usage dashboard.
---

# Token audit

Runs a local, stdlib-only pipeline over `~/.claude/projects/**/*.jsonl` (honours `CLAUDE_CONFIG_DIR`).
Nothing leaves the machine.

## Steps

1. Run the pipeline (outputs go to `~/.claude/token-audit/`, or `$TOKEN_AUDIT_DIR`):

   ```
   python3 "${CLAUDE_SKILL_DIR}/../../scripts/run_audit.py"
   ```

   If the dashboard is meant to be shared, add `--anonymize` (project names become `project-1`, `project-2`, ...;
   `usage_summary.json` still holds raw names, so share only `dashboard.html`/`report_data.json`).
   It writes `usage_summary.json`, `report_data.json` and `dashboard.html` there and prints a summary.
2. Relay the key numbers from the printed summary: period, total estimated cost, model mix,
   subagent share, session concentration, cache share, week over week.
3. Always state these caveats:
   - Dollars are API list-price equivalents from a pricing snapshot (date printed in the summary),
     not an invoice.
   - Raw tokens and these dollars do NOT match the weekly quota percentage in `/usage`: the quota is
     weighted by model. Do not try to reconcile them.
   - If the output contains a WARNING about unknown model IDs, say so prominently: those models were
     priced at $0 and the totals are understated. The fix is to add them to `scripts/pricing.py`.
4. Tell the user the dashboard path. Do not open or publish it automatically.

## Publishing (optional, only on request)

The dashboard is a plain HTML file. If the user wants it shared, tell the user first, then Claude
(not the script) publishes it with the Artifact tool: update only a URL the user supplies, otherwise
create a new private artifact. The data contains project names and usage figures, so confirm the
user is happy with that before publishing.
