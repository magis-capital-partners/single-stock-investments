# CEE — Milly adversarial (2026-07-20)

**Status:** re-pass after shadow-NAV rewrite

## Prior failure (fixed in dive)

- First scaffold treated CEE as a thin classic closed-end discount (−4% to reported NAV) and left Russia as a one-line footnote.
- That missed the actual edge: reported NAV zeros a still-disclosed Russia sleeve.

## Factual checks

- [x] Dive leads with Russia-at-zero / shadow NAV
- [x] MTM illustration cited (~$5.28 local / ~$8.68 full proxy per share)
- [x] Base case still keeps Russia at $0 (no smuggled recovery into the 4% return)
- [ ] Latest N-PORT share counts vs PH3 (31 Jul 2025) — **[HUMAN REVIEW]**
- [ ] ADR/GDR vs local unit mapping validated — **[HUMAN REVIEW]**

## Inference gaps

- Moscow mark-to-market ≠ realizable proceeds
- Bull 9.3% assumes ~half of local-only MTM; probability unset
- Fix Price line failed to price in the illustration

## Lens failure

Calling CEE “almost at NAV” because price ≈ reported NAV, while ignoring the zero-marked sleeve.
