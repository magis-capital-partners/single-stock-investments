# Factsheet audit, 2026-11-23

Proposal only. No factsheet, PDF, or other source file was deleted. This branch adds this note and the CSV beside it.

Read on 2026-11-24 from the git tree of this repo. Filename rule: path or filename contains `factsheet`, `fact-sheet`, `fact_sheet`, or `fact sheet` (any case, any extension), plus any file inside a folder named factsheets. No folder with that name exists in the working tree.

## Counts

| Class | Repo files | Vault files |
|---|---:|---:|
| KEEP | 9 | 0 |
| DELETE-CANDIDATE | 2 | 0 |
| UNSURE | 0 | 0 |
| pointer, unreadable | 0 individual paths | count unknown |

Readable factsheets: **11**, all in this repo, **4,437,794 bytes**.
Bytes reclaimable if the delete candidates are removed: **1,144** (both Goldman files). Vault bytes are unknown because those objects were not read.

## Delete candidates

Both Goldman paths are the same 572-byte file (SHA-256 `ef2a1a69b5aae292c1a315fcd5534fb33eb3903909ef1c5fb4c069119f401bea`). `file` identifies them as HTML, not PDF. The body is empty. The head is an Akamai boomerang snippet, an Adobe Launch script, `../index.js`, and `<meta name="robots" content="noindex, nofollow">`. There is no yield, holdings, AUM, or strategy text.

1. `GS/investor-documents/ir-gs/Fixed-Income-Fact-Sheet.pdf` (572 bytes). Empty HTML shell saved under a PDF name.
2. `GS/investor-documents/ir-gs/goldman-sachs-bank-usa-fixed-income-factsheet.pdf` (572 bytes). Exact duplicate of the file above.

They are listed in `GS/INDEX.csv` (size 572) and `GS/research/evidence/document_inventory.json`. `GS/research/evidence/filing_digest.md` already records 0 extracted pages for the second path. Download logs show the 572-byte body was stored as a successful download. If these two files are removed later, those index rows should be updated in the same change. This audit does not do that.

There are two delete candidates. The list stops there.

## UNSURE

No readable file was left as UNSURE.

Two files were close enough to record:

- `MTA/research/evidence/_text/factsheet.pdf.txt` is kept. It is the evidence extract of `MTA/investor-documents/ir-mta/factsheet.pdf`, not a second factsheet and not a hash duplicate. It repeats the royalty, GEO, and NAV figures. Deleting it would drop a research extract of a file this audit keeps.
- The January 2021 INFL pre-launch sheet has no performance table. It does name the ticker, managers, exchange, custodian, and investment criteria, so it stays KEEP.

## Files kept

| Path | Bytes | Pages | Extracted chars | Why kept |
|---|---:|---:|---:|---|
| `B/investor-documents/ir-b/Barrick_Fact_Sheet.pdf` | 421,415 | 3 | 35,211 | Q1 2026 Barrick highlights with net earnings, EBITDA, and operating figures. |
| `MTA/investor-documents/ir-mta/factsheet.pdf` | 428,325 | 2 | 11,053 | Metalla royalty and stream portfolio with asset exposures, GEO estimates, and NAV figures. |
| `MTA/research/evidence/_text/factsheet.pdf.txt` | 2,837 |  | 2,835 | Evidence text extract of the kept Metalla factsheet. Same royalty, GEO, and NAV figures, not an empty download. |
| `PSH/investor-documents/PSH-Fact-Sheet-March-2026.pdf` | 1,647,929 | 3 | 19,654 | Pershing Square fact sheet dated March 31, 2026, with portfolio company holdings. |
| `YUM/investor-documents/ir-yum/Yum-Russia-Ukraine-Factsheet-vF.pdf` | 223,662 | 1 | 1,395 | Yum Brands Russia and Ukraine supplement: restaurant counts and 2021 share of system sales, revenue, and operating profit. |
| `_system/reference/investment-wisdom/horizon-kinetics/pdfs/20210108173510_cb38f66f_HK_INFL_Pre-launch-Factsheet_January-2021_Final.pdf` | 245,274 | 2 | 8,331 | Pre-launch INFL sheet: ticker, portfolio managers, exchange, custodian, and investment criteria. No return table because the ETF had not launched. |
| `_system/reference/investment-wisdom/horizon-kinetics/pdfs/20210922045301_f7dabc8e_INFL-Factsheet-4.30.2021-4.pdf` | 128,712 | 2 | 11,964 | INFL fact sheet as of April 30, 2021, with NAV total returns and portfolio detail. |
| `_system/reference/investment-wisdom/horizon-kinetics/pdfs/20220814112910_b39dc566_INFL-Factsheet-Quarterly-Version-08.05.2022.pdf` | 205,128 | 2 | 17,666 | INFL quarterly fact sheet as of August 5, 2022, with NAV returns, top holdings, and sector mix. |
| `_system/reference/investment-wisdom/horizon-kinetics/pdfs/Horizon-Kinetics-JAPN-Factsheet.pdf` | 1,133,368 | 2 | 10,472 | JAPN fact sheet as of March 31, 2026: net assets, expense ratio, NAV returns, and top holdings. |

