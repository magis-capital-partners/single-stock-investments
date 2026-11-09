"""Unlinked, explicitly titled financial exhibits bind to their official index."""
import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_foreign_financial_attachments import fixture, url, run
from underwriting_foreign_financials import ReferenceBudget

ACC='0000000123-26-000003'
INDEX=url(ACC,ACC+'-index.html')

def index_fixture():
    sub,sources=fixture()
    sources[url(ACC,'results.htm')]=(
        '<html>Test Corporation Exhibit 99.1 Consolidated financial statements for the year ended September 30, 2026. '
        'Exhibit 99.2 Management discussion and analysis for the year ended September 30, 2026. SIGNATURE</html>').encode()
    source=('<html><title>EDGAR Filing Documents for '+ACC+'</title>Form 6-K '
        'SEC Accession No. '+ACC+' Filing Date 2026-11-03 Test Corporation CIK : 0000000123 '
        '<table><tr><td>1</td><td>Cover</td><td><a href="results.htm">results.htm</a></td><td>6-K</td><td>1000</td></tr>'
        '<tr><td>2</td><td>EX-99.1</td><td><a href="qfs.htm">qfs.htm</a></td><td>EX-99.1</td><td>1000</td></tr>'
        '<tr><td>3</td><td>EX-99.2</td><td><a href="qmda.htm">qmda.htm</a></td><td>EX-99.2</td><td>1000</td></tr>'
        '</table></html>')
    sources[INDEX]=source.encode()
    return sub,sources

def test_unlinked_explicit_financial_exhibits_use_one_shared_parent_slot():
    sub,s=index_fixture();docs,proof,calls=run(sub,s)
    assert proof['status']=='complete_current_financial_sources'
    assert len(docs)==4 and len(calls)==8 and len(set(calls))==8
    assert proof['reference_budget']['counts']==[4,4]
    child=next(d for d in docs if d['source_url']==url(ACC,'qfs.htm'))
    assert child['referenced_by']['source_url']==INDEX
    assert child['cover_referenced_by']['source_url']==url(ACC,'results.htm')
    assert child['period']=='2026-09-30' and child['filed']=='2026-11-03'
    assert child['coverage']=='complete_requested_primary_document'

def test_internal_financial_navigation_is_not_an_external_attachment_candidate():
    sub,s=fixture();annual=url('0000000123-26-000001','annual.htm')
    s[annual]=s[annual].replace(b'<table>',b'<a href="#statements">Consolidated financial statements for the year ended December 31, 2025</a><table>',1)
    docs,proof,calls=run(sub,s)
    assert proof['status']=='complete_current_financial_sources' and len(docs)==4
    assert len(calls)==7

@pytest.mark.parametrize('target',['qfs.htm#part','annual.htm?raw=1#statements','https://bad.test/annual.htm#statements'])
def test_fragment_exception_never_applies_to_other_documents_queries_or_hosts(target):
    sub,s=fixture();annual=url('0000000123-26-000001','annual.htm')
    s[annual]=s[annual].replace(b'<table>',('<a href="'+target+'">Consolidated financial statements for the year ended December 31, 2025</a><table>').encode(),1)
    with pytest.raises(ValueError,match='same issuer and accession'):run(sub,s)

def test_explicit_interim_report_survives_as_a_complete_source_but_not_an_annual_pair():
    sub,s=index_fixture();cover=url(ACC,'results.htm')
    sub['filings']['recent']['form']=sub['filings']['recent']['form'][:2]
    s[cover]=b'<html>Test Corporation Exhibit 99.1 Test Corporation Interim Report for the three months ended September 30, 2026. SIGNATURE</html>'
    s[INDEX]=s[INDEX].replace(b'<tr><td>3</td><td>EX-99.2</td><td><a href="qmda.htm">qmda.htm</a></td><td>EX-99.2</td><td>1000</td></tr>',b'')
    docs,proof,calls=run(sub,s)
    assert len(docs)==1 and docs[0]['financial_role']=='financial_report'
    assert docs[0]['period']=='2026-09-30'
    assert proof['status']=='current_financial_sources_unresolved'

