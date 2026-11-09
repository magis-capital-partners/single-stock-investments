"""Foreign financial attachments require source identity, periods and one shared budget."""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from underwriting_foreign_financials import ReferenceBudget, collect_foreign_financials

BASE = 'https://www.sec.gov/Archives/edgar/data/123/'
def url(a, name): return BASE+a.replace('-', '')+'/'+name

def fixture():
    rows = [('6-K', '2026-11-03', '2026-11-03', '0000000123-26-000004', 'dividend.htm'),
            ('6-K', '2026-11-03', '2026-11-03', '0000000123-26-000003', 'results.htm'),
            ('40-F', '2026-03-01', '2025-12-31', '0000000123-26-000001', 'annual.htm')]
    sub = {'cik': '123', 'name': 'Test Corporation', 'filings': {'recent': {
        k: [r[i] for r in rows] for i, k in enumerate(
            ('form', 'filingDate', 'reportDate', 'accessionNumber', 'primaryDocument'))}}}
    def cover(a, labels):
        return ('<html>Test Corporation<table>'+''.join(
            '<tr><td><a href="'+name+'">'+label+'</a></td></tr>' for name,label in labels)+'</table></html>').encode()
    def financial(period):
        return ('<html>Test Corporation Consolidated Statements of Cash Flows for the year ended '+period+
          '<table><tr><td>Cash assets liabilities revenue net income equity debt</td><td>100</td><td>200</td><td>300</td></tr>'+
          '<tr><td>'+'operating financial source text '*20+'</td></tr></table></html>').encode()
    sources = {
        url(rows[0][3], 'dividend.htm'): cover(rows[0][3], [('dividend-ex99.htm', 'News release')]),
        url(rows[1][3], 'results.htm'): cover(rows[1][3], [('qfs.htm', 'Condensed consolidated financial statements for the year ended September 30, 2026'),
                                                    ('qmda.htm', 'Management discussion and analysis for the year ended September 30, 2026')]),
        url(rows[2][3], 'annual.htm'): cover(rows[2][3], [('afs.htm', 'Consolidated financial statements for the year ended December 31, 2025'),
                                                   ('amda.htm', 'Management discussion and analysis for the year ended December 31, 2025')])}
    for row,names,period in [(rows[1], ('qfs.htm','qmda.htm'), 'September 30, 2026'), (rows[2], ('afs.htm','amda.htm'), 'December 31, 2025')]:
        sources.update({url(row[3],name):financial(period) for name in names})
    return sub,sources

def run(sub,sources,budget=None):
    calls=[]
    def fetch(u):
        calls.append(u)
        if isinstance(sources[u],Exception): raise sources[u]
        return sources[u]
    docs,proof=collect_foreign_financials(sub,'123','2026-11-08',fetch,budget=budget)
    return docs,proof,calls

def test_complete_current_and_annual_sources_keep_dates_hashes_and_full_context():
    sub,s=fixture();docs,p,calls=run(sub,s)
    assert len(docs)==4 and p['status']=='complete_current_financial_sources'
    assert {d['period'] for d in docs}=={'2026-09-30','2025-12-31'}
    assert all(d['period']!=d['filed'] and d['content_hash']==hashlib.sha256(s[d['source_url']]).hexdigest() for d in docs)
    assert all(d['coverage']=='complete_requested_primary_document' and len(d['contexts'])==1 for d in docs)
    assert len(calls)==7 and p['reference_budget']['counts']==[3,4]
    assert not any('dividend-ex99' in u for u in calls)

def test_dividend_only_current_day_cannot_be_called_financial():
    sub,s=fixture();sub['filings']['recent']['filingDate'][1]='2026-08-01'
    docs,p,calls=run(sub,s)
    assert p['status']=='current_financial_sources_unresolved'
    assert all(d['form']=='40-F' for d in docs)
    assert not any('results.htm' in u or 'qfs.htm' in u for u in calls)

def test_plural_comparative_annual_title_keeps_the_explicit_latest_completed_year():
    sub,s=fixture();u=url('0000000123-26-000001','annual.htm')
    s[u]=s[u].replace(b'year ended December 31, 2025',b'years ended December 31, 2025 and 2024')
    docs,p,_=run(sub,s)
    assert p['status']=='complete_current_financial_sources'
    assert {d['period'] for d in docs if d['form']=='40-F'}=={'2025-12-31'}

