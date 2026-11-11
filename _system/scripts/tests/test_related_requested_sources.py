"""Bounded requested legal sources for acquisition targets; synthetic issuers only."""
import hashlib
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from underwriting_evidence import requested_keywords
from underwriting_primary_references import linked_references
from underwriting_related_evidence import collect_target, merge_related_packet

BASE='https://www.sec.gov/Archives/edgar/data/123/000000012326000001/'
ANNUAL=BASE+'annual.htm'
CREDIT=BASE+'credit.htm'
CLOSING='https://www.sec.gov/Archives/edgar/data/123/000000012326000003/closing.htm'
AS_OF='2026-11-09'

def financial(extra=''):
    return ('<html><table><tr><td>Cash, debt, assets and capital. '+('Operating revenue and receivables. '*30)
            +'</td></tr></table>'+extra+'</html>').encode()

def fixture(monkeypatch, *, link=CREDIT, credit_body=None):
    import underwriting_evidence as evidence
    sub={'cik':'123','name':'Synthetic Target Inc.','filings':{'recent':{
      'form':['8-K','10-Q','10-K'],'filingDate':['2026-10-19','2026-08-01','2026-03-01'],
      'accessionNumber':['0000000123-26-000003','0000000123-26-000002','0000000123-26-000001'],
      'primaryDocument':['closing.htm','quarter.htm','annual.htm'],
      'reportDate':['2026-10-16','2026-06-30','2025-12-31'],'items':['2.01','', '']}}}
    sources={ANNUAL:financial('<a href="'+link+'">Revolving Credit and Security Agreement</a>'),
      BASE.replace('000000012326000001','000000012326000002')+'quarter.htm':financial(),
      CREDIT:credit_body or financial(),CLOSING:financial('Acquisition completed on October 16.')}
    calls=[]
    class Client:
        def get_json(self,url,**kw):
            if '/submissions/' in url:return sub
            return {'cik':123,'entityName':'Synthetic Target Inc.','facts':{'us-gaap':{
              'CashAndCashEquivalentsAtCarryingValue':{'units':{'USD':[{'val':1,'form':'10-Q',
              'filed':'2026-08-01','end':'2026-06-30','accn':'0000000123-26-000002'}]}}}}}
        def get_bytes(self,url,**kw):
            calls.append(url)
            if url not in sources:raise OSError('Offline source absent')
            return sources[url]
    monkeypatch.setattr(evidence,'filing_bytes',lambda root,t,a,client,url:client.get_bytes(url))
    return Client(),calls,sources

def test_explicit_closing_financing_survives_quoted_search_terms():
    terms=requested_keywords([{'detail':"Retrieve target closing financing and corporate debt. Search terms: 'borrowing base', 'guarantee'."}])
    assert 'closing financing' in terms and len(terms)<=18

def test_compound_security_title_is_a_credit_reference():
    refs=linked_references(financial('<a href="'+CREDIT+'">Revolving Credit and Security Agreement</a>'),
      ANNUAL,'123',['borrowing base'])
    assert [x['source_url'] for x in refs]==[CREDIT]

def test_normal_target_dispatches_requested_legal_and_closing_sources(monkeypatch,tmp_path):
    client,calls,sources=fixture(monkeypatch)
    target=collect_target(tmp_path,'TARGET','123',AS_OF,'USD',['closing financing','borrowing base'],client)
    urls={d['source_url'] for d in target['documents']}
    assert {CREDIT,CLOSING}<=urls
    assert target['latest_report']['period']=='2026-06-30'
    assert target['latest_report']['source_url'].endswith('/quarter.htm')
    assert all(d.get('period')!='2026-10-16' for d in target['documents'])
    assert target['primary_reference_usage']['counts']==[2,0]
    assert len(calls)==len(set(calls))==4


def test_no_request_preserves_the_original_financial_only_collection(monkeypatch,tmp_path):
    client,calls,_=fixture(monkeypatch)
    target=collect_target(tmp_path,'TARGET','123',AS_OF,'USD',client=client)
    assert len(target['documents'])==len(calls)==2
    assert 'primary_reference_usage' not in target

