"""Retrieve requested legal disclosures from issuer-bound primary citations."""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from underwriting_primary_references import linked_references, collect_requested_documents


PARENT = 'https://www.sec.gov/Archives/edgar/data/1059556/000162828026009136/mco-20251231.htm'
AGREEMENT = 'https://www.sec.gov/Archives/edgar/data/1059556/000119312524131945/d824452dex101.htm'


def test_incorporated_credit_agreement_is_selected_from_its_actual_exhibit_row():
    raw = (f'<table><tr><td><a href="{AGREEMENT}">10.1</a></td>'
           '<td>Credit Agreement, dated May 6, 2024, incorporated by reference.</td></tr>'
           '<tr><td><a href="executive.htm">Employment agreement</a></td></tr></table>').encode()
    refs = linked_references(raw, PARENT, '1059556', ['credit', 'covenant definitions'])
    assert [r['source_url'] for r in refs] == [AGREEMENT]
    assert refs[0]['referenced_by']['source_url'] == PARENT
    assert len(refs[0]['referenced_by']['content_hash']) == 64


@pytest.mark.parametrize('url', [
    'https://attacker.test/Archives/edgar/data/1059556/000119312524131945/credit.htm',
    'https://www.sec.gov/Archives/edgar/data/123/000119312524131945/credit.htm',
    'https://attacker@www.sec.gov/Archives/edgar/data/1059556/000119312524131945/credit.htm',
    'https://www.sec.gov/Archives/edgar/data/1059556/000119312524131945/../../secret.htm',
    'file:///credit.htm', 'javascript:credit()',
])
def test_disclosure_text_cannot_select_an_untrusted_network_destination(url):
    raw = f'<a href="{url}">Credit agreement</a>'.encode()
    assert linked_references(raw, PARENT, '1059556', ['credit']) == []


def test_no_extra_sources_are_fetched_without_an_explicit_evidence_request():
    assert collect_requested_documents({}, '1059556', '2026-11-02', [], [], None) == ([], [])


def test_dated_requested_notes_precede_generic_indentures_within_the_existing_fetch_limit():
    base = AGREEMENT.rsplit('/', 1)[0] + '/'
    labels = {
        'credit.htm': 'Credit Agreement and covenant definitions',
        'a-unrelated.htm': 'First Supplemental Indenture, dated 2011, Senior Notes due 2040',
        'b-unrelated.htm': 'Second Supplemental Indenture, dated 2012, Senior Notes due 2041',
        'c-unrelated.htm': 'Third Supplemental Indenture, dated 2013, Senior Notes due 2042',
        'requested-2015.htm': 'Fifth Supplemental Indenture, dated March 9, 2015, including the form of Senior Notes due 2027',
        'requested-2017.htm': 'Seventh Supplemental Indenture, dated June 12, 2017, including the form of Senior Notes due 2028',
        'new-supplement.htm': 'Nineteenth Supplemental Indenture, dated October 7, 2026',
    }
    raw = ('<table>' + ''.join(f'<tr><td><a href="{base}{name}">{label}</a></td></tr>'
                              for name, label in labels.items()) + '</table>').encode()
    calls = []
    def fetch(url):
        calls.append(url)
        return b'<p>Cash, debt and capital. ' + b'Complete operative principal, maturity and payment terms. ' * 30 + b'</p>'
    docs, errors = collect_requested_documents({}, '1059556', '2026-11-07',
        [{'source_url': PARENT, 'raw': raw, 'filed': '2026-10-21'}],
        ['2015 senior notes', '2017 senior notes', 'maturity date', 'nineteenth supplemental indenture'], fetch)
    assert not errors
    assert set(calls[:4]) == {base + name for name in (
        'requested-2015.htm', 'requested-2017.htm', 'credit.htm', 'new-supplement.htm')}
    assert len(calls) == 7 and len(calls) <= 8
    assert {d['source_url'] for d in docs} == set(calls)
    assert all(d['coverage'] == 'complete_requested_primary_document' for d in docs)


def test_an_explicit_dated_note_request_needs_no_generic_debt_keyword():
    raw = ('<a href="notes.htm">Fifth Supplemental Indenture, dated March 9, 2015, '
           'including the form of Senior Notes due 2027</a>').encode()
    refs = linked_references(raw, PARENT, '1059556', ['2015 senior notes'])
    assert [r['source_url'].rsplit('/', 1)[-1] for r in refs] == ['notes.htm']


