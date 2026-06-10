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

TICKER_STOPWORDS = {
    "PDF", "USD", "EPS", "CEO", "CFO", "AI", "USA", "ETF", "IPO",
    "Q1", "Q2", "Q3", "Q4", "AUM", "FCF", "EBIT", "EBITDA", "ROIC",
    "EV", "PE", "PB", "NAV", "CAGR", "YTD", "FY", "GAAP", "SEC", "IRS",
    "M&A", "LTM", "NTM", "TAM", "SAM", "GDP", "CPI", "PCE", "FED",
    "LLC", "LP", "INC", "LTD", "PLC", "NYSE", "NASDAQ", "TSE", "LSE",
    "OTC", "ADR", "SPAC", "REIT", "BPS", "APR", "MOU", "ESG", "MRO",
    "IBB", "SPX", "RUT", "VIX", "EOD", "YOY", "QOQ", "MOM", "WACC",
    "DCF", "IRR", "ROI", "ROE", "ROA", "COGS", "OPEX", "CAPEX", "COVID",
    "AFFO", "FFO", "NOI", "AIFMD", "ADGM", "IFRS", "FASB", "UCITS", "MIFID",
    "GDPR", "SOFR", "LIBOR", "EMEA", "APAC", "LATAM",
    "I", "A", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "HE", "IF",
    "IN", "IS", "IT", "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO",
    "UP", "US", "WE", "AM", "PM", "VS", "ETC", "THE", "AND", "FOR",
    "NOT", "BUT", "ALL", "ANY", "CAN", "HAD", "HER", "HIS", "HOW",
    "ITS", "MAY", "NEW", "NOW", "OLD", "OUR", "OUT", "OWN", "SAY",
    "SHE", "TOO", "USE", "WAY", "WHO", "BOY", "DID", "GET", "HAS",
    "HIM", "LET", "PUT", "SAW", "SIX", "TEN", "TOP", "TRY", "TWO",
    "WAR", "WAS", "WIN", "WON", "YES", "YET", "YOU", "BIG", "DAY",
    "END", "FAR", "FEW", "GOT", "HIT", "JOB", "LAW", "LOW", "MAN",
    "NET", "NON", "OFF", "OIL", "ONE", "PAY", "PER", "RAN", "RED",
    "RUN", "SET", "SIT", "SUN", "TAX", "VIA", "WAR", "WON",
}

PAREN_TICKER_RE = re.compile(r"\(([A-Z]{2,6}(?:\.[A-Z]{1,2}){0,2})\)")
DOLLAR_TICKER_RE = re.compile(r"\$([A-Z]{1,5}(?:\.[A-Z]{1,2})?)")
EXCHANGE_TICKER_RE = re.compile(r"\b([A-Z]{2,5}\.[A-Z]{1,2})\b")

NON_TICKER_DOTTED = {
    "U.S", "U.K", "E.U", "B.A", "M.A", "A.M", "P.M", "D.C", "Q.E", "P.E",
}

THEME_KEYWORDS: dict[str, list[str]] = {
    "AI": ["artificial intelligence", " ai ", "gpu", "hyperscaler", "large language model", "llm"],
    "Semiconductors": ["semiconductor", "chip", "foundry", "wafer", "nvidia", "micron"],
    "Rates": ["interest rate", "fed ", "treasury", "yield curve", "federal reserve"],
    "Energy": ["oil", "natural gas", "energy", "opec", "crude"],
    "Japan": ["japan", "tse", "yen", "boj", "tokyo"],
    "China": ["china", "beijing", "tariff", "chinese"],
    "Inflation": ["inflation", "cpi", "pricing power", "pce"],
    "Banking": ["bank", "credit", "deposit", "npl", "lending"],
    "Biotech": ["fda", "clinical", "biotech", "pipeline", "pharma"],
    "Healthcare": ["healthcare", "hospital", "medical", "drug"],
    "Gold": ["gold", "precious metal", "wheaton", "franco-nevada"],
    "Defense": ["defense", "military", "pentagon", "defence"],
    "Aerospace": ["aerospace", "aviation", "aircraft", "boeing"],
    "Onshoring": ["onshoring", "reshoring", "domestic manufacturing", "bring manufacturing home"],
    "Trade Policy": ["tariff", "trade war", "trade policy", "de-escalat"],
    "Automation": ["automation", "industrial automation", "robotics"],
    "Data Centers": ["data center", "datacenter", "colocation", "equinix"],
}

