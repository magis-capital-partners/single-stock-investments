"""Load sleeve YAML and JSON snapshots."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from . import PKG_DIR
from .etf_0dte_delivery import DEFAULT_MAX_AGE_DAYS, read_expected_delivery


def apply_ibkr_env(cfg: dict[str, Any]) -> dict[str, Any]:
    """Same knobs as ls-algo / SPX 0DTE: host, port, account from the environment."""
    ibkr = dict(cfg.get("ibkr") or {})
    host = os.environ.get("IBKR_HOST") or os.environ.get("TWS_HOST")
    port = os.environ.get("IBKR_PORT") or os.environ.get("TWS_PORT")
    account = os.environ.get("IBKR_ACCOUNT") or os.environ.get("IBKR_ACCOUNT_ID")
    if host:
        ibkr["host"] = host.strip()
    if port:
        ibkr["live_port"] = int(port)
    if account:
        ibkr["account_id"] = account.strip()
    cfg["ibkr"] = ibkr
    ingest = dict(cfg.get("ingest") or {})
    url = os.environ.get("SLEEVE_INGEST_URL")
    if url:
        ingest["url"] = url.strip()
        cfg["ingest"] = ingest
    return cfg


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (PKG_DIR / "config.yaml")
    with cfg_path.open(encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    return apply_ibkr_env(cfg)


def _read_json(rel: str) -> dict[str, Any]:
    path = PKG_DIR / rel
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_blacklist(cfg: dict[str, Any] | None = None) -> set[str]:
    cfg = cfg or load_config()
    rel = str((cfg.get("paths") or {}).get("blacklist_json") or "data/blacklist.json")
    payload = _read_json(rel)
    return {str(s).strip().upper() for s in payload.get("underlyings") or [] if str(s).strip()}


def load_etf_to_under(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    cfg = cfg or load_config()
    rel = str((cfg.get("paths") or {}).get("etf_to_under_json") or "data/etf_to_under.json")
    payload = _read_json(rel)
    raw = payload.get("map") or {}
    return {str(k).strip().upper(): str(v).strip().upper() for k, v in raw.items() if str(k).strip() and str(v).strip()}


def load_etf_ls_universe(cfg: dict[str, Any] | None = None) -> set[str]:
    cfg = cfg or load_config()
    rel = str((cfg.get("paths") or {}).get("etf_ls_universe_json") or "data/etf_ls_universe.json")
    payload = _read_json(rel)
    return {str(s).strip().upper() for s in payload.get("symbols") or [] if str(s).strip()}


def load_etf_0dte_expected_delivery(
    cfg: dict[str, Any] | None = None, *, today: date | None = None,
) -> dict[str, float] | None:
    """spx-0dte's SPY / QQQ delivery forecast for the configured account, or None.

    The path is `etf_0dte.live_dir` (spx-0dte's `data/live` on this host), which
    `ETF_0DTE_LIVE_DIR` overrides. Unset, or no account, means no forecast: every
    SPY / QQQ share no other book is known to hold is then unattributed.
    """
    cfg = load_config() if cfg is None else cfg
    section = cfg.get("etf_0dte") or {}
    live_dir = os.environ.get("ETF_0DTE_LIVE_DIR") or section.get("live_dir")
    account = str((cfg.get("ibkr") or {}).get("account_id") or "").strip()
    max_age = section.get("forecast_max_age_days")
    return read_expected_delivery(
        live_dir,
        account,
        today=today,
        max_age_days=DEFAULT_MAX_AGE_DAYS if max_age is None else int(max_age),
    )


def load_etf_0dte_known_holdings(cfg: dict[str, Any] | None = None) -> dict[str, float]:
    """Signed SPY / QQQ shares another book is known to hold (they keep their bucket)."""
    cfg = load_config() if cfg is None else cfg
    raw = (cfg.get("etf_0dte") or {}).get("known_share_holdings") or {}
    return {str(k).strip().upper(): float(v) for k, v in raw.items() if str(k).strip()}


def operator_config(cfg: dict[str, Any], owner: str) -> dict[str, Any]:
    ops = cfg.get("operators") or {}
    if owner not in ops:
        raise KeyError(f"Unknown operator {owner!r}")
    return dict(ops[owner])