def test_generic_helpers_cannot_displace_the_eighteenth_explicit_instrument():
    raw = b'<a href="notes.htm">Indenture dated March 9, 2015 including Senior Notes due 2027</a>'
    calls = []
    def fetch(url):
        calls.append(url)
        return b'<p>Cash, debt and capital. ' + b'Complete operative terms. ' * 40 + b'</p>'
    docs, errors = collect_requested_documents({}, '1059556', '2026-11-07',
        [{'source_url': PARENT, 'raw': raw}],
        [f'explicit query {i}' for i in range(17)] + ['2015 senior notes'], fetch)
    assert not errors and len(calls) == 1
    assert docs[0]['source_url'].endswith('/notes.htm')


def test_dated_indentures_match_their_own_date_without_inventing_a_base_alias():
    raw = ('<a href="old.htm">Indenture dated August 19, 2009 between the Company and Trustee</a>'
           '<a href="current.htm">Indenture dated August 19, 2010 between the Company and Trustee</a>').encode()
    refs = linked_references(raw, PARENT, '1059556', ['2010 indenture'])
    assert refs[0]['source_url'].endswith('/current.htm')
    assert refs[0]['_score'] > refs[1]['_score']


def test_unselected_primary_citations_remain_available_in_the_second_bounded_layer():
    base = AGREEMENT.rsplit('/', 1)[0] + '/'
    raw = ''.join(f'<a href="{base}agreement-{i}.htm">Credit Agreement {i}</a>' for i in range(6)).encode()
    calls = []
    def fetch(url):
        calls.append(url)
        return b'<p>Cash, debt and capital. ' + b'Complete operative terms. ' * 40 + b'</p>'
    docs, errors = collect_requested_documents({}, '1059556', '2026-11-07',
        [{'source_url': PARENT, 'raw': raw}], ['credit'], fetch)
    assert not errors
    assert len(calls) == 6 and len(set(calls)) == 6
    assert {d['source_url'] for d in docs} == set(calls)


def test_pending_index_citations_cannot_displace_selected_executed_children():
    base = AGREEMENT.rsplit('/', 1)[0] + '/'
    initial = [base+f'agreement-{i}.htm' for i in range(6)]
    children = [base+f'z-operative-{i}.htm' for i in range(4)]
    raw = ''.join(f'<a href="{url}">Credit Agreement</a>' for url in initial).encode()
    calls = []
    def fetch(url):
        calls.append(url)
        child = (f'<a href="{children[initial.index(url)]}">Executed Credit Agreement</a>'
                 if url in initial[:4] else '')
        return ('<p>Cash, debt and capital. '+'Complete operative terms. '*40+'</p>'+child).encode()
    docs, errors = collect_requested_documents({}, '1059556', '2026-11-07',
        [{'source_url': PARENT, 'raw': raw}], ['credit'], fetch)
    assert not errors and len(calls) == 8
    assert set(calls) == set(initial[:4]+children)


def test_a_requested_supplement_keeps_complete_operative_terms_without_financial_word_padding():
    from underwriting_evidence import document_record, primary_text, text_of
    raw = ('<html><p>Exhibit 4.1 Execution Version NINETEENTH SUPPLEMENTAL INDENTURE. '
           'This Nineteenth Supplemental Indenture is between the Company and the Trustee.</p>'
           '<p>Section 1. Appointment. ' + 'Successor Trustee shall perform its duties. ' * 35 + '</p>'
           '<p>Section 2. Acceptance. ' + 'The appointment is subject to the operative conditions. ' * 35 + '</p>'
           '<p>Section 3. Governing law. Terms continue through the final provision.</p>'
           '<p>IN WITNESS WHEREOF the Company and the Trustee have executed this instrument.</p></html>').encode()
    doc = document_record(AGREEMENT, raw, ['nineteenth supplemental indenture'], prefer_complete=True)
    assert doc['coverage'] == 'complete_requested_primary_document'
    assert doc['contexts'] == [text_of(primary_text(raw))]


def test_a_mention_of_an_indentures_title_cannot_enable_complete_legal_capture():
    from underwriting_evidence import document_record
    raw = ('<p>This report mentions the Nineteenth Supplemental Indenture and its Trustee.</p>'
           + '<p>Unrelated commentary. ' * 100 + '</p>').encode()
    doc = document_record(AGREEMENT, raw, ['nineteenth supplemental indenture'], prefer_complete=True)
    assert doc.get('coverage') != 'complete_requested_primary_document'


