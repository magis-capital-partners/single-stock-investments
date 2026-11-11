import hashlib,hmac,io,json,sys,urllib.error
from datetime import datetime,timezone
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import private_storage as store
import private_storage_s3 as s3

CONFIG={'account_id':'a'*32,'bucket':'single-stock-investments-private','object_prefix':'research-archive/v1/objects','requests_per_second':2}
class Identity:
    def __init__(self,status='active',identity='b'*32):self.calls=[];self.status=status;self.identity=identity
    def request(self,*args,**kwargs):self.calls.append(args);return json.dumps({'result':{'id':self.identity,'status':self.status}}).encode()
class Response:
    def __init__(self,data):self.data=data
    def read(self,limit):return self.data[:limit]
    def __enter__(self):return self
    def __exit__(self,*args):pass
class Opener:
    def __init__(self,responses):self.responses=list(responses);self.requests=[]
    def open(self,request,**kwargs):
        self.requests.append(request);result=self.responses.pop(0)
        if isinstance(result,Exception):raise result
        return Response(result)

def test_existing_token_is_derived_in_memory_and_verified_only_once(monkeypatch):
    token='existing authorized token';monkeypatch.setenv('CLOUDFLARE_API_TOKEN',token);identity=Identity();obj=s3.S3HTTP(CONFIG,identity_http=identity)
    assert obj.credentials()==('b'*32,hashlib.sha256(token.encode()).hexdigest());assert obj.credentials()[0]=='b'*32
    assert len(identity.calls)==1
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN','renewed existing token');obj.credentials();assert len(identity.calls)==2

@pytest.mark.parametrize('status,identity',[('disabled','b'*32),('active','malformed')])
def test_unverified_token_metadata_never_reaches_object_access(monkeypatch,status,identity):
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN','secret not for logs');obj=s3.S3HTTP(CONFIG,identity_http=Identity(status,identity))
    with pytest.raises(store.StorageError) as error:obj.credentials()
    assert 'secret not for logs' not in str(error.value)

def test_signature_binds_exact_method_path_payload_date_and_account():
    time=datetime(2026,11,11,tzinfo=timezone.utc);key='b'*32;secret='c'*64
    values=s3.signature_headers('PUT','account.r2.cloudflarestorage.com','/bucket/path with space',b'complete binary\0',key,secret,instant=time)
    assert values['x-amz-content-sha256']==hashlib.sha256(b'complete binary\0').hexdigest()
    assert values['x-amz-date']=='20261111T000000Z'
    assert 'Credential='+key+'/20261111/auto/s3/aws4_request' in values['Authorization']
    for method,host,path,body in [('GET','account.r2.cloudflarestorage.com','/bucket/path with space',b'complete binary\0'),('PUT','other.r2.cloudflarestorage.com','/bucket/path with space',b'complete binary\0'),('PUT','account.r2.cloudflarestorage.com','/bucket/other',b'complete binary\0'),('PUT','account.r2.cloudflarestorage.com','/bucket/path with space',b'trimmed')]:
        assert s3.signature_headers(method,host,path,body,key,secret,instant=time)['Authorization']!=values['Authorization']
    assert secret not in values['Authorization']

def test_s3_reads_exact_complete_bytes_without_rest_object_requests(monkeypatch):
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN','existing token');identity=Identity();opener=Opener([b'full original'])
    client=s3.S3HTTP(CONFIG,identity_http=identity,opener=opener);path='/'+CONFIG['bucket']+'/research-archive/v1/objects/a/b'
    assert client.request('GET',path,limit=13)==b'full original'
    assert opener.requests[0].full_url.startswith('https://'+'a'*32+'.r2.cloudflarestorage.com/')
    assert len(identity.calls)==1 and 'tokens/verify' in identity.calls[0][1]

def test_request_limit_retry_preserves_identity_and_honors_bounded_wait(monkeypatch):
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN','existing token');waits=[];monkeypatch.setattr(s3.time,'sleep',waits.append)
    error=urllib.error.HTTPError('https://storage',429,'rate limited',{'Retry-After':'90'},None)
    client=s3.S3HTTP(CONFIG,identity_http=Identity(),opener=Opener([error,b'original']))
    assert client.request('GET','/'+CONFIG['bucket']+'/object',limit=8)==b'original'
    assert 60 in waits and 30 in waits and all(x<=60 for x in waits)

@pytest.mark.parametrize('code',[401,403,413])
def test_auth_and_size_failures_do_not_silently_change_transport(monkeypatch,code):
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN','secret not for logs');error=urllib.error.HTTPError('https://storage',code,'hidden',{},None)
    client=s3.S3HTTP(CONFIG,identity_http=Identity(),opener=Opener([error]))
    with pytest.raises(store.StorageError,match='HTTP '+str(code)) as exc:client.request('GET','/'+CONFIG['bucket']+'/object',limit=8)
    assert 'secret not for logs' not in str(exc.value)

@pytest.mark.parametrize('path',['/other-bucket/file','/'+CONFIG['bucket']+'/../outside','/'+CONFIG['bucket']+'/object?query=1'])
def test_object_request_cannot_escape_bucket_or_gain_operations(monkeypatch,path):
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN','existing token');client=s3.S3HTTP(CONFIG,identity_http=Identity())
    with pytest.raises(store.StorageError):client.request('GET',path,limit=8)

def test_oversized_response_is_not_registered(monkeypatch):
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN','existing token');client=s3.S3HTTP(CONFIG,identity_http=Identity(),opener=Opener([b'oversized']))
    with pytest.raises(store.StorageError,match='bounded'):client.request('GET','/'+CONFIG['bucket']+'/object',limit=2)

def test_transport_is_opt_in_and_local_existing_oauth_remains_supported(monkeypatch):
    monkeypatch.delenv('CLOUDFLARE_API_TOKEN',raising=False);obj=store.R2Objects({**CONFIG,'object_transport':'s3_existing_api_token'})
    assert isinstance(obj.http,store.HTTP)
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN','existing token');obj=store.R2Objects({**CONFIG,'object_transport':'s3_existing_api_token'})
    assert isinstance(obj.http,s3.S3HTTP) and obj.base=='/'+CONFIG['bucket']+'/'
