#!/usr/bin/env python3
"""How the YouTube lane reports its two pushes to the scheduler.

From 2026-09-21 to 2026-09-23 every scheduled run logged "vault push failed"
and exited 0. Four untracked letters in the research vault collided with an
upstream ingest, `git pull --rebase` refused to check out over them, and three
days of corpus commits sat unpushed on the workstation while the task read
green. The log kept only the command that failed, not git's reason.

The push tests use real throwaway repositories, as test_vault_git does: the
failure is a specific git refusal, and a mocked git would only restate it.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import youtube_lane as lane  # noqa: E402
from vault_git import LOCK_NAME  # noqa: E402

MESSAGE = "chore(videos): transcript refresh 2026-09-23T14:15:12Z"
LETTERS = [f"letters/Eaglestone/letter{i}.pdf" for i in range(1, 5)]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def _configure(repo: Path) -> None:
    for key, value in (("user.email", "t@example.com"), ("user.name", "t"),
                       ("commit.gpgsign", "false"), ("core.autocrlf", "false"),
                       ("core.longpaths", "true")):
        _git(repo, "config", key, value)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class PushVaultTests(unittest.TestCase):
    """push_vault against a vault clone and the origin it pushes to."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.origin = self.base / "origin.git"
        self.vault = self.base / "vault"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        _git(self.origin, "config", "core.longpaths", "true")
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.vault)], check=True)
        _configure(self.vault)
        _git(self.vault, "remote", "add", "origin", str(self.origin))
        _write(self.vault / "videos" / "insights.json", "{}\n")
        _git(self.vault, "add", "-A")
        _git(self.vault, "commit", "-qm", "seed")
        _git(self.vault, "push", "-q", "origin", "main")

        self.lines: list[str] = []
        for patch in (mock.patch.object(lane, "videos_root", return_value=self.vault / "videos"),
                      mock.patch.object(lane, "log", side_effect=self.lines.append)):
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def _upstream(self, message: str, files: dict[str, str]) -> None:
        """Another writer lands a commit on origin, as the vault's ingest does."""
        other = self.base / "other"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(other)], check=True)
        _configure(other)
        for rel, text in files.items():
            _write(other / rel, text)
        _git(other, "add", "-A")
        _git(other, "commit", "-qm", message)
        _git(other, "push", "-q", "origin", "main")

    def _failure(self) -> str:
        return next(line for line in self.lines if line.startswith("vault push failed"))

    def _assert_left_clean(self) -> None:
        """The next writer must find no rebase in progress and no lock held."""
        git_dir = self.vault / ".git"
        for leftover in ("rebase-merge", "rebase-apply", "index.lock", LOCK_NAME):
            self.assertFalse((git_dir / leftover).exists(), leftover)

    def test_nothing_to_commit_is_none_not_a_failure(self):
        self.assertIsNone(lane.push_vault(MESSAGE))
        self.assertIn("vault: nothing to commit", self.lines)

    def test_a_completed_push_is_true(self):
        _write(self.vault / "videos" / "new.txt", "caption\n")
        self.assertIs(lane.push_vault(MESSAGE), True)
        self.assertEqual(_git(self.origin, "log", "-1", "--format=%s", "main"), MESSAGE)

    def test_untracked_files_blocking_the_rebase_fail_the_push_and_say_why(self):
        """2026-09-21..23: untracked letters in the vault, the same paths
        committed upstream by an ingest, and a pull --rebase that refused to
        check out over them."""
        self._upstream("ingest letters", {rel: "upstream\n" for rel in LETTERS})
        for rel in LETTERS:
            _write(self.vault / rel, "local\n")
        _write(self.vault / "videos" / "new.txt", "caption\n")

        self.assertIs(lane.push_vault(MESSAGE), False)

        failure = self._failure()
        self.assertIn("pull --rebase origin main", failure)
        self.assertIn("untracked working tree files would be overwritten", failure)
        self.assertIn(LETTERS[0], failure)
        # Stranded rather than lost: the commit waits locally for the next run,
        # and nobody's untracked files were touched.
        self.assertEqual(_git(self.vault, "log", "-1", "--format=%s"), MESSAGE)
        self.assertEqual(_git(self.origin, "log", "-1", "--format=%s", "main"), "ingest letters")
        self.assertEqual((self.vault / LETTERS[0]).read_text(encoding="utf-8"), "local\n")
        self._assert_left_clean()

    def test_a_rebase_conflict_fails_the_push_names_the_file_and_is_aborted(self):
        self._upstream("rewrite the catalog", {"videos/insights.json": '{"theirs": 1}\n'})
        _write(self.vault / "videos" / "insights.json", '{"ours": 1}\n')

        self.assertIs(lane.push_vault(MESSAGE), False)

        # git names the conflicted file on stdout; stderr only says a commit
        # could not be applied.
        self.assertIn("Merge conflict in videos/insights.json", self._failure())
        self.assertEqual(_git(self.vault, "log", "-1", "--format=%s"), MESSAGE)
        self._assert_left_clean()

    def test_waiting_out_the_lock_is_a_failure_not_a_skip(self):
        _write(self.vault / "videos" / "new.txt", "caption\n")
        timeout = TimeoutError("vault git lock not acquired within 900s")
        with mock.patch.object(lane, "vault_lock", side_effect=timeout):
            self.assertIs(lane.push_vault(MESSAGE), False)
        self.assertIn("lock not acquired", self._failure())

    def test_an_unwind_that_times_out_still_returns(self):
        """The dashboard publish runs after this. On 2026-09-17 a plain `git
        commit` in the vault outlived its 300s timeout; an abort that did the
        same must not escape and take the publish with it."""
        real = lane.run_git

        def git(repo, *args, **kwargs):
            if "pull" in args:
                raise subprocess.CalledProcessError(1, ["git", *args], "", "fatal: unable to access\n")
            if args[:2] == ("rebase", "--abort"):
                raise subprocess.TimeoutExpired(["git", *args], kwargs.get("timeout"))
            return real(repo, *args, **kwargs)

        _write(self.vault / "videos" / "new.txt", "caption\n")
        with mock.patch.object(lane, "run_git", side_effect=git):
            self.assertIs(lane.push_vault(MESSAGE), False)
        self.assertTrue(any(line.startswith("vault unwind failed") for line in self.lines))


