# Proposal: Closed-end fund / ETF discount-to-NAV sleeve

**Status:** implemented (sleeve + overlay + pilots) — human still gates recovery probabilities  
**Date:** 2026-07-20  
**Pilots:** CEE, URB.A.TO (Urbana Class A), PSH (Pershing Square Holdings)  
**Sources:** DWS product page; `CEE-PH3.pdf`; Urbana / PSH IR; Marvin workflow (`decision_stack`, `optionality_valuation`, `option_treatment`, `onboard_fund_nav_sleeve.py`)

---

## 1. Why this exists

Closed-end funds (CEFs) and a small subset of ETFs can trade away from economic ownership value for reasons the standard operating-company pipeline does not model well:

1. **Market-structure discount / premium** — price vs *reported* NAV (classic CEF).
2. **Accounting / Level-3 understatement** — reported NAV itself embeds forced zeros or stale marks (CEE Russian holdings at $0 since 2022-03-14 despite material share counts and historical cost).
3. **Stuck / non-redeemable sleeves** — creation/redemption cannot clear the mispricing (rare for plain ETFs; common for CEFs and for ETFs with sanctioned or illiquid legs).

CEE is the motivating example of (2), not a fat classic discount on reported NAV. As of recent market data the fund has often traded near NAV or even at a premium; the research edge is whether *economic* NAV (liquid CEE book + risked Russia recovery) exceeds price after expenses, sanctions, and expropriation risk.

`NAN` (Nuveen NY muni CEF) is already in `registry.json` as a stub with `payoff_lens: pending`. It is the natural contrast pilot for pure (1).

---

## 2. Design principle (framework governance)

Per `framework_governance.md`: **do not** invent a parallel research religion.

| Prefer | Avoid |
|--------|--------|
| Extend `optionality_valuation.md` with overlay **D. Fund / CEF look-through** | New mega-file `cef_valuation.md` unless governance checklist fails |
| Reuse `payoff_lens: asset` (+ `event` when catalyst is dated) | New payoff lens |
| Reuse archetype `holding_co` or `optionality` | New Stahl archetype |
| Reuse `holding_company_or_fund` component template | Duplicate SOTP schemas |
| New `valuation.json` keys + script handlers | Chat-only NAV math |
| Instrument tag in registry | Treating CEFs as operating compounders with Lawrence `full` FCF |

New file only if lint/script enforcement cannot live in existing docs: optional thin `fund_nav_discount.md` *as a section stub that redirects*, or keep everything inside optionality + classification trigger map.

---

## 3. Idea taxonomy (what we will and will not hunt)

### In scope

| Class | Mechanism | Examples | Primary edge |
|-------|-----------|----------|--------------|
| **A. Classic CEF discount** | Price ≪ reported NAV; tender/rights/activist/repurchase can close gap | Equity/muni/credit CEFs (`NAN` type) | Discount magnitude + governance catalyst |
| **B. Shadow NAV / zero-marked sleeve** | Reported NAV omits or zeros material assets | `CEE` Russia book | Probability-weighted recovery + liquid book floor |
| **C. Hard-to-arb ETF** | Creation/redemption broken or sleeve illiquid | Sanctioned-country ETFs, some single-country / commodity wrappers | Same as B; rarer |
| **D. Holdco-like listed fund** | Permanent capital vehicle with opaque marks | Adjacent to FRMO-style holdco work | Already covered by holdco SOTP; tag as fund only if regulated CEF/ETF |

### Out of scope (or separate sleeve)

- Levered / inverse / YieldBOOST decay products → stay in `_external/etf-dashboard` Darwin/borrow workflow.
- Plain index ETFs trading within a few bps of NAV → no research edge.
- “Buy any CEF at 5% discount” screens without catalyst or shadow-NAV thesis → idea funnel reject.

### Inefficiency labels (Q5)

Add to special-situation / MOI vocabulary (prose + optional `predictive_attribute`):

- `cef_market_structure_discount`
- `level3_or_sanction_zero_mark` (CEE)
- `forced_seller_or_retail_flow` (distribution / tax / country fear)
- `tender_or_repurchase_catalyst`

