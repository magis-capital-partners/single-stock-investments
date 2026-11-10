"""Management commentary needs matching complete statements and its own period."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_foreign_financial_attachments import fixture,run,url
from valuation_earnings import foreign_reporting_period
from underwriting_evidence import text_of,primary_text


def mda(period='September 30, 2026',heading=True,table=True):
    h=("Management's Discussion and Analysis of Results of Operations for the three and nine months ended "+period) if heading else 'Financial discussion'
    t=('<table><tr><td>Cash assets liabilities revenue net income equity debt</td><td>100</td><td>200</td><td>300</td></tr><tr><td>'+('operating financial source text '*20)+'</td></tr></table>') if table else ''
    return ('<html>Test Corporation '+h+t+'</html>').encode()


def test_matching_complete_statements_allow_a_separate_management_report_without_calling_it_statements():
    sub,s=fixture();key=url('0000000123-26-000003','qmda.htm');s[key]=mda()
    with pytest.raises(ValueError,match='financial statement tables'):foreign_reporting_period(s[key],'2026-11-08')
    docs,p,calls=run(sub,s)
    assert p['status']=='complete_current_financial_sources' and p['reference_budget']['counts']==[3,4]
    d=next(d for d in docs if d['source_url']==key)
    assert d['financial_role']=='management_discussion' and d['period']=='2026-09-30'
    assert d['contexts']==[text_of(primary_text(s[key]))]
    binding=d['financial_statement_period_binding']
    assert binding['source_url']==url('0000000123-26-000003','qfs.htm')
    assert binding['period']=='2026-09-30' and binding['content_hash']


def test_explicit_ampersand_management_title_stays_a_management_role():
    sub,s=fixture();a=url('0000000123-26-000001','annual.htm')
    s[a]=s[a].replace(b'Management discussion and analysis',b'Management discussion &amp; analysis')
    docs,p,_=run(sub,s)
    assert p['status']=='complete_current_financial_sources'
    assert any(d['source_url'].endswith('/amda.htm') and d['financial_role']=='management_discussion' for d in docs)


@pytest.mark.parametrize('change',['no_statement','wrong_own_period','missing_heading','no_table'])
def test_management_metadata_cannot_replace_missing_mismatched_or_nonfinancial_primary_evidence(change):
    sub,s=fixture();p=url('0000000123-26-000003','results.htm');d=url('0000000123-26-000003','qmda.htm')
    s[d]=mda('June 30, 2026' if change=='wrong_own_period' else 'September 30, 2026',heading=change!='missing_heading',table=change!='no_table')
    if change=='no_statement':
        s[p]=s[p].replace(b'<tr><td><a href="qfs.htm">Condensed consolidated financial statements for the year ended September 30, 2026</a></td></tr>',b'')
    with pytest.raises(ValueError):run(sub,s)


def test_management_report_cannot_borrow_statements_from_another_accession():
    sub,s=fixture();q=url('0000000123-26-000003','results.htm');qdoc=url('0000000123-26-000003','qmda.htm')
    s[qdoc]=mda();s[q]=s[q].replace(b'qfs.htm',b'../000000012326000002/qfs.htm')
    with pytest.raises(ValueError,match='same issuer and accession'):run(sub,s)


def test_explicit_period_ended_title_matches_the_independent_statement_period():
    sub,s=fixture();p=url('0000000123-26-000003','results.htm')
    s[p]=s[p].replace(b'for the year ended',b'for the period ended')
    docs,proof,_=run(sub,s)
    assert proof['status']=='complete_current_financial_sources'
    assert {d['period'] for d in docs if d['form']=='6-K'}=={'2026-09-30'}


@pytest.mark.parametrize('grammar', ['years ended', 'YEARS ENDED', 'years \n ended'])
def test_plural_completed_years_in_management_opening_bind_to_same_filing_statements(grammar):
    sub, sources = fixture()
    key = url('0000000123-26-000001', 'amda.htm')
    source = mda('December 31, 2025')
    original = b'Management\'s Discussion and Analysis of Results of Operations for the three and nine months ended December 31, 2025'
    opening = ("Management's Discussion and Analysis This MD&A was prepared as at March 10, 2026 "
               "and should be read with the audited financial statements as at and for the "
               + grammar + " December 31, 2025 and 2024.")
    sources[key] = source.replace(original, opening.encode())
    assert sources[key] != source
    with pytest.raises(ValueError, match='financial statement tables'):
        foreign_reporting_period(sources[key], '2026-11-08')
    documents, proof, calls = run(sub, sources)
    management = next(d for d in documents if d['source_url'] == key)
    assert management['period'] == '2025-12-31'
    assert management['contexts'] == [text_of(primary_text(sources[key]))]
    assert management['financial_statement_period_binding']['source_url'] == url('0000000123-26-000001', 'afs.htm')
    assert management['financial_statement_period_binding']['period'] == '2025-12-31'
    assert proof['status'] == 'complete_current_financial_sources'
    assert proof['reference_budget']['counts'] == [3, 4]
    assert len(calls) == len(set(calls))


@pytest.mark.parametrize('opening', [
    "Management's Discussion and Analysis for the years ended December 31, 2024 and 2023.",
    "Management's Discussion and Analysis for the years ended December 31, 2027 and 2026.",
    "Management's Discussion and Analysis prepared as at March 10, 2026.",
    "Management's Discussion and Analysis 2025 Annual Report.",
    "Management's Discussion and Analysis for the years ending December 31, 2025 and 2024.",
    "Management's Discussion and Analysis " + ('unchanged source window ' * 80)
    + "for the years ended December 31, 2025 and 2024.",
])
def test_plural_management_period_does_not_borrow_metadata_or_extend_the_source_window(opening):
    sub, sources = fixture()
    key = url('0000000123-26-000001', 'amda.htm')
    original = b'Management\'s Discussion and Analysis of Results of Operations for the three and nine months ended December 31, 2025'
    sources[key] = mda('December 31, 2025').replace(original, opening.encode())
    with pytest.raises(ValueError, match='Management title, own source period'):
        run(sub, sources)
