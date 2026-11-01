"""Explain relevance and enforce eligibility independently of raw event scores."""
from __future__ import annotations

from datetime import date
import math

from security_profiles import canonical_symbol, security_profile

ACCOUNTING_METRICS = {'net_income', 'operating_income', 'revenues', 'revenue', 'eps_basic', 'eps_diluted', 'cfo', 'operating_cash_flow'}
WRAPPER_RISKS = {'custody_loss', 'custody_shortfall', 'tracking_failure', 'redemption_suspension', 'fee_change', 'fund_liquidation'}
SPECIAL_METRICS = {
    'reit': {'affo', 'affo_per_share', 'ffo', 'occupancy', 'same_store_noi', 'net_debt_to_ebitda'},
    'bank': {'net_interest_margin', 'cet1_ratio', 'deposit_growth', 'credit_losses', 'nonperforming_loans'},
    'insurer': {'combined_ratio', 'reserve_development', 'underwriting_income', 'solvency_ratio'},
    'holding_company': {'nav_per_share', 'look_through_earnings', 'subsidiary_earnings', 'capital_allocation'},
}


def normalize_event_dates(event: dict, *, today: date | None = None) -> None:
    v = event.get('verification') or {}
    if event.get('source') == 'filing':
        published = v.get('filing_date') or event.get('published_at')
        if published:
            old = event.get('observed_at')
            event['processed_at'] = event.get('processed_at') or (old if old != published else None)
            event['published_at'] = str(published)[:10]
            event['observed_at'] = str(published)[:10]
        event['period_end'] = v.get('period_end') or event.get('period_end')
    if event.get('event_kind') != 'scheduled':
        try:
            event['freshness_days'] = max(0, ((today or date.today()) - date.fromisoformat(str(event.get('published_at') or event.get('observed_at'))[:10])).days)
        except ValueError:
            pass


