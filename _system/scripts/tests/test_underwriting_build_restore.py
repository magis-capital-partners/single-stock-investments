import json
import subprocess
import sys
from pathlib import Path

import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import private_storage_io as io
from test_private_storage_io import environment
from vault_publication_sparse import publication_entries


def build_restore():
    root = Path(__file__).resolve().parents[3]
    workflow = yaml.load((root / '.github/workflows/valuation-underwriting.yml').read_text(), Loader=yaml.BaseLoader)
    return next(s for s in workflow['jobs']['underwrite']['steps']
                if s.get('name') == 'Restore primary research and paid-call receipts')['with']


def test_company_build_restores_complete_underwriting_without_unrelated_history(environment, monkeypatch):
    vault, storage = environment
    ledger = b'{"id":1,"usage":"unknown"}\r\n{"id":2,"usage":"reported"}\r\n'
    required = {
        'valuation-underwriting/handoffs/latest/CPRT.json': b'{"handoff_hash":"sealed"}\n',
        'valuation-underwriting/handoffs/sealed.json': json.dumps({'packet': {'full_source_text': 'complete evidence\r\n\u6f22\u5b57 ' * 200}, 'review': 'approve'}).encode(),
        'valuation-underwriting/local-runtime/ledger.jsonl': ledger,
        'valuation-underwriting/local-runtime/states/CPRT.json': b'{"status":"approved_for_build"}\n',
        'valuation-underwriting/local-runtime/states/OTHER.json': b'{"retry_after":"2026-11-18","last_attempt":"preserved"}\n',
        'valuation-underwriting/local-runtime/cache/CPRT/paid/receipt.json': b'{"usage":"reported","original":true}\n',
        'valuation-underwriting/runtime/batch.json': b'{"completed":[]}\n',
        'dashboard-private/manifest.json': b'{"assets":{}}\n',
        'dashboard-private/migration-journal.jsonl': b'{"original":true}\n',
    }
    unrelated = 'company-research/cache/unrelated.json'
    path = vault / unrelated
    path.parent.mkdir(parents=True)
    path.write_bytes(b'legacy Git placeholder')
    subprocess.run(['git', '-c', 'user.name=test', '-c', 'user.email=test@example.test', 'add', '.'], cwd=vault, check=True, capture_output=True)
    subprocess.run(['git', '-c', 'user.name=test', '-c', 'user.email=test@example.test', 'commit', '-m', 'legacy tracked file'], cwd=vault, check=True, capture_output=True)
    storage.publish({**required, unrelated: b'unrelated historical bytes'})
    _, records = storage.snapshot()
    remote_before = dict(records)
    restore = build_restore()
    patterns = (['/dashboard-private/manifest.json', '/dashboard-private/migration-journal.jsonl', '/dashboard-private/.gitattributes']
                if restore.get('publication-only') == 'true' else ['/*'])
    patterns += restore.get('extra-paths', '').splitlines()
    subprocess.run(['git', 'sparse-checkout', 'set', '--no-cone', '--stdin'], input=('\n'.join(patterns) + '\n').encode(), cwd=vault, check=True, capture_output=True)
    fetched = []
    original_get = storage.objects.get
    monkeypatch.setattr(storage.objects, 'get', lambda identity, size: (fetched.append(identity), original_get(identity, size))[1])
    io.initialize(vault, storage=storage, sparse_scoped=True)
    for relative, raw in required.items():
        assert (vault / relative).read_bytes() == raw, relative
    assert not (vault / unrelated).exists()
    assert not ({c['stored_sha256'] for c in records[unrelated]['chunks']} & set(fetched))
    assert storage.snapshot()[1] == remote_before
    assert json.loads((vault / io.MARKER).read_bytes())['read_only'] is False


def test_company_build_selects_every_workspace_input_without_other_dashboard_pages(tmp_path):
    required = [
        ('assets', 'data/core.json'),
        ('repository_assets', '_system/reference/market-data/valuation_quotes/CPRT.json'),
        ('repository_assets', '_system/reference/market-data/valuation_fundamentals/CPRT.json'),
        ('repository_assets', '_system/reference/market-data/valuation_related_evidence/CPRT.json'),
        ('repository_assets', '_system/data/shared_valuation_forecasts.json'),
        ('repository_assets', 'CPRT/research/valuation.json'),
        ('repository_assets', 'OTHER/research/valuation.json'),
    ]
    manifest = {'assets': {}, 'repository_assets': {}}
    for index, (section, relative) in enumerate(required):
        path = tmp_path / ('dashboard/' if section == 'assets' else '') / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'workspace placeholder')
        manifest[section][relative] = {'private_sha256': f'{index+1:064x}'}
    manifest['assets']['data/ticker-details/unselected.json'] = {'private_sha256': 'f' * 64}
    original = json.dumps(manifest, sort_keys=True)
    scope = tmp_path if build_restore().get('publication-scope') == 'workspace' else None
    selected = {(section, relative) for section, relative, _ in publication_entries(manifest, scope)}
    assert selected == set(required)
    assert json.dumps(manifest, sort_keys=True) == original