def test_malformed_submissions_identity_holds_before_any_fetch():
    sub,s=fixture();sub['cik']=None;calls=[]
    with pytest.raises(ValueError,match='issuer CIK mismatch'):
        collect_foreign_financials(sub,'123','2026-11-08',lambda u:calls.append(u))
    assert not calls

@pytest.mark.parametrize('mutation', ['cross_issuer','cross_accession','query','external'])
def test_unsafe_explicit_financial_link_fails_before_attachment_fetch(mutation):
    sub,s=fixture();parent=url('0000000123-26-000003','results.htm')
    bad={'cross_issuer':'https://www.sec.gov/Archives/edgar/data/999/000000012326000003/qfs.htm',
         'cross_accession':'../000000012326000002/qfs.htm','query':'qfs.htm?raw=1',
         'external':'https://example.com/qfs.htm'}[mutation]
    s[parent]=s[parent].replace(b'qfs.htm',bad.encode())
    with pytest.raises(ValueError,match='same issuer and accession'):run(sub,s)

def test_exhibit_number_without_financial_title_is_not_a_financial_role():
    sub,s=fixture();parent=url('0000000123-26-000003','results.htm')
    s[parent]=b'<html>Test Corporation<table><tr><td><a href="qfs.htm">99.2</a></td><td>News release</td></tr></table></html>'
    docs,p,calls=run(sub,s)
    assert p['status']=='current_financial_sources_unresolved'
    assert not any('qfs.htm' in u for u in calls)

def test_source_without_financial_tables_cannot_inherit_title_period():
    sub,s=fixture();s[url('0000000123-26-000003','qfs.htm')]=b'<html>Test Corporation dividend declaration</html>'
    with pytest.raises(ValueError,match='financial statement tables'):run(sub,s)

def test_source_period_must_agree_with_its_own_explicit_exhibit_title():
    sub,s=fixture();u=url('0000000123-26-000003','qfs.htm')
    s[u]=s[u].replace(b'September 30, 2026',b'June 30, 2026')
    with pytest.raises(ValueError,match='title and source reporting periods'):run(sub,s)

def test_issuer_name_must_match_official_submissions():
    sub,s=fixture();u=url('0000000123-26-000003','qfs.htm')
    s[u]=s[u].replace(b'Test Corporation',b'Another Corporation')
    with pytest.raises(ValueError,match='issuer name'):run(sub,s)

def test_complete_context_limit_cannot_be_circumvented_by_windows():
    sub,s=fixture();u=url('0000000123-26-000003','qfs.htm')
    s[u]=s[u].replace(b'</html>',b'<p>'+b'cash operating assets '*20000+b'</p></html>')
    with pytest.raises(ValueError,match='complete bounded financial source'):run(sub,s)

def test_shared_budget_cannot_be_recreated_to_get_extra_parent_capacity():
    sub,s=fixture();budget=ReferenceBudget();outside=[]
    for i in range(3):budget.fetch('prior'+str(i),0,lambda u:outside.append(u) or b'prior')
    with pytest.raises(ValueError,match='reference capacity'):run(sub,s,budget)
    assert budget.snapshot()['counts']==[4,0]

def test_failed_fetch_still_uses_capacity_and_cannot_be_retried_without_accounting():
    budget=ReferenceBudget();calls=[]
    def fail(u):calls.append(u);raise OSError('source unavailable')
    for _ in range(2):
        with pytest.raises(OSError):budget.fetch('same',0,fail)
    assert calls==['same'] and budget.snapshot()['counts']==[1,0]

def test_budget_bounds_both_layers_and_reuses_exact_bytes():
    budget=ReferenceBudget();calls=[]
    for layer in range(2):
        for i in range(4):
            name=f'{layer}/{i}';assert budget.fetch(name,layer,lambda u:calls.append(u) or u.encode())==name.encode()
        with pytest.raises(ValueError,match='reference capacity'):budget.fetch(f'extra{layer}',layer,lambda u:b'bad')
    assert budget.fetch('0/0',0,lambda u:b'changed')==b'0/0'
    assert len(calls)==8 and budget.snapshot()['counts']==[4,4]

