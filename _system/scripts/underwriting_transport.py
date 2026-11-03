"""Lossless prompt transport. Original evidence IDs and hashes never change."""
from __future__ import annotations

import copy
import json
import re
import zlib
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


def _pack_legacy(payload):
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


def _unpack_legacy(envelope):
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


DENSE_INSTRUCTIONS = ('The payload uses underwriting-transport/2 LOSSLESS storage, not a summary. '
    'Decode recursively: a string exactly @<digits> is a zero-based reference to string_dictionary; '
    'a literal string beginning @@ loses exactly one leading @; '
    'dictionary entries and schema keys are literal, so decode only the payload; '
    'an object containing only $o has [schema_index, values], zipped with object_schemas[schema_index]; '
    'an object containing only $text is a list of literal strings or references, concatenated EXACTLY in order. '
    'Shared source passages are stored once. All original characters, observation order, missing/null '
    'distinctions, IDs, units, facts, quotations and hashes are preserved. Use original evidence IDs, never dictionary indexes.\n')


def _segments(text):
    # Keep every delimiter and whitespace character. Shifted, overlapping source
    # windows share complete sentences even when neither contains the other.
    return re.split(r'(?<=[.!?;,:])(?=\s)', text) if len(text) > 256 else [text]


def _content_segments(text):
    if len(text) <= 256: return [text]
    parts, buffer = [], ''
    for match in re.finditer(r'\S+\s*|\s+',text):
        word = match.group()
        buffer += word
        # Boundaries depend on source words, not their absolute position, so
        # overlapping windows still share passages after an insertion. CRC is
        # only a boundary selector; exact strings and SHA hashes prove identity.
        if len(buffer) >= 64 and (len(buffer) >= 384 or zlib.crc32(word.encode('utf-8')) & 15 == 0):
            parts.append(buffer); buffer = ''
    if buffer: parts.append(buffer)
    return parts


def _pack_dense(payload, segments):
    schemas, whole, counts = Counter(), Counter(), Counter()
    markers = {'$s', '$o', '$text'}
    def count(value):
        if isinstance(value, dict):
            require(all(isinstance(k,str) for k in value), 'Transport object keys must be strings')
            schemas[tuple(value)] += 1
            for item in value.values(): count(item)
        elif isinstance(value, list):
            for item in value: count(item)
        elif isinstance(value, str):
            whole[value] += 1
            counts[value] += 1
            pieces = segments(value)
            if len(pieces) > 1: counts.update(pieces)
    count(payload)
    strings, string_ids, columns, schema_ids = [], {}, [], {}
    def reference(text):
        if text not in string_ids:
            string_ids[text] = len(strings)
            strings.append(text)
        return '@'+str(string_ids[text])
    def shared(text):
        return counts[text] >= 2 and len(text) > 30
    def convert(value):
        if isinstance(value, dict):
            keys = tuple(value)
            values = [convert(v) for v in value.values()]
            if markers.intersection(keys) or (schemas[keys] >= 2 and sum(len(k)+3 for k in keys) > 35):
                if keys not in schema_ids:
                    schema_ids[keys] = len(columns)
                    columns.append(list(keys))
                return {'$o':[schema_ids[keys], values]}
            return dict(zip(keys,values))
        if isinstance(value, list): return [convert(v) for v in value]
        if isinstance(value, str):
            if whole[value] >= 2 and shared(value): return reference(value)
            pieces, literal, has_reference = [], '', False
            def escaped(text): return '@'+text if text.startswith('@') else text
            for piece in segments(value):
                if shared(piece):
                    if literal: pieces.append(escaped(literal)); literal = ''
                    pieces.append(reference(piece))
                    has_reference = True
                else: literal += piece
            if literal: pieces.append(escaped(literal))
            return {'$text':pieces} if has_reference else escaped(value)
        return value
    envelope = {'schema_version':'underwriting-transport/2', 'payload_hash':digest(payload),
                'payload':convert(payload), 'object_schemas':columns, 'string_dictionary':strings}
    require(unpack(envelope) == payload, 'Prompt transport failed lossless verification')
    return envelope


def pack(payload):
    return min((_pack_dense(payload,_segments), _pack_dense(payload,_content_segments)),key=lambda e:len(encoded(e)))


def unpack(envelope):
    if envelope.get('schema_version') == 'underwriting-transport/1': return _unpack_legacy(envelope)
    require(envelope.get('schema_version') == 'underwriting-transport/2', 'Unknown prompt transport')
    strings, schemas = envelope['string_dictionary'], envelope['object_schemas']
    require(isinstance(strings,list) and all(isinstance(s,str) for s in strings), 'Invalid string dictionary')
    require(isinstance(schemas,list) and all(isinstance(s,list) and all(isinstance(k,str) for k in s)
        and len(set(s)) == len(s) for s in schemas), 'Invalid object schemas')
    def restore(value):
        if isinstance(value,dict):
            if set(value) == {'$s'}:
                index = value['$s']
                require(type(index) is int and 0 <= index < len(strings), 'Invalid transport string reference')
                return strings[index]
            if set(value) == {'$o'}:
                pair = value['$o']
                require(isinstance(pair,list) and len(pair)==2, 'Invalid transport object')
                index,row = pair
                require(type(index) is int and 0 <= index < len(schemas) and isinstance(row,list)
                    and len(row)==len(schemas[index]), 'Incomplete transport object')
                return dict(zip(schemas[index],(restore(v) for v in row)))
            if set(value) == {'$text'}:
                require(isinstance(value['$text'],list), 'Invalid source text segments')
                parts = [restore(v) for v in value['$text']]
                require(all(isinstance(v,str) for v in parts), 'Invalid source text segment')
                return ''.join(parts)
            return {k:restore(v) for k,v in value.items()}
        if isinstance(value,list): return [restore(v) for v in value]
        if isinstance(value,str):
            if value.startswith('@@'): return value[1:]
            if re.fullmatch(r'@\d+',value):
                index = int(value[1:])
                require(0 <= index < len(strings), 'Invalid transport string reference')
                return strings[index]
        return copy.deepcopy(value)
    result = restore(envelope['payload'])
    require(digest(result)==envelope['payload_hash'], 'Transport evidence changed')
    return result


def render(payload):
    candidates = [encoded(payload), DENSE_INSTRUCTIONS+encoded(pack(payload))]
    # Retain the old, readable layout when it is smaller, and continue decoding
    # saved paid prompts without changing their evidence or session identities.
    if REFERENCE not in encoded(payload):
        candidates.append(INSTRUCTIONS+encoded(_pack_legacy(payload)))
    return min(candidates,key=len)
