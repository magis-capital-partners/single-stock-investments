# Third-plus reverse splits: signal study

Built 2026-10-24T03:10:33.254Z. Prices through 2026-10-12. Research only; no production authority.

## Result

No rule met every preregistered evidence and risk gate. The report identifies exploratory differences without calling them an optimal live strategy.

The primary comparison uses a $1 million reference NAV, 20 sessions, 1% recorded share-volume/ADV participation, strict restricted/unknown SSR exclusion and conditional historical prices. The $25,000 target is reduced by the declared capital and volume constraints; it is not a promise of $25,000 fills. Ten sessions is the replication. Same issuer history, whole-share sizing, persistent loan/share liabilities and fee/carry mechanics are reused. Independently verified borrow entries remain zero.

## Source and feature coverage

All 210 candidate events are counted here; portfolio maturity, price, restriction and risk exclusions occur later.

| Feature | Pass | Fail | Unknown |
| --- | --- | --- | --- |
| score60 | 56 | 80 | 74 |
| S1 | 13 | 28 | 169 |
| S2 | 0 | 0 | 210 |
| S3 | 77 | 113 | 20 |
| S4 | 17 | 4 | 189 |
| S5 | 55 | 153 | 2 |
| S6 | 154 | 47 | 9 |
| S7 | 190 | 12 | 8 |
| reported_runway | 98 | 61 | 51 |

Independent financing reviews: 0. Cached financing documents audited: 149; those with completion-language leads: 89. Leads, provider flags, signatures and semantic classification do not establish independently reconciled share issuance or cash proceeds. S2-dependent rules remain insufficient while those reviews are absent.

S1 uses unrestricted cash and a matched annual or annual-plus-YTD TTM operating cash-flow construction. Known unresolved financing and provider financing flags block pro forma cash selection. Its remaining estimates are conditional on incomplete cache coverage; an undiscovered transaction could change them. S4 requires comparable same-filing period-end common shares, with a source clause when actions cross the measurement window. It never substitutes EPS weighted-average shares.

## Primary rule comparison

The covered baseline has exactly the input availability needed for that rule. Compare both incremental columns: total profit can change merely because a feature is missing for some issuers. Intervals resample issuer-level differences and six-month calendar blocks of this already explored history. Holm adjusts the 11 new primary claims; these are development diagnostics, not a fresh confirmatory experiment.

| Rule | Trades / issuers | Net P&L | Delta vs all | Delta vs covered | Worst drawdown | Monthly mean | Holm p | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 41 / 33 | -$16,386 | $0 | $0 | -$25,417 | -$356 | — | reference |
| score60 | 17 / 15 | -$1,404 | $14,982 | $15,578 | -$5,151 | -$31 | — | reference |
| S1 | 3 / 3 | $89 | $16,475 | $21,630 | -$48 | $2 | 1.000 | insufficient_evidence |
| S2 | 0 / 0 | $0 | $16,386 | $0 | $0 | $0 | 1.000 | insufficient_evidence |
| S3 | 29 / 22 | -$14,926 | $1,460 | $2,250 | -$28,012 | -$324 | 1.000 | insufficient_evidence |
| S4 | 6 / 6 | $1,319 | $17,705 | $738 | -$981 | $29 | 1.000 | insufficient_evidence |
| S5 | 10 / 10 | $1,832 | $18,218 | $18,218 | -$2,150 | $40 | 1.000 | insufficient_evidence |
| S6 | 34 / 27 | -$21,032 | -$4,646 | -$4,646 | -$25,287 | -$457 | 1.000 | insufficient_evidence |
| S7 | 41 / 33 | $7,385 | $23,771 | $23,771 | -$2,419 | $161 | 1.000 | rejected |
| C1 | 0 / 0 | $0 | $16,386 | $0 | $0 | $0 | 1.000 | insufficient_evidence |
| C2 | 0 / 0 | $0 | $16,386 | $0 | $0 | $0 | 1.000 | insufficient_evidence |
| C3 | 0 / 0 | $0 | $16,386 | $0 | $0 | $0 | 1.000 | insufficient_evidence |
| C4 | 10 / 10 | $1,832 | $18,218 | $18,218 | -$2,150 | $40 | 1.000 | insufficient_evidence |

| Rule | Issuer interval: incremental total | Calendar-block interval: incremental total | Open positions / liability | Main gate failures |
| --- | --- | --- | --- | --- |
| baseline | $0 to $0 | $0 to $0 | 2 / $74 | — |
| score60 | -$17,901 to $71,043 | -$10,028 to $57,697 | 1 / $61 | — |
| S1 | -$15,496 to $70,285 | -$10,454 to $62,790 | 0 / $0 | fewer_than_30_issuers, increment_uncertain, family_adjusted_evidence_insufficient, concentrated_or_nonpositive_profit |
| S2 | -$15,469 to $70,354 | -$10,613 to $62,713 | 0 / $0 | fewer_than_30_issuers, no_incremental_covered_universe_profit, increment_uncertain, family_adjusted_evidence_insufficient, concentrated_or_nonpositive_profit |
| S3 | -$2,823 to $6,811 | -$4,137 to $7,545 | 0 / $0 | fewer_than_30_issuers, increment_uncertain, family_adjusted_evidence_insufficient, worse_drawdown, concentrated_or_nonpositive_profit |
| S4 | -$14,523 to $71,104 | -$9,418 to $65,237 | 1 / $61 | fewer_than_30_issuers, increment_uncertain, family_adjusted_evidence_insufficient, concentrated_or_nonpositive_profit, unresolved_obligations |
| S5 | -$13,435 to $70,779 | -$8,844 to $65,961 | 1 / $30 | fewer_than_30_issuers, increment_uncertain, family_adjusted_evidence_insufficient, unresolved_obligations |
| S6 | -$13,398 to $1,039 | -$10,371 to $499 | 2 / $43 | fewer_than_30_issuers, no_incremental_full_universe_profit, no_incremental_covered_universe_profit, increment_uncertain, family_adjusted_evidence_insufficient, concentrated_or_nonpositive_profit, unresolved_obligations |
| S7 | -$1,184 to $72,852 | -$1,775 to $73,088 | 2 / $74 | increment_uncertain, family_adjusted_evidence_insufficient, concentrated_or_nonpositive_profit, unresolved_obligations |
| C1 | -$15,469 to $70,354 | -$10,613 to $62,713 | 0 / $0 | fewer_than_30_issuers, no_incremental_covered_universe_profit, increment_uncertain, family_adjusted_evidence_insufficient, concentrated_or_nonpositive_profit |
| C2 | -$15,469 to $70,354 | -$10,613 to $62,713 | 0 / $0 | fewer_than_30_issuers, no_incremental_covered_universe_profit, increment_uncertain, family_adjusted_evidence_insufficient, concentrated_or_nonpositive_profit |
| C3 | -$15,469 to $70,354 | -$10,613 to $62,713 | 0 / $0 | fewer_than_30_issuers, no_incremental_covered_universe_profit, increment_uncertain, family_adjusted_evidence_insufficient, concentrated_or_nonpositive_profit |
| C4 | -$13,435 to $70,779 | -$8,844 to $65,961 | 1 / $30 | fewer_than_30_issuers, increment_uncertain, family_adjusted_evidence_insufficient, unresolved_obligations |

Monthly averages use the same 46 months beginning 2023-01-19 for every rule, including zero months. They are not forecast income. Closed and unresolved marked P&L remain separate in summary.json and local ledgers.

## Ten-session replication

