"""Source identity, extraction and issuer relevance for the owner research library.

No broker/data-terminal clients. Documents are data, never executable instructions.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from letter_matching import SecurityMaster, match_letter
from ticker_identity import identity_match_ok

CATEGORIES = {
    "calls": "Expert calls & meetings", "letters": "Fund commentary",
    "analysis": "Research & analysis", "filings": "Filings & company materials",
    "models": "Models & data", "industry": "Industry & commodity research",
    "media": "Other relevant sources",
}
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".htm", ".html", ".xml"}
SOURCE_SUFFIXES = TEXT_SUFFIXES | {".pdf", ".epub", ".xlsx", ".xls", ".docx", ".pptx", ".mp3", ".mp4", ".m4a", ".wav"}


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def tokens(value: str) -> set[str]:
    value = "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))
    return set(re.findall(r"[a-z0-9]+", value))


def date_from(value: str) -> str | None:
    found = re.search(r"(?<!\d)((?:19|20)\d{2})[-_](\d{2})[-_](\d{2})(?!\d)", value)
    if not found:
        return None
    from datetime import date
    try:
        return date(*map(int, found.groups())).isoformat()
    except ValueError:
        return None


def category(path: str, mime: str = "") -> str:
    low = path.lower().replace("_", "-")
    if re.search(r"expert.?calls|manager.?meetings|interview|meeting-notes|tegus|third.?bridge", low):
        return "calls"
    if re.search(r"superinvestor|fund.?letters|fund.?commentar|/letters/|investor.?letter|shareholder.?letter|quarterly.?letter", low):
        return "letters"
    if re.search(r"model|valuation|kpi|companyfacts|\.xlsx?$|\.csv$|\.tsv$", low) or "spreadsheet" in mime:
        return "models"
    if re.search(r"investor-documents|sec-edgar|filing|annual.report|earnings|presentation|10-[kq]|20-f|6-k|8-k", low):
        return "filings"
    if re.search(r"podcast|video|/episodes/", low):
        return "media"
    if re.search(r"/industry/|commodity|supply.?demand|market-data|world.model", low):
        return "industry"
    return "analysis"


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag in {"p", "div", "br", "tr", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def extract(data: bytes, suffix: str) -> tuple[str, str]:
    """Extract every page/sheet. Unsupported media remain inventoried, never empty-success."""
    try:
        if suffix in {".html", ".htm"}:
            parser = PlainHTML()
            parser.feed(data.decode("utf-8", errors="replace"))
            text = "".join(parser.parts)
        elif suffix in TEXT_SUFFIXES:
            text = data.decode("utf-8-sig", errors="replace")
        elif suffix == ".pdf":
            try:
                import fitz
                with fitz.open(stream=data, filetype="pdf") as reader:
                    text = "\n\f\n".join(page.get_text() for page in reader)
            except ImportError:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(data))
                text = "\n\f\n".join(page.extract_text() or "" for page in reader.pages)
        elif suffix in {".docx", ".pptx", ".xlsx"}:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = [n for n in archive.namelist() if (n == "word/document.xml" or re.fullmatch(r"ppt/slides/slide\d+\.xml", n) or n.startswith("xl/worksheets/") and n.endswith(".xml") or n == "xl/sharedStrings.xml")]
                text = "\n".join(f"\n[{name}]\n" + " ".join(ElementTree.fromstring(archive.read(name)).itertext()) for name in sorted(names))
        elif suffix == ".xls":
            import xlrd
            book = xlrd.open_workbook(file_contents=data)
            text = "\n".join(f"[{sheet.name}]\n" + "\n".join("\t".join(map(str, sheet.row_values(i))) for i in range(sheet.nrows)) for sheet in book.sheets())
        else:
            return "", "awaiting_transcript" if suffix in {".mp3", ".mp4", ".m4a", ".wav"} else "awaiting_extraction"
        text = text.replace("\x00", "").strip()
        return text, "indexed" if text else "awaiting_extraction"
    except (Exception,):
        return "", "awaiting_extraction"


def passage(text: str, evidence: str) -> dict:
    # Retain actual text and a reproducible locator, never invent page/time offsets.
    at = text.find(evidence) if evidence else -1
    if at < 0 and evidence:
        at = text.casefold().find(evidence.casefold())
    if at < 0:
        return {"text": evidence, "locator": "Matched company passage"}
    page = text[:at].count("\f") + 1
    line = text[:at].count("\n") + 1
    before = text[max(0, at - 150):at]
    stamp = re.findall(r"\b(?:\d{1,2}:)?\d{1,2}:\d{2}\b", before)
    return {"text": evidence, "offset": at, "line": line, "page": page if "\f" in text else None,
            "timestamp": stamp[-1] if stamp else None,
            "locator": f"Page {page}" if "\f" in text else f"Line {line}"}


class Matcher:
    def __init__(self, companies: dict, master: dict | None = None, *, narrow=True):
        registry = {"holdings": companies}
        self.companies = companies
        clean_master = {}
        for ticker, row in companies.items():
            meta = dict((master or {}).get(ticker, {}))
            trusted = meta.get("validation_status") in {"manual", "validated"} or meta.get("source") in {"book", "manual"}
            aliases = list(meta.get("aliases") or []) if trusted else []
            if trusted and meta.get("name") and meta["name"] != row.get("company"):
                aliases.append(meta["name"])
            meta.update(name=row.get("company") or (meta.get("name") if trusted else ""), aliases=aliases)
            clean_master[ticker] = meta
        self.master = SecurityMaster.from_dict(clean_master, registry)
        names = {row.get("company", "").casefold(): ticker for ticker, row in companies.items() if len(row.get("company", "").split()) >= 2}
        self.names = names
        self.name_pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?!\w)", re.I) if names else None
        self.title_names = {}
        self.issuer_names = {}
        for ticker, row in companies.items():
            name = re.sub(r"(?:,?\s+(?:incorporated|corporation|limited|inc|corp|ltd|plc))\.?$", "", row.get("company", ""), flags=re.I).strip().casefold()
            if name:
                self.issuer_names.setdefault(name, []).append(ticker)
            if len(name.split()) >= 2:
                self.title_names[name] = ticker
        self.title_pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in sorted(self.title_names, key=len, reverse=True)) + r")(?!\w)", re.I) if self.title_names else None
        self.names.update(self.title_names)
        self.name_pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in sorted(self.names, key=len, reverse=True)) + r")(?!\w)", re.I) if self.names else None
        self.issuer_siblings = {t: group for group in self.issuer_names.values() for t in group}
        self.selector = None
        self.scoped = {}
        if narrow and len(companies) > 24:
            aliases = {t: [row.get("company", ""), self.master.by_ticker.get(t, {}).get("name", ""), *(self.master.by_ticker.get(t, {}).get("aliases") or [])] for t, row in companies.items()}
            skip = {"inc", "corporation", "corp", "limited", "ltd", "plc", "the", "company", "group", "holdings", "sa", "co"}
            words = {name: tokens(name) - skip for names in aliases.values() for name in names if name}
            frequency = Counter(word for group in words.values() for word in group)
            self.selector = defaultdict(set)
            for ticker, names in aliases.items():
                self.selector[ticker.casefold()].add(ticker)
                self.selector[ticker.split(".", 1)[0].casefold()].add(ticker)
                for name in names:
                    terms = words.get(name, set())
                    if terms:
                        self.selector[min(terms, key=lambda w: (frequency[w], -len(w), w))].add(ticker)

    def match(self, title: str, text: str, explicit: list[str] = ()) -> tuple[list[dict], list[dict]]:
        if self.selector is not None:
            # Choose candidate issuers in one token pass, then run the same
            # semantic/exchange checks on their complete source text. No source
            # or candidate limit is introduced for the full coverage universe.
            candidates = set(explicit)
            for word in tokens(title + " " + text):
                candidates.update(self.selector.get(word, ()))
            for ticker in tuple(candidates):
                candidates.update(self.issuer_siblings.get(ticker, ()))
            candidates.intersection_update(self.companies)
            if not candidates:
                return [], []
            key = tuple(sorted(candidates))
            if key not in self.scoped:
                if len(self.scoped) >= 128:
                    self.scoped.pop(next(iter(self.scoped)))
                self.scoped[key] = Matcher({t:self.companies[t] for t in key}, {t:self.master.by_ticker[t] for t in key}, narrow=False)
            return self.scoped[key].match(title, text, explicit)
        linked, review = {}, []
        for ticker in explicit:
            row = self.companies.get(ticker)
            if not row:
                continue
            if identity_match_ok(title, ticker, company=row.get("company"), market=row.get("market"), exchange=row.get("exchange")):
                linked[ticker] = {"ticker": ticker, "relationship": "direct", "reason": "Company-specific research collection.", "match": "issuer_collection", "passages": []}
            else:
                review.append({"ticker": ticker, "reason": "Conflicting company or exchange identity"})
        # Strong company names in original titles remain discoverable before OCR
        # or transcription completes. Bare ticker substrings never qualify here.
        for hit in self.title_pattern.finditer(title) if self.title_pattern else []:
            ticker = self.title_names[hit.group().casefold()]
            row = self.companies[ticker]
            if ticker not in linked and identity_match_ok(title, ticker, company=row.get("company"), market=row.get("market"), exchange=row.get("exchange")):
                linked[ticker] = {"ticker": ticker, "relationship": "direct", "reason": "Company named in the source title.", "match": "company_title", "passages": []}
        for hit in self.master.name_re.finditer(title) if self.master.name_re else []:
            normalized = re.sub(r"[\s\-]+", " ", hit.group()).strip().lower()
            ticker = self.master.name_alias_to_ticker.get(normalized)
            row = self.companies.get(ticker, {})
            if ticker and ticker not in linked and identity_match_ok(title, ticker, company=row.get("company"), market=row.get("market"), exchange=row.get("exchange")):
                linked[ticker] = {"ticker": ticker, "relationship": "direct", "reason": "Company named in the source title.", "match": "company_title", "passages": []}
        # A complete, registered company name is stronger than a single-token
        # alias in the legacy letter matcher (e.g. Newmont Corporation).
        for hit in self.name_pattern.finditer(text) if self.name_pattern else []:
            ticker = self.names[hit.group().casefold()]
            row = self.companies[ticker]
            name = row["company"]
            if ticker in linked:
                continue
            boundary = text.rfind("\n\n", 0, hit.start())
            start = max(boundary + 2 if boundary >= 0 else 0, hit.start() - 200)
            end = text.find("\n\n", hit.end())
            end = min(end if end >= 0 else len(text), hit.end() + 350)
            evidence = text[start:end]
            substantive = re.search(r"\b(revenue|earnings|profit|margin|growth|business|production|costs?|valuation|cash.flow|competition|pricing|operates?|products?|demand|supply|forecast|dividend|risk|capital|debt|assets?|customers?)\b", evidence, re.I)
            narrative = re.search(r"\b(is|are|was|were|has|have|earns?|operates?|grew|grown|increased|expanded|reduced|expect|believe|owns?|offers?|provides?|generates?|produces?|sells?|reported)\b", evidence, re.I)
            if len(evidence.split()) < 15 or not substantive or not narrative or not identity_match_ok(evidence, ticker, company=name, market=row.get("market"), exchange=row.get("exchange")):
                continue
            evidence = text[max(start, hit.start()-150):min(end if end >= 0 else len(text), hit.end()+350)]
            linked[ticker] = {"ticker": ticker, "relationship": "direct", "reason": f"Discusses {name}.", "match": "registered_company_name", "passages": [passage(text,evidence)]}
        # Matching uses full text, not a filename or truncated insights feed.
        # The legacy letter rules inspect surrounding sentences. Bounded, overlapping
        # windows avoid quadratic work on large, unbroken financial tables while
        # still visiting the complete document (including its last page).
        chunks = (text[i:i+16_000] for i in range(0, max(1, len(text)), 15_000))
        hits = (hit for chunk in chunks for hit in match_letter(title + "\n" + chunk, self.master))
        for hit in hits:
            ticker = hit["ticker"]
            if ticker not in self.companies or ticker in linked:
                continue
            evidence = hit.get("evidence") or ""
            identifying_rules = {"company_name", "single_token_name", "raw_company_name", "dollar", "paren_exch", "exch_prefix", "paren_num_exch", "dotted"}
            if hit.get("tier") == "C" or not identifying_rules.intersection(hit.get("rules", [])) or hit.get("in_holdings_table") or len(evidence.split()) < 12:
                review.append({"ticker": ticker, "reason": "Weak or incidental mention"})
                continue
            row = self.companies[ticker]
            if not identity_match_ok(evidence, ticker, company=row.get("company"), market=row.get("market"), exchange=row.get("exchange")):
                review.append({"ticker": ticker, "reason": "Conflicting company or exchange identity"})
                continue
            linked[ticker] = {"ticker": ticker, "relationship": "direct", "reason": f"Discusses {row.get('company') or ticker}.", "match": "verified_passage", "passages": [passage(text, evidence)]}
        for tickers in self.issuer_names.values():
            found = next((linked[t] for t in tickers if t in linked), None)
            if found:
                for ticker in tickers:
                    linked.setdefault(ticker, {**found, "ticker": ticker})
        unique_review = {(item["ticker"], item["reason"]):item for item in review}
        return list(linked.values()), list(unique_review.values())


class SourceIndex:
    """Union only verified identities: original ID/revision, exact bytes, or explicit rendition refs."""
    def __init__(self):
        self.records = {}
        self.anchors = {}
        self.record_anchors = defaultdict(set)

    def add(self, record: dict, anchors: list[str]) -> str:
        existing = sorted({self.anchors[a] for a in anchors if a in self.anchors})
        key = record["id"] if record.get("revision") else existing[0] if existing else record["id"]
        current = self.records.setdefault(key, {**record, "id": key})
        for other in [record] + [self.records.pop(k) for k in existing if k != key]:
            for field in ("locations", "relationships", "review", "origins"):
                current.setdefault(field, [])
                for item in other.get(field, []):
                    if item not in current[field]:
                        current[field].append(item)
            other_size = other.get("text_length", len(other.get("text", "")))
            rank={'indexed':6,'needs_ocr':5,'needs_transcript':5,'empty_source':4,'unsupported':3,'access_unavailable':2,'failed':1,'awaiting_extraction':0,'awaiting_transcript':0}
            current_rank=rank.get(current.get('processing_status'),0)
            other_rank=rank.get(other.get('processing_status'),0)
            if other_rank>current_rank or (other_rank==current_rank and other_size > current.get("text_length", len(current.get("text", "")))):
                for field in ("text", "text_cache"):
                    if field in other:
                        current[field] = other[field]
                    else:
                        current.pop(field, None)
                current["text_length"] = other_size
                current["processing_status"] = other["processing_status"]
            for field in ("date", "author", "period", "model_purpose", "assumptions", "source_refs", "content_hash", "content_md5", "format"):
                if not current.get(field) and other.get(field):
                    current[field] = other[field]
            # A live original identifies the revision family of its local copies.
            if other.get("revision"):
                for field in ("revision", "family", "modified_at"):
                    current[field] = other.get(field)
        for other_key in existing:
            if other_key != key:
                moved = self.record_anchors.pop(other_key, set())
                for anchor in moved:
                    self.anchors[anchor] = key
                self.record_anchors[key].update(moved)
        for anchor in anchors:
            self.anchors[anchor] = key
            self.record_anchors[key].add(anchor)
        return key


def retain_previous(current: dict[str, dict], previous: dict[str, dict], successful: set[str]) -> dict:
    """A failed corpus scan cannot erase its prior records. Successful absence is visible."""
    result = dict(current)
    families = {r.get("family") for r in current.values() if r.get("family")}
    hashes = {r["content_hash"] for r in current.values() if r.get("content_hash")}
    revisions = {(r.get("family"), r["revision"]) for r in current.values() if r.get("revision")}
    for key, old in previous.items():
        if key in result:
            continue
        if old.get("content_hash") in hashes or (old.get("revision") and (old.get("family"), old["revision"]) in revisions):
            continue
        origins = set(old.get("origins", []))
        newer = old.get("family") in families if old.get("family") else False
        state = "superseded" if newer else "removed_or_unavailable" if origins and origins <= successful else "last_known"
        result[key] = {**old, "availability": state}
    return result
