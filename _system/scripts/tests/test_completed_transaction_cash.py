"""Executed transaction cash flows from complete primary disclosures; synthetic issuers."""
import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from underwriting_related_evidence import merge_related_packet

TEXT=('Synthetic Target Inc., a Delaware corporation (“ Target ”), entered into a merger agreement with '
      'Synthetic Parent Inc., a Delaware corporation (“ Parent ”), and Step Sub Inc., a Delaware corporation '
      'and a wholly owned subsidiary of Parent (“ Merger Sub ”). '
      'Item 2.01. Completion of Acquisition or Disposition of Assets. '
      'The remaining conditions were satisfied, and on October 16, 2026, Merger Sub merged with and into Target '
      '(the “ Merger ”), with Target continuing as the surviving corporation and a wholly owned subsidiary of Parent. '
      'The Merger was completed pursuant to Section 251(h). '
      'Item 5.01. Changes in Control of Registrant. '
      'The aggregate consideration paid by Parent and Merger Sub in connection with the acquisition of control of '
      'Target was approximately $123,456.00, which Parent funded from cash on hand and available cash resources.')

def case():
 parent={'ticker':'PARENT','company':'Synthetic Parent Inc.','cik':'999','currency':'USD','as_of':'2026-11-13',
   'financial_period':'2025-12-31','latest_report':{'period':'2025-12-31'},'evidence_hash':'a'*64,
   'observations':[{'id':'shares','unit':'shares','value':100,'period':'2025-12-31','source_kind':'primary'}],
   'documents':[{'id':'parent','source_url':'https://www.sec.gov/Archives/edgar/data/999/000000099926000001/annual.htm',
     'form':'10-K','period':'2025-12-31','content_hash':'b'*64,
     'contexts':['We completed the acquisition of Synthetic Target Inc.']} ]}
 doc={'id':'closing','source_url':'https://www.sec.gov/Archives/edgar/data/123/000000012326000003/closing.htm',
   'accession':'0000000123-26-000003','form':'8-K','filed':'2026-10-19','content_hash':'c'*64,
   'document_kind':'material_transaction_disclosure','coverage':'complete_requested_primary_document',
   'registered_securities':[{'issuer_cik':'123','symbol':'TARGET'}],'contexts':[TEXT]}
 target={'ticker':'TARGET','company':'Synthetic Target Inc.','cik':'123','currency':'USD',
   'as_of':parent['as_of'],'latest_report':{'period':'2026-06-30'},'evidence_hash':'d'*64,
   'source_hash':'e'*64,'observations':[],'documents':[doc]}
 return parent,target

def flows(result):
 return [o for o in result['observations'] if o.get('field')=='completed_acquisition_cash_consideration_paid']

def test_normal_related_merge_binds_completed_parent_payment_without_changing_report_periods():
 parent,target=case();saved=copy.deepcopy((parent,target));result=merge_related_packet(parent,target)
 point,=flows(result)
 assert point['value']==123456 and point['unit']=='USD' and point['measurement_type']=='flow'
 assert point['period']=='2026-10-19' and point['transaction_completion_date']=='2026-10-16' and point['payment_date'] is None and point['payer_ticker']=='PARENT' and point['source_issuer_ticker']=='TARGET'
 assert point.get('issuer_ticker') in (None,'PARENT')
 assert point['document_hash']=='c'*64 and point['source_url']==target['documents'][0]['source_url']
 assert point['reported_approximate'] is True
 assert result['financial_period']==parent['financial_period'] and result['latest_report']==parent['latest_report']
 assert result['related_issuers']['TARGET']['latest_report']==target['latest_report']
 assert (parent,target)==saved
 assert all(d.get('period')!='2026-10-16' for d in result['documents'])

@pytest.mark.parametrize('old,new',[
 ('paid by Parent','expected to be paid by Parent'),
 ('paid by Parent','received by Parent'),
 ('which Parent funded','which Parent expects to fund'),
 ('Merger Sub merged with and into Target','Merger Sub will merge with and into Target'),
 ('Synthetic Parent Inc., a Delaware corporation','Another Parent Inc., a Delaware corporation'),
 ('Synthetic Target Inc., a Delaware corporation','Another Target Inc., a Delaware corporation'),
 ('$123,456.00','123,456 shares'),
 ('$123,456.00','$123,456.00 per share'),
 ('and on October 16, 2026','and if on October 16, 2026'),
 ('on October 16, 2026','on February 30, 2026'),
])
def test_unexecuted_other_party_non_cash_or_ambiguous_disclosures_create_no_payment(old,new):
 parent,target=case();target['documents'][0]['contexts']=[TEXT.replace(old,new)]
 assert flows(merge_related_packet(parent,target))==[]

@pytest.mark.parametrize('change',[
 {'coverage':'requested_primary_context_only'},{'form':'6-K'},
 {'document_kind':'generic_news_release'},{'content_hash':'bad'},
 {'filed':'2026-11-14'},{'filed':'2026-10-15'},
 {'accession':'0000000123-26-000004'},
 {'source_url':'https://www.sec.gov/Archives/edgar/data/999/000000012326000003/closing.htm'},
 {'source_url':'https://attacker.test/Archives/edgar/data/123/000000012326000003/closing.htm'},
 {'source_url':'https://www.sec.gov/Archives/edgar/data/123/000000012326000003/closing.htm?alternate=1'},
 {'registered_securities':[{'issuer_cik':'999','symbol':'TARGET'}]},
])
def test_primary_identity_availability_and_complete_context_are_required(change):
 parent,target=case();target['documents'][0].update(change)
 assert flows(merge_related_packet(parent,target))==[]