def assess_relevance(event: dict) -> dict:
    event.pop('materiality_floor', None)
    normalize_event_dates(event)
    profile = event.get('security_profile') or security_profile(event.get('ticker') or '')
    metric = event.get('metric_name') or ''
    source = event.get('source')
    verified = event.get('entity_verified') is not False
    subject = event.get('issuer_ticker') or event.get('target_ticker')
    indirect = event.get('relationship') == 'indirect'
    if source == 'insider' and event.get('event_type') == 'form4_transaction':
        verified = verified and bool(subject) and bool(event.get('issuer_cik')) and (indirect or canonical_symbol(subject) == canonical_symbol(event.get('ticker')))
    if source == 'insider' and event.get('event_type') == 'insider_signal' and not event.get('constituent_identity_verified'):
        verified = False
        event['direction'] = 'neutral'
        event['title'] = 'Insider conviction estimate: verification required'
        # A historical model estimate's rebuild timestamp is not a news date.
        event['processed_at'] = event.get('processed_at') or event.get('observed_at')
        event['observed_at'], event['published_at'], event['freshness_days'] = None, None, None
    v = event.get('verification') or {}
    data_flags = list(v.get('parser_flags') or [])
    if source == 'filing':
        if not v.get('context_verified'):
            data_flags.append('context_unverified')
        if event.get('event_type') == 'filing_metric' and (event.get('prior_value') is None or event.get('current_value') is None):
            data_flags.append('context_unverified')
        for key in ('prior_value', 'current_value'):
            value = event.get(key)
            if value is not None:
                try:
                    if not math.isfinite(float(value)):
                        data_flags.append('non_finite_value')
                except (ValueError, TypeError):
                    data_flags.append('invalid_value')
    invalid = bool(set(data_flags) & {'non_finite_value', 'invalid_value', 'unit_mismatch', 'entity_context_mismatch', 'conflicting_context_values', 'segment_context'})
    validation = 'invalid' if invalid else ('unverified' if source == 'filing' and ('context_unverified' in data_flags or 'non_comparable_periods' in data_flags) else 'verified')
    gate, reason, factor = None, None, 1.0
    channel = 'operating_business'
    explanation = None
    if not verified:
        gate, reason, factor = 'context', 'subject_unverified', 0.2
        explanation = 'The affected issuer has not been verified. This event cannot establish a directional signal for this ticker.'
    elif invalid:
        gate, reason, factor = 'noise', 'invalid_financial_data', 0.0
        explanation = 'The financial comparison failed validation; reconcile the source before using it.'
    elif validation == 'unverified':
        gate, reason, factor = 'context', 'financial_comparison_unverified', 0.4
        explanation = 'Reporting periods, units or consolidated context need verification before this comparison can support a signal.'
    evidence_present = bool(event.get('evidence_ref') or event.get('evidence_url') or event.get('evidence_items') or v.get('source_filing_ref'))
    if not evidence_present and event.get('event_kind') != 'scheduled':
        gate, reason, factor = gate or 'context', reason or 'evidence_missing', min(factor, 0.4)
        explanation = explanation or 'Linked evidence is missing. Verify the reported development and its subject before treating it as a signal.'
        event['direction'] = 'neutral'
        if event.get('event_type') == 'leadership_risk':
            event['title'] = 'Governance watch: source verification required'
            event['processed_at'] = event.get('processed_at') or event.get('observed_at')
            event['observed_at'], event['published_at'], event['freshness_days'] = None, None, None
    kind = profile['economic_profile']
    if kind == 'unresolved' and source in {'filing', 'earnings', 'kpi_trend'} and (metric or event.get('impact_axis') == 'fundamentals'):
        gate, reason, factor = gate or 'context', reason or 'classification_unresolved', min(factor, 0.4)
        explanation = explanation or 'Instrument classification is unresolved; generic operating-company interpretations are withheld.'
    fund = kind.endswith('_fund')
    if fund and metric in ACCOUNTING_METRICS:
        channel = 'accounting_context'
        gate, reason, factor = gate or 'context', reason or 'fund_accounting_context', min(factor, 0.25)
        explanation = explanation or 'Fund accounting reflects portfolio gains, losses or capital movements. Assess the underlying exposure, NAV per share, tracking, fees and custody; this is not an operating-earnings signal.'
        event['direction'] = 'neutral'
    elif fund and (event.get('event_type') in WRAPPER_RISKS or metric in WRAPPER_RISKS):
        channel = 'wrapper_risk'
        explanation = explanation or 'A change in custody, fees, tracking or redemption mechanics can change the value or reliability of the fund exposure.'
    elif fund:
        channel = 'underlying_asset' if event.get('economic_channel') == 'underlying_asset' else 'wrapper_mechanics'
        explanation = explanation or 'Assess the underlying exposure and fund tracking separately. Flows or a larger asset base alone do not establish a directional price signal.'
    elif indirect:
        channel = 'capital_allocation'
        gate, reason, factor = gate or 'context', reason or 'indirect_exposure', min(factor, 0.45)
        explanation = explanation or f"{event.get('actor_name') or 'The investor'} transacted in {subject}. Assess the transaction relative to its own capital and portfolio; the purchase is not insider buying of this ticker."
        event['direction'] = 'neutral'
    elif source == 'insider':
        channel = 'ownership'
        code = event.get('transaction_code')
        if event.get('event_type') == 'form4_transaction' and code not in {'P', 'S'}:
            gate, reason, factor = gate or 'context', reason or 'non_discretionary_transaction', min(factor, 0.3)
            event['direction'] = 'neutral'
        explanation = explanation or f"Ownership activity in {subject or event.get('ticker')}. Consider the actor's role, transaction type, change in stake and trading plan before inferring conviction."
    elif kind in SPECIAL_METRICS:
        drivers = ', '.join(profile['economic_drivers'])
        explanation = explanation or f"Assess {metric.replace('_', ' ') or 'the development'} against {drivers}."
        if metric in {'net_income', 'eps_basic', 'eps_diluted'} and kind in {'reit', 'holding_company'}:
            gate, reason, factor = gate or 'context', reason or 'secondary_accounting_metric', min(factor, 0.5)
            event['direction'] = 'neutral'
        elif kind == 'bank' and metric in {'operating_cash_flow', 'cfo', 'cash', 'long_term_debt'}:
            gate, reason, factor = gate or 'context', reason or 'bank_funding_context', min(factor, 0.5)
            event['direction'] = 'neutral'
        elif metric and metric not in SPECIAL_METRICS[kind]:
            factor = min(factor, 0.8)
    adjustment = (profile.get('metric_importance') or {}).get(metric) or {}
    if adjustment.get('importance') == 'context' and adjustment.get('reason') and adjustment.get('evidence'):
        gate, reason, factor = gate or 'context', reason or 'documented_metric_adjustment', min(factor, 0.5)
        explanation = adjustment['reason']
        event['direction'] = 'neutral'
    if explanation is None:
        explanation = f"{metric.replace('_', ' ').capitalize() or 'This development'} may affect {', '.join(profile['economic_drivers'][:3]) or 'the investment case'}. Compare with the prior period and thesis assumptions."
    event.update(security_profile=profile, economic_channel=channel,
        economic_relevance=round(factor, 3), eligibility_cap=gate, eligibility_reason=reason,
        entity_verified=verified, data_validation={'status': validation, 'flags': sorted(set(data_flags))},
        fact_confidence=(v.get('parser_confidence') or event.get('confidence') or 'med') if evidence_present else 'low',
        interpretation_confidence='low' if gate else profile['classification_confidence'],
        why_it_matters=explanation,
        recommended_follow_up=('Verify issuer, periods, units and the economic interpretation against the primary evidence.' if gate else 'Compare the affected driver with the current thesis and its falsifiers.'))
    return event


def enforce_eligibility(event: dict) -> dict:
    cap = event.get('eligibility_cap')
    if event.get('superseded_by'):
        return event
    if cap == 'context' and event.get('tier') == 'noise':
        event['triage_rules'] = list(dict.fromkeys((event.get('triage_rules') or []) + [event['eligibility_reason']]))
        return event
    if cap:
        event.pop('materiality_floor', None)
        event['tier'] = cap
        event['triage_verdict'] = 'auto_noise' if cap == 'noise' else ('human_review' if event.get('triage_verdict') == 'human_review' or event.get('eligibility_reason') in {'subject_unverified', 'financial_comparison_unverified', 'classification_unresolved'} else 'auto_context')
        event['feed_eligible'] = cap != 'noise'
        event['triage_rules'] = list(dict.fromkeys((event.get('triage_rules') or []) + [event['eligibility_reason']]))
        # Preserved specialist scores remain visible, but cannot bypass eligibility.
        event['raw_materiality'] = event.get('raw_materiality', event.get('materiality'))
        event['materiality'] = min(int(event.get('materiality') or 0), 24 if cap == 'noise' else 54)
        event['score'] = event['materiality']
    return event
