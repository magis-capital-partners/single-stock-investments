"""Prioritize entry-price gaps; public volume never supplies verified capacity."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from .coverage_data import chart_url, parse_chart, validate_chart_url
from .coverage_research import write_public_json
from .free_evidence import FreeClient, sha
from .ledger import read_json


def validated_segments(bars, original, ticker, source_hash):
    grouped, kept = defaultdict(list), {}
    for d, r in bars.items(): grouped[r["_future_split_factor"]].append(d)
    for future, days in grouped.items():
        ratios = sorted(original[d]["close"]/bars[d]["close"] for d in days if original.get(d, {}).get("close"))
        if len(ratios) < 3: continue
        center = ratios[len(ratios)//2]
        factor = min((1., 1/future), key=lambda f: abs(center/f-1))
        errors = sorted(abs(r/factor-1) for r in ratios)
        if errors[len(errors)//2] > .02 or errors[int(.9*(len(errors)-1))] > .05: continue
        for d in days:
            kept[d] = {"date": d, **{k: bars[d][k]*factor for k in ("open", "high", "low", "close")},
                       "volume": None, "source_url": chart_url(ticker), "source_sha256": source_hash,
                       "nominal_units": "three_overlap_segment_validated"}
    return kept


def collect_prices(snapshots, store, policy, sessions, root, *, fetch=False, maximum=500):
    from .net_edge_study import entry_day
    root = Path(root)
    client = FreeClient(root/"price_cache", "SSI free historical research", maximum=maximum if fetch else 0, validator=validate_chart_url)
    prior_audit = read_json(root/"price_requests.json", [])
    failures = {r["url"] for r in prior_audit if r["status"] in {"http_404", "http_400"}}
    targets = defaultdict(list)
    last = max(i for i, d in enumerate(sessions) if d <= "2026-10-13")
    entry_cutoff = sessions[last-policy.sessions+1]
    for s in snapshots.values():
        day = entry_day(s, policy, sessions)
        if not day or not "2018-05-01" <= day <= entry_cutoff: continue
        prices = store.prices(s["database_ticker"])
        ix = sessions.index(day)
        path_missing = any(not all(prices.get(d, {}).get(k) for k in ("open", "high", "low", "close")) for d in sessions[ix:ix+policy.sessions])
        if path_missing: targets[s["database_ticker"]].append(s)
    # Uses eligibility and dates only. Later returns never order acquisition.
    ordered = sorted(targets, key=lambda t: (-sum((s.get("screen_rating") or -1) >= 60 for s in targets[t]),
                                            -sum(s["known_at"] >= "2023-10-14" for s in targets[t]), -len(targets[t]), t))
    overlay, audit = {}, []
    old_root = root.parent/"coverage_v4/price_cache"
    for i, ticker in enumerate(ordered):
        url = chart_url(ticker)
        old = old_root/(sha(url.encode())+".raw")
        raw = None
        if old.exists():
            proof = read_json(old.with_suffix(".json"))
            raw = old.read_bytes()
            if proof.get("url") != url or proof.get("sha256") != sha(raw): raise ValueError("Cached price source mismatch")
        elif url not in failures: raw = client.get(url)
        kept = {}
        if raw:
            bars, _, _ = parse_chart(raw, ticker)
            kept = validated_segments(bars, store.prices(ticker), ticker, sha(raw))
            windows = [(date.fromisoformat(s["ex_date"])-timedelta(days=45), date.fromisoformat(s["ex_date"])+timedelta(days=40)) for s in targets[ticker] if s.get("ex_date")]
            kept = {d: r for d, r in kept.items() if any(str(a) <= d <= str(b) for a, b in windows)}
        if kept: overlay[ticker] = kept
        audit.append({"ticker": ticker, "target_events": len(targets[ticker]), "validated_bars": len(kept),
                      "source_url": url, "status": "overlap_validated" if kept else "missing_or_units_unverified"})
        if i % 50 == 0: print("Prioritized prices", i, "/", len(ordered), "new requests", client.requests, flush=True)
    write_public_json(root/"price_requests.json", prior_audit+client.records)
    write_public_json(root/"price_recovery.json", {"targets": audit, "network_requests": client.requests,
        "request_status": dict(Counter(r["status"] for r in client.records)), "accepted_volume_rows": 0})
    return overlay, {"target_symbols": len(ordered), "validated_symbols": len(overlay),
                     "validated_bars": sum(len(r) for r in overlay.values()), "network_requests": client.requests,
                     "status": dict(Counter(r["status"] for r in client.records)), "accepted_volume_rows": 0}
