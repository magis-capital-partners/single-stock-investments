"""Literal CPRT citation presentation; synthetic fixtures are not issuer evidence."""
import copy
import json
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import underwriting_transport as transport
from underwriting_contract import ContractError, digest
from underwriting_evidence import supplemental_observations
from underwriting_codex import validate_input

PREFIX = 'FROZEN SOURCE QUOTATION'
QUOTE = ('TEST ONLY SYNTHETIC BALANCE TABLE (in thousands) July 31, 2026 '
         'Cash, cash equivalents, and restricted cash 1,000 900; '
         'this is an artificial transport fixture and never company financial evidence. ')


def fixture():
    fact = {'id':'fixture_balance', 'document_id':'fixture_document',
            'quote':QUOTE.replace('equivalents, and', 'equivalents and'),
            'numeric_token':'1,000', 'scale':1000, 'unit':'USD',
            'period':'2026-07-31', 'scope':'TEST ONLY synthetic fixture scope',
            'measurement_type':'balance', 'locator':'Synthetic table, current column',
            'field':'synthetic_fixture_balance'}
    packet = {'ticker':'CPRT', 'packet_hash':'a'*64, 'as_of':'2026-11-15',
              'currency':'USD', 'observations':[], 'documents':[{
                  'id':'fixture_document', 'content_hash':'b'*64,
                  'source_url':'https://example.invalid/synthetic-transport-fixture',
                  'contexts':[QUOTE]}]}
    previous = {'ticker':'CPRT', 'packet_hash':packet['packet_hash'],
                'supplemental_facts':[fact]}
    hint = {'schema_version':'underwriting-literal-source-quote/1',
            'packet_hash':packet['packet_hash'], 'document_id':'fixture_document',
            'document_hash':'b'*64, 'observation_id':'fixture_balance',
            'contract_hash':digest(previous), 'quote':QUOTE}
    return {'packet':packet, 'revision_base_hash':digest(previous),
            'revision_feedback':{'previous_contract':previous, 'literal_source_quote':hint}}


def restore_body(rendered):
    body = rendered.split('END FROZEN SOURCE QUOTATION\n',1)[-1]
    envelope = json.loads(body.splitlines()[-1])
    if str(envelope.get('schema_version','')).startswith('underwriting-transport/'):
        return transport.unpack(envelope)
    return envelope


def test_opt_in_quote_is_literal_before_complete_lossless_payload():
    payload=fixture();saved=copy.deepcopy(payload);text=transport.render(payload)
    assert text.startswith(PREFIX) and json.dumps(QUOTE,ensure_ascii=False,separators=(',',':')) in text.split('END FROZEN SOURCE QUOTATION')[0]
    assert restore_body(text)==saved and payload==saved


def test_render_does_not_accept_or_repair_the_original_invalid_author_fact():
    payload=fixture();packet=payload['packet'];fact=payload['revision_feedback']['previous_contract']['supplemental_facts'][0]
    with pytest.raises(ContractError,match='Fact quotation'):
        supplemental_observations(packet,[fact])
    transport.render(payload)
    with pytest.raises(ContractError,match='Fact quotation'):
        supplemental_observations(packet,[fact])
    assert packet['observations']==[] and 'equivalents and' in fact['quote']


@pytest.mark.parametrize('payload',[None,[],{'value':1},{'revision_feedback':{'unrelated':'unchanged'}}])
def test_no_profile_keeps_small_historical_rendering_exact(payload):
    assert transport.render(payload)==transport.encoded(payload)


def test_existing_context_key_alone_never_changes_historic_format():
    payload={'revision_feedback':{'validated_frozen_source_excerpt':'previous paid format'}}
    assert transport.render(payload)==transport.encoded(payload)


@pytest.mark.parametrize('key,value',[
 ('schema_version','unknown'),('packet_hash','c'*64),('document_hash','c'*64),
 ('document_id','other_document'),('observation_id','other_fact'),
 ('contract_hash','c'*64),('quote',None),('observation_id',1)])
