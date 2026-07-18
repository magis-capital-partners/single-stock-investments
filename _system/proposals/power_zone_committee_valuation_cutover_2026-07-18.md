# Power Zone valuation and Investment Committee cutover

**Date:** 2026-07-18
**Status:** implemented on `codex/power-zone-committee-cutover`
**Objective:** replace the deprecated Marvin-centered valuation and stance process with a portfolio-wide, evidence-gated system in which economic Power Zones select the fitting valuation method and three independent committee reviewers, while the human owner retains the capital decision.

## Executive decision

The repository has already implemented most of the new primitives, but it has not changed the production authority chain. The old path still computes a Lawrence/Marvin return, proposes a stance, publishes it into classification and portfolio features, and only then adds the economic-value contract and workbench as secondary artifacts.

The cutover should make this the only authoritative sequence:

```text
primary evidence
  -> economic ownership map
  -> Power Zone method route
  -> method-specific component valuation
  -> universal decision contract
  -> evidence/readiness gate
  -> hurdle-rate entry pricing
  -> frozen committee packet
  -> three isolated Power Zone reviews + outside pre-mortem
  -> evidence tribunal and one research response
  -> blind second round
  -> dissent-first chair synthesis
  -> human decision
  -> outcome ledger and calibration
```

Marvin remains useful as a research coordinator: acquire documents, extract facts, maintain evidence, refresh the narrative, and answer committee questions. Marvin must stop being the valuation authority, stance setter, committee, and final decision maker.

## What the prior plan was

The intended methodology is already stated across the economic-value protocol, Power Zone configuration, committee plan, valuation evidence worker, and ls-algo orchestrator:

1. Define the exact economic claim owned by one fully diluted share.
2. Inventory and value every material operating asset, financial asset, option, liability, reserve, and financing claim exactly once.
3. Route the security to a valuation method by its economic mechanism, not by a universal owner-cash template.
4. Use Power Zones to choose the relevant specialist methods and silence irrelevant specialists.
5. Require a complete universal valuation contract and explicit acceptance tests before calling a valuation decision-grade.
6. Price the decision-grade range at 10%, 12%, 15%, and 20% hurdle rates.
7. Trigger a full committee only for a new position, material thesis change, decision-critical conflict, live material exposure, or a price crossing the approved hurdle.
8. Freeze one evidence packet and send it to three isolated reviewers with distinct error models, plus a separate pre-mortem.
9. Resolve factual disputes before debating valuation, permit abstention, preserve dissent, and never average incompatible methods to manufacture consensus.
10. Stop at a named human owner's decision and use later total-return outcomes only for slow, minimum-sample calibration.

The 2026-07-17 ls-algo plan attempted to wire:

```text
Power Zones -> method routing -> workbench -> entry pricing -> gated IC -> dashboard
```

It correctly made the method route and committee seating the same object and stopped automation at `owner_decision_pending`. The limitation was scope: it was built around a temporary `ls_algo_underlying` registry sleeve rather than the canonical research universe and normal Marvin refresh path.

## Current production state

Repository audit on 2026-07-18:

| Surface | Current state | Consequence |
|---|---:|---|
| Registry holdings | 649 | Canonical universe |
| Research directories | 652 | Some folder/registry drift remains |
| `valuation.json` | 190 | 459 registry names have no valuation file |
| Old `method: full` | 131 of 190 | Owner-cash/Lawrence remains the dominant engine |
| Valuations without a Power Zone method route | 142 of 190 | New routing has not been backfilled |
| Power Zone output | 649 tickers; 42 with at least one zone | Mostly a display/filter artifact today |
| `valuation_workbench.json` | 42 | New decision surface has limited coverage |
| Workbench decision status | 41 evidence-blocked; 1 decision-grade | BMNR is the only current decision-grade workbench |
| Committee records | 9 | All are owner-decision-pending pilot records |
| Pricing analyses | 4 | Entry-pricing coverage is sparse |
| Current `ls_algo_underlying` registry members | 0 | The shipped nightly orchestrator processes no tickers |

The ls-algo dry run confirms the disconnect: zero sleeve tickers, zero workbenches, zero pricing builds, and zero committee gates.

