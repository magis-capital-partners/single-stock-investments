"""Shared, dependency-free utilities for the gas / power research model."""
from __future__ import annotations

import calendar
import hashlib
import json
import math
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / '_system/reference/market-data/energy'
ASSET_DIR = ROOT / '_system/reference/energy/assets'
CONFIG = Path(__file__).with_name('energy_model_config.json')
MODEL_VERSION = '1.0.0'


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def atomic_json(path: Path, value, *, compact=False) -> None:
    """Never replace a good artifact with a partial write or nonfinite number."""
    data = json.dumps(value, indent=None if compact else 2, separators=(',', ':') if compact else None,
                      ensure_ascii=False, allow_nan=False) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()[:20]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def month_end(period: str) -> date:
    year, month = map(int, period[:7].split('-'))
    return date(year, month, calendar.monthrange(year, month)[1])


def month_days(period: str) -> int:
    return month_end(period).day


def months(start: str, end: str):
    year, month = map(int, start[:7].split('-'))
    while f'{year:04d}-{month:02d}' <= end[:7]:
        yield f'{year:04d}-{month:02d}'
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def next_month(period: str) -> str:
    year, month = map(int, period[:7].split('-'))
    return f'{year + 1:04d}-01' if month == 12 else f'{year:04d}-{month + 1:02d}'


def finite(value, name: str, minimum=None, maximum=None) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f'{name} must be finite')
    if minimum is not None and number < minimum:
        raise ValueError(f'{name} must be >= {minimum}')
    if maximum is not None and number > maximum:
        raise ValueError(f'{name} must be <= {maximum}')
    return number


def interpolate(anchors: dict, year: float) -> float:
    points = sorted((float(k), finite(v, 'anchor')) for k, v in anchors.items())
    if not points:
        raise ValueError('empty annual path')
    if year <= points[0][0]:
        return points[0][1]
    for (left, lv), (right, rv) in zip(points, points[1:]):
        if year <= right:
            return lv + (rv - lv) * (year - left) / (right - left)
    return points[-1][1]


def available_records(series: dict, as_of: date) -> list[dict]:
    """Latest revised vintage is unavailable before its actual publication."""
    if str(series.get('published_at') or '9999')[:10] > as_of.isoformat():
        return []
    return [r for r in series.get('observations', []) if r['period'] <= as_of.isoformat()[:7]
            and str(r.get('published_at') or series['published_at'])[:10] <= as_of.isoformat()]
