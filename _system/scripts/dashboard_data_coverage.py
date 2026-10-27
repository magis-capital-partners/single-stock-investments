"""Measure published data coverage without treating research gates as approvals."""
from __future__ import annotations


def surface_coverage(surface: str, doc: dict) -> dict | None:
    if not isinstance(doc, dict) or doc.get('private_snapshot'):
        return None
    rows = doc.get('rows') or []
    fields = {
        'rock': ('ev_ebitda', 'fcf_yield_pct'),
        'banks': ('deposits_total_usd', 'dda_share_pct', 'cost_of_deposits_pct', 'p_tbv'),
        'nol': ('gross_nol_usd', 'market_cap_usd'),
    }.get(surface)
    if fields and isinstance(rows, list):
        missing = {key: sum(row.get(key) is None for row in rows) for key in fields}
        complete = sum(all(row.get(key) is not None for key in fields) for row in rows)
        if surface == 'rock':
            for key in ('shipments_million_tons', 'price_per_ton', 'cash_gp_per_ton', 'organic_volume_growth_pct', 'reserve_life_years'):
                missing[key] = sum(key not in ((row.get('operating_latest') or {}).get('FY') or {}).get('metrics', {}) for row in rows)
            complete = sum(not ((row.get('operating_coverage') or {}).get('required_missing')) and all(row.get(key) is not None for key in fields) for row in rows)
        return _result(len(rows), complete, missing, 'Fill missing source evidence; undisclosed metrics remain unavailable.')
    if surface == 'darwin':
        universe = doc.get('universe') or {}
        total, complete = universe.get('count', 0), universe.get('scored', 0)
        return _result(total, complete, {'unscored': max(0, total-complete)}, 'Retry missing option chains; preserve earnings and liquidity exclusions.')
    if surface == 'buyback-radar':
        counts = doc.get('counts') or {}
        return _result(counts.get('companies', 0), counts.get('verified', 0), {'unverified': counts.get('gaps', 0)}, 'Reconcile share counts and repurchase evidence; discovery events remain under review until terms pass.')
    if surface == 'short-alpha':
        summary = doc.get('summary') or {}
        return _result(summary.get('candidate_count', 0), summary.get('research_complete_count', 0), {}, 'Complete candidate research and refresh dated borrow evidence. A lead is not a position.')
    if surface == 'inflections':
        coverage = doc.get('coverage') or {}
        total = coverage.get('universe', 0)
        missing = len(coverage.get('no_trend_data') or [])
        return _result(total, max(0, total-missing), {'no_trend_data': missing}, 'Refresh filing facts and issuer-specific operating series; separate funds and unsupported instruments.')
    if surface == 'index-watch':
        names = doc.get('by_ticker') or {}
        missing = {}
        for row in names.values():
            for key in row.get('inputs_missing') or []:
                if isinstance(key, str):missing[key] = missing.get(key, 0)+1
        complete = sum(not row.get('inputs_missing') for row in names.values())
        return _result(len(names), complete, missing, 'Reconcile listing identity, market capitalization, float and trading-volume inputs.')
    if surface == 'market-risk-components':
        rows=doc.get('components') or []
        missing={key:sum(r.get('quality_state')==key for r in rows) for key in ('stale','delayed','unavailable')}
        return _result(len(rows),sum(r.get('quality_state')=='ready' for r in rows),missing,
                       'Refresh dated upstream component snapshots. Unconnected observed-flow sources remain unavailable.')
    if surface == 'technical-summary':
        summary=doc.get('summary') or {}
        return _result(summary.get('requested',0),summary.get('fresh',0),
                       {'unavailable':max(0,summary.get('requested',0)-summary.get('available',0))},
                       'Resolve renamed or delisted securities and retry failed price histories; retain limited-history labels.')
    if surface == 'podcasts' and isinstance(doc.get('podcast_index'),list):
        rows=doc['podcast_index'];complete=sum(row.get('summary_status')=='ready' for row in rows)
        return _result(len(rows),complete,{'summary_pending':len(rows)-complete},
                       'Process queued transcript summaries; preserve published episodes while new research is pending.')
    return None


def _result(total, complete, missing, next_action):
    total, complete = int(total), int(complete)
    return {'total_rows': total, 'complete_rows': complete,
            'incomplete_rows': max(0, total-complete),
            'coverage_pct': round(100*complete/total, 1) if total else None,
            'missing_by_field': missing, 'next_action': next_action}
