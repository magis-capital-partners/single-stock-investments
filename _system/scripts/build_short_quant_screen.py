#!/usr/bin/env python3
"""Quantitative short screen: score every covered name on the short frameworks.

Reads the free, already-collected inputs and nothing else: SEC companyfacts
quarterly series (``market-data/fundamentals``), the technical signal file,
the float/short-interest file, the latest FINRA short-interest file, and the
insider transaction CSVs. No Gateway, no vendor, no network.

Each signal maps to one lens in ``_system/research/short-alpha/frameworks.json``
and is scored 0..1 against a stated threshold, never a percentile, so a score
can be audited against the number it came from. The composite is

    attractiveness = 100 * (0.65 * decay + 0.20 * tape) * (1 - 0.5 * risk)

where ``decay`` averages the fundamental signals that exist for the name,
``tape`` is whether the price trend has already broken, and ``risk`` averages
crowding, illiquidity, volatility and a parabolic tape, the things that turn a
right thesis into a wrong trade. Fewer than three fundamental signals means no
score: a blank sheet is not a clean sheet.

Writes dashboard/data/short_quant_screen.json. The Short Alpha builder joins
it onto the candidate ledger. A score is a reason to open a file, not a thesis.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FUNDAMENTALS = ROOT / "_system" / "reference" / "market-data" / "fundamentals"
FLOAT_ADV = FUNDAMENTALS / "index_float_adv.json"
TECHNICAL = ROOT / "dashboard" / "data" / "technical_signals.json"
FINRA_DIR = ROOT / "_system" / "reference" / "market-data" / "ownership" / "short_interest"
INSIDER_DIR = ROOT / "_system" / "reference" / "market-data" / "insider"
CORE = ROOT / "dashboard" / "data" / "core.json"
SEC_TITLES = ROOT / "_system" / "data" / "sec_company_tickers_cache.json"
CANDIDATES = ROOT / "_system" / "research" / "short-alpha" / "candidates.json"
OUTPUT = ROOT / "dashboard" / "data" / "short_quant_screen.json"

SCHEMA_VERSION = "1.0"
MAX_FUNDAMENTAL_AGE_DAYS = 400
INSIDER_WINDOW_DAYS = 180
MIN_FUNDAMENTAL_SIGNALS = 3
TOP_ROWS = 75

# Signal id -> (framework id, weight inside its group, one-line reading).
FUNDAMENTAL_SIGNALS = {
    "accrual_ratio": ("accounting", 1.0, "Sloan accruals: net income minus operating cash flow over assets."),
    "profit_without_cash": ("earnings_vs_cash", 0.8, "Reported profit that operating cash flow does not back."),
    "cash_burn": ("cash_burn", 1.2, "Years of cash left at the trailing operating burn."),
    "equity_raised": ("dilution_financing", 1.0, "Equity that grew faster than earnings explain: capital raised."),
    "leverage": ("leverage_refinancing", 1.0, "Long-term debt against assets, worse when operating income is negative or equity is gone."),
    "margin_trend": ("margin_contraction", 1.0, "Trailing operating margin against the year before."),
    "revenue_turn": ("cycle_mean_reversion", 0.8, "Revenue growth that has turned down from a high level."),
    "insider_selling": ("promotion_insider_selling", 0.8, "Net open-market insider sales over 180 days against market cap."),
}
TAPE_SIGNALS = {
    "trend_broken": ("path_and_timing", 1.0, "Below the 200-day line with negative 12-1 momentum."),
}
RISK_SIGNALS = {
    "crowding": ("crowding_squeeze", 1.0, "Short interest against float and days to cover."),
    "illiquidity": ("borrow_and_carry", 1.0, "Dollar volume too thin to borrow, size, or exit."),
    "volatility": ("path_and_timing", 1.0, "Realized volatility and beta: how far a wrong week can run."),
    "parabolic": ("crowding_squeeze", 0.8, "Far above the 200-day line after a large run."),
}
THRESHOLDS = {
    "accrual_ratio": {"zero": 0.0, "full": 0.10},
    "cash_burn_years": {"full": 1.0, "zero": 4.0},
    "equity_raised_share": {"zero": 0.02, "full": 0.25},
    "debt_to_assets": {"zero": 0.20, "full": 0.50},
    "margin_trend": {"zero": 0.0, "full": -0.08},
    "revenue_growth": {"zero": 0.0, "full": -0.15},
    "insider_share_of_cap": {"zero": 0.0, "full": 0.005},
    "short_percent_float": {"zero": 0.05, "full": 0.20},
    "days_to_cover": {"zero": 2.0, "full": 8.0},
    "adv_dollar": {"full": 2_000_000, "zero": 10_000_000},
    "realized_vol_pct": {"zero": 35.0, "full": 90.0},
    "distance_200d_pct": {"zero": 20.0, "full": 60.0},
}


SIC_MAP = FUNDAMENTALS / "_sic_map.json"
SIC_USER_AGENT = "single-stock-investments research pipeline (contact: dag5wd@virginia.edu)"
SIC_REQUEST_DELAY_S = 0.15

# What the SIC code says about which lenses apply. A bank's operating cash
# flow is loan and deposit growth, not burn, and an insurer's is premium float;
# a REIT is levered by construction; a trust or blank check is not an operating
# company at all.
#
# Only depository institutions (6020-6099) and insurers (6311-6411) are
# "financial", and credit institutions (6111-6163) are "lenders". Everything
# else under 6000-6799 -- finance services 6199 (bitcoin miners such as WULF,
# IREN, CIFR, RIOT and the crypto treasuries file there), brokers 6211, asset
# managers 6282 -- burns cash, accrues and borrows like an operating company
# and keeps every lens.
#
# A lender's operating cash flow is its loan book: with every lens on, the
# committed inputs scored as of 2026-10-08 put SOFI first (CFO -$8.5B of
# originations against +$636M of profit) and RKT, UPST and FIGR in the top 20
# on that artifact alone.
BANK_SIC = (6020, 6099)
LENDER_SIC = (6111, 6163)
INSURER_SIC = (6311, 6411)
_LENS_OFF = frozenset({"accrual_ratio", "profit_without_cash", "cash_burn", "leverage"})
PROFILE_RULES = {
    "fund_or_trust": {"skip": True, "reason": "Not an operating company: trust, fund, or blank check."},
    "financial": {
        "disable": _LENS_OFF,
        "reason": "Bank, thrift or insurer: deposits, loans and premium float run through operating cash flow and the balance sheet, so the cash-burn, accrual and leverage lenses are off.",
    },
    "lender": {
        "disable": _LENS_OFF,
        "reason": "Lender: loan originations and sales run through operating cash flow and debt funds the book, so the cash-burn, accrual and leverage lenses are off.",
    },
    "real_estate": {"disable": {"leverage"}, "reason": "REIT: leverage is structural, so that lens is off."},
    "operating": {"disable": set(), "reason": None},
}
# Issuers whose EDGAR SIC (6199, finance services) misdescribes the business.
PROFILE_OVERRIDES = {
    "AXP": ("financial", "Bank holding company (American Express National Bank) that EDGAR files under SIC 6199."),
    "SOFI": ("financial", "Bank holding company (SoFi Bank, N.A.) that EDGAR files under SIC 6199."),
    "SYF": ("financial", "Bank holding company (Synchrony Bank) that EDGAR files under SIC 6199."),
    "UPST": ("lender", "Lending marketplace that buys and holds loans; EDGAR files it under SIC 6199."),
}


def profile_for(sic: int | None, ticker: str | None = None) -> str:
    if ticker and str(ticker).upper() in PROFILE_OVERRIDES:
        return PROFILE_OVERRIDES[str(ticker).upper()][0]
    if sic is None:
        return "operating"
    if sic in {6221, 6770} or 6720 <= sic <= 6729:
        return "fund_or_trust"
    if sic == 6798:
        return "real_estate"
    if BANK_SIC[0] <= sic <= BANK_SIC[1] or INSURER_SIC[0] <= sic <= INSURER_SIC[1]:
        return "financial"
    if LENDER_SIC[0] <= sic <= LENDER_SIC[1]:
        return "lender"
    return "operating"


def load_sic_map(ciks: dict[str, str], *, fetch: bool = True) -> dict[str, dict]:
    """ticker -> {cik, sic, description}, cached forever; SIC codes rarely move."""
    cached = _read_json(SIC_MAP, {}) or {}
    missing = {ticker: cik for ticker, cik in ciks.items() if cik and (ticker not in cached or cached[ticker].get("cik") != cik)}
    if fetch and missing:
        import time
        import urllib.request

        for ticker, cik in sorted(missing.items()):
            request = urllib.request.Request(f"https://data.sec.gov/submissions/CIK{cik}.json", headers={"User-Agent": SIC_USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    doc = json.loads(response.read())
            except Exception:  # noqa: BLE001 - a miss is cached as unknown, not fatal
                cached[ticker] = {"cik": cik, "sic": None, "description": None}
            else:
                sic_text = str(doc.get("sic") or "").strip()
                cached[ticker] = {"cik": cik, "sic": int(sic_text) if sic_text.isdigit() else None, "description": doc.get("sicDescription") or None}
            time.sleep(SIC_REQUEST_DELAY_S)
        SIC_MAP.parent.mkdir(parents=True, exist_ok=True)
        SIC_MAP.write_text(json.dumps(cached, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    return cached


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def ramp(value: float | None, zero: float, full: float) -> float | None:
    """Linear 0..1 between ``zero`` and ``full``; the pair may run either way."""
    if value is None or not math.isfinite(value):
        return None
    if zero == full:
        return 1.0 if value >= full else 0.0
    t = (value - zero) / (full - zero)
    return max(0.0, min(1.0, t))


def _parse_period(text: str) -> date | None:
    try:
        return datetime.strptime(str(text)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _quarters(points: list[dict]) -> list[tuple[date, float]]:
    out = []
    for point in points or []:
        period = _parse_period(point.get("period"))
        value = point.get("value")
        if period is None or value is None:
            continue
        try:
            out.append((period, float(value)))
        except (TypeError, ValueError):
            continue
    out.sort()
    return out


def ttm(quarters: list[tuple[date, float]], back: int = 0) -> float | None:
    """Sum of four consecutive quarters ending ``back`` quarters before the last."""
    end = len(quarters) - back
    if end < 4:
        return None
    window = quarters[end - 4:end]
    span = (window[-1][0] - window[0][0]).days
    if not 240 <= span <= 300:
        return None
    return sum(value for _, value in window)


def latest(quarters: list[tuple[date, float]], back: int = 0) -> float | None:
    index = len(quarters) - 1 - back
    return quarters[index][1] if index >= 0 else None


def fundamental_signals(doc: dict, as_of: date) -> tuple[dict, dict]:
    """Return (signals, facts) from one companyfacts series file."""
    metrics = (doc or {}).get("metrics") or {}
    series = {key: _quarters(metrics.get(key)) for key in (
        "revenues", "operating_income", "net_income", "cfo", "cash", "total_assets", "stockholders_equity", "long_term_debt",
    )}
    newest = max((q[-1][0] for q in series.values() if q), default=None)
    facts: dict = {"latest_period": newest.isoformat() if newest else None}
    if newest is None or (as_of - newest).days > MAX_FUNDAMENTAL_AGE_DAYS:
        facts["stale"] = True
        return {}, facts
    facts["stale"] = False

    ni = ttm(series["net_income"])
    cfo = ttm(series["cfo"])
    revenue = ttm(series["revenues"])
    revenue_prior = ttm(series["revenues"], back=4)
    revenue_prior2 = ttm(series["revenues"], back=8)
    oi = ttm(series["operating_income"])
    oi_prior = ttm(series["operating_income"], back=4)
    assets = latest(series["total_assets"])
    assets_prior = latest(series["total_assets"], back=4)
    equity = latest(series["stockholders_equity"])
    equity_prior = latest(series["stockholders_equity"], back=4)
    cash = latest(series["cash"])
    debt = latest(series["long_term_debt"])
    debt_period = series["long_term_debt"][-1][0] if series["long_term_debt"] else None
    if debt_period is not None and (newest - debt_period).days > MAX_FUNDAMENTAL_AGE_DAYS:
        debt = None  # a debt line that stopped reporting is unknown, not zero

    signals: dict = {}

    avg_assets = None
    if assets and assets_prior and assets > 0 and assets_prior > 0:
        avg_assets = (assets + assets_prior) / 2
    elif assets and assets > 0:
        avg_assets = assets
    if ni is not None and cfo is not None and avg_assets:
        value = (ni - cfo) / avg_assets
        signals["accrual_ratio"] = {"value": value, "score": ramp(value, **THRESHOLDS["accrual_ratio"])}
        if ni > 0:
            shortfall = 1 - (cfo / ni) if ni else None
            signals["profit_without_cash"] = {"value": shortfall, "score": ramp(shortfall, 0.0, 1.0)}
        else:
            signals["profit_without_cash"] = {"value": None, "score": 0.0, "note": "No reported profit to test."}

    if cfo is not None and cash is not None:
        if cfo < 0:
            years = cash / -cfo if cfo else None
            signals["cash_burn"] = {"value": years, "score": ramp(years, THRESHOLDS["cash_burn_years"]["zero"], THRESHOLDS["cash_burn_years"]["full"])}
        else:
            signals["cash_burn"] = {"value": None, "score": 0.0, "note": "Operating cash flow is positive."}

    if equity is not None and equity_prior is not None and ni is not None and equity_prior > 0:
        raised = (equity - equity_prior - ni) / equity_prior
        signals["equity_raised"] = {"value": raised, "score": ramp(raised, **THRESHOLDS["equity_raised_share"])}

    if assets and assets > 0:
        if debt is not None:
            ratio = debt / assets
            score = ramp(ratio, **THRESHOLDS["debt_to_assets"]) or 0.0
            note = None
            if oi is not None and oi < 0 and debt > 0:
                score = min(1.0, score + 0.5)
                note = "Operating income is negative with debt outstanding."
            if equity is not None and equity < 0:
                score = 1.0
                note = "Stockholders' equity is negative."
            signals["leverage"] = {"value": ratio, "score": score, **({"note": note} if note else {})}
        elif equity is not None and equity < 0:
            signals["leverage"] = {"value": None, "score": 1.0, "note": "Stockholders' equity is negative."}

    if oi is not None and oi_prior is not None and revenue and revenue_prior and revenue > 0 and revenue_prior > 0:
        margin = oi / revenue
        margin_prior = oi_prior / revenue_prior
        change = margin - margin_prior
        signals["margin_trend"] = {"value": change, "score": ramp(change, **THRESHOLDS["margin_trend"]), "margin": margin}

    if revenue is not None and revenue_prior and revenue_prior > 0:
        growth = revenue / revenue_prior - 1
        score = ramp(growth, **THRESHOLDS["revenue_growth"]) or 0.0
        note = None
        if revenue_prior2 and revenue_prior2 > 0:
            growth_prior = revenue_prior / revenue_prior2 - 1
            if growth_prior >= 0.20 and growth <= growth_prior - 0.15:
                score = max(score, 0.7 + min(0.3, (growth_prior - growth)))
                note = f"Growth fell from {growth_prior:.0%} to {growth:.0%}."
        signals["revenue_turn"] = {"value": growth, "score": score, **({"note": note} if note else {})}

    facts.update({
        "net_income_ttm": ni, "cfo_ttm": cfo, "revenue_ttm": revenue, "operating_income_ttm": oi,
        "cash": cash, "total_assets": assets, "stockholders_equity": equity, "long_term_debt": debt,
    })
    return signals, facts


def insider_signal(ticker: str, market_cap: float | None, as_of: date) -> dict | None:
    path = INSIDER_DIR / f"{ticker}_transactions.csv"
    if not path.exists():
        return None
    cutoff = as_of - timedelta(days=INSIDER_WINDOW_DAYS)
    sold = 0.0
    bought = 0.0
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            when = _parse_period(row.get("transaction_date"))
            if when is None or when < cutoff or when > as_of:
                continue
            code = str(row.get("transaction_code") or "").upper()
            try:
                value = float(row.get("value_usd") or 0)
            except ValueError:
                continue
            if code == "S":
                sold += value
            elif code == "P":
                bought += value
    net = sold - bought
    if market_cap and market_cap > 0:
        share = net / market_cap
        return {"value": share, "score": ramp(share, **THRESHOLDS["insider_share_of_cap"]) or 0.0, "net_usd": net, "basis": "market_cap"}
    return {"value": None, "score": ramp(net, 0.0, 20_000_000) or 0.0, "net_usd": net, "basis": "dollars"}


def tape_and_risk(tech: dict | None, flt: dict | None, finra: dict | None) -> tuple[dict, dict, dict]:
    measures = (tech or {}).get("measures") or {}
    context = (tech or {}).get("context") or {}
    tape: dict = {}
    risk: dict = {}
    facts: dict = {}

    dist200 = measures.get("distance_200d_pct")
    mom = measures.get("momentum_12_1_pct")
    if dist200 is not None and mom is not None:
        below = dist200 < 0
        negative = mom < 0
        tape["trend_broken"] = {"value": dist200, "score": 1.0 if (below and negative) else (0.5 if (below or negative) else 0.0), "momentum_12_1_pct": mom}
        risk["parabolic"] = {"value": dist200, "score": ramp(dist200, **THRESHOLDS["distance_200d_pct"]) or 0.0}

    vol = measures.get("realized_volatility_20d_pct")
    beta = context.get("beta_252d")
    if vol is not None:
        score = ramp(vol, **THRESHOLDS["realized_vol_pct"]) or 0.0
        if beta is not None and beta >= 2:
            score = min(1.0, score + 0.2)
        risk["volatility"] = {"value": vol, "score": score, "beta": beta}

    adv = (flt or {}).get("adv_dollar")
    if adv is None and context.get("dollar_volume_20d") is not None:
        adv = context.get("dollar_volume_20d")
    if adv is not None:
        risk["illiquidity"] = {"value": adv, "score": ramp(adv, THRESHOLDS["adv_dollar"]["zero"], THRESHOLDS["adv_dollar"]["full"]) or 0.0}

    spf = (flt or {}).get("short_percent_float")
    dtc = (flt or {}).get("days_to_cover")
    source = "float_file" if (spf is not None or dtc is not None) else None
    if dtc is None and finra:
        dtc = finra.get("days_to_cover")
        source = "finra"
    scores = [s for s in (ramp(spf, **THRESHOLDS["short_percent_float"]), ramp(dtc, **THRESHOLDS["days_to_cover"])) if s is not None]
    if scores:
        risk["crowding"] = {"value": spf, "days_to_cover": dtc, "score": max(scores), "source": source}
    facts.update({"price": measures.get("close") or ((tech or {}).get("latest") or {}).get("close"), "adv_dollar": adv})
    return tape, risk, facts


def composite(fund: dict, tape: dict, risk: dict) -> dict:
    def grouped(signals: dict, catalog: dict) -> float | None:
        total = 0.0
        weight = 0.0
        for key, row in signals.items():
            score = row.get("score")
            if score is None:
                continue
            w = catalog[key][1]
            total += score * w
            weight += w
        return total / weight if weight else None

    evidence = sum(1 for row in fund.values() if row.get("score") is not None)
    decay = grouped(fund, FUNDAMENTAL_SIGNALS) if evidence >= MIN_FUNDAMENTAL_SIGNALS else None
    tape_score = grouped(tape, TAPE_SIGNALS)
    risk_score = grouped(risk, RISK_SIGNALS)
    if decay is None:
        return {"score": None, "decay": None, "tape": tape_score, "risk": risk_score, "evidence_count": evidence}
    score = 100 * (0.65 * decay + 0.20 * (tape_score or 0.0)) * (1 - 0.5 * (risk_score or 0.0))
    return {"score": round(score, 1), "decay": round(decay, 3), "tape": None if tape_score is None else round(tape_score, 3), "risk": None if risk_score is None else round(risk_score, 3), "evidence_count": evidence}


def implied_frameworks(fund: dict, tape: dict, risk: dict) -> list[str]:
    out: list[str] = []
    for signals, catalog in ((fund, FUNDAMENTAL_SIGNALS), (tape, TAPE_SIGNALS), (risk, RISK_SIGNALS)):
        for key, row in signals.items():
            if (row.get("score") or 0) >= 0.5 and catalog[key][0] not in out:
                out.append(catalog[key][0])
    return out


def load_finra() -> dict[str, dict]:
    files = sorted(FINRA_DIR.glob("shrt*.csv")) if FINRA_DIR.is_dir() else []
    if not files:
        return {}
    out: dict[str, dict] = {}
    with files[-1].open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="|"):
            symbol = str(row.get("symbolCode") or "").strip().upper()
            if not symbol:
                continue
            try:
                dtc = float(row.get("daysToCoverQuantity") or "nan")
            except ValueError:
                dtc = math.nan
            out[symbol] = {
                "days_to_cover": dtc if math.isfinite(dtc) else None,
                "issue_name": row.get("issueName"),
                "settlement": row.get("settlementDate"),
            }
    return out


def load_names() -> dict[str, str]:
    core = _read_json(CORE, {}) or {}
    return {str(row.get("ticker")).upper(): str(row.get("company") or "") for row in core.get("tickers") or [] if row.get("ticker")}


def load_sec_titles() -> tuple[dict[str, str], dict[int, str]]:
    """(ticker -> title, cik -> title) from the committed SEC company_tickers cache."""
    doc = _read_json(SEC_TITLES, {}) or {}
    rows = doc.values() if isinstance(doc, dict) else doc if isinstance(doc, list) else []
    by_ticker: dict[str, str] = {}
    by_cik: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("title"):
            continue
        if row.get("ticker"):
            by_ticker.setdefault(str(row["ticker"]).upper(), str(row["title"]))
        try:
            by_cik.setdefault(int(row.get("cik_str")), str(row["title"]))
        except (TypeError, ValueError):
            pass
    return by_ticker, by_cik


def company_name(ticker: str, *, core_name: str | None, doc: dict | None, sec_titles: tuple[dict, dict] | None, finra: dict | None) -> str:
    """First real name: core.json, the fundamentals entity name, SEC by CIK then ticker, FINRA.

    core.json often stores the ticker itself as the company (WULF, IREN, AI),
    so a name equal to the ticker counts as missing, not as a name.
    """
    by_ticker, by_cik = sec_titles or ({}, {})
    doc = doc or {}
    cik_text = str(doc.get("cik") or "").strip()
    sec_by_cik = by_cik.get(int(cik_text)) if cik_text.isdigit() else None
    for name in (
        core_name,
        doc.get("entity_name") or doc.get("entityName") or doc.get("company"),
        sec_by_cik,
        by_ticker.get(ticker.upper()),
        (finra or {}).get("issue_name"),
    ):
        text = str(name or "").strip()
        if text and text.upper() != ticker.upper():
            return text
    return ""


def round_signals(signals: dict) -> dict:
    out = {}
    for key, row in signals.items():
        clean = {}
        for k, v in row.items():
            clean[k] = round(v, 4) if isinstance(v, float) else v
        out[key] = clean
    return out


def score_ticker(ticker: str, *, fundamentals: dict | None, tech: dict | None, flt: dict | None, finra: dict | None, as_of: date, sic: dict | None = None) -> dict:
    profile = profile_for((sic or {}).get("sic"), ticker)
    rule = PROFILE_RULES[profile]
    override = PROFILE_OVERRIDES.get(ticker.upper())
    reason = f"{override[1]} {rule.get('reason') or ''}".strip() if override else rule.get("reason")
    fund, facts = fundamental_signals(fundamentals, as_of) if fundamentals else ({}, {"latest_period": None, "stale": None})
    for key in rule.get("disable", set()):
        fund.pop(key, None)
    tape, risk, tape_facts = tape_and_risk(tech, flt, finra)
    price = (flt or {}).get("price") or tape_facts.get("price")
    shares = (flt or {}).get("shares_outstanding")
    market_cap = price * shares if price and shares else None
    insider = insider_signal(ticker, market_cap, as_of)
    if insider is not None:
        fund["insider_selling"] = insider
    # The lenses assume a business: a name with neither revenue nor an
    # operating burn is a trust, a shell, or a filer we cannot read.
    operating = bool(facts.get("revenue_ttm")) or (fund.get("cash_burn") or {}).get("value") is not None
    summary = composite(fund, tape, risk)
    if rule.get("skip") or not operating:
        summary = {**summary, "score": None, "decay": None}
    return {
        "ticker": ticker,
        **summary,
        "profile": profile,
        "sic": (sic or {}).get("sic"),
        "sic_description": (sic or {}).get("description"),
        "profile_note": reason if (rule.get("skip") or rule.get("disable")) else (None if operating else "No revenue and no operating burn on file, so the lenses have nothing to read."),
        "implied_frameworks": implied_frameworks(fund, tape, risk),
        "signals": {"fundamental": round_signals(fund), "tape": round_signals(tape), "risk": round_signals(risk)},
        "facts": {**{k: (round(v, 4) if isinstance(v, float) else v) for k, v in facts.items()}, "price": price, "market_cap": market_cap, "adv_dollar": tape_facts.get("adv_dollar")},
    }


def build(as_of: date | None = None, *, limit: int = TOP_ROWS, fetch_sic: bool = True) -> dict:
    as_of = as_of or date.today()
    technical = (_read_json(TECHNICAL, {}) or {}).get("by_ticker") or {}
    float_rows = (_read_json(FLOAT_ADV, {}) or {}).get("by_ticker") or {}
    finra = load_finra()
    names = load_names()
    sec_titles = load_sec_titles()
    tracked = {str(row.get("ticker")).upper() for row in (_read_json(CANDIDATES, {}) or {}).get("candidates") or []}
    fundamentals_files = {p.stem.upper(): p for p in FUNDAMENTALS.glob("*.json") if not p.name.startswith("_") and p.name != FLOAT_ADV.name} if FUNDAMENTALS.is_dir() else {}

    universe = sorted(set(fundamentals_files) | tracked)
    docs = {ticker: _read_json(fundamentals_files[ticker], None) for ticker in universe if ticker in fundamentals_files}
    sic_map = load_sic_map({ticker: str((doc or {}).get("cik") or "") for ticker, doc in docs.items()}, fetch=fetch_sic)
    rows = []
    for ticker in universe:
        row = score_ticker(
            ticker,
            fundamentals=docs.get(ticker),
            tech=technical.get(ticker),
            flt=float_rows.get(ticker),
            finra=finra.get(ticker),
            as_of=as_of,
            sic=sic_map.get(ticker),
        )
        row["company"] = company_name(ticker, core_name=names.get(ticker), doc=docs.get(ticker), sec_titles=sec_titles, finra=finra.get(ticker))
        row["tracked"] = ticker in tracked
        rows.append(row)

    scored = [row for row in rows if row["score"] is not None]
    scored.sort(key=lambda row: (-row["score"], row["ticker"]))
    for rank, row in enumerate(scored, start=1):
        row["rank"] = rank
    keep = {row["ticker"] for row in scored[:limit]} | tracked
    kept = [row for row in rows if row["ticker"] in keep]
    kept.sort(key=lambda row: (row["score"] is None, -(row["score"] or 0), row["ticker"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": as_of.isoformat(),
        "universe_count": len(universe),
        "scored_count": len(scored),
        "unscored_count": len(rows) - len(scored),
        "inputs": {
            "fundamentals": str(FUNDAMENTALS.relative_to(ROOT)),
            "technical": str(TECHNICAL.relative_to(ROOT)),
            "float_short_interest": str(FLOAT_ADV.relative_to(ROOT)),
            "finra_file": str(sorted(FINRA_DIR.glob("shrt*.csv"))[-1].relative_to(ROOT)) if FINRA_DIR.is_dir() and list(FINRA_DIR.glob("shrt*.csv")) else None,
            "insider": str(INSIDER_DIR.relative_to(ROOT)),
        },
        "methodology": {
            "composite": "100 x (0.65 x decay + 0.20 x tape) x (1 - 0.5 x risk). Decay is the weighted mean of the fundamental signals present; tape is whether the trend has broken; risk is the mean of crowding, illiquidity, volatility and a parabolic tape.",
            "minimum_evidence": f"A name needs at least {MIN_FUNDAMENTAL_SIGNALS} fundamental signals to score. Missing is not clean.",
            "profiles": "By SIC code: banks, thrifts (6020-6099), insurers (6311-6411) and lenders (6111-6163) lose the cash-burn, accrual and leverage lenses; REITs lose leverage; trusts, funds and blank checks are not scored. Other finance codes (finance services 6199, where bitcoin miners and crypto treasuries file, brokers, asset managers) keep every lens, except named bank holding companies and lenders filed under 6199. A name with no revenue and no operating burn is not scored.",
            "reading": "A score is a reason to open a file. The hypothesis, catalyst and falsifier still have to be written before a name is more than a lead.",
            "thresholds": THRESHOLDS,
            "signals": {
                key: {"framework": value[0], "weight": value[1], "reading": value[2]}
                for catalog in (FUNDAMENTAL_SIGNALS, TAPE_SIGNALS, RISK_SIGNALS)
                for key, value in catalog.items()
            },
        },
        "rows": kept,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--as-of", help="YYYY-MM-DD; default today")
    parser.add_argument("--limit", type=int, default=TOP_ROWS, help="top rows to keep beside every tracked candidate")
    parser.add_argument("--out", default=str(OUTPUT))
    parser.add_argument("--no-fetch", action="store_true", help="Use the cached SIC map only; never call SEC")
    args = parser.parse_args()
    as_of = _parse_period(args.as_of) if args.as_of else None
    doc = build(as_of, limit=args.limit, fetch_sic=not args.no_fetch)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    top = [row for row in doc["rows"] if row["score"] is not None][:10]
    print(f"short quant screen: {doc['scored_count']} scored of {doc['universe_count']}; wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    for row in top:
        print(f"  {row['rank']:>3} {row['ticker']:<8} {row['score']:>5.1f} decay={row['decay']} tape={row['tape']} risk={row['risk']} {row['company'][:40]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
