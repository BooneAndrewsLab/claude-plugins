#!/usr/bin/env python3
"""Step 2: usage_summary.json -> report_data.json (compact shape for the dashboard),
including the computed "findings" list. Stdlib only."""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pricing
from pricing import lookup, IGNORED_MODELS

DATA_DIR = pricing.data_dir()
IN_PATH = os.path.join(DATA_DIR, "usage_summary.json")
OUT_PATH = os.path.join(DATA_DIR, "report_data.json")

# Tip thresholds (a tip fires only when the data crosses its threshold).
TIP_SIDECHAIN_SHARE = 50.0          # % of total cost in subagents/forks
TIP_SIDECHAIN_EXPENSIVE_SHARE = 30.0  # % of sidechain cost on opus/fable-family models
EXPENSIVE_FAMILIES = ("opus", "fable")
TIP_CACHE_WRITE_SHARE = 35.0        # % of total cost spent on cache writes
TIP_SIDECHAIN_START_TOKENS = 20_000  # median first-turn context of subagents
TIP_TOP_SESSIONS_SHARE = 30.0       # % of cost in the 8 costliest sessions
TIP_LONG_SESSION_HOURS = 24.0
TIP_EFFORT_MIN_SHARE = 20.0         # % of effort-tagged cost that counts as "notable"
TIP_EFFORT_PER_TURN_RATIO = 2.0     # high per-turn cost / medium per-turn cost
TIP_WOW_GROWTH = 30.0               # % week-over-week growth

QUOTA_NOTE = ("Raw token counts and the dollar figures here do NOT map onto the weekly quota "
              "percentage shown by /usage: the quota is weighted by model, so the same tokens "
              "consume different amounts on different models. Dollars are API list-price "
              "equivalents (pricing snapshot %s), a comparison tool rather than a quota or invoice figure.")

# Words dropped from project directory names (Claude Code encodes paths as -home-user-code-x).
SKIP_PATH_WORDS = {"home", "users", "code", "mnt", "storage", "src", "projects", "work"}
SKIP_PATH_WORDS |= {p.lower() for p in os.path.expanduser("~").split(os.sep) if p}


ANON = {}   # raw project dir -> "project-N" when --anonymize is given


def label(name):
    if ANON:
        return ANON.get(name, "other")
    parts = [p for p in name.split("-") if p]
    kept = [p for p in parts if p.lower() not in SKIP_PATH_WORDS]
    return "-".join(kept) if kept else name


def usd(n):
    return "$" + format(round(n), ",")


def pct(a, b):
    return 100.0 * a / b if b else 0.0


def make_findings(d, out):
    """Every sentence below is computed from the data. Returns [{title, body}]."""
    f = []
    total = out["meta"]["total_cost"]
    if total <= 0:
        return f
    # model mix
    models = out["models"]
    top = models[0]
    shares = ", ".join("%s %s (%.0f%%)" % (m["name"], usd(m["cost"]), pct(m["cost"], total))
                       for m in models[:4])
    f.append(dict(title="Model mix",
                  body="Estimated cost by model: %s. Check whether the most expensive model is doing work "
                       "a cheaper one could." % shares))
    # effort
    eff = out["effort"]
    if eff:
        tot_eff = sum(v["cost"] for v in eff.values())
        name, v = max(eff.items(), key=lambda kv: kv[1]["cost"])
        total_msgs = sum(v2["msgs"] for v2 in eff.values())
        per = ", ".join("%s: %s/turn" % (k, "$%.3f" % (v2["cost"] / v2["msgs"]))
                        for k, v2 in eff.items() if v2["msgs"])
        f.append(dict(title="Reasoning effort",
                      body="'%s' effort accounts for %.0f%% of cost (among turns with a recorded effort) "
                           "and %.0f%% of those turns. Average cost per turn: %s." %
                           (name, pct(v["cost"], tot_eff), pct(v["msgs"], total_msgs), per)))
    # subagents
    sc = out["meta"]["sidechain_cost"]
    f.append(dict(title="Subagents / forks",
                  body="Sidechain (subagent/fork) turns are %.0f%% of cost (%s of %s); the rest is "
                       "main-session work." % (pct(sc, total), usd(sc), usd(total))))
    # week over week
    if out["prev7_cost"] > 0:
        chg = pct(out["last7_cost"] - out["prev7_cost"], out["prev7_cost"])
        f.append(dict(title="Week over week",
                      body="Last 7 active days: %s vs %s for the 7 before (%+.0f%%)." %
                           (usd(out["last7_cost"]), usd(out["prev7_cost"]), chg)))
    # concentration
    ts = out["top_sessions"]
    if ts:
        top_sum = sum(s["cost"] for s in ts)
        longest = max(ts, key=lambda s: s["msgs"])
        f.append(dict(title="Session concentration",
                      body="The %d costliest sessions account for %.0f%% of all cost. The longest of them "
                           "ran %s turns%s; long uncleared sessions re-read their whole context every turn, "
                           "so they are where /clear and scoped reads pay off." %
                           (len(ts), pct(top_sum, total), format(longest["msgs"], ","),
                            " over %.0f h" % longest["duration_h"] if longest.get("duration_h") else "")))
    # cache
    f.append(dict(title="Prompt cache",
                  body="Cache reads are %.1f%% of input-side tokens. By category, cache reads cost %s, cache "
                       "writes %s, output %s, uncached input %s." % (
                           out["cache_hit_rate"], usd(out["token_categories"]["cache_read"]),
                           usd(out["token_categories"]["cache_write"]), usd(out["token_categories"]["output"]),
                           usd(out["token_categories"]["base_input"]))))
    if out["meta"].get("thinking_fraction") is not None:
        f.append(dict(title="Thinking tokens",
                      body="%.0f%% of output tokens are reported as thinking tokens." %
                           (100 * out["meta"]["thinking_fraction"])))
    return f