@pytest.mark.parametrize('old,new', [
    ('This Nineteenth Supplemental Indenture', 'A report about the supplement'),
    ('Section 1', 'Paragraph one'), ('Trustee', 'Agent'),
    ('IN WITNESS WHEREOF', 'End of discussion'),
])
def test_complete_supplement_requires_its_own_operative_and_execution_structure(old, new):
    from underwriting_contract import ContractError
    from underwriting_evidence import document_record
    body = ('This Nineteenth Supplemental Indenture is between the Company and the Trustee. '
            'Section 1. Successor appointment. ' + 'The original obligations continue. ' * 40
            + 'IN WITNESS WHEREOF the parties executed this supplemental indenture.')
    raw = ('<p>' + body.replace(old, new) + '</p>').encode()
    try:
        doc = document_record(AGREEMENT, raw, ['nineteenth supplemental indenture'], prefer_complete=True)
    except ContractError:
        return  # A non-operative mention can also yield no relevant evidence.
    assert doc.get('coverage') != 'complete_requested_primary_document'


def test_dated_note_priority_uses_word_boundaries_and_the_exhibits_own_description():
    raw = ('<table><tr><td>2015 Senior Notes. '
           '<a href="wrong.htm">Indenture dated 2017 including Senior Notes due 2030</a> '
           '<a href="wrong-year.htm">Indenture dated 12015 including Senior Notes due 2030</a> '
           '<a href="wrong-kind.htm">Indenture dated 2015 including Senior Noteworthy terms</a> '
           '<a href="right.htm">Indenture dated 2015 including Senior Notes due 2027</a> '
           '<a href="https://www.sec.gov/Archives/edgar/data/999999/000119312524131945/foreign.htm">'
           'Indenture dated 2015 including Senior Notes due 2027</a>'
           '</td></tr></table>').encode()
    refs = linked_references(raw, PARENT, '1059556', ['2015 senior notes', 'maturity'])
    by_name = {r['source_url'].rsplit('/', 1)[-1]: r['_score'] for r in refs}
    assert refs[0]['source_url'].endswith('/right.htm')
    assert 'foreign.htm' not in by_name
    assert by_name['right.htm'] > max(by_name[name] for name in (
        'wrong.htm', 'wrong-year.htm', 'wrong-kind.htm'))


def test_a_broad_table_row_cannot_turn_a_form_or_certificate_into_a_credit_exhibit():
    raw = (f'<table><tr><td>Credit agreement and merger disclosures. '
           f'<a href="{AGREEMENT}">Credit Agreement</a> '
           '<a href="other.htm">Form 10-K</a> '
           '<a href="certificate.htm">Amended and Restated Certificate of Incorporation</a>'
           '</td></tr></table>').encode()
    assert [r['source_url'] for r in linked_references(raw, PARENT, '1059556', ['credit'])] == [AGREEMENT]


def test_a_date_anchor_to_an_old_report_is_not_frozen_as_a_credit_agreement():
    old = 'https://www.sec.gov/Archives/edgar/data/1059556/000105955625000025/mco-20241231.htm'
    raw = (f'<table><tr><td>Credit agreement references. <a href="{AGREEMENT}">Credit Agreement</a> '
           f'<a href="{old}">February 14, 2025</a></td></tr></table>').encode()
    submissions = {'filings': {'recent': {'form': ['10-K'],
        'accessionNumber': ['0001059556-25-000025'], 'primaryDocument': ['mco-20241231.htm']}}}
    calls = []
    def fetch(url):
        calls.append(url)
        return ('<p>Cash, debt, credit conditions and capital. '+('Complete agreement terms. '*40)+'</p>').encode()
    docs, errors = collect_requested_documents(submissions, '1059556', '2026-11-02',
        [{'source_url': PARENT, 'raw': raw, 'filed': '2026-02-18'}], ['credit'], fetch)
    assert not errors and calls == [AGREEMENT]
    assert [doc['source_url'] for doc in docs] == [AGREEMENT]


