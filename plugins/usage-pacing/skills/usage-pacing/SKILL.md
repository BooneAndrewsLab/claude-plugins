---
name: usage-pacing
description: Report weekly Claude quota usage against a linear pace. Use at the start of a big task, after a long agent batch, at /clear breakpoints, and before launching expensive (Opus/Fable) agents or fan-outs; also when a hook-injected "Weekly quota status" fact needs relaying. User can run /usage-pacing for an on-demand reading, or /usage-pacing setup to wire the statusline.
---

# Usage pacing

The weekly quota resets once a week; the linear target is 0% at the start of the
window and 100% at the reset. This plugin computes where the user is against it.

## Getting the number

Run (from Bash), never compute the target in your head:

    python3 "${CLAUDE_SKILL_DIR}/../../scripts/pace.py" report

It prints one line, e.g. `Weekly 48%, target 69%: 21 pts under pace; 51 h to reset.`
- Add `--fable` when Fable/Opus work is about to launch or the Fable pool is the question
  (this scrapes `claude -p "/usage"`, a few seconds).
- If it prints a failure message, relay that and ask the user to check `/usage`.
  Never invent or estimate a percentage.

## Wording rules

- One line, informational, no lecture. Example: "48% weekly usage, 21 pts under the linear
  target: room for heavier agents."
- Over-use matters more: say it *before* launching Opus/Fable work or big fan-outs.
- Under-use is a hint, not a nag.
- At most once per natural breakpoint; do not run the script every turn.
- Do not change the work plan because of an alert unless the user says so.
- If a hook injected a "Weekly quota status" fact, relay it as one line at the next
  natural breakpoint instead of running the script again.

## `/usage-pacing setup`

If the user asks to set up (or pacing numbers are never available): run

    python3 "${CLAUDE_SKILL_DIR}/../../scripts/pace.py" setup

It adds the statusLine entry to `~/.claude/settings.json` (plugins cannot do this
themselves) and refuses to overwrite an existing statusLine, printing how to chain it.
Tell the user to restart Claude Code. Settings (display, alert channel, thresholds) live in
`/plugin configure usage-pacing@boonelab-plugins`; the statusline is optional.
