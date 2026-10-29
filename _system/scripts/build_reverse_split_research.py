"""Publish only reverse-split comparisons; offline, no market-data acquisition."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / '_system/data/reverse_splits'
OUT = ROOT / 'dashboard/data/reverse_split_research'
METRICS = ('entered','issuers','net_pnl','mean_net_return','median_net_return','win_rate_closed','max_drawdown_dollars','conditional_daily_sharpe','open_positions','peak_margin','mean_position','mean_monthly_since_first_entry','borrow_cost','worst_adverse_price_return','issuer_bootstrap_mean_trade_return_95')

def build():
    OUT.mkdir(parents=True, exist_ok=True)
    sources = {}
    def read(relative):
        path = DATA / relative
        raw = path.read_bytes()
        sources[relative] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    repeat = read('repeat_magnitude_study/summary.json')
    protocol = read('repeat_magnitude_study/protocol.json')
    grid = read('sizing_timing_study_20261029/grid.json')
    study = read('third_plus_signal_study/summary.json')
    dictionary = read('third_plus_signal_study/feature_dictionary.json')
    def metrics(row):
        return {k: row.get(k) for k in METRICS}
    # Fixed size only: exclude score multipliers and rally rules from the selected strategy's filter comparisons.
    filters = [{**{k: r[k] for k in ('id','timing','h','mode','cost','rule')}, 'summary': metrics(r['summary'])}
               for r in grid if '_no_veto_' in r['rule'] and '_boost' not in r['rule'] and r['h'] in (5,10,20)]
    core = {
        'schema': 'reverse_split_research.v1', 'built_at': datetime.now(timezone.utc).isoformat(),
        'research_only': True, 'authority': 'none',
        'repeat': {'counting': repeat['counting'], 'returns': repeat['magnitude']['repeatTables'],
                   'magnitude': repeat['magnitude']['tables'], 'coverage': repeat['magnitude']['coverage'],
                   'entry': protocol['entry'], 'universe': protocol['universe'], 'history': protocol['history'],
                   'costs': protocol['costs'], 'price_asof': repeat['price_asof']},
        'filter_cases': filters,
        'third_plus': {'signals': dictionary['signals'], 'coverage': study['coverage'],
                       'primary': [{'arm': r['arm'], 'summary': metrics(r['summary']), 'decision': r.get('decision'),
                                    'holm_p': r.get('holm_p'), 'vs_covered': r.get('vs_covered')} for r in study['primary']],
                       'replication': [{'arm': r['arm'], 'summary': metrics(r)} for r in study['replication']],
                       'ordinal': study['ordinal_diagnostics'], 'price_asof': study['price_asof'],
                       'timing': 'Separate third-plus post-split study; primary 20 sessions, replication 10 sessions.'},
        'limits': ['Historical completed-event coverage is incomplete; cancelled announcements are not a complete population.',
                   'Repeat-event returns describe post-split price moves before trading costs, not announcement-entry returns.',
                   'Filter comparisons keep their own timing, holding period, costs and sizing. They do not change the selected strategy.',
                   'Missing features remain unknown; sparse covered samples and multiple testing limit inference.',
                   'Borrow availability and executable fills are unverified.'],
        'sources': sources,
    }
    body = (json.dumps(core, separators=(',', ':')) + '\n').encode()
    (OUT / 'summary.json').write_bytes(body)
    (OUT / 'manifest.json').write_text(json.dumps({'schema': 'reverse_split_research.manifest.v1', 'file': 'summary.json',
        'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body), 'sources': sources}) + '\n')
    print(json.dumps({'filter_cases': len(filters), 'repeat_cells': len(core['repeat']['returns']), 'bytes': len(body)}))

if __name__ == '__main__':
    build()