---

## 4. Decision-stack mapping

| Q | CEF / discount fund answer |
|---|----------------------------|
| **1 What is it?** | Regulated portfolio wrapper; look-through holdings + fees + leverage + distribution policy. Archetype: `holding_co` (look-through) or `optionality` when zero-marked sleeve dominates. |
| **2 Will it last?** | Moat is usually `n/a` or `unproven` at the *fund* level; durability lives in underlying holdings and in sponsor/board capital-return policy. |
| **3 Bear bounded?** | Floor = liquid look-through NAV minus leverage/expenses/liquidation friction; **never** treat zero-marked Russia as floor *or* as free lunch without explicit P. |
| **4 Return at price?** | Not Lawrence `full` on fund FCF. Use `scenario` and/or `yield_curve` on (a) discount close, (b) liquid NAV drift, (c) risked recovery. |
| **5 Why mispriced?** | Name class A/B/C + catalyst (repurchase, tender, sanction path, activist). |
| **6 What do we do?** | Stance from optionality table; size for option when recovery is the thesis. |

**Payoff lens default**

- Class A → `asset` (NAV discount).
- Class B → `asset` + optional secondary `event` note if a dated legal/policy path exists (do not force dual lenses in JSON; keep one `payoff_lens` and put dated path in catalyst prose / yield curve).
- Class C → same as B.

---

## 5. Valuation model (CEE-shaped, generalizable)

### 5.1 Three NAVs (never average silently)

| View | Definition | Decision use |
|------|------------|--------------|
| **Reported NAV** | Sponsor/SEC NAV per share | Market discount/premium; repurchase trigger |
| **Liquid economic NAV** | Look-through mark of freely transferable holdings + cash − liabilities − fees reserve | Dhando floor |
| **Complete economic NAV** | Liquid NAV + risked value of zero-marked / Level-3 / stuck sleeves | Overlay base / bull; stance only with human OK on P |

Separated-views rule from `optionality_valuation.md` applies: liquid floor and complete (risked) value are **separate decision views**.

### 5.2 CEE worked structure (from `CEE-PH3.pdf`)

As of 2025-07-31 (unaudited schedule):

- Poland / Hungary / other liquid book: marked in Level 1.
- Russia: Sberbank, PhosAgro, Fix Price, Magnit, Alrosa, Nornickel, MMK, Polyus, Gazprom, Lukoil, Tatneft, etc. at **$0** (Level 3); footnote (a) significant unobservable inputs.
- Russia **cost** disclosed: **$30,722,586** against net assets **~$99.99M** (~31% of then-NAV at cost — cost is not fair value).
- Sanctions / Central Bank freeze narrative in the same PDF; remaining local shares / sanctioned DRs still stuck after some private DR sales (later N-CSR / press).

**Component schedule** (template `holding_company_or_fund`):

1. Look-through listed non-Russia equities (market).
2. Cash / cash equivalents / securities-lending collateral (net of loaned securities).
3. Other assets and liabilities, net.
4. **Russia sleeve (dormant)** — `option_treatment: probability_weighted` or `zero` with explicit rationale; never silent zero.
5. Structural drag — expense ratio, any leverage, distribution tax friction.
6. Wrapper discount/premium — market price vs reported NAV (Class A layer).

### 5.3 Proposed `valuation.json` keys

