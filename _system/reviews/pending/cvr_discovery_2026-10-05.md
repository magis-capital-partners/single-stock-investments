# CVR discovery — 2026-10-05

**UTC:** 2026-10-05T22:06:10Z  
**SEC ok:** True  
**SEC added:** 25  
**CSV/inbox / free-news added:** 25  
**Stubs created:** 25  
**Unhealthy streak:** False  

Context-tier candidates / stubs stay off the **CVRs** filter until `cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout or milestones.

Free auto feeds: SEC EFTS, Google News RSS, SEC Atom (no API keys).

## Stub folders created

- `SSTI/` (+ skeleton terms / evidence / manifest)
- `ATER/` (+ skeleton terms / evidence / manifest)
- `ATOS/` (+ skeleton terms / evidence / manifest)
- `HVII/` (+ skeleton terms / evidence / manifest)
- `WTTR/` (+ skeleton terms / evidence / manifest)
- `NRDE/` (+ skeleton terms / evidence / manifest)
- `ONAR/` (+ skeleton terms / evidence / manifest)
- `FLOC/` (+ skeleton terms / evidence / manifest)
- `REGN/` (+ skeleton terms / evidence / manifest)
- `PCSA/` (+ skeleton terms / evidence / manifest)
- `TWI/` (+ skeleton terms / evidence / manifest)
- `CDIX/` (+ skeleton terms / evidence / manifest)
- `BLDC/` (+ skeleton terms / evidence / manifest)
- `ATCH/` (+ skeleton terms / evidence / manifest)
- `MKLY/` (+ skeleton terms / evidence / manifest)
- `GRND/` (+ skeleton terms / evidence / manifest)
- `SMA/` (+ skeleton terms / evidence / manifest)
- `WHK/` (+ skeleton terms / evidence / manifest)
- `HCAC/` (+ skeleton terms / evidence / manifest)
- `VCTR/` (+ skeleton terms / evidence / manifest)
- `LRHC/` (+ skeleton terms / evidence / manifest)
- `ATII/` (+ skeleton terms / evidence / manifest)
- `WOR/` (+ skeleton terms / evidence / manifest)
- `AIBT/` (+ skeleton terms / evidence / manifest)
- `IQST/` (+ skeleton terms / evidence / manifest)

## New candidates

| Ticker | Source | Form | CIK | Hint |
|--------|--------|------|-----|------|
| `SSTI` | sec_full_text | 8-K | 0001351636 | https://www.sec.gov/Archives/edgar/data/1351636/000119312526406024/ |
| `ATER` | sec_full_text | 8-K | 0001757715 | https://www.sec.gov/Archives/edgar/data/1757715/000143774926031486/ |
| `ATOS` | sec_full_text | 8-K | 0001488039 | https://www.sec.gov/Archives/edgar/data/1488039/000119312526406036/ |
| `HVII` | sec_full_text | 8-K | 0001846416 | https://www.sec.gov/Archives/edgar/data/1846416/000149315226044924/ |
| `WTTR` | sec_full_text | 8-K | 0001693256 | https://www.sec.gov/Archives/edgar/data/1693256/000110465926110440/ |
| `NRDE` | sec_full_text | 8-K/A | 0001759546 | https://www.sec.gov/Archives/edgar/data/1759546/000149315226045157/ |
| `ONAR` | sec_full_text | 8-K | 0001682265 | https://www.sec.gov/Archives/edgar/data/1682265/000147793226005919/ |
| `FLOC` | sec_full_text | 8-K | 0002035149 | https://www.sec.gov/Archives/edgar/data/2035149/000119312526411196/ |
| `REGN` | sec_full_text | 8-K | 0000872589 | https://www.sec.gov/Archives/edgar/data/872589/000110465926112340/ |
| `PCSA` | sec_full_text | 8-K/A | 0001533743 | https://www.sec.gov/Archives/edgar/data/1533743/000114036126038535/ |
| `TWI` | sec_full_text | 8-K | 0000899751 | https://www.sec.gov/Archives/edgar/data/899751/000089975126000069/ |
| `CDIX` | sec_full_text | 8-K | 0000811222 | https://www.sec.gov/Archives/edgar/data/811222/000168316826007348/ |
| `BLDC` | sec_full_text | S-4/A | 0002097508 | https://www.sec.gov/Archives/edgar/data/2097508/000118518526004213/ |
| `ATCH` | sec_full_text | 8-K | 0001963088 | https://www.sec.gov/Archives/edgar/data/1963088/000149315226044145/ |
| `MKLY` | sec_full_text | S-4/A | 0002067592 | https://www.sec.gov/Archives/edgar/data/2067592/000121390026106819/ |
| `GRND` | sec_full_text | 8-K | 0001820144 | https://www.sec.gov/Archives/edgar/data/1820144/000182014426000033/ |
| `SMA` | sec_full_text | 8-K | 0001585389 | https://www.sec.gov/Archives/edgar/data/1585389/000119312526406164/ |
| `WHK` | sec_full_text | 8-K/A | 0001921603 | https://www.sec.gov/Archives/edgar/data/1921603/000119312526402855/ |
| `HCAC` | sec_full_text | S-4 | 0002079013 | https://www.sec.gov/Archives/edgar/data/2079013/000182912626010706/ |
| `VCTR` | sec_full_text | PREM14A | 0001570827 | https://www.sec.gov/Archives/edgar/data/1570827/000110465926112931/ |
| `LRHC` | sec_full_text | 8-K | 0001879403 | https://www.sec.gov/Archives/edgar/data/1879403/000121390026105473/ |
| `ATII` | sec_full_text | DEFM14A | 0002028516 | https://www.sec.gov/Archives/edgar/data/2028516/000110465926110234/ |
| `WOR` | sec_full_text | 8-K | 0000108516 | https://www.sec.gov/Archives/edgar/data/108516/000119312526397953/ |
| `AIBT` | sec_full_text | 8-K | 0001763329 | https://www.sec.gov/Archives/edgar/data/1763329/000109690626001500/ |
| `IQST` | sec_full_text | 8-K | 0001527702 | https://www.sec.gov/Archives/edgar/data/1527702/000166357726000309/ |

## Next actions

1. Confirm target vs acquirer (CIK resolve already preferred target).
2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.
3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).
4. Nightly sync will sleeve + surface on dashboard.

