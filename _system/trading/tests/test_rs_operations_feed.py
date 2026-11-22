"""Box R operations feed: pinned R2 S3 read, out-of-process fetcher, cadence."""

import io
import json
import urllib.error

import pytest

from _system.trading.rs_paper_executor import __main__ as cli
from _system.trading.rs_paper_executor import operations_feed as feed
from _system.trading.rs_paper_executor.safety import SafetyError
from _system.trading.rs_paper_executor.inbox import proposals

def fetch_at(source,directory,now,**kwargs):
    kwargs.setdefault('clock',lambda:now)
    return feed.fetch_once(source,directory,now,**kwargs)


ENDPOINT = "https://" + "0123456789abcdef" * 2 + ".r2.cloudflarestorage.com"


@pytest.mark.parametrize("state_at", ["2026-11-19T14:57:59Z", None, "invalid"])
def test_freshly_republished_feed_rejects_stale_or_invalid_underlying_state(state_at):
    snapshot = {"generated_at": "2026-11-19T14:59:55Z", "state_at": state_at,
                "candidates": []}
    with pytest.raises(SafetyError):
        proposals(snapshot, {}, "2026-11-19T15:00:00Z")


def test_feed_accepts_fresh_underlying_state_and_the_legacy_single_clock():
    snapshot = {"generated_at": "2026-11-19T14:59:55Z", "candidates": []}
    assert proposals(snapshot, {}, "2026-11-19T15:00:00Z") == []
    snapshot["state_at"] = "2026-11-19T14:59:00Z"
    assert proposals(snapshot, {}, "2026-11-19T15:00:00Z") == []


def test_sigv4_matches_aws_published_get_object_example():
    # AWS Signature Version 4 documentation, "Example: GET Object".
    headers = {"host": "examplebucket.s3.amazonaws.com", "range": "bytes=0-9",
               "x-amz-content-sha256": feed.EMPTY_SHA256, "x-amz-date": "20130524T000000Z"}
    auth = feed.sigv4_authorization(
        "GET", "/test.txt", headers, key_id="AKIAIOSFODNN7EXAMPLE",
        secret="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", amz_date="20130524T000000Z",
        region="us-east-1")
    assert auth == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request,"
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date,"
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")


@pytest.mark.parametrize("endpoint", [
    "https://evil.example.com", "http://" + "0" * 32 + ".r2.cloudflarestorage.com",
    ENDPOINT + "/", "https://" + "0" * 31 + ".r2.cloudflarestorage.com", None])
def test_only_an_r2_account_endpoint_is_accepted(endpoint):
    with pytest.raises(SafetyError):
        feed.R2Object(endpoint, "id", "secret")


def test_only_the_operations_object_and_never_without_credentials():
    with pytest.raises(SafetyError, match="only Box R's operations object"):
        feed.R2Object(ENDPOINT, "id", "secret", key="collector-dashboard/shadow.json")
    with pytest.raises(SafetyError, match="only Box R's operations object"):
        feed.R2Object(ENDPOINT, "id", "secret", bucket="other")
    with pytest.raises(SafetyError, match="credentials missing"):
        feed.R2Object.from_env({"RS_OPERATIONS_S3_ENDPOINT": ENDPOINT})
    assert "secret" not in repr(feed.R2Object(ENDPOINT, "id", "secret"))


class Response(io.BytesIO):
    def __init__(self, body, etag='"e1"'):
        super().__init__(body)
        self.headers = {"ETag": etag}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Opener:
    def __init__(self, *answers):
        self.answers, self.requests = list(answers), []

    def open(self, request, timeout):
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, int):
            raise urllib.error.HTTPError(request.full_url, answer, "x", {}, None)
        return Response(answer)


