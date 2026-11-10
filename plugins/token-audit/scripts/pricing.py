"""Shared pricing table and path helpers for token-audit (stdlib only)."""
import os

# $ per million tokens. Snapshot taken from
# https://platform.claude.com/docs/en/about-claude/pricing
# Prices are API list prices; model IDs are the usual API IDs (dots become dashes).
PRICING_SNAPSHOT_DATE = "2026-11-10"
PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing"

def _p(i, o, w5, w1, r):
    return dict(input=i, out=o, write5m=w5, write1h=w1, read=r)

PRICING = {
    "claude-fable-5-2":  _p(8.0, 40.0, 10.0, 16.0, 0.20),
    "claude-mythos-5-2": _p(8.0, 40.0, 10.0, 16.0, 0.20),
    "claude-fable-5-1":  _p(10.0, 50.0, 12.50, 20.0, 0.25),
    "claude-mythos-5-1": _p(10.0, 50.0, 12.50, 20.0, 0.25),
    "claude-fable-5":    _p(10.0, 50.0, 12.50, 20.0, 1.0),
    "claude-mythos-5":   _p(10.0, 50.0, 12.50, 20.0, 1.0),
    "claude-opus-5-5":   _p(4.0, 20.0, 5.0, 8.0, 0.20),
    "claude-opus-5":     _p(5.0, 25.0, 6.25, 10.0, 0.50),
    "claude-opus-4-8":   _p(5.0, 25.0, 6.25, 10.0, 0.50),
    "claude-opus-4-7":   _p(5.0, 25.0, 6.25, 10.0, 0.50),
    "claude-opus-4-6":   _p(5.0, 25.0, 6.25, 10.0, 0.50),
    "claude-opus-4-5":   _p(5.0, 25.0, 6.25, 10.0, 0.50),
    "claude-opus-4-1":   _p(15.0, 75.0, 18.75, 30.0, 1.50),
    "claude-opus-4":     _p(15.0, 75.0, 18.75, 30.0, 1.50),
    "claude-sonnet-5-5": _p(2.0, 10.0, 2.50, 4.0, 0.10),
    "claude-sonnet-5":   _p(2.0, 10.0, 2.50, 4.0, 0.20),
    "claude-sonnet-4-6": _p(3.0, 15.0, 3.75, 6.0, 0.30),
    "claude-sonnet-4-5": _p(3.0, 15.0, 3.75, 6.0, 0.30),
    "claude-sonnet-4":   _p(3.0, 15.0, 3.75, 6.0, 0.30),
    "claude-haiku-4-5":  _p(1.0, 5.0, 1.25, 2.0, 0.10),
    # Haiku 5.5 is tiered by prompt size: the rates below apply up to 100k prompt
    # tokens; above that the "long" rates apply (see LONG_CONTEXT).
    "claude-haiku-5-5":  _p(0.10, 0.50, 0.125, 0.20, 0.01),
}
LONG_CONTEXT = {
    "claude-haiku-5-5": (100_000, _p(0.50, 2.50, 0.625, 1.0, 0.05)),
}
# Not priced on purpose (no tokens billed / not a real model).
IGNORED_MODELS = {"<synthetic>", None, ""}


def lookup(model):
    """Return the PRICING entry for a model ID, tolerating a trailing -YYYYMMDD
    date stamp and a [1m]-style suffix. Returns (key, entry) or (None, None)."""
    if not model:
        return None, None
    m = model.split("[")[0]
    if m in PRICING:
        return m, PRICING[m]
    parts = m.split("-")
    if len(parts) > 1 and parts[-1].isdigit() and len(parts[-1]) == 8:
        m2 = "-".join(parts[:-1])
        if m2 in PRICING:
            return m2, PRICING[m2]
    return None, None


def data_dir():
    d = os.environ.get("TOKEN_AUDIT_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "token-audit")
    os.makedirs(d, exist_ok=True)
    return d


def projects_dir():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "projects")
