"""Explicit derived rows preserve the complete original and exact native cap."""
import sys,copy,json
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_derived_key_transport as d
import underwriting_literal_key_transport as k
import underwriting_front_array_transport as f
import underwriting_dictionary_transport as rows
import underwriting_marker_transport as markers
import underwriting_compact_transport as six
import underwriting_token_transport as tokens
import underwriting_transport as t
import underwriting_pipeline as pipeline
import underwriting_codex as codex
from underwriting_contract import digest
from test_underwriting_completion_authority import env

def sample():
 n=2000;keys=tokens.KEYS;lit={keys[i]:'word_'+str(i)+' ' for i in range(n)}
 derived={keys[n+i]:keys[i]+keys[(i+1)%n]+('香' if i==0 else '') for i in range(n)}
 text=''.join(lit[keys[i]]+lit[keys[(i+1)%n]]+('香' if i==0 else '') for i in range(n))
 original={'ticker':'CPRT','text':text,'types':[1,1.0,-0.0,False,None,'😀']}
 five={'schema_version':tokens.SCHEMA,'payload_hash':digest(original),'payload':{'ticker':'CPRT','text':{'$tokens':keys[n:2*n]},'types':copy.deepcopy(original['types'])},'object_schemas':[],'string_dictionary':[],'literal_dictionary':lit,'derived_dictionary':derived,'maximum_dag_depth':12,'literal_escape':'~'}
 nine=rows.compact(markers.compact_strings(markers.compact(six.compact(five))))
 twelve=k.compact(f.compact(nine));assert twelve
 return original,five,twelve

@pytest.mark.parametrize('values',[
 ['丁一','丂一丁'],['丁一~一','丂丁~~|'],['丁literal|\\value','丂丁一'],
 ['丁一香','丂丁一'],['丁一~一~丁','丂丁~~一'],['丁','丂一'],
])
def test_ordered_explicit_keys_and_literal_inactive_glyphs_roundtrip(values):
 assert d._decode(d._encode(values,['一']),['一'])==values

@pytest.mark.parametrize('value',['','|D|','|D|text','|D|丁~','|D|丁~x','|D|丁丁','|D|丁a丁b','|D|丁~|','|D|丁~|x','|D|丁~|丂丂一'])
def test_ambiguous_cyclic_and_malformed_streams_fail(value):
 with pytest.raises(ValueError):d._decode(value,['一'])

@pytest.mark.parametrize('keys',[None,False,[],[''],['x'],['一','一'],[[]],[1]])
def test_existing_literal_scope_is_required(keys):
 with pytest.raises(ValueError):d._decode('|D|丁一',keys)

def test_complete_prior_envelope_and_types_remain_identical():
 original,_,twelve=sample();before=copy.deepcopy(twelve);thirteen=d.compact(twelve)
 assert thirteen and twelve==before
 assert t.encoded(t.unpack(thirteen))==t.encoded(original)
 assert t.encoded(k.unpack(twelve))==t.encoded(original)
 assert thirteen['transport_hash']==twelve['transport_hash'] and thirteen['payload_hash']==digest(original)

@pytest.mark.parametrize('mutation',[
 lambda e:e.update(extra=True),lambda e:e.update(payload_hash='0'*64),lambda e:e.update(transport_hash='0'*64),
 lambda e:e.update(schema_version=k.SCHEMA),lambda e:e.update(encoded_envelope=[]),
 lambda e:e['encoded_envelope'].update(encoded_envelope=[]),
 lambda e:e['encoded_envelope']['encoded_envelope'].update(derived_dictionary='|D|丁一'),
])
def test_original_complete_identity_guards_still_fail_closed(mutation):
 _,_,twelve=sample();e=d.compact(twelve);mutation(e)
 with pytest.raises(ValueError):d.unpack(e)

