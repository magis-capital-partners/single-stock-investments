"""Hash-bound, reversible pruning of disposable owned-runtime copies only."""
from __future__ import annotations
import hashlib
import argparse
from contextlib import contextmanager
import json
import lzma
import os
from pathlib import Path
import re
import tarfile
from datetime import datetime, timezone

def identity(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while piece:=stream.read(1024*1024):digest.update(piece)
    return digest.hexdigest()

def owned(root):
    root=Path(root).resolve()
    record=json.loads((root/'runtime-owner.json').read_text())
    if record.get('repository')!='magis-capital-partners/single-stock-investments' or record.get('purpose')!='local-codex-underwriting':
        raise ValueError('Only the owned underwriting runtime can be pruned')
    return root

def candidate(root,path):
    relative=path.relative_to(root)
    if path.is_symlink() or not path.resolve().is_relative_to(root) or any(p.lower()=='.git' for p in relative.parts):return None
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (path,*path.parents) if p!=root.parent):return None
    if len(relative.parts)==1 and re.fullmatch(r'private-publication(?:-[a-f0-9]{32})?[.]index',relative.name):
        return 'inactive temporary publication index; complete bytes and Git objects retained in backup'
    if relative.parts[0] in {'vault','work','evidence-inbox','runs','paid','packets','handoffs'}:return None
    if '__pycache__' in relative.parts and path.suffix=='.pyc':return 'disposable rebuildable Python bytecode cache'
    if '.pytest_cache' in relative.parts and path.name in {'README.md','CACHEDIR.TAG','.gitignore','nodeids','lastfailed','stepwise','durations'}:
        return 'disposable rebuildable test cache'
    if '.ruff_cache' in relative.parts and (path.name in {'CACHEDIR.TAG','.gitignore'} or re.fullmatch(r'[0-9a-f]{8,}',path.name)):
        return 'disposable rebuildable lint cache'
    return None

def inventory(root):
    root=owned(root)
    files=[]
    for base,folders,names in os.walk(root,followlinks=False):
        folders[:]=[name for name in folders if name.lower()!='.git' and not (Path(base)/name).is_symlink() and not getattr(Path(base)/name,'is_junction',lambda:False)()]
        for name in names:
            path=Path(base)/name
            reason=candidate(root,path)
            if reason:
                stat=path.stat()
                files.append({'path':path.relative_to(root).as_posix(),'sha256':identity(path),'bytes':stat.st_size,
                              'mtime_ns':stat.st_mtime_ns,'reason':reason})
    return {'schema_version':'owned-runtime-retention/1','root':str(root),'observed_at':datetime.now(timezone.utc).isoformat(),
            'files':sorted(files,key=lambda r:r['path']),'bytes':sum(r['bytes'] for r in files),
            'protected_paid_source_evidence_ledgers_history_pruned':False}

def checked_path(root,row):
    relative=Path(row['path'])
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe retention path')
    path=root/relative
    if not candidate(root,path):raise ValueError('Retention path is protected')
    if path.is_file() and (path.stat().st_size!=row['bytes'] or identity(path)!=row['sha256']):
        raise ValueError('A retention candidate changed; preserve it and rebuild the manifest')
    return path

def archive(root,manifest,destination):
    root=owned(root)
    if str(root)!=manifest['root']:raise ValueError('Retention root changed')
    if destination.exists():raise ValueError('Refusing to overwrite a retention archive')
    with destination.open('xb') as raw:
        with lzma.LZMAFile(raw,'w',filters=[{'id':lzma.FILTER_LZMA2,'dict_size':64*1024*1024}]) as compressed:
            with tarfile.open(fileobj=compressed,mode='w|') as bundle:
                for row in manifest['files']:
                    path=checked_path(root,row)
                    if not path.is_file():raise ValueError('Candidate disappeared before archival')
                    info=tarfile.TarInfo(row['path']);info.size=row['bytes'];info.mtime=0;info.mode=0o600
                    with path.open('rb') as source:bundle.addfile(info,source)
                    checked_path(root,row)
    verify(manifest,destination)
    return {'sha256':identity(destination),'bytes':destination.stat().st_size,'members':len(manifest['files'])}

def verify(manifest,archive_path):
    expected={row['path']:row for row in manifest['files']}
    seen=set()
    with tarfile.open(archive_path,'r|xz') as bundle:
        for member in bundle:
            row=expected.get(member.name)
            if row is None or member.name in seen or not member.isfile() or member.size!=row['bytes']:
                raise ValueError('Retention archive member identity changed')
            digest=hashlib.sha256();size=0
            with bundle.extractfile(member) as stream:
                while piece:=stream.read(1024*1024):digest.update(piece);size+=len(piece)
            if size!=row['bytes'] or digest.hexdigest()!=row['sha256']:raise ValueError('Retention restore hash changed')
            seen.add(member.name)
    if seen!=set(expected):raise ValueError('Retention archive is incomplete')
    return {'complete_members_verified':len(seen),'complete_bytes_verified':sum(r['bytes'] for r in expected.values())}


