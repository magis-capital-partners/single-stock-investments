"""A validated refresh may retry publication, without discarding unsaved work."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retry_validated_refresh import MAX_PUBLICATION_RETRIES, request_retry

ROOT = Path(__file__).resolve().parents[3]
PUSH = ROOT / '_system/scripts/ci_push_main.sh'
BASH = shutil.which('bash') or ('C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else None)


@pytest.mark.parametrize('prices_only', [True, False])
def test_retry_preserves_refresh_mode_and_advances_bounded_count(prices_only):
    calls = []
    result = request_retry('example/research', 1, prices_only, run=lambda *a, **k: calls.append((a, k)))
    assert result == {'status': 'publication_retry_requested', 'attempt': 2, 'prices_only': prices_only}
    args, options = calls[0]
    assert args[0] == ['gh', 'api', 'repos/example/research/dispatches', '--method', 'POST', '--input', '-']
    assert json.loads(options['input']) == {'event_type': 'refresh-autonomous-compounders',
        'client_payload': {'prices_only': prices_only, 'publication_retry_count': 2}}
    assert options['check'] is True and options['timeout'] == 60


@pytest.mark.parametrize('count', [-1, MAX_PUBLICATION_RETRIES, True, '1'])
def test_invalid_or_exhausted_retry_never_dispatches(count):
    with pytest.raises(ValueError):
        request_retry('example/research', count, True, run=lambda *a, **k: pytest.fail('must not dispatch'))


def test_ambiguous_mode_never_dispatches():
    with pytest.raises(ValueError, match='explicit'):
        request_retry('example/research', 0, 'false', run=lambda *a, **k: pytest.fail('must not dispatch'))


def test_only_a_validated_failed_publication_can_request_retry():
    job = yaml.safe_load((ROOT / '.github/workflows/autonomous-compounders.yml').read_text())['jobs']['refresh']
    steps = job['steps']
    assert steps[0]['with']['ref'] == 'main'
    retry = steps[-1]
    assert retry['if'] == "failure() && steps.verified_forecasts.outcome == 'success' && steps.publish.outcome == 'failure'"
    assert retry['run'] == 'python _system/scripts/retry_validated_refresh.py'
    assert 'publication_retry_count' in retry['env']['PUBLICATION_RETRY_COUNT']


def test_tracked_sources_with_lf_policy_have_normalized_git_blobs():
    # An index blob containing CRLF under an explicit LF policy becomes dirty
    # again immediately after restore, even on a fresh Linux CI checkout.
    entries = subprocess.check_output(['git', 'ls-files', '--eol', '-z', '--', '_system/scripts'], cwd=ROOT).split(b'\0')
    candidates = [entry.partition(b'\t')[2] for entry in entries
        if entry.split(b' ', 1)[0] in {b'i/crlf', b'i/mixed'}]
    if not candidates:
        return
    attrs = subprocess.run(['git', 'check-attr', '--cached', '-z', '--stdin', 'eol'],
        input=b'\0'.join(candidates)+b'\0', cwd=ROOT, check=True, capture_output=True).stdout.split(b'\0')
    violations = [attrs[i].decode() for i in range(0, len(attrs)-1, 3) if attrs[i+2] == b'lf']
    assert not violations, 'Committed blobs violate their LF policy: '+', '.join(violations)


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, 'init', '-q', '-b', 'main')
    git(tmp_path, 'config', 'user.name', 'test')
    git(tmp_path, 'config', 'user.email', 'test@example.com')
    git(tmp_path, 'config', 'core.autocrlf', 'false')
    (tmp_path / 'notes with spaces.txt').write_text('base\n', newline='\n')
    (tmp_path / 'candidate.txt').write_text('base\n', newline='\n')
    git(tmp_path, 'add', '.')
    git(tmp_path, 'commit', '-qm', 'seed')
    (tmp_path / 'notes with spaces.txt').write_text('backed-up edit\n', newline='\n')
    (tmp_path / 'candidate.txt').write_text('staged candidate\n', newline='\n')
    git(tmp_path, 'add', 'candidate.txt')
    return tmp_path


def shell(repo, code, *, ci=True):
    env = dict(os.environ, GITHUB_ACTIONS='true' if ci else 'false', CI_PUSH_SKIP_SELF_REFRESH='1')
    return subprocess.run([BASH, '-c', 'set -euo pipefail\nCI_PUSH_SOURCING=1 source "$1"\n' + code,
        'bash', str(PUSH).replace('\\', '/')], cwd=repo, env=env, capture_output=True, text=True, timeout=30)


def residual_stash(contents):
    # Simulate a hydrated file retaining dirt after a successful stash.
    return '''git() {
  if [ "${1:-}" = stash ]; then
    command git "$@"
    printf '%s\\n' "''' + contents + '''" > 'notes with spaces.txt'
  else
    command git "$@"
  fi
}
clean_worktree_for_rebase
'''


def test_verified_residual_is_restored_and_stash_and_index_preserved(repo):
    result = shell(repo, residual_stash('backed-up edit'))
    assert result.returncode == 0, result.stderr + result.stdout
    assert (repo / 'notes with spaces.txt').read_text() == 'base\n'
    assert git(repo, 'show', 'refs/stash:notes with spaces.txt') == 'backed-up edit\n'
    assert git(repo, 'show', ':candidate.txt') == 'staged candidate\n'
    assert git(repo, 'diff', '--name-only') == ''


def test_unbacked_residual_fails_without_discarding_changes(repo):
    result = shell(repo, residual_stash('unbacked edit'))
    assert result.returncode != 0
    assert 'not in the saved backup' in result.stdout
    assert (repo / 'notes with spaces.txt').read_text() == 'unbacked edit\n'
    assert git(repo, 'show', 'refs/stash:notes with spaces.txt') == 'backed-up edit\n'


def test_local_user_residual_is_never_force_restored(repo):
    result = shell(repo, residual_stash('backed-up edit'), ci=False)
    assert result.returncode != 0
    assert (repo / 'notes with spaces.txt').read_text() == 'backed-up edit\n'


def test_failed_stash_is_not_ignored(repo):
    result = shell(repo, '''git() {
  if [ "${1:-}" = stash ]; then return 1; else command git "$@"; fi
}
clean_worktree_for_rebase
''')
    assert result.returncode != 0
    assert (repo / 'notes with spaces.txt').read_text() == 'backed-up edit\n'


def test_rebase_failure_without_state_cannot_push_or_claim_resolution(repo):
    git(repo, 'restore', '--worktree', 'notes with spaces.txt')
    result = shell(repo, '''PYTHON=true
sync_self_from_origin_main() { :; }
materialize_push_dependencies() { :; }
ensure_main_rebase_history() { :; }
check_github_file_sizes() { :; }
check_push_file_sizes() { :; }
git() {
  case "${1:-}" in
    rebase) return 1 ;;
    push) touch pushed; return 0 ;;
    *) command git "$@" ;;
  esac
}
ci_push_main 'validated test candidate'
''')
    assert result.returncode != 0
    assert 'Rebase did not start' in result.stdout
    assert 'conflicts resolved' not in result.stdout
    assert not (repo / 'pushed').exists()
