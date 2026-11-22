"""Private, partitioned financial explorer inputs and bounded publication.

This module never contacts a broker or a data terminal. Source snapshots live in
the private artifact store; the repository contains only receipts and stubs.
"""
from __future__ import annotations

import json
import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote

from atomic_io import _atomic_write_text

INPUT_PATH = "_system/reference/stock-research/explorer.json"
SCHEMA = "stock-research-explorer.v1"
MAX_PART = 8 * 1024 * 1024
_INPUTS = {}
_PRIVATE_READERS={}


def read_explorer_json(root,relative,storage=None):
    """Read through R2 or an already hydrated copy; never stage in vault Git."""
    if relative not in {'dashboard/data/core.json','_system/reference/stock-research/valuation-inputs.json'} and not re.fullmatch(r'_system/reference/stock-research/(?:explorer/part-\d+|share-basis)\.json',relative):raise ValueError('Unsafe explorer source')
    publication=json.loads((root/'dashboard/private-assets.json').read_text(encoding='utf-8'))
    receipt=publication.get('assets' if relative.startswith('dashboard/') else 'repository_assets',{}).get(relative.removeprefix('dashboard/'))
    if not receipt or not re.fullmatch(r'[a-f0-9]{64}',receipt.get('private_sha256','')):raise ValueError('Missing private explorer receipt')
    path=root/relative
    if path.is_file():
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()==receipt['private_sha256']:return json.loads(raw)
    if root.resolve() not in _PRIVATE_READERS:
        from private_storage import PrivateStorage
        store=storage or PrivateStorage(root=root);_,records=store.snapshot();_PRIVATE_READERS[root.resolve()]=(store,records)
    store,records=_PRIVATE_READERS[root.resolve()]
    key='dashboard-private/objects/'+receipt['private_sha256']
    from private_dashboard_assets import decode_object_bytes
    raw=decode_object_bytes(store.restore(key,records=records),receipt['private_sha256'])
    if len(raw)>MAX_PART:raise ValueError('Explorer source exceeds its partition bound')
    return json.loads(raw)


class LocalCompanies(Mapping):
    """One company in memory at a time, including on small CI runners."""
    def __init__(self, paths, *, wrapped=False): self.paths,self.wrapped=paths,wrapped
    def __iter__(self): return iter(self.paths)
    def __len__(self): return len(self.paths)
    def __getitem__(self,key):
        document=json.loads(Path(self.paths[key]).read_text(encoding='utf-8'))
        return document['company'] if self.wrapped else document


class PartitionCompanies(Mapping):
    def __init__(self,root,locations,resolve_private,basis=None):
        self.root,self.locations,self.resolve_private=root,locations,resolve_private
        self.basis=basis or {}
        self.current_path,self.current=None,{}
    def __iter__(self): return iter(self.locations)
    def __len__(self): return len(self.locations)
    def __getitem__(self,key):
        relative=self.locations[key]
        if self.current_path!=relative:
            if self.resolve_private:
                part=read_explorer_json(self.root,relative)
            else:part=json.loads((self.root/relative).read_text(encoding='utf-8'))
            if part.get('schema_version')!=SCHEMA:raise ValueError('Invalid private research part')
            self.current_path,self.current=relative,part['companies']
        if key not in self.current:raise ValueError('Research part identity differs from its manifest')
        return {**self.current[key],'share_basis':self.basis[key]} if key in self.basis else self.current[key]


def compact_company(company):
    """Deduplicate citations without losing any source or calculation operand."""
    if company.get("sources"):
        return company
    sources, identities = {}, {}
    def ref(value):
        if not isinstance(value, dict):
            return value
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if raw not in identities:
            identity = str(len(identities)); identities[raw] = identity; sources[identity] = value
        return {"source_id": identities[raw]}
    def visit(value):
        if isinstance(value, list): return [visit(v) for v in value]
        if not isinstance(value, dict): return value
        result = {}
        for k,v in value.items():
            if k in {"source", "price_source"}: result[k] = ref(v)
            elif k == "source_refs" and isinstance(v,list): result[k] = [ref(s) for s in v]
            else: result[k] = visit(v)
        return result
    result = visit(company)
    del visit  # Release the recursive closure and its source table between issuers.
    result["sources"] = sources
    return result


