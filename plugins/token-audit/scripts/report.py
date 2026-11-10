#!/usr/bin/env python3
"""Step 1: analyze local Claude Code transcripts (<config>/projects/**/*.jsonl) -> usage_summary.json."""
import json
import glob
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pricing
from pricing import PRICING, lookup, LONG_CONTEXT, IGNORED_MODELS

PROJECTS_DIR = pricing.projects_dir()
UNPRICED = defaultdict(lambda: dict(msgs=0, tokens=0))  # model -> counts (priced at $0)

STRIP_TAGS = [
    "system-reminder", "local-command-stdout", "local-command-caveat",
    "command-name", "command-message", "command-args", "attachment",
]

def strip_wrappers(text):
    for tag in STRIP_TAGS:
        text = re.sub(rf"<{tag}>.*?</{tag}>", "", text, flags=re.DOTALL)
    return text.strip()

def cost_for(model, usage):
    key, p = lookup(model)
    inp = usage.get("input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    cache_read = usage.get("cache_read_input_tokens", 0) or 0
    cc = usage.get("cache_creation") or {}
    w1h = cc.get("ephemeral_1h_input_tokens", 0) or 0
    w5m = cc.get("ephemeral_5m_input_tokens", 0) or 0
    # fallback if breakdown missing but cache_creation_input_tokens present
    if not cc and usage.get("cache_creation_input_tokens"):
        w5m = usage["cache_creation_input_tokens"]
    if not p:
        if model not in IGNORED_MODELS:
            u = UNPRICED[model]
            u["msgs"] += 1
            u["tokens"] += inp + out + cache_read + w1h + w5m
        return 0.0
    if key in LONG_CONTEXT and inp + cache_read + w1h + w5m > LONG_CONTEXT[key][0]:
        p = LONG_CONTEXT[key][1]
    return (
        inp * p["input"]
        + out * p["out"]
        + cache_read * p["read"]
        + w1h * p["write1h"]
        + w5m * p["write5m"]
    ) / 1_000_000

def main():
    files = glob.glob(os.path.join(PROJECTS_DIR, "**", "*.jsonl"), recursive=True)

    per_project = defaultdict(lambda: dict(cost=0.0, tokens_in=0, tokens_out=0, cache_read=0,
                                            cache_write=0, thinking=0, msgs=0, sessions=set(),
                                            prompts=0, prompt_chars=0))
    per_day = defaultdict(lambda: dict(cost=0.0, tokens_out=0, msgs=0, prompts=0))
    per_model = defaultdict(lambda: dict(cost=0.0, tokens_in=0, tokens_out=0, msgs=0,
                                          cache_read=0, cache_write=0))
    per_session = defaultdict(lambda: dict(cost=0.0, tokens_out=0, msgs=0, project=None,
                                            sidechain_cost=0.0, first_ts=None, last_ts=None))
    effort_stats = defaultdict(lambda: dict(cost=0.0, msgs=0, tokens_out=0))
    sidechain_cost_total = 0.0
    mainchain_cost_total = 0.0
    total_cache_read = 0
    total_cache_write = 0
    total_input_noncache = 0

    prompts = []  # (timestamp, project, session, char_len, word_len, is_slash_command)
    parse_errors = 0
    lines_seen = 0

    for path in files:
        rel = os.path.relpath(path, PROJECTS_DIR)
        project = rel.split(os.sep)[0]
        is_subagent_file = "subagents" in rel.split(os.sep)
        try:
            with open(path, errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    lines_seen += 1
                    try:
                        d = json.loads(line)
                    except Exception:
                        parse_errors += 1
                        continue

                    t = d.get("type")
                    sid = d.get("sessionId") or "unknown"

                    if t == "assistant":
                        msg = d.get("message", {})
                        model = msg.get("model")
                        usage = msg.get("usage") or {}
                        if not usage:
                            continue
                        c = cost_for(model, usage)
                        is_side = bool(d.get("isSidechain")) or is_subagent_file
                        ts = d.get("timestamp", "")
                        day = ts[:10] if ts else "unknown"

                        pp = per_project[project]
                        pp["cost"] += c
                        pp["tokens_in"] += usage.get("input_tokens", 0) or 0
                        pp["tokens_out"] += usage.get("output_tokens", 0) or 0
                        pp["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
                        cc = usage.get("cache_creation") or {}
                        cw = (cc.get("ephemeral_1h_input_tokens", 0) or 0) + (cc.get("ephemeral_5m_input_tokens", 0) or 0)
                        if not cc and usage.get("cache_creation_input_tokens"):
                            cw = usage["cache_creation_input_tokens"]
                        pp["cache_write"] += cw
                        pp["thinking"] += (usage.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0
                        pp["msgs"] += 1
                        pp["sessions"].add(sid)

                        pd = per_day[day]
                        pd["cost"] += c
                        pd["tokens_out"] += usage.get("output_tokens", 0) or 0
                        pd["msgs"] += 1

                        pm = per_model[model]
                        pm["cost"] += c
                        pm["tokens_in"] += usage.get("input_tokens", 0) or 0
                        pm["tokens_out"] += usage.get("output_tokens", 0) or 0
                        pm["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
                        pm["cache_write"] += cw
                        pm["msgs"] += 1

                        ps = per_session[sid]
                        ps["cost"] += c
                        ps["tokens_out"] += usage.get("output_tokens", 0) or 0
                        ps["msgs"] += 1
                        ps["project"] = project
                        if ts:
                            if ps["first_ts"] is None or ts < ps["first_ts"]:
                                ps["first_ts"] = ts
                            if ps["last_ts"] is None or ts > ps["last_ts"]:
                                ps["last_ts"] = ts
                        if is_side:
                            ps["sidechain_cost"] += c
                            sidechain_cost_total += c
                        else:
                            mainchain_cost_total += c

                        eff = d.get("effort") or "none"
                        pe = effort_stats[eff]
                        pe["cost"] += c
                        pe["msgs"] += 1
                        pe["tokens_out"] += usage.get("output_tokens", 0) or 0

                        total_cache_read += usage.get("cache_read_input_tokens", 0) or 0
                        total_cache_write += cw
                        total_input_noncache += usage.get("input_tokens", 0) or 0

                    elif t == "user" and not d.get("isSidechain"):
                        msg = d.get("message", {})
                        content = msg.get("content")
                        text = None
                        if isinstance(content, str):
                            text = content
                        elif isinstance(content, list):
                            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                            if texts:
                                text = "\n".join(texts)
                        if text is None:
                            continue
                        cleaned = strip_wrappers(text)
                        if not cleaned:
                            continue
                        ts = d.get("timestamp", "")
                        is_slash = cleaned.startswith("/")
                        prompts.append((ts, project, sid, len(cleaned), len(cleaned.split()), is_slash))
        except Exception as e:
            print(f"error reading {path}: {e}", file=sys.stderr)

    # finalize
    for p in per_project.values():
        p["sessions"] = len(p["sessions"])

    for ts, project, sid, clen, wlen, is_slash in prompts:
        day = ts[:10] if ts else "unknown"
        per_day[day]["prompts"] += 1
        per_project[project]["prompts"] += 1
        per_project[project]["prompt_chars"] += clen

    total_cost = sum(p["cost"] for p in per_project.values())

    out = dict(
        generated_at=datetime.now().isoformat(),
        files_scanned=len(files),
        lines_seen=lines_seen,
        parse_errors=parse_errors,
        total_cost_usd=total_cost,
        mainchain_cost_usd=mainchain_cost_total,
        sidechain_cost_usd=sidechain_cost_total,
        total_cache_read_tokens=total_cache_read,
        total_cache_write_tokens=total_cache_write,
        total_noncache_input_tokens=total_input_noncache,
        per_project={k: v for k, v in sorted(per_project.items(), key=lambda kv: -kv[1]["cost"])},
        per_model=dict(per_model),
        per_day={k: v for k, v in sorted(per_day.items())},
        effort_stats=dict(effort_stats),
        per_session_top50=sorted(
            ({**v, "session": k} for k, v in per_session.items()),
            key=lambda v: -v["cost"]
        )[:50],
        prompts_summary=dict(
            total=len(prompts),
            slash_commands=sum(1 for p in prompts if p[5]),
            avg_chars=sum(p[3] for p in prompts) / len(prompts) if prompts else 0,
            avg_words=sum(p[4] for p in prompts) / len(prompts) if prompts else 0,
            longest=sorted(prompts, key=lambda p: -p[3])[:15],
        ),
    )

    out["unpriced_models"] = {str(k): v for k, v in UNPRICED.items()}
    out["pricing_snapshot_date"] = pricing.PRICING_SNAPSHOT_DATE
    out_path = os.path.join(pricing.data_dir(), "usage_summary.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)

    if UNPRICED:
        print("!" * 70, file=sys.stderr)
        print("WARNING: unknown model ID(s) priced at $0 -- cost is UNDERSTATED:", file=sys.stderr)
        for k, v in UNPRICED.items():
            print("  %s: %d messages, %d tokens" % (k, v["msgs"], v["tokens"]), file=sys.stderr)
        print("Add them to PRICING in scripts/pricing.py (%s)" % pricing.PRICING_URL, file=sys.stderr)
        print("!" * 70, file=sys.stderr)
    print("wrote", out_path)
    print("done. cost=%.2f  files=%d  prompts=%d" % (total_cost, len(files), len(prompts)))

if __name__ == "__main__":
    main()
