#!/usr/bin/env python3
"""Fetch thematic macro / industry indicator panels (context layer).

Broadly ingested context (FRED, Stooq, EIA, repo filings) consumed narrowly by
tagged holdings via apply_context_overlay.py. Tailwinds inform stance and
overlay sizing only; they never auto-inflate Lawrence base IRR.

  python3 _system/scripts/fetch_theme_panel.py            # fetch all themes
  python3 _system/scripts/fetch_theme_panel.py --theme ai_power_land
  python3 _system/scripts/fetch_theme_panel.py --offline   # recompute manifest from cached CSVs only

Network failures degrade gracefully: cached CSV history is kept and the last
known value is reused, with an error note in the manifest.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
CONFIG = SCRIPTS / "theme_panel_config.json"
THEMES_DIR = ROOT / "_system" / "reference" / "market-data" / "themes"
UA = "MarvinResearch/1.0 (theme-panel)"
TODAY = date.today().isoformat()

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
STOOQ_DAILY_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"

HYPERSCALERS = ("GOOGL", "AMZN", "META", "MSFT")


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _http_get(url: str, timeout: int = 30) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def fetch_fred(fred_id: str) -> tuple[list[tuple[str, float]], str | None]:
    raw = _http_get(FRED_URL.format(id=fred_id))
    if raw is None:
        return [], "network"
    rows: list[tuple[str, float]] = []
    for line in raw.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[1].strip()
        if not d or v in ("", "."):
            continue
        try:
            rows.append((d, float(v)))
        except ValueError:
            continue
    return rows, (None if rows else "empty")


def fetch_stooq_daily(symbol: str) -> tuple[list[tuple[str, float]], str | None]:
    raw = _http_get(STOOQ_DAILY_URL.format(symbol=symbol.lower()))
    if raw is None:
        return [], "network"
    rows: list[tuple[str, float]] = []
    for line in raw.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        d = parts[0].strip()
        try:
            close = float(parts[4].strip())
        except ValueError:
            continue
        if d:
            rows.append((d, close))
    return rows, (None if rows else "empty")


def fetch_eia(route: str, facets: dict | None) -> tuple[list[tuple[str, float]], str | None]:
    key = os.environ.get("EIA_API_KEY")
    if not key:
        return [], "no_eia_key"
    params = [f"api_key={key}", "frequency=monthly", "data[0]=value", "sort[0][column]=period", "sort[0][direction]=desc", "length=60"]
    for k, v in (facets or {}).items():
        params.append(f"facets[{k}][]={v}")
    url = f"https://api.eia.gov/v2/{route}/data/?" + "&".join(params)
    raw = _http_get(url)
    if raw is None:
        return [], "network"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return [], "bad_json"
    rows: list[tuple[str, float]] = []
    for rec in (payload.get("response") or {}).get("data") or []:
        d = str(rec.get("period") or "")
        val = rec.get("value")
        if d and val is not None:
            try:
                rows.append((d, float(val)))
            except (ValueError, TypeError):
                continue
    rows.sort()
    return rows, (None if rows else "empty")


def hyperscaler_capex_guide() -> tuple[list[tuple[str, float]], str | None, list[str]]:
    """Sum latest disclosed annual capex guide across hyperscalers from ai_overlay.

    Source of truth is each ticker's research/valuation.json (filing-cited), so no
    external fetch and no fabricated numbers.
    """
    import re

    total = 0.0
    contributors: list[str] = []
    for tk in HYPERSCALERS:
        vp = ROOT / tk / "research" / "valuation.json"
        if not vp.exists():
            continue
        try:
            val = json.loads(vp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        ov = val.get("ai_overlay") or {}
        capex_bn = None
        stress = ov.get("capex_stress_2026") or {}
        if isinstance(stress.get("capex_bn"), (int, float)):
            capex_bn = float(stress["capex_bn"])
        if capex_bn is None:
            guide = ((ov.get("in_model") or {}).get("capex_2026_guide")) or ""
            nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(guide))]
            if nums:
                capex_bn = max(nums)
        if capex_bn is not None:
            total += capex_bn
            contributors.append(f"{tk}:{capex_bn:.0f}")
    if not contributors:
        return [], "no_overlay_data", []
    return [(TODAY, round(total, 1))], None, contributors


def read_cached_csv(path: Path) -> list[tuple[str, float]]:
    if not path.exists():
        return []
    rows: list[tuple[str, float]] = []
    with path.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for r in reader:
            if len(r) < 2:
                continue
            try:
                rows.append((r[0], float(r[1])))
            except ValueError:
                continue
    return rows


def write_csv(path: Path, rows: list[tuple[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "value"])
        for d, v in rows:
            w.writerow([d, v])


def yoy(rows: list[tuple[str, float]]) -> tuple[float | None, float | None, float | None]:
    """Return (latest, prior_year_value, yoy_pct)."""
    if not rows:
        return None, None, None
    rows = sorted(rows)
    latest_date, latest_val = rows[-1]
    try:
        ld = datetime.strptime(latest_date[:10], "%Y-%m-%d").date()
    except ValueError:
        ld = None
    prior = None
    if ld is not None:
        best_gap = None
        for d, v in rows[:-1]:
            try:
                dd = datetime.strptime(d[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            gap = abs((ld - dd).days - 365)
            if (ld - dd).days >= 250 and (best_gap is None or gap < best_gap):
                best_gap, prior = gap, v
    pct = None
    if prior not in (None, 0):
        pct = round(100.0 * (latest_val - prior) / abs(prior), 1)
    return latest_val, prior, pct


def direction(pct: float | None) -> str:
    if pct is None:
        return "flat"
    if pct > 1.0:
        return "up"
    if pct < -1.0:
        return "down"
    return "flat"


def process_series(spec: dict, offline: bool) -> dict:
    sid = spec["id"]
    src = spec.get("source")
    csv_path = THEMES_DIR / f"{sid}.csv"
    cached = read_cached_csv(csv_path)
    rows: list[tuple[str, float]] = []
    err: str | None = None
    extra: dict = {}

    if offline:
        rows, err = cached, (None if cached else "offline_no_cache")
    elif src == "fred":
        rows, err = fetch_fred(spec["fred_id"])
    elif src == "stooq_daily":
        rows, err = fetch_stooq_daily(spec["stooq"])
    elif src == "eia":
        rows, err = fetch_eia(spec.get("eia_route", ""), spec.get("eia_facets"))
    elif src == "repo_valuation":
        rows, err, contributors = hyperscaler_capex_guide()
        if contributors:
            extra["contributors"] = contributors
    else:
        err = f"unknown_source:{src}"

    if not rows and cached:
        rows = cached
        err = err or "reused_cache"
    if rows:
        # Merge new observations into cached history without dropping older points.
        merged = {d: v for d, v in cached}
        merged.update({d: v for d, v in rows})
        rows = sorted(merged.items())
        write_csv(csv_path, rows)

    latest_val, prior_val, pct = yoy(rows)
    latest_date = rows[-1][0] if rows else None
    stale = True
    if latest_date:
        try:
            ld = datetime.strptime(latest_date[:10], "%Y-%m-%d").date()
            stale = (date.today() - ld).days > spec.get("staleness_max_days", 45)
        except ValueError:
            stale = True

    source_label = {
        "fred": f"fred:{spec.get('fred_id')}",
        "stooq_daily": f"stooq:{spec.get('stooq')}",
        "eia": f"eia:{spec.get('eia_route')}",
        "repo_valuation": "repo:valuation.json/ai_overlay",
    }.get(src, str(src))

    out = {
        "label": spec.get("label", sid),
        "latest": latest_val,
        "as_of": latest_date,
        "prior_year": prior_val,
        "yoy_pct": pct,
        "direction": direction(pct),
        "good_for": spec.get("good_for"),
        "source": source_label,
        "optional": bool(spec.get("optional")),
        "stale": stale,
        "error": err,
        "note": spec.get("note"),
    }
    out.update(extra)
    return out


def build(theme_filter: str | None, offline: bool) -> dict:
    cfg = load_config()
    THEMES_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": TODAY,
        "staleness_max_days": cfg.get("staleness_max_days", 10),
        "disclaimer": "Context only. Tailwinds inform stance and overlay sizing; never auto-inflate Lawrence base IRR (human review promotes to base).",
        "themes": {},
    }
    for theme_id, theme in (cfg.get("themes") or {}).items():
        if theme_filter and theme_id != theme_filter:
            continue
        series_out: dict = {}
        for spec in theme.get("series") or []:
            spec = {**spec, "staleness_max_days": spec.get("staleness_max_days", cfg.get("staleness_max_days", 45))}
            res = process_series(spec, offline)
            series_out[spec["id"]] = res
            flag = "STALE" if res["stale"] else "ok"
            print(f"  [{theme_id}] {spec['id']}: latest={res['latest']} yoy={res['yoy_pct']}% {flag} err={res['error']}")
        manifest["themes"][theme_id] = {
            "label": theme.get("label"),
            "description": theme.get("description"),
            "series": series_out,
        }
    (THEMES_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", help="Only refresh one theme id")
    ap.add_argument("--offline", action="store_true", help="Recompute manifest from cached CSVs only")
    args = ap.parse_args()
    build(args.theme, args.offline)
    print(f"Theme panel manifest written to {THEMES_DIR / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
