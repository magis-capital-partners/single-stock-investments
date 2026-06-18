# VIC local intake workflow

Purpose: capture one Value Investors Club idea page that the user is already viewing while logged in, then register it as a pending third-party source.

This is not a crawler:

- No GitHub Actions workflow stores or uses VIC credentials.
- No scheduled or bulk retrieval is supported.
- No browser navigation is automated.
- The local bookmarklet sends only page metadata, a user-entered note, and the text the user selected.
- Captured excerpts are capped by `_system/scripts/vic_local_intake.py` and default to 2,000 characters.

## Usage

Start the local intake dashboard:

```powershell
python _system/scripts/vic_local_intake.py --serve --queue _system/data/vic_intake_queue.csv
```

Queue several tickers from the command line if useful:

```powershell
python _system/scripts/vic_local_intake.py --tickers AMD,NVDA,TPL
```

Open `http://127.0.0.1:8765/`, create a browser bookmark from the `VIC Capture` bookmarklet, then:

1. Set the active ticker from the queue.
2. Open VIC from that ticker row.
3. Select the excerpt you want to preserve.
4. Click the bookmarklet.

The bookmarklet reads the active ticker from the local dashboard, so repeated captures for a queued ticker do not require retyping the ticker.

For a full PDF that is already open in the browser:

1. Use the browser's normal download button on that PDF.
2. Set the matching active ticker in the dashboard.
3. Click `Import Latest PDF`.

The dashboard imports the newest `.pdf` from `Downloads`, verifies that it is a PDF, copies it into `{TICKER}/third-party-analyses/vic/`, writes a sidecar note, and refreshes the source inventory. By default it only accepts a PDF downloaded in the last 720 minutes; change this with `--pdf-max-age-minutes`.

If the browser blocks the local request, the bookmarklet logs the JSON payload and tries to copy it to the clipboard. Save that JSON locally and import it:

```powershell
python _system/scripts/vic_local_intake.py --from-json C:\path\to\vic_payload.json
```

The helper writes:

- `{TICKER}/third-party-analyses/vic/vic_{date}_{slug}_{hash}.md`
- `{TICKER}/third-party-analyses/vic/vic_pdf_{date}_{slug}_{hash}.pdf`
- `{TICKER}/third-party-analyses/pending.md`
- `{TICKER}/third-party-analyses/references.md`
- `{TICKER}/third-party-analyses/source_inventory_{date}.json`
- `{TICKER}/third-party-analyses/source_inventory_{date}.md`

## Approval rule

VIC intakes remain `pending` until a human adds an explicit approved-registry row in `_system/frameworks/third_party_sources.md`.

Pending VIC notes may be used as variant-perception context only. They may not be used in base IRR, target price, or stance.
