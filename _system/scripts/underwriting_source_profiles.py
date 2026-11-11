"""Dated owner-authorized CPRT source limits; default company limits stay unchanged."""
from __future__ import annotations
import json
from pathlib import Path
from underwriting_contract import require

def configure_source_budget(root,ticker):
    if ticker!='CPRT':return
    path=Path(root)/'_system/config/underwriting_policy.json'
    policy=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    profile=(policy.get('owner_source_exceptions') or {}).get(ticker)
    if profile is None:return
    require(profile.get('id')=='CPRT-owner-20261111-v3'
        and profile.get('parent_cik')=='900075' and profile.get('target_cik')=='1637873'
        and profile.get('document_context_characters')==450000
        and profile.get('parent_references')==4 and profile.get('target_references')==13
        and profile.get('total_references')==17 and profile.get('layers')==2,
        'Unknown owner source exception')
    registry=json.loads((Path(root)/'_system/portfolio/registry.json').read_text(encoding='utf-8'))
    actual=str((((registry.get('holdings') or {}).get(ticker) or {}).get('download') or {}).get('cik') or '')
    require(actual.isdigit() and int(actual)==int(profile['parent_cik']),'Owner source exception parent identity mismatch')
    from underwriting_foreign_financials import source_budget
    source_budget().configure_owner_profile(profile)


def native_context_tokens(root,ticker,packet):
    """A dated CPRT-only context decision, distinct from evidence character limits."""
    scope=(packet.get('primary_reference_usage') or {}).get('owner_authorized_scope') or {}
    if ticker!='CPRT' or scope.get('id')!='CPRT-owner-20261111-v3':return None
    require(packet.get('ticker')=='CPRT' and scope.get('parent')=='CPRT' and scope.get('target_cik')=='1637873',
            'Native context exception cannot transfer between companies')
    policy=json.loads((Path(root)/'_system/config/underwriting_policy.json').read_text(encoding='utf8'))
    profile=(policy.get('owner_source_exceptions') or {}).get('CPRT') or {}
    requested=profile.get('native_context_exception')
    require(requested=={'id':'CPRT-native-context-owner-20261111','model':'gpt-6.1-sol',
        'reasoning_effort':'high','context_tokens':872000},'CPRT complete evidence requires an explicit native context decision before admission')
    return requested['context_tokens']
