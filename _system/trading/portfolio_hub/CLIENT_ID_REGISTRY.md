# IB Gateway client and order ownership ADR

Status: implemented. The machine-readable registry is authoritative.

## Canonical registry

Source: `_system/trading/ib_gateway_client_registry.v1.json`

- Registry version: `2026-09-09.1`
- Canonical SHA-256: `3d2ba10bda3a577696e8e85ae5a6efd1a934e33341ade782506b79f0bad82abd`
- Local validation:
  `python _system/scripts/check_ib_gateway_registry.py --skip-mirrors`
- Manual cross-repo mirror validation:
  `python _system/scripts/check_ib_gateway_registry.py`

Prose tables do not allocate IDs. A new or changed ID must land in the canonical
JSON and all repo mirrors before first use.

| SSI role | Client ID | Access/status | Connection rule |
|---|---:|---|---|
| Legacy Drew sleeve | 71 | transmit / active | Legacy sleeve path only |
| Legacy Michael sleeve | 72 | transmit / active | Legacy sleeve path only |
| Legacy sleeve sync | 73 | read-only / active | Must connect with `readonly=True` |
| Retired collector | 81 | none / disabled-reserved | **Never connect or re-enable** |
| Future observer | 82 | none / reserved | Reservation metadata; **never connect** |
| Portfolio hub order bridge | 91 | transmit / active | Exact human ticket only; sole hub transmitter |

The cross-system allocation is SPX 17/18/19/87/88/97; LS client 0 is
disabled-reserved because `ib_insync` auto-binds open orders for client zero.
LS client 83 is the read-only stale-order interlock, with 41/77/90/198 plus leased pool 100–129;
etf-0dte uses 50/51 (SPY/QQQ executors) and 130/131 (their +80 watchdogs);
SSI uses 71/72/73/81/82/91. Retired
IDs and ranges are recorded in the same JSON and may not be reused.

## Connection invariant

`_system.trading.ib_gateway_registry.assert_ssi_client_id` runs immediately
before both SSI raw Gateway connect paths. It proves ownership, role, status,
access, and read-only requirements before a socket opens. The CI scanner also
covers raw connects, Python CLI/environment defaults, TOML/YAML/JSON config,
shell defaults, and systemd settings. Historical Markdown prose is excluded
from allocation scanning.

The idle portfolio hub holds zero Gateway sessions. Client 91 is created only
in response to a specific human ticket, is bounded to that work, and is closed
in a `finally`. The command loop polls D1 over HTTPS, not Gateway. Broker truth
comes from Flex over HTTPS. There is no collector and no recurring Gateway
session.

Gateway restart authority remains outside SSI. A failed ibc_guard handshake
does not establish that every client is disconnected. Any spx-0dte remedial
restart requires independent evidence that the protected executor is dead in
addition to the guard's other limits.

## Recovery invariant

Before accepting commands, startup recovery reads open orders, classifies each
one by positive ownership, and refuses an unresolved `MAGIS|` namespace.
Uncertain-send reconciliation also checks completed orders. Manual,
foreign, and legacy orders are visible and never bound, modified, or cancelled.
`reqGlobalCancel` is prohibited.

Positive hub ownership requires all three: a `MAGIS|` orderRef, the configured
account, and client ID 91. `find_owned_order`, startup recovery, and cancellation
enforce the same tuple. If transport fails after `placeOrder` and before
acknowledgement, the intent becomes `SubmitUncertain`. Retry is prohibited until
reconciliation by that ownership tuple plus broker IDs and executions resolves
the state.

## Live gate

Live mode remains disabled until SPX and LS stamp and soak positive orderRefs, all working orders classify, Gateway restart/cancel-fill-race/partial-fill/uncertain-send scenarios pass, the watchdog and backups are active, and a capped allowlisted live canary is explicitly approved.
