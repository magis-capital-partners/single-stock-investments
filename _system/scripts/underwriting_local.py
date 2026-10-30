"""Local Codex judgment worker; only approved immutable handoffs reach GitHub."""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

from underwriting_contract import require
from underwriting_pipeline import ROOT, read, run_batch, stage_model, write

OPS = 'magis-capital-partners/single-stock-investments'
VAULT = 'magis-capital-partners/research-vault'


def git(directory, *args, data=None, env=None):
    return subprocess.check_output(['git', '-c', 'fetch.recurseSubmodules=false', '-c', 'submodule.recurse=false', *args],
                                   cwd=directory, input=data, env=env, timeout=180)


@contextmanager
def local_lock(home):
    home.mkdir(parents=True, exist_ok=True)
    with (home/'worker.lock').open('a+b') as handle:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            handle.write(b'0')
            handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError('The local underwriting worker is already running') from exc
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def clone_vault(home):
    vault = home/'vault'
    if not (vault/'.git').is_dir():
        require(not vault.exists(), 'Choose a new isolated local vault directory')
        subprocess.run(['git', 'clone', '--depth', '1', '--filter=blob:none', '--sparse', 'https://github.com/'+VAULT+'.git', str(vault)], check=True, timeout=180)
        git(vault, 'sparse-checkout', 'set', 'valuation-underwriting')
    require(git(vault, 'remote', 'get-url', 'origin').decode().strip().removesuffix('.git').endswith('/'+VAULT),
            'Local runtime vault remote does not match')
    git(vault, 'fetch', '-q', 'origin', 'main')
    # Never reset the private working tree: unpublished paid receipts must
    # survive a push failure. Only import the remote worker's shared ledger.
    exists = subprocess.run(['git', 'cat-file', '-e', 'origin/main:valuation-underwriting/runtime/ledger.jsonl'],
                            cwd=vault, capture_output=True, check=False, timeout=30)
    if exists.returncode == 0:
        path = vault/'valuation-underwriting/runtime/ledger.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(git(vault, 'show', 'origin/main:valuation-underwriting/runtime/ledger.jsonl'))
    return vault


def data_root(source, home, vault):
    import yaml
    from private_dashboard_assets import (
        decode_object_bytes,
        hydrate,
        hydrate_repository,
        private_object,
        safe_relative,
    )
    root = home/'data'
    retained = {}
    for path in (root/'_system/reference/market-data/valuation_fundamentals').glob('*.json'):
        value = read(path)
        if value.get('collected_at') and value.get('primary_observations'):
            retained[path.name] = value
    workflow = yaml.safe_load((source/'.github/workflows/valuation-underwriting.yml').read_text(encoding='utf-8'))
    checkout = next(s for s in workflow['jobs']['underwrite']['steps'] if s.get('uses') == 'actions/checkout@v4')
    for pattern in checkout['with']['sparse-checkout'].splitlines():
        for name in glob.glob(str(source/pattern.strip('/'))):
            path = Path(name)
            target = root/path.relative_to(source)
            if path.is_dir():
                shutil.copytree(path, target, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns('node_modules', '__pycache__', '*.pyc', '.pytest_cache'))
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    manifest = read(root/'dashboard/private-assets.json')
    for base, entries in ((root/'dashboard', manifest.get('assets') or {}), (root, manifest.get('repository_assets') or {})):
        for relative, entry in entries.items():
            if not (base/safe_relative(relative)).is_file():
                continue
            sha = entry['private_sha256']
            target = private_object(vault, sha)
            if not target.is_file():
                raw = git(vault, 'show', 'origin/main:dashboard-private/objects/'+sha)
                decode_object_bytes(raw, sha)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
    hydrate_repository(root)
    hydrate(root/'dashboard')
    for receipt_path in root.glob('*/research/underwriting_receipt.json'):
        identity = read(receipt_path).get('packet_hash') or ''
        if len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
            continue
        destination = vault/'valuation-underwriting/packets'/(identity+'.json')
        if not destination.is_file():
            try:
                raw = git(vault, 'show', 'origin/main:valuation-underwriting/packets/'+identity+'.json')
                require(json.loads(raw).get('packet_hash') == identity, 'Approved baseline evidence identity changed')
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            except subprocess.CalledProcessError:
                pass  # Missing private proof means cold underwriting, never unchecked reuse.
    for name, value in retained.items():
        path = root/'_system/reference/market-data/valuation_fundamentals'/name
        if prefer_local_facts(value, read(path)):
            write(path, value)
    return root


