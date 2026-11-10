# claude-plugins

Claude Code plugin marketplace from the Boone/Andrews labs (public, MIT).
The marketplace is named `boonelab-plugins` (names starting with `claude-` are reserved).

    /plugin marketplace add BooneAndrewsLab/claude-plugins
    /plugin install usage-pacing@boonelab-plugins
    /plugin install token-audit@boonelab-plugins

## Plugins

- `usage-pacing`: weekly-quota pace alerts.
- `token-audit`: audit your local Claude Code token usage/cost and build a self-contained HTML dashboard
  (`/token-audit`; `--anonymize` for a shareable version). Python 3 stdlib only. Costs are API-list-price
  equivalents and do not match the weekly quota percentage.

## usage-pacing

Soft alerts on weekly Claude quota vs a linear pace (0% at the window start, 100% at the reset).
Needs a Pro/Max/Ultra subscription. Python 3 only, no dependencies.

Pieces:
- `scripts/pace.py statusline`: reads `rate_limits.seven_day` from the statusline JSON, prints
  `wk 48% / pace 69%`, and saves state to `~/.claude/usage-pacing/state.json`. The reset time
  comes from the data, so nothing is hardcoded.
- `hooks/hooks.json`: SessionStart + UserPromptSubmit hook injects a factual one-liner when over
  pace (or far under, at session start only), throttled. At session start it also refreshes stale
  state by scraping `claude -p "/usage"` (~8 s, only if state is >30 min old), so alerts work with
  no statusline at all, e.g. in a headless remote session. The script is copied to
  `~/.claude/usage-pacing/pace.py` so the settings.json entry survives plugin updates.
- `skills/usage-pacing`: wording rules + `/usage-pacing` on demand (`--fable` adds the Fable pool,
  scraped from `/usage`, since the statusline JSON has no per-model figures). Fails soft, never
  invents a number.

Options (`/plugin configure usage-pacing@boonelab-plugins`, or `/config`):

| Option | Values | Default |
|---|---|---|
| `display` | `statusline` (show `wk N% / pace M%`) / `silent` (track, draw nothing) | `statusline` |
| `alert_channel` | `context` (Claude relays a line in chat; also shows in remote/web sessions) / `push` (also asks Claude for a mobile push; needs Remote Control + push enabled in `/config`) / `none` | `context` |
| `over_pts` / `under_pts` | alert thresholds in percentage points | 8 / 20 |
| `throttle_hours` | min gap between alerts of one kind | 2 |

The statusline is terminal-only (it does not render in the web/mobile clients); `context`/`push`
alerts are how remote sessions hear about it.

Install, then wire the statusline (plugins cannot set `statusLine` themselves):

    /plugin marketplace add BooneAndrewsLab/claude-plugins
    /plugin install usage-pacing@boonelab-plugins
    /usage-pacing setup        # adds the statusLine entry; restart Claude Code

If you already have a statusLine, `setup` leaves it alone and prints the command to chain.
Skip `setup` entirely if you only want chat alerts.

## token-audit

Run `/token-audit`: it reads your local transcripts (`~/.claude/projects/**/*.jsonl`), prices them by
model, and writes `usage_summary.json`, `report_data.json` and a self-contained `dashboard.html` to
`~/.claude/token-audit/` (override with `TOKEN_AUDIT_DIR`).

- Costs are API-list-price equivalents from a dated pricing snapshot; unknown model IDs trigger a
  loud warning and a banner instead of silently counting as $0. They do not match the weekly quota
  percentage (quota is model-weighted).
- Findings and tips are computed from the data. Tips are deterministic rules with thresholds (e.g. subagent
  model mix, cache-write share, subagent starting context, long sessions); they are not personalised advice.
  New metrics: subagent cost by model, starting-context size (median/p90), longest sessions.
- `--anonymize` renames projects to `project-1`, `project-2`, ... so the dashboard can be shared
  (`usage_summary.json` still contains raw project names; share only the dashboard).
- Options (`/plugin configure token-audit@boonelab-plugins`): `publish` = `always` (default) / `ask` / `never`,
  and `anonymize` (default off; adds `--anonymize`). By default Claude publishes the dashboard as a **private
  artifact** after each audit and gives you the link, so you do not need to find a local file; the URL is kept in
  `~/.claude/token-audit/artifact_url` and reused for updates. The dashboard contains project names unless
  anonymize is on. Set `publish` to `never` to keep it local only. Publishing is done by Claude, never by a script.
- Python 3 standard library only.

## License

MIT, see `LICENSE`.
