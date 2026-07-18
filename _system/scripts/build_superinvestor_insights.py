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
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import letter_matching as lm  # noqa: E402
from letter_dedup import deduplicate_letter_files, deduplicate_letter_records  # noqa: E402
from fund_registry import FundResolver  # noqa: E402
from fund_identity import consolidate_letter_funds_stable  # noqa: E402
from vault_paths import letters_root, path_to_letters_ref  # noqa: E402

LETTERS_ROOT = letters_root()
INCOMING = LETTERS_ROOT / "INCOMING"
INSIGHTS_PATH = LETTERS_ROOT / "insights.json"
INDEX_PATH = LETTERS_ROOT / "letters_index.json"
MANIFEST_PATH = LETTERS_ROOT / "manifest.csv"
DUPLICATE_AUDIT_PATH = LETTERS_ROOT / "duplicate_audit.json"
SECURITY_MASTER_PATH = ROOT / "_system" / "reference" / "securities" / "security_master.json"

_WORKER_MASTER: lm.SecurityMaster | None = None
_WORKER_RESOLVER: FundResolver | None = None
_WORKER_PERSONA_CFG: dict | None = None

# Minimum tier emitted into tickers / positions (consensus uses the same floor).
EMIT_MIN_TIER = "B"
CLASSIFICATION_POLICY_VERSION = 5

NONLETTER_FILENAME_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("conference_idea", re.compile(r"\b(conference|sohn|idea dinner|conference recap)\b", re.I)),
    ("monitor", re.compile(r"\b(monitors?|event driven trades|ed monitor)\b", re.I)),
    ("transcript", re.compile(r"\b(transcript|meeting notes?)\b", re.I)),
    ("product_marketing", re.compile(r"\b(presentation|factsheet|fact sheet|prospectus|tear sheet|deck)\b", re.I)),
    ("sell_side_research", re.compile(r"\b(primer|playbook|white paper|blackbook|guide|survey|research report)\b", re.I)),
]
LETTER_FILENAME_RE = re.compile(
    r"\b(investor|partner|shareholder|fund)\b.{0,35}\b(letter|newsletter|commentary|update)\b|"
    r"\b(letter|newsletter)\b",
    re.I,
)
LETTER_BODY_RE = re.compile(
    r"\b(dear (?:investor|partner|shareholder)s?|to our (?:investor|partner|shareholder)s?|"
    r"the fund (?:returned|gained|declined|appreciated|lost)|portfolio (?:returned|gained|declined))\b",
    re.I,
)
FUND_REPORT_RE = re.compile(r"\b(?:annual|semi[- ]?annual) report\b", re.I)

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
    "Obesity/GLP-1": ["obesity", "glp-1", "glp1", "semaglutide", "tirzepatide", "incretin", "wegovy", "ozempic"],
    "ADC": ["antibody-drug conjugate", " antibody drug conjugate", " adc ", "conjugate"],
    "mRNA": ["mrna", "mRNA", "messenger rna", "moderna", "biontech"],
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
    registry = load_json(ROOT / "_system" / "portfolio" / "registry.json")
    if not isinstance(registry, dict):
        registry = None
    return lm.SecurityMaster.from_dict(data, registry=registry)


def theme_stance(text: str, keywords: list[str]) -> str:
    lower = text.lower()
    windows: list[str] = []
    for kw in keywords:
        idx = lower.find(kw.strip())
        while idx >= 0 and len(windows) < 24:
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


def classify_document(path: Path, text: str) -> tuple[str, bool, str]:
    """Classify a PDF extract independently of its storage folder.

    The Drive letter folder also contains decks, monitors, conference notes,
    product literature, and sell-side research.  Those remain catalogued but
    must not create fund holdings or consensus observations.
    """
    label = path.stem.replace("_", " ").replace("-", " ")
    for kind, pattern in NONLETTER_FILENAME_RULES:
        if pattern.search(label):
            return kind, False, f"filename:{kind}"
    head = text[:5000]
    if LETTER_FILENAME_RE.search(label) or LETTER_BODY_RE.search(head):
        return "investor_letter", True, "letter_signal"
    if FUND_REPORT_RE.search(label) and re.search(r"\b(fund|portfolio|net assets|holdings)\b", head, re.I):
        return "fund_report", True, "fund_report_signal"
    return "other_research", False, "no_letter_signal"


