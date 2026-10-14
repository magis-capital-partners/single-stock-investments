"""Bridge to SSI's SEC method and Short Alpha evidence contract.

Raw companyfacts are filtered BEFORE the shared quarterly extractor is called.
Latest-revision SSI caches are a fallback, never silently historical truth.
Nothing here connects to ThetaData, a broker, or modifies the SSI repository.

Inside SSI the bridge imports ``build_fundamental_series`` and
``build_short_quant_screen`` as modules from ``_system/scripts`` instead of
loading them by file path; the manifest still records their hashes.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from copy import deepcopy
from collections import OrderedDict
from datetime import date, datetime, timezone
from pathlib import Path

from .config import SCRIPTS_DIR

SSI_URL = "https://single-stock-investments-2wt.pages.dev/"
REPO_URL = "https://github.com/magis-capital-partners/single-stock-investments/blob/main/"


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def _ssi_modules():
    """The SSI extractor and screen as imported modules (``None`` when absent)."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        import build_fundamental_series as extractor  # noqa: PLC0415
        import build_short_quant_screen as screen  # noqa: PLC0415
    except ImportError:
        return None, None
    return extractor, screen


def cik_id(value):
    return str(value or "").lstrip("0")


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


class FundamentalBridge:
    def __init__(self, cfg):
        self.cfg = cfg
        self.root = cfg.repo_root
        self.cache = cfg.raw_dir / "companyfacts"
        self.extract_path = SCRIPTS_DIR / "build_fundamental_series.py"
        self.screen_path = SCRIPTS_DIR / "build_short_quant_screen.py"
        self.extractor, self.screen = _ssi_modules()
        self.frameworks = read_json(self.root / "_system/research/short-alpha/frameworks.json")
        self.ledger = read_json(self.root / "_system/research/short-alpha/candidates.json")
        self.docs, self.scores = {}, {}
        self.raw_docs = OrderedDict()
        self.sic = read_json(self.root / "_system/reference/market-data/fundamentals/_sic_map.json")

    def manifest(self):
        files = [self.extract_path, self.screen_path,
                 self.root / "_system/research/short-alpha/frameworks.json",
                 self.root / "_system/frameworks/short_alpha_filing_furnace.md"]
        return {
            "available": bool(self.extractor and self.screen), "source_root": str(self.root),
            "dashboard": SSI_URL, "short_alpha": SSI_URL + "#/ideas/short-alpha",
            "links": [{"label": p.name, "url": REPO_URL + relative_path(p, self.root),
                       "local_path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None}
                      for p in files],
            "method": "Same SSI quarterly extractor and fundamental-signal thresholds; raw filings filtered before extraction. Weighted fundamental decay only; no current tape in historical scores.",
            "limits": ["Scores prioritize research; they are neither fraud findings nor probabilities of profit.",
                       "Missing data are unscored. Three observed signals are required for a composite.",
                       "Period-end is not availability. Date-only facts wait until the following day.",
                       "SSI's 24-quarter latest-revision cache loses older vintages; fallback coverage is explicitly limited.",
                       "Issuer identity, custom XBRL tags, non-US GAAP, restricted cash, warrants and dilution need filing review.",
                       "Today's manual candidate ledger is context only; it never changes historical scores."],
            "frameworks": self.frameworks.get("frameworks", []),
        }

    def series(self, ticker, cik, asof):
        key = (ticker, cik_id(cik), asof)
        if key in self.docs:
            return self.docs[key]
        raw_path = self.cache / f"CIK{int(cik):010d}.json" if cik_id(cik).isdigit() else None
        raw = None
        if raw_path and raw_path.exists():
            cache_key=str(raw_path)
            if cache_key not in self.raw_docs:
                self.raw_docs[cache_key]=read_json(raw_path)
                if len(self.raw_docs)>4:self.raw_docs.popitem(last=False)
            self.raw_docs.move_to_end(cache_key)
            raw=self.raw_docs[cache_key]
        source = "raw_companyfacts" if raw else "ssi_latest_revision_cache"
        provenance = []
        if raw and self.extractor:
            if cik_id(raw.get("cik")) != cik_id(cik):
                result = ({"metrics": {}}, "identity_mismatch", [])
                self.docs[key] = result
                return result
            filtered = {"facts": {"us-gaap": {}}}
            gaap = (raw.get("facts") or {}).get("us-gaap") or {}
            for tag, node in gaap.items():
                facts = [f for f in (node.get("units") or {}).get("USD", [])
                         if f.get("filed") and f["filed"][:10] < asof and f.get("end", "9999") <= asof
                         and isinstance(f.get("val"), (int, float)) and math.isfinite(f["val"])]
                if facts:
                    filtered["facts"]["us-gaap"][tag] = {"units": {"USD": facts}}
            metrics = {metric: self.extractor.extract_metric_series(filtered, metric)
                       for metric in self.extractor.METRIC_TAGS if metric != "eps_basic"}
            for metric, points in metrics.items():
                for p in points:
                    ends = p.get("from_periods") or [p["period"]]
                    supporting = [f for f in filtered["facts"]["us-gaap"].get(p["tag"], {}).get("units", {}).get("USD", [])
                                  if f.get("end") in ends and f.get("filed", "") <= p["filed"]]
                    p["accessions"] = sorted({f.get("accn") for f in supporting if f.get("accn")})
                    provenance.append({"metric": metric, **p})
            doc = {"metrics": metrics, "cik": cik, "ticker": ticker}
        else:
            doc = deepcopy(read_json(self.root / f"_system/reference/market-data/fundamentals/{ticker}.json"))
            if not doc:
                source = "missing"
            if doc and cik_id(doc.get("cik")) != cik_id(cik):
                doc, source = {}, "identity_mismatch"
            doc["metrics"] = {metric: [p for p in points if p.get("filed") and p["filed"] < asof and p.get("period", "9999") <= asof]
                              for metric, points in doc.get("metrics", {}).items()}
            provenance = [{"metric": metric, **p} for metric, points in doc["metrics"].items() for p in points]
        # Shared formula requires comparable fiscal periods. Prevent newest revenue
        # from being compared to an older CFO/NI window or a stale debt line.
        flow = {"revenues", "operating_income", "net_income", "cfo"}
        present = [points for metric, points in doc["metrics"].items() if metric in flow and points]
        anchor = max((p[-1]["period"] for p in present), default=None)
        for metric, points in list(doc["metrics"].items()):
            points = [p for p in points if (date.fromisoformat(asof) - date.fromisoformat(p["period"])).days <= 365 * 12]
            if points and (date.fromisoformat(asof) - date.fromisoformat(points[-1]["period"])).days > 400:
                points = []
            if metric in flow and points and points[-1]["period"] != anchor:
                points = []
            doc["metrics"][metric] = points
        result = (doc, source, provenance)
        self.docs[key] = result
        return result

    def score(self, ticker, cik, asof):
        key = (ticker, cik_id(cik), asof)
        if key in self.scores:
            return self.scores[key]
        doc, source, provenance = self.series(ticker, cik, asof)
        signals, facts = self.screen.fundamental_signals(doc, date.fromisoformat(asof)) if self.screen else ({}, {})
        # The equity bridge also reflects FX, OCI, acquisitions and distributions:
        # it cannot establish dilution, so omit it until issuance is reconciled.
        signals.pop("equity_raised", None)
        evidence = [key for key, row in signals.items() if row.get("value") is not None and row.get("score") is not None]
        # No-profit and positive-CFO pseudo-observations do not satisfy coverage.
        weighted = sum(signals[k]["score"] * self.screen.FUNDAMENTAL_SIGNALS[k][1] for k in evidence) if self.screen else 0
        weights = sum(self.screen.FUNDAMENTAL_SIGNALS[k][1] for k in evidence) if self.screen else 0
        issuer = read_json(self.cache / f"CIK{int(cik):010d}.issuer.json") if cik_id(cik).isdigit() else {}
        sic = issuer.get("sic") or (self.sic.get(ticker) or {}).get("sic")
        sic = int(sic) if str(sic or "").isdigit() else None
        profile = self.screen.profile_for(sic) if self.screen and sic is not None else "unknown"
        score = round(100 * weighted / weights, 1) if len(evidence) >= 3 and weights and profile == "operating" else None
        lenses = [self.screen.FUNDAMENTAL_SIGNALS[k][0] for k in evidence if signals[k]["score"] >= .5] if self.screen else []
        latest = facts.get("latest_period")
        relevant = sorted(provenance, key=lambda p: (p.get("period", ""), p.get("filed", "")), reverse=True)[:20]
        for p in relevant:
            p["source_urls"] = [f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a.replace('-', '')}/"
                                for a in p.get("accessions", [])[-4:]] if cik_id(cik).isdigit() else []
        result = {"ticker": ticker, "cik": cik, "as_of": asof, "score": score,
                  "evidence_count": len(evidence), "signals": signals, "facts": facts,
                  "lenses": sorted(set(lenses)), "profile": profile, "source": source,
                  "sic": sic, "profile_basis": "current SEC issuer metadata; historical classification requires reconciliation",
                  "historical_eligible": source == "raw_companyfacts" and score is not None,
                  "latest_period": latest, "evidence": relevant,
                  "conviction": "requires_analyst_review", "fraud_bad_actors": "unscored",
                  "borrow_gate": "historical_locate_missing", "valuation_gate": "unscored",
                  "catalyst_gate": "requires_dated_catalyst", "falsifier_gate": "requires_written_falsifier"}
        self.scores[key] = result
        return result

    def current_context(self, ticker):
        ledger = next((r for r in self.ledger.get("candidates", []) if r.get("ticker") == ticker), None)
        furnace = read_json(self.root / f"{ticker}/research/evidence/short_furnace_events.json")
        return {"ledger_as_of": self.ledger.get("as_of"), "candidate": ledger,
                "filing_events": furnace.get("events", []), "usage": "current context; excluded from historical scores"}


