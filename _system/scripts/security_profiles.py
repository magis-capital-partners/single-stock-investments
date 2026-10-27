"""Economic identity shared by security readiness and event interpretation.

Valuation routing is deliberately not an authority for instrument identity.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DRIVERS = {
    'operating_company': ['revenue quality', 'operating margins', 'owner cash generation', 'returns on capital'],
    'spot_crypto_fund': ['underlying asset economics', 'NAV per share', 'tracking difference', 'fees', 'custody'],
    'asset_fund': ['underlying portfolio', 'NAV per share', 'tracking difference', 'fees', 'liquidity'],
    'futures_fund': ['underlying exposure', 'roll yield', 'collateral', 'tracking difference', 'fees'],
    'leveraged_fund': ['daily exposure target', 'path dependence', 'financing costs', 'tracking difference'],
    'reit': ['AFFO per share', 'occupancy', 'lease economics', 'leverage'],
    'bank': ['credit losses', 'capital adequacy', 'deposit funding', 'net interest margin'],
    'insurer': ['underwriting results', 'reserves', 'investment income', 'capital adequacy'],
    'holding_company': ['look-through asset value', 'subsidiary economics', 'capital allocation'],
    'unresolved': [],
}


def canonical_symbol(value: str) -> str:
    # Only punctuation aliases of the same share class; never collapse A and B.
    symbol = str(value or '').strip().upper().replace('-', '.')
    return {'BKRB': 'BRK.B', 'BRKB': 'BRK.B'}.get(symbol, symbol)


def resolve_economic_profile(ticker: str, *, identity=None, entry=None, override=None) -> dict:
    identity, entry, override = identity or {}, entry or {}, override or {}
    registry_name = entry.get('company')
    name = override.get('issuer_name') or (registry_name if canonical_symbol(registry_name) != canonical_symbol(ticker) else None) or identity.get('issuer_name') or registry_name or ticker
    security_type = override.get('security_type') or entry.get('security_type') or identity.get('security_type')
    profile = override.get('economic_profile') or entry.get('economic_profile') or identity.get('economic_profile')
    text = ' '.join(str(x or '') for x in (name, entry.get('sector'), entry.get('industry'),
        identity.get('sector'), identity.get('industry'), (entry.get('classification') or {}).get('archetype'))).lower()
    evidence = override.get('identity_evidence') or identity.get('identity_evidence')
    if not profile:
        fund = security_type == 'exchange_traded_fund' or bool(re.search(r'\betf\b|exchange.traded fund', text))
        if fund:
            profile = 'leveraged_fund' if re.search(r'leveraged|inverse|[23]x\b', text) else (
                'futures_fund' if 'futures' in text else 'asset_fund')
            security_type = 'exchange_traded_fund'
        elif re.search(r'\breit\b|real estate investment trust', text):
            profile = 'reit'
        elif re.search(r'\bbank\b|banking|credit_and_normalized_returns', text):
            profile = 'bank'
        elif re.search(r'\binsurance\b|\binsurer\b', text):
            profile = 'insurer'
        elif security_type == 'pure_holding_company' or re.search(r'holding_co\b|holding_company', text):
            profile = 'holding_company'
        elif override.get('security_type') in {'operating_company', 'foreign_operating_company_adr'}:
            profile = 'operating_company'
        elif canonical_symbol(name) != canonical_symbol(ticker) and not re.search(r'\btrust\b', text):
            profile = 'operating_company'
        else:
            profile = 'unresolved'
    if profile not in DRIVERS:
        profile = 'unresolved'
    security_type = security_type if profile != 'unresolved' else 'unknown'
    security_type = security_type or ('exchange_traded_fund' if profile.endswith('_fund') else 'operating_company')
    return {
        'issuer_name': name, 'security_type': security_type, 'economic_profile': profile,
        'cik': override.get('cik') or (entry.get('download') or {}).get('cik') or identity.get('cik'),
        'underlying_exposure': override.get('underlying_exposure') or identity.get('underlying_exposure') or entry.get('underlying_exposure'),
        'economic_drivers': list(DRIVERS[profile]),
        'classification_status': 'unresolved' if profile == 'unresolved' else 'resolved',
        'classification_confidence': 'high' if evidence else ('medium' if profile != 'unresolved' else 'low'),
        'identity_evidence': evidence or ('registry_metadata' if profile != 'unresolved' else None),
        'metric_importance': override.get('metric_importance') or entry.get('metric_importance') or identity.get('metric_importance') or {},
    }


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=8)
def profile_inputs(root: Path = ROOT):
    return (_read(root / '_system/portfolio/registry.json').get('holdings') or {},
            _read(root / '_system/reference/security_identity_overrides.json').get('tickers') or {})


@lru_cache(maxsize=8)
def security_names(root: Path = ROOT):
    return _read(root / '_system/reference/securities/security_master.json')


@lru_cache(maxsize=4096)
def security_profile(ticker: str, root: Path = ROOT) -> dict:
    registry, overrides = profile_inputs(root)
    key = next((k for k in registry if canonical_symbol(k) == canonical_symbol(ticker)), ticker)
    override = overrides.get(ticker) or overrides.get(key) or next(
        (v for k, v in overrides.items() if canonical_symbol(k) == canonical_symbol(ticker)), {})
    identity = _read(root / key / 'research/security_identity.json')
    market = _read(root / key / 'research/market_inputs.json')
    entry = {**(registry.get(key) or {})}
    master = security_names(root).get(key) or {}
    if canonical_symbol(entry.get('company')) in {'', canonical_symbol(ticker)} and master.get('validation_status') in {'manual', 'verified'}:
        entry['company'] = master.get('name') or entry.get('company')
    for field in ('sector', 'industry'):
        entry[field] = entry.get(field) or market.get(field) or (market.get('company_info') or {}).get(field)
    return resolve_economic_profile(ticker, entry=entry, identity=identity, override=override)
