#!/usr/bin/env python3
"""Build structured insights from superinvestor letter text extracts.

Matching is delegated to the evidence-tiered engine in ``letter_matching.py``
(seeded by ``security_master.json``) and fund identity/date to
``fund_registry.py``. Only Tier A/B mentions are emitted into ``tickers`` and
``positions``; the full tiered ``mentions`` list is retained per letter so the
consensus layer can decide what to count.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import letter_matching as lm  # noqa: E402
from fund_registry import FundResolver  # noqa: E402

LETTERS_ROOT = ROOT / "_system" / "reference" / "superinvestor-letters"
INCOMING = LETTERS_ROOT / "INCOMING"
INSIGHTS_PATH = LETTERS_ROOT / "insights.json"
INDEX_PATH = LETTERS_ROOT / "letters_index.json"
MANIFEST_PATH = LETTERS_ROOT / "manifest.csv"
SECURITY_MASTER_PATH = ROOT / "_system" / "reference" / "securities" / "security_master.json"

# Minimum tier emitted into tickers / positions (consensus uses the same floor).
EMIT_MIN_TIER = "B"

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

ACTION_DIRECTION = {
    "new": "bullish", "add": "bullish", "buy": "bullish",
    "trim": "bearish", "exit": "bearish", "short": "bearish",
    "hold": "neutral", "discuss": "neutral",
}


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "unknown-fund"


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_security_master() -> lm.SecurityMaster:
    data = load_json(SECURITY_MASTER_PATH)
    if not isinstance(data, dict):
        # fall back to an empty master; matcher then only emits nothing useful,
        # so make sure build_security_master.py ran first.
        data = {}
    return lm.SecurityMaster.from_dict(data)


def theme_stance(text: str, keywords: list[str]) -> str:
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
    upper = text.upper()
    themes: list[dict] = []
    for theme, kws in THEME_KEYWORDS.items():
        hits = [k for k in kws if k in lower]
        if not hits:
            continue
        stance = theme_stance(text, hits)
        related = [t for t in tickers if (t.split(".", 1)[0] if "." in t else t) in upper][:5]
        themes.append({"theme": theme, "stance": stance, "tickers": related, "quote": hits[0].strip()})
    return themes[:10]


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


def source_document_ref(path: Path) -> str:
    candidates = []
    if path.suffix.lower() in {".txt", ".md"}:
        candidates.append(path.with_suffix(".pdf"))
    candidates.append(path)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.relative_to(ROOT)).replace("\\", "/")
    return str(path.relative_to(ROOT)).replace("\\", "/")


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


def mentions_to_positions(mentions: list[dict]) -> list[dict]:
    positions: list[dict] = []
    for m in mentions:
        action = m.get("action", "discuss")
        positions.append(
            {
                "ticker": m["ticker"],
                "action": {"discuss": "discussed"}.get(action, action),
                "thesis": m.get("evidence") or f"Mentioned in letter ({action})",
                "commentary": m.get("evidence") or "",
                "conviction": m.get("conviction", "low"),
                "tier": m.get("tier"),
                "in_book": m.get("in_book", False),
                "direction": ACTION_DIRECTION.get(action, "neutral"),
            }
        )
    return positions[:30]


def build_letter_record(path: Path, resolver: FundResolver, master: lm.SecurityMaster, persona_cfg: dict) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    meta = resolver.resolve(path, text)

    all_mentions = lm.match_letter(text, master)
    emitted = lm.emitted_mentions(all_mentions, EMIT_MIN_TIER)
    tickers = [m["ticker"] for m in emitted][:40]
    positions = mentions_to_positions(emitted)
    themes = extract_themes(text, tickers)
    sections = extract_sections(text)

    personas = meta.get("maps_to_persona") or []
    if not personas:
        fmap = persona_cfg.get("fund_persona_map") or {}
        fund_lower = (meta.get("fund") or "").lower()
        mgr_lower = (meta.get("manager") or "").lower()
        for k, ps in fmap.items():
            if k in fund_lower or (mgr_lower and k in mgr_lower):
                personas = ps
                break

    return {
        "fund_id": meta["fund_id"],
        "fund": meta["fund"],
        "manager": meta.get("manager", ""),
        "strategy": meta.get("strategy", ""),
        "quarter": meta.get("quarter") or "unknown",
        "letter_date": meta.get("letter_date"),
        "date_source": meta.get("date_source"),
        "fund_resolution": meta.get("resolution"),
        "source_file": str(path.relative_to(ROOT)).replace("\\", "/"),
        "source_document": source_document_ref(path),
        "lead_summary": extract_lead_summary(text),
        "themes": themes,
        "positions": positions,
        "tickers": tickers,
        "mentions": all_mentions[:60],
        "risks": sections.get("risks", []),
        "catalysts": sections.get("catalysts", []),
        "macro_views": sections.get("outlook", []) + sections.get("macro", []),
        "maps_to_persona": personas,
    }


def main() -> int:
    sys_path = ROOT / "_system" / "scripts"
    sys.path.insert(0, str(sys_path))
    from persona_lens_common import load_personas  # noqa: WPS433

    persona_cfg = load_personas()
    master = load_security_master()
    resolver = FundResolver()
    files = scan_letter_files()
    letters = [build_letter_record(f, resolver, master, persona_cfg) for f in files]
    resolver.write_unresolved()

    index = [
        {
            "fund_id": r["fund_id"],
            "fund": r["fund"],
            "manager": r["manager"],
            "quarter": r["quarter"],
            "letter_date": r["letter_date"],
            "date_source": r.get("date_source"),
            "source_file": r["source_file"],
            "source_document": r.get("source_document"),
            "tickers": r["tickers"],
            "themes": [t["theme"] for t in r["themes"]],
        }
        for r in letters
    ]

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "letter_count": len(letters),
        "emit_min_tier": EMIT_MIN_TIER,
        "security_master_count": len(master.by_ticker),
        "letters": letters,
    }
    LETTERS_ROOT.mkdir(parents=True, exist_ok=True)
    INSIGHTS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    INDEX_PATH.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["fund_id", "fund", "manager", "quarter", "letter_date", "source_file", "source_document"])
        for row in index:
            w.writerow([
                row["fund_id"], row["fund"], row["manager"], row["quarter"],
                row["letter_date"], row["source_file"], row.get("source_document"),
            ])

    emitted = sum(len(r["tickers"]) for r in letters)
    print(f"Wrote {INSIGHTS_PATH} ({len(letters)} letters, {emitted} Tier>={EMIT_MIN_TIER} ticker mentions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
