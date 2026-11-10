"""Explicit amending-agreement names bind only their own primary exhibit row."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from underwriting_primary_references import linked_references
PARENT='https://www.sec.gov/Archives/edgar/data/16875/000001687526000033/quarter.htm'
def link(name='Second Amending Agreement',href='amendment.htm'):
    return ('<table><tr><td>10.1</td><td><a href="'+href+'">'+name+', dated as of July 6, 2026, among Borrower, Covenantor, Administrative Agent and Lenders</a></td></tr></table>').encode()
@pytest.mark.parametrize('ordinal',['First','Second','Third','Fourteenth'])
def test_explicit_named_amending_agreement_routes_its_own_primary_exhibit(ordinal):
    refs=linked_references(link(ordinal+' Amending Agreement'),PARENT,16875,[ordinal.lower()+' amending agreement'])
    assert len(refs)==1 and refs[0]['source_url']==PARENT.rsplit('/',1)[0]+'/amendment.htm'
    assert refs[0]['referenced_by']['source_url']==PARENT
@pytest.mark.parametrize('terms',[['credit agreement'],['third amending agreement'],['second amending agreements'],['https://issuer.test/second amending agreement'],['xsecond amending agreement']])
def test_unrequested_different_plural_or_url_labels_do_not_supply_the_legal_title(terms):
    assert linked_references(link(),PARENT,16875,terms)==[]
@pytest.mark.parametrize('href',['https://evil.test/amendment.htm','https://www.sec.gov/Archives/edgar/data/999/000000099926000001/amendment.htm','../amendment.htm','amendment.htm?borrowed=true'])
def test_requested_name_keeps_existing_destination_and_issuer_guards(href):
    assert linked_references(link(href=href),PARENT,16875,['second amending agreement'])==[]
def test_neighboring_named_amendment_cannot_classify_an_unrelated_long_anchor():
    raw=b'<table><tr><td>Second Amending Agreement</td><td><a href="policy.htm">Employee pension policy and administration notice</a></td></tr></table>'
    assert linked_references(raw,PARENT,16875,['second amending agreement'])==[]
def test_explicit_name_from_normal_request_reaches_current_exhibit_before_generic_debt():
    from underwriting_evidence import requested_keywords
    terms=requested_keywords([{'detail':"Retrieve the July 6, 2026 amendment. Search: 'Financial Covenant', 'Second Amending Agreement'."}])
    raw=link()+b'<a href="old.htm">Credit Agreement dated January 1, 2024</a>'
    refs=linked_references(raw,PARENT,16875,terms)
    assert refs and refs[0]['source_url'].endswith('/amendment.htm') and len(terms)<=18

@pytest.mark.parametrize('failed',[False,True])
def test_named_amendment_uses_existing_complete_document_and_readiness_gates(failed):
    import hashlib
    from underwriting_primary_references import collect_requested_documents
    from underwriting_foreign_financials import bounded_sources,source_budget
    from underwriting_evidence import evidence_readiness,text_of
    from test_underwriting_pipeline import packet
    calls=[]
    raw=b'<p>Cash, debt, capital and assets. '+b'Operative borrowing conditions and payment language. '*40+b'</p>'
    def fetch(url):
        calls.append(url)
        if failed:raise OSError('Preserved source failure')
        return raw
    @bounded_sources
    def collect():
        docs,errors=collect_requested_documents({},16875,'2026-11-10',[{'source_url':PARENT,'raw':link(),'filed':'2026-10-29'}],['second amending agreement'],fetch)
        return docs,errors,source_budget().snapshot()
    docs,errors,budget=collect()
    assert len(calls)==1 and budget['counts']==[1,0]
    if failed:
        assert not docs and len(errors)==1 and errors[0]['source']=='requested_primary_reference'
        p=packet();p['collection_errors']=errors
        assert evidence_readiness(p)['status']=='evidence_gap'
    else:
        assert not errors and len(docs)==1
        assert docs[0]['content_hash']==hashlib.sha256(raw).hexdigest()
        assert docs[0]['contexts']==[text_of(raw.decode("utf-8"))] and docs[0]['coverage']=='complete_requested_primary_document'