def make_tips(out):
    """Deterministic rules; each fires only when the data supports it.
    Returns [{id, title, body, evidence}]; numbers are interpolated from the data."""
    tips = []
    m = out["meta"]
    total = m["total_cost"]
    if total <= 0:
        return tips
    sc = m["sidechain_cost"]
    sc_share = pct(sc, total)
    sbm = out.get("sidechain_by_model") or []
    exp_cost = sum(x["cost"] for x in sbm if any(f in x["name"].lower() for f in EXPENSIVE_FAMILIES))
    exp_share = pct(exp_cost, sc)
    if sc_share > TIP_SIDECHAIN_SHARE and exp_share > TIP_SIDECHAIN_EXPENSIVE_SHARE:
        tips.append(dict(
            id="subagent-model",
            title="Set an explicit model per subagent",
            body="Subagents and forks are a large part of cost and much of it ran on the most expensive model "
                 "family. Choosing haiku or sonnet explicitly for routine delegated work, and delegating fewer, "
                 "larger tasks, may reduce this.",
            evidence="Sidechain turns are %.0f%% of cost (%s); %.0f%% of sidechain cost is on opus/fable-family models (%s)."
                     % (sc_share, usd(sc), exp_share, usd(exp_cost))))
    cw = out["token_categories"]["cache_write"]
    cw_share = pct(cw, total)
    if cw_share > TIP_CACHE_WRITE_SHARE:
        tips.append(dict(
            id="cache-writes",
            title="Cache writes are a large share of cost",
            body="High cache-write cost can come from many fresh contexts (new sessions, many subagents) or from "
                 "idle gaps long enough for the prompt cache to expire, so the context is written again. "
                 "Batching related work and avoiding tiny subagents may help; this data does not show which cause applies.",
            evidence="Cache writes cost %s, %.0f%% of total cost (write cost is approximated at the 5-minute rate)."
                     % (usd(cw), cw_share)))
    sctx = (m.get("start_context_tokens") or {}).get("sidechain") or {}
    if sctx.get("median") and sctx["median"] > TIP_SIDECHAIN_START_TOKENS:
        tips.append(dict(
            id="start-context",
            title="Subagents start with a large context",
            body="Each subagent's first turn already carries a large fixed prefix. Hypothesis, not a finding: "
                 "unused MCP servers, plugins or agent definitions inflate it. Check with /context in a fresh "
                 "session and trim what you do not use.",
            evidence="Median subagent starting context is %s tokens (p90 %s) across %s subagent starts."
                     % (format(round(sctx["median"]), ","), format(round(sctx["p90"]), ","), format(sctx["n"], ","))))
    ts = out["top_sessions"]
    top_share = pct(sum(s["cost"] for s in ts), total)
    ss = m.get("session_stats") or {}
    long_n = ss.get("over_24h") or 0
    if top_share > TIP_TOP_SESSIONS_SHARE or long_n > 0:
        parts = []
        if top_share > TIP_TOP_SESSIONS_SHARE:
            parts.append("the %d costliest sessions are %.0f%% of cost" % (len(ts), top_share))
        if long_n:
            parts.append("%d session(s) spanned more than %d h (%.0f%% of cost; longest %.0f h)" % (
                long_n, TIP_LONG_SESSION_HOURS, pct(ss["over_24h_cost"], total), ss["longest_hours"]))
        tips.append(dict(
            id="long-sessions",
            title="Use /clear at breakpoints and keep handoff files",
            body="Long sessions re-read their growing context every turn. Clearing when a sub-task is done and "
                 "writing a short handoff file for what must carry over keeps later turns cheaper.",
            evidence="; ".join(parts).capitalize() + "."))
    eff = out["effort"]
    if eff.get("high") and eff.get("medium") and eff["high"]["msgs"] and eff["medium"]["msgs"]:
        tot_eff = sum(v["cost"] for v in eff.values())
        h, md = eff["high"], eff["medium"]
        hs = pct(h["cost"], tot_eff)
        ratio = (h["cost"] / h["msgs"]) / (md["cost"] / md["msgs"]) if md["cost"] else 0
        if hs > TIP_EFFORT_MIN_SHARE and ratio > TIP_EFFORT_PER_TURN_RATIO:
            tips.append(dict(
                id="high-effort",
                title="Reserve high effort for work that needs it",
                body="High-effort turns cost noticeably more per turn than medium. Part of that gap may come from "
                     "which models and tasks get high effort rather than from effort itself, so treat the ratio as "
                     "an upper bound.",
                evidence="High effort is %.0f%% of effort-tagged cost at %s/turn vs %s/turn for medium (%.1fx)."
                         % (hs, "$%.3f" % (h["cost"] / h["msgs"]), "$%.3f" % (md["cost"] / md["msgs"]), ratio)))
    if out["prev7_cost"] > 0:
        chg = pct(out["last7_cost"] - out["prev7_cost"], out["prev7_cost"])
        if chg > TIP_WOW_GROWTH:
            tips.append(dict(
                id="growth",
                title="Spend grew week over week (informational)",
                body="Recent spend is well above the previous week. This may be a bigger workload rather than "
                     "waste; the other tips show where to look if it is unexpected.",
                evidence="Last 7 active days %s vs %s before (%+.0f%%)." % (usd(out["last7_cost"]), usd(out["prev7_cost"]), chg)))
    return tips


