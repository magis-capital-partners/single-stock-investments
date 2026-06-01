# Copy Darwin AI Investments letter into the research vault (run on your PC).
# Usage (PowerShell):
#   .\copy_darwin_investor_pdf.ps1
#   .\copy_darwin_investor_pdf.ps1 -Source "C:\path\to\Darwin AI Investments - 1Q26.pdf"

param(
    [string]$Source = "",
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$Dest = Join-Path $RepoRoot "_system\reference\quant-evolution\Darwin_AI_Investments_1Q26.pdf"
$Frameworks = Join-Path $RepoRoot "_system\frameworks"
$Incoming = Join-Path $RepoRoot "_system\reference\quant-evolution\INCOMING"

function Find-DarwinPdf {
    if ($Source -and (Test-Path $Source)) { return $Source }
    if (Test-Path $Dest) { return $Dest }
    $names = @(
        "Darwin AI Investments - 1Q26.pdf",
        "Darwin_AI_Investments_1Q26.pdf"
    )
    foreach ($base in @($Frameworks, $Incoming, "$env:USERPROFILE\Downloads")) {
        foreach ($n in $names) {
            $p = Join-Path $base $n
            if (Test-Path $p) { return $p }
        }
    }
    if (Test-Path $Frameworks) {
        $hit = Get-ChildItem -Path $Frameworks -Filter "*Darwin*.pdf" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

$src = Find-DarwinPdf
if (-not $src) {
    Write-Error "Darwin PDF not found. Drop in _system\frameworks\ or pass -Source."
    exit 1
}

New-Item -ItemType Directory -Force -Path (Split-Path $Dest) | Out-Null
if ((Resolve-Path $src).Path -ne (Resolve-Path $Dest -ErrorAction SilentlyContinue).Path) {
    Copy-Item -Path $src -Destination $Dest -Force
    Write-Host "Copied $src → $Dest"
} else {
    Write-Host "Already at $Dest"
}
Write-Host "Next: pip install pypdf; python _system/scripts/ingest_darwin_investor_pdf.py"
