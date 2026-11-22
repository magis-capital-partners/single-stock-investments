"""Prepare stock research in the authenticated publication copy, after libraries are staged."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from atomic_io import _atomic_write_text
from source_links import SourceLinks, repository_url
from stock_one_pagers import build_one_pager, set_publication_inputs, load_universe_document
from stock_valuation_models import INPUT_PATH as VALUATION_INPUT_PATH, set_valuation_inputs, valuation_inputs
from stock_valuation_identity import quarantine_prior_valuation
from stock_valuation_aliases import consolidate_aliases
from stock_research_explorer import INPUT_PATH as EXPLORER_INPUT_PATH, load_explorer_inputs, stage_explorer
from vault_paths import research_vault_root

ROOT = Path(__file__).resolve().parents[2]


def curate_reading(data: Path):
    """Choose a primary report, substantive research and a letter before macro snapshots."""
    library = data / "company-research"
    for path in sorted((library / "companies").glob("*.json")):
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
    snapshot_path = "_system/reference/stock-research/universe.json"
    if (root / snapshot_path).is_file():
        set_publication_inputs(root, load_universe_document(root, resolve_private=True))
    if (root / VALUATION_INPUT_PATH).is_file():
        from private_dashboard_assets import read_resolved_json
        set_valuation_inputs(root, read_resolved_json(root, VALUATION_INPUT_PATH)[0])
    if (root / EXPLORER_INPUT_PATH).is_file():
        load_explorer_inputs(root, resolve_private=True)
    links = SourceLinks(root, vault)
    pilots, changed = [], 0
    data = site / "data"
    consolidate_aliases(root, data)
    prior_index = data / "source_links.json"
    if prior_index.is_file():
        for original in json.loads(prior_index.read_text(encoding="utf-8")).get("repairs", {}):
            links.resolve(original)
    curate_reading(data)
    core_snapshot=json.loads((data/'core.json').read_text(encoding='utf-8')) if (data/'core.json').is_file() else {}
    expected_explorer={r['ticker'] for r in core_snapshot.get('tickers',[])} or {p.stem for p in (data/'tickers').glob('*.json')}
    explorer = stage_explorer(root, data, expected_explorer,links)
    for path in sorted(data.rglob("*.json")):
        if path.name == "source_links.json" or path.is_relative_to(data/'research-explorer'):
            continue
        raw = path.read_text(encoding="utf-8")
        pilot = path.parent == data / "tickers"
        if not pilot and "github.com/" not in raw and "raw.githubusercontent.com/" not in raw and not re.search(r'"(?:ref|source_ref|source_refs|evidence_ref|model_ref|source_path)"\s*:', raw):
            continue
        value = json.loads(raw)
        if path == data / "core.json":
            for row in value.get("tickers", []):
                quarantine_prior_valuation(row, valuation_inputs(root).get(row.get("ticker"), {}))
        if pilot and isinstance(value, dict) and not value.get("private_snapshot"):
            if value.get("schema_version") == "stock-research-alias.v1":
                continue
            ticker = value.get("ticker")
            if not isinstance(ticker, str) or not ticker:
                raise ValueError(f"Missing stock identity in {path.name}")
            quarantine_prior_valuation(value, valuation_inputs(root).get(ticker, {}))
            value["one_pager"] = build_one_pager(root, ticker, value)
            pilots.append(ticker)
        # Register links in references as well, without changing frozen proof inputs.
        def collect(node):
            if isinstance(node, dict):
                for key, child in node.items():
                    if key in {"ref", "source_ref", "source_refs", "evidence_ref", "model_ref", "source_path"}:
                        for ref in child if isinstance(child, list) else [child]:
                            if isinstance(ref, str) and not ref.startswith(("http:", "https:")) and re.match(r"^(?:_system|[A-Za-z0-9._-]+)/", ref) and re.search(r"\.(?:pdf|md|txt|json|csv|xlsx?|html?|svg)(?:#.*)?$", ref, re.I):
                                # Register navigation without rewriting frozen proof refs.
                                links.resolve(ref)
                                links.resolve(repository_url(ref))
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
    core_path = data / "core.json"
    if core_path.is_file():
        core = json.loads(core_path.read_text(encoding="utf-8"))
        expected = {r["ticker"] for r in core.get("tickers", [])}
        if expected - set(pilots):
            raise ValueError(f"Missing stock briefs: {sorted(expected - set(pilots))}")
        if core_path.stat().st_size >= 6_000_000:
            raise ValueError("Dashboard core exceeds the 6 MB startup budget")
    from build_cloudflare_pages_site import MAX_FILE_BYTES
    largest = 0
    for path in data.rglob("*.json"):
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ValueError(f"Published data asset exceeds the hosting size limit: {path.relative_to(data)}")
        largest = max(largest, size)
    file_count=sum(p.is_file() for p in site.rglob('*'))
    if file_count>20000:raise ValueError(f'Complete publication has {file_count} files; hosting limit is 20,000')
    return {"stocks": len(pilots), "tickers": sorted(pilots), "explorer": explorer, "changed_publication_files": changed,
            "largest_data_asset_bytes": largest,'file_count':file_count, "source_links": dict(links.counts)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "_cf_project/site")
    args = parser.parse_args()
    print(json.dumps(prepare(ROOT, args.site, research_vault_root())))
