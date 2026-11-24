"""Dated public-feed observation and audit report. No broker imports or sockets."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from datetime import timedelta
import json
from pathlib import Path
import time

from .operations_feed import R2Object, read_local_clocks, utc_now
from .safety import timestamp


def read_rows(path):
    path=Path(path)
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line] if path.exists() else []


def sample(feed,now=None):
    now=now or utc_now()
    row={'checked_at':now,'gateway_contacted':False,'monitor_version':'verified_receipts.v1'}
    try:
        clocks,meta=read_local_clocks(Path(feed)/'operations.json')
        row.update(clocks)
        row['report_sha256']=meta['sha256']
        row['report_age_seconds']=(timestamp(now)-timestamp(clocks['generated_at'])).total_seconds()
        row['state_age_seconds']=(timestamp(now)-timestamp(clocks['state_at'])).total_seconds()
        receipt=meta.get('publish_receipt')
        if not receipt:raise ValueError('publisher acknowledgement receipt missing')
        row.update(publication_id=receipt['publication_id'],pipeline_commit=receipt.get('pipeline_commit'),
                   max_state_age_seconds=receipt['max_state_age_seconds'],publish_interval_seconds=receipt.get('publish_interval_seconds'),
                   upload_started_at=receipt['upload_started_at'],upload_completed_at=receipt['upload_completed_at'],
                   request_started_at=meta['request_started_at'],received_at=meta['received_at'])
        row['state_age_at_publish_seconds']=(timestamp(receipt['upload_completed_at'])-timestamp(clocks['state_at'])).total_seconds()
        row['publication_to_receipt_seconds']=(timestamp(meta['received_at'])-timestamp(receipt['upload_completed_at'])).total_seconds()
        row['receipt_to_check_seconds']=(timestamp(now)-timestamp(meta['received_at'])).total_seconds()
        row['upload_duration_seconds']=(timestamp(receipt['upload_completed_at'])-timestamp(receipt['upload_started_at'])).total_seconds()
        row['download_duration_seconds']=(timestamp(meta['received_at'])-timestamp(meta['request_started_at'])).total_seconds()
        row['fresh_both']=all(-2<=row[k]<=120 for k in ['report_age_seconds','state_age_seconds'])
    except Exception as exc:
        row.update(fresh_both=False,error_type=type(exc).__name__,reason=str(exc)[:200])
    try:row['fetch_status']=json.loads((Path(feed)/'operations.status.json').read_text())
    except (OSError,ValueError):pass
    return row


def monitor(feed,log,until,*,interval=10):
    log=Path(log);log.parent.mkdir(parents=True,exist_ok=True)
    while timestamp(utc_now())<timestamp(until):
        started=time.monotonic()
        with log.open('a',encoding='utf-8') as handle:
            handle.write(json.dumps(sample(feed),sort_keys=True)+'\n')
        time.sleep(max(.1,interval-(time.monotonic()-started)))


def percentiles(values):
    values=sorted(values)
    def p(q):
        if not values:return None
        position=(len(values)-1)*q;index=int(position)
        return values[index]+(values[min(index+1,len(values)-1)]-values[index])*(position-index)
    return {'samples':len(values),'p50':p(.5),'p95':p(.95),'max':values[-1] if values else None}


def is_newer_publication(candidate, sampled):
    if candidate['publication_id']==sampled.get('publication_id'):
        return False
    clocks=('state_at','generated_at')
    if all(candidate.get(key) and sampled.get(key) for key in clocks):
        return tuple(timestamp(candidate[key]) for key in clocks)>tuple(timestamp(sampled[key]) for key in clocks)
    return True


def report(rows,start,end,*,events=(),publisher=(),expected=None):
    begin,finish=timestamp(start),timestamp(end)
    all_rows=sorted(rows,key=lambda r:timestamp(r['checked_at']))
    visibility={
        r['publication_id']: r['at']
        for r in publisher if r.get('event')=='publication_visible'
    }
    selected=[]
    for raw in all_rows:
        if not begin<=timestamp(raw['checked_at'])<finish:
            continue
        row=dict(raw)
        visible_at=visibility.get(row.get('publication_id'))
        if visible_at and row.get('received_at') and row.get('state_at'):
            row['publisher_visibility_ack_at']=visible_at
            row['state_age_at_visibility_ack_seconds']=(timestamp(visible_at)-timestamp(row['state_at'])).total_seconds()
            row['visibility_ack_to_receipt_seconds']=(timestamp(row['received_at'])-timestamp(visible_at)).total_seconds()
        selected.append(row)
    fields=['report_age_seconds','state_age_seconds','state_age_at_publish_seconds','publication_to_receipt_seconds',
            'receipt_to_check_seconds','upload_duration_seconds','download_duration_seconds',
            'state_age_at_visibility_ack_seconds','visibility_ack_to_receipt_seconds']
    metrics={key:percentiles([r[key] for r in selected if isinstance(r.get(key),(int,float))]) for key in fields}
    publications=[r for r in publisher if r.get('event')=='publication_upload' and r.get('upload_completed_at')]
    by_publication={r['publication_id']:r for r in publications}
    visible=[]
    for publication in publications:
        if publication.get('accepted') is not True:
            continue
        if publication.get('visibility_mode')=='after_receipt':
            visible_at=visibility.get(publication['publication_id'])
            available=timestamp(visible_at) if visible_at else None
        else:
            available=timestamp(publication['upload_completed_at'])
        if available is not None:
            visible.append((available,publication))
    visible.sort(key=lambda item:item[0])
    visible_times=[available for available,_ in visible]
    bad=[]
    for row in selected:
        if not any(row.get(k,0)>120 for k in ('report_age_seconds','state_age_seconds')):continue
        checked=timestamp(row['checked_at']);index=bisect_right(visible_times,checked)-1
        latest=visible[index][1] if index>=0 else None
        evidence=[e for e in events if e.get('event') in ('fetch_failed','receipt_rejected') and 0<=(checked-timestamp(e['at'])).total_seconds()<=180]
        diagnostic=[e for e in publisher if e.get('at') and 0<=(checked-timestamp(e['at'])).total_seconds()<=180]
        confirmed_progress=[]
        if index>=0:
            confirmed_progress.append(visible_times[index])
        if row.get('received_at'):
            confirmed_progress.append(timestamp(row['received_at']))
        newest_progress=max(confirmed_progress,default=None)
        pending_diagnostic=[e for e in diagnostic if newest_progress is None or timestamp(e['at'])>=newest_progress]
        pending_publications=[
            e for e in pending_diagnostic if e.get('publication_id') and
            is_newer_publication(by_publication.get(e['publication_id'],e),row)
        ]
        if latest and is_newer_publication(latest,row):
            cause='consumer_has_not_committed_a_newer_acknowledged_publication'
        elif any(e.get('event')=='publication_visibility_failed' for e in pending_publications):
            cause='publisher_latest_report_visibility_failed_or_unconfirmed'
        elif any(e.get('event')=='receipt_archive_failed' for e in pending_publications):
            cause='publisher_receipt_archive_failed'
        elif any(e.get('event')=='publication_upload' and e.get('visibility_mode')=='after_receipt'
                 and e.get('accepted') is True
                 and (not visibility.get(e['publication_id']) or timestamp(visibility[e['publication_id']])>checked)
                 for e in pending_publications):
            cause='publisher_newer_upload_acknowledged_visibility_unconfirmed'
        elif any(e.get('event')=='checkpoint_failed' for e in pending_diagnostic):
            failure=next(e for e in reversed(pending_diagnostic) if e.get('event')=='checkpoint_failed')
            cause='publisher_checkpoint_pointer_unconfirmed' if failure.get('phase')=='pointer' else 'publisher_checkpoint_upload_unconfirmed'
        elif any(e.get('outcome')=='upload_outcome_unknown' for e in pending_publications):
            cause='publisher_upload_failed_or_acknowledgement_missing'
        elif any(e.get('reason')=='paused_checkpoint_too_old' for e in pending_diagnostic):
            cause='publisher_paused_because_committed_checkpoint_was_too_old'
        elif any(e.get('reason')=='insufficient_publication_headroom' for e in pending_diagnostic):
            cause='publisher_refused_for_insufficient_publication_headroom'
        elif latest:
            cause='publisher_has_not_advanced_the_last_acknowledged_publication'
        else:cause='publisher_telemetry_unavailable_root_cause_not_established'
        bad.append({**row,'cause':cause,'cause_scope':'observed pipeline stage; no unobserved upstream root cause asserted',
                    'newest_publisher_publication_id':latest['publication_id'] if latest else None,
                    'fetch_failure_evidence':evidence,'publisher_evidence':diagnostic[-12:]})
    # Conservative measured-time coverage. Never bridge an unobserved gap of more
    # than 15s, or keep a sample fresh after either original clock passes 120s.
    fresh_seconds=0.;covered_seconds=0.;gaps=[]
    for i,row in enumerate(all_rows):
        at=timestamp(row['checked_at']);next_at=timestamp(all_rows[i+1]['checked_at']) if i+1<len(all_rows) else finish
        left=max(begin,at);right=min(finish,next_at)
        if right<=left:continue
        gaps.append((right-left).total_seconds())
        measured_end=min(right,at+timedelta(seconds=15))
        covered_seconds+=max(0,(measured_end-left).total_seconds())
        if row.get('fresh_both') is True:
            remaining=120-max(row.get('state_age_seconds',120),row.get('report_age_seconds',120))
            fresh_end=min(measured_end,at+timedelta(seconds=max(0,remaining)))
            fresh_seconds+=max(0,(fresh_end-left).total_seconds())
    expected=expected or {}
    variants=sorted({(r.get('pipeline_commit'),r.get('max_state_age_seconds'),r.get('publish_interval_seconds')) for r in selected if r.get('publication_id')},key=str)
    receipts=[r for r in selected if r.get('publication_id') and not r.get('error_type')]
    frozen=bool(receipts) and all(all(r.get(k)==v for k,v in expected.items()) for r in receipts) if expected else None
    duration=(finish-begin).total_seconds()
    acknowledged=[r for r in publications if begin<=timestamp(r['upload_completed_at'])<finish]
    published=[(at,r) for at,r in visible if begin<=at<finish]
    publisher_metrics={
        'state_age_at_publish_seconds':percentiles([(timestamp(r['upload_completed_at'])-timestamp(r['state_at'])).total_seconds() for r in acknowledged if r.get('state_at')]),
        'upload_duration_seconds':percentiles([(timestamp(r['upload_completed_at'])-timestamp(r['upload_started_at'])).total_seconds() for r in acknowledged if r.get('upload_started_at')]),
        'queue_wait_seconds':percentiles([(timestamp(r['upload_started_at'])-timestamp(r['queued_at'])).total_seconds() for r in acknowledged if r.get('queued_at')]),
        'upload_ack_to_visibility_ack_seconds':percentiles([(at-timestamp(r['upload_completed_at'])).total_seconds()
                                                           for at,r in published if r.get('visibility_mode')=='after_receipt'])}
    if all_rows and timestamp(all_rows[0]['checked_at'])>begin:
        gaps.append(min(duration,(timestamp(all_rows[0]['checked_at'])-begin).total_seconds()))
    return {'schema':'rs_full_session_feed_observation.v1','start':start,'end':end,'generated_at':utc_now(),
            'qualifying_shadow_sessions':0,'gateway_contacted':False,'theta_accessed':False,
            'samples':len(selected),'fresh_samples':sum(r.get('fresh_both') is True for r in selected),
            'fresh_sample_share':sum(r.get('fresh_both') is True for r in selected)/len(selected) if selected else 0,
            'measured_time_share':covered_seconds/duration,'conservative_fresh_time_share':fresh_seconds/duration,
            'maximum_observation_gap_seconds':max(gaps,default=duration),'metrics_seconds':metrics,
            'publisher_metrics_seconds':publisher_metrics,
            'over_120_readings':bad,'unavailable_readings':[r for r in selected if r.get('error_type')],
            'expected_configuration':expected,'observed_configuration_variants':variants,'configuration_unchanged':frozen,
            'publisher_acknowledged_publications':len(acknowledged),
            'publisher_accepted_publications':sum(r.get('accepted') is True for r in acknowledged),
            'publisher_visible_publications':len(published),
            'publisher_unacknowledged_attempts':[r for r in publisher if r.get('event')=='publication_upload' and not r.get('upload_completed_at') and r.get('at') and begin<=timestamp(r['at'])<finish],
            'percentile_method':'linear interpolation at (n-1)*p; numerical samples only; unavailable rows reported separately',
            'acceptance':'owner_review_required_full_feed_observation_is_not_broker_shadow'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['monitor','report'])
    parser.add_argument('--feed-dir',required=True);parser.add_argument('--log',required=True)
    parser.add_argument('--until');parser.add_argument('--start');parser.add_argument('--end')
    parser.add_argument('--day');parser.add_argument('--expected');parser.add_argument('--output')
    parser.add_argument('--publisher-log');args=parser.parse_args()
    if args.command=='monitor':
        if not args.until:parser.error('monitor needs --until')
        monitor(args.feed_dir,args.log,args.until);return
    if not all([args.start,args.end,args.day,args.output]):parser.error('report needs start/end/day/output')
    publisher_path=Path(args.publisher_log) if args.publisher_log else Path(args.output).with_suffix('.publisher.jsonl')
    publisher_error=None
    if not args.publisher_log:
        try:publisher_path.write_bytes(R2Object.from_env().get_audit(args.day,utc_now()))
        except Exception as exc:publisher_error=type(exc).__name__+': '+str(exc)[:200]
    result=report(read_rows(args.log),args.start,args.end,events=read_rows(Path(args.feed_dir)/'events'/(args.day+'.jsonl')),
                  publisher=read_rows(publisher_path),expected=json.loads(Path(args.expected).read_text()) if args.expected else None)
    result['publisher_audit_download_error']=publisher_error
    if publisher_error:
        for key in ('publisher_acknowledged_publications','publisher_accepted_publications','publisher_visible_publications'):
            result[key]=None
    Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('samples','metrics_seconds','configuration_unchanged')}))


if __name__=='__main__':main()
