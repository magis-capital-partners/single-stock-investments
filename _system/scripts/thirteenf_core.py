#!/usr/bin/env python3
"""Pure 13F parsing, amendment merge, and change classification.

No network. Callers pass XML bytes and filing metadata.
"""
from __future__ import annotations

import re
from datetime import datetime
from xml.etree import ElementTree as ET

# Value is reported in whole dollars for filings on or after this date.
# Earlier filings report thousands of dollars.
DOLLAR_VALUE_CUTOFF = "2023-01-03"
STRUCTURAL_SUFFIXES = (".ESC", ".CVR", ".WTS", ".DB", ".CNT", ".MRG")
HOLDINGS_FORMS = {"13F-HR", "13F-HR/A"}
NOTICE_FORMS = {"13F-NT", "13F-NT/A"}
# A reviewed correction. Name-match once wrote Johnson & Johnson's CUSIP to a CVR ticker.
KNOWN_CUSIPS = {
    "478160104": {
        "ticker": "JNJ",
        "source": "reviewed",
        "confidence": "high",
        "issuer": "Johnson & Johnson",
    }
}
FORBIDDEN_MANAGER_KEYS = {
    "letter",
    "letters",
    "letter_source",
    "provenance",
    "email",
    "emails",
    "meeting",
    "meetings",
    "gated",
    "lp",
    "lp_letter",
    "how_found",
    "origin",
    "source_note",
}
FORBIDDEN_MANAGER_ROLES = {"letters", "letter", "email", "meeting", "gated"}
LICENSED_NAME_RE = re.compile(r"(tikr|factset|refinitiv|capital[\s_-]?iq|bloomberg)", re.I)


