"""Load the package configuration and resolve its paths.

The configuration lives beside the ledger at
``_system/data/reverse_splits/config.toml``. Entries under ``[paths]`` resolve
against that directory, so SQLite, raw caches and reports land in ``local/``
(ignored by git) while the JSONL ledger sits next to the file.
``[fundamentals].ssi_root`` resolves the same way; ``../../..`` is this
repository's root.

``RSDB_CONFIG`` in the environment points at an alternative configuration
file (tests and ad-hoc local runs).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = PACKAGE_DIR.parent
REPO_ROOT = SCRIPTS_DIR.parents[1]
DATA_DIR = REPO_ROOT / "_system" / "data" / "reverse_splits"
DEFAULT_CONFIG = DATA_DIR / "config.toml"
CONFIG_ENV = "RSDB_CONFIG"
# Kept for callers that imported ``ROOT`` from the original package.
ROOT = REPO_ROOT

_PATH_DEFAULTS = {
    "data_dir": ".",
    "ledger_dir": ".",
    "db_path": "local/reverse_splits.db",
    "decisions_db": "local/strategy_decisions.sqlite",
    "raw_dir": "local/raw",
    "edgar_cache": "local/raw/edgar",
    "finra_dir": "local/raw/finra",
    "ibkr_dir": "local/raw/ibkr",
    "databento_dir": "local/raw/databento",
    "reports_dir": "local/reports",
    "public_dir": "local/reports/public",
}


@dataclass
class Config:
    raw: dict[str, Any] = field(default_factory=dict)
    root: Path = DATA_DIR
    config_path: Path = DEFAULT_CONFIG

    def _path(self, key: str) -> Path:
        value = (self.raw.get("paths") or {}).get(key, _PATH_DEFAULTS[key])
        return Path(self.root) / str(value)

    @property
    def data_dir(self) -> Path:
        return self._path("data_dir")

    @property
    def local_dir(self) -> Path:
        """Ignored, reproducible research workbench; never truncate the ledger."""
        return self.db_path.parent

    @property
    def ledger_dir(self) -> Path:
        """Where the committed JSONL ledger lives (beside ``config.toml``)."""
        return self._path("ledger_dir")

    @property
    def db_path(self) -> Path:
        return self._path("db_path")

    @property
    def decisions_db_path(self) -> Path:
        return self._path("decisions_db")

    @property
    def raw_dir(self) -> Path:
        return self._path("raw_dir")

    @property
    def edgar_cache(self) -> Path:
        return self._path("edgar_cache")

    @property
    def finra_dir(self) -> Path:
        return self._path("finra_dir")

    @property
    def ibkr_dir(self) -> Path:
        return self._path("ibkr_dir")

    @property
    def databento_dir(self) -> Path:
        """Licensed Databento files. Local only: SSI is public."""
        return self._path("databento_dir")

    @property
    def reports_dir(self) -> Path:
        return self._path("reports_dir")

    @property
    def public_dir(self) -> Path:
        """Stand-in for the old repository's ``docs/data``: snapshot JSON and rerun outputs."""
        return self._path("public_dir")

    @property
    def repo_root(self) -> Path:
        """The SSI repository root (``[fundamentals].ssi_root``, relative to the config file)."""
        value = (self.raw.get("fundamentals") or {}).get("ssi_root")
        if not value:
            return REPO_ROOT
        path = Path(str(value))
        if not path.is_absolute():
            path = Path(self.config_path).parent / path
        return path.resolve()

    @property
    def dashboard_path(self) -> Path:
        return self.repo_root / "dashboard" / "data" / "reverse_splits.json"

    def ensure_dirs(self) -> None:
        for p in (
            self.data_dir,
            self.raw_dir,
            self.edgar_cache,
            self.finra_dir,
            self.ibkr_dir,
            self.reports_dir,
            self.public_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)

    def section(self, name: str) -> dict[str, Any]:
        return dict(self.raw.get(name, {}))


def load_config(path: Path | str | None = None, *, ensure_dirs: bool = True) -> Config:
    cfg_path = Path(path or os.environ.get(CONFIG_ENV) or DEFAULT_CONFIG).resolve()
    with cfg_path.open("rb") as f:
        raw = tomllib.load(f)
    cfg = Config(raw=raw, root=cfg_path.parent, config_path=cfg_path)
    if ensure_dirs:
        cfg.ensure_dirs()
    return cfg
