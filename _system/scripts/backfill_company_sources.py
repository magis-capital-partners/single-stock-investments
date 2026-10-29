#!/usr/bin/env python3
"""Resume all inventoried source extraction without rebuilding or publishing the website.

Uses local files, Git objects and HTTPS only. No brokerage or market-data terminal.
Every revision has a persisted outcome; failed/partial OCR is never called indexed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.parse import unquote, urlparse

from company_source_queue import SourceQueue
from company_sources import SOURCE_SUFFIXES, digest, extract
from company_extract_formats import EXTRA_SUFFIXES
from build_company_research import ROOT, IGNORE_NAMES, load, read_companies, write


def complete_cache(cached, suffix):
    if cached.get('status') != 'indexed' or not cached.get('text'):
        return False
    required = {'.pdf': 'pages', '.epub': 'chapters'}.get(suffix)
    return not required or bool(cached.get('extraction', {}).get(required))


def preserve_outcome(cache, job, status, result, error):
    """Expose failed originals to publication without erasing recovered text."""
    if status == 'indexed' or job['kind'] not in {'git','drive'}:
        return
    payload=job['payload']
    if job['kind']=='git':
        target=cache/'git'/(payload['sha']+'.json')
    else:
        revision=payload.get('revision')
        if not revision or revision in {'unknown','discover'}:return
        target=cache/'drive'/(digest(payload['id']+revision)+'.json')
    prior=load(target)
    if not prior.get('text'):
        write(target,{**prior,'version':1,'text':'','status':status,'attempted_at':time.time(),'error':error})


def audit_cache(queue, cache):
    """Requeue legacy PDF/ebook results that lack whole-document evidence."""
    reset = []
    for row in queue.db.execute("SELECT key,kind,payload,result FROM jobs WHERE status='indexed' AND kind IN ('git','drive')"):
        payload = json.loads(row['payload'])
        suffix = Path(payload.get('path') or payload.get('title') or '').suffix.lower()
        if suffix not in {'.pdf', '.epub'}:
            continue
        result = json.loads(row['result'] or '{}')
        name = Path(result.get('cache', '').replace('\\', '/')).name
        path = cache / row['kind'] / name
        if not name or not complete_cache(load(path), suffix):
            reset.append((row['key'],))
    queue.db.executemany("UPDATE jobs SET status='pending',retry_at=0 WHERE key=? AND status='indexed'", reset)
    queue.db.commit()
    return len(reset)


def transcript_for(path, vault):
    if path.suffix.lower() not in {'.mp3','.m4a','.mp4','.wav'}:
        return None
    for suffix in ('.txt','.md'):
        candidate = path.with_suffix(suffix)
        if candidate.is_file() and candidate.stat().st_size:
            return candidate
    if vault:
        for collection in ('podcasts','videos'):
            for candidate in (vault/collection/'episodes').glob('*/'+path.stem+'.txt'):
                if candidate.stat().st_size:
                    return candidate
    return None


def extract_complete(data, suffix, *, ocr=False):
    if not data.strip():
        return '', 'empty_source', {'reason':'Original contains no bytes or only whitespace'}
    if suffix == '.epu':
        suffix = '.epub'
    if suffix in {'.py', '.r', '.sql'}:
        # Model source is searchable text; never import or execute it.
        text, state = extract(data, '.txt')
        return text, state, {'format': 'model_source_text'}
    if suffix == '.doc':
        from legacy_doc import extract_text
        try:
            result=extract_text(data)
            return result.text,'indexed' if result.text.strip() else 'empty_source',{'format':'legacy_word','parser':result.parser,'warnings':result.warnings}
        except Exception as exc:
            return '', 'access_unavailable' if 'encrypt' in str(exc).lower() else 'failed', {'error':str(exc)[:180]}
    if suffix in {'.mobi','.azw3'}:
        from tempfile import TemporaryDirectory
        from mobi.kindleunpack import unpackBook
        # The unpacker supports unencrypted ebooks only. No DRM removal.
        try:
            with TemporaryDirectory(prefix='ssi-ebook-') as directory:
                temporary=Path(directory);original=temporary/('original'+suffix);original.write_bytes(data)
                destination=temporary/'unpacked';destination.mkdir()
                unpackBook(str(original),str(destination),epubver='A')
                candidates=[destination/'mobi8/original.epub',destination/'mobi7/book.html',destination/'original.001.pdf']
                converted=next((p for p in candidates if p.is_file()),None)
                if not converted:return '', 'failed', {'error':'No readable book rendition'}
                text,status,details=extract_complete(converted.read_bytes(),converted.suffix,ocr=ocr)
                return text,status,{'format':suffix.lstrip('.'),'conversion':'unencrypted Kindle unpack',**details}
        except (Exception,SystemExit) as exc:
            return '', 'access_unavailable' if re.search(r'DRM|encrypt',str(exc),re.I) else 'failed', {'error':str(exc)[:180]}
    if suffix in {'.png','.jpg','.jpeg','.jpg_large'}:
        if not ocr:return '', 'needs_ocr', {'format':'image'}
        try:
            import fitz
            with fitz.open(stream=data) as image:
                return extract_complete(image.convert_to_pdf(),'.pdf',ocr=True)
        except Exception as exc:return '', 'needs_ocr', {'error':type(exc).__name__}
    if suffix == '.epub':
        import io,posixpath,zipfile
        from xml.etree import ElementTree as ET
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                container=ET.fromstring(z.read('META-INF/container.xml'))
                package=next(e.attrib['full-path'] for e in container.iter() if e.tag.endswith('rootfile'))
                root=ET.fromstring(z.read(package));directory=posixpath.dirname(package)
                items={e.attrib['id']:e.attrib for e in root.iter() if e.tag.endswith('}item')}
                ordered=[items[e.attrib['idref']] for e in root.iter() if e.tag.endswith('}itemref')]
                paths=[posixpath.normpath(posixpath.join(directory,unquote(item['href']).split('#')[0])) for item in ordered]
                if 'META-INF/encryption.xml' in z.namelist():
                    encrypted=ET.fromstring(z.read('META-INF/encryption.xml'))
                    if any(e.attrib.get('URI') in paths for e in encrypted.iter()):
                        return '', 'access_unavailable', {'reason':'Encrypted book content requires an authorized readable edition'}
                bodies=[];missing=[];ocr_chapters=[]
                for path in paths:
                    raw=z.read(path);body,state=extract(raw,'.html')
                    if not body.strip() and re.search(br'<(?:img|svg|image)\b',raw,re.I):
                        recovered=False
                        if ocr:
                            from html.parser import HTMLParser
                            class Images(HTMLParser):
                                def __init__(self):super().__init__();self.refs=[]
                                def handle_starttag(self,tag,attrs):
                                    if tag in {'img','image'}:
                                        attrs=dict(attrs)
                                        ref=attrs.get('src') or attrs.get('href') or attrs.get('xlink:href')
                                        if ref:self.refs.append(ref)
                            parser=Images();parser.feed(raw.decode('utf-8',errors='replace'))
                            recovered=bool(parser.refs);parts=[]
                            for ref in dict.fromkeys(parser.refs):
                                uri=urlparse(ref)
                                image_path=posixpath.normpath(posixpath.join(posixpath.dirname(path),unquote(uri.path)))
                                if uri.scheme or uri.netloc or image_path.startswith(('../','/')) or image_path not in z.namelist():
                                    recovered=False;continue
                                image_text,image_state,details=extract_complete(z.read(image_path),'.png',ocr=True)
                                if image_state not in {'indexed','empty_source'}:recovered=False
                                parts.append(image_text)
                            body='\n'.join(parts)
                        if recovered:ocr_chapters.append(path)
                        else:missing.append(path)
                    bodies.append(body)
                return '\n\f\n'.join(bodies),'needs_ocr' if missing else 'indexed' if any(bodies) else 'empty_source',{'chapters':len(paths),'missing_chapters':missing,'ocr_chapters':ocr_chapters,'ocr_review':'unreviewed' if ocr_chapters else None}
        except Exception as exc:return '', 'failed', {'error':type(exc).__name__}
    if suffix != '.pdf':
        text, state = extract(data, suffix)
        return text, state, {}
    import fitz
    try:
        with fitz.open(stream=data, filetype='pdf') as pdf:
            if pdf.needs_pass:
                return '', 'access_unavailable', {'reason':'Original PDF requires a password'}
            pages, missing, ocr_pages = [], [], []
            for i, page in enumerate(pdf):
                body = page.get_text().strip()
                # A scan can have a small footer/header but no body text.
                scan = len(body) < 80 and (bool(page.get_images()) or (ocr and not body))
                ocr_complete = False
                if scan and ocr:
                    try:
                        body = page.get_text(textpage=page.get_textpage_ocr(language='eng',dpi=200,full=True)).strip()
                        ocr_complete = True
                        ocr_pages.append(i+1)
                    except Exception:
                        pass
                # Short covers and image-only closing pages are legitimate.
                # A completed OCR pass is indexed as automatic, unreviewed
                # extraction; failed OCR stays pending, regardless of length.
                if scan and not ocr_complete:
                    missing.append(i+1)
                pages.append(body)
            return '\n\f\n'.join(pages), 'needs_ocr' if missing else ('indexed' if any(pages) else 'empty_source'), {'pages':len(pages),'missing_pages':missing,'ocr_pages':ocr_pages,'ocr_review':'unreviewed' if ocr_pages else None}
    except Exception as exc:
        return '', 'failed', {'error':type(exc).__name__}


def seed(root, cache, queue, vault=None, kinds=('git','drive','media')):
    try:
        companies = read_companies(root)
    except RuntimeError:
        # A missing publication snapshot must not prevent recovery of the
        # already inventoried corpus. Never invent a smaller issuer universe.
        manifest=next((load(cache.parent/name/'manifest.json') for name in ('site','full-current','full') if (cache.parent/name/'manifest.json').is_file()),{})
        if not manifest.get('tickers'):
            raise
        companies={t:{} for t in manifest['tickers']}
        print('Using the prior complete company inventory while private publication inputs recover.',flush=True)
    preferred = set(load(root/'_system/reference/core_compounders.json').get('tickers', []))
    preferred.update(k for k,v in companies.items() if v.get('position') or v.get('held'))
    jobs = []
    if 'git' in kinds:
        tree = subprocess.run(['git','ls-tree','-r','-z','HEAD'],cwd=root,capture_output=True,check=True).stdout.decode('utf-8')
        for entry in tree.split('\0'):
            if '\t' not in entry:
                continue
            header, relative = entry.split('\t',1)
            bits = relative.split('/')
            path = Path(relative)
            if len(bits)<3 or bits[0] not in companies or bits[1] not in {'research','third-party-analyses','investor-documents','models','transcripts','financials'}:
                continue
            if path.suffix.lower() not in SOURCE_SUFFIXES | EXTRA_SUFFIXES or path.name in IGNORE_NAMES or re.search(r'(?:source_inventory|activist_reports_index|latest|security_identity|classification|human_decision|download|readiness|audit|committee_packet)',path.stem,re.I):
                continue
            sha=header.split()[-1]
            jobs.append({'key':'git:'+sha,'kind':'git','priority':100 if bits[0] in preferred else 0,'payload':{'sha':sha,'path':relative}})
    if 'drive' in kinds:
        inventory_cache=cache if (cache/'index.json').exists() or not vault else vault/'dashboard-private/company-research-cache'
        index=load(inventory_cache/'index.json')
        for part in index.get('record_parts',[]):
            for rec in load(inventory_cache/part).values():
                if rec.get('processing_status')=='indexed':
                    continue
                for location in rec.get('locations',[]):
                    match=re.search(r'(?:drive\.google\.com/file/d/|docs\.google\.com/(?:document|spreadsheets|presentation)/d/)([\w-]+)',location.get('url',''))
                    if not match:
                        continue
                    revision=rec.get('revision') or 'discover'
                    jobs.append({'key':'drive:'+match[1]+':'+revision,'kind':'drive','priority':100 if any(r['ticker'] in preferred for r in rec.get('relationships',[])) else 0,
                                 'payload':{'id':match[1],'revision':revision,'title':rec['title'],'format':rec.get('format')}})
    if 'media' in kinds and vault:
        for collection in ('podcasts','videos'):
            for path in (vault/collection/'audio-cache').glob('*'):
                if path.suffix.lower() in {'.mp3','.m4a','.mp4','.wav'}:
                    jobs.append({'key':'media:'+str(path.relative_to(vault)), 'kind':'media','priority':150,'payload':{'path':str(path)}})
    queue.enqueue(jobs)
    return len(jobs)


class Worker:
    def __init__(self, root, cache, vault=None, local_source=None, ocr=False, transcribe=False):
        self.root,self.cache,self.vault,self.local_source=root,cache,vault,local_source
        self.ocr,self.transcribe=ocr,transcribe
        self.service=None
        self.manifest=load(root/'dashboard/private-assets.json').get('repository_assets',{})
        self.git=None
        self.drive_inventory=None

    def git_bytes(self, payload):
        relative,sha=payload['path'],payload['sha']
        entry=self.manifest.get(relative)
        if entry and self.vault:
            from private_dashboard_assets import private_object
            private=private_object(self.vault,entry['private_sha256'])
            data=private.read_bytes()
            if digest(data)!=entry['private_sha256']:
                raise ValueError('Private source hash mismatch')
            return data
        for base in (self.root,self.local_source):
            if not base:
                continue
            path=base/relative
            if path.is_file():
                data=path.read_bytes()
                if hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()==sha:
                    return data
        # Persistent batch avoids a process per historical original. It reads
        # immutable committed objects even when another checkout has local edits.
        if self.git is None:
            self.git=subprocess.Popen(['git','cat-file','--batch'],cwd=self.root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        self.git.stdin.write((sha+'\n').encode());self.git.stdin.flush()
        header=self.git.stdout.readline().decode().strip().split()
        if len(header)!=3 or header[1]!='blob':
            raise FileNotFoundError('Git object unavailable')
        data=self.git.stdout.read(int(header[2]));self.git.stdout.read(1)
        return data

    def run(self, job):
        p=job['payload'];kind=job['kind']
        if kind=='media':
            path=Path(p['path']);companion=transcript_for(path,self.vault)
            recovered=self.cache/'transcripts'/(path.stem+'.txt')
            if companion is None and recovered.is_file():companion=recovered
            if companion is None and self.transcribe:
                from fetch_podcast_transcript import whisper_transcribe
                local_audio=self.cache/'transcripts'/path.name
                local_audio.parent.mkdir(parents=True,exist_ok=True)
                if not local_audio.exists():shutil.copy2(path,local_audio)
                text=whisper_transcribe(local_audio)
                if isinstance(text,tuple):
                    text=text[0]
                if text and len(text.split())>=40:
                    # Save in the private cache; never overwrite the vault's editorial files.
                    companion=self.cache/'transcripts'/(path.stem+'.txt')
                    companion.parent.mkdir(parents=True,exist_ok=True)
                    companion.write_text(text,encoding='utf-8')
            if companion:
                text=companion.read_text(encoding='utf-8')
                write(self.cache/'media'/(digest(path.name)+'.json'),{'text':text,'status':'indexed','transcript_path':str(companion),
                      'transcript_kind':'automatic' if companion.parent==self.cache/'transcripts' else 'existing','review_status':'unreviewed'})
                return 'indexed',{'transcript_path':str(companion)},None
            return 'needs_transcript',{},'No matching transcript; transcription required'
        if kind=='git':
            target=self.cache/'git'/(p['sha']+'.json');suffix=Path(p['path']).suffix.lower()
            cached=load(target)
            if complete_cache(cached, suffix):
                if cached.get('content_md5'):
                    write(self.cache/'md5'/(cached['content_md5']+'.json'),{'path':target.relative_to(self.cache).as_posix()})
                return 'indexed',{'cache':str(target),'reused':True},None
            data=self.git_bytes(p)
            if b'"private_snapshot"' in data[:2048]:
                try:
                    if json.loads(data).get('private_snapshot'):
                        return 'access_unavailable',{},'Private snapshot object missing; placeholder is not research text'
                except ValueError:
                    pass
        elif kind=='drive':
            # The discovery revision is immutable cache identity. Reuse it
            # before an API round trip; subsequent discovery queues any change.
            revision=p.get('revision')
            suffix=Path(p.get('title','')).suffix.lower()
            if revision and revision not in {'discover','unknown'}:
                target=self.cache/'drive'/(digest(p['id']+revision)+'.json')
                cached=load(target)
                if complete_cache(cached,suffix):
                    return 'indexed',{'cache':str(target),'reused':True},None
                if re.fullmatch(r'[a-fA-F0-9]{32}',revision):
                    pointer=load(self.cache/'md5'/(revision+'.json'))
                    linked=load(self.cache/pointer['path']) if pointer.get('path') and (self.cache/pointer['path']).resolve().is_relative_to(self.cache.resolve()) else {}
                    if complete_cache(linked,suffix) and linked.get('content_md5', revision)==revision:
                        write(target,linked)
                        return 'indexed',{'cache':str(target),'reused':True,'exact_original':True},None
            from drive_store_common import drive_service,execute_with_retry
            if self.service is None:
                self.service=drive_service(readonly=True)
                transport=getattr(self.service._http,'http',self.service._http)
                transport.timeout=30
            if self.drive_inventory is None:
                self.drive_inventory={row['id']:row for row in load(self.cache/'drive-inventory.json').get('items',[])}
            listed=self.drive_inventory.get(p['id'],{})
            verified_revision = bool(listed.get('md5Checksum') and listed['md5Checksum']==p.get('revision') and listed.get('mimeType')!='application/vnd.google-apps.shortcut')
            meta=listed if verified_revision else execute_with_retry(self.service.files().get(fileId=p['id'],fields='id,name,mimeType,modifiedTime,md5Checksum,shortcutDetails',supportsAllDrives=True))
            if meta['mimeType']=='application/vnd.google-apps.shortcut':
                meta=execute_with_retry(self.service.files().get(fileId=meta['shortcutDetails']['targetId'],fields='id,name,mimeType,modifiedTime,md5Checksum',supportsAllDrives=True))
            revision=meta.get('md5Checksum') or meta.get('modifiedTime') or 'unknown'
            suffix=Path(meta['name']).suffix.lower()
            target=self.cache/'drive'/(digest(p['id']+revision)+'.json')
            cached=load(target)
            if complete_cache(cached, suffix):
                return 'indexed',{'cache':str(target),'reused':True},None
            if meta.get('md5Checksum'):
                pointer=load(self.cache/'md5'/(meta['md5Checksum']+'.json'))
                linked=load(self.cache/pointer['path']) if pointer.get('path') and (self.cache/pointer['path']).resolve().is_relative_to(self.cache.resolve()) else {}
                if complete_cache(linked, suffix):
                    linked['status']='indexed'
                    write(target,linked)
                    return 'indexed',{'cache':str(target),'reused':True,'exact_original':True},None
            exports={'application/vnd.google-apps.document':('text/plain','.txt'),'application/vnd.google-apps.spreadsheet':('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','.xlsx'),'application/vnd.google-apps.presentation':('application/vnd.openxmlformats-officedocument.presentationml.presentation','.pptx')}
            if meta['mimeType'] in exports:
                mime,suffix=exports[meta['mimeType']]
                data=execute_with_retry(self.service.files().export_media(fileId=meta['id'],mimeType=mime))
            else:
                suffix=Path(meta['name']).suffix.lower()
                if suffix not in SOURCE_SUFFIXES | EXTRA_SUFFIXES | {'.py', '.r', '.sql'}:
                    return 'unsupported',{},'Unsupported original format: '+meta['mimeType']
                if suffix in {'.mp3','.mp4','.m4a','.wav'} and not self.transcribe:
                    return 'needs_transcript',{},'Audio requires linked transcript'
                request=self.service.files().get_media(fileId=meta['id'],supportsAllDrives=True)
                # Some text-heavy PDFs compress over 100:1 over HTTP. Request
                # original bytes rather than relaxing transport decode limits.
                if hasattr(request,'headers'):request.headers['accept-encoding']='identity'
                data=execute_with_retry(request)
                if meta.get('md5Checksum') and hashlib.md5(data,usedforsecurity=False).hexdigest()!=meta['md5Checksum']:
                    raise ValueError('Source revision changed during download; rediscover before indexing')
        else:
            raise ValueError('Unsupported queue kind')
        if suffix in {'.mp3','.mp4','.m4a','.wav'} and self.transcribe:
            from fetch_podcast_transcript import whisper_transcribe
            audio=self.cache/'transcripts'/(kind+'-'+(p.get('id') or p['sha'])+suffix)
            audio.parent.mkdir(parents=True,exist_ok=True)
            audio.write_bytes(data)
            transcript=audio.with_suffix('.txt')
            text=transcript.read_text(encoding='utf-8') if transcript.is_file() else whisper_transcribe(audio,{'title':p.get('title','')}) or ''
            status='indexed' if len(text.split())>=40 else 'needs_transcript'
            if status=='indexed':transcript.write_text(text,encoding='utf-8')
            details={'transcript_kind':'automatic','review_status':'unreviewed'}
        else:
            text,status,details=extract_complete(data,suffix,ocr=self.ocr)
        if status=='awaiting_extraction':status='empty_source' if not data.strip() else 'failed'
        if status=='awaiting_transcript':status='needs_transcript'
        md5=hashlib.md5(data,usedforsecurity=False).hexdigest()
        write(target,{'version':1,'text':text,'status':status,'attempted_at':time.time(),'content_sha256':digest(data),'content_md5':md5,'extraction':details})
        write(self.cache/'md5'/(md5+'.json'),{'path':target.relative_to(self.cache).as_posix()})
        # Reuse exact bytes across Drive, Git, OCR and local inventory passes.
        text_target=self.cache/'text'/(digest(data)+'.json')
        text_target.parent.mkdir(parents=True,exist_ok=True)
        temporary=text_target.with_suffix('.'+str(os.getpid())+'.tmp')
        try:
            os.link(target,temporary);temporary.replace(text_target)
        except OSError:
            temporary.unlink(missing_ok=True)
            write(text_target,{'version':1,'text':text,'status':status,'extraction':details})
        return status,{'cache':str(target),**details},None if status=='indexed' else 'Original requires '+status.replace('_',' ')

    def close(self):
        if self.git:
            self.git.stdin.close();self.git.wait(timeout=30)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=ROOT)
    parser.add_argument('--cache',type=Path,default=ROOT/'_private/company-research/cache')
    parser.add_argument('--vault',type=Path)
    parser.add_argument('--local-source',type=Path)
    parser.add_argument('--kind',nargs='+',choices=['git','drive','media'],default=['git','drive','media'])
    parser.add_argument('--seconds',type=int,default=0,help='Zero drains all due work. Progress survives every interruption.')
    parser.add_argument('--max-jobs',type=int,default=0)
    parser.add_argument('--ocr',action='store_true')
    parser.add_argument('--transcribe',action='store_true')
    parser.add_argument('--retry-status',nargs='*',default=[])
    parser.add_argument('--skip-seed',action='store_true')
    parser.add_argument('--discover-drive',action='store_true',help='Enumerate current Drive revisions before resuming the queue')
    parser.add_argument('--audit-cache',action='store_true',help='Reprocess legacy scan/ebook caches without complete extraction evidence')
    parser.add_argument('--only-status',nargs='+',choices=['needs_ocr','needs_transcript','access_unavailable','unsupported','failed','empty_source'],help='Process an explicit recovery lane, e.g. needs_ocr. Does not reset other workers.')
    args=parser.parse_args()
    from vault_paths import research_vault_root
    vault=args.vault or research_vault_root()
    if vault:os.environ['RESEARCH_VAULT_ROOT']=str(vault.resolve())
    queue=SourceQueue(args.cache/'work.sqlite')
    if args.discover_drive:
        from discover_company_sources import discover_drive
        print('Current Drive revisions:',discover_drive(args.source_root,args.cache,queue),flush=True)
    if not args.skip_seed:print('Inventoried work:',seed(args.source_root,args.cache,queue,vault,args.kind),flush=True)
    if args.audit_cache:print('Legacy documents queued for verification:',audit_cache(queue,args.cache),flush=True)
    if args.retry_status:queue.reset(args.retry_status,args.kind)
    worker=Worker(args.source_root,args.cache,vault,args.local_source,args.ocr,args.transcribe)
    started=time.monotonic();checkpointed=started;count=0
    try:
        while (not args.seconds or time.monotonic()-started<args.seconds) and (not args.max_jobs or count<args.max_jobs):
            job=queue.claim(args.kind,lease_seconds=21600 if args.ocr or args.transcribe else 600,statuses=args.only_status or ('pending','retry','running'))
            if not job:break
            try:status,result,error=worker.run(job)
            except (Exception,SystemExit) as exc:
                code=getattr(getattr(exc,'resp',None),'status',None)
                status='access_unavailable' if code in {401,403,404} or isinstance(exc,(FileNotFoundError,SystemExit)) else 'retry' if job['attempts']<4 else 'failed'
                result={};error=f'{type(exc).__name__}: '+str(exc)[:250]
            preserve_outcome(args.cache,job,status,result,error)
            queue.finish(job['key'],status,result=result,error=error)
            count+=1
            if time.monotonic()-checkpointed>=300:
                try:queue.checkpoint(args.cache/'queue-checkpoints')
                except OSError:print('Portable checkpoint deferred; durable queue is intact.',flush=True)
                checkpointed=time.monotonic()
            if count%250==0:print(json.dumps({'processed':count,'elapsed_seconds':round(time.monotonic()-started),**queue.report()}),flush=True)
    finally:
        report={**queue.report(),'processed_this_run':count,'elapsed_seconds':round(time.monotonic()-started)}
        write(args.cache/'backfill-report.json',report)
        queue.checkpoint(args.cache/'queue-checkpoints')
        print(json.dumps(report),flush=True)
        worker.close();queue.close()


if __name__=='__main__':main()