def _theme_keyword_matches(text: str, keyword: str) -> list[re.Match[str]]:
    clean = keyword.strip()
    if not clean:
        return []
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(clean)}(?![A-Za-z0-9])", re.I)
    return list(pattern.finditer(text))


def tickers_near_keyword(text: str, keyword: str, tickers: list[str], window: int = 400) -> list[str]:
    kw = keyword.strip().lower()
    if not kw:
        return []
    lower = text.lower()
    idx = lower.find(kw)
    if idx < 0:
        return []
    start = max(0, idx - window)
    end = min(len(text), idx + len(kw) + window)
    snippet = text[start:end].upper()
    found: list[str] = []
    for ticker in tickers:
        base = ticker.split(".", 1)[0] if "." in ticker else ticker
        token = base.upper()
        if token and token in snippet and ticker not in found:
            found.append(ticker)
    return found


def extract_themes(text: str, tickers: list[str]) -> list[dict]:
    themes: list[dict] = []
    for theme, kws in THEME_KEYWORDS.items():
        matches = {k: _theme_keyword_matches(text, k) for k in kws}
        matches = {k: rows for k, rows in matches.items() if rows}
        total_hits = sum(len(rows) for rows in matches.values())
        paragraph_hits = {
            text.count("\n\n", 0, row.start())
            for rows in matches.values()
            for row in rows
        }
        # A theme must be central enough to recur, use multiple distinct
        # signals, or span paragraphs.  One generic word no longer tags a PDF.
        if total_hits < 2 or not (len(matches) >= 2 or total_hits >= 3 or len(paragraph_hits) >= 2):
            continue
        hits = list(matches)
        stance = theme_stance(text, hits)
        related: list[str] = []
        for kw in hits:
            related.extend(tickers_near_keyword(text, kw, tickers))
        deduped: list[str] = []
        seen: set[str] = set()
        for ticker in related:
            if ticker not in seen:
                seen.add(ticker)
                deduped.append(ticker)
        related = deduped[:5]
        first = min((row for rows in matches.values() for row in rows), key=lambda row: row.start())
        quote = re.sub(r"\s+", " ", text[max(0, first.start() - 100):first.end() + 180]).strip()[:300]
        themes.append(
            {
                "theme": theme,
                "stance": stance,
                "tickers": related,
                "quote": quote,
                "confidence": "high" if len(matches) >= 2 and len(paragraph_hits) >= 2 else "med",
                "hit_count": total_hits,
            }
        )
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


def _stable_ref(path: Path) -> str:
    ref = path_to_letters_ref(path)
    if ref:
        return ref
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def source_document_ref(path: Path) -> str:
    candidates = []
    if path.suffix.lower() in {".txt", ".md"}:
        candidates.append(path.with_suffix(".pdf"))
    candidates.append(path)
    for candidate in candidates:
        if candidate.exists():
            return _stable_ref(candidate)
    return _stable_ref(path)


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
                "entity_type": m.get("entity_type"),
                "validation_status": m.get("validation_status"),
                "direction": ACTION_DIRECTION.get(action, "neutral"),
            }
        )
    return positions[:30]


