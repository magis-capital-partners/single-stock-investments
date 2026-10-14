# Framing a short before it is a position

**Type:** playbook (process, not a company)
**Status:** active
**Adapted from:** Michael's Short-Selling desk playbook, "Framing a short before it is a position", 2026-01-06 (last revised there 2026-09-12). Reworded for the SSI ledger; the steps are his.
**Applies to:** every new row in `_system/research/short-alpha/candidates.json` and every note written from `_system/templates/short_entry_template.md`.

## When to use this

Use it when a bot or an analyst opens a new idea. It sits before the lens work in `_system/frameworks/short_alpha_filing_furnace.md`: the furnace tells you what to look for in a filing; this page tells you what a note must contain before anyone treats it as a live idea. It has no ticker and no market data of its own.

## Steps

1. **Write the claim in one sentence a colleague can argue with.** "The market believes X; the filings show Y; the price changes when Z." If the sentence needs a paragraph, there is no claim yet.
2. **Name the category honestly.** If the claim is really about dilution, file it under `share-supply`, not `accounting`, because a filing happened to mention revenue. The category sets the lenses (`CATEGORY_LENSES` in `build_short_alpha_dashboard.py`), so a wrong category sends the research down the wrong partition.
3. **Separate evidence read from evidence needed.** Two lists. The first names documents with dates and locators. The second is the research plan. A note with only the second list is a lead, and its `stage` says `lead`.
4. **Write what would change our mind before arguing the short.** The falsifier goes into the row's `falsifiers` and into the note's "What would change our mind" section first, while the author is still neutral.
5. **Give tradability its own point.** If borrow, squeeze, or share supply could dominate the fundamental view, write it as a numbered point with the gate it hits (`borrow_and_carry`, `crowding_squeeze`, `share_supply`), not as a footnote. A correct fundamental view can still be a bad short.
6. **Set the stage to what is true today.** `lead` until someone is actually working the name; `researching` when it is on the desk; `live` only when shares are borrowed and a row exists in `ideas.json`; `closed` when finished, with the reason in the note; `rejected` when kept for reference only.

## Common failure modes

- A story in place of a mechanism. "Hype" is not a mechanism; "receivables grew 40% on 8% sales growth" is.
- Figures with no source and no date. A borrow fee is a reading on a date, never a standing fact.
- Two unrelated tickers in one file. Split them; the ledger holds one row per ticker for a reason.
- Updating the note without moving `updated_on`. The row and the note carry the same two dates.
- Letting a publisher report set the `fraud_bad_actors` tag. That tag is a human conclusion after a regulator, a court, an admitted restatement, or an evidence-backed determination.

## How this page stays useful

When the process changes, edit this file and the template together. Do not open a second playbook for the same process.
