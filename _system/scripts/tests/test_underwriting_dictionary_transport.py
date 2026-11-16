"""Complete dictionary rows preserve every original source and existing guard."""
import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_transport as t
import underwriting_dictionary_transport as rows
import underwriting_marker_transport as m
import underwriting_compact_transport as six
import underwriting_token_transport as tokens
from underwriting_contract import digest
from test_underwriting_token_transport import example


def fixture():
    original,e=example()
    original['literal']=['^','~','',None,False,0,1.0,{'^':'literal','!':['~']}]
    e['payload']['literal']=copy.deepcopy(original['literal']);e['payload_hash']=digest(original)
    return original,m.compact_strings(m.compact(six.compact(e)))


def test_complete_explicit_dictionary_rows_preserve_exact_payload_and_input():
    original,e=fixture();before=copy.deepcopy(e);nine=rows.compact(e)
    assert t.encoded(t.unpack(nine))==t.encoded(original) and e==before
    for field in ('literal_dictionary','derived_dictionary'):
        assert nine[field]==[key+value for key,value in e[field].items()]
        assert len(t.encoded(e[field]))-len(t.encoded(nine[field]))==3*len(e[field])
    assert nine['payload']==e['payload'] and nine['string_dictionary']==e['string_dictionary']


@pytest.mark.parametrize('mutate',[
 lambda e:e.update(schema_version='underwriting-transport/8'),
 lambda e:e.update(extra=True),lambda e:e.update(maximum_dag_depth=13),
 lambda e:e.update(literal_dictionary={}),lambda e:e.update(derived_dictionary='invalid'),
 lambda e:e['literal_dictionary'].append(e['literal_dictionary'][0]),
 lambda e:e['literal_dictionary'].__setitem__(0,''),
 lambda e:e['literal_dictionary'].__setitem__(0,False),
 lambda e:e['literal_dictionary'].__setitem__(0,[tokens.KEYS[0],'text']),
 lambda e:e['literal_dictionary'].reverse(),
 lambda e:e['literal_dictionary'].__setitem__(0,'?'+e['literal_dictionary'][0][1:]),
 lambda e:e['derived_dictionary'].__setitem__(0,e['literal_dictionary'][0]),
 lambda e:e['derived_dictionary'].__setitem__(0,e['derived_dictionary'][0][0]*2),
 lambda e:e['derived_dictionary'].__setitem__(0,e['derived_dictionary'][0][0]+'~'),
 lambda e:e.update(payload_hash='0'*64),
 lambda e:e['payload'].update(text='^~?'),
 lambda e:e['payload'].update(text='^'+tokens.KEYS[-1]),
 lambda e:e['payload'].update(bad='~unescaped'),
 lambda e:e['payload'].update(bad={'^':'unconverted'}),
 lambda e:e['literal_dictionary'].append(tokens.KEYS[-1]+'unused'),
])
def test_rows_cannot_weaken_existing_identity_type_escape_order_or_replay_checks(mutate):
    _,e=fixture();nine=rows.compact(e);mutate(nine)
    with pytest.raises(ValueError):t.unpack(nine)


@pytest.mark.parametrize('bound',[1,2])
def test_dictionary_entry_bound_is_preserved(monkeypatch,bound):
    _,e=fixture();nine=rows.compact(e);monkeypatch.setattr(rows,'MAX_ENTRIES',bound)
    with pytest.raises(ValueError,match='bound|rows'):t.unpack(nine)


def test_original_expansion_bounds_are_preserved(monkeypatch):
    _,e=fixture();nine=rows.compact(e);monkeypatch.setattr(tokens,'MAX_RESTORED',5)
    with pytest.raises(ValueError,match='bound'):t.unpack(nine)


def test_budgeted_rows_preserve_full_request_and_skip_unused_search(monkeypatch):
    original,e=example()
    monkeypatch.setattr(tokens,'eligible',lambda p:True);monkeypatch.setattr(tokens,'pack',lambda p:copy.deepcopy(e))
    eight=m.compact_strings(m.compact(six.compact(e)));nine=rows.compact(eight)
    # The instruction overhead matters; a larger real dictionary provides savings.
    monkeypatch.setattr(rows,'INSTRUCTIONS','rows\n')
    budget=len('rows\n'+t.encoded(nine))
    monkeypatch.setattr(t,'render',lambda p:(_ for _ in ()).throw(AssertionError('unused search')))
    text=t.render_for_budget(original,budget)
    assert len(text)<=budget and t.encoded(t.unpack(json.loads(text[text.index('{"schema_version":'):])) )==t.encoded(original)


def test_existing_fitting_layout_is_retained(monkeypatch):
    original,e=example();monkeypatch.setattr(tokens,'eligible',lambda p:True);monkeypatch.setattr(tokens,'pack',lambda p:copy.deepcopy(e))
    monkeypatch.setattr(rows,'compact',lambda e:(_ for _ in ()).throw(AssertionError('already fits')))
    assert 'underwriting-transport/8' in t.render_for_budget(original,1_000_000)


def test_undersized_budget_keeps_complete_fallback(monkeypatch):
    original,e=example();monkeypatch.setattr(tokens,'eligible',lambda p:True);monkeypatch.setattr(tokens,'pack',lambda p:copy.deepcopy(e))
    monkeypatch.setattr(t,'render',lambda p:'existing complete fallback')
    assert t.render_for_budget(original,1)=='existing complete fallback'


@pytest.mark.parametrize('value',['','x','~','^','\x00','😀','中'])
def test_empty_and_special_literal_row_values_are_restored_exactly(value):
    original={'text':value};key=tokens.KEYS[0]
    e={'schema_version':tokens.SCHEMA,'payload_hash':digest(original),
       'payload':{'text':{'$tokens':key}},'object_schemas':[],'string_dictionary':[],
       'literal_dictionary':{key:value},'derived_dictionary':{},'maximum_dag_depth':12,'literal_escape':'~'}
    nine=rows.compact(m.compact_strings(m.compact(six.compact(e))))
    assert nine['literal_dictionary']==[key+value]
    assert t.encoded(t.unpack(nine))==t.encoded(original)
