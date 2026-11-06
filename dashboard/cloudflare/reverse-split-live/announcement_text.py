"""Bounded text-only announcement extraction. No credentials, OCR inference or network."""
import base64,json,sys
def extract(raw):
    if len(raw)>24*1024*1024 or not raw.startswith(b'%PDF-'):raise ValueError('PDF byte limit or signature')
    import pymupdf
    with pymupdf.open(stream=raw,filetype='pdf') as doc:
        if doc.is_encrypted or doc.page_count>120:raise ValueError('Encrypted or over-limit PDF')
        parts=[]
        for page in doc:
            text=page.get_text()
            if len(text.strip())<40 and (page.get_images() or page.get_drawings()):raise ValueError('Non-text page requires verified text')
            if not text.strip():
                continue
            parts.append(text)
        text='\n\n'.join(parts)
        if not text.strip() or len(text)>2_000_000:raise ValueError('PDF text missing or over limit')
        return {'schema':'announcement_text.v1','text':text,'pages':doc.page_count,'complete':True}
if __name__=='__main__':
    try:
        payload=sys.stdin.buffer.read(40_000_001)
        if len(payload)>40_000_000:raise ValueError('Input limit')
        print(json.dumps(extract(base64.b64decode(json.loads(payload)['base64'],validate=True))))
    except Exception:raise SystemExit(1)
