"""Reuse only verified approved economic assumptions; never import old price targets."""
from __future__ import annotations

from underwriting_contract import digest


def change_context(previous_packet, previous_contract, packet):
    previous = {o['id']: o for o in previous_packet.get('observations') or []}
    current = {o['id']: o for o in packet.get('observations') or []}
    changed = set(previous)-set(current)
    added = set(current)-set(previous)
    previous_docs = {d['id']: d['content_hash'] for d in previous_packet.get('documents') or []}
    current_docs = {d['id']: d['content_hash'] for d in packet.get('documents') or []}
    changed |= {key for key, value in previous_docs.items() if current_docs.get(key) != value}
    old_report = previous_packet.get('latest_report') or {}
    new_report = packet.get('latest_report') or {}
    new_report_arrived = (new_report.get('period') or '', new_report.get('filed') or '') > (old_report.get('period') or '', old_report.get('filed') or '')
    affected = [a['id'] for a in previous_contract['assumptions'] if new_report_arrived or set(a['evidence_ids']) & changed]
    return {'previous_contract': previous_contract, 'previous_contract_hash': digest(previous_contract),
            'changed_or_removed_evidence_ids': sorted(changed), 'new_evidence_ids': sorted(added),
            'changed_fields': sorted({o.get('field') or '' for key, o in current.items() if key in added}),
            'assumptions_requiring_reconsideration': affected,
            'mode': 'reconsider_framework_and_all_assumptions' if new_report_arrived else 'review_changed_evidence_and_expiring_judgments',
            'instruction': 'Only this previously independently approved contract may be reused. Rebind facts to the current packet. '
                           'Explain every retained or changed assumption; the independent challenger reviews the full resulting contract.'}


def approved_baseline(root, ticker, vault, packet):
    from underwriting_pipeline import read, validate_saved
    try:
        receipt = validate_saved(root, ticker, vault)
        if not receipt:
            return None
        previous_packet = read(vault/'valuation-underwriting/packets'/(receipt['packet_hash']+'.json'))
        previous_contract = read(root/ticker/'research/underwriting_contract.json')
        return change_context(previous_packet, previous_contract, packet)
    except (ValueError, OSError, KeyError, TypeError):
        return None  # An unverified legacy valuation is never an assumption baseline.