| Rule | Trades / issuers | Net P&L | Max drawdown | Worst trade | Open liability |
| --- | --- | --- | --- | --- | --- |
| baseline | 63 / 50 | $7,647 | -$1,234 | -$703 | $0 |
| score60 | 17 / 15 | $2,111 | -$746 | -$73 | $61 |
| S1 | 3 / 3 | $55 | -$42 | -$16 | $0 |
| S2 | 0 / 0 | $0 | $0 | — | $0 |
| S3 | 33 / 25 | $8,141 | -$5,305 | -$386 | $0 |
| S4 | 6 / 6 | $673 | -$981 | -$197 | $61 |
| S5 | 10 / 10 | $1,413 | -$234 | -$64 | $0 |
| S6 | 47 / 39 | $5,544 | -$1,117 | -$703 | $0 |
| S7 | 63 / 50 | $6,270 | -$1,234 | -$703 | $0 |
| C1 | 0 / 0 | $0 | $0 | — | $0 |
| C2 | 0 / 0 | $0 | $0 | — | $0 |
| C3 | 0 / 0 | $0 | $0 | — | $0 |
| C4 | 10 / 10 | $1,413 | -$234 | -$64 | $0 |

## Fill and cost sensitivities

Full-size results have no capital admission cap. Recorded-volume cases are execution proxies; observed daily turnover is not pre-entry information or a locate. The passive-capture proxy is labeled unsupported and is never represented as legal-compliance or queue evidence. Strict SSR uses the existing status cache reconstructed at the entry open.

