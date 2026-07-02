"""Parse reporting-person names and filing class from SEC 13D/13G HTML/text."""
from __future__ import annotations

import re
from pathlib import Path

from activist_common import firm_name, match_firm_id

PASSIVE_13G_FORMS = frozenset({"SC 13G", "SC 13G/A"})
ACTIVIST_13D_FORMS = frozenset({"SC 13D", "SC 13D/A"})
PROXY_FORMS = frozenset({"DEFC14A", "PREC14A", "DFAN14A"})
UNRESOLVED_FIRM_ID = "unknown_activist"
UNRESOLVED_FIRM_NAME = "Unresolved SEC filer"
SEC_FILING_PREFIXES = ("SC-", "DEFC", "PREC", "DFAN")

ACTIVIST_INTENT_RE = re.compile(
    r"\b("
    r"seek(?:ing)?\s+(?:to\s+)?(?:elect|nominate)|"
    r"board\s+seat|"
    r"proxy\s+fight|"
    r"change\s+in\s+control|"
    r"strategic\s+alternatives|"
    r"operational\s+changes|"
    r"push\s+for|"
    r"activist"
    r")\b",
    re.I,
)

TAG_RE = re.compile(r"<[^>]+>")
ENTITY_SUFFIX_RE = re.compile(
    r"\b("
    r"LLC|L\.L\.C\.|LP|L\.P\.|INC\.?|CORP\.?|LTD\.?|TRUST|PARTNERS|"
    r"MANAGEMENT|CAPITAL|ADVISORS|ADVISERS|FUND|HOLDINGS|GROUP|COMPANY"
    r")\b",
    re.I,
)
PROXY_FILER_LABEL_RE = re.compile(
    r"\(Name of Person\(s\) Filing Proxy Statement[^)]*\)",
    re.I,
)
PROXY_REGISTRANT_LABEL_RE = re.compile(r"Name of Registrant as Specified in Its Charter", re.I)
CENTERED_P_RE = re.compile(
    r"<P[^>]*text-align:\s*center[^>]*>\s*(?:<B>)?\s*([^<]{3,120}?)\s*(?:</B>)?\s*</P>",
    re.I,
)
PROXY_BOLD_BEFORE_LABEL_RE = re.compile(
    r"(?:<span[^>]*font-weight:700[^>]*>([^<]{3,120})</span>|<B>([^<]{3,120})</B>)"
    r"\s*</(?:span|div|td|tr)>\s*(?:<(?:div|span|td|tr)[^>]*>\s*){0,8}\(Name of Person\(s\) Filing Proxy Statement",
    re.I,
)
SOLICITATION_GROUP_RE = re.compile(
    r"([A-Z][A-Za-z0-9 .,&'\-/]{2,100}?(?:LLC|L\.L\.C\.|LLP|L\.L\.P\.|Inc\.?|LP|Partners|Management|Fund|Trust|Company))"
    r"(?:\s*,?\s*(?:and|&)\s+[A-Z][A-Za-z0-9 .,&'\-/]{2,80}?(?:LLC|LLP|Inc\.?|LP|Fund|Trust|Company))?"
    r"\s*\(collectively",
    re.I,
)


def strip_html(text: str) -> str:
    text = TAG_RE.sub(" ", text or "")
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_noise_name(name: str) -> bool:
    low = name.lower().strip()
    if not low or len(low) < 3:
        return True
    if low in {
        "names of reporting persons",
        "name of reporting person",
        "i.r.s. identification no. of above persons (entities only)",
        "delaware",
        "united states",
        "new york",
        "california",
        "sec use only",
        "payment of filing fee (check the appropriate box):",
    }:
        return True
    if re.fullmatch(r"[\d\-]+", name):
        return True
    if low.startswith("name of registrant"):
        return True
    if "name of person(s) filing proxy statement" in low:
        return True
    return False


def _add_name(names: list[str], seen: set[str], name: str) -> None:
    name = re.sub(r"\s+", " ", name).strip(" .,-")
    name = re.sub(r"\s+\d+$", "", name)
    name = re.sub(r"^[:;\)\(]+", "", name).strip()
    name = re.sub(r"^[:;\s]+", "", name)
    if _is_noise_name(name):
        return
    low = name.lower()
    if low in seen:
        return
    seen.add(low)
    names.append(name)