def test_more_current_covers_than_parent_capacity_holds_without_old_scan():
    sub,s=fixture();r=sub['filings']['recent']
    for i in range(3):
        for k,v in {'form':'6-K','filingDate':'2026-11-03','reportDate':'2026-11-03',
                    'accessionNumber':f'0000000123-26-00001{i}','primaryDocument':f'more{i}.htm'}.items():r[k].insert(0,v)
    calls=[]
    with pytest.raises(ValueError,match='current foreign covers exceed'):collect_foreign_financials(sub,'123','2026-11-08',lambda u:calls.append(u))
    assert not calls

def test_normal_fact_collector_and_next_helper_share_the_same_allowance(tmp_path, monkeypatch):
    import copy
    import autonomous_compounders as ac
    from test_autonomous_compounders import inputs
    from underwriting_foreign_financials import bounded_sources, source_budget
    sub,s=fixture();calls=[]
    class Client:
        def get_json(self,u,**kw):return sub if '/submissions/' in u else {'facts':{}}
        def get_bytes(self,u,**kw):calls.append(u);return s[u]
    client=Client();monkeypatch.setattr(ac,'_PRIMARY_SEC_CLIENT',client)
    monkeypatch.setattr(ac,'quote',lambda *a:copy.deepcopy(inputs()['quote']))
    monkeypatch.setattr(ac,'provider_facts',lambda *a:copy.deepcopy(inputs()['facts']))
    @bounded_sources
    def collection():
        result=ac.collect('TEST',{'download':{'cik':'123'}},'2026-11-08',tmp_path)
        assert result['latest_report']['period']=='2026-09-30'
        assert result['report_discovery']['status']=='verified'
        assert len(result['primary_documents'])==4
        collect_foreign_financials(sub,'123','2026-11-08',client.get_bytes)
        return source_budget().snapshot()
    assert collection()['counts']==[3,4]
    assert len(calls)==7

def test_normal_packet_collects_exact_attachments_with_original_listing_proof(tmp_path):
    from test_foreign_report_periods import root
    from underwriting_evidence import prepare_packet
    root(tmp_path);sub,s=fixture();calls=[]
    class Client:
        def get_json(self,u,**kw):return sub if '/submissions/' in u else {'facts':{}}
        def get_bytes(self,u,**kw):calls.append(u);return s[u]
    p=prepare_packet(tmp_path,'BKNG','2026-11-08',collect=False,client=Client())
    assert len(p['documents'])==4 and p['primary_reference_usage']['counts']==[3,4]
    assert p['latest_report']['period']=='2026-09-30' and p['source_discovery']['status']=='verified'
    assert p['listing_ratio']['source_url']=='https://issuer.test/verified-unit'
    assert len(calls)==7

def test_normal_refresh_and_packet_do_not_double_the_reference_budget(tmp_path,monkeypatch):
    import copy,json
    import autonomous_compounders as ac
    import refresh_shared_forecasts as refresh
    from test_foreign_report_periods import root
    from underwriting_evidence import prepare_packet
    root(tmp_path);sub,s=fixture();calls=[]
    data=json.loads((tmp_path/refresh.FUNDAMENTALS/'BKNG.json').read_text())
    quote=json.loads((tmp_path/refresh.QUOTES/'BKNG.json').read_text())['quote']
    class Client:
        def get_json(self,u,**kw):return sub if '/submissions/' in u else {'facts':{}}
        def get_bytes(self,u,**kw):calls.append(u);return s[u]
    client=Client();monkeypatch.setattr(ac,'_PRIMARY_SEC_CLIENT',client)
    monkeypatch.setattr(ac,'quote',lambda *a:copy.deepcopy(quote))
    monkeypatch.setattr(ac,'provider_facts',lambda *a:copy.deepcopy(data['facts']))
    monkeypatch.setattr(refresh,'refresh_quote',lambda *a:None)
    p=prepare_packet(tmp_path,'BKNG','2026-11-08',collect=True,client=client)
    assert len(p['documents'])==4 and p['primary_reference_usage']['counts']==[3,4]
    assert p['source_discovery']['status']=='verified' and len(calls)==7

