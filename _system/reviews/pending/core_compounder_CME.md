# Core compounder review: CME

Research only; pending human review.
Proposal: `tci-f6b5456ddcd5305cad6a`

## Evidence and underwriting gaps

- {'persona': 'stahl', 'label': 'Murray Stahl', 'verdict': 'hold', 'return_pct': 11.2, 'key_metric': 'archetype=croupier', 'conviction': 0.06, 'falsifier': 'No asset intensity / pricing power (moat eroding + non-croupier)'} — CME/research/valuation.json#lens_consensus (as of 2026-06-03; opinion)
- {'persona': 'hk', 'label': 'Horizon Kinetics', 'verdict': 'hold', 'return_pct': 13.2, 'key_metric': 'payoff_lens=operating', 'conviction': 0.06, 'falsifier': 'No dated contractual payoff or royalty/trust structure'} — CME/research/valuation.json#lens_consensus (as of 2026-06-03; opinion)
- Typed moat-impairment falsifiers are missing. — CME/research/valuation_contract.json (as of 2026-06-03; inference)
- Tracked lens-investor history must be reconciled; existing specialist signals do not establish Hohn coverage. — _system/lenses/personas.json (as of None; inference)
- The strongest sourced bear argument is not available through latest.json. — CME/research/latest.json (as of 2026-06-03; opinion)
- Issuer operating periods postdate the model; reconcile them with its assumptions. — _system/reference/market-data/operating_kpis/CME.json (as of 2026-10-25T08:43:53Z; inference)
- Past scheduled earnings remain unconfirmed; verify the calendar before calling them reported. — CME/research/evidence/earnings_calendar.json (as of 2026-07-09T17:21:45Z; inference)
