# CVR discovery — 2026-09-28

**UTC:** 2026-09-28T21:08:40Z  
**SEC ok:** True  
**SEC added:** 8  
**CSV/inbox / free-news added:** 8  
**Stubs created:** 8  
**Unhealthy streak:** False  

Context-tier candidates / stubs stay off the **CVRs** filter until `cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout or milestones.

Free auto feeds: SEC EFTS, Google News RSS, SEC Atom (no API keys).

## Stub folders created

- `ZYME/` (+ skeleton terms / evidence / manifest)
- `LFCR/` (+ skeleton terms / evidence / manifest)
- `MGLD/` (+ skeleton terms / evidence / manifest)
- `NATH/` (+ skeleton terms / evidence / manifest)
- `BEAG/` (+ skeleton terms / evidence / manifest)
- `APAM/` (+ skeleton terms / evidence / manifest)
- `FXAC/` (+ skeleton terms / evidence / manifest)
- `PATK/` (+ skeleton terms / evidence / manifest)

## New candidates

| Ticker | Source | Form | CIK | Hint |
|--------|--------|------|-----|------|
| `ZYME` | sec_full_text | 8-K | 0001937653 | https://www.sec.gov/Archives/edgar/data/1937653/000119312526399383/ |
| `LFCR` | sec_full_text | 8-K | 0001005286 | https://www.sec.gov/Archives/edgar/data/1005286/000114036126037767/ |
| `MGLD` | sec_full_text | 8-K | 0001005101 | https://www.sec.gov/Archives/edgar/data/1005101/000149315226044491/ |
| `NATH` | sec_full_text | DEFM14A | 0000069733 | https://www.sec.gov/Archives/edgar/data/69733/000110465926110393/ |
| `BEAG` | sec_full_text | 8-K | 0001852207 | https://www.sec.gov/Archives/edgar/data/1852207/000121390026103758/ |
| `APAM` | sec_full_text | 8-K | 0001517302 | https://www.sec.gov/Archives/edgar/data/1517302/000151730226000124/ |
| `FXAC` | sec_full_text | 8-K | 0002121703 | https://www.sec.gov/Archives/edgar/data/2121703/000182912626010318/ |
| `PATK` | sec_full_text | S-4 | 0000076605 | https://www.sec.gov/Archives/edgar/data/76605/000162828026063259/ |

## Next actions

1. Confirm target vs acquirer (CIK resolve already preferred target).
2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.
3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).
4. Nightly sync will sleeve + surface on dashboard.

