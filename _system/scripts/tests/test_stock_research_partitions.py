"""Keep every stock and UTF-8 input inside the bounded private snapshot parts."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from partition_stock_research_history import partition
from stock_one_pagers import load_universe_document


def test_every_stock_round_trips_with_small_parts_and_unicode(tmp_path):
    companies = {f"T{i}": {"ticker": f"T{i}", "thesis": "資本 allocation " * 12} for i in range(12)}
    folder = tmp_path / "_system/reference/stock-research"
    report = partition({"schema_version": "stock-research-universe.v1", "companies": companies}, folder, max_bytes=800)
    assert report["parts"] > 1
    assert report["largest_part_bytes"] <= 800
    assert load_universe_document(tmp_path)["companies"] == companies
    index = json.loads((folder / "universe.json").read_text(encoding="utf-8"))
    assert index["stock_count"] == 12
