<#
.SYNOPSIS
    Keep the local-model analysis draining -- podcasts and videos -- and keep its
    model server up.

.DESCRIPTION
    Companion to whisper_supervisor.ps1, and written after the same lesson: the
    batch is deliberately quittable and nothing was restarting it. On 2026-09-03
    analyze_podcast_batch stopped at 16:32Z with 826 of 1,068 eligible episodes
    unanalysed, and it stayed stopped for three days while the Whisper backfill
    -- which does have a supervisor -- went on producing transcripts for it. The
    lane read as healthy because nothing reports on a process that simply is not
    there.

    **The model server is part of the job, not a precondition.** The batch exits
    cleanly on LocalLLMUnavailable, which is correct for the batch and useless on
    its own: after the 2026-09-05 reboot the LM Studio app came back but with no
    model loaded and no server listening, so every restart would have exited in
    seconds. This supervisor therefore proves the endpoint before each run and
    loads the model itself if it has to. A supervisor that only restarts the
    thing that failed would have looped 8,000 times against a dead port.

    **Waits rather than exits when the queue is empty.** Unlike the Whisper
    backlog this queue refills: Whisper is still draining ~670 episodes into it,
    and the weekly podcast refresh adds more. Exiting on empty would mean the
    analyser is missing exactly when new transcripts land. Use -ExitWhenEmpty for
    one-shot runs.

    **Single instance.** Two analysers over one corpus duplicate work and race
    each other's vault pushes -- the failure that cost roughly a third of a
    night's transcription when two Whisper daemons ran on 2026-08-25. A global
    mutex makes it impossible on this host; the batch's own lock file is the
    second line, not the first.

    **Two queues, one supervisor.** The video corpus needs the same local model
    as the podcast one, and running both at once is the mistake this whole file
    is shaped around -- Whisper beside llama-server measured 5.5x slower than
    the two in sequence. A second supervisor with its own mutex would have
    exactly that effect, and giving both supervisors the *same* mutex would be
    worse: this one holds it while idling for an hour on an empty queue, so the
    video lane would simply never run. One process draining both queues is the
    only arrangement where the constraint holds by construction.

    Videos go first while any remain. The corpus is 63 items against roughly
    eight hundred episodes, so it drains in a night and is thereafter a trickle
    of one or two a day -- after which this lane is almost always empty and the
    podcast queue has the box to itself.

.PARAMETER Model
    Identifier the batch asks the server for. Must match what -ModelPath is
    loaded as; qwen-gpu is what _system/agents/PODCAST.md documents.

.PARAMETER Hours
    Length of one batch run before the supervisor re-checks the endpoint and the
    queue. Not a limit on total work -- the loop restarts it.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File _system\scripts\analysis_supervisor.ps1
