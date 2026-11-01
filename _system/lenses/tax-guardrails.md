# Desk lens: tax-asset guardrails (NOL and Tax Assets)
Written 2026-10-29 by the NOL and Tax Assets desk. Scope: what any desk may say about NOLs, deferred tax assets (DTAs), valuation allowances (VA) and Section 382. It never decides whether to buy a stock and never puts a value on a tax asset. Graded by the desk test set at /workspace/shared/magis/nol_eval/test_set.json (24 cases) in the Friday 4 PM ET weekly review.

## 1. The lens
- An NOL can only shelter earnings the business makes; it is never the reason to buy.
- A DTA is a claim on future tax savings, not cash. It never goes into net cash, EV or liquidity.
- No present value of NOLs and no control premium for them.
- A Section 382 dollar limit exists in our work only if a filing states it, with the accession.
- A full VA is management saying it does not expect to use the losses soon; that is a negative signal.
- A 5% holder filing is an input to the 3-year 50-point owner-shift test, not an ownership change by itself.

## 2. Rules (decision tests)
| ID | Test (one line, answerable yes/no or with a number) | Source (document, date, page or accession) | Proven wrong if | Score (fired / right / wrong / mixed) | Cases |
|---|---|---|---|---|---|
| TAX-01 | Is the NOL the reason for the call? Yes → stop; rank the business first. | Desk rule (Drew, Oct 2026); 26 U.S.C. §172 80% cap | a name bought mainly for its NOL beats SPY over 3 yrs in most graded cases | untested | NOL-buy-thesis |
| TAX-02 | Is any DTA counted as cash, net cash or EV? Yes → remove it. | Desk rule; VNDA Q3 2026 10-Q 0001347178-26-000002 | — (definitional guardrail; retire only if Drew changes the rule) | untested | VNDA-DTA-cash |
| TAX-03 | Does every cited 382 limit carry a filing accession that states the dollar amount? No → write "limit not stated". | 26 U.S.C. §382; REI FY25 10-K 0001384195-26-000050; VNDA FY25 10-K 0001628280-26-007460 | a filing later shows the desk's "not stated" answer missed a stated limit in a document it read | untested | REI-382-limit, VNDA-382-limit, REI-382-change, VNDA-382-change, SIRI-382, NWL-382 |
| TAX-04 | Is the VA full? Yes → treat the losses as not expected to be used; flag, don't add. | VNDA Q3 2026 10-Q 0001347178-26-000002 | full-VA names release the VA within 4 quarters in most graded cases | untested | VNDA-VA-Q3 |
| TAX-05 | Is a 13G/13D or Form 4 being called an ownership change? Yes → relabel as a test input [I]. | 26 U.S.C. §382(g); WYY 0000906304-26-000187; VNDA 0002052113-26-001132; REI 0002012383-26-003839 | — (definitional; a stated ownership change in a later filing is a new fact, not a rule failure) | untested | WYY-13G-382, NWL-Form4-382, WYY-13G-Royce, VNDA-13G-BlackRock, REI-13G-BlackRock |
| TAX-06 | Is a rights-plan trigger quoted from the filing that states it (10-K or proxy), with its effect labeled inference? | TTI FY25 10-K 0000844965-26-000015 Note 15 p. F-35 (4.99%); plan-amendment vote 8-K 0000844965-26-000042 | — (citation rule) | untested | TTI-rights-plan, SIRI-rights-plan, REI-rights-plan |
| TAX-07 | Is a screener tax field implausible (e.g. VA > 100% of DTA) or a source stale/unresolvable? Yes → report it as a data error, don't use it. | nol_screener.json (BIIB VA 283%); nol_382_facts.json generated 2026-08-12 | flagged fields turn out correct on checking the filing | untested | BIIB-VA-283, stale-382-file, REN-cik, FUBO-lead |
| TAX-08 | Is each tax claim labeled fact [F] or inference [I], with filing numbers as [F] and owner-shift or COD effects as [I]? | Desk rule | — (labeling rule) | untested | HTZ-COD, SIRI-Q3-tax, VNDA-Q3-loss |

## 3. Quick screen
- TAX-01/02: the call's one_number and evidence fields in the desk brief.
- TAX-03/05: nol_382_facts.json (accession per row once rebuilt), 10-K income-tax note, 13G/13D list on EDGAR.
- TAX-04: latest 10-Q/10-K income-tax note; nol_screener.json VA field.
- TAX-06: 8-K Item 3.03/1.01 for rights plans.
- TAX-07: nol_screener.json fields vs the filing; _envelope.generated_at.

## 4. Failure modes and falsifiers
- None graded yet. First scoring: Fri 2026-10-30, 4 PM ET weekly review. Known risks: stale 382 facts file (generated 2026-08-12); screener VA field errors (BIIB).

## 5. Sources and evidence
- [F] 26 U.S.C. §382: ownership change = more than a 50-point increase by 5% shareholders over a 3-year testing period. §172: post-2017 NOLs carried forward indefinitely, capped at 80% of taxable income.
- [F] Accessions as listed in §2 and in nol_eval/test_set.json.
- Current desk status (Oct 29 2026 screener built 09:19Z): actionable SIRI, WYY, NWL; blocked by prior ownership change REI, VNDA; full VA VNDA.

## 6. Change log
- 2026-10-29: written as a guardrail lens; same day restructured into LENS_FORMAT.md (rules TAX-01 to TAX-08, all untested), reason: shared format and scoring. Mirrored in CHANGELOG.md.