def test_reference_contents_and_primary_chain_are_preserved_without_a_false_financial_period():
    raw = f'<a href="{AGREEMENT}">Credit Agreement</a>'.encode()
    body = ('<html><p>Credit agreement: cash, debt, capital, borrowing conditions.</p>'
            + 'Complete covenant definitions and permitted draws. ' * 100
            + '<p>Final unavailable-refinancing condition.</p></html>').encode()
    parent = {'source_url': PARENT, 'raw': raw, 'filed': '2026-02-18', 'form': '10-K'}
    def fetch(url):
        assert url == AGREEMENT
        return body
    docs, errors = collect_requested_documents({}, '1059556', '2026-11-02', [parent], ['credit'], fetch)
    assert not errors and len(docs) == 1
    doc = docs[0]
    assert doc['source_url'] == AGREEMENT
    assert doc['referenced_by']['filed'] == '2026-02-18'
    assert doc['coverage'] == 'complete_requested_primary_document'
    assert doc['contexts'][0].endswith('Final unavailable-refinancing condition.')
    assert 'period' not in doc and 'filed' not in doc


def test_failed_requested_reference_is_an_explicit_source_error():
    raw = f'<a href="{AGREEMENT}">Credit Agreement</a>'.encode()
    def fail(url):
        raise OSError('source unavailable')
    _, errors = collect_requested_documents({}, '1059556', '2026-11-02',
        [{'source_url': PARENT, 'raw': raw, 'filed': '2026-02-18'}], ['credit'], fail)
    assert errors[0]['source'] == 'requested_primary_reference'
    assert errors[0]['source_url'] == AGREEMENT


def test_transaction_filings_are_evidence_without_becoming_new_financial_statements():
    url = 'https://www.sec.gov/Archives/edgar/data/900075/000119312526423478/d129535d8k.htm'
    submissions = {'filings': {'recent': {'form': ['8-K', '8-K'], 'filingDate': ['2026-10-16', '2027-01-01'],
        'items': ['2.01', '1.01'], 'accessionNumber': ['0001193125-26-423478', '0001193125-27-000001'],
        'primaryDocument': ['d129535d8k.htm', 'future.htm'], 'reportDate': ['2026-10-16', '2027-01-01']}}}
    calls = []
    def fetch(target):
        calls.append(target)
        return ('<html>Copart completed the acquisition of ACV Auctions Inc. for cash; shares and debt '
                + 'merger transaction terms. ' * 30 + '</html>').encode()
    docs, errors = collect_requested_documents(submissions, '900075', '2026-11-02',
        [{'source_url': PARENT, 'filed': '2026-09-24', 'raw': b''}], ['merger consideration'], fetch)
    assert not errors and calls == [url]
    assert docs[0]['filed'] == '2026-10-16'
    assert 'period' not in docs[0]


def test_a_requested_source_failure_blocks_judgment_readiness():
    from underwriting_evidence import evidence_readiness
    from test_underwriting_pipeline import packet
    value = packet()
    value['collection_errors'] = [{'source': 'requested_primary_reference', 'source_url': AGREEMENT,
                                   'error': 'source unavailable'}]
    assert evidence_readiness(value)['status'] == 'evidence_gap'


def test_incorporation_through_an_announcing_filing_reaches_the_operative_exhibit():
    announcement = AGREEMENT.replace('d824452dex101.htm', 'announcement.htm')
    raw = f'<a href="{announcement}">Fourth Amendment to Credit Agreement, incorporated by reference to Exhibit 10.1.</a>'.encode()
    body = b'<table><tr><td>10.1</td><td><a href="d824452dex101.htm">Fourth Amendment to Credit Agreement</a></td></tr></table>'
    operative = b'<p>Fourth Amendment to Credit Agreement. Conditions to effectiveness and permitted draws.</p>'
    calls = []
    def fetch(url):
        calls.append(url)
        return {announcement: body, AGREEMENT: operative}[url]
    docs, errors = collect_requested_documents({}, '1059556', '2026-11-04',
        [{'source_url': PARENT, 'raw': raw, 'filed': '2026-02-18'}], ['credit', 'effective amendment'], fetch)
    assert not errors and calls == [announcement, AGREEMENT]
    by_url = {d['source_url']: d for d in docs}
    assert set(by_url) == {announcement, AGREEMENT}
    assert by_url[announcement]['content_hash'] == hashlib.sha256(body).hexdigest()
    assert by_url[AGREEMENT]['content_hash'] == hashlib.sha256(operative).hexdigest()
    assert by_url[AGREEMENT]['referenced_by']['source_url'] == announcement
    assert by_url[AGREEMENT]['referenced_by']['content_hash'] == hashlib.sha256(body).hexdigest()
    # The date of the later report must not become this undated intermediary's filing date.
    assert by_url[AGREEMENT]['referenced_by']['filed'] is None
    assert all('period' not in d and 'filed' not in d for d in docs)