#>
[CmdletBinding()]
param(
    [string] $Model      = 'qwen-gpu',
    [string] $ModelPath  = 'qwen/qwen3.5-9b',
    # One 12,000-character chunk is ~3,500 tokens and the reply is capped at
    # 3,000, so 8192 -- LM Studio's default -- leaves no room for the prompt.
    [int]    $ContextLength = 16384,
    [int]    $Hours      = 8,
    # The batch checkpoints to the vault after every episode, so this interval
    # is a ceiling rather than the usual cadence.
    [int]    $PushMins   = 15,
    [int]    $IdleMins   = 60,
    [int]    $MinBackoff = 120,
    [int]    $MaxBackoff = 1800,
    [int]    $MaxLogMB   = 32,
    [switch] $ExitWhenEmpty
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repo

$logDir = Join-Path $repo 'tmp'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'analysis_supervisor.log'

function Write-Log {
    param([string] $Message)
    $line = '[{0}] {1}' -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $Message
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding utf8
}

function Rotate-Log {
    if ((Test-Path $log) -and ((Get-Item $log).Length -gt ($MaxLogMB * 1MB))) {
        Move-Item -Path $log -Destination "$log.1" -Force
    }
}

# --- model server ----------------------------------------------------------
# Readiness is a real completion, not a reachability check -- llm_ready.py
# explains why at length. The short version: on 2026-09-06 a GET on
# http://localhost:1234/v1/models passed while every chat call returned HTTP
# 400, because that endpoint rejects the `json_object` response format the
# analyser uses and llm_local prefers it over the internal server whenever it
# answers. Starting :1234 is therefore not a repair, it is the fault. This
# supervisor never starts it; it loads the model and lets llm_local discover
# LM Studio's internal llama-server on its rotating port.
$lms    = Join-Path $env:USERPROFILE '.lmstudio\bin\lms.exe'
$python = 'python'

function Get-Remaining {
    # -1 means "could not tell", which the caller must not confuse with zero:
    # treating an unreadable status as an empty queue is how a lane goes quiet
    # while reporting healthy.
    param([string] $BatchPath)
    $json = & $python $BatchPath '--status' | Out-String
    try   { return [int]((ConvertFrom-Json $json).remaining) }
    catch { return -1 }
}

function Test-ModelReady {
    & $python (Join-Path $repo '_system\scripts\llm_ready.py') '--model' $Model | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Start-ModelServer {
    # lms writes progress to stderr, which Windows PowerShell 5.1 turns into
    # ErrorRecords that would trip $ErrorActionPreference = 'Stop'. Drop to
    # Continue around the calls and judge them by the probe, not by their exit.
    if (-not (Test-Path $lms)) {
        Write-Log "lms CLI not found at $lms; cannot load the model"
        return $false
    }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # Both numbers are load-time and neither has a safe default here. The
        # stock context is 8192, under the ~7k tokens one 12,000-character chunk
        # plus a 3,000-token reply needs; the stock parallelism is 4, which
        # quadruples the KV cache on a host that already sits under 1 GB free.
        Write-Log "model not ready; loading $ModelPath (ctx=$ContextLength parallel=1)"
        & $lms load $ModelPath --identifier $Model --gpu max `
              '-c' "$ContextLength" --parallel 1 -y 2>&1 | Out-Null
    } finally {
        $ErrorActionPreference = $prev
    }
    return (Test-ModelReady)
}

# --- single instance -------------------------------------------------------
$mutex = New-Object System.Threading.Mutex($false, 'Global\ssi-podcast-analysis')
if (-not $mutex.WaitOne(0)) {
    Write-Log 'another analysis supervisor already holds the lock; exiting'
    exit 0
}

$batch      = Join-Path $repo '_system\scripts\analyze_podcast_batch.py'
$videoBatch = Join-Path $repo '_system\scripts\analyze_video_batch.py'
$env:PYTHONUNBUFFERED = '1'

Write-Log "supervisor start: model=$Model hours=$Hours push=${PushMins}m repo=$repo"

$backoff = $MinBackoff
try {
    while ($true) {
        Rotate-Log

        if (-not (Test-ModelReady)) {
            if (-not (Start-ModelServer)) {
                Write-Log "model still not answering; retrying in $backoff s"
                Start-Sleep -Seconds $backoff
                $backoff = [Math]::Min($backoff * 2, $MaxBackoff)
                continue
            }
            Write-Log "model ready ($Model)"
        }

        # Ask each batch what is left. Each is the only thing that knows what
        # "eligible" means for its own corpus -- 25 KB of text surviving
        # per-show boilerplate removal for podcasts, an admitted relevance gate
        # for videos -- and both re-derive it from disk every time.
        $videoRemaining = Get-Remaining $videoBatch
        $remaining      = Get-Remaining $batch

        if ($remaining -lt 0 -and $videoRemaining -lt 0) {
            Write-Log "could not read analysis status; retrying in $backoff s"
            Start-Sleep -Seconds $backoff
            $backoff = [Math]::Min($backoff * 2, $MaxBackoff)
            continue
        }

        # Videos first while any remain: a small corpus that finishes, ahead of
        # a large one that is always refilling.
        if ($videoRemaining -gt 0) {
            $activeBatch = $videoBatch
            $activeLane  = 'video'
            $activeCount = $videoRemaining
        } else {
            $activeBatch = $batch
            $activeLane  = 'podcast'
            $activeCount = $remaining
        }

        if ($activeCount -le 0) {
            if ($ExitWhenEmpty) {
                Write-Log 'queue empty; supervisor done'
                break
            }
            # Whisper is still feeding this queue; idling is the working state,
            # not the finished one.
            Write-Log "both queues empty; re-checking in $IdleMins m"
            Start-Sleep -Seconds ($IdleMins * 60)
            continue
        }

        Write-Log "starting $activeLane batch ($activeCount remaining; video=$videoRemaining podcast=$remaining)"
        $started = Get-Date
        # Not Tee-Object: on 5.1 its -FilePath has no encoding parameter and
        # writes UTF-16LE, which interleaves with the UTF-8 Write-Log appends
        # and leaves the log unreadable. Echo and append explicitly.
        & $python '-u' $activeBatch '--model' $Model '--hours' "$Hours" '--push-every-minutes' "$PushMins" 2>&1 |
            ForEach-Object {
                Write-Host $_
                Add-Content -Path $log -Value $_ -Encoding utf8
            }
        $code = $LASTEXITCODE
        $ran  = [int]((Get-Date) - $started).TotalSeconds
        Write-Log "$activeLane batch exited code=$code after ${ran}s"

        # A run that did real work resets the backoff; one that died immediately
        # is a signal, not a blip. 600s is roughly one slow episode, so anything
        # under it means the batch never got started.
        if ($ran -ge 600) { $backoff = $MinBackoff }
        Write-Log "sleeping $backoff s before restart"
        Start-Sleep -Seconds $backoff
        if ($ran -lt 600) { $backoff = [Math]::Min($backoff * 2, $MaxBackoff) }
    }
}
finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
    Write-Log 'supervisor exit'
}
