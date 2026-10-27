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
            r"(?m)^\s*(?P<issuer>[^\W\d_][^\r\n]{2,85}?)\s+"
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
    result.extend(_portfolio_valuations(text))
    return result


def _portfolio_valuations(text):
    """Read dated quantity-first stock tables, excluding cash and attribution."""
    heading = re.compile(
        r"(?m)^\s*Portfolio Valuation[ \t]*\r?\n\s*"
        r"(?P<fund>[^\r\n]{3,140})\r?\n\s*"
        r"(?P<date>[A-Z][a-z]+\s+\d{1,2},\s+\d{4})\s*\r?\n", re.I
    )
    number = r"\(?-?\d[\d,]*(?:\.\d+)?\)?"
    price = r"\(?-?\d[\d,]*\.\d+\)?"
    row_pattern = re.compile(
        rf"(?P<shares>\d[\d,]*(?:\.\d+)?)\s+(?P<issuer>\S.*?)\s+"
        rf"(?P<price>{price})\s+(?P<value>{number})(?:\s+(?P<rest>.*))?"
    )

    def numeric(value):
        return float(value.replace(",", "").replace("(", "-").replace(")", ""))

    result = []
    for match in heading.finditer(text):
        body = text[match.end():match.end() + 9000]
        total = re.search(rf"(?m)^\s*TOTAL\s+ASSETS\s+({number})\b", body)
        if not total:
            continue
        body = body[:total.start()]
        if not re.search(
            r"UNITS\s+SECURITY\s+PRICE\s+VALUE\s+COST\s+COST\s+"
            r"GAIN/LOSS\s+ASSETS\s+INCOME\s+YIELD", body, re.I
        ):
            continue
        assets = numeric(total[1])
        rows, in_stocks = [], False
        section = r"[A-Z0-9 &/(),.-]+-\s*[a-z]{3}"
        currencies = set(re.findall(r"(?mi)^[A-Z0-9 &/(),.-]+-\s*([a-z]{3})\s*$", body))
        for line in body.splitlines():
            line = line.strip()
            if re.fullmatch(section, line, re.I):
                in_stocks = bool(re.fullmatch(r"COMMON\s+STOCKS\s*-\s*usd", line, re.I))
                continue
            if not in_stocks:
                continue
            if re.fullmatch(rf"{number}(?:\s+{number})+", line):
                in_stocks = False
                continue
            # Repair a split decimal without inventing missing digits or columns.
            normalized = re.sub(r"(?<=\d)\s+(?=\.\d{2}\b)", "", line)
            row = row_pattern.fullmatch(normalized)
            if not row or not any(character.isalpha() for character in row["issuer"]):
                continue
            value = numeric(row["value"])
            if value < 0:
                continue
            shares = numeric(row["shares"])
            issuer = row["issuer"].strip()
            split_price = re.search(r"\s+(\d+)$", issuer)
            if split_price and not re.search(r"(?:Class|Cl|Series|Ser)\s+\d+$", issuer, re.I):
                implied = value / shares if shares else 0
                joined = split_price[1] + row["price"]
                if abs(numeric(row["price"]) - implied) > 0.011 and abs(numeric(joined) - implied) <= 0.011:
                    issuer = issuer[:split_price.start()]
            weight = None
            values = [row["price"], row["value"], *(row["rest"] or "").split()]
            if (len(values) == 8 and all(re.fullmatch(number, v) for v in values)
                    and assets > 0 and {c.lower() for c in currencies} == {"usd"}):
                reported = numeric(values[5])
                if 0 <= reported <= 100 and abs(reported - 100 * value / assets) <= 0.11:
                    weight = reported
            rows.append({
                "issuer": issuer,
                "ticker": "",
                "shares": shares,
                "value_usd": value,
                "weight_pct": weight,
                "weight_basis": "reported_fund_assets" if weight is not None else None,
                "source_kind": "fund_disclosure",
                "evidence_quote": line,
            })
        if rows:
            result.append({
                "vehicle_name": match["fund"].strip(),
                "period_end": datetime.strptime(re.sub(r"\s+", " ", match["date"]), "%B %d, %Y").date().isoformat(),
                "date_basis": "explicit_table_as_of",
                "positions": rows,
            })
    return result