| Rule | Horizon | Volume cap | Cost | SSR | Net P&L | Mean position | Max drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 10 | full target | base | strict | -$4,079 | $24,997 | -$224,614 |
| baseline | 10 | full target | base | proxy | $79,884 | $24,997 | -$373,630 |
| baseline | 10 | 0.10% | base | strict | -$480 | $149 | -$2,503 |
| baseline | 10 | 0.10% | base | proxy | $4,529 | $165 | -$1,941 |
| baseline | 10 | 1.00% | base | strict | -$3,058 | $1,438 | -$24,408 |
| baseline | 10 | 1.00% | base | proxy | $37,777 | $1,518 | -$18,747 |
| baseline | 10 | 5.00% | base | strict | -$30,776 | $4,861 | -$121,563 |
| baseline | 10 | 5.00% | base | proxy | $92,532 | $5,110 | -$107,582 |
| baseline | 10 | 1.00% | lower_cost | strict | $8,597 | $807 | -$1,123 |
| baseline | 10 | 1.00% | depth_base | strict | $7,237 | $807 | -$1,323 |
| baseline | 10 | 1.00% | stress | strict | $4,445 | $807 | -$1,989 |
| baseline | 20 | full target | base | strict | $223,044 | $24,997 | -$223,079 |
| baseline | 20 | full target | base | proxy | $684,333 | $24,997 | -$377,004 |
| baseline | 20 | 0.10% | base | strict | -$1,652 | $149 | -$4,563 |
| baseline | 20 | 0.10% | base | proxy | $5,476 | $166 | -$4,007 |
| baseline | 20 | 1.00% | base | strict | -$16,403 | $1,438 | -$45,267 |
| baseline | 20 | 1.00% | base | proxy | $44,079 | $1,522 | -$38,973 |
| baseline | 20 | 5.00% | base | strict | -$118,580 | $4,861 | -$225,828 |
| baseline | 20 | 5.00% | base | proxy | $61,596 | $5,117 | -$210,114 |
| baseline | 20 | 1.00% | lower_cost | strict | -$15,323 | $824 | -$25,305 |
| baseline | 20 | 1.00% | depth_base | strict | -$17,202 | $824 | -$25,983 |
| baseline | 20 | 1.00% | stress | strict | -$19,982 | $824 | -$25,871 |
| score60 | 10 | full target | base | strict | $69,700 | $24,998 | -$17,449 |
| score60 | 10 | full target | base | proxy | -$14,914 | $24,997 | -$406,321 |
| score60 | 10 | 0.10% | base | strict | -$379 | $76 | -$706 |
| score60 | 10 | 0.10% | base | proxy | $2,618 | $178 | -$712 |
| score60 | 10 | 1.00% | base | strict | -$2,889 | $774 | -$6,302 |
| score60 | 10 | 1.00% | base | proxy | $16,786 | $1,451 | -$6,318 |
| score60 | 10 | 5.00% | base | strict | -$13,910 | $3,877 | -$31,113 |
| score60 | 10 | 5.00% | base | proxy | $26,302 | $5,303 | -$31,195 |
| score60 | 10 | 1.00% | lower_cost | strict | $2,325 | $631 | -$734 |
| score60 | 10 | 1.00% | depth_base | strict | $2,037 | $631 | -$763 |
| score60 | 10 | 1.00% | stress | strict | $1,385 | $631 | -$798 |
| score60 | 20 | full target | base | strict | $95,365 | $24,998 | -$30,107 |
| score60 | 20 | full target | base | proxy | $189,443 | $24,997 | -$376,083 |
| score60 | 20 | 0.10% | base | strict | -$732 | $76 | -$1,200 |
| score60 | 20 | 0.10% | base | proxy | $2,179 | $178 | -$1,694 |
| score60 | 20 | 1.00% | base | strict | -$6,799 | $774 | -$11,649 |
| score60 | 20 | 1.00% | base | proxy | $14,121 | $1,451 | -$13,815 |
| score60 | 20 | 5.00% | base | strict | -$33,665 | $3,877 | -$58,065 |
| score60 | 20 | 5.00% | base | proxy | $22,787 | $5,303 | -$58,587 |
| score60 | 20 | 1.00% | lower_cost | strict | -$1,067 | $631 | -$5,136 |
| score60 | 20 | 1.00% | depth_base | strict | -$1,528 | $631 | -$5,208 |
| score60 | 20 | 1.00% | stress | strict | -$2,568 | $631 | -$5,296 |
| S1 | 10 | full target | base | strict | $9,390 | $24,999 | -$6,693 |
| S1 | 10 | full target | base | proxy | -$51,484 | $24,997 | -$146,658 |
| S1 | 10 | 0.10% | base | strict | $3 | $11 | -$4 |
| S1 | 10 | 0.10% | base | proxy | -$126 | $62 | -$195 |
| S1 | 10 | 1.00% | base | strict | $55 | $134 | -$42 |
| S1 | 10 | 1.00% | base | proxy | -$1,203 | $644 | -$1,970 |
| S1 | 10 | 5.00% | base | strict | $311 | $686 | -$203 |
| S1 | 10 | 5.00% | base | proxy | -$5,940 | $3,231 | -$9,856 |
| S1 | 10 | 1.00% | lower_cost | strict | $62 | $134 | -$39 |
| S1 | 10 | 1.00% | depth_base | strict | $54 | $134 | -$43 |
| S1 | 10 | 1.00% | stress | strict | $29 | $134 | -$54 |
| S1 | 20 | full target | base | strict | $16,532 | $24,999 | -$12,399 |
| S1 | 20 | full target | base | proxy | $3,217 | $24,997 | -$138,983 |
| S1 | 20 | 0.10% | base | strict | $6 | $11 | -$4 |
| S1 | 20 | 0.10% | base | proxy | -$88 | $62 | -$195 |
| S1 | 20 | 1.00% | base | strict | $89 | $134 | -$48 |
| S1 | 20 | 1.00% | base | proxy | -$817 | $644 | -$1,970 |
| S1 | 20 | 5.00% | base | strict | $484 | $686 | -$243 |
| S1 | 20 | 5.00% | base | proxy | -$4,001 | $3,231 | -$9,856 |
| S1 | 20 | 1.00% | lower_cost | strict | $101 | $134 | -$48 |
| S1 | 20 | 1.00% | depth_base | strict | $88 | $134 | -$48 |
| S1 | 20 | 1.00% | stress | strict | $49 | $134 | -$49 |
| S2 | 10 | full target | base | strict | $0 | — | $0 |
| S2 | 10 | full target | base | proxy | $0 | — | $0 |
| S2 | 10 | 0.10% | base | strict | $0 | — | $0 |
| S2 | 10 | 0.10% | base | proxy | $0 | — | $0 |
| S2 | 10 | 1.00% | base | strict | $0 | — | $0 |
| S2 | 10 | 1.00% | base | proxy | $0 | — | $0 |
| S2 | 10 | 5.00% | base | strict | $0 | — | $0 |
| S2 | 10 | 5.00% | base | proxy | $0 | — | $0 |
| S2 | 10 | 1.00% | lower_cost | strict | $0 | — | $0 |
| S2 | 10 | 1.00% | depth_base | strict | $0 | — | $0 |
| S2 | 10 | 1.00% | stress | strict | $0 | — | $0 |
| S2 | 20 | full target | base | strict | $0 | — | $0 |
| S2 | 20 | full target | base | proxy | $0 | — | $0 |
| S2 | 20 | 0.10% | base | strict | $0 | — | $0 |
| S2 | 20 | 0.10% | base | proxy | $0 | — | $0 |
| S2 | 20 | 1.00% | base | strict | $0 | — | $0 |
| S2 | 20 | 1.00% | base | proxy | $0 | — | $0 |
| S2 | 20 | 5.00% | base | strict | $0 | — | $0 |
| S2 | 20 | 5.00% | base | proxy | $0 | — | $0 |
| S2 | 20 | 1.00% | lower_cost | strict | $0 | — | $0 |
| S2 | 20 | 1.00% | depth_base | strict | $0 | — | $0 |
| S2 | 20 | 1.00% | stress | strict | $0 | — | $0 |
| S3 | 10 | full target | base | strict | $148,237 | $24,997 | -$53,849 |
| S3 | 10 | full target | base | proxy | $166,985 | $24,998 | -$374,899 |
| S3 | 10 | 0.10% | base | strict | $333 | $109 | -$1,383 |
| S3 | 10 | 0.10% | base | proxy | $1,191 | $162 | -$1,368 |
| S3 | 10 | 1.00% | base | strict | $4,454 | $1,110 | -$13,150 |
| S3 | 10 | 1.00% | base | proxy | $13,876 | $1,536 | -$12,999 |
| S3 | 10 | 5.00% | base | strict | $22,896 | $5,560 | -$65,344 |
| S3 | 10 | 5.00% | base | proxy | $63,470 | $5,649 | -$64,591 |
| S3 | 10 | 1.00% | lower_cost | strict | $8,730 | $965 | -$5,298 |
| S3 | 10 | 1.00% | depth_base | strict | $7,900 | $965 | -$5,328 |
| S3 | 10 | 1.00% | stress | strict | $6,160 | $965 | -$5,395 |
| S3 | 20 | full target | base | strict | $173,493 | $24,997 | -$74,068 |
| S3 | 20 | full target | base | proxy | $431,707 | $24,998 | -$376,153 |
| S3 | 20 | 0.10% | base | strict | -$2,334 | $109 | -$3,929 |
| S3 | 20 | 0.10% | base | proxy | $839 | $162 | -$3,894 |
| S3 | 20 | 1.00% | base | strict | -$22,511 | $1,110 | -$38,955 |
| S3 | 20 | 1.00% | base | proxy | $6,398 | $1,536 | -$38,594 |
| S3 | 20 | 5.00% | base | strict | -$111,951 | $5,560 | -$194,382 |
| S3 | 20 | 5.00% | base | proxy | -$23,828 | $5,649 | -$192,567 |
| S3 | 20 | 1.00% | lower_cost | strict | -$14,057 | $997 | -$27,798 |
| S3 | 20 | 1.00% | depth_base | strict | -$15,675 | $997 | -$28,607 |
| S3 | 20 | 1.00% | stress | strict | -$17,874 | $996 | -$28,760 |
| S4 | 10 | full target | base | strict | $31,953 | $24,997 | -$14,783 |
| S4 | 10 | full target | base | proxy | $49,450 | $24,997 | -$17,840 |
| S4 | 10 | 0.10% | base | strict | -$167 | $472 | -$1,191 |
| S4 | 10 | 0.10% | base | proxy | -$80 | $256 | -$1,192 |
| S4 | 10 | 1.00% | base | strict | -$1,173 | $3,985 | -$9,819 |
| S4 | 10 | 1.00% | base | proxy | -$213 | $2,247 | -$9,835 |
| S4 | 10 | 5.00% | base | strict | $2,033 | $5,652 | -$9,819 |
| S4 | 10 | 5.00% | base | proxy | $6,905 | $4,996 | -$9,894 |
| S4 | 10 | 1.00% | lower_cost | strict | $767 | $828 | -$969 |
| S4 | 10 | 1.00% | depth_base | strict | $627 | $828 | -$981 |
| S4 | 10 | 1.00% | stress | strict | $351 | $828 | -$1,021 |
| S4 | 20 | full target | base | strict | $34,470 | $24,997 | -$21,460 |
| S4 | 20 | full target | base | proxy | $41,886 | $24,997 | -$28,935 |
| S4 | 20 | 0.10% | base | strict | $672 | $472 | -$1,191 |
| S4 | 20 | 0.10% | base | proxy | $646 | $256 | -$1,194 |
| S4 | 20 | 1.00% | base | strict | $5,745 | $3,985 | -$9,819 |
| S4 | 20 | 1.00% | base | proxy | $5,585 | $2,247 | -$9,851 |
| S4 | 20 | 5.00% | base | strict | $8,739 | $5,652 | -$9,819 |
| S4 | 20 | 5.00% | base | proxy | $7,978 | $4,996 | -$13,129 |
| S4 | 20 | 1.00% | lower_cost | strict | $1,463 | $828 | -$969 |
| S4 | 20 | 1.00% | depth_base | strict | $1,279 | $828 | -$981 |
| S4 | 20 | 1.00% | stress | strict | $833 | $828 | -$1,021 |
| S5 | 10 | full target | base | strict | $48,868 | $24,997 | -$8,033 |
| S5 | 10 | full target | base | proxy | $179,953 | $24,997 | -$87,453 |
| S5 | 10 | 0.10% | base | strict | $133 | $48 | -$24 |
| S5 | 10 | 0.10% | base | proxy | $1,390 | $123 | -$739 |
| S5 | 10 | 1.00% | base | strict | $1,413 | $495 | -$234 |
| S5 | 10 | 1.00% | base | proxy | $14,456 | $1,245 | -$7,399 |
| S5 | 10 | 5.00% | base | strict | $7,133 | $2,485 | -$1,171 |
| S5 | 10 | 5.00% | base | proxy | $63,952 | $5,330 | -$10,700 |
| S5 | 10 | 1.00% | lower_cost | strict | $1,495 | $495 | -$225 |
| S5 | 10 | 1.00% | depth_base | strict | $1,385 | $495 | -$244 |
| S5 | 10 | 1.00% | stress | strict | $1,136 | $495 | -$267 |
| S5 | 20 | full target | base | strict | $76,466 | $24,997 | -$73,336 |
| S5 | 20 | full target | base | proxy | $226,221 | $24,997 | -$118,986 |
| S5 | 20 | 0.10% | base | strict | $173 | $48 | -$210 |
| S5 | 20 | 0.10% | base | proxy | $1,593 | $123 | -$739 |
| S5 | 20 | 1.00% | base | strict | $1,832 | $495 | -$2,150 |
| S5 | 20 | 1.00% | base | proxy | $16,522 | $1,245 | -$7,399 |
| S5 | 20 | 5.00% | base | strict | $9,243 | $2,485 | -$10,784 |
| S5 | 20 | 5.00% | base | proxy | $70,526 | $5,330 | -$21,899 |
| S5 | 20 | 1.00% | lower_cost | strict | $1,958 | $495 | -$2,147 |
| S5 | 20 | 1.00% | depth_base | strict | $1,806 | $495 | -$2,150 |
| S5 | 20 | 1.00% | stress | strict | $1,404 | $495 | -$2,160 |
| S6 | 10 | full target | base | strict | -$83,887 | $24,997 | -$224,531 |
| S6 | 10 | full target | base | proxy | -$77,178 | $24,998 | -$373,630 |
| S6 | 10 | 0.10% | base | strict | -$610 | $172 | -$1,538 |
| S6 | 10 | 0.10% | base | proxy | $1,487 | $154 | -$1,454 |
| S6 | 10 | 1.00% | base | strict | -$5,392 | $1,632 | -$15,487 |
| S6 | 10 | 1.00% | base | proxy | $16,748 | $1,473 | -$14,662 |
| S6 | 10 | 5.00% | base | strict | -$43,027 | $4,636 | -$77,449 |
| S6 | 10 | 5.00% | base | proxy | $52,328 | $5,073 | -$74,004 |
| S6 | 10 | 1.00% | lower_cost | strict | $6,214 | $776 | -$1,050 |
| S6 | 10 | 1.00% | depth_base | strict | $5,262 | $776 | -$1,144 |
| S6 | 10 | 1.00% | stress | strict | $3,266 | $776 | -$1,562 |
| S6 | 20 | full target | base | strict | $136,233 | $24,997 | -$219,967 |
| S6 | 20 | full target | base | proxy | $508,198 | $24,998 | -$376,444 |
| S6 | 20 | 0.10% | base | strict | -$1,535 | $172 | -$4,035 |
| S6 | 20 | 0.10% | base | proxy | $3,012 | $154 | -$3,891 |
| S6 | 20 | 1.00% | base | strict | -$15,880 | $1,632 | -$40,477 |
| S6 | 20 | 1.00% | base | proxy | $27,165 | $1,478 | -$39,029 |
| S6 | 20 | 5.00% | base | strict | -$116,344 | $4,636 | -$202,263 |
| S6 | 20 | 5.00% | base | proxy | $35,979 | $5,083 | -$196,476 |
| S6 | 20 | 1.00% | lower_cost | strict | -$20,132 | $748 | -$25,152 |
| S6 | 20 | 1.00% | depth_base | strict | -$21,777 | $748 | -$25,845 |
| S6 | 20 | 1.00% | stress | strict | -$24,076 | $748 | -$25,817 |
| S7 | 10 | full target | base | strict | -$34,018 | $24,997 | -$222,103 |
| S7 | 10 | full target | base | proxy | $5,483 | $24,997 | -$373,630 |
| S7 | 10 | 0.10% | base | strict | -$265 | $139 | -$1,555 |
| S7 | 10 | 0.10% | base | proxy | $1,916 | $123 | -$1,454 |
| S7 | 10 | 1.00% | base | strict | -$1,720 | $1,338 | -$15,646 |
| S7 | 10 | 1.00% | base | proxy | $21,021 | $1,219 | -$14,662 |
| S7 | 10 | 5.00% | base | strict | -$24,516 | $4,233 | -$78,252 |
| S7 | 10 | 5.00% | base | proxy | $65,911 | $4,554 | -$74,004 |
| S7 | 10 | 1.00% | lower_cost | strict | $7,106 | $722 | -$1,123 |
| S7 | 10 | 1.00% | depth_base | strict | $5,912 | $722 | -$1,323 |
| S7 | 10 | 1.00% | stress | strict | $3,446 | $722 | -$1,964 |
| S7 | 20 | full target | base | strict | $181,992 | $24,997 | -$230,562 |
| S7 | 20 | full target | base | proxy | $606,552 | $24,997 | -$376,444 |
| S7 | 20 | 0.10% | base | strict | $1,454 | $139 | -$1,613 |
| S7 | 20 | 0.10% | base | proxy | $4,711 | $123 | -$1,381 |
| S7 | 20 | 1.00% | base | strict | $14,216 | $1,338 | -$15,296 |
| S7 | 20 | 1.00% | base | proxy | $47,940 | $1,221 | -$13,927 |
| S7 | 20 | 5.00% | base | strict | $34,158 | $4,233 | -$76,519 |
| S7 | 20 | 5.00% | base | proxy | $174,249 | $4,559 | -$71,115 |
| S7 | 20 | 1.00% | lower_cost | strict | $8,223 | $715 | -$2,329 |
| S7 | 20 | 1.00% | depth_base | strict | $7,158 | $715 | -$2,455 |
| S7 | 20 | 1.00% | stress | strict | $4,561 | $715 | -$3,078 |
| C1 | 10 | full target | base | strict | $0 | — | $0 |
| C1 | 10 | full target | base | proxy | $0 | — | $0 |
| C1 | 10 | 0.10% | base | strict | $0 | — | $0 |
| C1 | 10 | 0.10% | base | proxy | $0 | — | $0 |
| C1 | 10 | 1.00% | base | strict | $0 | — | $0 |
| C1 | 10 | 1.00% | base | proxy | $0 | — | $0 |
| C1 | 10 | 5.00% | base | strict | $0 | — | $0 |
| C1 | 10 | 5.00% | base | proxy | $0 | — | $0 |
| C1 | 10 | 1.00% | lower_cost | strict | $0 | — | $0 |
| C1 | 10 | 1.00% | depth_base | strict | $0 | — | $0 |
| C1 | 10 | 1.00% | stress | strict | $0 | — | $0 |
| C1 | 20 | full target | base | strict | $0 | — | $0 |
| C1 | 20 | full target | base | proxy | $0 | — | $0 |
| C1 | 20 | 0.10% | base | strict | $0 | — | $0 |
| C1 | 20 | 0.10% | base | proxy | $0 | — | $0 |
| C1 | 20 | 1.00% | base | strict | $0 | — | $0 |
| C1 | 20 | 1.00% | base | proxy | $0 | — | $0 |
| C1 | 20 | 5.00% | base | strict | $0 | — | $0 |
| C1 | 20 | 5.00% | base | proxy | $0 | — | $0 |
| C1 | 20 | 1.00% | lower_cost | strict | $0 | — | $0 |
| C1 | 20 | 1.00% | depth_base | strict | $0 | — | $0 |
| C1 | 20 | 1.00% | stress | strict | $0 | — | $0 |
| C2 | 10 | full target | base | strict | $0 | — | $0 |
| C2 | 10 | full target | base | proxy | $0 | — | $0 |
| C2 | 10 | 0.10% | base | strict | $0 | — | $0 |
| C2 | 10 | 0.10% | base | proxy | $0 | — | $0 |
| C2 | 10 | 1.00% | base | strict | $0 | — | $0 |
| C2 | 10 | 1.00% | base | proxy | $0 | — | $0 |
| C2 | 10 | 5.00% | base | strict | $0 | — | $0 |
| C2 | 10 | 5.00% | base | proxy | $0 | — | $0 |
| C2 | 10 | 1.00% | lower_cost | strict | $0 | — | $0 |
| C2 | 10 | 1.00% | depth_base | strict | $0 | — | $0 |
| C2 | 10 | 1.00% | stress | strict | $0 | — | $0 |
| C2 | 20 | full target | base | strict | $0 | — | $0 |
| C2 | 20 | full target | base | proxy | $0 | — | $0 |
| C2 | 20 | 0.10% | base | strict | $0 | — | $0 |
| C2 | 20 | 0.10% | base | proxy | $0 | — | $0 |
| C2 | 20 | 1.00% | base | strict | $0 | — | $0 |
| C2 | 20 | 1.00% | base | proxy | $0 | — | $0 |
| C2 | 20 | 5.00% | base | strict | $0 | — | $0 |
| C2 | 20 | 5.00% | base | proxy | $0 | — | $0 |
| C2 | 20 | 1.00% | lower_cost | strict | $0 | — | $0 |
| C2 | 20 | 1.00% | depth_base | strict | $0 | — | $0 |
| C2 | 20 | 1.00% | stress | strict | $0 | — | $0 |
| C3 | 10 | full target | base | strict | $0 | — | $0 |
| C3 | 10 | full target | base | proxy | $0 | — | $0 |
| C3 | 10 | 0.10% | base | strict | $0 | — | $0 |
| C3 | 10 | 0.10% | base | proxy | $0 | — | $0 |
| C3 | 10 | 1.00% | base | strict | $0 | — | $0 |
| C3 | 10 | 1.00% | base | proxy | $0 | — | $0 |
| C3 | 10 | 5.00% | base | strict | $0 | — | $0 |
| C3 | 10 | 5.00% | base | proxy | $0 | — | $0 |
| C3 | 10 | 1.00% | lower_cost | strict | $0 | — | $0 |
| C3 | 10 | 1.00% | depth_base | strict | $0 | — | $0 |
| C3 | 10 | 1.00% | stress | strict | $0 | — | $0 |
| C3 | 20 | full target | base | strict | $0 | — | $0 |
| C3 | 20 | full target | base | proxy | $0 | — | $0 |
| C3 | 20 | 0.10% | base | strict | $0 | — | $0 |
| C3 | 20 | 0.10% | base | proxy | $0 | — | $0 |
| C3 | 20 | 1.00% | base | strict | $0 | — | $0 |
| C3 | 20 | 1.00% | base | proxy | $0 | — | $0 |
| C3 | 20 | 5.00% | base | strict | $0 | — | $0 |
| C3 | 20 | 5.00% | base | proxy | $0 | — | $0 |
| C3 | 20 | 1.00% | lower_cost | strict | $0 | — | $0 |
| C3 | 20 | 1.00% | depth_base | strict | $0 | — | $0 |
| C3 | 20 | 1.00% | stress | strict | $0 | — | $0 |
| C4 | 10 | full target | base | strict | $48,868 | $24,997 | -$8,033 |
| C4 | 10 | full target | base | proxy | $141,924 | $24,997 | -$87,453 |
| C4 | 10 | 0.10% | base | strict | $133 | $48 | -$24 |
| C4 | 10 | 0.10% | base | proxy | $1,001 | $101 | -$198 |
| C4 | 10 | 1.00% | base | strict | $1,413 | $495 | -$234 |
| C4 | 10 | 1.00% | base | proxy | $10,439 | $1,021 | -$1,999 |
| C4 | 10 | 5.00% | base | strict | $7,133 | $2,485 | -$1,171 |
| C4 | 10 | 5.00% | base | proxy | $51,222 | $5,067 | -$10,002 |
| C4 | 10 | 1.00% | lower_cost | strict | $1,495 | $495 | -$225 |
| C4 | 10 | 1.00% | depth_base | strict | $1,385 | $495 | -$244 |
| C4 | 10 | 1.00% | stress | strict | $1,136 | $495 | -$267 |
| C4 | 20 | full target | base | strict | $76,466 | $24,997 | -$73,336 |
| C4 | 20 | full target | base | proxy | $188,875 | $24,997 | -$118,245 |
| C4 | 20 | 0.10% | base | strict | $173 | $48 | -$210 |
| C4 | 20 | 0.10% | base | proxy | $1,116 | $101 | -$418 |
| C4 | 20 | 1.00% | base | strict | $1,832 | $495 | -$2,150 |
| C4 | 20 | 1.00% | base | proxy | $11,627 | $1,021 | -$4,207 |
| C4 | 20 | 5.00% | base | strict | $9,243 | $2,485 | -$10,784 |
| C4 | 20 | 5.00% | base | proxy | $57,221 | $5,067 | -$21,068 |
| C4 | 20 | 1.00% | lower_cost | strict | $1,958 | $495 | -$2,147 |
| C4 | 20 | 1.00% | depth_base | strict | $1,806 | $495 | -$2,150 |
| C4 | 20 | 1.00% | stress | strict | $1,404 | $495 | -$2,160 |

