"""Registered class quantities need explicit pooled claims and primary income ties."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from underwriting_evidence import document_record, prepare_packet
from underwriting_inline_shares import converted_class_a_observation
from underwriting_contract import ContractError


URL = 'https://www.sec.gov/Archives/edgar/data/1403161/000140316126000134/v-20260930.htm'
QUOTE = {'symbol': 'V', 'calendar': 'XNYS', 'currency': 'USD', 'as_of': '2026-11-05'}
CONVERSION = ('Diluted class A common stock earnings per share calculation includes the assumed '
              'conversion of all class B-1, B-2, B-3 and C common stock and participating securities '
              'on an as-converted basis')


def fixture():
    def context(name, member=''):
        segment = ('<xbrli:segment><xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">'
                   +member+'</xbrldi:explicitMember></xbrli:segment>') if member else ''
        return (f'<xbrli:context id="{name}"><xbrli:entity><xbrli:identifier>0001403161</xbrli:identifier>'
                +segment+'</xbrli:entity><xbrli:period><xbrli:startDate>2025-10-01</xbrli:startDate>'
                '<xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context>')
    def numeric(tag, context, unit, value):
        return (f'<ix:nonFraction name="us-gaap:{tag}" contextRef="{context}" unitRef="{unit}" '
                f'format="ixt:num-dot-decimal" scale="6">{value}</ix:nonFraction>')
    return ('<html><ix:header>'+context('all')+context('a', 'us-gaap:CommonClassAMember')
            +context('preferred', 'us-gaap:PreferredStockMember')
            +'<xbrli:unit id="shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>'
             '<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'
             '</ix:header><ix:nonNumeric name="dei:EntityCentralIndexKey" contextRef="all">0001403161</ix:nonNumeric>'
             '<table><tr><td><ix:nonNumeric name="dei:Security12bTitle" contextRef="a">Class A Common Stock</ix:nonNumeric></td>'
             '<td><ix:nonNumeric name="dei:TradingSymbol" contextRef="a">V</ix:nonNumeric></td>'
             '<td><ix:nonNumeric name="dei:SecurityExchangeName" contextRef="a">New York Stock Exchange</ix:nonNumeric></td></tr></table>'
             '<p>Reported consolidated assets, cash flow and net income.</p>'
            +numeric('NetIncomeLoss', 'all', 'usd', '1000')
            +'<p>Note 16—Earnings Per Share</p><p>'
            +('Reported shares, earnings, capital and income allocation. '*12)+CONVERSION+'.</p><table>'
            +numeric('NetIncomeLossAvailableToCommonStockholdersDiluted', 'a', 'usd', '1000')
            +numeric('WeightedAverageNumberOfDilutedSharesOutstanding', 'a', 'shares', '20')
            +numeric('PreferredStockSharesOutstanding', 'preferred', 'shares', '5')
            +'</table><p>Final EPS footnote: share conversions are issuer-reported.</p>'
             '<p>Note 17—Compensation</p>'+('<p>Next note must not be included. </p>'*1200)+'</html>')


def extract(source=None, quote=None, **metadata):
    raw = (source or fixture()).encode()
    doc = document_record(URL, raw, form='10-K')
    doc.update({'form': '10-K', 'period': '2026-09-30', 'filed': '2026-11-05', **metadata})
    eps = document_record(URL, raw, ['note 16'], form='10-K')
    return converted_class_a_observation(raw, doc, quote or QUOTE, eps['contexts'])


@pytest.mark.parametrize('dash', ['—', '–'])
def test_complete_emdash_note_preserves_conversion_footnotes_and_stops_at_next_note(dash):
    source = fixture().replace(CONVERSION, ('Reported cash and share allocation disclosure. '*700)+CONVERSION)
    source = source.replace('—', dash)
    d = document_record(URL, source.encode(), ['note 16'])
    note = next(c for c in d['contexts'] if c.startswith('Note 16'))
    assert CONVERSION in note
    assert 'Final EPS footnote' in note
    assert 'Next note must not be included' not in note


def test_a_coupon_heading_inside_a_note_cannot_truncate_the_requested_disclosure():
    raw = ('<p>Note 3—Debt</p>'+('<p>Detailed debt, cash and capital obligations.</p>'*400)
           +'<p>4.125% SENIOR NOTES</p>'+('<p>Detailed payment and borrowing provisions.</p>'*400)
           +'<p>Final source-bound payment deadline.</p><p>Note 4—Taxes</p>'
           +'<p>Unrelated next disclosure.</p>').encode()
    d = document_record(URL, raw, ['note 3'])
    assert any(c.startswith('Note 3') and '4.125% SENIOR NOTES' in c
               and 'Final source-bound payment deadline' in c
               and 'Unrelated next disclosure' not in c for c in d['contexts'])


def test_reported_diluted_class_is_not_added_to_other_share_classes():
    p = extract()
    assert p['value'] == 20000000
    assert p['source_url'] == URL and p['field'] == 'shares'
    assert p['period'] == '2026-09-30' and p['start'] == '2025-10-01'
    assert 'all common classes' in p['scope']
    assert CONVERSION in p['_note_context']


@pytest.mark.parametrize('before,after', [
    (CONVERSION, 'No conclusion about conversion is supplied.'),
    ('>1000</ix:nonFraction></p>', '>700</ix:nonFraction></p>'),
    ('us-gaap:CommonClassAMember', 'us-gaap:CommonClassBMember'),
    ('0001403161', '0001403162'),
    ('WeightedAverageNumberOfDilutedSharesOutstanding', 'PreferredStockSharesOutstanding'),
    ('name="us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding"', 'name="v:WeightedAverageNumberOfDilutedSharesOutstanding"'),
    ('unitRef="shares"', 'unitRef="usd"'),
    ('scale="6">20', 'scale="6">-20'),
    ('scale="6">20', 'xsi:nil="true" scale="6">20'),
    ('scale="6">20', 'xsi:nil="TRUE" scale="6">20'),
    ('format="ixt:num-dot-decimal" scale="6">20', 'format="unknown:transform" scale="6">20'),
    ('<xbrli:segment>', '<xbrli:segment><xbrldi:typedMember dimension="x:Other">opaque</xbrldi:typedMember>'),
])
def test_unverified_claims_identity_units_or_values_stay_unadmitted(before, after):
    source = fixture()
    if before == '>1000</ix:nonFraction></p>':
        # Change only the diluted class numerator, preserving consolidated NI.
        before = 'name="us-gaap:NetIncomeLossAvailableToCommonStockholdersDiluted" contextRef="a" unitRef="usd" format="ixt:num-dot-decimal" scale="6">1000'
        after = before[:-4]+'700'
    assert before in source
    assert extract(source.replace(before, after)) is None


def test_identical_inline_repeats_are_allowed_but_conflicting_counts_are_not():
    source = fixture()
    fact = ('<ix:nonFraction name="us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding" '
            'contextRef="a" unitRef="shares" format="ixt:num-dot-decimal" scale="6">20</ix:nonFraction>')
    assert extract(source.replace(fact, fact+fact))['value'] == 20000000
    assert extract(source.replace(fact, fact+fact.replace('>20<', '>21<'))) is None


@pytest.mark.parametrize('change', [
    {'symbol': 'V28'}, {'symbol': 'V.US'}, {'currency': 'EUR'}, {'calendar': 'XNAS'}, {'as_of': '2026-11-04'},
])
def test_only_the_primary_registered_quoted_claim_is_supported(change):
    assert extract(quote={**QUOTE, **change}) is None


def test_changed_source_hash_is_rejected():
    assert extract(content_hash='0'*64) is None


def test_other_registered_common_classes_cannot_borrow_the_class_a_count():
    other = ('<table><tr><td><ix:nonNumeric name="dei:Security12bTitle" contextRef="preferred">Class B Common Stock</ix:nonNumeric></td>'
             '<td><ix:nonNumeric name="dei:TradingSymbol" contextRef="preferred">VB</ix:nonNumeric></td>'
             '<td><ix:nonNumeric name="dei:SecurityExchangeName" contextRef="preferred">New York Stock Exchange</ix:nonNumeric></td></tr></table>')
    assert extract(fixture().replace('</html>', other+'</html>')) is None


def test_primary_registration_context_must_bind_the_same_class():
    source = fixture().replace('name="dei:Security12bTitle" contextRef="a"', 'name="dei:Security12bTitle" contextRef="preferred"')
    source = source.replace('name="dei:TradingSymbol" contextRef="a"', 'name="dei:TradingSymbol" contextRef="preferred"')
    source = source.replace('name="dei:SecurityExchangeName" contextRef="a"', 'name="dei:SecurityExchangeName" contextRef="preferred"')
    assert extract(source) is None


def test_a_new_class_not_covered_by_the_primary_conversion_clause_stays_blocked():
    source = fixture().replace('us-gaap:PreferredStockMember', 'v:CommonClassDMember')
    source = source.replace('us-gaap:PreferredStockSharesOutstanding', 'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding')
    assert extract(source) is None


def test_a_truncated_note_or_missing_next_heading_cannot_prove_complete_claim_scope():
    raw = fixture().encode()
    d = document_record(URL, raw, form='10-K')
    d.update(form='10-K', period='2026-09-30', filed='2026-11-05')
    assert converted_class_a_observation(raw, d, QUOTE, [CONVERSION]) is None
    assert extract(fixture().replace('Note 17—Compensation', 'Unnumbered following text')) is None


def test_quarterly_and_mismatched_money_periods_remain_unsupported():
    assert extract(form='10-Q') is None
    source = fixture().replace('name="us-gaap:NetIncomeLoss"', 'name="us-gaap:OtherIncome"')
    assert extract(source) is None


def packet_root(root):
    def save(name, value):
        p = root/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value))
    save('dashboard/data/core.json', {'tickers': [{'ticker': 'V', 'company': 'Visa'}]})
    save('_system/portfolio/registry.json', {'holdings': {'V': {'download': {'cik': '1403161'}}}})
    market = {'status': 'verified', 'symbol': 'V', 'currency': 'USD', 'source_url': 'https://issuer.test/actions',
              'coverage_start': '2020-01-01', 'coverage_end': '2026-11-05', 'first_trade_date': '2008-03-19', 'events': []}
    save('_system/reference/market-data/valuation_quotes/V.json', {'quote': {**QUOTE, 'value': 1}, 'corporate_actions': market})
    facts = [{'field': f, 'value': v, 'period': '2026-09-30', 'filed': '2026-11-05',
              'currency': 'USD', 'source_url': URL, 'source_kind': 'primary', 'locator': f}
             for f, v in [('ocf', 1000), ('capex', 100)]]
    save('_system/reference/market-data/valuation_fundamentals/V.json',
         {'facts': facts, 'primary_observations': facts, 'report_discovery': {'status': 'verified'},
          'latest_report': {'period': '2026-09-30', 'filed': '2026-11-05', 'source_url': URL}})


class Client:
    def get_json(self, url, **kwargs):
        return {'filings': {'recent': {'form': ['10-K'], 'filingDate': ['2026-11-05'],
                'reportDate': ['2026-09-30'], 'accessionNumber': ['0001403161-26-000134'],
                'primaryDocument': ['v-20260930.htm']}}}

    def get_bytes(self, url, **kwargs):
        assert url == URL
        return fixture().encode()


def test_standard_collector_retains_claim_proof_without_a_secondary_share_fallback(tmp_path):
    packet_root(tmp_path)
    p = prepare_packet(tmp_path, 'V', '2026-11-06', collect=False, client=Client())
    shares = [o for o in p['observations'] if o['unit'] == 'shares']
    assert len(shares) == 1 and shares[0]['value'] == 20000000
    assert 'all common classes' in shares[0]['scope']
    assert p['readiness']['status'] == 'ready'
    assert any(CONVERSION in c for d in p['documents'] for c in d['contexts'])
    assert all(sum(map(len, d['contexts'])) <= 150000 for d in p['documents'])


def test_normal_split_epoch_gate_still_blocks_an_unverified_intervening_action(tmp_path):
    packet_root(tmp_path)
    path = tmp_path/'_system/reference/market-data/valuation_quotes/V.json'
    q = json.loads(path.read_text())
    q['corporate_actions']['events'] = [{'date': '2026-10-01', 'ratio': 2, 'source_url': 'https://issuer.test/split'}]
    path.write_text(json.dumps(q))
    with pytest.raises(ContractError, match='verified share count'):
        prepare_packet(tmp_path, 'V', '2026-11-06', collect=False, client=Client())
