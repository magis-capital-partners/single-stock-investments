"""Research ticker changes preserve archives without merging different securities."""
import json
from pathlib import Path
from atomic_io import _atomic_write_text

ALIAS_PATH = "_system/reference/stock-research/ticker-aliases.json"


def research_aliases(root: Path):
    path = root / ALIAS_PATH
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "stock-research-aliases.v1":
        raise ValueError("Invalid research ticker alias file")
    return data["aliases"]


def legacy_libraries(root, ticker):
    return [{"ticker": old, "company": row["company"], "cutoff": row["effective_date"],
             "issuer_cik": row["issuer_cik"], "excluded_cik": row.get("excluded_cik"), "source_ref": row["source_ref"]}
            for old, row in research_aliases(root).items() if row["ticker"] == ticker]


def consolidate_aliases(root, data):
    aliases = research_aliases(root)
    core_path = data / "core.json"
    if not aliases or not core_path.is_file():
        return
    core = json.loads(core_path.read_text(encoding="utf-8"))
    by_ticker = {row["ticker"]: row for row in core["tickers"]}
    for old, alias in aliases.items():
        target = alias["ticker"]
        if old not in by_ticker:
            continue
        if target not in by_ticker:
            raise ValueError("Research ticker alias target is missing: "+target)
        prior = by_ticker[old]
        detail = (data.parent / prior["detail_shard"]).resolve()
        if not detail.is_relative_to((data / "tickers").resolve()):
            raise ValueError("Research alias detail escapes the stock shard directory")
        _atomic_write_text(detail, json.dumps({"schema_version": "stock-research-alias.v1", "ticker": old,
                                              "redirect_ticker": target, "detail_shard": by_ticker[target]["detail_shard"]}, separators=(",", ":"))+"\n")
        by_ticker[target]["legacy_tickers"] = sorted(set([*by_ticker[target].get("legacy_tickers", []), old]))
        by_ticker[target]["company"] = alias["company"]+" (formerly "+old+")"
        core.setdefault("ticker_aliases", {})[old] = target
    core["tickers"] = [row for row in core["tickers"] if row["ticker"] not in aliases]
    core.setdefault("summary", {})["ticker_count"] = len(core["tickers"])
    for summary_key, row_key in (("with_research", "research_dir"), ("with_readme", "readme")):
        if summary_key in core["summary"]:
            core["summary"][summary_key] = sum(bool(row.get(row_key)) for row in core["tickers"])
    # Universe statistics in historical import receipts keep their own dates.
    _atomic_write_text(core_path, json.dumps(core, ensure_ascii=False, separators=(",", ":"))+"\n")
