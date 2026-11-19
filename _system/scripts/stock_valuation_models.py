"""Source-backed, editable research scenarios. Never changes underwriting authority.

The result is a sensitivity worksheet, not a new approved issuer forecast. Unknown
facts remain null; a share/currency mismatch prevents a numeric return. Terminal
equity proceeds already include the operating balance sheet (no second cash add).
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from functools import lru_cache
import json
import math
from pathlib import Path
import re

INPUT_PATH = "_system/reference/stock-research/valuation-inputs.json"
SCHEMA = "stock-valuation-inputs.v1"
_INPUTS = {}


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def set_valuation_inputs(root: Path, document: dict):
    if document.get("schema_version") != SCHEMA or not isinstance(document.get("companies"), dict):
        raise ValueError("Invalid stock valuation input snapshot")
    if any(ticker != model.get("ticker") for ticker, model in document["companies"].items()):
        raise ValueError("Stock valuation input identity mismatch")
    _INPUTS[root.resolve()] = document["companies"]
    valuation_inputs.cache_clear()


@lru_cache(maxsize=4)
def valuation_inputs(root: Path):
    if root.resolve() in _INPUTS:
        return _INPUTS[root.resolve()]
    path = root / INPUT_PATH
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("companies", {}) if data.get("schema_version") == SCHEMA else {}


def latest(history, identity, *, positive=False):
    series = next((s for s in history.get("series", []) if s["id"] == identity), {})
    # Income/cash flow anchors are annual amounts, never annualized single quarters.
    points = series.get("quarterly", []) if series.get("statement") == "balance" else series.get("annual", [])
    points = [p for p in points if number(p.get("value")) and (not positive or p["value"] > 0)]
    # Do not skip a recent loss in favor of an older positive year.
    if not points:
        return None
    point = max(points, key=lambda p: p["period"])
    return {**point, "unit": series.get("unit"), "metric": identity}


def paired_per_share(history, numerator, denominator="diluted_shares"):
    series = {s["id"]: s for s in history.get("series", [])}
    ns, ds = series.get(numerator, {}), series.get(denominator, {})
    # A flow requires matching fiscal duration, not merely a similar reporting year.
    denominator_points = ds.get("annual", [])
    if numerator in {"equity"} and denominator == "shares":
        numerator_points, denominator_points = ns.get("quarterly") or ns.get("annual", []), ds.get("quarterly") or ds.get("annual", [])
    else:
        numerator_points = ns.get("annual", [])
    shares = {(p.get("start"), p["period"]): p for p in denominator_points}
    matched = []
    for n in numerator_points:
        d = shares.get((n.get("start"), n["period"]))
        if d and number(n.get("value")) and number(d.get("value")) and d["value"] > 0:
            matched.append({**n, "value": n["value"] / d["value"], "unit": ns.get("unit", "") + "/shares",
                            "metric": numerator + "_per_share", "basis": f"{numerator} divided by matching {denominator}",
                            "calculation_inputs": [*(n.get("calculation_inputs") or [{"label": ns.get("label") or numerator, "value": n["value"], "unit": ns.get("unit"), "period": n["period"], "source": n.get("source")}]),
                                                   {"label": ds.get("label") or denominator, "value": d["value"], "unit": "shares", "period": d["period"], "source": d.get("source")}],
                            "source_refs": [*(n.get("source_refs") or [n.get("source")]), *(d.get("source_refs") or [d.get("source")])]})
    return max(matched, key=lambda p: p["period"]) if matched else None


def _source_date(point):
    sources = point.get("source_refs") or [point.get("source") or {}]
    return max([s.get("filed") or s.get("report_period") or point.get("period", "") for s in sources if isinstance(s, dict)], default=point.get("period", ""))


def valid_fx(fx, source, target, quote_day):
    try:
        age = (date.fromisoformat(quote_day)-date.fromisoformat(fx["as_of"])).days
    except (KeyError, ValueError, TypeError):
        return False
    return fx.get("from_currency") == source and fx.get("to_currency") == target and number(fx.get("rate")) and fx["rate"] > 0 and bool(fx.get("source_url")) and 0 <= age <= 7


def build_research_model(ticker, profile, history, quote, raw_model=None, contract=None, *, splits=None, basis_verified=False, published_forecast=None):
    raw_model, contract = raw_model or {}, contract or {}
    category = profile.get("category") or {"CPRT": "operating", "TBBK": "bank", "FRMO": "holding"}.get(ticker, "operating")
    claim_specific = ticker.endswith((".CVR", ".DB")) or bool(re.search(r"\.PS\d+$", ticker))
    if claim_specific:
        category = "development"
    raw_inputs, raw_cases = raw_model.get("inputs") or {}, raw_model.get("scenarios") or {}
    quote = deepcopy(quote or {})
    currency = quote.get("currency") or history.get("currency") or "USD"
    method, anchor = "earnings", None
    blockers, notes = [], []
    recorded_method = raw_model.get("method")
    recorded_date = raw_model.get("as_of") or (contract.get("dates") or {}).get("model_as_of")
    if category == "fund":
        method, anchor = "nav", latest(history, "nav_per_share")
        notes.append("Fund scenarios require reported NAV per share and assumptions for underlying NAV growth, distributions and the exit discount. Market price is not substituted for NAV.")
    elif category in {"holding", "bank", "insurance"}:
        method = "nav" if category == "holding" else "book"
        anchor = latest(history, "book_value_per_share") or paired_per_share(history, "equity", "shares")
        if not anchor and category != "holding":
            method, anchor = "earnings", latest(history, "diluted_eps") or latest(history, "basic_eps")
        notes.append("Book value is an accounting anchor. Check preferred capital, minorities, credit or reserve adequacy and any unrealized asset gains before using it as common-share value.")
    elif not claim_specific:
        anchor = paired_per_share(history, "free_cash_flow")
        if anchor and anchor["value"] > 0:
            method = "owner_cash"
        else:
            method, anchor = "earnings", latest(history, "diluted_eps") or latest(history, "basic_eps") or paired_per_share(history, "net_income")
    # A recorded FCF-per-share input is a dated research anchor, not a fresh filing.
    if not anchor and category not in {"fund", "development", "holding"} and number(raw_inputs.get("fcf_per_share")) and raw_inputs["fcf_per_share"] > 0 and raw_inputs.get("fcf_source"):
        eps_proxy = bool(re.search(r"\bEPS\b|earnings.per.share|net.income", str(raw_inputs["fcf_source"]), re.I)) or category in {"bank", "insurance"}
        method = "earnings" if eps_proxy else "owner_cash"
        anchor = {"value": raw_inputs["fcf_per_share"], "period": (contract.get("dates") or {}).get("latest_fact_as_of"),
                  "unit": currency + "/shares", "source": {"ref": f"{ticker}/research/valuation.json", "locator": raw_inputs["fcf_source"]},
                  "basis": "Recorded earnings proxy" if eps_proxy else "Recorded source-model FCF per share", "recorded_input": True}
    # Explicit future payoffs have timing. A present-value range does not.
    payoff = all(number(raw_cases.get(c, {}).get("payoff")) and number(raw_cases.get(c, {}).get("years")) and 0 < raw_cases[c]["years"] <= 30 for c in ("bear", "base", "bull"))
    if payoff and (not anchor or category == "development") and recorded_date:
        method, anchor = "payoff", None
    if method != "payoff" and (not anchor or anchor["value"] <= 0) and category not in {"bank", "insurance", "holding", "fund"}:
        revenue = paired_per_share(history, "revenue")
        if revenue and revenue["value"] > 0:
            method, anchor = "transition", revenue
        elif category == "development":
            method, anchor = "payoff", None
    if claim_specific:
        method, anchor = "payoff", None
        notes.append("This claim requires its own denomination, dated cash flows and payoff terms. Common-share earnings and common-share prices do not establish this security's value. A terminal-only scenario excludes any interim coupons or distributions.")
        if not quote.get("currency"):
            blockers.append("A verified denomination and unit for this claim are required")
        if quote.get("symbol") and quote["symbol"] != ticker:
            blockers.append("The entry quote must belong to this specific claim rather than the underlying common share")
    labels = {"owner_cash": ("Owner cash and reinvestment", "Annual free cash flow per share"),
              "earnings": ("Earnings and shareholder distributions", "Annual earnings per share"),
              "book": ("Common equity and distributions", "Common book value per share"),
              "nav": ("Asset value and distributions", "Reported NAV per share" if category == "fund" else "Attributable book value per share"),
              "transition": ("Revenue to profitable equity", "Annual revenue per share"),
              "payoff": ("Dated payoff scenarios", "Future payoff per share")}
    name, anchor_label = labels[method]
    if anchor:
        anchor = deepcopy(anchor)
        anchor_currency = str(anchor.get("unit") or "").split("/")[0]
        if anchor_currency != currency:
            fx = quote.get("fx_to_listing") or {}
            if valid_fx(fx, anchor_currency, currency, quote.get("as_of")):
                anchor["reporting_value"], anchor["reporting_currency"] = anchor["value"], anchor_currency
                anchor["value"] *= fx["rate"]
                anchor["unit"] = currency+"/shares"
                anchor["fx_conversion"] = fx
                anchor["source_refs"] = [*(anchor.get("source_refs") or [anchor.get("source")]),
                                         {"url": fx["source_url"], "locator": f"{anchor_currency}/{currency} spot {fx['rate']} at {fx['as_of']}"}]
                notes.append(f"The reported {anchor_currency} anchor is converted to {currency} at the disclosed dated spot rate. FX is held constant through the forecast; future currency changes are an unmodeled research risk.")
            else:
                blockers.append(f"Reporting currency {anchor_currency or 'unknown'} differs from quote currency {currency}; a dated FX conversion is required")
        if not anchor.get("source") and not anchor.get("source_refs"):
            blockers.append("The financial anchor needs a source")
        if not anchor.get("recorded_input"):
            # SEC comparatives are restated through the filing date. Adjust only
            # actions after that version; never adjust an already restated EPS twice.
            source_day = _source_date(anchor)
            ratio = math.prod(s["ratio"] for s in splits or [] if source_day < s["date"] <= quote.get("as_of", ""))
            if anchor.get("vendor_input") and ratio != 1:
                blockers.append("Vendor annual share basis spans a corporate action; reconcile it to the current listed share")
            elif ratio != 1:
                anchor["value"] /= ratio
                anchor["split_adjustment"] = {"ratio": ratio, "after_source_date": source_day, "through": quote.get("as_of")}
            if not basis_verified:
                blockers.append("Verify the listing share basis and corporate-action history before calculating a return")
            if anchor.get("vendor_input"):
                notes.append("The annual financial anchor is a vendor observation for this listing, rather than a filing reconciliation. Native common-share units are assumed to match the reported share; ADR and ambiguous claims remain blocked. Review the source and share basis before decision use.")
        else:
            notes.append("The per-share anchor comes from the dated source model. Its share basis and newer filings need review; it has not been relabelled as a current fact.")
    if ticker in {"BRK.A", "BRK.B", "BRK-B"} and anchor and not anchor.get("recorded_input"):
        blockers.append("Berkshire Class A/Class B attribution requires a verified per-class financial anchor")
    if quote.get("claim_unverified"):
        blockers.append("The listed share/ADR claim needs a verified conversion to the reported financial share")
    if not quote.get("source_url") or not quote.get("as_of"):
        notes.append("A sourced listing quote is unavailable. A manually entered dated entry price is a hypothetical research cost, not an observed market price.")
    cases = {}
    for i, case in enumerate(("bear", "base", "bull")):
        c = {"exit_multiple": (12, 18, 24)[i]}
        if method == "owner_cash":
            c.update(reinvestment=(.2, .35, .5)[i], incremental_roic=(.12, .18, .25)[i])
        elif method == "book":
            c.update(roe=(.06, .1, .14)[i], payout=(.5, .3, .1)[i], exit_multiple=(.6, 1, 1.4)[i])
        elif method == "nav":
            trailing = quote.get("trailing_distributions_per_share")
            yield_anchor = trailing / anchor["value"] if category == "fund" and anchor and anchor["value"] > 0 and number(trailing) else 0
            c.update(growth=(-.05, .03, .08)[i], distribution_yield=yield_anchor,
                     exit_multiple=(.95, 1, 1.05)[i] if category == "fund" else (.6, .85, 1.1)[i])
        elif method == "transition":
            c.update(growth=(0, .1, .2)[i], payout=0, target_margin=(.03, .1, .18)[i], dilution=(.05, .03, .01)[i])
        elif method == "payoff":
            c = {"payoff": None, "payoff_date": None}
            if payoff:
                y = raw_cases[case]["years"]
                start = date.fromisoformat(recorded_date[:10])
                from datetime import timedelta
                c = {"payoff": raw_cases[case]["payoff"], "payoff_date": (start + timedelta(days=round(y * 365.25))).isoformat()}
        else:
            c.update(growth=(0, .04, .08)[i], payout=(.3, .4, .5)[i])
            # Compatible source-model growth/multiples remain explicit research
            # assumptions. No old FCF is quietly converted into distributable EPS.
            rc = raw_cases.get(case) or {}
            if number(rc.get("growth_y1_5")) and number(rc.get("exit_pfcf_y10")) and anchor and anchor.get("recorded_input"):
                c.update(growth=rc["growth_y1_5"], exit_multiple=rc["exit_pfcf_y10"])
        cases[case] = c
    notes += ["Starting ranges are research assumptions, not company guidance or an approved investment case. Review and edit them for this company.",
              "IRR uses the dated entry price, interim shareholder distributions and an exit equity sale. Scenario present value discounts those same proceeds at the required return. No present-value upside is annualized as IRR.",
              "The terminal multiple values equity; cash, debt and retained assets are embedded in that equity value and are not added a second time."]
    if method == "owner_cash":
        notes.append("FCF after reported capital spending is a proxy, not fully normalized owner cash. Growth = incremental reinvestment × incremental return on capital; distributions = modeled cash × (1 − incremental reinvestment). Check maintenance, acquisitions, working capital and stock compensation.")
    if method == "earnings":
        notes.append("Earnings are not automatically cash. Only the assumed payout is distributed; growth and retained-capital needs require company-specific reconciliation. Buybacks are not counted as dividends or automatic share-count reduction.")
    if method == "transition":
        notes.append("No interim cash is assumed. Revenue grows per existing share after annual dilution; the exit uses the assumed future net margin and P/E. Financing, survival and the path to that margin need a separate reconciliation.")
    if method == "nav":
        notes.append("Asset-value growth is the change in NAV after distributions and costs; distribution yield is shown separately. Book value is a proxy where a full look-through NAV has not been reconciled.")
        if category == "fund":
            notes.append("Fund growth and exit premium/discount are exposure sensitivities, not an independently underwritten value of the portfolio. Any distribution starting yield uses trailing vendor cash payments; future distributions and vendor completeness require review. Leverage, futures roll and daily resets need a fund-specific path model.")
    result = {"schema_version": "stock-valuation-model.v1", "ticker": ticker, "authority": "screening_only", "capital_actionable": False,
            "method": method, "label": name, "anchor_label": anchor_label, "currency": currency,
            "inputs": {"entry_price": quote.get("value"), "entry_date": quote.get("as_of"), "anchor": anchor.get("value") if anchor else None,
                       "horizon": 7, "discount_rate": .1}, "anchor": anchor, "quote": quote, "cases": cases,
            "blockers": list(dict.fromkeys(blockers)), "notes": notes,
            "recorded_model": {"method": recorded_method, "as_of": recorded_date, "source_ref": f"{ticker}/research/valuation.json"} if raw_model else None}
    # Prefer a valid issuer cash-flow schedule over a generated sensitivity.
    # Scalar PV/NAV components and hypothetical time-zero settlements are never
    # silently turned into dated proceeds by this presentation worksheet.
    forecasts = [f for f in (contract.get("shared_forecast"), published_forecast) if isinstance(f, dict) and f.get("status") == "available"]
    forecasts.sort(key=lambda f: f.get("model_as_of") or "", reverse=True)
    for f in forecasts:
        if not (f.get("quote") or {}).get("currency") or not (f.get("quote") or {}).get("symbol"):
            continue  # A legacy untyped mark cannot establish the cash-flow claim.
        source_cases = {}
        valid = True
        for name, original in (("bear", "low"), ("base", "base"), ("bull", "high")):
            grouped = {}
            rows = (f.get("forward_cashflow_schedule") or {}).get(original) or []
            if not rows:
                valid = False
            for p in rows:
                when, amount = p.get("date"), p.get("amount_per_share")
                if not when or when <= quote.get("as_of", "") or not number(amount):
                    valid = False
                    break
                point = grouped.setdefault(when, {"date": when, "distribution": 0, "terminal": 0})
                key = "terminal" if re.search(r"terminal|exit|sale|reversion", str(p.get("proof_node") or ""), re.I) else "distribution"
                point[key] += amount
            if any(p["distribution"] + p["terminal"] < 0 for p in grouped.values()):
                valid = False
            source_cases[name] = {"scale": 1, "cashflows": [grouped[k] for k in sorted(grouped)]}
        if not valid:
            continue
        source_quote = f.get("quote") or {}
        source_currency = source_quote.get("currency")
        fixed_blockers = [g for g in blockers if "quote currency" not in g and "financial anchor" not in g and "share basis" not in g]
        if source_currency != currency:
            fixed_blockers.append("Source cash-flow currency differs from the entry quote currency")
        if not source_quote.get("symbol") or source_quote.get("symbol") != quote.get("symbol"):
            fixed_blockers.append("The source cash-flow listing must match the entry quote")
        source_day = source_quote.get("as_of") or f.get("as_of")
        if not source_day or (quote.get("as_of", "") > source_day and not basis_verified):
            fixed_blockers.append("Verify corporate actions between the source cash flows and the entry quote")
        ratio = math.prod(p["ratio"] for p in splits or [] if source_day and source_day < p["date"] <= quote.get("as_of", ""))
        if ratio != 1:
            for case in source_cases.values():
                for p in case["cashflows"]:
                    p["distribution"] /= ratio
                    p["terminal"] /= ratio
        result.update(method="dated_cashflows", label="Recorded issuer cash-flow scenarios", anchor_label="Dated shareholder proceeds", anchor=None,
                      cases=source_cases, blockers=fixed_blockers, source_forecast={"model_as_of": f.get("model_as_of"), "calculation_id": f.get("calculation_id"), "source_refs": f.get("source_refs") or []})
        result["inputs"]["anchor"] = None
        result["notes"] = ["The amounts and dates come from the recorded issuer forecast. Entry price and required return can be changed; cash-flow scale is an explicit sensitivity, not a rewrite of the source assumptions.",
                           "Dated proceeds are held fixed when the entry date changes. A changed entry date cannot reset or extend their realization dates.",
                           "This replay retains research-only authority and does not clear the issuer model's source, underwriting or capital gates."]
        if ratio != 1:
            result["source_forecast"]["share_basis_adjustment"] = {"ratio": ratio, "source_quote_date": source_day, "entry_date": quote.get("as_of")}
            result["notes"].append(f"Source per-share cash flows are divided by the {ratio:g}× corporate-action ratio between the source quote and this entry quote.")
        break
    return result


def model_for_stock(root, ticker, profile, history, row):
    saved = valuation_inputs(root).get(ticker)
    if saved:
        return deepcopy(saved)
    raw_path = root / ticker / "research/valuation.json"
    contract_path = root / ticker / "research/valuation_contract.json"
    def read(path):
        if not path.is_file():
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return {} if value.get("private_snapshot") else value
    return build_research_model(ticker, profile, history, (row.get("shared_forecast") or {}).get("quote"), read(raw_path), read(contract_path), published_forecast=row.get("shared_forecast"))
