"""Dated miner-electricity proxy, not an observed global mining price index.

Use EIA US industrial monthly prices to index Cambridge's June-2024 survey
median ($45/MWh). Two-month release lag is an explicit approximation. Never
substitute residential tariffs or present this reconstruction as HK's series.
"""
from __future__ import annotations

import calendar
import csv
import io
import json
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CRYPTO_DIR = ROOT / "_system/reference/market-data/crypto"
EIA_URL = "https://www.eia.gov/totalenergy/data/browser/csv.php?tbl=T09.08"
SURVEY_URL = "https://www.jbs.cam.ac.uk/wp-content/uploads/2025/04/2025-04-cambridge-digital-mining-industry-report.pdf"
ANCHOR = "2024-06-30"
SURVEY_PUBLISHED = "2025-04-28"


def parse_eia(text: str, *, retrieved_on: date) -> list[dict]:
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        period = r.get("YYYYMM", "")
        if r.get("MSN") != "ESICUUS" or len(period) != 6 or period[4:] == "13":
            continue
        try:
            year, month = int(period[:4]), int(period[4:])
            value = float(r["Value"]) / 100
            observed = date(year, month, calendar.monthrange(year, month)[1])
        except (ValueError, KeyError):
            continue
        if year < 2015 or observed > retrieved_on or value <= 0:
            continue
        # Lag approximation, not a claim of point-in-time data vintages.
        release_month = month + 2
        available = date(year + (release_month - 1) // 12, (release_month - 1) % 12 + 1, 1)
        if available > retrieved_on:
            continue
        rows.append({"date": observed.isoformat(), "available_on": available.isoformat(),
                     "usd_kwh": value, "retrieved_on": retrieved_on.isoformat()})
    return sorted(rows, key=lambda r: r["date"])


def load_rows(directory: Path = CRYPTO_DIR) -> list[dict]:
    path = directory / "btc_power_eia_industrial.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def proxy_on(day: date, rows: list[dict]) -> float | None:
    anchor = next((float(r["usd_kwh"]) for r in rows if r["date"] == ANCHOR), None)
    valid = [r for r in rows if r["available_on"] <= day.isoformat()]
    if not anchor or not valid:
        return None
    return .045 * float(valid[-1]["usd_kwh"]) / anchor


def metadata(day: date, directory: Path = CRYPTO_DIR) -> dict:
    rows = load_rows(directory)
    valid = [r for r in rows if r["available_on"] <= day.isoformat()]
    return {
        "kind": "reconstructed_proxy", "observed_global_series": False,
        "label": "Miner power proxy: US industrial index × Cambridge survey anchor",
        "method": "0.045 × EIA industrial USD/kWh / June-2024 EIA industrial USD/kWh",
        "anchor_usd_kwh": .045, "anchor_period": ANCHOR,
        "anchor_published": SURVEY_PUBLISHED,
        "anchor_is_future_information": day.isoformat() < SURVEY_PUBLISHED,
        "release_lag_assumption": "EIA period plus two months; revisions are not vintage controlled.",
        "limitations": "Retrospective US-indexed proxy, not observed global miner tariffs. Cambridge median is not a hashrate-weighted mean. Historical backtests must not treat the later survey anchor as known in advance.",
        "sources": [{"url": EIA_URL, "series": "ESICUUS", "unit": "USD/kWh"},
                    {"url": SURVEY_URL, "page": 9, "unit": "45 USD/MWh electricity only"}],
        "through": valid[-1]["date"] if valid else None,
        "retrieved_on": rows[-1].get("retrieved_on") if rows else None,
        "start": rows[0]["date"] if rows else None,
        "latest_usd_kwh": proxy_on(day, rows),
        "point_in_time_validated": False,
    }


def refresh(*, offline: bool = False, directory: Path = CRYPTO_DIR,
            as_of: date | None = None) -> dict:
    day = as_of or datetime.now(timezone.utc).date()
    status, error = "cached", None
    if not offline:
        try:
            req = urllib.request.Request(EIA_URL, headers={"User-Agent": "SSI-BTC-context/2.0"})
            raw = urllib.request.urlopen(req, timeout=35).read().decode("utf-8-sig")
            rows = parse_eia(raw, retrieved_on=day)
            if not rows or not any(r["date"] == ANCHOR for r in rows):
                raise ValueError("EIA industrial series or anchor missing")
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / "btc_power_eia_industrial.csv"
            temporary = path.with_suffix(".tmp")
            with temporary.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            temporary.replace(path)
            status = "refreshed"
        except Exception as exc:
            status, error = "cached_after_failure", str(exc)
    result = {**metadata(day, directory), "refresh_status": status, "refresh_error": error,
              "attempted_on": day.isoformat()}
    if result["latest_usd_kwh"] is None:
        result["refresh_status"] = "unavailable"
    (directory / "btc_power_history.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
