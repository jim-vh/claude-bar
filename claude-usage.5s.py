#!/usr/bin/env python3
"""
Claude usage — macOS menu bar widget (SwiftBar / xbar plugin)

Shows your Claude account's rolling usage windows (5-hour session, 7-day
weekly, and any per-model windows such as Fable) live in the menu bar.

INSTALL
  1. brew install --cask swiftbar        # or xbar
  2. Launch SwiftBar, pick a plugin folder when prompted.
  3. Copy this file into that folder, keeping the name:  claude-usage.5s.py
     (the ".5s." is SwiftBar's refresh interval — 5 seconds. Use .30s. or
      .1m. if you want it lazier; see CACHE_SECONDS below before you do.)
  4. chmod +x claude-usage.5s.py
  5. SwiftBar → Refresh all.

DEBUG
  Run it straight from the terminal to see the raw API response and the
  actual field names your account returns:

      ./claude-usage.5s.py --debug            # reads through the cache
      ./claude-usage.5s.py --debug --force    # forces a live API call

  --debug on its own is cache-friendly, so you can run it as often as you
  like. Only --force actually calls out, and only that can earn you a 429.

DATA SOURCE — READ THIS
  This calls https://api.anthropic.com/api/oauth/usage, an UNDOCUMENTED
  endpoint. It is not a supported API. It may change or vanish without
  notice, in which case this widget will show an error and you can bin it.
  The OAuth token is read locally from the same place Claude Code keeps it
  (macOS Keychain, falling back to ~/.claude/.credentials.json). Nothing is
  sent anywhere except Anthropic's own API. No token is written to disk by
  this script.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────
CACHE_SECONDS = 120     # don't hit the API more often than this. The menu bar
                        # redraws every 5s from cache; only every 2 min does it
                        # actually call out. Lower it and you risk 429s.
BACKOFF_MAX = 1800      # ceiling on the post-429 backoff, in seconds
STALE_MAX = 3600        # past this age a cached response is too old to show
WARN_AT = 50            # append  !   at this utilisation %
ALERT_AT = 80           # append  !!  at this utilisation %
BAR_WIDTH = 10
CACHE_FILE = Path(os.environ.get("TMPDIR", "/tmp")) / "claude-usage-widget.json"

# Pretty names for the structured `limits[]` entries the API returns. Per-model
# scopes (Fable, Opus, …) are labelled from their own display_name, so they
# don't need an entry here — they appear automatically.
LIMIT_LABELS = {
    "session": "Session (5h)",
    "weekly_all": "Weekly (7d)",
    "weekly_scoped": "Scoped (7d)",
}

# Fallback labels for the older top-level window shape (five_hour, seven_day…),
# used only when the response has no `limits[]` array.
LABELS = {
    "five_hour": "Session (5h)",
    "seven_day": "Weekly (7d)",
    "seven_day_opus": "Opus (7d)",
    "seven_day_sonnet": "Sonnet (7d)",
    "seven_day_fable": "Fable (7d)",
    "seven_day_oauth_apps": "Apps (7d)",
}

FONT = "font=Menlo size=12"


# ── Credentials ───────────────────────────────────────────────────────────
def get_oauth():
    """Read Claude Code's OAuth blob. Keychain first (macOS), then file.

    Returns the `claudeAiOauth` dict (accessToken, expiresAt, …) or None. None
    means Claude Code hasn't signed in on this machine yet — a wait-for-it state,
    not an error: the entry appears in the Keychain once Claude Code has run.
    """
    try:
        raw = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if raw:
            return json.loads(raw)["claudeAiOauth"]
    except Exception:
        pass

    creds = Path.home() / ".claude" / ".credentials.json"
    try:
        return json.loads(creds.read_text())["claudeAiOauth"]
    except Exception:
        return None


def token_expired(oauth):
    """True if the stored access token's expiry has passed.

    Only Claude Code refreshes this token (when it next runs), so an expired
    token means "waiting for Claude Code", not a real auth failure. We check it
    up front to avoid firing a doomed request at the endpoint every refresh.

    `expiresAt` is epoch milliseconds in current Claude Code builds; we tolerate
    seconds too. An absent/odd value returns False — let the API be the judge."""
    exp = oauth.get("expiresAt")
    if not isinstance(exp, (int, float)):
        return False
    exp_s = exp / 1000 if exp > 1e11 else exp   # ms → s if it looks like ms
    return time.time() >= exp_s


# ── API ───────────────────────────────────────────────────────────────────
def fetch_usage(token):
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def _read_cache():
    try:
        return json.loads(CACHE_FILE.read_text())
    except Exception:
        return {}


def _write_cache(blob):
    try:
        old = os.umask(0o077)
        CACHE_FILE.write_text(json.dumps(blob))
        os.umask(old)
    except Exception:
        pass


def _retry_after(e):
    """Seconds the server asked us to wait, if it said so."""
    try:
        return max(0, int(e.headers.get("Retry-After", "")))
    except Exception:
        return None


def cached_usage(token, force=False):
    """Serve from cache unless it's stale. Keeps us well clear of rate limits.

    Returns (data, age_seconds). A live fetch has age 0.

    Three layers keep us off the API:
      1. CACHE_SECONDS — the normal "don't ask again yet" window.
      2. A backoff after a 429, doubling each time up to BACKOFF_MAX, honouring
         Retry-After when the server sends one. Without this the 5s refresh just
         hammers the endpoint while it's telling us to back off.
      3. On any fetch failure, the last good response is served (up to
         STALE_MAX) rather than blanking the widget out with an error.
    """
    blob = _read_cache()
    now = time.time()
    data, fetched_at = blob.get("data"), blob.get("fetched_at", 0)
    age = now - fetched_at if data else None

    fresh = age is not None and age < CACHE_SECONDS
    backing_off = now < blob.get("retry_at", 0)
    if not force and (fresh or (backing_off and age is not None and age < STALE_MAX)):
        return data, age

    try:
        fetched = fetch_usage(token)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            # Double the backoff each consecutive 429; the server's Retry-After
            # wins if it gave us one. Reset on the next success.
            wait = _retry_after(e) or min(BACKOFF_MAX, max(CACHE_SECONDS, blob.get("backoff", 0) * 2))
            blob["backoff"] = wait
            blob["retry_at"] = now + wait
            _write_cache(blob)
        if data is not None and age < STALE_MAX:
            return data, age      # ride out the error on the last good response
        raise
    except Exception:
        if data is not None and age < STALE_MAX:
            return data, age
        raise

    _write_cache({"fetched_at": now, "data": fetched})
    return fetched, 0


# ── Rendering ─────────────────────────────────────────────────────────────
def _label_for_limit(lim):
    scope = lim.get("scope") or {}
    model = (scope.get("model") or {}).get("display_name") if isinstance(scope, dict) else None
    if model:
        return f"{model} (7d)"
    kind = lim.get("kind") or ""
    return LIMIT_LABELS.get(kind, kind.replace("_", " ").title() or "Usage")


SESSION_LABEL = LIMIT_LABELS["session"]


def _order(w):
    """Session window pinned first; everything else worst-first behind it."""
    return (0 if w[0] == SESSION_LABEL else 1, -w[1])


def windows(data):
    """Return [(label, pct, resets_at)] for every usage window.

    The 5-hour session window always comes first; the rest follow worst-first.

    Prefers the structured `limits[]` array — it carries per-model scopes such
    as Fable with real display names, which the top-level keys no longer do
    (they come back null). Falls back to discovering top-level `utilization`
    windows for older/other response shapes."""
    limits = data.get("limits")
    if isinstance(limits, list) and limits:
        out = []
        for lim in limits:
            if not isinstance(lim, dict) or lim.get("percent") is None:
                continue
            out.append((_label_for_limit(lim), float(lim["percent"]), lim.get("resets_at")))
        if out:
            return sorted(out, key=_order)

    # Fallback: any top-level object carrying a numeric 'utilization'. A null
    # utilization (e.g. extra_usage when disabled) is not a real window.
    out = []
    for key, val in data.items():
        if not isinstance(val, dict) or val.get("utilization") is None:
            continue
        pct = val["utilization"]
        pct = pct * 100 if pct <= 1 else pct   # tolerate 0-1 or 0-100
        label = LABELS.get(key, key.replace("_", " ").title())
        out.append((label, float(pct), val.get("resets_at")))
    return sorted(out, key=_order)


def bar(pct):
    filled = min(BAR_WIDTH, max(0, round(pct / 100 * BAR_WIDTH)))
    return "█" * filled + "░" * (BAR_WIDTH - filled)


def sigil(pct):
    # Plain-text severity marker — no colour, no emoji anywhere in this plugin.
    if pct >= ALERT_AT:
        return "!!"
    if pct >= WARN_AT:
        return "!"
    return ""


def resets_in(iso):
    if not iso:
        return ""
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        secs = (t - datetime.now(timezone.utc)).total_seconds()
        if secs <= 0:
            return "resetting"
        h, m = int(secs // 3600), int((secs % 3600) // 60)
        return f"resets in {h}h {m:02d}m" if h else f"resets in {m}m"
    except Exception:
        return ""


def render(ws, age, note=None):
    """Draw the menu bar line and dropdown for a set of usage windows.

    Shared by the normal path and the calm 'waiting' fallback, so a stale-but-
    real reading looks identical to a live one bar the footer's freshness tag.
    """
    # ── Menu bar line: the session window (ws[0] is pinned to it) ──
    # The percentage shown is the session's, but the marker tracks the hottest
    # window of them all, so a near-full weekly limit still shouts (! at
    # WARN_AT, !! at ALERT_AT). No colour or emoji anywhere — plain text only,
    # so it reads cleanly in both light and dark menu bars.
    _, top_pct, _ = ws[0]
    mark = sigil(max(pct for _, pct, _ in ws))
    print(f"{top_pct:.0f}%{(' ' + mark) if mark else ''} | {FONT}")

    # ── Dropdown: session first, then the rest worst-first ──
    print("---")
    for label, pct, reset in ws:
        print(f"{label:<14} {bar(pct)} {pct:5.1f}% {sigil(pct)} | {FONT}")
        r = resets_in(reset)
        if r:
            print(f"{'':<14} {r} | {FONT}")

    print("---")
    if age == 0:
        state = "fresh"
    elif age < CACHE_SECONDS:
        state = f"cached {int(age)}s"
    else:
        state = f"stale {int(age // 60)}m"   # API unreachable; last good reading
    print(f"Updated {datetime.now().strftime('%H:%M:%S')} ({state}) | {FONT}")
    if note:
        print(f"{note} | {FONT} length=60")
    print(f"Refresh now | refresh=true {FONT}")


def _last_good():
    """The most recent cached reading if still within STALE_MAX, else (None, None).

    Lets the 'waiting' state keep showing real numbers while Claude Code (or the
    network) comes back, instead of blanking the widget out."""
    blob = _read_cache()
    data, fetched_at = blob.get("data"), blob.get("fetched_at", 0)
    if not data:
        return None, None
    age = time.time() - fetched_at
    return (data, age) if age < STALE_MAX else (None, None)


def waiting(headline, detail=""):
    """Calm 'not ready yet' state — the widget is fine, it's just waiting on
    Claude Code (or the network) to come back. Never the word 'error'.

    Prefers to keep the last good reading on screen (stale-marked) with the
    reason as a footnote; falls back to a neutral placeholder when there's
    nothing cached. SwiftBar keeps refreshing on its own, so this self-heals the
    moment Claude Code reconnects — no user action required."""
    data, age = _last_good()
    if data is not None:
        ws = windows(data)
        if ws:
            render(ws, age, note=headline)
            sys.exit(0)

    print(f"Claude usage: … | {FONT}")
    print("---")
    print(f"{headline} | {FONT}")
    if detail:
        print(f"{detail} | {FONT} length=60")
    print("---")
    print(f"Refresh | refresh=true {FONT}")
    sys.exit(0)


def die(headline, detail=""):
    print(f"Claude usage: error | {FONT}")
    print("---")
    print(f"{headline} | {FONT}")
    if detail:
        print(f"{detail} | {FONT} length=60")
    print("---")
    print(f"Refresh | refresh=true {FONT}")
    sys.exit(0)


def main():
    debug = "--debug" in sys.argv
    # --debug reads through the cache like a normal run; --force is the opt-in
    # for a live call. Debugging shouldn't cost you a rate limit.
    force = "--force" in sys.argv

    oauth = get_oauth()
    token = (oauth or {}).get("accessToken")
    if not token:
        # Claude Code hasn't signed in on this machine yet. Not an error — the
        # token lands in the Keychain once Claude Code runs, and we pick it up on
        # the next refresh. Wait for it rather than shouting.
        waiting("Waiting for Claude Code to sign in",
                "Run `claude` once; this updates on its own after.")

    if not force and not debug and token_expired(oauth):
        # The stored token has lapsed and only Claude Code refreshes it. Don't
        # fire a doomed 401 at the endpoint every refresh — wait it out, keeping
        # the last good reading on screen. It self-heals when Claude Code runs.
        waiting("Waiting for Claude Code to refresh its token",
                "The saved token expired; Claude Code refreshes it when it runs.")

    try:
        data, age = cached_usage(token, force=force)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            # Rejected — nearly always a lapsed token Claude Code hasn't yet
            # refreshed. Wait for it to reconnect instead of erroring out.
            waiting("Waiting for Claude Code to refresh its token",
                    "Claude Code refreshes the saved token when it runs.")
        if e.code == 429:
            # Backing off automatically and nothing cached to show yet. Transient,
            # not an error — it clears itself.
            waiting("Rate limited — backing off",
                    "Retrying automatically; this clears on its own.")
        die(f"API error {e.code}", "The usage endpoint is undocumented and may have changed.")
    except Exception as e:
        # Network not up yet (e.g. straight after boot), DNS, timeout… all
        # transient. Wait and let SwiftBar's next refresh retry.
        waiting("Reconnecting to the usage API…", str(e))

    if debug:
        print(f"=== RAW RESPONSE ({'live' if age == 0 else f'cached, {int(age)}s old'}) ===")
        print(json.dumps(data, indent=2))
        print("\n=== PARSED WINDOWS ===")
        for label, pct, reset in windows(data):
            print(f"  {label:<24} {pct:5.1f}%  {reset or '-'}")
        return

    ws = windows(data)
    if not ws:
        die("No usage windows in response",
            "Run with --debug to see what the API actually returned.")

    render(ws, age)


if __name__ == "__main__":
    main()