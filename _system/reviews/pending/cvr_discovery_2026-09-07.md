# CVR discovery — 2026-09-07

**UTC:** 2026-09-07T19:01:55Z  
**SEC ok:** True  
**SEC added:** 25  
**CSV/inbox / free-news added:** 25  
**Stubs created:** 25  
**Unhealthy streak:** False  

Context-tier candidates / stubs stay off the **CVRs** filter until `cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout or milestones.

Free auto feeds: SEC EFTS, Google News RSS, SEC Atom (no API keys).

## Stub folders created

- `PASG/` (+ skeleton terms / evidence / manifest)
- `AA/` (+ skeleton terms / evidence / manifest)
- `MKTX/` (+ skeleton terms / evidence / manifest)
- `FULC/` (+ skeleton terms / evidence / manifest)
- `PL/` (+ skeleton terms / evidence / manifest)
- `NOTE/` (+ skeleton terms / evidence / manifest)
- `RPC/` (+ skeleton terms / evidence / manifest)
- `APOG/` (+ skeleton terms / evidence / manifest)
- `HFFG/` (+ skeleton terms / evidence / manifest)
- `VRT/` (+ skeleton terms / evidence / manifest)
- `USAR/` (+ skeleton terms / evidence / manifest)
- `TVA/` (+ skeleton terms / evidence / manifest)
- `SOUL/` (+ skeleton terms / evidence / manifest)
- `NANO/` (+ skeleton terms / evidence / manifest)
- `LMB/` (+ skeleton terms / evidence / manifest)
- `PARR/` (+ skeleton terms / evidence / manifest)
- `RGS/` (+ skeleton terms / evidence / manifest)
- `XPON/` (+ skeleton terms / evidence / manifest)
- `CRAC/` (+ skeleton terms / evidence / manifest)
- `AWI/` (+ skeleton terms / evidence / manifest)
- `LTRX/` (+ skeleton terms / evidence / manifest)
- `PATH/` (+ skeleton terms / evidence / manifest)
- `GOLD/` (+ skeleton terms / evidence / manifest)
- `MGNX/` (+ skeleton terms / evidence / manifest)
- `PSA/` (+ skeleton terms / evidence / manifest)

## New candidates

| Ticker | Source | Form | CIK | Hint |
|--------|--------|------|-----|------|
| `PASG` | sec_full_text | 8-K | 0001787297 | https://www.sec.gov/Archives/edgar/data/1787297/000114036126035517/ |
| `AA` | sec_full_text | S-4 | 0001675149 | https://www.sec.gov/Archives/edgar/data/1675149/000119312526377619/ |
| `MKTX` | sec_full_text | PREM14A | 0001278021 | https://www.sec.gov/Archives/edgar/data/1278021/000119312526383841/ |
| `FULC` | sec_full_text | S-4 | 0001680581 | https://www.sec.gov/Archives/edgar/data/1680581/000119312526379106/ |
| `PL` | sec_full_text | 8-K | 0001836833 | https://www.sec.gov/Archives/edgar/data/1836833/000119312526381874/ |
| `NOTE` | sec_full_text | 8-K | 0001823466 | https://www.sec.gov/Archives/edgar/data/1823466/000119312526380190/ |
| `RPC` | sec_full_text | 8-K/A | 0001841968 | https://www.sec.gov/Archives/edgar/data/1841968/000119312526383128/ |
| `APOG` | sec_full_text | 8-K | 0000006845 | https://www.sec.gov/Archives/edgar/data/6845/000000684526000087/ |
| `HFFG` | sec_full_text | 8-K | 0001680873 | https://www.sec.gov/Archives/edgar/data/1680873/000121390026096950/ |
| `VRT` | sec_full_text | 8-K | 0001674101 | https://www.sec.gov/Archives/edgar/data/1674101/000119312526379306/ |
| `USAR` | sec_full_text | 8-K | 0001970622 | https://www.sec.gov/Archives/edgar/data/1970622/000121390026097399/ |
| `TVA` | sec_full_text | 8-K | 0002033991 | https://www.sec.gov/Archives/edgar/data/2033991/000110465926104858/ |
| `SOUL` | sec_full_text | 8-K | 0002025608 | https://www.sec.gov/Archives/edgar/data/2025608/000149315226041389/ |
| `NANO` | sec_full_text | S-4/A | 0002101833 | https://www.sec.gov/Archives/edgar/data/2101833/000110465926104734/ |
| `LMB` | sec_full_text | 8-K | 0001606163 | https://www.sec.gov/Archives/edgar/data/1606163/000162828026059713/ |
| `PARR` | sec_full_text | 8-K | 0000821483 | https://www.sec.gov/Archives/edgar/data/821483/000143774926028947/ |
| `RGS` | sec_full_text | 8-K | 0000716643 | https://www.sec.gov/Archives/edgar/data/716643/000071664326000029/ |
| `XPON` | sec_full_text | 8-K | 0001894954 | https://www.sec.gov/Archives/edgar/data/1894954/000190359626000317/ |
| `CRAC` | sec_full_text | 8-K | 0002070887 | https://www.sec.gov/Archives/edgar/data/2070887/000121390026094001/ |
| `AWI` | sec_full_text | 8-K | 0000007431 | https://www.sec.gov/Archives/edgar/data/7431/000119312526377194/ |
| `LTRX` | sec_full_text | 8-K | 0001114925 | https://www.sec.gov/Archives/edgar/data/1114925/000168316826006732/ |
| `PATH` | sec_full_text | 8-K | 0001734722 | https://www.sec.gov/Archives/edgar/data/1734722/000173472226000047/ |
| `GOLD` | sec_full_text | 8-K | 0001591588 | https://www.sec.gov/Archives/edgar/data/1591588/000119312526380542/ |
| `MGNX` | sec_full_text | 8-K/A | 0001125345 | https://www.sec.gov/Archives/edgar/data/1125345/000112534526000059/ |
| `PSA` | sec_full_text | 8-K | 0001393311 | https://www.sec.gov/Archives/edgar/data/1393311/000119312526377690/ |

## Next actions

1. Confirm target vs acquirer (CIK resolve already preferred target).
2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.
3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).
4. Nightly sync will sleeve + surface on dashboard.

