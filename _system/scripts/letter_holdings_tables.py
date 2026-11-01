"""Explicit dated valuation tables in letters, including issuers without tickers."""

import re
from datetime import datetime


def extract_tables(text):
    # Conservative schema: explicit largest-holdings heading, named fund and
    # as-of date, shares held and market value columns. Never parse attribution,
    # illustrative investments, costs, vintages or returns as portfolio weights.
    heading = re.compile(
        r"(?:largest|top|portfolio) holdings in\s+(?P<fund>[A-Z][A-Z0-9-]{1,14})\s+as of\s+"
        r"(?P<date>[A-Z][a-z]+\s+\d{1,2},\s+\d{4})\s*:",
        re.I,
    )
    result = []
    for match in heading.finditer(text):
        body = text[match.end() : match.end() + 2400]
        stop = re.search(r"(?m)^\s*Total\b", body)
        if not stop:
            continue
        body = body[: stop.start()]
        if not re.search(r"Shares\s+Held", body, re.I) or not re.search(
            r"Market\s+Value", body, re.I
        ):
            continue
        rows = []
        for row in re.finditer(
            r"(?m)^\s*(?P<issuer>[A-Z][A-Za-z .&'’/-]{2,85}?)\s+"
            r"(?P<shares>\d{1,3}(?:,\d{3})+)\s+\$[\d.]+\s+\$[\d.]+\s+\d{4}\s+[\d.]+x\s*$",
            body,
        ):
            rows.append(
                {
                    "issuer": row["issuer"].strip(),
                    "ticker": "",
                    "shares": float(row["shares"].replace(",", "")),
                    "weight_pct": None,
                    "weight_basis": None,
                    "source_kind": "fund_disclosure",
                    "evidence_quote": row[0].strip(),
                }
            )
        if rows:
            result.append(
                {
                    "vehicle_name": match["fund"],
                    "period_end": datetime.strptime(match["date"], "%B %d, %Y")
                    .date()
                    .isoformat(),
                    "date_basis": "explicit_table_as_of",
                    "positions": rows,
                }
            )
    return result
