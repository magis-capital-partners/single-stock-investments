"""Lossless token-string containers and bounded complete-request fast path."""
import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_transport as t
import underwriting_token_transport as u
import underwriting_compact_transport as six
import underwriting_marker_transport as m
from underwriting_contract import digest
from test_underwriting_token_transport import example


def fixture():
    original,e=example()
    original['literal']=['^','~','^source','~T','~~','',None,False,1.0,{'^':'literal','~':'value'}]
    e['payload']['literal']=copy.deepcopy(original['literal']);e['payload_hash']=digest(original)
    return original,m.compact(six.compact(e))


def test_string_containers_shrink_without_changing_any_original_value():
    original,seven=fixture();before=copy.deepcopy(seven);eight=m.compact_strings(seven)
    assert t.encoded(t.unpack(eight))==t.encoded(original)
    assert seven==before
    assert eight['literal_dictionary']==seven['literal_dictionary']
    assert eight['derived_dictionary']==seven['derived_dictionary']
    assert eight['payload']['text'].startswith('^')
    assert len(t.encoded(seven['payload']['text']))-len(t.encoded(eight['payload']['text']))==5


@pytest.mark.parametrize('literal',['^','~','^^','~~','~^','^~','~ordinary','^ordinary',
    {'^':'source'}, {'$literal_v7':[['^','~']]}, {'nested':[{'!':'^'},'~']}])
def test_literal_prefixes_keys_and_nested_types_preserve_exact_original(literal):
    original,e=example();original['literal']=literal;e['payload']['literal']=copy.deepcopy(literal);e['payload_hash']=digest(original)
    eight=m.compact_strings(m.compact(six.compact(e)))
    assert t.encoded(t.unpack(eight))==t.encoded(original)


@pytest.mark.parametrize('mutate',[
    lambda e:e.update(extra='field'),lambda e:e.update(maximum_dag_depth=13),
    lambda e:e['payload'].update(bad='~unescaped'),lambda e:e['payload'].update(bad='~'),
    lambda e:e['payload'].update(text='^~'),lambda e:e['payload'].update(text='^~?'),
    lambda e:e.update(payload_hash='0'*64),lambda e:e['payload'].update(bad={'^':'unconverted'}),
    lambda e:e['payload'].update(bad={'$t':'unconverted'}),
    lambda e:e['literal_dictionary'].update({u.KEYS[0]:False}),
    lambda e:e['derived_dictionary'].update({u.KEYS[2]:u.KEYS[2]})])
def test_corrupt_or_ambiguous_string_encoding_keeps_existing_fail_closed_guards(mutate):
    _,seven=fixture();eight=m.compact_strings(seven);mutate(eight)
    with pytest.raises(ValueError):t.unpack(eight)


def test_expansion_and_depth_bounds_still_apply(monkeypatch):
    _,seven=fixture();eight=m.compact_strings(seven);monkeypatch.setattr(u,'MAX_RESTORED',5)
    with pytest.raises(ValueError,match='bound'):t.unpack(eight)


def test_fast_path_uses_a_verified_complete_encoding_and_skips_unused_search(monkeypatch):
    original,e=example();original['packet']={'ticker':'CPRT'};e['payload']['packet']=original['packet'];e['payload_hash']=digest(original)
    monkeypatch.setattr(u,'eligible',lambda p:True);monkeypatch.setattr(u,'pack',lambda p:copy.deepcopy(e))
    monkeypatch.setattr(t,'render',lambda p:(_ for _ in ()).throw(AssertionError('unnecessary full search')))
    text=t.render_for_budget(original,1_000_000);pos=text.index('{"schema_version":')
    import json
    assert t.encoded(t.unpack(json.loads(text[pos:])))==t.encoded(original)


def test_fast_path_keeps_normal_fallback_when_complete_candidate_does_not_fit(monkeypatch):
    original,e=example();monkeypatch.setattr(u,'eligible',lambda p:True);monkeypatch.setattr(u,'pack',lambda p:copy.deepcopy(e))
    calls=[];monkeypatch.setattr(t,'render',lambda p:calls.append(p) or 'unchanged complete fallback')
    assert t.render_for_budget(original,1)=='unchanged complete fallback' and calls==[original]


def test_other_company_scope_cannot_use_fast_path(monkeypatch):
    original={'packet':{'ticker':'V'}};monkeypatch.setattr(u,'pack',lambda p:(_ for _ in ()).throw(AssertionError('outside CPRT')))
    monkeypatch.setattr(t,'render',lambda p:'existing layout')
    assert t.render_for_budget(original,1_000_000)=='existing layout'


@pytest.mark.parametrize('budget',[None,True,0,-1,1.0,'1048576'])
def test_fast_path_rejects_invalid_budgets(budget):
    with pytest.raises(ValueError):t.render_for_budget({},budget)
