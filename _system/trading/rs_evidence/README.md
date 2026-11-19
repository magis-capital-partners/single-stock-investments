# RS evidence producers

These are the three producers behind the RS executor's evidence file
(`rs_paper_reviewed_evidence.v1`; see `../rs_paper_executor/README.md`, section
"Input contract and missing access"). Without them every candidate is refused
at the evidence step.

They hold no broker session, no IB client ID and no vendor login. Their only
reads are:
* public files from Nasdaq Trader, the SEC, and IBKR's anonymous short-stock
  FTP;
* Box R's `operations.json`, from the local copy that `rs-live-operations`
  (#1823's `operations-fetch`) writes to `/var/lib/rs-live/feed`. The
  producers hold no credential;
* optionally, a local file written by a licensed market-status handler. The
  owner has not picked that source yet.

They never touch the IB Gateway, ThetaData, Databento, NY4's SPX services or
Box R. **Nothing here is installed anywhere.** `rs-evidence-producers.service`
and `.timer` are uninstalled templates, like the executor's.

## Sections and rules

| Section (owner) | Key | Source | Freshness the executor demands |
| --- | --- | --- | --- |
| `identities` (`identity.py`) | ticker | Box R candidate, SEC `company_tickers_exchange.json`, Nasdaq SymDir, IBKR `usa.txt`, owner review | `at` ≤ 24 h, before `valid_until` |
| `borrow` (`borrow.py`) | str(conid) | IBKR `usa.txt` (`#BOF` clock is `at`) | ≤ 1800 s |
| `eligibility` (`eligibility.py`) | str(conid) | Nasdaq halt RSS, Nasdaq dated Rule 201 file, licensed handler | ≤ 30 s |

**Identity.**
* Automated: CIK↔ticker (SEC), ticker→conid/USD (IBKR file; the executor
  re-proves it at `qualify()`), common share (named common/ordinary share in
  Nasdaq's directory, otherwise `UNRESOLVED`), `action_source_sha256` (from the
  candidate) and `action_day` (the earliest of Box R's effective, legal and
  trading dates).
* Ratio and `conditions_resolved` follow `terms_mode`:
  * `owner_review` (the default) needs an attestation (`review` command)
    bound to the candidate ID, its CIK and its source hash. Until one exists,
    the row is written `verified: false` with the proposed terms.
  * `box_r_auto` accepts Box R's own extraction. That needs Box R to export
    `ratio`/`ratio_candidates` in `operations.json`, which it does not do
    today.
* A row whose content has not changed keeps its first `at`.
* Only the first live record of an action is an opportunity (owner
  2026-11-19):
  * `publication_clock` must be Box R's `timestamp`. A date-only SEC
    daily-index record, an undated archive catch-up or an `unknown` clock gets
    `verified: false` (`publication_clock_<value>`). A date-only clock can look
    fresh to the executor's 15-minute window the next morning.
  * A later scheduled record of the same issuer and action day is a duplicate
    publisher record. It gets no row, and `report` names `duplicate_of`.
    Unknown action days count as possible duplicates.
  * Synthetic controls never get a row.

**Borrow.** These are public indications only (`availability_only: true`,
`locate_approved: false`). **They are not allocations**, and a successful
WhatIf margin preview does not establish borrow availability (owner
2026-11-19). A conid that is missing from the file gets no row; it never gets
zero.
Watched conids are:
* identity conids;
* conids in RS's own claims file (the last good copy if that file is
  unreadable);
* `extra_watch`.

**Eligibility.**
* `True` (restricted) can come from any fresh source that lists the symbol.
* `False` (clear) can come only from a per-symbol source that the owner
  approved for clearing:
  * the halt RSS, if `halt_feed_clears` is set;
  * a licensed handler file whose source is in `approved_status_sources`.
