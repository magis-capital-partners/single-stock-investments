<#
.SYNOPSIS
    Run the Whisper and analysis lanes from their own worktree on main:
    create the worktree if it is missing, then point both scheduled tasks at it.

.DESCRIPTION
    Both tasks used to start their supervisor from the primary checkout, which
    concurrent agents switch between branches. lane_worktree.ps1 records what
    that cost -- eleven days without analysis, starting on 2026-09-11. This
    makes the arrangement the YouTube lane already had reproducible instead of
    something that exists only in one machine's Task Scheduler:

    * the worktree is sparse to _system, which is everything either lane reads
      at runtime (their import closure touches nothing else), and detached at
      origin/main, because main itself is checked out in the primary checkout
      and git allows a branch in only one worktree;
    * each task runs its supervisor from that worktree with -SyncMain, so the
      supervisor keeps the tree on main from then on.

    Safe to re-run. An existing worktree is left alone, and an existing task
    keeps its trigger, principal and settings; only its action is replaced.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File _system\scripts\install_local_lane_tasks.ps1
#>
[CmdletBinding()]
param(
    [string] $Worktree = 'C:\Users\drewg\Projects\dashboards\ssi-local-lanes',
    [string] $Branch   = 'main'
)

$ErrorActionPreference = 'Stop'
# Any checkout of this repository will do as the source: worktrees share one
# object store. This is the one the installer itself was run from.
$source = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Invoke-Git {
    param([string[]] $GitArgs)
    # git reports progress on stderr, which 5.1 turns into terminating errors
    # under 'Stop'. Judge it by its exit code instead.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & git @GitArgs 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    if ($code -ne 0) { throw "git $($GitArgs -join ' ') failed ($code): $($out -join ' | ')" }
    return $out
}

if (-not (Test-Path -LiteralPath (Join-Path $Worktree '.git'))) {
    Invoke-Git @('-C', $source, 'fetch', 'origin', $Branch) | Out-Null
    $sha = (Invoke-Git @('-C', $source, 'rev-parse', 'FETCH_HEAD') | Select-Object -Last 1).Trim()
    Invoke-Git @('-C', $source, 'worktree', 'add', '--no-checkout', '--detach', $Worktree, $sha) | Out-Null
    Invoke-Git @('-C', $Worktree, 'sparse-checkout', 'set', '--cone', '_system') | Out-Null
    Invoke-Git @('-C', $Worktree, 'read-tree', '-mu', 'HEAD') | Out-Null
    Write-Output "created $Worktree at $($sha.Substring(0, 11)) (origin/$Branch, sparse: _system)"
} else {
    Write-Output "worktree exists: $Worktree"
}

foreach ($name in 'whisper_supervisor.ps1', 'analysis_supervisor.ps1', 'lane_worktree.ps1') {
    if (-not (Test-Path -LiteralPath (Join-Path $Worktree "_system\scripts\$name"))) {
        throw "$Worktree has no _system\scripts\$name; the tasks would point at nothing"
    }
}

$user = "$env:USERDOMAIN\$env:USERNAME"
$lanes = @(
    @{ Task = 'SSI Whisper Backfill'; Script = 'whisper_supervisor.ps1'
       Description = 'Drains the podcast Whisper backlog until empty, from the ssi-local-lanes worktree kept on main. Single-instance via a global mutex; see _system/scripts/whisper_supervisor.ps1.' },
    @{ Task = 'SSI Podcast Analysis'; Script = 'analysis_supervisor.ps1'
       Description = 'Keeps the podcast and video analysis draining and the LM Studio model loaded, from the ssi-local-lanes worktree kept on main. See _system/scripts/analysis_supervisor.ps1.' }
)

foreach ($lane in $lanes) {
    $script = Join-Path $Worktree "_system\scripts\$($lane.Script)"
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -SyncMain" `
        -WorkingDirectory $Worktree
    if (Get-ScheduledTask -TaskName $lane.Task -ErrorAction SilentlyContinue) {
        Set-ScheduledTask -TaskName $lane.Task -Action $action | Out-Null
        $task = Get-ScheduledTask -TaskName $lane.Task
        $task.Description = $lane.Description
        $task | Set-ScheduledTask | Out-Null
    } else {
        # The settings the tasks were first registered with on 2026-09-06.
        $trigger   = New-ScheduledTaskTrigger -AtLogOn -User $user
        $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
        $settings  = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
            -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 5)
        Register-ScheduledTask -TaskName $lane.Task -Action $action -Trigger $trigger `
            -Principal $principal -Settings $settings -Description $lane.Description | Out-Null
    }
    Write-Output "$($lane.Task) -> $script -SyncMain"
}
