# RS evidence producers

These are the three producers behind the RS executor's evidence file
(`rs_paper_reviewed_evidence.v1`; see `../rs_paper_executor/README.md`, section
"Input contract and missing access"). Without them every candidate is refused
at the evidence step.

They hold no broker session, no IB client ID and no vendor login. Their only
reads are:
* public files from Nasdaq Trader, the SEC, and IBKR's anonymous short-stock
  FTP;
* Box R's `operations.json`, through the executor's own narrow read path;
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

**Borrow.** These are public indications only (`locate_approved: false`). A
conid that is missing from the file gets no row; it never gets zero.
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
  "fresh eligibility source required".
* If the halt feed fails, every row is rewritten as incomplete.

**Polling floors** (enforced by `load_config`):
* halt RSS ≥ 60 s. Nasdaq says the feed updates once a minute and asks
  that it not be polled more often.
* Rule 201 file ≥ 60 s; IBKR file ≥ 60 s (IBKR rewrites it about every 15
  minutes); SEC and SymDir references ≥ 1 h.

The halt feed's 60 s cycle and the 30 s limit mean a free-halt clearance can be
fresh for only part of each minute. A licensed handler is what makes the halt
and SSR components fresh enough for every cycle.

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
* `RS_OPERATIONS_READ_TOKEN` in the environment when `operations_url` is
  used.

Box R's operations URL and token come from `RS_OPERATIONS_URL` and
`RS_OPERATIONS_READ_TOKEN` in the same root-only `EnvironmentFile` the executor
unit uses, unless the config names `operations_file`/`operations_url`.
`operations_mirror` (off by default) writes a copy for an executor run with
`--operations-file`. The live unit now reads the URL itself.

## Verification

```text
python -m pytest -q _system/trading/tests/test_rs_evidence_producers.py
python -m ruff check _system/trading/rs_evidence _system/trading/tests/test_rs_evidence_producers.py --select F
```

The tests reuse Box R's captured halt feed and Rule 201 file. They run the
producers into an evidence file and pass it through the executor's own
`inbox.proposals()`, `PaperIBKR.eligibility()` and `Executor.eligibility()`.
No socket is opened.
