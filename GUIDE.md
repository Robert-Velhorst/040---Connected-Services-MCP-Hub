# Trello → ChatGPT connector — full guide

Everything needed to install, test and troubleshoot the connector.

- **Part 1 — Install** (5 minutes, no technical knowledge needed)
- **Part 2 — Test it in ChatGPT** (the tests that matter)
- **Part 3 — Test it from the command line** (proves it independently of ChatGPT)
- **Part 4 — Troubleshooting** (symptom → command → fix)
- **Part 5 — Reference** (what the numbers should be, how it works, settings)

---

# Part 1 — Install

### Step 1. Unzip

Unzip the folder somewhere permanent — **Desktop** or **Documents** is ideal.

> Do **not** run it from inside the `.zip`, and do not put it in a temporary
> folder. The ChatGPT app remembers this location, so if you move or delete the
> folder later the connector stops working. If you do move it, just run
> `install.bat` again from the new location.

> **Windows may block the files.** If you downloaded the zip, right-click it →
> **Properties** → tick **Unblock** at the bottom → **Apply**, *then* extract.
> This avoids a "Windows protected your PC" warning later.

### Step 2. Check the computer is ready *(optional, 20 seconds)*

Double-click **`preflight.bat`**. It changes nothing — it just checks Python,
your internet connection to Trello, disk space and whether the ChatGPT app is
set up, and tells you if anything needs sorting first.

You want it to say **`READY - run install.bat`**.

### Step 3. Run the installer

Double-click **`install.bat`**.

It opens a local browser page. Create or select a Power-Up at
<https://trello.com/power-ups/admin>, add `http://localhost:8765` as an allowed
origin, then enter its public API key once. The browser then sends you to
Trello to sign in and approve read-only access; no token is pasted into the
installer.

A successful run looks like this:

```
 [1/5] Python found: py -3.13
 [2/5] Creating the Python environment (this takes a minute)...
       Dependencies installed.
 [3/5] Connect Trello in your browser.
       The user token is saved in Windows Credential Manager.
 [4/5] Checking the connector starts and can reach Trello...
       Connected to Trello as: Noodzakelijk Online
       Visible to the connector: 85 boards, 29 workspaces
       Access mode: read-only (cannot change anything in Trello)
 [5/5] Registering with the ChatGPT app...
       trello registered in C:\Users\<you>\.codex\config.toml

  Setup complete.
```

> **If it says Python was not found**, install Python 3.13 from
> <https://www.python.org/downloads/release/python-3130/>. On the first screen
> of that installer, tick **“Add python.exe to PATH”**. Then run `install.bat`
> again.

### Step 4. Restart ChatGPT properly

This step is the one people skip, and nothing works without it.

1. Right-click the ChatGPT icon in the taskbar (bottom-right, near the clock).
2. Choose **Quit**. Closing the window is *not* enough — it keeps running.
3. Open ChatGPT again.

### Step 5. Confirm it registered

In ChatGPT: **Settings → Plugins → MCPs**. You should see **`trello`** listed with
a toggle, switched on.

That is the entire setup. There is no window to leave open, no server to start,
no port to forward and no tunnel. The ChatGPT app starts and stops the
connector by itself whenever you use it.

---

# Part 2 — Test it in ChatGPT

The first question you ask will take about **90 seconds** — the connector is
reading your whole account once and building a local index. Everything after
that is instant. Ask this first and wait for it to finish:

> **What is my Trello sync status?**

Expect `state: idle`, `ready: true`, and roughly 85 boards indexed.

Now the real tests. These five are the ones that used to fail.

### Test 1 — Does it see the whole account?

> **Give me an overview of my Trello account.**

Expect approximately:

| | |
| --- | --- |
| Workspaces | 29 |
| Boards | 85 |
| Cards | 1,160 |
| of which archived | 807 |
| Checklist items | 7,664 |
| Comments | 13,079 |

**Why it matters:** the old connector could only see 353 cards and zero
checklist items.

### Test 2 — Are checklists visible? *(the main problem)*

> **Search my Trello for “migraine” and show me the full checklist on the top
> result.**

Expect the card **“Case file | Anti migraine massages reimbursement”** and a
checklist of **20 steps**, listed out with their text.

**Why it matters:** checklists are where the actual content of your cards
lives. The old connector discarded them entirely, which is why analysis came
back thin.

