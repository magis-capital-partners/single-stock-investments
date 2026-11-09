"""Dispatch a research deployment after a verified merged reverse-split PR."""
from __future__ import annotations

import argparse
import json
import re
import subprocess


def release_targets(paths: list[str]) -> dict:
    worker = any(path.startswith('dashboard/cloudflare/reverse-split-live/')
                 or path == '.github/workflows/reverse-split-live.yml' for path in paths)
    # Preserve the dashboard's existing dashboard/** push behavior after bot merges.
    dashboard = any(path.startswith('dashboard/') for path in paths)
    return {'worker': worker, 'dashboard': dashboard}


def dispatch_release(repo: str, pr: int, run=subprocess.run) -> dict:
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or pr <= 0:
        raise ValueError('Invalid release repository or PR')

    def gh(*args: str, payload=None):
        result = run(['gh', 'api', *args], input=None if payload is None else json.dumps(payload),
                     text=True, capture_output=True, check=True, timeout=60)
        return json.loads(result.stdout) if result.stdout.strip() else None

    metadata = gh(f'repos/{repo}/pulls/{pr}')
    commit = metadata.get('merge_commit_sha') or ''
    if not metadata.get('merged') or not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('Refusing to release an unmerged or unidentified PR')
    pages = gh('--paginate', '--slurp', f'repos/{repo}/pulls/{pr}/files?per_page=100')
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise ValueError('Malformed release file inventory')
    paths = [entry['filename'] for page in pages for entry in page]
    if len(paths) > 3000 or any(not isinstance(path, str) for path in paths):
        raise ValueError('Release inventory exceeds its bound')
    targets = release_targets(paths)
    if not any(targets.values()):
        return {'status': 'not_applicable', 'pr': pr}
    if targets['worker']:
        gh('--method', 'POST', f'repos/{repo}/dispatches', '--input', '-', payload={
            'event_type': 'reverse-split-release',
            'client_payload': {'pr': pr, 'merged_commit': commit, 'research_only': True, 'orders': 0},
        })
    if targets['dashboard']:
        gh('--method', 'POST', f'repos/{repo}/actions/workflows/dashboard-pages.yml/dispatches', '--input', '-', payload={
            'ref': 'main', 'inputs': {'reason': f'Post-merge dashboard release for PR {pr} ({commit})', 'd1_full_resync': False},
        })
    return {'status': 'deployment_dispatched_not_yet_verified', 'pr': pr, 'merged_commit': commit, 'targets': targets}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--pr', type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(dispatch_release(args.repo, args.pr)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
