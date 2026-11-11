"""The complete package boundary and operative-document routing stay fail closed."""
import copy,hashlib,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from underwriting_primary_packages import metadata,package_url,documents,operative_references,validate_operative_member

CIK='1637873';ACC='0000950103-26-013780';URL=package_url(CIK,ACC)
META={'accession':ACC,'form':'8-K','filed':'2026-09-10','primary_document':'primary.htm','name':'ACV Auctions Inc.','cik':CIK}
SPEC={**META,'required_members':{'legal.htm':'EX-10.1'}}
REQUIRED={'legal.htm':'EX-10.1'}
def body(title):return ('<html><table><tr><td>Cash debt capital assets and liabilities. '*8+'</td></tr></table><p>'+title+' Financial cash debt assets and capital. '*35+'</p></html>').encode()
def block(kind,name,seq,text):return b'<DOCUMENT>\n<TYPE>'+kind.encode()+b'\n<SEQUENCE>'+str(seq).encode()+b'\n<FILENAME>'+name.encode()+b'\n<TEXT>\n'+text+b'\n</TEXT>\n</DOCUMENT>\n'
def raw():
    header=f'<SEC-DOCUMENT>{ACC}.txt\n<SEC-HEADER>\nACCESSION NUMBER: {ACC}\nCONFORMED SUBMISSION TYPE: 8-K\nFILED AS OF DATE: 20260910\nCENTRAL INDEX KEY: {CIK}\nCOMPANY CONFORMED NAME: ACV Auctions Inc.\nPUBLIC DOCUMENT COUNT: 2\n</SEC-HEADER>\n'.encode()
    return header+block('8-K','primary.htm',1,body('Primary report'))+block('EX-10.1','legal.htm',2,body('Credit Agreement'))+b'</SEC-DOCUMENT>'
def submissions():return {'cik':CIK,'name':'ACV Auctions Inc.','filings':{'recent':{'accessionNumber':[ACC],'form':['8-K'],'filingDate':['2026-09-10'],'primaryDocument':['primary.htm']}}}

def test_complete_package_preserves_every_selected_member_text_and_package_identity():
    source=raw();records,parents=documents(URL,source,CIK,META,REQUIRED)
    assert len(records)==len(parents)==2
    for record,parent in zip(records,parents):
        from underwriting_evidence import text_of,primary_text
        assert record['contexts']==[text_of(primary_text(parent['raw']))]
        assert record['content_hash']==hashlib.sha256(source).hexdigest()
        assert record['submission_document']['embedded_text_sha256']==hashlib.sha256(parent['raw']).hexdigest()
        assert record['source_url']==URL
        assert 'period' not in record

@pytest.mark.parametrize('old,new',[(b'PUBLIC DOCUMENT COUNT: 2',b'PUBLIC DOCUMENT COUNT: 3'),(b'CENTRAL INDEX KEY: 1637873',b'CENTRAL INDEX KEY: 900075'),(b'COMPANY CONFORMED NAME: ACV Auctions Inc.',b'COMPANY CONFORMED NAME: COPART INC'),(b'CONFORMED SUBMISSION TYPE: 8-K',b'CONFORMED SUBMISSION TYPE: 10-Q'),(b'FILED AS OF DATE: 20260910',b'FILED AS OF DATE: 20260911'),(b'<SEQUENCE>2',b'<SEQUENCE>1'),(b'<FILENAME>legal.htm',b'<FILENAME>primary.htm'),(b'<FILENAME>legal.htm',b'<FILENAME>../legal.htm'),(b'</SEC-DOCUMENT>',b''),(b'</DOCUMENT>',b'')])
def test_incomplete_conflicting_or_unsafe_package_is_rejected(old,new):
    with pytest.raises(ValueError):documents(URL,raw().replace(old,new),CIK,META,REQUIRED)

def test_package_url_cannot_borrow_another_issuer():
    with pytest.raises(ValueError):documents(URL.replace('/1637873/','/900075/'),raw(),CIK,META,REQUIRED)

def test_required_member_is_not_satisfied_by_another_exhibit_type():
    with pytest.raises(ValueError):documents(URL,raw().replace(b'<TYPE>EX-10.1',b'<TYPE>EX-99.1'),CIK,META,REQUIRED)

@pytest.mark.parametrize('key,value',[('cik','900075'),('primaryDocument',['other.htm']),('filingDate',['2026-09-11']),('form',['10-Q'])])
def test_package_selection_requires_exact_current_official_submissions(key,value):
    sub=submissions()
    if key=='cik':sub[key]=value
    else:sub['filings']['recent'][key]=value
    with pytest.raises(ValueError):metadata(sub,CIK,SPEC)

def test_registry_instrument_needs_title_in_already_collected_same_filing_source():
    parent='https://www.sec.gov/Archives/edgar/data/1637873/000162828024035701/warehouse.htm';child=parent.rsplit('/',1)[0]+'/guaranty.htm'
    profile={'target_cik':CIK,'target_reference_urls':[child],'required_operative_references':[{'source_url':child,'source_parent_url':parent,'title':'Performance Guaranty'}]}
    with pytest.raises(ValueError,match='title'):operative_references([{'source_url':parent,'raw':b'<html>No governing title</html>'}],CIK,profile)
    references=operative_references([{'source_url':parent,'raw':b'<html>Performance Guaranty</html>'}],CIK,profile)
    assert references[0]['source_url']==child
    profile['required_operative_references'][0]['source_url']=child.replace('000162828024035701','000162828024035702');profile['target_reference_urls']=[profile['required_operative_references'][0]['source_url']]
    with pytest.raises(ValueError,match='issuer/accession'):operative_references([{'source_url':parent,'raw':b'<html>Performance Guaranty</html>'}],CIK,profile)

@pytest.mark.parametrize('text',['Performance Guaranty June 21, 2024 ACV Citibank','Credit Agreement June 20, 2024 ACV Citibank','Performance Guaranty June 20, 2024 Other Lender'])
def test_operative_member_own_identity_cannot_be_borrowed_from_parent(text):
    with pytest.raises(ValueError):validate_operative_member(text.encode(),{'title':'Performance Guaranty'})