The four Horizon Kinetics PDFs are git-tracked under `_system/reference/investment-wisdom/`. `RESEARCH_VAULT_ROOT` points at `_external/research-vault`, and that directory is empty, so these copies live in this repo.

Different periods, not duplicates: INFL pre-launch (January 2021), INFL as of April 30, 2021, INFL as of August 5, 2022, and JAPN as of March 31, 2026. SHA-256 values differ.

`file` reports `Horizon-Kinetics-JAPN-Factsheet.pdf` as "0 page(s)". `pdfinfo` reports 2 pages, and `pdftotext` returns the NAV table, AUM, and holdings. The `file` page count is wrong. The PDF is kept.

## Pointers that could not be read

Private catalog and vault objects were not readable from this run. No factsheet path inside them is invented here. `magis-capital-partners/research-vault-legacy` was not fetched or otherwise touched.

| Pointer | What it claims | Where the bytes live | What this run could see |
|---|---|---|---|
| `_system/data/catalog/documents.jsonl` | `private_snapshot`, `entry_count` 8942 | research-catalog / R2, covering SSI, Drive, and research-vault | The stub only. No paths, names, or sizes. |
| `dashboard/data/document_catalog.json` | `private_snapshot`, collection `documents` 8942 | same private catalog | The stub only. |
| `dashboard/data/document_registry.json` | `private_snapshot`, collection `documents` 8942 | same private catalog | The stub only. |
| `magis-capital-partners/research-catalog` | metadata index in `_system/config/private_storage.json` (`catalog_repository_id` 1453145154) | GitHub private catalog; objects in R2 bucket `single-stock-investments-private` | GitHub API returned 404. No index shard was cloned. |
| `magis-capital-partners/research-vault` | letter and research corpus | private vault repo | GitHub API returned 404. Local checkout `_external/research-vault` has no files. |

Class for every factsheet that exists only behind those pointers: **pointer, unreadable**. Location: **vault** (catalog and R2), not this repo. A count would be a guess, so there is no count and no byte total.

The public summary `dashboard/data/document_catalog_summary.json` (generated 2026-10-16) says 8,815 documents, of which 409 are tagged vault. That file is a summary, not a path list, and it does not say how many of the 409 are factsheets.

## Google Drive index

This is not the vault and not a file in the git tree. `_system/reference/document-store/drive_filename_index.json` (generated 2026-11-19) indexes public Drive PDFs. It lists **75** filenames that match the factsheet rule. `private_pdfs_excluded` is **5,700**: licensed or private Drive PDFs were left out of the index, so more factsheets may exist there and are not listed.

The PDF bytes were not downloaded. They are not classified and they are not delete candidates. The reclaimable-byte total above does not include Drive.

Eight Drive filenames match a basename that is also in this repo. That is a name match only. Hashes were not compared, so they are not marked `duplicate_of`. `factsheet.pdf` is the ambiguous one: Metalla uses that basename in this repo, and the Drive file was not opened.

