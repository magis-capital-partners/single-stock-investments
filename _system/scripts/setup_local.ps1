# Verify local research-vault setup for single-stock-investments.
param(
    [string]$VaultRoot = $env:RESEARCH_VAULT_ROOT
)

$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$ErrorActionPreference = "Stop"

if (-not $VaultRoot) {
    $candidates = @(
        (Join-Path $Root "_external/research-vault"),
        (Join-Path (Split-Path $Root -Parent) "research-vault")
    )
    foreach ($c in $candidates) {
        if (Test-Path (Join-Path $c "superinvestor-letters")) {
            $VaultRoot = $c
            break
        }
    }
}

if (-not $VaultRoot -or -not (Test-Path $VaultRoot)) {
    Write-Host "ERROR: Research vault not found." -ForegroundColor Red
    Write-Host ""
    Write-Host "Clone the private vault repo, then set RESEARCH_VAULT_ROOT:"
    Write-Host '  git clone git@github.com:magis-capital-partners/research-vault.git ..\research-vault'
    Write-Host '  $env:RESEARCH_VAULT_ROOT = "..\research-vault"'
    exit 1
}

$env:RESEARCH_VAULT_ROOT = (Resolve-Path $VaultRoot).Path
Write-Host "RESEARCH_VAULT_ROOT=$($env:RESEARCH_VAULT_ROOT)"

python -c @"
import json, os, sys
sys.path.insert(0, r'$($Root -replace '\\','\\')\_system\scripts')
from vault_paths import vault_status, letters_root
status = vault_status()
print(json.dumps(status, indent=2))
if not status.get('letters_exists'):
    raise SystemExit('superinvestor-letters missing in vault')
print('OK: vault setup verified')
"@

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Optional: add to your PowerShell profile:"
Write-Host "`$env:RESEARCH_VAULT_ROOT = `"$($env:RESEARCH_VAULT_ROOT)`""
