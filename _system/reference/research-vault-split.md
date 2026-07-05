# Research vault split — operator guide

Two-repo layout after the vault migration:

| Repository | Visibility | Contents |
|------------|------------|----------|
| `magis-capital-partners/research-vault` | **Private** (Magis org) | Superinvestor letters, HK PDFs, SumZero, licensed sources |
| `magis-capital-partners/single-stock-investments` | Your choice (see billing) | Code, portfolio, CI, dashboard, derived JSON |

Path resolution: `_system/scripts/vault_paths.py`  
CI clone: `_system/scripts/ci_checkout_vault.sh`  
Local verify: `_system/scripts/setup_local.ps1`

## Manual steps (required once)

### 1. Create the private vault repo on GitHub

1. GitHub ? **magis-capital-partners** org ? **New repository**
2. Name: `research-vault`
3. Visibility: **Private**
4. Do **not** initialize with README (you will push local content)

### 2. Extract and push vault content

```powershell
cd C:\Users\drewg\Projects\dashboards\single-stock-investments
powershell -ExecutionPolicy Bypass -File _system/scripts/migrate_extract_vault.ps1

cd ..\research-vault
git init
git add -A
git commit -m "Initial research vault import from single-stock-investments."
git branch -M main
git remote add origin git@github.com:magis-capital-partners/research-vault.git
git push -u origin main
```

### 3. Remove vault trees from the operational repo

```powershell
cd C:\Users\drewg\Projects\dashboards\single-stock-investments
bash _system/scripts/migrate_remove_vault_from_ops.sh
# or on Windows without bash: git rm -rf _system/reference/superinvestor-letters
```

Commit and push the ops repo changes.

### 4. Configure GitHub Actions secrets (operational repo)

**Settings ? Secrets and variables ? Actions ? New repository secret**

| Secret | Value |
|--------|-------|
| `RESEARCH_VAULT_REPO_URL` | `https://github.com/magis-capital-partners/research-vault.git` |
| `RESEARCH_VAULT_CLONE_TOKEN` | Fine-grained PAT: **Contents read+write** on `research-vault` only |

Create the PAT under a machine user or your account with access to the private vault repo.

### 5. Local development

```powershell
$env:RESEARCH_VAULT_ROOT = "C:\Users\drewg\Projects\dashboards\research-vault"
powershell -ExecutionPolicy Bypass -File _system/scripts/setup_local.ps1
```

### 6. GitHub Actions minutes strategy (choose one)

| Option | Action |
|--------|--------|
| **Unlimited hosted minutes** | Make `single-stock-investments` **public** (after history scrub if HK PDFs were ever committed) |
| **Stay private** | Add a **self-hosted runner** and set `runs-on: self-hosted` on high-burn workflows |
| **Same org, two private repos** | Does **not** increase minute pool — avoid expecting relief from vault split alone |

OAuth-gated GitHub Pages does **not** hide git clone data if the ops repo is public.

### 7. Verify CI

1. **Actions ? Letter Backfill ? Run workflow** (max_files: 5 for smoke test)
2. Confirm commit lands in `research-vault` and dashboard JSON updates in ops repo
3. **Deploy Dashboard** chains as before

## Workflow changes

| Workflow | Vault interaction |
|----------|-------------------|
| `letter-backfill.yml` | Commits letters to vault; rebuilds ops dashboard |
| `drive-intake-sync`, `activist-scan-sync`, `darwin-refresh`, `dashboard-pages` | Clone vault before `rebuild-data` |
| Marvin / Vicki / daily-sync | Use `RESEARCH_VAULT_ROOT` / `HK_PDFS_ROOT` from vault |

## Composite actions

| Action | Purpose |
|--------|---------|
| `.github/actions/checkout-vault` | Clone/update research-vault |
| `.github/actions/commit-vault` | Push vault commits (letter backfill) |
