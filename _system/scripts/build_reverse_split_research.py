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

def announcement_comparisons(sources):
    directory=ROOT/'dashboard/data'
    if not (directory/'third_plus_announcement_manifest.json').exists():
        directory=DATA/'local/consolidation/announcement'
    manifest_path=directory/'third_plus_announcement_manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    def bound(name,expected):
        path=directory/name
        if path.resolve().parent!=directory.resolve():
            raise ValueError('Unexpected announcement source path')
        raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if digest!=expected:raise ValueError('Announcement source build mismatch')
        sources['announcement/'+name]=digest
        return json.loads(raw)
    root=bound(manifest['payload'],manifest['sha256'])
    if root['schema']!='announcement_full_study.v8' or root['production_authority']!='none' or root['historical_fills_verified'] is not False:
        raise ValueError('Unexpected announcement study')
    allowed={'score60','legacy_score60','S1','S2','S3','S4','reported_runway','burn','operating_loss','revenue15','margin8','accrual10','profit_no_cash','negative_equity','debt_distress'}
    arms=[a for a in root['arms'] if set(a['requires'])<=allowed]
    ids={a['id'] for a in arms};cases=[]
    metrics=['net_pnl','max_drawdown_dollars','entered','open_positions','mean_position','pnl_without_best5_issuers','price_imputed_entries','pnl_without_price_imputation','modeled_margin_requirement','mean_hold_sessions','estimated_quote_entries','unresolved_action_paths']
    for part in root['parts']:
        if part['cohort']!='scheduled_disclosures':continue
        doc=bound(part['file'],part['sha256'])
        if doc['cohort']!=part['cohort'] or doc['ordinal']!=part['ordinal'] or len(doc['models'])!=part['models']:
            raise ValueError('Announcement comparison identity mismatch')
        for r in doc['models']:
            if r['capacity']!='unlimited' or r['holding']!='entry20' or r['filter'] not in ids:continue
            cases.append({**{k:r[k] for k in ['id','ordinal','timing','scenario','filter','candidates','signal_pass','signal_unknown','feature_covered']},'summary':{k:r['summary'].get(k) for k in metrics},'coverage_control_net_pnl':r['coverage_control'].get('net_pnl')})
    return {'arms':arms,'cases':cases,'market_through':root['market_through'],'disclosure_through':root['disclosure_through'],'cohort':root['cohorts']['scheduled_disclosures'],'data_version':root['data_version'],
        'method':'Separate captured-announcement study: $100,000 target, 20 sessions from entry, independent opportunities and modeled access/fills. This does not change the selected five-session strategy.',
        'limits':'Prices and quotes include estimates and later-price imputations. The comparison explicitly reports profit without those imputed-price entries. Original-release dates are sometimes assumed; captured SEC time is not always the first press release. No historical fills or locates are verified.'}

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
    # Retain fundamental and repeat-count arms only; price weakness and rally vetoes belong to the retired lab.
    fundamental_signals = {'S1','S2','S3','S4','score60'}
    fundamental_arms = {r['id'] for r in dictionary['arms'] if set(r['requires']) <= fundamental_signals}
    def metrics(row):
        return {k: row.get(k) for k in METRICS}
    # Fixed size only: exclude score multipliers and rally rules from the selected strategy's filter comparisons.
    filters = [{**{k: r[k] for k in ('id','timing','h','mode','cost','rule')}, 'summary': metrics(r['summary'])}
               for r in grid if '_no_veto_' in r['rule'] and '_boost' not in r['rule'] and r['h'] in (1,5,10,20)]
    core = {
        'schema': 'reverse_split_research.v1', 'built_at': datetime.now(timezone.utc).isoformat(),
        'research_only': True, 'authority': 'none',
        'repeat': {'counting': repeat['counting'], 'returns': repeat['magnitude']['repeatTables'],
                   'magnitude': repeat['magnitude']['tables'], 'coverage': repeat['magnitude']['coverage'],
                   'entry': protocol['entry'], 'universe': protocol['universe'], 'history': protocol['history'],
                   'costs': protocol['costs'], 'price_asof': repeat['price_asof']},
        'filter_cases': filters,
        'announcement': announcement_comparisons(sources),
        'third_plus': {'signals': [r for r in dictionary['signals'] if r['id'] in fundamental_signals], 'coverage': study['coverage'],
                       'primary': [{'arm': r['arm'], 'summary': metrics(r['summary']), 'decision': r.get('decision'),
                                    'holm_p': r.get('holm_p'), 'vs_covered': r.get('vs_covered')} for r in study['primary'] if r['arm'] in fundamental_arms],
                       'replication': [{'arm': r['arm'], 'summary': metrics(r)} for r in study['replication'] if r['arm'] in fundamental_arms],
                       'ordinal': [r for r in study['ordinal_diagnostics'] if r['arm'] in fundamental_arms], 'price_asof': study['price_asof'],
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
