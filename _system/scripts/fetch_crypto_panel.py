#!/usr/bin/env python3
"""Fetch crypto network / stablecoin context panels into market-data/crypto/."""
from __future__ import annotations

import argparse
import csv
import json
import math
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
CONFIG = SCRIPTS / "crypto_panel_config.json"
CRYPTO_DIR = ROOT / "_system" / "reference" / "market-data" / "crypto"
UA = "MarvinResearch/1.0 (crypto-panel)"
TODAY = date.today().isoformat()
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
MEMPOOL = "https://mempool.space/api"
COINGECKO = "https://api.coingecko.com/api/v3"


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _get_json(url: str, timeout: int = 30) -> dict | list | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except Exception:
        return None


def read_csv_series(path: Path) -> list[tuple[str, float]]:
    if not path.exists():
        return []
    rows: list[tuple[str, float]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                rows.append((parts[0].strip(), float(parts[1])))
            except ValueError:
                continue
    rows.sort()
    return rows


def write_csv(path: Path, rows: list[tuple[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "value"])
        for d, v in sorted(rows):
            w.writerow([d, v])


def fetch_yahoo_daily(symbol: str) -> tuple[list[tuple[str, float]], str | None]:
    from datetime import timedelta

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=400)
    url = (
        f"{YAHOO_CHART_URL}/{symbol}?period1={int(start.timestamp())}"
        f"&period2={int(end.timestamp())}&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=25).read())
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except Exception:
        return [], "network"
    rows: list[tuple[str, float]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append((d, float(close)))
    rows.sort()
    return rows, (None if rows else "empty")


def fetch_mempool_hashrate(period: str = "1w") -> tuple[list[tuple[str, float]], str | None]:
    data = _get_json(f"{MEMPOOL}/v1/mining/hashrate/{period}")
    if not data or not isinstance(data, dict):
        return [], "network"
    rows: list[tuple[str, float]] = []
    for rec in data.get("hashrates") or []:
        if not isinstance(rec, dict):
            continue
        ts = rec.get("timestamp")
        hr = rec.get("avgHashrate")
        if ts is None or hr is None:
            continue
        d = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append((d, float(hr) / 1e18))
    if not rows and data.get("currentHashrate"):
        rows = [(TODAY, float(data["currentHashrate"]) / 1e18)]
    rows.sort()
    return rows, (None if rows else "empty")


def fetch_mempool_difficulty() -> tuple[list[tuple[str, float]], str | None]:
    data = _get_json(f"{MEMPOOL}/v1/mining/hashrate/1w")
    if not data or not isinstance(data, dict):
        return [], "network"
    try:
        diff = float(data.get("currentDifficulty") or 0)
        if diff <= 0:
            return [], "empty"
        return [(TODAY, diff)], None
    except (TypeError, ValueError):
        return [], "parse_error"


def fetch_mempool_fees_usd(btc_price: float) -> tuple[list[tuple[str, float]], str | None]:
    blocks = _get_json(f"{MEMPOOL}/blocks/tip/height")
    if not blocks:
        return [], "network"
    # use recommended fees * avg tx as rough proxy; fallback fixed estimate from mempool
    fees = _get_json(f"{MEMPOOL}/v1/fees/mempool-blocks")
    if not fees or not isinstance(fees, list):
        return [(TODAY, 0.05 * btc_price)], "estimate"
    total_fee_sat = 0
    n = 0
    for blk in fees[:6]:
        try:
            total_fee_sat += float(blk.get("totalFees") or 0)
            n += 1
        except (TypeError, ValueError):
            continue
    if n == 0:
        return [(TODAY, 0.05 * btc_price)], "estimate"
    avg_fee_btc = (total_fee_sat / n) / 1e8
    return [(TODAY, round(avg_fee_btc * btc_price, 4))], None


def fetch_coingecko(coin_id: str, metric: str) -> tuple[list[tuple[str, float]], str | None]:
    data = _get_json(f"{COINGECKO}/coins/{coin_id}?localization=false&tickers=false&community_data=false&developer_data=false")
    if not data:
        return [], "network"
    md = data.get("market_data") or {}
    if metric == "market_cap":
        val = (md.get("market_cap") or {}).get("usd")
    elif metric == "circulating_supply":
        val = md.get("circulating_supply")
        if val and (md.get("current_price") or {}).get("usd"):
            val = float(val) * float(md["current_price"]["usd"]) / 1e9
            return [(TODAY, round(val, 3))], None
    else:
        return [], "unknown_metric"
    if val is None:
        return [], "empty"
    return [(TODAY, round(float(val) / 1e9, 3))], None


def latest_from_rows(rows: list[tuple[str, float]]) -> tuple[float | None, str | None]:
    if not rows:
        return None, None
    d, v = rows[-1]
    return v, d


def yoy(rows: list[tuple[str, float]]) -> tuple[float | None, float | None]:
    if len(rows) < 2:
        return None, None
    latest_d, latest_v = rows[-1]
    try:
        target = date.fromisoformat(latest_d).replace(year=date.fromisoformat(latest_d).year - 1)
    except ValueError:
        return None, None
    prior = None
    for d, v in rows:
        if d <= target.isoformat():
            prior = v
    if prior is None or prior == 0:
        return None, None
    return prior, round(100.0 * (latest_v - prior) / abs(prior), 1)


def compute_hashprice(
    btc_price: float,
    hash_eh: float,
    fee_usd_per_block: float,
    subsidy_btc: float = 3.125,
) -> float:
    if hash_eh <= 0:
        return 0.0
    ph = hash_eh * 1e6
    blocks_per_day = 144.0
    daily_revenue = blocks_per_day * (subsidy_btc * btc_price + fee_usd_per_block)
    return round(daily_revenue / ph, 6)


def compute_breakeven_kwh(hashprice_ph_day: float, efficiency_j_th: float) -> float:
    hashprice_th_day = hashprice_ph_day / 1000.0
    kwh_per_th_day = (efficiency_j_th / 1000.0) * 24.0 / 1000.0
    if kwh_per_th_day <= 0:
        return 0.0
    return round(hashprice_th_day / kwh_per_th_day, 4)


def process_series(spec: dict, ctx: dict, offline: bool) -> dict:
    sid = spec["id"]
    src = spec.get("source")
    csv_path = CRYPTO_DIR / f"{sid}.csv"
    cached = read_csv_series(csv_path)
    rows: list[tuple[str, float]] = []
    err: str | None = None
    source_label = str(src)

    if offline:
        rows, err = cached, (None if cached else "offline_no_cache")
    elif src == "yahoo_daily":
        rows, err = fetch_yahoo_daily(spec.get("yahoo_symbol", ""))
        source_label = f"yahoo:{spec.get('yahoo_symbol')}"
    elif src == "mempool_hashrate":
        rows, err = fetch_mempool_hashrate(spec.get("period", "1w"))
        source_label = "mempool.space:hashrate"
    elif src == "mempool_difficulty":
        rows, err = fetch_mempool_difficulty()
        source_label = "mempool.space:difficulty"
    elif src == "mempool_fees":
        btc = ctx.get("btc_spot_usd") or 0.0
        rows, err = fetch_mempool_fees_usd(btc)
        source_label = "mempool.space:fees"
    elif src == "coingecko":
        rows, err = fetch_coingecko(spec.get("coin_id", ""), spec.get("metric", ""))
        source_label = f"coingecko:{spec.get('coin_id')}:{spec.get('metric')}"
    elif src == "computed_hashprice":
        hp = compute_hashprice(
            ctx.get("btc_spot_usd") or 0.0,
            ctx.get("btc_hash_rate_eh") or 0.0,
            ctx.get("btc_avg_fee_per_block_usd") or 0.0,
            float(ctx.get("block_subsidy_btc") or 3.125),
        )
        rows = [(TODAY, hp)]
        source_label = "computed:hashprice"
    elif src == "computed_breakeven":
        hp = ctx.get("btc_hashprice_usd_ph_day") or 0.0
        eff = float(spec.get("efficiency_j_th") or 30)
        rows = [(TODAY, compute_breakeven_kwh(hp, eff))]
        source_label = f"computed:breakeven_{eff}jth"
    else:
        err = f"unknown_source:{src}"

    if not rows and cached:
        rows = cached
        err = err or "reused_cache"
    if rows:
        merged = {d: v for d, v in cached}
        merged.update({d: v for d, v in rows})
        rows = sorted(merged.items())
        write_csv(csv_path, rows)

    latest, as_of = latest_from_rows(rows)
    prior, yoy_pct = yoy(rows)
    stale_days = int(spec.get("staleness_max_days") or 7)
    stale = False
    if as_of:
        try:
            stale = (date.today() - date.fromisoformat(as_of)).days > stale_days
        except ValueError:
            stale = True
    elif latest is None:
        stale = True

    if sid == "btc_spot_usd" and latest is not None:
        ctx["btc_spot_usd"] = latest
    if sid == "btc_hash_rate_eh" and latest is not None:
        ctx["btc_hash_rate_eh"] = latest
    if sid == "btc_avg_fee_per_block_usd" and latest is not None:
        ctx["btc_avg_fee_per_block_usd"] = latest
    if sid == "btc_hashprice_usd_ph_day" and latest is not None:
        ctx["btc_hashprice_usd_ph_day"] = latest

    direction = "flat"
    if isinstance(yoy_pct, (int, float)):
        if yoy_pct > 1.0:
            direction = "up"
        elif yoy_pct < -1.0:
            direction = "down"

    return {
        "label": spec.get("label"),
        "latest": latest,
        "as_of": as_of,
        "prior_year": prior,
        "yoy_pct": yoy_pct,
        "direction": direction,
        "good_for": spec.get("good_for"),
        "source": source_label,
        "optional": bool(spec.get("optional")),
        "stale": stale,
        "error": err,
        "note": spec.get("note"),
    }


def build(theme_filter: str | None = None, offline: bool = False) -> dict:
    cfg = load_config()
    ctx: dict = {"block_subsidy_btc": cfg.get("block_subsidy_btc", 3.125)}
    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": TODAY,
        "staleness_max_days": cfg.get("staleness_max_days", 7),
        "disclaimer": "Context only. Crypto metrics inform stance and overlays; never auto-inflate Lawrence base IRR.",
        "themes": {},
    }
    themes = cfg.get("themes") or {}
    for theme_id, theme in themes.items():
        if theme_filter and theme_id != theme_filter:
            continue
        series_out: dict = {}
        # pass 1: base series
        for spec in theme.get("series") or []:
            if spec.get("source", "").startswith("computed_"):
                continue
            series_out[spec["id"]] = process_series(spec, ctx, offline)
        # pass 2: computed
        for spec in theme.get("series") or []:
            if not spec.get("source", "").startswith("computed_"):
                continue
            series_out[spec["id"]] = process_series(spec, ctx, offline)
        manifest["themes"][theme_id] = {
            "label": theme.get("label"),
            "description": theme.get("description"),
            "series": series_out,
        }
    CRYPTO_DIR.mkdir(parents=True, exist_ok=True)
    (CRYPTO_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", help="Single theme id")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    build(args.theme, args.offline)
    print(f"Wrote {CRYPTO_DIR / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
