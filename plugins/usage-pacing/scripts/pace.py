#!/usr/bin/env python3
"""usage-pacing: weekly Claude quota vs a linear pace.

Modes (first argument):
  statusline  stdin = statusline JSON; writes state, prints a short line.
  hook        stdin = hook JSON; prints hook JSON with additionalContext when off pace.
  report      prints one line from the state file (add --fable to also scrape /usage).
  scrape      one line from `claude -p /usage` only (no state needed).
  setup       adds the statusLine entry to ~/.claude/settings.json (never overwrites a foreign one).

Options come from the plugin's userConfig (env CLAUDE_PLUGIN_OPTION_*): display, alert_channel,
over_pts, under_pts, throttle_hours. The statusline process cannot see them, so the SessionStart
hook copies `display` into the state file, and copies this script to a fixed path (STABLE) so the
settings.json statusLine entry survives plugin updates.
"""
import json, os, re, shlex, shutil, subprocess, sys, tempfile, time
from datetime import datetime, timedelta

WEEK = 7 * 86400
STATE_DIR = os.path.expanduser("~/.claude/usage-pacing")
STATE = os.path.join(STATE_DIR, "state.json")
STABLE = os.path.join(STATE_DIR, "pace.py")   # copy of this script, referenced from settings.json
STALE_S = 12 * 3600                  # ignore state older than this for alerts
REFRESH_S = 30 * 60                  # state older than this is refreshed by scraping /usage
GUARD = "USAGE_PACING_SCRAPING"      # set for the scrape subprocess so its own hooks don't recurse


def cfg(name, default, cast=str):
    v = os.environ.get("CLAUDE_PLUGIN_OPTION_" + name.upper())
    try:
        return cast(v) if v not in (None, "") else default
    except ValueError:
        return default


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
    if st.get("config", {}).get("display", "statusline") == "silent":
        return                       # state is still written; nothing is drawn
    t, d, _ = pace(used, rs)
    print(f"wk {used:.0f}% / pace {t:.0f}%")


def sync(st):
    """SessionStart housekeeping: stable script copy + config for the statusline process."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        src = os.path.abspath(__file__)
        if os.path.abspath(STABLE) != src:
            shutil.copyfile(src, STABLE)
    except OSError:
        pass
    st["config"] = {"display": cfg("display", "statusline")}


def refresh(st):
    """Scrape `claude -p /usage` into the state when it is stale (no statusline running)."""
    now = time.time()
    fresh = now - st.get("updated", 0) <= REFRESH_S and st.get("resets_at", 0) > now
    if fresh or now - st.get("scrape_failed", 0) < REFRESH_S:
        return
    try:
        u = parse_usage(usage_text(30))
    except Exception:
        u = {}
    if "all" in u and "resets_at" in u:
        st.update(used=u["all"], resets_at=u["resets_at"], updated=now, source="scrape")
    else:
        st["scrape_failed"] = now


def mode_hook():
    if os.environ.get(GUARD):
        return
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        return
    name = ev.get("hook_event_name", "UserPromptSubmit")
    st = load_state()
    if name == "SessionStart":
        sync(st)
        refresh(st)
        save_state(st)
    channel = cfg("alert_channel", "context")
    if channel == "none" or "used" not in st or time.time() - st.get("updated", 0) > STALE_S:
        return
    if st["resets_at"] < time.time():
        return                       # window rolled over; wait for fresh numbers
    over, under = cfg("over_pts", 8.0, float), cfg("under_pts", 20.0, float)
    throttle = cfg("throttle_hours", 2.0, float) * 3600
    t, d, _ = pace(st["used"], st["resets_at"])
    if d >= over:
        kind = "over"
    elif d <= -under and name == "SessionStart":
        kind = "under"
    else:
        return
    if time.time() - st.get("alerted", {}).get(kind, 0) < throttle:
        return
    st.setdefault("alerted", {})[kind] = time.time()
    save_state(st)
    msg = ("Weekly quota status (facts, from the usage-pacing plugin): "
           + line(st["used"], st["resets_at"])
           + " Relay this to the user as one short line at the next natural breakpoint "
             "(not every turn); informational only, do not change the work plan.")
    if channel == "push":
        msg += (" Also send it once as a mobile push with the PushNotification tool "
                "(status proactive, under 200 characters).")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": name,
                                             "additionalContext": msg}}))


def usage_text(timeout=90):
    d = tempfile.mkdtemp()
    r = subprocess.run(["timeout", str(timeout), "claude", "-p", "/usage"], cwd=d,
                       capture_output=True, text=True, env={**os.environ, GUARD: "1"})
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
    os.makedirs(STATE_DIR, exist_ok=True)
    src = os.path.abspath(__file__)
    if os.path.abspath(STABLE) != src:
        shutil.copyfile(src, STABLE)
    cmd = f"python3 {shlex.quote(STABLE)} statusline"
    try:
        with open(path) as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    old = (s.get("statusLine") or {}).get("command", "")
    if "statusLine" in s and "pace.py statusline" not in old:
        print("A statusLine is already configured, not touching it:\n  "
              + json.dumps(s["statusLine"]) + "\nTo add pacing, make that command also run:\n  "
              + cmd + "\n(it reads the same JSON on stdin and prints `wk N% / pace M%`).")
        return 1
    s["statusLine"] = {"type": "command", "command": cmd}
    with open(path, "w") as f:
        json.dump(s, f, indent=2)
        f.write("\n")
    print(f"{'Updated' if old else 'Added'} statusLine in {path}: {cmd}\n"
          "Restart Claude Code to pick it up. The script lives at a fixed path, so plugin updates "
          "do not break it (the SessionStart hook keeps the copy current).")
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
