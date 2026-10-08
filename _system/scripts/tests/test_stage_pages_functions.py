"""Pages Functions imports must resolve in the repo and in the staged bundle tree."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "_system" / "scripts" / "stage_pages_functions.py"
FUNCTIONS = ROOT / "dashboard" / "functions"
DATA = ROOT / "dashboard" / "data"


def load_stage():
    spec = importlib.util.spec_from_file_location("stage_pages_functions", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_javascript_imports_stay_inside_the_functions_tree():
    stage = load_stage()
    missing = []
    for path, spec, target in stage.relative_imports(FUNCTIONS):
        if spec.endswith(".json"):
            continue
        if not target.is_file():
            missing.append(f"{path.relative_to(ROOT)}: {spec}")
    assert missing == []


def test_json_imports_point_at_dashboard_data_and_are_staged():
    stage = load_stage()
    names = set()
    for path, spec, target in stage.relative_imports(FUNCTIONS):
        if not spec.endswith(".json"):
            continue
        assert target.parent == DATA.resolve(), f"{path.relative_to(ROOT)}: {spec} -> {target}"
        names.add(target.name)
        # Same specifier, staged beside the functions copy instead of dashboard/.
        relative = path.relative_to(FUNCTIONS)
        staged = (Path("/virtual/functions") / relative).parent / spec
        assert staged.resolve() == (Path("/virtual/data") / target.name).resolve()
    assert names == set(stage.FUNCTION_JSON)


def test_stage_copies_imported_json_beside_functions(tmp_path):
    stage = load_stage()
    repo = tmp_path / "repo"
    functions = repo / "dashboard" / "functions" / "api" / "v1" / "research"
    functions.mkdir(parents=True)
    data = repo / "dashboard" / "data"
    data.mkdir(parents=True)
    (functions / "overlap.js").write_text(
        'import holdings from "../../../../data/overlap_holdings.json" with { type: "json" };\n',
        encoding="utf-8",
    )
    for name in stage.FUNCTION_JSON:
        (data / name).write_text("{}", encoding="utf-8")
    dest = tmp_path / "staged"
    stage.stage(repo, dest)
    copied = dest / "functions" / "api" / "v1" / "research" / "overlap.js"
    assert copied.is_file()
    for name in stage.FUNCTION_JSON:
        assert (dest / "data" / name).read_text(encoding="utf-8") == "{}"
    resolved = (copied.parent / "../../../../data/overlap_holdings.json").resolve()
    assert resolved == (dest / "data" / "overlap_holdings.json").resolve()


def test_stage_refuses_to_overwrite_the_source_tree(tmp_path):
    stage = load_stage()
    repo = tmp_path / "repo"
    (repo / "dashboard" / "functions").mkdir(parents=True)
    (repo / "dashboard" / "data").mkdir()
    for name in stage.FUNCTION_JSON:
        (repo / "dashboard" / "data" / name).write_text("{}", encoding="utf-8")
    try:
        stage.stage(repo, repo / "dashboard")
    except ValueError as error:
        assert "source tree" in str(error)
    else:
        raise AssertionError("stage() should refuse to write into dashboard/")
