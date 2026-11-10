#!/usr/bin/env python3
"""Step 3: splice report_data.json into assets/dashboard-template.html -> dashboard.html."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pricing

START, END = "/*__USAGE_DATA_START__*/", "/*__USAGE_DATA_END__*/"
here = os.path.dirname(os.path.abspath(__file__))
tpl = open(os.path.join(here, "..", "assets", "dashboard-template.html")).read()
data = json.load(open(os.path.join(pricing.data_dir(), "report_data.json")))
a, b = tpl.index(START), tpl.index(END)
blob = json.dumps(data).replace("</", "<\\/")  # keep </script> out of the JSON
out = os.path.join(pricing.data_dir(), "dashboard.html")
open(out, "w").write(tpl[:a + len(START)] + blob + tpl[b:])
print("wrote", out)