def extract_reporting_persons(text: str, limit: int = 200_000) -> list[str]:
    raw = (text or "")[:limit]
    plain = strip_html(raw)
    names: list[str] = []
    seen: set[str] = set()

    patterns = [
        r"NAMES OF REPORTING PERSONS\s*(?:I\.R\.S\. IDENTIFICATION NO\. OF ABOVE PERSONS \(ENTITIES ONLY\)\s*)?(.{3,120}?)(?:\s*(?:I\.R\.S\.|CHECK THE APPROPRIATE|SEC USE ONLY|CITIZENSHIP|NUMBER OF SHARES|NAME OF REPORTING PERSON))",
        r"NAME OF REPORTING PERSON\s*(?:I\.R\.S\. IDENTIFICATION NO\. OF ABOVE PERSONS \(ENTITIES ONLY\)\s*)?(.{3,120}?)(?:\s*(?:I\.R\.S\.|CHECK THE APPROPRIATE|SEC USE ONLY|CITIZENSHIP|NUMBER OF SHARES|NAME OF REPORTING PERSON))",
        r"Item 2\.[\s\S]{0,400}?Identification Number\)\s*(.{3,120}?)(?:\s*(?:Item 3|Item 4|CUSIP|Check|$))",
    ]
    for pat in patterns:
        for m in re.finditer(pat, plain, re.I):
            chunk = m.group(1)
            chunk = re.split(r"\b(?:95-\d{7}|Check|Item \d)\b", chunk, maxsplit=1)[0]
            for part in re.split(r"\s{2,}|\n|;", chunk):
                _add_name(names, seen, part)

    if not names:
        for m in re.finditer(
            r"(?:NAMES OF REPORTING PERSONS|NAME OF REPORTING PERSON)[\s\S]{0,250}?<P[^>]*>\s*([^<]{3,120}?)\s*</P>",
            raw,
            re.I,
        ):
            _add_name(names, seen, strip_html(m.group(1)))

    if not names and any(form_hint in plain for form_hint in ("SCHEDULE 14A", "Proxy Statement")):
        names.extend(extract_proxy_filing_persons(raw))

    if not names:
        names.extend(extract_solicitation_group(raw))

    return names[:8]


def extract_proxy_filing_persons(text: str, limit: int = 200_000) -> list[str]:
    raw = (text or "")[:limit]
    label = PROXY_FILER_LABEL_RE.search(raw)
    if not label:
        return []

    start = 0
    registrant = PROXY_REGISTRANT_LABEL_RE.search(raw)
    if registrant:
        start = registrant.end()

    block = raw[start : label.start()]
    names: list[str] = []
    seen: set[str] = set()
    for match in CENTERED_P_RE.finditer(block):
        _add_name(names, seen, strip_html(match.group(1)))

    if names:
        return names[:8]

    plain_block = strip_html(block)
    lines = [line.strip() for line in re.split(r"\n+", plain_block) if line.strip()]
    for line in reversed(lines[-12:]):
        _add_name(names, seen, line)

    search_window = raw[max(0, label.start() - 20_000) : label.start()]
    for match in PROXY_BOLD_BEFORE_LABEL_RE.finditer(search_window):
        candidate = match.group(1) or match.group(2) or ""
        _add_name(names, seen, strip_html(candidate))

    return names[:8]


def extract_solicitation_group(text: str) -> list[str]:
    plain = strip_html(text)[:120_000]
    names: list[str] = []
    seen: set[str] = set()
    for match in SOLICITATION_GROUP_RE.finditer(plain):
        chunk = match.group(0)
        for part in re.split(r",|\band\b", chunk):
            part = part.replace("(collectively", "").strip(" .")
            _add_name(names, seen, part)
    return names[:5]


def slug_firm(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:80] or "unknown_filer"


def pick_primary_filer(filers: list[str]) -> str:
    entities = [f for f in filers if ENTITY_SUFFIX_RE.search(f)]
    if entities:
        return entities[0]
    return filers[0] if filers else ""


def display_firm_name(firm_id: str, firm_name_value: str, filers: list[str]) -> str:
    if firm_id != UNRESOLVED_FIRM_ID:
        return firm_name_value
    return UNRESOLVED_FIRM_NAME


def short_firm_label(firm_id: str, firm_name_value: str, filers: list[str]) -> str:
    if firm_id == UNRESOLVED_FIRM_ID:
        return UNRESOLVED_FIRM_NAME
    if firm_name_value and firm_name_value != UNRESOLVED_FIRM_NAME:
        base = firm_name_value
    else:
        base = pick_primary_filer(filers) or firm_name_value or firm_id
    extra = max(0, len(filers) - 1)
    if extra and not ENTITY_SUFFIX_RE.search(base):
        first = base.split()[0] if base.split() else base
        return f"{first} (+{extra})"
    if len(base) > 48:
        return base[:45] + "..."
    return base