Costs: lower 1% execution / 20% APR; base 1.72% / 50%; stress 4.25% / 150%; depth base 1.72% plus 4.23% times sqrt(order/$25k), capped at 80%, / 50% APR. Rates and depths are assumptions, not historical broker bills. Dividends, locate fees, servicing and forced-buy-in cash flows remain unobserved. Existing dated SEC/TAF fees are a frozen scenario.

## Equal account-capital and stress budgets

Each account uses a +200% price-rise stress, 0.5% NAV per-name loss reserve, 2% NAV sleeve reserve, three-name limit and 20% margin buffer. This implies nominal admission limits of 0.25% NAV per name and 1% NAV across the sleeve before other-system reservations. Other-system stress is set to zero for these conditional accounts; production use requires actual shared-account reservations. Admission uses prior available marks, not today’s later close. Subsequent mark breaches are flagged; these are not automatic guaranteed exits.

| NAV | Rule | Trades | Net P&L | Max drawdown | Peak exposure | Mark breach sessions |
| --- | --- | --- | --- | --- | --- | --- |
| $500,000 | baseline | 65 | $5,579 | -$1,017 | $3,453 | 0 |
| $1,000,000 | baseline | 63 | $7,647 | -$1,234 | $4,591 | 0 |
| $5,000,000 | baseline | 62 | $8,408 | -$6,475 | $16,735 | 0 |
| $10,000,000 | baseline | 62 | $7,838 | -$9,836 | $33,062 | 0 |
| $500,000 | baseline | 41 | $2,342 | -$3,127 | $2,587 | 0 |
| $1,000,000 | baseline | 41 | -$16,386 | -$25,417 | $3,308 | 0 |
| $5,000,000 | baseline | 41 | -$13,756 | -$26,360 | $16,363 | 0 |
| $10,000,000 | baseline | 41 | -$11,257 | -$25,417 | $32,690 | 0 |
| $500,000 | score60 | 17 | $1,763 | -$382 | $1,774 | 0 |
| $1,000,000 | score60 | 17 | $2,111 | -$746 | $3,373 | 0 |
| $5,000,000 | score60 | 17 | -$2,889 | -$6,302 | $6,491 | 0 |
| $10,000,000 | score60 | 17 | -$2,889 | -$6,302 | $6,491 | 0 |
| $500,000 | score60 | 17 | $1,162 | -$1,877 | $2,275 | 0 |
| $1,000,000 | score60 | 17 | -$1,404 | -$5,151 | $3,662 | 0 |
| $5,000,000 | score60 | 17 | -$6,799 | -$11,649 | $6,779 | 0 |
| $10,000,000 | score60 | 17 | -$6,799 | -$11,649 | $6,779 | 0 |
| $500,000 | S1 | 3 | $55 | -$42 | $185 | 0 |
| $1,000,000 | S1 | 3 | $55 | -$42 | $185 | 0 |
| $5,000,000 | S1 | 3 | $55 | -$42 | $185 | 0 |
| $10,000,000 | S1 | 3 | $55 | -$42 | $185 | 0 |
| $500,000 | S1 | 3 | $89 | -$48 | $185 | 0 |
| $1,000,000 | S1 | 3 | $89 | -$48 | $185 | 0 |
| $5,000,000 | S1 | 3 | $89 | -$48 | $185 | 0 |
| $10,000,000 | S1 | 3 | $89 | -$48 | $185 | 0 |
| $500,000 | S2 | 0 | $0 | $0 | $0 | 0 |
| $1,000,000 | S2 | 0 | $0 | $0 | $0 | 0 |
| $5,000,000 | S2 | 0 | $0 | $0 | $0 | 0 |
| $10,000,000 | S2 | 0 | $0 | $0 | $0 | 0 |
| $500,000 | S2 | 0 | $0 | $0 | $0 | 0 |
| $1,000,000 | S2 | 0 | $0 | $0 | $0 | 0 |
| $5,000,000 | S2 | 0 | $0 | $0 | $0 | 0 |
| $10,000,000 | S2 | 0 | $0 | $0 | $0 | 0 |
| $500,000 | S3 | 33 | $4,897 | -$2,669 | $4,952 | 0 |
| $1,000,000 | S3 | 33 | $8,141 | -$5,305 | $8,826 | 0 |
| $5,000,000 | S3 | 33 | $4,454 | -$13,150 | $11,355 | 0 |
| $10,000,000 | S3 | 33 | $4,454 | -$13,150 | $11,355 | 0 |
| $500,000 | S3 | 29 | $3,225 | -$4,272 | $5,233 | 1 |
| $1,000,000 | S3 | 29 | -$14,926 | -$28,012 | $8,970 | 0 |
| $5,000,000 | S3 | 29 | -$13,426 | -$29,845 | $11,663 | 0 |
| $10,000,000 | S3 | 29 | -$13,426 | -$29,845 | $11,663 | 0 |
| $500,000 | S4 | 6 | $770 | -$491 | $1,795 | 0 |
| $1,000,000 | S4 | 6 | $673 | -$981 | $3,266 | 0 |
| $5,000,000 | S4 | 6 | -$112 | -$4,906 | $16,328 | 0 |
| $10,000,000 | S4 | 6 | -$1,095 | -$9,819 | $32,677 | 0 |
| $500,000 | S4 | 6 | $1,068 | -$491 | $1,795 | 0 |
| $1,000,000 | S4 | 6 | $1,319 | -$981 | $3,266 | 0 |
| $5,000,000 | S4 | 6 | $3,319 | -$4,906 | $16,328 | 0 |
| $10,000,000 | S4 | 6 | $5,823 | -$9,819 | $32,677 | 0 |
| $500,000 | S5 | 10 | $1,338 | -$225 | $1,315 | 0 |
| $1,000,000 | S5 | 10 | $1,413 | -$234 | $1,476 | 0 |
| $5,000,000 | S5 | 10 | $1,413 | -$234 | $1,476 | 0 |
| $10,000,000 | S5 | 10 | $1,413 | -$234 | $1,476 | 0 |
| $500,000 | S5 | 10 | $1,738 | -$2,150 | $2,548 | 0 |
| $1,000,000 | S5 | 10 | $1,832 | -$2,150 | $2,548 | 0 |
| $5,000,000 | S5 | 10 | $1,832 | -$2,150 | $2,548 | 0 |
| $10,000,000 | S5 | 10 | $1,832 | -$2,150 | $2,548 | 0 |
| $500,000 | S6 | 48 | $4,704 | -$942 | $3,270 | 0 |
| $1,000,000 | S6 | 47 | $5,544 | -$1,117 | $4,415 | 0 |
| $5,000,000 | S6 | 46 | $10,148 | -$4,929 | $16,735 | 0 |
| $10,000,000 | S6 | 46 | $9,580 | -$9,836 | $33,062 | 0 |
| $500,000 | S6 | 34 | $312 | -$3,048 | $3,673 | 0 |
| $1,000,000 | S6 | 34 | -$21,032 | -$25,287 | $4,819 | 0 |
| $5,000,000 | S6 | 34 | -$19,245 | -$25,980 | $16,341 | 0 |
| $10,000,000 | S6 | 34 | -$16,743 | -$25,287 | $32,690 | 0 |
| $500,000 | S7 | 63 | $4,853 | -$1,017 | $3,453 | 0 |
| $1,000,000 | S7 | 63 | $6,270 | -$1,234 | $4,591 | 0 |
| $5,000,000 | S7 | 62 | $12,037 | -$4,929 | $16,735 | 0 |
| $10,000,000 | S7 | 62 | $11,467 | -$9,836 | $33,062 | 0 |
| $500,000 | S7 | 41 | $4,530 | -$1,651 | $2,587 | 0 |
| $1,000,000 | S7 | 41 | $7,385 | -$2,419 | $3,279 | 0 |
| $5,000,000 | S7 | 41 | $10,015 | -$10,439 | $16,363 | 0 |
| $10,000,000 | S7 | 41 | $12,514 | -$14,539 | $32,690 | 0 |
| $500,000 | C1 | 0 | $0 | $0 | $0 | 0 |
| $1,000,000 | C1 | 0 | $0 | $0 | $0 | 0 |
| $5,000,000 | C1 | 0 | $0 | $0 | $0 | 0 |
| $10,000,000 | C1 | 0 | $0 | $0 | $0 | 0 |
| $500,000 | C1 | 0 | $0 | $0 | $0 | 0 |
| $1,000,000 | C1 | 0 | $0 | $0 | $0 | 0 |
| $5,000,000 | C1 | 0 | $0 | $0 | $0 | 0 |
| $10,000,000 | C1 | 0 | $0 | $0 | $0 | 0 |
| $500,000 | C2 | 0 | $0 | $0 | $0 | 0 |
| $1,000,000 | C2 | 0 | $0 | $0 | $0 | 0 |
| $5,000,000 | C2 | 0 | $0 | $0 | $0 | 0 |
| $10,000,000 | C2 | 0 | $0 | $0 | $0 | 0 |
| $500,000 | C2 | 0 | $0 | $0 | $0 | 0 |
| $1,000,000 | C2 | 0 | $0 | $0 | $0 | 0 |
| $5,000,000 | C2 | 0 | $0 | $0 | $0 | 0 |
| $10,000,000 | C2 | 0 | $0 | $0 | $0 | 0 |
| $500,000 | C3 | 0 | $0 | $0 | $0 | 0 |
| $1,000,000 | C3 | 0 | $0 | $0 | $0 | 0 |
| $5,000,000 | C3 | 0 | $0 | $0 | $0 | 0 |
| $10,000,000 | C3 | 0 | $0 | $0 | $0 | 0 |
| $500,000 | C3 | 0 | $0 | $0 | $0 | 0 |
| $1,000,000 | C3 | 0 | $0 | $0 | $0 | 0 |
| $5,000,000 | C3 | 0 | $0 | $0 | $0 | 0 |
| $10,000,000 | C3 | 0 | $0 | $0 | $0 | 0 |
| $500,000 | C4 | 10 | $1,338 | -$225 | $1,315 | 0 |
| $1,000,000 | C4 | 10 | $1,413 | -$234 | $1,476 | 0 |
| $5,000,000 | C4 | 10 | $1,413 | -$234 | $1,476 | 0 |
| $10,000,000 | C4 | 10 | $1,413 | -$234 | $1,476 | 0 |
| $500,000 | C4 | 10 | $1,738 | -$2,150 | $2,548 | 0 |
| $1,000,000 | C4 | 10 | $1,832 | -$2,150 | $2,548 | 0 |
| $5,000,000 | C4 | 10 | $1,832 | -$2,150 | $2,548 | 0 |
| $10,000,000 | C4 | 10 | $1,832 | -$2,150 | $2,548 | 0 |

