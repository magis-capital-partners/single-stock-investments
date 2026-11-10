# Inflections

The company overview answers what changed in each tracked business, the support
for that claim, and its reporting period. The signal explorer retains the wider
observation set. Scope and company search apply to rows and coverage together.

## Reading the page

- Holdings uses authenticated core-row `in_holdings` membership and explicit
  ticker aliases. If that metadata is unavailable, it does not fall back to
  calling the entire universe holdings. All tracked uses the current tracked
  universe and excludes historical cache strays.
- Improving/Weakening/Mixed describe eligible reported business evidence.
  Company history can support or contradict that evidence. Peer comparisons,
  EPS surprises, monthly operating observations and demand/news context do not
  vote in the company assessment. Opposing evidence stays Mixed.
- Related composite components do not earn extra votes. Evidence filters find
  companies without rewriting their overall summary or hiding disagreements.
- Support belongs to the lead metric, not every claim about a company. The
  engine can confirm through two-quarter persistence **or** a trailing-year
  check. Those methods are labeled separately; legacy confirmation with no
  recorded method is disclosed rather than called two-quarter support.
- The source snapshot date is distinct from the underlying reporting period.
  Ages are recalculated on the viewing date. Unknown periods, stale financial
  series, volatile/sign-changing bases, duplicates and unselected signals cannot
  support a headline. Undated contextual observations remain readable with an
  explicit missing-period label and no persistence claim.
- No clear shift means usable financial data exists without a qualifying
  change. Insufficient data means the evidence cannot support an assessment.
  Both categories can be opened through coverage or the direction filter.
- Every result is reachable through explicit 25-row pagination. The explorer
  can include suppressed and steady observations through More filters.
- QDEL's respiratory model is closed and loaded only when requested inside
  company evidence. Its forward periods remain forecasts.

## Data and publication

`_system/scripts/build_inflections.py` reads cached KPI data and tracked company
identity. It does not contact any data service, Gateway or terminal. It writes:

- `data/inflection_overview.json`: small landing-page projection, with eligible
  business signal metadata needed to recompute age on the viewing date.
- `data/inflection_signals.json`: a lazy observation index without point history.
- `data/inflection_evidence/00.json` through `1f.json`: 32 bounded, deterministic
  buckets retaining the reported series and original calculation fields.
- `data/inflection_history.json`: previous successful observation fingerprints
  and last material changes; never brokerage positions or holdings membership.

The dashboard shard writer refreshes these assets after its publication guards.
The standalone cached-data command is:

```powershell
python _system/scripts/build_inflections.py
```

Evidence and index assets carry the same content-derived snapshot ID as the
overview. Readers reject mismatches and offer retry/reload rather than silently
combining different snapshots. The overview publishes after evidence buckets.
Rebuilds preserve source timestamps, and older source snapshots are rejected.

Change history starts with a baseline. New/Changed/Resolved labels require an
actual observation change across successful snapshots and expire after seven
days. Source timestamp changes and rebuilding identical observations do not
create new labels. Missing coverage or aging out is not resolution. Resolution
requires a newer usable report without a qualifying signal. Changes to wording
and noise strength alone do not generate business-change labels.

The company-detail control retains filters, pagination and expansion state.
Inspecting a metric from the explorer offers a return to its filtered results.
The initial view never requests the full KPI monolith, observation index, point
history or respiratory model.

## Verification

```powershell
python -m unittest discover -s _system/scripts/tests -p test_inflections.py
python -m unittest _system/scripts/test_kpi_trends.py _system/scripts/test_kpi_signal_enhancements.py _system/scripts/test_build_dashboard_shards.py
node --test dashboard/cloudflare/test-inflections.mjs
```

CI runs the projection and rendering contracts in Dashboard expansion checks.
The Python suite under `_system/scripts/tests` is also discovered by Python CI.
Browser checks should cover scope/search, lazy evidence, QDEL research, explorer
inspection and return, page navigation, retry states, keyboard focus and narrow
layouts. No network data pull is needed to verify this feature.
