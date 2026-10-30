# Special situations rows

Filing-backed situation rows for the Special Situations desk. A desk brief is
the day's ranked note. This ledger is the row the dashboard and the other desks
can cite. Nothing here is a position, a price target, or a base IRR.

| File | What it is |
|---|---|
| `schema.json` | JSON Schema for one row. `check_situation_rows.py` enforces it. |
| `situations.jsonl` | Append-only rows. The highest `version` for a `situation_id` is current. |
| `sources/` | Short notes in our own words, with the accession. Claim proposals point here. |

The Ideas book reads the projection on `dashboard/data/special_situations.json`
(`situation_rows`, plus a row in `rows` or `history` with
`source_feed: situation_register`). `build_special_situations.py` attaches the
latest lines whenever it rewrites that file.

## What a row holds

Tickers, situation type, the dated catalyst and what ends it, the forced seller
or ignored buyer, screens hit, the primary filing (form, accession, URL), the
one number that matters, and what would make the desk pass. `field_tags` marks
each of those as `fact` or `inference`. A `fact` statement names an accession.
`inputs_read` records the feed, the file stamp, `_envelope.generated_at` when
the file has one, and health. `status` is `open`, `closed`, `passed`, or
`wrong`. `drew_verdict` and `outcome` stay null until a later line sets them.

`cross_desk_tags` may be `nol_tax_assets`, `activism`, `tape_index`, or
`fundamental`.

Paid Special Situation Investments copy does not belong in this folder.

## Weekly review

Do not edit a line that is already on main. Append a new line.

1. Copy the latest line for that `situation_id`.
2. Add 1 to `version` and set `recorded_at` to the review time.
3. Change only what the week changed: `status`, `drew_verdict`, `outcome`, and
   any new filing fact. Leave the old line in the file.
4. `drew_verdict` is Drew's words (`by` is `drew`). A bot copies a verdict he
   wrote. It does not invent one. `outcome.tag` is `fact` only with an accession.
5. Run `python _system/scripts/check_situation_rows.py`.
6. Open the pull request on `grok/special_situations/YYYY-MM-DD-verdict`
   (underscore, so the data allowlist matches). Touch
   `situations.jsonl` and, if the Inbox should move the same day,
   `dashboard/data/special_situations.json` only when a human or CI rebuilds it.
   The nightly `build_special_situations.py` attaches the new line on its own.

`passed` means the desk passed. `wrong` means the row was not what the filing
said. `closed` means the catalyst ended and the outcome is recorded.

## Feed age

`python _system/scripts/check_desk_feed_age.py --desk special_situations`
flags a feed when its `_envelope.generated_at` (or `generated_at` / `build_time`
/ `generated`) or its newest row is more than two NYSE business days old, and
flags warrant rows with no `terms_status`. Activism uses the same script:
`--feed activist_feed` or `--desk activism`.
