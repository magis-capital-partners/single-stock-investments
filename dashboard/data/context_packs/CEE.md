# Agent context pack: CEE (The Central and Eastern Europe Fund, Inc.)

## Identity (stable)
- Ticker: CEE
- Company: The Central and Eastern Europe Fund, Inc.
- Book: holdings
- Stance: watch
- Archetype: holding_co

## What this business is (stable)
The Central and Eastern Europe Fund is a New York–listed closed-end fund run by DWS. It owns a portfolio of mostly Polish and Hungarian equities (banks, energy, insurers, retailers) plus a frozen Russian equity sleeve. Since 14 March 2022 the fund has carried those Russian holdings at zero under sanctions and capital controls, even though the share counts are still disclosed. The publicly reported net asset value therefore describes only the liquid book. The share price usually tracks that reported figure closely.

## Why the market might be wrong (stable)
The interesting mispricing is not the thin discount to reported net asset value. It is that reported net asset value itself may understate economic ownership by writing the entire Russian book to zero. The predictive attribute is a Level-3 / sanctions zero mark: local Moscow prices still exist for many names, but a United States fund cannot freely realize them. If any path to recovery, private sale, or eventual unblocking opens, that sleeve is a free (or cheap) option on top of a solvent Central European equity portfolio. Buybacks when the fund trades below reported net asset value are a secondary catalyst, not the main edge.

## Returns (stable, percent per year)
- Base return: pending

## Key assumptions (stable)
- Price today: $20.48 (source: Yahoo CEE, ~20 Jul 2026)
- Reported net asset value: $21.32 (source: DWS, as of 17 Jul 2026)
- Shares outstanding: 6,520,194 (source: DWS fund facts (verify))
- Discount to reported net asset value: −3.9% (source: price ÷ reported − 1)
- Russia sleeve in **base** complete NAV: **$0** (source: Fund accounting since 14 Mar 2022; **[Assumption]** until human sets probability)
- Russia cost basis (reference): $30,722,586 (source: `CEE-PH3.pdf` as of 31 Jul 2025)
- Russia MTM illustration (local only): ~$5.28 / share (source: `russia_mtm_illustration.json` **[Assumption / not realizable]**)
- Russia MTM illustration (full proxy): ~$8.68 / share (source: same; ADR/GDR mapping uncertain)

## Open questions (stable)
- Set `realization_probability_base` for the Russia sleeve (still 0% in base).
- Refresh share counts from the latest N-PORT / N-CSR (PH3 is 31 Jul 2025).
- Decide ADR/GDR mapping rules before trusting the ~$30 full-proxy NAV.
- Confirm whether any further private sales of non-sanctioned receipts occurred after PH3.

## Verified claims (stable, cited)
- [assumption] Discount to reported net asset value: −3.9% (source: CEE/research/thesis_card.json)
- [assumption] Price today: $20.48 (source: CEE/research/thesis_card.json)
- [assumption] Reported net asset value: $21.32 (source: CEE/research/thesis_card.json)
- [assumption] Russia MTM illustration (full proxy): ~$8.68 / share (source: CEE/research/thesis_card.json)
- [assumption] Russia MTM illustration (local only): ~$5.28 / share (source: CEE/research/thesis_card.json)
- [assumption] Russia cost basis (reference): $30,722,586 (source: CEE/research/thesis_card.json)
- [assumption] Russia sleeve in **base** complete NAV: **$0** (source: CEE/research/thesis_card.json)
- [assumption] Shares outstanding: 6,520,194 (source: CEE/research/thesis_card.json)
- [pending] The Central and Eastern Europe Fund is a New York–listed closed-end fund run by DWS. It owns a portfolio of mostly Polish and Hungarian equities (banks, energy, insurers, retailers) plus a frozen Russian equity sleeve. Since 14 March 2022 the fund has carried those Russian holdings at zero under sanctions and capital controls, even though the share counts are still disclosed. The publicly reported net asset value therefore describes only the liquid book. The share price usually tracks that reported figure closely. (source: CEE/research/thesis_card.json)
- [pending] The interesting mispricing is not the thin discount to reported net asset value. It is that reported net asset value itself may understate economic ownership by writing the entire Russian book to zero. The predictive attribute is a Level-3 / sanctions zero mark: local Moscow prices still exist for many names, but a United States fund cannot freely realize them. If any path to recovery, private sale, or eventual unblocking opens, that sleeve is a free (or cheap) option on top of a solvent Central European equity portfolio. Buybacks when the fund trades below reported net asset value are a secondary catalyst, not the main edge. (source: CEE/research/thesis_card.json)

