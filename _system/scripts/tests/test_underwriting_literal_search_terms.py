"""Literal author search lists must reach bounded primary collection."""
import copy
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from underwriting_evidence import requested_keywords, document_record, text_of

REQUIRED = {'revolving credit facility', 'total commitment', 'termination date',
            'expiration', 'compliance', 'each advance', 'material adverse effect', 'event of default'}


@pytest.mark.parametrize('separator', [', ', '; '])
def test_unquoted_current_search_list_survives_generic_prose_and_clause_history(separator):
    current = {'code': 'missing_current_credit_capacity_expiry_access_terms', 'detail':
        'The expanded packet supplies prior principal facts, but remaining current terms determine access. '
        'Retrieve Note 10, Section 4.3 and Schedule 1 commitments. Search terms: '
        + separator.join(['revolving credit facility', 'total commitment', 'termination date',
                          'expiration', 'compliance', 'each advance', 'material adverse effect', 'event of default'])
        + '. Include any amendments identified by the primary report.'}
    history = [{'detail': "Search: '2015 Senior Notes', '2017 Senior Notes', 'maturity date'."}]
    before = copy.deepcopy([current, history])
    terms = requested_keywords([current], history=history)
    assert REQUIRED | {'note 10', 'section 4.3', 'schedule 1',
                       '2015 senior notes', '2017 senior notes'} <= set(terms)
    assert not any('include any' in term for term in terms)
    assert len(terms) <= 18 and len(terms) == len(set(terms))
    assert [current, history] == before


def test_unquoted_definition_and_advance_queries_retain_the_complete_primary_passages():
    definition = '<p>“Termination Date” means ' + 'the contractual date and its stated qualifications ' * 90 + '.</p>'
    advance = ('<div>4.3 Each Advance. ' + 'Every stated borrowing condition remains operative. ' * 90
               + 'Final required advance condition.</div>')
    raw = ('<html><p>Cash, debt, credit and capital disclosures.</p>'
           + '<p>Unrelated source material.</p>' * 1400 + definition
           + '<p>Unrelated intervening source material.</p>' * 1400 + advance
           + '<div>5.1 Representations and Warranties.</div></html>').encode()
    terms = requested_keywords([{'code': 'missing_current_credit_capacity_expiry_access_terms', 'detail':
        'The expanded primary packet needs remaining terms to establish contractual access. '
        'Search terms: termination date, each advance.'}])
    doc = document_record('https://issuer.test/executed-credit', raw, terms)
    assert any(text_of(definition) in context for context in doc['contexts'])
    assert any(text_of(advance) in context for context in doc['contexts'])


def test_explicit_schedule_identifiers_do_not_capture_years_or_percentages():
    terms = requested_keywords([{'detail':
        'Retrieve Schedule 1 and Schedule 5.7. A repayment schedule 2028 and a schedule 3.5% are not identifiers. '
        'Search terms: total commitment, termination date.'}])
    assert {'schedule 1', 'schedule 5.7'} <= set(terms)
    assert not {'schedule 2028', 'schedule 3.5'} & set(terms)


@pytest.mark.parametrize('block', ['p', 'div'])
def test_requested_schedule_retains_the_complete_operating_table_after_the_contents(block):
    schedule = (f'<{block}>SCHEDULE 1 COMMITMENT SCHEDULE</{block}><table>'
                + ''.join(f'<tr><td>Lender identifier {i}</td><td>Contractual amount entry {i}</td></tr>' for i in range(45))
                + '</table>')
    raw = ('<html><p>Credit cash debt capital termination date each advance total commitment.</p>'
           + f'<{block}>SCHEDULE 1 COMMITMENT SCHEDULE</{block}><{block}>SCHEDULE 2 PRICING SCHEDULE</{block}>'
           + '<p>Unrelated source material.</p>' * 1400 + schedule
           + f'<{block}>SCHEDULE 2 PRICING SCHEDULE</{block}><p>Following pricing disclosure.</p></html>').encode()
    terms = requested_keywords([{'detail': 'Retrieve Schedule 1. Search terms: termination date, each advance, total commitment.'}])
    doc = document_record('https://issuer.test/executed-credit', raw, terms)
    assert any(text_of(schedule) in c for c in doc['contexts'])
    assert sum(map(len, doc['contexts'])) <= 350000


@pytest.mark.parametrize('block', ['p', 'div'])
def test_default_requests_retain_complete_labeled_default_and_remedy_articles(block):
    defaults = f'<{block}>ARTICLE VII - EVENTS OF DEFAULT</{block}>' + f'<{block}>Contractual event and qualification. </{block}>' * 100
    remedies = f'<{block}>ARTICLE VIII - ACCELERATION AND REMEDIES</{block}>' + f'<{block}>Contractual remedy and payment timing. </{block}>' * 100
    raw = ('<html><p>Credit cash debt capital event of default termination date.</p>'
           + f'<{block}>ARTICLE VII - EVENTS OF DEFAULT</{block}><{block}>ARTICLE VIII - ACCELERATION AND REMEDIES</{block}>'
           + f'<{block}>ARTICLE IX - GENERAL</{block}>'
           + '<p>Unrelated source material.</p>' * 1400 + defaults + remedies
           + f'<{block}>ARTICLE IX - GENERAL</{block}><p>Following general provisions.</p></html>').encode()
    terms = requested_keywords([{'detail': 'Search terms: event of default, termination date.'}])
    doc = document_record('https://issuer.test/executed-credit', raw, terms)
    assert any(text_of(defaults) in c for c in doc['contexts'])
    assert any(text_of(remedies) in c for c in doc['contexts'])


def test_bare_lists_keep_dotted_currency_labels_and_reject_url_or_command_queries():
    terms = requested_keywords([{'detail':
        'Search terms: U.S. Dollar, termination date, https://outside.test/path, $(run). '
        'Include other issuer disclosures.'}])
    assert {'u.s. dollar', 'termination date'} <= set(terms)
    assert not any('://' in term or '$' in term or 'include other' in term for term in terms)


def test_complete_article_retrieval_keeps_the_existing_passage_and_document_bounds():
    article = '<div>ARTICLE VII - EVENTS OF DEFAULT</div>' + '<p>Contractual condition and qualification. </p>' * 1200
    raw = ('<html><p>Credit cash debt capital event of default.</p>' + article
           + '<div>ARTICLE VIII - REMEDIES</div><p>Following remedy disclosure.</p></html>').encode()
    doc = document_record('https://issuer.test/executed-credit', raw, ['event of default'])
    assert len(text_of(article)) > 30000
    assert not any(text_of(article) in c for c in doc['contexts'])
    assert sum(map(len, doc['contexts'])) <= 350000

