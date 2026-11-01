"""Match Expert Call filenames to registry tickers and plan Drive moves.

Nothing here deletes a file. Low-confidence names stay unmatched.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from licensed_drive_common import drive_file_url, slug

COPY_RE = re.compile(r"^(?P<stem>.*) \((?P<n>\d+)\)\.(?P<ext>docx|md|pdf)$", re.IGNORECASE)
EXT_RE = re.compile(r"\.(docx|md|pdf)$", re.IGNORECASE)
DATE_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<body>.*)$")
VIC_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<ticker>[A-Z]{1,6})\s+(?P<company>.+)\.pdf$",
    re.IGNORECASE,
)
LEGAL_SUFFIXES = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "ltd",
    "limited",
    "llc",
    "plc",
    "nv",
    "sa",
    "ag",
    "lp",
    "llp",
}
OPTIONAL_SUFFIXES = {"holdings", "holding", "group", "companies"}
COMPLETE_ENDINGS = (
    " inc",
    " inc.",
    " corp",
    " corp.",
    " corporation",
    " ltd",
    " ltd.",
    " llc",
    " plc",
    " n.v.",
    " nv",
    " group",
    " co",
    " company",
    " holdings",
)
# Markdown stubs in the 2026-10 export sit below 512 bytes. Real notes start near 1 KB.
STUB_MD_BYTES = 512
CONFIDENCE_THRESHOLD = 0.90
PREFIX_MIN = 8
TRUNCATED_NAME_LEN = 100


@dataclass
class NameMatch:
    ticker: str
    company: str
    confidence: float
    method: str


def normalize_company(name: str) -> str:
    text = (name or "").lower().replace("&amp;", " and ").replace("&", " and ")
    text = text.replace(".", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [token for token in text.split() if token]
    while tokens and tokens[0] == "the":
        tokens.pop(0)
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    while len(tokens) > 1 and tokens[-1] in OPTIONAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def split_filename(name: str) -> dict:
    base = Path(str(name or "")).name
    copy_n = None
    match = COPY_RE.match(base)
    if match:
        stem = match.group("stem")
        copy_n = int(match.group("n"))
        ext = match.group("ext").lower()
    else:
        ext_match = EXT_RE.search(base)
        ext = ext_match.group(1).lower() if ext_match else ""
        stem = base[: -len(ext) - 1] if ext else base
    return {"original_name": base, "stem": stem.strip(), "ext": ext, "copy_n": copy_n}


def pair_key(parsed: dict) -> str:
    return parsed["stem"].casefold()


def parse_subject(original_name: str, stem: str) -> dict:
    match = DATE_RE.match(stem)
    if not match:
        return {"date": "", "company": "", "topic": stem[:80], "truncated": True, "role": stem}
    date = match.group("date")
    body = match.group("body").strip()
    truncated = len(original_name) >= TRUNCATED_NAME_LEN
    if "  " in body:
        role, company = body.rsplit("  ", 1)
        company = company.strip(" .")
        if company.lower().endswith(COMPLETE_ENDINGS):
            truncated = False
    else:
        role = body
        if re.search(r"\bat\b", body, flags=re.IGNORECASE):
            company = re.split(r"\bat\b", body, flags=re.IGNORECASE)[-1].strip(" .")
        else:
            company = ""
        truncated = True
    topic = re.split(r"\bat\b", role, maxsplit=1, flags=re.IGNORECASE)[0].strip(" -")
    return {
        "date": date,
        "company": company,
        "topic": topic or "call",
        "truncated": truncated or len(company) < PREFIX_MIN,
        "role": role,
    }


def parse_vic_pdf(name: str) -> dict | None:
    match = VIC_RE.match(Path(str(name or "")).name)
    if not match:
        return None
    return {
        "date": match.group("date"),
        "ticker": match.group("ticker").upper(),
        "company": match.group("company").strip(),
    }


class CompanyMatcher:
    def __init__(
        self,
        registry: dict[str, str],
        sec_titles: dict[str, str] | None = None,
        overrides_by_company: dict[str, str] | None = None,
        overrides_by_id: dict[str, str] | None = None,
        threshold: float = CONFIDENCE_THRESHOLD,
    ) -> None:
        self.registry = registry
        self.threshold = threshold
        self.overrides_by_id = {str(key): value for key, value in (overrides_by_id or {}).items()}
        self.overrides_by_norm: dict[str, str] = {}
        for raw, ticker in (overrides_by_company or {}).items():
            if ticker in registry:
                self.overrides_by_norm[normalize_company(raw)] = ticker
                self.overrides_by_norm[raw.strip().casefold()] = ticker
        self.by_norm: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.by_first: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        seen: set[tuple[str, str]] = set()
        sources = dict(registry)
        for ticker, title in (sec_titles or {}).items():
            if ticker in registry and title:
                sources.setdefault(ticker, title)
                self._add(ticker, title, seen)
        for ticker, company in registry.items():
            self._add(ticker, company, seen)

    def _add(self, ticker: str, company: str, seen: set[tuple[str, str]]) -> None:
        norm = normalize_company(company)
        if not norm or (ticker, norm) in seen:
            return
        seen.add((ticker, norm))
        display = self.registry.get(ticker) or company
        self.by_norm[norm].append((ticker, display))
        first = norm.split()[0]
        self.by_first[first].append((norm, ticker, display))

    def match(self, company: str, *, truncated: bool, drive_id: str = "") -> NameMatch | None:
        if drive_id and drive_id in self.overrides_by_id:
            ticker = self.overrides_by_id[drive_id]
            if ticker in self.registry:
                return NameMatch(ticker, self.registry[ticker], 1.0, "override_id")
        raw = (company or "").strip()
        if not raw:
            return None
        forced = self.overrides_by_norm.get(normalize_company(raw)) or self.overrides_by_norm.get(raw.casefold())
        if forced and forced in self.registry:
            return NameMatch(forced, self.registry[forced], 1.0, "override")
        norm = normalize_company(raw)
        if not norm:
            return None
        exact = self._unique(self.by_norm.get(norm) or [])
        if exact:
            if not truncated:
                return NameMatch(exact[0], exact[1], 1.0, "exact")
            extended = [
                cand
                for cand in self.by_norm
                if cand != norm and (cand.startswith(norm + " ") or cand.startswith(norm))
            ]
            if not extended:
                return NameMatch(exact[0], exact[1], 0.97, "exact_truncated")
        if truncated:
            return self._prefix(norm)
        return self._fuzzy(norm)

    def _unique(self, rows: list[tuple[str, str]]) -> tuple[str, str] | None:
        tickers = {ticker for ticker, _display in rows}
        if len(tickers) != 1:
            return None
        ticker, display = rows[0]
        return ticker, display

    def _prefix(self, norm: str) -> NameMatch | None:
        if len(norm) < PREFIX_MIN:
            return None
        hits: list[tuple[str, str]] = []
        first = norm.split()[0]
        pool = self.by_first.get(first) or []
        for cand_norm, ticker, display in pool:
            if not (cand_norm.startswith(norm) or norm.startswith(cand_norm)):
                continue
            shorter, longer = (norm, cand_norm) if len(norm) <= len(cand_norm) else (cand_norm, norm)
            if len(shorter) < PREFIX_MIN or not longer.startswith(shorter):
                continue
            # A short fragment such as "Hong Kong" must not claim the exchange.
            if len(shorter) / len(longer) < 0.55:
                continue
            hits.append((ticker, display))
        unique = self._unique(hits)
        if not unique:
            return None
        return NameMatch(unique[0], unique[1], 0.92, "prefix")

    def _fuzzy(self, norm: str) -> NameMatch | None:
        first = norm.split()[0]
        pool = self.by_first.get(first) or []
        scored: list[tuple[float, str, str]] = []
        for cand_norm, ticker, display in pool:
            ratio = SequenceMatcher(None, norm, cand_norm).ratio()
            scored.append((ratio, ticker, display))
        if not scored:
            return None
        scored.sort(key=lambda row: (-row[0], row[1]))
        best_ratio, best_ticker, best_display = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        tied = {ticker for ratio, ticker, _display in scored if abs(ratio - best_ratio) < 0.001}
        if len(tied) != 1:
            return None
        if best_ratio >= self.threshold and best_ratio - second >= 0.03:
            return NameMatch(best_ticker, best_display, round(best_ratio, 4), "fuzzy")
        return None


def proposed_filename(date: str, ticker: str, company: str, topic: str, ext: str) -> str:
    return f"{date or 'undated'}_{ticker}_{slug(company, 32)}_{slug(topic, 36)}.{ext or 'md'}"


def _record(raw: dict) -> dict:
    name = raw.get("name") or raw.get("Name") or raw.get("original_name") or ""
    parsed = split_filename(name)
    size = raw.get("size", raw.get("Size", 0)) or 0
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 0
    file_id = str(raw.get("id") or raw.get("ID") or "")
    subject = parse_subject(parsed["original_name"], parsed["stem"])
    return {
        **parsed,
        "size": size,
        "drive_file_id": file_id,
        "drive_url": drive_file_url(file_id, raw.get("webViewLink") or raw.get("drive_url")),
        "parents": raw.get("parents") or [],
        "parent_name": raw.get("parent_name") or "",
        **subject,
    }


def plan_expert_calls(
    raw_rows: list[dict],
    matcher: CompanyMatcher,
    *,
    root_name: str = "Expert Calls",
    threshold: float = CONFIDENCE_THRESHOLD,
) -> list[dict]:
    """Classify a flat or already-foldered Expert Calls listing.

    Files whose parent is already a subfolder are left alone. New uploads
    sit in the Expert Calls root and are planned the same way.
    """
    records = [_record(row) for row in raw_rows]
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[pair_key(record)].append(record)

    plans: list[dict] = []
    for group in groups.values():
        rooted = []
        for record in group:
            parent = record["parent_name"]
            if parent and parent not in {root_name, ""}:
                plans.append(_plan_row(record, bucket="already_filed", dest=f"{root_name}/{parent}", reason="already_in_subfolder"))
            else:
                rooted.append(record)
        if not rooted:
            continue
        copies = [row for row in rooted if row["copy_n"] is not None]
        bases = [row for row in rooted if row["copy_n"] is None]
        if copies and bases:
            for copy in copies:
                plans.append(_plan_row(copy, bucket="duplicate", dest=f"{root_name}/_Duplicates", reason="copy_suffix"))
        elif copies and not bases:
            bases = copies
        pdfs = [row for row in bases if row["ext"] == "pdf"]
        rest = [row for row in bases if row["ext"] != "pdf"]
        unexpected = [row for row in rest if row["ext"] not in {"md", "docx", ""}]
        rest = [row for row in rest if row["ext"] in {"md", "docx"}]
        for row in unexpected:
            plans.append(
                _plan_row(row, bucket="duplicate", dest=f"{root_name}/_Duplicates", reason="unexpected_extension")
            )
        for pdf in pdfs:
            vic = parse_vic_pdf(pdf["original_name"])
            if vic:
                ticker = vic["ticker"]
                plans.append(
                    _plan_row(
                        pdf,
                        bucket="misfiled_vic",
                        dest=f"Admin/Intake/VIC/{ticker}",
                        reason="misfiled_vic_writeup",
                        ticker=ticker,
                        company=vic["company"],
                    )
                )
            else:
                plans.append(_plan_row(pdf, bucket="unmatched", dest=f"{root_name}/_Unmatched", reason="pdf_not_a_call"))
        if not rest:
            continue
        md_rows = [row for row in rest if row["ext"] == "md"]
        stub = bool(md_rows) and all(row["size"] < STUB_MD_BYTES for row in md_rows)
        if stub:
            for row in rest:
                plans.append(_plan_row(row, bucket="duplicate", dest=f"{root_name}/_Duplicates", reason="empty_or_stub"))
            continue
        exts = {row["ext"] for row in rest if row["ext"] in {"md", "docx"}}
        if exts and exts != {"md", "docx"}:
            for row in rest:
                plans.append(_plan_row(row, bucket="duplicate", dest=f"{root_name}/_Duplicates", reason="orphan_copy"))
            continue
        sample = next((row for row in rest if row["ext"] == "md"), rest[0])
        found = matcher.match(sample["company"], truncated=bool(sample["truncated"]), drive_id=sample["drive_file_id"])
        if found and found.confidence >= threshold:
            dest = f"{root_name}/{found.ticker}"
            new_name_md = proposed_filename(sample["date"], found.ticker, found.company, sample["topic"], "md")
            for row in rest:
                new_name = proposed_filename(sample["date"], found.ticker, found.company, sample["topic"], row["ext"])
                if row["ext"] == "md":
                    new_name = new_name_md
                plans.append(
                    _plan_row(
                        row,
                        bucket="ticker",
                        dest=dest,
                        reason=found.method,
                        ticker=found.ticker,
                        company=found.company,
                        confidence=found.confidence,
                        new_name=new_name,
                    )
                )
        else:
            for row in rest:
                plans.append(
                    _plan_row(
                        row,
                        bucket="unmatched",
                        dest=f"{root_name}/_Unmatched",
                        reason="low_confidence" if sample["company"] else "company_not_parsed",
                        company=sample["company"],
                        confidence=found.confidence if found else 0.0,
                        ticker=found.ticker if found else "",
                    )
                )
    _assign_unique_names(plans)
    return plans


def _assign_unique_names(plans: list[dict]) -> None:
    """Keep a clean name from colliding with another file in the same folder."""
    used: set[tuple[str, str]] = set()
    for row in plans:
        if row["bucket"] == "already_filed":
            used.add((row["dest_folder"], str(row["new_name"]).casefold()))
    for row in plans:
        if row["bucket"] != "ticker":
            continue
        name = str(row["new_name"])
        key = (row["dest_folder"], name.casefold())
        if key not in used:
            used.add(key)
            continue
        stem, dot, ext = name.rpartition(".")
        suffix = (row.get("file_id") or "copy")[:8]
        renamed = f"{stem}_{suffix}.{ext}" if dot else f"{name}_{suffix}"
        row["new_name"] = renamed
        if "name_collision" not in row["reason"]:
            row["reason"] = f"{row['reason']}+name_collision"
        used.add((row["dest_folder"], renamed.casefold()))


def _plan_row(
    record: dict,
    *,
    bucket: str,
    dest: str,
    reason: str,
    ticker: str = "",
    company: str = "",
    confidence: float = 0.0,
    new_name: str = "",
) -> dict:
    return {
        "file_id": record["drive_file_id"],
        "original_name": record["original_name"],
        "size_bytes": record["size"],
        "extension": record["ext"],
        "bucket": bucket,
        "dest_folder": dest,
        "new_name": new_name or record["original_name"],
        "ticker": ticker,
        "company": company,
        "date": record.get("date") or "",
        "confidence": confidence,
        "reason": reason,
        "drive_url": record.get("drive_url") or "",
        "truncated": bool(record.get("truncated")),
        "parsed_company": record.get("company") or "",
        "source_parents": list(record.get("parents") or []),
    }


def summarize_plan(plans: list[dict]) -> dict:
    buckets: dict[str, int] = defaultdict(int)
    tickers = set()
    for row in plans:
        buckets[row["bucket"]] += 1
        if row["bucket"] == "ticker" and row.get("ticker"):
            tickers.add(row["ticker"])
    return {
        "files": len(plans),
        "ticker_files": buckets.get("ticker", 0),
        "unmatched_files": buckets.get("unmatched", 0),
        "duplicate_files": buckets.get("duplicate", 0),
        "misfiled_vic_files": buckets.get("misfiled_vic", 0),
        "already_filed_files": buckets.get("already_filed", 0),
        "ticker_folders": len(tickers),
    }
