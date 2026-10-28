#!/usr/bin/env python3
"""Publish only validated underwriting artifacts through exact-head CI and automerge."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time

from underwriting_contract import require
from underwriting_pipeline import ROOT, read, validate_saved
from vault_paths import research_vault_root


def git(root, *args, data=None, env=None):
    return subprocess.check_output(['git', *args], cwd=root, input=data, env=env).decode().strip()


def github(repo, path, payload=None):
    args = ['gh', 'api', f'repos/{repo}/'+path]
    if payload is not None:
        args += ['--method', 'POST', '--input', '-']
    raw = subprocess.check_output(args, input=None if payload is None else json.dumps(payload).encode())
    return json.loads(raw) if raw.strip() else None


def approved_paths(completed):
    paths = ['_system/data/underwriting_queue.json']
    for ticker in completed:
        paths += [ticker+'/research/'+name for name in ('valuation.json', 'valuation_contract.json', 'valuation_route.json',
                                                       'underwriting_contract.json', 'underwriting_review.json', 'underwriting_receipt.json')]
        paths += ['_system/reference/market-data/'+folder+'/'+ticker+'.json' for folder in ('valuation_quotes', 'valuation_fundamentals')]
    return paths


def publish(root=ROOT, *, batch_path=None, wait=False):
    batch = read(batch_path or root/'.underwriting-work/batch.json')
    require(batch.get('launched') is True, 'A dry-run cannot publish valuations')
    repo = os.environ['GITHUB_REPOSITORY']
    vault = research_vault_root()
    require(vault is not None, 'Preserve private underwriting evidence before publication')
    completed = batch.get('completed') or []
    for ticker in completed:
        validate_saved(root, ticker, vault)
    base = git(root, 'rev-parse', 'HEAD')
    git(root, 'fetch', '-q', 'origin', 'main')
    latest = git(root, 'rev-parse', 'origin/main')
    # A model changed by another researcher is re-queued, never overwritten.
    for ticker in completed:
        path = ticker+'/research/valuation.json'
        def revision(ref, path=path):
            result = subprocess.run(['git', 'rev-parse', ref+':'+path], cwd=root, capture_output=True, text=True, check=False)
            return result.stdout.strip() if result.returncode == 0 else None
        require(revision(base) == revision(latest), 'concurrent_model_update: '+ticker)
    work = root/'.underwriting-work'
    index = work/'publication.index'
    env = {**os.environ, 'GIT_INDEX_FILE': str(index)}
    git(root, 'read-tree', latest, env=env)
    changed = []
    for relative in approved_paths(completed):
        path = root/relative
        if not path.is_file():
            continue
        blob = git(root, 'hash-object', '-w', '--', relative)
        current = subprocess.run(['git', 'rev-parse', latest+':'+relative], cwd=root, capture_output=True, text=True, check=False)
        if current.returncode == 0 and current.stdout.strip() == blob:
            continue
        git(root, 'update-index', '--add', '--cacheinfo', '100644,'+blob+','+relative, env=env)
        changed.append(relative)
    if not changed:
        return {'status': 'unchanged', 'completed': completed}
    tree = git(root, 'write-tree', env=env)
    message = 'Update independently underwritten company models' if completed else 'Record autonomous underwriting gaps and retries'
    commit_env = {**env, 'GIT_AUTHOR_NAME': 'github-actions[bot]', 'GIT_COMMITTER_NAME': 'github-actions[bot]',
                  'GIT_AUTHOR_EMAIL': '41898282+github-actions[bot]@users.noreply.github.com',
                  'GIT_COMMITTER_EMAIL': '41898282+github-actions[bot]@users.noreply.github.com'}
    sha = git(root, 'commit-tree', tree, '-p', latest, data=(message+'\n').encode(), env=commit_env)
    branch = 'codex/underwriting-'+str(os.environ.get('GITHUB_RUN_ID') or int(time.time()))
    git(root, 'push', '-q', 'origin', sha+':refs/heads/'+branch)
    body = ('Primary-evidence underwriting completed for '+(', '.join(completed) or 'no companies in this batch')+'. '
            'Each accepted model has isolated author/challenger/builder receipts, a frozen private evidence packet, '
            'an exact assumption-contract check and PV/IRR reconciliation. '
            'Remaining gaps have automatic retries; no capital action or human approval queue is created.\n\n'
            'Validated models: '+str(len(completed))+'. Blocked: '+str(len(batch.get('blocked') or []))+'.\n')
    pr = github(repo, 'pulls', {'title': message+(' — '+', '.join(completed) if completed else ''),
                              'head': branch, 'base': 'main', 'body': body})
    number, url = pr['number'], pr['html_url']
    # GITHUB_TOKEN PRs do not start pull_request workflows. These explicit
    # dispatches create the source-quality gate and immutable underwriting gate.
    for event in ('research-quality-pr', 'underwriting-validate-pr'):
        github(repo, 'dispatches', {'event_type': event, 'client_payload': {'pr': number, 'sha': sha}})
    print(json.dumps({'pull_request': url, 'head_sha': sha}), flush=True)
    if wait:
        deadline = time.monotonic()+2400
        while time.monotonic() < deadline:
            status = github(repo, 'pulls/'+str(number))
            if status.get('merged'):
                if completed:
                    github(repo, 'dispatches', {'event_type': 'refresh-autonomous-compounders', 'client_payload': {'prices_only': True}})
                return {'status': 'merged', 'pull_request': url, 'completed': completed, 'price_refresh_requested': bool(completed)}
            if status.get('state') == 'closed':
                return {'status': 'closed_without_merge', 'pull_request': url, 'completed': []}
            if status.get('mergeable') is False:
                # Do not strand an assumption batch behind a human conflict
                # resolution. The next run starts against fresh evidence/main.
                subprocess.check_call(['gh', 'pr', 'close', str(number), '--repo', repo])
                return {'status': 'automatic_retry_after_conflict', 'pull_request': url, 'completed': []}
            time.sleep(30)
        subprocess.check_call(['gh', 'pr', 'close', str(number), '--repo', repo])
        return {'status': 'automatic_retry_after_checks_timeout', 'pull_request': url, 'completed': []}
    return {'status': 'checks_requested', 'pull_request': url, 'completed': completed}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait', action='store_true')
    args = parser.parse_args()
    print(json.dumps(publish(wait=args.wait)))