## Chronology, issuer concentration and controls

| Rule | Entry year | Trades / issuers | Marked P&L through cutoff | Unresolved |
| --- | --- | --- | --- | --- |
| baseline | 2023 | 2 / 2 | $174 | 0 |
| baseline | 2024 | 9 / 9 | $2,918 | 0 |
| baseline | 2025 | 17 / 15 | $813 | 1 |
| baseline | 2026 | 13 / 11 | -$20,290 | 1 |
| score60 | 2023 | 1 / 1 | $16 | 0 |
| score60 | 2024 | 2 / 2 | -$13 | 0 |
| score60 | 2025 | 4 / 3 | $283 | 0 |
| score60 | 2026 | 10 / 9 | -$1,689 | 1 |
| S1 | 2023 | 1 / 1 | $16 | 0 |
| S1 | 2025 | 1 / 1 | -$9 | 0 |
| S1 | 2026 | 1 / 1 | $82 | 0 |
| S3 | 2023 | 2 / 2 | $174 | 0 |
| S3 | 2024 | 3 / 3 | $2,557 | 0 |
| S3 | 2025 | 10 / 8 | $942 | 0 |
| S3 | 2026 | 14 / 11 | -$18,599 | 0 |
| S4 | 2024 | 1 / 1 | -$31 | 0 |
| S4 | 2025 | 1 / 1 | $499 | 0 |
| S4 | 2026 | 4 / 4 | $851 | 1 |
| S5 | 2023 | 1 / 1 | $16 | 0 |
| S5 | 2025 | 1 / 1 | $9 | 0 |
| S5 | 2026 | 8 / 8 | $1,806 | 1 |
| S6 | 2023 | 1 / 1 | $16 | 0 |
| S6 | 2024 | 4 / 4 | -$108 | 0 |
| S6 | 2025 | 16 / 13 | $1,211 | 1 |
| S6 | 2026 | 13 / 11 | -$22,151 | 1 |
| S7 | 2023 | 2 / 2 | $174 | 0 |
| S7 | 2024 | 9 / 9 | $2,918 | 0 |
| S7 | 2025 | 17 / 15 | $299 | 1 |
| S7 | 2026 | 13 / 11 | $3,994 | 1 |
| C4 | 2023 | 1 / 1 | $16 | 0 |
| C4 | 2025 | 1 / 1 | $9 | 0 |
| C4 | 2026 | 8 / 8 | $1,806 | 1 |