def test_receipt_time_is_after_download_and_bound_to_publisher_ack(tmp_path):
    import hashlib
    key = 'collector-dashboard/operations-receipts/2026-11-23/11111111-1111-4111-8111-111111111111.json'
    payload = json.dumps({'generated_at':'2026-11-23T14:30:00Z',
                          'state_at':'2026-11-23T14:29:30Z', 'candidates':[],
                          'publication':{'id':'11111111-1111-4111-8111-111111111111',
                                         'receipt_key':key}}).encode()
    receipt = json.dumps({'schema':'rs_operations_publication_receipt.v1',
                          'publication_id':'11111111-1111-4111-8111-111111111111',
                          'report_sha256':hashlib.sha256(payload).hexdigest(),
                          'generated_at':'2026-11-23T14:30:00Z',
                          'state_at':'2026-11-23T14:29:30Z',
                          'upload_started_at':'2026-11-23T14:30:01Z',
                          'upload_completed_at':'2026-11-23T14:30:02Z',
                          'max_state_age_seconds':75,
                          'accepted':True}).encode()
    source = feed.R2Object(ENDPOINT,'id','secret',opener=Opener(payload,receipt))
    fetch_at(source,tmp_path,'2026-11-23T14:30:10Z',clock=lambda:'2026-11-23T14:30:13Z')
    _,meta=feed.read_local(tmp_path/'operations.json')
    assert meta['request_started_at']=='2026-11-23T14:30:10Z'
    assert meta['received_at']=='2026-11-23T14:30:13Z'
    assert meta['publish_receipt']['upload_completed_at']=='2026-11-23T14:30:02Z'
    assert meta['publication_to_receipt_seconds']==11


def test_reader_keeps_previous_committed_generation_during_report_metadata_swap(tmp_path,monkeypatch):
    source=feed.R2Object(ENDPOINT,'id','secret',opener=Opener(
        body('2026-11-23T14:30:00Z'),body('2026-11-23T14:30:10Z')))
    fetch_at(source,tmp_path,'2026-11-23T14:30:01Z')
    original=feed._atomic_write
    def interleaved(path,data):
        original(path,data)
        if path.name=='operations.json':
            clocks,_=feed.read_local_clocks(path)
            assert clocks['generated_at']=='2026-11-23T14:30:00Z'
    monkeypatch.setattr(feed,'_atomic_write',interleaved)
    fetch_at(source,tmp_path,'2026-11-23T14:30:11Z')


def test_receipt_is_mandatory_when_the_dated_observation_requires_it(tmp_path):
    source=feed.R2Object(ENDPOINT,'id','secret',opener=Opener(body('2026-11-23T14:30:00Z')),require_receipt=True)
    with pytest.raises(SafetyError,match='receipt required'):
        fetch_at(source,tmp_path,'2026-11-23T14:30:01Z')
    assert not (tmp_path/'operations.meta.json').exists()


def test_replayed_older_state_cannot_replace_a_newer_local_generation(tmp_path):
    source=feed.R2Object(ENDPOINT,'id','secret',opener=Opener(body('2026-11-23T14:30:10Z'),body('2026-11-23T14:30:00Z')))
    fetch_at(source,tmp_path,'2026-11-23T14:30:11Z')
    with pytest.raises(SafetyError,match='regressed'):
        fetch_at(source,tmp_path,'2026-11-23T14:30:12Z')
    assert feed.read_local(tmp_path/'operations.json')[0]['generated_at']=='2026-11-23T14:30:10Z'


def test_duplicate_download_does_not_retime_the_first_receipt(tmp_path):
    payload=body('2026-11-23T14:30:00Z')
    source=feed.R2Object(ENDPOINT,'id','secret',opener=Opener(payload,payload))
    fetch_at(source,tmp_path,'2026-11-23T14:30:01Z')
    fetch_at(source,tmp_path,'2026-11-23T14:30:10Z')
    assert feed.read_local(tmp_path/'operations.json')[1]['received_at']=='2026-11-23T14:30:01Z'


@pytest.mark.parametrize('change',[{'accepted':False},{'report_sha256':'0'*64},
                                  {'max_state_age_seconds':180},{'state_at':'2026-11-23T14:20:00Z'}])