## How the current Marvin path conflicts with the plan

| Intended authority | Current behavior | Conflict |
|---|---|---|
| Power Zone selects the economic method | `marvin_valuation.py` starts from `method: full`, `scenario`, or `yield_curve`; 131 files use `full` | The old model chooses the answer before the economic route is authoritative |
| Every material claim is valued exactly once | The script can infer a minimal operating-only component from legacy scenarios | A partial owner-cash model can still produce an IRR and stance even when the complete valuation is evidence-blocked |
| Contract/readiness drives publication | `implied_return` and `stance_proposal` are written before and independently of workbench readiness | A legacy return can look actionable while the new contract says evidence-blocked |
| Power Zones are one source of truth | `power_zones.json`, `valuation_method_router.py`, `personas.json`, and followup `method_profile` fields encode overlapping but different taxonomies | Reviewer selection, UI zones, and valuation routing can disagree |
| Power Zones choose reviewers, not the answer | Persona lenses transform the same Marvin valuation and then calculate a relevance-weighted mean | This is correlated re-expression of one estimate, not independent wisdom of crowds |
| Three isolated reviewers test a frozen packet | `investment_committee_pipeline.py` initializes prompts but no production workflow runs the independent tasks, research loop, round two, and assembly | Committee files can be initialized without a reliable path to completion |
| Evidence is complete before committee freeze | `marvin_cloud_refresh.py` builds the workbench before optionality refresh, the completed deep dive, Milly, and final evidence checks | The decision artifact is built from an intermediate state |
| Committee/human decision is the stance authority | Classification, deep-dive prose, dashboard summaries, and Darwin features read `implied_return`, `stance_proposal`, `approved_stance`, and lens consensus | Downstream systems bypass committee state and the human decision record |
| Portfolio-wide routing | Nightly orchestration targets only `ls_algo_underlying` | The current registry contains zero members of that sleeve, making the orchestrator a no-op |
| Slow, attributable calibration | Power Zone display scores blend coarse classification matches with letter-overlap calibration | Popularity/holdings overlap is not evidence that a reviewer accurately valued this economic mechanism |

### The central conceptual conflict

The old system treats Marvin's base IRR as the thesis and lets other layers annotate it. The new system treats the complete economic-value contract as the thesis candidate and uses independent specialists to attack it before a human adopts it.

That is not a cosmetic rename. It is a reversal of authority:

```text
OLD: Marvin estimate -> stance -> lenses/overlays -> optional committee
NEW: evidence -> routed methods -> contract -> independent committee -> human stance
```

## Target operating model

### 1. One canonical Power Zone route

Create one versioned route document per ticker, for example `research/valuation_route.json`, generated from one canonical registry.

Required output:

- security and as-of date;
- economic profile and applicability score;
- routing facts and the source of each fact;
- primary valuation method;
- no more than two corroborating methods;
- required evidence and unresolved applicability tests;
- primary committee specialists;
- cross-check specialists;
- silent specialists;
- three selected independence groups;
- explicit owner override, if any;
- configuration version and deterministic input hash.

The canonical Power Zone registry should combine the useful parts of:

- `_system/frameworks/power_zones.json`;
- `_system/scripts/valuation_method_router.py`;
- `_system/lenses/personas.json`;
- profile fields in `_system/reference/valuation_followups.json`.

Keep two distinct concepts inside the same registry:

1. **Economic valuation profiles** decide which model fits the security.
2. **Specialist review zones** decide who is qualified to test the model.

Do not equate a famous-investor persona with a valuation formula. A specialist may be a primary method owner, a corroborating reviewer, a risk reviewer, or silent.

### 2. A canonical decision contract, not a canonical mega-model

Every specialized model must emit the existing universal contract:

- economic ownership map;
- additive and embedded components;
- low/base/high value per share;
- facts, estimates, and judgments separated;
- evidence tier and source for each material input;
- probability, timing, remaining capital, dilution, tax, and senior claims;
- overlap keys and double-counting checks;
- causal scenarios and reverse expectations;
- falsifiers and refresh triggers;
- price, fully diluted shares, market cap, and enterprise-value reconciliation;
- decision status and evidence blockers.

