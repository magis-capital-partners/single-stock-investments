"""Owner-directed completion of one existing paid CPRT model, never new work."""
import json
import re
from pathlib import Path

GRANT_ID = 'CPRT-owner-finish-without-call-stops-20261116'
ROLES = ('valuation_underwriter', 'valuation_challenger')
CALL_POLICY = Path('_system/config/llm_usage_policy.json')
RUN_POLICY = Path('_system/config/underwriting_policy.json')
HEX = re.compile(r'[0-9a-f]{64}')


def _read(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def completion_grant(policy, subject):
    if subject != 'CPRT':
        return None
    grants = policy.get('owner_completion_grants') or {}
    if not isinstance(grants, dict):
        return None
    grant = grants.get(subject)
    fields = {'id', 'active', 'subject', 'reason', 'consumers', 'instruction_sha256',
              'instruction_private_path', 'anchor_contract_hash', 'packet_hash',
              'completion_scope', 'independent_approval_required'}
    if (not isinstance(grant, dict) or set(grant) != fields or grant.get('id') != GRANT_ID
            or grant.get('active') is not True or grant.get('subject') != 'CPRT'
            or grant.get('reason') != 'company_underwriting' or grant.get('consumers') != list(ROLES)
            or grant.get('completion_scope') != 'existing_paid_revision_until_first_independent_approval'
            or grant.get('independent_approval_required') is not True
            or any(not HEX.fullmatch(str(grant.get(k) or ''))
                   for k in ('instruction_sha256', 'anchor_contract_hash', 'packet_hash'))
            or grant.get('instruction_private_path') != 'recovery/CPRT/owner-instructions/'
                +str(grant.get('instruction_sha256'))+'.json'):
        return None
    return grant


def completion_limit_authority(policy, consumer, subject, reason, proof):
    """Waive only discretionary call counts; all ordinary evidence gates still run."""
    grant = completion_grant(policy, subject)
    if (not grant or consumer not in ROLES or reason != 'company_underwriting'
            or not isinstance(proof, dict)
            or any(proof.get(k) != grant[k]
                   for k in ('id', 'instruction_sha256', 'packet_hash', 'anchor_contract_hash'))
            or proof.get('pending_paid_revision') is not True
            or proof.get('approval_absent') is not True
            or any(not HEX.fullmatch(str(proof.get(k) or ''))
                   for k in ('current_contract_hash', 'paid_cache_input_hash'))):
        return None
    return grant



def _unpaid_author_input_repair(root,work,state,detail):
    """Retry one genuine pre-admission size hold after a source repair, never a paid attempt."""
    from underwriting_contract import digest
    from underwriting_pipeline import processing_version,stage_hash
    from underwriting_evidence import supplemental_fact_diagnostics
    from underwriting_codex import MAX_INPUT_CHARACTERS
    match=re.fullmatch(r'local_input_too_large: ([1-9][0-9]*) characters exceeds 1048576; complete evidence retained',detail)
    if (not match or int(match[1])<=MAX_INPUT_CHARACTERS
            or not HEX.fullmatch(str(state.get('processing_version') or ''))
            or state['processing_version']==processing_version(root)):
        return False
    progress=_read(work/'progress/CPRT.json')
    if progress.get('approved') or progress.get('pending_review'):
        return False
    feedback=progress.get('feedback') or {};previous=feedback.get('previous_contract') or {}
    packet=_read(work/'packets'/(str(state.get('packet_hash'))+'.json'))
    if (packet.get('ticker')!='CPRT' or packet.get('packet_hash')!=state.get('packet_hash')
            or packet.get('evidence_hash')!=state.get('evidence_hash') or not previous):
        return False
    payload={'packet':packet,'revision_feedback':{**feedback,'supplemental_fact_diagnostics':
             supplemental_fact_diagnostics(packet,previous.get('supplemental_facts') or [])},
             'revision_base_hash':digest(previous)}
    identity=stage_hash(root,'author',payload);cache=work/'cache/CPRT'/identity
    record=_read(cache/'input_admission.json')
    return (set(record)=={'status','input_hash','payload_hash','reason','model_calls'}
            and record.get('status')=='blocked' and record.get('input_hash')==identity
            and record.get('payload_hash')==digest(payload) and record.get('reason')==detail
            and type(record.get('model_calls')) is int and record['model_calls']==0
            and not any((cache/name).exists() for name in ('receipt.json','output.json','prompt.txt','author_revision.json')))


def _unpaid_acquired_target_routing_repair(root, work, state, detail):
    """Retry only the diagnosed unmerged-current-target hold; normal readiness still gates calls."""
    from underwriting_contract import digest
    from underwriting_pipeline import processing_version, stage_hash, today
    expected = {'code':'requested_primary_document_unavailable',
                'detail':'Retry requested primary disclosure: '}
    if (not detail.startswith('evidence_not_ready: ') or
            not HEX.fullmatch(str(state.get('processing_version') or '')) or
            state['processing_version'] == processing_version(root)):
        return False
    try:
        if json.loads(detail[len('evidence_not_ready: '):]) != [expected]:
            return False
        readiness = state.get('evidence_readiness') or {}
        if readiness.get('status') != 'evidence_gap' or readiness.get('gaps') != [expected]:
            return False
        progress = _read(work/'progress/CPRT.json')
        if progress.get('approved') or progress.get('pending_review'):
            return False
        packet = _read(work/'packets'/(str(state.get('packet_hash'))+'.json'))
        data = work.parent/'data'
        if (not data.is_dir() or data.is_symlink() or
                _read(data/RUN_POLICY) != _read(root/RUN_POLICY) or
                completion_grant(_read(data/CALL_POLICY),'CPRT') !=
                completion_grant(_read(root/CALL_POLICY),'CPRT')):
            return False
        from underwriting_foreign_financials import bounded_sources
        from underwriting_source_profiles import configure_source_budget
        from underwriting_related_evidence import _retained_target_labels
        @bounded_sources
        def current_labels():
            configure_source_budget(data,'CPRT')
            return _retained_target_labels(data,packet,today())
        labels = current_labels()
        if set(labels) != {'1637873'}:
            return False
        label = labels['1637873']
        related = (packet.get('related_issuers') or {}).get(label.get('ticker')) or {}
        if (label.get('as_of') != today() or not related or any(
                label.get(key) != related.get(key) for key in ('source_hash','evidence_hash'))):
            return False
        parent_docs = [row for row in packet.get('documents') or []
                       if row.get('issuer_ticker') in (None,'','CPRT')]
        parent_points = [row for row in packet.get('observations') or []
                         if row.get('source_kind') == 'primary' and
                         row.get('issuer_ticker') in (None,'','CPRT') and
                         row.get('field') != 'completed_acquisition_cash_consideration_paid']
        if (readiness.get('documents') != len(parent_docs) or
                readiness.get('primary_observations') != len(parent_points)):
            return False
        feedback = progress.get('feedback') or {};previous = feedback.get('previous_contract') or {}
        from underwriting_evidence import supplemental_fact_diagnostics
        payload = {'packet':packet,'revision_feedback':{**feedback,'supplemental_fact_diagnostics':
                   supplemental_fact_diagnostics(packet,previous.get('supplemental_facts') or [])},
                   'revision_base_hash':digest(previous)}
        cache = work/'cache/CPRT'/stage_hash(root,'author',payload)
        return not any((cache/name).exists() for name in
            ('receipt.json','output.json','prompt.txt','author_revision.json','input_admission.json'))
    except (OSError,ValueError,TypeError,KeyError):
        return False


def pending_revision_authority(root, work, ticker, state, *, contract=None, packet=None):
    """Bind a continuation to paid lineage, frozen evidence and an unresolved review."""
    from underwriting_contract import digest
    grant = completion_grant(_read(root/CALL_POLICY), ticker)
    if (not grant or state.get('status') not in ('running', 'automatic_retry_pending')
            or state.get('handoff_hash') or state.get('packet_hash') != grant['packet_hash']
            or not HEX.fullmatch(str(state.get('evidence_hash') or ''))
            or _read(root/RUN_POLICY).get('maximum_model_minutes_per_run') != 100):
        return None
    if state.get('status') == 'automatic_retry_pending':
        gaps = state.get('gaps') or []
        allowed = {'model_call_daily_repo_limit', 'model_call_per_subject_daily_limit',
                   'total_daily_model_call_budget'}
        if not gaps or any(g.get('code') != 'StageBlocked' or not (
                g.get('detail') in allowed or str(g.get('detail') or '').startswith(
                    'author_or_challenger_unresolved:') or _unpaid_author_input_repair(
                        root,work,state,str(g.get('detail') or '')) or _unpaid_acquired_target_routing_repair(
                        root,work,state,str(g.get('detail') or ''))) for g in gaps):
            return None
    progress = _read(work/'progress/CPRT.json')
    feedback = progress.get('feedback') or {}
    previous = feedback.get('previous_contract') or {}
    if (progress.get('approved') or progress.get('packet_hash') != grant['packet_hash']
            or previous.get('ticker') != ticker or previous.get('packet_hash') != grant['packet_hash']
            or previous.get('evidence_hash') != state['evidence_hash']):
        return None
    history = progress.get('history') or []
    if not (digest(previous) == grant['anchor_contract_hash'] or any(
            h.get('contract_hash') == grant['anchor_contract_hash'] for h in history)):
        return None
    review = feedback.get('independent_challenge') or {}
    if review.get('verdict') == 'approve':
        return None
    pending_review = (review.get('verdict') == 'revise' and review.get('contract_hash') == digest(previous)
                      and any(f.get('severity') in ('minor', 'major', 'critical') for f in review.get('findings') or []))
    pending_compilation = (not review and bool(feedback.get('required_correction')) and any(
        any(f.get('severity') in ('major', 'critical') for f in h.get('findings') or []) for h in history))
    if not (pending_review or pending_compilation):
        return None
    candidate = contract if contract is not None else previous
    if (candidate.get('ticker') != ticker or candidate.get('packet_hash') != grant['packet_hash']
            or candidate.get('evidence_hash') != state['evidence_hash']
            or packet is not None and (packet.get('packet_hash') != grant['packet_hash']
                                       or packet.get('evidence_hash') != state['evidence_hash'])):
        return None
    ledger_path = work/'ledger.jsonl'
    if not ledger_path.is_file():
        return None
    rows = [json.loads(line) for line in ledger_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not rows:
        return None
    def key(row):
        return tuple(row.get(k) for k in ('consumer', 'subject', 'evidence_hash', 'run_id'))
    terminal = {key(row) for row in rows if row.get('status') in ('completed', 'failed')}
    if any(row.get('subject') == ticker and row.get('consumer') in ROLES
           and row.get('status') == 'reserved' and key(row) not in terminal for row in rows):
        return None
    current_hash = digest(candidate)
    for cache in sorted((work/'cache/CPRT').glob('*')):
        receipt = _read(cache/'receipt.json')
        usage = receipt.get('usage') or {}
        if (receipt.get('provider') != 'codex-local' or receipt.get('stage') != 'author'
                or receipt.get('model') != 'gpt-6.1-sol' or receipt.get('reasoning_effort') != 'high'
                or receipt.get('status') != 'finished' or not receipt.get('agent_id')
                or any(type(usage.get(k)) is not int for k in ('input_tokens', 'output_tokens'))
                or not HEX.fullmatch(cache.name) or not (cache/'output.json').is_file()):
            continue
        if digest(_read(cache/'output.json')) == current_hash:
            return {**{k: grant[k] for k in ('id', 'instruction_sha256', 'packet_hash', 'anchor_contract_hash')},
                    'current_contract_hash': current_hash, 'paid_cache_input_hash': cache.name,
                    'pending_paid_revision': True, 'approval_absent': True}
    return None
