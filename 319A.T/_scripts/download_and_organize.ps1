# 319A.T — download the company IR library (English index, JP and EN PDFs).
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Repo = Split-Path $Root -Parent
python (Join-Path $PSScriptRoot "download_ir_library.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