@pytest.mark.parametrize('phrase',['closing price','closing cash balance','closing remarks'])
def test_nontransaction_closing_words_do_not_add_a_financing_route(phrase):
    terms=requested_keywords([{'detail':"Retrieve "+phrase+". Search terms: 'cash', 'assets'."}])
    assert not any(x.startswith('closing ') for x in terms)

@pytest.mark.parametrize('url',[
 'https://www.sec.gov/Archives/edgar/data/999/000000012326000001/credit.htm',
 'https://attacker.test/credit.htm',
 BASE+'credit.htm?other=1',
 BASE+'../credit.htm'])
def test_compound_titles_keep_issuer_and_destination_guards(url):
    assert linked_references(financial('<a href="'+url+'">Revolving Credit and Security Agreement</a>'),
        ANNUAL,'123',['borrowing base'])==[]

def test_a_neighboring_policy_cannot_borrow_the_warehouse_title():
    raw=financial('<table><tr><td>Revolving Credit and Security Agreement '
        '<a href="policy.htm">Executive compensation retention and employment policy</a></td></tr></table>')
    assert linked_references(raw,ANNUAL,'123',['borrowing base'])==[]

def test_target_failure_retains_the_actual_source_and_consumes_capacity(monkeypatch,tmp_path):
    client,calls,_=fixture(monkeypatch)
    old=client.get_bytes
    def fetch(url,**kw):
        if url==CREDIT:
            calls.append(url);raise OSError('Isolated missing primary document')
        return old(url,**kw)
    client.get_bytes=fetch
    target=collect_target(tmp_path,'TARGET','123',AS_OF,'USD',['closing financing','borrowing base'],client)
    assert target['status']=='evidence_gap'
    assert target['primary_reference_usage']['counts']==[2,0]
    assert calls.count(CREDIT)==1
    assert any(e['source_url']==CREDIT and 'missing primary' in e['error'] for e in target['collection_errors'])

def test_target_cannot_reset_a_full_first_layer_and_uses_only_remaining_second_layer(monkeypatch,tmp_path):
    from underwriting_foreign_financials import bounded_sources,source_budget
    client,calls,_=fixture(monkeypatch)
    @bounded_sources
    def run():
        for i in range(4):source_budget().fetch('preserved-parent-'+str(i),0,lambda u:b'exact parent')
        target=collect_target(tmp_path,'TARGET','123',AS_OF,'USD',['closing financing','borrowing base'],client)
        assert target['status']=='evidence_gap'
        assert source_budget().snapshot()['counts']==[4,1]
        assert all('capacity' in e['error'] for e in target['collection_errors'])
    run()
    assert calls.count(CREDIT)==1 and CLOSING not in calls

def test_exact_bytes_are_reused_in_the_shared_scope(monkeypatch,tmp_path):
    from underwriting_foreign_financials import bounded_sources,source_budget
    client,calls,sources=fixture(monkeypatch)
    @bounded_sources
    def run():
        source_budget().fetch(CREDIT,0,lambda url:client.get_bytes(url))
        return collect_target(tmp_path,'TARGET','123',AS_OF,'USD',['closing financing','borrowing base'],client)
    target=run()
    assert calls.count(CREDIT)==1
    assert target['primary_reference_usage']['counts']==[2,0]
    assert 'collection_errors' not in target

def test_complete_context_cap_stays_unchanged_and_is_a_readiness_hold(monkeypatch,tmp_path):
    client,calls,_=fixture(monkeypatch,credit_body=financial('Cash debt assets. '*22000))
    target=collect_target(tmp_path,'TARGET','123',AS_OF,'USD',['borrowing base'],client)
    doc=next(d for d in target['documents'] if d['source_url']==CREDIT)
    assert sum(map(len,doc['contexts']))<=350000
    assert doc.get('coverage')!='complete_requested_primary_document'
    assert target['status']=='evidence_gap'
    assert any(e['source_url']==CREDIT and 'bounded context' in e['error'] for e in target['collection_errors'])

