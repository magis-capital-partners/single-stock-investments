"""Release reproducible company-build inputs after authenticated assets are staged."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def release(workspace: Path, vault: Path) -> dict:
    workspace, vault = workspace.resolve(), vault.resolve()
    if vault != (workspace / '_external/research-vault').resolve() or not vault.is_relative_to(workspace):
        raise ValueError('Only the deployment checkout may release build inputs')
    manifest = workspace / '_cf_project/site/data/company-research/manifest.json'
    if not manifest.is_file() or not json.loads(manifest.read_text(encoding='utf-8')).get('documents'):
        raise ValueError('Stage the complete authenticated company library first')
    def git(*args, **kwargs):
        return subprocess.run(['git', '-c', 'submodule.recurse=false', '-C', str(vault), *args],
                              capture_output=True, check=True, **kwargs)
    git('rev-parse', '--git-dir')
    omitted = ('dashboard-private/company-source-backfill-v2', 'dashboard-private/company-research-cache')
    targets = [vault / relative for relative in omitted]
    if any(path.resolve() != path or not path.resolve().is_relative_to(vault) for path in targets):
        raise ValueError('Build cache escapes its deployment checkout')
    before = shutil.disk_usage(workspace).free
    sparse = subprocess.run(['git', '-C', str(vault), 'config', '--bool', 'core.sparseCheckout'],
                            capture_output=True, text=True, check=False).stdout.strip() == 'true'
    if sparse:
        name = Path(git('rev-parse', '--git-path', 'info/sparse-checkout').stdout.decode().strip())
        patterns = (name if name.is_absolute() else vault / name).read_text().splitlines()
    else:
        patterns = ['/*']
    patterns.extend('!/' + relative + '/' for relative in omitted)
    # Omit tracked inputs instead of recording deletions. Their immutable bytes
    # remain in the private Git objects; no remote repository is changed.
    git('sparse-checkout', 'set', '--no-cone', '--stdin', input=('\n'.join(patterns)+'\n').encode())
    for target in targets:
        if target.exists():
            # Restoring the compressed cache also creates untracked derived
            # files, which sparse checkout deliberately leaves behind.
            shutil.rmtree(target)
    return {'released_build_inputs': list(omitted),
            'free_bytes_before': before, 'free_bytes_after': shutil.disk_usage(workspace).free}


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('This cleanup is only for an ephemeral GitHub deployment workspace')
    print(json.dumps(release(Path(os.environ['GITHUB_WORKSPACE']), Path(os.environ['RESEARCH_VAULT_ROOT']))))