- `20210108173510_cb38f66f_HK_INFL_Pre-launch-Factsheet_January-2021_Final.pdf` (Drive id `1sAuX8UdUqFehQXo05M2k3QVD9V9Z7XyC`)
- `20210922045301_f7dabc8e_INFL-Factsheet-4.30.2021-4.pdf` (Drive id `1f0rBSCyEFODTtIkofEQiBGJBBkVDCGXY`)
- `20220814112910_b39dc566_INFL-Factsheet-Quarterly-Version-08.05.2022.pdf` (Drive id `1F4-CNkUJBEvEmzIPfaUdaFYddpq-GRU-`)
- `Barrick_Fact_Sheet.pdf` (Drive id `1d-tNRzof0P1FDIYJt1IdK43L5KAc-iEF`)
- `factsheet.pdf` (Drive id `1ZKFIivEfUdSGgb8rQ0j3tmf2ybHhhdZs`)
- `Horizon-Kinetics-JAPN-Factsheet.pdf` (Drive id `1P6rR9rVlOb6nXvc76LqoKC5B_uwh1bCq`)
- `PSH-Fact-Sheet-March-2026.pdf` (Drive id `1nB0xLsyzqM1KKyMMvIXVn8TMZGfeNv9f`)
- `Yum-Russia-Ukraine-Factsheet-vF.pdf` (Drive id `11ZKQnUcgDRL6vTUKHbgKcxp-3lTcDv-_`)

Drive filenames left unread:

