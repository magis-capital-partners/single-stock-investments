# One forecast for PV, forward IRR and entry prices

Every ticker in Research coverage participates. The universe comes from the
coverage payload, not the 37-company compounder list. A newly onboarded ticker
is automatically included on the next refresh.

## Authoritative calculation

`valuation_forecast.py` unwinds the issuer's calculation proof into undiscounted
per-share cash flows. Each cash flow retains its component, proof node, scenario
discount rate and economic timing. Discounting these flows reproduces the
original component proof; it does not annualize an intrinsic-value/price gap.

The same flows produce present value, purchase-price IRR and hurdle entry prices.
Different bear/base/bull rates and different component rates remain distinct.
The model-date PV is retained for reconciliation. Current PV rolls the remaining
forecast forward to the calculation date; a later quote never moves forecast
payment dates or includes distributions that occurred before purchase.

An explicit cash/debt addition in an operating DCF is retained as a time-zero
acquisition adjustment. This is a hypothetical net-asset settlement sensitivity,
not a forecast of declared dividends. The card discloses the convention. No
extra cash/debt is added to a terminal value that already includes it.

Explicit dated schedules and future-payoff declarations support NAV, milestone,
royalty and catalyst models. A static NAV, reserve, capitalization multiple or
option-value judgment alone does not specify when shareholders receive cash.
Those components retain a timing gap. Negative equity needs an explicit
limited-liability waterfall rather than artificial acquisition cash flows.

Existing full per-share issuer scenarios are adapted before any first-pass
model is considered. Their normalized cash anchor, growth phases, terminal
multiple and horizon are retained. Required-return assumptions affect PV only;
where the original model supplied none, explicit 12/10/9% PV hurdles are disclosed.

## Missing issuer models

If no additive issuer valuation exists, dated annual operating fundamentals can
construct an **automatic first-pass operating model**. Its facts, assumptions and
calculation proof feed the same compiler. BOTH its PV and IRR therefore use the
same forecast. It is labeled screening-grade, with generic assumptions visible;
it never replaces an existing issuer component valuation.

This operating template deducts reported capex and observed SBC, retains 35% for
additional reinvestment, uses bounded historical cash-growth scenarios and
12/18/24 terminal equity multiples. Scenario required returns are 12/10/9%.
Missing SBC uses a disclosed 1% dilution sensitivity. These are model assumptions,
not sourced facts about future performance. The model anchor only changes when
the financial observations change, not when a quote changes.

Holdings, unsuitable method profiles, funds and material minority structures
cannot silently become operating DCFs or book-value sensitivities. Missing cash,
share-count, FX, timing and parent-attribution inputs remain specific gaps.

## Unattended refresh and publication

The existing twice-weekday workflow collects quotes across the entire coverage
universe. Financial inputs for missing models refresh weekly. Every run evaluates
all issuer models, publishes their calculation status, and retries failed
providers without aborting other companies. It requires no committee or human
approval to calculate or publish research results.

`refresh_shared_forecasts.py --collect` collects, calculates and publishes.
`refresh_shared_forecasts.py --check` replays the full universe from the saved
issuer models and observations and compares both actual served surfaces.
`--as-of YYYY-MM-DD` pins a replay date; it does not manufacture historical
knowledge from subsequently retrieved provider data.

The compact all-ticker audit is `_system/data/shared_valuation_forecasts.json`.
Complete schedules, component reconciliation, assumptions, sources and entry
prices live once in each ticker detail shard. Coverage carries compact decision
fields and the same calculation identifier. A normal dashboard rebuild invokes
the compiler again so it cannot restore obsolete estimates.

The main Forward Return column, sorting, scenario chart and workspace read the
shared result. The old mechanical compounder estimate is no longer a fallback.
Approval/confidence metadata remains distinct from numerical availability.

ADR ratios are bound to issuer/SEC sources in
`_system/reference/valuation_listing_ratios.json` and applied inside the same
proof as the share denominator. Reporting/listing FX is a separate dated
observation; converting currency alone cannot fix an ADR share-count mismatch.

Provider company names are checked against coverage identity, with SEC CIK
confirmation for renamed issuers where available. Primary-source aliases handle
translations and legal names. Clear issuer mismatches are withheld automatically;
they cannot publish another company's price or IRR. A missing name is disclosed
as symbol-only identity rather than claimed as name verification.

## Verification and limitations

Tests cover case-specific rates, mixed-rate components, current-price changes,
dated roll-forward, time-zero net assets, explicit milestone payoffs, NAV timing
gaps, currency conversion, stale quotes, future sources, complete coverage,
deterministic replay, served-payload tampering and committee-independent research
publication. Entry-price round trips must reproduce their target IRR within
0.01 percentage point. Component PVs reconcile within proof rounding tolerance.

An autonomous refresh cannot infer undisclosed realization terms or invent an
issuer forecast. The audit distinguishes available calculations, quote gaps and
model gaps. A ticker being covered does not mean every missing economic input
has become known.