def prefer_local_facts(local, incoming):
    """A source checkout update must not erase fresher privately collected facts."""
    local_report, incoming_report = local.get('latest_report') or {}, incoming.get('latest_report') or {}
    return (str(local.get('collected_at') or '') > str(incoming.get('collected_at') or '')
            and (local_report.get('period') or '', local_report.get('filed') or '')
                >= (incoming_report.get('period') or '', incoming_report.get('filed') or ''))


def publish_runtime(vault, home):
    """Overlay only owned private JSON; preserve every remote worker's files."""
    files = []
    for folder in ('local-runtime', 'handoffs'):
        files += [p for p in (vault/'valuation-underwriting'/folder).rglob('*') if p.is_file() and p.suffix in ('.json', '.jsonl')]
    if not files:
        return False
    for _ in range(3):
        git(vault, 'fetch', '-q', 'origin', 'main')
        base = git(vault, 'rev-parse', 'origin/main').decode().strip()
        env = {**os.environ, 'GIT_INDEX_FILE': str(home/'private-publication.index')}
        git(vault, 'read-tree', base, env=env)
        changed = False
        for path in files:
            relative = path.relative_to(vault).as_posix()
            blob = git(vault, 'hash-object', '-w', '--', relative).decode().strip()
            current = subprocess.run(['git', 'rev-parse', base+':'+relative], cwd=vault, capture_output=True, text=True, check=False, timeout=30)
            if current.returncode == 0 and current.stdout.strip() == blob:
                continue
            if relative.startswith('valuation-underwriting/handoffs/') and '/latest/' not in relative:
                require(current.returncode != 0, 'An immutable local handoff changed')
            git(vault, 'update-index', '--add', '--cacheinfo', '100644,'+blob+','+relative, env=env)
            changed = True
        if not changed:
            return False
        tree = git(vault, 'write-tree', '--missing-ok', env=env).decode().strip()
        author = {**env, 'GIT_AUTHOR_NAME': 'Magis local underwriting', 'GIT_COMMITTER_NAME': 'Magis local underwriting',
                  'GIT_AUTHOR_EMAIL': 'underwriting@users.noreply.github.com', 'GIT_COMMITTER_EMAIL': 'underwriting@users.noreply.github.com'}
        commit = git(vault, 'commit-tree', tree, '-p', base, data=b'Preserve local Codex underwriting sessions and handoffs\n', env=author).decode().strip()
        pushed = subprocess.run(['git', 'push', '-q', 'origin', commit+':refs/heads/main'], cwd=vault, capture_output=True, check=False, timeout=180)
        if pushed.returncode == 0:
            return True
    raise RuntimeError('Private runtime push changed concurrently; paid work remains saved locally')


def run_once(home, source=ROOT, tickers=None, launch=False):
    from underwriting_codex import preflight
    owner = read(home/'runtime-owner.json')
    require(owner.get('repository') == OPS and owner.get('purpose') == 'local-codex-underwriting',
            'Initialize a fresh owned runtime with underwriting_local.ps1 first')
    with local_lock(home):
        preflight()
        vault = clone_vault(home)
        os.environ['RESEARCH_VAULT_ROOT'] = str(vault)
        os.environ['UNDERWRITING_ARCHIVE_ROOT'] = str(source)
        root = data_root(source, home, vault)
        require(all(stage_model(root, stage)['provider'] == 'codex-local' for stage in ('author', 'challenger')),
                'The local worker requires the signed-in Codex policy on main')
        result = run_batch(root, work=home/'work', vault=vault, tickers=tickers, phase='author', launch=launch)
        write(home/'last-run.json', result)
        if launch:
            publish_runtime(vault, home)
            # Only a successful private push can make a handoff visible to CI.
            if result['selected']:
                payload = {'event_type': 'valuation-underwriting-run', 'client_payload': {'limit': 3}}
                subprocess.run(['gh', 'api', 'repos/'+OPS+'/dispatches', '--method', 'POST', '--input', '-'],
                               input=json.dumps(payload).encode(), check=True, timeout=60)
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--launch', action='store_true')
    parser.add_argument('--tickers', default='')
    args = parser.parse_args()
    print(json.dumps(run_once(args.home.resolve(), tickers=args.tickers.split(',') if args.tickers else None, launch=args.launch)))