STANCE_BULLISH = ("opportunity", "attractive", "added", "increased", "initiated", "bullish", "optimistic", "favorable", "tailwind")
STANCE_BEARISH = ("cautious", "concern", " risk", "overvalued", "sold", "exited", "trimmed", "reduced", "headwind", "disruption", "vulnerable")

SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "risks": re.compile(r"^(?:key\s+)?risks?(?:\s+identified)?\s*:?\s*$", re.I),
    "catalysts": re.compile(r"^(?:key\s+)?catalysts?(?:\s+include)?\s*:?\s*$", re.I),
    "outlook": re.compile(r"^(?:forward\s+)?outlook\s*:?\s*$|^market\s+outlook\s*:?\s*$", re.I),
    "macro": re.compile(r"^macro(?:\s+view|\s+outlook)?\s*:?\s*$|^economic\s+outlook\s*:?\s*$", re.I),
}


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "unknown-fund"


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_known_tickers() -> set[str]:
    known: set[str] = set()
    reg = load_json(ROOT / "_system" / "portfolio" / "registry.json")
    if isinstance(reg, dict):
        known.update(str(k).upper() for k in (reg.get("holdings") or {}))
    for p in ROOT.iterdir():
        if not p.is_dir() or p.name.startswith((".", "_")):
            continue
        if (p / "INDEX.csv").exists() or (p / "research" / "valuation.json").exists():
            known.add(p.name.upper())
    return known


def valid_ticker(tk: str, known: set[str]) -> bool:
    tk = tk.upper()
    if tk in TICKER_STOPWORDS or tk in NON_TICKER_DOTTED:
        return False
    if not re.match(r"^[A-Z0-9](?:[A-Z0-9.\-]{0,11})?$", tk):
        return False
    if re.match(r"^[A-Z]\.[A-Z]$", tk) and tk not in known:
        return False
    if len(tk) <= 2 and tk not in known:
        return False
    if len(tk) == 1:
        return tk in known
    return True


def is_table_like(s: str) -> bool:
    digits = sum(c.isdigit() for c in s)
    if digits > max(10, len(s) * 0.18):
        return True
    if re.search(r"\d{4,}", s) and digits >= 4:
        return True
    return False


def sentence_score(s: str, ticker: str) -> int:
    if is_table_like(s):
        return 9999
    score = len(s)
    if re.search(rf"\({re.escape(ticker)}\)", s, re.I):
        score -= 80
    if re.search(rf"\${re.escape(ticker)}\b", s, re.I):
        score -= 60
    if re.search(rf"\b{re.escape(ticker)}\b", s, re.I) and not re.search(r"\d/\d/\d{4}", s):
        score -= 20
    return score


def extract_tickers(text: str, known: set[str]) -> list[str]:
    found: set[str] = set()
    for m in PAREN_TICKER_RE.finditer(text):
        tk = m.group(1).upper()
        if valid_ticker(tk, known):
            found.add(tk)
    for m in DOLLAR_TICKER_RE.finditer(text):
        tk = m.group(1).upper()
        if valid_ticker(tk, known):
            found.add(tk)
    for m in EXCHANGE_TICKER_RE.finditer(text):
        tk = m.group(1).upper()
        if "." in tk and valid_ticker(tk, known):
            found.add(tk)
    for tk in sorted(known, key=len, reverse=True):
        if re.search(rf"(?<![A-Z0-9.]){re.escape(tk)}(?![A-Z0-9.])", text, re.I):
            found.add(tk)
    return sorted(found, key=lambda t: text.upper().find(t))[:30]


