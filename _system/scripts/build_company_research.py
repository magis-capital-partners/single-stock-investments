#!/usr/bin/env python3
"""Build complete, private company source libraries; never uses brokerage services.

Outputs belong under _private until copied into the authenticated Pages artifact.
No summaries/Insights caps are used as inventory boundaries.
"""
from __future__ import annotations

import argparse
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import quote

from company_sources import CATEGORIES, SOURCE_SUFFIXES, Matcher, SourceIndex, category, date_from, digest, extract, retain_previous, tokens

ROOT = Path(__file__).resolve().parents[2]
VAULT_COLLECTIONS = ("superinvestor-letters", "vic-research", "sumzero-research", "investment-wisdom", "manager-meetings", "expert-calls", "expert_calls", "valueline", "podcasts", "videos", "dropbox-ingestion", "short-research", "activist-research", "filings-extracts")
IGNORE_NAMES = {"README.md", "AGENTS.md", "SKILL.md", "INDEX.csv", "manifest.json", "catalog_manifest.jsonl", "DOWNLOAD_MANIFEST.json",
                "insights.json", "letters_index.json", "drive_import_manifest.json", "drive_import_log.jsonl", "fetch_log.jsonl",
                "duplicate_audit.json", "funds_unresolved.json", "funds.json", "manifest.csv", "sources.json"}
SKIP_PARTS = {".git", "_eval", "tests", "__pycache__", "node_modules", "dashboard-private", "sec-edgar"}
SHARED_MODELS = {
    "dashboard/data/energy_model.json": "Natural gas supply and demand model",
    "dashboard/data/energy_btc_bridge.json": "Natural gas and Bitcoin mining sensitivity model",
    "_system/scripts/energy_model_config.json": "Natural gas model assumptions and reference forecast",
    "_system/scripts/btc_cost_of_production.py": "Bitcoin cost-of-production methodology",
    "_system/scripts/energy_btc_bridge.py": "Natural gas and Bitcoin mining model methodology",
    "_system/scripts/power_cost_model.py": "Electricity contract cost model methodology",
}


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == body:
        return
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(body, encoding="utf-8")
    temp.replace(path)


