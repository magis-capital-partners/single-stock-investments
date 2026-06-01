# Darwin AI Investments — source notes (Phase 0)

**Public positioning** ([darwinaiventures.com](https://darwinaiventures.com/)):

- Adaptive, **neural network–driven** investment strategies
- **Reinforcement learning** on complex financial markets
- Private; offerings only via confidential documents to qualified investors

**Local investor letter (run on your PC):**

```powershell
powershell -ExecutionPolicy Bypass -File _system/scripts/copy_darwin_investor_pdf.ps1
pip install pypdf
python3 _system/scripts/ingest_darwin_investor_pdf.py
```

Saves to `Darwin_AI_Investments_1Q26.pdf` (gitignored). Cloud agents cannot read `C:\Users\werdn\Downloads\`.

## Claims extracted (fill from PDF)

| # | Claim | Page | Maps to our stack |
|---|--------|------|-------------------|
| 1 | _pending_ | — | `darwin/encoder.py` latent factors |
| 2 | _pending_ | — | `darwin/ppo.py` turnover-aware reward |
| 3 | _pending_ | — | `darwin/genetic.py` policy population |

## Mandate alignment

See `_system/portfolio/darwin_mandate.json` — **IRA profile**: semiannual rebalance, 10% turnover cap, 12 names, 15% max weight, `ira_marvin` policy. Full download plan: `_system/frameworks/darwin_ira_research_plan.md`.
