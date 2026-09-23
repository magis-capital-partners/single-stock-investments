"""The lane worktree sync, run for real against throwaway repositories.

On 2026-09-11 an agent switched the primary checkout to a branch that had
neither llm_ready.py nor analysis_supervisor.ps1. The analysis lane, which ran
out of that checkout, did no work for eleven days: first a "model not ready"
loop, then, after a reboot, a scheduled task that could not find its own
script. Both lanes now run from a worktree of their own, and lane_worktree.ps1
keeps it on origin/main.

These tests execute the PowerShell rather than grepping it. Every property
here is behavioural -- which HEAD moves, which does not, what a held mutex does
-- and the first draft had a scoping bug that no text match would find: a
helper parameter named $Log shadows the supervisors' own $log (PowerShell
variables are case-insensitive and dynamically scoped), so Write-Log handed the
callback itself to Add-Content as its -Path and every sync threw. The
supervisors catch that and carry on, so the lane would have run unsynced
forever with one line a day to say so. The harness below reproduces the
supervisors' Write-Log shape for that reason.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
HELPER = SCRIPTS / "lane_worktree.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
GIT = shutil.which("git")

HARNESS = r"""
param([string] $Helper, [string] $Repo, [string] $LogPath, [string] $Tree, [string] $Busy)
$ErrorActionPreference = 'Stop'
# The supervisors' shape: a script-level $log that Write-Log appends to, and
# the sync called from that same scope.
$log = $LogPath
function Write-Log {
    param([string] $Message)
    Add-Content -Path $log -Value $Message -Encoding utf8
}
. $Helper
$hold = $null
$busyList = @()
if ($Busy) {
    $hold = New-Object System.Threading.Mutex($false, $Busy)
    $busyList = @($Busy)
}
try {
    $ok = Sync-LaneWorktree -Repo $Repo -Logger { param($m) Write-Log $m } `
        -BusyMutexes $busyList -TreeMutex $Tree -TimeoutSeconds 120 -WaitMinutes 1
}
finally {
    if ($hold) { $hold.Dispose() }
}
if ($ok) { 'RESULT=True' } else { 'RESULT=False' }
"""


def git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        [GIT, "-c", "user.name=lane-test", "-c", "user.email=lane-test@example.invalid", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


@unittest.skipUnless(POWERSHELL and GIT, "needs PowerShell and git")
class SyncLaneWorktreeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.base = base
        # A plain repository serves as origin: fetching from one is fine, and
        # committing straight into it skips a push that takes seconds here.
        self.origin = base / "origin"
        subprocess.run([GIT, "init", "-q", "-b", "main", str(self.origin)], check=True)
        (self.origin / "a.txt").write_text("one\n", encoding="utf-8")
        git(self.origin, "add", "a.txt")
        git(self.origin, "commit", "-q", "-m", "one")
        self.first = git(self.origin, "rev-parse", "HEAD")

        # The primary checkout, and the lane's linked worktree beside it.
        self.primary = base / "primary"
        subprocess.run([GIT, "clone", "-q", str(self.origin), str(self.primary)], check=True)
        self.lane = base / "lane"
        git(self.primary, "worktree", "add", "-q", "--detach", str(self.lane), "HEAD")

        # main moves on after the lane was created.
        (self.origin / "a.txt").write_text("two\n", encoding="utf-8")
        git(self.origin, "commit", "-q", "-am", "two")
        self.second = git(self.origin, "rev-parse", "HEAD")

        self.harness = base / "harness.ps1"
        self.harness.write_text(HARNESS, encoding="utf-8")
        self.tree = f"Local\\ssi-lane-test-tree-{uuid.uuid4().hex}"

    def tearDown(self):
        self._tmp.cleanup()

    def sync(self, repo: Path, busy: str | None = None) -> tuple[bool, str]:
        log = self.base / f"supervisor-{uuid.uuid4().hex}.log"
        cmd = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.harness),
               "-Helper", str(HELPER), "-Repo", str(repo), "-LogPath", str(log), "-Tree", self.tree]
        if busy:
            cmd += ["-Busy", busy]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=self.base)
        self.assertEqual(out.returncode, 0, out.stderr)
        ok = "RESULT=True" in out.stdout
        text = log.read_text(encoding="utf-8-sig") if log.exists() else ""
        return ok, text

    def test_moves_a_linked_worktree_to_origin_main(self):
        ok, log = self.sync(self.lane)
        self.assertTrue(ok, log)
        self.assertEqual(git(self.lane, "rev-parse", "HEAD"), self.second)
        self.assertEqual((self.lane / "a.txt").read_text(encoding="utf-8").strip(), "two")
        self.assertIn(f"sync: {self.first[:11]} -> {self.second[:11]} (origin/main)", log)

        ok, log = self.sync(self.lane)
        self.assertTrue(ok, log)
        self.assertIn("already at origin/main", log)

    def test_messages_reach_the_supervisors_log_and_nowhere_else(self):
        """A helper variable that shadows the supervisors' $log breaks Write-Log."""
        before = {p.name for p in self.base.iterdir()}
        ok, log = self.sync(self.lane)
        self.assertTrue(ok)
        self.assertIn("sync:", log)
        created = {p.name for p in self.base.iterdir()} - before
        self.assertEqual(len(created), 1, f"unexpected files: {sorted(created)}")
        self.assertTrue(next(iter(created)).startswith("supervisor-"))

    def test_never_moves_the_primary_checkout(self):
        """Other agents work in it; its HEAD is theirs."""
        head = git(self.primary, "rev-parse", "HEAD")
        ok, log = self.sync(self.primary)
        self.assertFalse(ok)
        self.assertIn("sync refused", log)
        self.assertEqual(git(self.primary, "rev-parse", "HEAD"), head)

    def test_defers_while_another_lane_is_running(self):
        """Rewriting the scripts under a live Whisper daemon mixes versions mid-run."""
        busy = f"Local\\ssi-lane-test-busy-{uuid.uuid4().hex}"
        ok, log = self.sync(self.lane, busy=busy)
        self.assertFalse(ok)
        self.assertIn(f"sync deferred: {busy} is held", log)
        self.assertEqual(git(self.lane, "rev-parse", "HEAD"), self.first)

    def test_a_failed_fetch_leaves_the_checkout_in_place(self):
        """Stale code that runs beats a lane that does not."""
        git(self.primary, "remote", "set-url", "origin", str(self.base / "missing.git"))
        ok, log = self.sync(self.lane)
        self.assertFalse(ok)
        self.assertIn(f"sync failed at fetch", log)
        self.assertIn(f"staying on {self.first[:11]}", log)
        self.assertEqual(git(self.lane, "rev-parse", "HEAD"), self.first)

    def test_local_edits_are_refused_not_overwritten(self):
        (self.lane / "a.txt").write_text("edited by hand\n", encoding="utf-8")
        ok, log = self.sync(self.lane)
        self.assertFalse(ok)
        self.assertIn("sync failed at checkout", log)
        self.assertEqual((self.lane / "a.txt").read_text(encoding="utf-8"), "edited by hand\n")
        self.assertEqual(git(self.lane, "rev-parse", "HEAD"), self.first)


class SupervisorWiringTests(unittest.TestCase):
    """Each supervisor must defer to the other one, and never to itself."""

    MUTEX = re.compile(r"New-Object System\.Threading\.Mutex\(\$false, '([^']+)'\)")
    BUSY = re.compile(r"-BusyMutexes @\(([^)]*)\)")

    def wiring(self, name: str) -> tuple[str, list[str], str]:
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        own = self.MUTEX.findall(text)
        self.assertEqual(len(own), 1, f"{name} should hold exactly one single-instance mutex")
        busy = self.BUSY.findall(text)
        self.assertEqual(len(busy), 1, f"{name} should sync exactly once in its source")
        names = re.findall(r"'([^']+)'", busy[0])
        return own[0], names, text

    def test_each_supervisor_defers_to_the_other_and_not_itself(self):
        whisper_own, whisper_busy, whisper = self.wiring("whisper_supervisor.ps1")
        analysis_own, analysis_busy, analysis = self.wiring("analysis_supervisor.ps1")
        # Listing its own mutex would defer every sync forever, silently.
        self.assertNotIn(whisper_own, whisper_busy)
        self.assertNotIn(analysis_own, analysis_busy)
        self.assertIn(analysis_own, whisper_busy)
        self.assertIn(whisper_own, analysis_busy)
        for text in (whisper, analysis):
            self.assertIn("[switch] $SyncMain", text)
            self.assertIn("lane_worktree.ps1", text)
            self.assertIn("-Logger", text)


if __name__ == "__main__":
    unittest.main()
