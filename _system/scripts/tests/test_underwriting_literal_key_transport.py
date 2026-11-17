import sys,json,copy
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_literal_key_transport as k
import underwriting_front_array_transport as f
import underwriting_transport as t
from underwriting_contract import digest
from test_underwriting_array_transport import sample

@pytest.mark.parametrize('values',[[''],['',''],['hello','world'],['|K|','|A|','|F|','|S|'],['~','~~','~一','一丁中😀'],['\\','a|b','a\\|b'],['x\r\n\x00','中文日本語한국어']])
def test_explicit_keys_and_all_literal_characters_roundtrip(values):
 rows=[key+value for key,value in zip(k.KEYS,values)];assert k._decode(k._encode(rows))==rows

def test_complete_wrapped_payload_and_prior_envelope_unchanged():
 p,_,nine=sample(large=True);eleven=f.compact(nine);before=copy.deepcopy(eleven);twelve=k.compact(eleven);assert twelve and eleven==before and t.encoded(k.unpack(twelve))==t.encoded(p)
 assert t.encoded(f.unpack(eleven))==t.encoded(p) and twelve['transport_hash']==digest(eleven)

@pytest.mark.parametrize('text',['','|K|','|K|text','|K|一x~','|K|一x~x','|K|一x一y','|K|~一text'])
def test_bad_streams_fail(text):
 with pytest.raises(ValueError):k._decode(text)

@pytest.mark.parametrize('rows',[[],[''],['xvalue'],['一a','一b'],[True],[None]])
def test_bad_explicit_rows_fail(rows):
 with pytest.raises(ValueError):k._encode(rows)

@pytest.mark.parametrize('mutation',[lambda e:e.update(extra=1),lambda e:e.update(payload_hash='0'*64),lambda e:e.update(transport_hash='0'*64),lambda e:e.update(schema_version='underwriting-transport/11'),lambda e:e.update(encoded_envelope=[]),lambda e:e['encoded_envelope'].update(payload_hash='0'*64),lambda e:e['encoded_envelope']['encoded_envelope'].update(literal_dictionary='|K|一bad')])
def test_complete_identity_guards_fail(mutation):
 _,_,nine=sample(large=True);e=k.compact(f.compact(nine));mutation(e)
 with pytest.raises(ValueError):k.unpack(e)

def test_existing_text_and_entry_bounds_unchanged(monkeypatch):
 monkeypatch.setattr(k,'MAX_DICTIONARY_TEXT',3)
 with pytest.raises(ValueError,match='bound'):k._decode('|K|一abcd')
 monkeypatch.setattr(k,'MAX_DICTIONARY_TEXT',64000000);monkeypatch.setattr(k,'MAX_ENTRIES',1)
 with pytest.raises(ValueError,match='bound'):k._decode('|K|一a丁b')

def test_natural_key_glyphs_in_literal_values_never_become_keys():
 rows=['一first丁value','丁second一value'];stream=k._encode(rows);assert '~丁' in stream and '~一' in stream and k._decode(stream)==rows

import underwriting_token_transport as tokens
import underwriting_compact_transport as six
import underwriting_marker_transport as markers
import underwriting_dictionary_transport as rows
import underwriting_pipeline as pipeline
from test_underwriting_completion_authority import env

def large_sample():
 keys=tokens.KEYS[:3000];literals={key:'word_'+str(i)+' ' for i,key in enumerate(keys)}
 original={'ticker':'CPRT','text':''.join(literals.values()),'types':[1,1.0,-0.0,False,None,'😀']}
 five={'schema_version':tokens.SCHEMA,'payload_hash':digest(original),'payload':{'ticker':'CPRT','text':{'$tokens':keys},'types':copy.deepcopy(original['types'])},'object_schemas':[],'string_dictionary':[],'literal_dictionary':literals,'derived_dictionary':{},'maximum_dag_depth':12,'literal_escape':'~'}
 nine=rows.compact(markers.compact_strings(markers.compact(six.compact(five))))
 return original,five,f.compact(nine)

def test_generic_decoder_restores_complete_original_and_old_eleven():
 original,_,eleven=large_sample();twelve=k.compact(eleven)
 assert t.encoded(t.unpack(twelve))==t.encoded(original)
 assert t.encoded(t.unpack(eleven))==t.encoded(original)

def test_normal_budget_selects_complete_literal_stream_before_unchanged_fallback(monkeypatch):
 original,five,eleven=large_sample();twelve=k.compact(eleven);budget=len(k.INSTRUCTIONS+t.encoded(twelve))
 assert budget<len(f.INSTRUCTIONS+t.encoded(eleven))
 monkeypatch.setattr(tokens,'eligible',lambda p:True);monkeypatch.setattr(tokens,'pack',lambda p:copy.deepcopy(five));monkeypatch.setattr(t,'render',lambda p:'held complete original fallback')
 result=t.render_for_budget(original,budget)
 assert result.startswith(k.INSTRUCTIONS) and t.encoded(t.unpack(json.loads(result[len(k.INSTRUCTIONS):])))==t.encoded(original)
 assert t.render_for_budget(original,budget-1)=='held complete original fallback'

def test_old_fitting_layout_keeps_original_prompt(monkeypatch):
 original,five,eleven=large_sample();monkeypatch.setattr(tokens,'eligible',lambda p:True);monkeypatch.setattr(tokens,'pack',lambda p:copy.deepcopy(five))
 monkeypatch.setattr(k,'compact',lambda e:(_ for _ in ()).throw(AssertionError('existing complete layout fits')))
 assert len(t.render_for_budget(original,len(f.INSTRUCTIONS+t.encoded(eleven))))<=len(f.INSTRUCTIONS+t.encoded(eleven))

def test_unowned_inputs_use_unchanged_path(monkeypatch):
 monkeypatch.setattr(tokens,'eligible',lambda p:False);monkeypatch.setattr(k,'compact',lambda e:(_ for _ in ()).throw(AssertionError('unowned stream')));monkeypatch.setattr(t,'render',lambda p:'unchanged')
 assert t.render_for_budget({'packet':{'ticker':'V'}},1)=='unchanged'

def test_new_decoder_fingerprint_preserves_paid_stage_identity(env):
 root,work,state,author,_=env;p={'packet':{'ticker':'CPRT','packet_hash':author['packet_hash'],'evidence_hash':author['evidence_hash']}}
 version=pipeline.processing_version(root);identity=pipeline.stage_hash(root,'author',p);path=root/'_system/scripts/underwriting_literal_key_transport.py';path.parent.mkdir(parents=True,exist_ok=True);path.write_text('explicit literal key stream',encoding='utf-8')
 assert pipeline.processing_version(root)!=version and pipeline.stage_hash(root,'author',p)==identity

def test_existing_full_payload_expansion_guard_remains(monkeypatch):
 _,_,eleven=large_sample();twelve=k.compact(eleven);monkeypatch.setattr(tokens,'MAX_RESTORED',5)
 with pytest.raises(ValueError,match='bound'):t.unpack(twelve)
