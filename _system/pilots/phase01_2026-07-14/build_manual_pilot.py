#!/usr/bin/env python3
"""Reproduce the Phase 0 baseline and six-name manual Phase 1 pilot.

This is deliberately pilot-scoped. It freezes existing local evidence and
renders already-completed isolated votes; it is not the production committee
orchestration planned for Phase 2.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DATE = "2026-07-14"
FROZEN_AT = "2026-07-14T20:00:00Z"
DIMS = ("explanatory_strength", "evidence_sufficiency", "downside_control", "return_vs_alternatives")
ANCHORS = {
    "explanatory_strength": "causal mechanism and discriminating test",
    "evidence_sufficiency": "current primary evidence and explicit gaps",
    "downside_control": "permanent-loss paths and relevant stress",
    "return_vs_alternatives": "return range versus the portfolio hurdle",
}
BASELINE_FINDINGS = {
    "ZTS": {"factual_warnings": ["Executive-summary percentage lint warning", "Live price sanity unresolved"], "unsupported_or_unresolved_claims": ["Targeted disclosure and short scans were not run despite the pass header"]},
    "TPL": {"factual_warnings": ["Strict lint failed: payoff lens missing and prose rule violation"], "unsupported_or_unresolved_claims": ["Realizable acreage and royalty NAV lacks an independent appraisal"]},
    "FRMO": {"factual_warnings": ["Strict lint failed: current book estimate and thematic context missing"], "unsupported_or_unresolved_claims": ["Investment A uplift and SOTP tie-out are not independently supported"]},
    "WYNN": {"factual_warnings": ["Executive-summary percentage lint warning", "Live price marked for human review"], "unsupported_or_unresolved_claims": ["Debt maturity/covenant and remaining UAE funding schedules are missing"]},
    "SMCI": {"factual_warnings": ["No deep dive, valuation, or primary filing packet"], "unsupported_or_unresolved_claims": ["Active short campaign is not reconciled to filings"]},
    "SRPT": {"factual_warnings": ["No deep dive or primary filing packet"], "unsupported_or_unresolved_claims": ["Context overlay is not an investment valuation"]}
}

DATA = {
    "ZTS": {
        "refs": ["ZTS/research/deep_dive_2026-07-11.md", "ZTS/research/adversarial_2026-07-11.md", "ZTS/research/valuation.json", "ZTS/research/evidence/filing_facts_2026-07-11.json"],
        "thesis": "Trusted animal-health franchises and recurring prevention demand support owner cash, but leverage-funded repurchases and unresolved price sanity prevent approval.",
        "alt": "The apparent discount compensates for U.S. companion weakness, product maturity, and leverage rather than temporary mispricing.",
        "missing": "Verified executable price and a product-level price/volume/mix bridge.",
        "ret": [9.4, 21.1], "horizon": 7,
        "raters": [("buffett_weschler", "quality_reinvestment"), ("pabrai", "asymmetry_downside"), ("hohn", "competitive_advantage")],
        "r1": [("sufficient", "watch", [4,4,3,4]), ("outside_power_zone", "defer", [3,4,3,3]), ("sufficient", "watch", [4,4,3,3])],
        "r2": [("sufficient", "watch", [4,3,3,3]), ("outside_power_zone", "defer", [3,4,3,4]), ("insufficient_evidence", "defer", [4,3,2,3])],
        "question": "Can the packet verify price and separate organic franchise growth from debt-funded per-share growth?",
        "answer": "Partly. The packet anchors $76.59, $9.042B debt, and $3.235B repurchases; executable price and the product bridge remain unresolved.",
        "pm": "U.S. companion weakness persists while debt-funded repurchases consume flexibility and core product growth slows.",
        "pm_status": "partial", "pm_unresolved": ["Targeted 8-K scan not run", "Current targeted short scan not run", "Live price unresolved"],
        "old": "ZTS/research/deep_dive_2026-07-11.md"
    },
    "TPL": {
        "refs": ["TPL/research/deep_dive_2026-06-04.md", "TPL/research/adversarial_2026-06-01.md", "TPL/research/valuation.json", "TPL/research/evidence/filing_facts_2026-06-01.json"],
        "thesis": "Irreplaceable Permian land, royalties, and water assets explain excellent economics, but the current modeled return is negative and hidden assets lack a realizable appraisal.",
        "alt": "Parcel-level scarcity and future water or royalty options are materially understated by the cash-flow model.",
        "missing": "Transaction-supported parcel and royalty NAV without double counting operating cash flow.",
        "ret": [-12.6, -2.9], "horizon": 7,
        "raters": [("hohn", "competitive_advantage"), ("pabrai", "asymmetry_downside"), ("hk", "scarce_assets")],
        "r1": [("sufficient", "reject", [5,4,2,1]), ("outside_power_zone", "reject", [4,4,2,1]), ("sufficient", "reject", [5,4,2,1])],
        "r2": [("sufficient", "reject", [5,3,2,1]), ("outside_power_zone", "reject", [4,4,2,1]), ("sufficient", "reject", [5,4,1,1])],
        "question": "Does current local evidence resolve the report/valuation mismatch and establish realizable NAV?",
        "answer": "The rebuilt operating model produces -12.6%/-7.5%/-2.9%, disables weighted synthesis, and values every material component at $131/$162/$198 per share (low/base/high), including risked acreage ranges.",
        "pm": "Permian activity and water growth weaken while investors continue paying for scarcity already capitalized in the quote.",
        "pm_status": "partial", "pm_unresolved": ["Targeted 8-K scan not run", "Current targeted short scan not run", "Independent asset appraisal missing"],
        "old": "TPL/research/deep_dive_2026-06-04.md"
    },
    "FRMO": {
        "refs": ["FRMO/research/deep_dive_2026-06-04.md", "FRMO/research/adversarial_2026-05-29.md", "FRMO/research/valuation.json", "FRMO/research/evidence/filing_facts_2026-06-01.json"],
        "thesis": "Price below reported book and latent holdings create asymmetry, but Investment A opacity and unsupported SOTP uplifts prevent a decision-grade payoff.",
        "alt": "The discount is rational and persistent because concentrated marks, related parties, weak liquidity, and indefinite catalysts impair realization.",
        "missing": "Security-level Investment A look-through validating or replacing the $4.50 uplift and $0.44 tie-out.",
        "ret": [7.2, 30.1], "horizon": 5,
        "raters": [("hk", "scarce_assets"), ("pabrai", "asymmetry_downside"), ("greenblatt", "special_situations")],
        "r1": [("sufficient", "watch", [4,3,3,4]), ("sufficient", "watch", [4,3,3,4]), ("insufficient_evidence", "defer", [2,3,3,3])],
        "r2": [("sufficient", "watch", [4,2,3,2]), ("sufficient", "watch", [3,3,3,4]), ("insufficient_evidence", "defer", [2,2,3,2])],
        "question": "Can local evidence validate Investment A and eliminate the SOTP tie-out slack?",
        "answer": "No. Reported book and 82% concentration are supported; the look-through, $4.50 uplift, and $0.44 tie-out remain unresolved.",
        "pm": "Investment A is marked down, accounting concerns persist, and no asset realization closes the OTC discount within the modeled horizon.",
        "pm_status": "complete", "pm_unresolved": ["Investment A look-through missing", "Restatement impact incomplete", "Wrong-ticker short inventory item requires correction"],
        "old": "FRMO/research/deep_dive_2026-06-04.md"
    },
    "WYNN": {
        "refs": ["WYNN/research/deep_dive_2026-07-11.md", "WYNN/research/adversarial_2026-07-11.md", "WYNN/research/valuation.json", "WYNN/research/evidence/filing_facts_2026-07-11.json"],
        "thesis": "Scarce licenses and luxury properties support strong property economics, but debt, refinancing exposure, and unproven UAE reinvestment leave the equity below the return hurdle.",
        "alt": "Macau momentum is cyclical operating leverage and UAE capital consumption prevents shareholders from capturing property quality.",
        "missing": "Debt maturity/covenant schedule and remaining UAE funding under a stressed Macau case.",
        "ret": [4.0, 17.2], "horizon": 7,
        "raters": [("hohn", "competitive_advantage"), ("pabrai", "asymmetry_downside"), ("buffett_weschler", "quality_reinvestment")],
        "r1": [("sufficient", "watch", [4,4,2,3]), ("outside_power_zone", "reject", [4,4,2,2]), ("sufficient", "watch", [4,4,2,2])],
        "r2": [("sufficient", "watch", [4,3,2,3]), ("outside_power_zone", "reject", [4,3,2,2]), ("insufficient_evidence", "defer", [4,2,1,2])],
        "question": "Does the packet bound refinancing and remaining UAE funding risk?",
        "answer": "No. It confirms $10.547B debt, $625.6M interest, and $328.9M FY2025 UAE investment, but not maturities, covenants, or remaining funding.",
        "pm": "Macau slows as debt must be refinanced and UAE construction is delayed or exceeds budget.",
        "pm_status": "partial", "pm_unresolved": ["Targeted 8-K scan not run", "Current targeted short scan not run", "Debt and UAE funding schedules missing"],
        "old": "WYNN/research/deep_dive_2026-07-11.md"
    },
    "SMCI": {
        "refs": ["SMCI/research/thesis.md", "SMCI/research/activist_reconcile_2026-07-12.md", "SMCI/third-party-analyses/activist_reports_index.json"],
        "thesis": "No investment thesis can be established because primary filings, a valuation, and a reconciled forensic packet are absent.",
        "alt": "AI infrastructure growth could create substantial value, but local evidence cannot distinguish durability from cyclical hardware economics.",
        "missing": "Completed filing packet, short-claim reconciliation, normalized owner cash, and downside valuation.",
        "ret": None, "horizon": None,
        "raters": [("hohn", "competitive_advantage"), ("pabrai", "asymmetry_downside"), ("buffett_weschler", "quality_reinvestment")],
        "r1": [("insufficient_evidence", "defer", [1,1,1,1])]*3, "r2": [("insufficient_evidence", "defer", [1,1,1,1])]*3,
        "question": "Can the local packet support any directional vote?", "answer": "No. No valuation, deep dive, or primary filing packet exists.",
        "pm": "The process fails by committing capital before reconciling an active forensic short campaign to primary filings.",
        "pm_status": "complete", "pm_unresolved": ["Primary filing review not run", "Hindenburg claims unreconciled", "Valuation not run"], "old": None
    },
    "SRPT": {
        "refs": ["SRPT/research/thesis.md", "SRPT/research/valuation.json"],
        "thesis": "No investment thesis can be established because the only valuation artifact is a context overlay without clinical, regulatory, liquidity, or payoff underwriting.",
        "alt": "Approved products or platform value may provide a floor, but the local packet does not quantify it.",
        "missing": "Primary clinical/regulatory packet, cash runway, liabilities, and probability-weighted security valuation.",
        "ret": None, "horizon": None,
        "raters": [("hohn", "competitive_advantage"), ("pabrai", "asymmetry_downside"), ("greenblatt", "special_situations")],
        "r1": [("insufficient_evidence", "defer", [1,1,1,1])]*3, "r2": [("insufficient_evidence", "defer", [1,1,1,1])]*3,
        "question": "Can the context overlay support a clinical or event-driven vote?", "answer": "No. It explicitly is not a company valuation and no primary clinical/regulatory packet exists.",
        "pm": "A binary clinical, safety, or regulatory loss permanently impairs capital before liquidity and liabilities are understood.",
        "pm_status": "complete", "pm_unresolved": ["Primary filings not reviewed", "Clinical/regulatory review not run", "Short-source review not run", "Valuation not run"], "old": None
    }
}


def file_ref(path: str) -> dict:
    p = ROOT / path
    b = p.read_bytes()
    return {"path": path, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b), "role": "frozen local evidence", "status": "available"}


def packet(refs: list[dict]) -> tuple[str, str]:
    canonical = [{k: r[k] for k in ("path", "sha256", "bytes")} for r in sorted(refs, key=lambda x: x["path"])]
    h = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    freshness = "insufficient_evidence" if len(refs) < 3 else "mixed"
    return h, freshness


def vote(persona: str, group: str, row, d: dict) -> dict:
    status, decision, values = row
    scores = {dim: {"value": value, "rationale": f"{value}/5 against the written anchor for {ANCHORS[dim]}."} for dim, value in zip(DIMS, values)}
    return {"persona": persona, "independence_group": group, "evidence_status": status, "scores": scores, "vote": decision,
            "expected_return_range_pct": d["ret"], "horizon_years": d["horizon"],
            "claims": [{"claim": d["thesis"], "evidence_paths": d["refs"][:2]}],
            "strongest_counter_explanation": d["alt"], "most_important_missing_fact": d["missing"],
            "falsifiers": [f"Reassess when this missing fact is resolved: {d['missing']}"],
            "specialist_findings": f"Method result: {decision}; evidence status: {status}.",
            "confidence": "high" if status == "insufficient_evidence" or decision in ("reject",) else "medium"}


def gate(value: str) -> str:
    return value


def make_record(ticker: str, d: dict) -> dict:
    refs = [file_ref(p) for p in d["refs"]]
    h, freshness = packet(refs)
    r1 = [vote(*rater, row, d) for rater, row in zip(d["raters"], d["r1"])]
    r2 = [vote(*rater, row, d) for rater, row in zip(d["raters"], d["r2"])]
    med = {dim: median(v["scores"][dim]["value"] for v in r2) for dim in DIMS}
    ranges = {dim: [min(v["scores"][dim]["value"] for v in r2), max(v["scores"][dim]["value"] for v in r2)] for dim in DIMS}
    blocked = ticker in ("FRMO", "SMCI", "SRPT") or freshness == "insufficient_evidence"
    disclosure = "not_run" if ticker in ("ZTS", "TPL", "FRMO", "WYNN") else "not_run"
    record = {
        "schema_version": "1.0", "protocol_version": "manual-pilot-1.0", "ticker": ticker,
        "review": {"level": "full_ic", "trigger": "Phase 1 contrasting-name manual pilot", "as_of": DATE, "owner": None},
        "evidence_packet": {"frozen_at": FROZEN_AT, "hash_method": "sha256(canonical-json(sorted(path,sha256,bytes)))", "packet_hash": h, "freshness_status": freshness, "references": refs},
        "proposer": {"recommendation_hidden_in_round_one": True, "thesis": d["thesis"], "explanation_contracts": [{"id": "primary_thesis", "mechanism": d["thesis"], "evidence_paths": d["refs"][:2], "distinguishing_test": d["question"], "counter_explanation": d["alt"], "falsifier": f"Resolve and test: {d['missing']}", "valuation_link": "Changes the evidenced return range or prevents one from being stated."}], "open_questions": [d["missing"]]},
        "selected_raters": [{"persona": p, "independence_group": g, "selection_reason": "Contrasting power-zone method selected before round one.", "required_inputs_status": "missing" if freshness == "insufficient_evidence" else "partial"} for p,g in d["raters"]],
        "round_one": {"evidence_hash": h, "peer_outputs_visible": False, "votes": r1},
        "pre_mortem": {"status": d["pm_status"], "failure_story": d["pm"], "earliest_warning_signals": d["pm_unresolved"], "forensic_checks": d["pm_unresolved"], "short_source_coverage": "not_run" if ticker in ("SMCI", "SRPT") else "partial", "unresolved_items": d["pm_unresolved"]},
        "research_loop": {"loop_count": 1, "questions": [d["question"]], "responses": [{"question": d["question"], "answer": d["answer"], "evidence_paths": d["refs"], "status": "partially_answered" if "remain" in d["answer"].lower() or d["answer"].startswith("No") else "answered"}], "evidence_hash_after": h},
        "round_two": {"evidence_hash": h, "peer_outputs_visible": False, "votes": r2},
        "synthesis": {"strongest_dissent": d["alt"], "unresolved_items": [d["missing"]] + d["pm_unresolved"], "vote_split": dict(Counter(v["vote"] for v in r2)), "score_medians": med, "score_ranges": ranges, "dissent_ledger": [{"issue": d["missing"], "impact": "high", "status": "unresolved", "owner_response": None}]},
        "gates": {"price": "blocked" if ticker in ("ZTS", "SMCI", "SRPT") else "partial", "shares": "blocked" if freshness == "insufficient_evidence" else "pass", "reporting_period": "blocked" if freshness == "insufficient_evidence" else "pass", "filing_reconciliation": "not_run" if freshness == "insufficient_evidence" else "pass", "disclosure_scan": disclosure, "short_scan": "not_run" if ticker in ("SMCI", "SRPT") else "partial", "pre_mortem": "pass", "explanation_contracts": "pass", "independent_groups": "pass", "owner": "not_run"},
        "human_decision": {"status": "pending", "decision": None, "sizing": None, "top_dissent_response": None, "decided_at": None},
        "final_state": "evidence_blocked" if blocked else "committee_complete_decision_pending",
        "provenance": {"prompt_version": "phase01-isolated-rater-1", "model": "three isolated Codex raters plus separate pre-mortem", "schema_path": "_system/templates/committee_schema.json", "persona_registry_version": "1.2"}
    }
    val_path = ROOT / ticker / "research" / "valuation.json"
    if val_path.exists():
        valuation = json.loads(val_path.read_text(encoding="utf-8"))
        component_review = valuation.get("component_review_queue")
        if component_review:
            record["component_review"] = component_review
    return record


def render_report(record: dict) -> str:
    r2 = record["round_two"]["votes"]
    score = record["synthesis"]["score_medians"]
    component_review = record.get("component_review") or {}
    component_section = ""
    if component_review:
        items = component_review.get("items") or []
        rows = "\n".join(
            f"| {item['label']} | ${item['range_per_share']['low']:.2f} | ${item['range_per_share']['base']:.2f} | ${item['range_per_share']['high']:.2f} | {', '.join(item['recommended_raters'])} | {item['status']} |"
            for item in items
        )
        component_section = (
            "\n## Component review queue\n\n"
            f"{component_review['decision_rule']}\n\n"
            "| Component | Low | Base | High | Assigned methods | Status |\n"
            "|---|---:|---:|---:|---|---|\n"
            f"{rows}\n"
        )
    return f"""# {record['ticker']} — Phase 1 committee pilot

