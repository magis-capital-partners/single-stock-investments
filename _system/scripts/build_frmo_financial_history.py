"""Extract numerical FRMO statement rows with exact PDF page locators.

Reads existing company reports only. An additional official report may be passed
with --extra; this command never downloads reports or stores their narrative.
"""
from __future__ import annotations
import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re

from stock_one_pagers import fiscal_start, months_before

ROOT = Path(__file__).resolve().parents[2]
LABELS = {
    "assets": (r"total assets", "Total assets", "balance"),
    "cash": (r"cash and cash equivalents", "Cash and cash equivalents", "balance"),
    "liabilities": (r"total liabilities", "Total liabilities", "balance"),
    "equity": (r"stockholders.? equity attributable to the company", "Equity attributable to FRMO shareholders", "balance"),
    "revenue": (r"total revenue", "Total reported revenue, including investment gains", "income"),
    "net_income": (r"net income(?: \(loss\))? attributable to the company", "Net income attributable to FRMO shareholders", "income"),
    "diluted_eps": (r"(?:basic and diluted|diluted)", "Diluted earnings per share", "income"),
    "ocf": (r"net cash (?:flows )?(?:provided by|used in|from)(?: \(used in\))? operating activities", "Operating cash flow", "cashflow"),
}
NUMBER = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\s*\)?|(?<!\w)-(?!\w)")


def amounts(value):
    result = []
    for token in NUMBER.findall(value.replace("$", "")):
        token = token.replace(" ", "").strip()
        if token == "-":
            result.append(0.0)
        else:
            result.append(float(token.replace(",", "").replace("(", "-").replace(")", "")))
    return result


def extract(path: Path, period: str, official_url: str | None = None) -> list:
    from pypdf import PdfReader
    annual = "annual" in path.name.lower()
    reader = PdfReader(path)
    result, seen = [], set()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    for page_number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        flat = " ".join(text.split()).lower()
        # Primary statements precede notes and restatement reconciliation tables.
        for statement, heading in [("balance", "balance sheets"), ("income", "statements of income"), ("income", "statements of operations"), ("cashflow", "statements of cash flows")]:
            if statement in seen or heading not in flat or len(NUMBER.findall(text)) < 25:
                continue
            if statement == "balance" and "total assets" not in flat:
                continue
            if statement == "income" and not re.search(r"net income(?: \(loss\))? attributable to the company", flat):
                continue
            if statement == "cashflow" and "operating activities" not in flat:
                continue
            # Exclude prose and the notes' before/after restatement columns.
            if "revision adjustments" in flat or "as previously" in flat:
                continue
            seen.add(statement)
            scale = 1000 if re.search(r"in thousands|amounts in thousands", flat) else 1
            source = {"ref": official_url or f"FRMO/investor-documents/ir-frmo/{path.name}",
                      "url": (official_url + f"#page={page_number}") if official_url else None,
                      "locator": f"PDF page {page_number}; {heading}", "content_sha256": digest,
                      "report_period": period}
            lines = text.splitlines()
            for identity, (pattern, label, group) in LABELS.items():
                if group != statement:
                    continue
                for index, line in enumerate(lines):
                    normalized = " ".join(line.split())
                    match = re.match(r"^" + pattern + r"\s+([\d$()\-].*)$", normalized, re.I)
                    if not match:
                        continue
                    values = amounts(match.group(1))
                    if not values and index + 1 < len(lines):
                        values = amounts(lines[index + 1])
                    if not values:
                        continue
                    for col, end in [(0, period), (1, f"{int(period[:4])-1}{period[4:]}")]:
                        if col >= len(values) or not annual and col > 0:
                            continue
                        value_scale = 1 if identity == "diluted_eps" else scale
                        point = {"period": end, "value": values[col] * value_scale, "source": {**source, "locator": source["locator"] + "; " + normalized.split("$")[0].strip()},
                                 "basis": "reported; latest available comparative", "revision_period": period}
                        if statement != "balance":
                            point["start"] = fiscal_start(date.fromisoformat(end), "05-31").isoformat() if annual or statement == "cashflow" else months_before(date.fromisoformat(end).replace(day=1), 2).isoformat()
                        field = identity
                        if identity == "revenue":
                            field = "operating_revenue" if period >= "2026-05-31" else "revenue_including_investment_gains"
                            label = "Operating revenue, excluding investment gains" if field == "operating_revenue" else "Revenue including investment gains (prior presentation)"
                        result.append((field, label, statement, "annual" if annual else "ytd" if statement == "cashflow" else "quarterly", point))
                    break
            if statement == "balance":
                # Reported shares can be in thousands in the new presentation.
                common = re.search(r"issued and outstanding\s*[-,:]?\s*([\d,]+)\s*shares(?:\s+and\s+([\d,]+)\s*shares)?", flat, re.I)
                if common:
                    for col, end in enumerate([period, f"{int(period[:4])-1}{period[4:]}"] if annual else [period]):
                        share_value = float((common.group(2) if col and common.group(2) else common.group(1)).replace(",", "")) * scale
                        result.append(("shares", "Common shares outstanding", "balance", "annual" if annual else "quarterly",
                            {"period": end, "value": share_value, "source": {**source, "locator": source["locator"] + "; issued and outstanding common shares"}, "basis": "reported", "revision_period": period}))
    return result


