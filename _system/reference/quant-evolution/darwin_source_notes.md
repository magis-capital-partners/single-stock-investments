# Darwin AI Investments — source notes (Phase 0)

**Public positioning** ([darwinaiventures.com](https://darwinaiventures.com/)):

- Adaptive, **neural network–driven** investment strategies
- **Reinforcement learning** on complex financial markets
- Private; offerings only via confidential documents to qualified investors

**Local investor letter:** place `Darwin_AI_Investments_1Q26.pdf` in this folder (gitignored). After adding, append bullet claims below with page refs.

## Claims extracted (fill from PDF)

| # | Claim | Page | Maps to our stack |
|---|--------|------|-------------------|
| 1 | _pending_ | — | `darwin/encoder.py` latent factors |
| 2 | _pending_ | — | `darwin/ppo.py` turnover-aware reward |
| 3 | _pending_ | — | `darwin/genetic.py` policy population |

## Mandate alignment

See `_system/portfolio/darwin_mandate.json` — long-only, quarterly rebalance, 15% turnover cap, Marvin stance gate preserved.
