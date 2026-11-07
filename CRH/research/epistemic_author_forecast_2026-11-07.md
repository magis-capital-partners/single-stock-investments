# CRH — epistemic author forecast (`0c6457af11f4a63293a9b6da`)

**As of:** 2026-11-07 · **Route:** `quality_reinvestment` · **Method:** `owner_earnings_reinvestment_dcf`

## Executive summary

Frozen v3 falsifier draft **v9** (`crh-operating-owner-earnings-2026q3-v9`) at `CRH/research/falsifier_drafts/0c6457af11f4a63293a9b6da.json`, status **`awaiting_review`**. The forecast fires if Q3 FY2026 TTM normalized owner earnings fall **below 2,912 USD millions**, matching the low-case `owner_earnings` node on the admitted valuation contract proof.

## Facts

- Component fingerprint unchanged: `bec50643c728d39be77d8deeccb51f780006382bbed0c4787ea24ef3ad3e4353`.
- Contract hash: `bd620a53edf5039b9434177e2cbb06669d54209ff49ae136ef27404044ddaa1d`.
- Low/base/high per-share outputs on admitted packet: **26.05 / 59.87 / 128.63 USD** (operating_business_and_net_assets).
- Historical replay (Q3 FY2025 TTM): **2,605 USD millions** via `normalized_owner_earnings_ttm_m_v2` / `sec_companyfacts_ttm`.

## Inference

- **34%** fire probability weights cyclical construction materials demand and integration spending against a prior-year Q3 replay already under the low-case anchor.
- Q3 FY2026 target period remains unobservable at the information cutoff; forecast stays **ex_ante** and **calibration_eligible: false**.

## Opinion

Independent reviewer should challenge materiality, period semantics, and adapter replay only; author did not change economics after the published input SHA update.

## Calibration receipt

`release_hash`: null · `named_challenge`: null · `calibration_response`: **not_applicable** (global `insufficient_outcomes` on `quality_reinvestment` / `owner_earnings_reinvestment_dcf`).
