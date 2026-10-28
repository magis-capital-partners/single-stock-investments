param(
    [string]$RuntimeHome = (Join-Path $env:LOCALAPPDATA 'Magis/valuation-underwriting'),
    [switch]$Launch,
    [string]$Tickers = ''
)
$ErrorActionPreference = 'Stop'
$runtimeRoot = [IO.Path]::GetFullPath($RuntimeHome)
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $runtimeRoot 'source'))
if (-not $sourceRoot.StartsWith($runtimeRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Runtime source must stay inside the owned runtime directory.'
}
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$markerPath = Join-Path $runtimeRoot 'runtime-owner.json'
if (Test-Path -LiteralPath $markerPath) {
    $marker = Get-Content -Raw -LiteralPath $markerPath | ConvertFrom-Json
    if ($marker.repository -ne 'magis-capital-partners/single-stock-investments') { throw 'Unexpected runtime owner.' }
} else {
    $existing = Get-ChildItem -LiteralPath $runtimeRoot -Force | Where-Object { $_.Name -ne 'launch.ps1' }
    if ($existing) { throw 'Use a fresh runtime directory.' }
    @{ repository = 'magis-capital-partners/single-stock-investments'; purpose = 'local-codex-underwriting' } |
        ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath $markerPath
}
$env:GIT_TERMINAL_PROMPT = '0'
function Run-Git {
    & git @args
    if ($LASTEXITCODE -ne 0) { throw 'The isolated source update failed.' }
}
$newSource = -not (Test-Path -LiteralPath (Join-Path $sourceRoot '.git'))
if ($newSource) {
    Run-Git clone --filter=blob:none --sparse --no-checkout https://github.com/magis-capital-partners/single-stock-investments.git $sourceRoot
} else {
    $dirty = & git -C $sourceRoot status --porcelain --untracked-files=no
    if ($dirty) { throw 'The owned source has edits; preserve them before updating it.' }
}
$patterns = @('/_system/scripts/', '/_system/config/llm_usage_policy.json', '/_system/config/underwriting_policy.json',
        '/_system/prompts/valuation_underwriting.md', '/_system/portfolio/registry.json',
        '/_system/reference/valuation_identity_aliases.json', '/_system/reference/valuation_method_registry.json',
        '/_system/reference/valuation_listing_ratios.json', '/_system/reference/market-data/valuation_quotes/',
        '/_system/reference/market-data/valuation_fundamentals/', '/_system/reference/market-data/operating_kpis/',
        '/_system/data/shared_valuation_forecasts.json', '/_system/data/underwriting_queue.json',
        '/dashboard/data/core.json', '/dashboard/private-assets.json', '/*/research/valuation.json',
        '/*/research/underwriting_*.json', '/.github/workflows/valuation-underwriting.yml',
        '/.github/workflows/autonomous-compounders.yml')
Run-Git -C $sourceRoot sparse-checkout set --no-cone @patterns
$remote = & git -C $sourceRoot remote get-url origin
if ($remote -ne 'https://github.com/magis-capital-partners/single-stock-investments.git') { throw 'Unexpected runtime source remote.' }
Run-Git -C $sourceRoot fetch -q origin main
Run-Git -C $sourceRoot checkout -q --detach origin/main
$workerArgs = @((Join-Path $sourceRoot '_system/scripts/underwriting_local.py'), '--home', $runtimeRoot)
if ($Launch) { $workerArgs += '--launch' }
if ($Tickers) { $workerArgs += @('--tickers', $Tickers) }
& python @workerArgs
if ($LASTEXITCODE -ne 0) { throw 'Local underwriting did not finish; saved receipts remain in the runtime.' }
