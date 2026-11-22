"""Box R's operations snapshot, fetched OUTSIDE the executor process.

The executor's run loop must never wait on the network. ``urllib`` blocks, and a
read inside the loop stalls ib_insync's event loop, and with it position
protection, for up to the read timeout. A separate fetcher process
(``operations-fetch``, unit ``rs-live-operations``) holds the only credential,
polls the one object, and writes into its feed directory:

* ``operations.json``: Box R's bytes, unchanged. The executor still checks the
  producer's ``generated_at`` against its 120 s rule.
* ``operations.meta.json``: ``source_generated_at``, the producer's clock, and
  ``downloaded_at``, ours. They are kept apart and never merged.
* ``cadence/<ET day>.jsonl``: one row per NEW ``generated_at``, holding the
  measured publication interval and the download lag.
* ``operations.status.json``: the last attempt, the last success and the last
  error (never a secret).

Authentication: Cloudflare's bucket-scoped "Object Read only" R2 tokens work only
with R2's S3-compatible API, not the Cloudflare REST API (developers.cloudflare.com/r2/api/tokens/).
So this signs one SigV4 GET (region ``auto``) of the pinned bucket and key. That
token can read every object in the bucket; this code reads exactly one.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from .safety import SafetyError, timestamp

BUCKET = "single-stock-reverse-splits-evidence"
KEY = "collector-dashboard/operations.json"
ENDPOINT_RE = re.compile(r"^https://([0-9a-f]{32})\.r2\.cloudflarestorage\.com$")
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
MAX_BYTES = 16_000_000
RECEIPT_KEY = re.compile(r'^collector-dashboard/operations-receipts/\d{4}-\d{2}-\d{2}/([a-f0-9-]{36})\.json$')
FRESH_SECONDS = 120  # the executor's rule (inbox.proposals); reported, never changed here
ENV = ("RS_OPERATIONS_S3_ENDPOINT", "RS_OPERATIONS_ACCESS_KEY_ID",
       "RS_OPERATIONS_SECRET_ACCESS_KEY")


def _hmac(key, text):
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).digest()


def sigv4_authorization(method, path, headers, *, key_id, secret, amz_date,
                        region="auto", service="s3", query=""):
    """AWS Signature Version 4 ``Authorization`` value for one request.

    ``headers`` are the signed headers: lowercase names, including ``host``,
    ``x-amz-date`` and ``x-amz-content-sha256``."""
    names = sorted(headers)
    canonical_headers = "".join(
        n + ":" + " ".join(str(headers[n]).split()) + "\n" for n in names)
    signed = ";".join(names)
    canonical = "\n".join([method, path, query, canonical_headers, signed,
                           headers["x-amz-content-sha256"]])
    day = amz_date[:8]
    scope = "/".join([day, region, service, "aws4_request"])
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode("utf-8")).hexdigest()])
    key = _hmac(("AWS4" + secret).encode("utf-8"), day)
    for part in (region, service, "aws4_request"):
        key = _hmac(key, part)
    signature = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return ("AWS4-HMAC-SHA256 Credential=" + key_id + "/" + scope
            + ",SignedHeaders=" + signed + ",Signature=" + signature)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SafetyError("operations object redirect forbidden")


class R2Object:
    """GET of Box R's operations object over R2's S3 API, and nothing else."""

    def __init__(self, endpoint, key_id, secret, *, bucket=BUCKET, key=KEY, opener=None, require_receipt=False):
        if not ENDPOINT_RE.match(endpoint or ""):
            raise SafetyError(
                "R2 endpoint must be https://<32-hex account id>.r2.cloudflarestorage.com")
        if bucket != BUCKET or key != KEY:
            raise SafetyError("only Box R's operations object may be read")
        if not key_id or not secret:
            raise SafetyError("R2 read credentials are not set")
        self.host = urllib.parse.urlsplit(endpoint).hostname
        self.path = urllib.parse.quote("/" + bucket + "/" + key, safe="/-_.~")
        self._key_id, self._secret = key_id, secret
        self._opener = opener or urllib.request.build_opener(_NoRedirect)
        self.require_receipt = require_receipt

    @classmethod
    def from_env(cls, environ=None, **kw):
        environ = os.environ if environ is None else environ
        missing = [k for k in ENV if not environ.get(k)]
        if missing:
            raise SafetyError("operations feed credentials missing: " + ", ".join(missing))
        kw.setdefault('require_receipt',environ.get('RS_OPERATIONS_REQUIRE_RECEIPT')=='1')
        return cls(*(environ[k] for k in ENV), **kw)

    def __repr__(self):  # never print the credential
        return "R2Object(" + self.host + self.path + ")"

    def get(self, now, etag=None):
        """(status, body bytes or None, etag). 304 means unchanged."""
        return self._get(self.path,now,etag)

    def get_receipt(self,key,now):
        if not RECEIPT_KEY.fullmatch(key or ''):
            raise SafetyError('publication receipt key is outside the allowed prefix')
        path=urllib.parse.quote('/'+BUCKET+'/'+key,safe='/-_.~')
        return self._get(path,now,maximum=64000,timeout=3)[1]

    def get_audit(self,day,now):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):
            raise SafetyError('invalid publication audit day')
        path=urllib.parse.quote('/'+BUCKET+'/collector-dashboard/operations-audit/'+day+'.jsonl',safe='/-_.~')
        return self._get(path,now,maximum=32000000)[1]

    def _get(self,path,now,etag=None,maximum=MAX_BYTES,timeout=10):
        amz_date = timestamp(now).strftime("%Y%m%dT%H%M%SZ")
        signed = {"host": self.host, "x-amz-content-sha256": EMPTY_SHA256,
                  "x-amz-date": amz_date}
        headers = {"x-amz-content-sha256": EMPTY_SHA256, "x-amz-date": amz_date,
                   "Authorization": sigv4_authorization(
                       "GET", path, signed, key_id=self._key_id,
                       secret=self._secret, amz_date=amz_date)}
        if etag:
            headers["If-None-Match"] = etag  # unsigned on purpose; S3 permits it
        request = urllib.request.Request("https://" + self.host + path, headers=headers)
        try:
            with self._opener.open(request, timeout=timeout) as response:
                body = response.read(maximum + 1)
                tag = response.headers.get("ETag")
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return 304, None, etag
            label='operations object' if path==self.path else 'publication evidence'
            raise SafetyError(label+" GET returned HTTP " + str(exc.code)) from None
        if len(body) > maximum:
            raise SafetyError("operations object exceeds the input limit")
        return 200, body, tag


def _atomic_write(path, data):
    path = Path(path)
    tmp = path.with_name("." + path.name + ".tmp")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _et_day(now):
    return timestamp(now).astimezone(ZoneInfo("America/New_York")).date().isoformat()


def _state(directory):
    try:
        return json.loads((Path(directory) / "operations.meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _status(directory, now, **fields):
    path = Path(directory) / "operations.status.json"
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    old.update({"schema": "rs_operations_feed_status.v1", "last_attempt_at": now, **fields})
    _atomic_write(path, json.dumps(old, sort_keys=True).encode("utf-8"))


def _event(directory,now,**fields):
    target=Path(directory)/'events';target.mkdir(exist_ok=True)
    with (target/(_et_day(now)+'.jsonl')).open('a',encoding='utf-8') as handle:
        handle.write(json.dumps({'at':now,**fields},sort_keys=True)+'\n')


def publication_receipt(source,data,body,now):
    publication=data.get('publication')
    if publication is None:
        if getattr(source,'require_receipt',False):
            raise SafetyError('publication receipt required; legacy clock-only report refused')
        return None
    key=publication.get('receipt_key');match=RECEIPT_KEY.fullmatch(key or '')
    if not match or match[1]!=publication.get('id'):
        raise SafetyError('publication receipt identity invalid')
    proof=json.loads(source.get_receipt(key,now))
    if (proof.get('schema')!='rs_operations_publication_receipt.v1'
        or proof.get('publication_id')!=publication['id']
        or proof.get('report_sha256')!=hashlib.sha256(body).hexdigest()
        or proof.get('accepted') is not True):
        raise SafetyError('publication receipt does not accept these report bytes')
    for field in ('state_at','generated_at'):
        if timestamp(proof.get(field))!=timestamp(data.get(field)):
            raise SafetyError('publication receipt source clocks differ')
    started,completed=timestamp(proof.get('upload_started_at')),timestamp(proof.get('upload_completed_at'))
    guard=proof.get('max_state_age_seconds')
    age=(completed-timestamp(data['state_at'])).total_seconds()
    if (isinstance(guard,bool) or not isinstance(guard,(int,float)) or not 0<guard<=120
        or completed<started or not -2<=age<=guard
        or (completed-timestamp(now)).total_seconds()>2):
        raise SafetyError('publication receipt age guard or clocks invalid')
    return proof


def fetch_once(source, directory, now, *, clock=None):
    """One poll. Writes the snapshot only when it parses and carries a clock."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    clock=clock or utc_now
    meta = _state(directory)
    status, body, etag = source.get(now, meta.get("etag"))
    received=clock()  # immediately after the complete response body, before parsing/fsync
    if status == 304:
        _status(directory, now, last_success_at=received, last_error=None, changed=False)
        _event(directory,received,event='fetch',request_started_at=now,received_at=received,http_status=304,changed=False)
        return {"changed": False, "source_generated_at": meta.get("source_generated_at")}
    data = json.loads(body)
    generated = data.get("generated_at") if isinstance(data, dict) else None
    timestamp(generated)  # a snapshot without a producer clock is never published
    state_at = data.get("state_at", generated)
    timestamp(state_at)  # explicit null/invalid state clocks never replace a good copy
    try:proof=publication_receipt(source,data,body,clock())
    except Exception as exc:
        _event(directory,clock(),event='receipt_rejected',request_started_at=now,received_at=received,report_sha256=hashlib.sha256(body).hexdigest(),reason=str(exc)[:200])
        raise
    previous = meta.get("source_generated_at")
    if meta.get('source_state_at'):
        old_state,new_state=timestamp(meta['source_state_at']),timestamp(state_at)
        if new_state<old_state or (new_state==old_state and previous and timestamp(generated)<timestamp(previous)):
            raise SafetyError('operations source generation regressed')
    digest=hashlib.sha256(body).hexdigest()
    if digest==meta.get('sha256'):
        _status(directory,now,last_success_at=received,last_error=None,changed=False)
        _event(directory,received,event='fetch',request_started_at=now,received_at=received,http_status=200,changed=False,report_sha256=digest)
        return {'changed':False,'source_generated_at':generated}
    _atomic_write(directory / "operations.json", body)
    versions=directory/'versions';versions.mkdir(exist_ok=True)
    generation=versions/(digest+'.json')
    if not generation.exists():os.link(directory/'operations.json',generation)
    report_stat = generation.stat()
    new_meta = {"schema": "rs_operations_feed_meta.v2", "source_generated_at": generated,
                "source_state_at": state_at,
                "request_started_at":now,"received_at":received,"downloaded_at":received,
                "generation_file":'versions/'+generation.name,"sha256":digest,
                "bytes": len(body), "etag": etag,
                "report_mtime_ns": report_stat.st_mtime_ns,
                "report_inode": report_stat.st_ino,
                "candidates": len(data.get("candidates") or [])}
    if proof:
        new_meta['publish_receipt']=proof
        new_meta['publication_to_receipt_seconds']=(timestamp(received)-timestamp(proof['upload_completed_at'])).total_seconds()
        new_meta['clock_precision']='publisher_ack_and_complete_body_receipt'
        receipts=directory/'receipts';receipts.mkdir(exist_ok=True)
        _atomic_write(receipts/(proof['publication_id']+'.json'),json.dumps(proof,sort_keys=True).encode())
    else:new_meta['clock_precision']='legacy_missing_publish_receipt'
    _atomic_write(directory / "operations.meta.json",
                  json.dumps(new_meta, sort_keys=True).encode("utf-8"))
    if generated != previous:
        row = {"source_generated_at": generated, "downloaded_at": received,
               "request_started_at":now,"received_at":received,
               "download_lag_seconds": round(
                   (timestamp(received) - timestamp(generated)).total_seconds(), 1),
               "interval_seconds": None}
        if previous:
            row["interval_seconds"] = round(
                (timestamp(generated) - timestamp(previous)).total_seconds(), 1)
        cadence = directory / "cadence"
        cadence.mkdir(exist_ok=True)
        with (cadence / (_et_day(now) + ".jsonl")).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    committed=clock()
    _event(directory,committed,event='fetch',request_started_at=now,received_at=received,local_committed_at=committed,http_status=200,changed=True,report_sha256=digest,source_generated_at=generated,source_state_at=state_at,publication_id=proof.get('publication_id') if proof else None)
    _status(directory, now, last_success_at=committed, last_error=None, changed=True)
    for old in sorted(versions.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[8:]:
        try:old.unlink()
        except OSError:pass
    return {"changed": True, "source_generated_at": generated}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def run_fetcher(source, directory, *, poll_seconds=5, clock=utc_now, sleep=time.sleep,
                stop=lambda: False):
    """Poll until ``stop()``. Errors are recorded and backed off, never raised:
    the executor judges freshness itself from the producer's clock."""
    delay = poll_seconds
    while not stop():
        now = clock()
        try:
            fetch_once(source, directory, now,clock=clock)
            delay = poll_seconds
        except Exception as exc:  # network, HTTP, parse: record, back off, retry
            _status(directory, now, last_error=type(exc).__name__ + ": " + str(exc)[:200])
            delay = min(60, delay * 2)
            _event(directory,now,event='fetch_failed',error_type=type(exc).__name__,reason=str(exc)[:200],next_retry_seconds=delay)
        sleep(delay)


def read_local(path):
    """(operations, meta) for the executor: a local file read, no network."""
    path = Path(path)
    try:
        meta = json.loads(path.with_name("operations.meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    selected=_generation_path(path,meta)
    data = selected.read_bytes()
    if len(data) > MAX_BYTES:
        raise SafetyError("snapshot exceeds input limit")
    if meta.get('generation_file') and hashlib.sha256(data).hexdigest()!=meta.get('sha256'):
        raise SafetyError('snapshot generation checksum mismatch')
    return json.loads(data), meta


def _generation_path(path,meta):
    name=meta.get('generation_file')
    if name is None:return path
    if not re.fullmatch(r'versions/[a-f0-9]{64}\.json',name) or name!='versions/'+str(meta.get('sha256'))+'.json':
        raise SafetyError('invalid immutable feed generation path')
    return path.parent/name


def read_local_clocks(path):
    """Read clocks from validated download metadata, bound to its report file.

    Re-parsing the multi-megabyte catalog at low CPU priority can finish after
    a newer report has replaced it. A clock monitor needs the current file's
    clocks, not that older in-flight parse. Trading still reads the report.
    """
    path = Path(path)
    meta_path = path.with_name("operations.meta.json")
    for _ in range(3):
        raw = meta_path.read_bytes()
        if len(raw) > 64_000:
            raise SafetyError("feed clock metadata exceeds input limit")
        meta = json.loads(raw)
        selected=_generation_path(path,meta)
        try:before = selected.stat()
        except FileNotFoundError:continue
        expected = (meta.get("report_inode"), meta.get("report_mtime_ns"),
                    meta.get("bytes"))
        identity = lambda stat: (stat.st_ino, stat.st_mtime_ns, stat.st_size)
        if (identity(before) != expected or identity(selected.stat()) != expected):
            continue
        if (not re.fullmatch(r"[a-f0-9]{64}", meta.get("sha256") or "")
                or not 0 < before.st_size <= MAX_BYTES):
            raise SafetyError("invalid feed clock metadata")
        clocks = {"generated_at": meta.get("source_generated_at"),
                  "state_at": meta.get("source_state_at")}
        for value in clocks.values():
            timestamp(value)
        return clocks, meta
    raise SafetyError("feed was replaced or its clock metadata does not match")


def cadence_report(directory, day):
    rows = []
    path = Path(directory) / "cadence" / (day + ".jsonl")
    if path.exists():
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    gaps = sorted(r["interval_seconds"] for r in rows if r.get("interval_seconds") is not None)
    lags = sorted(r["download_lag_seconds"] for r in rows)

    def pct(values, q):
        return values[min(len(values) - 1, int(q * len(values)))] if values else None

    return {
        "schema": "rs_operations_cadence.v1", "day": day, "publications_seen": len(rows),
        "interval_seconds": {"median": pct(gaps, 0.5), "p90": pct(gaps, 0.9),
                             "max": gaps[-1] if gaps else None},
        "share_within_30s": (sum(g <= 30 for g in gaps) / len(gaps)) if gaps else None,
        "share_within_120s": (sum(g <= FRESH_SECONDS for g in gaps) / len(gaps)) if gaps else None,
        "download_lag_seconds": {"median": pct(lags, 0.5), "max": lags[-1] if lags else None},
        "note": "Intervals are between the producer's own generated_at clocks; the fetcher "
                "polls every few seconds, so a publication shorter than the poll can be missed.",
    }
