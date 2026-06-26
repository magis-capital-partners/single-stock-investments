# Publish workspace to GitHub and refresh dashboard data.
# GitHub Pages currently serves the legacy /docs folder on main (not dashboard/ directly).
# Keep dashboard/ as the working tree, then mirror it into docs/ before push.
$ErrorActionPreference = "Stop"
$Root = "C:\Users\werdn\Documents\Investing\Single Stock Investments"
Set-Location $Root

if (Get-Command gh -ErrorAction SilentlyContinue) {
    gh auth status 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Not logged in. Run: gh auth login --web"
        exit 1
    }
    $User = (gh api user -q .login)
} else {
    $User = "GoldmanDrew"
    Write-Host "gh CLI not found — assuming GitHub user: $User"
}

$RepoName = "single-stock-investments"

python _system/scripts/build_dashboard_data.py
robocopy dashboard docs /MIR /XD .git .wrangler /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
if ($LASTEXITCODE -gt 7) { throw "robocopy dashboard -> docs failed with exit code $LASTEXITCODE" }
git add dashboard docs
if (-not (git diff --staged --quiet)) {
    git commit -m "chore: refresh dashboard data"
}

git push -u origin main
Write-Host ""
Write-Host "Repo:    https://github.com/$User/$RepoName"
Write-Host "Pages:   https://$($User.ToLower()).github.io/$RepoName/"
Write-Host ""
Write-Host "If Pages is not live yet:"
Write-Host "  1. Settings -> General -> Change visibility -> Public"
Write-Host "  2. Settings -> Pages -> Build and deployment -> Source: GitHub Actions"
Write-Host "  3. Actions -> Deploy Dashboard (GitHub Pages) -> Run workflow"