### Test 3 — Are archived cards visible?

> **List every card on the board “001. General”, including archived ones. How
> many are there in total?**

Expect **131** cards.

**Why it matters:** the old connector showed 32 — it could not see archived
cards at all, and on your account those are 807 of 1,160.

### Test 4 — Does search reach across every board?

> **Search all of my Trello boards for “invoice” and group the results by
> board.**

Expect roughly **90 matches** spread across several boards, including hits
found inside checklist items and comments — not just card titles.

**Why it matters:** the old connector returned at most 10 results, from card
titles only.

### Test 5 — Does a single card come back complete?

Open any card in Trello, copy its URL from the address bar, then:

> **What is on this card? https://trello.com/c/XXXXXXXX**

Expect the description, every checklist with each item and its tick state,
labels, due dates, members, attachments and the comment history.

### Turning archived cards on and off

Archived cards are included by default, because most of this account's history
lives there (807 of 1,160 cards). If you would rather only see active work,
just say so:

> **Stop showing me archived Trello cards.**

The setting is remembered, so you do not have to repeat it. To go back:

> **Include archived cards again.**

You can also override it for a single question without changing the setting:

> **Search all boards for "invoice", including archived cards.**

Nothing is deleted when archived cards are hidden -- they stay indexed, so
switching back is instant and never triggers a re-sync. To check the current
setting, ask: *"What are my Trello connector settings?"*

### Then try a real question

Once those pass, the connector is doing its job. Try what you actually wanted
it for:

> **Look across all my Trello boards and summarise everything still outstanding
> on my tax office cases, including the unfinished checklist steps.**

> **Which of my boards have the most unfinished work, and what is blocking
> each one?**

---

# Part 3 — Test it from the command line

This proves the connector works independently of ChatGPT — useful if ChatGPT
is behaving oddly and you want to know which side the problem is on.

Open the folder you unzipped, and double-click:

### `verify.bat` — the full acceptance test

This starts the connector exactly the way ChatGPT does and checks everything:

```
  [ok]   Server starts and completes the MCP handshake
  [ok]   Tools exposed: 47
  [ok]   Read-only: no write tool is exposed
  [ok]   Read-only: delete_card is rejected outright
  [ok]   Index ready: 85/85 boards, 29 workspaces
  [ok]   Archived cards included: 807 of 1160 total
  [ok]   Checklist items captured: 7664
  [ok]   Comments captured: 13079
  [ok]   Search works across all boards: 409 matches for 'step'
  [ok]   Full card returned: 65 fields, 22 checklist items
  [ok]   Checklists present on the card object

  RESULT: ALL CHECKS PASSED
```

If this passes but ChatGPT still misbehaves, the problem is on the ChatGPT
side — almost always that it was not fully quit and reopened.

### `fix.bat` — diagnose and repair automatically

If anything is wrong, run this first. It checks every known cause in order and
repairs what it can on its own: Docker not running, a missing container image,
a missing storage volume, malformed or rejected credentials, and a stale or
tunnel-based entry left over from an older connector. It then tells you exactly
what (if anything) still needs doing by hand.

Safe to run as often as you like. Add `--dry-run` to diagnose without changing
anything.

### `check.bat` — a quick status report

Connection, registration and index coverage. This is the one to send if you
need help.

### Individual commands

Open **PowerShell** in the unzipped folder (Shift + right-click in the folder →
*Open PowerShell window here*) and run any of these:

```powershell
# Are the credentials valid and how much can they see?
.\trello\.venv\Scripts\python.exe .\trello\selftest.py

# Is the connector registered with the ChatGPT app, and where does it point?
.\trello\.venv\Scripts\python.exe .\trello\setup_codex.py --check

# How much of the account is indexed right now?
.\trello\.venv\Scripts\python.exe .\trello\status.py

# Full acceptance test (same as verify.bat)
.\trello\.venv\Scripts\python.exe .\trello\verify.py

# Re-read Trello now: changed boards only
.\trello\.venv\Scripts\python.exe .\trello\resync.py

# Re-read Trello now: every board, from scratch (~90 seconds)
.\trello\.venv\Scripts\python.exe .\trello\resync.py --force
```

The test suite must be run from inside the `trello` folder, because the
`freshdesk` folder next to it is a separate service with its own dependencies:

```powershell
cd trello
.\.venv\Scripts\python.exe -m pytest -q      # 58 tests, no internet needed
cd ..
```

