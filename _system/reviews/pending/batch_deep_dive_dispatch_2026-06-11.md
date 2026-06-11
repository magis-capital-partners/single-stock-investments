# Batch deep dive dispatch — Royalty King screen (2026-06-11)

**Trigger:** User requested deep dives for 26 tickers onboarded from `royalty_king_hk_screen_2026-06-11.md`.

**Queue file:** `_system/data/deep_dive_dispatch_queue.json` (26 tickers, `max_parallel`: 3)

## Tickers

`0388.HK, ABX, ASX.AX, B3SA3.SA, BMYS.KL, BOLSAA.MX, BSM, BYMA, CDZI, DB1.DE, ENX.PA, EVR, GPW.WA, GROY, HEE, KRP, MTA, NDAQ, NRP, NZX.NZ, PSE, S68.SI, TASE, TFPM, X.TO, XP`

## How to run (after merge to main)

1. **Batch workflow (recommended):**
   ```bash
   gh workflow run batch-marvin-deep-dive.yml -R GoldmanDrew/single-stock-investments
   ```
   Or push/merge this branch so the queue file on `main` triggers the workflow automatically.

2. **Manual per ticker:**
   ```bash
   gh workflow run marvin-deep-dive.yml -f ticker=GROY
   ```

3. **Daily refresh** will also pick `onboard_pending` holdings (newest onboard first).

## Notes

- Onboard used `--skip-download`; deep dive agents should run `marvin_cloud_refresh.py` which includes evidence build and US SEC download where configured.
- **International exchanges** (EU scaffold): IR PDF harvest may need Vicki brief if scrape returns thin results (`0388.HK`, `B3SA3.SA`, `BYMA`, etc.).
- **EVR** is CSE-listed; confirm SEDAR/CSE filings path during first dive.
- **HEE** ticker on ATHEX is often **EXAE**; folder symbol is `HEE` per Royalty King screen — verify listing symbol in dive.

## [HUMAN REVIEW]

- Merge PR #138 (or follow-on) to activate batch dispatch on `main`.
- Prioritize Royalty King high-conviction names first if queue should be partial: **GROY, EVR, TFPM, XP, 0388.HK**.

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] Royalty King + HK screen batch 2026-06-11: 26 tickers onboarded; deep dive queue staged for batch-marvin-deep-dive workflow.