The model library should use small modules for:

- scarce assets, royalties, and optionality;
- quality and reinvestment;
- capital-cycle and mid-cycle economics;
- credit, funding, and normalized financial returns;
- catalyst-backed asset value;
- predictable or contracted cash flow;
- binary milestone assets.

Lawrence owner-cash IRR remains a valid specialist method inside quality/predictable-cash-flow Power Zones. It must not remain the universal default or the stance authority.

### 3. Wisdom of crowds without false precision

The crowd should diversify error models, not multiply prose around one spreadsheet.

Rules:

- Three reviewers must have distinct independence groups and isolated contexts.
- Reviewers receive the same frozen evidence packet and route, not Marvin's final recommendation.
- Reviewers may abstain for insufficient evidence or an out-of-zone case.
- Each reviewer returns: factual disputes, component challenges, commensurable low/base/high estimates, causal assumptions, score dimensions, recommendation, confidence, missing fact, and falsifiers.
- The evidence tribunal resolves facts before round two.
- A single targeted research response may answer the highest-value missing facts.
- Round two remains blind to other votes; it may see the tribunal and research response.
- Numeric aggregation is allowed only for estimates with the same economic claim, method, unit, and horizon. Use a median and show the full range.
- Incompatible methods are reconciled, not averaged. The chair selects a primary method, explains why it dominates, and preserves alternative ranges and dissent.
- Median committee scores and vote splits summarize agreement; they do not create a buy order.
- The human owner records the decision, sizing, top-dissent response, and review date.

### 4. Clear responsibilities

| Role | Owns | Must not own |
|---|---|---|
| Research coordinator (current Marvin capabilities) | document acquisition, extraction, evidence ledger, economic-claim inventory, narrative, committee research response | authoritative route, final valuation, stance, sizing |
| Power Zone router | method applicability, required tests, reviewer eligibility, silent methods | valuation number, recommendation |
| Specialized valuation modules | reproducible component ranges and universal contract | evidence acceptance outside their contract |
| Independent reviewers | error detection, alternative assumptions, abstention, scored recommendation | editing the frozen packet or seeing peer votes |
| Evidence tribunal | fact reconciliation and unresolved-fact gate | selecting a valuation for consensus |
| Chair | method reconciliation, dissent-first synthesis, monitoring plan | owner decision or position size |
| Human owner | approve/watch/reject, sizing, dissent response, overrides | silent mutation of evidence or model history |

## Canonical artifacts and authority

| Artifact | Purpose | Authority |
|---|---|---|
| `evidence_manifest.json` | Frozen, hashed primary and approved secondary evidence | Evidence scope |
| `valuation_route.json` | Power Zone profile, methods, raters, silent specialists | Method/reviewer route |
| `valuation_contract.json` | Complete universal economic-value decision contract | Valuation and readiness |
| `pricing_analysis.json` | Hurdle-rate entry prices derived from the contract | Price trigger only |
| `committee_work/{date}/...` | Isolated stage outputs and provenance | Committee process |
| `committee_{date}.json` | Assembled dissent-first record | Committee recommendation |
| `human_decision.json` | Owner decision, sizing, dissent response, expiry | Capital decision |
| `valuation_workbench.json` | Read-only projection of the above artifacts | UI serving view |
| `valuation_history/` and outcome ledger | Point-in-time versions and matured results | Attribution/calibration |

`valuation.json` becomes a migration input and compatibility envelope. It must cease to be the final decision authority.

## New production pipeline

Replace the valuation portion of `marvin_cloud_refresh.py` with a portfolio-neutral orchestrator, tentatively `run_security_decision_pipeline.py`:

```text
Phase 1 - research refresh
  documents -> filings/transcripts -> market inputs -> third-party scan

Phase 2 - evidence close
  economic claim -> component inventory -> evidence reconciliation
  -> adversarial evidence check -> final evidence manifest

Phase 3 - route and value
  canonical Power Zone router -> specialized model(s)
  -> universal contract -> workbench/readiness

Phase 4 - price and committee gate
  decision-grade contract -> hurdle prices
  -> trigger check -> freeze packet

Phase 5 - committee
  proposer -> three blind reviews + pre-mortem
  -> tribunal -> one research response -> blind round two
  -> valuation reconciliation -> adversarial review -> chair

Phase 6 - human and serving
  owner decision pending -> dashboard/Darwin serving projection
  -> later outcome measurement and calibration
```

