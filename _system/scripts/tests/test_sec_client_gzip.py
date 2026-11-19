"""Compressed SEC responses preserve the exact semantic body and rate policy."""
import gzip
from io import BytesIO
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sec_client

def test_sec_client_negotiates_and_decodes_transfer_gzip(monkeypatch):
    payload=b'{"cik":1,"facts":{}}'
    class Response(BytesIO):
        headers={"Content-Encoding":"gzip"}
    def open_request(request,timeout):
        assert request.get_header("Accept-encoding")=="gzip"
        assert "@" in request.get_header("User-agent")
        return Response(gzip.compress(payload))
    monkeypatch.setattr(sec_client.urllib.request,"urlopen",open_request)
    client=sec_client.SecClient();client._pause=lambda:None
    assert client.get_json("https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json")=={"cik":1,"facts":{}}

def test_uncompressed_body_and_gzip_file_without_transfer_encoding_are_unchanged(monkeypatch):
    class Response(BytesIO):headers={}
    payload=gzip.compress(b'archived bytes')
    monkeypatch.setattr(sec_client.urllib.request,"urlopen",lambda *a,**kw:Response(payload))
    client=sec_client.SecClient();client._pause=lambda:None
    assert client.get_bytes("https://www.sec.gov/example.gz")==payload
