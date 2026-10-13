"""SEC filing checks for price-detected reverse splits, and the rename join.

Both come from EDGAR full-text search (efts; free; 2001 onward). One fact shapes
everything here: EDGAR display names carry an issuer's *current* tickers, so a
company that was renamed, acquired or delisted shows none, or a different one.
The ticker in use at the time survives only in the filing text (the 8-K cover
page lists the trading symbol).

``confirm(ticker, day)`` looks for a filing from 200 days before to 45 days
after the detected session that says reverse stock split, reverse split,
reverse share split, share consolidation or ADS ratio, together with the
ticker:

- ``display_ticker``: an issuer whose display name lists the ticker today.
- ``ticker_text``: the issuer with the most such filings whose text carries the
  ticker. This is weaker evidence, and it is skipped for tickers shorter than
  three letters, which collide with ordinary words.

``issuer_cik`` names the issuer a symbol belonged to near a date. The rename
join uses it: a ledger event kept under today's ticker is matched to a detection
near its date, with the same ratio, whose issuer has the ledger's CIK.

Answers are cached in ``reports/filing_checks.json``, so a long run resumes.
EDGAR errors are retried and never cached as "not found". Every request goes
through the package's ``RateLimitedSession`` with the configured User-Agent.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

URL = "https://efts.sec.gov/LATEST/search-index"
PHRASES = ('"reverse stock split"', '"reverse split"', '"reverse share split"', '"share consolidation"', '"ADS ratio"')
BEFORE_DAYS, AFTER_DAYS = 200, 45
MIN_TEXT_TICKER = 3
RENAME_DAYS = 5
RENAME_RATIO_TOLERANCE = 0.30


class SearchError(RuntimeError):
    """EDGAR kept failing for one query; the answer is unknown, not negative."""


def tickers_in(display_names) -> set[str]:
    """``"Workhorse Group Inc.  (WKHS, WKHSW)  (CIK 0001425287)"`` -> {WKHS, WKHSW}."""
    out = set()
    for name in display_names or []:
        for group in re.findall(r"\(([^)]*)\)", str(name)):
            for token in group.split(","):
                token = token.strip().upper()
                if token and not token.startswith("CIK"):
                    out.add(token)
    return out


def cik_of(source: dict) -> str | None:
    ciks = source.get("ciks") or []
    return str(ciks[0]).zfill(10) if ciks else None


# Forms an issuer files about itself, with its own symbol on the cover. A
# prospectus or a registration statement mentions other companies' tickers.
ISSUER_FORMS = frozenset({"8-K", "8-K/A", "6-K", "6-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A",
                          "DEF 14A", "PRE 14A", "DEFA14A", "DEF 14C", "PRE 14C"})


def _form(src: dict) -> str | None:
    return (src.get("root_forms") or [src.get("form")])[0]


def _text_issuer(ticker: str, hits: list[dict]) -> dict | None:
    """The issuer whose own filings carry the ticker in their text. A company
    whose display name lists other live tickers needs two such filings, so one
    passing mention by an unrelated issuer does not count."""
    own = [s for s in hits if _form(s) in ISSUER_FORMS and cik_of(s)]
    votes = Counter(cik_of(s) for s in own)
    for cik, n in votes.most_common():
        filings = [s for s in own if cik_of(s) == cik]
        live = set().union(*(tickers_in(s.get("display_names")) for s in filings))
        if live and ticker not in live and n < 2:
            continue
        return filings[0]
    return None


def _found(src: dict, phrase: str, method: str) -> dict:
    return {
        "status": "filing_confirmed",
        "method": method,
        "phrase": phrase.strip('"'),
        "accession": src.get("adsh"),
        "form": _form(src),
        "filed": src.get("file_date"),
        "cik": cik_of(src),
        "entity": (src.get("display_names") or [""])[0][:120],
    }


class FilingSearch:
    def __init__(self, http, cache_path: Path | None = None, retries: int = 4, backoff: float = 2.0):
        self.http, self.cache_path, self.retries, self.backoff = http, cache_path, retries, backoff
        self.cache: dict = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path and cache_path.exists() else {}
        self.requests = 0

    def save(self) -> None:
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = dict(self.cache)  # one C-level copy; other threads may be adding entries
            self.cache_path.write_text(json.dumps(snapshot, indent=0, sort_keys=True), encoding="utf-8")

    def search(self, q: str, start: date, end: date, cik: str | None = None) -> list[dict]:
        params = {"q": q, "dateRange": "custom", "startdt": start.isoformat(), "enddt": end.isoformat()}
        if cik:
            params["ciks"] = str(cik).zfill(10)
        last = None
        for attempt in range(self.retries):
            self.requests += 1
            try:
                payload = self.http.get(URL, params=params).json()
                return [hit.get("_source") or {} for hit in (payload.get("hits") or {}).get("hits") or []]
            except Exception as exc:  # noqa: BLE001 - EDGAR answers 500/429 intermittently
                last = exc
                time.sleep(self.backoff * (attempt + 1))
        raise SearchError(f"{q} {start}..{end}: {last}")

    def confirm(self, ticker: str, day: date) -> dict:
        key = f"confirm|{ticker.upper()}|{day.isoformat()}"
        if key in self.cache:
            return self.cache[key]
        ticker = ticker.upper()
        lo, hi = day - timedelta(days=BEFORE_DAYS), day + timedelta(days=AFTER_DAYS)
        result = {"status": "not_found"}
        for phrase in PHRASES:
            hits = self.search(f'{phrase} "{ticker}"', lo, hi)
            shown = next((s for s in hits if ticker in tickers_in(s.get("display_names"))), None)
            if shown:
                result = _found(shown, phrase, "display_ticker")
                break
            if hits and len(ticker) >= MIN_TEXT_TICKER:
                best = _text_issuer(ticker, hits)
                if best:
                    result = _found(best, phrase, "ticker_text")
                    break
        self.cache[key] = result
        return result

    def issuer_cik(self, ticker: str, day: date) -> str | None:
        """The issuer a symbol belonged to near ``day``: from a confirmed filing
        when there is one, else from filings near the date that list or carry it."""
        confirmed = self.confirm(ticker, day)
        if confirmed.get("cik"):
            return confirmed["cik"]
        key = f"issuer|{ticker.upper()}|{day.isoformat()}"
        if key not in self.cache:
            hits = self.search(f'"{ticker.upper()}"', day - timedelta(days=60), day + timedelta(days=30))
            shown = [cik_of(s) for s in hits if ticker.upper() in tickers_in(s.get("display_names")) and cik_of(s)]
            self.cache[key] = Counter(shown).most_common(1)[0][0] if shown else None
        return self.cache[key]


def rename_matches(event: dict, detections: list[dict]) -> list[dict]:
    """Detections that could be a ledger event recorded under a later ticker:
    within ``RENAME_DAYS`` of its ex date and, when the ledger has a ratio, with
    an inferred ratio within ``RENAME_RATIO_TOLERANCE`` of it."""
    ex = date.fromisoformat(str(event["ex_date"])[:10])
    ratio = event.get("ratio")
    want = 1.0 / float(ratio) if ratio else None
    out = []
    for det in detections:
        day = det["day"] if isinstance(det["day"], date) else date.fromisoformat(str(det["day"]))
        if abs((day - ex).days) > RENAME_DAYS or det["symbol"].upper() == str(event["ticker"]).upper():
            continue
        if want and abs(float(det["ratio_inferred"]) / want - 1) > RENAME_RATIO_TOLERANCE:
            continue
        out.append(det)
    return out


def run_checks(cfg, log=print, limit: int | None = None, workers: int = 3) -> dict:
    """Confirm every corroborated, listed, detector-only event in the detector
    report, then try the rename join for every listed ledger event it missed.
    Writes ``reports/filing_checks.json`` (cache) and ``reports/rename_joins.json``.

    EDGAR answers in seconds, so ``workers`` searches run side by side, each on
    its own rate-limited session and all on one cache; three stay well inside
    SEC's ten-requests-a-second fair-use limit."""
    import csv
    from concurrent.futures import ThreadPoolExecutor

    from .utils import RateLimitedSession

    reports = cfg.reports_dir
    edgar = cfg.raw.get("edgar") or {}

    def session():
        return RateLimitedSession(edgar.get("user_agent", "ReverseSplitResearch research@localhost"),
                                  max(0.25, float(edgar.get("request_delay_seconds", 0.25))))

    fs = FilingSearch(session(), reports / "filing_checks.json")
    detections = list(csv.DictReader((reports / "split_detections.csv").open(encoding="utf-8")))
    todo = [r for r in detections if r["listed_equity"] == "True" and r["corroborated"] == "True" and r["status"] == "detector_only"]
    todo = todo[:limit] if limit else todo
    counts: Counter = Counter()
    joins = []
    pool = [fs] + [FilingSearch(session()) for _ in range(max(0, workers - 1))]
    for extra in pool[1:]:
        extra.cache = fs.cache  # one cache; dict assignment is atomic under the GIL

    def check(item):
        n, row = item
        searcher = pool[n % len(pool)]
        try:
            return searcher.confirm(row["symbol"], date.fromisoformat(row["day"]))["status"]
        except SearchError as exc:
            log(f"error {row['symbol']} {row['day']}: {exc}")
            return "error"

    try:
        with ThreadPoolExecutor(max_workers=len(pool)) as ex:
            for i, status in enumerate(ex.map(check, enumerate(todo)), 1):
                counts[status] += 1
                if i % 50 == 0:
                    fs.save()
                    log(f"{i}/{len(todo)} checked: {dict(counts)} ({sum(p.requests for p in pool)} requests)")
        recon = json.loads((reports / "split_detection_reconciliation.json").read_text(encoding="utf-8"))
        ledger = {(e["ticker"], str(e["ex_date"])[:10]): e for e in
                  (json.loads(line) for line in (cfg.ledger_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
        listed = [r for r in detections if r["listed_equity"] == "True"]
        for event in recon.get("ledger_only_events") or []:
            full = ledger.get((event["ticker"], str(event["ex_date"])[:10])) or {}
            if event.get("exchange_class") != "listed" or not full.get("cik"):
                continue
            want = str(full["cik"]).zfill(10)
            for det in rename_matches(full, listed):
                try:
                    if fs.issuer_cik(det["symbol"], date.fromisoformat(det["day"])) == want:
                        joins.append({"ticker": event["ticker"], "ex_date": str(event["ex_date"])[:10], "cik": want,
                                      "filing_time_symbol": det["symbol"], "detected_day": det["day"],
                                      "ratio_inferred": det["ratio_inferred"]})
                        break
                except SearchError as exc:
                    log(f"rename error {event['ticker']}: {exc}")
    finally:
        fs.save()
    (reports / "rename_joins.json").write_text(json.dumps(joins, indent=1), encoding="utf-8")
    summary = {"checked": len(todo), **dict(counts), "rename_joins": len(joins), "requests": fs.requests}
    log(json.dumps(summary))
    return summary
