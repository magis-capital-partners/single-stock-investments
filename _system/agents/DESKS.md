# Magis desks

Seven desks read the same dashboard and file through the same two channels. This file is
the mandate; the prompts (`_system/prompts/grok_scan_agents.md`,
`_system/prompts/grok_stahl_agent.md`) are the souls; the desk lines in
`_system/memory-hub/research-equity/CONTEXT.md` are the one-line summaries. Proposal:
`_system/proposals/one_hub_for_humans_and_bots_2026-10-11.md`.

Shared rules. Read a file's stamp (`generated_at`, `build_time`, `generated`, `as_of`,
`meta.updated`) before its contents, and record it in `inputs_read`. Read
`_system/portfolio/registry.json` fresh; never hardcode tickers. Dashboard first, then the
filing the row points at, then the web to fill a name or an exhibit, labelled as web. A
headline is never a term. Ranked hits only, at most twelve, best first; say nothing when
nothing is new. Fact and inference stay separate. No price target, no stance, no position,
no base IRR, no fraud tag. `owner` names whose queue a brief lands in; either owner's bot
may file any desk, and the owner below is who adjudicates it.

Output, every desk, every run: `_system/data/desk_briefs/<desk>/<YYYY-MM-DD>.json` per
`_system/data/desk_briefs/README.md`, on a `grok/<desk>/<YYYY-MM-DD>-<slug>` branch, by
pull request, with `python _system/scripts/check_desk_briefs.py` green; plus at most three
`[PROPOSED]` lessons (Evidence, Seen, Harmful, Scope, Review after) in
`_system/memory-hub/research-equity/daily/<YYYY-MM-DD>.md`. The chat room gets one line
per hit (ticker and the one number) that points at the brief. Chat is never the record.

## Special Situations (`special_situations`)

