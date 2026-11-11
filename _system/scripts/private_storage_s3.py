"""R2 S3 transport using the existing Cloudflare API token, without new grants.

Cloudflare documents Access Key ID = token id and Secret Access Key =
SHA-256(token value). No token is created, saved, logged or granted access.
https://developers.cloudflare.com/r2/api/tokens/#get-s3-api-credentials-from-an-api-token
"""
from __future__ import annotations
import hashlib,hmac,json,os,re,threading,time,urllib.error,urllib.parse,urllib.request
from datetime import datetime,timezone
from private_storage import HTTP,NoRedirect,StorageError,StorageHTTPError

def signature_headers(method,host,path,body,access_id,secret,*,instant=None):
    if method not in ('GET','PUT'):raise StorageError('Unsupported immutable object operation')
    instant=instant or datetime.now(timezone.utc);stamp=instant.strftime('%Y%m%dT%H%M%SZ');day=stamp[:8]
    payload=hashlib.sha256(body or b'').hexdigest();uri=urllib.parse.quote(path,safe='/-_.~')
    signed='host;x-amz-content-sha256;x-amz-date'
    headers='host:'+host+'\nx-amz-content-sha256:'+payload+'\nx-amz-date:'+stamp+'\n'
    canonical='\n'.join((method,uri,'',headers,signed,payload));scope=day+'/auto/s3/aws4_request'
    message='AWS4-HMAC-SHA256\n'+stamp+'\n'+scope+'\n'+hashlib.sha256(canonical.encode()).hexdigest()
    def sign(key,value):return hmac.new(key,value.encode(),hashlib.sha256).digest()
    key=sign(sign(sign(sign(('AWS4'+secret).encode(),day),'auto'),'s3'),'aws4_request')
    signature=hmac.new(key,message.encode(),hashlib.sha256).hexdigest()
    return {'Authorization':'AWS4-HMAC-SHA256 Credential='+access_id+'/'+scope+', SignedHeaders='+signed+', Signature='+signature,
            'x-amz-date':stamp,'x-amz-content-sha256':payload,'Host':host,'Content-Type':'application/octet-stream','User-Agent':'Magis-private-storage/1'}

class S3HTTP:
    def __init__(self,config,*,identity_http=None,opener=None):
        self.config=config;self.host=config['account_id']+'.r2.cloudflarestorage.com'
        self.token_owner=config.get('s3_token_owner','auto')
        if self.token_owner not in ('auto','account','user'):raise StorageError('Unsupported storage token owner')
        self.identity_http=identity_http or HTTP(lambda:os.environ['CLOUDFLARE_API_TOKEN'].strip(),'api.cloudflare.com',content_type='application/json')
        self.opener=opener or urllib.request.build_opener(NoRedirect)
        self.interval=1/config.get('requests_per_second',2);self.lock=threading.Lock();self.next_request=0
        self._identity=None

    def credentials(self):
        token=os.environ.get('CLOUDFLARE_API_TOKEN','').strip()
        if not token:raise StorageError('Existing authorized storage API token is required for S3')
        fingerprint=hashlib.sha256(token.encode()).hexdigest()
        if not self._identity or self._identity[0]!=fingerprint:
            # Legacy token values do not encode their owner. A wrong verification
            # scope returns 400; only that response permits the other documented
            # scope, on this same account. Authentication failures never fall back.
            owners=([self.token_owner] if self.token_owner!='auto' else
                    ['account'] if token.startswith('cfat_') else ['user','account'])
            for index,owner in enumerate(owners):
                path='/client/v4/accounts/'+self.config['account_id']+'/tokens/verify' if owner=='account' else '/client/v4/user/tokens/verify'
                try:raw=self.identity_http.request('GET',path,limit=1024*1024)
                except StorageHTTPError as error:
                    if error.status==400 and index+1<len(owners):continue
                    raise
                response=json.loads(raw or b'{}');result=response.get('result') or {}
                if response.get('success') is not True or result.get('status')!='active' or not re.fullmatch(r'[0-9a-f]{32}',result.get('id','')):
                    raise StorageError('Existing storage token identity could not be verified')
                self.verified_token_owner=owner
                break
            self._identity=(fingerprint,result['id'])
        return self._identity[1],fingerprint

    def request(self,method,path,body=None,*,limit):
        if not path.startswith('/'+self.config['bucket']+'/') or '?' in path or '#' in path:
            raise StorageError('Immutable object request escaped the configured private bucket')
        from private_storage import relative_path
        relative_path(path[len(self.config['bucket'])+2:])
        access,secret=self.credentials()
        for attempt in range(4):
            with self.lock:
                delay=max(0,self.next_request-time.monotonic())
                if delay:time.sleep(delay)
                self.next_request=time.monotonic()+self.interval
            headers=signature_headers(method,self.host,path,body,access,secret)
            request=urllib.request.Request('https://'+self.host+urllib.parse.quote(path,safe='/-_.~'),data=body,method=method,headers=headers)
            try:
                with self.opener.open(request,timeout=120) as response:raw=response.read(limit+1)
            except urllib.error.HTTPError as error:
                if error.code==404:return None
                if error.code not in (429,500,502,503,504) or attempt==3:
                    raise StorageError(f'Private S3 storage {method} failed: HTTP {error.code}') from None
                delay=2**(attempt+1)
                if str(error.headers.get('Retry-After','')).isdigit():delay=max(delay,int(error.headers['Retry-After']))
                if delay>300:raise StorageError('Private storage requested a longer hold; verified progress remains') from None
                while delay:
                    pause=min(delay,60);time.sleep(pause);delay-=pause
                continue
            if len(raw)>limit:raise StorageError('Private storage response exceeds its exact bounded size')
            return raw
