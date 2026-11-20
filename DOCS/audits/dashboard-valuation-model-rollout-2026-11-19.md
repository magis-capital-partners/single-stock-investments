# Stock valuation worksheet rollout — 2026-11-19

Every active stock has an editable research valuation worksheet in its Valuation
tab, with bear/base/bull assumptions, scenario present values, annual IRRs, dated
shareholder cash flows, graphs and source references. The Summary tab includes
the base research scenario. Inputs and recorded issuer valuations remain dated
and separately labelled.

## Coverage and authority

- **985 unique stocks** after consolidating the duplicate historical SATS entry
  into the existing ECHO entry, as requested by the user. Former SATS research
  links open ECHO. Its historical company library remains available as a labelled
  archive; ambiguous or different-issuer matches are excluded.
- **774 worksheets calculate all three IRRs**: **2,322 case IRRs** reconcile to
  their dated cash-flow schedules. **211 worksheets identify missing inputs or
  unresolved quote/share/claim requirements** instead of inventing returns.
- **5,910 tab renders** pass across the active universe.
- Research worksheets have `authority: screening_only` and
  `capital_actionable: false`. Canonical underwriting and capital-eligibility
  gates retain their authority. A worksheet does not promote a stock's status.

## Economic treatment

Operating-company sensitivities use sourced annual FCF per share where available,
with additional reinvestment reducing distributions. Earnings, common-equity,
asset-value, transition and dated-payoff worksheets serve other company types.
Recent bank/broker balance-sheet evidence overrides missing industry metadata;
customer balances and bank operating cash flow are excluded from owner-cash models.

Valid issuer cash-flow forecasts take precedence over generated sensitivities.
Their original dates are preserved. IRR solves the dated purchase/distribution/sale
equation; present-value upside is never annualized into an IRR. Terminal equity
values do not receive a second cash/debt addition. Preferred capital, native
reporting currency, dated FX and corporate-action basis are disclosed where used.
Debt, CVRs and private claims require their own terms and unit of account.

Starting scenario ranges are explicit research assumptions. Users can edit them
and inspect the resulting cash flows. Edits remain in the current view and do not
write approved models or investment decisions. Historical anchor tables expose
the reported cash flow, capital expenditure, equity and share-count operands.

## Source corrections

The source refresh uses SEC company facts and the current SEC ticker registry,
with identified vendor annual observations and dated spot FX for additional
listings. Issuer/claim mismatches fail closed. In particular:

- HE uses parent-company financials (CIK 354707), replacing cached utility-
  subsidiary facts (CIK 46207); prior valuation marks are withheld.
- XOM's predecessor/successor annual and quarterly facts retain their original
  sources, with the primary filing's one-for-one share-exchange bridge.
- EchoStar research follows ECHO (CIK 1415404); Strive preferred shares now using
  SATS are not treated as the historical EchoStar common-share claim.

## Storage and verification

The model payload is kept in authenticated private storage. Git contains an
**89-byte structural stub**, its checksum receipt and public ticker-alias metadata.
The payload is uploaded immutably and read back before the receipt is changed.

The builder enforces an **8 MiB private-input limit**. Publication continues to
enforce the **6,000,000-byte startup-core budget** and **20 MiB per hosting asset**;
no size limit has been relaxed. Stock details load separately from the core.
The verified private model input is **4,495,950 bytes**.

Local staging measurements (the local library contains only pilot-library fixtures;
these are not measurements of the complete production source library):

- Core: **5,895,637 bytes**.
- Largest stock detail before the anchor-table metadata: **1,877,111 bytes**.
- Largest staged data asset: **7,801,191 bytes**.

Validation includes model/IRR reconciliation, all-stock rendering, financial-period
and currency handling, claim isolation, alias navigation, source safety, private
storage and publication guards. The final focused suite passed **232 tests and
three subtests**, including anchor-table assertions and special-claim templates.
Desktop/mobile browser checks
verified recalculation/reset, sourced values, bank routing and SATS-to-ECHO navigation.

The normal authenticated Cloudflare publication validates the complete source
library and its asset sizes before uploading the site.