def split_sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text.replace("\n", " "))
    parts = re.split(r"(?<=[.!?])\s+", flat)
    return [p.strip() for p in parts if len(p.strip()) > 15]


def sentence_for_ticker(text: str, ticker: str) -> str:
    pat = re.compile(rf"(?<![A-Z0-9.]){re.escape(ticker)}(?![A-Z0-9.])", re.I)
    hits = [s for s in split_sentences(text) if pat.search(s)]
    if not hits:
        return ""
    best = min(hits, key=lambda s: sentence_score(s, ticker))
    if sentence_score(best, ticker) >= 9999:
        return ""
    return best[:350]


def theme_stance(text: str, theme: str, keywords: list[str]) -> str:
    lower = text.lower()
    windows: list[str] = []
    for kw in keywords:
        idx = lower.find(kw.strip())
        while idx >= 0:
            start = max(0, idx - 120)
            end = min(len(lower), idx + len(kw) + 120)
            windows.append(lower[start:end])
            idx = lower.find(kw.strip(), idx + 1)
    if not windows:
        return "neutral"
    blob = " ".join(windows)
    bull = sum(1 for w in STANCE_BULLISH if w in blob)
    bear = sum(1 for w in STANCE_BEARISH if w in blob)
    if bull > bear + 1:
        return "constructive"
    if bear > bull + 1:
        return "cautious"
    return "neutral"


def extract_themes(text: str, tickers: list[str]) -> list[dict]:
    lower = f" {text.lower()} "
    themes: list[dict] = []
    for theme, kws in THEME_KEYWORDS.items():
        hits = [k for k in kws if k in lower]
        if not hits:
            continue
        stance = theme_stance(text, theme, hits)
        related = [t for t in tickers if t in text.upper()][:5]
        themes.append({
            "theme": theme,
            "stance": stance,
            "tickers": related,
            "quote": hits[0].strip(),
        })
    return themes[:10]


def extract_positions(text: str, tickers: list[str]) -> list[dict]:
    positions: list[dict] = []
    for tk in tickers[:20]:
        pat = re.compile(rf"(?<![A-Z0-9.]){re.escape(tk)}(?![A-Z0-9.])", re.I)
        if not pat.search(text):
            continue
        action = "discussed"
        if re.search(
            rf"(added|increased|initiated|purchased|bought).{{0,60}}(?<![A-Z0-9.]){re.escape(tk)}(?![A-Z0-9.])",
            text,
            re.I,
        ) or re.search(
            rf"(?<![A-Z0-9.]){re.escape(tk)}(?![A-Z0-9.]).{{0,60}}(added|increased|initiated|purchased|bought)",
            text,
            re.I,
        ):
            action = "add"
        elif re.search(
            rf"(reduced|trimmed|sold|exited|eliminated).{{0,60}}(?<![A-Z0-9.]){re.escape(tk)}(?![A-Z0-9.])",
            text,
            re.I,
        ) or re.search(
            rf"(?<![A-Z0-9.]){re.escape(tk)}(?![A-Z0-9.]).{{0,60}}(reduced|trimmed|sold|exited|eliminated)",
            text,
            re.I,
        ):
            action = "trim"
        commentary = sentence_for_ticker(text, tk)
        positions.append({
            "ticker": tk,
            "action": action,
            "thesis": commentary or f"Mentioned in letter ({action})",
            "commentary": commentary,
            "conviction": "med",
        })
    return positions[:25]


