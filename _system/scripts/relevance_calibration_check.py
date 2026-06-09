#!/usr/bin/env python3
"""Calibrate persona relevance vs superinvestor letter holdings."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from persona_lens_common import load_json, load_personas  # noqa: E402

LETTERS_INSIGHTS = ROOT / "_system" / "reference" / "superinvestor-letters" / "insights.json"
REPORT_PATH = ROOT / "dashboard" / "data" / "persona_calibration.json"


def fund_personas(fund: str, manager: str, cfg: dict) -> list[str]:
    fmap = cfg.get("fund_persona_map") or {}
    key = (fund or "").lower()
    mgr = (manager or "").lower()
    for k, personas in fmap.items():
        if k in key or k in mgr:
            return personas
    return []


def letter_holdings_by_persona(insights: list[dict], cfg: dict) -> dict[str, set[str]]:
    by_persona: dict[str, set[str]] = defaultdict(set)
    for row in insights:
        personas = row.get("maps_to_persona") or fund_personas(row.get("fund", ""), row.get("manager", ""), cfg)
        tickers = set()
        for pos in row.get("positions") or []:
            tk = pos.get("ticker")
            if tk:
                tickers.add(str(tk).upper())
        for th in row.get("themes") or []:
            for tk in th.get("tickers") or []:
                tickers.add(str(tk).upper())
        for p in personas:
            by_persona[p.lower()].update(tickers)
    return by_persona


def our_high_relevance_tickers(persona: str) -> set[str]:
    out: set[str] = set()
    for p in ROOT.iterdir():
        if not p.is_dir():
            continue
        lp = p / "research" / "lenses.json"
        if not lp.exists():
            continue
        data = load_json(lp)
        if not isinstance(data, dict):
            continue
        for lens in data.get("lenses") or []:
            if lens.get("persona") == persona and lens.get("relevance", 0) >= 1.0:
                out.add(p.name.upper())
    return out


def main() -> int:
    cfg = load_personas()
    insights_doc = load_json(LETTERS_INSIGHTS) or {"letters": []}
    letters = insights_doc.get("letters") or []
    holdings = letter_holdings_by_persona(letters, cfg)

    personas = sorted((cfg.get("personas") or {}).keys())
    rows = []
    for persona in personas:
        ours = our_high_relevance_tickers(persona)
        theirs = holdings.get(persona, set())
        overlap = ours & theirs if theirs else set()
        match_rate = round(len(overlap) / len(theirs), 3) if theirs else None
        rows.append(
            {
                "persona": persona,
                "our_high_relevance_count": len(ours),
                "letter_holdings_count": len(theirs),
                "overlap_count": len(overlap),
                "overlap_tickers": sorted(overlap),
                "match_rate": match_rate,
                "note": "No letter holdings mapped" if not theirs else None,
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "letter_count": len(letters),
        "personas": rows,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    for r in rows:
        mr = r["match_rate"]
        mr_s = f"{mr:.1%}" if mr is not None else "n/a"
        print(f"  {r['persona']}: match={mr_s} overlap={r['overlap_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
