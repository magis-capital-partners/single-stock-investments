#!/usr/bin/env python3
"""Seed option_scan, sotp_build, nav_overlay, and catalyst_paths in valuation.json.

Fills gaps so refresh_deep_dive_v2.py can render FRMO-style specificity for
optionality / holding_co / yield_curve names without overwriting hand-built FRMO.

Usage:
  python _system/scripts/seed_dive_overlays.py KEWL --write
  python _system/scripts/seed_dive_overlays.py --all --write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from portfolio_registry import load_registry  # noqa: E402


def _round2(x: float) -> float:
    return round(x, 2)


def _tie_out_lines(anchor: float, payoff: float, uplifts: list[tuple[str, str, float]]) -> list[dict]:
    """Build sotp_build lines that sum to payoff."""
    lines: list[dict] = [
        {
            "id": "book",
            "label": "GAAP book / price anchor",
            "gaap_per_share": anchor,
            "uplift_per_share": 0.0,
            "math": f"Anchor ${anchor}/sh",
        }
    ]
    running = anchor
    for lid, label, uplift in uplifts:
        lines.append(
            {
                "id": lid,
                "label": label,
                "gaap_per_share": 0.0,
                "uplift_per_share": uplift,
                "math": "[Assumption] — see scenario notes in valuation.json",
            }
        )
        running += uplift
    slack = _round2(payoff - running)
    if abs(slack) >= 0.01:
        lines.append(
            {
                "id": "tie_out",
                "label": "Tie-out to payoff",
                "gaap_per_share": 0.0,
                "uplift_per_share": slack,
                "math": f"Running sum + {slack} = ${payoff} payoff",
            }
        )
    return lines


def default_option_scan(val: dict, ticker: str) -> list[dict]:
    arch = (val.get("classification_inputs") or {}).get("archetype", "")
    mode = val.get("valuation_mode", "")
    ai = val.get("ai_overlay") or {}
    seg = val.get("segment_build") or {}
    nav = val.get("nav_overlay") or {}

    if ticker == "KEWL" or (arch == "optionality" and val.get("inputs", {}).get("copperwood_royalty_est_usd")):
        return [
            {
                "q": 1,
                "question": "GAAP book misstates core assets?",
                "answer": "Yes",
                "treatment": "nav_overlay",
                "evidence": "Mineral rights at historical cost; fair value in Copperwood royalties [Assumption]",
            },
            {
                "q": 2,
                "question": "Undeveloped reserves / acreage / dormant royalty?",
                "answer": "Yes",
                "treatment": "probability_weighted",
                "evidence": "Copperwood lease + >1M acres; SSI mineral-floor framing",
            },
            {
                "q": 3,
                "question": "In-business loss segment?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "No operating segments; lease income only",
            },
            {
                "q": 4,
                "question": "Backlog / contracted revenue not in FCF path?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Royalty option not in Lawrence base cash flow",
            },
            {
                "q": 5,
                "question": "Private or illiquid stakes below fair value?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "Single mineral estate",
            },
            {
                "q": 6,
                "question": "Transitory distribution / legal recovery?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "—",
            },
            {
                "q": 7,
                "question": "Embedded product option in revenue?",
                "answer": "No",
                "treatment": "n/a",
                "evidence": "—",
            },
        ]

    if ticker in ("MSB", "SJT") or val.get("optionality_gate", {}).get("framework", "").startswith("hk_"):
        return [
            {
                "q": 1,
                "question": "GAAP book misstates core assets?",
                "answer": "Partial",
                "treatment": "yield_curve",
                "evidence": "Trust/royalty; distributions not steady-state GAAP earnings",
            },
            {
                "q": 2,
                "question": "Undeveloped reserves / acreage / dormant royalty?",
                "answer": "Yes" if ticker == "SJT" else "No",
                "treatment": "yield_curve",
                "evidence": "HK equity yield curve on recovery path" if ticker == "SJT" else "Mesabi royalty on taconite",
            },
            {
                "q": 6,
                "question": "Transitory distribution / legal recovery?",
                "answer": "Yes",
                "treatment": "yield_curve",
                "evidence": "Bonus gap / arbitration / excess-cost recovery [Assumption]",
            },
        ]

    if arch == "holding_co" or ticker == "FRMO":
        return [
            {
                "q": 1,
                "question": "GAAP book misstates core assets?",
                "answer": "Yes",
                "treatment": "nav_floor",
                "evidence": "Private exchange stakes below economic value",
            },
            {
                "q": 5,
                "question": "Private or illiquid stakes below fair value?",
                "answer": "Yes",
                "treatment": "milestone_nav",
                "evidence": "MIH, HKHC, Investment A look-through",
            },
        ]

    if ai or seg.get("options"):
        rows = []
        if ai:
            rows.append(
                {
                    "q": 4,
                    "question": "Backlog / RPO / AI capex not in FCF path?",
                    "answer": "Yes",
                    "treatment": "embedded_in_segment",
                    "evidence": "ai_overlay in valuation.json",
                }
            )
        for opt in seg.get("options") or []:
            rows.append(
                {
                    "q": 3,
                    "question": f"In-business option: {opt.get('label', opt.get('id'))}?",
                    "answer": "Yes",
                    "treatment": opt.get("option_treatment", "zero"),
                    "evidence": opt.get("evidence", "[Assumption]")[:120],
                }
            )
        if rows:
            return rows

    if nav:
        return [
            {
                "q": 1,
                "question": "GAAP book misstates core assets?",
                "answer": "Yes",
                "treatment": "nav_overlay",
                "evidence": "nav_overlay in valuation.json",
            },
            {
                "q": 2,
                "question": "Undeveloped reserves / acreage?",
                "answer": "Yes",
                "treatment": "nav_floor",
                "evidence": "Segment build / undeveloped row",
            },
        ]

    return [
        {
            "q": 0,
            "question": "Material options after scan?",
            "answer": "No",
            "treatment": "n/a",
            "evidence": "Operating compounder / croupier — Lawrence full cash-flow path sufficient",
        }
    ]


def seed_sotp_build(val: dict, ticker: str) -> dict | None:
    base = (val.get("scenarios") or {}).get("base") or {}
    if base.get("sotp_build"):
        return None
    if val.get("method") != "yield_curve":
        return None
    payoff = base.get("payoff")
    years = base.get("years", 5)
    if payoff is None:
        return None
    inputs = val.get("inputs") or {}
    price = inputs.get("price", 0)
    book = inputs.get("book_per_share")
    shares = inputs.get("shares_outstanding")

    if ticker == "KEWL" and book:
        royalty = inputs.get("copperwood_royalty_est_usd", 7_700_000)
        per_sh_royalty = royalty / shares if shares else 0
        uplifts = [
            (
                "lease_cap",
                "Mineral lease run-rate capitalized",
                _round2(min(3.0, max(1.5, payoff - book - 15.0))),
            ),
            (
                "copperwood_partial",
                "Copperwood royalty option (partially in price @ entry)",
                _round2(min(14.0, per_sh_royalty * 0.35)),
            ),
            (
                "acreage",
                "667K-acre expansion + secondary lessee option",
                2.5,
            ),
        ]
        lines = _tie_out_lines(book, payoff, uplifts)
        return {
            "shares": shares,
            "book_per_share": book,
            "lines": lines,
            "year5_economic_nav_per_share": payoff,
            "sum_check": f"{book} + uplifts = {payoff}",
            "years": years,
            "notes": f"SSI ~${royalty/1e6:.1f}M/yr royalty at $4/lb Cu; base assumes lease-only Lawrence path",
        }

    if ticker == "MSB":
        anchor = price
        norm = inputs.get("normalized_distribution_per_share", 2.16)
        uplifts = [
            ("dist_cumulative", f"Normalized ~${norm}/unit cumulative distributions", 10.0),
            ("terminal_rerate", "Terminal re-rate on normalized yield", _round2(payoff - anchor - 10.0)),
        ]
        lines = _tie_out_lines(anchor, payoff, uplifts)
        return {
            "lines": lines,
            "year5_economic_nav_per_share": payoff,
            "years": years,
            "notes": "HK yield curve; bonus/arbitration in bull only",
        }

    if ticker == "SJT":
        anchor = price
        uplifts = [
            ("recovery_dist", "Royalties resume ~2028; avg ~$0.80/yr distributions NPV", 1.85),
            ("terminal_trust", "Terminal trust value on gas recovery", _round2(payoff - anchor - 1.85)),
        ]
        lines = _tie_out_lines(anchor, payoff, uplifts)
        return {
            "lines": lines,
            "year5_economic_nav_per_share": payoff,
            "years": years,
            "notes": base.get("notes", "HK yield curve"),
        }

    anchor = book if book else price
    if not anchor:
        return None
    uplift_total = _round2(payoff - anchor)
    if uplift_total <= 0:
        uplifts = [("catalyst", "Catalyst / recovery path", max(0.01, uplift_total + 0.5))]
    else:
        half = _round2(uplift_total / 2)
        uplifts = [
            ("operating_path", "Operating / distribution path", half),
            ("catalyst", "Catalyst or terminal re-rate", _round2(uplift_total - half)),
        ]
    lines = _tie_out_lines(anchor, payoff, uplifts)
    return {
        "lines": lines,
        "year5_economic_nav_per_share": payoff,
        "years": years,
        "notes": base.get("notes", "Auto-seeded from scenarios.base"),
    }


def seed_nav_overlay(val: dict, ticker: str) -> dict | None:
    if val.get("nav_overlay"):
        return None
    if ticker != "KEWL":
        return None
    inputs = val.get("inputs") or {}
    book = inputs.get("book_per_share", 12.7)
    royalty = inputs.get("copperwood_royalty_est_usd", 7_700_000)
    shares = inputs.get("shares_outstanding", 1_126_284)
    royalty_per_sh = royalty / shares if shares else 0
    overlay_nav = _round2(book + royalty_per_sh * 0.5)
    return {
        "status": "partial",
        "gaap_book_per_share": book,
        "overlay_nav_per_share": overlay_nav,
        "method": "probability_weighted",
        "components": [
            {
                "id": "copperwood_royalty",
                "label": "Copperwood production royalty",
                "probability_pct": 50,
                "payoff_per_share": _round2(royalty_per_sh),
                "source": "SSI @ $4/lb Cu [Assumption]",
            }
        ],
        "notes": "Do not use GAAP book as dhando floor; mineral estate off fair value",
    }


def seed_catalyst_paths(val: dict, ticker: str) -> list[dict] | None:
    if val.get("catalyst_paths"):
        return None
    base = (val.get("scenarios") or {}).get("base") or {}
    notes = base.get("notes", "")
    arch = (val.get("classification_inputs") or {}).get("archetype", "")

    if ticker == "KEWL":
        return [
            {"event": "Highland Copper Copperwood production start", "timing": "3–7 years", "impact": "Royalty cash flow"},
            {"event": "Michigan mining infrastructure grant", "timing": "uncertain", "impact": "Project acceleration"},
            {"event": "Secondary lessee on 667K-acre package", "timing": "medium term", "impact": "Lease income diversification"},
            {"event": "Failure mode", "timing": "—", "impact": "Reversion toward book ~$12.70"},
        ]
    if ticker == "MSB":
        return [
            {"event": "Normalized bonus / base distribution restored", "timing": "1–3 years", "impact": "~$2/unit run-rate"},
            {"event": "Arbitration / legal recovery", "timing": "uncertain", "impact": "One-time uplift"},
            {"event": "Iron ore price cycle", "timing": "cyclical", "impact": "Distribution volatility"},
        ]
    if ticker == "SJT":
        return [
            {"event": "Excess-cost recovery complete", "timing": "2028+", "impact": "Distributions resume"},
            {"event": "Natural gas price spike", "timing": "uncertain", "impact": "Bull distribution path"},
            {"event": "Trust wind-down", "timing": "bear case", "impact": "Capital loss"},
        ]
    if arch in ("holding_co", "optionality") and val.get("method") == "yield_curve":
        return [
            {"event": "Base catalyst path", "timing": f"{base.get('years', 5)} years", "impact": notes or "Dated payoff"},
            {"event": "Failure mode", "timing": "bear scenario", "impact": (val.get("scenarios") or {}).get("bear", {}).get("notes", "Marks stall")},
        ]
    return None


def seed_ticker(ticker: str, *, write: bool = False) -> dict:
    path = ROOT / ticker / "research" / "valuation.json"
    if not path.exists():
        return {"ticker": ticker, "skipped": "no valuation.json"}
    val = json.loads(path.read_text(encoding="utf-8"))
    changes: list[str] = []

    if not val.get("option_scan"):
        val["option_scan"] = default_option_scan(val, ticker)
        changes.append("option_scan")

    sotp = seed_sotp_build(val, ticker)
    if sotp:
        val.setdefault("scenarios", {}).setdefault("base", {})["sotp_build"] = sotp
        changes.append("sotp_build")

    nav = seed_nav_overlay(val, ticker)
    if nav:
        val["nav_overlay"] = nav
        gate = val.setdefault("optionality_gate", {})
        gate["overlay_nav_per_share"] = nav.get("overlay_nav_per_share")
        changes.append("nav_overlay")

    cats = seed_catalyst_paths(val, ticker)
    if cats:
        val["catalyst_paths"] = cats
        changes.append("catalyst_paths")

    if write and changes:
        path.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")

    return {"ticker": ticker, "changes": changes}


def registry_tickers() -> list[str]:
    reg = load_registry()
    holdings = reg.get("holdings", {})
    if isinstance(holdings, dict):
        return sorted(holdings.keys())
    return sorted({h["ticker"] for h in holdings})


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed dive overlay fields in valuation.json")
    parser.add_argument("tickers", nargs="*", help="Ticker(s)")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--write", action="store_true", help="Persist changes")
    args = parser.parse_args()

    tickers = registry_tickers() if args.all else [t.upper() for t in args.tickers]
    if not tickers:
        parser.error("Provide tickers or --all")

    for t in tickers:
        r = seed_ticker(t, write=args.write)
        if r.get("skipped"):
            print(f"SKIP {t}: {r['skipped']}")
        elif r.get("changes"):
            print(f"{'WROTE' if args.write else 'DRY'} {t}: {', '.join(r['changes'])}")
        else:
            print(f"OK {t}: nothing to seed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
