"""Lossless prompt transport. Original evidence IDs and hashes never change."""
from __future__ import annotations

import copy
import json
from collections import Counter

from underwriting_contract import digest, require

REFERENCE = '$underwriting_string'
INSTRUCTIONS = ('The payload uses underwriting-transport/1 lossless storage. Resolve objects '
                'containing only $underwriting_string through the zero-based string_dictionary. '
                'Restore observations by zipping each observations_table group columns with each row. '
                'All original observation IDs, facts, text, units and packet hashes are unchanged. '
                'Use original IDs in your response, never transport dictionary indexes.\n')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def pack(payload):
    counts = Counter()

    def count(value):
        if isinstance(value, dict):
            require(REFERENCE not in value, 'Reserved transport key in source evidence')
            for item in value.values():
                count(item)
        elif isinstance(value, list):
            for item in value:
                count(item)
        elif isinstance(value, str):
            counts[value] += 1

    count(payload)
    strings, indices = [], {}

    def convert(value):
        if isinstance(value, dict):
            result = {key: convert(item) for key, item in value.items()}
            rows = result.get('observations')
            if isinstance(rows, list) and rows and all(isinstance(row, dict) for row in rows):
                groups = []
                for row in rows:
                    columns = list(row)
                    if not groups or groups[-1]['columns'] != columns:
                        groups.append({'columns': columns, 'rows': []})
                    groups[-1]['rows'].append(list(row.values()))
                result.pop('observations')
                result['observations_table'] = groups
            return result
        if isinstance(value, list):
            return [convert(item) for item in value]
        if isinstance(value, str) and len(value) > 30 and counts[value] >= 3:
            if value not in indices:
                indices[value] = len(strings)
                strings.append(value)
            return {REFERENCE: indices[value]}
        return value

    envelope = {'schema_version': 'underwriting-transport/1', 'payload_hash': digest(payload),
                'payload': convert(payload), 'string_dictionary': strings}
    require(unpack(envelope) == payload, 'Prompt transport failed lossless verification')
    return envelope


def unpack(envelope):
    require(envelope.get('schema_version') == 'underwriting-transport/1', 'Unknown prompt transport')
    strings = envelope['string_dictionary']

    def restore(value):
        if isinstance(value, dict):
            if set(value) == {REFERENCE}:
                index = value[REFERENCE]
                require(type(index) is int and 0 <= index < len(strings), 'Invalid transport string reference')
                return strings[index]
            result = {key: restore(item) for key, item in value.items()}
            if 'observations_table' in result:
                result['observations'] = []
                for group in result.pop('observations_table'):
                    for row in group['rows']:
                        require(len(row) == len(group['columns']), 'Incomplete transport observation')
                        result['observations'].append(dict(zip(group['columns'], row)))
            return result
        if isinstance(value, list):
            return [restore(item) for item in value]
        return copy.deepcopy(value)

    result = restore(envelope['payload'])
    require(digest(result) == envelope['payload_hash'], 'Transport evidence changed')
    return result


def render(payload):
    original = encoded(payload)
    candidate = INSTRUCTIONS+encoded(pack(payload))
    return candidate if len(candidate) < len(original) else original
