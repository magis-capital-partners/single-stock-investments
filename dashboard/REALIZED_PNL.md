# Drew and Michael realized history

The tabs display IBKR-reported realized amounts independently of open holdings.
Partial closures, zero-profit closures, option booking events and reported
realizations on opening-marked executions are retained. Quantity is omitted when
the closed portion cannot be established. Realizations retained by IBKR on
canceled/rebooked executions are accounting adjustments, not active fills.

## Sources and ownership

The daily producer reuses `flex_trades.xml` and `flex_positions.xml` from the same
completed session in `/home/spx/ls-algo/data/runs/<session>/ibkr_flex/`. Reading
these files makes no IBKR request. Explicit supplemental retrieval uses only
Flex HTTPS, never a trading login, market-data subscription or Gateway socket.

The saved account setup confirms HIFO matching. Never reconstruct FIFO from
executions. Exact shared-owner attribution requires broker Closed Lots matches.
The currently archived trade query contains EXECUTION rows and no Closed Lots.
3905.T without its opening-lot match stays unallocated. Existing owner policy
inference is labeled; it is not promoted to authoritative evidence.

Initial policy membership is frozen with its historical-inference basis. Later
membership changes receive effective dates and do not rewrite earlier records.
Documented allocations are append-only evidence rules with author and reason.
Strategy exclusions precede owner overrides.

## Supplemental report setup

Create a separate Activity Flex query in Client Portal, preserving all existing
production queries. Include Trades with Closed Lots and the identifiers linking
opening lots to closing executions, opening date/time, closed quantity, basis,
realized P&L, currency/FX and full security identity. Include Corporate Actions
and Option Exercises/Assignments/Expirations when available. Inspect a small
report to validate its actual linkage and detail levels before backfilling.

The separate query `1687504` was validated against its 2026 YTD XML: Executions,
Closed Lots, audit identifiers, opening timestamps, currency conversion rates,
corporate actions, option events and the broker P&L summary are present. IBKR
emits `<Lot>` siblings immediately after their closing `<Trade>`; a Lot's
`transactionID` refers to the opening transaction. Keep both identities separate.
Sibling association requires matching contract/time/currency/model/direction,
and lot quantities and P&L must reconcile before they inform owner allocation.

Store `SLEEVE_CLOSED_LOTS_QUERY_ID` in the existing portfolio publisher's private
environment file. The daily wrapper retrieves a 35-day overlap only after the
primary EOD service has finished, using its established Flex reporting token in
a subprocess. It does not generate or rotate credentials. If this ID is absent,
the dashboard states that Closed Lots have not been received.

## Private runtime and commands

Run from the SSI copy using the portfolio-hub Python environment. Set the account
from the established private environment, not a committed default. The state
directory is `/home/spx/portfolio-hub/sleeve-realized` on NY4.

```bash
python -m _system.trading.sleeves.realized_cli --state "$STATE" --account "$ACCOUNT" \
  import /private/path/flex_trades.xml /private/path/flex_positions.xml
python -m _system.trading.sleeves.realized_cli --state "$STATE" --account "$ACCOUNT" \
  fetch --query-id "$CLOSED_LOTS_QUERY_ID" --from 2026-01-01 --through 2026-10-26
python -m _system.trading.sleeves.realized_cli --state "$STATE" --account "$ACCOUNT" \
  build --output /private/path/reconciliation.json
python -m _system.trading.sleeves.realized_cli --state "$STATE" --account "$ACCOUNT" publish
```

For older execution history, use `fetch --role executions --query-id
"$TRADES_QUERY_ID" --from YYYY-MM-DD --through YYYY-MM-DD`. Requests are split
into calendar months, including leap years. `--refresh` obtains restatements of
cached periods. Use the established Flex environment, serialize with the primary
producer, and never put the token in command arguments or logs. No report beyond
the service's actual availability is represented as complete coverage.

`assign /private/path/rule.json` records an ownership correction. A rule requires
`account`, `owner`, `author`, and `reason`, plus either an exact `record_id` or
`conid` with `opening_from` and `opening_through`. Keep rules private. Specific
opening lots, not the current aggregate ticker balance, determine ownership.

## Publication and recovery

Original XML is gzip-archived locally and uploaded as checksummed parts into the
existing private R2 bucket. The manifest lists ordered part checksums; concatenate
the numbered objects and decompress to recover the original report. Its SHA-256
must equal the source report ID. Normalized batches and manifests are archived
there too, under `sleeves/realized/`.

D1 stages normalized records and exact daily totals under an immutable generation.
Its active pointer changes only after all expected batches, source archives and
row counts are present. Interrupted uploads can replay safely. Requests use the
existing sleeve HMAC, shared nonce replay protection, strict bounded bodies and
the existing verified-owner read policy. There is no public static export.

The daily wrapper has no restart loop. A failure preserves the previous active
generation and logs a separate realized-history status. Source period mismatch,
missing reports, stale files and account mismatch fail closed. A new calendar
year retains prior years. Deployment retention removes only old derived
generations, keeping at least three and a week of completed cursor versions;
the active full history and source archives are retained.

## Accounting boundaries

- Realized amounts already include commissions where IBKR reports them net.
- Native amounts and broker FX are preserved; missing FX never becomes 1.
- Financial aggregation uses Decimal/BigInt, not floating-point SQL sums.
- Settlement target reached is not confirmed cash settlement. Status is based
  on the completed statement date, never today's wall clock.
- Periods default to realization date; settlement-target date is an explicit
  alternative. Missing settlement dates cannot satisfy that date filter.
- Missing lot matches, unsupported corporate actions and unreconciled summary
  differences are disclosed. No profit is invented from disappearing inventory.
- Broker summary reconciliation and owner allocation completeness are separate.
  The view does not claim NAV, account cash, time-weighted returns or tax advice.

## Validation and rollout

Run `python -m pytest -q _system/trading/sleeves/tests` and
`node --test dashboard/cloudflare/test-realized.mjs`, the existing portfolio hub
suites, the Gateway registry scanner, retention tests and Pages bundle checks.
Real-data reconciliation outputs belong only in private storage; committed
fixtures use synthetic identifiers and amounts.

Merge the code, apply the D1 migration through the existing Pages deployment,
copy the changed Python modules and daily wrapper to NY4, import/reconcile the
initial history, then publish and confirm the active generation's rows and
coverage. A repository merge alone does not update NY4's unversioned copy.
Do not restart or otherwise touch the Gateway or its service for this feature.
