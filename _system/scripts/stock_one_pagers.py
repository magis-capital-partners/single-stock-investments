"""Company-specific research briefs for every stock. Published models retain authority."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
import json
from copy import deepcopy
from pathlib import Path
import re
from functools import lru_cache

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


_PUBLICATION_INPUTS = {}


def set_publication_inputs(root: Path, document: dict) -> None:
    if document.get("schema_version") != "stock-research-universe.v1" or not document.get("companies"):
        raise ValueError("Invalid stock research input snapshot")
    _PUBLICATION_INPUTS[root.resolve()] = document["companies"]
    universe_inputs.cache_clear()


@lru_cache(maxsize=4)
def universe_inputs(root: Path) -> dict:
    """One private snapshot, loaded once, keeps histories out of Git and boot data."""
    if root.resolve() in _PUBLICATION_INPUTS:
        return _PUBLICATION_INPUTS[root.resolve()]
    # Reading research in a unit test or an editor must never acquire credentials
    # or silently download the private archive. Publication restores it explicitly.
    return read_json(root / "_system/reference/stock-research/universe.json").get("companies", {})


def company_profile(ticker: str, row: dict, contract: dict, raw: dict | None = None) -> dict:
    if ticker in PROFILES:
        return dict(PROFILES[ticker])
    classification = row.get("classification") or {}
    archetype = classification.get("archetype") or "unknown"
    method = (contract.get("method_route") or {}).get("profile_id") or (row.get("valuation_decision") or {}).get("method_profile")
    # SEC's industry code is preferable to broad narrative keyword matching.
    sic = str((raw or {}).get("sic") or row.get("sic") or "")
    instrument = str(row.get("instrument_type") or classification.get("instrument_type") or "").lower()
    bank = all((raw or {}).get("facts", {}).get("us-gaap", {}).get(tag) for tag in ("Deposits", "InterestIncomeExpenseNet"))
    kind = "fund" if instrument in {"etf", "mutualfund", "fund", "closed_end_fund"} or sic.startswith(("672", "673")) else "development" if ticker.endswith(".CVR") or instrument == "contingent_value_right" else "bank" if bank or sic.startswith(("602", "603", "609")) else (
        "holding" if archetype in {"holding_co", "holding_company"} else
        "property" if sic in {"6798", "6510", "6512", "6513"} else
        "insurance" if sic.startswith(("631", "632", "633", "635", "636")) else
        "development" if archetype in {"biotech", "optionality"} or method == "binary_milestone" else
        "cyclical" if archetype in {"cyclical", "capital_cycle", "commodity_cyclical", "resource"} or method == "capital_cycle" else
        "infrastructure" if archetype in {"infrastructure", "croupier"} else "operating")
    templates = {
        "fund": ("Fund and pooled investments", "Start with the holdings, net asset value, fees and distributions. Compare shareholder returns with the mandate and a relevant benchmark in the same currency.", "Concentrated holdings, leverage, fees and a widening discount to net assets can reduce shareholder returns.", ["Underlying holdings", "Net asset value", "Fees and leverage", "Premium or discount", "Distributions"], ["assets", "cash"]),
        "operating": ("Operating company", "Follow sales, margins, reinvestment and cash generation per share. Compare growth with the capital and dilution needed to produce it.", "Slower demand, weaker pricing or rising reinvestment needs can reduce shareholder cash generation.", ["Demand and pricing", "Margins", "Cash conversion", "Reinvestment", "Share count"], ["revenue", "operating_income", "free_cash_flow"]),
        "bank": ("Bank and lending", "Read net interest income, fees, deposits and loans together. Check credit losses and capital before treating earnings as distributable cash.", "Credit losses, funding costs and capital requirements can rise together and constrain shareholder distributions.", ["Net interest income", "Fees", "Funding and deposits", "Credit losses", "Capital per share"], ["net_interest_income", "net_income", "equity"]),
        "holding": ("Holding company and investments", "Start with attributable net assets and the share count. Trace each underlying interest, taxes, debt and minority claims before adding values.", "Concentration, illiquidity, taxes and overlapping ownership can prevent an apparent asset discount from being realized.", ["Attributable net assets", "Look-through ownership", "Taxes and debt", "Capital allocation", "Share count"], ["equity", "net_income", "cash"]),
        "property": ("Property and real assets", "Compare property income with recurring maintenance, occupancy and financing costs. Review asset values and debt maturities alongside earnings.", "Vacancies, refinancing costs and capital spending can weaken distributions even when accounting asset values appear stable.", ["Occupancy and rents", "Property income", "Recurring capital spending", "Debt maturities", "Value per share"], ["revenue", "ocf", "net_income"]),
        "insurance": ("Insurance", "Separate underwriting results from investment income. Review reserves, claims development, capital and book value per share.", "Underpriced risks, reserve shortfalls and investment losses can impair both earnings and capital.", ["Underwriting discipline", "Claims and reserves", "Investment income", "Capital adequacy", "Book value per share"], ["net_income", "equity", "revenue"]),
        "development": ("Development and milestone-led company", "Follow the dated milestones, available cash and financing needs. Separate current operations from outcomes that depend on future approvals or commercialization.", "Milestone delays, unsuccessful development and new funding can reduce or dilute the value of potential outcomes.", ["Dated milestones", "Cash runway", "Probability of success", "Funding needs", "Dilution"], ["cash", "ocf", "net_income"]),
        "cyclical": ("Cyclical and resource company", "Compare profits across the cycle with capacity, pricing and sustaining capital. Check balance-sheet resilience under weaker demand or commodity prices.", "Peak margins can overstate sustainable earnings while new capacity, weaker pricing and debt increase downside.", ["Prices and demand", "Capacity and utilization", "Mid-cycle margins", "Sustaining capital", "Balance sheet"], ["revenue", "operating_margin", "free_cash_flow"]),
        "infrastructure": ("Infrastructure and transaction networks", "Follow usage or transaction activity, pricing, operating leverage and the capital needed to maintain the network.", "Lower activity, regulation or competing infrastructure can weaken pricing power and returns on invested capital.", ["Activity and volumes", "Pricing", "Network economics", "Operating leverage", "Reinvestment"], ["revenue", "operating_income", "free_cash_flow"]),
    }
    title, focus, countercase, drivers, metrics = templates[kind]
    components = contract.get("economic_ownership_map") or ((row.get("valuation_workbench") or {}).get("business") or {}).get("components") or []
    labels = [c.get("label") for c in components if isinstance(c, dict) and c.get("label") and c.get("treatment") != "embedded"]
    description = "Published business components: " + "; ".join(labels[:3]) + "." if labels else "A company description has not yet been published. The financial history, model and research library below show the evidence currently available."
    return {"type": title, "category": kind, "description": description, "focus": focus,
            "countercase": countercase, "drivers": drivers, "chart_metrics": metrics,
            "kpis": list(dict.fromkeys([*metrics, "net_income", "cash", "equity", "diluted_shares"])),
            "key_inputs": [], "model_note": focus + " Assumptions and values below retain the published model's scope, dates and currency."}

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

IFRS_TAGS = {
    "revenue": ["Revenue"], "operating_income": ["ProfitLossFromOperatingActivities"],
    "net_income": ["ProfitLossAttributableToOwnersOfParent"],
    "diluted_eps": ["DilutedEarningsLossPerShare"], "diluted_shares": ["AdjustedWeightedAverageShares"],
    "assets": ["Assets"], "cash": ["CashAndCashEquivalents"], "equity": ["EquityAttributableToOwnersOfParent"],
    "liabilities": ["Liabilities"], "ocf": ["CashFlowsFromUsedInOperatingActivities"],
    "capex": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
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


def near_fiscal_end(end: date, fiscal_end: str) -> bool:
    month, day = map(int, fiscal_end.split("-"))
    return min(abs((end - date(y, month, min(day, monthrange(y, month)[1]))).days)
               for y in (end.year - 1, end.year, end.year + 1)) <= 14


def fiscal_start(end: date, year_end: str) -> date:
    month, day = map(int, year_end.split("-"))
    year = end.year if (end.month, end.day) <= (month, day) else end.year + 1
    return date(year - 1, month, day) + timedelta(days=1)


def _source(cik, item, tag, namespace="us-gaap"):
    accn = item.get("accn", "")
    return {"ref": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json",
            "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{accn}-index.html" if accn else f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json",
            "locator": f"{namespace}:{tag}; {item.get('start', 'instant')} to {item['end']}",
            "filed": item.get("filed"), "accession": accn}


def sec_series(raw: dict, metric: str, fiscal_end: str | None, currency: str = "USD") -> dict:
    label, statement, unit, tags = METRICS[metric]
    unit = unit.replace("USD", currency)
    collected = {}
    cik = raw.get("cik", 0)
    candidates = [("us-gaap", tag) for tag in tags] + [("ifrs-full", tag) for tag in IFRS_TAGS.get(metric, [])]
    for rank, (namespace, tag) in enumerate(candidates):
        for item in raw.get("facts", {}).get(namespace, {}).get(tag, {}).get("units", {}).get(unit, []):
            if item.get("form") not in {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A", "6-K"} or not isinstance(item.get("val"), (int, float)):
                continue
            end = item.get("end", "")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
                continue
            key = (item.get("start"), end)
            # Prefer the latest comparative/restatement; tag preference breaks ties.
            score = (item.get("filed", ""), -rank, item.get("accn", ""))
            if key not in collected or score > collected[key][0]:
                collected[key] = (score, item, tag, namespace)
    annual, quarter, cumulative = {}, {}, {}
    for _, item, tag, namespace in collected.values():
        end = date.fromisoformat(item["end"])
        point = {"period": item["end"], "value": item["val"], "source": _source(cik, item, tag, namespace), "basis": "reported"}
        if statement == "balance":
            if item.get("start"):
                continue
            quarter[item["end"]] = point
            if fiscal_end and near_fiscal_end(end, fiscal_end):
                annual[item["end"]] = point
            continue
        if not item.get("start"):
            continue
        start = date.fromisoformat(item["start"])
        days = (end - start).days
        point["start"] = item["start"]
        if 300 <= days <= 380:
            annual[item["end"]] = point
        if 60 <= days <= 110:
            quarter[item["end"]] = point
        if 60 <= days <= 380:
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
    if re.fullmatch(r"[A-Z]{3}", by_id[left].get("unit", "")) and re.fullmatch(r"[A-Z]{3}", by_id[right].get("unit", "")) and by_id[left]["unit"] != by_id[right]["unit"]:
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


def normalized_series(raw: dict) -> list:
    """Use the maintained quarterly cache without relabelling annual/YTD flows."""
    mapping = {"revenues": "revenue", "operating_income": "operating_income", "net_income": "net_income",
               "cfo": "ocf", "cash": "cash", "total_assets": "assets", "stockholders_equity": "equity"}
    # A Q4 explicitly derived from an annual filing identifies a fiscal boundary.
    # `fp=FY` alone does not: annual filings can repeat earlier quarter facts.
    annual_ends = {p["period"] for key, metric in mapping.items() if METRICS[metric][1] != "balance"
                   for p in raw.get("metrics", {}).get(key) or []
                   if p.get("derived") == "ytd_difference" and p.get("fp") == "FY"
                   and p.get("form") in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}}
    result = []
    for key, metric in mapping.items():
        observations = raw.get("metrics", {}).get(key) or []
        currencies = {p.get("currency") or "USD" for p in observations}
        if len(currencies) != 1:
            continue
        currency = next(iter(currencies))
        label, statement, unit, _ = METRICS[metric]
        points = []
        for p in observations:
            if not isinstance(p.get("value"), (int, float)) or not p.get("period"):
                continue
            points.append({"period": p["period"], "value": p["value"],
                           "basis": p.get("derived") or "reported quarterly" if statement != "balance" else "reported instant",
                           "source": {"url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(raw.get('cik') or 0):010d}.json",
                                      "ref": f"_system/reference/market-data/fundamentals/{raw.get('ticker')}.json",
                                      "locator": str(p.get("tag") or key) + "; period " + p["period"], "filed": p.get("filed")}})
        points.sort(key=lambda p: p["period"])
        annual = []
        for i, point in enumerate(points):
            if point["period"] not in annual_ends:
                continue
            if statement == "balance":
                annual.append(point)
                continue
            group = points[max(0, i - 3):i + 1]
            if len(group) != 4 or not all(60 <= (date.fromisoformat(b["period"]) - date.fromisoformat(a["period"])).days <= 110 for a, b in zip(group, group[1:])):
                continue
            annual.append({**point, "value": sum(p["value"] for p in group),
                           "basis": "sum of four sourced quarters ending at an annual-filing boundary",
                           "source_refs": [p["source"] for p in group]})
        result.append({"id": metric, "label": label, "statement": statement,
                       "unit": unit.replace("USD", currency), "annual": annual, "quarterly": points})
    return result


def financials(root: Path, ticker: str, profile: dict | None = None, cached: dict | None = None) -> dict:
    profile = profile or PROFILES.get(ticker, {})
    raw = read_json(root / ticker / "research/evidence/sec_companyfacts.json")
    cached = read_json(root / "_system/reference/stock-research" / f"{ticker}_financial_history.json") or cached or {}
    fiscal_end = profile.get("fiscal_end")
    currency = cached.get("currency") or "USD"
    series, notes = [], []
    if raw.get("facts"):
        # Choose a single reported monetary currency from the latest annual facts.
        choices = []
        annual_ends = []
        for namespace, facts in raw["facts"].items():
            if namespace not in {"us-gaap", "ifrs-full"}:
                continue
            for key in ("revenue", "net_income", "ocf"):
                for tag in METRICS[key][3] if namespace == "us-gaap" else IFRS_TAGS.get(key, []):
                    for unit, points in facts.get(tag, {}).get("units", {}).items():
                        if not re.fullmatch(r"[A-Z]{3}", unit):
                            continue
                        for p in points:
                            if p.get("start") and p.get("end") and 300 <= (date.fromisoformat(p["end"]) - date.fromisoformat(p["start"])).days <= 380:
                                choices.append((p["end"], p.get("filed", ""), unit))
                                annual_ends.append(p["end"])
        if choices:
            currency = max(choices)[2]
        if not fiscal_end and annual_ends:
            fiscal_end = max(annual_ends)[5:]
        bank = ticker == "TBBK" or profile.get("category") == "bank"
        excluded = {"revenue", "operating_income"} if bank else {"net_interest_income", "noninterest_income", "noninterest_expense", "credit_provision", "deposits", "loans", "loan_allowance"}
        series = [sec_series(raw, key, fiscal_end, currency) for key in METRICS if key not in excluded]
        series = [r for r in series if r["annual"] or r["quarterly"]]
    if not series:
        normalized = normalized_series(read_json(root / "_system/reference/market-data/fundamentals" / f"{ticker}.json"))
        series = deepcopy(cached.get("series") or normalized)
        by_id = {s["id"]: s for s in series}
        for incoming in normalized:
            target = by_id.get(incoming["id"])
            if target is None:
                series.append(incoming)
            elif target["unit"] == incoming["unit"]:
                points = {p["period"]: p for p in target.get("quarterly", [])}
                for point in incoming["quarterly"]:
                    previous = points.get(point["period"])
                    if previous is None or (point.get("source", {}).get("filed") or "") > (previous.get("source", {}).get("filed") or ""):
                        points[point["period"]] = point
                target["quarterly"] = sorted(points.values(), key=lambda p: p["period"])
        notes = cached.get("notes", [])
        fiscal_end = fiscal_end or cached.get("fiscal_year_end")
        annual_dates = [p["period"] for s in series for p in s.get("annual", [])]
        if not fiscal_end and annual_dates:
            fiscal_end = max(annual_dates)[5:]
        units = [s["unit"] for s in series if re.fullmatch(r"[A-Z]{3}", s.get("unit", ""))]
        if units:
            currency = units[0]
    elif cached.get("series"):
        by_id = {s["id"]: s for s in series}
        for incoming in cached["series"]:
            if incoming["id"] not in by_id:
                series.append(incoming)
                continue
            target = by_id[incoming["id"]]
            if target["unit"] != incoming["unit"]:
                continue
            for frequency in ["annual", "quarterly"]:
                points = {p["period"]: p for p in target[frequency]}
                for point in incoming.get(frequency, []):
                    previous = points.get(point["period"])
                    if previous is None or (point.get("source", {}).get("filed") or "") >= (previous.get("source", {}).get("filed") or ""):
                        points[point["period"]] = point
                target[frequency] = sorted(points.values(), key=lambda p: p["period"])
    existing = {s["id"] for s in series}
    if "free_cash_flow" not in existing:
        derived_series(series, "free_cash_flow", "Operating cash flow less capital expenditure", "ocf", "capex", lambda a, b: a - b, unit=currency, statement="cashflow")
    if "operating_margin" not in existing:
        derived_series(series, "operating_margin", "Operating margin", "operating_income", "revenue", lambda a, b: a / b * 100 if b else None, unit="percent")
    if "bank_operating_income" not in existing:
        derived_series(series, "bank_operating_income", "Net interest income + non-interest income", "net_interest_income", "noninterest_income", lambda a, b: a + b, unit=currency)
    if "book_value_per_share" not in existing:
        derived_series(series, "book_value_per_share", "Book value per common share", "equity", "shares", lambda a, b: a / b if b else None, unit=currency+"/shares", statement="balance")
    dates = [p["period"] for s in series for p in s.get("quarterly", []) + s.get("annual", [])]
    annual_dates = [p["period"] for s in series for p in s.get("annual", [])]
    return {"currency": currency, "fiscal_year_end": fiscal_end,
            "latest_fiscal_year_end": max(annual_dates) if annual_dates else None, "latest_period": max(dates) if dates else None,
            "series": series, "notes": ["Fiscal years are labelled by period end. Blank cells mean no comparable sourced value.",
                "Quarterly cash flows derived from YTD use explicit period differences. Stock measures are never summed.",
                "Annual sums from quarterly caches require four consecutive quarters and an explicit annual-minus-nine-month observation. Filing-year labels alone never identify a fiscal boundary.",
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


def build_one_pager(root: Path, ticker: str, row: dict | None = None) -> dict:
    row = row or {}
    cached = universe_inputs(root).get(ticker) or {}
    contract = read_json(root / ticker / "research/valuation_contract.json")
    thesis = read_json(root / ticker / "research/thesis_card.json")
    raw = read_json(root / ticker / "research/evidence/sec_companyfacts.json")
    industry = read_json(root / "_system/reference/market-data/fundamentals/_sic_map.json").get(ticker) or {}
    raw_profile = {**raw, "sic": raw.get("sic") or industry.get("sic")}
    profile_row = {**row, "instrument_type": (cached.get("performance") or {}).get("instrument_type") or row.get("instrument_type")}
    profile = company_profile(ticker, profile_row, contract, raw_profile) if raw or industry or not cached.get("profile") or ticker in PROFILES else {**cached["profile"]}
    assumptions = assumption_rows(contract) if contract else (cached.get("model") or {}).get("assumptions") or []
    published_forecast = row.get("shared_forecast") or {}
    source_forecast = contract.get("shared_forecast") or cached.get("source_forecast") or {}
    reference_only = bool(row) and (
        (source_forecast.get("calculation_id") or source_forecast.get("forecast_hash"))
        != (published_forecast.get("calculation_id") or published_forecast.get("forecast_hash"))
        or source_forecast.get("model_as_of") != published_forecast.get("model_as_of")
    )
    # Models published after the snapshot expose their own full input list. Do
    # not silently attach old inputs to a newer valuation.
    if published_forecast.get("model_assumptions") and (reference_only or not assumptions):
        assumptions = [{"id": a.get("id"), "label": a.get("label") or a.get("id"), "component": "Published forecast",
                        "kind": a.get("kind") or "assumption", "unit": a.get("unit"), "rationale": a.get("rationale"),
                        "source": a.get("source") or {}, "values": a.get("values") or {"base": a.get("value")}}
                       for a in published_forecast["model_assumptions"] if isinstance(a, dict)]
    performance = read_json(root / "_system/reference/stock-research" / f"{ticker}_total_return.json") or cached.get("performance") or {}
    if performance.get("benchmark_ref"):
        benchmark = read_json(root / "_system/reference/stock-research/SPY_total_return.json") or (universe_inputs(root).get("SPY") or {}).get("performance") or {}
        if benchmark.get("currency") == performance.get("currency"):
            performance = {**performance, "benchmark": benchmark}
    risks = (contract.get("monitoring") or {}).get("falsifiers") or cached.get("risks") or []
    if not risks:
        specs = read_json(root / ticker / "research/falsifier_specs.json").get("specs", [])
        risks = [s.get("derived_from") or s.get("falsifier") or s.get("description") for s in reversed(specs)]
    risks = list({json.dumps(r, sort_keys=True): r for r in risks if r}.values())
    components = contract.get("economic_ownership_map") or []
    model = {"as_of": (contract.get("dates") or {}).get("model_as_of") or contract.get("as_of"),
             "basis": (contract.get("valuation") or {}).get("output_basis"),
             "source_ref": f"{ticker}/research/valuation_contract.json",
             "components": [{"id": c.get("component_id"), "label": c.get("label"), "method": c.get("method"),
                             "treatment": c.get("treatment"), "included_in": c.get("included_in_component_id"),
                             "range": c.get("range_per_share")} for c in components]} if contract else dict(cached.get("model") or {})
    if not model.get("components"):
        workbench = ((row.get("valuation_workbench") or {}).get("business") or {}).get("components") or []
        model["components"] = [{"id": c.get("component_id"), "label": c.get("label"), "method": c.get("method"), "treatment": c.get("treatment"),
                                "included_in": c.get("included_in_component_id"), "range": c.get("range_per_share")} for c in workbench]
    model.update(assumptions=assumptions, reference_only=reference_only)
    if reference_only and published_forecast.get("model_assumptions"):
        # The current forecast's cash-flow schedule remains available in the row.
        # Old component prices must not acquire the newer forecast's date.
        model["components"] = []
        model["source_ref"] = published_forecast.get("source_model_ref") or model.get("source_ref")
    model["currency"] = (published_forecast.get("quote") or {}).get("currency") or (row.get("units") or {}).get("currency") or model.get("currency") or "USD"
    model.setdefault("source_ref", published_forecast.get("source_model_ref"))
    model["as_of"] = published_forecast.get("model_as_of") if reference_only and published_forecast.get("model_assumptions") else model.get("as_of") or published_forecast.get("model_as_of")
    history = financials(root, ticker, profile, cached.get("financials"))
    thesis_text = thesis.get("why_market_wrong") or cached.get("thesis") or ""
    return {"schema_version": "stock-one-pager.v1", "ticker": ticker, "profile": profile,
            "financials": history, "performance": performance, "model": model,
            "source_forecast": {k: source_forecast.get(k) for k in ("calculation_id", "forecast_hash", "model_as_of")},
            "thesis": re.sub(r"\*\*|\[(?:Fact|Inference|Assumption)\]", "", str(thesis_text)).strip(),
            "risks": risks,
            "source_refs": [f"{ticker}/research/thesis_card.json", f"{ticker}/research/valuation_contract.json"],
            "coverage": {"assumptions": len(assumptions), "authority": "presentation_only",
                         "financial_history": "sourced" if history["series"] else "unavailable"}}
