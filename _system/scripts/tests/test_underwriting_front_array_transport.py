import sys,json,copy
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_front_array_transport as f
import underwriting_array_transport as old
import underwriting_transport as t
import underwriting_token_transport as tokens
from underwriting_contract import digest
from test_underwriting_array_transport import sample

@pytest.mark.parametrize('values',[
 [''],['',''],['projection_warehouse_parent_funding_y1','projection_warehouse_parent_funding_y2','projection_warehouse_parent_funding_y1'],
 ['Lliteral','p12:literal','P0,1:literal','|F|','|A|','|S|','\\','|','a|b','a\\b'],
 ['😀alpha','😀beta','😀alpha'],['中\r\n"\x00','中\r\n"\x00extra','中\r\n"\x00'],['a','b','c']*100,
])
def test_front_members_exact(values):
 packed=f._front_join(values);assert f._front_members(packed[len(f.FRONT):])==values

def test_complete_inner_payload_round_trip_and_old_layout_unchanged():
 original,_,nine=sample();before=copy.deepcopy(nine);eleven=f.compact(nine)
 assert eleven['transport_hash']==digest(nine) and nine==before
 assert t.encoded(f.unpack(eleven))==t.encoded(original)
 assert t.encoded(f._restore(eleven['encoded_envelope']))==t.encoded(nine)
 assert t.encoded(t.unpack(old.compact(nine)))==t.encoded(original)
 assert '1.0' in t.encoded(f.unpack(eleven)) and '-0.0' in t.encoded(f.unpack(eleven))

@pytest.mark.parametrize('text',['','p1:x','P0,1:x','Lx|p2:y','Lx|P1,1:y','Lx|P-1,1:y','Lx|P0,-1:y','Lx|p01:y','Lx|P0,01:y','Lx|q1:x','Lx|p1:y\\','Lx|p1:\\q'])
def test_malformed_front_members_fail(text):
 with pytest.raises(ValueError):f._front_members(text)

@pytest.mark.parametrize('change',[
 lambda e:e.update(schema_version='underwriting-transport/10'),lambda e:e.update(extra=True),
 lambda e:e.update(payload_hash='0'*64),lambda e:e.update(transport_hash='0'*64),lambda e:e.update(encoded_envelope=[]),
 lambda e:e['encoded_envelope'].update(payload='|UNKNOWN|'),lambda e:e['encoded_envelope'].update(payload='|S|not-prefixed'),
 lambda e:e['encoded_envelope'].update(payload='|F|P0,0:bad'),
])
def test_identity_and_malformed_wrapper_fail(change):
 _,_,nine=sample();e=f.compact(nine);change(e)
 with pytest.raises(ValueError):f.unpack(e)

def test_prefix_expansion_is_bounded_before_allocation(monkeypatch):
 monkeypatch.setattr(f,'MAX_DICTIONARY_TEXT',8)
 with pytest.raises(ValueError,match='bound'):f._restore('|F|Labc|p3:def')

def test_prefix_budget_is_shared_across_arrays(monkeypatch):
 monkeypatch.setattr(f,'MAX_DICTIONARY_TEXT',5)
 with pytest.raises(ValueError,match='bound'):f._restore(['|F|Labc','|F|Ldef'])

def test_existing_restored_payload_bound_remains(monkeypatch):
 _,_,nine=sample();e=f.compact(nine);monkeypatch.setattr(tokens,'MAX_RESTORED',5)
 with pytest.raises(ValueError,match='bound'):f.unpack(e)

def test_original_marker_literals_are_not_redecoded():
 for value in ('|F|','|A|','|S|','|F|P0,0:bad'):
  assert f._restore(old.LITERAL+value)==value

def test_complete_repeated_prefix_array_has_a_real_character_saving():
 values=['projection_warehouse_parent_equity_funding_balance_year_'+str(i) for i in range(1000)]
 assert len(t.encoded(f._front_join(values)))<len(t.encoded(old._joined(values)))
 assert f._front_members(f._front_join(values)[len(f.FRONT):])==values

import underwriting_pipeline as pipeline
import underwriting_marker_transport as markers
import underwriting_dictionary_transport as rows
import underwriting_compact_transport as six
from test_underwriting_completion_authority import env

