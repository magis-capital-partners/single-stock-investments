#!/usr/bin/env python3
"""ClinicalTrials.gov profiles + peer-momentum for biotech quant universe.

Offline-safe: builds peer clusters from cached profiles / company-name Jaccard;
peer_momentum_12m from local Yahoo monthly returns CSVs when present.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from ownership_common import (  # noqa: E402
    CLINICAL_PATH,
    SIGNALS_PATH,
    load_json,
    now_iso,
    save_json,
    yahoo_symbol,
)

RETURNS_DIR = ROOT / "_system" / "reference" / "market-data" / "returns"
CT_API = "https://clinicaltrials.gov/api/v2/studies"
UA = "MarvinResearch/1.0 (marvin@oakcliff-capital.com)"

INDICATION_STOP = {
    "study", "trial", "phase", "patients", "treatment", "disease", "disorder",
    "syndrome", "cancer", "advanced", "metastatic", "adults", "subjects",
}


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 3 and w not in INDICATION_STOP}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def fetch_trials_for_sponsor(company: str, *, max_studies: int = 8) -> list[dict]:
    if not company or len(company) < 3:
        return []
    params = urllib.parse.urlencode(
        {
            "query.spons": company,
            "pageSize": max_studies,
            "format": "json",
            "fields": "NCTId,BriefTitle,Condition,Phase,InterventionName,OverallStatus",
        }
    )
    url = f"{CT_API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.load(resp)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return []
    out: list[dict] = []
    for study in data.get("studies") or []:
        proto = (study.get("protocolSection") or {})
        ident = proto.get("identificationModule") or {}
        cond = proto.get("conditionsModule") or {}
        design = proto.get("designModule") or {}
        arms = proto.get("armsInterventionsModule") or {}
        conditions = cond.get("conditions") or []
        phases = design.get("phases") or []
        interventions = [i.get("name") for i in (arms.get("interventions") or []) if i.get("name")]
        out.append(
            {
                "nct_id": ident.get("nctId"),
                "title": ident.get("briefTitle"),
                "conditions": conditions,
                "phases": phases,
                "interventions": interventions[:8],
            }
        )
    return out


def profile_from_trials(ticker: str, company: str, trials: list[dict]) -> dict:
    tags: set[str] = set()
    phases: set[str] = set()
    modalities: set[str] = set()
    for t in trials:
        for c in t.get("conditions") or []:
            tags |= tokenize(c)
        for p in t.get("phases") or []:
            phases.add(str(p))
        for iv in t.get("interventions") or []:
            low = (iv or "").lower()
            if "mrna" in low or "rna" in low:
                modalities.add("mrna")
            if "antibody" in low or "adc" in low or "conjugate" in low:
                modalities.add("adc")
            if "car-t" in low or "cell" in low:
                modalities.add("cell")
            if "small molecule" in low or "inhibitor" in low:
                modalities.add("small_molecule")
            tags |= tokenize(iv)
    # Theme keywords for Insights join
    theme_hits = []
    blob = " ".join(sorted(tags | modalities)).lower()
    if any(x in blob for x in ("obesity", "glp", "semaglutide", "tirzepatide", "incretin")):
        theme_hits.append("Obesity/GLP-1")
    if "adc" in modalities or "conjugate" in blob:
        theme_hits.append("ADC")
    if "mrna" in modalities or "mrna" in blob:
        theme_hits.append("mRNA")
    return {
        "ticker": ticker,
        "company": company,
        "trial_count": len(trials),
        "indication_tags": sorted(tags)[:40],
        "phases": sorted(phases),
        "modalities": sorted(modalities),
        "theme_tags": theme_hits,
        "peer_cluster_id": None,
        "peer_tickers": [],
        "peer_momentum_12m": None,
    }


def load_return_12m(ticker: str) -> float | None:
    path = RETURNS_DIR / f"{ticker.upper()}.csv"
    if not path.exists():
        # try yahoo symbol form
        path = RETURNS_DIR / f"{yahoo_symbol(ticker)}.csv"
    if not path.exists():
        return None
    rows: list[tuple[str, float]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            d = row.get("date") or row.get("Date") or ""
            r = row.get("return") or row.get("monthly_return") or row.get("ret")
            if r is None or r == "":
                # try close-to-close if only Adj Close present — skip
                continue
            try:
                rows.append((d[:10], float(r)))
            except ValueError:
                continue
    if len(rows) < 6:
        return None
    rows.sort(key=lambda x: x[0])
    # Compound last 12 monthly returns if available
    window = rows[-12:]
    cum = 1.0
    for _, r in window:
        # accept either fraction or percent
        frac = r / 100.0 if abs(r) > 1.5 else r
        cum *= 1.0 + frac
    return round((cum - 1.0) * 100.0, 2)


def fetch_yahoo_monthly_returns(ticker: str) -> float | None:
    """Compute ~12m total return from Yahoo chart monthly closes; cache CSV."""
    sym = yahoo_symbol(ticker)
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        f"?interval=1mo&range=2y"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; MarvinResearch/1.0)", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = json.load(resp)
        result = data["chart"]["result"][0]
        ts = result.get("timestamp") or []
        closes = (result.get("indicators") or {}).get("quote", [{}])[0].get("close") or []
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None
    pairs = [(t, c) for t, c in zip(ts, closes) if c is not None]
    if len(pairs) < 7:
        return None
    RETURNS_DIR.mkdir(parents=True, exist_ok=True)
    rows_out = []
    for i in range(1, len(pairs)):
        prev, cur = pairs[i - 1][1], pairs[i][1]
        if not prev:
            continue
        ret = (cur / prev) - 1.0
        from datetime import datetime, timezone

        d = datetime.fromtimestamp(pairs[i][0], tz=timezone.utc).strftime("%Y-%m-%d")
        rows_out.append({"date": d, "return": round(ret, 6), "close": cur})
    path = RETURNS_DIR / f"{ticker.upper()}.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "return", "close"])
        w.writeheader()
        w.writerows(rows_out)
    return load_return_12m(ticker)


def build_peer_baskets(profiles: dict[str, dict], *, max_peers: int = 15) -> None:
    tickers = list(profiles)
    vectors = {t: set(profiles[t].get("indication_tags") or []) | set(profiles[t].get("modalities") or []) for t in tickers}
    # Simple connected components via greedy clustering on similarity ≥ 0.15
    cluster_id = 0
    assigned: dict[str, int] = {}
    for t in tickers:
        if t in assigned:
            continue
        cluster_id += 1
        assigned[t] = cluster_id
        for u in tickers:
            if u in assigned:
                continue
            if jaccard(vectors[t], vectors[u]) >= 0.15:
                assigned[u] = cluster_id
    # Peer lists: top similar within cluster (or global if singleton)
    for t in tickers:
        cid = assigned.get(t)
        candidates = [u for u in tickers if u != t and assigned.get(u) == cid]
        if len(candidates) < 2:
            scored = sorted(
                ((u, jaccard(vectors[t], vectors[u])) for u in tickers if u != t),
                key=lambda x: x[1],
                reverse=True,
            )
            candidates = [u for u, s in scored if s > 0][:max_peers]
        else:
            scored = sorted(
                ((u, jaccard(vectors[t], vectors[u])) for u in candidates),
                key=lambda x: x[1],
                reverse=True,
            )
            candidates = [u for u, _ in scored[:max_peers]]
        profiles[t]["peer_cluster_id"] = f"cluster_{cid}"
        profiles[t]["peer_tickers"] = candidates


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--max-fetch", type=int, default=40, help="Max ClinicalTrials sponsor lookups")
    ap.add_argument("--fetch-returns", action="store_true", help="Harvest Yahoo monthly returns online")
    args = ap.parse_args()

    signals = load_json(SIGNALS_PATH, {"by_ticker": {}})
    existing = load_json(CLINICAL_PATH, {"by_ticker": {}})
    profiles: dict[str, dict] = dict(existing.get("by_ticker") or {})

    universe = {
        t: row
        for t, row in (signals.get("by_ticker") or {}).items()
        if row.get("in_biotech_quant_universe") and ":" not in t
    }

    fetched = 0
    for ticker, row in sorted(universe.items()):
        company = row.get("company") or row.get("issuer") or ticker
        if args.offline:
            if ticker not in profiles:
                profiles[ticker] = profile_from_trials(ticker, company, [])
                # Seed tags from company name tokens so Jaccard still works offline
                profiles[ticker]["indication_tags"] = sorted(tokenize(company))[:20]
            continue
        if fetched >= args.max_fetch and ticker in profiles and profiles[ticker].get("trial_count"):
            continue
        if ticker in profiles and (profiles[ticker].get("trial_count") or 0) > 0 and not args.fetch_returns:
            continue
        trials = fetch_trials_for_sponsor(company)
        time.sleep(0.25)
        fetched += 1
        profiles[ticker] = profile_from_trials(ticker, company, trials)
        if not profiles[ticker]["indication_tags"]:
            profiles[ticker]["indication_tags"] = sorted(tokenize(company))[:20]

    # Ensure every universe name has a profile
    for ticker, row in universe.items():
        if ticker not in profiles:
            company = row.get("company") or row.get("issuer") or ticker
            profiles[ticker] = profile_from_trials(ticker, company, [])
            profiles[ticker]["indication_tags"] = sorted(tokenize(company))[:20]

    build_peer_baskets(profiles)

    # Own returns + peer momentum
    own_ret: dict[str, float] = {}
    for ticker in profiles:
        ret = load_return_12m(ticker)
        if ret is None and args.fetch_returns and not args.offline:
            ret = fetch_yahoo_monthly_returns(ticker)
            time.sleep(0.15)
        if ret is not None:
            own_ret[ticker] = ret

    for ticker, prof in profiles.items():
        peers = prof.get("peer_tickers") or []
        peer_rets = [own_ret[p] for p in peers if p in own_ret]
        if peer_rets:
            prof["peer_momentum_12m"] = round(sum(peer_rets) / len(peer_rets), 2)
        else:
            prof["peer_momentum_12m"] = None

    payload = {
        "generated_at": now_iso(),
        "schema_version": 2,
        "status": "live" if any((p.get("trial_count") or 0) > 0 for p in profiles.values()) else "partial",
        "ticker_count": len(profiles),
        "by_ticker": profiles,
        "notes": "Peer momentum = equal-weight 12m return of clinical-similarity peers. Own-price momentum banned.",
    }
    save_json(CLINICAL_PATH, payload)

    for ticker, prof in profiles.items():
        if ticker in signals.get("by_ticker", {}):
            sig = signals["by_ticker"][ticker]
            sig["peer_momentum_12m"] = prof.get("peer_momentum_12m")
            sig["peer_cluster_id"] = prof.get("peer_cluster_id")
            sig["clinical_theme_tags"] = prof.get("theme_tags")
    save_json(SIGNALS_PATH, signals)
    with_momo = sum(1 for p in profiles.values() if p.get("peer_momentum_12m") is not None)
    print(f"Wrote clinical profiles for {len(profiles)} tickers ({with_momo} with peer momentum)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
