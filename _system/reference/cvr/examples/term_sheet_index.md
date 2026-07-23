# CVR / contingent consideration — term sheet index

**Updated:** 2026-07-23  
**Confirmed operating model:** pre-close = opportunities; post-close = show universe claims.

## Operating model (locked)

| Book | Purpose | What we do |
|------|---------|------------|
| **Pre-close opportunities** | Find / size deals where contingent cash is still inside a listed stock | Screen → term sheet → deal + contingent IRR → buy limit / max loss → accumulate toward close |
| **Post-close universe** | Show CVRs already in SSI | Milestone calendar, efforts read, p_marvin, payout/expiry status. Trade only if listed; else claim inventory |

Registry: `_system/reference/cvr/cvr_universe.json`  
Dashboard: pinned sleeve filter **CVRs** (`cvr_all`) immediately after **All**.

## Plain English stages

| Stage | What you own | Trade contingent alone? | Sleeve role |
|-------|--------------|-------------------------|-------------|
| **Pre-close** | Target common still listed | No — buy/sell the stock | **Opportunity** |
| **Post-close, non-tradable** | Contractual claim | No | **Universe display / claim inventory** |
| **Post-close, tradable** | Listed CVR (OTC) | Yes | **Universe + optional secondary book** |

---

## Pre-close opportunities (active)

| ID | Vehicle | Contingent | Key date / catalyst | Terms |
|----|---------|------------|---------------------|-------|
| MFBP.CONTINGENT | **MFBP** | $6.73 (on top of $46.57 close cash) | ECIP redemption; close ~2026 Q4; Treasury apps after 2026-08-15 | `MFBP/research/` |

---

## Post-close universe (in SSI)

| ID | Tradeable | Max | Outside / key dates | Terms |
|----|-----------|-----|---------------------|-------|
| ABMD.CVR | No | $35.00 | Sales 2027–29; FDA by 2028-01-01; guidelines by 2029-12-31 | `ABMD.CVR/research/` |
| MRTX.CVR | No | $12.00 | MRTX1719 NDA acceptance by 2031-01-23 | `MRTX.CVR/research/` |
| PRVL.CVR | No | $4.00 (declining) | Marketing auth by 2028-12-01 | `PRVL.CVR/research/` |

---

## One-line economics

### Pre-close — MFBP (Optus)
$46.57 at close + $6.73 if ECIP preferred redeems. CEO color: requirements met; Treasury window opens 2026-08-15; ~10 + 30–90 days process. Opportunity = stock vs cash+contingent probability.

### Post-close — ABMD.CVR (JNJ)
Was $380 + CVR up to $35 (sales / FDA STEMI / Class I guidelines). Non-tradable. Budget-spend efforts on clinical tracks.

### Post-close — MRTX.CVR (BMY)
Was $58 + $12 on MRTX1719 NDA acceptance by 2031-01-23. Non-tradable.

### Post-close — PRVL.CVR (LLY)
Was $22.50 + up to $4 on first marketing auth by 2028-12-01; decays after 2024. Non-tradable.