def test_shared_currency_without_a_verified_usd_basis_is_not_converted():
 parent,target=case();parent['currency']=target['currency']='EUR'
 assert flows(merge_related_packet(parent,target))==[]


@pytest.mark.parametrize('edit',[
 lambda p,t:t['documents'][0].update(contexts=[TEXT+' '+TEXT]),
 lambda p,t:t['documents'].append(copy.deepcopy(t['documents'][0])),
 lambda p,t:t['documents'][0].update(contexts=[TEXT,TEXT]),
 lambda p,t:p['latest_report'].update(period='2026-10-31'),
 lambda p,t:t['documents'][0].update(registered_securities=[]),
])
def test_duplicates_partial_sources_and_pre_baseline_payments_are_not_added(edit):
 parent,target=case();edit(parent,target)
 assert flows(merge_related_packet(parent,target))==[]

def test_existing_primary_documents_and_observations_are_preserved_exactly():
 parent,target=case();result=merge_related_packet(parent,target)
 assert result['documents'][:-1]==parent['documents']
 assert result['documents'][-1]=={**target['documents'][0],'issuer_ticker':'TARGET'}
 assert result['observations'][0]==parent['observations'][0]
 point,=flows(result)
 assert point['source_quote'] in TEXT and point['completion_quote'] in TEXT
 assert point['payer_identity_quote'] in TEXT and point['target_identity_quote'] in TEXT
 assert 'not total acquisition funding or a liability cap' in point['claim_scope']
 assert point['payment_date'] is None

def test_exact_paid_integer_and_nonapproximate_wording_are_preserved():
 parent,target=case();target['documents'][0]['contexts']=[TEXT.replace('approximately $123,456.00','$123456')]
 point,=flows(merge_related_packet(parent,target))
 assert point['value']==123456 and point['reported_approximate'] is False and point['numeric_token']=='123456'

def test_unresolved_requested_payment_stops_before_judgment_but_other_requests_do_not_change():
 from underwriting_related_evidence import _require_requested_transaction_cash
 parent,target=case();missing=merge_related_packet(parent,{**target,'documents':[]})
 assert _require_requested_transaction_cash(copy.deepcopy(missing),[{'code':'other_request'}])==missing
 held=_require_requested_transaction_cash(missing,[{'code':'unbound_post_baseline_acquisition_cash_payment'}])
 assert held['readiness']['status']=='evidence_gap'
 assert any(g['code']=='requested_primary_document_unavailable' for g in held['readiness']['gaps'])
 ready=merge_related_packet(*case());before=copy.deepcopy(ready)
 assert _require_requested_transaction_cash(ready,[{'code':'unbound_post_baseline_acquisition_cash_payment'}])==before

def test_requested_payment_rejects_stale_or_misattributed_bound_source():
 from underwriting_related_evidence import _require_requested_transaction_cash
 for key,value in [('document_hash','f'*64),('payer_ticker','ANOTHER')]:
  packet=merge_related_packet(*case());flows(packet)[0][key]=value
  held=_require_requested_transaction_cash(packet,[{'code':'unbound_post_baseline_acquisition_cash_payment'}])
  assert held['readiness']['status']=='evidence_gap'


def test_a_sentence_ending_with_an_item_reference_does_not_end_its_own_section():
 parent,target=case()
 target['documents'][0]['contexts']=[TEXT.replace('The aggregate consideration',
   'The information is incorporated into this Item 5.01. As a result of the consummation, control changed. The aggregate consideration')]
 assert len(flows(merge_related_packet(parent,target)))==1

def test_consideration_in_another_real_item_cannot_be_borrowed():
 parent,target=case()
 target['documents'][0]['contexts']=[TEXT.replace('The aggregate consideration',
   'Item 5.02. Departure of Directors or Certain Officers. The aggregate consideration')]
 assert flows(merge_related_packet(parent,target))==[]


def test_an_unrecognized_different_item_still_ends_the_payment_section():
 parent,target=case()
 target['documents'][0]['contexts']=[TEXT.replace('The aggregate consideration',
   'Item 4.02. Non-Reliance on Previously Issued Financial Statements. The aggregate consideration')]
 assert flows(merge_related_packet(parent,target))==[]

def test_accession_format_cannot_be_borrowed_from_compact_url_digits():
 parent,target=case();target['documents'][0]['accession']='000000012326000003'
 assert flows(merge_related_packet(parent,target))==[]


@pytest.mark.parametrize('prefix',['For illustration only: ','A hypothetical example follows: ','If the offer had closed: '])
def test_hypothetical_payment_cannot_borrow_a_completed_transaction(prefix):
 parent,target=case();target['documents'][0]['contexts']=[TEXT.replace('The aggregate consideration',prefix+'The aggregate consideration')]
 assert flows(merge_related_packet(parent,target))==[]
