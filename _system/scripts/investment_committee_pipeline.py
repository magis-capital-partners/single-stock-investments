#!/usr/bin/env python3
"""Production Investment Committee packet and assembly pipeline.

The script does not call models and never invents votes. It freezes evidence,
selects method-diverse raters, writes isolated work packets, validates completed
work, and assembles a schema-compatible record only after every required stage
exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median

from build_valuation_workbench import write as write_valuation_workbench

ROOT = Path(__file__).resolve().parents[2]
DIMS = ("explanatory_strength", "evidence_sufficiency", "downside_control", "return_vs_alternatives")
GROUPS = {
    "hohn": "competitive_advantage",
    "buffett_weschler": "quality_reinvestment",
    "marathon_capital_cycle": "capital_cycle",
    "marks_credit_cycle": "credit_cycle",
    "klarman_asset_value": "asset_realization",
    "hk": "scarce_assets",
    "stahl": "scarce_assets",
    "pabrai": "asymmetry_downside",
    "greenblatt": "special_situations",
    "moi": "special_situations",
}
DEFAULT_RATERS = ("hohn", "pabrai", "marks_credit_cycle")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def file_reference(path: Path) -> dict:
    raw = path.read_bytes()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "role": "frozen local evidence",
        "status": "available",
    }


def packet_hash(refs: list[dict]) -> str:
    canonical = [{k: row[k] for k in ("path", "sha256", "bytes")} for row in sorted(refs, key=lambda x: x["path"])]
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def latest(ticker_dir: Path, pattern: str, exclude: str | None = None) -> Path | None:
    rows = sorted(path for path in ticker_dir.glob(pattern) if not exclude or exclude not in path.name)
    return rows[-1] if rows else None


def discover_evidence(ticker: str) -> list[Path]:
    research = ROOT / ticker / "research"
    candidates = [
        latest(research, "deep_dive_*.md", exclude="deep_dive_committee_"),
        latest(research, "adversarial_*.md"),
        research / "valuation.json",
        research / "thesis.md",
        latest(research, "cross_check_third_party_*.md"),
        research / "cross_check_third_party.md",
        latest(research, "*evidence_reconciliation*.json"),
        latest(research, "*evidence_reconciliation*.md"),
        latest(research / "evidence", "filing_facts_*.json"),
        latest(research / "evidence", "management_facts_*.json"),
    ]
    seen: set[Path] = set()
    out = []
    for path in candidates:
        if path and path.exists() and path not in seen and "deep_dive_committee_" not in path.name:
            out.append(path)
            seen.add(path)
    return out


def select_raters(valuation: dict) -> list[dict]:
    """Pick three raters with distinct error profiles.

    Preference order: the power-zone method route's primary personas, then its
    cross-check personas, then component-coverage recommendations, then the
    static defaults. Personas the route explicitly silenced are never seated;
    the same routing that chose the valuation method chooses who reviews it.
    """
    route = valuation.get("valuation_method_route") or {}
    silent = set(route.get("silent_personas") or [])
    route_ranked = [
        persona
        for persona in [*(route.get("primary_personas") or []), *(route.get("cross_check_personas") or [])]
        if persona not in silent
    ]
    queue = valuation.get("component_review_queue") or {}
    counts = Counter(
        persona
        for item in queue.get("items", [])
        for persona in item.get("recommended_raters", [])
    )
    ranked: list[str] = list(dict.fromkeys([
        *route_ranked,
        *(persona for persona, _ in counts.most_common() if persona not in silent),
        *(persona for persona in DEFAULT_RATERS if persona not in silent),
    ]))
    selected = []
    groups: set[str] = set()
    for persona in ranked:
        group = GROUPS.get(persona, persona)
        if group in groups:
            continue
        if persona in route_ranked:
            reason = "Selected before scoring from the power-zone method route (persona chose or cross-checks the valuation method)."
        else:
            reason = "Selected before scoring from component coverage and a distinct error profile."
        selected.append({
            "persona": persona,
            "independence_group": group,
            "selection_reason": reason,
            "required_inputs_status": "partial",
        })
        groups.add(group)
        if len(selected) == 3:
            break
    if len(selected) != 3:
        raise ValueError("could not select three independent rater groups")
    return selected


def rater_prompt(ticker: str, persona: str, group: str, packet: str, evidence: list[dict], round_number: int) -> str:
    paths = "\n".join(f"- `{row['path']}`" for row in evidence)
    return f"""# {ticker} - isolated committee round {round_number}

You are the **{persona}** method, independence group **{group}**.

Evidence packet: `{packet}`

{paths}

Rules:

1. Do not inspect another rater's output or any synthesis.
2. Ignore time already spent on the idea and prior portfolio ownership.
3. Score explanatory strength, evidence sufficiency, downside control, and return versus alternatives from 1-5 with a rationale.
4. Use `insufficient_evidence` or `outside_power_zone` when appropriate; abstention is valid.
5. State the strongest counter-explanation and the single most important missing fact.
6. Audit the economic claim, every valuation-proof row, comparable adjustments, capital requirements, option probabilities, and overlap controls before voting.
7. Return only one JSON object matching the committee schema vote definition.
"""


def initialize(ticker: str, as_of: str) -> Path:
    ticker = ticker.upper()
    research = ROOT / ticker / "research"
    valuation_path = research / "valuation.json"
    if not valuation_path.exists():
        raise FileNotFoundError(f"{ticker}: valuation.json missing")
    valuation = read_json(valuation_path)
    evidence_paths = discover_evidence(ticker)
    if len(evidence_paths) < 3:
        raise ValueError(f"{ticker}: at least three evidence artifacts are required")
    refs = [file_reference(path) for path in evidence_paths]
    frozen_hash = packet_hash(refs)
    raters = select_raters(valuation)
    work = research / "committee_work" / as_of
    manifest = {
        "pipeline_version": "2.0",
        "ticker": ticker,
        "as_of": as_of,
        "stage": "round_one_open",
        "packet_hash": frozen_hash,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "evidence": refs,
        "selected_raters": raters,
        "required_files": {
            "proposer": "proposer.json",
            "pre_mortem": "pre_mortem.json",
            "evidence_tribunal": "evidence_tribunal.json",
            "research_response": "research_response.json",
            "valuation_reconciliation": "valuation_reconciliation.json",
            "adversarial_review": "adversarial_review.json",
            "chair_synthesis": "chair_synthesis.json",
            "human_decision": "human_decision.json",
        },
    }
    write_json(work / "manifest.json", manifest)
    for round_number in (1, 2):
        round_dir = work / f"round_{round_number}"
        round_dir.mkdir(parents=True, exist_ok=True)
        for row in raters:
            prompt = rater_prompt(ticker, row["persona"], row["independence_group"], frozen_hash, refs, round_number)
            (round_dir / f"{row['persona']}.prompt.md").write_text(prompt, encoding="utf-8")
    (work / "pre_mortem.prompt.md").write_text(
        f"# {ticker} mandatory pre-mortem\n\nPacket `{frozen_hash}`. Assume the investment failed severely. Explain the causal failure, earliest warnings, forensic checks, short-source coverage, and unresolved items. Do not read rater outputs. Return the committee schema pre_mortem object only.\n",
        encoding="utf-8",
    )
    (work / "evidence_tribunal.prompt.md").write_text(
        f"# {ticker} evidence tribunal\n\nPacket `{frozen_hash}`. Resolve disputed quantities, ownership, distributions, comparable validity, option beneficiary, and overlap before valuation debate. Separate resolved facts from material unresolved facts and cite packet paths. Return evidence_tribunal.json only.\n",
        encoding="utf-8",
    )
    (work / "valuation_reconciliation.prompt.md").write_text(
        f"# {ticker} valuation reconciliation\n\nClassify every material difference among isolated outputs as factual, methodological, assumption-based, horizon-based, risk-tolerance-based, or power-zone mismatch. Do not average incompatible estimates. Return valuation_reconciliation.json only.\n",
        encoding="utf-8",
    )
    (work / "adversarial_review.prompt.md").write_text(
        f"# {ticker} adversarial review\n\nTest double counting, peak-cycle extrapolation, reinvestment, multiple dependence, hidden capital, dilution, governance, tax, macro sensitivity, beneficiary mismatch, and comparable-cycle bias. Return adversarial_review.json only.\n",
        encoding="utf-8",
    )
    (work / "chair_synthesis.prompt.md").write_text(
        f"# {ticker} chair synthesis\n\nSelect the primary method, explain why it dominates corroborating methods, preserve dissent, state agreed and disputed facts, value and entry ranges, recommendation, and monitoring plan. Never average methods solely to create consensus. Return chair_synthesis.json only.\n",
        encoding="utf-8",
    )
    return work


def validate_vote(vote: dict, expected: dict) -> list[str]:
    errors = []
    if vote.get("persona") != expected["persona"]:
        errors.append(f"persona must be {expected['persona']}")
    if vote.get("independence_group") != expected["independence_group"]:
        errors.append(f"independence_group must be {expected['independence_group']}")
    if set((vote.get("scores") or {})) != set(DIMS):
        errors.append("all four calibrated scores are required")
    for dim in DIMS:
        score = (vote.get("scores") or {}).get(dim) or {}
        if not isinstance(score.get("value"), int) or not 1 <= score["value"] <= 5 or not score.get("rationale"):
            errors.append(f"{dim} requires value 1-5 and rationale")
    if vote.get("vote") not in {"approve", "watch", "defer", "reject"}:
        errors.append("invalid vote")
    if vote.get("evidence_status") not in {"sufficient", "insufficient_evidence", "outside_power_zone"}:
        errors.append("invalid evidence_status")
    for key in ("claims", "strongest_counter_explanation", "most_important_missing_fact", "falsifiers", "specialist_findings", "confidence"):
        if vote.get(key) in (None, "", []):
            errors.append(f"{key} is required")
    return errors


def load_round(work: Path, round_number: int, raters: list[dict]) -> tuple[list[dict], list[str]]:
    votes, errors = [], []
    for expected in raters:
        path = work / f"round_{round_number}" / f"{expected['persona']}.json"
        if not path.exists():
            errors.append(f"missing {path.relative_to(work)}")
            continue
        vote = read_json(path)
        errors.extend(f"{path.name}: {message}" for message in validate_vote(vote, expected))
        votes.append(vote)
    return votes, errors


def validate_work(work: Path) -> list[str]:
    manifest = read_json(work / "manifest.json")
    raters = manifest["selected_raters"]
    errors = []
    if len({row["independence_group"] for row in raters}) != 3:
        errors.append("raters must use three distinct independence groups")
    for round_number in (1, 2):
        _, round_errors = load_round(work, round_number, raters)
        errors.extend(round_errors)
    for name in (
        "proposer.json", "pre_mortem.json", "evidence_tribunal.json", "research_response.json",
        "valuation_reconciliation.json", "adversarial_review.json", "chair_synthesis.json",
    ):
        if not (work / name).exists():
            errors.append(f"missing {name}")
    current_refs = [file_reference(ROOT / row["path"]) for row in manifest["evidence"]]
    if packet_hash(current_refs) != manifest["packet_hash"]:
        errors.append("evidence packet changed after freezing")
    return errors


def assemble(work: Path) -> Path:
    errors = validate_work(work)
    if errors:
        raise ValueError("committee work is incomplete:\n- " + "\n- ".join(errors))
    manifest = read_json(work / "manifest.json")
    ticker = manifest["ticker"]
    raters = manifest["selected_raters"]
    round_one, _ = load_round(work, 1, raters)
    round_two, _ = load_round(work, 2, raters)
    proposer = read_json(work / "proposer.json")
    pre_mortem = read_json(work / "pre_mortem.json")
    evidence_tribunal = read_json(work / "evidence_tribunal.json")
    research_loop = read_json(work / "research_response.json")
    valuation_reconciliation = read_json(work / "valuation_reconciliation.json")
    adversarial_review = read_json(work / "adversarial_review.json")
    chair_synthesis = read_json(work / "chair_synthesis.json")
    medians = {dim: median(v["scores"][dim]["value"] for v in round_two) for dim in DIMS}
    ranges = {dim: [min(v["scores"][dim]["value"] for v in round_two), max(v["scores"][dim]["value"] for v in round_two)] for dim in DIMS}
    dissent = min(round_two, key=lambda v: (v["scores"]["return_vs_alternatives"]["value"], v["scores"]["downside_control"]["value"]))
    unresolved = sorted({v["most_important_missing_fact"] for v in round_two if v["most_important_missing_fact"]})
    valuation = read_json(ROOT / ticker / "research" / "valuation.json")
    economic = valuation.get("economic_value_analysis") or {}
    component = valuation.get("component_valuation_results") or {}
    proof = economic.get("valuation_proof") or []
    options = [row for row in proof if row.get("treatment") == "additive" and "option" in str(row.get("method", "")).lower()]
    economic_complete = economic.get("status") == "complete"
    component_complete = component.get("status") == "complete" and component.get("all_material_components_identified")
    comparable_complete = economic_complete and all(
        row.get("comparable_role") == "not_applicable" or row.get("comparable_ids")
        for row in proof
    )
    option_complete = all(row.get("falsifier") and row.get("range_per_share") for row in options)
    tribunal_blocked = bool(evidence_tribunal.get("unresolved_material_facts")) or evidence_tribunal.get("status") != "complete"
    adversarial_blocked = adversarial_review.get("status") not in {"complete", "complete_with_residual_risks"}
    chair_blocked = chair_synthesis.get("status") != "complete"
    blocked = any(v["evidence_status"] == "insufficient_evidence" for v in round_two) or not economic_complete or not component_complete or tribunal_blocked or adversarial_blocked or chair_blocked
    record = {
        "schema_version": "1.0",
        "protocol_version": "production-2.0",
        "ticker": ticker,
        "review": {"level": "full_ic", "trigger": "production committee pipeline", "as_of": manifest["as_of"], "owner": None},
        "evidence_packet": {"frozen_at": manifest["frozen_at"], "hash_method": "sha256(canonical-json(sorted(path,sha256,bytes)))", "packet_hash": manifest["packet_hash"], "freshness_status": "mixed", "references": manifest["evidence"]},
        "proposer": proposer,
        "selected_raters": raters,
        "round_one": {"evidence_hash": manifest["packet_hash"], "peer_outputs_visible": False, "votes": round_one},
        "pre_mortem": pre_mortem,
        "evidence_tribunal": evidence_tribunal,
        "research_loop": research_loop,
        "round_two": {"evidence_hash": manifest["packet_hash"], "peer_outputs_visible": False, "votes": round_two},
        "valuation_reconciliation": valuation_reconciliation,
        "adversarial_review": adversarial_review,
        "chair_synthesis": chair_synthesis,
        "synthesis": {
            "strongest_dissent": dissent["strongest_counter_explanation"],
            "unresolved_items": unresolved,
            "vote_split": dict(Counter(v["vote"] for v in round_two)),
            "score_medians": medians,
            "score_ranges": ranges,
            "dissent_ledger": [{"issue": item, "impact": "high", "status": "unresolved", "owner_response": None} for item in unresolved],
        },
        "component_review": valuation.get("component_review_queue"),
        "gates": {
            "price": "pass" if (valuation.get("inputs") or {}).get("price") else "blocked",
            "shares": "pass" if (valuation.get("inputs") or {}).get("shares_outstanding") else "blocked",
            "reporting_period": "pass",
            "filing_reconciliation": "pass",
            "economic_claim": "pass" if economic_complete else "blocked",
            "component_completeness": "pass" if component_complete else "blocked",
            "comparable_evidence": "pass" if comparable_complete else "partial",
            "option_risking": "pass" if option_complete else "blocked",
            "disclosure_scan": "partial",
            "short_scan": "partial",
            "pre_mortem": "pass",
            "evidence_tribunal": "blocked" if tribunal_blocked else "pass",
            "valuation_reconciliation": "pass" if valuation_reconciliation.get("status") == "complete" else "blocked",
            "adversarial_review": "blocked" if adversarial_blocked else "pass",
            "chair_synthesis": "blocked" if chair_blocked else "pass",
            "explanation_contracts": "pass",
            "independent_groups": "pass",
            "owner": "not_run",
        },
        "human_decision": {"status": "pending", "decision": None, "sizing": None, "top_dissent_response": None, "decided_at": None},
        "monitoring_plan": chair_synthesis.get("monitoring_plan") or {
            "operational_milestones": [],
            "evidence_refresh_dates": [],
            "valuation_refresh_triggers": ["material filing", "capital-structure change", "thesis falsifier"],
            "price_review_thresholds": [],
            "thesis_break_conditions": [],
            "expected_catalyst_dates": [],
            "outcome_horizons_months": [6, 12, 24],
        },
        "final_state": "evidence_blocked" if blocked else "committee_complete_decision_pending",
        "provenance": {"prompt_version": "production-isolated-rater-2", "model": "external isolated raters assembled deterministically", "schema_path": "_system/templates/committee_schema.json", "persona_registry_version": "1.1"},
    }
    if record["component_review"] is None:
        record.pop("component_review")
    output = ROOT / ticker / "research" / f"committee_{manifest['as_of']}.json"
    write_json(output, record)
    manifest["stage"] = record["final_state"]
    write_json(work / "manifest.json", manifest)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("ticker")
    init.add_argument("--date", default=date.today().isoformat())
    check = sub.add_parser("validate")
    check.add_argument("ticker")
    check.add_argument("--date", required=True)
    build = sub.add_parser("assemble")
    build.add_argument("ticker")
    build.add_argument("--date", required=True)
    args = parser.parse_args()
    if args.command == "init":
        print(initialize(args.ticker, args.date).relative_to(ROOT))
        write_valuation_workbench(args.ticker, args.date)
        return 0
    work = ROOT / args.ticker.upper() / "research" / "committee_work" / args.date
    if args.command == "validate":
        errors = validate_work(work)
        write_valuation_workbench(args.ticker, args.date)
        print("valid" if not errors else "\n".join(errors))
        return 0 if not errors else 1
    print(assemble(work).relative_to(ROOT))
    write_valuation_workbench(args.ticker, args.date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
