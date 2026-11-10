import copy,hashlib,json,sys
from pathlib import Path
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import private_storage as store
from test_private_storage import Objects,MemoryCatalog

def test_packed_complete_binary_unicode_empty_and_legacy_layouts():
    objects=Objects();files={'evidence/a':'漢字\r\n'.encode()*100,'evidence/b':b'PK\x03\x04'+bytes(range(255)),'evidence/empty':b''}
    entries=store.store_packed(objects,files)
    assert len(objects.data)==1
    for path,raw in files.items():assert store.restore_bytes(objects,entries[path])==raw
    old=store.store_bytes(objects,b'old layout');assert store.restore_bytes(objects,old)==b'old layout'

def test_pack_rollovers_keep_each_original_file_and_order(monkeypatch):
    monkeypatch.setattr(store,'MAX_CHUNK_BYTES',64)
    objects=Objects();files={'a':bytes(range(150)),'b':bytes(range(100,200))}
    entries=store.store_packed(objects,files)
    assert all(len(x)<=64 for x in objects.data.values())
    assert len(entries['a']['chunks'])==3
    for path,raw in files.items():assert store.restore_bytes(objects,entries[path])==raw

@pytest.mark.parametrize('field,value',[('packed_offset',-1),('packed_offset',True),('packed_offset',100000),('packed_bytes',0),('packed_bytes',True),('packed_bytes',100000),('encoding','packed-zlib'),('sha256','0'*64)])
def test_invalid_pack_boundaries_and_codec_stay_held(field,value):
    objects=Objects();entry=store.store_packed(objects,{'a':b'original'})['a'];entry['chunks'][0][field]=value
    with pytest.raises(store.StorageError):store.restore_bytes(objects,entry)

def test_cross_file_slice_cannot_substitute_another_claim():
    objects=Objects();entries=store.store_packed(objects,{'a':b'first','b':b'other'})
    entries['a']['chunks'][0]['packed_offset']=entries['b']['chunks'][0]['packed_offset']
    with pytest.raises(store.StorageError):store.restore_bytes(objects,entries['a'])

def test_cache_is_bounded_and_only_contains_verified_full_objects():
    class HTTP:
        def __init__(self):self.calls=[];self.data={}
        def request(self,method,path,body=None,**kw):self.calls.append((method,path));return self.data.get(path)
    http=HTTP();obj=store.R2Objects({'account_id':'a','bucket':'b','object_prefix':'p'},http=http)
    for raw in (b'a',b'b',b'c'):
        identity=store.sha(raw);http.data[obj.base+obj.key(identity)]=raw;assert obj.get(identity,1)==raw
    assert len(obj._verified_cache)==2
    count=len(http.calls);assert obj.get(store.sha(b'c'),1)==b'c';assert len(http.calls)==count
    with pytest.raises(store.StorageError):obj.get(store.sha(b'c'),2)
    raw=b'changed';identity=store.sha(raw);http.data[obj.base+obj.key(identity)]=b'corrupt'
    with pytest.raises(store.StorageError):obj.get(identity,len(raw))
    assert identity not in obj._verified_cache

def legacy_fixture():
    objects,catalog=Objects(),MemoryCatalog();pin='a'*40;path='evidence/original.json';raw=b'complete original\r\n';entry=store.store_packed(objects,{path:raw})[path]
    entry['git_blob']=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    shard='legacy/'+pin+'/indexes/a.json';manifest='legacy/'+pin+'/manifest.json';prefix=store.sha(path.encode())[:2]
    catalog.records[shard]=store.store_bytes(objects,store.encoded_json({path:entry}))
    catalog.records[manifest]=store.store_bytes(objects,store.encoded_json({'schema_version':'private-legacy-manifest/1','source_commit':pin,'complete':True,'shards':{prefix:shard}}))
    s=store.PrivateStorage(config={'legacy_pin':pin,'legacy_archive_manifest':manifest},objects=objects,catalog=catalog)
    return s,catalog,path,raw,manifest,shard

def test_cold_legacy_lookup_restores_original_and_current_pointer_wins():
    s,c,p,raw,_,_=legacy_fixture();assert s.restore(p)==raw
    s.publish({p:b'new version'});assert s.restore(p)==b'new version'

@pytest.mark.parametrize('alteration',['missing-manifest','missing-shard','wrong-pin','incomplete','wrong-blob'])
def test_legacy_identity_and_completeness_cannot_default(alteration):
    s,c,p,raw,m,sh=legacy_fixture()
    if alteration=='missing-manifest':del c.records[m]
    elif alteration=='missing-shard':del c.records[sh]
    elif alteration in ('wrong-pin','incomplete'):
        v=json.loads(store.restore_bytes(s.objects,c.records[m]));v['source_commit' if alteration=='wrong-pin' else 'complete']='b'*40 if alteration=='wrong-pin' else False;c.records[m]=store.store_bytes(s.objects,store.encoded_json(v))
    else:
        v=json.loads(store.restore_bytes(s.objects,c.records[sh]));v[p]['git_blob']='0'*40;c.records[sh]=store.store_bytes(s.objects,store.encoded_json(v))
    with pytest.raises(store.StorageError):s.restore(p)