* Absence from Nasdaq's daily Rule 201 file is never clearance.
* `at` is the oldest deciding input.
* With no intraday SSR source (today's state), every row is
  `ssr: null, complete: false`, and the executor refuses every entry with
  "fresh eligibility source required". In shadow only, it then runs the
  later gates and records a conditional would-be entry (owner 2026-11-19,
  option B; see the executor README). That is why an incomplete row's `at`
  is the write time: a row that stops being rewritten goes stale, and the
  shadow path refuses it as well.
* If the halt feed fails, every row is rewritten as incomplete.

**Polling floors** (enforced by `load_config`):
* halt RSS ≥ 60 s. Nasdaq says the feed updates once a minute and asks
  that it not be polled more often.
* Rule 201 file ≥ 60 s; IBKR file ≥ 60 s (IBKR rewrites it about every 15
  minutes); SEC and SymDir references ≥ 1 h.

The halt feed's 60 s cycle and the 30 s limit mean a free-halt clearance can be
fresh for only part of each minute. A licensed handler is what makes the halt
and SSR components fresh enough for every cycle.

## Exact missing fields, IBKR capabilities and proposed cost (owner 2026-11-19)

The owner's order: identify these before buying anything. Nothing has been
bought. `status` prints `entry_gaps` for the live evidence file: the field
that blocks each name, by the executor's own checks (`gaps.py`).

**What blocks every entry today**

| Executor field | Today | What closes it |
| --- | --- | --- |
| `identities.ratio`, `conditions_resolved` | **Missing** until an owner review (`owner_review_required`) | The `review` command per candidate, or `box_r_auto` plus Box R exporting `ratio` |
| `identities.type` for unnamed NYSE names | `UNRESOLVED` (144 of 7,687 in `otherlisted`) | OpenFIGI fallback (free), if the owner approves it |
| `identities` for date-only or catch-up records | Refused by design | Nothing: these are not opportunities |
| `identities.cik` cross-check | Needs the SEC User-Agent contact in the config | The owner supplies it |
| `borrow.apr`, `available_shares` | Present: IBKR public file, about every 15 min | An indication, never an allocation (see below) |
| `eligibility.halted = false` | Restriction yes, clearance **no**: the RSS clears only with `halt_feed_clears` (off) | The owner's `halt_feed_clears` call, or a licensed handler |
| `eligibility.ssr = false` | **Missing.** No free per-symbol intraday clearance exists | A licensed status feed (below) |
| `eligibility.complete`, `source_verified` | False on every row, because SSR is missing | Same |

**What IBKR already offers** (from IBKR's documentation; nothing was
connected to check it):

| Capability | What it gives | Usable for RS? |
| --- | --- | --- |
| TWS API generic tick 236: tick 46 `Shortable`, tick 89 `Shortable Shares` | Shortable level (>2.5: at least 1000 shares; >1.5: if a locate is found) and a share count | **Already used:** the executor caps size by tick 89. Both are indications, not allocations |
| Public FTP `usa.txt` | `FEERATE`, `REBATERATE`, `AVAILABLE` per conid, about every 15 min | **Already used** by `borrow.py`. Indications. IBKR's tick page names this file as the source for the fee rate |
| TWS API tick 49 `Halted` | 1 general halt, 2 volatility halt; **0 "only if the contract is in a TWS watchlist"**; -1 unavailable | Proves *halted*, never *not halted* on a Gateway. Already merged as a restriction |
| SSR / Rule 201 in the TWS API | **None.** No tick or field documents a short-sale restriction | No |
| Web API snapshot fields 7636/7637/7644 (shortable shares, **fee rate**, shortable) | A live indicative fee rate | **No, not on NY4.** A Web API brokerage session is one per username, and a competing login can end the other session. It would compete with the SPX Gateway's login. It needs a second username |
| Pre-borrow (TWS API: `secType SBL`, exchange `PREBORROW`, BUY `MKT`) | **The only real allocation IBKR offers** | Needs a Portfolio Margin account, the Pre-Borrow permission and a **$10,000 minimum** (an older guide says $100,000). It costs a $20 ticket fee plus a $20 borrow fee, a fill is not guaranteed, and unused shares are returned after about one settlement cycle. **It cannot serve pilot names of $5,000** |
| Flex Borrow Fee Details (Box R already reads it) | Rates actually charged on held loans, after the fact | Reconciliation only, not pre-trade |

So without a pre-borrow, borrow is established only when the short order
executes; IBKR locates at order time. A WhatIf preview does not establish it.

**Proposed subscription** (none bought; owner's call):
* **IEX TOPS, $1,000/month licence**, plus connectivity, which has not been
  quoted. It is the cheapest source that gives per-symbol Rule 201 state and
  halts for every listing market. A handler writes the plug-point file below.
* The alternatives cover Nasdaq-listed names only:
  * Databento XNAS.ITCH status: about $3,300/month, and another Databento
    session.
  * Nasdaq Basic through Databento: $1,680/firm + $14.10/user, plus the plan.
* A SIP through a vendor: cost unverified.

The full table and citations are in the design note.

**The owner's shadow acceptance gate needs a source.** That gate is three
fully gated, deduplicated issuer/action opportunities from three issuers
over two or more sessions. "Fully gated" includes eligibility, which cannot
pass while SSR is unknown. Option B's conditional entries
(`fully_gated: false`) show the later gates working, but they cannot meet
the gate.

## Licensed handler file (the plug point)

`rs_market_status.v1`, written by the handler for whichever source the owner
picks:

```json
{"schema": "rs_market_status.v1", "source": "<name in approved_status_sources>",
 "gapless": true, "current_as_of": "<UTC ISO of last sequenced message or heartbeat>",
 "coverage": ["XNAS", "..."],
 "symbols": {"ABC": {"halted": false, "ssr": false}}}
```

`gapless: true` is the handler's assertion that its session has no sequence
gap. A symbol the file does not list is unknown, never clear.

## Commands

```text
python -m _system.trading.rs_evidence once   --config /etc/rs-live/producers.json [--only identity,borrow]
python -m _system.trading.rs_evidence run    --config /etc/rs-live/producers.json
python -m _system.trading.rs_evidence status --config /etc/rs-live/producers.json
python -m _system.trading.rs_evidence review --config /etc/rs-live/producers.json --candidate <id> --ratio 10 --action-day 2026-11-25 --by <initials>
```

The config needs:
* `user_agent`, the SEC fair-access contact. The owner supplies it; the code
  never invents one.
* `operations_file`: `/var/lib/rs-live/feed/operations.json`, the copy
  `rs-live-operations` maintains. The fetcher's `operations.meta.json`
  `downloaded_at` is recorded beside Box R's `generated_at` in the identity
  producer's meta. `operations_url` (with `RS_OPERATIONS_READ_TOKEN`) is for
  development only. A bucket-scoped R2 read token does not work with the
  Cloudflare REST URL, which is why #1823 moved the fetch into its own
  process.
* `operations_mirror` is off by default and not needed on NY4.

Install steps for NY4 are in `../rs_paper_executor/NY4_SHADOW_INSTALL.md`,
section 7.

## Verification

```text
python -m pytest -q _system/trading/tests/test_rs_evidence_producers.py _system/trading/tests/test_rs_evidence_owner_rules.py _system/trading/tests/test_rs_shadow_conditional.py
python -m ruff check _system/trading/rs_evidence _system/trading/tests/test_rs_evidence_producers.py --select F
```

The tests reuse Box R's captured halt feed and Rule 201 file. They run the
producers into an evidence file and pass it through the executor's own
`inbox.proposals()`, `PaperIBKR.eligibility()` and `Executor.eligibility()`.
No socket is opened.