@pytest.mark.parametrize('value',[
 [-1],[-2,'source',1.0,-0.0,False,None],['!L'],['!L',[-1]],['!0'],[-0.0,1],
 [True,False],{'!':[0,[]]},{'!':[True,['literal']]},{'!':[-1,['literal']]},
 {'nested':[[-1,{'!L':'literal'}],['|F|','!L','|A|']]},
])
def test_schema_row_markers_preserve_original_types_and_literals(value):
 original,five,_=sample();original['row_literal']=copy.deepcopy(value)
 five['payload']['row_literal']=copy.deepcopy(value);five['payload_hash']=digest(original)
 nine=rows.compact(markers.compact_strings(markers.compact(six.compact(five))))
 eleven=f.compact(nine)
 assert t.encoded(t.unpack(eleven))==t.encoded(original)
 assert t.encoded(f._restore(eleven['encoded_envelope']))==t.encoded(nine)

@pytest.mark.parametrize('value',[[-32769],[-10**100]])
def test_schema_row_indices_obey_existing_entry_bound(value):
 with pytest.raises(ValueError,match='bound'):f._restore(value)

def test_schema_row_unmatched_arity_fails_original_decoder():
 _,_,nine=sample();e=f.compact(nine)
 e['encoded_envelope']['payload']=[-1,'not the original object']
 # Even a wrapper with an updated inner hash cannot bypass the original decoder.
 restored=f._restore(e['encoded_envelope']);e['transport_hash']=digest(restored)
 with pytest.raises(ValueError):f.unpack(e)

def test_container_depth_stays_bounded_before_restoration(monkeypatch):
 monkeypatch.setattr(f,'MAX_CONTAINER_DEPTH',2)
 with pytest.raises(ValueError,match='depth'):f._restore([[[['x']]]])

def test_generic_unpack_and_normal_budget_path_keep_whole_payload(monkeypatch):
 original,five,_=sample(large=True)
 # Real dense schema objects create a smaller complete row encoding.
 original['schema_rows']=[{'name':'literal','number':1.0,'zero':-0.0} for _ in range(1000)]
 five['object_schemas']=[['name','number','zero']]
 five['payload']['schema_rows']=[{'$o':[0,['literal',1.0,-0.0]]} for _ in range(1000)];five['payload_hash']=digest(original)
 nine=rows.compact(markers.compact_strings(markers.compact(six.compact(five))))
 eleven=f.compact(nine);budget=len(f.INSTRUCTIONS+t.encoded(eleven))
 assert budget<len(old.INSTRUCTIONS+t.encoded(old.compact(nine)))
 monkeypatch.setattr(tokens,'eligible',lambda p:True)
 monkeypatch.setattr(tokens,'pack',lambda p:copy.deepcopy(five))
 monkeypatch.setattr(t,'render',lambda p:'held full original fallback')
 result=t.render_for_budget(original,budget)
 assert result.startswith(f.INSTRUCTIONS) and len(result)<=budget
 assert t.encoded(t.unpack(json.loads(result[len(f.INSTRUCTIONS):])))==t.encoded(original)
 assert t.render_for_budget(original,budget-1)=='held full original fallback'

def test_prior_complete_fitting_layout_does_not_call_new_codec(monkeypatch):
 original,five,nine=sample(large=True)
 monkeypatch.setattr(tokens,'eligible',lambda p:True)
 monkeypatch.setattr(tokens,'pack',lambda p:copy.deepcopy(five))
 monkeypatch.setattr(f,'compact',lambda e:(_ for _ in ()).throw(AssertionError('old layout fits')))
 result=t.render_for_budget(original,len(old.INSTRUCTIONS+t.encoded(old.compact(nine))))
 assert len(result)<=len(old.INSTRUCTIONS+t.encoded(old.compact(nine)))

def test_unowned_payload_never_uses_new_fast_path(monkeypatch):
 monkeypatch.setattr(tokens,'eligible',lambda p:False)
 monkeypatch.setattr(f,'compact',lambda e:(_ for _ in ()).throw(AssertionError('unowned new codec')))
 monkeypatch.setattr(t,'render',lambda p:'original full fallback')
 assert t.render_for_budget({'packet':{'ticker':'V'}},1)=='original full fallback'

def test_decoder_fingerprint_keeps_paid_stage_cache_identity(env):
 root,work,state,author,_=env;payload={'packet':{'ticker':'CPRT','packet_hash':author['packet_hash'],'evidence_hash':author['evidence_hash']}}
 before=pipeline.processing_version(root);paid=pipeline.stage_hash(root,'author',payload)
 module=root/'_system/scripts/underwriting_front_array_transport.py';module.parent.mkdir(parents=True,exist_ok=True);module.write_text('checked prefix rows',encoding='utf-8')
 assert pipeline.processing_version(root)!=before and pipeline.stage_hash(root,'author',payload)==paid
