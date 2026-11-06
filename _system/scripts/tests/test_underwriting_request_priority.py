"""Current primary queries survive bounded retries without losing criticism."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from underwriting_evidence import requested_keywords


def older_requests():
    return [{'code': f'prior_{i}', 'detail':
             f"Retrieve Note {i+1}. Search terms: 'covenant {i}', 'funding clause {i}', 'credit condition {i}'."}
            for i in range(8)]


CURRENT = {'code': 'near_term_note_terms', 'detail':
           "Note 13 lacks current payment terms. Search terms: '2015 Senior Notes', "
           "'2017 Senior Notes', 'maturity date', 'principal', 'redemption', "
           "'business day', 'Nineteenth Supplemental Indenture'."}
REQUIRED = {'2015 senior notes', '2017 senior notes', 'business day',
            'nineteenth supplemental indenture'}


@pytest.mark.parametrize('instrument', ['2015 Senior Notes', '2017 Senior Notes'])
def test_digit_leading_primary_instrument_labels_remain_literal_queries(instrument):
    assert instrument.lower() in requested_keywords([
        {'code': 'payment_terms', 'detail': f"Search terms: '{instrument}', 'maturity date'."}])


@pytest.mark.parametrize('resume', [True, False])
def test_current_primary_queries_reach_collection_with_full_history(tmp_path, monkeypatch, resume):
    import underwriting_pipeline as pipeline
    import underwriting_related_evidence as related
    from test_underwriting_pipeline import company_root, packet

    company_root(tmp_path)
    history = older_requests()
    state = {'evidence_request_history': copy.deepcopy(history)}
    if resume:
        state['evidence_requests'] = [copy.deepcopy(CURRENT)]
    collected = []
    provider_calls = []
    frozen = packet()

    def prepare(*args, focus_keywords=()):
        collected.append(list(focus_keywords))
        if resume:
            return {'readiness': {'status': 'evidence_gap',
                    'gaps': [{'code': 'test_collection_stop', 'detail': 'No provider needed.'}]}}
        return copy.deepcopy(frozen)

    def author(*args, **kwargs):
        provider_calls.append(True)
        return {'status': 'evidence_gap', 'gaps': [copy.deepcopy(CURRENT)]}, {}

    monkeypatch.setattr(pipeline, 'prepare_packet', prepare)
    monkeypatch.setattr(pipeline, 'call_stage', author)
    monkeypatch.setattr(related, 'augment_requested_targets', lambda root, p, gaps, as_of: p)
    with pytest.raises(pipeline.StageBlocked):
        pipeline.run_company(tmp_path, tmp_path/'work', 'TEST', '2026-10-26',
                             state, tmp_path/'vault', prepare=prepare)

    keywords = collected[0 if resume else 1]
    assert REQUIRED <= set(keywords)
    assert len(keywords) <= 18
    assert len(keywords) == len(set(keywords))
    assert 'covenant 0' in keywords  # Historical queries fill the remaining budget.
    assert state['evidence_request_history'] == history + [CURRENT]
    assert provider_calls == ([] if resume else [True])