Important ordering changes:

1. Do not build the final workbench before optionality, primary-evidence, and adversarial checks finish.
2. Do not publish a stance from a legacy IRR before readiness and committee state are known.
3. Re-freeze the committee packet whenever any hashed evidence, route, or contract input changes.
4. Routine document refreshes may stop after Phase 3 when there is no material decision trigger.

## Trigger and gate policy

### Lightweight path for every researched security

Every material refresh should run evidence reconciliation, Power Zone routing, the applicable valuation module, the universal contract, history capture, and the workbench.

### Full committee triggers

Initialize a committee only when all readiness gates pass and at least one trigger exists:

- proposed new position;
- live material portfolio or risk-book exposure;
- material thesis or capital-structure change;
- decision-critical evidence conflict;
- base entry price crosses the owner's hurdle;
- existing human decision expires;
- owner explicitly requests review.

### Hard committee gates

- route status is reviewed or deterministically high-confidence;
- all material components are represented exactly once;
- no critical evidence acceptance test remains open;
- universal contract is `decision_grade`;
- price and fully diluted share count are current;
- deep dive and adversarial evidence review are complete;
- no frozen-packet mutation;
- three independent reviewer groups can be seated.

If a trigger fires while evidence-blocked, create a prioritized evidence task, not a committee vote.

## Migration plan

### Phase 0 - freeze authority and add observability

1. Document the authority hierarchy in `investment_process.md`, `framework_governance.md`, the cloud runbook, and agent instructions.
2. Add a repository-wide deprecation manifest for legacy producers and consumers.
3. Add dashboard counters for legacy-only, routed, evidence-blocked, decision-grade, committee-pending, and human-decided.
4. Add CI checks that fail if a new file promotes legacy stance on an evidence-blocked security.
5. Preserve current files; make no destructive migration yet.

**Exit gate:** every decision surface can identify its source artifact and engine version.

### Phase 1 - unify Power Zones

1. Create one canonical profile/specialist registry and one `power_zone_router.py`.
2. Make `build_power_zones.py`, valuation routing, committee seating, and the dashboard read the same route output.
3. Remove duplicate rule calculations from `persona_lens_common.py` and `valuation_method_router.py`; keep compatibility wrappers temporarily.
4. Add route tests for one gold case per economic profile plus exclusion, abstention, and three-group seatability tests.
5. Tighten overly broad zones: require mechanism-specific inputs, not just two coarse classification matches.

**Exit gate:** the displayed Power Zone, primary model, committee raters, and silent specialists are identical for every routed ticker.

### Phase 2 - establish the canonical contract writer

1. Move reusable calculations out of `marvin_valuation.py` into the specialized method modules.
2. Build a new contract writer that consumes evidence plus the reviewed route and writes `valuation_contract.json` directly.
3. Treat inferred minimal/legacy components as `legacy_reference`, always evidence-blocked and never stance-capable.
4. Add schema checks that every material component has evidence, range, overlap control, falsifier, and risk/timing treatment where applicable.
5. Capture immutable valuation history before every write.

**Exit gate:** the validation cohort produces the same or better ranges without reading `results_lawrence_legacy` as an authority.

### Phase 3 - complete real committee orchestration

1. Add a workflow/action that runs each committee stage as a separate task with a distinct context and recorded run provenance.
2. Validate packet hash, route hash, prompt version, model/run ID, independence group, and prohibited peer-output access.
3. Implement stage transitions rather than prompt-file existence alone.
4. Block chair synthesis until the tribunal, research response, round two, reconciliation, and adversarial review all validate.
5. Write `human_decision.json` through an owner-only path; never infer it from an agent recommendation.

**Exit gate:** one end-to-end canary goes from decision-grade contract to `owner_decision_pending` with verifiable isolation and no manual file fabrication.

### Phase 4 - shadow mode on the current high-value cohort