def test_original_expansion_and_depth_guards_are_still_enforced(monkeypatch):
 _,_,twelve=sample();e=d.compact(twelve);monkeypatch.setattr(tokens,'MAX_RESTORED',5)
 with pytest.raises(ValueError,match='bound'):t.unpack(e)

def test_derived_entry_and_text_bounds_are_unchanged(monkeypatch):
 monkeypatch.setattr(d,'MAX_ENTRIES',2)
 with pytest.raises(ValueError,match='bound'):d._decode('|D|丁一丂一',['一'])
 monkeypatch.setattr(d,'MAX_ENTRIES',32768);monkeypatch.setattr(d,'MAX_DICTIONARY_TEXT',2)
 with pytest.raises(ValueError,match='bound'):d._decode('|D|丁abc',['一'])

def test_normal_budget_uses_complete_derived_stream_before_fallback(monkeypatch):
 original,five,twelve=sample();e=d.compact(twelve);budget=len(d.INSTRUCTIONS+t.encoded(e))
 assert budget<len(k.INSTRUCTIONS+t.encoded(twelve))
 monkeypatch.setattr(tokens,'eligible',lambda p:True);monkeypatch.setattr(tokens,'pack',lambda p:copy.deepcopy(five));monkeypatch.setattr(t,'render',lambda p:'held complete original fallback')
 rendered=t.render_for_budget(original,budget)
 assert rendered.startswith(d.INSTRUCTIONS) and t.encoded(t.unpack(json.loads(rendered[len(d.INSTRUCTIONS):])))==t.encoded(original)
 assert t.render_for_budget(original,budget-1)=='held complete original fallback'

def test_old_paid_fitting_layout_does_not_use_new_stream(monkeypatch):
 original,five,twelve=sample();monkeypatch.setattr(tokens,'eligible',lambda p:True);monkeypatch.setattr(tokens,'pack',lambda p:copy.deepcopy(five))
 monkeypatch.setattr(d,'compact',lambda p:(_ for _ in ()).throw(AssertionError('old layout already fits')))
 assert len(t.render_for_budget(original,len(k.INSTRUCTIONS+t.encoded(twelve))))<=len(k.INSTRUCTIONS+t.encoded(twelve))

def test_native_budget_counts_whole_prefix_newlines_and_surrogates(monkeypatch):
 original,five,_=sample();prefix='ROLE\n😀\n';monkeypatch.setattr(tokens,'eligible',lambda p:True);monkeypatch.setattr(tokens,'pack',lambda p:copy.deepcopy(five));monkeypatch.setattr(t,'render',lambda p:'held complete fallback')
 actual=codex.input_characters;monkeypatch.setattr(codex,'input_characters',lambda s:actual(s,newline='\r\n'))
 e=d.compact(sample()[2]);budget=actual(prefix+d.INSTRUCTIONS+t.encoded(e),newline='\r\n')
 result=t.render_for_budget(original,budget,native_prefix=prefix)
 assert result.startswith(d.INSTRUCTIONS) and actual(prefix+result,newline='\r\n')<=budget
 assert t.render_for_budget(original,budget-1,native_prefix=prefix)=='held complete fallback'
 assert len(prefix+result)<budget

@pytest.mark.parametrize('prefix',[False,1,[],{}])
def test_native_prefix_type_is_strict(prefix):
 with pytest.raises(ValueError):t.render_for_budget({},100,native_prefix=prefix)

def test_new_source_fingerprint_preserves_paid_stage_key(env):
 root,work,state,author,_=env;p={'packet':{'ticker':'CPRT','packet_hash':author['packet_hash'],'evidence_hash':author['evidence_hash']}}
 version=pipeline.processing_version(root);key=pipeline.stage_hash(root,'author',p);module=root/'_system/scripts/underwriting_derived_key_transport.py';module.parent.mkdir(parents=True,exist_ok=True);module.write_text('explicit derived stream',encoding='utf-8')
 assert pipeline.processing_version(root)!=version and pipeline.stage_hash(root,'author',p)==key
