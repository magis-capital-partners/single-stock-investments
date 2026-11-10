"""Explicit percentage search tokens retain literal queries, not invented sections."""
import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from underwriting_evidence import requested_keywords, document_record

@pytest.mark.parametrize('prefix', [
    'The coupon range is 2.620%–3.680%.',
    'Interest rates range from 2.620 % to 3.680 %.',
    'The disclosed rate range is 2.620%—3.680%.',
])
def test_literal_percentage_searches_do_not_become_legal_sections(prefix):
    gap={'detail':prefix+' Search terms: “2.620”, “3.680”, “Guaranteed Senior Notes”.'}
    saved=copy.deepcopy(gap)
    terms=requested_keywords([gap])
    assert terms==['2.620','3.680','guaranteed senior notes']
    assert gap==saved

@pytest.mark.parametrize('prefix', [
    'No percentage appears in this request.',
    'The reported percentage is 12.620%.',
    'The reported percentage is 2.6200%.',
    'The unrelated URL is https://issuer.test/2.620%.',
])
def test_unbound_decimal_searches_keep_the_existing_section_behavior(prefix):
    terms=requested_keywords([{'detail':prefix+" Search terms: '2.620'."}])
    assert terms==['section 2.620']

def test_an_explicit_section_prefix_stays_a_section_even_when_a_percentage_matches():
    terms=requested_keywords([{'detail':
        "A rate of 2.620% is disclosed. Search terms: 'Section 2.620'."}])
    assert terms==['section 2.620']

def test_explicit_section_lists_and_matching_percentage_queries_both_survive():
    terms=requested_keywords([{'detail':
        "Retrieve Section 2.620 and the 2.620% coupon disclosure. Search terms: '2.620'."}])
    assert terms==['section 2.620','2.620']

def test_percentages_after_the_search_list_do_not_reclassify_earlier_queries():
    terms=requested_keywords([{'detail':
        "Search terms: '2.620'. A later sentence reports 2.620%."}])
    assert terms==['section 2.620']

def test_literal_percentage_searches_keep_the_same_global_query_limit_and_history():
    current=[{'detail':"Disclosed rate 2.620%. Search terms: '2.620', 'principal'."}]
    history=[{'detail':f"Search terms: 'historical term {i}'."}for i in range(12)]
    saved=copy.deepcopy(history)
    terms=requested_keywords(current,history=history)
    assert terms[:2]==['2.620','principal'] and len(terms)<=18
    assert len(terms)==len(set(terms)) and history==saved

def test_literal_rate_query_reaches_its_exact_primary_document_context():
    raw=('<html><table><tr><td>Cash and debt, assets and liabilities; annual capital and operating amounts 100, 200 and 300.</td></tr></table>'
         +'<p>Unrelated filing disclosure.</p>'*1300
         +'<p>The individual note coupon is 2.620 % and payment terms follow.</p>'
         +'<p>Unrelated later filing disclosure.</p>'*1300+'</html>').encode()
    terms=requested_keywords([{'detail':
        "The request identifies 2.620%. Search terms: '2.620'."}])
    doc=document_record('https://issuer.test/annual',raw,terms,form='10-K')
    assert any('individual note coupon is 2.620 % and payment terms follow' in c for c in doc['contexts'])


def test_literal_percentage_focus_cannot_promote_a_nonfinancial_table():
    raw=('<html><table><tr><td>'+('An unrelated label 2.620 % in a table. '*6)+'</td></tr></table></html>').encode()
    from underwriting_contract import ContractError
    with pytest.raises(ContractError,match='No financial tables'):
        document_record('https://issuer.test/annual',raw,['2.620'],form='10-K')

def test_a_section_number_cannot_replace_the_requested_source_percentage_occurrence():
    raw=('<html><table><tr><td>Cash and debt, assets and liabilities; annual capital and operating amounts 100, 200 and 300.</td></tr></table>'
         +'<p>Section 2.620 contains contractual text.</p>'
         +'<p>Unrelated filing disclosure.</p>'*1300
         +'<p>The exact source percentage is 2.620 %; this is the requested disclosure.</p>'
         +'<p>Unrelated filing disclosure.</p>'*1300+'</html>').encode()
    doc=document_record('https://issuer.test/annual',raw,['2.620'],form='10-K')
    assert any('exact source percentage is 2.620 %; this is the requested disclosure' in c for c in doc['contexts'])
