"""A valid research JSON must also fit the actual deployment asset boundary."""
from pathlib import Path


def test_published_calmar_is_small_enough_to_be_deployed():
    root = Path(__file__).resolve().parents[4]
    path = root/"_system/data/reverse_splits/calmar_research.json"
    if path.exists():
        assert path.stat().st_size < 20*1024*1024, "Pages staging would silently omit the Calmar results"


def test_expanded_research_evidence_assets_fit_the_deployment_boundary():
    root = Path(__file__).resolve().parents[4]/"_system/data/reverse_splits"
    paths = [root/"coverage_research.json", *root.glob("coverage_audits/*.json"), *root.glob("coverage_packets/*.json")]
    for path in paths:
        if path.exists():
            assert path.stat().st_size < 20*1024*1024, f"Pages staging would omit {path.name}"
