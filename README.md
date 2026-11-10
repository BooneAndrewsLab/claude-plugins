# claude-plugins

Private Claude Code plugin marketplace for the Boone/Andrews labs
(marketplace name: `boonelab-plugins`; `claude-` names are reserved).

    /plugin marketplace add BooneAndrewsLab/claude-plugins
    /plugin install usage-pacing@boonelab-plugins

## Plugins

- `usage-pacing`: weekly-quota pace alerts (WIP). Tracking issue (private):
  https://github.com/BooneAndrewsLab/lab-work/issues/1

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
