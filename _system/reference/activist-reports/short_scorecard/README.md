# Short-seller scorecard

One file per publisher. The seed is Fugazi Research: `Fugazi_Research.md` and `Fugazi_Research.csv`.

A scorecard is the price record after a short print. It is separate from the activist feed. Leave feed-building code alone when you add a row.

## Append a new print

1. Confirm it is a company report. Record the ticker, the report date, the pre-report close, Day 1 %, and whether a filing confirms the claim or cuts against it. The author's conclusion stays the author's. The number you add from our side comes from a filing or the dashboard. Use `SHORT_REPORT_BRIEF_TEMPLATE.md` for the brief.
2. Pre-report close is the last regular-session close before the publication date, in unadjusted dollars. Day 1 is the publication-date close versus that print when the publication date is a session, and the next session when it is not. If the note went out after the close, Day 1 is the next session. Say which one you used.
3. Low after report is the lowest regular-session trade from Day 1 through the latest close, with that date, versus the pre-report close. Total to date is the latest close versus the same pre-report close. Percentages use split-adjusted prices. Star the row when a reverse split lands after the report, so a reader does not compare the raw pre-close to today's raw price.
4. A second report on a name already in the table updates that row. Keep one line per name, the way a Schedule 13D and its amendments are one chain. The Fugazi seed still shows two Sidus Space rows, because that is how the original 28 was counted. A later Sidus print updates the latest Sidus row.
5. Leave sector pieces out. Fugazi's "Lost in Space" note (12 June 2026, covering ASTS, RDW, SPCE, SIDU, MNTS, and RKTO) is the example. A later company report on one of those names can still earn its own row.
6. In the same pass, fill the outcomes lane: a delisting, a listing-compliance deadline, or a regulator finding. "None found," with the date you checked, is a complete entry.
7. Recompute the median strip on the rows that sit in the universe, and date the as-of close. Keep the old strip in the note so a one-day price move is visible.

## Fugazi universe, so the seed stays reproducible

Thirty posts on fugaziresearch.com from 6 June 2025 through 5 October 2026. The scorecard keeps 28.

Left out:

- Lost in Space, 12 June 2026, the sector piece.
- The second Energous report, 2 April 2026. The counted Energous row is 24 March 2026.

The median strip on the 27 reports before SDEV is day-1 −3.5%, max drawdown −74.3%, total −66.0% through the 5 October 2026 close. The table's Total column is the 6 October 2026 close, and that total median is −67.0%.