def test_invalid_publisher_receipt_never_replaces_a_good_local_generation(tmp_path,change):
    import hashlib
    identifier='11111111-1111-4111-8111-111111111111'
    key='collector-dashboard/operations-receipts/2026-11-23/'+identifier+'.json'
    payload=json.dumps({'generated_at':'2026-11-23T14:30:00Z','state_at':'2026-11-23T14:29:30Z',
                        'publication':{'id':identifier,'receipt_key':key},'candidates':[]}).encode()
    proof={'schema':'rs_operations_publication_receipt.v1','publication_id':identifier,
           'report_sha256':hashlib.sha256(payload).hexdigest(),'accepted':True,
           'state_at':'2026-11-23T14:29:30Z','generated_at':'2026-11-23T14:30:00Z',
           'upload_started_at':'2026-11-23T14:30:01Z','upload_completed_at':'2026-11-23T14:30:02Z',
           'max_state_age_seconds':75,**change}
    source=feed.R2Object(ENDPOINT,'id','secret',opener=Opener(body('2026-11-23T14:29:20Z'),payload,json.dumps(proof).encode()))
    fetch_at(source,tmp_path,'2026-11-23T14:29:21Z')
    with pytest.raises(SafetyError):fetch_at(source,tmp_path,'2026-11-23T14:30:03Z')
    assert feed.read_local(tmp_path/'operations.json')[0]['generated_at']=='2026-11-23T14:29:20Z'


def body(generated_at, candidates=2):
    return json.dumps({"generated_at": generated_at,
                       "candidates": [{} for _ in range(candidates)]}).encode()


def test_signed_get_of_the_pinned_object_with_conditional_refetch():
    opener = Opener(body("2026-11-19T15:00:00+00:00"), 304)
    source = feed.R2Object(ENDPOINT, "KEYID", "SECRET", opener=opener)
    status, data, etag = source.get("2026-11-19T15:00:05+00:00")
    assert status == 200 and etag == '"e1"'
    req = opener.requests[0]
    assert req.full_url == ENDPOINT + "/single-stock-reverse-splits-evidence/collector-dashboard/operations.json"
    auth = req.get_header("Authorization")
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=KEYID/20261119/auto/s3/aws4_request,")
    assert "SECRET" not in auth and req.get_method() == "GET"
    assert source.get("2026-11-19T15:00:10+00:00", etag) == (304, None, '"e1"')
    assert opener.requests[1].get_header("If-none-match") == '"e1"'


def test_fetch_keeps_producer_and_download_clocks_apart(tmp_path):
    opener = Opener(body("2026-11-19T15:00:00+00:00"), 304, body("2026-11-19T15:00:30+00:00", 3))
    source = feed.R2Object(ENDPOINT, "id", "secret", opener=opener)
    fetch_at(source, tmp_path, "2026-11-19T15:00:04+00:00")
    assert fetch_at(source, tmp_path, "2026-11-19T15:00:09+00:00")["changed"] is False
    fetch_at(source, tmp_path, "2026-11-19T15:00:36+00:00")
    data, meta = feed.read_local(tmp_path / "operations.json")
    assert data["generated_at"] == "2026-11-19T15:00:30+00:00"
    assert meta["source_generated_at"] == "2026-11-19T15:00:30+00:00"
    assert meta["downloaded_at"] == "2026-11-19T15:00:36+00:00" and meta["candidates"] == 3
    rows = [json.loads(x) for x in (tmp_path / "cadence" / "2026-11-19.jsonl").read_text().splitlines()]
    assert [r["interval_seconds"] for r in rows] == [None, 30.0]
    assert rows[1]["download_lag_seconds"] == 6.0
    report = feed.cadence_report(tmp_path, "2026-11-19")
    assert report["publications_seen"] == 2 and report["share_within_30s"] == 1.0