def extract_sections(text: str) -> dict[str, list[str]]:
    lines = [ln.strip() for ln in text.splitlines()]
    active: str | None = None
    buckets: dict[str, list[str]] = {"risks": [], "catalysts": [], "outlook": [], "macro": []}
    for ln in lines:
        if not ln:
            continue
        matched = False
        for key, pat in SECTION_PATTERNS.items():
            if pat.match(ln):
                active = key
                matched = True
                break
        if matched:
            continue
        if active and (ln.startswith("-") or ln.startswith("•") or ln.startswith("*")):
            item = re.sub(r"^[-•*]\s*", "", ln).strip()
            if len(item) > 10:
                buckets[active].append(item[:280])
        elif active and len(ln) > 20 and not ln.isupper():
            buckets[active].append(ln[:280])
            if len(buckets[active]) >= 5:
                active = None
    return {k: v[:5] for k, v in buckets.items() if v}


def extract_lead_summary(text: str, max_chars: int = 480) -> str:
    paras: list[str] = []
    buf: list[str] = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            if buf:
                paras.append(" ".join(buf))
                buf = []
            continue
        if re.match(r"^\d+$", s) or len(s) < 25:
            continue
        buf.append(s)
    if buf:
        paras.append(" ".join(buf))
    good = [p for p in paras if len(p) >= 80 and not re.match(r"^(CIO|Q[1-4]|Investor Letter)", p, re.I)]
    if not good:
        good = [p for p in paras if len(p) >= 40]
    summary = " ".join(good[:2])
    return summary[:max_chars].strip()


def infer_fund_name(path: Path) -> tuple[str, str]:
    stem = path.stem.replace("_", " ").replace("-", " ")
    parts = stem.split()
    manager = ""
    if len(parts) >= 2 and parts[0][0:1].isupper():
        manager = parts[0]
    fund = stem.title()
    return fund, manager


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
    seen: set[str] = set()
    out: list[Path] = []
    for f in sorted(files):
        key = str(f.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def build_letter_record(path: Path, cfg: dict, known: set[str]) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    fund, manager = infer_fund_name(path)
    quarter = quarter_from_path(path)
    tickers = extract_tickers(text, known)
    themes = extract_themes(text, tickers)
    positions = extract_positions(text, tickers)
    sections = extract_sections(text)
    fmap = cfg.get("fund_persona_map") or {}
    personas: list[str] = []
    fund_lower = fund.lower()
    mgr_lower = manager.lower()
    for k, ps in fmap.items():
        if k in fund_lower or (mgr_lower and k in mgr_lower):
            personas = ps
            break
    return {
        "fund_id": slugify(fund),
        "fund": fund,
        "manager": manager,
        "quarter": quarter,
        "letter_date": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
        "source_file": str(path.relative_to(ROOT)).replace("\\", "/"),
        "lead_summary": extract_lead_summary(text),
        "themes": themes,
        "positions": positions,
        "tickers": tickers,
        "risks": sections.get("risks", []),
        "catalysts": sections.get("catalysts", []),
        "macro_views": sections.get("outlook", []) + sections.get("macro", []),
        "maps_to_persona": personas,
    }


def main() -> int:
    sys_path = ROOT / "_system" / "scripts"
    import sys

    sys.path.insert(0, str(sys_path))
    from persona_lens_common import load_personas  # noqa: WPS433

    cfg = load_personas()
    known = load_known_tickers()
    files = scan_letter_files()
    letters = [build_letter_record(f, cfg, known) for f in files]

    index = [
        {
            "fund_id": r["fund_id"],
            "fund": r["fund"],
            "manager": r["manager"],
            "quarter": r["quarter"],
            "letter_date": r["letter_date"],
            "source_file": r["source_file"],
            "tickers": r["tickers"],
            "themes": [t["theme"] for t in r["themes"]],
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
        w.writerow(["fund_id", "fund", "manager", "quarter", "letter_date", "source_file"])
        for row in index:
            w.writerow([
                row["fund_id"],
                row["fund"],
                row["manager"],
                row["quarter"],
                row["letter_date"],
                row["source_file"],
            ])

    print(f"Wrote {INSIGHTS_PATH} ({len(letters)} letters from {len(files)} text files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
