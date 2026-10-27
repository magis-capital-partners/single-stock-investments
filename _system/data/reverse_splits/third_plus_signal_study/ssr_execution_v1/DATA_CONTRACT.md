# SSR execution replay input contract

This is an offline research interface. It has no broker connection, transmitter or live authority. Source attestations are statements about inputs, not proof of fills. Do not relabel one-second bars or venue-only BBO as consolidated NBBO.

## Private archive

Place qualified files under the existing cache repository:

~~~
_system/data/reverse_splits/local/third_plus_signal_study/ssr_execution_v1/archive/
  index.local.json
  sessions/<file>.local.json
~~~

The index schema is third_plus_execution_archive.v1. Its sessions array contains event_id, ISO date, kind (entry or cover), relative file, and SHA-256 sha256. Entry keys are the frozen event ID; cover keys are event ID plus cover date. The same event can have multiple cover dates. All input files must remain within the archive, must match the index hash, must have the exact event identity/date, and must not be synthetic. No sealed or holdout paths are permitted. Files and ledgers remain private.

## Session

Each file uses schema third_plus_execution_session.v1, with:

| Field | Meaning |
| --- | --- |
| event_id, issuer, date | Exact frozen split-event ID, SEC issuer and actual trading date |
| open_ms, close_ms | Dated exchange session open/close as UTC epoch milliseconds; include early closes and calendar changes |
| capture_start_ms, capture_end_ms | Actual captured interval. It must cover the required decision/execution window; include acknowledgement/cancel race buffers |
| source_hashes | SHA-256 fingerprints of actual upstream inputs, not only this normalized file |
| volume_scope | direct_unique_venues; never sum consolidated and direct volume |
| evidence | Explicit booleans for identity, consolidated_nbbo, venue_book, eligible_trades, market_status, dated_price_grid, feed_continuity, receipt_clock, route_rules |
| route_rules.initial_display_exception | True only where dated venue/order handling supports retaining initially displayed above-bid eligibility. False triggers a protective price-test cancellation on bid touch |
| native_repricing.verified | Required for E3; attested actual account/security/route support. The mode must be nasdaq_slide_down with a positive minimum_sell_price and source-available available_ms at or before arrival. Native downward repricing resets queue immediately and never crosses the original sell floor. No arbitrary generic peg substitute |
| edge_per_share, edge_available_ms, edge_source_sha256 | Fixed source-available expected net edge before new child commission. Forecast clock must precede the original arrival. Include intended cover/financing costs in the forecast, retain model provenance, and never fit from this trade's future return |
| borrow | Archived broker events with available_ms, expires_ms, whole quantity and nonempty confirmation. A documented denial can have quantity zero. Current inventory is not historical approval |
| locate_cost_usd | Nonnegative actual or explicitly modeled prepaid cost for this parent. It can remain with no entry fill |
| events | Receipt-ordered normalized market/trade records |

An evidence flag should be true only after identity/units, full capture, feed quality, direct/consolidated reconciliation and dated rules have been checked. Missing flags are gaps. The runner does not independently reconstruct or certify external raw feeds. It rejects synthetically marked files and hash/identity mismatches. Lying in an attestation cannot be detected by a JSON schema.

A source-available edge forecast is deliberately required. No new return predictor is trained or optimized by this implementation. Missing forecasts block readiness. The numerical child/window/participation settings remain hypotheses. The parent share budget never expands after a decline, and cumulative entry proceeds are also capped at $100k.

## Atomic market state

A market event has:

- type, ts_ms (source event time), available_ms (receipt/availability time, never before event time).
- venue for the chosen execution venue, bid/ask for the **consolidated** NBBO, and chosen-venue ask ask_size.
- tick and grid_id, from dated route/security price-increment rules.
- status: clear, restricted or unknown; trading: boolean; feed_ok: boolean.
- liquidity_id: identity of the current chosen-venue liquidity state; unchanged heartbeats keep the same identity. Never invent replenishment by assigning a new identity to the same depth.
- book: price-keyed displayed chosen-venue ask depth. It establishes estimated queue ahead at acknowledgement. Inside improvement has zero displayed queue ahead at a genuinely empty price, with hidden-liquidity uncertainty still explicit.
- Optional dynamic net_edge_per_share, with net_edge_available_ms and net_edge_source_sha256; its availability must precede the event receipt.

This atomically reconstructed state combines legal national price and chosen-venue queue fields. It is **not** a raw venue-BBO snapshot renamed NBBO. A normalizer must verify the synchronization and capture provenance first. Quote changes themselves do not provide cancellation credit to our queue. Unchanged healthy heartbeat packets can refresh state without changing price or providing new liquidity. Out-of-order older market states are ignored.

## Trade

A trade event has ts_ms, available_ms, venue, stable venue trade_id, positive price, positive whole size, aggressor (B, S or U), regular, and optional own_execution.

Only regular external direct-venue prints contribute observed-flow budget. Auction/corrected/canceled/nonregular prints and own executions do not. Venue/trade ID deduplicates print records. A passive short additionally requires chosen-venue buyer-initiated eligible flow at or above the working price, after acknowledgement and the applicable market state. Unknown aggressor cannot fill it. No OHLC-to-aggressor inference is accepted.

Order latency is separate from data availability. Captures need honest receipt clocks or explicitly conservative reconstructed receipt times with provenance. The stress grid changes order acknowledgement/cancel latency to 100, 500 and 2,000ms; it does not pretend a sampled second is a true receipt event.

## Portfolio and covers

Use the frozen price/security/calendar loader for marks, split factors and settlement. Its financial inputs are hash checked. Entry and cover files need matching event/issuer/date identities. Covers attempt from 90 to 15 minutes before the original 20th session's actual close. Missing cover capture is an evidence gap. Partial balances retry on later observed sessions and remain marked; fractions are not silently closed.

Cover orders can take the current ask only within parent/observed-flow budgets and available displayed liquidity. One unchanged liquidity identity cannot be consumed twice. The counterfactual effect of the strategy on other participants, hidden depth and replenishment remains a modeling limitation; compare to own executions before sizing up.

Carry uses the prior available mark after share-unit changes, modeled 102%-rounded collateral, calendar-day APR/360, settlement and known loan returns. Actual financing, recalls, dividends, taxes, venue fee/rebate schedules and operations need observed inputs or separate cost experiments. The dated modeled fixed-commission schedule is reused from the prior framework; it is not a broker invoice.

## Results and limitations

The runner evaluates 21 frozen signals, E0-E3, 30/60 minutes, 5/10% observed flow, three latencies and conditional/archived-approval borrow modes. Incomplete entry paths make the portfolio not_estimable with **null** performance, including the effect of unknown earlier positions on later name slots. Missing exits produce incomplete_exit_evidence; any ledger values are partial-path diagnostics, not complete strategy performance.

Complete source-attested paths produce **conditional simulations**, not verified historical or live fills. Selection claims require complete matched paths, uncertainty/multiple comparisons, concentration, stress and future execution calibration. Empty-signal arms can legitimately have zero P&L because they have no eligible decisions; this is different from missing execution data.

The cache audit and request manifest use no external service. No positive-cost purchase or holdout access is authorized by running the scripts. Qualified normalized input acquisition is a separate unresolved data task.