- **Owner:** both. Michael's archived `Special-Situations` repo folds into this desk.
- **Reads:** `dashboard/data/portfolio_news.json` (`build_time`; categories m_and_a, spinoff, restructuring, capital_raise, buyback, dividend_policy, corporate_action; confidence >= 0.8), `dashboard/data/warrants.json` (`generated_at`), `dashboard/data/activist_feed.json` (`generated_at`; deal paper only: SC TO-T, SC TO-C, DEFM14A, PREM14A, S-4, 425, 8-K 1.01/2.01), `dashboard/data/document_catalog.json` (`generated_at`), `dashboard/data/special_situations.json` (`generated_at`; ranked rows, discovery, the forced_sellers lane), `dashboard/data/separations.json` (`generated_at`; filed terms, spread, flows, `odd_lot_alerts`, `discovery_events`), `_system/reference/cvr/cvr_universe.json`, `_system/data/cvr_agent_queue.json` (209 stubs awaiting terms; read, never size` (`as_of`), `dashboard/data/nol_382_facts.json` (`generated_at`; Section 355 and ownership-change language on a spin), `_system/portfolio/registry.json` (`meta.updated`).
- **Screens:** spin-offs and orphan stocks (ratio, when-issued window, who must sell, insider equity); split-offs and exchange offers (discount, upper limit, odd-lot priority, proration, settlement); CVRs and merger securities (milestone, cap, expiry, trades or not); no-vote deals and topping bids that lost; warrant terms (strike, expiry, cashless, reset); capital-structure shock that creates a security or a forced seller (recap stub, rights offering, odd-lot tender, special distribution); post-reorganization equity.
- **Output:** the brief (lane ids `spinoffs`, `split_offs`, `mergers`, `warrants`, `restructurings`, `forced_sellers`) and the lessons, as above. `screens_empty` names the screens that returned nothing.
- **Never:** a price target; a quote from Greenblatt (the book is the checklist, in your own words); a rank without a dated end or a forced seller; a spread without a filed formula; a stub, spin or warrant left to another desk; an edit to any `MEMORY.md`; a new hub.

## Activism (`activism`)

- **Owner:** both.
- **Reads:** `dashboard/data/activist_feed.json` (`generated_at`; materiality, forms, side, `include_in_feed`, `reporting_persons`, `match_reason`), `_system/reference/activist-reports/` (new short reports and letters), `dashboard/data/short_alpha.json` (`generated_at`, `as_of`; candidates with origin activist_index and the short-report scorecard), `dashboard/data/special_situations.json` (`generated_at`; deal paper already classified under mergers), `dashboard/data/document_catalog.json` (`generated_at`), `_system/portfolio/registry.json` (`meta.updated`).
- **Screens:** 13D and amendments (what changed: stake, purpose, seats, settlement, sale demand); 13G and amendments (new stake, round number crossed, 13G-to-13D switch, issuer or founder control filings); proxy solicitations (DFAN14A, DEFA14A, DEFC14A, PREC14A, PX14A6G); short reports (author's claim, author's evidence, one filing fact for or against).
- **Output:** the brief (lane ids `13d`, `13g`, `control_filing`, `proxy`, `short_report`; one campaign is one item, amendment chains and dual-class pairs collapsed) and the lessons. After the items, classification bugs (wrong ticker, wrong firm, English-word match) as `[PROPOSED]` lessons pointing at `match_firm_id`, `match_report_to_ticker` and `publisher_target_verdict`.
- **Never:** identity from `firm_name` (cover page and `reporting_persons` only; HoldCo Asset Management is untrusted until the document names it); a ticker from an English word (OPEN is not Illumina's open letter); a short seller's conclusion presented as the desk's; a fraud tag; a brief per amendment.

## Fundamentals (`fundamentals`)

- **Owner:** drew.
- **Reads:** `dashboard/data/kpi_trends.json` (`generated_at`; `inflection_count`, per-ticker direction), `dashboard/data/portfolio_news.json` (`build_time`; categories guidance, earnings_material, capital_raise, buyback, dividend_policy, management, accounting, legal, regulatory; confidence >= 0.8; about a 30-day window), `dashboard/data/document_catalog.json` (`generated_at`) and the news row's `linked_filing`, `dashboard/data/fico_watch.json` (`generated_at`; optional, FICO only), `dashboard/data/special_situations.json` (`generated_at`; what Special Situations already owns before a handoff), `_system/portfolio/registry.json` (`meta.updated`; holdings versus universe).
- **Screens:** guidance and KPI breaks (accelerating or decelerating in `kpi_trends`, or a company-issued change; steady is not a break); capital-structure change that stays with the going concern (raise, buyback start or exhaustion, dividend cut, special dividend, convertible); news versus filing disagreement (both sentences, filing primary); management, accounting and legal events (CEO/CFO exit, restatement, auditor change, material weakness, government or court action).
- **Output:** the brief (lane ids `guidance_break`, `kpi_inflection`, `capital_structure`, `news_vs_filing`, `management`, `accounting`, `legal`) and the lessons. Each item says whether the ticker is a holding or only in the universe, and whether `kpi_trends` agrees with the headline.
- **Never:** an EPS surprise with no operating fact; an analyst note or a price-target change; a stub, warrant, rights offering, spin or CVR brief (one line and `handoff: special_situations`, no re-extraction of strike, milestone or ratio); a going-concern capital print dressed as a special situation.

## NOL and Tax Assets (`nol_tax_assets`)

- **Owner:** drew.
- **Reads:** `dashboard/data/nol_screener.json` (`built_at`; `tax_reality`, `criteria`, `actionable_count`, `blocker_tally`, rows), `dashboard/data/nol_382_facts.json` (`generated_at`; `prior_ownership_change`, `nol_rights_plan`, `bankruptcy_382_exception`, `needs_review`, the stored filing quote), `dashboard/data/separations.json` (`generated_at`; `terms.section_355_claimed` on spins and split-offs), `dashboard/data/activist_feed.json` (`generated_at`; new stakes above 5% that can start an ownership-change clock), `_system/portfolio/registry.json` (`meta.updated`).
- **Screens:** actionable rows and blockers that just changed; large gross NOL or NOL DTA versus market cap where the blocker is not "management fully reserves it" alone; a prior ownership change with the stated limitation; an NOL rights plan with its trigger; a live transaction (merger, large issuance, 5% stake) that could cause the next ownership change; `needs_review` rows, quoting the stored excerpt.
- **Output:** the brief (at most ten items; lane ids `actionable`, `blocker_changed`, `prior_382_change`, `rights_plan`, `ownership_change_risk`, `needs_review`; `one_number` is the one tax number: gross NOL, NOL DTA, allowance percent or a stated 382 limit) and the lessons, ending with the blocker tally in `notes`.
- **Never:** a present value; a control premium; a DTA treated as cash; a Section 382 limit the facts file does not state; the bankruptcy exception unless `bankruptcy_382_exception.mentioned` is true and the filing is quoted; a Section 355 or exchange-treatment opinion read as ownership-change capacity at the spun entity.

## Index, forced flow and tape (`tape_index`)

- **Owner:** drew.
- **Reads:** `dashboard/data/index_membership.json` (`generated`; membership `as_of`; scorecards, `impact_proxy` with `demand_shock_source`, `confirmed_events`, `prediction.recon_watch`), `dashboard/data/portfolio_news.json` (`build_time`; category index_inclusion), `dashboard/data/technical_summary.json` (`generated_at`, `model_version`, `summary.fear_states`, `market_context`), `dashboard/data/technical_signals.json` only for history on a name already being briefed, `dashboard/data/capitulation_daily.json` when the summary's capitulation block is missing, `dashboard/data/separations.json` (`generated_at`; `forced_seller_rows` and index-exclusion legs), `dashboard/data/special_situations.json` (`generated_at`; the forced_sellers lane), `_system/portfolio/registry.json` (`meta.updated`).
- **Screens:** confirmed index adds, deletes and migrations with effective dates; `recon_watch` and tight `distance_to_boundary_pct`; large `demand_shock_pct_of_adv` with its source named; a spin or deletion that forces an index fund to sell a thin line; tape flags at the stored thresholds only (RSI 14 at 25/35/70, stretch_z at +/-2, trend_z at +/-1.25, Chaikin money flow at +/-0.10, the stored breakout definition, capitulation states with their scores).
- **Output:** the brief (at most fifteen items; lane ids `index_event`, `forced_flow`, `breakout`, `approaching_overbought`, `overbought`, `approaching_oversold`, `oversold`, `capitulation`; `one_number` is the flow or tape number quoted from the file with its threshold) and the lessons, with `market_context` in `notes` and whether the run's flags cluster in that state.
- **Never:** a recomputed indicator; a buy or a sell; an override of a fundamental or special-situations conclusion; an `assumed_bps_fallback` dressed as a measured shock; a scorecard replaced by a blog; a rank for a spun ticker absent from `index_membership` and `technical_summary`.

## Murray Stahl (`stahl`)

- **Owner:** drew.
- **Reads:** `_system/reference/investment-wisdom/horizon-kinetics/*-extract.txt` (date on each; newest is the April 2026 Q1 commentary), the web for Horizon Kinetics commentaries and letters dated after that, `_system/reference/investment-wisdom/hk_ticker_index.json`, the `FRMO` and `HKHC` folders and latest filings, `dashboard/data/portfolio_news.json` (`build_time`; royalties, trusts, land, water, exchanges, clearing, bitcoin, gold, spinoffs), `dashboard/data/index_membership.json` (`generated`), `dashboard/data/document_catalog.json` (`generated_at`), `dashboard/data/separations.json` and `dashboard/data/special_situations.json` (`generated_at`; the spinoffs lane: Form 10, ratio, who must sell), `_system/memory-hub/research-equity/daily/` (last 14 days), the Stahl shelf under `_system/reference/investment-wisdom/stahl/podcast/episodes/spoken/` when a hit needs the original category.
- **Screens:** Horizon Kinetics update (anything newer than April 2026); royalties and scarce assets (who spends the capital, what is dormant, what date is filed); exchanges and true croupiers (handled volume versus share, fee model, principal at risk); crypto (monetary asset, croupier, miner kept separate); predictive attributes (owner-operator, dormant asset, spin-off, bits and pieces, long product life, equity yield curve, index distortion).
- **Output:** the brief (lane ids `hk_update`, `royalty_scarce_asset`, `croupier_exchange`, `crypto`, `predictive_attribute`, `equity_yield_curve`; `one_number` is the current figure with its date and document, never a 2008 or 2024 illustration) and the lessons, with the newest commentary date actually read in `notes`. Horizon Kinetics opinion stays opinion; the TPL board conflict stays visible.
- **Never:** a new Stahl sentence, price or recommendation; pasted essay text; a bank, pipeline or capital-intensive toll called a croupier; a Horizon Kinetics assumption promoted into a base return; a dormant asset with no filed catalyst called a curve.

## Short Selling (`short_selling`)

- **Owner:** michael (Michael's archived `Short-Selling` repo folds into this desk and he owns the reverse-split decisions); Drew's bot may file too.
- **Reads:** `dashboard/data/short_alpha.json` (`generated_at`, `as_of`; `candidates`, `positions`, `frameworks`, `summary`), `dashboard/data/reverse_splits.json` (`generated_at`; arriving with the reverse-splits lane, skip while absent), `dashboard/data/activist_feed.json` (`generated_at`; `side: short`), `dashboard/data/portfolio_news.json` (`build_time`; categories capital_raise, restructuring, forward_split; confidence >= 0.8), `dashboard/data/document_catalog.json` (`generated_at`; the 8-K, 424B, S-3 or 10-K behind a hit), `_system/portfolio/registry.json` (`meta.updated`).
- **Screens:** reverse-split announcements (ratio, effective date, the filing, the stated reason); dilution supply (ATM programs, registered directs, convertibles, warrant inducements, lock-up expiries; size versus float from the filing); going-concern language (10-K and 10-Q, with the quote located); activist short reports (author's claim, one filing or dashboard fact that confirms or cuts against it); borrow readings (rate, availability, utilization, each with its source and date; the Client Portal availability CSV through the Shorts tab, never a Gateway probe).
- **Output:** the brief (lane ids `reverse_split`, `dilution_supply`, `going_concern`, `activist_short`, `borrow`; `one_number` is the ratio, the raise size versus float, the borrow rate or the report-date price with its date) and the lessons.
- **Never:** a fraud tag (`fraud_bad_actors` is a human conclusion); a position, a size or a stance; copied report text; an invented borrow figure; any IB Gateway contact (CLAUDE.md Rule 9); a spin, stub or CVR brief (one line and `handoff: special_situations`).