Run the old and new systems side by side for:

1. the nine validation-cohort names;
2. BMNR, the sole current decision-grade workbench;
3. current core/hold names;
4. material live portfolio/risk-book names;
5. at least one gold case from each Power Zone profile.

Produce a comparison ledger with:

- old Marvin IRR and stance;
- new contract range and return range;
- route and committee recommendation;
- evidence/readiness difference;
- source of divergence: missing component, method, assumptions, horizon, financing, or risk tolerance;
- owner resolution.

**Exit gate:** no unexplained material divergence and at least one completed canary per profile.

### Phase 5 - switch readers before deleting writers

Change consumers in this order:

1. `build_dashboard_data.py` and dashboard/detail views;
2. `sync_classification.py`;
3. `refresh_deep_dive_v2.py` and narrative templates;
4. Darwin feature extraction and eligibility gates;
5. target-weight policies and labels;
6. research lint, cross-check, and quality gates.

Reader precedence:

```text
human_decision.json
  > latest valid committee record
  > decision-grade valuation_contract.json
  > evidence-blocked/provisional contract
  > legacy reference, visibly non-actionable
```

Rename `ira_marvin` to an engine-neutral policy such as `ira_research_committee`. Until the new decision exists, a name must be ineligible or use an explicit grandfathered human decision; it must not silently fall back to a fresh Marvin stance.

**Exit gate:** no production decision, stance, eligibility, or sizing reader depends on `implied_return`, `stance_proposal`, `results_lawrence_legacy`, or `lens_consensus`.

### Phase 6 - switch the normal refresh workflow

1. Make the new portfolio-neutral orchestrator the sole valuation close in cloud and local refreshes.
2. Update daily refresh, onboard, batch refresh, Make targets, README, and agent instructions.
3. Keep the current Marvin entry point as a thin research-refresh compatibility wrapper for one release cycle.
4. Repair the universe source: target registry holdings or explicit rollout/portfolio queues, not the missing `ls_algo_underlying` sleeve.
5. Run routing for all registry holdings; run full valuation and IC only by priority and gates.

**Exit gate:** every new or materially refreshed analysis uses the new sequence without a manual side path.

### Phase 7 - deprecate and remove the old method

1. Stop writing fresh `results_lawrence_legacy`, `stance_proposal`, and persona-blended decision fields.
2. Move legacy values into a namespaced, read-only `legacy_reference` block during archival migration.
3. Delete legacy reader fallbacks after two clean production cycles.
4. Rename workflows and UI labels that imply Marvin is the decision engine.
5. Delete or archive `persona_consensus.py` as a decision mechanism; retain specialist insights only as non-authoritative context.
6. Convert `marvin_valuation.py` to an offline migration tool, then remove it after all required historical snapshots are preserved.
7. Add a CI forbidden-reference rule so deprecated fields cannot re-enter production code.

**Exit gate:** a repository search finds deprecated fields only in archived data, migration code, and explicit compatibility tests.

### Phase 8 - portfolio rollout and calibration

Roll out by decision value, not alphabetical completeness:

1. live material positions and proposed new purchases;
2. core/hold names and the current validation cohort;
3. current 42 Power Zone names;
4. remaining 190 names with valuations;
5. remaining registry names when research demand or a material trigger arises.

Do not run a full committee on all 649 names. Route all names, maintain lightweight readiness, and spend committee budget only where a capital decision is live.

Calibration rules:

- record split- and dividend-aware 6-, 12-, and 24-month outcomes;
- attribute outcomes to the route, method, reviewer, and decision version actually used;
- exclude incomplete, price-only, or post-hoc records;
- require at least 20 attributable matured outcomes before reviewing a specialist's relevance inside a Power Zone;
- make weight changes human-reviewed and versioned;
- never automatically reward bullishness or penalize correct abstention.

## Legacy deprecation map

