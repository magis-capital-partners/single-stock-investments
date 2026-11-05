"""Real-run gaps: financial notes, acquisition targets and entity scope."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import pytest

from underwriting_contract import ContractError, compile_contract, digest
from underwriting_evidence import document_record, requested_keywords
from test_underwriting_pipeline import packet, contract


def test_a_requested_note_keeps_its_disclosure_not_just_a_contents_mention():
    raw = ('<html><table>2026 consolidated cash flow and assets and debt in millions 1000.</table>'
           '<p>Contents: Note 9 Debt.</p>'+('General disclosure. '*500)
           +'<p>Note 9. Debt</p>'+('Debt terms and refinancing discussion. '*100)
           +'<p>Aggregate maturities 2030 principal 1749 million.</p></html>').encode()
    d = document_record('https://issuer.test/report', raw, ['note 9'])
    assert any('principal 1749 million' in c for c in d['contexts'])


def test_adjacent_note_windows_keep_their_source_text_once():
    raw=('<html><p>Note 4. Guarantees</p>'+('Guarantee obligations. '*400)
         +'<p>Note 5. Borrowing</p>'+('Borrowing terms and collateral. '*400)
         +'<p>Final maturity in 2030.</p></html>').encode()
    d=document_record('https://issuer.test/report',raw,['note 4','note 5'])
    assert any('Guarantee obligations.' in c and 'Final maturity in 2030.' in c for c in d['contexts'])
    assert not any(a in b for i,a in enumerate(d['contexts']) for j,b in enumerate(d['contexts']) if i!=j)


def test_a_bounded_quarterly_filing_keeps_every_note_and_contractual_footnote():
    from underwriting_evidence import text_of
    raw=('<html><p>Quarterly cash, debt and capital disclosures.</p>'+('Detailed report text. '*1000)
         +'<p>Supplier receivables and restricted investments: exact funding conditions.</p>'
         +('Contractual obligation detail. '*400)+'<p>Final commitment footnote.</p></html>').encode()
    d=document_record('https://issuer.test/quarter',raw,form='10-Q')
    assert d['coverage']=='complete_quarterly_filing'
    assert d['contexts']==[text_of(raw.decode())]


def test_note_numbers_in_gap_details_become_explicit_retrieval_terms():
    terms = requested_keywords([{'code':'missing_debt','detail':"Retrieve Note 9, Debt and Note 15, Settlement Risk. Search terms: 'maturity', 'collateral'."}])
    assert {'note 9','note 15','maturity','collateral'} <= set(terms)


@pytest.mark.parametrize('reference,expected', [
    ('Notes 3 and 13', {'note 3', 'note 13'}),
    ('Notes 3, 13, and 15', {'note 3', 'note 13', 'note 15'}),
    ('Notes 3, 13 or 15', {'note 3', 'note 13', 'note 15'}),
    ('Note 3 and Note 13', {'note 3', 'note 13'}),
])
def test_plural_financial_note_lists_reach_the_collector(reference, expected):
    terms = requested_keywords([{'code': 'environmental_funding', 'detail':
        f'Retrieve 2025 10-K {reference}. Search: "Chiquita", "insurance". '
        'The 2026 payment of 305.554 million does not establish remaining obligations.'}])
    assert {term for term in terms if term.startswith('note ')} == expected
    assert {'chiquita', 'insurance'} <= set(terms)


def test_bond_coupon_percentages_and_report_years_are_not_financial_note_numbers():
    terms = requested_keywords([{'detail':
        'Retrieve the issued notes 3.5% and senior notes 3 % due 2027, using the 2025 report.'}])
    assert not any(term.startswith('note ') for term in terms)


@pytest.mark.parametrize('block', ['p', 'div'])
def test_plural_note_requests_keep_complete_numbered_disclosures_past_cross_references(block):
    from underwriting_evidence import text_of
    note3 = (f'<{block}><b>3.</b>&nbsp;<b>ACCOUNTING POLICIES</b></{block}>'
             + f'<{block}>Reported cash obligations and closure costs. </{block}>' * 800
             + f'<{block}>Final accounting policy payment boundary.</{block}>')
    note13 = (f'<{block}>13. COMMITMENTS AND CONTINGENCIES</{block}>'
              + f'<{block}>See Note 3. Accounting policies remain applicable. </{block}>' * 800
              + f'<{block}>Final environmental payment and insurance boundary.</{block}>')
    raw = ('<html><div class="page"><p>See Note 13 for the commitments disclosure.</p>'
           + '<p>Unrelated introductory disclosure.</p>' * 1200
           + note3 + f'<{block}>4. ESTIMATES</{block}>'
           + '<p>Unrelated intervening disclosure.</p>' * 1200
           + note13 + f'<{block}>14. SHAREHOLDERS’ EQUITY</{block}>'
           + '<p>Subsequent unrelated equity disclosure.</p>' * 1200 + '</div></html>').encode()
    terms = requested_keywords([{'detail': 'Retrieve Notes 3 and 13. Search: "insurance".'}])
    doc = document_record('https://issuer.test/annual', raw, terms)
    assert any(text_of(note3) in c for c in doc['contexts'])
    assert any(text_of(note13) == c.strip() for c in doc['contexts'])
    assert sum(map(len, doc['contexts'])) <= 350000


def test_requested_credit_sections_survive_quoted_numbers_and_search_punctuation():
    terms = requested_keywords([{'code': 'missing_revolver_terms', 'detail':
        'Retrieve Sections 4.02 (Conditions to All Credit Extensions) and 8.02 '
        '(Remedies upon Event of Default). Search terms: “4.02,” “each Credit Extension,” '
        '“no Default,” “8.02,” and “Non-Investment Grade Covenant Period.”'}])
    assert {'section 4.02', 'section 8.02', 'each credit extension', 'no default',
            'non-investment grade covenant period'} <= set(terms)


def test_unquoted_section_lists_and_subsections_retrieve_the_containing_sections():
    terms = requested_keywords([{'detail':
        'Retrieve Sections 4.02(a), 8.02 and 8.03, plus Section 2.08(b). '
        'Reported cash of 257.4 million is not a section reference.'}])
    assert {'section 4.02', 'section 8.02', 'section 8.03', 'section 2.08'} <= set(terms)
    assert 'section 257.4' not in terms


@pytest.mark.parametrize('block', ['p', 'div'])
def test_numbered_html_paragraphs_retain_complete_requested_credit_clauses(block):
    from underwriting_evidence import text_of
    draw = ('4.02 Conditions to All Credit Extensions. '
            + 'The conditions to each borrowing are contractual requirements. ' * 90
            + 'No Default shall exist after giving effect to the requested extension.')
    remedies = ('8.02 Remedies upon Event of Default. '
                + 'The remedies upon a continuing default are specified here. ' * 90
                + 'All unpaid principal shall automatically become immediately due and payable.')
    draw_html = (draw.replace('4.02 ', '4.02<FONT>&nbsp;&nbsp;</FONT><U>', 1)
                 .replace('Extensions.', 'Extensions</U>.', 1))
    raw = ('<html><p>Cash, debt, credit, capital and assets.</p>'
           '<table><tr><td>4.02 Conditions to All Credit Extensions</td><td>76</td></tr>'
           '<tr><td>8.02 Remedies upon Event of Default</td><td>97</td></tr></table>'
           + '<p>Unrelated introductory disclosure. </p>' * 1200
           + '<p>' + draw_html + '</p>'
           + '<p>4.03 Other Provisions. Unrelated subsequent clause.</p>'
           + '<p>Unrelated intervening disclosure. </p>' * 1200
           + '<p>' + remedies + '</p>'
           + '<p>8.03 Application of Funds. Subsequent clause.</p></html>').encode()
    if block == 'div':
        raw = raw.replace(b'<p>', b'<div>').replace(b'</p>', b'</div>')
    doc = document_record('https://issuer.test/agreement', raw, ['section 4.02', 'section 8.02'])
    assert any(text_of(draw_html) in context for context in doc['contexts'])
    assert any(remedies in context for context in doc['contexts'])
    assert text_of(draw_html) in text_of(raw.decode())


@pytest.mark.parametrize('block', ['p', 'div'])
def test_page_break_reference_to_an_earlier_section_keeps_the_clause_tail(block):
    from underwriting_evidence import text_of
    clause = (f'<{block}>SECTION 5.2 Conditions Precedent to all Credit Extensions.</{block}>'
              f'<{block}>' + 'The condition remains applicable. ' * 400 + f'</{block}>'
              f'<{block}>Section 4.16 or the borrower satisfies the final required condition.</{block}>')
    raw = ('<html><p>Cash, credit, debt, assets and capital.</p>'
           '<table><tr><td>Section 5.2 Conditions Precedent</td><td>70</td></tr></table>'
           + '<p>Unrelated introductory disclosure.</p>' * 1200
           + clause
           + f'<{block}>SECTION 6.1 Organization and Power.</{block}>'
           + '<p>Unrelated following disclosure.</p>' * 1200 + '</html>').encode()
    doc = document_record('https://issuer.test/agreement', raw, ['section 5.2'])
    assert any(text_of(clause) in context for context in doc['contexts'])


@pytest.mark.parametrize('block', ['p', 'div'])
@pytest.mark.parametrize('outer_depth', [1, 3])
def test_nested_page_containers_do_not_hide_requested_section_headings(block, outer_depth):
    from underwriting_evidence import text_of
    clause = (f'<{block}><b>Section&nbsp;4.02.</b> Each Credit Event.</{block}>'
              f'<{block}>' + 'The specified condition must be satisfied. ' * 400 + f'</{block}>'
              f'<{block}>The final payment deadline remains part of this condition.</{block}>')
    content = ('<p>Cash, credit, debt, assets and capital.</p>'
               '<table><tr><td>Section 4.02. Each Credit Event</td><td>67</td></tr></table>'
               + '<p>Unrelated introductory disclosure.</p>' * 1200
               + clause
               + f'<{block}>Section 4.03. Other Credit Events.</{block}>'
               + '<p>Unrelated following disclosure.</p>' * 1200)
    raw = ('<html>' + '<div class="page">' * outer_depth + content
           + '</div>' * outer_depth + '</html>').encode()
    doc = document_record('https://issuer.test/agreement', raw, ['section 4.02'])
    assert any(text_of(clause) in context for context in doc['contexts'])


def registered_security_document(symbol='TEST', title='Common Shares', *, context='listing',
                                 extra='', filed='2026-03-19'):
    raw = (f'<html><ix:nonNumeric name="dei:EntityCentralIndexKey" contextRef="issuer">123</ix:nonNumeric>'
           f'<ix:nonNumeric name="dei:Security12bTitle" contextRef="{context}"><b>{title}</b></ix:nonNumeric>'
           f'<ix:nonNumeric name="dei:TradingSymbol" contextRef="{context}">{symbol}</ix:nonNumeric>'
           f'<ix:nonNumeric name="dei:SecurityExchangeName" contextRef="{context}">New York Stock Exchange</ix:nonNumeric>'
           + extra + '<p>Cash, credit, debt and capital disclosures.</p></html>').encode()
    doc = document_record('https://www.sec.gov/Archives/edgar/data/123/000000012326000001/annual.htm', raw)
    doc.update(form='40-F', filed=filed, period='2025-12-31')
    return doc


def test_registered_common_share_units_are_bound_to_the_exact_primary_symbol_and_issuer():
    from underwriting_evidence import listing_ratio_from_documents
    doc = registered_security_document()
    ratio = listing_ratio_from_documents([doc], symbol='TEST', calendar='XNYS', as_of='2026-11-04')
    assert ratio['ordinary_shares_per_listing_share'] == 1
    assert ratio['basis'] == 'direct_registered_common_or_ordinary_share'
    assert ratio['source_as_of'] == doc['filed']
    assert ratio['document_hash'] == doc['content_hash']
    assert 'dei:TradingSymbol' in ratio['locator']
    assert any('Common Shares' in c and 'TEST' in c for c in doc['contexts'])
    assert listing_ratio_from_documents([doc], symbol='OTHER', calendar='XNYS', as_of='2026-11-04') is None
    assert listing_ratio_from_documents([doc], symbol='TEST', calendar='XNAS', as_of='2026-11-04') is None
    wrong_issuer = {**doc, 'source_url': doc['source_url'].replace('/data/123/', '/data/456/')}
    assert listing_ratio_from_documents([wrong_issuer], symbol='TEST', calendar='XNYS', as_of='2026-11-04') is None


@pytest.mark.parametrize('title', ['Preferred Shares', 'American Depositary Shares',
                                 'Units including Common Shares', 'Warrants for Common Shares',
                                 'Common Shares with attached rights'])
def test_cover_security_descriptions_never_default_other_claims_to_one_ordinary_share(title):
    from underwriting_evidence import listing_ratio_from_documents
    assert listing_ratio_from_documents([registered_security_document(title=title)],
                                        symbol='TEST', calendar='XNYS', as_of='2026-11-04') is None


def test_missing_or_conflicting_cover_fields_do_not_establish_a_listing_unit():
    from underwriting_evidence import listing_ratio_from_documents
    conflict = '<ix:nonNumeric name="dei:Security12bTitle" contextRef="listing">Preferred Shares</ix:nonNumeric>'
    doc = registered_security_document(extra=conflict)
    assert listing_ratio_from_documents([doc], symbol='TEST', calendar='XNYS', as_of='2026-11-04') is None
    plain = {'contexts': ['Common Shares TEST New York Stock Exchange'], 'filed': '2026-03-19',
             'source_url': doc['source_url'], 'content_hash': 'a' * 64}
    assert listing_ratio_from_documents([plain], symbol='TEST', calendar='XNYS', as_of='2026-11-04') is None


def test_a_newer_explicit_security_class_blocks_an_older_common_share_registration():
    from underwriting_evidence import listing_ratio_from_documents
    old = registered_security_document()
    newer = registered_security_document(title='American Depositary Shares', filed='2026-06-01')
    assert listing_ratio_from_documents([old, newer], symbol='TEST', calendar='XNYS', as_of='2026-11-04') is None


def test_explicit_depositary_representation_must_agree_with_direct_registration():
    from underwriting_evidence import listing_ratio_from_documents
    doc = registered_security_document()
    doc['contexts'].append('Each ADS represents two common shares.')
    with pytest.raises(ContractError, match='sources_disagree'):
        listing_ratio_from_documents([doc], symbol='TEST', calendar='XNYS', as_of='2026-11-04')


@pytest.mark.parametrize('filed', ['2023-01-01', '2026-11-05'])
def test_direct_registration_must_be_current_and_known_on_the_quote_date(filed):
    from underwriting_evidence import listing_ratio_from_documents
    assert listing_ratio_from_documents([registered_security_document(filed=filed)],
                                        symbol='TEST', calendar='XNYS', as_of='2026-11-04') is None


def test_multiple_registered_common_classes_do_not_select_an_aggregate_share_basis():
    from underwriting_evidence import listing_ratio_from_documents
    second_class = ('<ix:nonNumeric name="dei:Security12bTitle" contextRef="second">Class B Common Shares</ix:nonNumeric>'
                    '<ix:nonNumeric name="dei:TradingSymbol" contextRef="second">TEST-B</ix:nonNumeric>'
                    '<ix:nonNumeric name="dei:SecurityExchangeName" contextRef="second">New York Stock Exchange</ix:nonNumeric>')
    assert listing_ratio_from_documents([registered_security_document(extra=second_class)],
                                        symbol='TEST', calendar='XNYS', as_of='2026-11-04') is None


def test_cover_evidence_does_not_displace_a_selected_financial_table():
    tables = ''.join('<table><tr><td>FinancialMarker'+str(i)+'</td><td>'
                     + 'Reported cash debt assets and capital. ' * 5 + '</td></tr></table>' for i in range(30))
    doc = registered_security_document(extra=tables)
    for i in range(30):
        assert any('FinancialMarker'+str(i)+' ' in c for c in doc['contexts'])


def test_cold_foreign_packet_uses_registered_share_units_without_changing_reported_shares(tmp_path):
    from test_underwriting_pipeline import company_root
    from underwriting_evidence import prepare_packet
    from underwriting_pipeline import read, write
    company_root(tmp_path)
    quote_path = tmp_path/'_system/reference/market-data/valuation_quotes/TEST.json'
    quote = read(quote_path)
    quote['quote']['calendar'] = 'XNYS'
    write(quote_path, quote)
    facts = [{'field': field, 'value': value, 'currency': 'USD', 'period': '2025-12-31',
              'form': '6-K', 'source_kind': 'primary',
              'source_url': 'https://www.sec.gov/Archives/edgar/data/123/000000012326000001/annual.htm',
              'locator': field} for field, value in [('net_income', 1000), ('equity', 5000), ('shares', 100)]]
    write(tmp_path/'_system/reference/market-data/valuation_fundamentals/TEST.json',
          {'facts': facts, 'primary_documents': [registered_security_document()]})
    result = prepare_packet(tmp_path, 'TEST', '2026-10-26', collect=False)
    assert result['listing_ratio']['ordinary_shares_per_listing_share'] == 1
    assert [o['value'] for o in result['observations'] if o['unit'] == 'shares'] == [100]


def issuer_annual_packet(monkeypatch):
    import autonomous_compounders as ac
    from test_autonomous_compounders import frmo_pdf_source
    frmo_pdf_source(monkeypatch)
    report = ac.frmo_report('2026-11-05')
    p = packet()
    p.update(ticker='FRMO', as_of='2026-11-05', financial_period='2026-05-31',
             latest_report=report['latest_report'], documents=report['primary_documents'])
    for row in p['observations']:
        row['period'] = '2026-05-31'
    return p


def test_complete_registered_issuer_report_satisfies_the_annual_document_gate(monkeypatch):
    from underwriting_evidence import evidence_readiness
    p = issuer_annual_packet(monkeypatch)
    assert evidence_readiness(p, require_documents=True)['status'] == 'ready'
    assert p['latest_report']['filed'] == ''  # The collection date is not a filing date.


def test_failed_issuer_discovery_keeps_the_normal_primary_source_retry_gate(monkeypatch):
    from underwriting_evidence import evidence_readiness
    p = issuer_annual_packet(monkeypatch)
    p['source_discovery'] = {'status': 'failed'}
    result = evidence_readiness(p, require_documents=True)
    assert any(g['code'] == 'report_discovery_failed' for g in result['gaps'])
    assert result['status'] == 'evidence_gap'


@pytest.mark.parametrize('field,value', [('source_kind', 'primary_metric_extract'),
    ('coverage', 'selected_tables'), ('issuer_ticker', 'OTHER'), ('page_count', 201),
    ('available_as_of', '2026-11-06'), ('available_as_of', '2026-00-00'),
    ('source_url', 'https://unrelated.test/FRMO_Annual_Report_2026.pdf'),
    ('contexts', ['Only a derived equity total.'])])
def test_issuer_source_completeness_identity_availability_and_hash_checks_stay_closed(monkeypatch, field, value):
    from underwriting_evidence import evidence_readiness
    p = issuer_annual_packet(monkeypatch)
    p['documents'][0][field] = value
    result = evidence_readiness(p, require_documents=True)
    assert result['status'] == 'evidence_gap'
    assert any(g['code'] == 'annual_primary_document_missing' for g in result['gaps'])


def test_possessives_do_not_consume_actual_transaction_search_terms():
    terms = requested_keywords([{'code': 'transaction_terms', 'detail':
        "Copart's disclosure omits the target's funding. Search 'merger consideration', "
        "'equity awards', 'indebtedness', 'financing' and 'closing conditions'."}])
    assert {'merger consideration', 'equity awards', 'indebtedness', 'financing', 'closing conditions'} <= set(terms)
    assert not any('disclosure omits' in term for term in terms)


def test_quoted_search_phrases_can_contain_a_possessive():
    assert "owner's earnings" in requested_keywords([{'code': 'cash', 'detail':
        'Search terms: "owner\'s earnings", \'cash flow\'.'}])


def test_new_disclosure_requests_retain_earlier_debt_and_settlement_sections():
    from underwriting_evidence import merge_evidence_requests
    old = [{'code':'debt','detail':'Retrieve Note 9, Debt.'}, {'code':'settlement','detail':'Retrieve Note 15, Settlement.'}]
    new = [{'code':'litigation','detail':'Retrieve Note 14, Litigation and annual Note 19.'}]
    merged = merge_evidence_requests(old,new)
    assert {'note 9','note 15','note 14','note 19'} <= set(requested_keywords(merged))
    revised = merge_evidence_requests(merged,[{'code':'debt','detail':'Retrieve updated Note 9, Debt.'}])
    assert len(revised)==3 and revised[-1]['detail'].startswith('Retrieve updated')


def related_packet():
    p = packet()
    p.update(ticker='TARGET', company='Distinct Acquisition Target Inc.', financial_period='2025-09-30',
             latest_report={'period':'2026-06-30','filed':'2026-08-01'})
    p['observations'][0].update(period='2026-06-30', field='cash', measurement_type='balance')
    p['documents'] = [{'id':'target_doc','source_url':'https://www.sec.gov/target','content_hash':'b'*64,'contexts':['Target balance sheet.']}]
    p['packet_hash'] = digest({k:v for k,v in p.items() if k != 'packet_hash'})
    return p


def test_a_delisted_target_is_resolved_from_primary_legal_name_and_sec_submissions(tmp_path, monkeypatch):
    import underwriting_related_evidence as related
    p = packet()
    p['documents'] = [{'id': 'closing', 'source_url': 'https://www.sec.gov/parent', 'content_hash': 'c'*64,
                      'contexts': ['The parent completed its acquisition of ACV Auctions Inc. (ACV).']}]
    target = related_packet()
    target.update(ticker='ACVA', cik='1637873', company='ACV Auctions Inc.')
    calls = []
    class Client:
        def get_json(self, url, **kwargs):
            calls.append(url)
            if url.endswith('company_tickers.json'):
                return {}  # The acquired issuer is absent from the current list.
            if 'efts.sec.gov' in url:
                return {'hits': {'hits': [{'_source': {'ciks': ['0001637873'], 'file_date': '2026-08-01'}}]}}
            if 'CIK0001637873.json' in url:
                return {'cik': '1637873', 'name': 'ACV Auctions Inc.', 'tickers': ['ACVA']}
            pytest.fail('Unexpected source: '+url)
    monkeypatch.setattr(related, 'collect_target', lambda *args, **kwargs: target)
    merged = related.augment_requested_targets(tmp_path, p,
        [{'code': 'acv_target', 'detail': 'Retrieve ACV target primary financials for the acquisition.'}],
        '2026-11-02', Client())
    assert merged['related_issuers']['ACVA']['cik'] == '1637873'
    assert any('efts.sec.gov' in url for url in calls)


@pytest.mark.parametrize('name,tickers', [('Unrelated Corporation', ['WRONG']), ('ACV Auctions Inc.', ['A', 'B'])])
def test_sec_search_does_not_authorize_an_unrelated_issuer_or_ambiguous_listing(name, tickers):
    from underwriting_related_evidence import discover_historical_targets
    p = packet()
    p['documents'] = [{'contexts': ['The parent acquired ACV Auctions Inc.']}]
    class Client:
        def get_json(self, url, **kwargs):
            if 'efts.sec.gov' in url:
                return {'hits': {'hits': [{'_source': {'ciks': ['123'], 'file_date': '2026-01-01'}}]}}
            return {'cik': '123', 'name': name, 'tickers': tickers}
    assert discover_historical_targets(p, 'acquire ACV financials', '2026-11-02', Client()) == []


def test_a_parent_share_class_alias_cannot_become_an_acquisition_target(tmp_path, monkeypatch):
    import json
    import underwriting_related_evidence as related
    p = packet()
    p['company'] = 'Parent Company Inc.'
    p['documents'] = [{'contexts': ['Parent Company Inc. completed an acquisition.']}]
    path = tmp_path / '_system/portfolio/registry.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'holdings': {'TEST': {'download': {'cik': '123'}}}}))
    class Client:
        def get_json(self, url, **kwargs):
            assert url.endswith('company_tickers.json')
            return {'0': {'title': 'Parent Company Inc.', 'ticker': 'TEST-A', 'cik_str': 123}}
    monkeypatch.setattr(related, 'collect_target', lambda *a, **k: pytest.fail('Parent collected as target'))
    result = related.augment_requested_targets(tmp_path, p,
        [{'detail': 'Retrieve Parent acquisition funding.'}], '2026-11-02', Client())
    assert not result.get('related_issuers')


def test_acquisition_evidence_preserves_entity_period_and_excludes_target_share_basis():
    from underwriting_related_evidence import merge_related_packet
    p, target = packet(), related_packet()
    p['documents'] = [{'id':'parent_doc','source_url':'https://www.sec.gov/parent','content_hash':'c'*64,
                       'contexts':['The parent agreed to acquire Distinct Acquisition Target Inc. for cash.']}]
    p['latest_report'] = {'period':'2026-07-31','filed':'2026-09-01'}
    p['packet_hash'] = digest({k:v for k,v in p.items() if k != 'packet_hash'})
    merged = merge_related_packet(p, target)
    assert merged['ticker'] == 'TEST'
    assert merged['related_issuers']['TARGET']['latest_report']['period'] == '2026-06-30'
    assert sum(o['unit']=='shares' for o in merged['observations']) == 1
    selected = next(o for o in merged['observations'] if o.get('issuer_ticker') == 'TARGET')
    assert selected['id'] != p['observations'][0]['id']
    assert merged['packet_hash'] == digest({k:v for k,v in merged.items() if k != 'packet_hash'})
    # Parent and acquired issuer can report on different fiscal calendars.
    c = contract(merged)
    c['facts'].append({'id':'target_cash','observation_id':selected['id']})
    compile_contract(merged,c)


def test_an_unrelated_name_cannot_expand_the_primary_evidence_boundary():
    from underwriting_related_evidence import merge_related_packet
    p=packet()
    p['documents']=[{'id':'parent','contexts':['The parent has no such acquisition.']}]
    with pytest.raises(ContractError,match='acquisition'):
        merge_related_packet(p,related_packet())


def test_generic_words_around_a_transaction_are_not_an_acquired_issuer():
    from underwriting_related_evidence import acquisition_mentioned
    p = {'documents':[{'contexts':['Our liquidity supports the acquisition of ACV Auctions. We provide auction services.']} ]}
    assert acquisition_mentioned(p,'ACV Auctions Inc.')
    assert not acquisition_mentioned(p,'Liquidity Services Inc.')


def test_changed_or_failed_target_collection_invalidates_parent_source_freshness(tmp_path):
    from underwriting_evidence import source_fingerprint
    from underwriting_pipeline import write
    parent = tmp_path/'_system/reference/market-data/valuation_fundamentals/TEST.json'
    cache = tmp_path/'_system/reference/market-data/valuation_related_evidence/TARGET.json'
    write(parent,{'underwriting_related_issuers':{'TARGET':{'source_hash':'original'}}})
    baseline = source_fingerprint(tmp_path,'TEST')
    write(cache,{'source_hash':'original','status':'ready','as_of':'2026-10-30'})
    assert source_fingerprint(tmp_path,'TEST') == baseline
    write(cache,{'source_hash':'changed','status':'ready','as_of':'2026-10-30'})
    assert source_fingerprint(tmp_path,'TEST') != baseline
    write(cache,{'source_hash':'original','status':'collection_failed','as_of':'2026-10-30'})
    assert source_fingerprint(tmp_path,'TEST') != baseline


def test_acquired_issuer_reports_are_rechecked_within_the_same_day(tmp_path,monkeypatch):
    import underwriting_related_evidence as related
    from underwriting_pipeline import write,read
    write(tmp_path/'TEST/research/valuation.json',{'underwriting':{'related_issuers':{'TARGET':{'cik':'123'}}},
                                               'economic_analysis':{'currency':'USD'}})
    calls=[]
    def collect(*args):
        calls.append(args)
        return {'as_of':'2026-10-30','source_hash':str(len(calls)),'status':'ready'}
    monkeypatch.setattr(related,'collect_target',collect)
    related.refresh_related_sources(tmp_path,'TEST','2026-10-30')
    related.refresh_related_sources(tmp_path,'TEST','2026-10-30')
    assert len(calls)==2
    assert read(tmp_path/'_system/reference/market-data/valuation_related_evidence/TARGET.json')['source_hash']=='2'


def test_target_discovery_uses_sec_identity_and_parent_transaction_evidence(tmp_path,monkeypatch):
    import underwriting_related_evidence as related
    from underwriting_pipeline import write
    p=packet()
    p['documents']=[{'id':'parent','content_hash':'c'*64,'contexts':['We agreed to acquire Distinct Acquisition Target Inc. for cash.']}]
    p['packet_hash']=digest({k:v for k,v in p.items() if k!='packet_hash'})
    class Client:
        def get_json(self,url,**kwargs):
            assert url=='https://www.sec.gov/files/company_tickers.json'
            return {'0':{'ticker':'TARGET','title':'Distinct Acquisition Target Inc.','cik_str':123},
                    '1':{'ticker':'OTHER','title':'Unrelated Business Inc.','cik_str':456}}
    calls=[]
    def collect(root,ticker,cik,*args):
        calls.append((ticker,cik))
        t=related_packet();t.update(cik=str(cik),source_hash='source')
        return t
    monkeypatch.setattr(related,'collect_target',collect)
    out=related.augment_requested_targets(tmp_path,p,[{'detail':"Retrieve acquisition financial statements of Distinct Acquisition Target and Unrelated Business."}],'2026-10-30',Client())
    assert calls==[('TARGET',123)]
    assert set(out['related_issuers'])=={'TARGET'}
