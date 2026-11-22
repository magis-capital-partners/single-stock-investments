"""Evaluate saved research thresholds after publication, using D1 over HTTPS only."""
from __future__ import annotations
import hashlib
import json
import math
import os
from private_storage import HTTP, cloudflare_token, load_config


def triggered(index,rules):
    companies={r['ticker']:r for r in index.get('companies',[])}
    for id,rule in rules.items():
        row=companies.get(rule.get('ticker'));point=(row or {}).get('latest',{}).get(rule.get('metric'))
        value=point.get('value') if point else None;threshold=rule.get('value')
        if not isinstance(value,(float,int)) or isinstance(value,bool) or not math.isfinite(value) or not isinstance(threshold,(float,int)) or isinstance(threshold,bool) or not math.isfinite(threshold):continue
        hit={'lte':value<=threshold,'gte':value>=threshold,'lt':value<threshold,'gt':value>threshold}.get(rule.get('op'),False)
        if hit:yield {'rule_id':id,'ticker':row['ticker'],'metric':rule['metric'],'observed_value':value,'unit':point.get('unit'),'period':point['period'],'filed':point.get('filed'),'note':str(rule.get('note',''))[:2000]}


def evaluate_saved_alerts(root,store):
    config=load_config(root);http=HTTP(cloudflare_token,'api.cloudflare.com',content_type='application/json')
    base='/client/v4/accounts/'+config['account_id']+'/d1/database'
    databases=json.loads(http.request('GET',base,limit=1024*1024))
    name=os.environ.get('RESEARCH_D1_DATABASE','single-stock-investments')
    db=next((d['uuid'] for d in databases.get('result',[]) if d.get('name')==name),None)
    if not db:raise ValueError('The existing research dashboard database was not found')
    def query(sql,params=()):
        body=json.dumps({'sql':sql,'params':list(params)},separators=(',',':')).encode()
        result=json.loads(http.request('POST',base+'/'+db+'/query',body,limit=4*1024*1024))
        if result.get('success') is not True:raise ValueError('Research alert database query failed')
        return result['result'][0].get('results',[])
    pointer_raw=store.objects.http.request('GET',store.objects.base+'research-explorer/v1/current.json',limit=1024*1024)
    if not pointer_raw:raise ValueError('No verified financial release is published')
    pointer=json.loads(pointer_raw);record=pointer['index'];index=json.loads(store.restore('alerts/index',records={'alerts/index':record}))
    viewers=query("SELECT viewer_email, value_json FROM research_preferences WHERE preference_key = 'workspace'")
    count=0
    for viewer in viewers:
        workspace=json.loads(viewer['value_json']);rules=workspace.get('alerts',{})
        if not isinstance(rules,dict):continue
        for event in triggered(index,rules):
            key=hashlib.sha256(json.dumps([event['rule_id'],event['ticker'],event['metric'],event['period'],event['observed_value']],separators=(',',':')).encode()).hexdigest()
            query('INSERT OR IGNORE INTO research_alert_events(viewer_email,event_key,rule_id,ticker,metric,observed_value,unit,period,filed,note,release_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                  [viewer['viewer_email'],key,event['rule_id'],event['ticker'],event['metric'],event['observed_value'],event['unit'],event['period'],event['filed'],event['note'],hashlib.sha256(pointer_raw).hexdigest()])
            count+=1
    return {'viewers':len(viewers),'thresholds_met':count,'release_as_of':pointer['as_of']}
