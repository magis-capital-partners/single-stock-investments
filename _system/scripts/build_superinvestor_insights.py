#!/usr/bin/env python3
"""Build structured insights from superinvestor letter text extracts."""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LETTERS_ROOT = ROOT / "_system" / "reference" / "superinvestor-letters"
INCOMING = LETTERS_ROOT / "INCOMING"
INSIGHTS_PATH = LETTERS_ROOT / "insights.json"
INDEX_PATH = LETTERS_ROOT / "letters_index.json"
MANIFEST_PATH = LETTERS_ROOT / "manifest.csv"

TICKER_RE = re.compile(r"\b([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\b")
THEME_KEYWORDS = {
    "AI": ["artificial intelligence", " ai ", "gpu", "hyperscaler", "capex"],
    "Rates": ["interest rate", "fed ", "treasury", "yield curve"],
    "Energy": ["oil", "natural gas", "energy", "opec"],
    "Japan": ["japan", "tse", "yen", "boj"],
    "China": ["china", "beijing", "tariff"],
    "Inflation": ["inflation", "cpi", "pricing power"],
    "Banking": ["bank", "credit", "deposit", "npl"],
    "Biotech": ["fda", "clinical", "biotech", "pipeline"],
}


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "unknown-fund"


def infer_fund_name(path: Path) -> tuple[str, str]:
    stem = path.stem.replace("_", " ").replace("-", " ")
    parts = stem.split()
    manager = ""
    if len(parts) >= 2 and parts[0].istitle():
        manager = parts[0]
    fund = stem.title()
    return fund, manager


def extract_tickers(text: str) -> list[str]:
    found = set()
    for m in TICKER_RE.finditer(text):
        tk = m.group(1)
        if tk in {"PDF", "USD", "EPS", "CEO", "CFO", "AI", "USA", "ETF", "IPO", "Q1", "Q2", "Q3", "Q4"}:
            continue
        if len(tk) <= 5:
            found.add(tk)
    return sorted(found)[:40]


def extract_themes(text: str) -> list[dict]:
    lower = f" {text.lower()} "
    themes = []
    for theme, kws in THEME_KEYWORDS.items():
        hits = [k for k in kws if k in lower]
        if hits:
            stance = "neutral"
            if any(w in lower for w in [" cautious", " concern", " risk", " overvalued"]):
                stance = "cautious"
            elif any(w in lower for w in [" opportunity", " attractive", " added", " increased"]):
                stance = "constructive"
            themes.append({"theme": theme, "stance": stance, "tickers": [], "quote": hits[0].strip()})
    return themes[:8]


def extract_positions(text: str, tickers: list[str]) -> list[dict]:
    positions = []
    lower = text.lower()
    for tk in tickers[:15]:
        pattern = re.compile(rf"\b{re.escape(tk)}\b", re.I)
        if not pattern.search(text):
            continue
        action = "discussed"
        if re.search(rf"(added|increased|initiated).{{0,40}}\b{tk}\b", text, re.I):
            action = "add"
        elif re.search(rf"(reduced|trimmed|sold|exited).{{0,40}}\b{tk}\b", text, re.I):
            action = "trim"
        positions.append({"ticker": tk, "action": action, "thesis": f"Mentioned in letter ({action})", "conviction": "med"})
    return positions[:20]


def quarter_from_path(path: Path) -> str:
    for part in path.parts:
        if re.match(r"20\d{2}Q[1-4]", part, re.I):
            return part.upper()
    return "unknown"


def scan_letter_files() -> list[Path]:
    files: list[Path] = []
    for base in [INCOMING, LETTERS_ROOT]:
        if not base.exists():
            continue
        for ext in ("*.txt", "*.md"):
            files.extend(base.rglob(ext))
        for qdir in base.glob("20*"):
            if qdir.is_dir():
                files.extend(qdir.glob("*.txt"))
                files.extend(qdir.glob("*.md"))
    # dedupe
    seen = set()
    out = []
    for f in sorted(files):
        key = str(f.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def build_letter_record(path: Path, cfg: dict) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    fund, manager = infer_fund_name(path)
    quarter = quarter_from_path(path)
    tickers = extract_tickers(text)
    themes = extract_themes(text)
    for th in themes:
        th["tickers"] = tickers[:5]
    positions = extract_positions(text, tickers)
    fmap = cfg.get("fund_persona_map") or {}
    personas = []
    for k, ps in fmap.items():
        if k in fund.lower() or k in manager.lower():
            personas = ps
            break
    return {
        "fund": fund,
        "manager": manager,
        "quarter": quarter,
        "letter_date": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
        "source_file": str(path.relative_to(ROOT)).replace("\\", "/"),
        "themes": themes,
        "positions": positions,
        "macro_views": [],
        "maps_to_persona": personas,
    }


def main() -> int:
    sys_path = ROOT / "_system" / "scripts"
    import sys

    sys.path.insert(0, str(sys_path))
    from persona_lens_common import load_personas  # noqa: WPS433

    cfg = load_personas()
    files = scan_letter_files()
    letters = [build_letter_record(f, cfg) for f in files]

    index = [
        {
            "fund": r["fund"],
            "manager": r["manager"],
            "quarter": r["quarter"],
            "letter_date": r["letter_date"],
            "source_file": r["source_file"],
        }
        for r in letters
    ]

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "letter_count": len(letters),
        "letters": letters,
    }
    LETTERS_ROOT.mkdir(parents=True, exist_ok=True)
    INSIGHTS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    INDEX_PATH.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["fund", "manager", "quarter", "letter_date", "source_file"])
        for row in index:
            w.writerow([row["fund"], row["manager"], row["quarter"], row["letter_date"], row["source_file"]])

    print(f"Wrote {INSIGHTS_PATH} ({len(letters)} letters from {len(files)} text files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
