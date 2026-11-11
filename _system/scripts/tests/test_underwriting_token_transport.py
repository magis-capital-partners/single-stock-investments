"""Complete text and typed reconstruction; malformed dictionary transports fail closed."""
import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_transport as t
import underwriting_token_transport as u
from underwriting_contract import digest

A,B,C=u.KEYS[:3]
def example():
    original={'amount':1.0,'text':'Cash debt ','ids':['obs_01',None,False]}
    envelope={'schema_version':u.SCHEMA,'payload_hash':digest(original),'payload':{**original,'text':{'$tokens':C}},'object_schemas':[],'string_dictionary':[],
        'literal_dictionary':{A:'Cash ',B:'debt '},'derived_dictionary':{C:A+B},'maximum_dag_depth':12,'literal_escape':'~'}
    return original,envelope

def test_explicit_lookup_restores_exact_characters_types_and_order():
    original,envelope=example()
    assert t.encoded(t.unpack(envelope))==t.encoded(original)
    assert isinstance(t.unpack(envelope)['amount'],float)

def test_literal_marker_escaping_is_lossless():
    original,envelope=example();marker=A
    original['text']='Cash debt '+marker+'literal'
    envelope['payload']['text']['$tokens']+='~'+marker+'literal';envelope['payload_hash']=digest(original)
    assert t.encoded(t.unpack(envelope))==t.encoded(original)

@pytest.mark.parametrize('bad',['~','~?',C+'x~'])
def test_incomplete_or_unknown_reference_is_rejected(bad):
    _,envelope=example();envelope['payload']['text']['$tokens']=bad
    with pytest.raises(ValueError):t.unpack(envelope)

@pytest.mark.parametrize('bad',[C,C+A])
def test_forward_and_cyclic_derived_references_are_rejected(bad):
    _,envelope=example();envelope['derived_dictionary'][C]=bad
    with pytest.raises(ValueError,match='forward or cyclic'):t.unpack(envelope)

@pytest.mark.parametrize('change',[lambda e:e.update(maximum_dag_depth=13),lambda e:e.update(maximum_dag_depth=True),lambda e:e.update(extra='unrecognized'),lambda e:e['literal_dictionary'].update({C:'duplicate'}),lambda e:e['literal_dictionary'].update({A:False}),lambda e:e['payload']['text'].update(extra='ambiguous')])
def test_metadata_conflicts_and_ambiguous_objects_fail_closed(change):
    _,envelope=example();change(envelope)
    with pytest.raises(ValueError):t.unpack(envelope)

def test_dictionary_written_order_is_authenticated():
    _,envelope=example();envelope['literal_dictionary']={B:'debt ',A:'Cash '}
    with pytest.raises(ValueError,match='key order'):t.unpack(envelope)

def test_unused_dictionary_cannot_hide_unrelated_material():
    _,envelope=example();envelope['payload']['text']={'$tokens':A+B}
    with pytest.raises(ValueError,match='Unused'):t.unpack(envelope)

def test_changed_financial_type_or_value_rejects_payload_hash():
    _,envelope=example();envelope['payload']['amount']=1
    with pytest.raises(ValueError,match='changed'):t.unpack(envelope)

def test_bounded_expansion_does_not_allocate_unbounded_text(monkeypatch):
    _,envelope=example();monkeypatch.setattr(u,'MAX_RESTORED',5)
    with pytest.raises(ValueError,match='bound'):t.unpack(envelope)

def test_cumulative_dictionary_expansion_is_bounded(monkeypatch):
    _,envelope=example();monkeypatch.setattr(u,'MAX_DICTIONARY_TEXT',12)
    with pytest.raises(ValueError,match='bound'):t.unpack(envelope)

def test_derived_nesting_is_bounded():
    _,envelope=example();envelope['literal_dictionary']={A:'Cash '};derived={};prior=A
    for i in range(1,15):
        key=u.KEYS[i];derived[key]=prior+prior;prior=key
    envelope['derived_dictionary']=derived;envelope['payload']['text']={'$tokens':prior}
    with pytest.raises(ValueError,match='nesting'):t.unpack(envelope)

def test_supported_packer_preserves_unicode_escapes_shapes_and_source_hashes():
    payload={'text':('Cash debt assets. '+u.KEYS[0]+'Café “receivables”\n')*30,'sequence':[None,False,0,0.0,{'source_hash':'a'*64}],'literal':'@12'}
    packed=u.pack(payload)
    assert packed and t.encoded(t.unpack(packed))==t.encoded(payload)

@pytest.mark.parametrize('ticker',['V','TFPM','OTHER',None])
def test_new_layout_does_not_change_other_companies(ticker):
    assert not u.eligible({'packet':{'ticker':ticker,'primary_reference_usage':{'owner_authorized_scope':{'parent':'CPRT','target_cik':'1637873','document_context_characters':450000}}}})

def test_old_cprt_paid_packets_do_not_opt_into_new_layout():
    assert not u.eligible({'packet':{'ticker':'CPRT'}})

def test_reserved_original_marker_uses_legacy_supported_layout():
    assert u.pack({'$tokens':'literal'}) is None


def test_adjacent_identical_references_do_not_conflict_with_literal_escapes():
    original,envelope=example();original['text']='Cash debt Cash debt '
    envelope['payload']['text']['$tokens']=C+C;envelope['payload_hash']=digest(original)
    assert t.encoded(t.unpack(envelope))==t.encoded(original)

def test_long_at_prefix_and_nested_reserved_objects_preserve_original_shapes():
    payload={'long':'@'+'Cash debt assets '*40,'nested':{'marker':'~'+u.KEYS[0]},'repeat':['Cash debt assets '*40]*3}
    packed=u.pack(payload)
    assert packed and t.encoded(t.unpack(packed))==t.encoded(payload)
