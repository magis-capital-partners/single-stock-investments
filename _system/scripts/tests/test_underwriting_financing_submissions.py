"""Complete issuer-bound financing exhibits within the existing fetch budget."""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from underwriting_primary_references import collect_requested_documents

CIK='1652044'
PARENT='https://www.sec.gov/Archives/edgar/data/1652044/000165204426000018/report.htm'


def filing(number=101, filed='2026-02-13', **changes):
    return {'form':'8-K','filingDate':filed,'items':'8.01,9.01',
            'accessionNumber':f'0001652044-26-{number:06d}', 'primaryDocument':f'report-{number}.htm'} | changes


def submissions(*rows):
    return {'filings':{'recent':{key:[row[key] for row in rows] for key in filing()}}}


def package(row, *, cik=CIK, accession=None, omit_end=False):
    acc=accession or row['accessionNumber']
    bodies=[('8-K',row['primaryDocument'],
             'Item 8.01. Other Events. Senior Notes Offering. '+ 'Full issuer disclosure. '*40),
            ('EX-4.2','note-one.htm','First operative provision. '+'Complete first note terms. '*40+'Final first provision.'),
            ('EX-4.3','note-two.htm','Second operative provision. '+'Complete second note terms. '*40+'Final second provision.'),
            ('GRAPHIC','image.jpg','Not a financial/legal document.')]
    raw=(f'<SEC-DOCUMENT>{acc}.txt\n<SEC-HEADER>\nACCESSION NUMBER: {acc}\n'
         f'CONFORMED SUBMISSION TYPE: {row["form"]}\nFILED AS OF DATE: {row["filingDate"].replace("-","")}\n'
         f'PUBLIC DOCUMENT COUNT: {len(bodies)}\nFILER:\nCENTRAL INDEX KEY: {cik}\n</SEC-HEADER>\n')
    for i,(kind,name,body) in enumerate(bodies,1):
        raw+=f'<DOCUMENT>\n<TYPE>{kind}\n<SEQUENCE>{i}\n<FILENAME>{name}\n<TEXT>\n<html><p>{body}</p></html>\n</TEXT>\n</DOCUMENT>\n'
    if not omit_end:raw+='</SEC-DOCUMENT>'
    return raw.encode()


def collect(rows, fetch, keywords=('2026 us dollar notes','maturities')):
    return collect_requested_documents(submissions(*rows),CIK,'2026-11-07',
        [{'source_url':PARENT,'raw':b'', 'filed':'2026-02-05','form':'10-K'}],list(keywords),fetch)


def test_current_issuance_request_collects_complete_authenticated_note_exhibits():
    row=filing();raw=package(row);calls=[]
    def fetch(url):calls.append(url);return raw
    docs,errors=collect([row],fetch)
    assert not errors and len(calls)==1
    assert calls[0].endswith('/000165204426000101/0001652044-26-000101.txt')
    assert len(docs)==3  # primary disclosure and both complete EX-4 instruments
    text=' '.join(' '.join(d['contexts']) for d in docs)
    assert 'Final first provision.' in text and 'Final second provision.' in text
    assert 'Not a financial/legal document.' not in text
    assert all(d['content_hash']==hashlib.sha256(raw).hexdigest() for d in docs)
    assert all(d['source_url']==calls[0] for d in docs)
    assert len({d['id'] for d in docs})==3
    assert all(d['filed']=='2026-02-13' and 'period' not in d for d in docs)
    assert all(d['coverage']=='complete_requested_primary_document' for d in docs)


@pytest.mark.parametrize('mutate',[
    lambda r:package(r,cik='999999'),
    lambda r:package(r,accession='0001652044-26-999999'),
    lambda r:package(r,omit_end=True),
    lambda r:package(r).replace(b'PUBLIC DOCUMENT COUNT: 4',b'PUBLIC DOCUMENT COUNT: 5'),
    lambda r:package(r).replace(b'CONFORMED SUBMISSION TYPE: 8-K',b'CONFORMED SUBMISSION TYPE: 10-K'),
    lambda r:package(r).replace(b'FILED AS OF DATE: 20260213',b'FILED AS OF DATE: 20260214'),
    lambda r:package(r).replace(b'note-two.htm',b'note-one.htm'),
    lambda r:package(r).replace(b'note-two.htm',b'note-two.pdf'),
    lambda r:package(r).replace(b'Final second provision.',b'X'*350001),
])
def test_conflicting_or_incomplete_submission_identity_blocks_collection(mutate):
    row=filing();docs,errors=collect([row],lambda url:mutate(row))
    assert not docs and errors


def test_current_financing_discovery_rejects_future_malformed_and_other_year_rows():
    rows=[filing(filed='2027-01-01'),filing(102,accessionNumber='../escape'),
          filing(103,primaryDocument='../report.htm'),filing(104,filed='2025-03-01')]
    def fetch(url):raise AssertionError('Unsupported source must not be fetched: '+url)
    assert collect(rows,fetch)==([],[])


def test_failed_package_capture_remains_an_explicit_readiness_blocker():
    from underwriting_evidence import evidence_readiness
    from test_underwriting_pipeline import packet as ready_packet
    def fetch(url):raise OSError('primary submission unavailable')
    docs,errors=collect([filing()],fetch)
    assert not docs and errors
    p=ready_packet();p['collection_errors']=errors
    assert evidence_readiness(p)['status']=='evidence_gap'


def test_generic_credit_requests_do_not_fetch_every_current_report():
    def fetch(url):raise AssertionError('No explicit dated issuance request')
    assert collect([filing()],fetch,keywords=('credit agreement','covenants'))==([],[])


def test_conflicting_discovery_cannot_choose_an_arbitrary_filing_identity():
    def fetch(url):raise AssertionError('Conflicting metadata must not reach fetch')
    docs,errors=collect([filing(),filing(filed='2026-02-14')],fetch)
    assert not docs and errors[0]['source']=='requested_financing_discovery'


def test_security_cover_cannot_turn_a_stock_offering_into_requested_note_evidence():
    row=filing()
    raw=package(row).replace(b'Item 8.01. Other Events. Senior Notes Offering.',
                            b'Securities registered: Senior Notes Offering. Item 8.01. Other Events. Common Stock Offering.')
    docs,errors=collect([row],lambda url:raw)
    assert not errors and not docs


def test_financing_packages_keep_eight_fetch_limit_and_report_uncollected_candidates():
    rows=[filing(101+i) for i in range(10)];calls=[]
    def fetch(url):
        calls.append(url)
        row=next(r for r in rows if r['accessionNumber']+'.txt' in url)
        return package(row)
    docs,errors=collect(rows,fetch)
    assert len(calls)==8 and len(set(calls))==8
    assert len(docs)==24
    assert any(e['source']=='requested_financing_source_budget' for e in errors)
