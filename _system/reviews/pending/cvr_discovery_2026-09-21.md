# CVR discovery — 2026-09-21

**UTC:** 2026-09-21T19:53:46Z  
**SEC ok:** True  
**SEC added:** 25  
**CSV/inbox / free-news added:** 25  
**Stubs created:** 25  
**Unhealthy streak:** False  

Context-tier candidates / stubs stay off the **CVRs** filter until `cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout or milestones.

Free auto feeds: SEC EFTS, Google News RSS, SEC Atom (no API keys).

## Stub folders created

- `AEMD/` (+ skeleton terms / evidence / manifest)
- `CETX/` (+ skeleton terms / evidence / manifest)
- `ACGC/` (+ skeleton terms / evidence / manifest)
- `ELAB/` (+ skeleton terms / evidence / manifest)
- `FPS/` (+ skeleton terms / evidence / manifest)
- `KCA-UN/` (+ skeleton terms / evidence / manifest)
- `CNVS/` (+ skeleton terms / evidence / manifest)
- `PXED/` (+ skeleton terms / evidence / manifest)
- `DMAA/` (+ skeleton terms / evidence / manifest)
- `CDNA/` (+ skeleton terms / evidence / manifest)
- `EBS/` (+ skeleton terms / evidence / manifest)
- `MTB/` (+ skeleton terms / evidence / manifest)
- `RLGT/` (+ skeleton terms / evidence / manifest)
- `SAIL/` (+ skeleton terms / evidence / manifest)
- `AENT/` (+ skeleton terms / evidence / manifest)
- `WHD/` (+ skeleton terms / evidence / manifest)
- `WYFI/` (+ skeleton terms / evidence / manifest)
- `QNCX/` (+ skeleton terms / evidence / manifest)
- `MMTX/` (+ skeleton terms / evidence / manifest)
- `HCTI/` (+ skeleton terms / evidence / manifest)
- `VRA/` (+ skeleton terms / evidence / manifest)
- `ABM/` (+ skeleton terms / evidence / manifest)
- `ADI/` (+ skeleton terms / evidence / manifest)
- `CNM/` (+ skeleton terms / evidence / manifest)
- `CDT/` (+ skeleton terms / evidence / manifest)

## New candidates

| Ticker | Source | Form | CIK | Hint |
|--------|--------|------|-----|------|
| `AEMD` | sec_full_text | 8-K | 0000882291 | https://www.sec.gov/Archives/edgar/data/882291/000168316826007206/ |
| `CETX` | sec_full_text | 8-K/A | 0001435064 | https://www.sec.gov/Archives/edgar/data/1435064/000149315226042895/ |
| `ACGC` | sec_full_text | 8-K | 0002111542 | https://www.sec.gov/Archives/edgar/data/2111542/000121390026100367/ |
| `ELAB` | sec_full_text | 8-K | 0001840563 | https://www.sec.gov/Archives/edgar/data/1840563/000121390026101143/ |
| `FPS` | sec_full_text | 8-K | 0002080126 | https://www.sec.gov/Archives/edgar/data/2080126/000208012626000034/ |
| `KCA-UN` | sec_full_text | S-4 | 0002102713 | https://www.sec.gov/Archives/edgar/data/2102713/000119312526394814/ |
| `CNVS` | sec_full_text | 8-K | 0001173204 | https://www.sec.gov/Archives/edgar/data/1173204/000119312526394472/ |
| `PXED` | sec_full_text | 8-K | 0001600222 | https://www.sec.gov/Archives/edgar/data/1600222/000095014226002563/ |
| `DMAA` | sec_full_text | 8-K | 0002028614 | https://www.sec.gov/Archives/edgar/data/2028614/000121390026099738/ |
| `CDNA` | sec_full_text | 8-K/A | 0001217234 | https://www.sec.gov/Archives/edgar/data/1217234/000121723426000052/ |
| `EBS` | sec_full_text | 8-K | 0001367644 | https://www.sec.gov/Archives/edgar/data/1367644/000136764426000091/ |
| `MTB` | sec_full_text | 8-K | 0000036270 | https://www.sec.gov/Archives/edgar/data/36270/000003627026000052/ |
| `RLGT` | sec_full_text | 8-K | 0001171155 | https://www.sec.gov/Archives/edgar/data/1171155/000119312526390772/ |
| `SAIL` | sec_full_text | 8-K | 0002030781 | https://www.sec.gov/Archives/edgar/data/2030781/000162828026061015/ |
| `AENT` | sec_full_text | 8-K | 0001823584 | https://www.sec.gov/Archives/edgar/data/1823584/000149315226042245/ |
| `WHD` | sec_full_text | 8-K | 0001699136 | https://www.sec.gov/Archives/edgar/data/1699136/000162828026060938/ |
| `WYFI` | sec_full_text | 8-K | 0002042022 | https://www.sec.gov/Archives/edgar/data/2042022/000121390026099424/ |
| `QNCX` | sec_full_text | 8-K | 0001662774 | https://www.sec.gov/Archives/edgar/data/1662774/000119312526390652/ |
| `MMTX` | sec_full_text | S-4/A | 0002077033 | https://www.sec.gov/Archives/edgar/data/2077033/000149315226043206/ |
| `HCTI` | sec_full_text | 8-K | 0001839285 | https://www.sec.gov/Archives/edgar/data/1839285/000121390026097953/ |
| `VRA` | sec_full_text | 8-K | 0001495320 | https://www.sec.gov/Archives/edgar/data/1495320/000162828026061971/ |
| `ABM` | sec_full_text | 8-K | 0000771497 | https://www.sec.gov/Archives/edgar/data/771497/000119312526384364/ |
| `ADI` | sec_full_text | 8-K | 0000006281 | https://www.sec.gov/Archives/edgar/data/6281/000119312526385938/ |
| `CNM` | sec_full_text | 8-K | 0001856525 | https://www.sec.gov/Archives/edgar/data/1856525/000185652526000091/ |
| `CDT` | sec_full_text | 8-K | 0001896212 | https://www.sec.gov/Archives/edgar/data/1896212/000149315226043398/ |

## Next actions

1. Confirm target vs acquirer (CIK resolve already preferred target).
2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.
3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).
4. Nightly sync will sleeve + surface on dashboard.

