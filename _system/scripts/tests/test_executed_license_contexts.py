"""Complete executed requested license contexts preserve all original text and guards."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from underwriting_evidence import document_record,text_of
URL='https://www.sec.gov/Archives/edgar/data/1374310/000110465926111989/license.htm'
FOCUS=['master license agreement','order 1-1']
def source(kind='order'):
    title=('THIS Master License Agreement' if kind=='master' else 'THIS Order No. 1-1')
    return ('EXECUTION COPY '+title+' is entered into by and between Alpha and Beta. '
            'The parties refer to the Master License Agreement. 1. Interpretation. '
            + 'The operative licensed rights and obligations remain stated here. '*30
            + ' Fees [***]. IN WITNESS WHEREOF Alpha By: /s/ Jane Smith Beta By: /s/ John Doe.').encode()
@pytest.mark.parametrize('kind',['master','order'])
def test_complete_requested_executed_license_without_financial_tables_is_retained_verbatim(kind):
    raw=source(kind);doc=document_record(URL,raw,FOCUS,prefer_complete=True,expected_license_title='master license agreement' if kind=='master' else 'order 1-1')
    assert doc['coverage']=='complete_requested_primary_document'
    assert doc['contexts']==[text_of(raw.decode())] and '[***]'in doc['contexts'][0]
@pytest.mark.parametrize('remove',['EXECUTION COPY','IN WITNESS WHEREOF','/s/ Jane Smith','between','Master License Agreement'])
def test_execution_and_self_identification_are_required_for_complete_legal_capture(remove):
    raw=source().replace(remove.encode(),b'')
    if remove.startswith('/s/'):raw=raw.replace(b'/s/ John Doe',b'')
    with pytest.raises(ValueError):
        document_record(URL,raw,FOCUS,prefer_complete=True,expected_license_title='order 1-1')
@pytest.mark.parametrize('focus',[[],['royalty'],['order 1-1'],['master license agreement','order 2-1']])
def test_no_missing_master_or_unrequested_order_can_enable_complete_legal_capture(focus):
    try:doc=document_record(URL,source(),focus,prefer_complete=True,expected_license_title='order 1-1')
    except ValueError:return
    assert doc.get('coverage')!='complete_requested_primary_document'
def test_license_capture_cannot_supply_a_financial_report_role():
    try:doc=document_record(URL,source(),FOCUS,form='10-Q',prefer_complete=True,expected_license_title='order 1-1')
    except ValueError:return
    assert doc.get('coverage')not in('complete_requested_primary_document','complete_quarterly_filing')
def test_legal_capture_requires_prefer_complete_and_the_same_complete_context_cap():
    try:doc=document_record(URL,source(),FOCUS,prefer_complete=False,expected_license_title='order 1-1')
    except ValueError:doc={}
    assert doc.get('coverage')!='complete_requested_primary_document'
    try:doc=document_record(URL,source()+b' Extra operative words.'*20000,FOCUS,prefer_complete=True,expected_license_title='order 1-1')
    except ValueError:return
    assert doc.get('coverage')!='complete_requested_primary_document'
def test_a_late_title_cannot_borrow_an_opening_source_identity():
    raw=b'Unrelated report. '*120+source()
    with pytest.raises(ValueError):
        document_record(URL,raw,FOCUS,prefer_complete=True,expected_license_title='order 1-1')
def test_incomplete_requested_license_source_reaches_existing_readiness_hold():
    from underwriting_primary_references import collect_requested_documents
    from underwriting_foreign_financials import bounded_sources,source_budget
    from underwriting_evidence import evidence_readiness
    from test_underwriting_pipeline import packet
    parent='https://www.sec.gov/Archives/edgar/data/1374310/000110465926111989/parent.htm'
    raw=b'<a href="license.htm">Master License Agreement, dated September 28, 2026</a>'
    @bounded_sources
    def run():
        docs,errors=collect_requested_documents({},1374310,'2026-11-10',[{'source_url':parent,'raw':raw,'filed':'2026-09-29'}],FOCUS,lambda u:b'<p>Master License Agreement '+b'Operative legal language. '*50+b'</p>')
        return docs,errors,source_budget().snapshot()
    docs,errors,budget=run();assert not docs and len(errors)==1 and budget['counts']==[1,0]
    p=packet();p['collection_errors']=errors;assert evidence_readiness(p)['status']=='evidence_gap'

@pytest.mark.parametrize('expected',['master license agreement','order 2-1'])
def test_source_own_referenced_title_cannot_borrow_another_requested_instrument(expected):
    raw=source()+b' Cash debt and assets.'
    with pytest.raises(ValueError):
        document_record(URL,raw,FOCUS+['order 2-1'],prefer_complete=True,expected_license_title=expected)
