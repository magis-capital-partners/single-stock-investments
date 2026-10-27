#!/usr/bin/env python3
"""Extract the Section 382 facts that XBRL cannot express, with citations.

The NOL screener models the 382 limit from market cap alone, which assumes a
clean slate. Three facts decide whether that assumption holds, none of them
tagged in XBRL:

  1. PRIOR OWNERSHIP CHANGE. Loss companies routinely disclose that a change
     already happened -- "as a result of ownership changes in 2019 and 2022,
     $X of our NOLs are subject to an annual limitation". If so the headline
     carryforward is already impaired BEFORE an acquirer arrives, and the
     screener's estimate is too high. This is the single largest modelled
     error and the reason this script exists.
  2. SECTION 382(l)(5)/(l)(6). The bankruptcy exceptions; (l)(5) can remove
     the limitation entirely, which moves a row the other way.
  3. NOL RIGHTS PLAN. A 382 poison pill, typically triggering near 4.9%,
     makes an acquisition impossible without board cooperation -- a hard
     blocker on the whole thesis regardless of the arithmetic. These live in
     8-K / DEF 14A / the charter as often as the 10-K, so both are searched.

DESIGN: retrieval is deterministic, classification is the judgment call.
Regex finds candidate passages for pennies; what needs judgment is telling a
PROSPECTIVE risk factor from a HISTORICAL event. Vanda's 10-K says its
attributes "would be subject to limitation ... should an ownership change ...
occur" -- boilerplate present in nearly every loss company's filing and
meaning nothing has happened. Reading that as an impairment would be worse
than not looking. So every hit is classified, and anything the rules cannot
separate is emitted as `needs_review` rather than guessed: an unresolved fact
is cheap, a confidently wrong one silently corrupts the valuation.

Output carries a verbatim quote, the accession number and a resolvable URL per
fact, so a wrong extraction is auditable rather than invisible.

Usage:
  python _system/scripts/extract_nol_382_facts.py --from-screener
  python _system/scripts/extract_nol_382_facts.py --tickers SIRI NWL REI VNDA
  python _system/scripts/extract_nol_382_facts.py --tickers SIRI --write

ASCII-only output: this runs on a cp1252 console.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCREENER = ROOT / "dashboard" / "data" / "nol_screener.json"
OUTPUT = ROOT / "dashboard" / "data" / "nol_382_facts.json"

SEC_UA = "Marvin Research marvin@single-stock-investments.local"
SEC_THROTTLE_S = 0.15
# A proxy can be hundreds of megabytes. Skip it rather than loading it; the
# 10-K and 10-Q still carry the income-tax note, and a skipped file is recorded.
MAX_DOCUMENT_BYTES = 30_000_000
CONTEXT_BEFORE = 320
CONTEXT_AFTER = 520
# Forms searched, newest first. 10-K carries the tax footnote; DEF 14A and 8-K
# carry rights plans, which a 10-K may never mention.
# 10-Q is the latest interim income-tax note. DEF 14A stays because a tax
# rights plan is often only in the proxy. 8-Ks are filtered to rights-plan
# and charter items so a May filing is not crowded out by unrelated current
# reports. Caps are per bucket after that filter.
FORM_BUCKETS = {
    "10-K": "10-K",
    "10-K/A": "10-K",
    "10-Q": "10-Q",
    "10-Q/A": "10-Q",
    "8-K": "8-K",
    "8-K/A": "8-K",
    "DEF 14A": "DEF 14A",
}
MAX_FILINGS_PER_FORM = {"10-K": 1, "10-Q": 1, "DEF 14A": 1, "8-K": 12}
# Item 1.01 (material agreement), 3.03 (rights of holders), 5.03 (articles).
# Item 8.01 is too common to treat as a rights-plan signal by itself.
RIGHTS_PLAN_ITEMS = {"1.01", "3.03", "5.03"}
EIGHT_K_TEXT_RE = re.compile(r"tax|rights plan|nol|section\s*382|ownership", re.I)
# Public CIKs for the eight-name refresh. The screener is preferred when it
# has a CIK; this map lets CI run `--tickers` with no path outside the repo.
CIK_FALLBACK = {
    "REI": "0001384195",
    "SIRI": "0000908937",
    "VNDA": "0001347178",
    "NWL": "0000814453",
    "JAKK": "0001009829",
    "TVTX": "0001438533",
    "TTI": "0000844965",
    "GDOT": "0001386278",
}

# --------------------------------------------------------------------------
# classification vocabulary
#
# A hit is only useful once you know whether it describes something that
# HAPPENED or something that MIGHT. These two lists are deliberately narrow;
# anything matching both, or neither, is escalated rather than resolved.
# --------------------------------------------------------------------------
HISTORICAL_MARKERS = (
    r"\bwe (?:have )?experienced\b",
    r"\bwe (?:have )?underwent\b",
    r"\bunderwent an ownership change\b",
    r"\bownership change (?:occurred|has occurred)\b",
    r"\bas a result of (?:the|an|our|prior) ownership change",
    r"\bwe determined that an ownership change\b",
    r"\bhave been subject to (?:an )?annual limitation",
    r"\bare subject to (?:an )?annual limitation",
    r"\bresulted in an ownership change\b",
    r"\btriggered an ownership change\b",
    # "the pre-ownership change period" presupposes a change already happened;
    # REI's 10-K uses exactly this and matched no other historical marker, so
    # it escalated to needs_review rather than being missed outright.
    r"\bpre-ownership change\b",
    r"\bpost-ownership change\b",
    r"\bprior ownership change\b",
)
PROSPECTIVE_MARKERS = (
    r"\bwould be subject\b",
    r"\bcould be subject\b",
    r"\bmay be subject\b",
    r"\bshould an ownership change\b",
    r"\bif we experience\b",
    r"\bif an ownership change\b",
    r"\bin the event (?:of|that)\b",
    r"\bmay be limited\b",
    r"\bcould be limited\b",
    r"\bmay become subject\b",
)

PATTERNS = {
    "ownership_change": r"ownership change",
    "bankruptcy_382": r"382\s*\(\s*l\s*\)\s*\(\s*[56]\s*\)|section\s*382\(l\)\(5\)|bankruptcy exception",
    # A 382 pill is rarely called a "rights plan" in the filing. TETRA's is a
    # "Tax Plan" that "deters any person or group from becoming ... a
    # 5-percent stockholder for purposes of Section 382" -- a hard blocker on
    # any acquisition, and invisible to a Rights-Agreement-only pattern. The
    # house styles are Tax Benefit Preservation Plan, Tax Asset Protection
    # Plan, NOL Rights Plan and plain Tax Plan; match the function, not a name.
    "rights_plan": (
        r"[Tt]ax (?:[Bb]enefit [Pp]reservation|[Aa]sset [Pp]rotection|[Bb]enefits? [Pp]reservation)"
        r"\s*(?:Plan|Agreement)"
        r"|(?:NOL|[Ss]ection\s*382|[Tt]ax [Bb]enefit)[^.]{0,80}?[Rr]ights\s*(?:Agreement|Plan)"
        r"|[Rr]ights\s*(?:Agreement|Plan)[^.]{0,80}?(?:NOL|net operating loss|[Ss]ection\s*382)"
        r"|[Tt]ax Plan[^.]{0,120}?(?:[Ss]ection\s*382|ownership change|5-percent stockholder)"
        r"|(?:[Ss]ection\s*382|ownership change)[^.]{0,120}?[Tt]ax Plan"
    ),
}
# Dollar amounts and years inside an ownership-change passage.
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
TRIGGER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def http_get(url: str, raw: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read(MAX_DOCUMENT_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None if raw else {"__error__": f"{type(exc).__name__}: {str(exc)[:120]}"}
    time.sleep(SEC_THROTTLE_S)
    if len(body) > MAX_DOCUMENT_BYTES:
        return None if raw else {"__error__": f"document exceeds {MAX_DOCUMENT_BYTES} bytes"}
    if raw:
        return body
    try:
        return json.loads(body.decode())
    except json.JSONDecodeError:
        return {"__error__": "unparseable json"}


def strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&#\d+;|&[a-zA-Z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# A heading the hit sits under. HTML 10-Ks usually have no page number; page
# stays null unless a "page N" or "F-N" marker is within this many characters
# before the hit. A null page is not a guessed page.
SECTION_RE = re.compile(
    r"(?i)\b((?:note|item)\s+\d+[a-z]?(?:\s*[:.\-\u2013\u2014]\s*|\s+)[a-z0-9][^.]{2,80})"
)
PAGE_MARK_RE = re.compile(r"(?i)(?:\bpage\s+(\d{1,4})\b|\b(F-\d{1,4})\b)")
# "Note 15, Income Taxes", "NOTE 14 INCOME TAXES", "(16) Income Taxes",
# and "11. Income Taxes". A bare number plus the words, as in a table cell
# ("507 Income taxes paid"), is not a heading.
TAX_NOTE_RE = re.compile(
    r"(?i)("
    r"note\s+\d+[a-z]?\s*[,:.\-\u2013\u2014]?\s*income\s+tax(?:es)?"
    r"|\(\s*\d+[a-z]?\s*\)\s*income\s+tax(?:es)?"
    r"|\d+[a-z]?\.\s*income\s+tax(?:es)?"
    r")"
)
# "are subject to Section 382 limitations" is a historical impairment sentence
# that does not use the words "ownership change" and does not state a dollar cap.
LIMITATIONS_PHRASE_RE = re.compile(
    r"(?i)(.{0,160}subject to Section\s*382 limitations?.{0,80})"
)
STATED_LIMIT_RE = re.compile(
    r"(?i)(?:annual\s+limitation|section\s*382\s+limitation|limited\s+to)"
    r"(?:\s+(?:of|is|was|equals))?\s{0,40}\$\s?([\d,]+(?:\.\d+)?)\s*(billion|million|thousand)?"
)
PAGE_LOOKBACK = 2500
SECTION_LOOKBACK = 8000


def _clean_locator(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" -.:")[:120]


def _heading_ok(section: str) -> bool:
    """Reject a year or a singular 'income tax' table phrase as a note title."""
    if re.match(r"(?i)^(19|20)\d{2}\b", section):
        return False
    return bool(re.search(r"(?i)income taxes\b", section))


def nearest_section(text: str, index: int) -> str | None:
    """Heading closest before index. An income-tax heading beats a nearer Item 1."""
    start = max(0, index - SECTION_LOOKBACK)
    window = text[start : index + 40]
    anchor = index - start
    matches = [m for m in SECTION_RE.finditer(window) if m.start() <= anchor]
    if not matches:
        return None
    taxish = [m for m in matches if re.search(r"income tax", m.group(1), re.I)]
    title = _clean_locator((taxish or matches)[-1].group(1))
    if len(title) > 70 or "financial statement" in title.lower():
        return None
    return title


def nearest_page(text: str, index: int) -> str | None:
    """Page marker immediately before index, or None when the HTML has none."""
    window = text[max(0, index - PAGE_LOOKBACK) : index]
    matches = list(PAGE_MARK_RE.finditer(window))
    if not matches:
        return None
    return next(group for group in matches[-1].groups() if group)


def find_income_tax_section(text: str) -> dict | None:
    """Last Note or Item heading that is the income-tax note. No invented page.

    The first hit is often the table of contents. The note itself repeats the
    heading later, so the last heading wins. A bare 'income taxes' in a sentence
    is not a section.
    """
    matches = [
        m for m in TAX_NOTE_RE.finditer(text)
        if _heading_ok(_clean_locator(m.group(1)))
    ]
    if not matches:
        return None
    match = matches[-1]
    section = _clean_locator(match.group(1))
    if len(section) > 70:
        return None
    return {
        "section": section,
        "page": nearest_page(text, match.start()),
    }


def stated_limit_usd(passage: str) -> float | None:
    """Dollar limit only when the sentence states an annual or Section 382 limitation.

    A valuation-allowance or pretax figure in the same paragraph is not a limit.
    """
    match = STATED_LIMIT_RE.search(passage)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    scale = {"billion": 1e9, "million": 1e6, "thousand": 1e3}.get(
        (match.group(2) or "").lower(), 1.0
    )
    return value * scale


def _form_bucket(form: str) -> str | None:
    return FORM_BUCKETS.get(form)


def _filing_record(cik: str, recent: dict, index: int, n: int) -> dict | None:
    accession = (recent.get("accessionNumber") or [None] * n)[index]
    primary = (recent.get("primaryDocument") or [None] * n)[index]
    if not accession or not primary:
        return None
    items = (recent.get("items") or [None] * n)[index]
    description = (recent.get("primaryDocDescription") or [None] * n)[index]
    return {
        "form": (recent.get("form") or [None] * n)[index],
        "accession": accession,
        "filed": (recent.get("filingDate") or [None] * n)[index],
        "items": items,
        "description": description,
        "url": (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{primary}"
        ),
    }


def _eight_k_is_tax_or_rights(record: dict) -> bool:
    raw_items = str(record.get("items") or "")
    item_set = {part.strip() for part in raw_items.split(",") if part.strip()}
    blob = f"{record.get('description') or ''} {raw_items}"
    return bool(item_set & RIGHTS_PLAN_ITEMS) or bool(EIGHT_K_TEXT_RE.search(blob))


def recent_filings(cik: str) -> list[dict]:
    """Newest 10-K, 10-Q, and DEF 14A, plus rights-plan 8-Ks, from submissions."""
    padded = str(cik).zfill(10)
    doc = http_get(f"https://data.sec.gov/submissions/CIK{padded}.json")
    if not doc or doc.get("__error__"):
        return []
    recent = (doc.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    picked: dict[str, list[dict]] = {"10-K": [], "10-Q": [], "DEF 14A": [], "8-K": []}
    newest_8k: list[dict] = []
    interesting_8k: list[dict] = []
    for i, form in enumerate(forms):
        bucket = _form_bucket(form)
        if not bucket:
            continue
        record = _filing_record(padded, recent, i, len(forms))
        if not record:
            continue
        if bucket != "8-K":
            if len(picked[bucket]) < MAX_FILINGS_PER_FORM[bucket]:
                picked[bucket].append(record)
            continue
        # Newest current reports, plus older ones that look like a rights plan
        # or a tax disclosure. The newest-six pass keeps a plan that the item
        # codes do not label.
        if len(newest_8k) < 6:
            newest_8k.append(record)
        if _eight_k_is_tax_or_rights(record) and len(interesting_8k) < MAX_FILINGS_PER_FORM["8-K"]:
            interesting_8k.append(record)
    seen_acc: set[str] = set()
    for record in newest_8k + interesting_8k:
        if record["accession"] in seen_acc:
            continue
        seen_acc.add(record["accession"])
        picked["8-K"].append(record)
        if len(picked["8-K"]) >= MAX_FILINGS_PER_FORM["8-K"]:
            break
    out: list[dict] = []
    for bucket in ("10-K", "10-Q", "DEF 14A", "8-K"):
        out.extend(picked[bucket])
    return out


def classify_tense(passage: str) -> tuple[str, list[str]]:
    """HISTORICAL / PROSPECTIVE / AMBIGUOUS, plus the markers that decided it."""
    lowered = passage.lower()
    hist = [p for p in HISTORICAL_MARKERS if re.search(p, lowered)]
    pros = [p for p in PROSPECTIVE_MARKERS if re.search(p, lowered)]
    if hist and not pros:
        return "historical", hist
    if pros and not hist:
        return "prospective", pros
    if hist and pros:
        return "ambiguous", hist + pros
    return "ambiguous", []


def change_years(passage: str) -> list[str]:
    """Years plausibly naming WHEN a change happened.

    A naive year scan over this language is mostly noise: every such passage
    cites the "Internal Revenue Code of 1986", and filings restate their own
    period end, so Vanda's real answer (2014) arrived buried in
    ['1986', '2014', '2017', '2025', '2026']. Keep only years sitting close to
    the phrase itself, drop the statutory reference, and drop anything at or
    beyond the current year, which is the filing's own dateline rather than a
    past event.
    """
    now = datetime.now(timezone.utc).year
    out: set[str] = set()
    for anchor in re.finditer(r"ownership change", passage, re.I):
        window = passage[max(0, anchor.start() - 140) : anchor.end() + 200]
        window = re.sub(r"Internal Revenue Code of \d{4}", " ", window, flags=re.I)
        for match in YEAR_RE.finditer(window):
            year = int(match.group(0))
            if 1990 <= year < now:
                out.add(str(year))
    return sorted(out)


def scan_filing(text: str, filing: dict) -> list[dict]:
    facts: list[dict] = []
    for kind, pattern in PATTERNS.items():
        for match in re.finditer(pattern, text, re.I):
            start = max(0, match.start() - CONTEXT_BEFORE)
            passage = text[start : match.end() + CONTEXT_AFTER].strip()
            tense, markers = classify_tense(passage)
            fact = {
                "kind": kind,
                "tense": tense,
                "markers": markers[:4],
                "quote": passage[:900],
                "form": filing["form"],
                "accession": filing["accession"],
                "filed": filing["filed"],
                "section": nearest_section(text, match.start()),
                "page": nearest_page(text, match.start()),
                "url": filing["url"],
            }
            if kind == "ownership_change":
                # A dollar figure elsewhere in the paragraph is not a Section 382 limit.
                fact["limited_amount_usd"] = stated_limit_usd(passage) if tense == "historical" else None
                fact["dollar_limit_stated"] = fact["limited_amount_usd"] is not None
                fact["years_mentioned"] = change_years(passage)
            if kind == "rights_plan":
                triggers = [float(t) for t in TRIGGER_RE.findall(passage)]
                # A 382 pill sits near 4.9%. A round 5 in the same sentence is
                # often a different test. Prefer the figure closest to 4.99.
                under_10 = [t for t in triggers if t <= 10.0]
                pill_band = [t for t in under_10 if 4.5 <= t <= 5.0]
                pool = pill_band or under_10
                fact["trigger_pct"] = min(pool, key=lambda t: abs(t - 4.99)) if pool else None
            facts.append(fact)
            if len(facts) >= 40:
                return facts
    return facts


def summarize(ticker: str, facts: list[dict]) -> dict:
    """Collapse raw hits into the fields the 382 model would consume.

    `prior_ownership_change` is only asserted on a HISTORICAL hit. Prospective
    boilerplate appears in nearly every loss company's risk factors and means
    nothing happened; treating it as an event would impair every row on the
    screen. Ambiguous hits set needs_review instead of deciding.
    """
    owner = [f for f in facts if f["kind"] == "ownership_change"]
    historical = [f for f in owner if f["tense"] == "historical"]
    ambiguous = [f for f in owner if f["tense"] == "ambiguous"]
    pill = [f for f in facts if f["kind"] == "rights_plan"]
    bankruptcy = [f for f in facts if f["kind"] == "bankruptcy_382"]

    amounts = [f.get("limited_amount_usd") for f in historical if f.get("limited_amount_usd")]
    years = sorted({y for f in historical for y in f.get("years_mentioned") or []})
    triggers = [f.get("trigger_pct") for f in pill if f.get("trigger_pct")]
    chosen_trigger = min(triggers) if triggers else None
    with_trigger = [f for f in pill if f.get("trigger_pct") == chosen_trigger]
    pill_evidence = next((f for f in with_trigger if f.get("section")), None)
    if pill_evidence is None and with_trigger:
        pill_evidence = with_trigger[0]
    if pill_evidence is None and pill:
        pill_evidence = pill[0]
    change_evidence = historical[0] if historical else None

    return {
        "ticker": ticker,
        "prior_ownership_change": {
            "occurred": bool(historical),
            "years": years,
            "limited_amount_usd": max(amounts) if amounts else None,
            "dollar_limit_stated": bool(amounts),
            "evidence": change_evidence,
            "hit_counts": {
                "historical": len(historical),
                "prospective": len(owner) - len(historical) - len(ambiguous),
                "ambiguous": len(ambiguous),
            },
        },
        "nol_rights_plan": {
            "present": bool(pill),
            "trigger_pct": min(triggers) if triggers else None,
            "evidence": pill_evidence,
        },
        "bankruptcy_382_exception": {
            "mentioned": bool(bankruptcy),
            "evidence": bankruptcy[0] if bankruptcy else None,
        },
        # An ambiguous ownership-change hit is the case worth a human or an LLM;
        # everything else here is settled by the rules.
        "needs_review": bool(ambiguous) and not historical,
        "reviewed_forms": sorted({f["form"] for f in facts}),
    }


def _income_tax_note(text: str, filing: dict) -> dict:
    found = find_income_tax_section(text) or {}
    return {
        "form": filing["form"],
        "accession": filing["accession"],
        "filed": filing["filed"],
        "section": found.get("section"),
        "page": found.get("page"),
        "url": filing["url"],
        "section_found": bool(found.get("section")),
    }


def extract_for(ticker: str, cik: str) -> dict:
    filings = recent_filings(cik)
    if not filings:
        return {
            "ticker": ticker,
            "cik": cik,
            "accession": None,
            "section": None,
            "page": None,
            "error": "no filings retrieved",
        }
    facts: list[dict] = []
    tax_notes: list[dict] = []
    limitation_hits: list[dict] = []
    for filing in filings:
        body = http_get(filing["url"], raw=True)
        if not body:
            filing["skipped"] = "download failed or document over the size cap"
            continue
        text = strip_html(body.decode("utf-8", "replace"))
        facts.extend(scan_filing(text, filing))
        if filing["form"] in ("10-K", "10-K/A", "10-Q", "10-Q/A"):
            tax_notes.append(_income_tax_note(text, filing))
            phrase = LIMITATIONS_PHRASE_RE.search(text)
            if phrase:
                quote = re.sub(r"\s+", " ", phrase.group(1)).strip()
                limitation_hits.append(
                    {
                        "quote": quote[:400],
                        "form": filing["form"],
                        "accession": filing["accession"],
                        "filed": filing["filed"],
                        "section": nearest_section(text, phrase.start()),
                        "page": nearest_page(text, phrase.start()),
                        "url": filing["url"],
                        "dollar_limit_stated": stated_limit_usd(quote) is not None,
                    }
                )
    result = summarize(ticker, facts)
    # A carryforward "subject to Section 382 limitations" is not an ownership-change
    # hit and is not a dollar limit. Flag it so the row does not read as silent.
    result["section_382_limitations_phrase"] = limitation_hits[0] if limitation_hits else None
    if limitation_hits and not (result.get("prior_ownership_change") or {}).get("occurred"):
        if not limitation_hits[0].get("dollar_limit_stated"):
            result["needs_review"] = True
            result["needs_review_reason"] = (
                "The filing says tax attributes are subject to Section 382 limitations "
                "and states no annual dollar limit. No dollar limit is inferred."
            )
    result["cik"] = str(cik).zfill(10)
    # Newest periodic report that actually contains an income-tax heading,
    # otherwise the newest 10-Q or 10-K that was fetched.
    located = [n for n in tax_notes if n.get("section_found")]
    pool = located or tax_notes
    pool.sort(key=lambda n: n.get("filed") or "", reverse=True)
    note = pool[0] if pool else None
    result["income_tax_note"] = note
    result["accession"] = (note or {}).get("accession")
    result["section"] = (note or {}).get("section")
    result["page"] = (note or {}).get("page")
    result["filings_scanned"] = [
        {k: f[k] for k in ("form", "accession", "filed", "url", "skipped") if k in f} for f in filings
    ]
    return result


def screener_targets() -> list[tuple[str, str]]:
    """Rows worth the fetch: anything not structurally blocked, with a CIK.

    Deliberately not all 89. A row already blocked because its own auditor
    fully reserves the asset does not become investable if a filing says the
    NOL is unimpaired, so spending SEC round-trips on it buys nothing.
    """
    doc = json.loads(SCREENER.read_text(encoding="utf-8"))
    out = []
    for row in doc.get("rows") or []:
        if not row.get("cik"):
            continue
        if row.get("usability") in ("material_after_382", "immaterial_after_382"):
            out.append((row["ticker"], row["cik"]))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="*", help="explicit tickers (needs --cik-from-screener)")
    parser.add_argument("--from-screener", action="store_true",
                        help="every non-blocked screener row carrying a CIK")
    parser.add_argument("--write", action="store_true", help=f"write {OUTPUT.name}")
    args = parser.parse_args()

    if args.from_screener or not args.tickers:
        targets = screener_targets()
    else:
        by_ticker: dict[str, dict] = {}
        if SCREENER.is_file():
            doc = json.loads(SCREENER.read_text(encoding="utf-8"))
            by_ticker = {r["ticker"]: r for r in doc.get("rows") or [] if r.get("ticker")}
        wanted = [t.upper() for t in args.tickers]
        targets = []
        missing = []
        for ticker in wanted:
            row = by_ticker.get(ticker) or {}
            cik = row.get("cik") or CIK_FALLBACK.get(ticker)
            if cik:
                targets.append((ticker, str(cik).zfill(10)))
            else:
                missing.append(ticker)
        if missing:
            print(f"no CIK in screener or fallback for: {', '.join(missing)}", file=sys.stderr)

    results = []
    for ticker, cik in targets:
        print(f"  scanning {ticker} (CIK {cik}) ...", flush=True)
        results.append(extract_for(ticker, cik))

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "SEC EDGAR submissions + primary documents",
        "method": (
            "Deterministic regex retrieval over the latest 10-K, latest 10-Q, latest DEF 14A, "
            "and 8-Ks whose items or description point at a rights plan or tax disclosure, "
            "then tense classification. Each row carries the income-tax note accession and "
            "section. page is set only when a page marker sits just before the heading; "
            "HTML filings often have none, and a missing page is left null. A Section 382 "
            "dollar limit is recorded only when the sentence states an annual limitation "
            "or a Section 382 limitation. Prospective risk-factor boilerplate is NOT an "
            "ownership change; ambiguous hits set needs_review rather than being resolved. "
            "Public EDGAR only; no path outside this repo."
        ),
        "not_extractable": [
            "NUBIG / NUBIL -- requires asset-level tax basis versus fair value, which is "
            "not disclosed in any filing. Flag candidates qualitatively; never model a number.",
        ],
        "research_only": True,
        "rows": results,
    }
    if args.write:
        OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {OUTPUT} ({len(results)} rows)")
    else:
        for r in results:
            oc = r.get("prior_ownership_change") or {}
            print(f"  {r['ticker']:6s} prior_change={oc.get('occurred')} "
                  f"years={oc.get('years')} pill={(r.get('nol_rights_plan') or {}).get('present')} "
                  f"needs_review={r.get('needs_review')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
