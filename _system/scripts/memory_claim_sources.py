#!/usr/bin/env python3
"""Extract supplemental claim rows from deep dives, adversarial reviews, and valuation."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EXEC_SUMMARY_RE = re.compile(
    r"##\s*Executive summary\s*\n+(.+?)(?=\n##\s|\Z)",
    re.I | re.S,
)
RISKS_RE = re.compile(r"##\s*Risks(?:\s*&\s*inversion)?\s*\n+(.+?)(?=\n##\s|\Z)", re.I | re.S)
RETURNS_RE = re.compile(r"\*\*Returns statement:\*\*\s*(.+?)(?:\n|$)", re.I)
ADVERSARIAL_FACT_RE = re.compile(r"^\s*[-*]\s*\*\*Factual[^:]*:\*\*\s*(.+)$", re.I | re.M)
ADVERSARIAL_GAP_RE = re.compile(r"^\s*[-*]\s*\*\*(?:Inference|Short)[^:]*:\*\*\s*(.+)$", re.I | re.M)


def _latest_md(research: Path, prefix: str) -> Path | None:
    files = sorted(research.glob(f"{prefix}_*.md"), reverse=True)
    return files[0] if files else None


def _bullet_lines(section: str, limit: int = 4) -> list[str]:
    lines = []
    for raw in section.splitlines():
        line = re.sub(r"^\s*[-*]\s*", "", raw.strip())
        line = re.sub(r"\*\*", "", line)
        if len(line) >= 24:
            lines.append(line[:320])
        if len(lines) >= limit:
            break
    return lines


def from_deep_dive(ticker: str, ticker_dir: Path) -> list[dict]:
    research = ticker_dir / "research"
    path = _latest_md(research, "deep_dive")
    if not path:
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    date_m = re.search(r"deep_dive_(\d{4}-\d{2}-\d{2})\.md$", path.name)
    as_of = date_m.group(1) if date_m else None
    rows: list[dict] = []

    sm = EXEC_SUMMARY_RE.search(text)
    if sm:
        summary = re.sub(r"\*\*", "", sm.group(1).strip())
        summary = re.sub(r"\s+", " ", summary)
        if len(summary) >= 40:
            rows.append(
                {
                    "ticker": ticker,
                    "source": "deep_dive",
                    "claim_type": "thesis",
                    "direction": "neutral",
                    "title": "Deep dive executive summary",
                    "summary": summary[:320],
                    "observed_at": as_of,
                    "impact_axis": "variant_view",
                    "evidence_ref": rel,
                    "evidence_label": "Deep dive",
                }
            )

    rm = RETURNS_RE.search(text)
    if rm:
        statement = re.sub(r"\s+", " ", rm.group(1).strip())
        if len(statement) >= 20:
            rows.append(
                {
                    "ticker": ticker,
                    "source": "deep_dive",
                    "claim_type": "variant_view",
                    "direction": "neutral",
                    "title": "Returns statement",
                    "summary": statement[:320],
                    "observed_at": as_of,
                    "impact_axis": "variant_view",
                    "evidence_ref": rel,
                    "evidence_label": "Deep dive",
                }
            )

    risks = RISKS_RE.search(text)
    if risks:
        for line in _bullet_lines(risks.group(1), limit=3):
            rows.append(
                {
                    "ticker": ticker,
                    "source": "deep_dive",
                    "claim_type": "risk",
                    "direction": "bearish",
                    "title": "Deep dive risk",
                    "summary": line,
                    "observed_at": as_of,
                    "impact_axis": "risk",
                    "evidence_ref": rel,
                    "evidence_label": "Deep dive",
                }
            )
    return rows


def from_adversarial(ticker: str, ticker_dir: Path) -> list[dict]:
    research = ticker_dir / "research"
    path = _latest_md(research, "adversarial")
    if not path:
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    date_m = re.search(r"adversarial_(\d{4}-\d{2}-\d{2})\.md$", path.name)
    as_of = date_m.group(1) if date_m else None
    rows: list[dict] = []
    for match in ADVERSARIAL_FACT_RE.finditer(text):
        summary = re.sub(r"\s+", " ", match.group(1).strip())[:320]
        if len(summary) >= 20:
            rows.append(
                {
                    "ticker": ticker,
                    "source": "adversarial_review",
                    "claim_type": "risk",
                    "direction": "bearish",
                    "title": "Adversarial factual flag",
                    "summary": summary,
                    "observed_at": as_of,
                    "impact_axis": "risk",
                    "evidence_ref": rel,
                    "evidence_label": "Adversarial",
                }
            )
    for match in ADVERSARIAL_GAP_RE.finditer(text):
        summary = re.sub(r"\s+", " ", match.group(1).strip())[:320]
        if len(summary) >= 20:
            rows.append(
                {
                    "ticker": ticker,
                    "source": "adversarial_review",
                    "claim_type": "risk",
                    "direction": "bearish",
                    "title": "Adversarial review gap",
                    "summary": summary,
                    "observed_at": as_of,
                    "impact_axis": "risk",
                    "evidence_ref": rel,
                    "evidence_label": "Adversarial",
                }
            )
    return rows


def from_valuation_stance(ticker: str, ticker_dir: Path) -> list[dict]:
    val_path = ticker_dir / "research" / "valuation.json"
    if not val_path.exists():
        return []
    try:
        val = json.loads(val_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    classification = val.get("classification") or {}
    stance_raw = classification.get("stance") or val.get("stance")
    stance = stance_raw if isinstance(stance_raw, str) else (stance_raw.get("value") if isinstance(stance_raw, dict) else None)
    implied = classification.get("implied_irr") or val.get("implied_irr")
    if not stance and implied is None:
        return []
    parts = []
    if stance:
        parts.append(f"Stance: {stance}.")
    if implied is not None:
        parts.append(f"Implied return: {implied}%.")
    note = classification.get("normalization_note") or val.get("normalization_note")
    if note:
        parts.append(str(note)[:180])
    summary = " ".join(parts).strip()
    if len(summary) < 20:
        return []
    direction = "bullish" if stance in {"buy", "strong_buy", "core"} else "neutral"
    if stance in {"avoid", "sell", "trim"}:
        direction = "bearish"
    return [
        {
            "ticker": ticker,
            "source": "deep_dive",
            "claim_type": "variant_view",
            "direction": direction,
            "title": "Valuation stance",
            "summary": summary[:320],
            "observed_at": classification.get("analysis_as_of") or val.get("as_of"),
            "impact_axis": "variant_view",
            "evidence_ref": str(val_path.relative_to(ROOT)).replace("\\", "/"),
            "evidence_label": "valuation.json",
        }
    ]


def supplemental_claim_rows(ticker: str, ticker_dir: Path) -> list[dict]:
    rows: list[dict] = []
    rows.extend(from_deep_dive(ticker, ticker_dir))
    rows.extend(from_adversarial(ticker, ticker_dir))
    rows.extend(from_valuation_stance(ticker, ticker_dir))
    return rows


BIOTECH_QUANT_DIR = ROOT / "_system" / "reference" / "biotech-quant"
SYNTHESIS_PATH = BIOTECH_QUANT_DIR / "SYNTHESIS.md"
FACTOR_SPEC_PATH = BIOTECH_QUANT_DIR / "FACTOR_SPEC.json"
METHODOLOGY_BULLET_RE = re.compile(
    r"^##\s*5\.\s*Methodology claim bullets.*?\n+(.*?)(?=\n##\s|\Z)",
    re.I | re.S,
)
NUMBERED_CLAIM_RE = re.compile(r"^\s*\d+\.\s+(.+)$", re.M)


def from_biotech_methodology(limit: int = 20) -> list[dict]:
    """Evergreen methodology claims from the biotech-quant library (context tier)."""
    rows: list[dict] = []
    if not SYNTHESIS_PATH.exists():
        return rows
    text = SYNTHESIS_PATH.read_text(encoding="utf-8", errors="ignore")
    section = METHODOLOGY_BULLET_RE.search(text)
    body = section.group(1) if section else text
    evidence_ref = str(SYNTHESIS_PATH.relative_to(ROOT)).replace("\\", "/")
    paper = BIOTECH_QUANT_DIR / "papers" / "verdad_biotech_investing_2026.pdf"
    if paper.exists():
        evidence_ref = str(paper.relative_to(ROOT)).replace("\\", "/")
    for match in NUMBERED_CLAIM_RE.finditer(body):
        summary = re.sub(r"\s+", " ", match.group(1).strip())[:320]
        if len(summary) < 24:
            continue
        rows.append(
            {
                "ticker": None,
                "source": "biotech_quant_library",
                "claim_type": "methodology",
                "direction": "neutral",
                "title": "Biotech quant methodology",
                "summary": summary,
                "observed_at": "2026-07-09",
                "impact_axis": "variant_view",
                "evidence_ref": evidence_ref,
                "evidence_label": "Verdad / synthesis",
                "score": 18,
            }
        )
        if len(rows) >= limit:
            break
    if FACTOR_SPEC_PATH.exists():
        try:
            spec = json.loads(FACTOR_SPEC_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            spec = {}
        banned = spec.get("banned_for_biotech") or []
        if banned:
            rows.append(
                {
                    "ticker": None,
                    "source": "biotech_quant_library",
                    "claim_type": "methodology",
                    "direction": "neutral",
                    "title": "Biotech quant banned metrics",
                    "summary": (
                        "Biotech overlay bans traditional metrics: "
                        + ", ".join(str(b) for b in banned)
                        + "."
                    )[:320],
                    "observed_at": "2026-07-09",
                    "impact_axis": "variant_view",
                    "evidence_ref": str(FACTOR_SPEC_PATH.relative_to(ROOT)).replace("\\", "/"),
                    "evidence_label": "FACTOR_SPEC",
                    "score": 16,
                }
            )
    return rows[:limit]


def load_biotech_factor_spec() -> dict:
    if not FACTOR_SPEC_PATH.exists():
        return {}
    try:
        return json.loads(FACTOR_SPEC_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
