#!/usr/bin/env python3
"""Calendar-time volatility versus an equal-volume clock.

Daily bars only. A session is never split. No network and no file reads.
Both the volatility builder and the technical builder import this module so
the two panels cannot grow two definitions.

The gap is a description of history. It is not a forecast.
"""

from __future__ import annotations

import math
import statistics

RV_WINDOW = 20
QUOTA_LOOKBACK = 252
TRADING_DAYS = 252
OVERSIZE_MAX_SHARE = 0.20
MISSING_MAX_SHARE = 0.05
MIN_AUTOCORR = 20

WITHHOLD_RETURNS = "fewer than 20 daily returns"
WITHHOLD_BUCKETS = "fewer than 20 completed buckets"
WITHHOLD_OVERSIZE = "more than one in five buckets is a single oversized day"
WITHHOLD_MISSING = "volume is missing on more than one in twenty sessions"

CAPTION = (
    "Calendar-time volatility is how much SPY's adjusted close moved over the last 20 sessions. "
    "Volume-time volatility recounts those closes only after a fixed number of shares has traded. "
    "The gap is what remains after busy and quiet days are given equal weight. It is not a forecast. "
    "These are daily bars. The paper measured New York and London ticks, which can split one day into many slices. "
    "A daily bar cannot, so a single busy day is one bucket, never a fraction of one."
)

CLUSTERING_SENTENCE = (
    "Absolute moves are still clumped after the equal-volume packing."
)

SCHEMA = {
    "research_only": True,
    "in_base_irr": False,
    "authority": "none",
}


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _price(row: dict):
    price = _finite(row.get("adj_close"))
    if price is None:
        price = _finite(row.get("close"))
    if price is None or price <= 0:
        return None
    return price


def _volume(row: dict):
    volume = _finite(row.get("volume"))
    if volume is None or volume <= 0:
        return None
    return volume


def _round(value, digits: int = 4):
    if value is None:
        return None
    return round(float(value), digits)


def _clean_rows(rows) -> list[dict]:
    by_date: dict[str, dict] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        date = str(row.get("date") or "").strip()
        price = _price(row)
        if not date or price is None:
            continue
        by_date[date] = {"date": date, "price": price, "volume": _volume(row)}
    return [by_date[key] for key in sorted(by_date)]


def _lag1(values: list[float]):
    if len(values) < MIN_AUTOCORR:
        return None
    left = values[:-1]
    right = values[1:]
    mean_left = statistics.fmean(left)
    mean_right = statistics.fmean(right)
    numerator = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    left_scale = math.sqrt(sum((a - mean_left) ** 2 for a in left))
    right_scale = math.sqrt(sum((b - mean_right) ** 2 for b in right))
    if left_scale == 0 or right_scale == 0:
        return None
    return numerator / (left_scale * right_scale)


def _quota_window(clean: list[dict], open_index: int) -> tuple[float, float, float] | None:
    """Median volume, mean volume, and missing share over the 252 sessions before open_index.

    The quota is frozen from this window. Later sessions do not revise it.
    """
    if open_index < QUOTA_LOOKBACK:
        return None
    window = clean[open_index - QUOTA_LOOKBACK : open_index]
    volumes = []
    missing = 0
    for row in window:
        if row["volume"] is None:
            missing += 1
        else:
            volumes.append(row["volume"])
    if len(volumes) < 2:
        return None
    quota = statistics.median(volumes)
    if quota <= 0:
        return None
    return quota, statistics.fmean(volumes), missing / QUOTA_LOOKBACK


def _buckets(clean: list[dict]) -> list[dict]:
    """Walk cleaned sessions and close a bucket when accumulated shares reach the quota.

    A session with no volume does not advance the clock and does not emit a
    bucket. A session whose volume is already at least the quota is one bucket.
    It is never divided.
    """
    buckets: list[dict] = []
    open_index = None
    start_price = None
    quota = None
    mean_volume = None
    missing_share = None
    accumulated = 0.0
    sessions = 0

    for index, row in enumerate(clean):
        if open_index is None:
            if row["volume"] is None:
                continue
            frozen = _quota_window(clean, index)
            if frozen is None or index == 0:
                continue
            quota, mean_volume, missing_share = frozen
            start_price = clean[index - 1]["price"]
            open_index = index
            accumulated = 0.0
            sessions = 0
        volume = row["volume"]
        if volume is None:
            continue
        accumulated += volume
        sessions += 1
        if accumulated + 1e-9 < quota:
            continue
        buckets.append(
            {
                "end_date": row["date"],
                "end_index": index,
                "open_index": open_index,
                "return": math.log(row["price"] / start_price),
                "accumulated": accumulated,
                "sessions": sessions,
                "oversized": sessions == 1 and accumulated > quota,
                "quota": quota,
                "mean_daily_volume": mean_volume,
                "missing_share": missing_share,
            }
        )
        open_index = None
        start_price = None
        quota = None
        mean_volume = None
        missing_share = None
        accumulated = 0.0
        sessions = 0
    return buckets


