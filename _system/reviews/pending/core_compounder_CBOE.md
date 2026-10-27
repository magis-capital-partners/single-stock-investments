# Core compounder review: CBOE

Research only; pending human review.
Proposal: `tci-5cafb18939850d55c345`

## Evidence and underwriting gaps

- First Marvin deep dive; batch onboard 2026-06-03. — CBOE/research/thesis_card.json (as of 2026-06-03; inference)
- No third-party sources indexed; stance rests on filings only. — CBOE/research/thesis_card.json (as of 2026-06-03; inference)
- Entry band **$250–255** for ~15% base annual return is model-derived, not human-approved. — CBOE/research/thesis_card.json (as of 2026-06-03; inference)
- {'persona': 'stahl', 'label': 'Murray Stahl', 'verdict': 'hold', 'return_pct': 13.2, 'key_metric': 'archetype=croupier', 'conviction': 0.16, 'falsifier': 'No asset intensity / pricing power (moat eroding + non-croupier)'} — CBOE/research/valuation.json#lens_consensus (as of 2026-06-03; opinion)
- {'persona': 'hk', 'label': 'Horizon Kinetics', 'verdict': 'hold', 'return_pct': 15.2, 'key_metric': 'payoff_lens=operating', 'conviction': 0.16, 'falsifier': 'No dated contractual payoff or royalty/trust structure'} — CBOE/research/valuation.json#lens_consensus (as of 2026-06-03; opinion)
- {'persona': 'munger', 'label': 'Charlie Munger', 'verdict': 'hold', 'return_pct': 13.2, 'key_metric': 'moat=stable', 'conviction': 0.06, 'falsifier': 'Moat eroding/unproven or irr_method pending'} — CBOE/research/valuation.json#lens_consensus (as of 2026-06-03; opinion)
- Typed moat-impairment falsifiers are missing. — CBOE/research/valuation_contract.json (as of 2026-06-03; inference)
- Tracked lens-investor history must be reconciled; existing specialist signals do not establish Hohn coverage. — _system/lenses/personas.json (as of None; inference)
- The strongest sourced bear argument is not available through latest.json. — CBOE/research/latest.json (as of 2026-06-03; opinion)
- Issuer operating periods postdate the model; reconcile them with its assumptions. — _system/reference/market-data/operating_kpis/CBOE.json (as of 2026-10-27; inference)
