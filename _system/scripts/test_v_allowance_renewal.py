"""Owner-scoped UTC-day allowance renewals preserve every actual admission."""
import copy
from datetime import datetime,timezone
import pytest
from llm_call_gate import evaluate
AT=datetime(2026,11,10,17,tzinfo=timezone.utc)
POLICY={'default':{'duplicate_evidence_block':True,'cooldown_hours':0},'consumers':{
 'valuation_underwriter':{'daily_repo_limit':12,'per_subject_daily_limit':2,'allowed_reasons':['company_underwriting'],'dated_subject_daily_limits':{'2026-11-10':{'V':4}}},
 'valuation_challenger':{'daily_repo_limit':6,'per_subject_daily_limit':2,'allowed_reasons':['company_underwriting'],'dated_subject_daily_limits':{'2026-11-10':{'V':3}}}}}
def reservations(n,consumer='valuation_underwriter',subject='V',at=AT):
 return [{'timestamp':at.isoformat(),'consumer':consumer,'subject':subject,'evidence_hash':str(i+1)*64,'status':'reserved','run_id':str(i)}for i in range(n)]
def check(rows,consumer='valuation_underwriter',subject='V',at=AT,**kw):
 return evaluate(consumer=consumer,subject=subject,reason=kw.pop('reason','company_underwriting'),evidence_hash=kw.pop('evidence_hash','f'*64),policy_doc=kw.pop('policy_doc',POLICY),ledger=rows,at=at,**kw)
@pytest.mark.parametrize('used',[2,3])
def test_two_fresh_author_calls_are_admitted_without_releasing_original_rows(used):
 rows=reservations(used);saved=copy.deepcopy(rows);result=check(rows)
 assert result['approved']and result['effective_per_subject_daily_limit']==4 and rows==saved
 assert result['dated_subject_limit_scope']=={'UTC_day':'2026-11-10','subject':'V'}
def test_the_fifth_author_is_still_suppressed():
 assert check(reservations(4))['gate_reason']=='per_subject_daily_limit'
@pytest.mark.parametrize('used',[1,2])
def test_two_fresh_challenger_calls_use_only_their_separate_renewed_limit(used):
 result=check(reservations(used,'valuation_challenger'),consumer='valuation_challenger')
 assert result['approved']and result['effective_per_subject_daily_limit']==3
def test_fourth_challenger_is_suppressed():
 assert check(reservations(3,'valuation_challenger'),consumer='valuation_challenger')['gate_reason']=='per_subject_daily_limit'
@pytest.mark.parametrize('day',[9,11])
def test_renewal_does_not_apply_before_or_after_its_exact_UTC_date(day):
 at=AT.replace(day=day);result=check(reservations(2,at=at),at=at)
 assert result['gate_reason']=='per_subject_daily_limit'
def test_another_company_keeps_its_original_two_call_limit():
 assert check(reservations(2,subject='CPRT'),subject='CPRT')['gate_reason']=='per_subject_daily_limit'
@pytest.mark.parametrize('consumer,total',[('valuation_underwriter',12),('valuation_challenger',6)])
def test_repository_daily_limits_remain_independent(consumer,total):
 rows=reservations(2,consumer)+reservations(total-2,consumer,'OTHER')
 assert check(rows,consumer=consumer)['gate_reason']=='daily_repo_limit'
def test_duplicate_evidence_remains_suppressed():
 rows=reservations(2);assert check(rows,evidence_hash=rows[0]['evidence_hash'])['gate_reason']=='duplicate_evidence_hash'
def test_processed_state_remains_suppressed():
 assert check(reservations(2),state={'evidence_hash':'f'*64})['gate_reason']=='evidence_already_processed'
def test_reason_and_missing_evidence_guards_are_not_renewed():
 assert check(reservations(2),reason='unapproved_work')['gate_reason']=='reason_not_allowed'
 assert check(reservations(2),evidence_hash='')['gate_reason']=='missing_evidence_hash'
@pytest.mark.parametrize('invalid',[True,'4',0,-1,13])
def test_invalid_or_repo_exceeding_renewal_fails_closed(invalid):
 p=copy.deepcopy(POLICY);p['consumers']['valuation_underwriter']['dated_subject_daily_limits']['2026-11-10']['V']=invalid
 assert check(reservations(2),policy_doc=p)['gate_reason']=='invalid_dated_subject_daily_limit'
@pytest.mark.parametrize('invalid',[[],{'2026-11-10':[]}])
def test_invalid_renewal_mapping_fails_closed(invalid):
 p=copy.deepcopy(POLICY);p['consumers']['valuation_underwriter']['dated_subject_daily_limits']=invalid
 assert check(reservations(2),policy_doc=p)['gate_reason']=='invalid_dated_subject_daily_limit'
def test_renewal_cannot_be_borrowed_by_a_different_consumer():
 p=copy.deepcopy(POLICY);p['consumers']['valuation_builder']={'daily_repo_limit':6,'per_subject_daily_limit':2}
 assert check(reservations(2,'valuation_builder'),consumer='valuation_builder',policy_doc=p)['gate_reason']=='per_subject_daily_limit'

def test_checked_repo_grant_is_only_V_today_with_original_global_and_default_limits():
 import json
 from pathlib import Path
 p=json.loads((Path(__file__).resolve().parents[1]/'config/llm_usage_policy.json').read_bytes())
 author=p['consumers']['valuation_underwriter'];review=p['consumers']['valuation_challenger']
 assert (author['daily_repo_limit'],author['per_subject_daily_limit'])==(12,2)
 assert (review['daily_repo_limit'],review['per_subject_daily_limit'])==(6,2)
 assert author['dated_subject_daily_limits']=={'2026-11-10':{'V':4}}
 assert review['dated_subject_daily_limits']=={'2026-11-10':{'V':3}}
 assert not p['consumers']['valuation_builder'].get('dated_subject_daily_limits')
