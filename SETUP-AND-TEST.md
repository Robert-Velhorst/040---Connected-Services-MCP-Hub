# Trello → ChatGPT connector — setup & test

*The one-page version. For step-by-step screenshots-level detail, more tests,
command-line checks and troubleshooting, see **[GUIDE.md](GUIDE.md)**.*

## What was wrong

The server was reaching Trello correctly, but discarding most of the data before ChatGPT ever saw it.

- **Each card has 67 fields; the code kept 16.** Everything else was dropped silently — no rror,e no warning. The biggest loss was **checklists**, which is where the actual step-by-step content of your cards lives.
- **Archived cards were invisible.** On your `001. General` board that hid 99 of 131 cards. Across the account, 807 of 1,160.
- **Search returned at most 10 results**, because Trello's default limit was never raised.
- **Comment history stopped at 50 per board.**
- **Trello intermittently blocks requests** (roughly 1 in 10, at random). The old code treated that as fatal, so any bulk read died partway through.

## What it does now

|  | before | now |
| --- | --- | --- |
| Cards ChatGPT can reach | 353 | **1,160** |
| Checklist items | 0 | **7,664** |
| Comments | capped at 50 per board | **13,079** |
| Fields kept per card | 16 | **65+** (everything Trello sends) |
| Search results | capped at 10 | unlimited, and it searches checklist and comment text too |
| Boards covered | partial, crashed on blocks | **85 of 85, workspaces 29 of 29** |

The connector keeps a local index of your whole account so ChatGPT can answer questions that span every board at once, instead of timing out. It refreshes itself in the background every 15 minutes and only re-reads boards that actually changed.

## Install — one time, about 3 minutes

1. Unzip this folder anywhere (Desktop is fine).
2. Double-click **`install.bat`**. It will ask for your Trello API key and token, then set everything up.
3. **Fully quit the ChatGPT app and reopen it** — not just close the window; right-click the taskbar icon and Quit.

Then in ChatGPT: **Settings → Plugins → MCPs** — you should see **`trello`**, enabled, with a toggle.

That's the whole setup. Nothing to start, no window to leave open, no port or tunnel. The ChatGPT app launches and stops the connector by itself.

> If Python is missing, `install.bat` will say so and give you the download link. Install it (tick **"Add Python to PATH"**), then run `install.bat` again.

## Test it

The first launch spends about 90 seconds building the index. Ask `"What's my Trello sync status?"` to watch it finish — then try these:

| Ask ChatGPT | You should get |
| --- | --- |
| "Give me an overview of my Trello account." | 29 workspaces, 85 boards, 1,160 cards |
| "Search my Trello for *migraine* and show the checklist on the top card." | The card **Case file \| Anti migraine massages reimbursement** with its **20-step** checklist |
| "List every card on the board *001. General*, including archived ones." | **131** cards, not 32 |
| "Search all my boards for *invoice*." | ~90 matches across several boards |
| Paste any Trello card URL and ask "what's on this card?" | Full card: description, checklists, labels, dates, attachments, comments |

The last two are the ones worth checking closely — they are exactly what used to come back empty or truncated.

## Things worth knowing

- **It is read-only.** The connector can only read. It cannot create, change, archive or delete anything in Trello — the write tools are not loaded at all, so there is no way for ChatGPT to touch your boards even by accident.
- **Archived cards are included by default**, since most of your history lives there (807 of 1,160). To turn them off, just say *"stop showing me archived cards"* — it is remembered until you change it back. They stay indexed either way, so switching is instant.
- **Your credentials stay on your machine**, in the file `trello\.env`. They are not sent anywhere except to Trello.
- **Please rotate your Trello API token** once you are happy this works — the current one was shared over chat during this job. Revoke and reissue at <https://trello.com/power-ups/admin>, then re-run `install.bat` and paste the new values.

## If something looks wrong

Two one-click tools sit next to `install.bat`:

- **`verify.bat`** — runs the connector the same way ChatGPT does and checks everything end to end, printing a PASS/FAIL list. If this passes but ChatGPT still can't see your Trello, the app simply wasn't fully quit and reopened.
- **`check.bat`** — quick status: connection, registration, and how much of your account is indexed.

Send me the output of either and I can tell what happened. [GUIDE.md](GUIDE.md) has a troubleshooting section covering the common cases.
