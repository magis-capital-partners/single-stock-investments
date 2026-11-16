"""Short containers preserve every token dictionary guard and original JSON value."""
import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_transport as t
import underwriting_token_transport as u
import underwriting_compact_transport as c
from underwriting_contract import digest
from test_underwriting_token_transport import example


def test_compact_roundtrip_preserves_all_types_order_and_hashes():
 original,envelope=example();before=copy.deepcopy(envelope);short=c.compact(envelope)
 assert t.encoded(t.unpack(short))==t.encoded(original)
 assert envelope==before and short['payload_hash']==envelope['payload_hash']
 assert short['literal_dictionary']==envelope['literal_dictionary'] and short['derived_dictionary']==envelope['derived_dictionary']
 assert c.SHORT in short['payload']['text']


def test_repeated_container_labels_shrink_without_removing_any_source():
 original,envelope=example();original['rows']=[original['text']]*100
 envelope['payload']['rows']=[{'$tokens':u.KEYS[2]} for _ in range(100)];envelope['payload_hash']=digest(original)
 short=c.compact(envelope)
 assert len(t.encoded(envelope))-len(t.encoded(short))==505
 assert t.encoded(t.unpack(short))==t.encoded(original)


@pytest.mark.parametrize('literal',[{'$t':'source literal'},{'$literal_v6':[]},{'$t':{'$literal_v6':['x']}},
                                  {'$t':None,'other':False},{'$literal_v6':[['key',1.0]],'$t':'text'}])
def test_original_marker_keys_and_nested_literals_are_not_interpreted(literal):
 original,envelope=example();original['literal']=literal;envelope['payload']['literal']=copy.deepcopy(literal);envelope['payload_hash']=digest(original)
 assert t.encoded(t.unpack(c.compact(envelope)))==t.encoded(original)


@pytest.mark.parametrize('mutate',[
 lambda e:e.update(extra='field'),lambda e:e.update(maximum_dag_depth=13),lambda e:e.update(maximum_dag_depth=True),
 lambda e:e['payload']['text'].update(extra='ambiguous'),lambda e:e['payload']['text'].update({'$t':False}),
 lambda e:e['payload']['text'].update({'$t':'~'}),lambda e:e['payload']['text'].update({'$t':'~?'}),
 lambda e:e['derived_dictionary'].update({u.KEYS[2]:u.KEYS[2]}),
 lambda e:e['literal_dictionary'].update({u.KEYS[0]:False}),
 lambda e:e['payload'].update(amount=1),lambda e:e.update(payload_hash='0'*64)])
def test_ambiguous_corrupt_typed_or_recursive_input_remains_rejected(mutate):
 _,envelope=example();short=c.compact(envelope);mutate(short)
 with pytest.raises(ValueError):t.unpack(short)


@pytest.mark.parametrize('literal',[None,{},[['x',1],['x',2]],[[1,'value']],[['x']],[['x',1,2]]])
def test_invalid_literal_wrappers_fail_closed(literal):
 _,envelope=example();short=c.compact(envelope);short['payload']['bad']={c.LITERAL:literal}
 with pytest.raises(ValueError):t.unpack(short)


def test_long_container_nesting_is_bounded(monkeypatch):
 _,envelope=example();short=c.compact(envelope);monkeypatch.setattr(c,'MAX_CONTAINER_DEPTH',1)
 with pytest.raises(ValueError,match='depth'):t.unpack(short)


def test_old_token_transport_still_decodes_without_reencoding():
 original,envelope=example();assert t.encoded(t.unpack(envelope))==t.encoded(original)
 assert envelope['schema_version']=='underwriting-transport/5'


def test_unchanged_source_expansion_and_dictionary_budgets_still_apply(monkeypatch):
 _,envelope=example();short=c.compact(envelope);monkeypatch.setattr(u,'MAX_RESTORED',5)
 with pytest.raises(ValueError,match='bound'):t.unpack(short)


def test_unused_dictionary_entries_stay_invalid():
 _,envelope=example();short=c.compact(envelope);short['payload']['text']={c.SHORT:u.KEYS[0]+u.KEYS[1]}
 with pytest.raises(ValueError,match='Unused'):t.unpack(short)


def test_renderer_offers_new_layout_only_to_existing_authorized_CPRT_scope():
 payload={'packet':{'ticker':'CPRT','primary_reference_usage':{'owner_authorized_scope':{'parent':'CPRT','target_cik':'1637873','document_context_characters':450000}}},'text':'Cash receivables debt and claims. '*30}
 layouts=list(t._complete_layouts(payload));short=[e for _,e in layouts if e['schema_version']==c.SCHEMA]
 assert short and all(t.encoded(t.unpack(e))==t.encoded(payload) for e in short)
 payload['packet']['ticker']='V'
 assert all(e['schema_version']!=c.SCHEMA for _,e in t._complete_layouts(payload))


def test_old_CPRT_scope_does_not_acquire_the_new_layout():
 payload={'packet':{'ticker':'CPRT'},'text':'Cash receivables debt. '*20}
 assert all(e['schema_version']!=c.SCHEMA for _,e in t._complete_layouts(payload))
