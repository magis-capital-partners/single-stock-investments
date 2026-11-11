"""Original paid bytes and append-only real ledger values survive storage upgrade."""
import json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from private_storage_io import _retain_or_advance_private_bytes
from private_storage import StorageError

def test_equivalent_json_keeps_exact_original_paid_bytes(tmp_path):
    path=tmp_path/'paid.json';original=b'{\r\n "usage": {"input":1,"output":null}, "status":"unknown"\r\n}\r\n';path.write_bytes(original)
    private=b'{"status":"unknown","usage":{"output":null,"input":1}}\n'
    result=_retain_or_advance_private_bytes(path,'runtime/paid.json',private)
    assert result['action']=='retain_original_serialization' and path.read_bytes()==original

@pytest.mark.parametrize('incoming',[b'{"amount":1.0}',b'{"amount":true}',b'{"amount":2}'])
def test_financial_values_types_and_missing_fields_cannot_be_treated_as_serialization(tmp_path,incoming):
    path=tmp_path/'paid.json';path.write_bytes(b'{"amount":1}')
    assert _retain_or_advance_private_bytes(path,'runtime/paid.json',incoming) is None
    assert path.read_bytes()==b'{"amount":1}'

def test_equal_ledger_rows_keep_every_original_raw_byte(tmp_path):
    path=tmp_path/'ledger.jsonl';original=b'{ "id":1, "status":"unknown" }\r\n\r\n{"id":2,"status":"pending"}\r\n';path.write_bytes(original)
    incoming=b'{"status":"unknown","id":1}\n{"status":"pending","id":2}\n'
    result=_retain_or_advance_private_bytes(path,'runtime/ledger.jsonl',incoming)
    assert result['original_rows']==result['final_rows']==2 and path.read_bytes()==original

@pytest.mark.parametrize('newline',[b'\n',b'\r\n',b''])
def test_only_new_verified_rows_append_and_original_prefix_is_exact(tmp_path,newline):
    path=tmp_path/'ledger.jsonl';original=b'{ "id":1, "status":"reported" }'+newline;path.write_bytes(original)
    incoming=b'{"status":"reported","id":1}\n{"id":2,"status":"pending"}\n'
    result=_retain_or_advance_private_bytes(path,'runtime/ledger.jsonl',incoming)
    assert path.read_bytes().startswith(original) and result['original_raw_bytes_remain_exact_prefix']
    rows=[json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]
    assert rows==[{'id':1,'status':'reported'},{'id':2,'status':'pending'}]

@pytest.mark.parametrize('incoming',[b'{"id":1,"status":"reported"}\n',b'{"id":2,"status":"pending"}\n{"id":1,"status":"unknown"}\n',b'{"id":1,"status":"reported"}\n{"id":2,"status":"pending"}\n',b'{"id":1.0,"status":"unknown"}\n{"id":2,"status":"pending"}\n'])
def test_older_reordered_reclassified_or_type_changed_ledger_is_refused(tmp_path,incoming):
    path=tmp_path/'ledger.jsonl';original=b'{"id":1,"status":"unknown"}\n{"id":2,"status":"pending"}\n';path.write_bytes(original)
    with pytest.raises(StorageError):_retain_or_advance_private_bytes(path,'runtime/ledger.jsonl',incoming)
    assert path.read_bytes()==original

@pytest.mark.parametrize('incoming',[b'{"id":1,"id":2}\n',b'{"id":NaN}\n',b'[]\n'])
def test_malformed_ledger_never_overwrites_original(tmp_path,incoming):
    path=tmp_path/'ledger.jsonl';original=b'{"id":1}\n';path.write_bytes(original)
    with pytest.raises(StorageError):_retain_or_advance_private_bytes(path,'runtime/ledger.jsonl',incoming)
    assert path.read_bytes()==original
