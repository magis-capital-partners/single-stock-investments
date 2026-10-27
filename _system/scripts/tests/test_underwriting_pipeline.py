"""The real author -> challenger -> compiler -> shared forecast boundary."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from underwriting_contract import (
    CHECKS,
    ContractError,
    compile_contract,
    digest,
    validate_review,
)


def packet():
    p = {'schema_version': 'underwriting-evidence/1', 'ticker': 'TEST', 'company': 'Test business',
         'as_of': '2026-10-26', 'currency': 'USD', 'evidence_hash': 'a'*64, 'financial_period': '2025-12-31',
         'share_basis': {'as_of': '2026-10-26', 'symbol': 'TEST', 'source_url': 'https://issuer.test/shares'},
         'latest_report': {'period': '2025-12-31', 'filed': '2026-02-01'},
         'observations': [
             {'id': 'cash_obs', 'value': 1000, 'unit': 'USD', 'period': '2025-12-31',
              'field': 'ocf', 'source_url': 'https://issuer.test/annual', 'locator': 'Annual cash flow', 'source_kind': 'primary'},
             {'id': 'shares_obs', 'value': 100, 'unit': 'shares', 'period': '2025-12-31',
              'field': 'shares', 'source_url': 'https://issuer.test/annual', 'locator': 'Annual diluted shares', 'source_kind': 'primary'}],
         'documents': []}
    p['packet_hash'] = digest(p)
    return p


def contract(p=None):
    p = p or packet()
    def assumption(i, value, unit='ratio'):
        return {'id': i, 'value': value, 'unit': unit, 'allowed_range': {'min': 0, 'max': max(1, value*2)},
                'rationale': 'Company cash generation supports this explicit judgment.', 'evidence_ids': ['cash_obs'],
                'counterevidence': 'A sustained cash decline would contradict the forecast.',
                'falsifier': 'Two reported periods below the modeled cash baseline.', 'review_trigger': 'New primary report.'}
    return {'schema_version': 'underwriting-contract/1', 'ticker': 'TEST', 'as_of': p['as_of'],
            'packet_hash': p['packet_hash'], 'evidence_hash': p['evidence_hash'], 'currency': 'USD',
            'framework': 'operating_dcf', 'framework_rationale': 'An operating cash franchise.',
            'archetype': 'compounder', 'archetype_rationale': 'A recurring operating cash franchise with measured reinvestment.',
            'alternatives_considered': [{'framework': 'asset_nav', 'reason_rejected': 'Ongoing cash generation drives value.'}],
            'horizon_years': 2, 'horizon_rationale': 'Two explicit forecast years before exit.',
            'review_due': '2027-01-24', 'financial_period': '2025-12-31',
            'facts': [{'id': 'reported_cash', 'observation_id': 'cash_obs'}, {'id': 'shares', 'observation_id': 'shares_obs'}],
            'component_inventory': [{'id': 'parent_business', 'treatment': 'modeled', 'component_ids': ['business'],
                                     'rationale': 'The operating component includes all parent claims with no separate debt addition.',
                                     'evidence_ids': ['cash_obs']}],
            'assumptions': [assumption('normalization', 1), assumption('discount_rate', .1), assumption('terminal_multiple', 10, 'multiple')],
            'checklist': {k: {'conclusion': 'Explicitly considered; see sourced cash and share bridge.', 'evidence_ids': ['cash_obs']} for k in CHECKS},
            'components': [{'id': 'business', 'category': 'operating_business', 'claim_scope': 'Parent common equity',
                            'scope_reconciliation': 'Cash and diluted shares belong to the same parent claim.',
                            'drivers': [
                                {'id': 'normalized_cash', 'op': 'multiply', 'args': ['reported_cash', 'normalization'], 'unit': 'USD'},
                                {'id': 'cash_ps', 'op': 'divide', 'args': ['normalized_cash', 'shares'], 'unit': 'USD per share'},
                                {'id': 'terminal_ps', 'op': 'multiply', 'args': ['cash_ps', 'terminal_multiple'], 'unit': 'USD per share'}],
                            'discount_rate_ref': 'discount_rate',
                            'cashflows': [{'year': 1, 'amount_ref': 'cash_ps'}, {'year': 2, 'amount_ref': 'cash_ps'},
                                          {'year': 2, 'amount_ref': 'terminal_ps'}]}]}


def review(c):
    return {'schema_version': 'underwriting-review/1', 'ticker': c['ticker'], 'packet_hash': c['packet_hash'],
            'contract_hash': digest(c), 'verdict': 'approve', 'framework_accepted': True,
            'assumption_coverage': [a['id'] for a in c['assumptions']], 'checklist_coverage': list(CHECKS),
            'component_inventory_coverage': [i['id'] for i in c['component_inventory']],
            'findings': [], 'independent_thesis': 'Normalized cash supports this range, with explicit downside sensitivity.'}


def test_compiler_uses_frozen_observations_and_existing_forecast_engine():
    from test_shared_valuation_forecast import sourced_market, sourced_quote
    from valuation_forecast import build_forecast
    p, c = packet(), contract()
    value = compile_contract(p, c)
    f = build_forecast(value, quote=sourced_quote(), market=sourced_market(underwriting_validation={'status': 'verified', 'contract_hash': digest(c)}),
                       as_of='2026-10-26', evaluated_at='2026-10-26T23:00:00+00:00')
    assert f['status'] == 'available', f['gaps']
    assert f['present_value_today_per_share']['base'] == pytest.approx(100)
    assert f['forward_irr_pct']['base'] == pytest.approx(10, abs=.001)
    assert value['valuation_methodology']['automation'] == 'independent_underwriting'


@pytest.mark.parametrize('archetype,framework,profile', [
    ('compounder','operating_dcf','quality_reinvestment'),
    ('cyclical','sum_of_parts','capital_cycle'),
    ('financial_balance_sheet','financial_equity','credit_and_normalized_returns'),
    ('pre_profit','inventory_runoff','catalyst_asset_value'),
    ('utility','operating_dcf','predictable_cash_flow'),
    ('resource','royalty_cashflow','scarce_asset_optionality'),
])
def test_reviewed_company_economics_route_from_fresh_classification(archetype, framework, profile):
    from valuation_method_router import route_valuation
    c = contract()
    c.update(archetype=archetype,framework=framework)
    model = compile_contract(packet(),c)
    model['classification_inputs'] = {'archetype':'compounder'}
    assert route_valuation(model)['profile_id'] == profile


@pytest.mark.parametrize('ratio', [2, 5, .5])
def test_listing_receipts_convert_ordinary_share_cashflows_exactly_once(ratio):
    from test_shared_valuation_forecast import sourced_market, sourced_quote
    from valuation_forecast import build_forecast
    p = packet()
    p['listing_ratio'] = {'ordinary_shares_per_listing_share': ratio, 'source_url': 'https://issuer.test/depositary',
                          'source_as_of': '2025-12-31', 'locator': 'Common shares represented by one depositary receipt'}
    p['packet_hash'] = digest({k: v for k, v in p.items() if k != 'packet_hash'})
    c = contract(p)
    model = compile_contract(p, c)
    f = build_forecast(model, quote=sourced_quote(value=100*ratio),
                       market=sourced_market(underwriting_validation={'status': 'verified', 'contract_hash': digest(c)}),
                       as_of='2026-10-26', evaluated_at='2026-10-26T23:00:00+00:00')
    assert f['status'] == 'available', f['gaps']
    assert f['present_value_today_per_share']['base'] == pytest.approx(100*ratio)
    assert f['forward_irr_pct']['base'] == pytest.approx(10, abs=.001)
    assert compile_contract(p, c) == model
    assert sum(i['id'] == 'compiled_listing_ratio' for i in model['component_valuation_results']['additive_components'][0]['calculation_proof']['inputs']) == 1


@pytest.mark.parametrize('text,expected', [
    ('American depositary shares, each representing five common shares.', 5),
    ('Each ADS represents two Class A ordinary shares.', 2),
    ('Two American depositary shares represent one ordinary share.', .5),
    ('American depositary shares each of which represents eight Class A ordinary shares.', 8),
    ('Each ADS represents five (5) common shares.', 5),
])
def test_listing_ratio_is_extracted_from_frozen_primary_disclosure(text, expected):
    from underwriting_evidence import listing_ratio_from_documents
    doc = {'contexts': [text], 'filed': '2026-08-01', 'period': '2026-06-30',
           'source_url': 'https://issuer.test/filing', 'content_hash': 'a'*64}
    ratio = listing_ratio_from_documents([doc])
    assert ratio['ordinary_shares_per_listing_share'] == expected
    assert ratio['locator'] in text
    assert ratio['document_hash'] == doc['content_hash']
    with pytest.raises(ContractError, match='ambiguous'):
        listing_ratio_from_documents([{**doc, 'contexts': [text, 'Each ADS represents three ordinary shares.']}])


def test_frozen_contexts_keep_the_first_depositary_representation():
    from underwriting_evidence import document_record, listing_ratio_from_documents
    raw = ('<html>Each ADS represents five (5) common shares. '+('Business disclosure. '*250)
           +'Each ADS or common share purchased under the employee program.</html>').encode()
    doc = document_record('https://issuer.test/annual', raw)
    doc.update(period='2025-12-31', filed='2026-04-16')
    assert listing_ratio_from_documents([doc])['ordinary_shares_per_listing_share'] == 5


@pytest.mark.parametrize('mutate', [
    lambda c: c.update(packet_hash='b'*64),
    lambda c: c['facts'][0].update(value=99999),
    lambda c: c['assumptions'][0].pop('counterevidence'),
    lambda c: c['assumptions'][0].update(evidence_ids=['invented']),
    lambda c: c['checklist'].pop('normalization'),
    lambda c: c['components'][0]['drivers'][0].update(args=['reported_cash', 18]),
    lambda c: c['components'][0]['drivers'][1].update(args=['normalized_cash', 'discount_rate']),
    lambda c: c['components'][0]['cashflows'][0].update(year=8),
    lambda c: c.update(horizon_years=7),
])
def test_unverified_facts_hidden_constants_missing_judgments_and_unit_errors_are_rejected(mutate):
    c = contract()
    mutate(c)
    with pytest.raises(ContractError):
        compile_contract(packet(), c)


def test_incomplete_or_stale_challenge_cannot_approve_the_builder():
    c = contract()
    validate_review(c, review(c))
    for key, value in [('contract_hash', 'x'), ('assumption_coverage', []), ('verdict', 'revise'),
                       ('findings', [{'severity': 'major', 'resolved': False, 'detail': 'Peak cash is unnormalized.'}])]:
        r = review(c)
        r[key] = value
        with pytest.raises(ContractError):
            validate_review(c, r)


def test_price_only_collection_skips_financial_collection(tmp_path, monkeypatch):
    import refresh_shared_forecasts as refresh
    from test_valuation_market_sync import fixture
    fixture(tmp_path)
    calls = []
    monkeypatch.setattr(refresh, 'refresh_missing_model_inputs', lambda *a: pytest.fail('Price-only repricing fetched financials'))
    monkeypatch.setattr(refresh, 'refresh_quote', lambda *a: calls.append(a[0]))
    refresh.run(tmp_path, '2026-10-26', collect=True, prices_only=True)
    assert calls == ['BKNG']


def test_after_close_publication_has_an_event_trigger_and_lightweight_fallbacks():
    import yaml
    root = Path(__file__).resolve().parents[3]
    doc = yaml.safe_load((root/'.github/workflows/autonomous-compounders.yml').read_text())
    trigger = doc.get('on', doc.get(True))
    assert 'Market Close' in trigger['workflow_run']['workflows']
    assert any('16' in r['cron'] and r.get('timezone') == 'America/New_York' for r in trigger['schedule'])
    assert '--prices-only' in str(doc)


def test_production_underwriting_checkout_contains_the_approved_method_registry():
    import subprocess

    import yaml
    root = Path(__file__).resolve().parents[3]
    doc = yaml.safe_load((root/'.github/workflows/valuation-underwriting.yml').read_text())
    checkout = next(s for s in doc['jobs']['underwrite']['steps'] if s.get('uses') == 'actions/checkout@v4')
    paths = checkout['with']['sparse-checkout']
    assert '/_system/reference/valuation_method_registry.json' in paths.splitlines()
    related = '/_system/reference/market-data/valuation_related_evidence/'
    assert related in paths.splitlines()
    assert related in (root/'_system/scripts/underwriting_local.ps1').read_text()
    marker = related.strip('/')+'/README.md'
    assert subprocess.check_output(['git', 'ls-files', '--error-unmatch', '--', marker], cwd=root, text=True).strip() == marker
    assert '/.github/workflows/autonomous-compounders.yml' in paths.splitlines()
    assert '/.github/workflows/valuation-underwriting.yml' in paths.splitlines()


def company_root(root):
    import underwriting_pipeline as pipeline
    from test_shared_valuation_forecast import sourced_market, sourced_quote
    def save(path, value):
        pipeline.write(root/path, value)
    save(Path('dashboard/data/core.json'), {'tickers': [{'ticker': 'TEST', 'company': 'Test business'}]})
    save(Path('_system/reference/market-data/valuation_quotes/TEST.json'),
         {'quote': sourced_quote(), 'corporate_actions': sourced_market()})
    save(pipeline.POLICY, {'required_contract_schema': 'underwriting-contract/1', 'maximum_companies_per_run': 1, 'maximum_batch_size': 3, 'maximum_author_attempts': 2})
    save(pipeline.CALL_POLICY, {'default': {'daily_repo_limit': 6, 'per_subject_daily_limit': 2, 'cooldown_hours': 0},
                              'model_ladder': {'default_model': 'cheap', 'frontier_model': 'strong', 'consumers': {
                                  role: {'frontier_reasons': ['company_underwriting']} for role in ('valuation_underwriter', 'valuation_challenger')}}})
    prompts = root/'_system/prompts'
    prompts.mkdir(parents=True)
    (prompts/'valuation_underwriting.md').write_text('Frozen primary evidence; isolated roles.', encoding='utf-8')


def mock_stages(c, calls, *, bad_review=False, bad_builder=False):
    import underwriting_pipeline as pipeline
    def execute(stage, payload, output, receipt_path):
        calls.append(stage)
        if stage == 'author':
            answer = c
        elif stage == 'challenger':
            answer = review(c)
            if bad_review:
                answer['findings'] = [{'severity': 'major', 'detail': 'The normalized earnings baseline is unproven.'}]
        else:
            answer = copy.deepcopy(payload['canonical_model'])
            if bad_builder:
                answer['inputs']['price'] = 12345
        pipeline.write(output, answer)
        pipeline.write(receipt_path, {'agent_id': stage+'-'+str(len(calls)), 'status': 'finished', 'run_id': 'run-'+str(len(calls))})
    return execute


def test_end_to_end_writes_only_independently_reviewed_models_and_replays_private_evidence(tmp_path, monkeypatch):
    import refresh_shared_forecasts as refresh
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    monkeypatch.setattr(pipeline, 'today', lambda: '2026-10-26')
    monkeypatch.setattr(refresh, 'refresh_quote', lambda *a, **kw: None)
    monkeypatch.setattr(refresh, 'refresh_missing_model_inputs', lambda *a: None)
    p, c, calls = packet(), contract(), []
    result = pipeline.run_batch(tmp_path, launch=True, work=tmp_path/'work', vault=tmp_path/'vault',
                                prepare=lambda *a: p, execute=mock_stages(c, calls))
    assert result['completed'] == ['TEST'] and result['blocked'] == []
    assert calls == ['author', 'challenger']
    receipt = pipeline.validate_saved(tmp_path, 'TEST', tmp_path/'vault')
    assert receipt['requires_human_review'] is False
    assert len({receipt['stages'][s]['agent_id'] for s in ('author', 'challenger')}) == 2
    assert receipt['stages']['builder']['provider'] == 'deterministic'
    assert receipt['stages']['builder']['model_calls'] == 0
    assert pipeline.build_queue(tmp_path, '2026-10-26')['summary']['statuses'] == {'reviewed': 1}


@pytest.mark.parametrize('bad_review,bad_builder', [(True, False), (False, True)])
def test_failed_challenge_or_builder_cannot_replace_an_existing_model(tmp_path, monkeypatch, bad_review, bad_builder):
    import refresh_shared_forecasts as refresh
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    original = {'ticker': 'TEST', 'sentinel': 'Existing model must survive'}
    pipeline.write(tmp_path/'TEST/research/valuation.json', original)
    monkeypatch.setattr(pipeline, 'today', lambda: '2026-10-26')
    monkeypatch.setattr(refresh, 'refresh_quote', lambda *a, **kw: None)
    monkeypatch.setattr(refresh, 'refresh_missing_model_inputs', lambda *a: None)
    calls = []
    if bad_builder:
        original_compiler = pipeline.compiled_build
        def corrupt(*args):
            value, receipt = original_compiler(*args)
            value['inputs']['price'] = 12345
            return value, receipt
        monkeypatch.setattr(pipeline, 'compiled_build', corrupt)
    result = pipeline.run_batch(tmp_path, launch=True, work=tmp_path/'work', vault=tmp_path/'vault', prepare=lambda *a: packet(),
                                execute=mock_stages(contract(), calls, bad_review=bad_review, bad_builder=bad_builder))
    assert not result['completed'] and result['blocked'][0]['ticker'] == 'TEST'
    assert pipeline.read(tmp_path/'TEST/research/valuation.json') == original
    assert not (tmp_path/'TEST/research/underwriting_receipt.json').exists()
    assert 'automatic_retry_pending' in result['queue_summary']['statuses']


def test_price_changes_do_not_trigger_paid_underwriting_but_new_financial_facts_do(tmp_path):
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    before = pipeline.input_fingerprint(tmp_path, 'TEST')
    quote = tmp_path/'_system/reference/market-data/valuation_quotes/TEST.json'
    value = pipeline.read(quote)
    value['quote']['value'] *= 2
    pipeline.write(quote, value)
    assert pipeline.input_fingerprint(tmp_path, 'TEST') == before
    pipeline.write(tmp_path/'_system/reference/market-data/valuation_fundamentals/TEST.json', {'facts': [{'field': 'ocf', 'value': 100}]})
    assert pipeline.input_fingerprint(tmp_path, 'TEST') != before


def test_challenger_findings_are_returned_to_the_author_for_automatic_revision(tmp_path, monkeypatch):
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    calls, author_payloads = [], []
    c = contract()
    def execute(stage, payload, output, receipt_path):
        calls.append(stage)
        if stage == 'author':
            author_payloads.append(payload)
            answer = c
        elif stage == 'challenger':
            answer = review(c)
            answer.update(verdict='revise', findings=[{'severity': 'major', 'detail': 'Separate the captive finance debt claim.'}])
        else:
            pytest.fail('The builder must not receive an unapproved contract')
        pipeline.write(output, answer)
        pipeline.write(receipt_path, {'agent_id': stage+'-'+str(len(calls)), 'status': 'finished'})
    with pytest.raises(pipeline.StageBlocked):
        pipeline.run_company(tmp_path, tmp_path/'work', 'TEST', '2026-10-26', {}, tmp_path/'vault',
                             prepare=lambda *a: packet(), execute=execute)
    assert len(author_payloads) == 2
    findings = author_payloads[1]['revision_feedback']['independent_challenge']['findings']
    assert findings[0]['detail'] == 'Separate the captive finance debt claim.'


def test_rejected_proposals_resume_with_full_critique_across_batches(tmp_path, monkeypatch):
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    settings = pipeline.read(tmp_path/pipeline.POLICY)
    settings['maximum_author_attempts'] = 1
    pipeline.write(tmp_path/pipeline.POLICY, settings)
    monkeypatch.setattr(pipeline, 'evaluate', lambda **kw: {'approved': True})
    calls, payloads, state = [], [], {}
    c = contract()
    def execute(stage, payload, output, receipt_path):
        calls.append(stage)
        if stage == 'author':
            payloads.append(payload)
            answer = c
        else:
            answer = review(c)
            answer.update(verdict='revise', independent_thesis='A long independent thesis. '*180,
                          findings=[{'severity':'major','detail':'Retained cash must fund the merchant liability.'}])
        pipeline.write(output, answer)
        pipeline.write(receipt_path, {'agent_id':stage+str(len(calls)), 'status':'finished', 'finished_at':pipeline.now()})
    for _ in range(2):
        with pytest.raises(pipeline.StageBlocked):
            pipeline.run_company(tmp_path,tmp_path/'work','TEST','2026-10-26',state,tmp_path/'vault',
                                 prepare=lambda *a:packet(),execute=execute)
    assert calls == ['author','challenger','author']  # Identical rejected proposal reuses its review.
    assert payloads[1]['revision_feedback']['previous_contract'] == c
    assert payloads[1]['revision_feedback']['independent_challenge']['findings'][0]['detail'].startswith('Retained cash')
    assert pipeline.read(tmp_path/'work/progress/TEST.json')['history']


def test_approved_strong_stages_resume_after_a_compiler_interruption(tmp_path, monkeypatch):
    import refresh_shared_forecasts as refresh
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    monkeypatch.setattr(pipeline,'today',lambda:'2026-10-26')
    monkeypatch.setattr(refresh,'refresh_quote',lambda *a,**kw:None)
    monkeypatch.setattr(refresh,'refresh_missing_model_inputs',lambda *a:None)
    calls, state, c = [], {}, contract()
    execute = mock_stages(c,calls)
    compiler = pipeline.compiled_build
    monkeypatch.setattr(pipeline, 'compiled_build', lambda *args: (_ for _ in ()).throw(pipeline.StageBlocked('interrupted assembly')))
    with pytest.raises(pipeline.StageBlocked):
        pipeline.run_company(tmp_path,tmp_path/'work','TEST','2026-10-26',state,tmp_path/'vault',
                             prepare=lambda *a:packet(),execute=execute)
    monkeypatch.setattr(pipeline, 'compiled_build', compiler)
    result = pipeline.run_company(tmp_path,tmp_path/'work','TEST','2026-10-26',state,tmp_path/'vault',
                                  prepare=lambda *a:packet(),execute=execute)
    assert result['status'] == 'validated'
    assert calls == ['author','challenger']


def test_only_pull_request_creation_uses_the_existing_service_credential(monkeypatch):
    import json

    import publish_underwriting as publisher
    monkeypatch.setenv('GH_TOKEN','default-repository-token')
    monkeypatch.setenv('UNDERWRITING_PR_TOKEN','existing-service-token')
    used = []
    def execute(args, **kw):
        used.append((args,kw.get('env',{}).get('GH_TOKEN')))
        return json.dumps({'number':1}).encode()
    monkeypatch.setattr(publisher.subprocess,'check_output',execute)
    publisher.github('example/test','pulls',{'title':'Data publication'})
    publisher.github('example/test','dispatches',{'event_type':'underwriting-validate-pr'})
    assert [token for _,token in used] == ['existing-service-token','default-repository-token']


def test_pre_checkpoint_paid_reviews_are_recovered_with_the_latest_proposal(tmp_path, monkeypatch):
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    monkeypatch.setattr(pipeline,'evaluate',lambda **kw:{'approved':True})
    work, state, c = tmp_path/'work', {}, contract()
    for index in range(2):
        c = copy.deepcopy(c)
        c['assumptions'][0]['value'] -= .05
        def execute(stage,payload,output,receipt_path):
            answer = c if stage == 'author' else {**review(c),'verdict':'revise',
                        'findings':[{'severity':'major','detail':'Unresolved financing '+str(index)}]}
            pipeline.write(output,answer)
            pipeline.write(receipt_path,{'agent_id':stage+str(index),'status':'finished',
                                        'finished_at':f'2026-10-26T0{index}:00:00+00:00'})
        pipeline.call_stage(tmp_path,work,'TEST','author',{'packet':packet(),'attempt':index},state,execute=execute)
        pipeline.call_stage(tmp_path,work,'TEST','challenger',
                            pipeline.challenge_payload(packet(),c,compile_contract(packet(),c)),state,execute=execute)
    saved = pipeline.load_progress(tmp_path,work,'TEST',packet())
    assert len(saved['history']) == 2
    assert saved['feedback']['previous_contract'] == c
    assert saved['feedback']['independent_challenge']['findings'][0]['detail'].endswith('1')
    changed = packet()
    changed['packet_hash'] = 'f'*64
    assert pipeline.load_progress(tmp_path,work,'TEST',changed)['feedback'] is None


def test_new_evidence_preserves_saved_unresolved_criticism_without_reusing_approval(tmp_path):
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    work=tmp_path/'work'
    pipeline.write(work/'progress/TEST.json',{'scope':'old','packet_hash':'old','history':[],
        'feedback':{'required_correction':'Funding access is unsupported.',
                    'independent_challenge':{'findings':[{'severity':'major','detail':'Execute unavailable owner funding.'}]}}})
    result=pipeline.load_progress(tmp_path,work,'TEST',packet())
    assert 'approved' not in result
    assert 'CURRENT packet' in result['feedback']['required_correction']
    assert pipeline.unresolved_findings(result['feedback'])[0]['detail']=='Execute unavailable owner funding.'


def test_retrieving_more_context_keeps_the_rejected_contract_and_its_major_findings(tmp_path,monkeypatch):
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    policy=pipeline.read(tmp_path/pipeline.POLICY)
    pipeline.write(tmp_path/pipeline.POLICY,{**policy,'maximum_author_attempts':3})
    monkeypatch.setattr(pipeline,'evaluate',lambda **kw:{'approved':True})
    monkeypatch.setattr(pipeline,'today',lambda:'2026-10-26')
    first,expanded=packet(),packet()
    expanded['evidence_hash']='e'*64
    expanded['packet_hash']=digest({k:v for k,v in expanded.items() if k!='packet_hash'})
    def prepare(*args,focus_keywords=()):return expanded if focus_keywords else first
    monkeypatch.setattr(pipeline,'prepare_packet',prepare)
    old,new=contract(first),contract(expanded)
    counts={'author':0,'challenger':0}
    finding={'severity':'major','detail':'Funding is not established before senior payments fall due.'}
    def execute(stage,payload,output,receipt_path):
        counts[stage]+=1
        if stage=='author':
            if counts[stage]==1:answer=old
            elif counts[stage]==2:answer={'status':'evidence_gap','gaps':[{'code':'funding_terms','detail':"Retrieve Note 9 and search terms: 'maturity'."}]}
            else:
                feedback=payload['revision_feedback']
                assert feedback['previous_contract']==old
                assert finding in feedback['prior_findings']
                assert feedback['independent_challenge']['findings']==[finding]
                answer=new
        else:
            answer=review(old if counts[stage]==1 else new)
            if counts[stage]==1:answer.update(verdict='revise',findings=[finding])
        pipeline.write(output,answer)
        pipeline.write(receipt_path,{'agent_id':stage+str(counts[stage]),'status':'finished'})
    result=pipeline.run_batch(tmp_path,launch=True,work=tmp_path/'work',vault=tmp_path/'vault',phase='author',prepare=prepare,execute=execute)
    assert result['approved']==['TEST'],result
    assert counts=={'author':3,'challenger':2}


@pytest.mark.parametrize('unapproved',[False,True])
def test_publication_recovery_checks_the_producer_and_the_data_only_diff(monkeypatch, unapproved):
    import publish_underwriting as publisher
    monkeypatch.setenv('GITHUB_REPOSITORY','example/test')
    events = []
    def api(repo,path,payload=None):
        if path.startswith('actions/runs/'):
            return {'path':'.github/workflows/valuation-underwriting.yml','head_repository':{'full_name':repo}}
        if path.startswith('compare/'):
            return {'files':[{'filename':'unexpected.py' if unapproved else '_system/data/underwriting_queue.json','status':'modified'}],
                    'commits':[{'sha':'a'*40}]}
        if path.startswith('pulls?'):
            return []
        events.append((path,payload))
        return {'number':42,'html_url':'https://example.test/pull/42','head':{'sha':'a'*40}}
    monkeypatch.setattr(publisher,'github',api)
    if unapproved:
        with pytest.raises(ContractError,match='unapproved changes'):
            publisher.recover_publication('codex/underwriting-1234')
        assert not events
    else:
        result = publisher.recover_publication('codex/underwriting-1234')
        assert result['status'] == 'checks_requested'
        assert [p['event_type'] for path,p in events if path == 'dispatches'] == ['research-quality-pr','underwriting-validate-pr']
    with pytest.raises(ContractError,match='Not a producer branch'):
        publisher.recover_publication('codex/untrusted-code')


def test_supplemental_numbers_are_checked_against_the_exact_frozen_table():
    from underwriting_evidence import supplemental_observations
    p = packet()
    text = 'Reporting period 2026 June 30, amounts in millions. Automotive operating cash flow $1,234.'
    p['documents'] = [{'id': 'annual', 'source_url': 'https://issuer.test/annual', 'content_hash': 'a'*64, 'contexts': [text]}]
    row = {'id': 'extra', 'document_id': 'annual', 'quote': text, 'numeric_token': '$1,234', 'scale': 1_000_000,
           'unit': 'USD', 'period': '2026-06-30', 'measurement_type': 'flow', 'scope': 'Automotive parent business', 'locator': 'Cash flow table'}
    assert supplemental_observations(p, [row])[0]['value'] == 1_234_000_000
    for changed in [{'numeric_token': '234'}, {'scale': 1000}, {'period': '2025-06-30'}, {'quote': text.replace('$1,234', '$9,999')}]:
        with pytest.raises(ContractError):
            supplemental_observations(p, [{**row, **changed}])


@pytest.mark.parametrize('share_field', ['shares', 'ordinary_shares'])
def test_packet_is_cold_and_a_financial_company_does_not_need_compounder_cash_inputs(tmp_path, share_field):
    import underwriting_pipeline as pipeline
    from underwriting_evidence import prepare_packet
    company_root(tmp_path)
    pipeline.write(tmp_path/'TEST/research/valuation.json', {'inputs': {'price': 987654321}, 'classification': {'archetype': 'old_wrong_label'}})
    rows = []
    for field, value, currency in [('net_income', 1000, 'USD'), ('equity', 5000, 'USD'), (share_field, 100, 'USD')]:
        rows.append({'field': field, 'value': value, 'currency': currency, 'period': '2025-12-31',
                     'source_kind': 'primary', 'source_url': 'https://issuer.test/annual', 'locator': field})
    pipeline.write(tmp_path/'_system/reference/market-data/valuation_fundamentals/TEST.json', {'facts': rows})
    p = prepare_packet(tmp_path, 'TEST', '2026-10-26', collect=False)
    rendered = str(p)
    assert '987654321' not in rendered and 'old_wrong_label' not in rendered
    assert 'quote' not in p and 'classification' not in p and 'valuation' not in p
    assert p['financial_period'] == '2025-12-31'
    assert {'net_income', 'equity', share_field} <= {o['field'] for o in p['observations']}


def test_changed_primary_kpis_reach_the_packet_but_collection_clocks_do_not_trigger_paid_work(tmp_path):
    import underwriting_pipeline as pipeline
    from underwriting_evidence import prepare_packet
    company_root(tmp_path)
    facts = [{'field': f, 'value': v, 'currency': 'USD', 'period': '2025-12-31', 'source_kind': 'primary',
              'source_url': 'https://issuer.test/annual', 'locator': f} for f,v in [('net_income',1000),('shares',100)]]
    pipeline.write(tmp_path/'_system/reference/market-data/valuation_fundamentals/TEST.json', {'facts': facts})
    path = tmp_path/'_system/reference/market-data/operating_kpis/TEST.json'
    point = {'kpi': 'monthly_volume', 'value': 100, 'unit': 'vehicles', 'period': '2026-09-30',
             'source_url': 'https://issuer.test/traffic', 'doc': 'September volumes', 'source_kind': 'primary', 'claim_type': 'fact'}
    pipeline.write(path, {'points': [point], 'fetched_at': '2026-10-25'})
    before = pipeline.input_fingerprint(tmp_path, 'TEST')
    packet_before = prepare_packet(tmp_path, 'TEST', '2026-10-26', collect=False)
    assert any('monthly_volume' in ' '.join(d['contexts']) for d in packet_before['documents'])
    pipeline.write(path, {'points': [{**point,'fetched_at':'2026-10-26T22:00:00Z'},
                                    {**point,'kpi':'derived_price_ratio','claim_type':'inference','value':9999}],
                         'fetched_at': '2026-10-26'})
    assert pipeline.input_fingerprint(tmp_path, 'TEST') == before
    assert prepare_packet(tmp_path, 'TEST', '2026-10-26', collect=False)['evidence_hash'] == packet_before['evidence_hash']
    pipeline.write(path, {'points': [{**point,'value':101}]})
    assert pipeline.input_fingerprint(tmp_path, 'TEST') != before
    assert prepare_packet(tmp_path, 'TEST', '2026-10-26', collect=False)['evidence_hash'] != packet_before['evidence_hash']


def test_corrected_processing_code_releases_a_failed_case_without_waiting_until_tomorrow(tmp_path):
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    state = {'TEST': {'retry_after':'2026-10-29', 'input_fingerprint':pipeline.input_fingerprint(tmp_path,'TEST'),
                      'processing_version':pipeline.processing_version(tmp_path)}}
    assert pipeline.build_queue(tmp_path,'2026-10-26',state)['companies'][0]['status'] == 'automatic_retry_pending'
    (tmp_path/'_system/prompts/valuation_underwriting.md').write_text('Corrected processing instructions.',encoding='utf-8')
    assert pipeline.build_queue(tmp_path,'2026-10-26',state)['companies'][0]['status'] == 'needs_underwriting'


def test_instruction_changes_invalidate_model_cache_without_repeating_unchanged_calls(tmp_path):
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    state,calls,payload = {},[],{'packet':packet()}
    execute = mock_stages(contract(),calls)
    first = pipeline.call_stage(tmp_path,tmp_path/'work','TEST','author',payload,state,execute=execute)[1]
    assert pipeline.call_stage(tmp_path,tmp_path/'work','TEST','author',payload,state,execute=execute)[1]['input_hash'] == first['input_hash']
    (tmp_path/'_system/prompts/valuation_underwriting.md').write_text('New complete underwriting instructions.',encoding='utf-8')
    changed = pipeline.call_stage(tmp_path,tmp_path/'work','TEST','author',payload,state,execute=execute)[1]
    assert changed['input_hash'] != first['input_hash']
    assert calls == ['author','author']


def test_reasoning_changes_cannot_reuse_a_different_effort_assumption_call(tmp_path):
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    policy = pipeline.read(tmp_path/pipeline.CALL_POLICY)
    role = policy['model_ladder']['consumers']['valuation_underwriter']
    role.update(model='gpt-6.1-sol',reasoning_effort='high')
    pipeline.write(tmp_path/pipeline.CALL_POLICY,policy)
    calls,state,payload = [],{}, {'packet':packet()}
    first = pipeline.call_stage(tmp_path,tmp_path/'work','TEST','author',payload,state,execute=mock_stages(contract(),calls))[1]
    role['reasoning_effort'] = 'medium'
    pipeline.write(tmp_path/pipeline.CALL_POLICY,policy)
    second = pipeline.call_stage(tmp_path,tmp_path/'work','TEST','author',payload,state,execute=mock_stages(contract(),calls))[1]
    assert first['model'] == second['model'] == 'gpt-6.1-sol'
    assert first['reasoning_effort'] == 'high' and second['reasoning_effort'] == 'medium'
    assert first['input_hash'] != second['input_hash']
    assert calls == ['author','author']


def test_live_underwriting_roles_pin_sol_high_and_auto_without_changing_other_lanes():
    import underwriting_pipeline as pipeline
    root = Path(__file__).resolve().parents[3]
    assert pipeline.stage_model(root,'author') == {'id':'gpt-6.1-sol','reasoning_effort':'high','provider':'codex-local'}
    assert pipeline.stage_model(root,'challenger') == {'id':'gpt-6.1-sol','reasoning_effort':'high','provider':'codex-local'}
    assert pipeline.stage_model(root,'builder') == {'id':'underwriting-compiler/1','reasoning_effort':None,'provider':'deterministic'}
    assert pipeline.read(root/pipeline.CALL_POLICY)['model_ladder']['default_model'] == 'composer-2.5'


def test_local_judgment_handoff_builds_on_another_host_without_repeating_judgment(tmp_path, monkeypatch):
    import refresh_shared_forecasts as refresh
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    monkeypatch.setattr(pipeline,'today',lambda:'2026-10-26')
    monkeypatch.setattr(refresh,'refresh_quote',lambda *a,**kw:None)
    monkeypatch.setattr(refresh,'refresh_missing_model_inputs',lambda *a:None)
    c,calls = contract(),[]
    vault = tmp_path/'vault'
    authored = pipeline.run_batch(tmp_path,launch=True,phase='author',work=tmp_path/'local-work',vault=vault,
                                  prepare=lambda *a:packet(),execute=mock_stages(c,calls))
    assert authored['approved'] == ['TEST'] and authored['completed'] == []
    assert calls == ['author','challenger']
    assert not (tmp_path/'TEST/research/valuation.json').exists()
    built = pipeline.run_batch(tmp_path,launch=True,phase='build',work=tmp_path/'remote-work',vault=vault,
                               prepare=lambda *a:pytest.fail('The builder must use the frozen handoff'),execute=mock_stages(c,calls))
    assert built['completed'] == ['TEST']
    assert calls == ['author','challenger']
    assert pipeline.validate_saved(tmp_path,'TEST',vault)['status'] == 'validated'
    assert not pipeline.run_batch(tmp_path,launch=True,phase='build',work=tmp_path/'third-work',vault=vault,
                                  execute=lambda *a:pytest.fail('An accepted handoff was repeated'))['selected']


def test_changed_handoff_cannot_reach_the_remote_builder(tmp_path, monkeypatch):
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    monkeypatch.setattr(pipeline,'today',lambda:'2026-10-26')
    vault = tmp_path/'vault'
    pipeline.run_batch(tmp_path,launch=True,phase='author',work=tmp_path/'local',vault=vault,
                       prepare=lambda *a:packet(),execute=mock_stages(contract(),[]))
    path = next((vault/'valuation-underwriting/handoffs').glob('*.json'))
    value = pipeline.read(path)
    value['contract']['assumptions'][0]['value'] = .9
    pipeline.write(path,value)
    result = pipeline.run_batch(tmp_path,launch=True,phase='build',work=tmp_path/'remote',vault=vault,
                                 execute=lambda *a:pytest.fail('Tampered assumptions reached a model'))
    assert not result['completed'] and result['blocked']


def test_saved_review_binding_is_required_even_when_the_old_arithmetic_still_works(tmp_path, monkeypatch):
    import refresh_shared_forecasts as refresh
    import underwriting_pipeline as pipeline
    import vault_paths
    company_root(tmp_path)
    vault = tmp_path/'vault'
    monkeypatch.setattr(pipeline, 'today', lambda: '2026-10-26')
    monkeypatch.setattr(refresh, 'refresh_quote', lambda *a, **kw: None)
    monkeypatch.setattr(refresh, 'refresh_missing_model_inputs', lambda *a: None)
    monkeypatch.setattr(vault_paths, 'research_vault_root', lambda: vault)
    result = pipeline.run_batch(tmp_path, launch=True, work=tmp_path/'work', vault=vault,
                                prepare=lambda *a: packet(), execute=mock_stages(contract(), []))
    assert result['completed'] == ['TEST']
    initial = refresh.calculate('TEST', tmp_path, '2026-10-26')
    assert initial['status'] == 'available'
    assert initial['model_basis'] == 'independent_underwriting'
    path = tmp_path/'TEST/research/underwriting_review.json'
    changed = pipeline.read(path)
    changed['contract_hash'] = 'changed'
    pipeline.write(path, changed)
    f = refresh.calculate('TEST', tmp_path, '2026-10-26')
    assert 'underwriting_contract_unverified' in {g['code'] for g in f['gaps']}
    assert f['present_value_today_per_share']['base'] is None


def test_missing_model_price_does_not_erase_a_verified_snapshot_quote():
    from test_shared_valuation_forecast import model
    from valuation_forecast import build_forecast
    v = model()
    v['inputs'] = {}
    f = build_forecast(v)
    assert f['status'] == 'available', f['gaps']
    assert f['quote']['value'] == 100


def test_an_overwritten_model_cannot_bypass_a_failed_underwriting_receipt():
    from test_shared_valuation_forecast import model
    from valuation_forecast import build_forecast
    v = model()
    v['market_snapshot']['underwriting_validation'] = {'status': 'unverified'}
    f = build_forecast(v)
    assert f['status'] != 'available'
    assert 'underwriting_contract_unverified' in {g['code'] for g in f['gaps']}
    assert f['present_value_today_per_share']['base'] is None


def test_routine_legacy_jobs_cannot_rewrite_sealed_company_economics(tmp_path, monkeypatch):
    import automate_valuation_readiness as automation
    import fetch_equity_prices as prices
    import underwriting_pipeline as pipeline
    from marvin_valuation import compute_valuation
    sealed = compile_contract(packet(), contract())
    original = copy.deepcopy(sealed)
    path = tmp_path/'TEST/research/valuation.json'
    pipeline.write(path, sealed)
    saved = path.read_bytes()
    monkeypatch.setattr(automation, 'ROOT', tmp_path)
    monkeypatch.setattr(prices, 'ROOT', tmp_path)
    monkeypatch.setattr(prices, 'fetch_price', lambda *a: pytest.fail('Legacy price injection must not run'))
    assert prices.merge_ticker('TEST', force=True)
    assert path.read_bytes() == saved
    assert automation.compile_valuation('TEST', '2026-10-27', {}, {}) == original
    assert automation.merge_compiled_model(original, {'as_of': '2026-10-27', 'inputs': {'price': 999}}) == original
    assert compute_valuation(sealed) == original
    assert sealed == original


def test_paid_budget_is_enforced_before_a_provider_can_be_called(tmp_path):
    import underwriting_pipeline as pipeline
    from llm_call_gate import append_ledger
    company_root(tmp_path)
    settings = pipeline.read(tmp_path/pipeline.POLICY)
    settings['maximum_model_calls_per_day'] = 1
    pipeline.write(tmp_path/pipeline.POLICY, settings)
    work = tmp_path/'work'
    append_ledger(work/'ledger.jsonl', {'consumer': 'valuation_underwriter', 'subject': 'OTHER',
                   'status': 'reserved', 'timestamp': pipeline.now(), 'evidence_hash': 'already-paid', 'run_id': 'prior'})
    with pytest.raises(pipeline.StageBlocked, match='total_daily_model_call_budget'):
        pipeline.call_stage(tmp_path, work, 'TEST', 'author', {'packet': packet()}, {},
                            execute=lambda *a: pytest.fail('A call escaped the daily budget'))


def test_publisher_builds_a_data_only_commit_and_explicitly_starts_head_checks(tmp_path, monkeypatch):
    import subprocess

    import publish_underwriting as publisher
    import refresh_shared_forecasts as refresh
    import underwriting_pipeline as pipeline
    root, remote, vault = tmp_path/'repo', tmp_path/'remote.git', tmp_path/'vault'
    root.mkdir()
    company_root(root)
    archive = root/'archive/already-published-primary.txt'
    archive.parent.mkdir()
    archive.write_text('The remote already owns this unchanged primary archive object.')
    def git(*args, cwd=root):
        return subprocess.check_output(['git', *args], cwd=cwd, stderr=subprocess.DEVNULL, text=True).strip()
    git('init', '-q', '-b', 'main')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.test')
    git('add', '.')
    git('commit', '-q', '-m', 'Baseline')
    git('init', '-q', '--bare', str(remote))
    git('remote', 'add', 'origin', str(remote))
    git('push', '-q', 'origin', 'main')
    # Model the sparse producer: the server has an unchanged archive object
    # that the local job must not need to hydrate to publish selected data.
    blob = git('rev-parse', 'main:archive/already-published-primary.txt')
    local_object = root/'.git/objects'/blob[:2]/blob[2:]
    assert local_object.resolve().is_relative_to(root.resolve())
    local_object.chmod(0o600)
    local_object.unlink()
    monkeypatch.setattr(pipeline, 'today', lambda: '2026-10-26')
    monkeypatch.setattr(refresh, 'refresh_quote', lambda *a, **kw: None)
    monkeypatch.setattr(refresh, 'refresh_missing_model_inputs', lambda *a: None)
    monkeypatch.setattr(publisher, 'research_vault_root', lambda: vault)
    monkeypatch.setenv('GITHUB_REPOSITORY', 'example/test')
    monkeypatch.setenv('GITHUB_RUN_ID', 'underwriting-fixture')
    result = pipeline.run_batch(root, launch=True, work=root/'.underwriting-work', vault=vault,
                                prepare=lambda *a: packet(), execute=mock_stages(contract(), []))
    assert result['completed'] == ['TEST']
    (root/'unexpected-code.py').write_text('raise RuntimeError("must never be published")')
    events = []
    def api(repo, path, payload=None):
        if path == 'pulls':
            return {'number': 123, 'html_url': 'https://example.test/pull/123'}
        events.append(payload['event_type'])
    monkeypatch.setattr(publisher, 'github', api)
    published = publisher.publish(root)
    assert published['status'] == 'checks_requested'
    assert events == ['research-quality-pr', 'underwriting-validate-pr']
    commit = git('rev-parse', 'refs/remotes/origin/codex/underwriting-underwriting-fixture')
    changed = git('diff', '--name-only', 'main', commit).splitlines()
    assert 'TEST/research/valuation.json' in changed
    assert 'TEST/research/underwriting_receipt.json' in changed
    assert 'unexpected-code.py' not in changed
    assert all(p in publisher.approved_paths(['TEST']) for p in changed)
