#!/usr/bin/env python3
"""Stage the Pages Functions tree Wrangler bundles.

Wrangler compiles ``<dest>/functions`` as its own module root. The deploy
used to copy only ``dashboard/functions`` into that directory. Routes import
``_lib`` with a relative path that stays inside the tree. Two routes also
import JSON from ``dashboard/data``, one directory above ``dashboard/functions``:

- ``functions/api/v1/research/overlap.js`` imports
  ``../../../../data/overlap_holdings.json``
- ``functions/api/v1/sleeves/time-average.js`` imports
  ``../../../../data/time_average_growth_params.json``
- ``functions/_lib/owner_residual.js`` imports
  ``../../data/etf_ls_universe.json``

From the repo those paths land on ``dashboard/data/<file>``, which is where
the builders write them and where Node resolves them for the function tests.
From the staged tree the same paths land on ``<dest>/data/<file>``. Those
files have to be copied there or the Pages bundle cannot resolve them.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FUNCTION_JSON = (
    "overlap_holdings.json",
    "time_average_growth_params.json",
    "etf_ls_universe.json",
)
IMPORT_RE = re.compile(r"""from\s+["'](\.[^"']+)["']""")


def relative_imports(functions_dir: Path) -> list[tuple[Path, str, Path]]:
    found: list[tuple[Path, str, Path]] = []
    for path in sorted(functions_dir.rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        for spec in IMPORT_RE.findall(text):
            found.append((path, spec, (path.parent / spec).resolve()))
    return found


def stage(repo_root: Path, dest: Path) -> None:
    repo_root = repo_root.resolve()
    dest = dest.resolve()
    functions_src = repo_root / "dashboard" / "functions"
    data_src = repo_root / "dashboard" / "data"
    functions_dest = dest / "functions"
    if (
        dest in {repo_root, functions_src, data_src}
        or functions_dest == functions_src
        or functions_src in dest.parents
        or data_src in dest.parents
    ):
        raise ValueError(f"refusing to stage into the source tree: {dest}")
    missing = [name for name in FUNCTION_JSON if not (data_src / name).is_file()]
    if missing:
        raise FileNotFoundError(f"missing Pages function data: {', '.join(missing)}")
    dest.mkdir(parents=True, exist_ok=True)
    if functions_dest.exists():
        shutil.rmtree(functions_dest)
    shutil.copytree(functions_src, functions_dest)
    data_dest = dest / "data"
    data_dest.mkdir(parents=True, exist_ok=True)
    for name in FUNCTION_JSON:
        shutil.copy2(data_src / name, data_dest / name)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: stage_pages_functions.py DEST", file=sys.stderr)
        return 2
    stage(ROOT, Path(args[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
