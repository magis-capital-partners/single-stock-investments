"""Filing-owned related-issuer monetary observations; synthetic primary identities only."""
import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from underwriting_related_evidence import collect_target
import underwriting_evidence as ev
CIK='123';NAME='Synthetic Target Inc.';DAY='2026-11-11'
URL='https://www.sec.gov/Archives/edgar/data/123/000000012326000001/quarter.htm'
def filing(*,name=NAME,cik='0000000123',period='2026-06-30',form='10-Q',entity='0000000123',unit='iso4217:USD',dimension='',fmt='ixt:num-dot-decimal',extra=''):
 return (f'''<html xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:dei="http://xbrl.sec.gov/dei/2025" xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:iso4217="http://www.xbrl.org/2003/iso4217"><ix:header><xbrli:context id="c1"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">{entity}</xbrli:identifier>{dimension}</xbrli:entity><xbrli:period><xbrli:instant>{period}</xbrli:instant></xbrli:period></xbrli:context><xbrli:unit id="usd"><xbrli:measure>{unit}</xbrli:measure></xbrli:unit><ix:nonNumeric name="dei:EntityRegistrantName" contextRef="c1">{name}</ix:nonNumeric><ix:nonNumeric name="dei:EntityCentralIndexKey" contextRef="c1">{cik}</ix:nonNumeric><ix:nonNumeric name="dei:DocumentPeriodEndDate" contextRef="c1">{period}</ix:nonNumeric><ix:nonNumeric name="dei:DocumentType" contextRef="c1">{form}</ix:nonNumeric></ix:header><table><tr><td>Cash debt assets liabilities capital operating revenue receivables. '''+('Financial assets and liabilities. '*30)+f'''</td><td><ix:nonFraction name="us-gaap:Assets" id="f1" contextRef="c1" unitRef="usd" scale="3" format="{fmt}">1,234</ix:nonFraction><ix:nonFraction name="us-gaap:CashAndCashEquivalentsAtCarryingValue" id="f2" contextRef="c1" unitRef="usd" scale="3" format="{fmt}">234</ix:nonFraction><ix:nonFraction name="us-gaap:Liabilities" id="f3" contextRef="c1" unitRef="usd" scale="3" format="{fmt}">1,000</ix:nonFraction>{extra}</td></tr></table></html>''').encode()
def client(monkeypatch,body=None):
 monkeypatch.setattr(ev,'filing_bytes',lambda root,t,a,c,u:c.get_bytes(u))
 class C:
  def __init__(self):self.calls=[]
  def get_json(self,u,**kw):
   self.calls.append(u)
   if '/companyfacts/' in u:return {'cik':123,'entityName':'Different Parent Inc.','facts':{}}
   return {'cik':'123','name':NAME,'filings':{'recent':{'form':['10-Q'],'filingDate':['2026-08-01'],'accessionNumber':['0000000123-26-000001'],'primaryDocument':['quarter.htm'],'reportDate':['2026-06-30']}}}
  def get_bytes(self,u,**kw):self.calls.append(u);assert u==URL;return body or filing()
 return C()
def run(tmp_path,c):return collect_target(tmp_path,'TARGET',CIK,DAY,'USD',['assets'],c,fact_source='filing_inline')
def test_filing_source_uses_only_own_verified_identity_and_facts(monkeypatch,tmp_path):
 c=client(monkeypatch);target=run(tmp_path,c)
 assert not any('/companyfacts/' in u for u in c.calls)
 assert {o['field']:o['value'] for o in target['observations']}=={'Assets':1234000,'CashAndCashEquivalentsAtCarryingValue':234000,'Liabilities':1000000}
 assert all(o['source_url']==URL and o['document_hash']==target['documents'][0]['content_hash'] for o in target['observations'])
 assert target['facts_provenance']['method']=='filing_inline'
 assert target['latest_report']['period']=='2026-06-30'
def test_default_api_identity_conflict_still_rejected(monkeypatch,tmp_path):
 c=client(monkeypatch)
 with pytest.raises(ValueError,match='names disagree'):collect_target(tmp_path,'TARGET',CIK,DAY,'USD',['assets'],c)
 assert URL not in c.calls
@pytest.mark.parametrize('changes',[
 {'name':'Different Issuer Inc.'},{'cik':'999'},{'entity':'999'},{'period':'2026-09-30'},
 {'form':'10-K'},{'unit':'iso4217:EUR'},{'unit':'evil:USD'},
 {'dimension':'<xbrli:segment><xbrldi:explicitMember dimension="A">B</xbrldi:explicitMember></xbrli:segment>'},
 {'fmt':'ixt:unknown-transform'}])
def test_filing_source_rejects_conflicting_identity_period_unit_or_scope(monkeypatch,tmp_path,changes):
 c=client(monkeypatch,filing(**changes))
 with pytest.raises(ValueError):run(tmp_path,c)
def test_invalid_source_mode_fails_before_network(monkeypatch,tmp_path):
 c=client(monkeypatch)
 with pytest.raises(ValueError):collect_target(tmp_path,'TARGET',CIK,DAY,'USD',['assets'],c,fact_source='unchecked')
 assert not c.calls

def test_nested_annual_date_keeps_full_outer_period(monkeypatch,tmp_path):
 body=filing().replace(b'>2026-06-30</ix:nonNumeric>',b'><ix:nonNumeric name="dei:CurrentFiscalYearEndDate" contextRef="c1">June 30</ix:nonNumeric>, 2026</ix:nonNumeric>')
 c=client(monkeypatch,body);assert run(tmp_path,c)['latest_report']['period']=='2026-06-30'

def test_filing_mode_requires_exact_parent_and_cik_policy(tmp_path):
 import json
 from underwriting_related_evidence import related_fact_source
 p=tmp_path/'_system/config/underwriting_policy.json';p.parent.mkdir(parents=True)
 p.write_text(json.dumps({'related_fact_sources':{'PARENT':{'123':'filing_inline'}}}))
 assert related_fact_source(tmp_path,'PARENT','000123')=='filing_inline'
 assert related_fact_source(tmp_path,'OTHER','123')=='companyfacts'
 assert related_fact_source(tmp_path,'PARENT','999')=='companyfacts'
def test_unknown_configured_source_mode_is_rejected(tmp_path):
 import json
 from underwriting_related_evidence import related_fact_source
 p=tmp_path/'_system/config/underwriting_policy.json';p.parent.mkdir(parents=True)
 p.write_text(json.dumps({'related_fact_sources':{'PARENT':{'123':'unchecked'}}}))
 with pytest.raises(ValueError):related_fact_source(tmp_path,'PARENT','123')