Entry-year results include later carry and marks on that cohort through the cutoff. Calendar-month results below instead measure portfolio value changes during each month.

| Rule | Without best issuer | Without best five issuers | Worst trade | Worst daily change | Worst adverse price rise |
| --- | --- | --- | --- | --- | --- |
| baseline | -$20,696 | -$23,881 | -$24,306 | -$25,224 | 3268.18% |
| score60 | -$2,255 | -$3,374 | -$3,788 | -$4,916 | 404.57% |
| S1 | $7 | $0 | -$9 | -$48 | 208.33% |
| S2 | $0 | $0 | — | $0 | — |
| S3 | -$19,236 | -$23,431 | -$24,306 | -$25,207 | 3268.18% |
| S4 | $820 | -$31 | -$31 | -$405 | 102.99% |
| S5 | $981 | $26 | -$97 | -$1,396 | 253.92% |
| S6 | -$21,882 | -$24,178 | -$24,306 | -$25,224 | 3268.18% |
| S7 | $3,075 | -$110 | -$738 | -$676 | 672.85% |
| C1 | $0 | $0 | — | $0 | — |
| C2 | $0 | $0 | — | $0 | — |
| C3 | $0 | $0 | — | $0 | — |
| C4 | $981 | $26 | -$97 | -$1,396 | 253.92% |

