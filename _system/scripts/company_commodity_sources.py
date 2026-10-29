"""Attach captured commodity originals to only the model's reviewed company scope."""
from pathlib import Path
from urllib.parse import urlparse, unquote

from commodity_common import load
from commodity_inputs import REQUIRED, FREE_INPUTS


def originals(root, vault):
    local=Path(root)/'_private/commodity'
    preserved=Path(vault)/'dashboard-private/commodity-inputs' if vault else None
    base=local if (local/'observations.json').is_file() else preserved
    if not base or not (base/'observations.json').is_file():return
    panel=load(base/'observations.json',{})
    captures={r.get('url'):r for p in (base/'free-vintages').glob('*.json') if (r:=load(p,{})).get('url')}
    by_url={}
    def add(url,sha,model,tickers,title=None,period=None,path=None):
        if not url or not sha:return
        key=(url,sha)
        item=by_url.setdefault(key,{'url':url,'sha256':sha,'tickers':set(),'models':set(),
                                   'title':title or unquote(Path(urlparse(url).path).name) or 'Commodity source',
                                   'date':period,'path':path or base/'objects'/sha})
        item['tickers'].update(tickers);item['models'].add(model)
    for config_path in (Path(root)/'_system/scripts/commodity_configs').glob('*.json'):
        config=load(config_path);model=config['id'];tickers=config['related_tickers']
        for ref in config.get('sources',[]):
            captured=panel.get('sources',{}).get(ref['id'],{})
            add(captured.get('resolved_url') or ref['url'],captured.get('sha256'),model,tickers,ref.get('label'),ref.get('published_at'))
        for key in REQUIRED[model]+(['cushing_working_capacity'] if model=='crude' else []):
            ref=panel.get('series',{}).get(key,{})
            add(ref.get('source_url'),ref.get('sha256'),model,tickers,key.replace('_',' ').title())
        for key,_ in FREE_INPUTS[model]:
            dataset=panel.get('free_inputs',{}).get(key,{})
            add(dataset.get('source_url'),dataset.get('sha256'),model,tickers,dataset.get('title'),dataset.get('period'))
            add(dataset.get('monthly_source_url'),dataset.get('monthly_sha256'),model,tickers,'Copper monthly exchange inventory history')
            for row in dataset.get('rows',[])+dataset.get('history',[]):
                add(row.get('source_url'),row.get('sha256'),model,tickers,period=row.get('period'))
            # A report with an unreadable numeric table is still relevant
            # research. Keep its captured original in the company library.
            for failure in dataset.get('parse_failures',[]):
                url=failure.get('source_url');capture=captures.get(url,{})
                add(url,capture.get('sha256'),model,tickers)
        if model=='crude':
            for path in (base/'forecast-vintages').glob('*.json'):
                ref=load(path,{})
                if ref.get('sha256'):
                    add(ref.get('source_url'),ref['sha256'],model,tickers,'EIA archived oil forecast · '+ref.get('published_at',''),ref.get('published_at'),base/'forecast-vintages'/(ref['sha256']+'.xlsx'))
    for item in by_url.values():
        item['tickers']=sorted(item['tickers']);item['models']=sorted(item['models'])
        yield item


def build(builder):
    count=0
    for item in originals(builder.root,builder.vault):
        owners=[t for t in item['tickers'] if t in builder.companies]
        if not owners:continue
        state='awaiting_extraction';text='';recovered={}
        try:
            data=item['path'].read_bytes()
            from company_sources import digest
            if digest(data)!=item['sha256']:raise ValueError('Commodity original checksum mismatch')
            suffix=Path(urlparse(item['url']).path).suffix.lower()
            if data.startswith(b'%PDF'):suffix='.pdf'
            elif data.startswith(b'PK'):
                import io,zipfile
                with zipfile.ZipFile(io.BytesIO(data)) as book:
                    if 'xl/workbook.xml' in book.namelist():suffix='.xlsx'
            elif data.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):suffix='.xls'
            elif b'<html' in data[:2000].lower() or b'<!doctype html' in data[:2000].lower():suffix='.html'
            elif suffix=='.csv':suffix='.csv'
            recovered=load(builder.cache/'commodity-text'/(item['sha256']+'.json'),{})
            if recovered.get('status')=='indexed' and recovered.get('original_sha256')==item['sha256'] and digest(recovered.get('text',''))==recovered.get('text_sha256'):
                text,state=recovered['text'],'indexed'
            else:
                recovered={}
                text,state,_=builder.cached_extract(data,suffix)
        except (OSError,ValueError):
            builder.file_failures['shared:commodity_originals']+=1
            state='access_unavailable'
        # Assign scope from the reviewed commodity model, not from incidental
        # company names inside a global report or a large statistical workbook.
        record=builder.base('commodity:'+item['sha256'],item['title'],'shared:commodity_originals',state=state,
                            date=item['date'],locations=[{'kind':'source','url':item['url'],'label':'Original commodity publication'}],path='commodity/'+item['title'])
        record.update(text=text,category='industry',relationships=[{'ticker':t,'relationship':'industry_context',
                      'reason':'Source for the '+', '.join(item['models'])+' model relevant to this company.',
                      'match':'reviewed_commodity_scope','passages':[]} for t in owners],review=[])
        record['content_sha256']=item['sha256']
        if state=='indexed' and recovered.get('extraction',{}).get('ocr_pages'):
            record['extraction_review']='Automatic OCR; verify against the original'
        builder.add(record,['sha:'+item['sha256'],'url:'+item['url']]);count+=1
    builder.receipt('shared:commodity_originals',count)
