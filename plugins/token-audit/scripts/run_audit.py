#!/usr/bin/env python3
"""Run the whole audit: report -> extract -> dashboard. Outputs go to
$TOKEN_AUDIT_DIR or ~/.claude/token-audit/ (survives plugin updates).
Pass --anonymize to replace project names with project-1, project-2, ... (safe to share)."""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
flags = ["--anonymize"] if "--anonymize" in sys.argv[1:] else []   # project-1, project-2, ... for sharing
for step in ("report.py", "extract.py", "build_dashboard.py"):
    r = subprocess.run([sys.executable, os.path.join(here, step)] + (flags if step == "extract.py" else []))
    if r.returncode:
        sys.exit("step %s failed" % step)

# Short plain-text summary (computed from report_data.json) for the caller to relay.
import json
sys.path.insert(0, here)
import pricing
d = json.load(open(os.path.join(pricing.data_dir(), "report_data.json")))
m = d["meta"]
print("\n=== token-audit summary ===")
print("Period: %s to %s (%d active days), %d transcript files" %
      (m["first_day"], m["last_day"], m["active_days"], m["files_scanned"]))
print("Estimated API-list-price equivalent: $%s (pricing snapshot %s)" %
      (format(round(m["total_cost"]), ","), m["pricing_snapshot_date"]))
for f in d["findings"]:
    print("- %s: %s" % (f["title"], f["body"]))
if d.get("tips"):
    print("Tips (computed rules, not personalised advice):")
    for t in d["tips"]:
        print("- %s: %s (%s)" % (t["title"], t["body"], t["evidence"]))
if m["unpriced_models"]:
    print("WARNING: unknown model IDs priced at $0 (costs understated): " +
          ", ".join(sorted(m["unpriced_models"])))
print("NOTE: " + m["quota_note"])
print("Outputs in", pricing.data_dir(), "(dashboard.html is self-contained)")
