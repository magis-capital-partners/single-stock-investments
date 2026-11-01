"""Cost savings preserve evidence, independent judgments and publication gates."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_underwriting_pipeline import contract, packet, review
from underwriting_contract import ContractError, digest
from underwriting_pipeline import (
    compiled_build,
    usage_summary,
    validate_stage_receipts,
    write,
)
from underwriting_transport import pack, render, unpack


@pytest.mark.parametrize('extra', [None, {}, {'zero': 0, 'negative': -3, 'text': '日本語 € \"quotes\"', 'list': [None, False]}])
def test_transport_is_lossless_even_with_missing_fields_and_unicode(extra):
    p = packet()
    p['observations'].extend([{'id': 'sparse', 'value': extra}, copy.deepcopy(p['observations'][0])])
    value = {'packet': p, 'revision_feedback': extra}
    envelope = pack(value)
    assert unpack(envelope) == value
    envelope['payload_hash'] = 'f'*64
    with pytest.raises(ContractError, match='changed'):
        unpack(envelope)


def test_transport_reduces_repeated_source_metadata_without_replacing_facts():
    observations = [{'id': 'obs_'+str(i), 'field': 'OperatingCashFlow', 'value': i, 'unit': 'USD',
                     'source_url': 'https://primary.issuer.test/annual-report-financial-tables',
                     'locator': 'Consolidated statement of cash flows, amounts in whole dollars',
                     'period': '2025-12-31', 'source_kind': 'primary'} for i in range(100)]
    payload = {'packet': {'observations': observations}}
    assert len(render(payload)) < .7*len(json.dumps(payload))
    assert unpack(pack(payload))['packet']['observations'] == observations


def test_deterministic_assembly_needs_no_provider_and_rejects_a_forged_receipt():
    p, c = packet(), contract()
    model, compiler = compiled_build(p, c, review(c))
    receipts = {'author': {'agent_id': 'author-session'}, 'challenger': {'agent_id': 'independent-session'}, 'builder': compiler}
    validate_stage_receipts(receipts, model)
    assert compiler['model_calls'] == 0 and compiler['model_hash'] == digest(model)
    changed = copy.deepcopy(model)
    changed['inputs']['price'] = 99
    with pytest.raises(ContractError, match='compiler receipt'):
        validate_stage_receipts(receipts, changed)
    receipts['challenger']['agent_id'] = 'author-session'
    with pytest.raises(ContractError, match='independent'):
        validate_stage_receipts(receipts, model)


def test_usage_never_treats_unreported_tokens_as_zero_cost(tmp_path, monkeypatch):
    write(tmp_path/'cache/T/a/receipt.json', {'agent_id': 'one', 'stage': 'author',
          'usage': {'input_tokens': 100, 'cached_input_tokens': 80, 'output_tokens': 20}})
    write(tmp_path/'cache/T/b/receipt.json', {'agent_id': 'one', 'stage': 'author', 'usage': {'input_tokens': 999}})
    write(tmp_path/'cache/T/c/receipt.json', {'agent_id': 'two', 'stage': 'challenger'})
    write(tmp_path/'progress/T.json', {'approved': {'contract': 'frozen'}})
    original_glob = Path.glob
    def reverse_discovery(path, pattern):
        return iter(sorted(original_glob(path, pattern), reverse=True))
    monkeypatch.setattr(Path, 'glob', reverse_discovery)
    result = usage_summary(tmp_path)
    assert result['sessions'] == 2 and result['sessions_without_usage'] == 1
    assert result['input_tokens'] == 100 and result['output_tokens'] == 20
    assert result['tokens_per_approved_company'] is None


def test_readiness_withholds_calls_until_the_latest_primary_report_is_available():
    from underwriting_evidence import evidence_readiness
    p = packet()
    p['latest_report'] = {'period': '2026-06-30', 'filed': '2026-08-01'}
    assert evidence_readiness(p, require_documents=True)['status'] == 'evidence_gap'
    p['documents'] = [{'form': '10-K', 'period': '2025-12-31'}, {'form': '10-Q', 'period': '2026-06-30'}]
    assert evidence_readiness(p, require_documents=True)['status'] == 'ready'
    p['source_discovery'] = {'status': 'failed'}
    assert 'report_discovery_failed' in {g['code'] for g in evidence_readiness(p, require_documents=True)['gaps']}


def test_source_checkout_cannot_replace_fresher_local_evidence():
    from underwriting_local import prefer_local_facts
    old = {'collected_at': '2026-10-28T10:00:00Z', 'latest_report': {'period': '2026-03-31', 'filed': '2026-05-01'}}
    new = {'collected_at': '2026-10-29T10:00:00Z', 'latest_report': {'period': '2026-06-30', 'filed': '2026-08-01'}}
    assert prefer_local_facts(new, old)
    assert not prefer_local_facts(old, new)
    assert not prefer_local_facts({**old, 'collected_at': '2026-10-30T10:00:00Z'}, new)


def test_missing_primary_evidence_spends_no_judgment_calls(tmp_path):
    import underwriting_pipeline as pipeline
    from test_underwriting_pipeline import company_root
    company_root(tmp_path)
    p = packet()
    p['readiness'] = {'status': 'evidence_gap', 'gaps': [{'code': 'latest_primary_document_missing'}]}
    result = pipeline.run_batch(tmp_path, launch=True, phase='author', work=tmp_path/'work', vault=tmp_path/'vault',
                                prepare=lambda *args: p, execute=lambda *args: pytest.fail('Evidence gap spent a model call'))
    assert not result['approved'] and 'evidence_not_ready' in result['blocked'][0]['gaps'][0]['detail']


def test_focused_retrieval_reads_the_requested_claim_and_changes_the_bound_evidence():
    from underwriting_evidence import document_record
    raw = ('<html><table>Consolidated debt and assets cash capital 100</table>'
           + 'Business overview. '*300 + 'Warrant holders have a separate claim on proceeds.' + '</html>').encode()
    base = document_record('https://issuer.test/annual', raw)
    focused = document_record('https://issuer.test/annual', raw, ['warrant'])
    assert base['content_hash'] == focused['content_hash']
    assert any('Warrant holders' in c for c in focused['contexts'])


def test_new_report_reconsiders_every_assumption_but_price_clocks_do_not():
    from underwriting_updates import change_context
    p, c = packet(), contract()
    unchanged = change_context(p, c, copy.deepcopy(p))
    assert unchanged['assumptions_requiring_reconsideration'] == []
    updated = copy.deepcopy(p)
    updated['latest_report'] = {'period': '2026-06-30', 'filed': '2026-08-01'}
    changed = change_context(p, c, updated)
    assert changed['mode'] == 'reconsider_framework_and_all_assumptions'
    assert set(changed['assumptions_requiring_reconsideration']) == {a['id'] for a in c['assumptions']}


def test_collection_audit_does_not_equate_a_successful_request_with_primary_coverage(tmp_path):
    from refresh_shared_forecasts import FUNDAMENTALS, collection_summary
    write(tmp_path/FUNDAMENTALS/'PRIMARY.json', {'facts': [{'source_kind': 'primary'}], 'report_discovery': {'status': 'verified'}})
    write(tmp_path/FUNDAMENTALS/'PROVIDER.json', {'facts': [{'source_kind': 'provider_reported'}]})
    write(tmp_path/FUNDAMENTALS/'EMPTY.json', {'errors': [{'error': 'missing disclosure'}]})
    result = collection_summary(tmp_path, ['PRIMARY', 'PROVIDER', 'EMPTY'])
    assert result['with_financial_observations'] == 2
    assert result['with_primary_observations'] == 1
    assert result['without_financial_observations'] == 1 and result['with_collector_errors'] == 1


def test_expired_review_cannot_reuse_an_old_approved_packet(tmp_path, monkeypatch):
    import underwriting_pipeline as pipeline
    from test_underwriting_pipeline import company_root
    company_root(tmp_path)
    monkeypatch.setattr(pipeline, 'evaluate', lambda **kwargs: {'approved': True})
    work, vault, state, calls, current = tmp_path/'work', tmp_path/'vault', {}, [], packet()
    chosen = {}
    def execute(stage, payload, output, receipt):
        calls.append(stage)
        if stage == 'author':
            chosen['contract'] = contract(payload['packet'])
            chosen['contract']['review_due'] = '2026-10-27' if len(calls) == 1 else '2027-01-24'
            answer = chosen['contract']
        else:
            answer = review(chosen['contract'])
        write(output, answer)
        write(receipt, {'agent_id': stage+str(len(calls)), 'status': 'finished'})
    result = pipeline.run_company(tmp_path, work, 'TEST', current['as_of'], state, vault,
                                  prepare=lambda *args: current, execute=execute, phase='author')
    state['review_due'] = result['review_due']
    current = copy.deepcopy(current)
    current['as_of'] = '2026-10-28'
    current['packet_hash'] = digest({k: v for k, v in current.items() if k != 'packet_hash'})
    result = pipeline.run_company(tmp_path, work, 'TEST', current['as_of'], state, vault,
                                  prepare=lambda *args: current, execute=execute, phase='author')
    assert calls == ['author', 'challenger', 'author', 'challenger']
    assert result['review_due'] == '2027-01-24'


def test_hosted_compilation_does_not_require_any_model_api_key():
    import yaml
    root = Path(__file__).resolve().parents[3]
    workflow = (root/'.github/workflows/valuation-underwriting.yml').read_text(encoding='utf-8')
    assert 'CURSOR_API_KEY' not in workflow and 'OPENAI_API_KEY' not in workflow
    assert '--phase build --launch' in workflow
    assert yaml.safe_load(workflow)['jobs']['underwrite']['steps']


def test_equal_quarter_and_ytd_values_keep_distinct_observation_identities():
    from underwriting_evidence import _observation
    point = {'field': 'NetIncomeLoss', 'value': 0, 'currency': 'USD', 'period': '2026-06-30',
             'source_url': 'https://issuer.test/filing', 'locator': 'Income statement', 'start': '2026-01-01'}
    assert _observation(point)['id'] != _observation({**point, 'start': '2026-04-01'})['id']


def test_sol_pilot_measurements_remain_separate_from_unknown_legacy_usage(tmp_path):
    write(tmp_path/'cache/OLD/a/receipt.json', {'agent_id': 'legacy', 'stage': 'author', 'model': 'old-model'})
    for role in ('author', 'challenger'):
        write(tmp_path/f'cache/T/{role}/receipt.json', {'agent_id': role, 'stage': role, 'model': 'gpt-6.1-sol',
              'usage': {'input_tokens': 100, 'output_tokens': 20}})
    write(tmp_path/'progress/T.json', {'approved': {'receipts': {role: {'model': 'gpt-6.1-sol'} for role in ('author', 'challenger')}}})
    result = usage_summary(tmp_path)
    assert result['tokens_per_approved_company'] is None
    assert result['by_model']['gpt-6.1-sol']['tokens_per_approved_company'] == 240
    assert result['by_model']['old-model']['sessions_without_usage'] == 1
