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
                    'author_or_challenger_unresolved:')) for g in gaps):
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