def expand_company(company):
    sources = company.get("sources", {})
    if not sources: return company
    def visit(value):
        if isinstance(value,list): return [visit(v) for v in value]
        if not isinstance(value,dict): return value
        if set(value)=={"source_id"}:
            if value["source_id"] not in sources: raise ValueError("Missing source identity")
            return sources[value["source_id"]]
        return {k:visit(v) for k,v in value.items() if k!="sources"}
    document=visit(company)
    del visit
    for series in document.get('series',[]):
        if not series.get('label'):series['label']=series['id'].replace('_',' ').capitalize()
    return document


def set_explorer_inputs(root: Path, document: dict):
    if document.get("schema_version") != SCHEMA or not isinstance(document.get("companies"), Mapping):
        raise ValueError("Invalid stock explorer inputs")
    _INPUTS[root.resolve()] = document


def load_explorer_inputs(root: Path, *, resolve_private=False):
    if root.resolve() in _INPUTS:
        return _INPUTS[root.resolve()]
    path = root / INPUT_PATH
    if not path.is_file():
        return {"schema_version": SCHEMA, "companies": {}}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "stock-research-explorer-parts.v1":
        raise ValueError("Invalid explorer manifest")
    locations=manifest.get('company_parts')
    if locations:
        basis={}
        if manifest.get('share_basis'):
            if manifest['share_basis']!='_system/reference/stock-research/share-basis.json':raise ValueError('Unsafe share basis asset')
            if resolve_private:
                basis=read_explorer_json(root,manifest['share_basis']).get('companies',{})
        if len(locations)!=manifest.get('stock_count') or any(not re.fullmatch(r"_system/reference/stock-research/explorer/part-\d+\.json",v) or v not in manifest.get('parts',[]) for v in locations.values()):raise ValueError('Invalid private research locations')
        # Editor/test reads never acquire private credentials.
        if not resolve_private and any(json.loads((root/p).read_text(encoding='utf-8')).get('private_snapshot') for p in manifest['parts']):return {'schema_version':SCHEMA,'companies':{}}
        doc={'schema_version':SCHEMA,'as_of':manifest.get('as_of'),'companies':PartitionCompanies(root,locations,resolve_private,basis)}
        set_explorer_inputs(root,doc);return doc
    companies = {}
    for relative in manifest.get("parts", []):
        if not re.fullmatch(r"_system/reference/stock-research/explorer/part-\d+\.json", relative):
            raise ValueError("Invalid explorer part path")
        if resolve_private:
            from private_dashboard_assets import read_resolved_json
            part = read_resolved_json(root, relative)[0]
        else:
            part = json.loads((root / relative).read_text(encoding="utf-8"))
            if part.get("private_snapshot"):
                return {"schema_version": SCHEMA, "companies": {}}
        if part.get("schema_version") != SCHEMA or companies.keys() & part.get("companies", {}).keys():
            raise ValueError("Invalid or overlapping explorer parts")
        companies.update(part.get("companies", {}))
    if len(companies) != manifest.get("stock_count"):
        raise ValueError("Explorer coverage differs from its receipt")
    doc = {"schema_version": SCHEMA, "as_of": manifest.get("as_of"), "companies": companies}
    set_explorer_inputs(root, doc)
    return doc