class DescribeFailureTests(unittest.TestCase):
    def test_the_reason_survives_a_long_preamble(self):
        preamble = [f" * branch main -> FETCH_HEAD ({i})" for i in range(30)]
        verdict = [
            "error: The following untracked working tree files would be overwritten by checkout:",
            "\tletters/Eaglestone/letter1.pdf",
            "Please move or remove them before you switch branches.",
            "Aborting",
            "error: could not detach HEAD",
        ]
        exc = subprocess.CalledProcessError(1, ["git", "pull", "--rebase", "origin", "main"],
                                            output="", stderr="\n".join(preamble + verdict) + "\n")
        text = lane.describe_failure(exc)
        self.assertTrue(text.startswith("`git pull --rebase origin main` exited 1"))
        for line in verdict:
            self.assertIn(line, text)
        # Bounded, and it is the head that gets dropped.
        self.assertNotIn("(0)", text)
        self.assertLessEqual(len(text.splitlines()), 1 + lane.GIT_TAIL_LINES)

    def test_timeouts_and_os_errors_are_named(self):
        timed_out = subprocess.TimeoutExpired(["git", "commit", "-m", "a message"], 300)
        self.assertEqual(lane.describe_failure(timed_out),
                         "`git commit -m 'a message'` timed out after 300s")
        self.assertEqual(lane.describe_failure(FileNotFoundError("git")), "FileNotFoundError: git")


class ExitCodeTests(unittest.TestCase):
    """The scheduler sees only the exit code. Every push failure must reach it,
    and the vault's must not cost the dashboard its publish."""

    def _run(self, *, vault, published=True, main_push=True, argv=()):
        calls: list[str] = []
        lines: list[str] = []

        def step(name, args, *, required, timeout=None):
            calls.append(name)
            return published if name == "publish" else True

        def push(which, result):
            def fake(message):
                calls.append(which)
                return result
            return fake

        with contextlib.ExitStack() as stack:
            for patch in (
                mock.patch.object(lane, "load_env_file", return_value=0),
                mock.patch.dict(os.environ, {"YOUTUBE_API_KEY": "test"}),
                mock.patch.object(lane, "videos_root", return_value=Path("vault") / "videos"),
                mock.patch.object(lane, "self_update"),
                mock.patch.object(lane, "step", side_effect=step),
                mock.patch.object(lane, "push_vault", side_effect=push("push_vault", vault)),
                mock.patch.object(lane, "push_main", side_effect=push("push_main", main_push)),
                mock.patch.object(lane, "log", side_effect=lines.append),
                mock.patch.object(sys, "argv", ["youtube_lane.py", *argv]),
            ):
                stack.enter_context(patch)
            code = lane.main()
        return code, calls, lines

    def test_exit_code_reflects_both_pushes(self):
        # (vault push, publish succeeded, main push) -> exit code
        cases = {
            (True, True, True): 0,
            (None, True, None): 0,    # a quiet day: nothing to commit anywhere
            (None, True, True): 0,
            (True, True, None): 0,
            (False, True, True): 1,   # the 2026-09-21..23 runs, which exited 0
            (False, True, None): 1,
            (True, True, False): 1,   # the 2026-09-08 run
            (False, True, False): 1,
            (True, False, None): 1,   # publish failed, so main was never pushed
            (False, False, None): 1,
        }
        for (vault, published, main_push), expected in cases.items():
            with self.subTest(vault=vault, published=published, main_push=main_push):
                code, calls, _ = self._run(vault=vault, published=published, main_push=main_push)
                self.assertEqual(code, expected)
                self.assertIn("publish", calls)
                self.assertEqual("push_main" in calls, published)

    def test_a_failed_vault_push_still_publishes_then_fails_the_run(self):
        code, calls, lines = self._run(vault=False, main_push=True)
        self.assertEqual(code, 1)
        self.assertEqual(calls[-3:], ["push_vault", "publish", "push_main"])
        # The last line before exit is what explains a non-zero code in the log.
        self.assertIn("vault push failed", lines[-1])

    def test_no_push_leaves_both_repositories_alone(self):
        code, calls, _ = self._run(vault=False, main_push=False, argv=["--no-push"])
        self.assertEqual(code, 0)
        self.assertNotIn("push_vault", calls)
        self.assertNotIn("push_main", calls)

    def test_the_supervisor_hands_the_lane_code_to_the_scheduler(self):
        """The task runs youtube_supervisor.ps1 with -File, so its exit code is
        what LastTaskResult records. It must be the lane's."""
        ps1 = (SCRIPTS / "youtube_supervisor.ps1").read_text(encoding="utf-8")
        self.assertIn("$code = $LASTEXITCODE", ps1)
        self.assertIn("exit $code", ps1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
