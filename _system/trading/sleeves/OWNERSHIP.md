# Strategy ownership and corrections

The daily Flex batch prepares `ownership-current.json` in the private realized
state directory before publishing any owner book. Configure
`SLEEVE_OWNERSHIP_REGISTRY` to that file and `SLEEVE_OWNERSHIP_REQUIRED=1`.
`SLEEVE_LS_UNIVERSE_ROOT` optionally points to the existing LS daily run files.
No Gateway connection, order submission or market-data request is involved.

Executed broker `ETF_LS|` and `B5P|` references prove LS ownership. Documented
`ETF_LS|MANUAL|SELLPUT|` and `SELLCALL|` option overlays belong to Drew. Proposed
trades, submission claims, client IDs and simulated ledgers are not execution
evidence. Opening transaction/trade identifiers are scoped by account, conId,
model and ID domain. Exact opening timestamps are a secondary match only when
all matching executions agree. Canceled/conflicting evidence requires review.

Closed lots inherit their opening owner, including a human exit of an LS lot.
An LS exit of a human lot requires review. Broker Closed Lots must conserve
both quantity and P&L before any split is used. HIFO is never reconstructed from
chronological fills. Missing links, transfers, assignments, corporate changes,
reversals or shared lots cannot invent a human allocation: known LS contracts
and dated candidate universes move ambiguous lots outside confirmed totals.
Dated universes never prove an execution or retroactively claim earlier lots.
Existing dated custody rules and protected SPX/ETF books remain in force.

Current positions are classified before aggregation; signed quantities, native
costs, stated FX and unrealized P&L are summed by owner/strategy. One signed
account snapshot carries the ownership version, allocations and exact owner
economics. D1 activates broker positions and allocations in one transaction;
validation requires quantity and value conservation. Older separate allocation
publishers cannot overwrite this projection. Missing canonical allocations do
not invoke Michael's historical residual fallback. Legacy sleeve synchronization
uses the same registry and cannot overwrite matched lots with ticker tags.

Historical inference policies remain frozen. The new ownership version is an
explicit evidence correction applied across history. Every record and CSV
includes that version; immutable registry JSON and original XML are compressed
and archived privately in R2 with checksums. The JSON artifact is labeled as
JSON in the source manifest. Never commit account data, identifiers or reports.

Before rollout, save the prior build privately, build the candidate, then run
`ownership_audit.audit_changes(before, after)`. It refuses changes to record
identities, quantities, reported P&L, FX, costs, proceeds or commissions. Keep its
per-record owner transitions and before/after totals privately. Review ambiguous
lots in Portfolio → Reconciliation and realized coverage notes; they are absent
from confirmed owner totals. Publication is staged and idempotent; repeat a
failed upload to finish it. Daily preparation failure leaves the hosted books
unchanged, and no retry loop contacts the Gateway.

For rollback retain the previous complete D1 source run and realized generation,
their immutable R2 sources, the previous registry and local SQLite backups. Rebuild
the prior code/registry pair into a NEW source run and realized generation; never
edit a completed generation or restore the old permissive residual publisher.
The current realized pointer may also be returned to its previously verified
generation by an authenticated operator after checking the corresponding source
run. Reconcile both ownership versions before serving a combined view.
