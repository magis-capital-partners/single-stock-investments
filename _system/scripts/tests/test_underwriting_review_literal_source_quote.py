"""CPRT review quote presentation; synthetic fixtures never supply issuer facts."""
import copy
import json
import pytest
from test_underwriting_literal_source_quote import fixture, QUOTE
import underwriting_transport as transport
from underwriting_contract import ContractError,digest
from underwriting_codex import validate_input


def review_fixture():
    old=fixture();contract=old['revision_feedback']['previous_contract']
    contract['supplemental_facts'][0]['quote']=QUOTE
    diagnostics={'synthetic_fixture':True}
    return {'packet':old['packet'],'contract':contract,'contract_hash':digest(contract),
            'deterministic_value_driver_tests':diagnostics,'diagnostics_hash':digest(diagnostics)}


def test_review_shows_verified_full_quote_and_bound_contract_without_changing_payload():
    payload=review_fixture();saved=copy.deepcopy(payload);text=transport.render(payload)
    assert text.startswith('FROZEN CONTRACT SOURCE QUOTATION')
    assert 'Contract SHA-256: '+payload['contract_hash'] in text
    assert transport.encoded(QUOTE) in text.split('END FROZEN CONTRACT SOURCE QUOTATION')[0]
    body=text.split('END FROZEN CONTRACT SOURCE QUOTATION\n')[-1]
    envelope=json.loads(body.splitlines()[-1])
    restored=transport.unpack(envelope) if str(envelope.get('schema_version','')).startswith('underwriting-transport/') else envelope
    assert restored==saved and payload==saved


def test_author_displays_only_the_already_verified_revision_base_identity():
    payload=fixture();text=transport.render(payload)
    assert 'Revision base contract SHA-256: '+payload['revision_base_hash'] in text
    assert 'Document SHA-256: '+payload['revision_feedback']['literal_source_quote']['document_hash'] in text


@pytest.mark.parametrize('change',['contract_hash','packet_hash','source_hash','duplicate_source','duplicate_fact','quote','year','scale','number','currency','diagnostics_hash','extra_author_feedback'])
def test_review_quote_identity_and_existing_financial_guards_fail_closed(change,monkeypatch):
    payload=review_fixture();fact=payload['contract']['supplemental_facts'][0]
    if change=='contract_hash':payload['contract_hash']='c'*64
    elif change=='packet_hash':payload['contract']['packet_hash']='c'*64
    elif change=='source_hash':payload['packet']['documents'][0]['content_hash']='invalid'
    elif change=='duplicate_source':payload['packet']['documents'].append(copy.deepcopy(payload['packet']['documents'][0]))
    elif change=='duplicate_fact':payload['contract']['supplemental_facts'].append(copy.deepcopy(fact))
    elif change=='quote':fact['quote']=QUOTE.replace('equivalents, and','equivalents and')
    elif change=='year':fact['quote']=QUOTE.replace('2026','year unspecified');payload['packet']['documents'][0]['contexts']=[fact['quote']]
    elif change=='scale':fact['quote']=QUOTE.replace('in thousands','scale unspecified');payload['packet']['documents'][0]['contexts']=[fact['quote']]
    elif change=='number':fact['numeric_token']='2,000'
    elif change=='currency':fact['unit']='EUR'
    elif change=='diagnostics_hash':payload['diagnostics_hash']='c'*64
    else:payload['revision_feedback']={'untrusted_fixture':True}
    if change!='contract_hash':payload['contract_hash']=digest(payload['contract'])
    monkeypatch.setattr(transport,'_complete_layouts',lambda _:pytest.fail('Invalid review quote reached packing'))
    with pytest.raises(ContractError):transport.render(payload)


@pytest.mark.parametrize('payload',[{'value':'unchanged'},None,[],{'contract':{'ticker':'OTHER'},'packet':{'ticker':'OTHER'}},{'contract':{'ticker':'CPRT','supplemental_facts':[]},'packet':{'ticker':'CPRT'}}])
def test_non_profile_and_no_quote_payloads_keep_old_small_encoding(payload):
    assert transport.render(payload)==transport.encoded(payload)


def test_review_literal_prefix_counts_against_same_native_cap():
    payload=review_fixture();text=transport.render(payload)
    assert validate_input(text)['maximum_input_characters']==1048576
    with pytest.raises(Exception):validate_input('x'*1048576+text)


def test_review_literal_quote_preserves_unicode_and_encoded_marker_lookalikes():
    payload=review_fixture();quote=QUOTE.rstrip()+' Literal ^~ @0 «3» café {"key":"value"}.'
    payload['contract']['supplemental_facts'][0]['quote']=quote
    payload['packet']['documents'][0]['contexts']=[quote]
    payload['contract_hash']=digest(payload['contract'])
    text=transport.render(payload)
    line=next(row for row in text.splitlines() if row.startswith('Quotation as a literal JSON string: '))
    assert json.loads(line.split(': ',1)[1])==quote


def test_complete_review_fast_path_retains_literal_quote_and_exact_full_payload(monkeypatch):
    import underwriting_token_transport as tokens
    from test_underwriting_token_transport import example
    original,envelope=example();profile=review_fixture();original.update(profile);envelope['payload'].update(copy.deepcopy(profile));envelope['payload_hash']=digest(original)
    monkeypatch.setattr(tokens,'eligible',lambda _:True);monkeypatch.setattr(tokens,'pack',lambda _:copy.deepcopy(envelope))
    monkeypatch.setattr(transport,'render',lambda _:pytest.fail('Fitting complete request used fallback'))
    text=transport.render_for_budget(original,1000000)
    assert text.startswith('FROZEN CONTRACT SOURCE QUOTATION')
    restored=transport.unpack(json.loads(text[text.index('{"schema_version":'):]))
    assert transport.encoded(restored)==transport.encoded(original)


def test_review_fast_path_counts_literal_prefix_before_accepting_complete_budget(monkeypatch):
    import underwriting_token_transport as tokens
    from test_underwriting_token_transport import example
    original,envelope=example();profile=review_fixture();original.update(profile);envelope['payload'].update(copy.deepcopy(profile));envelope['payload_hash']=digest(original)
    monkeypatch.setattr(tokens,'eligible',lambda _:True);monkeypatch.setattr(tokens,'pack',lambda _:copy.deepcopy(envelope))
    complete=transport.render_for_budget(original,1000000)
    prefix=transport._literal_review_source_quote_prefix(original)
    monkeypatch.setattr(transport,'render',lambda _:'unchanged full fallback')
    assert transport.render_for_budget(original,len(complete)-len(prefix))=='unchanged full fallback'
