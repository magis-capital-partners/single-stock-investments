#!/usr/bin/env python3
"""Build Biotech-tab paper long/short book from composite quintiles (no Darwin)."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from memory_claim_sources import load_biotech_factor_spec  # noqa: E402
from ownership_common import PAPER_BOOK_PATH, SIGNALS_PATH, load_json, now_iso, save_json  # noqa: E402

LONG_CAP = 25
SHORT_CAP = 25
MIN_LIVE_FACTORS = 2


def live_factor_count(row: dict, spec: dict) -> int:
    n = 0
    for factor in spec.get("factors") or []:
        if factor.get("status") not in {"live", "partial"}:
            continue
        keys = factor.get("signal_keys") or []
        if any(row.get(k) is not None for k in keys):
            n += 1
    return n


def assign_composite_quintiles(by_ticker: dict[str, dict]) -> dict[str, int]:
    scored = {
        t: float(r["composite_score"])
        for t, r in by_ticker.items()
        if r.get("composite_score") is not None
    }
    if not scored:
        return {}
    ordered = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    n = len(ordered)
    out: dict[str, int] = {}
    for i, (t, _) in enumerate(ordered):
        out[t] = 5 - min(4, int(i * 5 / max(n, 1)))
    return out


def main() -> int:
    signals = load_json(SIGNALS_PATH, {"by_ticker": {}})
    spec = load_biotech_factor_spec()
    universe = {
        t: r
        for t, r in (signals.get("by_ticker") or {}).items()
        if r.get("in_biotech_quant_universe")
    }
    quintiles = assign_composite_quintiles(universe)
    for t, q in quintiles.items():
        universe[t]["composite_quintile"] = q
        if t in signals.get("by_ticker", {}):
            signals["by_ticker"][t]["composite_quintile"] = q

    long_cands = []
    for t, r in universe.items():
        if live_factor_count(r, spec) < MIN_LIVE_FACTORS:
            continue
        if (r.get("composite_quintile") or 0) < 5 and (r.get("composite_score") or 0) < 70:
            # Prefer top quintile; allow high composite if quintile sparse
            if (r.get("composite_quintile") or 0) < 4:
                continue
        issuer = r.get("issuer_size_bucket") or "unknown"
        # Prefer small/mid issuer size (Verdad small-cap edge)
        size_rank = {"small": 0, "mid": 1, "unknown": 2, "large": 3}.get(issuer, 2)
        long_cands.append((size_rank, -(r.get("composite_score") or 0), t, r))
    long_cands.sort()
    long_book = []
    for _, _, t, r in long_cands[:LONG_CAP]:
        long_book.append(
            {
                "ticker": t,
                "company": r.get("company"),
                "composite_score": r.get("composite_score"),
                "composite_quintile": r.get("composite_quintile"),
                "issuer_size_bucket": r.get("issuer_size_bucket"),
                "consensus_quintile": r.get("consensus_quintile"),
                "spend_value_quintile": r.get("spend_value_quintile"),
                "in_book": bool(r.get("in_book")),
            }
        )

    short_cands = []
    for t, r in universe.items():
        score = r.get("short_candidate_score") or 0
        si_q = r.get("short_interest_quintile") or 0
        cons_q = r.get("consensus_quintile") or 5
        if score <= 0 and si_q < 4 and cons_q > 2:
            continue
        short_cands.append((-float(score), -si_q, cons_q, t, r))
    short_cands.sort()
    short_book = []
    for _, _, _, t, r in short_cands[:SHORT_CAP]:
        short_book.append(
            {
                "ticker": t,
                "company": r.get("company"),
                "short_candidate_score": r.get("short_candidate_score"),
                "short_interest_pct": r.get("short_interest_pct"),
                "short_interest_quintile": r.get("short_interest_quintile"),
                "days_to_cover": r.get("days_to_cover"),
                "consensus_quintile": r.get("consensus_quintile"),
                "in_book": bool(r.get("in_book")),
            }
        )

    prior = load_json(PAPER_BOOK_PATH, {})
    prior_long = {r.get("ticker") for r in (prior.get("long") or [])}
    prior_short = {r.get("ticker") for r in (prior.get("short") or [])}
    cur_long = {r["ticker"] for r in long_book}
    cur_short = {r["ticker"] for r in short_book}

    payload = {
        "generated_at": now_iso(),
        "as_of": now_iso()[:10],
        "quarter": signals.get("quarter"),
        "factor_spec_version": spec.get("schema_version"),
        "min_live_factors": MIN_LIVE_FACTORS,
        "banned_factors": spec.get("banned_for_biotech") or [],
        "notes": "Not live trading. Biotech-tab paper sleeve only — no Darwin account.",
        "long": long_book,
        "short": short_book,
        "membership_delta": {
            "long_added": sorted(cur_long - prior_long),
            "long_removed": sorted(prior_long - cur_long),
            "short_added": sorted(cur_short - prior_short),
            "short_removed": sorted(prior_short - cur_short),
        },
    }
    save_json(PAPER_BOOK_PATH, payload)
    save_json(SIGNALS_PATH, signals)
    print(f"Wrote paper book: {len(long_book)} long / {len(short_book)} short")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
