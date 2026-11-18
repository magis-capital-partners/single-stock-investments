"""Prepare stock research in the authenticated publication copy, after libraries are staged."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from atomic_io import _atomic_write_text
from source_links import SourceLinks
from stock_one_pagers import PROFILES, build_one_pager
from vault_paths import research_vault_root

ROOT = Path(__file__).resolve().parents[2]


def curate_reading(data: Path):
    """Choose a primary report, substantive research and a letter before macro snapshots."""
    library = data / "company-research"
    for ticker in PROFILES:
        path = library / f"companies/{ticker}.json"
        if not path.is_file():
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        rows = []
        for page in manifest.get("pages", []):
            candidate = (library / page).resolve()
            if not candidate.is_relative_to(library.resolve()) or not candidate.is_file():
                continue
            rows.extend(json.loads(candidate.read_text(encoding="utf-8")))
        rows = [r for r in rows if r.get("relationship") == "direct" and r.get("is_latest", True)
                and r.get("availability") == "available"]
        featured = []
        for category in ("filings", "analysis", "letters", "models"):
            matches = [r for r in rows if r.get("category") == category
                       and not re.search(r"thematic.context|insider.signal|open.questions|import.log", r.get("title", ""), re.I)]
            def rank(record):
                title = record.get("title", "")
                substantive = bool(re.search(r"10[- ]?[KQ]|annual.report|quarterly.report|deep.dive|stock.specific.model|valuation.contract", title, re.I))
                return substantive, record.get("date") or ""
            if matches:
                featured.append(max(matches, key=rank))
        manifest["featured"] = featured[:3]
        _atomic_write_text(path, json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n")


def prepare(root: Path, site: Path, vault: Path | None = None) -> dict:
    links = SourceLinks(root, vault)
    pilots, changed = [], 0
    data = site / "data"
    prior_index = data / "source_links.json"
    if prior_index.is_file():
        for original in json.loads(prior_index.read_text(encoding="utf-8")).get("repairs", {}):
            links.resolve(original)
    curate_reading(data)
    for path in sorted(data.rglob("*.json")):
        if path.name == "source_links.json":
            continue
        raw = path.read_text(encoding="utf-8")
        pilot = path.parent == data / "tickers" and path.stem in PROFILES
        if not pilot and "github.com/" not in raw and "raw.githubusercontent.com/" not in raw:
            continue
        value = json.loads(raw)
        if pilot and isinstance(value, dict) and not value.get("private_snapshot"):
            value["one_pager"] = build_one_pager(root, path.stem, value)
            brief = value["one_pager"]
            if not brief["model"]["assumptions"] or not brief["financials"]["series"] or not brief["risks"]:
                raise ValueError(f"Incomplete {path.stem} pilot inputs; refusing to publish an empty brief")
            pilots.append(path.stem)
        # Register links in references as well, without changing frozen proof inputs.
        def collect(node):
            if isinstance(node, dict):
                for child in node.values():
                    collect(child)
            elif isinstance(node, list):
                for child in node:
                    collect(child)
            elif isinstance(node, str) and node.startswith(("https://github.com/", "https://raw.githubusercontent.com/")) and "\n" not in node:
                links.resolve(node)
        collect(value)
        repaired = links.repair_tree(value)
        result = json.dumps(repaired, ensure_ascii=False, separators=(",", ":")) + "\n"
        if result.rstrip() != raw.rstrip():
            # Library assets can be hardlinked to their private source. Replace the
            # publication path atomically; never edit that shared inode in place.
            _atomic_write_text(path, result)
            changed += 1
    index = {"schema_version": "source-links.v1", "repairs": links.repairs, "counts": dict(links.counts)}
    data.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(data / "source_links.json", json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n")
    return {"pilots": sorted(pilots), "changed_publication_files": changed, "source_links": dict(links.counts)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "_cf_project/site")
    args = parser.parse_args()
    print(json.dumps(prepare(ROOT, args.site, research_vault_root())))
