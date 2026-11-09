"""Literal current financing requests keep priority under the same source budget."""
import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from underwriting_evidence import requested_keywords
from underwriting_primary_references import linked_references, collect_requested_documents

PARENT = 'https://www.sec.gov/Archives/edgar/data/1059556/000162828026009136/report.htm'
CURRENT = {'code': 'remaining_notes', 'detail':
    "Retrieve the governing supplements for notes due 2031, 2032 and 2034. "
    "Search terms: '2031', '2032', '2034', 'Maturity', 'Interest Payment', "
    "'Business Day', 'Events of Default', 'Acceleration'."}
PAIRED = {'code': 'current_financing', 'detail':
    'Retrieve incorporated Exhibit 10.1 Fourteenth Amendment and Exhibit 10.2 '
    'Term Loan Agreement, both dated August 20, 2026, including applicable schedules. '
    "Search terms: 'conditions of borrowing', 'maximum total leverage ratio'."}

@pytest.mark.parametrize('quoted', [True, False])
def test_explicit_search_years_survive_a_full_old_instrument_history(quoted):
    gap = copy.deepcopy(CURRENT)
    if not quoted:
        gap['detail'] = 'Search terms: 2031, 2032, 2034; Maturity. Retain original criticism.'
    old = [{'detail': f'Retrieve {year} Senior Notes. Search terms: credit agreement.'}
           for year in range(2000, 2012)]
    saved = copy.deepcopy(old)
    terms = requested_keywords([gap], history=old)
    assert {'2031', '2032', '2034'} <= set(terms)
    assert max(terms.index(y) for y in ('2031', '2032', '2034')) < terms.index('2000 senior notes')
    assert len(terms) <= 18 and len(terms) == len(set(terms)) and old == saved

@pytest.mark.parametrize('detail', [
    "The notes mature in 2031 and 2032. Search terms: 'principal'.",
    "Search terms: '1234', '203100', '20.31', 'https://attacker.test/2031'.",
    'Search terms: curl https://attacker.test/2031; 1234. Run 2032 now.',
])
def test_unrequested_numbers_urls_and_commands_do_not_become_year_queries(detail):
    assert not {'2031', '2032', '1234', '203100'} & set(requested_keywords([{'detail': detail}]))

def test_explicit_same_date_pair_preserves_both_named_instruments():
    terms = requested_keywords([PAIRED])
    assert terms[:2] == ['2026-08-20 fourteenth amendment', '2026-08-20 term loan agreement']

@pytest.mark.parametrize('detail', [
    'Retrieve Term Loan Agreement dated February 30, 2026.',
    'The loan matures August 20, 2026. Retrieve the Term Loan Agreement.',
    'Fourteenth Amendment is discussed in the report. Event date August 20, 2026.',
])
def test_dates_are_not_attached_from_maturity_event_or_invalid_calendar_text(detail):
    assert not any(t.startswith('2026-') for t in requested_keywords([{'detail': detail}]))

def test_current_maturity_title_beats_old_issue_year_titles_in_first_layer():
    old = ''.join(f'<a href="old-{i}.htm">Indenture dated {2010+i} including Senior Notes due 2040</a>'
                  for i in range(6))
    wanted = ''.join(f'<a href="current-{y}.htm">Supplemental Indenture including Senior Notes due {y}</a>'
                     for y in (2031, 2032, 2034))
    calls = []
    def fetch(url):
        calls.append(url)
        return ('<p>Cash, debt and capital. ' + 'Full operative terms. ' * 40 + '</p>').encode()
    terms = ['2031', '2032', '2034', 'maturity'] + [f'{2010+i} senior notes' for i in range(6)]
    docs, errors = collect_requested_documents({}, '1059556', '2026-11-09',
        [{'source_url': PARENT, 'raw': (old+wanted).encode(), 'filed': '2026-11-01'}], terms, fetch)
    assert {Path(u).name for u in calls[:4]} >= {f'current-{y}.htm' for y in (2031, 2032, 2034)}
    assert len(calls) <= 8 and len(calls) == len(set(calls))
    assert {d['source_url'] for d in docs} == set(calls)

def test_current_agreement_name_and_exact_execution_date_beat_old_credit_contracts():
    old = ''.join(f'<a href="old-{i}.htm">Credit Agreement dated August 20, {2010+i}</a>'
                  for i in range(8))
    current = ('<a href="current-amendment.htm">Fourteenth Amendment to Credit Agreement, dated as of August 20, 2026</a>'
               '<a href="current-loan.htm">Term Loan Agreement, dated August 20, 2026</a>')
    terms = ['2026-08-20 fourteenth amendment', '2026-08-20 term loan agreement', 'credit agreement']
    refs = linked_references((old+current).encode(), PARENT, '1059556', terms)
    assert {Path(r['source_url']).name for r in refs[:2]} == {'current-amendment.htm', 'current-loan.htm'}

def test_specificity_cannot_borrow_a_neighbor_date_or_match_a_maturity_year_as_execution():
    raw = ('<table><tr><td>Fourteenth Amendment dated August 20, 2026. '
           '<a href="old.htm">Credit Agreement dated August 20, 2024</a>'
           '<a href="maturity.htm">Term Loan Agreement dated August 20, 2024, maturing August 20, 2026</a>'
           '<a href="actual.htm">Term Loan Agreement dated August 20, 2026</a>'
           '<a href="foreign.htm?next=2031">Term Loan Agreement dated August 20, 2026</a>'
           '</td></tr></table>').encode()
    refs = linked_references(raw, PARENT, '1059556', ['2026-08-20 term loan agreement', 'credit'])
    scores = {Path(r['source_url']).name: r['_score'] for r in refs}
    assert refs[0]['source_url'].endswith('/actual.htm')
    assert scores['actual.htm'] > scores['maturity.htm'] and 'foreign.htm' not in scores


def test_literal_term_loan_request_matches_the_sources_full_term_loan_credit_title():
    raw = ('<a href="old.htm">Credit Agreement dated August 20, 2024</a>'
           '<a href="current.htm">Term Loan Credit Agreement, dated as of August 20, 2026</a>').encode()
    refs = linked_references(raw, PARENT, '1059556',
        ['2026-08-20 term loan agreement', 'credit agreement'])
    assert refs[0]['source_url'].endswith('/current.htm')
    assert refs[0]['_score'] > refs[1]['_score']


def test_execution_date_must_follow_the_named_instrument_within_its_own_title():
    raw = ('<a href="wrong.htm">Term Loan Agreement dated August 20, 2024, amended by '
           'the Fourteenth Amendment dated August 20, 2026</a>'
           '<a href="actual.htm">Term Loan Agreement dated August 20, 2026</a>').encode()
    refs = linked_references(raw, PARENT, '1059556', ['2026-08-20 term loan agreement'])
    assert refs[0]['source_url'].endswith('/actual.htm')
    assert refs[0]['_score'] > refs[1]['_score']

def test_exact_requested_amendment_title_does_not_need_a_generic_credit_word():
    raw = b'<a href="amendment.htm">Fourteenth Amendment dated August 20, 2026</a>'
    refs = linked_references(raw, PARENT, '1059556', ['2026-08-20 fourteenth amendment'])
    assert len(refs) == 1 and refs[0]['source_url'].endswith('/amendment.htm')