def test_bad_source_identity_or_shape_fails_closed_before_packing(key,value,monkeypatch):
    payload=fixture();payload['revision_feedback']['literal_source_quote'][key]=value
    monkeypatch.setattr(transport,'_complete_layouts',lambda _:pytest.fail('Invalid hint reached packing'))
    with pytest.raises(ContractError):transport.render(payload)


def test_reference_cannot_supply_a_new_value_or_scale():
    payload=fixture();payload['revision_feedback']['literal_source_quote']['value']=9
    with pytest.raises(ContractError,match='Invalid literal source quotation reference'):
        transport.render(payload)


def test_invalid_verbatim_quote_still_uses_unchanged_source_guard():
    payload=fixture();payload['revision_feedback']['literal_source_quote']['quote']=QUOTE.replace('equivalents, and','equivalents and')
    with pytest.raises(ContractError,match='Fact quotation'):
        transport.render(payload)


@pytest.mark.parametrize('change',['stale_packet','stale_base','other_company','review_payload','duplicate_fact','duplicate_document'])
def test_cross_scope_ambiguity_and_reviewer_injection_are_rejected(change):
    payload=fixture();feedback=payload['revision_feedback'];previous=feedback['previous_contract']
    if change=='stale_packet':previous['packet_hash']='c'*64
    elif change=='stale_base':payload['revision_base_hash']='c'*64
    elif change=='other_company':payload['packet']['ticker']=previous['ticker']='OTHER'
    elif change=='review_payload':payload['contract']={}
    elif change=='duplicate_fact':previous['supplemental_facts'].append(copy.deepcopy(previous['supplemental_facts'][0]))
    else:payload['packet']['documents'].append(copy.deepcopy(payload['packet']['documents'][0]))
    if change=='duplicate_fact':
        payload['revision_base_hash']=feedback['literal_source_quote']['contract_hash']=digest(previous)
    with pytest.raises(ContractError):transport.render(payload)


@pytest.mark.parametrize('failure',['number','scale','year','future','currency','oversized'])
def test_financial_extraction_checks_are_not_weakened(failure):
    payload=fixture();previous=payload['revision_feedback']['previous_contract'];fact=previous['supplemental_facts'][0];hint=payload['revision_feedback']['literal_source_quote']
    if failure=='number':fact['numeric_token']='2,000'
    elif failure=='scale':hint['quote']=QUOTE.replace('in thousands','units unspecified')
    elif failure=='year':hint['quote']=QUOTE.replace('2026','year unspecified')
    elif failure=='future':fact['period']='2027-07-31';hint['quote']=QUOTE.replace('2026','2027')
    elif failure=='currency':fact['unit']='EUR'
    else:hint['quote']=QUOTE+'x'*8001
    payload['packet']['documents'][0]['contexts']=[hint['quote']]
    payload['revision_base_hash']=hint['contract_hash']=digest(previous)
    with pytest.raises(ContractError):transport.render(payload)


def test_literal_extra_context_counts_towards_unchanged_native_cap():
    payload=fixture();text=transport.render(payload);prefix=text.split('END FROZEN SOURCE QUOTATION\n')[0]
    assert validate_input(text)['maximum_input_characters']==1048576
    with pytest.raises(Exception,match='1048576|1,048,576|exceed|large|cap'):
        validate_input('x'*1048576+prefix)


def test_unicode_markers_and_embedded_json_remain_exact_evidence():
    payload=fixture();q=QUOTE+'Literal «3» @0 and {"schema_version":"underwriting-transport/5"}; café.'
    payload['packet']['documents'][0]['contexts']=[q]
    payload['revision_feedback']['literal_source_quote']['quote']=q
    text=transport.render(payload)
    assert restore_body(text)==payload
    line=next(x for x in text.splitlines() if x.startswith('Quotation as a literal JSON string: '))
    assert json.loads(line.split(': ',1)[1])==q
