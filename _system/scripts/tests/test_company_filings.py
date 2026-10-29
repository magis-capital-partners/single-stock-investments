import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backfill_company_filings import eligible, recover, cached_filing, candidates, fingerprint
from company_source_cache import pack, restore

URL = 'https://www.sec.gov/Archives/edgar/data/1/0001/company.htm'


class Client:
    def get_bytes(self, url, **kwargs):
        return b'<html><body><h1>Company filing</h1><p>Revenue and operating results.</p></body></html>'


def test_original_and_text_integrity_survive_private_archive(tmp_path):
    cache = tmp_path/'cache'
    assert recover(cache, URL, Client()) == 'indexed'
    doc = cached_filing(cache, URL)
    assert b'Company filing' in base64.b64decode(doc['original_base64'])
    assert 'Revenue' in doc['text']
    pack(cache, tmp_path/'archive')
    restore(tmp_path/'archive', tmp_path/'restored')
    assert cached_filing(tmp_path/'restored', URL) == doc
    path = cache/'filings'/(fingerprint(URL)+'.json')
    doc['text'] = 'tampered'
    path.write_text(json.dumps(doc))
    assert cached_filing(cache, URL) == {}


def test_only_catalogued_pending_official_edgar_documents_are_eligible(tmp_path):
    assert eligible(URL)
    for url in ('http://www.sec.gov/Archives/edgar/data/1', 'https://evil.example/Archives/edgar/data/1', 'https://www.sec.gov.evil.example/Archives/edgar/data/1', 'https://www.sec.gov@localhost/Archives/edgar/data/1'):
        assert not eligible(url)
    row = {'processing_status':'awaiting_extraction','locations':[{'kind':'filing','url':URL}]}
    (tmp_path/'index.json').write_text(json.dumps({'record_parts':['records.json']}))
    (tmp_path/'records.json').write_text(json.dumps({'pending':row,'done':{**row,'processing_status':'indexed'},'removed':{**row,'availability':'removed_or_unavailable'}}))
    assert candidates(tmp_path) == [URL]


def test_policy_response_is_not_research_text(tmp_path):
    class Blocked:
        def get_bytes(self, *args, **kwargs):
            return b'<html>Your Request Originates from an Undeclared Automated Tool</html>'
    assert recover(tmp_path, URL, Blocked()) == 'access_unavailable'
    assert not cached_filing(tmp_path, URL)['text']


def test_recovered_filings_stay_with_issuer(tmp_path):
    from build_company_research import Builder
    cache=tmp_path/'cache'
    recover(cache, URL, Client())
    folder=tmp_path/'AAA/investor-documents'
    folder.mkdir(parents=True)
    (folder/'DOWNLOAD_MANIFEST.json').write_text(json.dumps([{'url':URL,'form':'10-K'}]))
    build=Builder(tmp_path,None,tmp_path/'out',cache,companies={'AAA':{'company':'Company filing'},'BBB':{'company':'Revenue and operating results'}})
    build.filings('AAA')
    record=next(iter(build.index.records.values()))
    assert record['processing_status']=='indexed'
    assert [r['ticker'] for r in record['relationships']]==['AAA']