```json
{
  "valuation_mode": "optionality",
  "method": "scenario",
  "instrument_type": "closed_end_fund",
  "classification_inputs": {
    "archetype": "holding_co",
    "payoff_lens": "asset",
    "moat": "n/a",
    "dhando": "partial"
  },
  "optionality_gate": {
    "framework": "fund_lookthrough_nav",
    "floor_pass": true,
    "floor_metric": "liquid_nav_per_share",
    "floor_value": null,
    "primary_metric": "complete_nav_discount_to_price",
    "notes": "Stance gate on liquid NAV; Russia sleeve is overlay only until human sets P_base"
  },
  "fund_nav_overlay": {
    "as_of": "YYYY-MM-DD",
    "shares_outstanding": null,
    "market_price": null,
    "reported_nav": null,
    "discount_to_reported_nav_pct": null,
    "expense_ratio_net": null,
    "leverage_pct": null,
    "liquid_nav_per_share": null,
    "complete_nav_per_share_base": null,
    "zero_marked_sleeves": [
      {
        "id": "russia_equity_sleeve",
        "label": "Russian securities marked at zero",
        "option_treatment": "probability_weighted",
        "cost_basis_total": 30722586,
        "reported_value": 0,
        "proxy_gross_value_base": null,
        "realization_probability_base": null,
        "years_to_realization_base": null,
        "friction_haircut_pct": null,
        "evidence": "CEE-PH3.pdf; N-CSR footnotes; sanctions narrative",
        "human_review": true
      }
    ],
    "evidence_refresh": {
      "type": "fund_nav",
      "sources": ["sponsor_nav", "sec_nport", "sec_ncsr", "market_price"]
    }
  },
  "component_valuation": {
    "version": "1.0",
    "template": "holding_company_or_fund",
    "all_material_components_identified": true,
    "components": []
  }
}
```

**Hard rules**

- Base IRR / base complete NAV may include a non-zero Russia sleeve **only** after `[HUMAN REVIEW]` sets `realization_probability_base` (and proxy mark method).
- Until then: `option_treatment: zero` in base, wide bull sensitivity, and Milly flags any narrative that smuggles recovery into “cheap vs NAV.”
- Discount magnitude reported as **% of price** and **% of liquid / complete NAV** (MOI Ch 3 rule already in optionality doc).

### 5.4 IRR arithmetic pattern (report end)

1. Price today.
2. Reported NAV and discount/premium.
3. Liquid look-through NAV (show work from holdings + cash − liabilities).
4. Risked sleeve PV (P × proxy mark × ownership − friction), or explicit $0.
5. Complete NAV = liquid + risked sleeves − structural drag.
6. Scenario returns: (bear) liquid NAV fades / discount widens; (base) liquid NAV path + partial recovery or discount close; (bull) higher P or tender.
7. **Returns statement** matches executive summary one number.

---

## 6. Workflow integration (end-to-end)

Matches current automation in `onboard_research_automation.md`.

```text
Discover → Onboard → Download (N-CSR/N-PORT/IR) → Evidence build
  → Cross-check → Deep dive (asset/optionality) → marvin_cloud_refresh
  → Milly → Human review → Stance / sleeve membership
```

### 6.1 Discover / idea funnel

Add a **Fund discount** branch to `idea_funnel.md` (section only):

1. Screen CEFConnect / sponsor lists / SEC N-PORT universe for discount **or** known zero-marked geographies.
2. Reject if discount thin **and** no shadow sleeve **and** no capital-return catalyst.
3. Tag candidate class A/B/C before onboard.
4. Clone check: activist 13D on CEFs, tender history, repurchase authorizations (CEE has recurring repurchase when at discount).

Optional later: small screener script `screen_cef_discounts.py` writing `_system/portfolio/fund_discount_watchlist.json` — **phase 2**, after pilot valuation schema is stable.

### 6.2 Onboard

Extend `onboard_ticker.py` / registry schema:

| Field | Values |
|-------|--------|
| `instrument_type` | `operating_company` (default), `closed_end_fund`, `etf`, `royalty_trust`, … |
| `download.type` | keep `us_shared` for US CEFs; add form allow-list |

Scaffold same ticker folder layout as equities (`README`, `investor-documents/`, `research/`).  
Classification defaults: `archetype: holding_co`, `payoff_lens: asset`, `investment_sleeve: fund_nav_discounts` (new sleeve).

**Pilot onboard order:** `CEE` first (Class B), then finish `NAN` (Class A) to prove both paths.

### 6.3 Download / evidence

US CEF/ETF primary set (EDGAR + sponsor IR):