def build_letter_record(
    path: Path,
    resolver: FundResolver,
    master: lm.SecurityMaster,
    persona_cfg: dict,
    document_meta: dict | None = None,
) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    meta = resolver.resolve(path, text)
    document_type, letter_eligible, classification_reason = classify_document(path, text)

    if letter_eligible:
        all_mentions = lm.match_letter(text, master, as_of=meta.get("letter_date"))
        emitted = lm.emitted_mentions(all_mentions, EMIT_MIN_TIER)
        tickers = [m["ticker"] for m in emitted][:40]
        positions = mentions_to_positions(emitted)
        themes = extract_themes(text, tickers)
        sections = extract_sections(text)
    else:
        # Non-letter documents remain discoverable through the document
        # catalog/PDF library, but cannot leak into fund holdings or consensus.
        all_mentions = []
        tickers = []
        positions = []
        themes = []
        sections = {}

    personas = meta.get("maps_to_persona") or []
    if not personas:
        fmap = persona_cfg.get("fund_persona_map") or {}
        fund_lower = (meta.get("fund") or "").lower()
        mgr_lower = (meta.get("manager") or "").lower()
        for k, ps in fmap.items():
            if k in fund_lower or (mgr_lower and k in mgr_lower):
                personas = ps
                break

    document_meta = document_meta or {}
    return {
        "fund_id": meta["fund_id"],
        "fund": meta["fund"],
        "manager": meta.get("manager", ""),
        "strategy": meta.get("strategy", ""),
        "quarter": meta.get("quarter") or "unknown",
        "letter_date": meta.get("letter_date"),
        "date_source": meta.get("date_source"),
        "date_confidence": meta.get("date_confidence"),
        "fund_resolution": meta.get("resolution"),
        "fund_confidence": "high" if meta.get("resolution") == "curated" else "med",
        "document_type": document_type,
        "letter_eligible": letter_eligible,
        "classification_reason": classification_reason,
        "source_file": _stable_ref(path),
        "source_document": source_document_ref(path),
        "canonical_document_id": document_meta.get("canonical_document_id"),
        "content_hash": document_meta.get("content_hash"),
        "content_length": document_meta.get("content_length"),
        "duplicate_sources": document_meta.get("duplicate_sources") or [],
        "duplicate_count": int(document_meta.get("duplicate_count") or 0),
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


def _worker_init() -> None:
    global _WORKER_MASTER, _WORKER_RESOLVER, _WORKER_PERSONA_CFG
    from persona_lens_common import load_personas

    _WORKER_MASTER = load_security_master()
    _WORKER_RESOLVER = FundResolver()
    _WORKER_PERSONA_CFG = load_personas()


def _worker_build(task: tuple[str, dict]) -> dict:
    if _WORKER_MASTER is None or _WORKER_RESOLVER is None or _WORKER_PERSONA_CFG is None:
        _worker_init()
    path_text, document_meta = task
    return build_letter_record(
        Path(path_text),
        _WORKER_RESOLVER,  # type: ignore[arg-type]
        _WORKER_MASTER,  # type: ignore[arg-type]
        _WORKER_PERSONA_CFG,  # type: ignore[arg-type]
        document_meta,
    )


def main() -> int:
    sys_path = ROOT / "_system" / "scripts"
    sys.path.insert(0, str(sys_path))
    from persona_lens_common import load_personas  # noqa: WPS433

    persona_cfg = load_personas()
    master = load_security_master()
    resolver = FundResolver()
    source_files = scan_letter_files()
    files, document_meta_by_path, duplicate_audit = deduplicate_letter_files(source_files)
    tasks = [
        (str(path), document_meta_by_path.get(str(path.resolve()).lower(), {}))
        for path in files
    ]
    workers = max(1, min(int(os.environ.get("LETTER_BUILD_WORKERS", "8")), os.cpu_count() or 1))
    if workers == 1:
        letters = [
            build_letter_record(path, resolver, master, persona_cfg, document_meta)
            for path, (_path_text, document_meta) in zip(files, tasks)
        ]
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init) as pool:
            letters = list(pool.map(_worker_build, tasks, chunksize=8))
        # Worker-local unresolved queues are reconstructed deterministically
        # from their returned normalized identities before writing the review file.
        for row in letters:
            if row.get("fund_resolution") != "normalized":
                continue
            fund_id = row.get("fund_id") or "unknown-fund"
            resolver.unresolved.setdefault(
                fund_id,
                {"fund_id": fund_id, "fund": row.get("fund") or fund_id, "examples": []},
            )
            examples = resolver.unresolved[fund_id]["examples"]
            example = Path(str(row.get("source_file") or "")).stem
            if example and example not in examples and len(examples) < 5:
                examples.append(example)
    resolver.write_unresolved()
    letters, fund_identity_audit = consolidate_letter_funds_stable(letters)
    letters, duplicate_audit = deduplicate_letter_records(letters, duplicate_audit)
    DUPLICATE_AUDIT_PATH.write_text(
        json.dumps(duplicate_audit, indent=2) + "\n", encoding="utf-8"
    )

    with_positions = sum(1 for r in letters if r.get("positions"))
    actionable = sum(
        1
        for r in letters
        if any(p.get("action") in {"add", "trim", "new", "exit", "short", "buy"} for p in (r.get("positions") or []))
    )
    letter_count = len(letters) or 1
    stats = {
        "letters_with_positions_pct": round(with_positions / letter_count, 4),
        "letters_with_actionable_pct": round(actionable / letter_count, 4),
    }

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
        "classification_policy_version": CLASSIFICATION_POLICY_VERSION,
        "letter_count": len(letters),
        "emit_min_tier": EMIT_MIN_TIER,
        "security_master_count": len(master.by_ticker),
        "stats": stats,
        "fund_identity_audit": fund_identity_audit,
        "document_dedup_audit": duplicate_audit,
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
