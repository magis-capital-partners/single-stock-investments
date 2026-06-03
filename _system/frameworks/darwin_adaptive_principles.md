# Darwin adaptive principles (exploration phase)

Marvin supplies **beliefs** (IRR, stance, falsifiers). Darwin supplies **allocation** (policies, evolution, constraints). Production and exploration use the same pipeline with different champion rules in `darwin_mandate.json`.

## Phases A–E (implemented)

| Phase | Module | Output |
|-------|--------|--------|
| **A** Data ingest | `darwin/import_external_data.py`, `darwin/prices.py` | ETF returns (SPY, QQQ, …) from etf-dashboard; longer price panel when CSVs exist |
| **B** Observatory | `darwin/observatory.py` | `dashboard/data/darwin_observatory.json`, `_system/reviews/pending/darwin_regime_brief_{date}.md` |
| **C** Adaptive policies | `darwin/policies.py` (`risk_parity_vol`), exploration champion | Best in-sample policy when `exploration.enabled` |
| **D** Epistemic hygiene | `darwin/bias_scan.py`, `darwin/questions.py`, `darwin/scorecard.py` | Bias flags, `open_questions.md` scaffolds, `darwin_improvement_scorecard.jsonl` |
| **E** Stress sim | `darwin/simulation.py` | Bootstrap paths in `darwin_portfolio.json` → `stress_simulation` |

## External repos

Clone optional siblings (not committed; see `.gitignore`):

```bash
git clone https://github.com/GoldmanDrew/etf-dashboard.git _external/etf-dashboard
git clone https://github.com/GoldmanDrew/ls-algo.git _external/ls-algo
```

Or set:

- `DARWIN_ETF_DASHBOARD_ROOT`
- `DARWIN_LS_ALGO_ROOT`

Sync only:

```bash
python3 _system/scripts/build_darwin_portfolio.py --sync-external
# or
make darwin-sync-external
```

Manifest: `_system/reference/market-data/external/sources_manifest.json`

## Exploration vs production

| Setting | Exploration (`enabled: true`) | Production |
|---------|------------------------------|------------|
| Champion | `best_insample` among policies + ensemble | `preferred_policy` or ML/OOS gates |
| `ml_selected` | Ignored for gating | Requires OOS when `pit.require_oos_for_ml` |
| Policies | `exploration.policies_active` list | Same pool; champion not forced to `ira_marvin` |

PIT discipline remains on for audit/backtest (`darwin_pit_discipline.md`); exploration does not disable leakage checks.

## Commands

```bash
make darwin-build          # fast production + exploration build
make darwin-sync-external  # etf-dashboard + ls-algo ingest
make darwin-pit-check      # build + PIT checker
```

## SFI / adaptive markets framing

- **Complexity:** Many policies compete; ensemble blends top scores (deflated Sharpe).
- **Adaptation:** Regime merges research stress + macro (VIX, yields); turnover scales in stress.
- **Continual improvement:** Scorecard JSONL + PIT history track audit/OOS/bias over time.
- **Separation:** Marvin files are inputs; Darwin never writes `valuation.json` or `MEMORY.md`.

## Dashboard

Holdings view unchanged. **Darwin** tab shows exploration badge, observatory, bias scan, stress bands, and benchmarks including `risk_parity_vol`.