def main():
    if not os.path.exists(IN_PATH):
        sys.exit("missing %s -- run report.py first" % IN_PATH)
    d = json.load(open(IN_PATH))
    if "--anonymize" in sys.argv[1:] or os.environ.get("TOKEN_AUDIT_ANONYMIZE"):
        ranked = sorted(d["per_project"].items(), key=lambda kv: -kv[1]["cost"])
        ANON.update({k: "project-%d" % (i + 1) for i, (k, _) in enumerate(ranked)})

    unpriced = {m: v for m, v in d.get("unpriced_models", {}).items()}
    for m in d["per_model"]:
        if m not in IGNORED_MODELS and lookup(m)[1] is None:
            unpriced.setdefault(m, dict(msgs=d["per_model"][m]["msgs"], tokens=0))
    if unpriced:
        print("!" * 70, file=sys.stderr)
        print("WARNING: unknown model ID(s) priced at $0; all costs are UNDERSTATED: %s" %
              ", ".join(sorted(unpriced)), file=sys.stderr)
        print("Add them to PRICING in scripts/pricing.py (%s)" % pricing.PRICING_URL, file=sys.stderr)
        print("!" * 70, file=sys.stderr)

    days = d["per_day"]
    day_keys = sorted(k for k in days if k != "unknown")
    daily = [dict(date=k, cost=round(days[k]["cost"], 2), msgs=days[k]["msgs"],
                  prompts=days[k]["prompts"]) for k in day_keys]
    last7, prev7 = day_keys[-7:], (day_keys[-14:-7] if len(day_keys) >= 14 else [])

    tot_read = d["total_cache_read_tokens"]
    tot_write = d["total_cache_write_tokens"]
    tot_in = d["total_noncache_input_tokens"]
    denom = tot_read + tot_write + tot_in
    total_out = sum(v["tokens_out"] for v in d["per_model"].values())
    thinking = sum(v.get("thinking", 0) for v in d["per_project"].values())

    meta = dict(
        generated_at=d["generated_at"],
        files_scanned=d["files_scanned"],
        total_cost=round(d["total_cost_usd"], 2),
        mainchain_cost=round(d["mainchain_cost_usd"], 2),
        sidechain_cost=round(d["sidechain_cost_usd"], 2),
        total_prompts=d["prompts_summary"]["total"],
        total_msgs=sum(v["msgs"] for v in d["per_project"].values()),
        first_day=day_keys[0] if day_keys else None,
        last_day=day_keys[-1] if day_keys else None,
        active_days=len(day_keys),
        pricing_snapshot_date=pricing.PRICING_SNAPSHOT_DATE,
        unpriced_models=unpriced,
        quota_note=QUOTA_NOTE % pricing.PRICING_SNAPSHOT_DATE,
        thinking_fraction=(thinking / total_out) if total_out and thinking else None,
        start_context_tokens=d.get("start_context_tokens"),
        session_stats=d.get("session_stats"),
        tokens_by_model={m: dict(input=v["tokens_in"], output=v["tokens_out"],
                                 cache_read=v["cache_read"], cache_write=v["cache_write"])
                         for m, v in d["per_model"].items() if m not in IGNORED_MODELS},
    )

    projects = []
    for k, v in d["per_project"].items():
        projects.append(dict(name=label(k), cost=round(v["cost"], 2), sessions=v["sessions"],
                             msgs=v["msgs"], prompts=v["prompts"],
                             ratio=round(v["msgs"] / v["prompts"], 1) if v["prompts"] else None))
    projects.sort(key=lambda p: -p["cost"])

    models = [dict(name=k, cost=round(v["cost"], 2), msgs=v["msgs"])
              for k, v in d["per_model"].items() if k not in IGNORED_MODELS]
    models.sort(key=lambda m: -m["cost"])

    cat = dict(cache_read=0.0, cache_write=0.0, output=0.0, base_input=0.0)
    for k, v in d["per_model"].items():
        p = lookup(k)[1]
        if not p:
            continue
        cat["cache_read"] += v["cache_read"] * p["read"] / 1e6
        cat["output"] += v["tokens_out"] * p["out"] / 1e6
        cat["cache_write"] += v["cache_write"] * p["write5m"] / 1e6  # approx: mixed 1h/5m writes
        cat["base_input"] += v["tokens_in"] * p["input"] / 1e6

    effort = {k: dict(cost=round(v["cost"], 2), msgs=v["msgs"])
              for k, v in d["effort_stats"].items() if k != "none"}

    top_sessions = []
    for s in d["per_session_top50"][:8]:
        dur = None
        if s["first_ts"] and s["last_ts"]:
            t1 = datetime.fromisoformat(s["first_ts"].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(s["last_ts"].replace("Z", "+00:00"))
            dur = round((t2 - t1).total_seconds() / 3600, 1)
        top_sessions.append(dict(project=label(s["project"]), cost=round(s["cost"], 2), msgs=s["msgs"],
                                 sidechain_cost=round(s["sidechain_cost"], 2), duration_h=dur))

    out = dict(
        meta=meta, daily=daily,
        last7_cost=round(sum(days[k]["cost"] for k in last7), 2),
        prev7_cost=round(sum(days[k]["cost"] for k in prev7), 2),
        cache_hit_rate=round(pct(tot_read, denom), 2),
        projects=projects, models=models,
        token_categories={k: round(v, 2) for k, v in cat.items()},
        effort=effort, top_sessions=top_sessions,
    )
    out["sidechain_by_model"] = sorted(
        (dict(name=k, cost=round(v["cost"], 2), msgs=v["msgs"])
         for k, v in (d.get("sidechain_by_model") or {}).items() if k not in IGNORED_MODELS),
        key=lambda x: -x["cost"])
    out["findings"] = make_findings(d, out)
    out["tips"] = make_tips(out)
    json.dump(out, open(OUT_PATH, "w"), indent=2)
    print("wrote", OUT_PATH)


if __name__ == "__main__":
    main()
