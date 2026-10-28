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
