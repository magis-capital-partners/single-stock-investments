"""Private, reproducible before/after ownership audit. Never changes economics."""
from collections import Counter
from decimal import Decimal
from .strategy_ownership import digest


def audit_changes(before, after):
    previous = {r["record_id"]: r for r in before["records"]}
    current = {r["record_id"]: r for r in after["records"]}
    if previous.keys() != current.keys():
        raise ValueError("ownership correction changed broker realization identities")
    fields = ("quantity", "realized_native", "realized_usd", "cost_basis", "fx_rate", "currency", "commission", "proceeds")
    changes = []
    for identity, row in current.items():
        old = previous[identity]
        if any(old.get(key) != row.get(key) for key in fields):
            raise ValueError("ownership correction changed broker financial amounts")
        if old["owner"] != row["owner"] or old["strategy"] != row["strategy"]:
            changes.append({"record_id": identity, "symbol": row["symbol"], "from_owner": old["owner"],
                            "to_owner": row["owner"], "reason": row["allocation_reason"]})
    def totals(history):
        owners = {r["owner"] for r in history["records"]}
        return {owner: str(sum((Decimal(r["realized_usd"]) for r in history["records"]
                               if r["owner"] == owner and r["realized_usd"] is not None), Decimal(0))) for owner in owners}
    return {"schema_version": "ownership_audit.v1", "before_generation": before["generation_id"],
            "after_generation": after["generation_id"], "ownership_version": after["ownership_version"],
            "financial_amounts_unchanged": True, "record_count": len(current),
            "before_totals_usd": totals(before), "after_totals_usd": totals(after),
            "transitions": dict(Counter(f"{c['from_owner']}->{c['to_owner']}" for c in changes)),
            "changes": changes, "before_hash": digest(before), "after_hash": digest(after)}
