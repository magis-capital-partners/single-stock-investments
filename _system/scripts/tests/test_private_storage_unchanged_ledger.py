"""An unchanged CI ledger cannot overwrite a later real author admission."""
import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import private_storage as storage
import private_storage_io as io
from test_private_storage_io import environment

LEDGER = 'valuation-underwriting/local-runtime/ledger.jsonl'
BASE = b'{"id":1,"usage":"unknown"}\n{"id":2,"usage":"pending"}\n'
LEGACY = b'{ "usage": "unknown", "id": 1 }\r\n\r\n{ "id": 2, "usage": "pending" }\r\n'
NEW = b'{"id":3,"usage":"reported","input":123}\n'

@pytest.mark.parametrize('local', [BASE, LEGACY])
@pytest.mark.parametrize('concurrent', [False, True])
def test_equal_events_publish_neither_ledger_nor_control(environment, monkeypatch, local, concurrent):
    vault, fake = environment
    fake.publish({LEDGER: BASE})
    io.initialize(vault, storage=fake)
    if concurrent:
        fake.publish({LEDGER: BASE + NEW})
    upstream = copy.deepcopy(fake.catalog.records[LEDGER])
    (vault/LEDGER).write_bytes(local)
    original_publish = fake.catalog.publish
    calls = []
    def publish(updates, expected, **kwargs):
        calls.append((copy.deepcopy(updates), copy.deepcopy(kwargs)))
        return original_publish(updates, expected, **kwargs)
    monkeypatch.setattr(fake.catalog, 'publish', publish)
    (vault/'audit.json').write_bytes(b'{"preserved":true}')
    result = io.publish_paths(vault, {LEDGER: vault/LEDGER, 'audit.json': vault/'audit.json'}, storage=fake)
    assert result['files_preserved'] == 1
    assert calls and all(LEDGER not in updates and not kwargs.get('control_files') for updates, kwargs in calls)
    assert fake.catalog.records[LEDGER] == upstream
    assert fake.restore(LEDGER) == BASE + (NEW if concurrent else b'')
    assert (vault/LEDGER).read_bytes() == local
    assert fake.restore('audit.json') == b'{"preserved":true}'


def test_genuine_new_events_still_publish_the_full_control(environment, monkeypatch):
    vault, fake = environment
    fake.publish({LEDGER: BASE})
    io.initialize(vault, storage=fake)
    (vault/LEDGER).write_bytes(LEGACY + NEW)
    original_publish = fake.catalog.publish
    controls = []
    def publish(updates, expected, **kwargs):
        controls.append(kwargs.get('control_files'))
        return original_publish(updates, expected, **kwargs)
    monkeypatch.setattr(fake.catalog, 'publish', publish)
    io.publish_paths(vault, {LEDGER: vault/LEDGER}, storage=fake)
    assert controls == [{'control/admission-ledger.jsonl': LEGACY + NEW}]
    assert fake.restore(LEDGER) == LEGACY + NEW
    assert (vault/LEDGER).read_bytes() == LEGACY + NEW


def test_genuine_concurrent_ledger_events_remain_a_conflict(environment):
    vault, fake = environment
    fake.publish({LEDGER: BASE})
    io.initialize(vault, storage=fake)
    fake.publish({LEDGER: BASE + NEW})
    local = LEGACY + b'{"id":4,"usage":"pending"}\n'
    (vault/LEDGER).write_bytes(local)
    with pytest.raises(storage.ConcurrentUpdate):
        io.publish_paths(vault, {LEDGER: vault/LEDGER}, storage=fake)
    assert fake.restore(LEDGER) == BASE + NEW
    assert (vault/LEDGER).read_bytes() == local


@pytest.mark.parametrize('path', ['valuation-underwriting/runtime/ledger.jsonl',
                                 'other/ledger.jsonl',
                                 'valuation-underwriting/local-runtime/states/CPRT.json'])
def test_other_paths_keep_existing_concurrency_guards(environment, path):
    vault, fake = environment
    fake.publish({path: BASE})
    io.initialize(vault, storage=fake)
    fake.publish({path: BASE + NEW})
    (vault/path).write_bytes(LEGACY)
    with pytest.raises(storage.ConcurrentUpdate):
        io.publish_paths(vault, {path: vault/path}, storage=fake)
    assert fake.restore(path) == BASE + NEW
    assert (vault/path).read_bytes() == LEGACY


@pytest.mark.parametrize('incoming', [b'{"id":1.0}\n', b'{"id":true}\n',
                                     b'{"id":"1"}\n', b'{"id":null}\n',
                                     b'{"id":2}\n', b'', b'{"id":1}\n{"id":1}\n'])
def test_types_values_missing_or_duplicate_rows_are_not_serialization(incoming):
    assert not io._identical_real_ledger_events(b'{"id":1}\n', incoming)


def test_row_order_and_usage_status_are_not_serialization():
    assert not io._identical_real_ledger_events(BASE, b'{"id":2,"usage":"pending"}\n{"id":1,"usage":"unknown"}\n')
    assert not io._identical_real_ledger_events(BASE, BASE.replace(b'unknown', b'reported'))


@pytest.mark.parametrize('incoming', [b'{"id":1,"id":1}\n', b'{"id":NaN}\n',
                                     b'{"id":Infinity}\n', b'[]\n', b'null\n', b'broken\n', b'\xff\n'])
def test_invalid_ledger_stays_held(incoming):
    with pytest.raises(storage.StorageError):
        io._identical_real_ledger_events(b'{"id":1}\n', incoming)


def test_receipt_retry_allowance_is_not_expanded_to_ledgers():
    assert io.RECEIPT_PATHS == frozenset({'dashboard-private/manifest.json',
                                        'dashboard-private/migration-journal.jsonl'})
