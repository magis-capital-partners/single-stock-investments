import unittest

from deploy.lightsail.release_check import release_status


COMMIT = "a" * 40
RUNS_URL = (
    "/actions/workflows/reverse-split-live.yml/runs"
    f"?branch=main&head_sha={COMMIT}&per_page=30"
)


def run(run_id, **changes):
    return dict(
        id=run_id,
        run_attempt=2,
        head_sha=COMMIT,
        head_branch="main",
        event="repository_dispatch",
        status="completed",
        conclusion="success",
    ) | changes


def job(**changes):
    return dict(name="deploy", head_sha=COMMIT, status="completed", conclusion="success") | changes


class ReleaseCheckTest(unittest.TestCase):
    def test_successful_dispatch_checks_the_exact_deploy_job(self):
        responses = {
            RUNS_URL: {"workflow_runs": [run(99), run(98)]},
            "/actions/runs/99/attempts/2/jobs?per_page=30": {"jobs": [job(conclusion="skipped")]},
            "/actions/runs/98/attempts/2/jobs?per_page=30": {"jobs": [job()]},
        }
        self.assertEqual(release_status(COMMIT, responses.pop), "success")
        self.assertFalse(responses)

    def test_ignores_non_release_runs_and_requires_deploy_success(self):
        responses = {
            RUNS_URL: {"workflow_runs": [
                run(99, head_sha="b" * 40), run(98, head_branch="other"),
                run(97, event="schedule"), run(96, conclusion="failure"),
                run(95, event="push"),
            ]},
            "/actions/runs/95/attempts/2/jobs?per_page=30": {
                "jobs": [job(head_sha="b" * 40), job(conclusion="failure"), job(name="collect")]
            },
        }
        self.assertNotEqual(release_status(COMMIT, responses.pop), "success")
        self.assertFalse(responses)
