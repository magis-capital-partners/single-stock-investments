"""Retrieve requested legal disclosures from issuer-bound primary citations."""
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
