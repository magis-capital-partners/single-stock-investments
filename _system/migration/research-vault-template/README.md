# research-vault

Private repository for licensed and proprietary investment reference material used by [single-stock-investments](https://github.com/magis-capital-partners/single-stock-investments).

**Do not make this repository public.**

## Layout

| Path | Contents |
|------|----------|
| `superinvestor-letters/` | Hedge fund / superinvestor LP letters (`.txt` extracts, indexes, manifests; PDFs local-only) |
| `investment-wisdom/` | Horizon Kinetics PDFs, MOI, curated extracts |
| `sumzero-research/` | SumZero licensed research PDFs |
| `dropbox-ingestion/` | Stahl / SumZero Dropbox archive metadata and parsed text |

## Local clone (Magis org members)

```powershell
cd C:\Users\drewg\Projects\dashboards
git clone git@github.com:magis-capital-partners/research-vault.git
git clone git@github.com:magis-capital-partners/single-stock-investments.git
$env:RESEARCH_VAULT_ROOT = "C:\Users\drewg\Projects\dashboards\research-vault"
```

The operational repo resolves paths via `_system/scripts/vault_paths.py`.

## CI secrets (operational repo)

| Secret | Purpose |
|--------|---------|
| `RESEARCH_VAULT_REPO_URL` | `https://github.com/magis-capital-partners/research-vault.git` |
| `RESEARCH_VAULT_CLONE_TOKEN` | Fine-grained PAT with **Contents: Read and write** on this repo |

Letter backfill commits corpus changes here; dashboard JSON commits go to the operational repo.
