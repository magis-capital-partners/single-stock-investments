# CVR discovery — 2026-11-09

**UTC:** 2026-11-09T23:57:50Z  
**SEC ok:** True  
**SEC added:** 25  
**CSV/inbox / free-news added:** 25  
**Stubs created:** 25  
**Unhealthy streak:** False  

Context-tier candidates / stubs stay off the **CVRs** filter until `cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout or milestones.

Free auto feeds: SEC EFTS, Google News RSS, SEC Atom (no API keys).

## Stub folders created

- `KPTI/` (+ skeleton terms / evidence / manifest)
- `CMMB/` (+ skeleton terms / evidence / manifest)
- `SHFS/` (+ skeleton terms / evidence / manifest)
- `SYRE/` (+ skeleton terms / evidence / manifest)
- `DTB/` (+ skeleton terms / evidence / manifest)
- `RNST/` (+ skeleton terms / evidence / manifest)
- `PLNH/` (+ skeleton terms / evidence / manifest)
- `ELF/` (+ skeleton terms / evidence / manifest)
- `ARCB/` (+ skeleton terms / evidence / manifest)
- `BELFA/` (+ skeleton terms / evidence / manifest)
- `ON/` (+ skeleton terms / evidence / manifest)
- `CRD-A/` (+ skeleton terms / evidence / manifest)
- `ACEL/` (+ skeleton terms / evidence / manifest)
- `JMKE/` (+ skeleton terms / evidence / manifest)
- `SVAQ/` (+ skeleton terms / evidence / manifest)
- `RGEN/` (+ skeleton terms / evidence / manifest)
- `RMTI/` (+ skeleton terms / evidence / manifest)
- `PSQH/` (+ skeleton terms / evidence / manifest)
- `MGPI/` (+ skeleton terms / evidence / manifest)
- `XPOF/` (+ skeleton terms / evidence / manifest)
- `DOCS/` (+ skeleton terms / evidence / manifest)
- `ONT/` (+ skeleton terms / evidence / manifest)
- `VRTS/` (+ skeleton terms / evidence / manifest)
- `GYGY/` (+ skeleton terms / evidence / manifest)
- `UFPI/` (+ skeleton terms / evidence / manifest)

## New candidates

| Ticker | Source | Form | CIK | Hint |
|--------|--------|------|-----|------|
| `KPTI` | sec_full_text | 8-K | 0001503802 | https://www.sec.gov/Archives/edgar/data/1503802/000119312526444164/ |
| `CMMB` | sec_full_text | DEFM14A | 0001534248 | https://www.sec.gov/Archives/edgar/data/1534248/000149315226049444/ |
| `SHFS` | sec_full_text | 8-K | 0001854963 | https://www.sec.gov/Archives/edgar/data/1854963/000149315226048425/ |
| `SYRE` | sec_full_text | 8-K | 0001636282 | https://www.sec.gov/Archives/edgar/data/1636282/000163628226000132/ |
| `DTB` | sec_full_text | 8-K | 0000936340 | https://www.sec.gov/Archives/edgar/data/936340/000119312526448536/ |
| `RNST` | sec_full_text | 8-K | 0000715072 | https://www.sec.gov/Archives/edgar/data/715072/000119312526434444/ |
| `PLNH` | sec_full_text | DEFM14A | 0001813452 | https://www.sec.gov/Archives/edgar/data/1813452/000110465926121478/ |
| `ELF` | sec_full_text | 8-K | 0001600033 | https://www.sec.gov/Archives/edgar/data/1600033/000160003326000048/ |
| `ARCB` | sec_full_text | 8-K | 0000894405 | https://www.sec.gov/Archives/edgar/data/894405/000110465926122317/ |
| `BELFA` | sec_full_text | 8-K | 0000729580 | https://www.sec.gov/Archives/edgar/data/729580/000143774926033795/ |
| `ON` | sec_full_text | 8-K | 0001097864 | https://www.sec.gov/Archives/edgar/data/1097864/000119312526443681/ |
| `CRD-A` | sec_full_text | 8-K | 0000025475 | https://www.sec.gov/Archives/edgar/data/25475/000119312526443691/ |
| `ACEL` | sec_full_text | 8-K | 0001698991 | https://www.sec.gov/Archives/edgar/data/1698991/000169899126000068/ |
| `JMKE` | sec_full_text | 8-K | 0002127043 | https://www.sec.gov/Archives/edgar/data/2127043/000212704326000015/ |
| `SVAQ` | sec_full_text | S-4/A | 0002085659 | https://www.sec.gov/Archives/edgar/data/2085659/000121390026115045/ |
| `RGEN` | sec_full_text | 8-K | 0000730272 | https://www.sec.gov/Archives/edgar/data/730272/000162828026067405/ |
| `RMTI` | sec_full_text | 8-K | 0001041024 | https://www.sec.gov/Archives/edgar/data/1041024/000110465926122103/ |
| `PSQH` | sec_full_text | 8-K | 0001847064 | https://www.sec.gov/Archives/edgar/data/1847064/000110465926123566/ |
| `MGPI` | sec_full_text | 8-K | 0000835011 | https://www.sec.gov/Archives/edgar/data/835011/000083501126000122/ |
| `XPOF` | sec_full_text | 8-K | 0001802156 | https://www.sec.gov/Archives/edgar/data/1802156/000119312526449959/ |
| `DOCS` | sec_full_text | 8-K | 0001516513 | https://www.sec.gov/Archives/edgar/data/1516513/000151651326000049/ |
| `ONT` | sec_full_text | 8-K | 0001643615 | https://www.sec.gov/Archives/edgar/data/1643615/000119312526447197/ |
| `VRTS` | sec_full_text | 8-K | 0000883237 | https://www.sec.gov/Archives/edgar/data/883237/000088323726000064/ |
| `GYGY` | sec_full_text | 8-K | 0002111846 | https://www.sec.gov/Archives/edgar/data/2111846/000121390026112232/ |
| `UFPI` | sec_full_text | 8-K | 0000912767 | https://www.sec.gov/Archives/edgar/data/912767/000091276726000058/ |

## Next actions

1. Confirm target vs acquirer (CIK resolve already preferred target).
2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.
3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).
4. Nightly sync will sleeve + surface on dashboard.