def classify_sec_filing(form: str, text: str, filers: list[str]) -> str:
    if form in PROXY_FORMS:
        return "activist_proxy"
    if form in ACTIVIST_13D_FORMS:
        return "activist_13d"
    if form in PASSIVE_13G_FORMS:
        blob = f"{text} {' '.join(filers)}"
        if match_firm_id(blob):
            return "registry_13g"
        if ACTIVIST_INTENT_RE.search(blob):
            return "activist_13g"
        return "passive_13g"
    return "other"


def should_index_filing(filing_class: str, *, include_passive: bool = False) -> bool:
    if filing_class in {"activist_13d", "activist_proxy", "activist_13g", "registry_13g"}:
        return True
    if filing_class == "passive_13g" and include_passive:
        return True
    return False


def should_include_in_feed(filing_class: str) -> bool:
    return filing_class in {"activist_13d", "activist_proxy", "activist_13g", "registry_13g"}


def resolve_firm(form: str, text: str, filers: list[str]) -> dict:
    blob = f"{text}\n{' '.join(filers)}"
    registry_id = match_firm_id(blob)
    primary = pick_primary_filer(filers)
    primary = re.sub(r"^[:;\s]+", "", primary).strip()

    resolution = "registry" if registry_id else ("sec_filer" if primary else "unknown")
    if registry_id:
        return {
            "firm_id": registry_id,
            "firm_name": firm_name(registry_id),
            "confidence": 0.95,
            "reporting_persons": filers,
            "filer_resolution": resolution,
        }
    if primary:
        fid = f"sec_filer:{slug_firm(primary)}"
        return {
            "firm_id": fid,
            "firm_name": primary,
            "confidence": 0.85,
            "reporting_persons": filers,
            "filer_resolution": "proxy_cover_block" if form in PROXY_FORMS else "sec_cover_page",
        }

    registry_id = match_firm_id(text)
    if registry_id:
        return {
            "firm_id": registry_id,
            "firm_name": firm_name(registry_id),
            "confidence": 0.75,
            "reporting_persons": filers,
            "filer_resolution": "body_text_registry",
        }

    return {
        "firm_id": UNRESOLVED_FIRM_ID,
        "firm_name": UNRESOLVED_FIRM_NAME,
        "confidence": 0.4,
        "reporting_persons": filers,
        "filer_resolution": "unknown",
    }


def build_activist_title(
    analysis: dict,
    form: str,
    *,
    ticker: str | None = None,
    report_date: str | None = None,
) -> str:
    firm_id = analysis.get("firm_id") or UNRESOLVED_FIRM_ID
    filers = analysis.get("reporting_persons") or []
    short = short_firm_label(firm_id, analysis.get("firm_name") or "", filers)

    if firm_id == UNRESOLVED_FIRM_ID:
        bits = [form]
        if form in PROXY_FORMS:
            bits[0] = f"{form} (proxy solicitation)"
        if ticker:
            bits.append(ticker)
        if report_date:
            bits.append(report_date)
        return " · ".join(bits)

    if form in PROXY_FORMS:
        return f"{short} — {form} (proxy solicitation)"
    return f"{short} — {form}"


def is_sec_filing_relpath(path: str | None) -> bool:
    if not path:
        return False
    filing = Path(path.replace("\\", "/"))
    for part in (filing.name, filing.parent.name):
        if part.startswith(SEC_FILING_PREFIXES):
            return True
    return False


def form_from_filing_path(path: Path | str) -> str | None:
    filing = Path(str(path).replace("\\", "/"))
    name = filing.name
    parent = filing.parent.name
    if parent.startswith("SC-13D"):
        return "SC 13D/A" if name.startswith("A_") else "SC 13D"
    if parent.startswith("SC-13G"):
        return "SC 13G/A" if name.startswith("A_") else "SC 13G"
    stem = name.split("_")[0]
    if stem.startswith(SEC_FILING_PREFIXES):
        return stem.replace("-", " ")
    return None


def analyze_sec_filing(form: str, text: str) -> dict:
    filers = [re.sub(r"^[:;\s]+", "", f).strip() for f in extract_reporting_persons(text)]
    filers = [f for f in filers if f]
    filing_class = classify_sec_filing(form, text, filers)
    firm = resolve_firm(form, text, filers)
    firm["firm_name"] = display_firm_name(firm["firm_id"], firm["firm_name"], filers)
    return {
        **firm,
        "filing_class": filing_class,
        "include_in_feed": should_include_in_feed(filing_class),
        "index_filing": should_index_filing(filing_class),
    }
