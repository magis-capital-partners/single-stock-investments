import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reverse_split_release import dispatch_release, release_targets


class Release(unittest.TestCase):
    def fake(self, paths, merged=True, fail=False):
        calls = []

        def run(args, **kwargs):
            calls.append((args, kwargs))
            if '--method' in args:
                if fail:
                    raise subprocess.CalledProcessError(1, args)
                return SimpleNamespace(stdout='')
            if '--paginate' in args:
                return SimpleNamespace(stdout=json.dumps([[{'filename': p} for p in page] for page in paths]))
            return SimpleNamespace(stdout=json.dumps({'merged': merged, 'merge_commit_sha': 'a' * 40}))

        return calls, run

    def test_merged_changes_on_a_later_inventory_page_dispatch_each_required_release_once(self):
        calls, run = self.fake([['README.md'], ['dashboard/cloudflare/reverse-split-live/worker.mjs']])
        result = dispatch_release('owner/repo', 123, run)
        self.assertEqual(result['status'], 'deployment_dispatched_not_yet_verified')
        sent = [kwargs for args, kwargs in calls if '--method' in args]
        self.assertEqual(len(sent), 2)
        self.assertEqual(json.loads(sent[0]['input'])['client_payload']['merged_commit'], 'a' * 40)
        self.assertEqual(json.loads(sent[0]['input'])['event_type'], 'reverse-split-release')
        self.assertFalse(json.loads(sent[1]['input'])['inputs']['d1_full_resync'])

    def test_unmerged_or_unrelated_pr_never_dispatches(self):
        calls, run = self.fake([['README.md']])
        self.assertEqual(dispatch_release('owner/repo', 123, run)['status'], 'not_applicable')
        self.assertFalse(any('--method' in args for args, _ in calls))
        calls, run = self.fake([['dashboard/cloudflare/reverse-split-live/worker.mjs']], merged=False)
        with self.assertRaisesRegex(ValueError, 'unmerged'):
            dispatch_release('owner/repo', 123, run)
        self.assertEqual(len(calls), 1)

    def test_dispatch_failure_is_visible_and_does_not_report_a_release(self):
        _, run = self.fake([['.github/workflows/reverse-split-live.yml']], fail=True)
        with self.assertRaises(subprocess.CalledProcessError):
            dispatch_release('owner/repo', 123, run)

    def test_frontend_only_change_starts_the_dashboard_without_a_collector_event(self):
        calls, run = self.fake([['dashboard/reverse-split-shadow.js']])
        result = dispatch_release('owner/repo', 123, run)
        posts = [(args, kwargs) for args, kwargs in calls if '--method' in args]
        self.assertEqual(len(posts), 1)
        self.assertIn('repos/owner/repo/actions/workflows/dashboard-pages.yml/dispatches', posts[0][0])
        self.assertEqual(result['targets'], {'worker': False, 'dashboard': True, 'public_status': False})

    def test_release_workflow_is_separate_from_collection(self):
        root = Path(__file__).resolve().parents[3]
        text = (root / '.github/workflows/reverse-split-live.yml').read_text(encoding='utf8')
        self.assertIn('reverse-split-release', text)
        self.assertIn("github.event.action != 'reverse-split-release'", text)
        self.assertIn("github.event.action == 'reverse-split-release'", text)
        self.assertEqual(release_targets(['.github/workflows/reverse-split-live.yml']), {'worker': True, 'dashboard': False, 'public_status': False})
        self.assertEqual(release_targets(['dashboard/reverse-split-shadow.js']), {'worker': False, 'dashboard': True, 'public_status': False})
        self.assertEqual(release_targets(['_system/scripts/validate_dashboard_data.py']), {'worker': False, 'dashboard': True, 'public_status': False})

    def test_public_source_repair_queues_its_existing_leased_service_once(self):
        calls, run = self.fake([['dashboard/cloudflare/reverse-split-live/market-status-source.mjs']])
        result = dispatch_release('owner/repo', 123, run)
        sent = [json.loads(kwargs['input']) for args, kwargs in calls if '--method' in args]
        self.assertTrue(result['targets']['public_status'])
        self.assertEqual([p.get('event_type') for p in sent[:2]], ['reverse-split-release', 'reverse-split-status-continue'])
        self.assertEqual(sent[1]['client_payload']['orders'], 0)
        self.assertEqual(len(sent), 3)
        self.assertEqual(release_targets(['.github/workflows/reverse-split-market-status.yml']), {'worker': False, 'dashboard': False, 'public_status': True})
        root = Path(__file__).resolve().parents[3]
        source_workflow = yaml.load((root / '.github/workflows/reverse-split-market-status.yml').read_text(encoding='utf8'), Loader=yaml.BaseLoader)
        self.assertEqual(source_workflow['concurrency']['cancel-in-progress'], 'false')

    def test_post_merge_release_explicitly_handles_skipped_optional_ancestor_jobs(self):
        root = Path(__file__).resolve().parents[3]
        workflow = yaml.load((root / '.github/workflows/marvin-pr-automerge.yml').read_text(encoding='utf8'), Loader=yaml.BaseLoader)
        condition = workflow['jobs']['release-reverse-split']['if']
        # An explicit status check is required: implicit success() includes skipped ancestors.
        self.assertIn('!cancelled()', condition)
        self.assertIn("needs.merge.result == 'success'", condition)
        self.assertIn("needs.merge.outputs.merged == 'true'", condition)


if __name__ == '__main__':
    unittest.main()
