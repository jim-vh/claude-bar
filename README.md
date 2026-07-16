# claude-bar

See how much of your Claude usage you've burned through — right in your Mac's
menu bar.

```
                                    ⌘  30% !  🔋  Wed 14:22
```

Click it and you get the full picture:

```
Session (5h)   ███░░░░░░░  30.0 %
               resets in 3h 12m
Weekly (7d)    █████░░░░░  52.4 % !
               resets in 4h 08m
Fable (7d)     █░░░░░░░░░  11.0 %
               resets in 2d 6h
```

No more wondering whether you're about to hit your limit mid-task.

---

## Install

Two steps: install the app, drop in the file. No Terminal needed.

### Step 1 — Install SwiftBar

[SwiftBar](https://github.com/swiftbar/SwiftBar) is a free, open-source app that
puts small scripts — like this one — into your menu bar.

**[⬇ Download SwiftBar](https://github.com/swiftbar/SwiftBar/releases/latest)**
— grab the `.dmg` from the latest release, open it, and drag SwiftBar into your
Applications folder.

Now **open SwiftBar**. The first time it runs, it asks you to choose a *plugin
folder* — the folder it watches for things to show in your menu bar. Make a new
empty folder somewhere you'll remember (e.g. `Documents/SwiftBar`) and pick it.
Approve any permission prompt macOS shows.

### Step 2 — Put the widget in that folder

**[⬇ Download claude-usage.5s.py](https://raw.githubusercontent.com/jim-vh/claude-bar/main/claude-usage.5s.py)**
— right-click that link and choose *Download Linked File*.

Then **drag the downloaded `claude-usage.5s.py` into your SwiftBar plugin
folder**.

That's it. Your usage appears in the menu bar within a few seconds. If it
doesn't, click the SwiftBar icon → *Refresh all*.

> **Keep the filename exactly as it is.** SwiftBar reads the refresh rate from
> it — the `.5s.` means "redraw every 5 seconds". If your browser saves it as
> `claude-usage.5s.py.txt`, rename it back.

### Step 3 — Make sure you're signed in to Claude Code

The widget never asks you for a password or an API key. It reads the login that
[Claude Code](https://claude.com/claude-code) already saved on your Mac, so you
need to have signed in there at least once.

If the menu bar says **"Not logged in to Claude Code"**, open Terminal, run
`claude`, sign in, then click the widget → *Refresh now*.

---

## Reading it

The menu bar shows your **5-hour session window** — the one that matters
minute-to-minute — as a single percentage.

| What you see | What it means |
|---|---|
| `30%` | 30% of your session window used, everything's fine |
| `52% !` | something has passed 50% — worth knowing |
| `88% !!` | something has passed 80% — you're close to a limit |

The `!` markers track your **hottest** window, not just the session one. So a
nearly-full weekly limit still warns you even while your session sits at 5%.
Click the widget to see which window it is.

The dropdown lists every window you have — session first, then worst-first —
each with a bar, a percentage, and how long until it resets.

## Uninstall

Drag `claude-usage.5s.py` out of your SwiftBar plugin folder and into the Trash.
To remove SwiftBar itself, drag it out of Applications.

---

## Common problems

**Nothing appears in the menu bar.**
Click the SwiftBar icon → *Refresh all*. Still nothing? Check the file is in the
folder SwiftBar is actually watching — SwiftBar icon → *Preferences* shows the
plugin folder — and that the filename is still `claude-usage.5s.py` (browsers
sometimes append `.txt`).

**It says "Not logged in to Claude Code".**
Run `claude` in the Terminal and sign in. See Step 3.

**It says "Token rejected (401/403)".**
Your saved login is stale or lacks the right scope. Sign out and back in to
Claude Code (`/logout`, then `/login`), then refresh the widget.

**It says "Rate limited (429)".**
It's calling the API too often. Open `claude-usage.5s.py` in any text editor and
raise `CACHE_SECONDS` near the top.

## How often it updates

The `.5s.` in the filename is SwiftBar's redraw rate — every 5 seconds. But the
widget only *calls Anthropic* every 2 minutes (`CACHE_SECONDS = 120` in the
script); in between it redraws from a local cache. That's deliberate — calling
an undocumented endpoint every 5 seconds is a good way to get rate-limited.

To change the redraw rate, rename the file (`.30s.`, `.1m.`, …). SwiftBar reads
the interval from the filename.

## Privacy and the data source

The widget calls `https://api.anthropic.com/api/oauth/usage`, an **undocumented**
endpoint. It is not a supported API and may change or disappear without notice.
If that happens, the widget shows an error rather than lying to you.

- Your OAuth token is read locally, from wherever Claude Code already put it
  (macOS Keychain, falling back to `~/.claude/.credentials.json`).
- The token is sent to **Anthropic's own API and nowhere else** — no third-party
  servers, no telemetry, no analytics.
- No token is written to disk. Only the usage response is cached, in your temp
  folder, readable by your user alone.

It's a single readable Python file with no dependencies —
[read it](claude-usage.5s.py) before you run it, if you like.

## Requirements

- macOS
- [SwiftBar](https://github.com/swiftbar/SwiftBar)
- Python 3 (already on your Mac)
- A Claude account you've signed in to via Claude Code

---

## Advanced

If you're comfortable in a terminal, there's a Makefile.

```sh
git clone https://github.com/jim-vh/claude-bar.git
cd claude-bar
make install
```

`make install` copies the plugin into your SwiftBar plugin folder, marks it
executable, and triggers a refresh. It finds the folder from SwiftBar's own
preference (`defaults read com.ameba.SwiftBar PluginDirectory`), falling back to
`~/Library/Application Support/SwiftBar/Plugins`. Override it:

```sh
make install PLUGIN_DIR="/path/to/your/plugin/folder"
```

`make uninstall` removes it again.

### Debugging

```sh
make debug        # or: ./claude-usage.5s.py --debug
```

Prints the raw API response and the parsed windows, bypassing the cache. Use it
when a window is missing or mislabelled — it shows the actual field names your
account returns.

### How it parses the response

Windows come from the response's structured `limits[]` array, which carries
per-model scopes (like Fable) with real display names. It falls back to the
older top-level `five_hour` / `seven_day` keys if `limits[]` is absent. Either
way, new windows appear automatically without a code change.

### Permissions note

You don't need to `chmod +x` the plugin yourself — SwiftBar sets the executable
bit for you. (Unless you've disabled that with `defaults write com.ameba.SwiftBar
MakePluginExecutable -bool NO`, in which case: `chmod +x claude-usage.5s.py`.)

### Contributing: no colour, no emoji

The widget emits plain text only — no SwiftBar `color=` directives, no emoji.
Severity is text (`!`, `!!`) and the bars are monochrome `█`/`░`. This keeps it
legible in both light and dark menu bars, and makes it sit naturally next to the
rest of your menu bar text. Please keep it that way in pull requests.

---

## Licence

[MIT](LICENSE) — do what you like with it, just keep the copyright notice. No
warranty.

## Not affiliated with Anthropic

This is an unofficial, community-made widget. It is not made, endorsed, or
supported by Anthropic. "Claude" is a trademark of Anthropic, used here only to
describe what the widget shows.