- `20210108173510_cb38f66f_HK_INFL_Pre-launch-Factsheet_January-2021_Final.pdf`
- `20210922045301_f7dabc8e_INFL-Factsheet-4.30.2021-4.pdf`
- `20220814112910_b39dc566_INFL-Factsheet-Quarterly-Version-08.05.2022.pdf`
- `2023_08 Sandglass Opportunity Fund - Letter and Factsheet.pdf`
- `2024_04 Sandglass Opportunity Fund - Letter and Factsheet.pdf`
- `2024_11 Sandglass Opportunity Fund - Letter and Factsheet.pdf`
- `2025_05 Sandglass Opportunity Fund - Letter and Factsheet.pdf`
- `2025_09 Sandglass Opportunity Fund - Letter and Factsheet.pdf`
- `2026-09-16_DLD_Convertible-Arb-Fact-Sheet.pdf`
- `2026-09-16_DLD_Master-Fund-Fact-Sheet.pdf`
- `2026-10-09_Hatch-Cove-Capital_Fact-Sheet.pdf`
- `2026-10-09_K-Squared-Capital_Insignia-Institutional-Factsheet.pdf`
- `2026-10-13_Amber-Road-Investors_Monthly-Factsheet-August-2026.pdf`
- `2026-10-14_Electron-Capital_Fact-Sheet-September-2026.pdf`
- `2026-10-14_Thames-Capital_Absolute-Return-Fund-Factsheet-September-2026.pdf`
- `2026-11-09_Electron-Capital_Fact-Sheet-Oct-2026.pdf`
- `Ananda Factsheet Feb 2024.pdf`
- `ARR Factsheet - 2026-03-31.pdf`
- `AVCO+factsheet.pdf`
- `Barrick_Fact_Sheet.pdf`
- `Brennan OCP Fund Factsheet (May 2020).pdf`
- `Caledonia Mthly_L0019-2077_Fact_Sheet_Caledonia_Fund_Mar_2016.pdf`
- `Edgbaston 2017-06 EIP Investment Letter & Fact Sheet - FINAL.pdf`
- `Edgbaston 2017-12 EIP Investment Letter & Fact Sheet - FINAL.pdf`
- `Edgbaston 2019-09 EIP Investment Letter & Fact Sheet - FINAL.PDF`
- `Edgbaston 2019-12 EIP Investment Letter & Fact Sheet - FINAL.pdf`
- `Edgbaston 2020-06 EIP Investment Letter & Fact Sheet - FINAL.pdf`
- `EIP Investment Letter & Fact Sheet - FINAL 2018-06.PDF`
- `EIP Investment Letter & Fact Sheet - FINAL 2020-03.pdf`
- `EIP Investment Letter & Fact Sheet - FINAL.pdf`
- `Factsheet Mar 2021.pdf`
- `factsheet.pdf`
- `FBFC Fund Factsheet - (February 2024) vF.pdf`
- `FBFC Fund Factsheet - (January 2023) VF.pdf`
- `FBFC Fund Factsheet - (January 2024) vF.pdf`
- `FBFC Fund Factsheet - (March 2023) vF.pdf`
- `FBFC Fund Factsheet - (September 2022) .pdf`
- `Fund-Data-Fact-Sheet_Polar-Capital-Funds-plc-Asian-Stars-Fund-Polar-Capital-Funds-plc-Asian-Stars-Fund-I-USD_30-04-2025.pdf`
- `GA-Courtenay Special Situations Fund Monthly Factsheet - Feb 24.pdf`
- `GA-Courtenay Special Situations Fund Monthly Factsheet - Jan 24.pdf`
- `GA-Courtenay Special Situations Fund Monthly Factsheet - June-2025.pdf`
- `GA-Courtenay Special Situations Fund Monthly Factsheet - May-2026(2).pdf`
- `GA-Courtenay Special Situations Fund Monthly Factsheet - Nov 23.pdf`
- `GA-Courtenay Special Situations Fund Monthly Factsheet - Sep 2024.pdf`
- `Hill Fort India Fund Factsheet - July 2020.pdf`
- `Horizon-Kinetics-JAPN-Factsheet.pdf`
- `Invenomic Fund LP Fact Sheet - September 2024.pdf`
- `Lazard Coherence Long Short Credit - Factsheet (Aug 2021).pdf`
- `Lazard Rathmore Fact Sheet - August.pdf`
- `Lazard Rathmore Plus Fact Sheet - August 2021.pdf`
- `MidOcean Absolute Return Credit Fund Factsheet - March 2020.pdf`
- `MIRI Strategic EM Fund Factsheet April 2021 - Prelim.pdf`
- `MZAF Fact Sheet 2018.12.31.pdf`
- `Olesen Value Fund L.P. factsheet - Dec 2023.pdf`
- `Professional-Investor-Fact-Sheet_Polar-Capital-Funds-plc-Artificial-Intelligence-Fund-I-Acc-USD_31-03-2025.pdf`
- `PSH-Fact-Sheet-March-2026.pdf`
- `rtw-biotech-opportunitiesmarch-2025-factsheet-plusq1-letter_vff.pdf`
- `Sandglass 2023_09 Sandglass Opportunity Fund - Letter and Factsheet.pdf`
- `Sandglass 2023_12 Sandglass Opportunity Fund - Letter and Factsheet.pdf`
- `Sandglass 2023_Q4 Sandglass Pathfinder - Letter and Factsheet.pdf`
- `Sandglass Opportunity Fund - Letter and Factsheet 2022_06.pdf`
- `Sandglass Opportunity Fund - Letter and Factsheet 2022_09.pdf`
- `Sandglass Opportunity Fund - Letter and Factsheet 2022_12.pdf`
- `Sandglass Opportunity Fund - Letter and Factsheet 2023_03.pdf`
- `Sandglass Opportunity Fund - Letter and Factsheet 2023_06.pdf`
- `Sandglass Opportunity Fund - Letter and Factsheet 2024_03.pdf`
- `Sandglass Opportunity Fund - Letter and Factsheet 2024_12.pdf`
- `Sandglass Pathfinder - Letter and Factsheet 2023_Q1.pdf`
- `Sandglass Pathfinder - Letter and Factsheet 2023_Q3.pdf`
- `Sandglass Pathfinder - Letter and Factsheet 2024_Q1.pdf`
- `Sandglass Pathfinder - Letter and Factsheet2022_Q4.pdf`
- `Three Body Factsheet Jan 2021.pdf`
- `Three Body Factsheet Oct 2020.pdf`
- `Yulan Factsheet - 2018 Dec.pdf`
- `Yum-Russia-Ukraine-Factsheet-vF.pdf`

## How files were classed

For each git-tracked match: SHA-256, `file`, `pdfinfo` page count when the bytes are a PDF, and `pdftotext -layout`. Non-PDF text is the decoded file. Extracted chars are the length of that text (Unicode characters, not bytes).

- KEEP: performance, holdings, exposures, AUM, terms, or specific strategy or operating figures.
- DELETE-CANDIDATE: empty or near-empty text, an image-only shell with nothing usable, disclaimer only, a login/error/redirect/cookie page saved as a file, or a hash or same-period duplicate of a kept file.
- UNSURE: borderline content. None in the readable set.
- pointer, unreadable: a catalog or vault reference whose bytes this run could not open.

No image-only PDF turned up. The kept PDFs that also contain images still have a text layer with the figures above.

## Approval

If the two Goldman shells are approved for deletion, the change is those two paths only, plus the index rows that name them. Nothing else in this report is proposed for deletion.
