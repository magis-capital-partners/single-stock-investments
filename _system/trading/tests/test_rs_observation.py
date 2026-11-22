"""Full-window statistics must retain bad readings and clock-stage evidence."""
from _system.trading.rs_paper_executor.observation import report


def row(at,age,**more):
    return {'checked_at':f'2026-11-23T14:30:{at:02d}Z','state_age_seconds':age,
            'report_age_seconds':10,'fresh_both':age<=120,'publication_id':'old',
            'pipeline_commit':'reviewed','max_state_age_seconds':75,'publish_interval_seconds':10,**more}


def test_full_window_retains_every_over_age_reading_and_download_cause():
    rows=[row(0,70),row(10,125),row(20,140),row(30,50)]
    publisher=[{'event':'publication_upload','accepted':True,'publication_id':'new',
                'upload_completed_at':'2026-11-23T14:30:05Z'}]
    failed={'event':'fetch_failed','at':'2026-11-23T14:30:06Z','reason':'HTTP 503'}
    x=report(rows,'2026-11-23T14:30:00Z','2026-11-23T14:30:40Z',events=[failed],publisher=publisher,
             expected={'pipeline_commit':'reviewed','max_state_age_seconds':75,'publish_interval_seconds':10})
    assert x['metrics_seconds']['state_age_seconds']=={'samples':4,'p50':97.5,'p95':137.75,'max':140}
    assert len(x['over_120_readings'])==2
    assert all(r['cause']=='consumer_has_not_committed_a_newer_acknowledged_publication' for r in x['over_120_readings'])
    assert x['over_120_readings'][0]['fetch_failure_evidence']==[failed]
    assert x['configuration_unchanged'] is True
    assert x['qualifying_shadow_sessions']==0


def test_missing_observations_and_configuration_changes_cannot_be_counted_as_fresh():
    rows=[row(30,70),row(40,80,pipeline_commit='changed')]
    x=report(rows,'2026-11-23T14:30:00Z','2026-11-23T14:31:00Z',expected={'pipeline_commit':'reviewed'})
    assert x['maximum_observation_gap_seconds']==30
    assert x['measured_time_share']==25/60
    assert x['configuration_unchanged'] is False


def test_sample_ceases_to_be_fresh_when_original_state_clock_crosses_120():
    x=report([row(0,115),row(10,125)],'2026-11-23T14:30:00Z','2026-11-23T14:30:20Z')
    assert x['conservative_fresh_time_share']==.25