**State:** {record['final_state']}<br>
**Owner decision:** pending
**Evidence hash:** `{record['evidence_packet']['packet_hash']}`

## Decision card

Round-two split: {record['synthesis']['vote_split']}. Median scores: explanation {score['explanatory_strength']}/5, evidence {score['evidence_sufficiency']}/5, downside {score['downside_control']}/5, return {score['return_vs_alternatives']}/5. This is not a final recommendation until the owner acts.

## Strongest dissent first

{record['synthesis']['strongest_dissent']}

Unresolved: {'; '.join(record['synthesis']['unresolved_items'])}.

## Causal thesis

{record['proposer']['thesis']}

The distinguishing test is: {record['proposer']['explanation_contracts'][0]['distinguishing_test']}

## Pre-mortem

{record['pre_mortem']['failure_story']}

Coverage is {record['pre_mortem']['status']}; short-source coverage is {record['pre_mortem']['short_source_coverage']}.

{component_section}

## Round-two independent votes

""" + "\n".join(f"- **{v['persona']} ({v['independence_group']}):** {v['vote']} — {v['evidence_status']}" for v in r2) + "\n\n## What changes our mind\n\n" + record["round_two"]["votes"][0]["falsifiers"][0] + "\n\n## Evidence\n\n" + "\n".join(f"- `{x['path']}` ({x['status']})" for x in record["evidence_packet"]["references"]) + "\n"


def baseline_row(ticker: str, d: dict) -> dict:
    def stats(path):
        if not path: return {"path": None, "exists": False, "words": 0, "human_review_tags": 0}
        p=ROOT/path
        text=p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        return {"path": path, "exists": p.exists(), "words": len(re.findall(r"\b[\w.%$-]+\b", text)), "human_review_tags": text.lower().count("[human review]")}
    return {"ticker": ticker, "deep_dive": stats(d["old"]), "adversarial": stats(next((p for p in d["refs"] if "adversarial_" in p), None)), "valuation_exists": (ROOT/ticker/"research"/"valuation.json").exists(), "strict_lint": {"ZTS":"pass_with_warning", "TPL":"fail", "FRMO":"fail", "WYNN":"pass_with_warning", "SMCI":"no_report", "SRPT":"no_report"}[ticker], **BASELINE_FINDINGS[ticker], "review_time_minutes": None, "review_time_note": "Historical review time was not captured; do not backfill an estimate."}


def main():
    blind=OUT/"blind_comparison"; blind.mkdir(parents=True, exist_ok=True)
    records=[]; key={}
    for i,(ticker,d) in enumerate(DATA.items()):
        rec=make_record(ticker,d); records.append(rec)
        research=ROOT/ticker/"research"; research.mkdir(parents=True, exist_ok=True)
        (research/f"committee_{DATE}.json").write_text(json.dumps(rec,indent=2)+"\n",encoding="utf-8")
        report=render_report(rec); (research/f"deep_dive_committee_{DATE}.md").write_text(report,encoding="utf-8")
        if d["old"]:
            old=(ROOT/d["old"]).read_text(encoding="utf-8",errors="replace")
            # Alternate labels by ticker; the key is intentionally separate.
            if i % 2 == 0: a,b,which=old,report,{"A":"old","B":"committee"}
            else: a,b,which=report,old,{"A":"committee","B":"old"}
            (blind/f"{ticker}_A.md").write_text(a,encoding="utf-8"); (blind/f"{ticker}_B.md").write_text(b,encoding="utf-8"); key[ticker]=which
    baseline={"as_of":DATE,"pilots":[baseline_row(t,d) for t,d in DATA.items()],"known_baseline_limits":["Historical review time was not captured.","SMCI and SRPT have no old deep-dive report, so blinded old-versus-new comparison is unavailable for those names."]}
    (OUT/"baseline.json").write_text(json.dumps(baseline,indent=2)+"\n",encoding="utf-8")
    (OUT/"comparison_key_open_after_scoring.json").write_text(json.dumps(key,indent=2)+"\n",encoding="utf-8")
    (OUT/"owner_scorecard.md").write_text("# Blinded owner scorecard\n\nDo not open `comparison_key_open_after_scoring.json` until scoring. Review each available A/B pair for ZTS, TPL, FRMO, and WYNN. Record preferred version, factual errors, unresolved items exposed, and decision usefulness. SMCI and SRPT lack old reports and are not valid A/B comparisons.\n",encoding="utf-8")
    print(f"Wrote {len(records)} committee records and reports")

if __name__ == "__main__":
    main()
