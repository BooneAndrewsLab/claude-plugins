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
- `hooks/hooks.json`: SessionStart + UserPromptSubmit hook injects a factual one-liner when
  >= 8 pts over pace (or >= 20 under, at session start only), at most once per 2 h per kind.
- `skills/usage-pacing`: wording rules + `/usage-pacing` on demand (`--fable` adds the Fable pool,
  scraped from `claude -p "/usage"`, since the statusline JSON has no per-model figures).
  Falls back to that scrape when no fresh state exists; fails soft, never invents a number.

Install, then wire the statusline (plugins cannot set `statusLine` themselves):

    /plugin marketplace add BooneAndrewsLab/claude-plugins
    /plugin install usage-pacing@boonelab-plugins
    /usage-pacing setup        # adds the statusLine entry; restart Claude Code

If you already have a statusLine, `setup` leaves it alone and prints the command to chain.
The setup path points into the plugin cache; re-run it after a plugin update.
