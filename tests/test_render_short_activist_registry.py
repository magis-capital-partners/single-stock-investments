from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "_system" / "scripts" / "render_short_activist_registry.py"
SPEC = importlib.util.spec_from_file_location("render_short_activist_registry", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_short_registry_markdown_matches_the_json() -> None:
    text = MODULE.render_markdown()
    assert text == MODULE.OUTPUT.read_text(encoding="utf-8")
    doc = json.loads(MODULE.SOURCE.read_text(encoding="utf-8"))
    for firm in doc["firms"]:
        if firm.get("side") in {"short", "both"}:
            assert f"**{firm['name']}**" in text
    assert "Kerrisdale Capital" in text
    assert "Bucephalus Research" in text
    assert "Do not edit the firm tables by hand." in text