def process_proof(root):
    R=owned(root)
    import ctypes as C,ctypes.wintypes as W,json,os,datetime
    from pathlib import Path
    k=C.WinDLL('kernel32',use_last_error=True);n=C.WinDLL('ntdll')
    class PE(C.Structure):
     _fields_=[('dwSize',W.DWORD),('cntUsage',W.DWORD),('th32ProcessID',W.DWORD),('th32DefaultHeapID',C.c_size_t),('th32ModuleID',W.DWORD),('cntThreads',W.DWORD),('th32ParentProcessID',W.DWORD),('pcPriClassBase',W.LONG),('dwFlags',W.DWORD),('szExeFile',W.WCHAR*260)]
    class US(C.Structure):_fields_=[('Length',W.USHORT),('MaximumLength',W.USHORT),('Buffer',C.c_void_p)]
    k.CreateToolhelp32Snapshot.restype=W.HANDLE;k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD]
    k.Process32FirstW.argtypes=[W.HANDLE,C.POINTER(PE)];k.Process32NextW.argtypes=[W.HANDLE,C.POINTER(PE)]
    k.OpenProcess.restype=W.HANDLE;k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.CloseHandle.argtypes=[W.HANDLE]
    n.NtQueryInformationProcess.argtypes=[W.HANDLE,W.ULONG,C.c_void_p,W.ULONG,C.POINTER(W.ULONG)]
    h=k.CreateToolhelp32Snapshot(2,0);p=PE();p.dwSize=C.sizeof(p);ok=k.Process32FirstW(h,C.byref(p));rows=[];errors=[]
    while ok:
     if p.szExeFile.lower() in ('python.exe','pythonw.exe','pwsh.exe','powershell.exe') and p.th32ProcessID!=os.getpid():
      ph=k.OpenProcess(0x1000,False,p.th32ProcessID)
      if ph:
       size=W.ULONG();n.NtQueryInformationProcess(ph,60,None,0,C.byref(size))
       if 0<size.value<1048576:
        buf=C.create_string_buffer(size.value);status=n.NtQueryInformationProcess(ph,60,buf,size,C.byref(size))
        if status==0:
         u=US.from_buffer(buf);lo=C.addressof(buf);hi=lo+len(buf)
         if lo<=u.Buffer<=hi and u.Buffer+u.Length<=hi:
          cmd=C.wstring_at(u.Buffer,u.Length//2)
          rows.append({'pid':p.th32ProcessID,'parent_pid':p.th32ParentProcessID,'name':p.szExeFile,'command_line':cmd})
         else:errors.append({'pid':p.th32ProcessID,'error':'out_of_buffer'})
        else:errors.append({'pid':p.th32ProcessID,'status':status})
       k.CloseHandle(ph)
      else:errors.append({'pid':p.th32ProcessID,'error':C.get_last_error()})
     ok=k.Process32NextW(h,C.byref(p))
    k.CloseHandle(h)
    k.CreateFileW.restype=W.HANDLE;k.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE]
    class OVER(C.Structure):_fields_=[('Internal',C.c_size_t),('InternalHigh',C.c_size_t),('Offset',W.DWORD),('OffsetHigh',W.DWORD),('hEvent',W.HANDLE)]
    k.LockFileEx.argtypes=[W.HANDLE,W.DWORD,W.DWORD,W.DWORD,W.DWORD,C.POINTER(OVER)];k.UnlockFileEx.argtypes=[W.HANDLE,W.DWORD,W.DWORD,W.DWORD,C.POINTER(OVER)]
    locks=[]
    for name in ('launcher.lock','worker.lock'):
     f=k.CreateFileW(str(R/name),0xC0000000,3 if name=='worker.lock' else 0,None,3,0,None)
     available=f!=C.c_void_p(-1).value
     if available:
      ov=OVER();available=bool(k.LockFileEx(f,3,0,1,0,C.byref(ov)))
      if available:k.UnlockFileEx(f,0,1,0,C.byref(ov))
      k.CloseHandle(f)
     locks.append({'name':name,'available':available})
    controllers=[r for r in rows if any(x in r['command_line'] for x in ('underwriting_local.py','underwriting_local_worker.py','underwriting_local.ps1')) or ('valuation-underwriting' in r['command_line'] and 'launch.ps1' in r['command_line'])]
    proof={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'processes':controllers,'locks':locks,'inventory_errors':errors,'no_controller_stopped':True,'no_lock_removed':True,'python_powershell_inventory':rows}
    return proof

