"""Presentation data for three stock research pilots. No prices or models are recalculated."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
import json
from pathlib import Path
import re

PROFILES = {
    "CPRT": {
        "type": "Operating company · auction marketplace", "fiscal_end": "07-31",
        "description": "Copart connects insurers and other vehicle sellers with buyers through its auction network. Its yards, logistics, buyer participation and insurer relationships support the service revenue earned on each vehicle.",
        "focus": "Follow auction activity and revenue per vehicle, then check how much operating profit becomes cash after maintaining and expanding the yard network.",
        "countercase": "Lower insurer assignments, weaker pricing or higher yard and acquisition costs can reduce cash generation even while reported revenue holds up.",
        "drivers": ["Auction activity", "Revenue per vehicle", "Yard utilization", "Cash conversion", "Reinvestment and acquisitions"],
        "chart_metrics": ["revenue", "operating_income", "free_cash_flow"],
        "kpis": ["revenue", "operating_income", "operating_margin", "free_cash_flow", "diluted_shares"],
        "key_inputs": ["revenue_factor", "equity_margin", "cash_conversion", "maintenance_multiplier", "discount_rate"],
        "model_note": "Operating cash generation, maintenance and growth investment, acquired businesses and shareholder cash flows. Asset value must not be added again when it already supports the operating cash flows.",
    },
    "TBBK": {
        "type": "Bank · fintech sponsorship and specialty lending", "fiscal_end": "12-31",
        "description": "The Bancorp combines payment and fintech sponsorship services with specialty lending. Its economics depend on fee income, the spread earned on funded assets, credit losses and the capital required to support the business.",
        "focus": "Read net interest income and fee income separately. Compare loan growth with deposits and credit costs, and check earnings against equity and the share count.",
        "countercase": "Partner concentration, tighter regulation, rising funding costs or deteriorating loans can weaken earnings and constrain distributions and buybacks.",
        "drivers": ["Net interest income", "Fee income", "Loans and deposits", "Credit losses", "Capital and share count"],
        "chart_metrics": ["net_interest_income", "noninterest_income", "net_income"],
        "kpis": ["net_interest_income", "noninterest_income", "credit_provision", "loans", "deposits", "diluted_shares"],
        "key_inputs": ["growth_rate", "discount_rate", "terminal_multiple", "enhancement_failure_probability"],
        "model_note": "Read the published fintech and lending components separately, including funding, credit losses and required capital. Bank operating cash flow is not a substitute for distributable shareholder earnings.",
    },
    "FRMO": {
        "type": "Holding company · investments and management interests", "fiscal_end": "05-31",
        "description": "FRMO owns investment assets and interests in investment-management and other businesses. Reported consolidated assets include interests attributable to other investors; common shareholders own the parent company's attributable equity.",
        "focus": "Start with equity attributable to FRMO shareholders and book value per share. Then examine concentrated holdings, management-company interests, taxes and the difference between accounting marks and realizable value.",
        "countercase": "Concentrated or illiquid investments, market declines, tax liabilities and overlapping ownership can make apparent discounts difficult to realize.",
        "drivers": ["Attributable book value", "Investment concentration", "Management-company interests", "Tax and minority claims", "Shares outstanding"],
        "chart_metrics": ["book_value_per_share", "equity", "net_income"],
        "kpis": ["book_value_per_share", "equity", "cash", "net_income", "shares"],
        "key_inputs": ["economic_realization_pct", "catalyst_realization_pct", "attributable_liquid_pct", "reserve_m"],
        "model_note": "Look-through net assets and distinct management-company or exchange interests, after tax and other senior claims. Show embedded versus additive ownership explicitly to avoid counting the same assets twice.",
    },
}

# Small, explicit publication inputs; publishing a pilot never checks out an
# issuer's complete document archive or contacts a data provider.
PILOT_INPUT_PATHS = tuple(
    f"{ticker}/research/{name}"
    for ticker in PROFILES
    for name in ("valuation_contract.json", "thesis_card.json", "falsifier_specs.json")
    if ticker != "FRMO" or name != "falsifier_specs.json"
) + tuple(f"{ticker}/research/evidence/sec_companyfacts.json" for ticker in ("CPRT", "TBBK"))

# Only explicit GAAP tags are substituted; unlike bank revenue definitions are not blended.
METRICS = {
    "revenue": ("Revenue", "income", "USD", ["RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenues", "SalesRevenueNet"]),
    "net_interest_income": ("Net interest income", "income", "USD", ["InterestIncomeExpenseNet"]),
    "noninterest_income": ("Non-interest income", "income", "USD", ["NoninterestIncome"]),
    "credit_provision": ("Provision for credit losses", "income", "USD", ["ProvisionForLoanLeaseAndOtherLosses", "ProvisionForLoanAndLeaseLosses"]),
    "noninterest_expense": ("Non-interest expense", "income", "USD", ["NoninterestExpense"]),
    "operating_income": ("Operating income", "income", "USD", ["OperatingIncomeLoss"]),
    "net_income": ("Net income attributable to shareholders", "income", "USD", ["NetIncomeLossAvailableToCommonStockholdersBasic", "NetIncomeLoss"]),
    "diluted_eps": ("Diluted earnings per share", "income", "USD/shares", ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"]),
    "diluted_shares": ("Weighted average diluted shares", "income", "shares", ["WeightedAverageNumberOfDilutedSharesOutstanding"]),
    "assets": ("Total assets", "balance", "USD", ["Assets"]),
    "cash": ("Cash and cash equivalents", "balance", "USD", ["CashAndCashEquivalentsAtCarryingValue"]),
    "equity": ("Equity attributable to shareholders", "balance", "USD", ["StockholdersEquity"]),
    "liabilities": ("Total liabilities", "balance", "USD", ["Liabilities"]),
    "deposits": ("Deposits", "balance", "USD", ["Deposits"]),
    "loans": ("Loans, net of allowance", "balance", "USD", ["FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss", "LoansAndLeasesReceivableNetReportedAmount", "FinancingReceivableRecordedInvestmentExcludingAccruedInterestAfterAllowanceForCreditLoss"]),
    "loan_allowance": ("Allowance for credit losses", "balance", "USD", ["FinancingReceivableAllowanceForCreditLosses", "FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest", "LoansAndLeasesReceivableAllowance"]),
    "ocf": ("Operating cash flow", "cashflow", "USD", ["NetCashProvidedByUsedInOperatingActivities"]),
    "capex": ("Capital expenditures", "cashflow", "USD", ["PaymentsToAcquirePropertyPlantAndEquipment"]),
    "sbc": ("Stock-based compensation", "cashflow", "USD", ["ShareBasedCompensation"]),
}


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def months_before(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 - months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(value.day, monthrange(year, month + 1)[1]))


def fiscal_start(end: date, year_end: str) -> date:
    month, day = map(int, year_end.split("-"))
    year = end.year if (end.month, end.day) <= (month, day) else end.year + 1
    return date(year - 1, month, day) + timedelta(days=1)


def _source(cik, item, tag):
    accn = item.get("accn", "")
    return {"ref": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json",
            "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{accn}-index.html" if accn else f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json",
            "locator": f"us-gaap:{tag}; {item.get('start', 'instant')} to {item['end']}",
            "filed": item.get("filed"), "accession": accn}


def sec_series(raw: dict, metric: str, fiscal_end: str) -> dict:
    label, statement, unit, tags = METRICS[metric]
    collected = {}
    cik = raw.get("cik", 0)
    for rank, tag in enumerate(tags):
        for item in raw.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get(unit, []):
            if item.get("form") not in {"10-K", "10-K/A", "10-Q", "10-Q/A"} or not isinstance(item.get("val"), (int, float)):
                continue
            end = item.get("end", "")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
                continue
            key = (item.get("start"), end)
            # Prefer the latest comparative/restatement; tag preference breaks ties.
            score = (item.get("filed", ""), -rank, item.get("accn", ""))
            if key not in collected or score > collected[key][0]:
                collected[key] = (score, item, tag)
    annual, quarter, cumulative = {}, {}, {}
    for _, item, tag in collected.values():
        end = date.fromisoformat(item["end"])
        point = {"period": item["end"], "value": item["val"], "source": _source(cik, item, tag), "basis": "reported"}
        if statement == "balance":
            if item.get("start"):
                continue
            quarter[item["end"]] = point
            if end.strftime("%m-%d") == fiscal_end:
                annual[item["end"]] = point
            continue
        if not item.get("start"):
            continue
        start = date.fromisoformat(item["start"])
        days = (end - start).days
        point["start"] = item["start"]
        if 300 <= days <= 380 and end.strftime("%m-%d") == fiscal_end:
            annual[item["end"]] = point
        if 60 <= days <= 110:
            quarter[item["end"]] = point
        if start == fiscal_start(end, fiscal_end) and 60 <= days <= 380:
            cumulative[item["end"]] = point
    # A YTD observation becomes a quarter only by subtracting the preceding YTD.
    for end, point in sorted(cumulative.items()):
        if end in quarter or metric == "diluted_eps":
            continue
        previous = [p for d, p in cumulative.items() if d < end and p.get("start") == point.get("start") and 60 <= (date.fromisoformat(end) - date.fromisoformat(d)).days <= 110]
        if previous:
            prior = max(previous, key=lambda p: p["period"])
            amount = point["value"] - prior["value"]
            if metric == "diluted_shares":
                total_days = (date.fromisoformat(end) - date.fromisoformat(point["start"])).days + 1
                prior_days = (date.fromisoformat(prior["period"]) - date.fromisoformat(prior["start"])).days + 1
                amount = (point["value"] * total_days - prior["value"] * prior_days) / (total_days - prior_days)
            quarter[end] = {**point, "start": (date.fromisoformat(prior["period"]) + timedelta(days=1)).isoformat(),
                            "value": amount, "basis": "weighted-average period difference" if metric == "diluted_shares" else "derived from YTD difference",
                            "source_refs": [prior["source"], point["source"]]}
    # Q4 often appears only as the annual amount less the first nine months.
    for end, point in annual.items():
        if end in quarter or statement == "balance" or metric == "diluted_eps":
            continue
        preceding = [p for d, p in cumulative.items() if d < end and p.get("start") == point.get("start") and 60 <= (date.fromisoformat(end) - date.fromisoformat(d)).days <= 110]
        if preceding:
            prior = max(preceding, key=lambda p: p["period"])
            amount = point["value"] - prior["value"]
            if metric == "diluted_shares":
                total_days = (date.fromisoformat(end) - date.fromisoformat(point["start"])).days + 1
                prior_days = (date.fromisoformat(prior["period"]) - date.fromisoformat(prior["start"])).days + 1
                amount = (point["value"] * total_days - prior["value"] * prior_days) / (total_days - prior_days)
            quarter[end] = {**point, "start": (date.fromisoformat(prior["period"]) + timedelta(days=1)).isoformat(),
                            "value": amount, "basis": "weighted-average period difference" if metric == "diluted_shares" else "annual less nine months",
                            "source_refs": [prior["source"], point["source"]]}
    return {"id": metric, "label": label, "statement": statement, "unit": unit,
            "annual": sorted(annual.values(), key=lambda p: p["period"]),
            "quarterly": sorted(quarter.values(), key=lambda p: p["period"])}


def derived_series(series: list, identity: str, label: str, left: str, right: str, operation, unit="USD", statement="income"):
    by_id = {item["id"]: item for item in series}
    if left not in by_id or right not in by_id:
        return
    result = {"id": identity, "label": label, "unit": unit, "statement": statement}
    for frequency in ["annual", "quarterly"]:
        a = {p["period"]: p for p in by_id[left].get(frequency, [])}
        b = {p["period"]: p for p in by_id[right].get(frequency, [])}
        result[frequency] = []
        for period in sorted(a.keys() & b.keys()):
            value = operation(a[period]["value"], b[period]["value"])
            if value is not None:
                result[frequency].append({"period": period, "value": value, "basis": f"derived: {left} and {right}",
                    "source": a[period]["source"], "source_refs": [a[period]["source"], b[period]["source"]]})
    if result["annual"] or result["quarterly"]:
        series.append(result)


def financials(root: Path, ticker: str) -> dict:
    profile = PROFILES[ticker]
    raw = read_json(root / ticker / "research/evidence/sec_companyfacts.json")
    cached = read_json(root / "_system/reference/stock-research" / f"{ticker}_financial_history.json")
    notes = []
    if raw.get("facts"):
        excluded = {"revenue", "operating_income"} if ticker == "TBBK" else {"net_interest_income", "noninterest_income", "noninterest_expense", "credit_provision", "deposits", "loans", "loan_allowance"}
        series = [sec_series(raw, key, profile["fiscal_end"]) for key in METRICS if key not in excluded]
        series = [row for row in series if row["annual"] or row["quarterly"]]
    else:
        series = cached.get("series", [])
        notes = cached.get("notes", [])
    if raw.get("facts") and cached.get("series"):
        by_id = {s["id"]: s for s in series}
        for incoming in cached["series"]:
            if incoming["id"] not in by_id:
                series.append(incoming)
                continue
            row = by_id[incoming["id"]]
            for frequency in ["annual", "quarterly"]:
                points = {p["period"]: p for p in row[frequency]}
                for point in incoming[frequency]:
                    previous = points.get(point["period"])
                    if previous is None or (point.get("source", {}).get("filed") or "") >= (previous.get("source", {}).get("filed") or ""):
                        points[point["period"]] = point
                row[frequency] = sorted(points.values(), key=lambda p: p["period"])
    derived_series(series, "free_cash_flow", "Operating cash flow less capital expenditure", "ocf", "capex", lambda a, b: a - b, statement="cashflow")
    derived_series(series, "operating_margin", "Operating margin", "operating_income", "revenue", lambda a, b: a / b * 100 if b else None, unit="percent")
    derived_series(series, "bank_operating_income", "Net interest income + non-interest income", "net_interest_income", "noninterest_income", lambda a, b: a + b)
    derived_series(series, "book_value_per_share", "Book value per common share", "equity", "shares", lambda a, b: a / b if b else None, unit="USD/shares", statement="balance")
    dates = [p["period"] for s in series for p in s.get("quarterly", []) + s.get("annual", [])]
    return {"currency": "USD", "fiscal_year_end": profile["fiscal_end"], "latest_period": max(dates) if dates else None,
            "series": series, "notes": ["Fiscal years are labelled by their period end. Blank cells mean no comparable sourced value.",
                "Quarterly cash flows derived from YTD use explicit period differences. Stock measures are never summed.",
                "Per-share figures retain the filing's reported comparative basis; no additional split normalization is assumed.", *notes]}


def assumption_rows(contract: dict) -> list:
    rows = {}
    for component in contract.get("economic_ownership_map", []):
        proof = component.get("calculation_proof") or {}
        for case, nodes in (proof.get("traces") or {}).items():
            for node in nodes if isinstance(nodes, list) else []:
                if node.get("kind") in {"output", "calculation", "derived"} or node.get("value") is None:
                    continue
                key = (component.get("component_id"), node.get("id"))
                row = rows.setdefault(key, {"id": node.get("id"), "component": component.get("label") or component.get("component_id"),
                    "label": node.get("label") or str(node.get("id", "")).replace("_", " "), "kind": node.get("kind", "assumption"),
                    "unit": node.get("unit"), "rationale": node.get("rationale"), "source": node.get("source") or {}, "values": {}})
                row["values"][case] = node["value"]
    # New economic schedules declare input nodes directly rather than proof traces.
    def visit(value, component="Business"):
        if isinstance(value, dict):
            if value.get("kind") in {"fact", "estimate", "assumption", "judgment", "parameter"} and "value" in value and (value.get("id") or value.get("label")):
                key = (component, value.get("id") or value.get("label"))
                if key not in rows:
                    rows[key] = {"id": key[1], "component": component, "label": value.get("label") or str(key[1]).replace("_", " "),
                        "kind": value["kind"], "unit": value.get("unit"), "rationale": value.get("rationale"),
                        "source": value.get("source") or {}, "values": {"base": value["value"]}}
            for child in value.values():
                if isinstance(child, (dict, list)):
                    visit(child, component)
        elif isinstance(value, list):
            for child in value:
                visit(child, component)
    for component in contract.get("economic_ownership_map", []):
        visit(component.get("economic_model") or component.get("driver_model") or {}, component.get("label", "Business"))
    return list(rows.values())


def build_one_pager(root: Path, ticker: str, row: dict | None = None) -> dict | None:
    if ticker not in PROFILES:
        return None
    row = row or {}
    profile = PROFILES[ticker]
    contract = read_json(root / ticker / "research/valuation_contract.json")
    thesis = read_json(root / ticker / "research/thesis_card.json")
    assumptions = assumption_rows(contract)
    performance = read_json(root / "_system/reference/stock-research" / f"{ticker}_total_return.json")
    if performance.get("benchmark_ref"):
        benchmark = read_json(root / "_system/reference/stock-research/SPY_total_return.json")
        if benchmark.get("currency") == performance.get("currency"):
            performance = {**performance, "benchmark": benchmark}
    source_forecast = contract.get("shared_forecast") or {}
    published_forecast = row.get("shared_forecast") or {}
    reference_only = bool(row) and (
        (source_forecast.get("calculation_id") or source_forecast.get("forecast_hash"))
        != (published_forecast.get("calculation_id") or published_forecast.get("forecast_hash"))
        or source_forecast.get("model_as_of") != published_forecast.get("model_as_of")
    )
    risks = list(dict.fromkeys(contract.get("monitoring", {}).get("falsifiers", [])))
    if not risks:
        specs = read_json(root / ticker / "research/falsifier_specs.json").get("specs", [])
        risks = list(dict.fromkeys(s.get("derived_from") or s.get("falsifier") or s.get("description") for s in reversed(specs) if s.get("derived_from") or s.get("falsifier") or s.get("description")))
    return {"schema_version": "stock-one-pager.v1", "ticker": ticker, "profile": profile,
            "financials": financials(root, ticker),
            "performance": performance,
            "model": {"as_of": contract.get("dates", {}).get("model_as_of") or contract.get("as_of"),
                      "reference_only": reference_only,
                      "basis": contract.get("valuation", {}).get("output_basis"), "assumptions": assumptions,
                      "source_ref": f"{ticker}/research/valuation_contract.json",
                      "components": [{"id": c.get("component_id"), "label": c.get("label"), "method": c.get("method"),
                          "treatment": c.get("treatment"), "included_in": c.get("included_in_component_id"),
                          "range": c.get("range_per_share")} for c in contract.get("economic_ownership_map", [])]},
            "thesis": re.sub(r"\*\*|\[(?:Fact|Inference|Assumption)\]", "", thesis.get("why_market_wrong") or "").strip(),
            "risks": risks,
            "source_refs": [f"{ticker}/research/thesis_card.json", f"{ticker}/research/valuation_contract.json"],
            "coverage": {"assumptions": len(assumptions), "authority": "presentation_only",
                         "financial_history": "sourced"}}