def test_nested_reference_failure_is_reported_and_blocks_readiness():
    from underwriting_evidence import evidence_readiness
    from test_underwriting_pipeline import packet
    announcement = AGREEMENT.replace('d824452dex101.htm', 'announcement.htm')
    def fetch(url):
        if url == announcement:
            return b'<a href="d824452dex101.htm">Executed Revolving Credit Agreement</a>'
        raise OSError('operative agreement unavailable')
    docs, errors = collect_requested_documents({}, '1059556', '2026-11-04',
        [{'source_url': PARENT, 'raw': f'<a href="{announcement}">Credit Agreement</a>'.encode()}], ['credit'], fetch)
    assert [d['source_url'] for d in docs] == [announcement]
    assert errors == [{'source': 'requested_primary_reference', 'source_url': AGREEMENT,
                       'error': 'operative agreement unavailable'}]
    value = packet()
    value['collection_errors'] = errors
    assert evidence_readiness(value)['status'] == 'evidence_gap'


def test_followup_preserves_initial_sources_and_bounds_cycles_and_depth():
    base = AGREEMENT.rsplit('/', 1)[0] + '/'
    initial = [base + f'agreement-{i}.htm' for i in range(4)]
    nested = [base + f'operative-{i}.htm' for i in range(4)]
    third = base + 'beyond-depth.htm'
    parent = ''.join(f'<a href="{url}">Credit Agreement</a>' for url in initial).encode()
    calls = []
    def fetch(url):
        calls.append(url)
        assert url != third
        if url in initial:
            i = initial.index(url)
            return (f'<a href="{nested[i]}">Executed Credit Agreement</a>'
                    f'<a href="{PARENT}">Credit Agreement</a>'
                    '<a href="https://attacker.test/credit.htm">Credit Agreement</a>').encode()
        return (f'<a href="{initial[0]}">Credit Agreement</a>'
                f'<a href="{third}">Credit Agreement</a>').encode()
    docs, errors = collect_requested_documents({}, '1059556', '2026-11-04',
        [{'source_url': PARENT, 'raw': parent}], ['credit'], fetch)
    assert not errors
    assert set(calls) == set(initial + nested) and len(calls) == 8
    assert {d['source_url'] for d in docs} == set(initial + nested)


def test_nested_parent_date_comes_from_its_verified_submission():
    announcement = AGREEMENT.replace('d824452dex101.htm', 'announcement.htm')
    submissions = {'filings': {'recent': {'form': ['8-K'], 'filingDate': ['2024-05-07'],
        'accessionNumber': ['0001193125-24-131945'], 'primaryDocument': ['announcement.htm']}}}
    def fetch(url):
        return (b'<a href="d824452dex101.htm">Executed Credit Agreement</a>' if url == announcement
                else b'<p>Executed credit agreement and borrowing conditions.</p>')
    docs, errors = collect_requested_documents(submissions, '1059556', '2026-11-04',
        [{'source_url': PARENT, 'raw': f'<a href="{announcement}">Credit Agreement</a>'.encode(),
          'filed': '2026-02-18'}], ['credit'], fetch)
    assert not errors
    operative = next(d for d in docs if d['source_url'] == AGREEMENT)
    assert operative['referenced_by']['filed'] == '2024-05-07'
    assert 'filed' not in operative and 'period' not in operative


def test_malformed_or_future_submission_metadata_does_not_date_nested_sources():
    announcement = AGREEMENT.replace('d824452dex101.htm', 'announcement.htm')
    submissions = {'filings': {'recent': {'form': ['8-K', '8-K'],
        'filingDate': ['2026-01-01', '2027-01-01'], 'accessionNumber': [None, '0001193125-24-131945'],
        'primaryDocument': ['malformed.htm', 'announcement.htm']}}}
    def fetch(url):
        return (b'<a href="d824452dex101.htm">Executed Credit Agreement</a>' if url == announcement
                else b'<p>Executed credit agreement and borrowing conditions.</p>')
    docs, errors = collect_requested_documents(submissions, '1059556', '2026-11-04',
        [{'source_url': PARENT, 'raw': f'<a href="{announcement}">Credit Agreement</a>'.encode(),
          'filed': '2026-02-18'}], ['credit'], fetch)
    assert not errors
    assert next(d for d in docs if d['source_url'] == AGREEMENT)['referenced_by']['filed'] is None
