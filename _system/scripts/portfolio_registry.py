#!/usr/bin/env python3
"""Shared helpers for portfolio registry.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
CLASS_PATH = ROOT / "_system" / "portfolio" / "classification.json"
HOLDINGS_PATH = ROOT / "_system" / "portfolio" / "holdings.md"
US_CONFIG_PATH = ROOT / "_system" / "scripts" / "us_ticker_config.json"

EXCHANGE_META = {
    "8697.T": "TSE",
    "319A.T": "TSE",
    "3905.T": "TSE",
    "7176.T": "TSE",
    "AMZN": "NASDAQ",
    "APLD": "NASDAQ",
    "BN": "NYSE",
    "CPRT": "NASDAQ",
    "CSGP": "NASDAQ",
    "CSU": "TSX",
    "DHR": "NYSE",
    "FRMO": "OTC",
    "HNFSA": "OTC Pink",
    "WRLC": "OTC Pink",
    "PDER": "OTC Pink",
    "BVERS": "OTC Pink",
    "GCCO": "OTC Pink",
    "CKX": "NYSE American",
    "GOOGL": "NASDAQ",
    "ICE": "NYSE",
    "KEWL": "OTC Pink",
    "OTCM": "OTCQX",
    "QDEL": "NASDAQ",
    "SJT": "NYSE",
    "SPGI": "NYSE",
    "TEQ.ST": "Nasdaq First North",
    "SPIE.PA": "Euronext Paris",
    "UMG.AS": "Euronext Amsterdam",
    "BRKN.SW": "SIX",
    "EVO.ST": "Nasdaq Stockholm",
    "WBI": "NYSE",
    "HE": "NYSE",
    "HEI": "NYSE",
    "MIAX": "NYSE",
    "FNV": "NYSE",
    "WPM": "NYSE",
    "PBT": "NYSE",
    "CBOE": "CBOE",
    "CME": "CME",
    "OR": "NYSE",
    "TRC": "NYSE",
    "HKHC": "OTCQX",
    "MRSH": "NYSE",
    "DMLP": "NASDAQ",
    "GLXY": "NASDAQ",
    "BKRB": "NYSE",
    "MSTR": "NASDAQ",
    "RPRX": "NASDAQ",
    "RGLD": "NASDAQ",
    "SBR": "NYSE",
    "PCYO": "NASDAQ",
    "BUR": "NYSE",
    "ALS.TO": "TSX",
    "PSK.TO": "TSX",
    "ADN.TO": "TSX",
    "RYN": "NYSE",
    "PCH": "NASDAQ",
    "LAND": "NASDAQ",
    "IEX.NS": "NSE",
    "DRR.AX": "ASX",
    "IDA.AX": "ASX",
    "LSEG": "LSE",
    "PSH": "LSE",
    "CEE": "NYSE",
    "NAN": "NYSE",
    "URB.A.TO": "TSX",
    "DC.A.TO": "TSX",
    "RMV.L": "LSE",
    "0388.HK": "HKEX",
    "ABX": "NASDAQ",
    "ASX.AX": "ASX",
    "B3SA3.SA": "B3",
    "BMYS.KL": "KLSE",
    "BOLSAA.MX": "BMV",
    "BSM": "NYSE",
    "BYMA": "BYMA",
    "CDZI": "NASDAQ",
    "DB1.DE": "XETRA",
    "ENX.PA": "Euronext Paris",
    "SU.PA": "Euronext Paris",
    "RMS.PA": "Euronext Paris",
    "SAF.PA": "Euronext Paris",
    "AIR.PA": "Euronext Paris",
    "AENA.MC": "BME Madrid",
    "CLNX.MC": "BME Madrid",
    "CP": "NYSE",
    "CNI": "NYSE",
    "FER": "NASDAQ",
    "TIPT": "NASDAQ",
    "VNOM": "NASDAQ",
    "LGND": "NASDAQ",
    "LIF.TO": "TSX",
    "FRU.TO": "TSX",
    "TPZ.TO": "TSX",
    "EVR": "CSE",
    "GPW.WA": "WSE",
    "DNP.WA": "WSE",
    "GROY": "NYSE American",
    "HEE": "ATHEX",
    "KRP": "NYSE",
    "MTA": "NYSE American",
    "NDAQ": "NASDAQ",
    "NRP": "NYSE",
    "NZX.NZ": "NZX",
    "PSE": "PSE",
    "S68.SI": "SGX",
    "TASE": "TASE",
    "TFPM": "NYSE",
    "X.TO": "TSX",
    "XP": "NASDAQ",
    "TOI.V": "TSXV",
    "RX.V": "TSXV",
    "1211.HK": "HKEX",
    "LIFCO.ST": "Nasdaq Stockholm",
    "RACE": "NYSE",
    "WCN": "NYSE",
    "MKL": "NYSE",
    "0700.HK": "HKEX",
    "MBGL": "NYSE",
}

DOWNLOAD_TYPE_OVERRIDES = {
    "QDEL": "us_dedicated",
    "CSU": "ca_csu",
    "TEQ.ST": "eu_teq",
    "EVO.ST": "uk_ir",
    "8697.T": "jp_ps1",
    "3905.T": "jp_archive",
    "7176.T": "jp_archive",
    "IEX.NS": "in_ir",
    "DRR.AX": "au_asx",
    "IDA.AX": "au_asx",
    "LSEG": "uk_ir",
    "PSH": "uk_ir",
    "URB.A.TO": "uk_ir",
    "RMV.L": "uk_ir",
    "0388.HK": "uk_ir",
    "B3SA3.SA": "uk_ir",
    "BMYS.KL": "uk_ir",
    "BOLSAA.MX": "uk_ir",
    "BYMA": "uk_ir",
    "DB1.DE": "uk_ir",
    "ENX.PA": "uk_ir",
    "EVR": "uk_ir",
    "GPW.WA": "uk_ir",
    "DNP.WA": "uk_ir",
    "HEE": "uk_ir",
    "NZX.NZ": "au_asx",
    "PSE": "uk_ir",
    "S68.SI": "uk_ir",
    "TASE": "uk_ir",
    "X.TO": "uk_ir",
    "ASX.AX": "au_asx",
    "RX.V": "uk_ir",
    "1211.HK": "uk_ir",
    "0700.HK": "uk_ir",
}


def infer_market_from_ticker(ticker: str) -> str | None:
    """Suffix-based market when onboarding without explicit --market."""
    if ticker.endswith(".NS"):
        return "IN"
    if ticker.endswith(".T"):
        return "JP"
    if ticker.endswith(".AX"):
        return "AU"
    if ticker.endswith(".NZ"):
        return "AU"
    if ticker.endswith(".TO"):
        return "CA"
    if ticker.endswith(".HK"):
        return "EU"
    if ticker.endswith((".DE", ".PA", ".WA", ".SA", ".MX", ".KL", ".SI", ".AS", ".SW", ".MC")):
        return "EU"
    if ticker.endswith(".L"):
        return "UK"
    if ticker == "LSEG":
        return "UK"
    return None


DEFAULT_CLASSIFICATION = {
    "archetype": "unknown",
    "moat": "unproven",
    "dhando": "pending",
    "stance": "watch",
    "cycle": "-",
    "moi_bucket": "pending",
    "payoff_lens": "pending",
    "investment_sleeve": "-",
}


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"meta": {"version": 1}, "holdings": {}, "watchlist": {}}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(data: dict) -> None:
    data.setdefault("meta", {})
    data["meta"]["version"] = 1
    data["meta"]["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def infer_download_type(ticker: str, market: str, us_config: dict) -> str:
    if ticker in DOWNLOAD_TYPE_OVERRIDES:
        return DOWNLOAD_TYPE_OVERRIDES[ticker]
    if market in {"US", "CA"} and ticker in us_config:
        return "us_shared"
    if market == "US":
        return "us_shared"
    if market == "CA":
        return "ca_csu"
    if market in {"SE", "EU"}:
        return "uk_ir"
    if market == "IN":
        return "in_ir"
    if market == "UK":
        return "uk_ir"
    if market == "AU":
        return "au_asx"
    if market == "JP":
        return "jp_ps1"
    return "us_shared"


def build_download_block(ticker: str, market: str, us_config: dict) -> dict:
    dtype = infer_download_type(ticker, market, us_config)
    block: dict = {"type": dtype}
    cfg = us_config.get(ticker, {})
    if cfg:
        if cfg.get("cik"):
            block["cik"] = str(cfg["cik"])
        if cfg.get("ir_roots"):
            block["ir_roots"] = list(cfg["ir_roots"])
        opts = {}
        for key in ("min_filing_date", "sec_any_recent", "download_8k_exhibits"):
            if key in cfg:
                opts[key] = cfg[key]
        if opts:
            block["options"] = opts
    return block


# Ownership is not a research stance. `classification.stance` stays
# core / accumulate / hold / watch / trim / exit. The owned group records
# which accounts hold a long equity, without share counts or market values.
OWNED_GROUP_ID = "owned"
OWNED_SCHEMA = "owned_holdings_group_v1"
OWNED_ROLES = {"long", "short_option_only"}
OWNED_SIZE_KEYS = {
    "shares",
    "share_count",
    "quantity",
    "qty",
    "contracts",
    "contract_count",
    "notional",
    "notional_usd",
    "market_value",
    "market_value_usd",
    "cost",
    "cost_basis",
    "weight",
    "weight_pct",
    "dollars",
    "dollar_value",
    "multiplier",
}
def owned_group(reg: dict | None) -> dict:
    groups = (reg or {}).get("groups") or {}
    group = groups.get(OWNED_GROUP_ID) or {}
    return group if isinstance(group, dict) else {}


def _walk_keys(value, prefix: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, key
            yield from _walk_keys(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_keys(child, f"{prefix}[{index}]")


def tracking_groups_of(holding: dict | None) -> list[str]:
    raw = (holding or {}).get("tracking_groups") or []
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def owned_long_tickers(reg: dict | None) -> list[str]:
    members = owned_group(reg).get("members") or {}
    if not isinstance(members, dict):
        return []
    return sorted(
        ticker
        for ticker, row in members.items()
        if isinstance(row, dict) and row.get("role") == "long"
    )


def is_owned_long_holding(holding: dict | None) -> bool:
    return OWNED_GROUP_ID in tracking_groups_of(holding)


def stamp_owned_tracking_groups(reg: dict) -> list[str]:
    """Denormalize long membership onto each holding.

    Pipelines that already walk `holdings` can see the group without reading
    `groups.owned`. Stance is left untouched. Returns the long tickers.
    """
    holdings = reg.setdefault("holdings", {})
    longs = set(owned_long_tickers(reg))
    for ticker, holding in holdings.items():
        if not isinstance(holding, dict):
            continue
        groups = [item for item in tracking_groups_of(holding) if item != OWNED_GROUP_ID]
        if ticker in longs:
            groups.append(OWNED_GROUP_ID)
            holding["tracking_groups"] = groups
        elif "tracking_groups" in holding:
            if groups:
                holding["tracking_groups"] = groups
            else:
                holding.pop("tracking_groups", None)
    return sorted(longs)


def owned_views_by_ticker(reg: dict | None) -> dict[str, dict]:
    """Public per-ticker view. Account labels only. No sizes."""
    group = owned_group(reg)
    accounts = group.get("accounts") or {}
    if not isinstance(accounts, dict):
        accounts = {}
    members = group.get("members") or {}
    if not isinstance(members, dict):
        return {}
    views: dict[str, dict] = {}
    for ticker in sorted(members):
        member = members[ticker]
        if not isinstance(member, dict):
            continue
        options = []
        for opt in member.get("short_options") or []:
            if not isinstance(opt, dict):
                continue
            account_id = str(opt.get("account") or "")
            label = (accounts.get(account_id) or {}).get("label") or account_id
            options.append(
                {
                    "account": account_id,
                    "account_label": label,
                    "side": opt.get("side"),
                    "right": opt.get("right"),
                    "strike": opt.get("strike"),
                    "expiry": opt.get("expiry"),
                }
            )
        account_ids = [str(item) for item in (member.get("accounts") or [])]
        views[str(ticker)] = {
            "group": OWNED_GROUP_ID,
            "role": member.get("role"),
            "as_of": group.get("as_of"),
            "accounts": [
                {
                    "id": account_id,
                    "label": (accounts.get(account_id) or {}).get("label") or account_id,
                }
                for account_id in account_ids
            ],
            "broker_symbols": [str(item) for item in (member.get("broker_symbols") or [])],
            "short_options": options,
        }
    return views


def owned_dashboard_overlay(reg: dict | None) -> dict:
    group = owned_group(reg)
    accounts = group.get("accounts") or {}
    if not isinstance(accounts, dict):
        accounts = {}
    hedges = []
    for row in group.get("short_hedges") or []:
        if not isinstance(row, dict):
            continue
        account_id = str(row.get("account") or "")
        hedges.append(
            {
                "account": account_id,
                "account_label": (accounts.get(account_id) or {}).get("label") or account_id,
                "broker_symbol": row.get("broker_symbol"),
                "role": "short_hedge",
                "onboard": False,
            }
        )
    views = owned_views_by_ticker(reg)
    return {
        "schema": OWNED_SCHEMA,
        "group": OWNED_GROUP_ID,
        "as_of": group.get("as_of"),
        "purpose": group.get("purpose"),
        "long_count": sum(1 for view in views.values() if view.get("role") == "long"),
        "coverage_notes": list(group.get("coverage_notes") or []),
        "symbol_aliases": dict(group.get("symbol_aliases") or {}),
        "by_ticker": views,
        "short_hedges": hedges,
    }


def validate_owned_group(reg: dict | None) -> list[str]:
    """Return human-readable errors. Empty means the public group is safe to publish."""
    errors: list[str] = []
    group = owned_group(reg)
    if not group:
        return ["groups.owned is missing"]
    if group.get("schema") != OWNED_SCHEMA:
        errors.append(f"groups.owned.schema must be {OWNED_SCHEMA}")
    for path, key in _walk_keys(group):
        if str(key).lower() in OWNED_SIZE_KEYS:
            errors.append(f"groups.owned size field not allowed: {path}")
    accounts = group.get("accounts") or {}
    if not isinstance(accounts, dict) or not accounts:
        errors.append("groups.owned.accounts must be a non-empty object")
        accounts = {}
    account_ids = set(accounts)
    for account_id, account in accounts.items():
        if not isinstance(account, dict) or not str(account.get("label") or "").strip():
            errors.append(f"account {account_id} needs a public label")
    holdings = (reg or {}).get("holdings") or {}
    members = group.get("members") or {}
    if not isinstance(members, dict) or not members:
        errors.append("groups.owned.members must be a non-empty object")
        members = {}
    long_tickers = []
    for ticker, member in members.items():
        if not isinstance(member, dict):
            errors.append(f"{ticker} member must be an object")
            continue
        role = member.get("role")
        if role not in OWNED_ROLES:
            errors.append(f"{ticker} role must be long or short_option_only")
            continue
        member_accounts = member.get("accounts") or []
        if not isinstance(member_accounts, list):
            errors.append(f"{ticker} accounts must be a list")
            member_accounts = []
        unknown = [item for item in member_accounts if item not in account_ids]
        if unknown:
            errors.append(f"{ticker} references unknown accounts: {unknown}")
        if role == "long":
            long_tickers.append(ticker)
            if not member_accounts:
                errors.append(f"{ticker} long member needs at least one account")
            if ticker not in holdings:
                errors.append(f"{ticker} long member is not in registry holdings")
            else:
                groups = tracking_groups_of(holdings.get(ticker))
                if OWNED_GROUP_ID not in groups:
                    errors.append(f"{ticker} long member is missing tracking_groups owned")
        else:
            if member_accounts:
                errors.append(f"{ticker} short_option_only member must not be listed as a long account")
            if not member.get("short_options"):
                errors.append(f"{ticker} short_option_only member needs a short option flag")
        for opt in member.get("short_options") or []:
            if not isinstance(opt, dict):
                errors.append(f"{ticker} short option flag must be an object")
                continue
            if opt.get("account") not in account_ids:
                errors.append(f"{ticker} short option uses an unknown account")
            if opt.get("side") != "short" or opt.get("right") not in {"put", "call"}:
                errors.append(f"{ticker} short option flag needs side short and right put or call")
            if not opt.get("expiry"):
                errors.append(f"{ticker} short option flag needs an expiry")
    for ticker, holding in holdings.items():
        if is_owned_long_holding(holding) and ticker not in long_tickers:
            errors.append(f"{ticker} has tracking_groups owned but is not a long member")
    aliases = group.get("symbol_aliases") or {}
    if not isinstance(aliases, dict):
        errors.append("symbol_aliases must be an object")
        aliases = {}
    for broker, registry_ticker in aliases.items():
        if registry_ticker not in long_tickers:
            errors.append(f"alias {broker} does not point at a long member")
        if registry_ticker not in holdings:
            errors.append(f"alias {broker} -> {registry_ticker} is not a registry holding")
    hedges = group.get("short_hedges") or []
    if not isinstance(hedges, list):
        errors.append("short_hedges must be a list")
        hedges = []
    for row in hedges:
        if not isinstance(row, dict):
            errors.append("short hedge must be an object")
            continue
        symbol = str(row.get("broker_symbol") or "")
        if row.get("onboard") is not False:
            errors.append(f"{symbol} short hedge must set onboard false")
        if row.get("role") != "short_hedge":
            errors.append(f"{symbol} short hedge role must be short_hedge")
        if row.get("account") not in account_ids:
            errors.append(f"{symbol} short hedge uses an unknown account")
        if symbol in holdings or symbol in members:
            errors.append(f"{symbol} short hedge must not be onboarded as a holding")
    return errors