def test_legal_helper_can_only_use_the_remaining_shared_capacity():
    from underwriting_foreign_financials import bounded_sources,source_budget
    from underwriting_primary_references import collect_requested_documents
    sub,s=fixture();calls=[]
    parent=url('0000000123-26-000001','annual.htm')
    body=b'<html>'+b'cash assets debt credit agreement '*30+b'</html>'
    extras={url('0000000123-26-000001',n):body for n in ('loan.htm','loan2.htm')}
    def fetch(u):calls.append(u);return {**s,**extras}[u]
    @bounded_sources
    def collection():
        collect_foreign_financials(sub,'123','2026-11-08',fetch)
        docs,errors=collect_requested_documents(sub,'123','2026-11-08',[{'source_url':parent,'filed':'2026-03-01',
          'raw':b'<table><tr><td><a href="loan.htm">Credit Agreement</a></td></tr><tr><td><a href="loan2.htm">Credit Agreement</a></td></tr></table>'}],['credit agreement'],fetch)
        assert len(docs)==1 and errors
        return source_budget().snapshot()
    assert collection()['counts']==[4,4] and len(calls)==8

def test_consumed_parent_allowance_prevents_a_target_from_getting_another_eight(tmp_path):
    from underwriting_foreign_financials import bounded_sources,source_budget
    from underwriting_related_evidence import collect_target
    sub,s=fixture();calls=[]
    class Client:
        def get_json(self,u,**kw):return sub if '/submissions/' in u else {'facts':{}}
        def get_bytes(self,u,**kw):calls.append(u);return s[u]
    @bounded_sources
    def collection():
        source_budget().resume({'counts':[4,4],'urls_by_layer':[[f'p{i}' for i in range(4)],[f'c{i}' for i in range(4)]]})
        with pytest.raises(ValueError,match='reference capacity'):
            collect_target(tmp_path,'TARGET','123','2026-11-08','USD',client=Client())
    collection();assert not calls

def test_related_issuer_uses_the_same_verified_attachment_periods(tmp_path):
    from underwriting_related_evidence import collect_target
    sub,s=fixture();calls=[]
    class Client:
        def get_json(self,u,**kw):
            if '/submissions/' in u:return sub
            return {'entityName':'Test Corporation','facts':{'us-gaap':{
              'CashAndCashEquivalentsAtCarryingValue':{'units':{'USD':[{'val':1,'form':'6-K',
                'filed':'2026-11-03','end':'2026-09-30','accn':'0000000123-26-000003'}]}}}}}
        def get_bytes(self,u,**kw):calls.append(u);return s[u]
    target=collect_target(tmp_path,'TARGET','123','2026-11-08','USD',client=Client())
    assert len(target['documents'])==4 and len(calls)==7
    assert target['latest_report']['period']=='2026-09-30'
    assert all(o['unit']=='USD' and o['source_kind']=='primary' for o in target['observations'])

def test_collection_scope_is_released_after_failure_and_between_companies():
    from underwriting_foreign_financials import bounded_sources,source_budget
    from concurrent.futures import ThreadPoolExecutor
    @bounded_sources
    def collection(fail):
        for i in range(4):source_budget().fetch(str(i),0,lambda u:u.encode())
        if fail:raise OSError('isolated collection failure')
        return source_budget().snapshot()['counts']
    with pytest.raises(OSError):collection(True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(collection,[False,False]))==[[4,0],[4,0]]
    with pytest.raises(ValueError,match='collection scope'):source_budget()

def test_foreign_cover_bytes_cannot_come_from_another_member_of_the_accession(tmp_path,monkeypatch):
    import underwriting_evidence as evidence
    from test_foreign_report_periods import root
    root(tmp_path);sub,s=fixture()
    class Client:
        def get_json(self,u,**kw):return sub if '/submissions/' in u else {'facts':{}}
        def get_bytes(self,u,**kw):return s[u]
    def ambiguous_archive(*a):raise AssertionError('Accession-only archive lookup cannot verify this exact foreign URL')
    monkeypatch.setattr(evidence,'filing_bytes',ambiguous_archive)
    packet=evidence.prepare_packet(tmp_path,'BKNG','2026-11-08',collect=False,client=Client())
    assert len(packet['documents'])==4 and packet['latest_report']['period']=='2026-09-30'
