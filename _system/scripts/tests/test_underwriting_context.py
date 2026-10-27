"""Scale headers and requested disclosures survive bounded primary extraction."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import underwriting_evidence as evidence


def test_supplemental_fact_quote_keeps_the_scale_header_outside_its_table():
    raw = (b'<html><p>Supplemental cash flow information (in millions).</p>'
           b'<table>For the period ended September 30, 2026. Company excluding Finance; Finance; Eliminations. '
           b'Operating cash flow 5,895; assets 20,000; liabilities 7,000; debt 1,000; capital spending 3,000.</table></html>')
    document = evidence.document_record('https://issuer.test/report', raw)
    quote = next(c for c in document['contexts'] if '5,895' in c)
    assert 'in millions' in quote
    assert document['content_hash'] == hashlib.sha256(raw).hexdigest()
    packet = {'as_of': '2026-10-29', 'currency': 'USD', 'observations': [], 'documents': [document]}
    rows = evidence.supplemental_observations(packet, [{'id': 'parent_ocf', 'document_id': document['id'],
        'quote': quote, 'numeric_token': '5,895', 'scale': 1_000_000, 'unit': 'USD', 'period': '2026-09-30',
        'field': 'parent_operating_cash', 'locator': 'Company excluding Finance, operating cash flow',
        'scope': 'Parent excluding captive finance', 'measurement_type': 'flow'}])
    assert rows[0]['value'] == 5_895_000_000


def test_evidence_request_uses_balanced_quoted_terms_instead_of_boilerplate():
    gaps = [
        {'code': 'missing_parent_cash_table', 'detail': "The expanded contexts still omit currency scale headers. Search terms: 'Company excluding Finance', 'in millions', 'Investing activity'."},
        {'code': 'missing_cash_obligations', 'detail': "Retrieve current disclosures. Search terms: 'BOSK', 'program cancellation', 'remaining cash', 'guarantees'."},
        {'code': 'missing_captive_constraints', 'detail': "Retrieve current disclosures. Search terms: 'managed leverage', 'support agreement', 'credit losses', 'lease residual'."},
    ]
    terms = evidence.requested_keywords(gaps)
    assert terms[:3] == ['company excluding finance', 'bosk', 'managed leverage']
    assert {'in millions', 'support agreement', 'credit losses', 'guarantees'} <= set(terms)
    assert not {'expanded', 'contexts', 'still', 'omit', 'missing_parent_cash_table'} & set(terms)
    assert len(evidence.requested_keywords(gaps*30)) <= 18


def test_focused_phrases_choose_the_disclosure_instead_of_a_table_of_contents_mention():
    text = ('<html>Contents: support agreement. '+('Unrelated discussion. '*400)
            +'Support agreement requires managed leverage below 9 and restricts distributions. '
            +'Lease residual stress limits remittances.'+('Trailing discussion. '*250)+'</html>')
    document = evidence.document_record('https://issuer.test/report', text.encode(),
                                        ['support agreement', 'managed leverage', 'lease residual'])
    assert any('requires managed leverage below 9' in c for c in document['contexts'])
    assert sum(map(len, document['contexts'])) <= 150_000


def test_focused_extraction_is_bounded_and_reproducible():
    raw = ('<html>'+''.join('<table>Quarter ended September 30, 2026; cash capital debt assets liabilities '
        +str(i)+' '+('support agreement managed leverage lease residual '*100)+'</table>' for i in range(90))+'</html>').encode()
    terms = ['support agreement', 'managed leverage', 'lease residual']
    first = evidence.document_record('https://issuer.test/report', raw, terms)
    assert first == evidence.document_record('https://issuer.test/report', raw, terms)
    assert sum(map(len, first['contexts'])) <= 150_000