def partition(document: dict, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    parts, current,locations = [], {},{}
    def flush():
        if not current:
            return
        name = f"part-{len(parts):03d}.json"
        raw = json.dumps({"schema_version": SCHEMA, "companies": current}, ensure_ascii=False, separators=(",", ":")) + "\n"
        if len(raw.encode()) > MAX_PART:
            raise ValueError("Explorer part exceeds 8 MiB")
        _atomic_write_text(destination / name, raw)
        parts.append("_system/reference/stock-research/explorer/" + name)
        locations.update({t:parts[-1] for t in current})
    for ticker in sorted(document["companies"]):
        company=document['companies'][ticker]
        company = compact_company(company)
        candidate = {**current, ticker: company}
        if len(json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode()) > MAX_PART - 256:
            flush()
            current = {}
        current[ticker] = company
    flush()
    manifest = {"schema_version": "stock-research-explorer-parts.v1", "as_of": document["as_of"],
                "stock_count": len(document["companies"]), "parts": parts,"company_parts":locations}
    _atomic_write_text(destination.parent / "explorer.json", json.dumps(manifest, separators=(",", ":")) + "\n")
    return manifest


def stage_explorer(root: Path, data: Path, expected: set[str],links=None):
    document = load_explorer_inputs(root)
    companies = document["companies"]
    if not companies:
        return {"stocks": 0, "status": "no_private_snapshot"}
    # New universe entrants still get the complete interface, with truthful gaps.
    from build_stock_research_explorer import empty_company, summary
    from financial_changes import ComparisonIndex
    from stock_one_pagers import universe_inputs
    comparison = ComparisonIndex(root, document["as_of"])
    briefs = universe_inputs(root)
    benchmark = (briefs.get("SPY") or {}).get("performance") or {}
    target = data / "research-explorer"
    target.mkdir(parents=True, exist_ok=True)
    rows, largest, with_history = [], 0, 0
    pending,locations,bundles={}, {}, []
    pending_bytes=0
    def flush():
        nonlocal pending,pending_bytes,largest
        if not pending:return
        name=f'bundle-{len(bundles):03d}.json'
        raw=json.dumps({'schema_version':SCHEMA,'companies':pending},ensure_ascii=False,separators=(',',':'))+'\n'
        size=len(raw.encode())
        if size>MAX_PART:raise ValueError('Research fallback bundle exceeds 8 MiB')
        _atomic_write_text(target/name,raw);largest=max(largest,size)
        locations.update({ticker:name for ticker in pending});bundles.append(name)
        pending={};pending_bytes=0
    for ticker in sorted(expected):
        company = companies.get(ticker) or empty_company(ticker, document.get("as_of"))
        path = target / (quote(ticker, safe="") + ".json")
        compact=compact_company(company)
        if links and compact.get('sources'):
            from source_links import repository_url
            for source in compact['sources'].values():
                for key in ('ref','url'):
                    value=source.get(key)
                    if isinstance(value,str) and value:
                        links.resolve(value)
                        if not value.startswith(('https:','http:')):links.resolve(repository_url(value))
            compact={**compact,'sources':links.repair_tree(compact['sources'])}
        raw = json.dumps(compact, ensure_ascii=False, separators=(",", ":")) + "\n"
        size = len(raw.encode())
        if size > MAX_PART-256:
            raise ValueError(f"Explorer asset too large: {ticker}")
        item_bytes=size+len(json.dumps(ticker).encode())+2
        if pending_bytes+item_bytes>MAX_PART-256:flush()
        pending[ticker]=compact;pending_bytes+=item_bytes
        # Remove only this generated, obsolete per-company publication copy.
        if path.is_file():path.unlink()
        expanded = expand_company(compact)
        rows.append(summary(expanded))
        performance = (briefs.get(ticker) or {}).get("performance") or {}
        comparison.add(expanded, performance, benchmark)
        with_history += any(s.get("monthly") for s in company.get("series", []))
    flush()
    for path in target.glob('bundle-*.json'):
        if re.fullmatch(r'bundle-\d+\.json',path.name) and path.name not in bundles:path.unlink()
    change_bytes = json.dumps(comparison.finish(rows), ensure_ascii=False, separators=(",", ":"))
    change_size = len(change_bytes.encode())
    if change_size > 20 * 1024 * 1024:
        raise ValueError("Financial changes exceed the hosted object budget")
    _atomic_write_text(target / "changes.json", change_bytes)
    fallback={'schema_version':'stock-research-fallback.v1','as_of':document.get('as_of'),'company_bundles':locations}
    _atomic_write_text(target/'manifest.json',json.dumps(fallback,separators=(',',':'))+'\n')
    index = {"schema_version": "stock-research-index.v1", "as_of": document.get("as_of"), "companies": rows}
    raw = json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n"
    if len(raw.encode()) > 20 * 1024 * 1024:
        raise ValueError("Research screener index exceeds hosting budget")
    _atomic_write_text(target / "index.json", raw)
    return {"stocks": len(rows), "historical_valuation_stocks": with_history, "largest_asset_bytes": max(largest,change_size), "comparison_bytes":change_size,
            "index_bytes": len(raw.encode()),'fallback_bundles':len(bundles)}