@pytest.mark.parametrize('title',['Press release dated November 3, 2026','News release','Dividend declaration','99.1'])
def test_generic_cover_titles_never_trigger_index_financial_discovery(title):
    sub,s=index_fixture();s[url(ACC,'results.htm')]=('<html>Test Corporation Exhibit 99.1 '+title+'. SIGNATURE</html>').encode()
    docs,proof,calls=run(sub,s)
    assert INDEX not in calls and proof['status']=='current_financial_sources_unresolved'
    assert len(docs)==2

@pytest.mark.parametrize('old,new',[
    ('CIK : 0000000123','CIK : 0000000999'),
    ('Form 6-K','Form 8-K'),
    ('SEC Accession No. '+ACC,'SEC Accession No. 0000000123-26-000002'),
    ('Filing Date 2026-11-03','Filing Date 2026-11-04'),
    ('Test Corporation','Other Corporation'),
    ('<td>EX-99.1</td><td>1000','<td>EX-99.3</td><td>1000'),
    ('href="qfs.htm"','href="https://www.sec.gov/Archives/edgar/data/999/000000012326000003/qfs.htm"'),
])
def test_official_index_must_match_the_cover_identity_form_date_and_exhibit(old,new):
    sub,s=index_fixture();assert old.encode() in s[INDEX];s[INDEX]=s[INDEX].replace(old.encode(),new.encode())
    with pytest.raises(ValueError):run(sub,s)

def test_duplicate_index_member_type_cannot_choose_between_exhibits():
    sub,s=index_fixture();s[INDEX]=s[INDEX].replace(b'</table>',b'<tr><td>4</td><td>Other</td><td><a href="other.htm">other.htm</a></td><td>EX-99.1</td><td>100</td></tr></table>')
    with pytest.raises(ValueError):run(sub,s)

def test_unlinked_financial_title_cannot_override_the_source_statement_table_guard():
    sub,s=index_fixture();s[url(ACC,'qfs.htm')]=b'<html>Test Corporation Dividend declaration for September 30, 2026.</html>'
    with pytest.raises(ValueError,match='financial statement tables'):run(sub,s)

def test_an_index_uses_existing_shared_capacity_instead_of_a_new_allowance():
    sub,s=index_fixture();budget=ReferenceBudget();budget.fetch('prior',0,lambda u:b'prior')
    with pytest.raises(ValueError,match='reference capacity'):run(sub,s,budget)
    assert budget.snapshot()['counts']==[4,0]

def test_repeated_helpers_reuse_exact_index_and_child_bytes_without_extra_capacity():
    from underwriting_foreign_financials import collect_foreign_financials
    sub,s=index_fixture();budget=ReferenceBudget();calls=[]
    def fetch(u):calls.append(u);return s[u]
    first=collect_foreign_financials(sub,'123','2026-11-08',fetch,budget=budget)
    second=collect_foreign_financials(sub,'123','2026-11-08',fetch,budget=budget)
    assert first==second and len(calls)==8 and budget.snapshot()['counts']==[4,4]


@pytest.mark.parametrize('title',[
    'Insider Trading Policy incorporated by reference to the Annual Report on Form 20-F',
    'Recovery Policy incorporated by reference to the Annual Report on Form 20-F',
    'Annual Report on Form 20-F filed last year',
])
def test_generic_report_citations_are_not_financial_attachment_titles(title):
    from underwriting_foreign_financials import _financial_links
    parent={'source_url':url('0000000123-26-000001','annual.htm')}
    raw=('<a href="https://www.sec.gov/Archives/edgar/data/123/000000012325000001/policy.htm">'+title+'</a>').encode()
    assert _financial_links(raw,parent,'123')==[]


@pytest.mark.parametrize('old,new',[
    ('href="results.htm"','href="another-cover.htm"'),
    ('<td>6-K</td><td>1000','<td>OTHER</td><td>1000'),
    ('href="qmda.htm">qmda.htm','href="qfs.htm">qfs.htm'),
])
def test_selected_index_members_bind_the_exact_primary_cover_and_unique_files(old,new):
    sub,s=index_fixture();assert old.encode() in s[INDEX];s[INDEX]=s[INDEX].replace(old.encode(),new.encode())
    with pytest.raises(ValueError):run(sub,s)
