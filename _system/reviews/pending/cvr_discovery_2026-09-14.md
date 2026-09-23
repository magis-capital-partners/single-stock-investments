# CVR discovery — 2026-09-14

**UTC:** 2026-09-14T19:45:26Z  
**SEC ok:** True  
**SEC added:** 25  
**CSV/inbox / free-news added:** 25  
**Stubs created:** 25  
**Unhealthy streak:** False  

Context-tier candidates / stubs stay off the **CVRs** filter until `cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout or milestones.

Free auto feeds: SEC EFTS, Google News RSS, SEC Atom (no API keys).

## Stub folders created

- `LAB/` (+ skeleton terms / evidence / manifest)
- `INM/` (+ skeleton terms / evidence / manifest)
- `BWIN/` (+ skeleton terms / evidence / manifest)
- `CSR/` (+ skeleton terms / evidence / manifest)
- `IRT/` (+ skeleton terms / evidence / manifest)
- `SUPN/` (+ skeleton terms / evidence / manifest)
- `EFSI/` (+ skeleton terms / evidence / manifest)
- `JMSB/` (+ skeleton terms / evidence / manifest)
- `RSSS/` (+ skeleton terms / evidence / manifest)
- `GAME/` (+ skeleton terms / evidence / manifest)
- `AIRJ/` (+ skeleton terms / evidence / manifest)
- `QUBT/` (+ skeleton terms / evidence / manifest)
- `BRO/` (+ skeleton terms / evidence / manifest)
- `SWMR/` (+ skeleton terms / evidence / manifest)
- `LPTH/` (+ skeleton terms / evidence / manifest)
- `NOMA/` (+ skeleton terms / evidence / manifest)
- `LHAI/` (+ skeleton terms / evidence / manifest)
- `EZRA/` (+ skeleton terms / evidence / manifest)
- `APUR/` (+ skeleton terms / evidence / manifest)
- `FELE/` (+ skeleton terms / evidence / manifest)
- `LPBB/` (+ skeleton terms / evidence / manifest)
- `IPGP/` (+ skeleton terms / evidence / manifest)
- `PRDO/` (+ skeleton terms / evidence / manifest)
- `DSGR/` (+ skeleton terms / evidence / manifest)
- `KPLT/` (+ skeleton terms / evidence / manifest)

## New candidates

| Ticker | Source | Form | CIK | Hint |
|--------|--------|------|-----|------|
| `LAB` | sec_full_text | S-4/A | 0001162194 | https://www.sec.gov/Archives/edgar/data/1162194/000114036126036084/ |
| `INM` | sec_full_text | S-4/A | 0001728328 | https://www.sec.gov/Archives/edgar/data/1728328/000119312526386611/ |
| `BWIN` | sec_full_text | 8-K | 0001781755 | https://www.sec.gov/Archives/edgar/data/1781755/000095010326013874/ |
| `CSR` | sec_full_text | 8-K | 0000798359 | https://www.sec.gov/Archives/edgar/data/798359/000114036126035986/ |
| `IRT` | sec_full_text | 8-K | 0001466085 | https://www.sec.gov/Archives/edgar/data/1466085/000143774926029903/ |
| `SUPN` | sec_full_text | DEFM14A | 0001356576 | https://www.sec.gov/Archives/edgar/data/1356576/000110465926107109/ |
| `EFSI` | sec_full_text | 8-K | 0000880641 | https://www.sec.gov/Archives/edgar/data/880641/000119312526384457/ |
| `JMSB` | sec_full_text | 8-K | 0001710482 | https://www.sec.gov/Archives/edgar/data/1710482/000155278126000472/ |
| `RSSS` | sec_full_text | 8-K | 0001386301 | https://www.sec.gov/Archives/edgar/data/1386301/000110465926106331/ |
| `GAME` | sec_full_text | 8-K | 0001714562 | https://www.sec.gov/Archives/edgar/data/1714562/000149315226041884/ |
| `AIRJ` | sec_full_text | 8-K | 0001855474 | https://www.sec.gov/Archives/edgar/data/1855474/000119312526389855/ |
| `QUBT` | sec_full_text | 8-K/A | 0001758009 | https://www.sec.gov/Archives/edgar/data/1758009/000121390026098032/ |
| `BRO` | sec_full_text | 8-K | 0000079282 | https://www.sec.gov/Archives/edgar/data/79282/000119312526386867/ |
| `SWMR` | sec_full_text | 8-K | 0002092574 | https://www.sec.gov/Archives/edgar/data/2092574/000110465926106499/ |
| `LPTH` | sec_full_text | 8-K | 0000889971 | https://www.sec.gov/Archives/edgar/data/889971/000143774926030074/ |
| `NOMA` | sec_full_text | 8-K | 0001994214 | https://www.sec.gov/Archives/edgar/data/1994214/000149315226042486/ |
| `LHAI` | sec_full_text | 8-K/A | 0002017758 | https://www.sec.gov/Archives/edgar/data/2017758/000121390026098789/ |
| `EZRA` | sec_full_text | 8-K | 0001812727 | https://www.sec.gov/Archives/edgar/data/1812727/000149315226041914/ |
| `APUR` | sec_full_text | 8-K | 0002093524 | https://www.sec.gov/Archives/edgar/data/2093524/000121390026098971/ |
| `FELE` | sec_full_text | 8-K | 0000038725 | https://www.sec.gov/Archives/edgar/data/38725/000003872526000062/ |
| `LPBB` | sec_full_text | S-4 | 0002023676 | https://www.sec.gov/Archives/edgar/data/2023676/000121390026099372/ |
| `IPGP` | sec_full_text | 8-K | 0001111928 | https://www.sec.gov/Archives/edgar/data/1111928/000111192826000169/ |
| `PRDO` | sec_full_text | 8-K | 0001046568 | https://www.sec.gov/Archives/edgar/data/1046568/000119312526389857/ |
| `DSGR` | sec_full_text | 8-K | 0000703604 | https://www.sec.gov/Archives/edgar/data/703604/000119312526387187/ |
| `KPLT` | sec_full_text | 8-K/A | 0001785424 | https://www.sec.gov/Archives/edgar/data/1785424/000110465926107062/ |

## Next actions

1. Confirm target vs acquirer (CIK resolve already preferred target).
2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.
3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).
4. Nightly sync will sleeve + surface on dashboard.