def load(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else ({} if default is None else default)


def write_mapping(root: Path, folder: str, values: dict) -> list[str]:
    """Stable private cache shards also stay below GitHub's individual blob limit."""
    groups = defaultdict(dict)
    for key, value in values.items():
        groups[digest(key)[:2]][key] = value
    files = []
    for prefix, group in sorted(groups.items()):
        relative = f"{folder}/{prefix}.json"
        write(root / relative, group)
        files.append(relative)
    return files


def resolved(root: Path, relative: str):
    """Read private snapshots without hydrating or overwriting the user's files."""
    from private_dashboard_assets import private_source
    path = root / relative
    if not path.is_file():
        return None
    manifest = load(root / "dashboard/private-assets.json")
    entries = manifest.get("assets", {}) if relative.startswith("dashboard/") else manifest.get("repository_assets", {})
    key = relative.removeprefix("dashboard/") if relative.startswith("dashboard/") else relative
    base = root / "dashboard" if relative.startswith("dashboard/") else root
    if key in entries:
        path = private_source(base, key, {"assets": entries})
    return path


def document(root: Path, relative: str):
    path = resolved(root, relative)
    result = load(path) if path else {}
    if isinstance(result, dict) and result.get("private_snapshot"):
        raise RuntimeError(f"Unresolved private input: {relative}")
    return result


def url_anchor(url: str) -> str:
    match = re.search(r"(?:drive\.google\.com/file/d/|docs\.google\.com/(?:document|spreadsheets|presentation)/d/)([A-Za-z0-9_-]+)", url)
    return "drive:" + match[1] if match else "url:" + url


def safe_files(directory: Path):
    if not directory.is_dir():
        return
    for folder, subdirs, names in os.walk(directory):
        subdirs[:] = sorted(d for d in subdirs if d not in SKIP_PARTS and not d.startswith("."))
        for name in sorted(names):
            path = Path(folder) / name
            if path.suffix.lower() in SOURCE_SUFFIXES and name not in IGNORE_NAMES and not name.endswith(".meta.json"):
                yield path


def read_companies(root: Path) -> dict:
    registry = document(root, "_system/portfolio/registry.json")
    companies = {str(t).upper(): row for book in ("watchlist", "holdings") for t, row in (registry.get(book) or {}).items()}
    core = document(root, "dashboard/data/core.json")
    for row in core.get("tickers", []):
        if row.get("ticker"):
            companies[row["ticker"]] = {**companies.get(row["ticker"], {}), **{k: row[k] for k in ("company", "market", "exchange", "display_ticker") if row.get(k)}}
    if not companies:
        raise RuntimeError("No company universe; refusing to publish an empty library")
    return companies


class Builder:
    def __init__(self, root: Path, vault: Path | None, output: Path, cache: Path, *, companies=None):
        self.root, self.vault, self.output, self.cache = root, vault, output, cache
        self.companies = companies if companies is not None else read_companies(root)
        master = document(root, "_system/reference/securities/security_master.json") if companies is None else {}
        master = master.get("securities", master)
        self.matcher = Matcher(self.companies, {t:master.get(t,{}) for t in self.companies})
        self.index = SourceIndex()
        self.receipts = []
        self.good = set()
        self.refs = defaultdict(list)
        self.metadata = {}
        self.file_failures = Counter()
        self.now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.previous = load(cache / "index.json")
        if self.previous.get("record_parts"):
            self.previous["records"] = {}
            for part in self.previous["record_parts"]:
                self.previous["records"].update(load(cache / part))
        self.previous_versions = {(r.get("family"), r.get("revision")):r for r in self.previous.get("records", {}).values() if r.get("revision")}
        self.themes = load(Path(__file__).with_name("company_research_themes.json"), [])
        # Consume the maintained business-driver map, with explicit issuer lists
        # and rationale. Portfolio-wide wildcards and the legacy unreviewed
        # linkage graph are deliberately ineligible as company sources.
        curated = document(root, "_system/portfolio/holdings_themes.json").get("themes", {})
        for theme_id, theme in curated.items():
            tickers = [t for t in theme.get("tickers", []) if t != "*" and t in self.companies]
            if tickers and theme.get("rationale"):
                patterns = [re.escape(theme_id).replace("_", "[ _-]")]
                for node in (root / "_system/reference/industry").glob("*.json"):
                    if theme_id in load(node).get("linked_theme_ids", []):
                        patterns.append(re.escape(node.stem).replace("_", "[ _-]"))
                self.themes.append({"id": theme_id, "patterns": patterns, "tickers": tickers, "reason": theme["rationale"]})
        self.seen = set()
        identities = {t:{k:r.get(k) for k in ("company", "market", "exchange")} for t,r in self.companies.items()}
        self.match_version = digest(json.dumps(identities, sort_keys=True) + json.dumps(master, sort_keys=True) + digest(Path(__file__).with_name("company_sources.py").read_bytes()))
        match_manifest = load(cache / "matches.json")
        self.matches = {}
        if match_manifest.get("version") == self.match_version:
            for part in match_manifest.get("parts", []):
                self.matches.update(load(cache / part))

    def receipt(self, name, count, status="complete", detail=None):
        if self.file_failures[name]:
            status, detail = "partial", f"{self.file_failures[name]} originals could not be read; discovery continued"
        self.receipts.append({"collection": name, "discovered": count, "status": status, "checked_at": self.now, "detail": detail})
        if status == "complete":
            self.good.add(name)
        print(f"Research inventory: {name}: {count} files ({status})", flush=True)

    def add(self, record, anchors):
        # Keep source bodies on disk. A full coverage run can contain many GB
        # of filings; only the document currently being processed is resident.
        body = record.pop("text", "")
        record["text_length"] = len(body)
        if body:
            sha = digest(body)
            path = self.cache / "published-text" / (sha + ".json")
            if not path.is_file():
                write(path, {"text": body})
            record["text_cache"] = sha
        return self.index.add(record, anchors)

    def text(self, record):
        if "text" in record:
            return record["text"]
        if record.get("text_cache"):
            return load(self.cache / "published-text" / (record["text_cache"] + ".json")).get("text", "")
        return ""

    def source_words(self, record):
        if not record.get("text_cache") and not record.get("text"):
            return []
        key = record.get("text_cache") or digest(record.get("text", ""))
        path = self.cache / "words" / (key + ".json")
        if path.is_file():
            return load(path, [])
        words = sorted(tokens(self.text(record)))
        write(path, words)
        return words

    def base(self, identity, title, origin, *, text="", state="indexed", date=None, author=None, period=None, explicit=(), locations=(), mime="", path=""):
        match_text = text
        if explicit and Path(path).suffix.lower() in {".json", ".csv", ".tsv"}:
            # Company-owned tables already have issuer identity. Discover other
            # issuers only in narrative fields, never among numeric observations
            # or schema keys. The full original remains indexed for search.
            narratives = []
            if Path(path).suffix.lower() == ".json":
                try:
                    pending = [json.loads(text)]
                    while pending:
                        value = pending.pop()
                        if isinstance(value, dict):
                            pending.extend(value.values())
                        elif isinstance(value, list):
                            pending.extend(value)
                        elif isinstance(value, str) and len(value) >= 80 and len(value.split()) >= 15:
                            narratives.append(value)
                except ValueError:
                    pass
            match_text = "\n\n".join(narratives)
        # A Drive filename and its vault rendition often differ only by the
        # extension. Reuse issuer matching for their identical complete text;
        # original titles and locations remain distinct source metadata.
        suffix = Path(title).suffix.lower()
        match_title = title[:-len(suffix)] if suffix in SOURCE_SUFFIXES else title
        match_key = digest(self.match_version + match_title + digest(match_text) + json.dumps(list(explicit)))
        if match_key not in self.matches:
            self.matches[match_key] = self.matcher.match(match_title, match_text, explicit)
        links, review = self.matches[match_key]
        record = {"id": digest(identity)[:32], "title": title, "category": category(path or title, mime), "date": date or date_from(title), "author": author or "", "period": period,
                  "origins": [origin], "locations": list(locations), "text": text, "processing_status": state,
                  "relationships": list(links), "review": list(review), "availability": "available", "indexed_at": self.now,
                  "family": digest(re.sub(r"(?:19|20)\d{2}[-_]\d{2}[-_]\d{2}", "", path or identity))[:24]}
        for theme in self.themes:
            # Title/path signals must be about the subject itself; no blanket macro wildcard.
            matched = not explicit and any(re.search(pattern, path or title, re.I) for pattern in theme.get("patterns", []))
            if not matched:
                continue
            for ticker in theme["tickers"]:
                if ticker not in self.companies or any(r["ticker"] == ticker for r in record["relationships"]):
                    continue
                record["relationships"].append({"ticker": ticker, "relationship": "industry_context", "reason": theme["reason"], "match": "reviewed_business_driver", "passages": [], "theme": theme["id"]})
            if record["category"] not in {"models", "calls", "letters", "media"}:
                record["category"] = "industry"
        return record

    def cached_extract(self, data, suffix):
        sha = digest(data)
        path = self.cache / "text" / f"{sha}.json"
        prior = load(path)
        if prior.get("version") == 1 and prior.get("status") == "indexed":
            return prior["text"], prior["status"], sha
        text, state = extract(data, suffix)
        write(path, {"version": 1, "text": text, "status": state})
        return text, state, sha

    def local(self, path: Path, origin: str, *, explicit=(), relative=None):
        try:
            return self._local(path, origin, explicit=explicit, relative=relative)
        except (OSError, ValueError, RuntimeError):
            self.file_failures[origin] += 1
            rel = relative or path.relative_to(self.root).as_posix()
            record = self.base("unreadable:" + rel, path.stem, origin, explicit=explicit, path=rel, state="awaiting_extraction")
            record["availability"] = "unavailable"
            self.add(record, ["path:" + rel])

    def _local(self, path: Path, origin: str, *, explicit=(), relative=None):
        rel = relative or path.relative_to(self.root).as_posix()
        logical = "_system/reference/" + rel.removeprefix("vault/") if rel.startswith("vault/") else rel
        actual = resolved(self.root, rel) if not rel.startswith("vault/") else path
        if actual is None:
            return
        data = actual.read_bytes()
        companion = next((path.with_suffix(s) for s in (".txt", ".md") if path.suffix.lower() == ".pdf" and path.with_suffix(s).is_file()), None)
        if companion:
            text, state, _ = self.cached_extract(companion.read_bytes(), companion.suffix.lower())
            sha = digest(data)
        else:
            text, state, sha = self.cached_extract(data, ".txt" if rel in SHARED_MODELS and path.suffix == ".py" else path.suffix.lower())
        # Metadata-only placeholders are not evidence and never become "zero sources".
        if '"private_snapshot":true' in text.replace(" ", ""):
            raise RuntimeError(f"Unresolved private snapshot: {rel}")
        meta_path = path.with_suffix(".meta.json")
        meta = load(meta_path)
        md = self.metadata.get(logical, {})
        title = meta.get("title") or md.get("title") or path.stem.replace("_", " ")
        repo = "research-vault" if rel.startswith("vault/") else "single-stock-investments"
        repository_path = rel.removeprefix("vault/")
        if actual != path and self.vault and actual.is_relative_to(self.vault):
            repo, repository_path = "research-vault", actual.relative_to(self.vault).as_posix()
        locations = [{"kind": "vault" if repo == "research-vault" else "repository", "url": f"https://github.com/magis-capital-partners/{repo}/blob/main/{quote(repository_path, safe='/')}", "label": "Vault original" if repo == "research-vault" else "Research original"}]
        for loc in self.refs[logical]:
            if loc not in locations:
                locations.insert(0, loc)
        record = self.base("sha256:" + sha, title, origin, text=text, state=state, date=meta.get("published") or md.get("date"), author=meta.get("show_title") or md.get("author"), period=meta.get("period") or md.get("period"), explicit=explicit, locations=locations, path=rel)
        record["content_hash"] = sha
        record["content_md5"] = hashlib.md5(data, usedforsecurity=False).hexdigest()
        record["format"] = path.suffix.lstrip(".")
        if rel in SHARED_MODELS:
            record["category"] = "models"
        if path.suffix.lower() == ".json":
            try:
                body = json.loads(text)
                if isinstance(body, dict):
                    record["date"] = body.get("as_of") or body.get("model_as_of") or record["date"]
                    record["model_purpose"] = body.get("description") or body.get("purpose")
                    record["assumptions"] = body.get("assumptions")
                    record["source_refs"] = body.get("sources") or body.get("source_refs") or ([body["reference"]] if body.get("reference") else None)
            except ValueError:
                pass
        rendition = str(Path(logical).with_suffix(""))
        anchors = ["sha:" + sha, "path:" + logical]
        anchors.append("md5:" + hashlib.md5(data, usedforsecurity=False).hexdigest())
        # Adjacent PDF/text versions are explicit original/extract companions, not filename guesses across folders.
        if path.suffix.lower() in {".pdf", ".txt", ".md"}:
            anchors.append("rendition:" + rendition)
        anchors.extend(url_anchor(loc["url"]) for loc in locations if loc["kind"] == "drive")
        self.add(record, anchors)

    def registries(self):
        for relative in ("dashboard/data/document_registry.json", "dashboard/data/document_catalog.json"):
            try:
                doc = document(self.root, relative)
                rows = doc.get("documents", [])
                for row in rows:
                    ref = row.get("local_pdf_path") or row.get("path") or row.get("local_path") or ""
                    url = row.get("drive_web_view_link") or row.get("drive_url") or row.get("webViewLink")
                    ticker = row.get("ticker")
                    if not ticker and ref.split("/")[0] in self.companies:
                        ticker = ref.split("/")[0]
                    loc = [{"kind": "drive", "url": url, "label": "Open original"}] if url else []
                    if ref:
                        self.refs[ref].extend(loc)
                        self.metadata[ref] = row
                    title = row.get("title") or row.get("filename") or Path(ref).stem or "Research document"
                    identity = row.get("sha256") or row.get("doc_id") or url or ref
                    if not identity:
                        continue
                    record = self.base(str(identity), title, relative, state="awaiting_extraction", date=row.get("document_date") or row.get("date"), explicit=[ticker] if ticker else [], locations=loc, path=ref)
                    anchors = (["path:" + ref] if ref else []) + ([url_anchor(url)] if url else [])
                    if row.get("sha256"):
                        anchors.append("sha:" + row["sha256"].removeprefix("sha256:"))
                    self.add(record, anchors)
                self.receipt(relative, len(rows), "complete" if doc else "unavailable")
            except Exception as exc:
                self.receipt(relative, 0, "failed", type(exc).__name__)

    def local_corpora(self):
        if self.vault:
            try:
                for row in load(self.vault / "superinvestor-letters/letters_index.json", []):
                    for field in ("source_file", "source_document"):
                        if row.get(field):
                            self.metadata[row[field]] = {**self.metadata.get(row[field], {}), "author": row.get("fund") or row.get("manager"), "date": row.get("letter_date"), "period": row.get("quarter")}
            except (OSError, ValueError, TypeError):
                self.receipt("vault:letter_metadata", 0, "failed", "Fund names and dates could not be read")
        for ticker in sorted(self.companies):
            name = "company:" + ticker
            count = 0
            try:
                base = self.root / ticker
                self.filings(ticker)
                self.company_inventory(ticker)
                for folder in ("research", "third-party-analyses", "investor-documents", "transcripts", "models", "financials"):
                    for path in safe_files(base / folder):
                        if re.search(r"(?:source_inventory|activist_reports_index|latest|security_identity|classification|human_decision|download|readiness|audit|forecast_market_sync|committee_packet)", path.stem, re.I):
                            continue
                        self.local(path, name, explicit=[ticker])
                        count += 1
                self.receipt(name, count, "complete" if base.exists() else "unavailable", None if base.exists() else "Company files absent from this checkout")
            except Exception as exc:
                self.receipt(name, count, "failed", type(exc).__name__)
        if not self.vault:
            self.receipt("vault", 0, "unavailable", "Private vault not mounted")
            return
        for collection in VAULT_COLLECTIONS:
            folder = self.vault / collection
            if not folder.is_dir():
                continue
            count = 0
            try:
                for path in safe_files(folder):
                    rel = path.relative_to(self.vault).as_posix()
                    explicit = [p for p in path.relative_to(folder).parts[:-1] if p in self.companies]
                    self.local(path, "vault:" + collection, explicit=explicit, relative="vault/" + rel)
                    count += 1
                self.receipt("vault:" + collection, count)
            except Exception as exc:
                self.receipt("vault:" + collection, count, "failed", type(exc).__name__)
        for collection in ("industry", "world_model", "market-data", "energy", "kpi"):
            folder = self.root / "_system/reference" / collection
            count = 0
            try:
                for path in safe_files(folder):
                    self.local(path, "shared:" + collection)
                    count += 1
                self.receipt("shared:" + collection, count, "complete" if folder.exists() else "unavailable")
            except Exception as exc:
                self.receipt("shared:" + collection, count, "failed", type(exc).__name__)
        self.shared_models()

    def shared_models(self):
        count = 0
        for relative, title in SHARED_MODELS.items():
            if not (self.root / relative).is_file():
                continue
            self.metadata[relative] = {"title": title, "author": "Internal research"}
            self.local(self.root / relative, "shared:models")
            count += 1
        self.receipt("shared:models", count)

    def git_inventory(self, extraction_budget=300):
        """A sparse deploy still inventories historical company originals from the Git tree.

        Missing file bytes are honestly marked awaiting extraction, never hidden.
        Live local files take precedence; Git IDs also detect renames and copies.
        """
        result = subprocess.run(["git", "ls-tree", "-r", "-z", "HEAD"], cwd=self.root, capture_output=True, check=True)
        count = 0
        started = time.monotonic()
        for entry in result.stdout.decode("utf-8").split("\0"):
            if not entry or "\t" not in entry:
                continue
            header, rel = entry.split("\t", 1)
            parts = rel.split("/")
            if len(parts) < 3 or parts[0] not in self.companies or parts[1] not in {"research", "third-party-analyses", "investor-documents", "models", "transcripts", "financials"}:
                continue
            path = Path(rel)
            if path.suffix.lower() not in SOURCE_SUFFIXES or path.name in IGNORE_NAMES:
                continue
            if "sec-edgar" in parts and path.suffix.lower() not in {".htm", ".html", ".txt", ".pdf"}:
                continue
            if re.search(r"(?:source_inventory|activist_reports_index|latest|security_identity|classification|human_decision|download|readiness|audit|committee_packet)", path.stem, re.I):
                continue
            count += 1
            existing = self.index.records.get(self.index.anchors.get("path:" + rel), {})
            if existing.get("processing_status") == "indexed":
                continue
            sha = header.split()[-1]
            url = f"https://github.com/magis-capital-partners/single-stock-investments/blob/main/{quote(rel,safe='/')}"
            cached_path = self.cache / "git" / (sha + ".json")
            cached = load(cached_path)
            if not cached and time.monotonic() - started < extraction_budget:
                try:
                    local_path = self.root / rel
                    blob = local_path.read_bytes() if local_path.is_file() else subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=self.root, capture_output=True, check=True, timeout=25).stdout
                    body, status, _ = self.cached_extract(blob, path.suffix.lower())
                    if '"private_snapshot":true' not in body.replace(" ", ""):
                        cached = {"text": body, "status": status}
                        write(cached_path, cached)
                except (subprocess.SubprocessError, OSError):
                    pass
            locations = [{"kind":"repository","url":url,"label":"Research original"}]
            locations = self.refs.get(rel) or locations
            record = self.base("git:"+sha,path.stem.replace("_"," "),"git_inventory",text=cached.get("text", ""),explicit=[parts[0]],state=cached.get("status", "awaiting_extraction"),locations=locations,path=rel)
            self.add(record,["git:"+sha,"path:"+rel])
        self.receipt("git_inventory",count)

    def filings(self, ticker):
        path = self.root / ticker / "investor-documents/DOWNLOAD_MANIFEST.json"
        doc = load(path)
        def rows(value):
            if isinstance(value, list):
                for x in value:
                    yield from rows(x)
            elif isinstance(value, dict):
                url = value.get("url") or value.get("source_url") or value.get("sec_url")
                if url and re.match(r"https?://", str(url)):
                    yield value, url
                else:
                    for x in value.values():
                        if isinstance(x, (dict, list)):
                            yield from rows(x)
        for row, url in rows(doc):
            filed = row.get("filing_date") or row.get("filingDate") or row.get("date")
            title = " · ".join(str(v) for v in [row.get("form") or row.get("type"), filed, row.get("primary_document") or row.get("primary")] if v) or Path(url).name
            location = {"kind": "filing", "url": url, "label": "Official filing"}
            rec = self.base(url, title, "company:" + ticker, state="awaiting_extraction", explicit=[ticker], date=filed, period=row.get("report"), locations=[location], path="filings/" + title)
            ref = row.get("local") or row.get("local_path")
            if ref:
                self.refs[ref].append(location)
                self.metadata[ref] = {"title": title, "date": filed}
            self.add(rec, ["url:" + url] + (["path:" + ref] if ref else []))

    def company_inventory(self, ticker):
        relative = f"{ticker}/third-party-analyses/source_inventory.json"
        doc = document(self.root, relative)
        for row in doc.get("sources", []):
            ref = row.get("path") or row.get("source_ref")
            url = row.get("url") or row.get("source_url") or row.get("drive_url")
            if not ref and not url:
                continue
            locations = [{"kind": "source", "url": url, "label": "Original source"}] if url else []
            if ref:
                self.refs[ref].extend(locations)
            rec = self.base(url or ref, row.get("title") or Path(ref or url).stem, "company:"+ticker, state="awaiting_extraction", date=row.get("date"), author=row.get("author"), explicit=[ticker] if row.get("status") in {"approved", "context", "verified"} else [], locations=locations, path=ref or url)
            self.add(rec, (["path:"+ref] if ref else []) + (["url:"+url] if url else []))

    def drive(self, service=None, roots=None, download=False, download_budget=300):
        """Enumerate all pages and all formats under configured research roots, including licensed folders."""
        from drive_store_common import drive_service, configured_root_ids, execute_with_retry, build_folder_paths, FOLDER_MIME
        if service is None:
            service = drive_service(readonly=True)
        # Bound a stalled transport as well as the batch's extraction budget.
        http = getattr(service, "_http", None)
        transport = getattr(http, "http", http)
        if transport is not None and hasattr(transport, "timeout"):
            transport.timeout = 30
        if roots is None:
            roots = configured_root_ids(document(self.root, "_system/reference/document-store/google_drive_config.json"))
        if not roots:
            raise RuntimeError("No configured Drive research roots")
        items, seen, queue = {}, set(), []
        drives = set()
        for root in roots:
            meta = execute_with_retry(service.files().get(fileId=root, fields="id,name,driveId,parents", supportsAllDrives=True))
            if meta.get("driveId") and not meta.get("parents"):
                drives.add(meta["driveId"])
            else:
                queue.append(root)
        fields = "nextPageToken,files(id,name,mimeType,parents,webViewLink,modifiedTime,md5Checksum,size,appProperties,shortcutDetails)"
        for drive_id in drives:
            token = None
            while True:
                response = execute_with_retry(service.files().list(corpora="drive",driveId=drive_id,q="trashed = false",pageSize=1000,pageToken=token,supportsAllDrives=True,includeItemsFromAllDrives=True,fields=fields))
                items.update({item["id"]: item for item in response.get("files",[])})
                token = response.get("nextPageToken")
                if not token:
                    break
        while queue:
            parent = queue.pop(0)
            if parent in seen:
                continue
            seen.add(parent)
            token = None
            while True:
                response = execute_with_retry(service.files().list(q=f"'{parent}' in parents and trashed = false", pageSize=1000, pageToken=token, supportsAllDrives=True, includeItemsFromAllDrives=True,
                    fields=fields))
                for item in response.get("files", []):
                    items[item["id"]] = item
                    if item["mimeType"] == FOLDER_MIME:
                        queue.append(item["id"])
                token = response.get("nextPageToken")
                if not token:
                    break
        paths = build_folder_paths(list(items.values()), roots)
        download_start = time.monotonic()
        count = 0
        attempted = {p.stem for p in (self.cache / "drive").glob("*.json")}
        def priority(item):
            revision = item.get("md5Checksum") or item.get("modifiedTime") or "unknown"
            return digest(item["id"] + revision) not in attempted, item.get("modifiedTime", ""), item["id"]
        for item in sorted(items.values(), key=priority, reverse=True):
            if item["mimeType"] == FOLDER_MIME:
                continue
            count += 1
            name = item["name"]
            parent = "/".join(paths.get(p, "") for p in item.get("parents", []))
            full = parent + "/" + name
            explicit = [p for p in parent.split("/") if p in self.companies]
            props = item.get("appProperties") or {}
            if props.get("ticker") in self.companies:
                explicit.append(props["ticker"])
            url = item.get("webViewLink") or f"https://drive.google.com/file/d/{item['id']}/view"
            existing = self.index.anchors.get(url_anchor(url)) or self.index.anchors.get("md5:" + str(item.get("md5Checksum")))
            old = self.index.records.get(existing, {})
            revision = item.get("md5Checksum") or item.get("modifiedTime") or "unknown"
            changed = (old.get("content_md5") and item.get("md5Checksum") and old["content_md5"] != item["md5Checksum"]) or (old.get("revision") and old["revision"] != revision)
            if changed:
                old["family"] = "drive:" + item["id"]
                old["availability"] = "superseded"
                self.index.anchors.pop(url_anchor(url), None)
                old = {}
            text, state = self.text(old), old.get("processing_status", "awaiting_extraction")
            prior = self.previous_versions.get(("drive:" + item["id"], revision), {})
            if not text and prior.get("text_cache"):
                text, state = self.text(prior), prior["processing_status"]
            cachefile = self.cache / "drive" / f"{digest(item['id'] + revision)}.json"
            cached = load(cachefile)
            if cached and (cached.get("text") or not text):
                text, state = cached.get("text", ""), cached["status"]
            retry_due = time.time() - cached.get("attempted_at", 0) >= 86400
            if not text and retry_due and download and (download_budget <= 0 or time.monotonic() - download_start < download_budget):
                try:
                    mime = item["mimeType"]
                    exports = {"application/vnd.google-apps.document": ("text/plain", ".txt"), "application/vnd.google-apps.spreadsheet": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"), "application/vnd.google-apps.presentation": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx")}
                    if mime in exports:
                        export_mime, suffix = exports[mime]
                        data = execute_with_retry(service.files().export_media(fileId=item["id"], mimeType=export_mime))
                    elif Path(name).suffix.lower() in SOURCE_SUFFIXES and not mime.startswith(("audio/", "video/")):
                        suffix = Path(name).suffix.lower()
                        data = execute_with_retry(service.files().get_media(fileId=item["id"], supportsAllDrives=True))
                    else:
                        data, suffix = b"", ".unsupported"
                    text, state, _ = self.cached_extract(data, suffix)
                except Exception as exc:
                    state = "access_unavailable" if getattr(getattr(exc, "resp", None), "status", None) in {403, 404} else "awaiting_extraction"
                write(cachefile, {"text": text, "status": state, "attempted_at": time.time()})
            identity = "md5:" + item["md5Checksum"] if item.get("md5Checksum") else "drive:" + item["id"] + ":" + revision
            rec = self.base(identity, name, "drive", text=text, state=state, explicit=explicit, locations=[{"kind": "drive", "url": url, "label": "Open original"}], mime=item["mimeType"], path=full)
            rec.update({"family": "drive:" + item["id"], "revision": revision, "modified_at": item.get("modifiedTime"), "format": item["mimeType"]})
            if state == "access_unavailable":
                rec["availability"] = "access_unavailable"
            anchors = [url_anchor(url)]
            if item.get("md5Checksum"):
                anchors.append("md5:" + item["md5Checksum"])
            if props.get("sha256"):
                anchors.append("sha:" + props["sha256"])
            self.add(rec, anchors)
        self.receipt("drive", count)

    def publish(self):
        records = retain_previous(self.index.records, self.previous.get("records", {}), self.good)
        by_ticker = defaultdict(list)
        bundles, content_batch, content_size = {}, {}, 0
        def flush_content():
            nonlocal content_batch, content_size
            if content_batch:
                filename = "documents/" + digest(json.dumps(content_batch, sort_keys=True))[:24] + ".json"
                write(self.output / filename, content_batch)
                bundles.update({sid:filename for sid in content_batch})
                content_batch, content_size = {}, 0
        review = []
        status_counts = Counter()
        for rec in records.values():
            previous = self.previous.get("records", {}).get(rec["id"], {})
            if previous.get("indexed_at"):
                rec["indexed_at"] = previous["indexed_at"]
            status_counts[rec["processing_status"]] += 1
            review.extend({"source_id": rec["id"], **r} for r in rec.get("review", []))
            if not any(r["ticker"] in self.companies for r in rec.get("relationships", [])):
                continue
            full_text = self.text(rec)
            parts = []
            if len(full_text.encode("utf-8")) > 1_000_000:
                for start in range(0,len(full_text),1_000_000):
                    part = full_text[start:start+1_000_000]
                    filename = "text/" + digest(part) + ".json"
                    write(self.output / filename, {"text":part})
                    parts.append(filename)
            content = {"id": rec["id"], "title": rec["title"], "text": "" if parts else full_text, "text_parts":parts, "locations": rec.get("locations", []), "processing_status": rec["processing_status"]}
            content_bytes = len(json.dumps(content, ensure_ascii=False).encode())
            if content_batch and content_size + content_bytes > 4_000_000:
                flush_content()
            content_batch[rec["id"]] = content
            content_size += content_bytes
            for relation in rec.get("relationships", []):
                if relation["ticker"] not in self.companies:
                    continue
                view = {k: v for k, v in rec.items() if k not in {"text", "text_cache", "text_length", "relationships", "review"}}
                view.update(relation)
                by_ticker[relation["ticker"]].append(view)
        flush_content()
        summary = {}
        review_counts = Counter(r.get("ticker") for r in review)
        unassigned_pending = sum(r["processing_status"] != "indexed" and not r.get("relationships") for r in records.values())
        for ticker in sorted(self.companies):
            rows = sorted(by_ticker[ticker], key=lambda r: (r.get("relationship") == "direct", r.get("date") or "", r["title"]), reverse=True)
            # Multiple matching passages/locations still count as one document per company.
            unique = {}
            for row in rows:
                unique.setdefault(row["id"], row)
            rows = list(unique.values())
            families = defaultdict(list)
            for row in rows:
                families[row.get("family") or row["id"]].append(row)
            for versions in families.values():
                versions.sort(key=lambda r: (r.get("availability") != "superseded", r.get("modified_at") or r.get("date") or "", r.get("indexed_at") or ""), reverse=True)
                for i, row in enumerate(versions):
                    row["is_latest"] = i == 0
                    row["version_count"] = len(versions)
            index = defaultdict(list)
            source_ids = [r["id"] for r in rows]
            for ordinal, row in enumerate(rows):
                row["content_path"] = bundles[row["id"]]
                for word in set(self.source_words(records[row["id"]])) | tokens(row["title"] + " " + row.get("author", "")):
                    index[word].append(ordinal)
            pages = []
            for i in range(0, len(rows), 100):
                page = rows[i:i+100]
                filename = f"companies/{ticker}/{digest(json.dumps(page, sort_keys=True))[:24]}.json"
                write(self.output / filename, page); pages.append(filename)
            search_path = f"search/{ticker}.json"
            search_parts, search_chunk, search_size = [], {}, 0
            for word, ids in sorted(index.items()):
                entry_size = len(json.dumps({word: ids}).encode())
                if search_chunk and search_size + entry_size > 4_000_000:
                    filename = f"search/{ticker}/{digest(json.dumps(search_chunk, sort_keys=True))[:24]}.json"
                    write(self.output / filename, search_chunk)
                    search_parts.append(filename)
                    search_chunk, search_size = {}, 0
                search_chunk[word] = ids
                search_size += entry_size
            if search_parts:
                filename = f"search/{ticker}/{digest(json.dumps(search_chunk, sort_keys=True))[:24]}.json"
                write(self.output / filename, search_chunk)
                search_parts.append(filename)
                write(self.output / search_path, {"__parts": search_parts, "__ids": source_ids})
            else:
                write(self.output / search_path, {**search_chunk, "__ids": source_ids})
            counts = dict(Counter(r["category"] for r in rows))
            pending = sum(r["processing_status"] != "indexed" for r in rows)
            receipts = [r for r in self.receipts if not r["collection"].startswith("company:") or r["collection"] == "company:" + ticker]
            incomplete = [r for r in receipts if r["status"] != "complete"]
            review_count = review_counts[ticker]
            coverage = {"checked_at": self.now, "status": "partial" if incomplete or pending or review_count or unassigned_pending else "complete", "pending": pending, "unassigned_pending": unassigned_pending, "review_count": review_count, "unavailable_collections": len(incomplete), "receipts": receipts}
            featured=[]
            for kind in ("analysis","calls","letters","filings","models"):
                hit=next((r for r in rows if r["category"]==kind and r["relationship"]=="direct" and r.get("availability")=="available"),None)
                if hit:
                    featured.append(hit)
            manifest = {"schema_version": 1, "ticker": ticker, "company": self.companies[ticker].get("company"), "total": len(rows), "categories": counts, "coverage": coverage, "pages": pages, "search_path": search_path, "featured": featured}
            write(self.output / f"companies/{ticker}.json", manifest)
            summary[ticker] = {"total": len(rows), "categories": counts, "pending": pending}
        report = {"schema_version": 1, "generated_at": self.now, "documents": len(records), "companies": len(summary), "linked_companies": sum(v["total"] > 0 for v in summary.values()), "processing": dict(status_counts), "review_count": len(review), "receipts": self.receipts, "tickers": summary}
        write(self.output / "manifest.json", report)
        if len(json.dumps(review).encode()) > 4_000_000:
            review_parts = []
            for start in range(0, len(review), 1000):
                chunk = review[start:start+1000]
                relative = "review/" + digest(json.dumps(chunk, sort_keys=True))[:24] + ".json"
                write(self.output / relative, {"items": chunk})
                review_parts.append(relative)
            write(self.output / "review.json", {"count": len(review), "parts": review_parts})
        else:
            write(self.output / "review.json", {"items": review})
        saved = {}
        saved_text = set()
        for key, record in records.items():
            sha = record.get("text_cache")
            if not sha and record.get("text"):
                sha = digest(record["text"])
                if sha not in saved_text:
                    write(self.cache / "published-text" / (sha + ".json"), {"text": record["text"]})
                    saved_text.add(sha)
            saved[key] = {k:v for k,v in record.items() if k != "text"}
            if sha:
                saved[key]["text_cache"] = sha
        parts = write_mapping(self.cache, "records", saved)
        write(self.cache / "index.json", {"record_parts": parts, "receipts": self.receipts, "generated_at": self.now})
        write(self.cache / "matches.json", {"version": self.match_version, "parts": write_mapping(self.cache, "relationships", self.matches)})
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--vault", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "_private/company-research/site")
    parser.add_argument("--cache", type=Path, default=ROOT / "_private/company-research/cache")
    parser.add_argument("--drive", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--download-budget-seconds", type=int, default=300, help="Text extraction work budget; inventory is never capped. Zero means unlimited.")
    parser.add_argument("--tickers", nargs="+", help="Explicitly scoped verification run; omit to build the full universe")
    args = parser.parse_args()
    from vault_paths import research_vault_root
    vault = args.vault or research_vault_root()
    if vault:
        os.environ["RESEARCH_VAULT_ROOT"] = str(vault.resolve())
    companies = read_companies(args.source_root)
    if args.tickers:
        companies = {t:companies[t] for t in args.tickers}
    build = Builder(args.source_root, vault, args.output, args.cache, companies=companies if args.tickers else None)
    build.registries()
    build.local_corpora()
    try:
        build.git_inventory()
    except Exception as exc:
        build.receipt("git_inventory", 0, "failed", type(exc).__name__)
    if args.drive:
        try:
            build.drive(download=args.download, download_budget=args.download_budget_seconds)
        except (Exception, SystemExit) as exc:
            build.receipt("drive", 0, "failed", type(exc).__name__)
    else:
        build.receipt("drive", 0, "not_scanned", "Using stored originals; live Drive enumeration was not requested")
    report = build.publish()
    print(json.dumps({k: v for k, v in report.items() if k not in {"tickers", "receipts"}}))


if __name__ == "__main__":
    main()