@contextmanager
def idle_runtime(root):
    root=owned(root)
    if os.name!='nt':raise ValueError('Native Windows runtime inventory is required before pruning')
    proof=process_proof(root)
    if proof['processes'] or proof['inventory_errors'] or not all(x['available'] for x in proof['locks']):
        raise ValueError('A running controller or unavailable inventory keeps retention held')
    import msvcrt
    handles=[]
    try:
        for name in ('launcher.lock','worker.lock'):
            handle=(root/name).open('r+b');handles.append(handle)
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        yield proof
    finally:
        for handle in reversed(handles):
            try:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            finally:handle.close()

def apply(root,manifest,archive_path,remote_proof,*,storage,expected_manifest_sha256):
    root=owned(root)
    from private_storage import encoded_json,sha
    if sha(encoded_json(manifest))!=expected_manifest_sha256:raise ValueError('Exact reviewed pruning list identity changed')
    if identity(archive_path)!=remote_proof['archive_sha256'] or not remote_proof.get('remote_full_restore_verified'):
        raise ValueError('Verified complete private restoration is required')
    raw=storage.restore(remote_proof['logical_path'])
    if raw is None or hashlib.sha256(raw).hexdigest()!=remote_proof['archive_sha256']:
        raise ValueError('Required private restoration archive is missing or changed')
    verify(manifest,archive_path)
    removed=[];retained=[]
    with idle_runtime(root) as process:
        for row in manifest['files']:
            try:path=checked_path(root,row)
            except ValueError:
                retained.append({'path':row['path'],'reason':'changed or no longer disposable; preserved'});continue
            if not path.is_file():
                retained.append({'path':row['path'],'reason':'already absent; no deletion'});continue
            # Exact single-file unlink only, after path/root/type/full-hash checks.
            # No directory, lock, Git history or protected evidence is removed.
            path.unlink();removed.append(row)
    return {'schema_version':'owned-runtime-retention-result/1','observed_at':datetime.now(timezone.utc).isoformat(),
            'manifest_sha256':expected_manifest_sha256,'archive_sha256':remote_proof['archive_sha256'],
            'files_removed':len(removed),'bytes_reclaimed':sum(x['bytes'] for x in removed),
            'removed':removed,'retained':retained,'process_lock_proof':process,
            'protected_paid_source_evidence_ledgers_history_pruned':False}

def retention_selection(records,*,now,referenced=(),log_days=14,preview_days=30,rollback_count=5):
    """Only explicitly registered disposable artifacts may expire.

    Unregistered files and all referenced/evidence/paid/audit objects remain.
    This policy selects candidates; full archival and exact apply gates remain.
    """
    if (log_days,preview_days,rollback_count)!=(14,30,5):raise ValueError('Owner retention policy changed')
    references=set(referenced);protected=('valuation-underwriting/','evidence/','audit/','legacy/')
    rollback=sorted((r for r in records if r.get('kind')=='rollback_deployment'),key=lambda r:r['created_at'],reverse=True)
    keep={r['path'] for r in rollback[:rollback_count]}|references
    selected=[]
    for row in records:
        path=row['path']
        if path in keep or path.startswith(protected) or row.get('required_audit') or not row.get('rebuild_verified'):
            continue
        kind=row.get('kind');days={'disposable_success_log':log_days,'rebuildable_preview':preview_days}.get(kind)
        if kind=='rollback_deployment':selected.append(row)
        elif days is not None and (now-datetime.fromisoformat(row['created_at'])).total_seconds()>days*86400:
            selected.append(row)
    return selected

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['plan','apply']);p.add_argument('--runtime-home',required=True,type=Path);p.add_argument('--manifest',required=True,type=Path);p.add_argument('--archive',type=Path);p.add_argument('--remote-proof',type=Path);p.add_argument('--manifest-sha256');p.add_argument('--result',type=Path)
    a=p.parse_args()
    if a.action=='plan':a.manifest.write_text(json.dumps(inventory(a.runtime_home),indent=2),encoding='utf-8');return
    if not all((a.archive,a.remote_proof,a.manifest_sha256,a.result)):p.error('Apply requires exact manifest hash, full archive, private restore proof and result path')
    from private_storage import PrivateStorage
    result=apply(a.runtime_home,json.loads(a.manifest.read_text(encoding='utf-8')),a.archive,json.loads(a.remote_proof.read_text(encoding='utf-8')),storage=PrivateStorage(),expected_manifest_sha256=a.manifest_sha256)
    a.result.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({'files_removed':result['files_removed'],'bytes_reclaimed':result['bytes_reclaimed']}))
if __name__=='__main__':main()
