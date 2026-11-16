"""A paid, valid author can reach review without another author or unbounded RAM."""
from collections import Counter
from pathlib import Path
import sys
import tracemalloc
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import underwriting_token_transport as token
import pytest
from test_underwriting_economics import economic_contract, economic_review
from test_underwriting_pipeline import company_root, packet
from underwriting_contract import compile_contract, digest


def paid_valid_author(root, monkeypatch):
    import underwriting_pipeline as pipeline
    company_root(root)
    pipeline.write(root/pipeline.POLICY,{**pipeline.read(root/pipeline.POLICY),
                                      'required_contract_schema':'underwriting-contract/2'})
    monkeypatch.setattr(pipeline,'evaluate',lambda **kw:{'approved':True})
    c=economic_contract();state={};work=root/'work'
    def execute(stage,payload,output,receipt):
        pipeline.write(output,c)
        pipeline.write(receipt,{'agent_id':'already-paid-author','status':'finished',
            'finished_at':'2026-10-26T01:00:00+00:00','output_import':{'output_hash':digest(c)}})
    pipeline.call_stage(root,work,'TEST','author',{'packet':packet()},state,execute=execute)
    return pipeline,work,state,c


def test_paid_compiled_author_resumes_directly_at_independent_review(tmp_path,monkeypatch):
    pipeline,work,state,c=paid_valid_author(tmp_path,monkeypatch)
    progress=pipeline.load_progress(tmp_path,work,'TEST',packet())
    assert progress['pending_review']['author']==c
    calls=[]
    def execute(stage,payload,output,receipt):
        calls.append(stage)
        assert stage=='challenger','A valid paid contract must not be authored again'
        pipeline.write(output,economic_review(c,compile_contract(packet(),c)))
        pipeline.write(receipt,{'agent_id':'independent-reviewer','status':'finished',
                               'finished_at':'2026-10-26T02:00:00+00:00'})
    result=pipeline.run_company(tmp_path,work,'TEST','2026-10-26',state,tmp_path/'vault',
                                prepare=lambda *args:packet(),execute=execute,phase='author')
    assert result['status']=='approved_for_build' and calls==['challenger']
    assert state['stage_attempts']=={'author':1,'challenger':1}


def test_pending_review_survives_unpaid_preparation_failure(tmp_path,monkeypatch):
    pipeline,work,state,c=paid_valid_author(tmp_path,monkeypatch)
    real_call=pipeline.call_stage
    def stop_before_review(root,work,ticker,stage,*args,**kwargs):
        assert stage=='challenger'
        raise MemoryError('review preparation before admission')
    monkeypatch.setattr(pipeline,'call_stage',stop_before_review)
    with pytest.raises(MemoryError):
        pipeline.run_company(tmp_path,work,'TEST','2026-10-26',state,tmp_path/'vault',
                             prepare=lambda *args:packet(),phase='author')
    saved=pipeline.read(work/'progress/TEST.json')
    assert saved['pending_review']['author']==c
    assert not saved.get('approved') and state['stage_attempts']=={'author':1}


def test_tampered_paid_author_cannot_be_recovered_for_review(tmp_path,monkeypatch):
    pipeline,work,state,c=paid_valid_author(tmp_path,monkeypatch)
    output=next((work/'cache/TEST').glob('*/output.json'))
    changed=pipeline.read(output);changed['assumptions'][0]['value']-=.01;pipeline.write(output,changed)
    with pytest.raises(pipeline.ContractError,match='Paid author output identity changed'):
        pipeline.load_progress(tmp_path,work,'TEST',packet())


def test_paid_rejected_author_is_not_sent_for_another_unchanged_review(tmp_path,monkeypatch):
    pipeline,work,state,c=paid_valid_author(tmp_path,monkeypatch)
    rejected=economic_review(c,compile_contract(packet(),c))
    rejected.update(verdict='revise',findings=[{'severity':'major','detail':'Preserve actual funding criticism.'}])
    def execute(stage,payload,output,receipt):
        pipeline.write(output,rejected)
        pipeline.write(receipt,{'agent_id':'prior-independent-review','status':'finished',
                               'finished_at':'2026-10-26T02:00:00+00:00'})
    pipeline.call_stage(tmp_path,work,'TEST','challenger',
        pipeline.challenge_payload(packet(),c,compile_contract(packet(),c)),state,execute=execute)
    progress=pipeline.load_progress(tmp_path,work,'TEST',packet())
    assert not progress.get('pending_review')
    assert progress['feedback']['independent_challenge']==rejected


def old_rank(streams, depth, limit):
    runs=Counter()
    for stream in streams.values():
        for width in (8,16,32,64):
            runs.update(tuple(stream[i:i+width]) for i in range(len(stream)-width+1)
                if max((depth[x] for x in stream[i:i+width] if type(x) is int),default=0)<token.MAX_DEPTH)
    ranked=[]
    for run,n in runs.items():
        if n<2:continue
        length=sum(3 if type(x) is int else len(x) for x in run)
        gain=n*(length-3)-(length+12)
        if gain>16:ranked.append((gain,repr(run),run))
    return sorted(ranked,reverse=True)[:limit]


def test_exact_run_ranking_keeps_counts_types_depth_and_ties():
    streams={'first':([0,1,'literal Ω',2,3,'0','~']*30),
             'second':([3,'other',2,1,0,'True']*25), 'too_deep':[4]*40}
    depth=[0,1,1,2,12]
    for limit in (0,1,3,2048):
        assert token._rank_run_candidates(streams,depth,limit)==old_rank(streams,depth,limit)


def test_unique_full_runs_do_not_remain_in_one_unbounded_counter():
    streams={'source':['word-'+str(i) for i in range(12000)]}
    tracemalloc.start()
    try:
        result=token._rank_run_candidates(streams,[],2048)
        peak=tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert result==[]
    assert peak<10_000_000


def test_spilled_repeated_runs_keep_exact_ranking_across_chunks():
    words=['source-'+str(i) for i in range(1400)]
    streams={'one':words,'two':words[:],'mixed':([0,'0',1,'Ω']*1200)}
    assert token._rank_run_candidates(streams,[0,1],2048)==old_rank(streams,[0,1],2048)


def test_complete_token_envelope_is_identical_to_original_run_ranking(monkeypatch):
    from underwriting_transport import encoded
    payload={'packet':{'ticker':'CPRT'},'types':[1,1.0,None,False],
             'full_text':''.join('Exact operating and restricted finance source Ω '+str(i%19)+'; '
                                 for i in range(600))}
    current=token.pack(payload)
    monkeypatch.setattr(token,'_rank_run_candidates',old_rank)
    assert encoded(token.pack(payload))==encoded(current)


@pytest.mark.parametrize('bad',[True,False,1.5,None])
def test_binary_scratch_rejects_invalid_internal_atom_types(bad):
    with pytest.raises(ValueError,match='Invalid internal token atom'):
        token._rank_run_candidates({'bad':[bad]*20},[0],2048)
