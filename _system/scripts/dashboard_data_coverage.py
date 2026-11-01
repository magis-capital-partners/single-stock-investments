"""Coverage of published evidence. Presence, verification and readiness stay distinct.

Offline only: never opens a provider session or schedules work. Required fields
describe the named metric set, not investment approval or universal eligibility.
"""
from __future__ import annotations

import math
from collections import Counter


def present(value) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    return isinstance(value, str) and bool(value.strip())


def result(total, complete, missing, definition, action, *, kind="field_presence", excluded=0):
    total, complete = max(0, int(total)), max(0, int(complete))
    if complete > total:
        raise ValueError("Coverage numerator exceeds its applicable denominator")
    return {"total_rows": total, "complete_rows": complete, "incomplete_rows": total-complete,
            "excluded_rows": excluded, "coverage_pct": round(100*complete/total, 1) if total else None,
            "missing_by_field": dict(missing), "definition": definition, "kind": kind,
            "next_action": action, "decision_approval": False}


def surface_coverage(surface: str, doc: dict) -> dict | None:
    if not isinstance(doc, dict) or doc.get("private_snapshot"):
        return None
    rows = doc.get("rows")
    fields = {"rock": ("ev_ebitda", "fcf_yield_pct"),
              "banks": ("deposits_total_usd", "dda_share_pct", "cost_of_deposits_pct", "p_tbv"),
              "nol": ("gross_nol_usd", "market_cap_usd")}.get(surface)
    if fields and isinstance(rows, list):
        rows = [r for r in rows if isinstance(r, dict)]
        missing = {key: sum(not present(r.get(key)) for r in rows) for key in fields}
        complete = sum(all(present(r.get(k)) for k in fields) for r in rows)
        if surface == "rock":
            # Operating metrics use a separate source contract. Do not pretend a
            # financial-data count also establishes operating-data completeness.
            missing["operating_required"] = sum(bool(r.get("operating_coverage", {}).get("required_missing")) for r in rows)
        out = result(len(rows), complete, missing, "Required comparison fields: " + ", ".join(fields),
                     "Reconcile source filings, units and periods; retain explicit reasons for undisclosed metrics.")
        out["backlog"] = [{"entity": r.get("ticker") or r.get("company") or "Unresolved issuer",
                           "missing": [k for k in fields if not present(r.get(k))],
                           "reason": r.get("evidence_gaps") or r.get("missing_reason") or "Required values are absent from this source publication; verify issuer filings, periods and reporting currency.",
                           "source": r.get("source_url") or r.get("source_ref"),
                           "checked_at": r.get("source_checked_at") or doc.get("built_at") or doc.get("generated_at")}
                          for r in rows if any(not present(r.get(k)) for k in fields)]
        return out
    if surface == "darwin":
        u=doc.get("universe") or {}
        if "count" not in u or "scored" not in u:
            return None
        return result(u["count"],u["scored"],{"unscored":u["count"]-u["scored"]},"Published scores / declared signal universe",
                      "Classify failed chains separately from earnings, liquidity and instrument exclusions.",kind="score_coverage")
    if surface == "buyback-radar":
        c=doc.get("counts") or {}
        if "companies" not in c or "verified" not in c:
            return None
        return result(c["companies"],c["verified"],{"unverified":c.get("gaps",c["companies"]-c["verified"])},
                      "Verified buyback evidence / declared company universe",
                      "Reconcile diluted shares and repurchase filings; discovery events remain under review.",kind="verification")
    if surface == "short-alpha":
        s=doc.get("summary") or {}
        if "candidate_count" not in s or "research_complete_count" not in s:
            return None
        return result(s["candidate_count"],s["research_complete_count"],{},"Research-complete candidates / published candidate universe",
                      "Complete held positions and time-sensitive theses first; require dated borrow and primary evidence.",kind="research_readiness")
    if surface == "inflections":
        c=doc.get("coverage") or {}
        if "universe" not in c:return None
        missing=len(c.get("no_trend_data") or [])
        return result(c["universe"],c["universe"]-missing,{"no_trend_data":missing},"Trend availability / declared broad universe",
                      "Separate unsupported instruments from missing issuer series before changing the eligible denominator.")
    if surface == "index-watch":
        rows=doc.get("by_ticker")
        if not isinstance(rows,dict):return None
        missing=Counter(k for r in rows.values() for k in (r.get("inputs_missing") or []))
        return result(len(rows),sum(not r.get("inputs_missing") for r in rows.values()),missing,
                      "Rows without listed input gaps / broad published universe; index eligibility is separate",
                      "Reconcile security identity, source dates, market cap, earnings, float, shares and volume.")
    if surface == "technical-summary":
        s=doc.get("summary") or {}
        if not all(k in s for k in ("requested","available","fresh")):return None
        return result(s["requested"],s["fresh"],{"unavailable":s["requested"]-s["available"],"not_fresh":s["available"]-s["fresh"]},
                      "Fresh technical snapshots / requested names",
                      "Resolve renamed, delisted and limited-history securities; retry only genuine collection failures.",kind="freshness")
    if surface == "market-risk-components":
        rows=doc.get("components")
        if not isinstance(rows,list):return None
        return result(len(rows),sum(r.get("quality_state")=="ready" for r in rows),Counter(r.get("quality_state") or "unknown" for r in rows if r.get("quality_state")!="ready"),
                      "Ready source components / registered components",
                      "Inspect each component's expected session, source clock and missing-evidence reason.",kind="source_readiness")
    if surface == "podcasts" and isinstance(doc.get("podcast_index"),list):
        rows=doc["podcast_index"];ready=sum(r.get("summary_status")=="ready" for r in rows)
        states=Counter(r.get("summary_status") or "not_classified" for r in rows if r.get("summary_status")!="ready")
        return result(len(rows),ready,states,"Reader summaries ready / published podcast catalog",
                      "Prioritize portfolio-relevant transcripts, then process the existing bounded summary queue.",kind="processing")
    if surface == "biotech-quant":
        s=doc.get("summary") or {}
        if "universe" not in s or "scored" not in s:return None
        factors={r["id"]:r.get("universe",0)-r.get("populated",0) for r in doc.get("coverage",[]) if r.get("id")}
        out=result(s["universe"],s["scored"],factors,"Scored companies / declared biotech universe; factor dates and validation are separate",
                   "Verify historical availability, date spend inputs, classify undated insider zeros, and collect peer/short-interest evidence.",kind="score_coverage")
        out["factors"]=[{k:r.get(k) for k in ("id","label","status","observed_at","populated","universe","zeros")} for r in doc.get("coverage",[])]
        out["independent_forward_outcomes"]=s.get("independent_forward_outcomes")
        return out
    if surface == "irr-readiness":
        s=doc.get("summary") or {}
        if "companies" not in s or "ready" not in s:return None
        return result(s["companies"],s["ready"],s.get("blocked_requirements") or {},"Companies passing every canonical IRR requirement / assessed companies",
                      "Reconcile price/source mapping first; then complete issuer-specific models, proof and dated cash flows without weakening publication gates.",kind="decision_readiness")
    return None