### Re-register after moving the folder

```powershell
.\trello\.venv\Scripts\python.exe .\trello\setup_codex.py
```

### Remove the connector completely

```powershell
.\trello\.venv\Scripts\python.exe .\trello\setup_codex.py --remove
```

Then delete the unzipped folder and, if you want the local index gone too,
delete `%LOCALAPPDATA%\trello-mcp`.

---

# Part 4 — Troubleshooting

### “trello” does not appear in Settings → Plugins → MCPs

1. Confirm it registered:
   ```powershell
   .\trello\.venv\Scripts\python.exe .\trello\setup_codex.py --check
   ```
   You want `status: 'trello' registered` and both `interpreter exists: True`
   and `main.py exists: True`.
2. If that is fine, ChatGPT was not fully quit. Right-click the taskbar icon →
   **Quit** → reopen. Closing the window is not enough.
3. If `interpreter exists: False`, the folder was moved. Re-run `install.bat`.

### ChatGPT says it cannot find any Trello tools

Same cause as above nine times out of ten. Verify the connector itself is fine
with `verify.bat` — if that passes, it is the ChatGPT side.

### “Invalid API key or token”

```powershell
.\trello\.venv\Scripts\python.exe .\trello\selftest.py
```

If it reports rejected credentials, revoke the connector in Trello and run
`trello\oauth_connect.py` from the installed virtual environment to approve
access again.

### Answers seem to be missing recent changes

The index refreshes every 15 minutes. To refresh immediately, ask ChatGPT:

> **Refresh my Trello data.**

Then check progress with **“What is my Trello sync status?”**

### A few boards show as failed

Normal and self-healing. Trello intermittently blocks automated requests at
random; the connector retries with backoff, slows itself down when it happens,
and re-queues anything that still failed for the next pass. If the same board
fails for hours, send the output of `check.bat`.

### The first question takes a long time or times out

That is the initial index build (~90 seconds on this account). Ask **“What is
my Trello sync status?”** and wait for `ready: true`, then continue.

---

# Part 5 — Reference

### What “fixed” means, in numbers

| | before | now |
| --- | --- | --- |
| Cards reachable | 353 | **1,160** |
| Archived cards | 0 | **807** |
| Checklist items | 0 | **7,664** |
| Comments | capped at 50 per board | **13,079** |
| Fields kept per card | 16 of 67 | **65+** |
| Search results | capped at 10 | unlimited, incl. checklist and comment text |
| Boards covered | crashed partway | **85 of 85** |

### How it works

The connector keeps a local index of your Trello account in
`%LOCALAPPDATA%\trello-mcp\trello_cache.db`, so questions spanning every board
answer instantly instead of timing out. It refreshes in the background every 15
minutes and only re-reads boards that actually changed — a refresh takes about
5 seconds, a full rebuild about 90.

Nothing leaves your machine except requests to Trello itself. The native setup
stores the public app key under `%LOCALAPPDATA%\trello-mcp` and the user token in
Windows Credential Manager; neither is written into shared configuration.

### It cannot change anything

The connector runs read-only. The tools that could create, edit, archive or
delete are not loaded at all — so ChatGPT cannot alter your boards even if
asked to. `verify.bat` proves this by attempting a delete and confirming it is
refused.

### Settings you can change

For network/Docker deployments, edit `trello\.env`, then fully quit and reopen
ChatGPT. Native Windows installations use the browser consent flow instead:

| Setting | Default | What it does |
| --- | --- | --- |
| `TRELLO_INCLUDE_ARCHIVED_DEFAULT` | `true` | Whether archived cards are shown by default. You can also change this from chat at any time |
| `TRELLO_SYNC_INTERVAL_SECONDS` | `900` | Seconds between background refreshes. `0` = only at startup |
| `TRELLO_READ_ONLY` | `true` | Leave as `true` unless you deliberately want ChatGPT to be able to edit Trello |
| `TRELLO_REQUESTS_PER_SECOND` | `4` | Lower it if Trello blocks requests often |
| `TRELLO_SYNC_ON_START` | `true` | Whether to refresh when ChatGPT launches the connector |

### Reconnect or revoke access

Use the Applications section of your Trello account to revoke this connector.
Run `trello\oauth_connect.py` again to reconnect; the old token is replaced in
Windows Credential Manager only after Trello validates the new approval.
