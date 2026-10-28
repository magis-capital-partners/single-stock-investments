"""Shared provenance and accounting rules for context-only commodity models."""
from __future__ import annotations

import calendar
import hashlib
import json
import math
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(__file__).with_name('commodity_configs')
DEFAULT_PANEL = ROOT / '_private/commodity/observations.json'
VERSION = 'commodity_models.v1'
LB_PER_TONNE = 2204.62262185


def load(path, default=None):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else default


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def periods(start, end):
    year, month = map(int, start.split('-'))
    while f'{year:04d}-{month:02d}' <= end:
        yield f'{year:04d}-{month:02d}', calendar.monthrange(year, month)[1]
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def provenance(config, panel, as_of):
    sources = []
    for ref in config['sources']:
        if ref['published_at'] > as_of.isoformat():
            raise ValueError(f"Future source: {ref['id']}")
        source = dict(ref)
        fetched = panel.get('sources', {}).get(ref['id'], {})
        source['age_days'] = (as_of - date.fromisoformat(ref['published_at'])).days
        source['stale'] = source['age_days'] > ref['max_age_days']
        source['fetch_status'] = fetched.get('status', 'not_refetched')
        source['last_fetched_at'] = fetched.get('fetched_at')
        source['current_sha256'] = fetched.get('sha256')
        source['changed_since_review'] = bool(ref.get('sha256') and fetched.get('sha256') and ref['sha256'] != fetched['sha256'])
        # A hash of typed inputs is not misrepresented as a hash of the publisher's file.
        source['transcription_sha256'] = digest(config['reference'])
        sources.append(source)
    return sources


def shell(config, panel, as_of):
    sources = provenance(config, panel, as_of)
    status = 'source_review_due' if any(s['stale'] or s['changed_since_review'] for s in sources if s.get('required', True)) else 'research_scenarios'
    return {'id': config['id'], 'title': config['title'], 'engine': config['engine'],
            'question': config['question'], 'in_base_irr': False, 'status': status,
            'unit': config['unit'], 'as_of': as_of.isoformat(), 'sources': sources,
            'config_sha256': digest(config), 'reference': config['reference'],
            'falsifiers': config['falsifiers'], 'limitations': config['limitations'],
            'related_tickers': config['related_tickers'], 'cost_floor': config['cost_floor'],
            'validation': [], 'scenarios': [], 'history': []}


def check(name, error, tolerance=0.011):
    return {'check': name, 'residual': round(error, 8), 'tolerance': tolerance, 'passed': abs(error) <= tolerance}


def series(panel, key, as_of):
    # Reject invalid prices and future observations. Negative real yields are allowed.
    return [r for r in panel.get('series', {}).get(key, {}).get('observations', [])
            if r.get('date', '9999') <= as_of.isoformat() and finite(r.get('value'))]