def local_tag(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def parse_amount(value) -> int | None:
    """Parse a share or value figure. Commas and one decimal point are allowed."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def normalize_date(value: str | None) -> str | None:
    """Return YYYY-MM-DD from an SEC date (YYYY-MM-DD or MM-DD-YYYY)."""
    if not value:
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    match = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", text)
    if match:
        month, day, year = match.groups()
        return f"{year}-{month}-{day}"
    return None


def pad_cik(value: str | None) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    return digits.zfill(10)


def other_managers_from_primary(xml_bytes: bytes) -> list[dict]:
    """Managers named on a 13F cover who file their own information table.

    The filing manager in the header is not included. A 13F-NT has no holdings
    of its own; these are the books that replace it for that period.
    """
    root = ET.fromstring(xml_bytes)
    found: list[dict] = []
    seen: set[str] = set()
    for node in root.iter():
        if local_tag(node.tag) != "otherManager":
            continue
        entry: dict[str, str] = {}
        for child in node.iter():
            key = local_tag(child.tag)
            text = (child.text or "").strip()
            if text and key in {"cik", "name", "form13FFileNumber"} and key not in entry:
                entry[key] = text
        cik = pad_cik(entry.get("cik"))
        if not cik or cik in seen:
            continue
        seen.add(cik)
        found.append(
            {
                "cik": cik,
                "name": entry.get("name") or "",
                "file_number": entry.get("form13FFileNumber") or "",
            }
        )
    return found


def book_source_for_latest_period(filings: list[dict]) -> dict:
    """Pick the book for the newest period of report.

    A 13F-HR for that period is the book. A notice alone is not. An older
    holdings filing must not stand in for a later notice.
    """
    dated = [row for row in filings if normalize_date(row.get("report_date"))]
    if not dated:
        return {"mode": "none", "period": None, "filings": [], "notice": None}
    period = max(normalize_date(row.get("report_date")) or "" for row in dated)
    period_rows = [row for row in dated if normalize_date(row.get("report_date")) == period]
    holdings = [row for row in period_rows if row.get("form") in HOLDINGS_FORMS]
    holdings.sort(key=lambda row: (row.get("filing_date") or "", row.get("accession") or ""))
    if holdings:
        return {"mode": "direct", "period": period, "filings": holdings, "notice": None}
    notices = [row for row in period_rows if row.get("form") in NOTICE_FORMS]
    notices.sort(key=lambda row: (row.get("filing_date") or "", row.get("accession") or ""))
    if notices:
        return {"mode": "notice", "period": period, "filings": [], "notice": notices[-1]}
    return {"mode": "none", "period": period, "filings": [], "notice": None}


def quarter_from_period(value: str | None) -> str | None:
    """Label a quarter from the period-of-report date, never the filing date."""
    iso = normalize_date(value)
    if not iso:
        return None
    try:
        year = int(iso[:4])
        month = int(iso[5:7])
    except ValueError:
        return None
    if month < 1 or month > 12:
        return None
    return f"{year}Q{(month - 1) // 3 + 1}"


def period_end_for_quarter(quarter: str) -> str | None:
    match = re.fullmatch(r"(\d{4})Q([1-4])", quarter or "")
    if not match:
        return None
    year, q = int(match.group(1)), int(match.group(2))
    month_day = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[q]
    return f"{year}-{month_day}"


def structural_ticker(ticker: str | None) -> bool:
    upper = (ticker or "").upper().strip()
    if not upper:
        return False
    if any(upper.endswith(suffix) for suffix in STRUCTURAL_SUFFIXES):
        return True
    return re.search(r"\.PS\d", upper) is not None


def value_to_usd(raw, filing_date: str | None) -> int | None:
    amount = parse_amount(raw)
    if amount is None:
        return None
    filed = normalize_date(filing_date) or ""
    if filed and filed < DOLLAR_VALUE_CUTOFF:
        return amount * 1000
    return amount


def parse_info_table_xml(xml_bytes: bytes) -> list[dict]:
    """Flatten one information table. Shares live under shrsOrPrnAmt/sshPrnamt."""
    root = ET.fromstring(xml_bytes)
    rows: list[dict] = []
    for node in root.iter():
        if local_tag(node.tag) != "infoTable":
            continue
        row: dict = {}
        for child in list(node):
            key = local_tag(child.tag)
            if key == "shrsOrPrnAmt":
                for sub in list(child):
                    row[local_tag(sub.tag)] = (sub.text or "").strip()
                if "sshPrnamt" not in row:
                    for sub in child.iter():
                        if local_tag(sub.tag) == "sshPrnamt" and sub.text:
                            row["sshPrnamt"] = sub.text.strip()
            elif key == "votingAuthority":
                for sub in list(child):
                    row[f"voting_{local_tag(sub.tag)}"] = (sub.text or "").strip()
            else:
                row[key] = (child.text or "").strip()
        if row.get("cusip") or row.get("nameOfIssuer"):
            rows.append(row)
    return rows


def _flag(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"true", "y", "yes", "1"}


def parse_primary_doc_xml(xml_bytes: bytes) -> dict:
    """Cover page and summary. Missing tags stay None rather than guessing."""
    root = ET.fromstring(xml_bytes)
    found: dict[str, str] = {}
    for node in root.iter():
        key = local_tag(node.tag)
        text = (node.text or "").strip()
        if text and key not in found:
            found[key] = text
    period = normalize_date(found.get("periodOfReport") or found.get("reportCalendarOrQuarter"))
    amendment_raw = found.get("amendmentType") or ""
    amendment_type = amendment_raw.strip().upper() or None
    if amendment_type and "RESTATEMENT" in amendment_type:
        amendment_type = "RESTATEMENT"
    elif amendment_type and "NEW HOLDINGS" in amendment_type:
        amendment_type = "NEW HOLDINGS"
    return {
        "submission_type": found.get("submissionType"),
        "report_type": found.get("reportType"),
        "period_end": period,
        "quarter": quarter_from_period(period),
        "is_amendment": _flag(found.get("isAmendment")) or bool(amendment_type),
        "amendment_type": amendment_type,
        "filing_manager": found.get("name"),
        "table_entry_total": parse_amount(found.get("tableEntryTotal")),
        "table_value_total_usd": parse_amount(found.get("tableValueTotal")),
        "confidential_omitted": _flag(found.get("isConfidentialOmitted")),
        "other_manager_count": parse_amount(found.get("otherIncludedManagersCount")),
    }


def normalize_info_rows(raw_rows: list[dict], *, filing_date: str | None) -> list[dict]:
    out: list[dict] = []
    for raw in raw_rows:
        cusip = str(raw.get("cusip") or "").upper().strip()
        put_call = str(raw.get("putCall") or "").upper().strip() or None
        sh_prn = str(raw.get("sshPrnamtType") or "SH").upper().strip() or "SH"
        out.append(
            {
                "cusip": cusip,
                "figi": (raw.get("figi") or raw.get("FIGI") or "") or None,
                "issuer": raw.get("nameOfIssuer") or "",
                "title_of_class": raw.get("titleOfClass") or "",
                "sh_prn": sh_prn,
                "put_call": put_call,
                "shares": parse_amount(raw.get("sshPrnamt")),
                "value_usd": value_to_usd(raw.get("value"), filing_date),
                "discretion": raw.get("investmentDiscretion") or "",
                "other_manager": raw.get("otherManager") or "",
            }
        )
    return out


def position_key(row: dict) -> tuple:
    return (
        (row.get("cusip") or "").upper(),
        row.get("put_call") or "",
        (row.get("sh_prn") or "SH").upper(),
    )


def aggregate_positions(rows: list[dict]) -> list[dict]:
    """One CUSIP can be several rows (discretion, other manager). Sum them.

    Stock, puts, and calls stay separate. Share-denominated rows are not added
    to principal-amount rows.
    """
    grouped: dict[tuple, dict] = {}
    for row in rows:
        key = position_key(row)
        current = grouped.get(key)
        if current is None:
            grouped[key] = dict(row)
            continue
        if row.get("shares") is not None:
            current["shares"] = (current.get("shares") or 0) + row["shares"]
        if row.get("value_usd") is not None:
            current["value_usd"] = (current.get("value_usd") or 0) + row["value_usd"]
        if row.get("issuer") and not current.get("issuer"):
            current["issuer"] = row["issuer"]
        if row.get("figi") and not current.get("figi"):
            current["figi"] = row["figi"]
    return list(grouped.values())


def merge_filings(filings: list[dict]) -> list[dict]:
    """Merge one period's filings, oldest first.

    A 13F-HR or a RESTATEMENT replaces the book. NEW HOLDINGS adds rows and
    must not wipe the rest of the book. Notices are ignored.
    """
    book: dict[tuple, dict] = {}
    for filing in filings:
        form = filing.get("form") or ""
        if form in NOTICE_FORMS:
            continue
        if form and form not in HOLDINGS_FORMS:
            continue
        rows = aggregate_positions(filing.get("rows") or [])
        amendment = (filing.get("amendment_type") or "").upper() or None
        if form == "13F-HR/A" and amendment == "NEW HOLDINGS":
            for row in rows:
                book[position_key(row)] = row
            continue
        if form == "13F-HR/A" and amendment not in {None, "RESTATEMENT"}:
            for row in rows:
                book.setdefault(position_key(row), row)
            continue
        book = {position_key(row): row for row in rows}
    return list(book.values())


def reconcile(raw_row_count: int, rows: list[dict], primary: dict | None) -> dict:
    """Compare disclosed rows with the cover-page totals. Tolerance is 1%."""
    primary = primary or {}
    expected_rows = primary.get("table_entry_total")
    expected_value = primary.get("table_value_total_usd")
    # Cover-page value is in the same units as the info table before our
    # pre-2023 thousands adjustment. Callers pass the already-normalized total
    # when they have multiplied it.
    actual_value = sum(int(row.get("value_usd") or 0) for row in rows)
    row_ok = expected_rows is None or int(expected_rows) == int(raw_row_count)
    if expected_value is None:
        value_ok = True
        value_gap = None
    else:
        expected = int(expected_value)
        value_gap = actual_value - expected
        value_ok = abs(value_gap) <= max(1, int(abs(expected) * 0.01))
    return {
        "raw_row_count": raw_row_count,
        "aggregated_row_count": len(rows),
        "table_entry_total": expected_rows,
        "table_value_total_usd": expected_value,
        "actual_value_usd": actual_value,
        "value_gap_usd": value_gap,
        "rows_match": row_ok,
        "value_match": value_ok,
        "ok": bool(row_ok and value_ok),
        "may_be_incomplete": bool(primary.get("confidential_omitted")),
    }


def group_filings_by_period(filings: list[dict], *, periods: int) -> list[list[dict]]:
    """Newest N periods of 13F-HR and 13F-HR/A, returned oldest period first.

    Each period's filings are oldest first so a restatement or new-holdings
    amendment is applied after the original book. Notices are dropped.
    """
    by_period: dict[str, list[dict]] = {}
    for filing in filings:
        if filing.get("form") not in HOLDINGS_FORMS:
            continue
        period = normalize_date(filing.get("report_date")) or ""
        if not period:
            continue
        by_period.setdefault(period, []).append(filing)
    chosen = sorted(by_period, reverse=True)[: max(0, periods)]
    groups: list[list[dict]] = []
    for period in sorted(chosen):
        group = sorted(
            by_period[period],
            key=lambda row: (row.get("filing_date") or "", row.get("accession") or ""),
        )
        groups.append(group)
    return groups


def classify_change(current_shares: int | None, prior_shares: int | None) -> str:
    cur = current_shares or 0
    prev = prior_shares or 0
    if prev <= 0 and cur > 0:
        return "new"
    if cur <= 0 and prev > 0:
        return "exit"
    if prev <= 0 and cur <= 0:
        return "unchanged"
    delta = (cur - prev) / prev
    if abs(delta) < 0.01:
        return "unchanged"
    return "add" if delta > 0 else "trim"


def diff_positions(
    current: list[dict],
    prior: list[dict],
    *,
    manager_id: str,
    period: str,
    prior_period: str | None,
) -> list[dict]:
    """Share changes versus the prior period. Equity rows only (no puts or calls)."""
    def equity(rows: list[dict]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for row in rows:
            if row.get("put_call"):
                continue
            if (row.get("sh_prn") or "SH").upper() not in {"SH", ""}:
                continue
            cusip = (row.get("cusip") or "").upper()
            if not cusip:
                continue
            out[cusip] = row
        return out

    cur_map = equity(current)
    prev_map = equity(prior)
    changes: list[dict] = []
    for cusip in sorted(set(cur_map) | set(prev_map)):
        now = cur_map.get(cusip)
        old = prev_map.get(cusip)
        cur_sh = (now or {}).get("shares")
        old_sh = (old or {}).get("shares")
        kind = classify_change(cur_sh, old_sh)
        base = now or old or {}
        prev_sh = old_sh or 0
        delta = (cur_sh or 0) - prev_sh
        delta_pct = None if prev_sh <= 0 else round(delta / prev_sh * 100, 2)
        changes.append(
            {
                "manager_id": manager_id,
                "period": period,
                "prior_period": prior_period,
                "cusip": cusip,
                "issuer": base.get("issuer") or "",
                "ticker": base.get("ticker"),
                "ssi_ticker": base.get("ssi_ticker") or base.get("ticker"),
                "change_type": kind,
                "shares": cur_sh,
                "shares_prior": old_sh,
                "shares_delta": delta,
                "shares_delta_pct": delta_pct,
                "value_usd": (now or {}).get("value_usd"),
                "put_call": None,
            }
        )
    return changes


def annotate_weights(rows: list[dict]) -> list[dict]:
    equity = [row for row in rows if not row.get("put_call")]
    total = sum(int(row.get("value_usd") or 0) for row in equity)
    ranked = sorted(equity, key=lambda row: int(row.get("value_usd") or 0), reverse=True)
    rank = {position_key(row): index + 1 for index, row in enumerate(ranked)}
    out = []
    for row in rows:
        copied = dict(row)
        value = int(row.get("value_usd") or 0)
        if row.get("put_call") or total <= 0:
            copied["weight_pct"] = None
            copied["rank"] = None
        else:
            copied["weight_pct"] = round(value / total * 100, 4)
            copied["rank"] = rank.get(position_key(row))
        out.append(copied)
    return out


def discover_dataset_urls(html: str) -> list[str]:
    """Pull Form 13F data-set zip links from the sec.gov listing page."""
    rels = re.findall(r'(/files/[^"\'\s>]+form13f\.zip)', html or "")
    seen: list[str] = []
    for rel in rels:
        url = f"https://www.sec.gov{rel}"
        if url not in seen:
            seen.append(url)

    def sort_key(url: str) -> str:
        match = re.search(r"/(\d{2}[a-z]{3}\d{4})-", url, re.I)
        if not match:
            return url
        try:
            return datetime.strptime(match.group(1), "%d%b%Y").strftime("%Y-%m-%d")
        except ValueError:
            return match.group(1)

    return sorted(seen, key=sort_key, reverse=True)


def parse_form_idx(text: str) -> list[dict]:
    """Rows from an EDGAR daily form index. Header lines are skipped."""
    rows = []
    for line in (text or "").splitlines():
        if not line or line.startswith("---") or line.startswith("Form Type"):
            continue
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 5:
            continue
        form, company, cik, filed, filename = parts[0], parts[1], parts[2], parts[3], parts[4]
        if not form.startswith("13F"):
            continue
        rows.append(
            {
                "form": form,
                "company": company.strip(),
                "cik": str(cik).strip(),
                "filing_date": normalize_date(filed) or filed,
                "filename": filename.strip(),
            }
        )
    return rows


def cusip_entries_from_legacy(mappings: dict) -> dict:
    """Move string maps onto source/confidence entries and quarantine structural tickers."""
    active: dict[str, dict] = {}
    quarantine: dict[str, dict] = {}
    for cusip, value in (mappings or {}).items():
        key = str(cusip).upper().strip()
        if key in KNOWN_CUSIPS:
            active[key] = dict(KNOWN_CUSIPS[key])
            continue
        if isinstance(value, dict):
            ticker = str(value.get("ticker") or "").upper().strip()
            entry = {
                "ticker": ticker,
                "source": value.get("source") or "legacy",
                "confidence": value.get("confidence") or "medium",
            }
        else:
            ticker = str(value or "").upper().strip()
            entry = {"ticker": ticker, "source": "legacy", "confidence": "medium"}
        if not ticker:
            continue
        if structural_ticker(ticker):
            entry["reason"] = "structural_ticker"
            quarantine[key] = entry
        else:
            active[key] = entry
    for cusip, entry in KNOWN_CUSIPS.items():
        active[cusip] = dict(entry)
    return {"mappings": active, "quarantine": quarantine}


def ticker_map(entries: dict) -> dict[str, str]:
    """Active CUSIP to ticker. Structural and quarantined rows are left out."""
    out = {}
    for cusip, entry in (entries or {}).items():
        if isinstance(entry, str):
            ticker = entry.upper().strip()
        else:
            ticker = str((entry or {}).get("ticker") or "").upper().strip()
        if ticker and not structural_ticker(ticker):
            out[str(cusip).upper()] = ticker
    return out


def bridge_local_listing(issuer: str, us_ticker: str | None, names: dict[str, str]) -> str | None:
    """Point an ADR or US line at an SSI local ticker when the company is the book name.

    Name fallback is not written back into the CUSIP map.
    """
    if us_ticker and us_ticker.upper() in {key.upper() for key in names}:
        return us_ticker.upper()
    issuer_key = _company_key(issuer)
    if len(issuer_key) < 6:
        return us_ticker.upper() if us_ticker else None
    hits = []
    for ticker, company in names.items():
        if _company_key(company) == issuer_key and "." in ticker:
            hits.append(ticker.upper())
    if len(hits) == 1:
        return hits[0]
    return us_ticker.upper() if us_ticker else None


def _company_key(name: str) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    text = re.sub(r"\s+", " ", text).strip()
    for suffix in (
        " incorporated", " corporation", " corp", " company", " inc", " ltd", " plc",
        " llc", " lp", " sa", " nv", " ag", " co", " limited", " adr", " ads",
    ):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def manager_confidentiality_issues(document: dict) -> list[str]:
    """Public registry may carry a name and a CIK, not where the name came from."""
    issues = []
    for index, manager in enumerate(document.get("managers") or []):
        label = manager.get("manager_id") or f"row {index}"
        for key in manager:
            if key.lower() in FORBIDDEN_MANAGER_KEYS:
                issues.append(f"{label}: field {key} is provenance and cannot be public")
        for role in manager.get("roles") or []:
            if str(role).lower() in FORBIDDEN_MANAGER_ROLES:
                issues.append(f"{label}: role {role} reveals where the manager came from")
        blob = " ".join(str(value) for value in _walk_values(manager))
        if re.search(r"\b(lp letter|letters?|email-only|gated|meeting notes)\b", blob, re.I):
            issues.append(f"{label}: text describes letter, email, or meeting provenance")
        if LICENSED_NAME_RE.search(blob):
            issues.append(f"{label}: text names a licensed data vendor")
    return issues


def _walk_values(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)
    elif value is not None:
        yield value


def licensed_path(path: str) -> bool:
    name = path.replace("\\", "/").split("/")[-1]
    return bool(LICENSED_NAME_RE.search(name))
