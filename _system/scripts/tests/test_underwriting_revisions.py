"""Edits preserve the actual authored draft and still require full cold review."""
import copy

import pytest

from test_underwriting_economics import economic_contract, economic_review
from test_underwriting_pipeline import packet, company_root
from underwriting_contract import ContractError, compile_contract, digest
from underwriting_revisions import materialize, validate_derivation


def proposal(base, edits):
    return {'schema_version':'underwriting-contract-revision/1',
            'base_contract_hash':digest(base),'edits':edits}


def test_exact_edits_keep_every_untouched_financial_claim_and_order():
    base = economic_contract()
    original = copy.deepcopy(base)
    edits = [{'path':['holding_horizon_years'],'value':1},
             {'path':['holding_horizon_rationale'],'value':'Explicit owner period independent of later contractual funding.'},
             {'path':['components','business','drivers','copy_cash'],
              'value':{'id':'copy_cash','op':'multiply','args':['normalized_cash',1],'unit':'USD'},
              'before':'cash_ps'},
             {'path':['components','business','drivers','cash_ps','args'],'value':['copy_cash','shares']},
             {'path':['economic_analysis','bridges',{'component_id':'business','year':2},'cash_generation_ref'],
              'value':'copy_cash'}]
    revised = materialize(base,proposal(base,edits))
    assert base == original
    assert revised['facts'] == base['facts']
    assert revised['assumptions'] == base['assumptions']
    assert revised['economic_analysis']['bridges'][0] == base['economic_analysis']['bridges'][0]
    assert compile_contract(packet(),revised)['valuation_methodology']['horizon_years'] == 1


@pytest.mark.parametrize('edit', [
    'not-an-edit-object',
    {'path':['components','missing','terminal'],'value':{}},
    {'path':['components','business','drivers','cash_ps'],'value':{'id':'changed_identity'}},
    {'path':['components','business','drivers','new'],'value':{'id':'new'},'before':'missing'},
    {'path':['economic_analysis','bridges',{'component_id':'business'}],'op':'remove'},
    {'path':['missing'],'op':'remove'},
    {'path':[],'value':{}},
])
def test_ambiguous_missing_or_identity_changing_edits_are_rejected(edit):
    base = economic_contract()
    with pytest.raises(ContractError):
        materialize(base,proposal(base,[edit]))


def test_revision_hash_and_full_economic_validation_cannot_be_bypassed():
    base = economic_contract()
    p = proposal(base,[{'path':['assumptions','normalization','value'],'value':3}])
    revised = materialize(base,p)
    with pytest.raises(ContractError,match='outside declared bounds'):
        compile_contract(packet(),revised)
    p['base_contract_hash'] = '0'*64
    with pytest.raises(ContractError,match='base contract hash'):
        materialize(base,p)


def test_real_pipeline_reviews_the_expanded_contract_and_cold_replays_derivation(tmp_path,monkeypatch):
    import underwriting_pipeline as pipeline
    import refresh_shared_forecasts as refresh
    import vault_paths
    company_root(tmp_path)
    policy = pipeline.read(tmp_path/pipeline.POLICY)
    pipeline.write(tmp_path/pipeline.POLICY,{**policy,'required_contract_schema':'underwriting-contract/2'})
    monkeypatch.setattr(pipeline,'today',lambda:'2026-10-26')
    monkeypatch.setattr(refresh,'refresh_quote',lambda *a,**kw:None)
    monkeypatch.setattr(refresh,'refresh_missing_model_inputs',lambda *a,**kw:None)
    monkeypatch.setattr(vault_paths,'research_vault_root',lambda:tmp_path/'vault')
    base = economic_contract()
    patch = proposal(base,[{'path':['assumptions','normalization','value'],'value':.9}])
    revised = materialize(base,patch)
    work = tmp_path/'work'
    progress = pipeline.load_progress(tmp_path,work,'TEST',packet())
    progress['feedback'] = {'previous_contract':base,'required_correction':'Reassess cash generation against the primary filing.'}
    pipeline.write(work/'progress/TEST.json',progress)
    def execute(stage,payload,output,receipt):
        if stage == 'author':
            assert payload['revision_base_hash'] == digest(base)
            answer = patch
        else:
            assert payload['contract'] == revised
            answer = economic_review(revised,compile_contract(packet(),revised))
        pipeline.write(output,answer)
        pipeline.write(receipt,{'agent_id':stage+'-revision','status':'finished','run_id':stage+'-revision'})
    result = pipeline.run_batch(tmp_path,launch=True,work=work,vault=tmp_path/'vault',
                                prepare=lambda *a:packet(),execute=execute)
    assert result['completed'] == ['TEST'],result
    saved = pipeline.validate_saved(tmp_path,'TEST',tmp_path/'vault')
    receipt = saved['stages']['author']
    assert receipt['contract_revision']['proposal'] == patch
    assert list((work/'cache/TEST').glob('*/author_revision.json'))
    tampered = copy.deepcopy(receipt)
    tampered['contract_revision']['proposal']['edits'][0]['value'] = .8
    with pytest.raises(ContractError,match='output changed'):
        validate_derivation(tampered,digest(revised))
    tampered['contract_revision']['provider_output_hash'] = digest(tampered['contract_revision']['proposal'])
    with pytest.raises(ContractError,match='reviewed contract'):
        validate_derivation(tampered,digest(revised))


def test_an_invalid_old_cache_cannot_erase_new_operator_corrections(tmp_path):
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    work = tmp_path/'work'
    progress = pipeline.load_progress(tmp_path,work,'TEST',packet())
    progress['feedback'] = {'required_correction':'Resolve the new capital attribution finding.',
                            'previous_contract':economic_contract(),
                            'operator_review':{'detail':'The new finding must survive an old compiler failure.'}}
    pipeline.write(work/'progress/TEST.json',progress)
    base = economic_contract()
    invalid = copy.deepcopy(base)
    invalid['assumptions'][0]['value'] = 3
    review = economic_review(base,compile_contract(packet(),base))
    review['contract_hash'] = digest(invalid)
    for role,answer in (('author',invalid),('challenger',review)):
        path = work/'cache/TEST'/role
        pipeline.write(path/'output.json',answer)
        pipeline.write(path/'receipt.json',{'status':'finished','agent_id':role,'stage':role,'input_hash':role})
    (tmp_path/'_system/prompts/valuation_underwriting.md').write_text('Changed instructions preserve the latest corrections.')
    loaded = pipeline.load_progress(tmp_path,work,'TEST',packet())
    assert loaded['feedback']['operator_review'] == progress['feedback']['operator_review']
    assert loaded['feedback']['previous_contract'] == base
