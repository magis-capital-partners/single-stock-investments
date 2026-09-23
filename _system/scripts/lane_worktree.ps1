<#
.SYNOPSIS
    Keep a lane worktree on origin/main. Dot-sourced by whisper_supervisor.ps1
    and analysis_supervisor.ps1, and used only when they run with -SyncMain.

.DESCRIPTION
    Until 2026-09-23 both supervisors ran straight out of the primary checkout,
    and concurrent agents switch that checkout between branches. On 2026-09-11
    one moved it to a branch that had neither llm_ready.py nor
    analysis_supervisor.ps1. The supervisor that was already running lost its
    readiness probe and logged "model not ready" every 30 minutes for three
    days. After the 2026-09-15 reboot the at-logon task could not start at all:
    0xFFFD0000 is powershell.exe's exit code for a -File script that does not
    exist. The lane did no work for eleven days, and nothing reported it.

    The fix is the one the YouTube lane already had: run from a worktree
    nobody checks anything out in (ssi-local-lanes), and keep that worktree on
    main. This file is the "keep it on main" half: fetch, then a detached
    checkout of what was fetched.

    Rules, each learned elsewhere in this repo:

    * Never in the primary checkout. Moving HEAD there pulls the floor out from
      under whatever agent is working in it. A linked worktree's .git is a
      file and the primary checkout's is a directory; that is the test.
    * Never under a running lane. The Whisper daemon imports modules lazily
      for days, so rewriting _system/scripts beneath it mixes versions
      mid-run. Every lane takes the worktree mutex before it runs anything,
      and the sync checks the other lanes' single-instance mutexes after
      taking it. A mutex that exists means its supervisor is alive, which is
      a liveness test rather than an age test (see the batch lock files for
      why the difference matters).
    * Never blocks the lane. A failed or timed-out fetch logs and leaves the
      current checkout in place: stale code that runs beats a lane that
      silently does not. Git's output goes to files under a real timeout, for
      the reason vault_git.run_git gives: a pipe waits for an EOF that a
      grandchild such as git-remote-https can hold open indefinitely.
#>

function Invoke-LaneGit {
    param(
        [Parameter(Mandatory)] [string]   $Repo,
        [Parameter(Mandatory)] [string[]] $GitArgs,
        [int] $TimeoutSeconds = 600
    )
    $out = [System.IO.Path]::GetTempFileName()
    $err = [System.IO.Path]::GetTempFileName()
    $env:GIT_TERMINAL_PROMPT = '0'
    try {
        $proc = Start-Process -FilePath 'git' -ArgumentList $GitArgs -WorkingDirectory $Repo `
            -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
        # Without touching Handle first, ExitCode reads back as $null on 5.1.
        $null = $proc.Handle
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            & taskkill.exe /T /F /PID $proc.Id 2>&1 | Out-Null
            return [pscustomobject]@{ Code = -1; Output = "timed out after ${TimeoutSeconds}s" }
        }
        # Get-Content -Raw gives one string per file, or $null when it is empty.
        $streams = @((Get-Content -Raw -LiteralPath $out), (Get-Content -Raw -LiteralPath $err))
        $text = ($streams | Where-Object { $_ }) -join "`n"
        return [pscustomobject]@{ Code = $proc.ExitCode; Output = "$text".Trim() }
    }
    catch {
        return [pscustomobject]@{ Code = -1; Output = "$_" }
    }
    finally {
        Remove-Item -Path $out, $err -ErrorAction SilentlyContinue
    }
}

function Get-LastLine {
    param([string] $Text)
    $lines = @(($Text -split "`r?`n") | Where-Object { $_.Trim() })
    if ($lines.Count -eq 0) { return '' }
    return $lines[-1].Trim()
}

