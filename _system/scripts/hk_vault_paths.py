"""Shared HK vault path resolution for scan and extract refresh."""
from __future__ import annotations

import json
import os
from pathlib import Path

from vault_paths import wisdom_ref, wisdom_root

ROOT = Path(__file__).resolve().parents[2]
WISDOM = wisdom_root()
PATHS_PATH = WISDOM / "hk_paths.json"


def load_paths_cfg() -> dict:
    if PATHS_PATH.is_file():
        return json.loads(PATHS_PATH.read_text(encoding="utf-8"))
    return {
        "hk_pdfs_root_env": "HK_PDFS_ROOT",
        "hk_pdfs_root_cloud_default": "/opt/cursor/hk_pdfs",
        "vault_text_subdir": "book/build/text",
        "in_repo_extracts": wisdom_ref("horizon-kinetics"),
    }


def resolve_vault_root(paths_cfg: dict | None = None) -> Path | None:
    cfg = paths_cfg or load_paths_cfg()
    env_key = cfg.get("hk_pdfs_root_env", "HK_PDFS_ROOT")
    if os.environ.get(env_key):
        p = Path(os.environ[env_key])
        return p if p.is_dir() else None

    vault = wisdom_root()
    hk_pdfs = vault / "horizon-kinetics" / "pdfs"
    if hk_pdfs.is_dir():
        return hk_pdfs

    cloud_default = cfg.get("hk_pdfs_root_cloud_default", "")
    if cloud_default:
        p = Path(cloud_default)
        if p.is_dir():
            return p
    win = cfg.get("hk_pdfs_root_windows", "")
    if win and Path(win).is_dir():
        return Path(win)
    return None


def vault_text_dir(vault_root: Path, paths_cfg: dict | None = None) -> Path:
    cfg = paths_cfg or load_paths_cfg()
    sub = cfg.get("vault_text_subdir", "book/build/text")
    return vault_root / sub


def in_repo_extracts_dir(paths_cfg: dict | None = None) -> Path:
    cfg = paths_cfg or load_paths_cfg()
    rel = cfg.get("in_repo_extracts", wisdom_ref("horizon-kinetics"))
    if rel.startswith("_system/"):
        return ROOT / rel
    return wisdom_root() / "horizon-kinetics"
