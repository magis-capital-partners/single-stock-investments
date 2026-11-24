# CVR discovery — 2026-11-24

**UTC:** 2026-11-24T02:22:13Z  
**SEC ok:** True  
**SEC added:** 25  
**CSV/inbox / free-news added:** 25  
**Stubs created:** 25  
**Unhealthy streak:** False  

Context-tier candidates / stubs stay off the **CVRs** filter until `cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout or milestones.

Free auto feeds: SEC EFTS, Google News RSS, SEC Atom (no API keys).

## Stub folders created

- `ZS/` (+ skeleton terms / evidence / manifest)
- `CRWD/` (+ skeleton terms / evidence / manifest)
- `ALTG/` (+ skeleton terms / evidence / manifest)
- `ALCUF/` (+ skeleton terms / evidence / manifest)
- `SVCC/` (+ skeleton terms / evidence / manifest)
- `TTEK/` (+ skeleton terms / evidence / manifest)
- `IRHO/` (+ skeleton terms / evidence / manifest)
- `SBDS/` (+ skeleton terms / evidence / manifest)
- `GTERA/` (+ skeleton terms / evidence / manifest)
- `VELO/` (+ skeleton terms / evidence / manifest)
- `TLSI/` (+ skeleton terms / evidence / manifest)
- `SPIR/` (+ skeleton terms / evidence / manifest)
- `AROC/` (+ skeleton terms / evidence / manifest)
- `HUMA/` (+ skeleton terms / evidence / manifest)
- `VERI/` (+ skeleton terms / evidence / manifest)
- `VTIX/` (+ skeleton terms / evidence / manifest)
- `SQFT/` (+ skeleton terms / evidence / manifest)
- `SND/` (+ skeleton terms / evidence / manifest)
- `LFWD/` (+ skeleton terms / evidence / manifest)
- `MNTK/` (+ skeleton terms / evidence / manifest)
- `AAWH/` (+ skeleton terms / evidence / manifest)
- `MWH/` (+ skeleton terms / evidence / manifest)
- `GLIBA/` (+ skeleton terms / evidence / manifest)
- `SES/` (+ skeleton terms / evidence / manifest)
- `RMR/` (+ skeleton terms / evidence / manifest)

## New candidates

| Ticker | Source | Form | CIK | Hint |
|--------|--------|------|-----|------|
| `ZS` | sec_full_text | 8-K | 0001713683 | https://www.sec.gov/Archives/edgar/data/1713683/000119312526471211/ |
| `CRWD` | sec_full_text | 8-K | 0001535527 | https://www.sec.gov/Archives/edgar/data/1535527/000110465926130785/ |
| `ALTG` | sec_full_text | 8-K | 0001759824 | https://www.sec.gov/Archives/edgar/data/1759824/000119312526472630/ |
| `ALCUF` | sec_full_text | DEFM14A | 0001901336 | https://www.sec.gov/Archives/edgar/data/1901336/000110465926128751/ |
| `SVCC` | sec_full_text | 8-K | 0002033593 | https://www.sec.gov/Archives/edgar/data/2033593/000121390026121502/ |
| `TTEK` | sec_full_text | 8-K | 0000831641 | https://www.sec.gov/Archives/edgar/data/831641/000110465926125600/ |
| `IRHO` | sec_full_text | S-4/A | 0002051985 | https://www.sec.gov/Archives/edgar/data/2051985/000121390026118113/ |
| `SBDS` | sec_full_text | 8-K | 0001870600 | https://www.sec.gov/Archives/edgar/data/1870600/000187060026000049/ |
| `GTERA` | sec_full_text | 8-K | 0002043766 | https://www.sec.gov/Archives/edgar/data/2043766/000114036126043465/ |
| `VELO` | sec_full_text | 8-K | 0001825079 | https://www.sec.gov/Archives/edgar/data/1825079/000119312526455425/ |
| `TLSI` | sec_full_text | 8-K | 0001826667 | https://www.sec.gov/Archives/edgar/data/1826667/000162828026072513/ |
| `SPIR` | sec_full_text | 8-K | 0001816017 | https://www.sec.gov/Archives/edgar/data/1816017/000162828026072744/ |
| `AROC` | sec_full_text | 8-K | 0001389050 | https://www.sec.gov/Archives/edgar/data/1389050/000110465926125218/ |
| `HUMA` | sec_full_text | 8-K | 0001818382 | https://www.sec.gov/Archives/edgar/data/1818382/000119312526454402/ |
| `VERI` | sec_full_text | 8-K | 0001615165 | https://www.sec.gov/Archives/edgar/data/1615165/000161516526000004/ |
| `VTIX` | sec_full_text | 8-K | 0001606242 | https://www.sec.gov/Archives/edgar/data/1606242/000121390026120170/ |
| `SQFT` | sec_full_text | 8-K | 0001080657 | https://www.sec.gov/Archives/edgar/data/1080657/000149315226052646/ |
| `SND` | sec_full_text | 8-K | 0001529628 | https://www.sec.gov/Archives/edgar/data/1529628/000152962826000116/ |
| `LFWD` | sec_full_text | 8-K | 0001607962 | https://www.sec.gov/Archives/edgar/data/1607962/000117891326005208/ |
| `MNTK` | sec_full_text | 8-K | 0001826600 | https://www.sec.gov/Archives/edgar/data/1826600/000119312526462117/ |
| `AAWH` | sec_full_text | 8-K | 0001756390 | https://www.sec.gov/Archives/edgar/data/1756390/000162828026073387/ |
| `MWH` | sec_full_text | 8-K | 0002065636 | https://www.sec.gov/Archives/edgar/data/2065636/000119312526456918/ |
| `GLIBA` | sec_full_text | 8-K | 0002057463 | https://www.sec.gov/Archives/edgar/data/2057463/000110465926125416/ |
| `SES` | sec_full_text | 8-K | 0001819142 | https://www.sec.gov/Archives/edgar/data/1819142/000181914226000066/ |
| `RMR` | sec_full_text | 8-K | 0001644378 | https://www.sec.gov/Archives/edgar/data/1644378/000164437826000025/ |

## Next actions

1. Confirm target vs acquirer (CIK resolve already preferred target).
2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.
3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).
4. Nightly sync will sleeve + surface on dashboard.