function Sync-LaneWorktree {
    <#
    Returns $true when the worktree is at origin/$Branch afterwards, $false when
    the sync was refused, deferred or failed. Callers ignore the result: every
    outcome is logged, and none of them stops the lane.
    #>
    param(
        [Parameter(Mandatory)] [string]      $Repo,
        [Parameter(Mandatory)] [scriptblock] $Logger,
        # Single-instance mutexes of the OTHER lanes that run from this
        # worktree. Never the caller's own, which it is holding.
        [string[]] $BusyMutexes = @(),
        [string]   $Branch = 'main',
        [string]   $TreeMutex = 'Global\ssi-lane-worktree',
        [int]      $TimeoutSeconds = 600,
        [int]      $WaitMinutes = 30
    )

    if (-not (Test-Path -LiteralPath (Join-Path $Repo '.git') -PathType Leaf)) {
        & $Logger "sync refused: $Repo is not a linked worktree, and HEAD is never moved in the primary checkout"
        return $false
    }

    # Taken even when the sync turns out to be deferred: a lane starting while
    # another one is mid-checkout must wait for the checkout to finish before
    # it runs anything from the tree.
    $tree = New-Object System.Threading.Mutex($false, $TreeMutex)
    $owned = $false
    try {
        try {
            $owned = $tree.WaitOne([TimeSpan]::FromMinutes($WaitMinutes))
        }
        catch [System.Threading.AbandonedMutexException] {
            # A previous holder died mid-sync. The mutex is ours now; the
            # checkout below repairs whatever it left half-written.
            $owned = $true
        }
        if (-not $owned) {
            & $Logger "sync skipped: $TreeMutex still held after $WaitMinutes min"
            return $false
        }

        foreach ($name in $BusyMutexes) {
            $other = $null
            $busy = $false
            try {
                $busy = [System.Threading.Mutex]::TryOpenExisting($name, [ref] $other)
            }
            catch {
                # Exists but cannot be opened, which still means it exists.
                $busy = $true
            }
            if ($other) { $other.Dispose() }
            if ($busy) {
                & $Logger "sync deferred: $name is held, so another lane is running from this worktree"
                return $false
            }
        }

        $before = (Invoke-LaneGit -Repo $Repo -GitArgs @('rev-parse', 'HEAD') -TimeoutSeconds 60).Output
        if ($before -notmatch '^[0-9a-f]{40}$') {
            & $Logger "sync failed: HEAD did not resolve in $Repo ($(Get-LastLine $before))"
            return $false
        }
        $from = $before.Substring(0, 11)
        $fetch = Invoke-LaneGit -Repo $Repo -GitArgs @('fetch', 'origin', $Branch) -TimeoutSeconds $TimeoutSeconds
        if ($fetch.Code -ne 0) {
            & $Logger ("sync failed at fetch (code {0}); staying on {1}: {2}" -f
                    $fetch.Code, $from, (Get-LastLine $fetch.Output))
            return $false
        }
        $target = (Invoke-LaneGit -Repo $Repo -GitArgs @('rev-parse', 'FETCH_HEAD') -TimeoutSeconds 60).Output
        if ($target -notmatch '^[0-9a-f]{40}$') {
            & $Logger "sync failed: FETCH_HEAD did not resolve ($(Get-LastLine $target)); staying on $from"
            return $false
        }
        $to = $target.Substring(0, 11)
        if ($target -eq $before) {
            & $Logger "sync: already at origin/$Branch $to"
            return $true
        }
        $checkout = Invoke-LaneGit -Repo $Repo -GitArgs @('checkout', '--detach', $target) -TimeoutSeconds $TimeoutSeconds
        if ($checkout.Code -ne 0) {
            & $Logger ("sync failed at checkout (code {0}); staying on {1}: {2}" -f
                    $checkout.Code, $from, (Get-LastLine $checkout.Output))
            return $false
        }
        & $Logger "sync: $from -> $to (origin/$Branch)"
        return $true
    }
    finally {
        if ($owned) { $tree.ReleaseMutex() }
        $tree.Dispose()
    }
}
