"""Immutable policy and exchange-session clocks for the forward comparison."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import lru_cache
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parents[3]
STATE = ROOT / '_system/data/reverse_splits/third_plus_forward_v1'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def stamp(value):
    at = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.tzinfo is None:
        raise ValueError('An explicit timezone is required')
    return at.astimezone(timezone.utc)


def utcnow():
    return datetime.now(timezone.utc)


def code_receipts():
    files = [p for p in Path(__file__).parent.glob('*.py') if not p.name.startswith('test_')]
    files.append(ROOT/'_system/scripts/third_plus_signal/features.cjs')
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in sorted(files)}


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    temporary.write_text(canonical(value) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def definitions():
    common = {
        'version': 'third_plus_forward.v1', 'mode': 'prospective_research',
        'production_authority': 'none', 'all_names_assumed_tradable': True,
        'documented_split_ordinal_minimum': 3,
        'rally_veto': {'single_daily_gain_gte': .5, 'completed_sessions': 5},
        'cash_burn': {'ttm_operating_cashflow_lt': 0, 'freshness_days': 200,
                      'method': 'shared third_plus_signal/features.cjs financialSnapshot'},
        'weak_close': {'close_lt_open': True, 'close_range_fraction_lte': .25},
        'target_usd': 100000, 'maximum_concurrent_issuers': 3,
        'gross_budget_usd': 300000, 'squeeze_loss_budget_usd': 600000,
        'squeeze_up_fraction': 2, 'reference_nav_usd': 10000000,
        'entry': {'start_minutes_after_open': 1, 'duration_minutes': 60,
                  'source_delay_minutes': 5, 'wait_for_effective_session_close': True,
                  'freeze': 'first complete snapshot after effective close, before entry; incomplete decisions in final five minutes'},
        'execution': {'policy': 'E2', 'participation': .1, 'child_usd': 2000,
                      'ack_ms': 500, 'reprice_seconds': 5, 'eligible_capture': .5},
        'hold_sessions_including_entry': 20,
        'cover': {'start_minutes_before_close': 90, 'stop_minutes_before_close': 15,
                  'retry_sessions': 2, 'unfilled_residual': 'remain open; manual exception review'},
        'base_costs': {'borrow_apr': .5, 'borrow_collateral': 1.02, 'day_basis': 360,
                       'half_spread_bps': 86, 'impact_per_side_bps': 10,
                       'locate_per_share': .01, 'locate_minimum': 5},
        'tie_break': 'event_id ascending', 'unknown_required_signal': 'abstain',
        'slot_accounting': 'separate book per policy; requested orders reserve until window end; partial fills occupy one issuer',
        'observation_rules': {'public_quotes': 'indicative references, never executable NBBO or fills',
                              'reference_returns': 'price benchmarks, never strategy P&L',
                              'fills': 'explicit sourced paper or broker observations only',
                              'missed_entry': 'record missed; never backdate enrollment',
                              'corporate_action': 'explicit quantity/price adjustment; unresolved identity pauses accounting'},
        'review': {'minimum_closed_issuers': 30, 'minimum_closed_positions': 50,
                   'maximum_median_entry_shortfall_bps': 100,
                   'maximum_median_cover_shortfall_bps': 100,
                   'maximum_p90_cover_delay_sessions': 2,
                   'maximum_unresolved_positions': 0,
                   'maximum_borrow_apr': 1.5,
                   'minimum_net_after_costs': 0,
                   'maximum_best_five_profit_fraction': .5,
                   'result': 'human review only; count thresholds do not establish an edge or enable orders'},
        'backtest_publication': '0dee2805aa5569a4c5c7cfd93460eacdcb3c75615944b3b1322e7e8cd020c4be',
        'historical_data_through': '2026-10-12',
        'retrospective_selection': True,
    }
    return [dict(common, id='burn_weak_h20', label='Cash burn + weak close', requires=['S7', 'burn', 'S5']),
            dict(common, id='burn_control_h20', label='Cash-burn control', requires=['S7', 'burn'])]


def freeze(directory=STATE, now=None):
    now = now or utcnow()
    path = Path(directory) / 'policies.json'
    expected = [{'policy': p, 'sha256': sha(p)} for p in definitions()]
    if path.exists():
        doc = json.loads(path.read_text(encoding='utf-8'))
        if doc.get('policies') != expected or doc.get('production_authority') != 'none':
            raise ValueError('Frozen policy changed: create a new version and keep the original')
        stamp(doc['frozen_at'])
        return doc
    doc = {'schema': 'third_plus_forward_policies.v1', 'frozen_at': now.isoformat(),
           'production_authority': 'none', 'policies': expected}
    write(path, doc)
    return doc


@lru_cache(maxsize=1)
def calendar():
    import exchange_calendars as xc
    return xc.get_calendar('XNYS', start='2020-01-01', end='2035-12-31')


def sessions(start, end):
    return [s.date().isoformat() for s in calendar().sessions_in_range(start, end)]


def opening(day):
    return calendar().session_open(day).to_pydatetime()


def closing(day):
    return calendar().session_close(day).to_pydatetime()


def entry_clock(effective_day, known_at):
    cal = calendar()
    if not cal.is_session(effective_day):
        raise ValueError('Effective split date must be a verified exchange session')
    after = max(closing(effective_day), stamp(known_at) + timedelta(minutes=5))
    for day in sessions(effective_day, (after + timedelta(days=20)).date().isoformat()):
        if opening(day) >= after and day > effective_day:
            return opening(day) + timedelta(minutes=1)
    raise ValueError('No eligible entry session')


def schedule(entry_at):
    day = stamp(entry_at).astimezone(NY).date().isoformat()
    days = sessions(day, (stamp(entry_at) + timedelta(days=65)).date().isoformat())
    cover = days[19]
    return {'entry_at': stamp(entry_at).isoformat(),
            'entry_end': (stamp(entry_at) + timedelta(minutes=60)).isoformat(),
            'cover_day': cover, 'cover_start': (closing(cover) - timedelta(minutes=90)).isoformat(),
            'cover_end': (closing(cover) - timedelta(minutes=15)).isoformat(),
            'retry_days': days[20:22], 'exception_after': (closing(days[21]) - timedelta(minutes=15)).isoformat()}
