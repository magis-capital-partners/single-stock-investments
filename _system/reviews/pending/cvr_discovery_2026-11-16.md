# CVR discovery — 2026-11-16

**UTC:** 2026-11-16T23:53:34Z  
**SEC ok:** True  
**SEC added:** 1  
**CSV/inbox / free-news added:** 1  
**Stubs created:** 1  
**Unhealthy streak:** False  

Context-tier candidates / stubs stay off the **CVRs** filter until `cvr_terms.json` has `stub=false` and `terms_complete=true` with max payout or milestones.

Free auto feeds: SEC EFTS, Google News RSS, SEC Atom (no API keys).

## Stub folders created

- `CMCAF/` (+ skeleton terms / evidence / manifest)

## New candidates

| Ticker | Source | Form | CIK | Hint |
|--------|--------|------|-----|------|
| `CMCAF` | sec_full_text | DEFM14A | 0001865248 | https://www.sec.gov/Archives/edgar/data/1865248/000147793226006925/ |

## Next actions

1. Confirm target vs acquirer (CIK resolve already preferred target).
2. Pull merger exhibit / CVR agreement into ticker `investor-documents/sec/`.
3. Complete `cvr_terms.json` (`stub=false`, `terms_complete=true`).
4. Nightly sync will sleeve + surface on dashboard.

