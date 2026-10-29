"""Portable compressed extraction cache, stored only in the private research vault."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import zipfile
import uuid

FOLDERS=('git','drive','media','transcripts','queue-checkpoints','md5','metadata','relationships','match-work','records','published-text','words')
ROOT_FILES=('matches.json','index.json','drive-inventory.json','backfill-report.json')


def pack(cache,destination):
    destination.mkdir(parents=True,exist_ok=True)
    files=[];size=0;pending=[]
    manifest=destination/'manifest.json'
    previous=json.loads(manifest.read_text(encoding='utf-8')).get('parts',[]) if manifest.is_file() else []
    reusable={p['input_sha256']:p for p in previous if p.get('input_sha256')}
    def create_part(files):
        payload=[(p.relative_to(cache).as_posix(),p.read_bytes()) for p in files]
        fingerprint=hashlib.sha256()
        for name,data in payload:
            fingerprint.update(name.encode()+b'\0'+hashlib.sha256(data).digest())
        signature=fingerprint.hexdigest();prior=reusable.get(signature)
        if prior:
            path=destination/prior['file']
            if path.parent.resolve()==destination.resolve() and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==prior['sha256']:
                return prior
        temporary=destination/('building-'+uuid.uuid4().hex+'.zip')
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for name,data in payload:
                info=zipfile.ZipInfo(name);info.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(info,data)
        sha=hashlib.sha256(temporary.read_bytes()).hexdigest();name=sha+'.zip'
        target=destination/name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==sha:temporary.unlink()
        else:temporary.replace(target)
        return {'file':name,'sha256':sha,'files':len(files),'input_sha256':signature}
    def entries(directory):
        if not directory.is_dir():return
        with os.scandir(directory) as listing:
            for item in listing:
                if item.is_dir(follow_symlinks=False):
                    yield from entries(Path(item.path))
                elif item.is_file(follow_symlinks=False) and Path(item.name).suffix in {'.json','.txt','.md'}:
                    # Directory enumeration already supplies size/type on
                    # Windows; avoid two extra filesystem probes per original.
                    yield Path(item.path),item.stat(follow_symlinks=False).st_size
    paths=[(cache/name,(cache/name).stat().st_size) for name in ROOT_FILES if (cache/name).is_file()]
    for folder in FOLDERS:paths.extend(entries(cache/folder))
    # Keep unrelated source buckets stable when inventory metadata or one
    # document changes. A rolling archive over the whole cache can otherwise
    # rewrite gigabytes of unchanged parts after a small insertion.
    buckets=defaultdict(list)
    for path,length in paths:
        relative=path.relative_to(cache)
        bucket=(relative.parts[0],path.stem[:2]) if len(relative.parts)>1 else ('root',relative.name)
        buckets[bucket].append((path,length))
    # Compression releases the GIL. Four bounded workers also overlap small
    # file reads, without loading the complete corpus into memory.
    with ThreadPoolExecutor(max_workers=4) as pool:
        def flush():
            nonlocal files,size
            if files:pending.append(pool.submit(create_part,files))
            files=[];size=0
        for bucket in sorted(buckets):
            for path,length in sorted(buckets[bucket]):
                if size+length>32_000_000:flush()
                if length>90_000_000:raise ValueError('Oversized extraction cache entry')
                files.append(path);size+=length
            flush()
        parts=[job.result() for job in pending]
    temporary=manifest.with_suffix('.'+str(os.getpid())+'.tmp')
    temporary.write_text(json.dumps({'schema_version':1,'parts':parts},indent=2)+'\n',encoding='utf-8')
    temporary.replace(manifest)
    # Old immutable parts may belong to another publication; leave retention to
    # the private vault owner. Only manifest-listed parts are restored.
    return {'parts':len(parts),'files':sum(p['files'] for p in parts)}


def restore(source,cache):
    manifest=source/'manifest.json'
    if not manifest.is_file():return {'parts':0}
    parts=json.loads(manifest.read_text(encoding='utf-8'))['parts']
    for part in parts:
        path=source/part['file']
        if path.parent.resolve()!=source.resolve():raise ValueError('Invalid archive path')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=part['sha256']:raise ValueError('Private cache checksum mismatch')
        with zipfile.ZipFile(path) as z:
            for item in z.infolist():
                target=cache/item.filename
                if not target.resolve().is_relative_to(cache.resolve()) or (Path(item.filename).parts[0] not in FOLDERS and item.filename not in ROOT_FILES):
                    raise ValueError('Unsafe cache path')
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(z.read(item))
    return {'parts':len(parts)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['pack','restore'])
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    args=parser.parse_args()
    print(pack(args.cache,args.archive) if args.action=='pack' else restore(args.archive,args.cache))
