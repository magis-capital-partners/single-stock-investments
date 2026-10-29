#!/usr/bin/env python3
"""Turn one verified activist filing into pending claim proposals.

The output is JSON that ``agent_proposals.py`` accepts. This module does not
submit, and it never marks a claim approved. Submit with::

  python _system/scripts/agent_proposals.py submit proposal.json

``provenance.source_paths`` is the SEC filing URL and the accession. Percent
of class is a share of the class. It is not a return and is not rescaled.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

LABELS = ("campaign", "control filing", "governance agreement", "passive")
ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SEC_HOSTS = frozenset({"www.sec.gov", "sec.gov", "data.sec.gov"})
AGENT = "activism-desk"

REQUIRED = (
    "subject_ticker",
    "subject_cik",
    "filer_name",
    "filer_cik",
    "form",
    "accession",
    "filing_date",
    "label",
    "source_url",
)


def normalize_cik(value: Any, *, field: str) -> str:
    digits = str(value).strip()
    if not digits.isdigit() or not 1 <= len(digits) <= 10:
        raise ValueError(f"{field} must be a 1 to 10 digit CIK")
    return digits.zfill(10)


def _require_text(filing: dict[str, Any], field: str) -> str:
    value = filing.get(field)
    if value is None or not str(value).strip():
        raise ValueError(f"missing {field}")
    return str(value).strip()


def _sec_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() not in SEC_HOSTS:
        raise ValueError("source_url must be an https SEC filing URL")
    return value.strip()


def _optional_number(filing: dict[str, Any], field: str) -> int | float | None:
    if field not in filing or filing[field] is None or filing[field] == "":
        return None
    value = filing[field]
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{field} must be a number")
    number = float(value) if isinstance(value, str) else value
    if isinstance(number, float) and number.is_integer():
        return int(number)
    return number


def _default_statement(filing: dict[str, Any], *, percent: int | float | None, shares: int | float | None) -> str:
    bits = [
        f"{filing['filer_name']} filed {filing['form']} on {filing['subject_ticker']}",
        f"dated {filing['filing_date']}",
        f"accession {filing['accession']}",
    ]
    if percent is not None:
        bits.append(f"{percent} percent of the class")
    if shares is not None:
        bits.append(f"{shares} shares")
    sentence = ", ".join(bits) + "."
    return f"{sentence} Label: {filing['label']}."


def proposals_from_filing(filing: dict[str, Any]) -> list[dict[str, Any]]:
    """Build one pending claim proposal for a verified filing.

    Returns a list so callers can concatenate several filings. One filing
    produces one proposal. The proposal status is left unset so
    ``agent_proposals.submit`` stamps ``pending_human_review``.
    """
    if not isinstance(filing, dict):
        raise ValueError("filing must be an object")
    cleaned: dict[str, Any] = {}
    for field in REQUIRED:
        cleaned[field] = _require_text(filing, field)
    cleaned["subject_ticker"] = cleaned["subject_ticker"].upper()
    cleaned["subject_cik"] = normalize_cik(cleaned["subject_cik"], field="subject_cik")
    cleaned["filer_cik"] = normalize_cik(cleaned["filer_cik"], field="filer_cik")
    if not ACCESSION_RE.fullmatch(cleaned["accession"]):
        raise ValueError("accession must look like 0001104659-26-119439")
    if not DATE_RE.fullmatch(cleaned["filing_date"]):
        raise ValueError("filing_date must be YYYY-MM-DD")
    label = cleaned["label"].lower()
    if label not in LABELS:
        raise ValueError(f"label must be one of: {', '.join(LABELS)}")
    cleaned["label"] = label
    source_url = _sec_url(cleaned["source_url"])
    percent = _optional_number(filing, "percent_of_class")
    shares = _optional_number(filing, "shares")
    statement = str(filing.get("statement") or "").strip() or _default_statement(
        cleaned, percent=percent, shares=shares
    )
    payload: dict[str, Any] = {
        "statement": statement,
        "claim_type": "fact",
        "status": "pending",
        "source_path": source_url,
        "source_locator": cleaned["accession"],
        "label": cleaned["label"],
        "subject_ticker": cleaned["subject_ticker"],
        "subject_cik": cleaned["subject_cik"],
        "filer_name": cleaned["filer_name"],
        "filer_cik": cleaned["filer_cik"],
        "form": cleaned["form"],
        "accession": cleaned["accession"],
        "filing_date": cleaned["filing_date"],
    }
    if percent is not None:
        # Share of the class. Not a per-year return, so leave the number as filed.
        payload["percent_of_class"] = percent
    if shares is not None:
        payload["shares"] = shares
    for extra in ("event_date", "amendment_no", "security_title", "corrections", "issuer_tickers"):
        if filing.get(extra) not in (None, "", []):
            payload[extra] = filing[extra]
    summary = str(filing.get("summary") or "").strip() or statement
    proposal = {
        "agent": AGENT,
        "kind": "claim",
        "ticker": cleaned["subject_ticker"],
        "summary": summary,
        "payload": payload,
        "provenance": {
            "source_paths": [source_url, cleaned["accession"]],
            "as_of": cleaned["filing_date"],
        },
    }
    return [proposal]


def proposals_from_filings(filings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for filing in filings:
        out.extend(proposals_from_filing(filing))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=Path, help="One filing object, or a list of them")
    parser.add_argument("--out", type=Path, default=None, help="Write a JSON list of proposals")
    args = parser.parse_args(argv)
    raw = json.loads(args.file.read_text(encoding="utf-8"))
    filings = raw if isinstance(raw, list) else [raw]
    proposals = proposals_from_filings(filings)
    text = json.dumps(proposals, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {len(proposals)} proposal(s) to {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