def test_clock_monitor_uses_bound_download_metadata_without_reparsing_catalog(tmp_path, monkeypatch):
    payload=json.dumps({"generated_at":"2026-11-20T15:21:57Z", "state_at":"2026-11-20T15:21:00Z", "candidates":[{}]*1000}).encode()
    source=feed.R2Object(ENDPOINT,"id","secret",opener=Opener(payload))
    fetch_at(source,tmp_path,"2026-11-20T15:22:00Z")
    path=tmp_path/"operations.json"
    read=type(path).read_bytes
    def bounded_read(target):
        if target==path:pytest.fail("The clock monitor reparsed the full catalog while a new report could replace it")
        return read(target)
    monkeypatch.setattr(type(path),"read_bytes",bounded_read)
    clocks,meta=feed.read_local_clocks(path)
    assert clocks=={"generated_at":"2026-11-20T15:21:57Z", "state_at":"2026-11-20T15:21:00Z"}
    assert meta["downloaded_at"]=="2026-11-20T15:22:00Z"


def test_clock_metadata_never_attests_to_a_different_report_file(tmp_path):
    payload=json.dumps({"generated_at":"2026-11-20T15:21:57Z", "state_at":"2026-11-20T15:21:00Z", "candidates":[]}).encode()
    source=feed.R2Object(ENDPOINT,"id","secret",opener=Opener(payload))
    fetch_at(source,tmp_path,"2026-11-20T15:22:00Z")
    path=tmp_path/"operations.json"
    path.write_bytes(body("2026-11-20T15:22:15Z"))
    with pytest.raises(SafetyError,match="metadata|replaced"):
        feed.read_local_clocks(path)


@pytest.mark.parametrize("bad", [b"{", json.dumps({"candidates": []}).encode(),
                                 json.dumps({"generated_at": "2026-11-19T15:00:00Z", "state_at": None}).encode(),
                                 json.dumps({"generated_at": "2026-11-19T15:00:00Z", "state_at": "bad"}).encode(),
                                 json.dumps({"generated_at": "no clock"}).encode()])
def test_a_snapshot_without_a_producer_clock_never_replaces_the_good_copy(tmp_path, bad):
    source = feed.R2Object(ENDPOINT, "id", "secret",
                           opener=Opener(body("2026-11-19T15:00:00+00:00"), bad))
    fetch_at(source, tmp_path, "2026-11-19T15:00:04+00:00")
    with pytest.raises((SafetyError, ValueError)):
        fetch_at(source, tmp_path, "2026-11-19T15:00:09+00:00")
    assert json.loads((tmp_path / "operations.json").read_bytes())["generated_at"] \
        == "2026-11-19T15:00:00+00:00"


def test_fetcher_records_errors_and_backs_off_instead_of_exiting(tmp_path):
    source = feed.R2Object(ENDPOINT, "id", "secret", opener=Opener(403, 403, body("2026-11-19T15:00:00+00:00")))
    sleeps, ticks = [], iter(["2026-11-19T15:00:0%d+00:00" % i for i in [0,1,2,2,2,2]])
    feed.run_fetcher(source, tmp_path, poll_seconds=5, clock=lambda: next(ticks),
                     sleep=sleeps.append, stop=lambda: len(sleeps) >= 3)
    assert sleeps == [10, 20, 5]
    status = json.loads((tmp_path / "operations.status.json").read_text())
    assert status["last_error"] is None and status["last_success_at"] == "2026-11-19T15:00:02+00:00"


def test_cli_fetch_once_reports_freshness_without_a_broker(tmp_path, capsys, monkeypatch):
    from datetime import datetime, timezone
    from _system.trading.tests.test_rs_live_guards import live_config

    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(feed.R2Object, "from_env", classmethod(
        lambda cls, environ=None: cls(ENDPOINT, "id", "secret", opener=Opener(body(now)))))
    path = tmp_path / "c.json"
    path.write_text(json.dumps(live_config(tmp_path)))
    argv = ["operations-fetch", "--config", str(path), "--feed-dir", str(tmp_path / "feed"), "--once"]
    assert cli.main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["fresh_within_120s"] is True and out["broker_connection_opened"] is False
    assert cli.main(["operations-cadence", "--config", str(path), "--feed-dir",
                     str(tmp_path / "feed"), "--day", now[:10]]) == 0
