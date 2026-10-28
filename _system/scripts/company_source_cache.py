"""Portable compressed extraction cache, stored only in the private research vault."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

FOLDERS=('git','drive','media','transcripts','queue-checkpoints','md5','metadata','relationships')
ROOT_FILES=('matches.json',)


def pack(cache,destination):
    destination.mkdir(parents=True,exist_ok=True)
    parts=[];files=[];size=0
    def flush():
        nonlocal files,size
        if not files:return
        temporary=destination/'building.zip'
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in files:
                info=zipfile.ZipInfo(p.relative_to(cache).as_posix());info.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(info,p.read_bytes())
        sha=hashlib.sha256(temporary.read_bytes()).hexdigest();name=sha+'.zip'
        target=destination/name
        if target.exists():temporary.unlink()
        else:temporary.replace(target)
        parts.append({'file':name,'sha256':sha,'files':len(files)});files=[];size=0
    paths=[cache/name for name in ROOT_FILES]
    for folder in FOLDERS:paths.extend(sorted((cache/folder).rglob('*')))
    for path in paths:
        if not path.is_file() or path.suffix not in {'.json','.txt','.md'}:continue
        if size+path.stat().st_size>32_000_000:flush()
        if path.stat().st_size>90_000_000:raise ValueError('Oversized extraction cache entry')
        files.append(path);size+=path.stat().st_size
    flush()
    (destination/'manifest.json').write_text(json.dumps({'schema_version':1,'parts':parts},indent=2)+'\n',encoding='utf-8')
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
