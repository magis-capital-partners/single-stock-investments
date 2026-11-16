"""Bounded text-only announcement extraction. No credentials, OCR inference or network."""
import base64,hashlib,json,sys
# A page-count exception is never a general expansion of the external reader.
# Every approved report retains its exact original bytes, expected page count,
# native-text checks, byte/output limits and the caller's bounded timeout.
REVIEWED_LARGE_REPORTS={
    '61bcd17da2e271511e736fe00a1db8e8a6e3d76c79654c7efb635dfe85e0bd70':{
        'schema':'announcement_bounded_source_review.v1',
        'source_sha256':'61bcd17da2e271511e736fe00a1db8e8a6e3d76c79654c7efb635dfe85e0bd70',
        'source_url':'https://www.sec.gov/Archives/edgar/data/1866226/000121390026119240/ea031214601ex99-1.pdf',
        'pages':513,'reviewed_at':'2026-11-16T00:24:16Z',
        'scope':'Exact 513-page native-text exhibit only. All pages have native text; no OCR candidate or financial value is supplied by this review. Standard 120-page and unreviewed external 512-page limits remain unchanged.'
    }
}
def extract(raw, profile='standard'):
    if profile not in {'standard','external_primary_report'}:raise ValueError('Unsupported extraction profile')
    byte_limit,page_limit=(48*1024*1024,512) if profile=='external_primary_report' else (24*1024*1024,120)
    if len(raw)>byte_limit or not raw.startswith(b'%PDF-'):raise ValueError('PDF byte limit or signature')
    import pymupdf
    with pymupdf.open(stream=raw,filetype='pdf') as doc:
        review=REVIEWED_LARGE_REPORTS.get(hashlib.sha256(raw).hexdigest()) if profile=='external_primary_report' and doc.page_count>page_limit else None
        reviewed_pages=review and review.get('pages')
        if doc.is_encrypted or (doc.page_count>page_limit and not (isinstance(reviewed_pages,int) and page_limit<reviewed_pages<=768 and doc.page_count==reviewed_pages)):raise ValueError('Encrypted or over-limit PDF')
        parts=[];review_pages=[];ocr_candidates=[]
        for index,page in enumerate(doc):
            text=page.get_text()
            if len(text.strip())<40 and (page.get_images() or page.get_drawings()):
                review_pages.append(index+1)
                if len(review_pages)<=5:
                    try:
                        candidate=page.get_text(textpage=page.get_textpage_ocr(language='eng',dpi=150,full=True))
                        ocr_candidates.append({'page':index+1,'text':candidate[:100000],'verified':False})
                    except Exception:
                        ocr_candidates.append({'page':index+1,'status':'OCR_unavailable_or_failed','verified':False})
            if not text.strip():
                continue
            parts.append(text)
        text='\n\n'.join(parts)
        if (not text.strip() and not review_pages) or len(text)>2_000_000:raise ValueError('PDF text missing or over limit')
        result={'schema':'announcement_text.v1','text':text,'pages':doc.page_count,'complete':not review_pages,'review_pages':review_pages,'ocr_candidates':ocr_candidates,'OCR_admitted_to_signals':False}
        if review:result['reader_review']=review
        return result
if __name__=='__main__':
    try:
        payload=sys.stdin.buffer.read(72_000_001)
        if len(payload)>72_000_000:raise ValueError('Input limit')
        value=json.loads(payload)
        print(json.dumps(extract(base64.b64decode(value['base64'],validate=True),value.get('profile','standard'))))
    except Exception:raise SystemExit(1)
