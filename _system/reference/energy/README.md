# Gas, power and Bitcoin model

The dashboard workspace lives in **Insights → Ticker insights → World Model**, immediately above **BTC snowball (HK)**. It is a public-data research model. The optional energy overlay changes a separate mining-cost comparison; the existing BTC demand fit and all security base IRRs remain unchanged.

## Run and refresh

From the repository root, using Python 3.12 or later:

```powershell
python -m pip install -r _system/scripts/requirements-energy.txt
python _system/scripts/fetch_energy_panel.py
python _system/scripts/fetch_energy_assets.py
python _system/scripts/build_energy_model.py
python _system/scripts/validate_energy_model.py
python _system/scripts/build_hk_snowball_model.py
```

The two fetchers use public EIA HTTPS resources. They do not use ThetaData, IB, brokerage sessions, vendor credentials, or a paid data seat. Normal refreshes reuse data acquired the same day; `--force` retries immediately. Failed sources retain their last successful records and surface warnings. `--offline` loads caches without network calls. The model builder itself makes no network calls.

The existing `world-model-weekly` pipeline installs the workbook reader and runs the energy acquisition, model and validation steps between the crypto refresh and BTC/World Model publication. No new hosting service or separate automation is needed. Weekly data will refresh in that existing lane; the UI's Reload button reloads the latest published artifacts rather than running acquisition.

To preview locally:

```powershell
python -m http.server 18765 --bind 127.0.0.1 --directory dashboard
```

Open `http://127.0.0.1:18765/#/insights/tickers`. Keep a separate preview port if another application already uses that port.

## What is implemented

- Monthly US dry production, four end-use sectors, residual consumption, imports/exports, working storage, and Henry Hub spot history from 2010 onward.
- Weekly Lower 48 working storage with regional observations and the five-year comparison. This different geography is displayed separately, never substituted into the US monthly conservation equation.
- Four monthly scenarios through 2032: public reference, scarcity hypothesis, supply/demand relief, and tight supply/weather. Published EIA September 2026 STEO quarterly rates anchor the path through 2027; later extensions are explicitly assumed.
- Seasonal daily flows, injection/withdrawal screening limits, capacity and operating-minimum constraints. The model reports unserved demand and excess supply explicitly when storage cannot absorb the balance.
- Public LNG train and EIA-860M gas generator inventories, source hashes and release dates. LNG month/quarter/half-year/year date precision is retained. Undated approvals are excluded. Cumulative planned generator capacity is a cross-check, not a second addition to national power demand.
- ERCOT, PJM, other-US and unknown foreign power-cost sensitivities; fixed/merchant power cohorts and contract expiry. Heat rates, basis, pass-through and miner exposure are assumptions.
- Separate mining electricity, nonpower, operating and total costs; fees in revenue; day-weighted halving months; explicit hashrate/efficiency paths. An optional two-state shutdown/retarget experiment is labeled experimental.
- Scenario/year/region controls, baseline/energy-linked comparison, searchable project records, CSV/JSON downloads, data provenance, model limitations, and falsification conditions on the existing BTC tab.
- Validation at every build, dated model snapshots, source-vintage archives, matching energy/bridge IDs, stale-source gating and optional-file failure handling.

Downloads are prebuilt under `dashboard/data/energy_exports`: each case CSV joins gas balances to dated BTC cost rows, and the full JSON includes both models and their shared content ID. Missing BTC rows remain blank rather than appearing as zero cost.

## Change assumptions

Edit `_system/scripts/energy_model_config.json` and rebuild. Keep reviewed assumptions under version control; do not overwrite public observations to fit a hypothesis. For an experiment, copy the config and run:

```powershell
python _system/scripts/build_energy_model.py --config path/to/experiment.json --output-dir path/to/results
```

Production and LNG `terminal_2030` entries are December exit rates. Other consumption anchors are annualized daily rates with historical seasonality. Gas-price anchors are annual-center assumptions, interpolated monthly. Weather percentages multiply selected winter/summer sectors. Project delay and utilization affect the separate inventory cross-check; they do not silently add to or rewrite the national balance.

The generator cross-check assumes 50% utilization and 7.5 MMBtu/MWh. It excludes retirement dispatch effects and should not be read as a net generation forecast. Baseload LNG output is distinct from peak output and feedgas consumption.

