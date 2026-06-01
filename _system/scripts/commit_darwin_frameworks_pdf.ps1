# Commit and push Darwin 1Q26 PDF from _system/frameworks/
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)
Set-Location $RepoRoot
$Frameworks = Join-Path $RepoRoot "_system\frameworks"
$names = @("Darwin AI Investments - 1Q26.pdf", "Darwin_AI_Investments_1Q26.pdf")
$src = $null
foreach ($n in $names) {
    $p = Join-Path $Frameworks $n
    if (Test-Path $p) { $src = $p; break }
}
if (-not $src) {
    $hit = Get-ChildItem -Path $Frameworks -Filter "*Darwin*.pdf" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { $src = $hit.FullName }
}
if (-not $src) {
    Write-Error "Darwin PDF not found in $Frameworks"
    exit 1
}
$rel = $src.Substring($RepoRoot.Length + 1)
git add -- $rel
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "Nothing new to commit: $rel"
    exit 0
}
git commit -m "chore: add Darwin AI Investments 1Q26 investor letter (frameworks)"
git push origin HEAD
Write-Host "Pushed $rel"
