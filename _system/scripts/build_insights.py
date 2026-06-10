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
        fund_id = letter.get("fund_id") or fund
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
                    fund_id=fund_id,
                    quarter=letter.get("quarter"),
                    tickers=th.get("tickers") or [],
                )
            )
        for pos in letter.get("positions") or []:
            tk = pos.get("ticker")
            if not tk:
                continue
            action = pos.get("action", "discussed")
            commentary = pos.get("commentary") or pos.get("thesis") or ""
            claim = commentary if commentary else f"{fund} {action} {tk}"
            out.append(
                insight_record(
                    source="superinvestor_letter",
                    as_of=as_of,
                    scope="ticker",
                    ref=tk,
                    claim=claim,
                    direction={"add": "bullish", "trim": "bearish"}.get(action, "neutral"),
                    evidence_ref=letter.get("source_file"),
                    fund=fund,
                    fund_id=fund_id,
                    quarter=letter.get("quarter"),
                    action=action,
                    commentary=commentary,
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


def theme_rankings(records: list[dict], quarter: str | None = None, our_tickers: set[str] | None = None) -> list[dict]:
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
            if tk and re.match(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$", str(tk).upper()):
                bucket["top_tickers"].add(str(tk).upper())
    out: list[dict] = []
    holdings = our_tickers or set()
    for bucket in by_theme.values():
        all_tickers = sorted(bucket["top_tickers"])
        ours = [t for t in all_tickers if t in holdings]
        rest = [t for t in all_tickers if t not in holdings]
        top = (ours + rest)[:8]
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


def theme_rankings_by_quarter(records: list[dict], our_tickers: set[str] | None = None) -> dict[str, list[dict]]:
    quarters = sorted({r.get("quarter") for r in records if r.get("quarter")})
    out = {"all": theme_rankings(records, our_tickers=our_tickers)}
    for q in quarters:
        out[q] = theme_rankings(records, quarter=q, our_tickers=our_tickers)
    return out


def fund_registry(letters: list[dict], our_tickers: set[str]) -> list[dict]:
    """One row per fund+quarter with overlap against our book."""
    by_key: dict[str, dict] = {}
    for letter in letters:
        fund = letter.get("fund") or "Unknown"
        fund_id = letter.get("fund_id") or fund
        quarter = letter.get("quarter") or "—"
        key = f"{fund_id}|{quarter}"
        letter_tickers = {str(t).upper() for t in (letter.get("tickers") or [])}
        overlap = sorted(letter_tickers & our_tickers)
        row = by_key.setdefault(
            key,
            {
                "fund_id": fund_id,
                "fund": fund,
                "manager": letter.get("manager") or "",
                "quarter": quarter,
                "our_tickers": set(overlap),
                "tickers": set(letter_tickers),
                "themes": set(),
                "maps_to_persona": letter.get("maps_to_persona") or [],
                "lead_summary": letter.get("lead_summary") or "",
                "evidence_ref": letter.get("source_file"),
                "letter_date": letter.get("letter_date"),
            },
        )
        row["our_tickers"].update(overlap)
        row["tickers"].update(letter_tickers)
        for th in letter.get("themes") or []:
            if th.get("theme"):
                row["themes"].add(th["theme"])
        if not row["lead_summary"] and letter.get("lead_summary"):
            row["lead_summary"] = letter["lead_summary"]
    out = []
    for row in by_key.values():
        out.append(
            {
                "fund_id": row["fund_id"],
                "fund": row["fund"],
                "manager": row["manager"],
                "quarter": row["quarter"],
                "letter_date": row["letter_date"],
                "our_tickers": sorted(row["our_tickers"]),
                "our_ticker_count": len(row["our_tickers"]),
                "tickers": sorted(row["tickers"])[:20],
                "themes": sorted(row["themes"]),
                "maps_to_persona": row["maps_to_persona"],
                "lead_summary": (row["lead_summary"] or "")[:280],
                "evidence_ref": row["evidence_ref"],
            }
        )
    return sorted(out, key=lambda x: (-x["our_ticker_count"], x["fund"]))


def letter_index(letters: list[dict], our_tickers: set[str]) -> list[dict]:
    rows: list[dict] = []
    for letter in letters:
        tickers = [str(t).upper() for t in (letter.get("tickers") or [])]
        overlap = sorted(set(tickers) & our_tickers)
        positions = letter.get("positions") or []
        adds = [p["ticker"] for p in positions if p.get("action") == "add" and p.get("ticker")]
        trims = [p["ticker"] for p in positions if p.get("action") == "trim" and p.get("ticker")]
        rows.append(
            {
                "fund_id": letter.get("fund_id"),
                "fund": letter.get("fund"),
                "manager": letter.get("manager") or "",
                "quarter": letter.get("quarter"),
                "letter_date": letter.get("letter_date"),
                "themes": [t.get("theme") for t in (letter.get("themes") or []) if t.get("theme")],
                "tickers": tickers[:20],
                "our_overlap": overlap,
                "adds": adds[:8],
                "trims": trims[:8],
                "lead_summary": (letter.get("lead_summary") or "")[:320],
                "maps_to_persona": letter.get("maps_to_persona") or [],
                "source_file": letter.get("source_file"),
            }
        )
    return sorted(rows, key=lambda x: (x.get("letter_date") or "", x.get("fund") or ""), reverse=True)


def fund_profiles(letters: list[dict], our_tickers: set[str]) -> dict[str, dict]:
    by_fund: dict[str, dict] = {}
    for letter in letters:
        fund_id = letter.get("fund_id") or slugify(letter.get("fund", "unknown"))
        profile = by_fund.setdefault(
            fund_id,
            {
                "fund_id": fund_id,
                "fund": letter.get("fund"),
                "manager": letter.get("manager") or "",
                "maps_to_persona": letter.get("maps_to_persona") or [],
                "our_tickers": set(),
                "letters": [],
            },
        )
        if letter.get("manager") and not profile["manager"]:
            profile["manager"] = letter["manager"]
        if letter.get("maps_to_persona"):
            profile["maps_to_persona"] = letter["maps_to_persona"]
        tickers = {str(t).upper() for t in (letter.get("tickers") or [])}
        profile["our_tickers"].update(tickers & our_tickers)
        profile["letters"].append(
            {
                "quarter": letter.get("quarter"),
                "letter_date": letter.get("letter_date"),
                "lead_summary": letter.get("lead_summary") or "",
                "themes": letter.get("themes") or [],
                "positions": letter.get("positions") or [],
                "tickers": letter.get("tickers") or [],
                "risks": letter.get("risks") or [],
                "catalysts": letter.get("catalysts") or [],
                "macro_views": letter.get("macro_views") or [],
                "source_file": letter.get("source_file"),
            }
        )
    for profile in by_fund.values():
        profile["our_tickers"] = sorted(profile["our_tickers"])
        profile["letters"] = sorted(
            profile["letters"],
            key=lambda x: (x.get("letter_date") or "", x.get("quarter") or ""),
            reverse=True,
        )
        profile["latest_quarter"] = profile["letters"][0].get("quarter") if profile["letters"] else None
    return by_fund


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "unknown-fund"


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
        if not tk or not re.match(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$", tk):
            continue
        by_ticker.setdefault(tk, []).append(r)
    return by_ticker


def ticker_discussants(letters: list[dict], our_tickers: set[str]) -> dict[str, list[dict]]:
    """Per-ticker summary of which funds discuss it (letters only)."""
    by_ticker: dict[str, dict[str, dict]] = {}
    for letter in letters:
        fund = letter.get("fund") or "Unknown"
        fund_id = letter.get("fund_id") or fund
        for pos in letter.get("positions") or []:
            tk = str(pos.get("ticker", "")).upper()
            if not tk:
                continue
            bucket = by_ticker.setdefault(tk, {})
            entry = bucket.setdefault(
                fund_id,
                {
                    "fund": fund,
                    "fund_id": fund_id,
                    "quarter": letter.get("quarter"),
                    "letter_date": letter.get("letter_date"),
                    "action": pos.get("action", "discussed"),
                    "commentary": pos.get("commentary") or pos.get("thesis") or "",
                    "source_file": letter.get("source_file"),
                    "in_our_book": tk in our_tickers,
                },
            )
            if pos.get("commentary") and len(pos["commentary"]) > len(entry.get("commentary") or ""):
                entry["commentary"] = pos["commentary"]
                entry["action"] = pos.get("action", entry["action"])
    out: dict[str, list[dict]] = {}
    for tk, funds in by_ticker.items():
        rows = sorted(funds.values(), key=lambda x: (x.get("letter_date") or ""), reverse=True)
        out[tk] = rows[:12]
    return out


def main() -> int:
    records: list[dict] = []

    letters_doc = load_json(LETTERS_INSIGHTS) or {"letters": []}
    letters = letters_doc.get("letters") or []
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
        "letter_count": len(letters),
        "theme_rankings": theme_rankings(records, our_tickers=our_tickers),
        "theme_rankings_by_quarter": theme_rankings_by_quarter(records, our_tickers),
        "letter_index": letter_index(letters, our_tickers),
        "fund_registry": fund_registry(letters, our_tickers),
        "fund_profiles": fund_profiles(letters, our_tickers),
        "ticker_discussants": ticker_discussants(letters, our_tickers),
        "by_ticker": ticker_insights(records),
        "records": records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(records)} insight records, {len(letters)} letters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
