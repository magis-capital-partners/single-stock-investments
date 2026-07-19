#!/usr/bin/env python3
"""Index page-anchored valuation-method evidence from local research extracts.

This is a discovery index, not an approval mechanism.  It stores hashes and
matched concepts rather than copying the research corpus into the operational
repository.  A candidate can influence production only after it is distilled
into and approved as a versioned method card.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "_system" / "reference" / "valuation_method_registry.json"
OUTPUT = ROOT / "_system" / "research" / "valuation_library_index.json"
TEXT_EXTENSIONS = {".txt", ".md"}
TERM_GROUPS = {
    "royalty_distribution_curve": {"royalty", "production", "reserve", "tons", "depletion", "distribution", "bonus"},
    "net_asset_value": {"asset value", "net asset", "liquidation", "realization", "replacement cost", "sum of the parts"},
    "owner_earnings_reinvestment_dcf": {"owner earnings", "reinvestment", "incremental return", "roic", "free cash flow", "reverse dcf"},
    "midcycle_capacity_value": {"capital cycle", "capacity", "utilization", "mid-cycle", "supply response", "replacement cost"},
    "capital_structure_and_excess_return": {"tangible book", "cost of equity", "return on equity", "credit loss", "regulatory capital", "funding"},
    "probability_weighted_catalyst_nav": {"catalyst", "probability", "break value", "event", "payoff", "liquidation"},
    "risk_adjusted_milestone_value": {"milestone", "success probability", "cash runway", "dilution", "failure", "pipeline"},
    "owner_cash_or_dividend_discount": {"dividend", "required return", "regulated", "contracted", "maintenance capital", "distribution"},
}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paragraph_hash(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode("utf-8")).hexdigest()


def roots(explicit: list[str]) -> list[Path]:
    candidates = [ROOT / "_system" / "reference" / "investment-wisdom"]
    vault = os.getenv("RESEARCH_VAULT_ROOT")
    if vault: candidates.append(Path(vault))
    candidates.extend(Path(value) for value in explicit)
    return sorted({path.resolve() for path in candidates if path.exists()})


def text_files(search_roots: list[Path], maximum: int) -> list[Path]:
    rows = []
    for base in search_roots:
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS and path.stat().st_size <= 20_000_000:
                rows.append(path)
                if len(rows) >= maximum: return rows
    return rows


def portable_ref(path: Path, search_roots: list[Path]) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        pass
    for index, base in enumerate(search_roots, 1):
        try:
            return f"library://root-{index}/{path.resolve().relative_to(base.resolve()).as_posix()}"
        except ValueError:
            continue
    return f"library://external/{path.name}"


def page_paragraphs(text: str):
    pages = text.split("\f")
    for page_number, page in enumerate(pages, 1):
        for paragraph_number, paragraph in enumerate(re.split(r"\n\s*\n", page), 1):
            normalized = re.sub(r"\s+", " ", paragraph).strip()
            if len(normalized) >= 80:
                yield page_number, paragraph_number, normalized


def build(search_roots: list[Path], maximum_files: int = 10_000, maximum_hits_per_method: int = 100, maximum_bytes: int = 250_000_000) -> dict:
    approved = {row["method_id"] for row in json.loads(REGISTRY.read_text(encoding="utf-8")).get("method_cards") or [] if row.get("status") == "approved"}
    hits = {method: [] for method in approved}
    scanned, errors, total_bytes = [], [], 0
    for path in text_files(search_roots, maximum_files):
        if all(len(hits[method]) >= maximum_hits_per_method for method in approved):
            break
        if total_bytes + path.stat().st_size > maximum_bytes:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            digest = file_hash(path)
            ref = portable_ref(path, search_roots)
            scanned.append({"path": ref, "bytes": path.stat().st_size, "sha256": digest})
            total_bytes += path.stat().st_size
            for page, paragraph, content in page_paragraphs(text):
                lower = content.lower()
                for method, terms in TERM_GROUPS.items():
                    if method not in approved or len(hits[method]) >= maximum_hits_per_method: continue
                    matched = sorted(term for term in terms if term in lower)
                    if len(matched) < 2: continue
                    hits[method].append({
                        "source_path": ref, "source_sha256": digest,
                        "page": page, "paragraph": paragraph,
                        "paragraph_sha256": paragraph_hash(content),
                        "matched_concepts": matched, "score": len(matched),
                        "review_status": "candidate_unreviewed",
                    })
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    for method in hits:
        hits[method].sort(key=lambda row: (-row["score"], row["source_path"], row["page"], row["paragraph"]))
    counts = Counter({method: len(rows) for method, rows in hits.items()})
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority": "discovery_only",
        "production_rule": "Candidate passages cannot affect valuation until an approved method-card version cites and encodes the method.",
        "roots": [{"id": f"root-{index}", "name": path.name} for index, path in enumerate(search_roots, 1)],
        "files_scanned": len(scanned),
        "bytes_scanned": total_bytes,
        "limits": {"maximum_files": maximum_files, "maximum_bytes": maximum_bytes, "maximum_hits_per_method": maximum_hits_per_method},
        "candidate_counts": dict(sorted(counts.items())),
        "candidates": hits,
        "source_manifest_hash": paragraph_hash(json.dumps(scanned, sort_keys=True)),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", default=[])
    parser.add_argument("--max-files", type=int, default=10_000)
    parser.add_argument("--max-bytes", type=int, default=250_000_000)
    parser.add_argument("--max-hits-per-method", type=int, default=100)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = build(roots(args.root), args.max_files, args.max_hits_per_method, args.max_bytes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"files_scanned": payload["files_scanned"], "bytes_scanned": payload["bytes_scanned"], "candidate_counts": payload["candidate_counts"]}, sort_keys=True))
    return 1 if payload["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
