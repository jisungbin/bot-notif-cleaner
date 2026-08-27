# Bot Notification Cleaner

A Chrome extension that automatically marks **PR notifications created by Renovate and Dependabot as Done** every time you visit github.com. Your inbox keeps only human-authored PRs and review requests.

## How it works

```
content script (github.com/*)  ──sendMessage──▶  background.js (MV3 SW)
                                                      │ if cooldown (30s) passed
                                                      ▼ connectNative
                                                 host/notif-host.py
                                                      │ gh auth token → direct REST calls
                                                      ▼
                              GET /notifications → resolve PR author → DELETE /threads/{id}
                                                      │
   badge (-N / ✓ / ⚠)  ◀────── {done, scanned, error?} ─────┘
```

- **Extension**: only triggers and reports. It wakes the host on every github.com full page load, gated by a 30-second cooldown (prevents duplicate runs across multiple tabs and rapid reloads). Clicking the toolbar icon bypasses the cooldown.
- **Host (`notif-host.py`)**: does all the classification and API work. It shells out to `gh auth token` once for a token, then calls the REST API directly via `urllib` — spawning `gh` once per notification would add seconds of process-creation overhead. PR author lookups run 8-way parallel and are cached in `~/.cache/bot-notif-cleaner/authors.json`.

Classification is based **solely on the PR author**: the host fetches `subject.url` and marks the thread Done only if `user.login` is `renovate[bot]` or `dependabot[bot]`. No title heuristics, so human PRs are never misclassified. Lookups that fail or time out are skipped rather than deleted.

Only the notification inbox is scanned (`GET /notifications` without `all=true`). Passing `all=true` also returns already-read and already-Done threads, and the response carries no field to tell them apart — which would both inflate the count and re-process the same threads on every run.

## Install

**Prerequisites**: `brew install gh`, `gh auth login`

### 1. Load the extension (to get its ID)

1. `chrome://extensions` → enable **Developer mode** (top right)
2. **Load unpacked** → select the `extension/` folder
3. Copy the **ID** shown on the card

### 2. Install the native messaging host

```bash
./install.sh <EXTENSION_ID>
```

### 3. Verify token scopes

```bash
gh api /notifications --jq 'length'   # a number means you're good
```

If this returns 403, add the `notifications` scope. (A token with `repo` usually passes as is.)

```bash
gh auth refresh -h github.com -s notifications
```

### 4. Reload the extension

Reload from `chrome://extensions`, then visit github.com.

## Badges

| Badge | Meaning |
|-------|---------|
| `…` (gray) | Scanning |
| `-N` (green) | N threads marked Done (clears after 4s) |
| `✓` (gray) | Nothing to do (clears after 4s) |
| `⚠` (red) | Error — hover the icon for the reason. Stays until resolved |

## Debugging

```bash
python3 host/notif-host.py --dry    # print classification only, delete nothing
```

The host is spawned fresh on every `connectNative`, so edits to the Python file take effect without reloading the extension.

For the extension side, open `chrome://extensions` → **service worker** on the card, and look for the `[NotifCleaner]` prefix in the console.
