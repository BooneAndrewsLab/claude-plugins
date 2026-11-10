#!/usr/bin/env python3
"""usage-pacing: weekly Claude quota vs a linear pace.

Modes (first argument):
  statusline  stdin = statusline JSON; writes state, prints a short line.
  hook        stdin = hook JSON; prints hook JSON with additionalContext when off pace.
  report      prints one line from the state file (add --fable to also scrape /usage).
  scrape      one line from `claude -p /usage` only (no state needed).
  setup       adds the statusLine entry to ~/.claude/settings.json (never overwrites).
"""
import json, os, re, subprocess, sys, tempfile, time
from datetime import datetime, timedelta

WEEK = 7 * 86400
STATE_DIR = os.path.expanduser("~/.claude/usage-pacing")
STATE = os.path.join(STATE_DIR, "state.json")
OVER_PTS, UNDER_PTS = 8, 20          # alert thresholds, percentage points
THROTTLE_S = 2 * 3600                # min gap between injected alerts of one kind
STALE_S = 12 * 3600                  # ignore state older than this


def pace(used, resets_at, now=None):
    """Return (target_pct, delta_pts, hours_left); delta>0 means over pace."""
    now = time.time() if now is None else now
    start = resets_at - WEEK
    target = min(max((now - start) / WEEK * 100, 0.0), 100.0)
    return target, used - target, max(resets_at - now, 0) / 3600


def line(used, resets_at, fable=None, now=None):
    t, d, h = pace(used, resets_at, now)
    side = "over" if d > 0 else "under"
    f = f" (Fable {fable:.0f}%)" if fable is not None else ""
    return (f"Weekly {used:.0f}%{f}, target {t:.0f}%: {abs(d):.0f} pts {side} pace; "
            f"{h:.0f} h to reset.")


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=STATE_DIR)
    with os.fdopen(fd, "w") as f:
        json.dump(st, f)
    os.replace(tmp, STATE)


def mode_statusline():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    sd = (data.get("rate_limits") or {}).get("seven_day") or {}
    used, rs = sd.get("used_percentage"), sd.get("resets_at")
    if used is None or rs is None:
        return                       # no data yet (first turn, non-subscriber): print nothing
    st = load_state()
    st.update(used=used, resets_at=rs, updated=time.time())
    save_state(st)
    t, d, _ = pace(used, rs)
    print(f"wk {used:.0f}% / pace {t:.0f}%")


def mode_hook():
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        return
    name = ev.get("hook_event_name", "UserPromptSubmit")
    st = load_state()
    if not st or time.time() - st.get("updated", 0) > STALE_S:
        return
    if st["resets_at"] < time.time():
        return                       # window rolled over; wait for fresh numbers
    t, d, _ = pace(st["used"], st["resets_at"])
    if d >= OVER_PTS:
        kind = "over"
    elif d <= -UNDER_PTS and name == "SessionStart":
        kind = "under"
    else:
        return
    last = st.get("alerted", {}).get(kind, 0)
    if time.time() - last < THROTTLE_S:
        return
    st.setdefault("alerted", {})[kind] = time.time()
    save_state(st)
    msg = ("Weekly quota status (facts, from the usage-pacing plugin): "
           + line(st["used"], st["resets_at"])
           + " Relay this to the user as one short line at the next natural breakpoint "
             "(not every turn); informational only, do not change the work plan.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": name,
                                             "additionalContext": msg}}))


def usage_text():
    d = tempfile.mkdtemp()
    r = subprocess.run(["timeout", "90", "claude", "-p", "/usage"], cwd=d,
                       capture_output=True, text=True)
    return r.stdout


def parse_usage(text):
    """-> dict(all=%, fable=%, resets_at=epoch|None) from `/usage` output; may be partial."""
    out = {}
    m = re.search(r"Current week \(all models\): (\d+)% used(?: · resets ([^\n(]+?)\s*\(([^)]+)\))?", text)
    if m:
        out["all"] = float(m.group(1))
        if m.group(2):
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(m.group(3))
                s = m.group(2).strip().replace(" ", "", 0)
                mon_day, clock = [x.strip() for x in s.split(",")]
                clock = clock.lower()
                fmt = "%I:%M%p" if ":" in clock else "%I%p"
                now = datetime.now(tz)
                dt = datetime.strptime(f"{mon_day} {now.year} {clock}", f"%b %d %Y {fmt}").replace(tzinfo=tz)
                if dt < now - timedelta(days=1):
                    dt = dt.replace(year=now.year + 1)
                out["resets_at"] = dt.timestamp()
            except Exception:
                pass
    m = re.search(r"Current week \(Fable\): (\d+)% used", text)
    if m:
        out["fable"] = float(m.group(1))
    return out


def mode_report(want_fable, scrape_only=False):
    st = {} if scrape_only else load_state()
    fresh = st and time.time() - st.get("updated", 0) <= STALE_S and st["resets_at"] > time.time()
    fable = None
    if not fresh or want_fable:
        try:
            u = parse_usage(usage_text())
        except Exception as e:
            u = {}
        fable = u.get("fable")
        if not fresh:
            if "all" not in u or "resets_at" not in u:
                print("usage-pacing: could not get the weekly figure (statusline state missing/stale "
                      "and `claude -p /usage` failed to parse). Please check /usage yourself.")
                return 1
            st = {"used": u["all"], "resets_at": u["resets_at"]}
    print(line(st["used"], st["resets_at"], fable))
    return 0


def mode_setup():
    path = os.path.expanduser("~/.claude/settings.json")
    script = os.path.abspath(__file__)
    cmd = f"python3 {script} statusline"
    try:
        with open(path) as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    if "statusLine" in s:
        print("A statusLine is already configured, not touching it:\n  "
              + json.dumps(s["statusLine"]) + "\nTo add pacing, make that command also run:\n  "
              + cmd + "\n(it reads the same JSON on stdin and prints `wk N% / pace M%`).")
        return 1
    s["statusLine"] = {"type": "command", "command": cmd}
    with open(path, "w") as f:
        json.dump(s, f, indent=2)
        f.write("\n")
    print(f"Added statusLine to {path}: {cmd}\nRestart Claude Code to pick it up. "
          "Note: the path points into the plugin cache and changes when the plugin updates; re-run setup then.")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:] or ["report"]
    m = a[0]
    if m == "statusline":
        mode_statusline()
    elif m == "hook":
        mode_hook()
    elif m == "report":
        sys.exit(mode_report("--fable" in a))
    elif m == "scrape":
        sys.exit(mode_report(True, scrape_only=True))
    elif m == "setup":
        sys.exit(mode_setup())
    else:
        print(__doc__)
        sys.exit(2)
