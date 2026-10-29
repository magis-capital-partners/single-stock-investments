# Activist records (Activism desk)

One markdown file per firm, plus `index.json` (machine-readable copy of every record and every rule case) and `score.py` (re-scores the lens). Built 2026-10-29. The lens these records grade is `/workspace/shared/magis/lenses/activism.md`.

## Sources
- Facts come from SEC EDGAR only: the submissions API (`data.sec.gov/submissions/CIK##########.json`), full-text search (`efts.sec.gov/LATEST/search-index`, forms `SC 13D` and `SCHEDULE 13D`, plus amendments) and the filing archives. Requests send the User-Agent `Magis Research drew@magiscapitalpartners.com` and stay under 10 per second.
- Short-report dates and claims come from the publisher's site or our saved copy. They are labeled [web]. A news report used for an outcome is also labeled [web].
- Identity comes from the 13D cover page and the reporting persons, not from the firm name.
- No stock returns. The only price data referenced is the Fugazi scorecard, which labels its own source (Yahoo Finance).
- Nothing is estimated. If an outcome is not confirmed in a filing (or a labeled web source), it is `unresolved`.

## Point-in-time rule
Each campaign has two blocks:
1. **As of first 13D**: the filing date (the as-of date), accession, stake on the cover page, whether a 13G came first, and the Item 4 ask as written then. Nothing learned later goes here.
2. **After**: the peak stake, any ask added in an amendment (dated), contest steps, every outcome event with its accession, and the days count.

A rule test may use only the as-of block to make its prediction. The after block grades it.

## Fields (campaigns, `index.json` → `campaigns`)
| Field | Meaning |
|---|---|
| id | Desk prefix + ticker (e.g. SBD-ALIT). A second campaign at the same issuer gets a year suffix (SBD-ROG23, SBD-ROG25). |
| firm, issuer, ticker, issuer_cik | Who and what. |
| first13d, first_date | Accession and filing date of the first 13D in the chain (the as-of date). |
| stake_first, stake_peak | Percent of class on the first 13D cover page; highest percent in the 13D chain. |
| switch, switch_note | True if the filer had a 13G on the issuer before the 13D. |
| ask_at_filing, ask_specific, ask_type | Item 4 at filing in our words; whether it names a concrete demand; type: board, sale, ops, structural, generic, none. |
| ask_added | (date, text) if a later amendment added a demand. |
| contest_step | (date, text) for the first nomination notice, slate or special-meeting request. |
| events | (date, what happened with accession, tag). |
| concession_date, days_to_concession | First settlement, board seat, strategic review or sale announcement, or activist-won vote. A CEO change alone is not a concession. Days are counted from first_date; a concession signed before the 13D counts as 0. |
| outcome, status | Plain-words outcome; resolved / unresolved / n/a. |
| kind | campaign, or a non-campaign class: control, merger-derived, spin-derived, financing. |

Short reports (`short_reports`): firm, date, ticker, claim (our words), ctype (hard = a specific factual, accounting or legal claim that a filing could confirm; soft = valuation, competition, credit or governance view), event (confirm / disconfirm / none), ev_note (the evidence), src. A report is scored only after 180 days. Confirming events: restatement, SEC or DOJ action, auditor resignation, guidance or dividend cut, delisting. An auditor dismissal with no disagreements does not count.

## Window and caps
13Ds first filed on or after 2023-01-01, newest first, up to 12 per firm. Older chains that were amended after 2023 are listed in each firm file but not scored, because their as-of date is before the window.

## Adding a case and re-scoring
1. When a campaign resolves (or a new 13D appears), append or update the record in the firm file and in `index.json` → `campaigns`. Never edit the as-of block after the fact.
2. Add the case to each rule it tests in `index.json` → `rule_cases` with result right / wrong / mixed and a one-line note.
3. Run `python3 score.py`.
4. Copy the new score into `lenses/activism.md` §2 and add a dated line to its §6 change log (and to `lenses/CHANGELOG.md`, if that file's owner allows desk entries).