| Legacy surface | Transitional treatment | Final state |
|---|---|---|
| `marvin_valuation.py` | Calculator compatibility and history migration only | Removed from production refresh |
| `implied_return` | Show as `legacy_reference` in shadow comparisons | Not read by production decisions |
| `stance_proposal` | Freeze existing values; no new authority | Replaced by committee recommendation + human decision |
| `approved_stance` in `valuation.json` | Migrate with provenance | Replaced by `human_decision.json` |
| `results_lawrence_legacy` | Preserve historical snapshots | Archive-only |
| `lens_consensus` valuation blend | Insights-only, clearly correlated | Removed as a decision signal |
| `persona_lens.py` verdicts | Optional specialist context | Not an IC substitute |
| `valuation_method_router.py` | Wrapper over canonical router | Removed after callers migrate |
| `build_power_zones.py` local scoring | Projection from canonical routes | No separate routing logic |
| `run_ls_algo_valuation_pipeline.py` | Generalize or retire | Replaced by portfolio-neutral orchestrator |
| `ira_marvin` | Versioned alias during shadow mode | `ira_research_committee` or equivalent |
| “Marvin conflicts” / “Marvin + Darwin” UI | Compatibility labels | “Research/IC conflicts” and engine-neutral labels |

## Tests and controls

### Unit and schema tests

- deterministic Power Zone route from frozen inputs;
- required mechanism-specific inputs and exclusion rules;
- three distinct committee independence groups or explicit block;
- component completeness and overlap uniqueness;
- option probability/timing/capital/dilution treatment;
- no decision-grade state with an open critical gap;
- no stance from a legacy-only or evidence-blocked record;
- commensurable-estimate aggregation only;
- packet and route immutability across committee stages;
- human-decision ownership and expiry.

### Integration tests

- new security from onboard through workbench;
- evidence-blocked trigger creates a research task, not a committee;
- decision-grade price crossing initializes one committee exactly once;
- changed evidence invalidates all downstream committee work;
- isolated round execution and validated assembly;
- dashboard, classification, narrative, and Darwin all resolve the same authority;
- point-in-time backtest reads the contract/decision version available at that date.

### CI removal gates

Fail CI when production code:

- invokes `marvin_valuation.py` outside an approved migration path;
- reads deprecated stance/IRR fields for a decision;
- computes a second Power Zone route;
- publishes decision-grade with incomplete ownership coverage;
- initializes a committee without a decision-grade contract;
- writes a human decision from an agent workflow;
- assembles committee work without valid isolation provenance.

## Dashboard and user experience

Lead with:

1. readiness: missing, legacy-only, provisional, evidence-blocked, decision-grade, committee-open, owner-decision-pending, decided, expired;
2. price versus the decision-grade low/base/high range;
3. primary Power Zone and method;
4. material components and open acceptance tests;
5. committee state, raters, vote split, strongest dissent, and unresolved facts;
6. human decision, sizing, dissent response, and next review date;
7. old Marvin IRR only inside a collapsed migration-comparison section until removed.

The dashboard must never show a green stance or allocation eligibility when the authoritative contract is evidence-blocked.

## Success criteria

The migration is complete when:

- 100% of researched/priority securities have one deterministic, versioned Power Zone route;
- every displayed valuation range comes from a universal contract with complete economic-claim coverage;
- the Power Zone shown in the UI is the same object that chose the method and committee seats;
- all full committees have verifiable frozen-packet isolation and three independent error models;
- human decisions are stored separately from agent recommendations;
- no production reader uses deprecated Marvin or persona-consensus fields for stance, eligibility, or sizing;
- the normal cloud/local refresh invokes only the new orchestrator;
- evidence-blocked names cannot become allocation inputs without an explicit, still-valid grandfathered human decision;
- old methodology code and labels are removed after the shadow/cutover gates pass;
- outcome calibration remains descriptive until minimum sample sizes are met.

## Recommended first implementation slice

Do not begin with all 649 names. Prove the new authority chain end to end:

1. unify Power Zone routing and committee seating;
2. make BMNR the first decision-grade canary;
3. run one contrasting evidence-blocked cohort name through gap closure;
4. complete one real isolated committee and owner-decision handoff;
5. switch dashboard and classification readers for those canaries;
6. shadow the remaining validation cohort;
7. then make the new orchestrator the default for all material refreshes.

This slice tests the hard part: not the valuation arithmetic, but whether every system agrees on who has authority to route, value, review, decide, and later learn.
