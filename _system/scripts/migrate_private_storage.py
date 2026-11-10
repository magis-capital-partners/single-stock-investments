"""Resumable, lossless migration of one pinned legacy private tree.

Only the new owned staging repository is written. The legacy vault and its
history stay read-only. Every complete source blob is checked against Git,
stored privately, read back and checked before a durable batch is registered.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil,stat,subprocess,time
from pathlib import Path
from private_storage import (PrivateStorage,StorageError,encoded_json,relative_path,
                             restore_bytes,sha,store_bytes,store_packed,run_git)

PIN=re.compile(r'[0-9a-f]{40}\Z')

def git_blob(raw):return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()

def inventory(repository,pin):
    if not PIN.fullmatch(pin):raise StorageError('Exact legacy commit required')
    raw=run_git(repository,'ls-tree','-rz',pin).stdout
    rows=[]
    for line in raw.split(b'\0'):
        if not line:continue
        meta,path=line.split(b'\t',1);mode,kind,identity=meta.decode().split();name=path.decode('utf-8')
        relative_path(name)
        if kind!='blob' or mode not in ('100644','100755') or not PIN.fullmatch(identity):
            raise StorageError('Unsupported legacy source tree member')
        rows.append({'path':name,'mode':mode,'git_blob':identity})
    if len({r['path'] for r in rows})!=len(rows):raise StorageError('Duplicate legacy source paths')
    return rows,sha(raw)

def verified_batch(storage,record):
    raw=storage.restore(record['logical_path'])
    if raw is None or sha(raw)!=record['sha256']:raise StorageError('Required migration batch is missing')
    batch=json.loads(raw)
    if batch.get('source_commit')!=storage.config['legacy_pin']:raise StorageError('Migration source commit changed')
    return batch

def publish_batch(storage,number,entries,source_listing):
    value={'schema_version':'private-legacy-batch/1','source_commit':storage.config['legacy_pin'],
           'source_listing_sha256':source_listing,'number':number,'entries':entries,'complete_original_bytes_verified':True}
    raw=encoded_json(value);name='legacy/'+storage.config['legacy_pin']+'/batches/'+str(number).zfill(6)+'-'+sha(raw)+'.json'
    _,expected=storage.snapshot();commit=storage.publish({name:raw},expected=expected)
    if storage.restore(name)!=raw:raise StorageError('Migration batch did not round-trip')
    return {'logical_path':name,'sha256':sha(raw),'catalog_commit':commit,'files':len(entries),'bytes':sum(x['bytes'] for x in entries.values())}

def read_blobs(repository,identities):
    env={**os.environ,'GIT_NO_LAZY_FETCH':'1'}
    process=subprocess.Popen(['git','-C',str(repository),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
    try:
        for identity in identities:
            process.stdin.write((identity+'\n').encode());process.stdin.flush()
            header=process.stdout.readline().decode().strip().split()
            if len(header)!=3 or header[:2]!=[identity,'blob']:raise StorageError('Exact fetched legacy blob is missing')
            size=int(header[2])
            if size>256*1024*1024:raise StorageError('Legacy file requires separate streamed preservation')
            data=bytearray()
            while len(data)<size:
                piece=process.stdout.read(min(1024*1024,size-len(data)))
                if not piece:raise StorageError('Truncated legacy Git blob')
                data.extend(piece)
            if process.stdout.read(1)!=b'\n':raise StorageError('Legacy Git blob boundary changed')
            raw=bytes(data)
            if git_blob(raw)!=identity:raise StorageError('Legacy source Git blob hash changed')
            yield identity,raw
        process.stdin.close()
        if process.wait(timeout=60):raise StorageError('Legacy Git source reader failed')
    finally:
        for stream in (process.stdout,process.stderr):stream.close()
        if process.poll() is None:process.terminate();process.wait(timeout=15)

def migrate(repository,output,*,storage=None,batch_files=128,max_batches=None,release_staging_packs=False):
    storage=storage or PrivateStorage();repository=Path(repository).resolve();output=Path(output).resolve()
    marker=repository/'migration-owner.json'
    if json.loads(marker.read_text(encoding='utf-8'))!={'purpose':'verified-private-legacy-migration','source_commit':storage.config['legacy_pin']}:
        raise StorageError('Owned migration staging identity required')
    remote=run_git(repository,'remote','get-url','origin').stdout.decode().strip()
    if remote!='https://github.com/'+storage.config['legacy_repository']+'.git':raise StorageError('Legacy source remote identity changed')
    rows,listing=inventory(repository,storage.config['legacy_pin']);output.mkdir(parents=True,exist_ok=True)
    journal=output/'migration-journal.json';progress=json.loads(journal.read_text()) if journal.exists() else {'source_commit':storage.config['legacy_pin'],'source_listing_sha256':listing,'batches':[]}
    if progress['source_commit']!=storage.config['legacy_pin'] or progress['source_listing_sha256']!=listing:raise StorageError('Migration inventory changed')
    if not progress['batches']:
        catalog_commit,records=storage.snapshot()
        prefix='legacy/'+storage.config['legacy_pin']+'/batches/'
        for name,entry in sorted(records.items()):
            if not name.startswith(prefix):continue
            if not re.fullmatch(re.escape(prefix)+r'[0-9]{6}-[0-9a-f]{64}[.]json',name):raise StorageError('Unexpected migration batch path')
            if int(name[len(prefix):len(prefix)+6])!=len(progress['batches']):raise StorageError('Missing or conflicting migration checkpoint')
            batch=json.loads(storage.restore(name,records=records))
            progress['batches'].append({'logical_path':name,'sha256':entry['sha256'],'catalog_commit':catalog_commit,'files':len(batch['entries']),'bytes':sum(x['bytes'] for x in batch['entries'].values())})
    all_entries={}
    for record in progress['batches']:
        batch=verified_batch(storage,record)
        if batch['source_listing_sha256']!=listing:raise StorageError('Migration source listing changed')
        for name,entry in batch['entries'].items():
            if name in all_entries:raise StorageError('Overlapping migration batches')
            all_entries[name]=entry
    by_blob={}
    for row in rows:
        if row['path'] not in all_entries:by_blob.setdefault(row['git_blob'],[]).append(row)
    identities=list(by_blob);completed=0
    for start in range(0,len(identities),batch_files):
        if max_batches is not None and completed>=max_batches:break
        if shutil.disk_usage(repository).free<12*1024**3:raise StorageError('Migration disk reserve reached; verified progress is preserved')
        selected=identities[start:start+batch_files]
        # Download only explicitly pinned source blobs, with normal Git transport.
        # This creates no remote refs or writes in the legacy vault.
        pack_location=Path(run_git(repository,'rev-parse','--git-path','objects/pack').stdout.decode().strip())
        pack_root=(pack_location if pack_location.is_absolute() else repository/pack_location).resolve()
        if not pack_root.is_relative_to(repository):raise StorageError('Staging object root escaped the owned repository')
        before_packs={p.name for p in pack_root.iterdir()}
        run_git(repository,'-c','fetch.unpackLimit=1','fetch','--no-tags','origin',*selected)
        new_packs=[p for p in pack_root.iterdir() if p.name not in before_packs]
        batch_entries={};pending={};total=0
        def flush():
            nonlocal total
            if not pending:return
            packed=store_packed(storage.objects,pending)
            for identity,raw in pending.items():
                for row in by_blob[identity]:
                    entry=dict(packed[identity],git_blob=identity,git_mode=row['mode'])
                    batch_entries[row['path']]=entry
            pending.clear();total=0
        for identity,raw in read_blobs(repository,selected):
            if total+len(raw)>64*1024*1024:flush()
            pending[identity]=raw;total+=len(raw)
        flush()
        record=publish_batch(storage,len(progress['batches']),batch_entries,listing)
        progress['batches'].append(record);all_entries.update(batch_entries)
        temporary=journal.with_suffix('.new');temporary.write_bytes(encoded_json(progress));temporary.replace(journal)
        if release_staging_packs:
            released=[]
            for path in new_packs:
                if (path.parent.resolve()!=pack_root.resolve() or path.is_symlink()
                        or not re.fullmatch(r'pack-[0-9a-f]{40}[.](pack|idx|rev|promisor)',path.name)):
                    raise StorageError('Unsafe staging pack release path')
                released.append({'path':path.name,'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size})
            # Only new duplicate transport packs are released after their full
            # original blobs and exact path index are verified in private storage.
            # Existing metadata packs and all original vault Git objects stay.
            proof=output/('staging-release-'+str(len(progress['batches'])).zfill(6)+'.json')
            proof.write_bytes(encoded_json({'verified_batch':record,'duplicate_staging_files':released,'original_vault_untouched':True}))
            for path in new_packs:
                if os.name=='nt':path.chmod(path.stat().st_mode|stat.S_IWRITE)
                path.unlink()
        completed+=1
        print(json.dumps({'batch':len(progress['batches']),'files_verified':len(all_entries),'total_files':len(rows),'bytes_verified':sum(x['bytes'] for x in all_entries.values())}),flush=True)
    complete=set(all_entries)=={r['path'] for r in rows}
    if not complete:return {'complete':False,'files_verified':len(all_entries),'total_files':len(rows)}
    for row in rows:
        if all_entries[row['path']]['git_blob']!=row['git_blob']:raise StorageError('Final migration Git identity mismatch')
    shards={format(i,'02x'):{} for i in range(256)}
    for name,entry in all_entries.items():shards[sha(name.encode())[:2]][name]=entry
    names={};payloads={};prefix='legacy/'+storage.config['legacy_pin']
    for key,values in shards.items():
        raw=encoded_json(values);name=prefix+'/indexes/'+sha(raw)+'.json';payloads[name]=raw;names[key]=name
    manifest={'schema_version':'private-legacy-manifest/1','source_commit':storage.config['legacy_pin'],
              'source_listing_sha256':listing,'path_count':len(rows),'unique_git_blobs':len({r['git_blob'] for r in rows}),
              'complete':True,'shards':names,'legacy_history_preserved':True}
    raw=encoded_json(manifest);manifest_path=prefix+'/manifests/'+sha(raw)+'.json';payloads[manifest_path]=raw
    _,expected=storage.snapshot();commit=storage.publish(payloads,expected=expected)
    for name,original in payloads.items():
        if storage.restore(name)!=original:raise StorageError('Final legacy index round-trip failed')
    proof={'complete':True,'source_commit':storage.config['legacy_pin'],'files_verified':len(rows),'manifest_path':manifest_path,'catalog_commit':commit,'legacy_history_deleted':False}
    (output/'migration-completion-proof.json').write_bytes(encoded_json(proof));print(json.dumps(proof),flush=True);return proof

def initialize_repository(repository,config):
    repository=Path(repository).resolve();marker=repository/'migration-owner.json'
    expected={'purpose':'verified-private-legacy-migration','source_commit':config['legacy_pin']}
    if repository.exists():
        if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8'))!=expected:
            raise StorageError('Refusing to repurpose an existing repository')
    else:
        repository.mkdir(parents=True,mode=0o700)
        run_git(repository,'init','--bare')
        run_git(repository,'config','core.longpaths','true')
        run_git(repository,'remote','add','origin','https://github.com/'+config['legacy_repository']+'.git')
        marker.write_bytes(encoded_json(expected))
    run_git(repository,'fetch','--no-tags','--depth','1','--filter=blob:none','origin',config['legacy_pin'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repository',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--batch-files',default=128,type=int);p.add_argument('--max-batches',type=int);p.add_argument('--release-staging-packs',action='store_true');p.add_argument('--initialize-repository',action='store_true')
    args=p.parse_args()
    if not 1<=args.batch_files<=256:raise StorageError('Bounded migration batch required')
    storage=PrivateStorage()
    if args.initialize_repository:initialize_repository(args.repository,storage.config)
    migrate(args.repository,args.output,storage=storage,batch_files=args.batch_files,max_batches=args.max_batches,release_staging_packs=args.release_staging_packs)
if __name__=='__main__':main()
