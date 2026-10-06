#!/usr/bin/env python3
"""Build the FICO fundamentals watch for the dashboard.

Automatic rows come from the SEC companyfacts feed. Segment splits, the
mortgage-price sentence, lender comments, and the policy grid stay pinned to
the last filing a person read. A newer 10-Q or 10-K turns the panel red
instead of leaving those pinned numbers looking current.

  python _system/scripts/build_fico_watch.py

Writes dashboard/data/fico_watch.json and FICO/research/kpi_ledger.json.
None of the gates are base-return inputs.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import world_model_common as wm  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FACTS_PATH = ROOT / "FICO" / "research" / "evidence" / "fico_watch_facts.json"
DASHBOARD_PATH = ROOT / "dashboard" / "data" / "fico_watch.json"
LEDGER_PATH = ROOT / "FICO" / "research" / "kpi_ledger.json"
CIK = "0000814547"
UA = "MarvinResearch single-stock-investments (research)"
PERIODIC = {"10-Q", "10-K"}

PILL = {
    "fail": "Broken",
    "pass": "Holding",
    "unchecked": "Not disclosed",
    "stale": "Recheck",
    "missing": "Not collected",
    "context": "Context",
}


def parse_day(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def span_days(row: dict) -> int | None:
    start = parse_day(row.get("start"))
    end = parse_day(row.get("end"))
    if not start or not end:
        return None
    return (end - start).days


def is_periodic(row: dict) -> bool:
    return str(row.get("form") or "") in PERIODIC


def usd_rows(gaap: dict | None, tag: str) -> list[dict]:
    node = (gaap or {}).get(tag) or {}
    units = node.get("units") or {}
    rows = units.get("USD") or []
    return list(rows)


def latest_duration(rows: list[dict], *, min_days: int, max_days: int) -> dict | None:
    best = None
    best_key = None
    for row in rows:
        if not is_periodic(row):
            continue
        days = span_days(row)
        if days is None or days < min_days or days > max_days:
            continue
        key = (str(row.get("end") or ""), days, str(row.get("filed") or ""))
        if best_key is None or key > best_key:
            best = row
            best_key = key
    return best


def latest_instant(rows: list[dict]) -> dict | None:
    best = None
    best_key = None
    for row in rows:
        if not is_periodic(row):
            continue
        if row.get("start"):
            continue
        end = row.get("end")
        if not end:
            continue
        key = (str(end), str(row.get("filed") or ""))
        if best_key is None or key > best_key:
            best = row
            best_key = key
    return best


def latest_periodic(submissions: dict | None) -> dict | None:
    recent = ((submissions or {}).get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    filed = recent.get("filingDate") or []
    periods = recent.get("reportDate") or []
    best = None
    for index, form in enumerate(forms):
        if form not in PERIODIC:
            continue
        row = {
            "form": form,
            "accession": accessions[index] if index < len(accessions) else "",
            "filed": filed[index] if index < len(filed) else "",
            "period_end": periods[index] if index < len(periods) else "",
        }
        if best is None or (row["filed"], row["accession"]) > (best["filed"], best["accession"]):
            best = row
    return best


def accession_key(value: str | None) -> str:
    return str(value or "").replace("-", "").strip()


def money_millions(value: float | None) -> str | None:
    if value is None:
        return None
    return f"${value / 1_000_000:,.1f} million"


def load_previous() -> dict | None:
    if not DASHBOARD_PATH.exists():
        return None
    try:
        return json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _by_id(rows: list[dict], row_id: str) -> dict | None:
    for row in rows:
        if row.get("id") == row_id:
            return row
    return None


def resolve_actual(facts: dict, gate: dict, computed: dict):
    pointer = gate.get("actual_from")
    if pointer == "computed.leverage":
        return computed.get("leverage"), computed.get("leverage_as_of"), "sec:companyfacts"
    if pointer and pointer.startswith("policy."):
        row = _by_id(facts.get("policy") or [], pointer.split(".", 1)[1])
        if not row:
            return None, None, ""
        return row.get("actual"), row.get("as_of"), row.get("source") or ""
    return gate.get("actual"), gate.get("as_of"), gate.get("source") or ""


def policy_needs_recheck(facts: dict, today: date) -> bool:
    window = int(facts.get("policy_recheck_days") or 21)
    dated = []
    for row in list(facts.get("policy") or []) + list(facts.get("lenders") or []):
        day = parse_day(row.get("as_of"))
        if day:
            dated.append(day)
    if not dated:
        return True
    newest = max(dated)
    return (today - newest).days > window


def leverage_from_gaap(gaap: dict | None) -> dict:
    """Net debt over operating income stretched to a year.

    Net debt is long-term debt including the portion due within a year, minus
    cash. The income base is the longest recent year-to-date span (six months,
    nine months, or a full year), scaled by 365 / span days. A single quarter
    is used only when no longer span exists.
    """
    empty = {"leverage": None, "leverage_as_of": None, "lines": []}
    if not gaap:
        return empty
    debt = latest_instant(usd_rows(gaap, "LongTermDebtNoncurrent"))
    current = latest_instant(usd_rows(gaap, "LongTermDebtCurrent"))
    cash = latest_instant(usd_rows(gaap, "CashAndCashEquivalentsAtCarryingValue"))
    income_rows = usd_rows(gaap, "OperatingIncomeLoss")
    income = latest_duration(income_rows, min_days=170, max_days=380)
    income_basis = "year-to-date"
    if income is None:
        income = latest_duration(income_rows, min_days=80, max_days=100)
        income_basis = "latest quarter times four, because a longer span was not in the feed"
    if not debt or not cash or not income:
        return empty
    debt_value = float(debt["val"])
    current_value = float(current["val"]) if current else 0.0
    cash_value = float(cash["val"])
    income_value = float(income["val"])
    days = span_days(income) or 0
    if days <= 0 or income_value <= 0:
        return empty
    if income_basis.startswith("latest quarter"):
        annualized = income_value * 4
    else:
        annualized = income_value * (365 / days)
    net = debt_value + current_value - cash_value
    ratio = net / annualized
    as_of = str(income.get("end") or debt.get("end") or "")
    lines = [
        {
            "id": "debt_noncurrent",
            "label": "Long-term debt, excluding the portion due within a year",
            "display": money_millions(debt_value),
            "as_of": debt.get("end"),
            "note": "SEC companyfacts, LongTermDebtNoncurrent.",
        },
        {
            "id": "debt_current",
            "label": "Long-term debt due within a year",
            "display": money_millions(current_value) if current else "Not in the feed",
            "as_of": (current or {}).get("end"),
            "note": "SEC companyfacts, LongTermDebtCurrent. Included in the net-debt figure.",
        },
        {
            "id": "cash",
            "label": "Cash",
            "display": money_millions(cash_value),
            "as_of": cash.get("end"),
            "note": "SEC companyfacts, cash and cash equivalents.",
        },
        {
            "id": "operating_income",
            "label": "Operating income used for the multiple",
            "display": money_millions(income_value),
            "as_of": income.get("end"),
            "note": (
                f"{days} days in the span. Stretched to a year this is "
                f"{money_millions(annualized)}. Basis: {income_basis}."
            ),
        },
    ]
    quarter = latest_duration(usd_rows(gaap, "RevenueFromContractWithCustomerExcludingAssessedTax"), min_days=80, max_days=100)
    ytd = latest_duration(usd_rows(gaap, "RevenueFromContractWithCustomerExcludingAssessedTax"), min_days=170, max_days=380)
    oi_quarter = latest_duration(income_rows, min_days=80, max_days=100)
    if quarter:
        lines.append({
            "id": "revenue_quarter",
            "label": "Revenue, latest quarter",
            "display": money_millions(float(quarter["val"])),
            "as_of": quarter.get("end"),
            "note": "SEC companyfacts. Company total, not the Scores segment.",
        })
    if ytd:
        lines.append({
            "id": "revenue_ytd",
            "label": "Revenue, year to date",
            "display": money_millions(float(ytd["val"])),
            "as_of": ytd.get("end"),
            "note": f"SEC companyfacts. Span {span_days(ytd)} days.",
        })
    if oi_quarter:
        lines.append({
            "id": "operating_income_quarter",
            "label": "Operating income, latest quarter",
            "display": money_millions(float(oi_quarter["val"])),
            "as_of": oi_quarter.get("end"),
            "note": "SEC companyfacts. Company total, not the Scores segment.",
        })
    buyback = latest_duration(usd_rows(gaap, "PaymentsForRepurchaseOfCommonStock"), min_days=170, max_days=380)
    if buyback:
        lines.append({
            "id": "buybacks_ytd",
            "label": "Stock repurchase payments, year to date",
            "display": money_millions(float(buyback["val"])),
            "as_of": buyback.get("end"),
            "note": f"SEC companyfacts. Span {span_days(buyback)} days. This is cash spent, not a statement that the price was wise.",
        })
    interest = _interest_ytd(gaap)
    return {
        "leverage": round(ratio, 2),
        "leverage_as_of": as_of,
        "leverage_note": (
            f"Net debt {money_millions(net)} "
            f"({money_millions(debt_value)} plus {money_millions(current_value)} minus {money_millions(cash_value)}) "
            f"divided by {money_millions(annualized)} of operating income stretched to a year. "
            "Not a company-reported EBITDA multiple."
        ),
        "interest_ytd_millions": None if interest is None else round(interest / 1_000_000, 1),
        "lines": lines,
    }


def _interest_ytd(gaap: dict) -> float | None:
    best = None
    best_key = None
    for tag in ("InterestExpense", "InterestExpenseNonoperating"):
        row = latest_duration(usd_rows(gaap, tag), min_days=170, max_days=380)
        if not row:
            continue
        key = (str(row.get("end") or ""), span_days(row) or 0)
        if best_key is None or key > best_key:
            best = row
            best_key = key
    if not best:
        return None
    return float(best["val"])


def build_gates(facts: dict, computed: dict, *, today: date, narrative_unread: bool) -> list[dict]:
    recheck = policy_needs_recheck(facts, today)
    built = []
    for gate in facts.get("gates") or []:
        actual, as_of, source = resolve_actual(facts, gate, computed)
        status = wm.eval_expected(gate.get("expected"), actual)
        if gate.get("recheck_with_policy") and recheck:
            status = "stale"
        if narrative_unread and gate.get("unread_if_newer_filing") and status != "unchecked":
            status = "stale"
        display = gate.get("display")
        note = gate.get("note") or gate.get("statement") or ""
        if gate.get("kpi_id") == "net_debt_to_annualized_operating_income":
            if computed.get("leverage") is None:
                display = "Not in the feed"
                note = "Debt, cash, or operating income was missing from the SEC feed on this run."
            else:
                display = f"{computed['leverage']:.2f}×"
                note = computed.get("leverage_note") or note
                source = "sec:companyfacts"
                as_of = computed.get("leverage_as_of")
        if narrative_unread and gate.get("unread_if_newer_filing"):
            note = "A newer SEC filing is unread. " + note
        built.append({
            "kpi_id": gate["kpi_id"],
            "label": gate.get("label") or gate["kpi_id"],
            "statement": gate.get("statement") or "",
            "fail_line": gate.get("fail_line") or gate.get("label"),
            "unit": gate.get("unit") or "",
            "expected": gate.get("expected") or {},
            "actual": actual,
            "as_of": as_of,
            "source": source,
            "status": status,
            "display": display if display else ("Not disclosed" if actual is None else str(actual)),
            "note": note,
            "pill": PILL.get(status, status),
        })
    return built


def build_payload(
    facts: dict,
    submissions: dict | None,
    gaap: dict | None,
    *,
    today: date | None = None,
    sec_error: str | None = None,
    previous: dict | None = None,
    generated_at: str | None = None,
) -> dict:
    today = today or date.today()
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    pinned = facts.get("pinned_filing") or {}
    latest = latest_periodic(submissions) if submissions else None
    if sec_error and previous and previous.get("freshness", {}).get("latest"):
        latest = previous["freshness"]["latest"]
    unread = bool(
        latest
        and pinned.get("accession")
        and accession_key(latest.get("accession")) != accession_key(pinned.get("accession"))
        and not sec_error
    )
    computed = leverage_from_gaap(gaap)
    reused_auto = False
    if computed.get("leverage") is None and sec_error and previous:
        prior_auto = previous.get("auto") or {}
        if prior_auto.get("leverage") is not None:
            computed = {
                "leverage": prior_auto.get("leverage"),
                "leverage_as_of": prior_auto.get("leverage_as_of"),
                "leverage_note": prior_auto.get("leverage_note"),
                "interest_ytd_millions": prior_auto.get("interest_ytd_millions"),
                "lines": prior_auto.get("lines") or [],
            }
            reused_auto = True
    gates = build_gates(facts, computed, today=today, narrative_unread=unread)
    if sec_error:
        freshness_state = "sec_unchecked"
        freshness_detail = (
            "The SEC check did not finish. Automatic totals are the last successful check, "
            "not a confirmation from today. " + sec_error
        )
    elif unread:
        freshness_state = "unread_filing"
        freshness_detail = (
            f"Latest {latest.get('form')} filed {latest.get('filed')} "
            f"(period {latest.get('period_end')}, accession {latest.get('accession')}) "
            f"is newer than the filing these segment rows were read from "
            f"({pinned.get('form')} filed {pinned.get('filed')}). "
            "Do not treat the Scores split, bureau share, or margin as current."
        )
    else:
        freshness_state = "current"
        freshness_detail = (
            f"Segment rows match {pinned.get('form')} filed {pinned.get('filed')} "
            f"(period {pinned.get('period_end')}). Automatic debt, cash, and revenue "
            "rows were read from the SEC companyfacts feed on this run."
        )
    fails = [gate["fail_line"] for gate in gates if gate["status"] == "fail"]
    if freshness_state == "unread_filing":
        tone = "fail"
        title = "A newer SEC filing is unread"
        detail = freshness_detail
    elif freshness_state == "sec_unchecked":
        tone = "watch"
        title = "The SEC check did not run"
        detail = freshness_detail
    elif fails:
        tone = "fail"
        title = ". ".join(fails)
        detail = (
            "These lines are the watch. A holding pill means that particular gate "
            "has not broken. It does not mean the mortgage toll is safe."
        )
    else:
        tone = "pass"
        title = "The watched lines are holding"
        detail = "No gate is broken on the numbers currently loaded."
    banner_bits = []
    if freshness_state == "unread_filing":
        banner_bits.append("Newer filing unread")
    if freshness_state == "sec_unchecked":
        banner_bits.append("SEC check did not run")
    banner_bits.extend(fails)
    if not banner_bits:
        banner_bits.append("Watched lines are holding")
    narrative_rows = []
    for row in facts.get("narrative") or []:
        display = row.get("display")
        note = row.get("note") or ""
        badge = "Last read"
        source = row.get("source") or ""
        if row.get("xbrl_check") == "interest_ytd_millions" and computed.get("interest_ytd_millions") is not None:
            fed = computed["interest_ytd_millions"]
            expect = row.get("xbrl_expect_millions")
            display = f"${fed:,.1f} million"
            badge = "SEC feed"
            source = "sec:companyfacts"
            if expect is not None and abs(fed - float(expect)) > 10:
                note = f"The last human read recorded ${expect:.0f} million. The SEC feed says ${fed:,.1f} million. This row follows the feed. " + note
            else:
                note = "SEC companyfacts year-to-date interest, same order of magnitude as the last human read. " + note
        status = "context"
        pill = badge
        if unread and badge != "SEC feed":
            status = "stale"
            pill = "Unread"
            note = "A newer SEC filing is unread. " + note
        shown = dict(row)
        shown["source"] = source
        narrative_rows.append(_row(shown, display, note, status, pill))
    sec_rows = []
    for line in computed.get("lines") or []:
        sec_rows.append({
            "id": line["id"],
            "label": line["label"],
            "display": line.get("display") or "Not in the feed",
            "note": line.get("note") or "",
            "as_of": line.get("as_of"),
            "source": "sec:companyfacts",
            "status": "context",
            "pill": "SEC feed" if not reused_auto else "Last check",
        })
    policy_rows = [_context_row(row, unread=False, recheck=policy_needs_recheck(facts, today)) for row in facts.get("policy") or []]
    lender_rows = [_context_row(row, unread=False, recheck=policy_needs_recheck(facts, today)) for row in facts.get("lenders") or []]
    missing_rows = []
    for row in facts.get("missing") or []:
        missing_rows.append({
            "id": row["id"],
            "label": row["label"],
            "display": row.get("display") or "Not collected",
            "note": row.get("note") or "",
            "as_of": None,
            "source": "",
            "status": "missing",
            "pill": "Not collected",
        })
    return {
        "schema": "fico_watch.v1",
        "generated_at": generated_at,
        "ticker": "FICO",
        "banner": {"tone": tone, "text": "FICO · " + " · ".join(banner_bits), "action": "Open FICO"},
        "verdict": {"tone": tone, "title": title, "detail": detail},
        "freshness": {
            "state": freshness_state,
            "detail": freshness_detail,
            "pinned": pinned,
            "latest": latest,
            "sec_error": sec_error,
            "reused_auto": reused_auto,
        },
        "trust": (
            "Debt, cash, revenue, operating income, buybacks, and interest refresh from the SEC "
            "companyfacts feed on the nightly dashboard build and again on Sunday. "
            "The Scores split, bureau share, margin, unit-price sentence, lenders, and the policy "
            "grid stay at the last filing a person read. None of these gates are in the base return."
        ),
        "groups": [
            {"id": "gates", "label": "Lines that change the watch", "rows": [_gate_row(g) for g in gates]},
            {"id": "sec", "label": "Automatic, from the SEC feed", "rows": sec_rows},
            {"id": "narrative", "label": "Last filing a person read", "rows": narrative_rows},
            {"id": "lenders", "label": "Lenders", "rows": lender_rows},
            {"id": "policy", "label": "Policy", "rows": policy_rows},
            {"id": "missing", "label": "Not on the feed yet", "rows": missing_rows},
        ],
        "auto": {
            "leverage": computed.get("leverage"),
            "leverage_as_of": computed.get("leverage_as_of"),
            "leverage_note": computed.get("leverage_note"),
            "interest_ytd_millions": computed.get("interest_ytd_millions"),
            "lines": computed.get("lines") or [],
            "checked_at": ((previous or {}).get("auto") or {}).get("checked_at") if reused_auto else generated_at,
        },
        "gates": gates,
    }


def _row(row: dict, display: str, note: str, status: str, pill: str) -> dict:
    return {
        "id": row.get("id"),
        "label": row.get("label"),
        "display": display,
        "note": note,
        "as_of": row.get("as_of"),
        "source": row.get("source") or "",
        "status": status,
        "pill": pill,
    }


def _context_row(row: dict, *, unread: bool, recheck: bool) -> dict:
    status = "stale" if recheck else "context"
    pill = "Recheck" if recheck else "Context"
    note = row.get("note") or ""
    if recheck:
        note = "Past the recheck window. Confirm this before trusting it. " + note
    return _row(row, row.get("display") or "", note, status, pill)


def _gate_row(gate: dict) -> dict:
    return {
        "id": gate["kpi_id"],
        "label": gate["label"],
        "display": gate["display"],
        "note": gate["note"],
        "as_of": gate.get("as_of"),
        "source": gate.get("source") or "",
        "status": gate["status"],
        "pill": gate["pill"],
    }


def ledger_from_payload(payload: dict, today: date) -> dict:
    kpis = []
    for gate in payload.get("gates") or []:
        actual = gate.get("actual")
        kpis.append({
            "kpi_id": gate["kpi_id"],
            "label": gate["label"],
            "unit": gate.get("unit") or "",
            "statement": gate.get("statement") or "",
            "expected": gate.get("expected") or {},
            "actual": {"value": actual, "as_of": gate.get("as_of")},
            "status": gate["status"],
            "source": gate.get("source") or "FICO/research/evidence/fico_watch_facts.json",
            "evidence_tier": "filing",
            "last_checked": today.isoformat(),
            "binds_to": {
                "on_fail": "open_diligence",
                "note": gate.get("statement") or gate["label"],
            },
            "in_base_irr": False,
        })
    summary = wm.summarize_statuses(kpis)
    return {
        "ticker": "FICO",
        "as_of": today.isoformat(),
        "schema_version": "1.0",
        "scaffold_meta": {
            "generated_by": "build_fico_watch.py",
            "generated_at": today.isoformat(),
            "note": "FICO mortgage-toll watch. Context only. Not a base return input.",
        },
        "kpis": kpis,
        "summary": summary,
    }


def write_outputs(payload: dict, today: date) -> None:
    public = {key: value for key, value in payload.items() if key != "gates"}
    public["gate_status"] = [
        {"kpi_id": gate["kpi_id"], "status": gate["status"], "display": gate["display"]}
        for gate in payload.get("gates") or []
    ]
    wm.write_json(DASHBOARD_PATH, public)
    wm.write_json(LEDGER_PATH, ledger_from_payload(payload, today))


def main() -> int:
    facts = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
    today = date.today()
    submissions = None
    gaap = None
    sec_error = None
    try:
        submissions = fetch_json(f"https://data.sec.gov/submissions/CIK{CIK}.json")
        company = fetch_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json")
        gaap = (company.get("facts") or {}).get("us-gaap") or {}
    except Exception as exc:  # network, SEC, or JSON — keep the last good automatic rows
        sec_error = f"{type(exc).__name__}: {exc}"
    payload = build_payload(
        facts,
        submissions,
        gaap,
        today=today,
        sec_error=sec_error,
        previous=load_previous(),
    )
    write_outputs(payload, today)
    print(
        f"fico watch {payload['freshness']['state']} "
        f"banner={payload['banner']['text']} "
        f"leverage={payload['auto'].get('leverage')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
