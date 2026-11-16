"""Short marker keys preserve full source data and every underlying guard."""
import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_transport as t
import underwriting_token_transport as u
import underwriting_compact_transport as old
import underwriting_marker_transport as new
from underwriting_contract import digest
from test_underwriting_token_transport import example


def test_roundtrip_preserves_types_order_hashes_and_dictionary_bytes():
    original,e=example();six=old.compact(e);before=copy.deepcopy(six);seven=new.compact(six)
    assert t.encoded(t.unpack(seven))==t.encoded(original)
    assert six==before and seven['payload_hash']==six['payload_hash']
    assert seven['literal_dictionary']==six['literal_dictionary']
    assert seven['derived_dictionary']==six['derived_dictionary']


def test_schema_and_token_containers_both_shrink():
    original,e=example();original={'amount':1.0,'text':original['text']}
    e.update(payload={'$o':[0,[1.0,{'$tokens':u.KEYS[2]}]]},object_schemas=[['amount','text']],payload_hash=digest(original))
    six=old.compact(e);seven=new.compact(six)
    assert len(t.encoded(six))-len(t.encoded(seven))==2
    assert t.encoded(t.unpack(seven))==t.encoded(original)


@pytest.mark.parametrize('literal',[{'!':[False,None]},{'^':'literal'}, {'$literal_v7':[]},
    {'!':{'^':'literal'},'^':None},{'$t':'old literal','$literal_v6':[]},
    {'nested':[{'!':1.0},{'^':False}]}])
def test_original_reserved_keys_remain_literal(literal):
    original,e=example();original['literal']=literal;e['payload']['literal']=copy.deepcopy(literal);e['payload_hash']=digest(original)
    assert t.encoded(t.unpack(new.compact(old.compact(e))))==t.encoded(original)


@pytest.mark.parametrize('mutate',[
    lambda e:e.update(extra='field'),lambda e:e.update(maximum_dag_depth=13),
    lambda e:e['payload']['text'].update(extra='ambiguous'),lambda e:e['payload']['text'].update({'^':False}),
    lambda e:e['payload']['text'].update({'^':'~'}),lambda e:e['payload']['text'].update({'^':'~?'}),
    lambda e:e['derived_dictionary'].update({u.KEYS[2]:u.KEYS[2]}),
    lambda e:e['literal_dictionary'].update({u.KEYS[0]:False}),
    lambda e:e['payload'].update(amount=1),lambda e:e.update(payload_hash='0'*64),
    lambda e:e['payload'].update(bad={'$t':'unconverted'}),lambda e:e['payload'].update(bad={'$o':[]})])
def test_corruption_ambiguity_types_and_existing_guards_remain_rejected(mutate):
    _,e=example();seven=new.compact(old.compact(e));mutate(seven)
    with pytest.raises(ValueError):t.unpack(seven)


@pytest.mark.parametrize('literal',[None,{},[['x',1],['x',2]],[[1,'v']],[['x']],[['x',1,2]]])
def test_malformed_literal_wrapper_fails_closed(literal):
    _,e=example();seven=new.compact(old.compact(e));seven['payload']['bad']={new.LITERAL:literal}
    with pytest.raises(ValueError):t.unpack(seven)


def test_container_and_source_expansion_bounds_still_apply(monkeypatch):
    _,e=example();seven=new.compact(old.compact(e));monkeypatch.setattr(new,'MAX_CONTAINER_DEPTH',1)
    with pytest.raises(ValueError,match='depth'):t.unpack(seven)


def test_new_layout_only_uses_the_existing_authorized_CPRT_scope():
    packet={'ticker':'CPRT','primary_reference_usage':{'owner_authorized_scope':{'parent':'CPRT','target_cik':'1637873','document_context_characters':450000}}}
    payload={'packet':packet,'text':'Exact complete source statements and funding conditions. '*20}
    variants=[e for _,e in t._complete_layouts(payload) if e['schema_version']==new.SCHEMA]
    assert variants and all(t.encoded(t.unpack(e))==t.encoded(payload) for e in variants)
    packet['ticker']='V'
    assert all(e['schema_version']!=new.SCHEMA for _,e in t._complete_layouts(payload))


def test_existing_source_expansion_and_unused_dictionary_guards_apply(monkeypatch):
    _,e=example();seven=new.compact(old.compact(e));monkeypatch.setattr(u,'MAX_RESTORED',5)
    with pytest.raises(ValueError,match='bound'):t.unpack(seven)


def test_new_module_changes_processing_version_without_changing_paid_stage_key(tmp_path):
    from test_underwriting_pipeline import company_root
    from underwriting_pipeline import processing_version,stage_hash
    company_root(tmp_path);payload={'complete':'unchanged'}
    before=processing_version(tmp_path);paid=stage_hash(tmp_path,'challenger',payload)
    target=tmp_path/'_system/scripts/underwriting_marker_transport.py'
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text('# checked new transport module')
    assert processing_version(tmp_path)!=before
    assert stage_hash(tmp_path,'challenger',payload)==paid
