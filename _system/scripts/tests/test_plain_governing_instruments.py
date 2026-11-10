"""Explicit plain governing instruments survive bounded quoted search requests."""
import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from underwriting_evidence import requested_keywords
from underwriting_primary_references import linked_references

@pytest.mark.parametrize('verb',['Retrieve','Obtain','Provide','Include','Supply'])
def test_plain_governing_and_supplemental_requests_survive_quoted_searches(verb):
    gap={'detail':verb+" default and rescission terms from the governing indenture and applicable supplemental indentures. Search: 'cross-acceleration', 'notice'."}
    terms=requested_keywords([gap])
    assert terms[:2]==['indenture','supplemental indenture']
    assert {'cross-acceleration','notice'}<=set(terms)

@pytest.mark.parametrize('name,expected',[
    ('base indenture','base indenture'),
    ('supplemental indentures','supplemental indenture'),
])
def test_qualified_plain_instrument_names_keep_their_literal_identity(name,expected):
    assert expected in requested_keywords([{'detail':
        'Retrieve the '+name+". Search terms: 'payment'."}])

@pytest.mark.parametrize('detail',[
    "The governing indenture is already supplied. Search terms: 'payment'.",
    "Search terms: 'payment'. Retrieve the governing indenture later.",
    "Retrieve https://issuer.test/governing/indenture. Search terms: 'payment'.",
    "A base indenture was discussed. Obtain only current figures. Search terms: 'payment'.",
])
def test_unrequested_or_search_tail_mentions_do_not_become_plain_instrument_queries(detail):
    terms=requested_keywords([{'detail':detail}])
    assert not {'indenture','base indenture','supplemental indenture'}&set(terms)

def test_current_plain_instruments_keep_the_same_global_limit_and_paid_history():
    current=[{'detail':"Retrieve governing indenture and supplemental indentures. Search: 'notice', 'rescission'."}]
    history=[{'detail':f"Retrieve {year} Senior Notes. Search: 'credit agreement'."}for year in range(2000,2012)]
    saved=copy.deepcopy(history);terms=requested_keywords(current,history=history)
    assert terms[:2]==['indenture','supplemental indenture']and len(terms)<=18
    assert len(terms)==len(set(terms))and history==saved

def test_plain_request_reaches_existing_issuer_bound_indentures_without_widening_roles():
    parent='https://www.sec.gov/Archives/edgar/data/1408198/000140819826000011/annual.htm'
    raw=('<table><tr><td>4.1</td><td><a href="base.htm">Indenture dated January 1, 2020</a></td></tr>'
         '<tr><td>4.2</td><td><a href="supplement.htm">Supplemental Indenture dated January 2, 2020</a></td></tr>'
         '<tr><td>4.3</td><td><a href="https://evil.test/indenture.htm">Indenture</a></td></tr>'
         '<tr><td>4.4</td><td><a href="https://www.sec.gov/Archives/edgar/data/999/000000099926000001/foreign.htm">Indenture</a></td></tr>'
         '<tr><td>4.5</td><td><a href="annual.htm">Form 10-K</a></td></tr></table>').encode()
    terms=requested_keywords([{'detail':
        "Retrieve governing indenture and supplemental indentures. Search: 'cross-acceleration', 'notice'."}])
    refs=linked_references(raw,parent,'1408198',terms)
    assert {Path(r['source_url']).name for r in refs}=={'base.htm','supplement.htm'}
    assert all(r['referenced_by']['source_url']==parent for r in refs)


def _collect_counted_references(count):
    from underwriting_primary_references import collect_requested_documents
    from underwriting_foreign_financials import bounded_sources,source_budget
    parent='https://www.sec.gov/Archives/edgar/data/1408198/000140819826000011/annual.htm'
    raw=''.join(f'<a href="note-{i}.htm">Indenture dated January {i+1}, 2020</a>'for i in range(count)).encode()
    calls=[]
    def fetch(url):
        calls.append(url);return ('<p>Cash, debt, capital and assets. '+('Operative notice and payment language. '*40)+'</p>').encode()
    terms=requested_keywords([{'detail':"Retrieve the governing indenture and supplemental indentures. Search: 'notice'."}])
    @bounded_sources
    def run():
        documents,errors=collect_requested_documents({},'1408198','2026-11-10',
            [{'source_url':parent,'raw':raw,'filed':'2026-02-01'}],terms,fetch)
        return documents,errors,source_budget().snapshot()
    documents,errors,budget=run()
    return documents,errors,budget,calls

def test_unfetched_explicit_governing_citations_remain_held_at_the_same_shared_capacity():
    documents,errors,budget,calls=_collect_counted_references(10)
    assert len(calls)==len(set(calls))==len(documents)==8 and budget['counts']==[4,4]
    assert len(errors)==2
    assert all(e['source']=='requested_primary_reference'and 'shared reference capacity'in e['error']for e in errors)

def test_unfetched_governing_citations_reach_the_existing_pre_admission_readiness_gate():
    from underwriting_evidence import evidence_readiness
    from test_underwriting_pipeline import packet
    _,errors,_,_=_collect_counted_references(10);p=packet();p['collection_errors']=errors
    readiness=evidence_readiness(p)
    assert readiness['status']=='evidence_gap'
    assert sum(g['code']=='requested_primary_document_unavailable'for g in readiness['gaps'])==2

def test_a_complete_bounded_governing_source_graph_does_not_create_a_capacity_hold():
    documents,errors,budget,calls=_collect_counted_references(3)
    assert len(documents)==len(calls)==3 and budget['counts']==[3,0]and not errors