| Signal | Complete closed labels / issuers | Controlled coefficient | Cluster 95% | Status |
| --- | --- | --- | --- | --- |
| S1 | 8 / 8 | — | — | insufficient_support |
| S2 | 0 / 0 | — | — | insufficient_support |
| S3 | 33 / 27 | -109.68% | -313.44% to 94.07% | exploratory_issuer_cluster_OLS |
| S4 | 3 / 3 | — | — | insufficient_support |
| S5 | 39 / 31 | 131.82% | -93.53% to 357.17% | exploratory_issuer_cluster_OLS |
| S6 | 39 / 31 | -16.65% | -90.12% to 56.81% | exploratory_issuer_cluster_OLS |
| S7 | 39 / 31 | 473.42% | -170.89% to 1117.73% | exploratory_issuer_cluster_OLS |

Controlled fits use as-of provider magnitude, ordinal 4+, year, log price and log prior ADV. Unresolved labels stay out of these fits and their attrition is explicit; they stay in portfolio liabilities. No controlled association is treated as causal. Provisional CIK/symbol class identity and mechanical action repairs remain limitations.

| Diagnostic | Rule | Trades | Net P&L | Max drawdown |
| --- | --- | --- | --- | --- |
| provider_only_history | baseline | 62 | $6,531 | -$1,666 |
| provider_only_history | baseline | 40 | -$15,774 | -$25,417 |
| provider_only_history | score60 | 17 | $2,111 | -$746 |
| provider_only_history | score60 | 17 | -$1,404 | -$5,151 |
| provider_only_history | S1 | 2 | $70 | -$18 |
| provider_only_history | S1 | 2 | $98 | -$48 |
| provider_only_history | S2 | 0 | $0 | $0 |
| provider_only_history | S2 | 0 | $0 | $0 |
| provider_only_history | S3 | 33 | $8,141 | -$5,305 |
| provider_only_history | S3 | 29 | -$14,926 | -$28,012 |
| provider_only_history | S4 | 6 | $673 | -$981 |
| provider_only_history | S4 | 6 | $1,319 | -$981 |
| provider_only_history | S5 | 10 | $1,413 | -$234 |
| provider_only_history | S5 | 10 | $1,832 | -$2,150 |
| provider_only_history | S6 | 45 | $4,501 | -$1,275 |
| provider_only_history | S6 | 34 | -$21,399 | -$25,287 |
| provider_only_history | S7 | 62 | $5,155 | -$1,666 |
| provider_only_history | S7 | 40 | $7,997 | -$2,455 |
| provider_only_history | C1 | 0 | $0 | $0 |
| provider_only_history | C1 | 0 | $0 | $0 |
| provider_only_history | C2 | 0 | $0 | $0 |
| provider_only_history | C2 | 0 | $0 | $0 |
| provider_only_history | C3 | 0 | $0 | $0 |
| provider_only_history | C3 | 0 | $0 | $0 |
| provider_only_history | C4 | 10 | $1,413 | -$234 |
| provider_only_history | C4 | 10 | $1,832 | -$2,150 |
| unadjusted_reported_runway_exploratory | reported_runway | 28 | $4,074 | -$5,315 |
| unadjusted_reported_runway_exploratory | reported_runway | 25 | $1,757 | -$2,265 |
| one_extra_session_clock_delay | baseline | 48 | $15,159 | -$4,927 |
| one_extra_session_clock_delay | score60 | 18 | $3,145 | -$2,493 |
| one_extra_session_clock_delay | S1 | 7 | -$674 | -$1,413 |
| one_extra_session_clock_delay | S2 | 0 | $0 | $0 |
| one_extra_session_clock_delay | S3 | 30 | -$17,195 | -$31,470 |
| one_extra_session_clock_delay | S4 | 6 | $1,058 | -$295 |
| one_extra_session_clock_delay | S5 | 19 | $1,387 | -$5,700 |
| one_extra_session_clock_delay | S6 | 32 | $9,888 | -$4,941 |
| one_extra_session_clock_delay | S7 | 46 | $10,846 | -$4,986 |
| one_extra_session_clock_delay | C1 | 0 | $0 | $0 |
| one_extra_session_clock_delay | C2 | 0 | $0 | $0 |
| one_extra_session_clock_delay | C3 | 0 | $0 | $0 |
| one_extra_session_clock_delay | C4 | 13 | -$120 | -$4,632 |

