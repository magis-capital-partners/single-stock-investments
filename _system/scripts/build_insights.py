#!/usr/bin/env python3
"""Merge multi-source insights into dashboard/data/insights.json."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "dashboard" / "data" / "insights.json"
LETTERS_INSIGHTS = ROOT / "_system" / "reference" / "superinvestor-letters" / "insights.json"
NEWS_PATH = ROOT / "dashboard" / "data" / "portfolio_news.json"
THEMES_DIR = ROOT / "_system" / "reference" / "market-data" / "themes"


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def insight_record(**kwargs) -> dict:
    base = {
        "in_base_irr": False,
        "confidence": "med",
    }
    base.update(kwargs)
    return base


def from_superinvestor_letters(doc: dict) -> list[dict]:
    out: list[dict] = []
    for letter in doc.get("letters") or []:
        fund = letter.get("fund", "Unknown")
        as_of = letter.get("letter_date")
        for th in letter.get("themes") or []:
            out.append(
                insight_record(
                    source="superinvestor_letter",
                    as_of=as_of,
                    scope="theme",
                    ref=th.get("theme"),
                    claim=f"{fund}: {th.get('theme')} — {th.get('stance', 'neutral')}",
                    direction={"constructive": "bullish", "cautious": "bearish"}.get(th.get("stance"), "neutral"),
                    evidence_ref=letter.get("source_file"),
                    fund=fund,
                    quarter=letter.get("quarter"),
                    tickers=th.get("tickers") or [],
                )
            )
        for pos in letter.get("positions") or []:
            tk = pos.get("ticker")
            if not tk:
                continue
            out.append(
                insight_record(
                    source="superinvestor_letter",
                    as_of=as_of,
                    scope="ticker",
                    ref=tk,
                    claim=f"{fund} {pos.get('action', 'discussed')} {tk}",
                    direction={"add": "bullish", "trim": "bearish"}.get(pos.get("action"), "neutral"),
                    evidence_ref=letter.get("source_file"),
                    fund=fund,
                    quarter=letter.get("quarter"),
                )
            )
    return out


def from_valuation_context(ticker: str, val: dict) -> list[dict]:
    out: list[dict] = []
    overlay = val.get("context_overlay") or {}
    as_of = overlay.get("as_of") or val.get("as_of")
    for theme in overlay.get("themes") or []:
        for ind in theme.get("indicators") or []:
            if ind.get("latest") is None:
                continue
            out.append(
                insight_record(
                    source="macro",
                    as_of=ind.get("as_of") or as_of,
                    scope="ticker",
                    ref=ticker,
                    claim=f"{ind.get('label')}: {ind.get('latest')} ({ind.get('direction', 'flat')})",
                    direction={"up": "bullish", "down": "bearish"}.get(ind.get("direction"), "neutral"),
                    evidence_ref=f"{ticker}/research/valuation.json#context_overlay",
                    theme_id=theme.get("theme_id"),
                )
            )

    insider = val.get("insider_signal") or {}
    if insider.get("band") and insider.get("band") != "negligible":
        out.append(
            insight_record(
                source="insider",
                as_of=insider.get("as_of") or as_of,
                scope="ticker",
                ref=ticker,
                claim=f"Insider conviction band: {insider.get('band')} (ICS {insider.get('ics')})",
                direction="bearish" if insider.get("ics", 0) < 0 else "bullish",
                evidence_ref=f"{ticker}/research/valuation.json#insider_signal",
                confidence="low",
            )
        )
    return out


def from_third_party(ticker_dir: Path, ticker: str) -> list[dict]:
    out: list[dict] = []
    inv_path = ticker_dir / "third-party-analyses" / "source_inventory_2026-06-07.json"
    if not inv_path.exists():
        invs = sorted(ticker_dir.glob("third-party-analyses/source_inventory_*.json"), reverse=True)
        inv_path = invs[0] if invs else None
    if not inv_path or not inv_path.exists():
        return out
    doc = load_json(inv_path)
    if not isinstance(doc, dict):
        return out
    for src in doc.get("sources") or []:
        title = src.get("title") or src.get("source") or "Third party"
        out.append(
            insight_record(
                source="third_party",
                as_of=src.get("date") or doc.get("as_of"),
                scope="ticker",
                ref=ticker,
                claim=f"Third-party source indexed: {title}",
                direction="neutral",
                evidence_ref=str(inv_path.relative_to(ROOT)).replace("\\", "/"),
                confidence="low",
            )
        )
    return out[:5]


def from_theme_panel() -> list[dict]:
    out: list[dict] = []
    if not THEMES_DIR.exists():
        return out
    for csv_path in THEMES_DIR.glob("*.csv"):
        try:
            lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
            if len(lines) < 2:
                continue
            header = [h.strip().lower() for h in lines[0].split(",")]
            last = lines[-1].split(",")
            date_idx = header.index("date") if "date" in header else 0
            val_idx = 1 if len(last) > 1 else 0
            out.append(
                insight_record(
                    source="theme",
                    as_of=last[date_idx].strip() if date_idx < len(last) else None,
                    scope="portfolio",
                    ref=csv_path.stem,
                    claim=f"Theme panel {csv_path.stem}: latest {last[val_idx].strip()}",
                    direction="neutral",
                    evidence_ref=str(csv_path.relative_to(ROOT)).replace("\\", "/"),
                    confidence="low",
                )
            )
        except (ValueError, IndexError):
            continue
    return out


def from_news(doc: dict) -> list[dict]:
    out: list[dict] = []
    for item in doc.get("items") or doc.get("news") or []:
        out.append(
            insight_record(
                source="news",
                as_of=item.get("date"),
                scope=item.get("scope", "portfolio"),
                ref=item.get("ticker") or item.get("title"),
                claim=item.get("title") or item.get("summary") or "News item",
                direction="neutral",
                evidence_ref=item.get("url"),
                confidence="low",
            )
        )
    return out[:30]


def theme_rankings(records: list[dict], quarter: str | None = None) -> list[dict]:
    """Count distinct letters per theme (not raw paragraph hits)."""
    by_theme: dict[str, dict] = {}
    for r in records:
        if r.get("source") != "superinvestor_letter" or r.get("scope") != "theme":
            continue
        if quarter and r.get("quarter") != quarter:
            continue
        theme = r.get("ref") or "Other"
        fund = r.get("fund") or "Unknown"
        bucket = by_theme.setdefault(
            theme,
            {
                "theme": theme,
                "letter_count": 0,
                "fund_count": 0,
                "bullish": 0,
                "bearish": 0,
                "neutral": 0,
                "top_tickers": set(),
                "_funds": set(),
            },
        )
        if fund not in bucket["_funds"]:
            bucket["_funds"].add(fund)
            bucket["fund_count"] += 1
            bucket["letter_count"] += 1
            direction = r.get("direction", "neutral")
            bucket[direction] = bucket.get(direction, 0) + 1
        for tk in r.get("tickers") or []:
            if tk:
                bucket["top_tickers"].add(str(tk).upper())
    out: list[dict] = []
    for bucket in by_theme.values():
        top = sorted(bucket["top_tickers"])[:8]
        out.append(
            {
                "theme": bucket["theme"],
                "letter_count": bucket["letter_count"],
                "fund_count": bucket["fund_count"],
                "bullish": bucket["bullish"],
                "bearish": bucket["bearish"],
                "neutral": bucket["neutral"],
                "top_tickers": top,
            }
        )
    return sorted(out, key=lambda x: (-x["letter_count"], x["theme"]))


def theme_rankings_by_quarter(records: list[dict]) -> dict[str, list[dict]]:
    quarters = sorted({r.get("quarter") for r in records if r.get("quarter")})
    out = {"all": theme_rankings(records)}
    for q in quarters:
        out[q] = theme_rankings(records, quarter=q)
    return out


def fund_registry(records: list[dict], our_tickers: set[str]) -> list[dict]:
    """One row per fund+quarter with overlap against our book."""
    by_key: dict[str, dict] = {}
    for r in records:
        if r.get("source") != "superinvestor_letter":
            continue
        fund = r.get("fund") or "Unknown"
        quarter = r.get("quarter") or "—"
        key = f"{fund}|{quarter}"
        row = by_key.setdefault(
            key,
            {
                "fund": fund,
                "quarter": quarter,
                "our_tickers": set(),
                "sample_claim": None,
                "evidence_ref": r.get("evidence_ref"),
            },
        )
        if r.get("scope") == "ticker" and r.get("ref"):
            tk = str(r["ref"]).upper()
            if tk in our_tickers:
                row["our_tickers"].add(tk)
            if not row["sample_claim"]:
                row["sample_claim"] = r.get("claim")
        elif r.get("scope") == "theme" and not row["sample_claim"]:
            row["sample_claim"] = r.get("claim")
    out = []
    for row in by_key.values():
        out.append(
            {
                "fund": row["fund"],
                "quarter": row["quarter"],
                "our_tickers": sorted(row["our_tickers"]),
                "our_ticker_count": len(row["our_tickers"]),
                "sample_claim": row["sample_claim"],
                "evidence_ref": row["evidence_ref"],
            }
        )
    return sorted(out, key=lambda x: (-x["our_ticker_count"], x["fund"]))


def our_holdings_tickers() -> set[str]:
    reg_path = ROOT / "_system" / "portfolio" / "registry.json"
    if not reg_path.exists():
        return set()
    reg = load_json(reg_path)
    if not isinstance(reg, dict):
        return set()
    return {str(k).upper() for k in (reg.get("holdings") or {})}


def ticker_insights(records: list[dict]) -> dict[str, list[dict]]:
    by_ticker: dict[str, list[dict]] = {}
    for r in records:
        if r.get("scope") != "ticker":
            continue
        tk = str(r.get("ref", "")).upper()
        if not tk or not re.match(r"^[A-Z0-9.\-]+$", tk):
            continue
        by_ticker.setdefault(tk, []).append(r)
    return by_ticker


def main() -> int:
    records: list[dict] = []

    letters_doc = load_json(LETTERS_INSIGHTS) or {"letters": []}
    records.extend(from_superinvestor_letters(letters_doc))

    for p in ROOT.iterdir():
        if not p.is_dir() or p.name.startswith((".", "_")):
            continue
        val_path = p / "research" / "valuation.json"
        if not val_path.exists():
            continue
        val = load_json(val_path)
        if isinstance(val, dict):
            records.extend(from_valuation_context(p.name, val))
        records.extend(from_third_party(p, p.name))

    records.extend(from_theme_panel())
    news_doc = load_json(NEWS_PATH)
    if isinstance(news_doc, dict):
        records.extend(from_news(news_doc))

    our_tickers = our_holdings_tickers()
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "record_count": len(records),
        "theme_rankings": theme_rankings(records),
        "theme_rankings_by_quarter": theme_rankings_by_quarter(records),
        "fund_registry": fund_registry(records, our_tickers),
        "by_ticker": ticker_insights(records),
        "records": records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(records)} insight records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
