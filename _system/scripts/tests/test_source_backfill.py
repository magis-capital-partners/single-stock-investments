import io
import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from company_source_queue import SourceQueue
from company_source_cache import pack,restore
from backfill_company_sources import extract_complete,transcript_for
from company_sources import SourceIndex


def test_empty_scan_outcome_survives_metadata_union():
    index=SourceIndex()
    index.add({'id':'a','processing_status':'awaiting_extraction','text':''},['original'])
    index.add({'id':'b','processing_status':'needs_ocr','text':''},['original'])
    assert index.records['a']['processing_status']=='needs_ocr'


def test_retry_status_is_scoped_to_selected_collection(tmp_path):
    q=SourceQueue(tmp_path/'work.sqlite')
    q.enqueue([{'key':kind,'kind':kind,'payload':{}} for kind in ['git','media']])
    for kind in ['git','media']:
        job=q.claim([kind]);q.finish(job['key'],'indexed')
    q.reset(['indexed'],['media'])
    assert q.report()['by_kind']['git']=={'indexed':1}
    assert q.report()['by_kind']['media']=={'pending':1}
    q.close()


def test_queue_resume_revision_retry_and_private_checkpoint(tmp_path):
    q=SourceQueue(tmp_path/'work.sqlite')
    q.enqueue([{'key':'drive:a:1','kind':'drive','payload':{'id':'a'},'priority':50},
               {'key':'drive:b:1','kind':'drive','payload':{'id':'b'}}])
    first=q.claim();assert first['key']=='drive:a:1'
    q.finish(first['key'],'indexed',result={'text':'private'})
    q.enqueue([{'key':'drive:a:1','kind':'drive','payload':{'id':'a'}},
               {'key':'drive:a:2','kind':'drive','payload':{'id':'a'},'priority':100}])
    assert q.claim()['key']=='drive:a:2'
    q.checkpoint(tmp_path/'queue-checkpoints');q.close()
    restored=SourceQueue(tmp_path/'fresh.sqlite')
    assert restored.report()['by_kind']['drive']=={'indexed':1,'pending':2}
    other=restored.claim();assert other['key']=='drive:b:1'
    restored.finish(other['key'],'indexed')
    revision=restored.claim();assert revision['key']=='drive:a:2'
    restored.finish(revision['key'],'retry',error='temporary')
    assert restored.claim() is None
    restored.close()


def test_expired_lease_is_recoverable_and_active_lease_is_exclusive(tmp_path):
    q=SourceQueue(tmp_path/'work.sqlite')
    q.enqueue([{'key':'a','kind':'git','payload':{}}])
    assert q.claim(lease_seconds=-1)['attempts']==1
    assert q.claim()['attempts']==2
    assert q.claim() is None
    q.close()


def test_partial_pdf_is_not_indexed():
    fitz=pytest.importorskip('fitz')
    pdf=fitz.open();pdf.new_page().insert_text((30,30),'A complete textual page with enough readable research. '*4)
    page=pdf.new_page();image=fitz.Pixmap(fitz.csRGB,(0,0,20,20));image.clear_with(255)
    page.insert_image(fitz.Rect(0,0,200,200),pixmap=image)
    text,state,detail=extract_complete(pdf.tobytes(),'.pdf')
    assert 'research' in text and state=='needs_ocr' and detail['missing_pages']==[2]


def test_epub_reads_spine_order_and_preserves_scan_gap():
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        z.writestr('META-INF/container.xml','<container><rootfile full-path="book/package.opf"/></container>')
        z.writestr('book/package.opf','<package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="a" href="a.xhtml"/><item id="b" href="b.xhtml"/></manifest><spine><itemref idref="b"/><itemref idref="a"/></spine></package>')
        z.writestr('book/b.xhtml','<html><body>Company discussion in chapter one.</body></html>')
        z.writestr('book/a.xhtml','<html><body><img src="scan.png"/></body></html>')
    text,state,details=extract_complete(b.getvalue(),'.epub')
    assert text.startswith('Company discussion') and state=='needs_ocr'
    assert details['missing_chapters']==['book/a.xhtml']


def test_transcript_companion_and_cache_archive_portability(tmp_path):
    audio=tmp_path/'podcasts/audio-cache/episode.mp3';audio.parent.mkdir(parents=True);audio.write_bytes(b'audio')
    transcript=tmp_path/'podcasts/episodes/show/episode.txt';transcript.parent.mkdir(parents=True);transcript.write_text('Transcript')
    assert transcript_for(audio,tmp_path)==transcript
    cache=tmp_path/'cache';(cache/'git').mkdir(parents=True);(cache/'git/a.json').write_text('{"text":"private"}')
    (cache/'work.sqlite').write_bytes(b'not portable')
    archive=tmp_path/'archive';assert pack(cache,archive)['files']==1
    target=tmp_path/'restored';restore(archive,target)
    assert json.loads((target/'git/a.json').read_text())['text']=='private'
    assert not (target/'work.sqlite').exists()
    part=next(archive.glob('*.zip'));part.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='checksum'):restore(archive,tmp_path/'corrupt')
