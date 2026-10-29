#!/usr/bin/env python3
"""Stage a complete private company library only into the authenticated site artifact."""
from pathlib import Path
import argparse
import json
import shutil
import os


def stage(source: Path, site: Path, *, hardlink=False) -> dict:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    routes = json.loads((site / "_routes.json").read_text(encoding="utf-8"))
    if routes.get("include") != ["/*"] or routes.get("exclude"):
        raise RuntimeError("Research sources require authentication on every asset")
    if not manifest.get("documents") or not manifest.get("linked_companies"):
        raise RuntimeError("Refusing to deploy an empty company library")
    destination = site / "data/company-research"
    required = {"manifest.json", "review.json"}
    review = json.loads((source / "review.json").read_text(encoding="utf-8"))
    required.update(review.get("parts", []))
    bundles = set()
    for ticker in manifest["tickers"]:
        company_path = f"companies/{ticker}.json"
        company = json.loads((source / company_path).read_text(encoding="utf-8"))
        required.update([company_path, company["search_path"], *company["pages"]])
        search = json.loads((source / company["search_path"]).read_text(encoding="utf-8"))
        required.update(search.get("__parts", []))
        for page in company["pages"]:
            for row in json.loads((source / page).read_text(encoding="utf-8")):
                bundles.add(row["content_path"])
    required.update(bundles)
    for bundle in bundles:
        for doc in json.loads((source / bundle).read_text(encoding="utf-8")).values():
            required.update(doc.get("text_parts", []))
    count = 0
    for relative in sorted(required):
        path = (source / relative).resolve()
        if not path.is_relative_to(source.resolve()):
            raise RuntimeError("Invalid research asset reference")
        if path.stat().st_size >= 20 * 1024 * 1024:
            raise RuntimeError(f"Research asset needs further sharding: {path.name}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and os.path.samefile(path, target):
            pass
        elif hardlink and not target.exists():
            try:os.link(path,target)
            except OSError:shutil.copy2(path,target)
        else:
            shutil.copy2(path, target)
        count += 1
    for ticker in manifest["tickers"]:
        company = json.loads((destination / f"companies/{ticker}.json").read_text(encoding="utf-8"))
        if not all((destination / p).is_file() for p in company["pages"] + [company["search_path"]]):
            raise RuntimeError(f"Missing library pages for {ticker}")
    return {"files": count, "documents": manifest["documents"], "companies": manifest["companies"]}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=Path("_private/company-research/site"))
    parser.add_argument("--site",type=Path,default=Path("_cf_project/site"))
    parser.add_argument("--hardlink",action="store_true",help="Link immutable generated assets for local validation without duplicating their bytes")
    args=parser.parse_args()
    print(json.dumps(stage(args.source,args.site,hardlink=args.hardlink)))
