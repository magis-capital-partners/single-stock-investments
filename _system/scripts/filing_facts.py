"""Extract canonical filing metrics from cached full-tier _text extracts.

Used by build_filing_evidence.py → research/evidence/filing_facts_{date}.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# IX line format from build_filing_evidence HTML extract: "Revenues: 619.8"
IX_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)*):\s*([\d,.\-]+|&#8212;|\u2014)$")

CANONICAL = {
    "revenues": (
        "Revenues",
        "Revenue",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": (
        "NetIncomeLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "ProfitLoss",
    ),
    "eps_basic": ("EarningsPerShareBasic",),
    "total_assets": ("Assets",),
    "stockholders_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "long_term_debt": (
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "DebtInstrumentCarryingAmount",
    ),
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
}


def _parse_num(raw: str) -> float | None:
    raw = raw.strip().replace(",", "")
    if raw in ("", "—", "-", "&#8212;"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_ix_fact_lines(text: str) -> dict[str, list[float]]:
    """Return tag → list of numeric values in document order (pairs often current/prior)."""
    out: dict[str, list[float]] = {}
    for line in text.splitlines():
        line = line.strip()
        m = IX_LINE.match(line)
        if not m:
            continue
        tag, val_s = m.group(1), m.group(2)
        val = _parse_num(val_s)
        if val is None:
            continue
        short = tag.split(":")[-1] if ":" in tag else tag
        out.setdefault(short, []).append(val)
    return out


def _first_pair(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"current": None, "prior": None}
    if len(values) == 1:
        return {"current": values[0], "prior": None}
    return {"current": values[0], "prior": values[1]}


def canonical_metrics(ix: dict[str, list[float]]) -> dict:
    metrics: dict = {}
    for canon, tags in CANONICAL.items():
        for tag in tags:
            if tag in ix:
                pair = _first_pair(ix[tag])
                metrics[canon] = {**pair, "tag": tag, "all_values": ix[tag][:6]}
                break
    return metrics


def latest_full_text_path(evidence_dir: Path) -> Path | None:
    text_dir = evidence_dir / "_text"
    if not text_dir.is_dir():
        return None
    files = sorted(text_dir.glob("*.txt"), key=lambda p: p.name, reverse=True)
    prefs = (
        "exhibit99-2",
        "Annual_Report",
        "annual",
        "10-K",
        "10_K",
        "40-F",
        "Semi-Annual",
        "10-Q",
        "10_Q",
        "Quarterly",
        "Interim",
    )
    for pref in prefs:
        for f in files:
            if pref.lower() in f.name.lower() and "mgmt" not in f.parts:
                return f
    return files[0] if files else None


def parse_otc_prose_metrics(text: str) -> dict:
    """Extract disclosure-form metrics from OTC / IR PDF text extracts."""
    metrics: dict = {}
    m = re.search(r"Total shares outstanding:\s*([\d,]+)", text, re.I)
    if m:
        metrics["shares_outstanding"] = {
            "current": int(m.group(1).replace(",", "")),
            "source": "otc_disclosure_form",
        }
    m = re.search(r"over\s+([\d.]+)\s+million\s+acres", text, re.I)
    if m:
        metrics["mineral_acres_gross"] = {
            "current": f">{m.group(1)}M",
            "source": "otc_disclosure_form",
        }
    m = re.search(r"agreement on\s+([\d,]+)\s+acres", text, re.I)
    if m:
        metrics["leased_acres"] = {
            "current": int(m.group(1).replace(",", "")),
            "source": "otc_disclosure_form",
        }
    for label, key in (
        (r"Net income[^\d$]*\$?\s*([\d,]+)", "net_income"),
        (r"Mineral lease[^\d$]*\$?\s*([\d,]+)", "mineral_lease_income"),
        (r"book value[^\d$]*\$?\s*([\d,.]+)\s*per share", "book_value_per_share"),
        (r"Total stockholders[^\']*equity[^\d$]*\$?\s*([\d,]+)", "stockholders_equity"),
    ):
        m = re.search(label, text, re.I)
        if m and key not in metrics:
            raw = m.group(1).replace(",", "")
            try:
                val = float(raw)
            except ValueError:
                continue
            metrics[key] = {"current": val, "source": "otc_prose_regex"}
    return metrics


def build_filing_facts(ticker: str, evidence_dir: Path, source_path: Path | None) -> dict:
    if source_path is None or not source_path.exists():
        return {
            "ticker": ticker,
            "error": "no_full_tier_text_extract",
            "metrics": {},
        }
    text = source_path.read_text(encoding="utf-8", errors="ignore")[:250_000]
    ix = parse_ix_fact_lines(text)
    metrics = canonical_metrics(ix)
    parser = "ix_facts"
    if not metrics:
        otc = parse_otc_prose_metrics(text)
        if otc:
            metrics = otc
            parser = "otc_prose"
    try:
        rel_src = source_path.relative_to(evidence_dir.parent)
    except ValueError:
        rel_src = source_path.name
    out = {
        "ticker": ticker,
        "source_text": str(rel_src).replace("\\", "/"),
        "metrics": metrics,
        "raw_tag_count": len(ix),
        "parser": parser,
    }
    return out


def write_filing_facts_json(ticker_dir: Path, as_of: str) -> Path | None:
    evidence_dir = ticker_dir / "research" / "evidence"
    src = latest_full_text_path(evidence_dir)
    facts = build_filing_facts(ticker_dir.name, evidence_dir, src)
    facts["as_of"] = as_of
    out = evidence_dir / f"filing_facts_{as_of}.json"
    if not evidence_dir.exists():
        return None
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if not facts.get("metrics"):
        candidates = [out] if out.exists() else []
        candidates.extend(sorted(evidence_dir.glob("filing_facts_*.json"), reverse=True))
        for p in candidates:
            if not p.exists():
                continue
            try:
                old = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if old.get("metrics"):
                facts["metrics"] = old["metrics"]
                if p != out:
                    facts["metrics_preserved_from"] = p.name
                break
    out.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    return out