| Form / doc | Use |
|------------|-----|
| **N-CSR / N-CSRS** | Annual/semi financials, Russia/sanctions footnotes, expense ratio |
| **N-PORT** | Monthly holdings detail (when available) |
| **N-CEN** | Census / service providers |
| **DEF 14A** | Board, repurchase/tender authority |
| **8-K / press** | Tender, repurchase extension, Russia update |
| Sponsor factsheet / schedule PDF | e.g. DWS `CEE-PH3.pdf` |

Wire into existing `download_us_investor_docs.py` allow-list (today optimized for 10-K/10-Q issuers).  
`build_filing_evidence.py`: add fund digest sections — holdings concentration, zero-mark footnotes, leverage, distribution.

Copy user-provided PDFs into `{TICKER}/investor-documents/` and log in `_download_log.txt` (CEE-PH3 already in Downloads).

### 6.4 Cross-check

Same `scan_third_party_sources.py` + `cross_check_third_party_*.md` path.  
Approved third parties only in base IRR. CEFConnect / Morningstar discount stats are **market data**, not narrative authorities — cite as inputs with as-of dates; do not treat as thesis approval.

### 6.5 Research / deep dive

Report order unchanged (`deep_dive_structure.md`). Content shifts:

- **What this business is** → what the *fund* owns and how the wrapper works (≤5 sentences).
- **Business & moat** → look-through mechanics + option scan (Russia sleeve row mandatory for CEE).
- **No** operating Hohn IRR theater for the fund itself.
- **Valuation & IRR** last with `fund_nav_overlay` ledger.

Archetype prose: extend `archetype_valuation_prose.md` `holding_co` with a short “regulated fund” subsection (lead metric = liquid vs complete NAV).

### 6.6 Mechanical refresh

Extend `evidence_refresh.type: fund_nav` inside cloud refresh:

1. Pull latest market price + sponsor/reported NAV (Polygon/Yahoo + IR or CEFConnect-style feed — **choose one durable source**, document in script).
2. Recompute discount to reported NAV.
3. Do **not** auto-update `realization_probability_base`.
4. Flag stale holdings if N-PORT/N-CSR older than threshold (e.g. 120 days) → `[HUMAN REVIEW]`.
5. `marvin_cloud_refresh.py TICKER --date YYYY-MM-DD` remains the only mechanical close.

### 6.7 Milly / lint / committee

Milly checklist additions for fund dives:

- Did the dive conflate reported NAV discount with shadow-NAV upside?
- Is any non-zero recovery P sourced, or smuggled?
- Are expense ratio and share count current?
- Lens failure mode present (value trap: discount persists; sanctions permanent; expropriation).

Lint: classification footer; assumption ledger; ban-list prose; `fund_nav_overlay` present when `instrument_type` is CEF/ETF.

### 6.8 Portfolio / dashboard

| Change | Detail |
|--------|--------|
| Sleeve | Add `fund_nav_discounts` to `investment_sleeves.json` |
| Registry | `instrument_type` + IR roots (DWS CEE URL for pilot) |
| Dashboard | Optional columns: reported discount %, liquid NAV / price, shadow sleeve flag |
| Darwin / etf-dashboard | No merge of decay/borrow products into this sleeve |

---

## 7. CEE pilot plan (concrete next steps)

### Phase 0 — Agree gates (human)

1. Approve this proposal direction (extend optionality vs new framework file).
2. Agree that **base case Russia P = 0** until human sets P; bull only in sensitivity.
3. Confirm sleeve name and that CEFs are allowed in taxable/IRA mandates (liquidity, K-1 rare for CEE — still check).

### Phase 1 — Scaffold + evidence (deterministic)

1. Onboard `CEE` via existing onboard path + DWS IR root.  
2. Ingest `CEE-PH3.pdf` into `CEE/investor-documents/`.  
3. Pull latest N-CSR / N-PORT / repurchase 8-K.  
4. Build filing digest; write `research/evidence/` fund-oriented summary.  
5. Draft `valuation.json` with `fund_nav_overlay` and Russia sleeve `human_review: true`.

### Phase 2 — Narrative + adversarial

