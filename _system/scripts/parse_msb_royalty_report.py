#!/usr/bin/env python3
"""Parse Mesabi Trust royalty 8-K Ex. 99.1 → filing panel + evidence JSON.

  python _system/scripts/parse_msb_royalty_report.py
  python _system/scripts/parse_msb_royalty_report.py --write

Context only. Never edits valuation.json IRR fields.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MSB_SEC = ROOT / "MSB" / "investor-documents" / "sec-edgar"
EVIDENCE_OUT = ROOT / "MSB" / "research" / "evidence" / "royalty_report_latest.json"
PANEL_OUT = ROOT / "_system" / "reference" / "market-data" / "themes" / "filing_panels" / "msb_royalty_panel.csv"

TONS_RE = re.compile(
    r"credited Mesabi Trust with\s+([\d,]+)\s+tons of iron ore shipped",
    re.I,
)
BASE_RE = re.compile(r"base royalty of\s+\$?\s*([\d,]+(?:\.\d+)?)", re.I)
BONUS_RE = re.compile(
    r"bonus royalty in the amount of\s+\$?\s*([\d,]+(?:\.\d+)?|\(zero\)|zero)",
    re.I,
)
THRESHOLD_RE = re.compile(
    r"bonus royalty threshold of\s+\$?\s*([\d,]+(?:\.\d+)?)\s*per ton",
    re.I,
)
PERIOD_RE = re.compile(
    r"quarter ended\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
    re.I,
)


def _strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = text.replace("\xa0", " ").replace("&#8220;", '"').replace("&#8221;", '"')
    text = re.sub(r"\s+", " ", text)
    return text


def _parse_money(token: str) -> float:
    t = token.strip().lower().replace(",", "")
    if t in {"(zero)", "zero", "0"}:
        return 0.0
    return float(t)


def _parse_month_day_year(text: str) -> str | None:
    try:
        return datetime.strptime(text.strip(), "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def _royalty_score(raw: str) -> int:
    """Score exhibits; distribution-only 8-Ks mention bonus but lack shipment math."""
    text = raw.lower()
    keys = (
        "tons of iron ore shipped",
        "credited mesabi trust with",
        "bonus royalty threshold",
        "base royalty of",
        "quarterly royalty report",
    )
    return sum(1 for k in keys if k in text)


def find_latest_royalty_exhibit(sec_dir: Path = MSB_SEC) -> Path | None:
    if not sec_dir.exists():
        return None
    scored: list[tuple[int, float, Path]] = []
    for path in sec_dir.iterdir():
        if not path.is_file():
            continue
        name = path.name.lower().replace("-", "").replace("_", "")
        if "exhibit" not in path.name.lower() or "ex99" not in name:
            continue
        if path.suffix.lower() not in {".htm", ".html", ".txt"}:
            continue
        raw = path.read_text(encoding="utf-8", errors="ignore")
        score = _royalty_score(raw)
        if score < 3:
            continue
        scored.append((score, path.stat().st_mtime, path))
    if not scored:
        return None
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return scored[0][2]


def parse_royalty_html(raw: str, *, source_path: str) -> dict:
    text = _strip_html(raw)
    tons_m = TONS_RE.search(text)
    base_m = BASE_RE.search(text)
    bonus_m = BONUS_RE.search(text)
    thr_m = THRESHOLD_RE.search(text)
    period_m = PERIOD_RE.search(text)

    missing = [
        name
        for name, match in [
            ("tons_shipped", tons_m),
            ("base_royalty_usd", base_m),
            ("bonus_royalty_usd", bonus_m),
            ("bonus_threshold_usd", thr_m),
        ]
        if not match
    ]
    if missing:
        raise ValueError(f"royalty parse incomplete; missing {', '.join(missing)}")

    period_end = _parse_month_day_year(period_m.group(1)) if period_m else None
    tons = int(tons_m.group(1).replace(",", ""))
    base = _parse_money(base_m.group(1))
    bonus = _parse_money(bonus_m.group(1))
    threshold = float(thr_m.group(1).replace(",", ""))

    return {
        "ticker": "MSB",
        "operator_ticker": "CLF",
        "mine": "Northshore / Silver Bay",
        "period_end": period_end,
        "as_of": period_end or date.today().isoformat(),
        "tons_shipped": tons,
        "base_royalty_usd": base,
        "bonus_royalty_usd": bonus,
        "bonus_threshold_usd": threshold,
        "bonus_on": bonus > 0,
        "source_path": source_path.replace("\\", "/"),
        "parsed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "in_base_irr": False,
        "note": (
            "Deemed pellet price vs bonus threshold drives bonus switch. "
            "Iron ore spot / CLF steel tons are orientation only."
        ),
    }


def upsert_panel_row(panel_path: Path, row: dict) -> None:
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "as_of",
        "ticker",
        "period_end",
        "tons_shipped",
        "base_royalty_usd",
        "bonus_royalty_usd",
        "bonus_threshold_usd",
        "source_path",
    ]
    rows: list[dict] = []
    if panel_path.exists():
        with panel_path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    key = row.get("period_end") or row.get("as_of")
    kept = [r for r in rows if (r.get("period_end") or r.get("as_of")) != key]
    kept.append(
        {
            "as_of": row.get("as_of") or "",
            "ticker": "MSB",
            "period_end": row.get("period_end") or "",
            "tons_shipped": row.get("tons_shipped"),
            "base_royalty_usd": row.get("base_royalty_usd"),
            "bonus_royalty_usd": row.get("bonus_royalty_usd"),
            "bonus_threshold_usd": row.get("bonus_threshold_usd"),
            "source_path": row.get("source_path") or "",
        }
    )
    kept.sort(key=lambda r: r.get("as_of") or "")
    with panel_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="Write evidence JSON + royalty panel CSV")
    ap.add_argument("--path", type=Path, help="Explicit royalty exhibit path")
    args = ap.parse_args()

    path = args.path or find_latest_royalty_exhibit()
    if not path or not path.exists():
        print("parse_msb_royalty_report: no royalty exhibit found")
        return 1

    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    payload = parse_royalty_html(path.read_text(encoding="utf-8", errors="ignore"), source_path=rel)
    print(
        f"parsed {rel}: tons={payload['tons_shipped']:,} "
        f"bonus=${payload['bonus_royalty_usd']:,.0f} "
        f"threshold=${payload['bonus_threshold_usd']:.2f}"
    )

    if args.write:
        EVIDENCE_OUT.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        upsert_panel_row(PANEL_OUT, payload)
        print(f"wrote {EVIDENCE_OUT.relative_to(ROOT)}")
        print(f"wrote {PANEL_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
