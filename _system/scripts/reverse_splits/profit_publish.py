"""Publish compact public event shards and aggregate strategy research to SSI."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import shutil

from .profit_data import digest, fingerprint, read, write
from .profit_evidence import status
from .profit_prices import CASES, FEE_SOURCES
from .profit_replay import SIGNALS


def public_event(e,coverage,name):
    fields=['id','deal_id','issuer','cik','ticker','family','event_date','known_at','clock_basis','exchange','source_url',
            'source_locator','source_sha256','source_dataset','accession','form','review_status','identity_status',
            'event_status','episode_start','features','locator_basis','source_hash_basis']
    out={k:e.get(k) for k in fields}
    out['name']=e.get('name') or name or ''
    if e.get('source_review'):out['source_review']=e['source_review']
    if e.get('terms_review'):
        out['terms_review']={k:v for k,v in e['terms_review'].items() if k in {'source_url','locator','evidence_known_at','source_sha256','saleable_shares','shares_before','net_proceeds','economic_state','notes','reviewer'}}
    f=e.get('financials',{})
    out['financials']={k:f.get(k) for k in ['cash','ttm_cfo','runway_years','score','period','currency','cash_pressure',
        'cash_pressure_known','status','source_url','source_sha256']}
    out['price_coverage']=coverage.get(e['id'],{})
    out['passages']=[{**r,'excerpt':r['excerpt'][:900]} for r in e.get('passages',[])[:2]]
    return out

def operations(args):
    """Public source facts and aggregate receipts only; no private trade paths."""
    def optional(name):
        path=args.work/name
        return read(path) if path.exists() else {}
    prices=optional('market_data_receipt.local.json');discovery=optional('public_discovery.local.json')
    audit=optional('liability_audit.local.json');rows=audit.get('rows',[])
    terms=optional('terms_import.json')
    if isinstance(terms,dict):terms=terms.get('records',[])
    names={e['id']:e.get('ticker') for e in read(args.work/'effective_events.local.json')}
    forward=optional('forward_policies.json')
    return {'schema_version':'short_profit_operations.v1','as_of':datetime.now(timezone.utc).isoformat(),
        'source_review':optional('source_review_receipt.json'),
        'financial_backfill':optional('financial_backfill_receipt.json'),
        'financial_coverage':optional('financial_coverage.local.json'),
        'market_data':{**{k:prices.get(k) for k in ['through','actual_last_day','overlay_rows','skipped_missing_invalid_rows','new_paid_downloads_usd','identity_warning','price_overlay_sha256','raw_manifest_sha256']},
            'distinct_requested_symbols':len({s for r in prices.get('requests',[]) if r.get('status')=='downloaded' for s in r['symbols']}),
            'successful_zero_cost_requests':sum(r.get('status')=='downloaded' for r in prices.get('requests',[])),
            'refused_chargeable_requests':sum(r.get('status')=='refused_nonzero_or_invalid_quote' for r in prices.get('requests',[]))},
        'universe_expansion':{k:discovery.get(k) for k in ['indexed_filings','processed_filings','remaining_filings','coverage_complete','since','scope']},
        'obligation_audit':{'as_of':audit.get('as_of'),'scope':audit.get('scope'),'records':len(rows),
            'primary_headers_bound':sum(bool(r.get('primary_header_bound')) for r in rows),
            'loan_terminations_verified':sum(bool(r.get('loan_termination_verified')) for r in rows),
            'rows':[{k:r.get(k) for k in ['event_id','ticker','cik','source_url','source_sha256','primary_header_bound','resolution_status','loan_termination_verified','obligation_retained']} for r in rows]},
        'reconciled_financings':[{'ticker':names.get(r['event_id']),**{k:r.get(k) for k in ['event_id','source_url','locator','evidence_known_at','source_sha256','saleable_shares','shares_before','net_proceeds','economic_state','notes']}} for r in terms],
        'forward_policies':forward,
        'account_exports':'Excluded at user request. No historical broker exports imported.',
        'borrow_monitor':'Public IBKR FTP, dated SQL archive and dashboard history; current indications are not historical loan approvals.'}


def publish(args):
    events=read(args.work/'effective_events.local.json')
    manifest=read(args.work/'source_manifest.json')
    models=read(args.work/'models.json')
    protocol=read(args.work/'protocol.json')
    coverage=read(args.work/'price_coverage.local.json')
    if models['protocol_sha256']!=protocol['sha256']:raise ValueError('Models do not match frozen protocol')
    if models['events_sha256']!=fingerprint(events):raise ValueError('Models do not match effective event evidence')
    version=fingerprint({'events':models['events_sha256'],'models':fingerprint(models),'protocol':protocol['sha256']})[:24]
    dest=args.out;dest.mkdir(parents=True,exist_ok=True)
    coverage_index={r['id']:r for r in coverage['event_coverage']}
    names={e['cik']:e['name'] for e in events if e.get('name')}
    groups=defaultdict(list)
    for e in events:groups[(e['family'],e['event_date'][:4])].append(public_event(e,coverage_index,names.get(e['cik'])))
    parts=[]
    for (family,year),group in sorted(groups.items()):
        group.sort(key=lambda e:(e['event_date'],e['id']),reverse=True)
        for start in range(0,len(group),400):
            file=dest/f'events-{family}-{year}-{start//400:03d}.json'
            write(file,{'schema_version':'short_profit_events.v1','dataset_version':version,'events':group[start:start+400]})
            parts.append({'file':file.name,'family':family,'year':year,'rows':len(group[start:start+400]),'bytes':file.stat().st_size,'sha256':digest(file)})
    source_audit=args.source_root/'_system/data/reverse_splits/local/literature_audit_2026-10-21/bibliography_audit.json'
    corrections={
        'hillion_vermaelen_2004_pipe_dreams':'Supplied May 2004 draft is Brophy, Ouimet and Sialm. Related to later PIPE paper; not an independent replication.',
        'billett_floros_garfinkel_2019_atm':'63% is ATM incidence relative to SEO incidence; capacity is not actual issuance.',
        'microcapledger_rs_study':'250-session -72.24% median uses 760 observed paths, not all 1183; pre-split-close clock.',
        'microcapledger_deficiency_study':'4720 notice rows are 2722 provider-defined episodes; raw vs benchmark-relative returns differ.',
        'frazzini_israel_moskowitz_2012_costs':'Reports more encouraging institutional costs/capacity than old estimates; not calibrated microcap cost coefficients.',
        'hou_xue_zhang_2020_replicating':'Supplied 2017 NBER draft is not assumed identical to final 2020 publication.',
        'muravyev_pearson_pollet_2022':'Supplied version is a September 2016 draft.',
    }
    literature=[]
    if source_audit.exists():
        for r in read(source_audit):
            literature.append({'id':r['audit_id'],'key':r['key'],'title':r['title'],'authors':r['authors_or_firm'],
                'year':r['year'],'type':r['type'],'url':r['url'],'available_in_supplied_pack':bool(r['resolved_files']),
                'audit_note':corrections.get(r['key']),'scope':'Catalog and identity screening; selected passages checked, not full replication.'})
    write(dest/'literature.json',{'schema_version':'short_profit_literature.v1','rows':literature})
    queue=read(args.work/'review_queue.json')
    write(dest/'review-queue.json',{'schema_version':'short_profit_review.v1','dataset_version':version,'rows':queue})
    write(dest/'corporate-actions.json',{'schema_version':'short_profit_actions.v1','dataset_version':version,
        'rows':read(args.work/'corporate_action_repairs.json')})
    evidence=status(args.work)
    ops=operations(args)
    write(dest/'operations.json',ops)
    discovery_path=args.work/'public_discovery.local.json'
    discovery=read(discovery_path) if discovery_path.exists() else {}
    discovery_receipt={k:discovery.get(k) for k in ['requests','coverage_complete','new_paid_downloads_usd','since','scope']}
    discovery_receipt.update(records=len(discovery.get('records',[])),failures=discovery.get('failures',[]),
                             sha256=digest(discovery_path) if discovery_path.exists() else None)
    patient_path=args.source_root/'_system/data/reverse_splits/patient_execution_2026-10-20.json'
    if not patient_path.exists():patient_path=Path(__file__).resolve().parents[2]/'data/reverse_splits/patient_execution_2026-10-20.json'
    patient=read(patient_path) if patient_path.exists() else None
    old=[]
    if patient:
        for r in patient['models']:
            if r['minutes']==60 and r['mode']=='flow' and r.get('participation',.05)==.05:
                old.append({k:r.get(k) for k in ['id','case','target','annual_pnl','net_pnl','mean_position','max_dd_dollars',
                    'cover_residual_fraction','cover_residual_trades','residual_gap20','residual_gap100','peak_margin','peak_collateral']})
    repaired=read(args.work/'patient_liabilities.json') if (args.work/'patient_liabilities.json').exists() else None
    count=Counter(e['family'] for e in events)
    summary={'schema_version':'short_profit_program.v1','dataset_version':version,'built_at':datetime.now(timezone.utc).isoformat(),
        'research_only':True,'authority':'none','nav':10_000_000,'counts':dict(count),'issuers':len({e['issuer'] for e in events}),
        'source_manifest':manifest,'public_discovery':discovery_receipt,'operations':ops,'protocol':protocol,'cases':list(CASES.values()),'signals':[{'id':i,'label':l} for i,l in SIGNALS],
        'models':models['models'],'research_code_sha256':models['code_sha256'],'price_coverage':coverage['counts'],'corporate_actions':coverage['corporate_actions'],'evidence':evidence,
        'study_aggregates':read(args.work/'study_aggregates.json'),'parts':parts,
        'review_panel_size':len(queue),'defaults':{'signal':'financing_cash','horizon':5,'target':25000,'case':'base','sizing':'fixed','exit_policy':'time'},
        'legacy_patient_reference':old,'patient_liability_replay':repaired,
        'cost_evidence':{'base_roundtrip_25k':.0595,'quoted_spread_roundtrip':.0172,'incremental_depth_at25k':.0423,
            'basis':'Conditional static-book median at $25k; square-root size interpolation and transfer to new event dates are assumptions. Not measured patient $25k-$50k fills.',
            'borrow_basis':'20/50/150% APR sensitivities. Not a verified historical loan series.',
            'proceeds_interest_basis':'Current IBKR Pro tiers frozen as a sensitivity; existing USD shorts consume the first $100k band. Calendar-day settled collateral; no repeated zero band.',
            'other_fee_allowance':'$0.000003/share both sides is a fixed venue/CAT allowance, not a historical CAT-rate reconstruction.',
            'sources':FEE_SOURCES},
        'stages':[
            {'label':'Dataset and source links','status':'implemented','detail':'Public metadata shards; source hashes; PIT feature/outcome separation.'},
            {'label':'100-episode verification','status':'in_review' if evidence['source_reviews'] else 'awaiting_source_review','detail':f"{evidence['source_reviews']} reviewed; {evidence['review_passes']} pass all checks. Extracted context is not a reconciled cap table."},
            {'label':'Costed holding and sizing tests','status':'implemented_conditional','detail':f"{len(models['models'])} registered comparisons; all retained, including empty/unresolved cases."},
            {'label':'Observed execution calibration','status':'awaiting_evidence','detail':f"{evidence['observed_fills']} observed fills; {evidence['nbbo_matched_fills']} matched to verified NBBO."},
            {'label':'Prospective strategy validation','status':'collecting' if evidence['frozen_estimates'] else 'awaiting_frozen_estimates','detail':f"{evidence['frozen_estimates']} frozen estimates; {evidence['frozen_abstentions']} abstentions; {evidence['evaluated_forecasts']} outcomes."},
            {'label':'Production readiness','status':'not_demonstrated','detail':'Requires sufficient forward outcomes, completed covers, real borrow and shared-account risk evidence.'}],
        'limitations':[
            'The supplied datasets and cached SEC corpus are incomplete discovery sources, not a full-market financing universe.',
            'Provider event dates, issuer aliases and inferred financing states require source review. No executed issuance is inferred from registration capacity.',
            'Daily OHLC4 execution, 5% recorded-flow capacity, SSR capture, impact and borrow are assumptions; prices are not verified NBBO or broker fills.',
            'Uncovered positions and fractional corporate-action obligations remain marked liabilities; stale prices can understate loss.',
            'Trading P&L deducts modeled execution, commissions, regulatory charges and carry, with a credit-interest sensitivity. Unverified locate charges, dividends/corporate-action cash, operating overhead and tax are not established; full business net income is unproven.',
            'Market data, private broker records and full research PDFs remain local. The designated sealed holdout was not read.',
            'No real-time broker connection, orders, ThetaData or new paid downloads. $20k/month is a commercial target, not a return forecast.'],
        'sources':[
            {'label':'Reverse-split study','url':'https://microcapledger.com/research/what-happens-after-reverse-split/'},
            {'label':'Deficiency study','url':'https://microcapledger.com/research/nasdaq-deficiency-notice-outcomes/'},
            {'label':'SEC original filing archive','url':'https://www.sec.gov/edgar/search/'}]}
    write(dest/'summary.json',summary)
    write(dest.parent/'profit_program_research_2026-10-22.json',{
        'schema_version':'short_profit_research_receipt.v1','built_at':summary['built_at'],'aggregate_only':True,
        'hypothesis_ids':protocol['protocol']['hypotheses'],'protocol_sha256':protocol['sha256'],
        'dataset_version':version,'summary_ref':'profit_program/summary.json','comparisons':len(models['models']),
        'assessment':'Exploratory conditional results. Source, corporate-action and security-linkage repairs occurred during development. Not validated profitability or production authority.'})
    write(dest/'manifest.json',{'schema_version':'short_profit_manifest.v1','dataset_version':version,
        'summary_sha256':digest(dest/'summary.json'),'parts':parts,'files':[
            {'file':n,'sha256':digest(dest/n)} for n in ['literature.json','review-queue.json','corporate-actions.json','operations.json','baseline-2026-10-22.json'] if (dest/n).exists()]})
    # Copy the authored audit, not third-party full-text papers.
    report=args.source_root/'output/pdf/short_alpha_literature_audit_and_profit_plan_2026-10-21.pdf'
    if report.exists():shutil.copyfile(report,dest/'audit-2026-10-21.pdf')
    args.dashboard.mkdir(parents=True,exist_ok=True)
    shutil.copytree(dest,args.dashboard,dirs_exist_ok=True)
    print(f'Published {len(events)} event records in {len(parts)} shards and {len(models["models"])} comparisons.',flush=True)