Miner cohort weights sum to one. Fixed shares expire after `contract_end`; merchant tariffs take regional gas-price changes from the $0.05/kWh delivered baseline. Foreign/unknown exposure receives no inferred US gas sensitivity. Availability is descriptive because the network hashrate input is already realized; applying it again would double-count downtime. Effective J/TH already includes PUE.

Nonpower cost is a daily residual calibrated from the legacy total and reconstructed electricity cost. Its operating/capital allocation is assumed. A higher tariff affects electricity only, rather than scaling nonpower costs by a fixed electricity share. Cost is not a BTC valuation floor. Hashprice uses 1 EH/s = 1,000 PH/s; electricity uses `EH/s × J/TH × 24,000` kWh/day.

## Validation and data boundaries

```powershell
python -m unittest discover -s _system/scripts/tests -p test_energy_model.py -v
python _system/scripts/test_btc_cost_of_production.py
python _system/scripts/test_hk_snowball_model.py
python _system/scripts/validate_energy_model.py
node _system/scripts/tests/test_energy_model_ui.cjs
```

Tests cover monthly-volume units and leap years, storage conservation/overflow/shortfall, base-versus-working-gas identity, prior-date joins, publication cutoff, fixed-contract expiry, independent nonpower costs, fees, halving months, stale/missing inputs, hashprice migration and the two-state difficulty experiment. The artifact validator independently checks conservation and BTC accounting before atomic publication.

The first history acquisition is a revised snapshot. Historical reconciliation residuals and a seasonal-naive benchmark are displayed; **no out-of-sample predictive skill is claimed**. Archived snapshots support prospective evaluation. `--as-of` rejects source vintages and reference forecasts published after that date; a historical replay requires a retained vintage, not today's revised history with an older label.

`energy_model.json` and `energy_btc_bridge.json` share a content ID. The UI refuses a mismatched bridge. If a required gas source is older than 120 days by publication or observation, the BTC overlay is disabled. Required crypto inputs expire after 14 days. Missing fees are explicitly marked as assumed zero. The optional energy fetch does not block the legacy BTC panel.

The reviewed STEO forecast is deliberately versioned, not silently replaced with an unrelated new forecast. Refresh the values and dated citation when reviewing each monthly STEO. Warnings begin after 60 days, and the BTC bridge is disabled after 120 days. Source-specific archives retain revised histories. Large source XLSX/PDF binaries and private source material are not copied into the repository.

## Research extensions that require additional evidence

This release does not reconstruct a licensed well/acreage inventory, solve regional pipeline dispatch or hourly electricity market clearing, normalize individual miner contracts, calibrate NOAA weather regressions, or produce security-level recommendations. Verified miner-contract coverage is explicitly zero. Regional tariff assumptions are not observed wholesale-price histories. Realistic long-run difficulty adjustment, migration and miner re-entry need finer operating data.

Those are research/data requirements, not hidden completed features. The public model tests disclosed aggregate hypotheses and makes their BTC cost implications inspectable. It should remain optional until contract coverage, holdout performance and repeated source refreshes justify promotion.

## Publication and failure handling

The reviewed reference is the **October 6, 2026 EIA STEO**, with quantities from [Table 5a](https://www.eia.gov/outlooks/steo/tables/pdf/5atab.pdf) and Henry Hub prices from [Table 2](https://www.eia.gov/outlooks/steo/tables/pdf/2tab.pdf). The configuration records both source hashes and the review date. Quarterly quantities are disaggregated with historical month shares; values after 2027 remain analyst assumptions.

`python _system/scripts/refresh_energy_model.py` refreshes the public data and publishes a matched model/bridge pair, static CSV/JSON downloads, and `energy_refresh_status.json`. Direct runs fail visibly if the balance cannot be rebuilt. The weekly World Model lane uses `--optional` to record the failure, retain prior energy results, and continue updating the existing models. The UI displays failed refreshes and old build dates.

The compact project registry stores planned gas generators and totals for all inventory categories. The linked EIA workbook retains full operating-unit detail. Generated vintages and duplicate history snapshots are ignored; the current normalized observations and compact public outputs are committed. The full JSON download uses compact encoding to avoid storing another large formatted copy.
