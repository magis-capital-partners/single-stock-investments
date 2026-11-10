Announcement observation and SLXN financial repair — November 9, 2026

Quotes are observed independently of fundamental eligibility. Every detected
candidate is registered before enrichment, including an unresolved ticker. The
shared Databento connection warms resolved symbols; no second feed is opened.
Existing recent candidates register late at startup with their original clocks
preserved. Raw books do not imply verified issuer identity. Metadata verification
is bounded to two new requests per observation pass, without blocking evaluation.

Five-second sampled books preserve bid, ask, both displayed sizes, instrument/raw
transport identity and timestamps. This is selected-venue L1, not SIP NBBO, full
tick history, depth, executions or measured impact. Subscriptions remain capped
at 128; unsupported/missing symbols and budget exhaustion remain visible gaps.
Watches extend ten calendar days beyond receipt or the extracted split date.
The observer's active names are retained during subscription rotation.

Pending samples remain in SQLite until immutable private R2 storage acknowledges
their SHA-addressed archive. Archive IDs and latest/first observations survive
checkpoints; failures retain pending bytes. Summary and latest raw download appear
on the authenticated shadow dashboard. Archive records are observations, never
fills. Historical announcement windows are not reconstructed from late samples.

SLXN's June 30, 2026 primary filing reports current related-party promissory debt
of $985,000 and an explicitly tagged noncurrent zero (ixt:fixed-zero). The parser
now understands the XBRL transform and the two reviewed issuer-specific debt
concepts. A bare dash, nil, absent row or a different issuer does not become zero.
Source: SEC accession 0001178913-26-004138, original SHA-256
b206932c4b9a848847c2fccaf2fea76e8693e5356f9c3d8975884be8832877e1.
Replaying current source evidence gives three factors and 56.5, below the frozen
60 threshold. No revenue is imputed, policy threshold changed, or old fill added.
Parser changes archive the complete previous work state before rebuilding it.

Existing sizing chooses displayed/price-budget/borrow-constrained capacity. Borrow
is included in estimated P&L; this is not a calibrated net-edge sizing model.
A prospective model would evaluate each quantity q using:

  expected net P&L(q) = q * (expected sell price(q) - expected cover price(q))
                        - sum(daily shares * collateral mark * APR / 360)
                        - commissions - other expected costs - uncertainty reserve

For USD shorts the illustrative collateral mark is ceil(1.02 * daily stock mark).
Do not subtract spreads twice when they are already in sell/cover prices. Daily
fees and collateral can change; calendar days and unsettled liabilities matter.
The expected cover price must come from a separately validated forward forecast,
not the fundamental score. Missing costs or forecast leave net edge unknown.
Any new edge-based cohort must have a new prospective policy version and must not
rewrite these trial policies, approvals, decisions or simulated records.