def test_related_source_errors_reach_parent_readiness(monkeypatch,tmp_path):
    from underwriting_evidence import evidence_readiness
    client,calls,_=fixture(monkeypatch,credit_body=financial('Cash debt assets. '*22000))
    target=collect_target(tmp_path,'TARGET','123',AS_OF,'USD',['borrowing base'],client)
    parent={'ticker':'PARENT','cik':'999','currency':'USD','company':'Synthetic Parent Inc.',
      'as_of':AS_OF,'financial_period':'2025-12-31','observations':[],'evidence_hash':'a'*64,
      'documents':[{'id':'parent','source_url':'https://www.sec.gov/Archives/edgar/data/999/000000099926000001/annual.htm',
      'content_hash':'b'*64,'contexts':['We completed the acquisition of Synthetic Target Inc.']}],
      'collection_errors':[{'source':'prior_parent_capture','error':'Preserved prior issue'}]}
    merged=merge_related_packet(parent,target)
    assert merged['collection_errors'][0]==parent['collection_errors'][0]
    assert any(e.get('issuer_ticker')=='TARGET' and e['source_url']==CREDIT
        for e in merged['collection_errors'][1:])
    assert any(g['code']=='requested_primary_document_unavailable' for g in evidence_readiness(merged)['gaps'])

def test_current_filing_metadata_cannot_be_fetched_after_the_as_of_date(monkeypatch,tmp_path):
    client,calls,_=fixture(monkeypatch)
    old=client.get_json
    def get(url,**kw):
        value=old(url,**kw)
        if '/submissions/' in url:value['filings']['recent']['filingDate'][0]='2026-11-10'
        return value
    client.get_json=get
    target=collect_target(tmp_path,'TARGET','123',AS_OF,'USD',['closing financing','borrowing base'],client)
    assert CLOSING not in calls
    assert target['latest_report']['period']=='2026-06-30'

def test_requested_target_collection_rejects_conflicting_official_issuer_identity(monkeypatch,tmp_path):
    client,calls,_=fixture(monkeypatch)
    old=client.get_json
    def get(url,**kw):
        value=old(url,**kw)
        if '/submissions/' in url:value['cik']='999'
        return value
    client.get_json=get
    with pytest.raises(ValueError,match='issuer'):
        collect_target(tmp_path,'TARGET','123',AS_OF,'USD',['closing financing'],client)
    assert not calls

@pytest.mark.parametrize('source',['requested_financing_discovery','requested_financing_source_budget'])
def test_financing_source_errors_cannot_be_silently_ready(source):
    from underwriting_evidence import evidence_readiness
    p={'as_of':AS_OF,'financial_period':'2025-12-31','ticker':'PARENT','observations':[],
       'documents':[],'collection_errors':[{'source':source,'error':'Held before admission'}]}
    assert any(g['code']=='requested_primary_document_unavailable' for g in evidence_readiness(p)['gaps'])

def test_explicit_exhibit_lists_preserve_all_literal_terms_within_eighteen_queries():
    detail=("Retrieve closing financing and closing consents, the corporate facilities in Exhibits 10.19/10.24 "
      "and warehouse facilities in Exhibits 10.25/10.26. Search terms: 'change of control', 'consent', "
      "'termination', 'payoff', 'early amortization event', 'eligible receivables', 'borrowing base', 'guarantee'.")
    terms=requested_keywords([{'detail':detail}])
    assert {'exhibit 10.19','exhibit 10.24','exhibit 10.25','exhibit 10.26','closing financing',
      'closing consents','change of control','consent','termination','payoff','early amortization event',
      'eligible receivables','borrowing base','guarantee'}<=set(terms)
    assert len(terms)<=18

def test_exact_exhibit_row_has_priority_over_unrequested_adjacent_amendments():
    raw=financial('<table>'+''.join('<tr><td>'+str(i)+'.1</td><td><a href="credit'+str(i)+'.htm">'
      'Revolving Credit and Security Agreement</a></td></tr>' for i in range(1,7))+'</table>')
    refs=linked_references(raw,ANNUAL,'123',['exhibit 5.1','exhibit 6.1','borrowing base'])
    assert {r['source_url'] for r in refs[:2]}=={BASE+'credit5.htm',BASE+'credit6.htm'}

