"""Compact phrase indexes must preserve full evidence and every old decoder."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_transport as t
from underwriting_contract import ContractError,digest
from underwriting_codex import MAX_INPUT_CHARACTERS,validate_input
from test_underwriting_inline_transport import source_payload


def inline():
    p=source_payload()
    p['literals']=[{'$inline':'~00 ^00 |00 %00 «0»'}, {'$literal_object':[['x',False]]},
                   {'float':1.0,'integer':1,'bool':True,'null':None,'unicode':'日本語 😃\r\n\t'}]
    return p,t._pack_inline(t._pack_dense(p,t._content_segments,8))


def test_grouped_phrase_references_roundtrip_without_changing_old_inline_storage():
    p,v3=inline();before=copy.deepcopy(v3)
    grouped=t._group_inline(v3)
    assert grouped['schema_version']=='underwriting-transport/4'
    assert t.unpack(grouped)==p and digest(t.unpack(grouped))==digest(p)
    assert v3==before and t.unpack(v3)==p
    restored=t.unpack(grouped)
    assert type(restored['literals'][2]['float']) is float and type(restored['literals'][2]['integer']) is int


@pytest.mark.parametrize('bad',['~','~0','~!!','~zz',None,0])
def test_malformed_or_out_of_range_grouped_references_fail_closed(bad):
    p,v3=inline();grouped=t._group_inline(v3);grouped['payload']={'$inline':bad}
    with pytest.raises(ContractError,match='grouped'):
        t.unpack(grouped)


def test_grouped_dictionary_is_literal_and_changed_or_unused_entries_are_rejected():
    p=source_payload()
    for d in p['packet']['documents']:
        d['contexts'][0]=d['contexts'][0].replace('primary source','primary ~00 ^00 «0» source')
    grouped=t._group_inline(t._pack_inline(t._pack_dense(p,t._content_segments,8)))
    assert any('~00' in s or '«0»' in s for s in grouped['phrase_dictionary'])
    assert t.unpack(grouped)==p
    changed=copy.deepcopy(grouped);changed['phrase_dictionary'][0]+=' changed'
    with pytest.raises(ContractError,match='changed'):t.unpack(changed)
    unused=copy.deepcopy(grouped);unused['phrase_dictionary'].append('unbound original text')
    with pytest.raises(ContractError,match='Unused inline'):t.unpack(unused)


@pytest.mark.parametrize('markers',['','^^','x','~^|%extra',None])
def test_marker_alphabet_cannot_be_redefined(markers):
    p,v3=inline();grouped=t._group_inline(v3);grouped['phrase_markers']=markers
    with pytest.raises(ContractError,match='grouped'):t.unpack(grouped)


def test_large_complete_payload_chooses_the_new_layout_before_the_actual_native_gate(monkeypatch):
    p={'packet':{'documents':[{'id':'doc_'+str(i),'contexts':[''.join(
        'Verbatim contractual provision_'+str(j%30)+' with original obligations and exact original payment language, '
        'unique_'+str(i)+'_'+str(j)+'. ' for j in range(240))]} for i in range(8)]}}
    original_hash=digest(p)
    old=[t.encoded(p),t.INSTRUCTIONS+t.encoded(t._pack_legacy(p))]
    for dense in t._dense_layouts(p):
        old.append(t.DENSE_INSTRUCTIONS+t.encoded(dense))
        v3=t._pack_inline(dense)
        if v3:old.append(t.INLINE_INSTRUCTIONS+t.encoded(v3))
    remaining=len(min(old,key=len))-512
    monkeypatch.setattr(t,'GROUPED_MIN_CHARACTERS',0)
    rendered=t.render(p)
    validate_input('H'*(MAX_INPUT_CHARACTERS-remaining)+rendered)
    assert 'underwriting-transport/4' in rendered
    assert digest(p)==original_hash


@pytest.mark.parametrize('count',[4096,4097,8193,12289,16384])
def test_group_boundaries_and_active_marker_literals_preserve_every_character(count):
    phrases=['literal ~00 ^00 |00 %00 entry_'+str(i)+' ' for i in range(count)]
    tail=' original ~00 ^00 |00 %00 «0» '
    original=''.join(phrases)+tail
    v3={'schema_version':'underwriting-transport/3','payload_hash':digest(original),
        'payload':{'$inline':''.join('«'+str(i)+'»' for i in range(count))+tail.replace('«','««')},
        'phrase_dictionary':phrases,'string_dictionary':[],'object_schemas':[]}
    grouped=t._group_inline(v3)
    assert t.unpack(grouped)==original and len(grouped['phrase_markers'])==(count+4095)//4096


def test_small_paid_payloads_do_not_enter_the_additional_phrase_search(monkeypatch):
    monkeypatch.setattr(t,'_pack_grouped',lambda *a:pytest.fail('Small input entered expensive phrase search'))
    assert t.render({'small':'unchanged'})==t.encoded({'small':'unchanged'})
