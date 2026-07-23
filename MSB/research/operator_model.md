# MSB operator model (Cliffs + commodities)

**Artifact:** `operator_model.json` (machine) · this note (human)

## Do we need commodity prices?

Yes, as **orientation**, not as the cash engine:

| Input | Role |
|-------|------|
| Iron ore spot (FRED / proxy) | Regime for pellet pricing / bonus probability |
| Steel ETF (SLX) | Demand sentiment for Cliffs utilization |
| CLF steel shipments / FY guide | Operator cadence (not Northshore tons) |
| Mesabi royalty 8-K | **Source of truth** for tons, base royalty, bonus, threshold |

MSB distributions = Northshore tons × contractual base/bonus. Bonus turns on when **deemed** pellet price clears the adjusted threshold (e.g. **$71.70**/ton in 2026). Spot iron ore can diverge from that deemed price.

## Refresh

```bash
python _system/scripts/parse_msb_royalty_report.py --write
python _system/scripts/fetch_theme_panel.py --theme iron_ore_steel
python _system/scripts/build_msb_operator_model.py --write
# or
python _system/scripts/marvin_cloud_refresh.py MSB --date YYYY-MM-DD
```

`in_base_irr` stays false until human promotion.

## CLF panel ritual

After each Cliffs earnings release:

```bash
python _system/scripts/update_clf_operating_panel.py \
  --as-of YYYY-MM-DD --shipments X.XXX --fy-guide-mid 16.75 --asp NNNN \
  --source 'https://www.clevelandcliffs.com/...' --note 'Qn 2026 earnings'
python _system/scripts/fetch_theme_panel.py --theme iron_ore_steel
python _system/scripts/build_msb_operator_model.py --write
```

## World Model KPI ledger

Not on `main` yet. When `_system/reference/linkages/` + `kpi_ledger.json` land, add edges for iron ore / CLF shipments / Northshore tons / bonus into MSB ledger rows with `in_base_irr: false`. Until then `operator_model.json` is the SoT for operator transmission.
