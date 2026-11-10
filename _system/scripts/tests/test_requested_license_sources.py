"""Named primary license instruments retain their literal request and source identity."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from underwriting_evidence import requested_keywords
from underwriting_primary_references import linked_references,collect_requested_documents
PARENT='https://www.sec.gov/Archives/edgar/data/1374310/000137431026000001/quarter.htm'
def row(title,href='license.htm',number='10.1'):
 return ('<tr><td>'+number+'</td><td><a href="'+href+'">'+title+'</a></td></tr>').encode()
@pytest.mark.parametrize('verb',['Retrieve','Obtain','Provide','Include','Supply'])
def test_explicit_master_license_and_order_list_precede_clause_searches(verb):
 terms=requested_keywords([{'detail':verb+" the Master License Agreement and Orders 1-1 and 2-1. Search 'effective date', 'royalty', 'license fee'."}])
 assert terms[:3]==['master license agreement','order 1-1','order 2-1']and len(terms)<=18
@pytest.mark.parametrize('detail',[
 "The Master License Agreement is already present. Search: 'royalty'.",
 "Search: 'royalty'. Retrieve the Master License Agreement and Orders 1-1 and 2-1.",
 "Retrieve https://issuer.test/Master-License-Agreement/Orders-1-1. Search: 'royalty'.",
 "Master License Agreement was discussed. Obtain only current figures. Search: 'royalty'.",
])
def test_unrequested_search_tail_and_url_mentions_do_not_supply_license_queries(detail):
 assert 'master license agreement'not in requested_keywords([{'detail':detail}])
def test_named_master_and_only_requested_orders_bind_to_own_primary_title():
 raw=row('Master License Agreement, dated September 28, 2026')+row('Order No. 1-1 to the Master License Agreement, dated September 28, 2026','one.htm','10.2')+row('Order No. 2-1 to the Master License Agreement, dated September 28, 2026','two.htm','10.3')
 refs=linked_references(raw,PARENT,1374310,['master license agreement','order 1-1'])
 assert {r['source_url'].rsplit('/',1)[-1]for r in refs}=={'license.htm','one.htm'}
 assert all(r['referenced_by']['source_url']==PARENT for r in refs)
@pytest.mark.parametrize('terms',[['royalty'],['license fee'],['effective date'],['exhibit 10.1'],['master licensing agreement'],['https://issuer.test/master license agreement']])
def test_generic_terms_or_exhibit_numbers_do_not_classify_license_sources(terms):
 assert linked_references(row('Master License Agreement, dated September 28, 2026'),PARENT,1374310,terms)==[]
@pytest.mark.parametrize('href',['https://evil.test/license.htm','https://www.sec.gov/Archives/edgar/data/999/000000099926000001/license.htm','../license.htm','license.htm?borrowed=true'])
def test_license_request_keeps_issuer_and_path_guards(href):
 assert linked_references(row('Master License Agreement, dated September 28, 2026',href),PARENT,1374310,['master license agreement'])==[]
@pytest.mark.parametrize('title',['Annual disclosure mentions Master License Agreement','Order No. 1-10 to the Master License Agreement','Order No. 2-1 to an unrelated agreement'])
def test_incidental_mentions_other_orders_and_other_agreements_do_not_match(title):
 assert linked_references(row(title),PARENT,1374310,['master license agreement','order 1-1'])==[]
def test_neighboring_legal_title_cannot_classify_unrelated_long_anchor():
 raw=b'<tr><td>Master License Agreement</td><td><a href="policy.htm">Employee policy and administration handbook</a></td></tr>'
 assert linked_references(raw,PARENT,1374310,['master license agreement'])==[]
def _collect(count,fail=False):
 from underwriting_foreign_financials import bounded_sources,source_budget
 raw=b''.join(row('Order No. 1-'+str(i)+' to the Master License Agreement, dated September 28, 2026','order-'+str(i)+'.htm','10.'+str(i))for i in range(1,count+1));calls=[]
 def fetch(url):
  calls.append(url)
  if fail:raise OSError('Preserved source failure')
  number=url.rsplit('order-',1)[1].split('.',1)[0]
  return ('EXECUTION COPY THIS Order No. 1-'+number+' by and between Alpha and Beta under the Master License Agreement. '+ 'Complete operative legal language. '*40+' IN WITNESS WHEREOF /s/ Jane Smith /s/ John Doe.').encode()
 @bounded_sources
 def run():
  docs,errors=collect_requested_documents({},1374310,'2026-11-10',[{'source_url':PARENT,'raw':raw,'filed':'2026-10-30'}],['master license agreement']+['order 1-'+str(i)for i in range(1,count+1)],fetch)
  return docs,errors,source_budget().snapshot()
 return run(),calls
def test_required_unfetched_license_citations_hold_at_existing_shared_capacity():
 (docs,errors,budget),calls=_collect(10)
 assert len(calls)==len(set(calls))==len(docs)==8 and budget['counts']==[4,4]
 assert len(errors)==2 and all('shared reference capacity'in e['error']for e in errors)
@pytest.mark.parametrize('failed',[False,True])
def test_license_sources_keep_complete_document_and_failure_readiness_gates(failed):
 from underwriting_evidence import evidence_readiness
 from test_underwriting_pipeline import packet
 (docs,errors,budget),calls=_collect(1,failed)
 assert len(calls)==1 and budget['counts']==[1,0]
 if failed:
  assert not docs and len(errors)==1;p=packet();p['collection_errors']=errors;assert evidence_readiness(p)['status']=='evidence_gap'
 else:assert len(docs)==1 and not errors and docs[0]['coverage']=='complete_requested_primary_document'

def test_source_own_license_title_survives_short_exhibit_anchor_and_marks():
 raw=b'<tr><td><a href="license.htm">10.1</a></td><td>10.1 +* Master License Agreement, dated September 28, 2026</td></tr>'
 assert len(linked_references(raw,PARENT,1374310,['master license agreement']))==1
def test_comma_separated_order_identifiers_are_literal_not_a_range():
 terms=requested_keywords([{'detail':"Retrieve Master License Agreement and Orders 1-1, 3-1. Search terms: 'royalty'."}])
 assert terms[:3]==['master license agreement','order 1-1','order 3-1']and 'order 2-1'not in terms
def test_policy_title_extending_the_contract_name_is_not_the_named_instrument():
 assert linked_references(row('Master License Agreement policy and administration overview'),PARENT,1374310,['master license agreement'])==[]
