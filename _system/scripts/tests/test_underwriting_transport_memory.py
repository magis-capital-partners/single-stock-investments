"""Complete evidence must not require simultaneous copies of every encoding."""
import hashlib
import json
from pathlib import Path
import sys
import tracemalloc

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from underwriting_contract import digest
import underwriting_transport as transport


@pytest.mark.parametrize('value', [None, True, 0, -0.0, 1e-300,
    {'text':'Original © 😀 « \\ \n', 'types':[1, 1.0, False, None], 'order':[3, 1, 2]},
    {'mixed':{1:'integer', 2:'second'}, 'empty':[{}, []]}])
def test_streamed_digest_keeps_exact_existing_canonical_identity(value):
    expected = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                        allow_nan=False).encode()).hexdigest()
    assert digest(value) == expected


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf')])
def test_digest_still_rejects_nonfinite_values(value):
    with pytest.raises(ValueError):
        digest({'source':value})


def test_digest_does_not_allocate_a_second_complete_primary_package():
    source = 'Complete original evidence © 😀 « exact bytes and types. '*2000
    payload = {'documents':[{'id':i, 'complete_text':source} for i in range(24)]}
    expected = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                        allow_nan=False).encode()).hexdigest()
    largest_string = len(json.dumps(source).encode())
    tracemalloc.start()
    try:
        result = digest(payload)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert result == expected
    assert peak < largest_string*5


def test_render_does_not_retain_all_complete_candidate_strings(monkeypatch):
    def layouts(payload):
        for index in range(16):
            yield '', {'full_source':'x'*1_000_000, 'index':index}
    monkeypatch.setattr(transport, '_complete_layouts', layouts)
    tracemalloc.start()
    try:
        rendered = transport.render({'a':1})
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert rendered == '{"a":1}'
    assert peak < 6_000_000


def test_equal_length_transport_keeps_existing_first_candidate(monkeypatch):
    monkeypatch.setattr(transport, '_complete_layouts', lambda payload: iter([('', {'b':2})]))
    assert transport.render({'a':1}) == '{"a":1}'


def test_grouped_search_keeps_only_best_complete_candidate(monkeypatch):
    live, maximum = set(), []
    class Complete(dict):
        def __init__(self, index):
            super().__init__(index=index, complete_source='x'*(100-index))
            live.add(id(self));maximum.append(len(live))
        def __del__(self):
            live.discard(id(self))
    monkeypatch.setattr(transport, '_phrase_candidates', lambda *args: list(range(8)))
    monkeypatch.setattr(transport, '_pack_inline', lambda dense, phrases, **kw: {'index':8-len(phrases)})
    monkeypatch.setattr(transport, '_prune_inline', lambda value: (
        {**value, 'phrase_dictionary':['original']}, {value['index']}))
    monkeypatch.setattr(transport, '_group_inline', lambda value: Complete(value['index']))
    result = transport._pack_grouped({})
    assert result['index'] == 7
    assert max(maximum) <= 3
