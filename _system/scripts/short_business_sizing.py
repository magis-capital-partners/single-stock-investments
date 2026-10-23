"""Offline dollar-profit sensitivity of the existing same-day short replay.

Uses existing entry/cover rules, permits smaller targets, and estimates current
fixed-plan regulatory charges. No data downloads, broker calls or live authority.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

TICKETS = (250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000)
PROTOCOL = {
    'version': 'short_business_sizing.v1', 'hypothesis_id': 'H20',
    'tickets': TICKETS, 'test_start': '2023-01-03', 'test_end': '2026-10-13',
    'policies': ['fixed target without a forecast edge filter', 'fixed target with existing adaptive net-edge filter', 'adaptive choice across all targets'],
    'cost_cases': ['bull', 'base', 'bear'], 'variants': 57,
    'entry_and_exit': 'Unchanged opening decision/100ms IOC response and same-day close sweep; full-target admission required; no new patient execution algorithm.',
    'selection': 'Same expanding earlier-session forecasts, 0.5% net buffer, 50% forecast cover support, three issuers and 10%-NAV squeeze reserve as short_adaptive_sizing.v1.',
    'fees': 'IBKR Pro Fixed $0.005/share, $1 minimum, 1% notional cap per leg; current SEC 20.60/million sold and CAT 0.000003/share each side. Normal FINRA TAF 0.000195/share sold capped at $9.79 is retained rather than extrapolating the temporary 2026Q4 holiday. Components rounded up to cents per modeled leg.',
    'fee_basis': 'Current forward cost sensitivity applied to historical fills; not historically invoiced costs. One modeled order per leg, with no extra minimums for a future sliced execution algorithm.',
    'financing': 'Same-day modeled flat: borrow and proceeds interest both zero. Actual locate charges, delayed-cover borrowing and account funding costs unverified.',
    'overhead': 'Trading P&L before annual data, infrastructure, labor, capital opportunity cost and tax; report annual overhead break-even, not assumed zero operating expense.',
    'consistency': 'Trades, win fraction, losing trades, worst trade, closing-equity dollar drawdown, calendar-year dollars and profit excluding the best trade. No unobserved squeeze extrapolation.',
    'validation': 'Retrospective sizing sensitivity after larger-ticket research; all 57 declared variants reported, no winner promoted. Existing designated execution holdout file remains unread.',
    'fee_sources': ['https://www.interactivebrokers.com/en/pricing/commissions-stocks.php', 'https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2', 'https://www.govinfo.gov/content/pkg/FR-2026-09-23/html/2026-19392.htm'],
}


def cents(amount):
    return math.ceil(max(0., amount)*100-1e-10)/100


def regulatory(shares, sell_price):
    if shares <= 0:
        return 0.
    return (cents(shares*sell_price*.0000206) + cents(min(9.79, shares*.000195))
            + 2*cents(shares*.000003))


def dollar_metrics(model, decisions, days, nav):
    pnl = np.zeros(len(days))
    for i, r, *_ in model['series']:
        pnl[i] = r*nav
    cumulative = np.cumsum(pnl)
    peaks = np.maximum.accumulate(np.r_[0., cumulative])[1:]
    years = (date.fromisoformat(days[-1])-date.fromisoformat(days[0])).days/365.2425
    trades = [d['result']['net_pnl'] for d in decisions if d['result']['filled']]
    annual = {y: float(sum(p for d, p in zip(days, pnl) if d.startswith(y)))
              for y in sorted({d[:4] for d in days})}
    m = model['metrics']
    return {'trades': len(trades), 'trades_per_year': len(trades)/years,
            'mean_position': m['mean_notional'], 'net_trading_pnl': float(pnl.sum()),
            'annualized_trading_pnl': float(pnl.sum()/years),
            'annual_overhead_break_even': float(pnl.sum()/years),
            'annualized_pnl_ex_best_trade': float((pnl.sum()-max(trades))/years) if trades else 0.,
            'mean_profit_per_trade': float(np.mean(trades)) if trades else None,
            'trade_win_fraction': sum(t > 0 for t in trades)/len(trades) if trades else None,
            'losing_trades': sum(t < 0 for t in trades),
            'worst_trade_dollars': min(trades) if trades else None,
            'closing_equity_max_drawdown_dollars': float(max(peaks-cumulative)),
            'worst_day_dollars': float(min(pnl)), 'annual_pnl': annual,
            'modeled_cover_trades': m['modeled_cover_trades'],
            'modeled_cover_share_fraction': m['modeled_cover_share_fraction'],
            'broker_and_regulatory_cost': m['commission_cost'], 'execution_cost': m['execution_cost'],
            'borrow_cost': m['borrow_cost'], 'proceeds_interest': m['proceeds_interest'],
            'peak_margin_dollars': m['peak_margin']*nav,
            'squeeze_reserve_dollars': m['stress_reserve_200']*nav,
            'fully_observed_cover_pnl_diagnostic': m['fully_observed_cover_pnl_diagnostic'],
            'gate_counts': m['gate_counts']}


def fixed_edge_predictions(predictions, ticket):
    """Keep all parent opportunities, but offer only the declared size to the filter."""
    return {day: ([{**p, 'adaptive': [c for c in p['adaptive'] if c['ticket'] == ticket]}
                   for p in rows], n) for day, (rows, n) in predictions.items()}


def build(source_root, local_out):
    local_out.mkdir(parents=True, exist_ok=True)
    (local_out/'protocol.json').write_text(json.dumps(PROTOCOL, indent=2)+'\n', encoding='utf-8')
    spec = importlib.util.spec_from_file_location('adaptive', Path(__file__).with_name('short_adaptive_sizing.py'))
    s = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(s)
    s.TICKETS = TICKETS
    s.PROTOCOL = {**s.PROTOCOL, 'tickets': TICKETS}
    candidate, execute = s.candidate, s.execute

    def with_fees(row, ticket, gross, history, case):
        c = candidate(row, ticket, gross, history, case)
        if c:
            _, cash, _ = s.take(row['decision']['bid_levels'], c['quantity'], limit=c['limit'])
            extra = regulatory(c['quantity'], cash/c['quantity'])/(c['quantity']*row['mid'])
            c = {**c, 'predicted_regulatory_cost': extra, 'predicted_net': c['predicted_net']-extra,
                 'expected_dollars': c['expected_dollars']-extra*c['quantity']*row['mid']}
        return c

    def execute_with_fees(row, c, case):
        r = execute(row, c, case)
        if r['filled']:
            extra = regulatory(r['filled'], r['sell_vwap'])
            r = {**r, 'net_pnl': r['net_pnl']-extra, 'commissions': r['commissions']+extra,
                 'regulatory_cost': extra}
        return r

    s.candidate, s.execute = with_fees, execute_with_fees
    rows, days, source = s.load_rows(source_root)
    results = []
    for case in s.CASES:
        predictions = {d: s.predict(rows, d, case) for d in sorted({r['date'] for r in rows if s.dstart(r['date'])})}
        for ticket in TICKETS:
            for kind, pp, policy in (
                ('fixed', predictions, {'id': 'fixed'+str(ticket), 'ticket': ticket}),
                ('edge_filtered', fixed_edge_predictions(predictions, ticket), {'id': 'adaptive'}),
            ):
                model, decisions = s.replay(rows, days, policy, case, pp)
                result = {'case': case['id'], 'policy': kind, 'target': ticket,
                          **dollar_metrics(model, decisions, days, s.NAV)}
                results.append(result)
                s.audit.write(local_out/f"{case['id']}_{kind}_{ticket}.decisions.local.json", decisions)
                print(case['id'], kind, ticket, result['trades'], round(result['annualized_trading_pnl']), flush=True)
        model, decisions = s.replay(rows, days, {'id': 'adaptive'}, case, predictions)
        results.append({'case': case['id'], 'policy': 'adaptive', 'target': None,
                        **dollar_metrics(model, decisions, days, s.NAV)})
        s.audit.write(local_out/f"{case['id']}_adaptive.decisions.local.json", decisions)
    return {'schema_version': PROTOCOL['version'], 'built_at': datetime.now(timezone.utc).isoformat(),
            'research_only': True, 'authority': 'none', 'aggregate_only': True, 'hypothesis_ids': ['H20'],
            'protocol': PROTOCOL, 'cases': s.CASES, 'years': (date.fromisoformat(days[-1])-date.fromisoformat(days[0])).days/365.2425,
            'test_calendar_start': days[0], 'test_calendar_end': days[-1],
            'population': {'training_events': sum(r['date'] < days[0] for r in rows), 'test_events': sum(s.dstart(r['date']) for r in rows)},
            'results': results, 'sources': {name: s.audit.sha(source/name) for name in ('books.local.json', 'paths.local.json', 'manifest.json')}}


def report(doc):
    cash = lambda v: ('-' if v < 0 else '')+f'${abs(v):,.0f}' if v is not None else 'Unavailable'
    lines = ['# Short strategy dollar profit and smaller position sensitivity', '',
             'Retrospective research on the existing reverse-split event family. No broker orders or data downloads.', '',
             f"Test calendar: {doc['test_calendar_start']} through {doc['test_calendar_end']} ({doc['years']:.3f} calendar years); 226 eligible test events, 56 initial earlier training events. All 57 declared sizing/cost variants are retained. The patient execution proposal is not implemented in this replay.", '',
             'Annual profit below is total modeled dollar P&L divided by elapsed calendar years. It is not compounded CAGR or a forecast of future income. Target sizes are dollars of short notional, independent of how portfolio returns are presented.', '',
             '## Fixed targets in the base cost case', '',
             '| Target per name | Trades | Trades per year | Annual trading profit | Win rate | Worst trade | Closing equity max drawdown | Covers with modeled residual |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in doc['results']:
        if r['case'] == 'base' and r['policy'] == 'fixed':
            lines.append(f"| {cash(r['target'])} | {r['trades']} | {r['trades_per_year']:.1f} | {cash(r['annualized_trading_pnl'])} | {r['trade_win_fraction']:.1%} | {cash(r['worst_trade_dollars'])} | {cash(r['closing_equity_max_drawdown_dollars'])} | {r['modeled_cover_trades']} |")
    lines += ['', 'Smaller targets admit additional names, so the rows have different traded populations. They are not a controlled comparison of the same trades at different sizes. Smaller fixed targets do not demonstrate more consistent profitability: every fixed target below $25k has negative 2026 P&L through October 13. Fixed $25k earns more dollars with a smaller observed closing drawdown than several smaller targets, but four of its covers require hypothetical completion beyond observed depth.', '',
              '## Fixed targets with the existing net edge filter', '',
              '| Target per name | Trades | Annual trading profit | Win rate | Closing equity max drawdown |',
              '|---|---:|---:|---:|---:|']
    for r in doc['results']:
        if r['case'] == 'base' and r['policy'] == 'edge_filtered':
            win = f"{r['trade_win_fraction']:.1%}" if r['trade_win_fraction'] is not None else 'No trades'
            lines.append(f"| {cash(r['target'])} | {r['trades']} | {cash(r['annualized_trading_pnl'])} | {win} | {cash(r['closing_equity_max_drawdown_dollars'])} |")
    lines += ['', '## Adaptive choice across all target sizes', '',
              'The existing forecast selects among $250, $500, $1k, $2.5k, $5k, $10k, $25k, $50k and $100k. It must pass the original 0.5% expected net buffer, forecast cover support and shared risk limits. No target is selected using its realized test return.', '',
              '| Cost case | Trades | Mean position | Annual trading profit | Closing equity max drawdown |',
              '|---|---:|---:|---:|---:|']
    for r in doc['results']:
        if r['policy'] == 'adaptive':
            lines.append(f"| {r['case'].title()} | {r['trades']} | {cash(r['mean_position'])} | {cash(r['annualized_trading_pnl'])} | {cash(r['closing_equity_max_drawdown_dollars'])} |")
    r = next(v for v in doc['results'] if v['case'] == 'base' and v['policy'] == 'adaptive')
    lines += ['', f"Base takes {r['trades']} trades, about {r['trades_per_year']:.1f} per year, averaging {cash(r['mean_position'])}. Trading profit totals {cash(r['net_trading_pnl'])}; annualized profit is {cash(r['annualized_trading_pnl'])}. The win rate is {r['trade_win_fraction']:.1%}, with {r['losing_trades']} losing trades. Removing the single best trade reduces annualized profit to {cash(r['annualized_pnl_ex_best_trade'])}. One cover has modeled residual shares. The similar bull/base/bear totals partly reflect different selections; they are not a confidence interval for business income.", '',
              '| Calendar period | Base adaptive trading profit |', '|---|---:|']
    for year, profit in r['annual_pnl'].items():
        label = year + (' through October 13' if year == '2026' else '')
        lines.append(f'| {label} | {cash(profit)} |')
    lines += ['', '## Business profit after operating expenses', '',
              f"Base adaptive can absorb only about {cash(r['annualized_trading_pnl'])} of annual overhead before its historical average operating profit reaches zero. The following costs are illustrations, not estimates of the current infrastructure bill.", '',
              '| Assumed annual operating overhead | Annual operating profit at the base historical run rate |', '|---|---:|']
    for overhead in (2000, 5000, 10000):
        lines.append(f"| {cash(overhead)} | {cash(r['annualized_trading_pnl']-overhead)} |")
    lines += ['', 'Trading P&L deducts modeled spread/depth costs, the declared impact buffers, censored-cover surcharges, fixed commissions and regulatory fees. Modeled same-day flat positions incur zero borrow charges and zero short-proceeds interest. Actual locate charges, routing differences, settlement failures, delayed covers and account funding remain unverified. Data subscriptions, infrastructure, labor, capital opportunity cost and tax are not deducted because their actual incremental amounts are unknown. Margin collateral is a capital requirement, not an expense to subtract in full.', '',
              'Fee assumptions use the [IBKR Pro Fixed schedule](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php) and [SEC Section 31 rate](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2), applied as a forward cost sensitivity throughout history. The normal $0.000195/share FINRA TAF is included conservatively, despite the temporary October-December 2026 holiday. This does not claim historical invoices or a future sliced-order commission total.', '',
              '## Interpretation and remaining risk', '',
              'Current evidence supports investigating a low-overhead side strategy generating hundreds to a few thousand dollars a year at smaller tickets under these assumptions. It does not establish a six-figure annual business. At an illustrative 2% average net trading edge, $5k entries earn $100 each; $100k annual trading profit would require 1,000 completed trades per year, before overhead. Neither that trade count nor maintaining that edge at greater breadth is established.', '',
              'The drawdown figures use completed same-day P&L and omit unobserved intraday losses. A $5k short whose price triples loses $10k before costs. More fills and smaller individual loss dollars do not guarantee steadier annual profits or bounded squeeze losses. All results depend on unverified historical borrow approvals and executable routing; no live profit has been demonstrated by this experiment.', '',
              'The new intraday execution proposal and additional event families remain separate research opportunities. Their hoped-for improvement is not included in the dollar estimate. The designated execution-study holdout file was not read. H20 is a retrospective sizing sensitivity, not a newly untouched out-of-sample result.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--local-out', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if not args.local_out.resolve().is_relative_to((args.source_root/'_system/data/reverse_splits/local').resolve()):
        parser.error('Individual decisions must stay inside the ignored local workbench')
    doc = build(args.source_root, args.local_out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report(doc), encoding='utf-8')


if __name__ == '__main__':
    main()
