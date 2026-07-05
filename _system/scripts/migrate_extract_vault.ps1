# One-time migration: extract vault corpora to sibling research-vault (Windows).
# Usage: powershell -ExecutionPolicy Bypass -File _system/scripts/migrate_extract_vault.ps1
param(
    [string]$Target = ""
)

$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not $Target) {
    $Target = Join-Path (Split-Path $Root -Parent) "research-vault"
}
$ErrorActionPreference = "Stop"

function Copy-Tree {
    param([string]$SrcName, [string]$DestName = $SrcName)
    $src = Join-Path $Root "_system/reference/$SrcName"
    $dest = Join-Path $Target $DestName
    if (Test-Path $src) {
        Write-Host "Copying $SrcName -> $DestName/"
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        robocopy $src $dest /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $SrcName (exit $LASTEXITCODE)" }
    } else {
        Write-Host "Skip missing $SrcName"
    }
}

New-Item -ItemType Directory -Force -Path $Target | Out-Null
Copy-Tree "superinvestor-letters"
Copy-Tree "investment-wisdom"
Copy-Tree "sumzero-research"

$dropbox = Join-Path $Root "_system/dropbox_ingestion"
if (Test-Path $dropbox) {
    $dest = Join-Path $Target "dropbox-ingestion"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    robocopy $dropbox $dest /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
}

$template = Join-Path $Root "_system/migration/research-vault-template"
foreach ($f in @("README.md", ".gitignore")) {
    $src = Join-Path $template $f
    $dest = Join-Path $Target $f
    if ((Test-Path $src) -and -not (Test-Path $dest)) {
        Copy-Item $src $dest
    }
}

$env:RESEARCH_VAULT_ROOT = $Target
python -c @"
import json, os, sys
sys.path.insert(0, r'$($Root -replace '\\','/')/_system/scripts')
os.environ['RESEARCH_VAULT_ROOT'] = r'$($Target -replace '\\','/')'
from vault_paths import vault_status
print(json.dumps(vault_status(), indent=2))
"@

Write-Host ""
Write-Host "Vault extract complete: $Target"
