"""One low-priority process that runs the three producers on their cadences.

It holds no broker session, no IB client ID and no vendor login. Its only
network reads are public files (Nasdaq Trader, SEC, IBKR's anonymous
short-stock FTP). It reads Box R's ``operations.json`` from the local copy that
``rs-live-operations`` (``operations-fetch``, #1823) maintains, so it holds no
credential at all. It also reads an optional local file written by a licensed
feed handler the owner has not chosen yet.

Failure policy, per section:

* identity: on an operations or reference failure keep the last rows (each
  carries its own ``at``/``valid_until``; the executor also requires a fresh
  operations snapshot before any proposal);
* borrow: keep the last rows (each carries IBKR's own file clock);
* eligibility: rewrite every row as incomplete. A clear that cannot be
  re-proven is withdrawn, not left to age.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import json
import os
from pathlib import Path
import time

from _system.trading.rs_paper_executor.inbox import read_https
from _system.trading.rs_paper_executor.operations_feed import read_local
from _system.trading.rs_paper_executor.safety import SafetyError, timestamp

from . import sources
from .borrow import build_borrow
from .eligibility import build_eligibility
from .identity import TERMS_MODES, build_identities
from .reviews import Reviews
from .store import EvidenceStore, atomic_write

DEFAULTS = {
    "terms_mode": "owner_review",
    "identity_lookback_seconds": 3600,
    "cadence_seconds": {
        "identity": 15,
        "ibkr_file": 300,
        "borrow": 300,
        "eligibility": 10,
        "halt_feed": 60,
        "restriction_file": 300,
        "references": 21600,
    },
    "eligibility": {
        "max_age_seconds": 30,
        "halt_feed_clears": False,
        "market_status_file": None,
        "approved_status_sources": [],
    },
    "extra_watch": {},
}


def load_config(path):
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    config = {**DEFAULTS, **loaded}
    config["cadence_seconds"] = {**DEFAULTS["cadence_seconds"], **loaded.get("cadence_seconds", {})}
    config["eligibility"] = {**DEFAULTS["eligibility"], **loaded.get("eligibility", {})}
    if config["terms_mode"] not in TERMS_MODES:
        raise SafetyError("terms_mode must be one of " + ", ".join(TERMS_MODES))
    if not config.get("evidence"):
        raise SafetyError("evidence path required")
    # Live reads the local copy rs-live-operations writes (one process holds the
    # R2 credential). An explicit operations_url is for development only.
    if not (config.get("operations_file") or config.get("operations_url")):
        raise SafetyError("Box R operations source required")
    if config["eligibility"]["max_age_seconds"] > 30:
        raise SafetyError("eligibility cannot be configured older than the executor accepts")
    # Nasdaq Trader: the halt feed updates once a minute, "please do not query
    # the data more than once a minute". The restriction file is daily.
    floors = {"halt_feed": 60, "restriction_file": 60, "references": 3600, "ibkr_file": 60}
    for name, floor in floors.items():
        if config["cadence_seconds"][name] < floor:
            raise SafetyError(f"{name} cadence below the source's polling floor ({floor} s)")
    return config


def claimed_watch(path):
    """Conids RS itself holds or has claimed (its own published claims file)."""
    if not path or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != "ib_account_symbol_claims.v1" or data.get("system") != "reverse-split":
        raise SafetyError("claims file is not the reverse-split claims file")
    watch = {}
    for symbol, row in (data.get("claims") or {}).items():
        conid = row.get("conid") if isinstance(row, dict) else None
        if isinstance(conid, int) and not isinstance(conid, bool) and conid > 0:
            watch[conid] = symbol
    return watch


@dataclass
class Fetchers:
    """Network edges, replaceable in tests."""

    https: object = None
    ibkr: object = sources.ibkr_shortstock_ftp
    operations: object = None
    clock: object = sources.utc_now


@dataclass
class State:
    refs: dict = field(default_factory=dict)
    due: dict = field(default_factory=dict)
    restriction: object = None
    halt_feed: object = None
    claims: dict = field(default_factory=dict)
    operations_meta: dict = field(default_factory=dict)


SESSION_TASKS = ("halt_feed", "restriction_file", "eligibility")


def regular_session(now, calendar=None):
    """Within a frozen-calendar session, or in the five minutes before one."""
    from _system.trading.rs_paper_executor.policy import Calendar

    calendar = calendar or Calendar()
    soon = (timestamp(now) + timedelta(minutes=5)).isoformat()
    return bool(calendar.session(now) or calendar.session(soon))


class Producers:
    def __init__(self, config, fetchers=None, in_session=regular_session):
        self.config = config
        self.in_session = in_session
        self.fetchers = fetchers or Fetchers()
        if self.fetchers.https is None:
            ua = config.get("user_agent")
            self.fetchers.https = lambda url: sources.https_get(url, user_agent=ua)
        if self.fetchers.operations is None:
            self.fetchers.operations = self._operations
        self.store = EvidenceStore(config["evidence"], config.get("archive_dir"))
        self.state = State()

    # ----------------------------------------------------------- references
    def _operations(self):
        if self.config.get("operations_file"):
            data, self.state.operations_meta = read_local(self.config["operations_file"])
            return data
        self.state.operations_meta = {}
        return read_https(self.config["operations_url"], os.environ["RS_OPERATIONS_READ_TOKEN"])

    def refresh_references(self, now):
        refs = self.state.refs
        try:
            data, observed = self.fetchers.https(sources.SEC_TICKERS_URL)
            refs["sec"] = sources.parse_sec_tickers(data, observed)
        except Exception as exc:  # keep the previous copy while it is in date
            refs["sec_error"] = type(exc).__name__
        try:
            listings = []
            for name in ("nasdaqlisted", "otherlisted"):
                data, observed = self.fetchers.https(
                    sources.NASDAQ_ROOT + "/dynamic/SymDir/" + name + ".txt"
                )
                listings.append(sources.parse_symbol_directory(data.decode("utf-8-sig"), name, observed))
            refs["listings"] = listings
        except Exception as exc:
            refs["listings_error"] = type(exc).__name__
        for key, limit in (("sec", 36 * 3600),):
            if key in refs and (timestamp(now) - timestamp(refs[key]["as_of"])).total_seconds() > limit:
                refs.pop(key)
        if "listings" in refs and any(
            (timestamp(now) - timestamp(d["as_of"])).total_seconds() > 36 * 3600
            for d in refs["listings"]
        ):
            refs.pop("listings")

    def refresh_ibkr(self, now):
        try:
            data, observed = self.fetchers.ibkr()
            self.state.refs["ibkr"] = sources.parse_ibkr_shortstock(data, observed)
            self.state.refs.pop("ibkr_error", None)
        except Exception as exc:
            self.state.refs["ibkr_error"] = type(exc).__name__
        ibkr = self.state.refs.get("ibkr")
        if ibkr and (timestamp(now) - timestamp(ibkr["as_of"])).total_seconds() > 3600:
            # Too old to map identities from; borrow rows age out on their own clock.
            self.state.refs.pop("ibkr")

    # ------------------------------------------------------------- producers
    def watch(self, evidence):
        watch = {}
        for ticker, row in evidence.get("identities", {}).items():
            if isinstance(row.get("conid"), int):
                watch[row["conid"]] = ticker
        try:
            self.state.claims = claimed_watch(self.config.get("claims_file"))
        except (SafetyError, ValueError, OSError):
            pass  # an unreadable claims file never drops a held name: last good copy
        watch.update(self.state.claims)
        for conid, ticker in (self.config.get("extra_watch") or {}).items():
            watch[int(conid)] = ticker
        return watch

    def run_identity(self, now):
        evidence = self.store.read()
        meta = {"producer": "identity", "generated_at": now, "terms_mode": self.config["terms_mode"]}
        try:
            operations = self.fetchers.operations()
            if self.config.get("operations_mirror"):
                # The executor's --operations-file: the same snapshot, unaltered
                # in content, so one process holds the narrow R2 token.
                mirror = Path(self.config["operations_mirror"])
                mirror.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(
                    mirror,
                    json.dumps(operations, sort_keys=True).encode(),
                )
            reviews = Reviews.load(self.config.get("reviews"))
            rows, report = build_identities(
                operations,
                self.state.refs,
                reviews,
                now,
                terms_mode=self.config["terms_mode"],
                previous=evidence.get("identities"),
                lookback_seconds=self.config["identity_lookback_seconds"],
            )
            for row in rows.values():
                self.store.archive(row["proof"])
            meta.update(status="ok", operations_generated_at=operations.get("generated_at"),
                        operations_downloaded_at=self.state.operations_meta.get("downloaded_at"),
                        report=report)
        except Exception as exc:
            rows = evidence.get("identities", {})
            meta.update(status="degraded_kept_previous", error=type(exc).__name__)
        self.store.write_section("identities", rows, meta)
        return rows, meta

    def run_borrow(self, now):
        evidence = self.store.read()
        meta = {"producer": "borrow", "generated_at": now}
        ibkr = self.state.refs.get("ibkr")
        if ibkr is None:
            rows = evidence.get("borrow", {})
            meta.update(status="degraded_kept_previous", error=self.state.refs.get("ibkr_error", "no_file"))
        else:
            rows, report = build_borrow(ibkr, self.watch(evidence), now)
            meta.update(status="ok", source_as_of=ibkr["as_of"], report=report)
        self.store.write_section("borrow", rows, meta)
        return rows, meta

    def refresh_halts(self, now):
        try:
            data, observed = self.fetchers.https(sources.HALT_URL)
            self.state.halt_feed = sources.parse_halt_feed(data, observed)
        except Exception as exc:
            self.state.halt_feed = None
            self.state.refs["halt_error"] = type(exc).__name__

    def refresh_restriction(self, now):
        day = sources.eastern_day(now)
        try:
            data, observed = self.fetchers.https(sources.shorthalts_url(day))
            self.state.restriction = sources.parse_shorthalts(data.decode("utf-8-sig"), day, observed)
        except Exception as exc:
            if self.state.restriction is None or self.state.restriction["day"] != day:
                self.state.restriction = None
            self.state.refs["restriction_error"] = type(exc).__name__

    def market_status(self, now):
        cfg = self.config["eligibility"]
        if not cfg.get("market_status_file"):
            return None
        try:
            return sources.parse_market_status(
                Path(cfg["market_status_file"]).read_bytes(),
                now,
                allowed_sources=set(cfg.get("approved_status_sources") or ()),
                max_age_seconds=cfg["max_age_seconds"],
            )
        except Exception:
            return None

    def run_eligibility(self, now):
        evidence = self.store.read()
        cfg = self.config["eligibility"]
        restriction = self.state.restriction
        if restriction is not None and restriction["day"] != sources.eastern_day(now):
            restriction = None
        rows, summary = build_eligibility(
            self.watch(evidence),
            now,
            max_age=cfg["max_age_seconds"],
            halt_feed=self.state.halt_feed,
            halt_feed_clears=cfg["halt_feed_clears"] is True,
            restrictions=[restriction] if restriction else [],
            status=self.market_status(now),
        )
        meta = {
            "producer": "eligibility",
            "generated_at": now,
            "status": "ok",
            "summary": summary,
            "halt_feed_as_of": (self.state.halt_feed or {}).get("as_of"),
            "restriction_file_as_of": (restriction or {}).get("as_of"),
            "intraday_ssr_clearance": bool(cfg.get("market_status_file")),
        }
        self.store.write_section("eligibility", rows, meta)
        return rows, meta

    # ------------------------------------------------------------------ loop
    def step(self, now, *, only=None):
        cadence = self.config["cadence_seconds"]
        order = (
            ("references", self.refresh_references),
            ("ibkr_file", self.refresh_ibkr),
            ("identity", self.run_identity),
            ("borrow", self.run_borrow),
            ("halt_feed", self.refresh_halts),
            ("restriction_file", self.refresh_restriction),
            ("eligibility", self.run_eligibility),
        )
        ran = []
        for name, task in order:
            if only is not None and name not in only:
                continue
            if name in SESSION_TASKS and not self.in_session(now):
                # Public exchange pages are polled only around regular hours.
                continue
            due = self.state.due.get(name)
            if due is not None and timestamp(now) < due:
                continue
            task(now)
            self.state.due[name] = timestamp(now) + timedelta(seconds=cadence[name])
            ran.append(name)
        return ran


def run_forever(producers, *, max_seconds, sleep=time.sleep, clock=None):
    clock = clock or producers.fetchers.clock
    start = time.monotonic()
    while time.monotonic() - start < max_seconds:
        producers.step(clock())
        sleep(1)
