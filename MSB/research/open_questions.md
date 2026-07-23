# Open questions — MSB

**As of:** 2026-07-23

## What changed in the market narrative?

- [x] CLF Q2 2026 (2026-07-23): steel tons soft QoQ on maintenance; H2 guide strong on price/margins. Stock +~18%. Transmission to MSB is mine-level, not CLF EPS — see `operator_model.json`.
- [ ] July 30, 2026 Mesabi quarterly royalty report (tons, deemed pellet price, bonus vs **$71.70** threshold).

## What would falsify our base case?

- [ ] Persistent zero bonus with sub-threshold deemed pricing as the new normal (producing proof low ~$30/unit becomes the anchor).
- [ ] Northshore idle / swing-mine curtailment that collapses tons for multiple quarters.
- [ ] Adverse AAA arbitration outcome (legal option already $0 in base).

## What is the market implied story we disagree with?

- [x] Annualizing July **$0.05** distribution / Q1 zero bonus as permanent broken yield (bonus is a mechanical switch; trough ≠ terminal).

## Next research action

- [ ] On July 30 royalty 8-K: `python _system/scripts/parse_msb_royalty_report.py --write` then `build_msb_operator_model.py --write`.
- [ ] IC gap: independently reproducible reserve / royalty-tier depletion schedule (blocks decision-grade freeze).
- [ ] After World Model KPI ledger lands on main: wire `iron_ore_steel` edges into `MSB/research/kpi_ledger.json` (context only).
