"""Short repeated primary phrases must retain every literal character and claim."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from underwriting_codex import MAX_INPUT_CHARACTERS, validate_input
from underwriting_contract import ContractError, digest
from underwriting_transport import _best_dense, _pack_legacy, encoded, pack, render, unpack


def source_payload():
    return {"packet": {"documents": [
        {"id": "doc_" + str(i), "contexts": [
            "".join("unaltered primary source passage item_" + str(i) + "_" + str(j) + " "
                    for j in range(40))]}
        for i in range(24)]}}


def test_complete_shifted_short_passages_fit_the_actual_native_gate():
    payload = source_payload()
    original_hash = digest(payload)
    rendered = render(payload)
    # Keep the native gate itself as the signal. The old storage misses short
    # phrases surrounded by unique source words and spends this room on repeats.
    validate_input("H" * (MAX_INPUT_CHARACTERS - 24_000) + rendered)
    assert unpack(pack(payload)) == payload
    assert digest(payload) == original_hash


@pytest.mark.parametrize('literal', [
    '«0»', '««123»', '«-1»', '«unclosed', '@0', '@@9', '日本語 😃\r\n\t',
])
def test_inline_escapes_original_markers_unicode_and_whitespace(literal):
    payload = source_payload()
    payload['packet']['documents'][0]['contexts'][0] = literal + ' ' + payload['packet']['documents'][0]['contexts'][0]
    payload['literal_objects'] = [
        {'$inline': literal},
        {'$literal_object': [['duplicate', 1], ['duplicate', 2]]},
        {'$inline': {'nested': literal}, '$literal_object': None},
        {'float': 1.0, 'integer': 1, 'zero': 0, 'false': False, 'null': None},
        {'missing': 'The absent field must stay absent'},
    ]
    before = digest(payload)
    envelope = pack(payload)
    assert envelope['schema_version'] == 'underwriting-transport/3'
    restored = unpack(envelope)
    assert restored == payload and digest(restored) == before
    assert type(restored['literal_objects'][3]['float']) is float
    assert type(restored['literal_objects'][3]['integer']) is int
    assert type(restored['literal_objects'][3]['false']) is bool
    assert 'null' not in restored['literal_objects'][4]


def test_phrase_entries_are_literal_and_never_recursively_decoded():
    payload = source_payload()
    for doc in payload['packet']['documents']:
        doc['contexts'][0] = doc['contexts'][0].replace('primary source', 'primary «0» @@3 source')
    envelope = pack(payload)
    assert envelope['schema_version'] == 'underwriting-transport/3'
    assert any('«0»' in s or '@@3' in s for s in envelope['phrase_dictionary'])
    assert unpack(envelope) == payload


@pytest.mark.parametrize('bad', ['«', '«-1»', '«00»', '«999999999999999999999»', '«１２»', None, 0])
def test_malformed_inline_references_are_rejected(bad):
    envelope = pack(source_payload())
    assert envelope['schema_version'] == 'underwriting-transport/3'
    envelope['payload'] = {'$inline': bad}
    with pytest.raises(ContractError, match='inline'):
        unpack(envelope)


def test_changed_or_unused_phrase_entries_cannot_bypass_the_payload_hash():
    envelope = pack(source_payload())
    changed = copy.deepcopy(envelope)
    changed['phrase_dictionary'][0] += ' changed'
    with pytest.raises(ContractError, match='changed'):
        unpack(changed)
    unused = copy.deepcopy(envelope)
    unused['phrase_dictionary'].append('unbound source passage')
    with pytest.raises(ContractError, match='Unused inline'):
        unpack(unused)
    invalid = copy.deepcopy(envelope)
    invalid['phrase_dictionary'][0] = 0
    with pytest.raises(ContractError, match='Invalid inline dictionary'):
        unpack(invalid)


@pytest.mark.parametrize('pairs', [None, [['key']], [[0, 'value']], [['x', 1], ['x', 2]]])
def test_malformed_literal_object_wrappers_are_rejected(pairs):
    envelope = pack(source_payload())
    envelope['payload'] = {'$literal_object': pairs}
    with pytest.raises(ContractError, match='literal transport'):
        unpack(envelope)


def test_saved_v1_v2_envelopes_keep_their_original_decode_rules():
    payload = {'observations': [{'id': 'obs_1', 'value': 1.0}, {'id': 'obs_2', 'value': None}],
               '$inline': 'literal «0»', '$literal_object': [['literal', True]], 'refs': ['@0', '@@9']}
    for saved in (_pack_legacy(payload), _best_dense(payload)):
        assert saved['schema_version'] in {'underwriting-transport/1', 'underwriting-transport/2'}
        assert unpack(saved) == payload


def test_inline_rendering_is_deterministic_and_never_changes_the_input():
    payload = source_payload()
    before = copy.deepcopy(payload)
    assert encoded(pack(payload)) == encoded(pack(copy.deepcopy(payload)))
    assert render(payload) == render(copy.deepcopy(payload))
    assert payload == before