def equal_volume_buckets(rows) -> list[dict]:
    """Public bucket walk. Input rows use adj_close or close, plus volume."""
    return _buckets(_clean_rows(rows))


def _calendar_vol(returns: list, index: int):
    if index < RV_WINDOW:
        return None
    sample = returns[index - RV_WINDOW + 1 : index + 1]
    if len(sample) < RV_WINDOW or any(value is None for value in sample):
        return None
    return statistics.stdev(sample) * math.sqrt(TRADING_DAYS) * 100.0


def _point(date: str, calendar, volume_time, gap, ratio, bucket, window, reason, daily_corr, bucket_corr) -> dict:
    oversized_share = None
    if window:
        oversized_share = sum(1 for item in window if item["oversized"]) / len(window)
    buckets_per_year = None
    if bucket and bucket["quota"]:
        buckets_per_year = TRADING_DAYS * bucket["mean_daily_volume"] / bucket["quota"]
    clustering = None
    if (
        reason is None
        and daily_corr is not None
        and bucket_corr is not None
        and daily_corr > 0
        and bucket_corr > 0
    ):
        clustering = CLUSTERING_SENTENCE
    return {
        "date": date,
        "calendar_vol": _round(calendar),
        "volume_time_vol": _round(volume_time),
        "gap": _round(gap),
        "ratio": _round(ratio),
        "quota": None if bucket is None else int(round(bucket["quota"])),
        "mean_daily_volume": None if bucket is None else int(round(bucket["mean_daily_volume"])),
        "buckets_in_window": len(window),
        "oversized_share": _round(oversized_share),
        "buckets_per_year": _round(buckets_per_year, 2),
        "withheld_reason": reason,
        "daily_abs_autocorr": _round(daily_corr),
        "bucket_abs_autocorr": _round(bucket_corr),
        "clustering_sentence": clustering,
    }


def series(rows) -> list[dict]:
    """One strictly trailing row per session that has a price.

    A row uses only sessions on or before its own date. The quota on a bucket
    was frozen when that bucket opened, from the 252 sessions before the open.
    """
    clean = _clean_rows(rows)
    count = len(clean)
    returns: list = [None] * count
    for index in range(1, count):
        returns[index] = math.log(clean[index]["price"] / clean[index - 1]["price"])
    buckets = _buckets(clean)
    points = []
    cursor = 0
    for index, row in enumerate(clean):
        while cursor < len(buckets) and buckets[cursor]["end_index"] <= index:
            cursor += 1
        ended = buckets[:cursor]
        window = ended[-RV_WINDOW:]
        calendar = _calendar_vol(returns, index)
        latest_bucket = ended[-1] if ended else None
        reason = None
        volume_time = None
        gap = None
        ratio = None
        if calendar is None:
            reason = WITHHOLD_RETURNS
        elif len(window) < RV_WINDOW:
            reason = WITHHOLD_BUCKETS
        elif latest_bucket and latest_bucket["missing_share"] > MISSING_MAX_SHARE:
            reason = WITHHOLD_MISSING
        else:
            oversized_share = sum(1 for item in window if item["oversized"]) / len(window)
            if oversized_share > OVERSIZE_MAX_SHARE:
                reason = WITHHOLD_OVERSIZE
            else:
                scale = TRADING_DAYS * latest_bucket["mean_daily_volume"] / latest_bucket["quota"]
                volume_time = statistics.stdev(item["return"] for item in window) * math.sqrt(scale) * 100.0
                gap = calendar - volume_time
                if calendar:
                    ratio = volume_time / calendar
        daily_abs = [abs(value) for value in returns[max(0, index - QUOTA_LOOKBACK + 1) : index + 1] if value is not None]
        year_buckets = [item for item in ended if item["end_index"] > index - QUOTA_LOOKBACK]
        bucket_abs = [abs(item["return"]) for item in year_buckets]
        points.append(
            _point(
                row["date"],
                calendar,
                volume_time,
                gap,
                ratio,
                latest_bucket,
                window,
                reason,
                _lag1(daily_abs),
                _lag1(bucket_abs),
            )
        )
    return points


def latest_point(rows) -> dict:
    """Latest session only, for a ticker payload. Schema flags ride on the point."""
    points = series(rows)
    if not points:
        point = _point(None, None, None, None, None, None, [], WITHHOLD_RETURNS, None, None)
    else:
        point = points[-1]
    point.update(SCHEMA)
    return point


def market_document(rows, *, symbol: str = "SPY") -> dict:
    """SPY history plus the latest point. The page draws the last 120 gaps."""
    points = series(rows)
    latest = latest_point(rows)
    return {
        "schema_version": 1,
        **SCHEMA,
        "symbol": symbol,
        "as_of": latest.get("date"),
        "stale": False,
        "price_source": "Yahoo symbol SPY, adjusted close, share volume",
        "caption": CAPTION,
        "latest": latest,
        "history": points[-120:],
    }
