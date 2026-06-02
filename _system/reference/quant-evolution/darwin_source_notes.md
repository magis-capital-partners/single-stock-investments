# Darwin AI Investments — source notes (Phase 0–4)

**Public positioning** ([darwinaiventures.com](https://darwinaiventures.com/)):

- Adaptive, **neural network–driven** investment strategies
- **Reinforcement learning** on complex financial markets
- Private; offerings only via confidential documents to qualified investors

**Local investor letter:**

Vault: `_system/reference/quant-evolution/Darwin_AI_Investments_1Q26.pdf` (gitignored)  
Extract: `Darwin_AI_Investments_1Q26_extract.txt` (gitignored)

```bash
bash _system/scripts/copy_darwin_investor_pdf.sh
pip install pypdf
python3 _system/scripts/ingest_darwin_investor_pdf.py
```

Alignment doc: `_system/frameworks/darwin_source_alignment.md`  
Mandate: `_system/portfolio/darwin_mandate.json` → `source_overrides`

## Claims extracted (1Q26 ingest)

| # | Claim | Maps to our stack | Action |
|---|--------|-------------------|--------|
| 1 | Adaptive neural network strategies on real-world markets | `darwin/encoder.py`, `darwin/ppo.py` | replicate |
| 2 | Reinforcement learning; reward includes trading costs / turnover | `darwin/ppo.py`, `turnover_penalty_kappa` | replicate |
| 3 | Population-based search; survivors persist | `darwin/genetic.py`, `darwin/persistence.py` | replicate |
| 4 | Regime adaptation under stress | `darwin/regime.py`, `darwin/adversary.py` | replicate |
| 5 | Concentrated book, low turnover | `ira_marvin`, `darwin/constraints.py` | replicate |
| 6 | Proprietary model weights | — | skip |

Full text: run ingest after placing PDF in INCOMING or `_system/frameworks/`.

## Mandate alignment (IRA)

- Semiannual rebalance, **≤10%** one-way turnover
- 8–12 names, max **15%** per issue
- Marvin stance gate; ML champion only if OOS Sharpe ≥ 0.25 and ≥12 periods
- Plan: `_system/frameworks/darwin_ira_research_plan.md`