def test_pending_citations_use_only_remaining_capacity_across_the_two_layers():
    from underwriting_foreign_financials import bounded_sources,source_budget
    from underwriting_primary_references import collect_requested_documents
    raw=financial('<table>'+''.join('<tr><td><a href="loan'+str(i)+'.htm">Credit Agreement</a>'
      '</td></tr>' for i in range(4))+'</table>')
    calls=[]
    @bounded_sources
    def run():
        for i in range(2):source_budget().fetch('parent-'+str(i),0,lambda u:b'prior parent')
        docs,errors=collect_requested_documents({},'123',AS_OF,
            [{'source_url':ANNUAL,'raw':raw,'filed':'2026-03-01'}],['credit'],
            lambda u:(calls.append(u) or financial()))
        assert len(docs)==4 and not errors
        assert source_budget().snapshot()['counts']==[4,2]
    run()
    assert len(set(calls))==len(calls)==4

def test_unfetched_requested_citations_stay_held_when_both_layers_are_full():
    from underwriting_foreign_financials import bounded_sources,source_budget
    from underwriting_primary_references import collect_requested_documents
    raw=financial('<a href="loan.htm">Credit Agreement</a>')
    @bounded_sources
    def run():
        for layer in (0,1):
            for i in range(4):source_budget().fetch(str(layer)+'-'+str(i),layer,lambda u:b'prior')
        docs,errors=collect_requested_documents({},'123',AS_OF,
          [{'source_url':ANNUAL,'raw':raw,'filed':'2026-03-01'}],['credit'],
          lambda u:pytest.fail('Exhausted allowance fetched more evidence'),require_all_citations=True)
        assert not docs and any('capacity' in e['error'] for e in errors)
    run()

@pytest.mark.parametrize('field,value',[('cik',999),('cik',None),('entityName','Different Parent Corporation'),('entityName',None)])
def test_current_companyfacts_identity_conflict_stays_held(monkeypatch,tmp_path,field,value):
    client,calls,_=fixture(monkeypatch)
    original=client.get_json
    def get(url,**kw):
        obj=original(url,**kw)
        if '/companyfacts/' in url:obj[field]=value
        return obj
    client.get_json=get
    with pytest.raises(ValueError,match='issuer'):
        collect_target(tmp_path,'TARGET','123',AS_OF,'USD',['closing financing','borrowing base'],client)
    assert not calls

def test_query_limit_remains_eighteen_with_many_explicit_exhibit_labels():
    detail='Retrieve Exhibits '+', '.join('10.'+str(i) for i in range(1,25))+'. Search terms: cash, debt.'
    assert len(requested_keywords([{'detail':detail}]))==18

def test_parent_ready_field_cannot_survive_unavailable_target_sources():
    from underwriting_evidence import evidence_readiness
    parent={'ticker':'PARENT','cik':'999','company':'Synthetic Parent Inc.','currency':'USD',
      'as_of':AS_OF,'financial_period':'2025-12-31','observations':[],'evidence_hash':'a'*64,
      'readiness':{'status':'ready','gaps':[]},'documents':[{'id':'parent',
      'source_url':'https://www.sec.gov/Archives/edgar/data/999/000000099926000001/annual.htm',
      'content_hash':'b'*64,'contexts':['We completed the acquisition of Synthetic Target Inc.']}]}
    target={'ticker':'TARGET','company':'Synthetic Target Inc.','cik':'123','currency':'USD',
      'observations':[],'documents':[],'source_hash':'c'*64,'evidence_hash':'d'*64,
      'collection_errors':[{'source':'requested_primary_reference','source_url':CREDIT,'error':'Required source remains held'}]}
    merged=merge_related_packet(parent,target)
    assert merged['readiness']==evidence_readiness(merged,require_documents=True)
    assert merged['readiness']['status']=='evidence_gap'