def build(root: Path, extra: Path | None = None) -> dict:
    reports = [(p, p.name[:10], None) for p in sorted((root / "FRMO/investor-documents/ir-frmo").glob("*Report.pdf")) if re.match(r"\d{4}-\d{2}-\d{2}", p.name)]
    if extra:
        reports.append((extra, "2026-05-31", "https://www.frmocorp.com/_content/10k/FRMO_Annual_Report_2026.pdf"))
    series = {}
    for path, period, url in reports:
        for identity, label, statement, frequency, point in extract(path, period, url):
            row = series.setdefault(identity, {"id": identity, "label": label, "statement": statement,
                    "unit": "USD/shares" if identity == "diluted_eps" else "shares" if identity == "shares" else "USD",
                    "annual": {}, "quarterly": {}, "ytd": {}})
            target = row[frequency]
            if point["period"] not in target or point["revision_period"] > target[point["period"]]["revision_period"]:
                target[point["period"]] = point
    for row in series.values():
        # Fiscal year-end balances are quarter observations, not summed flows.
        if row["statement"] == "balance":
            row["quarterly"].update(row["annual"])
        if row["statement"] == "cashflow":
            cumulatives = {**row["ytd"], **row["annual"]}
            for end, point in sorted(cumulatives.items()):
                start = fiscal_start(date.fromisoformat(end), "05-31")
                prior = [p for d, p in cumulatives.items() if d < end and fiscal_start(date.fromisoformat(d), "05-31") == start and 60 <= (date.fromisoformat(end) - date.fromisoformat(d)).days <= 110]
                if prior:
                    previous = max(prior, key=lambda p: p["period"])
                    row["quarterly"][end] = {**point, "value": point["value"] - previous["value"], "basis": "derived from YTD difference", "source_refs": [previous["source"], point["source"]]}
                elif (date.fromisoformat(end) - start).days <= 110:
                    row["quarterly"][end] = point
        for frequency in ["annual", "quarterly"]:
            row[frequency] = sorted(row[frequency].values(), key=lambda p: p["period"])
        row.pop("ytd")
    return {"schema_version": "financial-history.v1", "ticker": "FRMO", "currency": "USD", "series": list(series.values()),
            "notes": ["Parent-attributable equity and earnings exclude noncontrolling interests.",
                      "Latest available comparative values supersede earlier presentations. FY2025 was revised in the FY2026 report.",
                      "Revenue including investment gains and the new operating-revenue presentation are separate series and must not be spliced together.",
                      "Historical quarterly reports may precede later revisions; the exact source version is retained on each observation."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extra", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "_system/reference/stock-research/FRMO_financial_history.json")
    args = parser.parse_args()
    output = build(ROOT, args.extra)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print({row["id"]: {key: len(row[key]) for key in ["annual", "quarterly"]} for row in output["series"]})
