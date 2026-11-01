# CVR discovery — 2026-10-19

**UTC:** 2026-10-19T20:43:27Z  
**SEC ok:** True  
**SEC added:** 25  
**CSV/inbox / free-news added:** 25  
**Stubs created:** 25  
**Unhealthy streak:** False  

Context-tier candidates / stubs stay off the **CVRs** filter until `cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout or milestones.

Free auto feeds: SEC EFTS, Google News RSS, SEC Atom (no API keys).

## Stub folders created

- `VEEE/` (+ skeleton terms / evidence / manifest)
- `VTRS/` (+ skeleton terms / evidence / manifest)
- `PCRX/` (+ skeleton terms / evidence / manifest)
- `INSW/` (+ skeleton terms / evidence / manifest)
- `BMBL/` (+ skeleton terms / evidence / manifest)
- `CCC/` (+ skeleton terms / evidence / manifest)
- `SLN/` (+ skeleton terms / evidence / manifest)
- `OPCH/` (+ skeleton terms / evidence / manifest)
- `LEU/` (+ skeleton terms / evidence / manifest)
- `PAG/` (+ skeleton terms / evidence / manifest)
- `HSCS/` (+ skeleton terms / evidence / manifest)
- `LCII/` (+ skeleton terms / evidence / manifest)
- `VREOF/` (+ skeleton terms / evidence / manifest)
- `DLX/` (+ skeleton terms / evidence / manifest)
- `TARS/` (+ skeleton terms / evidence / manifest)
- `YYAI/` (+ skeleton terms / evidence / manifest)
- `CRON/` (+ skeleton terms / evidence / manifest)
- `RPM/` (+ skeleton terms / evidence / manifest)
- `BEEM/` (+ skeleton terms / evidence / manifest)
- `CRGY/` (+ skeleton terms / evidence / manifest)
- `IONQ/` (+ skeleton terms / evidence / manifest)
- `CDNL/` (+ skeleton terms / evidence / manifest)
- `ZONE/` (+ skeleton terms / evidence / manifest)
- `CMII/` (+ skeleton terms / evidence / manifest)
- `CHAR/` (+ skeleton terms / evidence / manifest)

## New candidates

| Ticker | Source | Form | CIK | Hint |
|--------|--------|------|-----|------|
| `VEEE` | sec_full_text | 8-K | 0001855509 | https://www.sec.gov/Archives/edgar/data/1855509/000173112226001330/ |
| `VTRS` | sec_full_text | 8-K | 0001792044 | https://www.sec.gov/Archives/edgar/data/1792044/000114036126039024/ |
| `PCRX` | sec_full_text | 8-K | 0001396814 | https://www.sec.gov/Archives/edgar/data/1396814/000110465926114571/ |
| `INSW` | sec_full_text | 8-K | 0001679049 | https://www.sec.gov/Archives/edgar/data/1679049/000110465926116371/ |
| `BMBL` | sec_full_text | 8-K | 0001830043 | https://www.sec.gov/Archives/edgar/data/1830043/000095010326015480/ |
| `CCC` | sec_full_text | 8-K | 0001818201 | https://www.sec.gov/Archives/edgar/data/1818201/000119312526422320/ |
| `SLN` | sec_full_text | 8-K | 0001479615 | https://www.sec.gov/Archives/edgar/data/1479615/000119312526424695/ |
| `OPCH` | sec_full_text | 8-K | 0001014739 | https://www.sec.gov/Archives/edgar/data/1014739/000110465926113904/ |
| `LEU` | sec_full_text | 8-K | 0001065059 | https://www.sec.gov/Archives/edgar/data/1065059/000162828026066212/ |
| `PAG` | sec_full_text | 8-K | 0001019849 | https://www.sec.gov/Archives/edgar/data/1019849/000114036126039664/ |
| `HSCS` | sec_full_text | DEFM14A | 0001468492 | https://www.sec.gov/Archives/edgar/data/1468492/000121390026110484/ |
| `LCII` | sec_full_text | DEFM14A | 0000763744 | https://www.sec.gov/Archives/edgar/data/763744/000076374426000091/ |
| `VREOF` | sec_full_text | S-4 | 0001771706 | https://www.sec.gov/Archives/edgar/data/1771706/000110465926115064/ |
| `DLX` | sec_full_text | 8-K/A | 0000027996 | https://www.sec.gov/Archives/edgar/data/27996/000002799626000129/ |
| `TARS` | sec_full_text | 8-K/A | 0001819790 | https://www.sec.gov/Archives/edgar/data/1819790/000181979026000069/ |
| `YYAI` | sec_full_text | 8-K/A | 0001674440 | https://www.sec.gov/Archives/edgar/data/1674440/000149315226047025/ |
| `CRON` | sec_full_text | 8-K | 0001656472 | https://www.sec.gov/Archives/edgar/data/1656472/000165647226000061/ |
| `RPM` | sec_full_text | 8-K | 0000110621 | https://www.sec.gov/Archives/edgar/data/110621/000119312526414916/ |
| `BEEM` | sec_full_text | 8-K | 0001398805 | https://www.sec.gov/Archives/edgar/data/1398805/000143774926032264/ |
| `CRGY` | sec_full_text | 8-K | 0001866175 | https://www.sec.gov/Archives/edgar/data/1866175/000186617526000138/ |
| `IONQ` | sec_full_text | 8-K | 0001824920 | https://www.sec.gov/Archives/edgar/data/1824920/000119312526419609/ |
| `CDNL` | sec_full_text | 8-K | 0002079999 | https://www.sec.gov/Archives/edgar/data/2079999/000119312526424737/ |
| `ZONE` | sec_full_text | 8-K | 0001956741 | https://www.sec.gov/Archives/edgar/data/1956741/000121390026109483/ |
| `CMII` | sec_full_text | S-4 | 0002088805 | https://www.sec.gov/Archives/edgar/data/2088805/000121390026107728/ |
| `CHAR` | sec_full_text | 8-K | 0002024459 | https://www.sec.gov/Archives/edgar/data/2024459/000121390026107409/ |

## Next actions

1. Confirm target vs acquirer (CIK resolve already preferred target).
2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.
3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).
4. Nightly sync will sleeve + surface on dashboard.

