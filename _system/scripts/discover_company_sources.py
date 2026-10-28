"""Inventory current Drive revisions without downloading or publishing research."""
from build_company_research import document,write
from drive_store_common import drive_service,configured_root_ids,execute_with_retry,FOLDER_MIME


def discover_drive(root,cache,queue):
    service=drive_service(readonly=True)
    transport=getattr(service._http,'http',service._http);transport.timeout=30
    roots=configured_root_ids(document(root,'_system/reference/document-store/google_drive_config.json'))
    if not roots:raise RuntimeError('No configured Drive research roots')
    items={};folders=[];drives=set();seen=set()
    for root_id in roots:
        meta=execute_with_retry(service.files().get(fileId=root_id,fields='id,driveId,parents',supportsAllDrives=True))
        if meta.get('driveId') and not meta.get('parents'):drives.add(meta['driveId'])
        else:folders.append(root_id)
    def collect(**parameters):
        token=None
        while True:
            page=execute_with_retry(service.files().list(**parameters,pageToken=token,pageSize=1000,supportsAllDrives=True,includeItemsFromAllDrives=True,
                 fields='nextPageToken,files(id,name,mimeType,md5Checksum,modifiedTime,parents,appProperties)'))
            for item in page.get('files',[]):
                items[item['id']]=item
                if item['mimeType']==FOLDER_MIME and 'driveId' not in parameters:folders.append(item['id'])
            token=page.get('nextPageToken')
            if not token:break
    for drive in drives:collect(corpora='drive',driveId=drive,q='trashed = false')
    while folders:
        folder=folders.pop()
        if folder in seen:continue
        seen.add(folder);collect(q=f"'{folder}' in parents and trashed = false")
    preferred=set(document(root,'_system/reference/core_compounders.json').get('tickers',[]))
    jobs=[]
    for item in items.values():
        if item['mimeType']==FOLDER_MIME:continue
        revision=item.get('md5Checksum') or item.get('modifiedTime') or 'unknown'
        jobs.append({'key':'drive:'+item['id']+':'+revision,'kind':'drive',
                     'priority':100 if item.get('appProperties',{}).get('ticker') in preferred else 0,
                     'payload':{'id':item['id'],'revision':revision,'title':item['name']}})
    queue.enqueue(jobs)
    write(cache/'drive-inventory.json',{'items':list(items.values())})
    return len(jobs)