## Filing digest excerpt (semi-stable)
# Filing digest — CEE

**Generated:** 2026-08-06  
**Agent:** Marvin (`build_filing_evidence.py`)  
**Inventory:** `CEE/research/evidence/document_inventory.json`  

Documents in folder: **44** (all listed below; Tier 1–3 extracted or keyword-scanned).

## Document inventory

| Tier | Kind | File date | Path | Chars |
|------|------|-----------|------|-------|
| partial | proxy | 2023-05-12 | `investor-documents/sec-edgar/DEF 14A_20230512_rpt20230622_acc0001193125_23_143209.htm` | 30000 |
| partial | proxy | 2024-05-21 | `investor-documents/sec-edgar/DEF 14A_20240521_rpt20240627_acc0001193125_24_143715.htm` | 30000 |
| partial | proxy | 2025-05-21 | `investor-documents/sec-edgar/DEF 14A_20250521_rpt20250630_acc0001193125_25_124000.htm` | 30000 |
| full | proxy | 2026-05-20 | `investor-documents/sec-edgar/DEF 14A_20260520_rpt20260630_acc0001193125_26_231886.htm` | 124910 |
| partial | 8-K | 2018-05-08 | `investor-documents/sec-edgar/8-K_20180508_rpt20180508_acc0000088053_18_000481.htm` | 2827 |
| partial | 8-K | 2020-06-29 | `investor-documents/sec-edgar/8-K_20200629_rpt20200630_acc0000088053_20_000738.htm` | 4023 |
| partial | 8-K | 2020-09-25 | `investor-documents/sec-edgar/8-K_20200925_rpt20200925_acc0000088053_20_000969.htm` | 4008 |
| partial | 8-K | 2020-10-27 | `investor-documents/sec-edgar/8-K_20201027_rpt20201027_acc0000088053_20_001184.htm` | 2467 |
| partial | 8-K | 2021-05-12 | `investor-documents/sec-edgar/8-K_20210512_rpt20210512_acc0000088053_21_000452.htm` | 2218 |
| partial | 8-K | 2022-02-23 | `investor-documents/sec-edgar/8-K_20220223_rpt20220223_acc0000088053_22_000141.htm` | 2257 |
| inventory | other | — | `investor-documents/CEE-PH3.pdf` | 0 |
| inventory | other | 2022-04-25 | `investor-documents/sec-edgar/PRE 14A_20220425_rpt20220623_acc0001193125_22_117372.htm` | 0 |
| inventory | other | 2018-01-29 | `third-party-analyses/activist_reports/long/SC-13G/A_20180129_acc0000072971_18_000159.htm` | 0 |
| inventory | other | 2018-02-08 | `third-party-analyses/activist_reports/long/SC-13G/A_20180208_acc0001207017_18_000009.htm` | 0 |
| inventory | other | 2018-02-09 | `third-party-analyses/activist_reports/long/SC-13G/A_20180209_acc0001072613_18_000110.htm` | 0 |
| inventory | other | 2019-01-22 | `third-party-analyses/activist_reports/long/SC-13G/A_20190122_acc0000072971_19_000106.htm` | 0 |
| inventory | other | 2019-02-08 | `third-party-analyses/activist_reports/long/SC-13G/A_20190208_acc0001072613_19_000045.htm` | 0 |
| inventory | other | 2019-02-13 | `third-party-analyses/activist_reports/long/SC-13G/A_20190213_acc0001207017_19_000013.htm` | 0 |
| inventory | other | 2019-08-09 | `third-party-analyses/activist_reports/long/SC-13G/A_20190809_acc0000072971_19_000344.htm` | 0 |
| inventory | other | 2020-02-10 | `third-party-analyses/activist_reports/long/SC-13G/A_20200210_acc0001207017_20_000009.htm` | 0 |
| inventory | other | 2020-02-12 | `third-party-analyses/activist_reports/long/SC-13G/A_20200212_acc0001072613_20_000053.htm` | 0 |
| inventory | other | 2021-02-10 | `third-party-analyses/activist_reports/long/SC-13G/A_20210210_acc0001207017_21_000009.htm` | 0 |
| inventory | other | 2021-02-12 | `third-party-analyses/activist_reports/long/SC-13G/A_20210212_acc0000072971_21_000150.htm` | 0 |
| inventory | other | 2021-02-12 | `third-party-analyses/activist_reports/long/SC-13G/A_20210212_acc0001072613_21_000197.htm` | 0 |
| inventory | other | 2021-12-08 | `third-party-analyses/activist_reports/long/SC-13G/A_20211208_acc0000072971_21_000352.htm` | 0 |
| inventory | other | 2022-01-18 | `third-party-analyses/activist_reports/long/SC-13G/A_20220118_acc0001890906_22_000004.htm` | 0 |
| inventory | other | 2022-02-10 | `third-party-analyses/activist_reports/long/SC-13G/A_20220210_acc0001207017_22_000008.htm` | 0 |
| inventory | other | 2022-02-11 | `third-party-analyses/activist_reports/long/SC-13G/A_20220211_acc0001072613_22_000118.htm` | 0 |
| inventory | other | 2022-02-14 | `third-party-analyses/activist_reports/long/SC-13G/A_20220214_acc0001172661_22_000592.htm` | 0 |
| inventory | other | 2022-04-07 | `third-party-analyses/activist_reports/long/SC-13G/A_20220407_acc0001890906_22_000124.htm` | 0 |
| inventory | other | 2022-04-08 | `third-party-analyses/activist_reports/long/SC-13G/A_20220408_acc0001072613_22_000380.htm` | 0 |
| inventory | other | 2022-07-08 | `third-party-analyses/activist_reports/long/SC-13G/A_20220708_acc0001072613_22_000477.htm` | 0 |
| inventory | other | 2023-03-08 | `third-party-analyses/activist_reports/long/SC-13G/A_20230308_acc0001207017_23_000007.htm` | 0 |
| inventory | other | 2024-02-14 | `third-party-analyses/activist_reports/long/SC-13G/A_20240214_acc0000921895_24_000472.htm` | 0 |
| inventory | other | 2024-02-14 | `third-party-analyses/activist_reports/long/SC-13G/A_20240214_acc0001013594_24_000199.htm` | 0 |
| inventory | other | 2024-11-14 | `third-party-analyses/activist_reports/long/SC-13G/A_20241114_acc0001013594_24_000952.htm` | 0 |
| inventory | other | 2020-02-04 | `third-party-analyses/activist_reports/long/SC-13G_20200204_acc0000072971_20_000140.htm` | 0 |
| inventory | other | 2020-06-10 | `third-party-analyses/activist_reports/long/SC-13G_20200610_acc0000072971_20_000269.htm` | 0 |
| inventory | other | 2021-02-16 | `third-party-analyses/activist_reports/long/SC-13G_20210216_acc0001172661_21_000429.htm` | 0 |
| inventory | other | 2021-12-09 | `third-party-analyses/activist_reports/long/SC-13G_20211209_acc0001890906_21_000021.htm` | 0 |
| inventory | other | 2022-03-28 | `third-party-analyses/activist_reports/long/SC-13G_20220328_acc0000921895_22_000995.htm` | 0 |
| inventory | other | 2022-11-10 | `third-party-analyses/activist_reports/long/SC-13G_20221110_acc0001013594_22_000690.htm` | 0 |
| inventory | other | 2024-01-22 | `third-party-analyses/activist_reports/long/SC-13G_20240122_acc0001013594_24_000063.htm` | 0 |
| inventory | other | 2024-02-13 | `third-party-analyses/activist_reports/long/SC-13G_20240213_acc0

## Canonical pointers (open only when needed)
- deep_dive: CEE/research/deep_dive_2026-07-20.md (sha256 sha256:75a909656deea852...)
- filing_digest: CEE/research/evidence/filing_digest.md (sha256 sha256:dc8fcdc84c8efc7e...)
- adversarial: CEE/research/adversarial_2026-07-20.md (sha256 sha256:647ce51368b0d53b...)
- valuation: CEE/research/valuation.json (sha256 sha256:93c42c15249df15c...)
- thesis_card: CEE/research/thesis_card.json (sha256 sha256:77d3a6ff5da8efc2...)

## Excluded from this pack
- CEE/research/valuation.json (full; returns block included, open only for assumption audit)
- CEE/research/evidence/_text/ (raw filing text; use agent_search.py for chunk retrieval)
- dashboard/data/kpi_trends.json (monolith; KPI summary is in the L1 shard)
