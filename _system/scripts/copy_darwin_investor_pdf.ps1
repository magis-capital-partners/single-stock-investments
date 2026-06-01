# Copy Darwin AI Investments letter into the research vault (run on your PC).
# Usage (PowerShell):
#   .\copy_darwin_investor_pdf.ps1
#   .\copy_darwin_investor_pdf.ps1 -Source "C:\Users\werdn\Downloads\Darwin AI Investments - 1Q26.pdf"

param(
    [string]$Source = "$env:USERPROFILE\Downloads\Darwin AI Investments - 1Q26.pdf",
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$Dest = Join-Path $RepoRoot "_system\reference\quant-evolution\Darwin_AI_Investments_1Q26.pdf"

if (-not (Test-Path $Source)) {
    Write-Error "Source PDF not found: $Source"
    Write-Host "Place the file in Downloads or pass -Source explicitly."
    exit 1
}

New-Item -ItemType Directory -Force -Path (Split-Path $Dest) | Out-Null
Copy-Item -Path $Source -Destination $Dest -Force
Write-Host "Copied to $Dest"
Write-Host "Next: python _system/scripts/ingest_darwin_investor_pdf.py"