1. Deep dive v2 following report prose rules.  
2. `marvin_cloud_refresh.py CEE --date 2026-07-20` (or run date).  
3. Milly `adversarial_*.md`; fix factual errors.  
4. Pending review card in `_system/reviews/pending/`.

### Phase 3 — Generalize

1. Document overlay **D** in `optionality_valuation.md` + trigger row in `classification.md`.  
2. Extend download allow-list + `fetch_market_inputs` for `fund_nav`.  
3. Finish `NAN` as Class A template.  
4. Optional screener + watchlist (only after two clean pilots).  
5. Architecture review checkbox per `architecture_review_template.md` if a standalone framework file is still wanted.

---

## 8. Risk register (CEE-specific, generalizable)

| Risk | Why it kills the thesis |
|------|-------------------------|
| Permanent sanctions / capital controls | Recovery P → 0; option expires worthless |
| Expropriation / forced local sale | Share count exists only on paper |
| Private sale clearance far below proxy marks | Bull NAV overstated |
| Expense drag + wide bid/ask | Thin discount never compounds |
| Premium to reported NAV | Class A edge absent; only Class B remains |
| Double counting | Adding Russia cost basis as if it were NAV |
| Country ETF alternative | Cheaper liquid Poland/Hungary beta without wrapper fees |

**Lens failure mode (required in Risks):** “Discount or zero-mark never closes; patient capital earns expense ratio for nothing.”

---

## 9. Explicit non-goals

- Building a second etf-dashboard inside SSI.
- Auto-promoting CEFs to `core` on screen output.
- Using Russian local exchange prints as Level-1 marks for US-held frozen shares without legal path.
- Editing `MEMORY.md` with CEE beliefs before human promotion.

---

## 10. Success criteria

1. `CEE` folder has primary PDFs, `valuation.json` with three-NAV views, and a lint-clean deep dive.  
2. Russia sleeve cannot enter base complete NAV without human P.  
3. `NAN` demonstrates Class A path with same schema (zero-marked sleeve empty).  
4. Cloud refresh updates price/reported NAV without rewriting recovery assumptions.  
5. Dashboard can filter `fund_nav_discounts` sleeve.  
6. No new framework file unless governance review says extension is insufficient.

---

## 11. Open questions for human

1. **Base recovery policy:** keep Russia at $0 in base forever until a tradable path exists, or allow a tiny P (e.g. 5–10%) in base?  
2. **Proxy mark method for Russia:** last pre-freeze market, local MICEX-derived, sector multiples, or cost×haircut only in bull?  
3. **Universe ambition:** opportunistic pilots only, or build a recurring CEF screen?  
4. **Mandate fit:** taxable only vs IRA-ok; max position size for illiquid CEFs.  
5. **Sibling funds:** EEA / GF (same DWS complex, repurchase programs) — research as peer set or ignore until CEE done?

---

## 12. Recommended decision

**Proceed with Phase 0–2 on CEE as Class B pilot**, schema as `fund_nav_overlay` under existing optionality / `holding_company_or_fund` machinery, base Russia = explicit zero pending human P. Generalize download + sleeve only after CEE deep dive survives Milly.

---

## 13. Agent learning (post-CEE rewrite, 2026-07-20)

Failure: first CEE dive treated a thin reported-NAV discount as the thesis and buried Russia.

**Rules / enforcement now in tree:**

| Layer | Path |
|-------|------|
| Normative | `optionality_valuation.md` § D mandatory narrative; `option_treatment.md` row 1b + anti-patterns; `report_prose.md` Q5 note |
| Trigger map | `classification.md` → fund_nav_overlay opens § D + lint |
| Arsenal | `analysis_arsenal.md` shadow row |
| Cursor | `.cursor/rules/fund-nav-discounts.mdc` |
| Prompt | `deep_dive_template.md` Q5 fund note |
| Adversarial | `MILLY.md` check 10b + option coverage row |
| Mechanical | `lint_deep_dive.py` → `lint_shadow_fund_nav()` errors if Q5/exec bury zero mark |
