"""Parse reporting-person names and filing class from SEC 13D/13G HTML/text."""
from __future__ import annotations

import re

from activist_common import firm_name, match_firm_id

PASSIVE_13G_FORMS = frozenset({"SC 13G", "SC 13G/A"})
ACTIVIST_13D_FORMS = frozenset({"SC 13D", "SC 13D/A"})
PROXY_FORMS = frozenset({"DEFC14A", "PREC14A", "DFAN14A"})

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


def strip_html(text: str) -> str:
    text = TAG_RE.sub(" ", text or "")
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_reporting_persons(text: str, limit: int = 200_000) -> list[str]:
    raw = (text or "")[:limit]
    plain = strip_html(raw)
    names: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        name = re.sub(r"\s+", " ", name).strip(" .,-")
        name = re.sub(r"\s+\d+$", "", name)
        name = re.sub(r"^[:;\s]+", "", name)
        if not name or len(name) < 3:
            return
        low = name.lower()
        if low in seen:
            return
        if low in {
            "names of reporting persons",
            "name of reporting person",
            "i.r.s. identification no. of above persons (entities only)",
            "delaware",
            "united states",
            "new york",
            "california",
            "sec use only",
        }:
            return
        if re.fullmatch(r"[\d\-]+", name):
            return
        seen.add(low)
        names.append(name)

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
                add(part)

    if not names:
        for m in re.finditer(
            r"(?:NAMES OF REPORTING PERSONS|NAME OF REPORTING PERSON)[\s\S]{0,250}?<P[^>]*>\s*([^<]{3,120}?)\s*</P>",
            raw,
            re.I,
        ):
            add(strip_html(m.group(1)))

    return names[:5]


def slug_firm(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:80] or "unknown_filer"


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
    primary = filers[0] if filers else ""
    primary = re.sub(r"^[:;\s]+", "", primary).strip()
    if registry_id:
        return {
            "firm_id": registry_id,
            "firm_name": firm_name(registry_id),
            "confidence": 0.95,
            "reporting_persons": filers,
        }
    if primary:
        fid = f"sec_filer:{slug_firm(primary)}"
        return {
            "firm_id": fid,
            "firm_name": primary,
            "confidence": 0.85,
            "reporting_persons": filers,
        }
    return {
        "firm_id": "unknown_activist",
        "firm_name": "Unknown filer",
        "confidence": 0.4,
        "reporting_persons": filers,
    }


def analyze_sec_filing(form: str, text: str) -> dict:
    filers = extract_reporting_persons(text)
    filing_class = classify_sec_filing(form, text, filers)
    firm = resolve_firm(form, text, filers)
    return {
        **firm,
        "filing_class": filing_class,
        "include_in_feed": should_include_in_feed(filing_class),
        "index_filing": should_index_filing(filing_class),
    }
