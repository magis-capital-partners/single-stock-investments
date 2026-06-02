#!/usr/bin/env python3
"""Build management / transcript evidence for Marvin deep dives."""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TODAY = date.today().isoformat()

MGMT_PATH = re.compile(
    r"(transcript|shareholder.?meeting|annual.?meeting|earnings.?call|"
    r"investor.?day|/transcripts/)",
    re.I,
)

CLAIM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("cashflow_outlook_2026", re.compile(r"cash[- ]?flow\s+positive|revenue[s]?\s+exceed\s+cost|self[- ]?sustain", re.I)),
    ("cashflow_breakeven", re.compile(r"cash\s*flow\s*break[- ]?even|operating\s+loss|burn", re.I)),
    ("copperwood", re.compile(r"copperwood|highland\s+copper", re.I)),
    ("lease_income", re.compile(r"lease\s+(?:income|payment)|royalt", re.I)),
    ("diversification", re.compile(r"diversif|solar|recycl|nickel|lithium|critical\s+mineral", re.I)),
    ("production_timing", re.compile(r"production|commenc|construct|feasibility|permit", re.I)),
]


def parse_date(name: str) -> str:
    m = re.search(r"(20\d{2})[-_]?(0[1-9]|1[0-2])[-_]?(0[1-9]|[12]\d|3[01])", name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def find_docs(ticker_dir: Path) -> list[dict]:
    out: list[dict] = []
    for path in ticker_dir.rglob("*"):
        if path.suffix.lower() not in (".pdf", ".txt", ".md", ".html"):
            continue
        rel = path.relative_to(ticker_dir).as_posix()
        if rel.startswith("research/") or rel.startswith("_"):
            continue
        if not MGMT_PATH.search(rel):
            continue
        out.append(
            {
                "path": rel,
                "filename": path.name,
                "file_date": parse_date(path.name) or parse_date(rel),
                "suffix": path.suffix.lower(),
            }
        )
    out.sort(key=lambda d: (d["file_date"], d["path"]), reverse=True)
    return out


def extract_text(path: Path, suffix: str) -> str:
    if suffix in (".txt", ".md", ".html"):
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages[:100])
        except Exception as e:
            return f"[pdf error: {e}]"
    return ""


def extract_claims(text: str, source: str, file_date: str) -> list[dict]:
    claims: list[dict] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 25:
            continue
        for cid, pat in CLAIM_PATTERNS:
            if pat.search(line) and cid not in seen:
                seen.add(cid)
                claims.append(
                    {
                        "id": cid,
                        "excerpt": line[:500],
                        "source": source,
                        "file_date": file_date,
                        "status": "unverified",
                        "epistemic_tier": "management_statement",
                    }
                )
    return claims


def build_ticker(ticker: str) -> int:
    ticker_dir = ROOT / ticker
    if not ticker_dir.is_dir():
        print(f"SKIP {ticker}")
        return 1
    docs = find_docs(ticker_dir)
    evidence = ticker_dir / "research" / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    all_claims: list[dict] = []
    lines = [
        f"# Management & transcript digest — {ticker}",
        "",
        f"**Generated:** {TODAY}",
        f"**Script:** `build_management_evidence.py`",
        "",
        f"Documents: **{len(docs)}**",
        "",
    ]
    for doc in docs:
        full = ticker_dir / doc["path"]
        text = extract_text(full, doc["suffix"]) if full.is_file() else ""
        claims = extract_claims(text, doc["path"], doc["file_date"])
        all_claims.extend(claims)
        cache = evidence / "_text" / "mgmt"
        cache.mkdir(parents=True, exist_ok=True)
        if text and not text.startswith("[pdf"):
            safe = re.sub(r"[^\w.-]", "_", doc["filename"])[:80]
            (cache / f"{safe}.txt").write_text(text[:250_000], encoding="utf-8")
        lines.append(f"- `{doc['path']}` ({doc['file_date'] or '—'}): {len(claims)} claims")

    if all_claims:
        lines.extend(["", "## Claims", ""])
        for c in all_claims[:40]:
            lines.append(f"### {c['id']}")
            lines.append(f"- Source: `{c['source']}`")
            lines.append(f"- {c['excerpt'][:300]}")
            lines.append("")

    (evidence / f"management_digest_{TODAY}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    facts = {"ticker": ticker, "as_of": TODAY, "document_count": len(docs), "claims": all_claims}
    (evidence / f"management_facts_{TODAY}.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")
    print(f"OK {ticker}: docs={len(docs)} claims={len(all_claims)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="+")
    args = parser.parse_args()
    rc = 0
    for t in args.tickers:
        rc |= build_ticker(t.upper())
    return min(rc, 1)


if __name__ == "__main__":
    raise SystemExit(main())
