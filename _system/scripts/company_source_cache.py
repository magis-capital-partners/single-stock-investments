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

FOLDERS=('git','drive','filings','commodity-text','media','transcripts','queue-checkpoints','md5','metadata','relationships','match-work','records','published-text','words')
ROOT_FILES=('matches.json','index.json','drive-inventory.json','backfill-report.json')
PUBLICATION_FOLDERS={'records','relationships','published-text','words'}
PUBLICATION_ROOT_FILES={'matches.json','index.json'}


def pack(cache,destination,release_packed_inputs=False):
    if release_packed_inputs:
        if not cache.is_dir() or cache.is_symlink() or any((cache/name).is_symlink() for name in FOLDERS+ROOT_FILES):
            raise ValueError('Release requires an existing cache without linked source roots')
        if destination.resolve().is_relative_to(cache.resolve()):
            raise ValueError('The archive must be outside the released cache')
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
            if files:pending.append((files,pool.submit(create_part,files)))
            files=[];size=0
        for bucket in sorted(buckets):
            for path,length in sorted(buckets[bucket]):
                if size+length>32_000_000:flush()
                if length>90_000_000:raise ValueError('Oversized extraction cache entry')
                files.append(path);size+=length
            flush()
        parts=[job.result() for _,job in pending]
    temporary=manifest.with_suffix('.'+str(os.getpid())+'.tmp')
    temporary.write_text(json.dumps({'schema_version':1,'parts':parts},indent=2)+'\n',encoding='utf-8')
    temporary.replace(manifest)
    result={'parts':len(parts),'files':sum(p['files'] for p in parts)}
    if release_packed_inputs:
        # Verify every source against the finished archive before deleting any
        # packed input. Never remove the cache tree or unarchived bookkeeping.
        # The source corpus and Git's new compressed objects otherwise coexist
        # on the runner, exhausting disk even with bounded upload batches.
        cache_root=cache.resolve()
        for part,(group,_) in zip(parts,pending):
            archive_path=destination/part['file']
            if archive_path.resolve().parent!=destination.resolve():
                raise ValueError('Invalid archive path for cache release')
            if hashlib.sha256(archive_path.read_bytes()).hexdigest()!=part['sha256']:
                raise ValueError('Private cache checksum mismatch; packed inputs retained')
            with zipfile.ZipFile(archive_path) as z:
                names=[p.relative_to(cache).as_posix() for p in group]
                if z.namelist()!=names:
                    raise ValueError('Archive coverage changed; packed inputs retained')
                for path,name in zip(group,names):
                    if path.is_symlink() or not path.resolve().is_relative_to(cache_root):
                        raise ValueError('Unsafe cache release path')
                    if path.read_bytes()!=z.read(name):
                        raise ValueError('Archive content differs; packed inputs retained')
        for path,_ in paths:
            path.unlink()
        result.update(released_files=len(paths),released_input_bytes=sum(length for _,length in paths))
    # Old immutable parts may belong to another publication; leave retention to
    # the private vault owner. Only manifest-listed parts are restored.
    return result


def restore(source,cache,publication_only=False):
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
                if publication_only and Path(item.filename).parts[0] not in PUBLICATION_FOLDERS and item.filename not in PUBLICATION_ROOT_FILES:
                    continue
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(z.read(item))
    return {'parts':len(parts)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['pack','restore'])
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--publication-only',action='store_true',help='Restore verified publication records, full text and search tokens only')
    parser.add_argument('--release-packed-inputs',action='store_true',help='After packing, verify and delete only archived cache files to leave room for Git upload objects')
    args=parser.parse_args()
    if args.publication_only and args.action!='restore':parser.error('--publication-only is a restore option')
    if args.release_packed_inputs and args.action!='pack':parser.error('--release-packed-inputs is a pack option')
    print(pack(args.cache,args.archive,args.release_packed_inputs) if args.action=='pack' else restore(args.archive,args.cache,args.publication_only))