## Walk-forward selection

Each quarter can use only positions closed and modeled loan returns completed before a 20-session embargo. A rule needs at least 30 prior selected issuers and multiplicity-adjusted positive evidence; otherwise the baseline is retained. All historical years were already explored, so this is a causal development replay, not an untouched test.

| Quarter | Training issuers | Selected rule | Reason |
| --- | --- | --- | --- |
| 2023Q1 | 0 | baseline | insufficient_prior_completed_evidence |
| 2023Q2 | 1 | baseline | insufficient_prior_completed_evidence |
| 2023Q4 | 1 | baseline | insufficient_prior_completed_evidence |
| 2024Q1 | 1 | baseline | insufficient_prior_completed_evidence |
| 2024Q2 | 2 | baseline | insufficient_prior_completed_evidence |
| 2024Q3 | 3 | baseline | insufficient_prior_completed_evidence |
| 2024Q4 | 5 | baseline | insufficient_prior_completed_evidence |
| 2025Q1 | 8 | baseline | insufficient_prior_completed_evidence |
| 2025Q2 | 11 | baseline | insufficient_prior_completed_evidence |
| 2025Q3 | 13 | baseline | insufficient_prior_completed_evidence |
| 2025Q4 | 20 | baseline | insufficient_prior_completed_evidence |
| 2026Q1 | 21 | baseline | insufficient_prior_completed_evidence |
| 2026Q2 | 23 | baseline | insufficient_prior_completed_evidence |
| 2026Q3 | 25 | baseline | insufficient_prior_completed_evidence |
| 2026Q4 | 29 | baseline | insufficient_prior_completed_evidence |

Walk-forward portfolio net P&L: -$16,386; maximum drawdown -$25,417.

## Delayed-entry and next-open exit stage

No historical finalist passed all gates; the implemented timing/exit stage is not searched on rejected rules.

The implemented confirmation observes at most three completed post-split bars, requires a rebound followed by a close below the prior bar low, and enters only at a later session open. Matched delayed and signal-window baselines are supported. The 20% close-risk comparator executes at the following session’s observed open and does not clip gap losses to a stop price. These extra experiments run only for historical finalists.

## Common-window monthly ledger

| Month | baseline | S3 | S5 | S7 |
| --- | --- | --- | --- | --- |
| 2023-01 | -$462 | -$462 | $0 | -$462 |
| 2023-02 | $620 | $620 | $0 | $620 |
| 2023-03 | $0 | $0 | $0 | $0 |
| 2023-04 | $0 | $0 | $0 | $0 |
| 2023-05 | $0 | $0 | $0 | $0 |
| 2023-06 | $0 | $0 | $0 | $0 |
| 2023-07 | $0 | $0 | $0 | $0 |
| 2023-08 | $0 | $0 | $0 | $0 |
| 2023-09 | $0 | $0 | $0 | $0 |
| 2023-10 | $0 | $0 | $0 | $0 |
| 2023-11 | -$39 | -$39 | -$39 | -$39 |
| 2023-12 | $55 | $55 | $55 | $55 |
| 2024-01 | $0 | $0 | $0 | $0 |
| 2024-02 | $0 | $0 | $0 | $0 |
| 2024-03 | $0 | $0 | $0 | $0 |
| 2024-04 | -$11 | $0 | $0 | -$11 |
| 2024-05 | -$96 | $0 | $0 | -$96 |
| 2024-06 | $0 | $0 | $0 | $0 |
| 2024-07 | $1,359 | $1,357 | $0 | $1,359 |
| 2024-08 | -$9 | $0 | $0 | -$9 |
| 2024-09 | $0 | $0 | $0 | $0 |
| 2024-10 | $1,264 | $1,243 | $0 | $1,264 |
| 2024-11 | $321 | $114 | $0 | $321 |
| 2024-12 | $101 | -$156 | $0 | $101 |
| 2025-01 | -$11 | $0 | $0 | -$11 |
| 2025-02 | $1,111 | $0 | $0 | $1,111 |
| 2025-03 | -$1,165 | $0 | $0 | -$1,165 |
| 2025-04 | -$36 | $0 | $0 | -$36 |
| 2025-05 | $182 | $186 | $0 | $182 |
| 2025-06 | -$748 | -$503 | $0 | -$748 |
| 2025-07 | $525 | $363 | $0 | $525 |
| 2025-08 | -$36 | $226 | -$18 | -$36 |
| 2025-09 | -$573 | -$45 | $27 | -$573 |
| 2025-10 | $5 | $532 | $0 | $5 |
| 2025-11 | $1,005 | $73 | $0 | $1,005 |
| 2025-12 | $462 | $110 | $0 | $6 |
| 2026-01 | $131 | $17 | $323 | $74 |
| 2026-02 | $962 | $390 | $753 | $962 |
| 2026-03 | $301 | -$336 | -$63 | $301 |
| 2026-04 | $51 | $607 | $262 | $51 |
| 2026-05 | $826 | $923 | -$1 | $78 |
| 2026-06 | -$23,458 | -$23,402 | $244 | $1,507 |
| 2026-07 | $698 | $821 | $92 | $765 |
| 2026-08 | $79 | $2,000 | $15 | $79 |
| 2026-09 | $203 | $380 | $127 | $203 |
| 2026-10 | -$2 | $0 | $55 | -$2 |

## Forward shadow workflow

Production authority is none. Frozen shadow policy lists 0 historical finalists. The journal contains 0 real enrollments and 0 observed fills; no historical record is fabricated as a prospective forecast.

Manual commands: node _system/scripts/third_plus_signal_study.cjs build; review-import --input <review JSON>; shadow-import --input <evidence JSON>; shadow-status; verify. Review imports need source/issuer/hash bindings and two independent outcome-blinded reviewers. Shadow enrollment freezes aware source clocks, future entry, policy and input hashes; evidence imports preserve a tamper-evident append-only chain. There is no broker or scheduler command.

A minimum future review point is 50 eligible decisions across 30 issuers. That is not statistical proof or permission to trade. The study requires actual approvals, attempts including failures, fills, all costs and reconciled loan returns to assess executable profit.

## Reproduction and validation

Legacy baseline checks: 10 sessions delta $0; 20 sessions delta $0. The original accounting fixtures and new source/clock/missing-data/journal/portfolio tests are in the test suite. Protocol, source hashes, model manifest and audit aggregates are saved with this report. Raw source extracts, features, per-event returns, and full position ledgers remain in the ignored local directory.

No designated sealed holdout was opened. No paid downloads, Gateway sockets, production policy changes or live orders occurred. No current rate or borrow quantity is backfilled into history. New entries require a fresh verified security and broker evidence even where a conditional historical feature passes.
