---
name: token-audit
description: Audit the user's local Claude Code token usage and cost (by model, project, session, cache, effort, week over week) and build a self-contained HTML dashboard. Use when asked to audit token usage or spend, find where tokens go, or refresh the usage dashboard.
---

# Token audit

Runs a local, stdlib-only pipeline over `~/.claude/projects/**/*.jsonl` (honours `CLAUDE_CONFIG_DIR`).
Nothing leaves the machine.

## Steps

Settings (plugin options): publish = `${user_config.publish}` (always / ask / never), anonymize = `${user_config.anonymize}`.

1. Run the pipeline (outputs go to `~/.claude/token-audit/`, or `$TOKEN_AUDIT_DIR`). If anonymize is `true`, add `--anonymize`
   (project names become `project-1`, `project-2`, ...; `usage_summary.json` still holds raw names, so only
   `dashboard.html`/`report_data.json` are shareable):

   ```
   python3 "${CLAUDE_SKILL_DIR}/../../scripts/run_audit.py"
   ```

   It writes `usage_summary.json`, `report_data.json` and `dashboard.html` there and prints a summary
   (findings, then computed tips).
2. Publish according to the publish setting (Claude does this with the Artifact tool, never a script):
   - `never`: do not publish; the answer gives the local `dashboard.html` path.
   - `ask`: ask the user once whether to publish, then follow `always` if yes.
   - `always`: publish without asking, but say what was published.
   - Remember the artifact URL in `~/.claude/token-audit/artifact_url` (plain text, one line; user data dir, never in a repo).
     If it exists (and the user has not objected), read that artifact first, then republish to that URL with the
     dashboard (copy `dashboard.html` into the session scratchpad if the tool requires it). Otherwise create a new
     private artifact: title "Claude Code Usage Audit", icon "chart", a one-sentence description, label = plugin version + date;
     then write its URL to that file. Never hardcode a URL.
   - After publishing, call the Artifact `open` action only if the publish result did not already surface the
     artifact to the user (do not open twice).
   - If publishing fails, fall back to the local path and say so.
   - First time only (no `artifact_url` file yet): tell the user once that artifacts are private by default, that the
     dashboard contains project names unless anonymize is on, and that they can switch publishing off with the
     `publish` option (`/plugin configure token-audit`).
3. Final answer: put the artifact link first (the local path only as a fallback), then relay the key numbers: period,
   total estimated cost, model mix, subagent share, session concentration, cache share, week over week, and the
   computed tips.
4. Then add 2 or 3 tips of your own under the label "Claude's interpretation (not computed)", at most ~5 lines,
   grounded in the printed numbers and distinguishing what the data shows from what you infer. Do not repeat the computed tips.
5. Always state these caveats:
   - Dollars are API list-price equivalents from a pricing snapshot (date printed in the summary),
     not an invoice.
   - Raw tokens and these dollars do NOT match the weekly quota percentage in `/usage`: the quota is
     weighted by model. Do not try to reconcile them.
   - If the output contains a WARNING about unknown model IDs, say so prominently: those models were
     priced at $0 and the totals are understated. The fix is to add them to `scripts/pricing.py`.