def refresh_companyfacts(cfg, tickers=None, limit=None):
    """SEC-only, cache-preserving download for research candidates and traded names."""
    import requests  # deferred: network command only

    from .db import init_db
    bridge = FundamentalBridge(cfg)
    conn = init_db(cfg.db_path)
    rows = conn.execute("SELECT DISTINCT ticker,cik FROM reverse_splits WHERE cik IS NOT NULL AND exchange_class='listed'").fetchall()
    conn.close()
    if tickers is None:
        snapshot = read_json(cfg.public_dir / "backtest.json")
        tickers = {t["ticker"] for b in snapshot.get("books", []) for t in b.get("trades", [])}
        tickers.update(r["ticker"] for r in snapshot.get("research", {}).get("candidates", []))
    picks = sorted({(row["ticker"], row["cik"]) for row in rows if row["ticker"] in tickers and cik_id(row["cik"]).isdigit()})
    bridge.cache.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = cfg.section("edgar")["user_agent"]
    results = []
    selected = picks[:limit] if limit is not None else picks
    for ticker, cik in selected:
        path = bridge.cache / f"CIK{int(cik):010d}.json"
        if path.exists():
            results.append({"ticker": ticker, "status": "cached"})
            continue
        try:
            response = session.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json", timeout=25)
            response.raise_for_status()
            doc = response.json()
            if cik_id(doc.get("cik")) != cik_id(cik) or not doc.get("facts"):
                raise ValueError("issuer or facts missing")
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(doc), encoding="utf-8")
            temp.replace(path)
            results.append({"ticker": ticker, "status": "downloaded"})
        except (requests.RequestException, ValueError) as exc:
            results.append({"ticker": ticker, "status": "unavailable", "reason": str(exc)[:160]})
            if isinstance(exc, requests.HTTPError) and exc.response.status_code in {403, 429}:
                break  # Respect a denied/rate-limited SEC endpoint; keep existing caches.
        print(f"[fundamentals] {ticker}: {results[-1]['status']}", flush=True)
        time.sleep(max(.25, float(cfg.section("edgar").get("request_delay_seconds", .25))))
    issuer_results = []
    for ticker, cik in selected:
        path = bridge.cache / f"CIK{int(cik):010d}.issuer.json"
        if path.exists():
            continue
        try:
            response = session.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", timeout=25)
            response.raise_for_status()
            doc = response.json()
            if cik_id(doc.get("cik")) != cik_id(cik):
                raise ValueError("issuer mismatch")
            metadata = {k: doc.get(k) for k in ("cik", "name", "sic", "sicDescription", "tickers", "exchanges")}
            metadata["fetched_at"] = datetime.now(timezone.utc).isoformat()
            path.write_text(json.dumps(metadata), encoding="utf-8")
            issuer_results.append({"ticker": ticker, "status": "downloaded"})
        except (requests.RequestException, ValueError) as exc:
            issuer_results.append({"ticker": ticker, "status": "unavailable", "reason": str(exc)[:160]})
            if isinstance(exc, requests.HTTPError) and exc.response.status_code in {403, 429}:
                break
        print(f"[issuer classification] {ticker}: {issuer_results[-1]['status']}", flush=True)
        time.sleep(.25)
    manifest = {"built_at": datetime.now(timezone.utc).isoformat(), "requested": len(picks), "results": results, "issuer_metadata": issuer_results}
    (bridge.cache / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"requested": len(picks), "processed": len(results), "issuer_metadata_downloaded": sum(r["status"] == "downloaded" for r in issuer_results),
            **{status: sum(r["status"] == status for r in results) for status in ("cached", "downloaded", "unavailable")}}
