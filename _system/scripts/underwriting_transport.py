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

INLINE_INSTRUCTIONS = ('The payload uses underwriting-transport/3 LOSSLESS storage, not a summary. '
    'First restore inline objects in payload and string_dictionary: an object containing only $inline '
    'stores full text where literal «« becomes one « and «digits» is a zero-based reference into '
    'the literal phrase_dictionary. Concatenate exactly; never recursively decode a phrase entry. '
    'An object containing only $literal_object stores its original literal keys and values as ordered '
    '[key,value] pairs; restore each value, then the object. After this first pass, decode recursively: '
    'a string exactly @<digits> references string_dictionary; a literal string beginning @@ loses '
    'exactly one leading @. String dictionary entries and schema keys are literal in this second pass. '
    'An object containing only $o has [schema_index,values], zipped with object_schemas[schema_index]; '
    'an object containing only $text is a list of literal strings or references concatenated EXACTLY '
    'in order. All original source characters, observation order, missing/null distinctions, types, '
    'IDs, units, facts, quotations and hashes are preserved. Use original evidence IDs in responses, '
    'never transport indexes.\n')


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


def _pack_dense(payload, segments, minimum_shared_length=30):
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
        return counts[text] >= 2 and len(text) > minimum_shared_length
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


def _dense_layouts(payload):
    # Primary document IDs and dates are short but repeat across many facts.
    # Keep the original layouts: reference overhead can outweigh their savings
    # on small packets. Every candidate has the same verified decoded payload.
    return (_pack_dense(payload, segments, threshold)
            for threshold in (30, 8) for segments in (_segments, _content_segments))


def _best_dense(payload):
    return min(_dense_layouts(payload), key=lambda e: len(encoded(e)))


def _inline_parts(text, dictionary_size):
    """Yield literal text and integer references, with no recursive expansion."""
    require(isinstance(text, str), 'Invalid inline source text')
    position = 0
    while position < len(text):
        opening = text.find('«', position)
        if opening < 0:
            yield text[position:]
            return
        if opening > position:
            yield text[position:opening]
        if text.startswith('««', opening):
            yield '«'
            position = opening + 2
            continue
        closing = text.find('»', opening + 1)
        require(closing >= 0, 'Incomplete inline reference')
        digits = text[opening + 1:closing]
        require(re.fullmatch(r'[0-9]+', digits) is not None and
                len(digits) <= len(str(max(0, dictionary_size - 1))), 'Invalid inline reference')
        index = int(digits)
        require(str(index) == digits and index < dictionary_size, 'Invalid inline reference')
        yield index
        position = closing + 1


def _phrase_candidates(envelope, limit):
    # Learn exact word spans, not summaries or replacements of financial facts.
    # Fixed-width/source-boundary chunks miss short repeated legal phrases when
    # each occurrence is surrounded by different words. Limit the vocabulary,
    # while every unselected character remains literal in the complete payload.
    texts = set()
    def collect(value):
        if isinstance(value, dict):
            for item in value.values(): collect(item)
        elif isinstance(value, list):
            for item in value: collect(item)
        elif isinstance(value, str) and len(value) > 128:
            texts.add(value)
    collect(envelope['payload'])
    collect(envelope['string_dictionary'])
    counts = Counter()
    for text in sorted(texts):
        words = re.findall(r'\S+\s*|\s+', text)
        for size in (1, 2, 3, 4, 6, 8):
            counts.update(''.join(words[i:i + size]) for i in range(len(words) - size + 1))
    ranked = sorted(((len(s) * (n - 1) - 6 * n - 4, s)
                     for s, n in counts.items() if n >= 2 and len(s) > 6), reverse=True)
    return [text for saving, text in ranked if saving > 8][:limit]


def _pack_inline(envelope, *, phrases=None, shortest=False):
    phrases = _phrase_candidates(envelope, 4096) if phrases is None else phrases
    if not phrases:
        return None
    indices, trie = {s: i for i, s in enumerate(phrases)}, {}
    for phrase in phrases:
        node = trie
        for word in re.findall(r'\S+\s*|\s+', phrase):
            node = node.setdefault(word, {})
        node[None] = phrase

    def inline(text):
        if len(text) <= 128:
            return text
        words, parts, position = re.findall(r'\S+\s*|\s+', text), [], 0
        if shortest:
            size = len(words)
            costs, choices = [0] * (size + 1), [None] * size
            for position in range(size - 1, -1, -1):
                literal = words[position].replace('«', '««')
                best_cost = len(encoded(literal)) - 2 + costs[position + 1]
                best = (position + 1, literal)
                node = trie
                for i in range(position, min(position + 8, size)):
                    node = node.get(words[i])
                    if node is None:
                        break
                    if None in node:
                        ref = '«' + str(indices[node[None]]) + '»'
                        cost = len(ref) + costs[i + 1]
                        if cost < best_cost:
                            best_cost, best = cost, (i + 1, ref)
                costs[position], choices[position] = best_cost, best
            position = 0
            while position < size:
                position, part = choices[position]
                parts.append(part)
            candidate = {'$inline': ''.join(parts)}
            return candidate if len(encoded(candidate)) < len(encoded(text)) else text
        while position < len(words):
            node, best, end = trie, None, position
            for i in range(position, min(position + 8, len(words))):
                node = node.get(words[i])
                if node is None: break
                if None in node: best, end = node[None], i + 1
            if best is None:
                parts.append(words[position].replace('«', '««'))
                position += 1
            else:
                parts.append('«' + str(indices[best]) + '»')
                position = end
        candidate = {'$inline': ''.join(parts)}
        return candidate if len(encoded(candidate)) < len(encoded(text)) else text

    def convert(value):
        if isinstance(value, str): return inline(value)
        if isinstance(value, list): return [convert(v) for v in value]
        if isinstance(value, dict):
            if {'$inline', '$literal_object'}.intersection(value):
                return {'$literal_object': [[k, convert(v)] for k, v in value.items()]}
            return {k: convert(v) for k, v in value.items()}
        return value

    result = {**envelope, 'schema_version': 'underwriting-transport/3',
              'payload': convert(envelope['payload']),
              'string_dictionary': convert(envelope['string_dictionary'])}
    used = Counter()
    def count_references(value):
        if isinstance(value, dict):
            if set(value) == {'$inline'}:
                used.update(p for p in _inline_parts(value['$inline'], len(phrases)) if type(p) is int)
            else:
                for v in value.values(): count_references(v)
        elif isinstance(value, list):
            for v in value: count_references(v)
    count_references(result['payload'])
    count_references(result['string_dictionary'])
    # Unused candidates are never sent to the model. Put the most-used exact
    # phrases first so their references stay short; do not change any source ID.
    order = sorted(used, key=lambda i: (-used[i], phrases[i]))
    remapping = {old: new for new, old in enumerate(order)}
    def renumber(value):
        if isinstance(value, dict):
            if set(value) == {'$inline'}:
                return {'$inline': ''.join('«' + str(remapping[p]) + '»' if type(p) is int
                    else p.replace('«', '««') for p in _inline_parts(value['$inline'], len(phrases)))}
            return {k: renumber(v) for k, v in value.items()}
        if isinstance(value, list): return [renumber(v) for v in value]
        return value
    result['payload'] = renumber(result['payload'])
    result['string_dictionary'] = renumber(result['string_dictionary'])
    result['phrase_dictionary'] = [phrases[i] for i in order]
    require(unpack(result) == unpack(envelope), 'Inline transport failed lossless verification')
    return result


def _unpack_inline(envelope):
    phrases = envelope.get('phrase_dictionary')
    require(isinstance(phrases, list) and all(isinstance(s, str) for s in phrases),
            'Invalid inline dictionary')
    used = set()
    def restore(value):
        if isinstance(value, dict):
            if set(value) == {'$inline'}:
                parts = list(_inline_parts(value['$inline'], len(phrases)))
                used.update(p for p in parts if type(p) is int)
                return ''.join(phrases[p] if type(p) is int else p for p in parts)
            if set(value) == {'$literal_object'}:
                pairs = value['$literal_object']
                require(isinstance(pairs, list) and all(isinstance(p, list) and len(p) == 2
                    and isinstance(p[0], str) for p in pairs), 'Invalid literal transport object')
                require(len({p[0] for p in pairs}) == len(pairs), 'Duplicate literal transport key')
                return {k: restore(v) for k, v in pairs}
            return {k: restore(v) for k, v in value.items()}
        if isinstance(value, list): return [restore(v) for v in value]
        return value
    original = {**envelope, 'schema_version': 'underwriting-transport/2',
                'payload': restore(envelope['payload']),
                'string_dictionary': restore(envelope['string_dictionary'])}
    original.pop('phrase_dictionary')
    require(used == set(range(len(phrases))), 'Unused inline dictionary entry')
    return unpack(original)


GROUPED_ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_'
GROUPED_MARKERS = '~^|%'
# This is an optional encoding-search threshold, never a model admission limit.
GROUPED_MIN_CHARACTERS = 800_000
GROUPED_INSTRUCTIONS = ('The payload uses underwriting-transport/4 LOSSLESS storage, not a summary. '
    'First restore inline objects in payload and string_dictionary: an object containing only $inline '
    'stores full text. A doubled phrase_markers character is one literal marker. Otherwise a marker '
    'followed by exactly two symbols XY references the literal phrase_dictionary at 4096 times the '
    'zero-based marker position plus 64 times index(X) plus index(Y), using alphabet ' + GROUPED_ALPHABET + '. '
    'Concatenate exactly; never recursively decode a phrase entry. An object containing only '
    '$literal_object stores original literal keys and values as ordered [key,value] pairs; restore '
    'each value, then the object. After this first pass, decode recursively: a string exactly @<digits> '
    'references string_dictionary; a literal string beginning @@ loses exactly one leading @. '
    'String dictionary entries and schema keys are literal in this second pass. An object containing '
    'only $o has [schema_index,values], zipped with object_schemas[schema_index]; an object containing '
    'only $text concatenates its strings or references EXACTLY in order. All original source characters, '
    'observation order, missing/null distinctions, types, IDs, units, facts, quotations and hashes are '
    'preserved. Use original evidence IDs in responses, never transport indexes.\n')


def _grouped_parts(text, markers, dictionary_size):
    require(isinstance(text, str), 'Invalid grouped inline source text')
    position, literal = 0, []
    while position < len(text):
        char = text[position]
        if char not in markers:
            literal.append(char)
            position += 1
            continue
        require(position + 1 < len(text), 'Incomplete grouped inline reference')
        if text[position + 1] == char:
            literal.append(char)
            position += 2
            continue
        require(position + 2 < len(text), 'Incomplete grouped inline reference')
        high, low = GROUPED_ALPHABET.find(text[position + 1]), GROUPED_ALPHABET.find(text[position + 2])
        index = markers.index(char) * 4096 + high * 64 + low
        require(high >= 0 and low >= 0 and index < dictionary_size, 'Invalid grouped inline reference')
        if literal:
            yield ''.join(literal)
            literal = []
        yield index
        position += 3
    if literal:
        yield ''.join(literal)


def _group_inline(envelope):
    phrases = envelope['phrase_dictionary']
    require(0 < len(phrases) <= 16384, 'Invalid grouped dictionary capacity')
    markers = GROUPED_MARKERS[:(len(phrases) + 4095) // 4096]
    def convert(value):
        if isinstance(value, dict):
            if set(value) == {'$inline'}:
                parts = []
                for part in _inline_parts(value['$inline'], len(phrases)):
                    if type(part) is int:
                        parts.append(markers[part // 4096] + GROUPED_ALPHABET[(part % 4096) // 64]
                                     + GROUPED_ALPHABET[part % 64])
                    else:
                        for marker in markers:
                            part = part.replace(marker, marker * 2)
                        parts.append(part)
                return {'$inline': ''.join(parts)}
            return {k: convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(v) for v in value]
        return value
    result = {**envelope, 'schema_version': 'underwriting-transport/4', 'phrase_markers': markers,
              'payload': convert(envelope['payload']), 'string_dictionary': convert(envelope['string_dictionary'])}
    require(unpack(result) == unpack(envelope), 'Grouped transport failed lossless verification')
    return result


def _unpack_grouped(envelope):
    phrases = envelope.get('phrase_dictionary')
    require(isinstance(phrases, list) and 0 < len(phrases) <= 16384
            and all(isinstance(s, str) for s in phrases), 'Invalid grouped dictionary')
    markers = envelope.get('phrase_markers')
    require(markers == GROUPED_MARKERS[:(len(phrases) + 4095) // 4096], 'Invalid grouped marker alphabet')
    def restore(value):
        if isinstance(value, dict):
            if set(value) == {'$inline'}:
                return {'$inline': ''.join('«' + str(p) + '»' if type(p) is int else p.replace('«', '««')
                    for p in _grouped_parts(value['$inline'], markers, len(phrases)))}
            return {k: restore(v) for k, v in value.items()}
        if isinstance(value, list):
            return [restore(v) for v in value]
        return value
    original = {**envelope, 'schema_version': 'underwriting-transport/3',
                'payload': restore(envelope['payload']), 'string_dictionary': restore(envelope['string_dictionary'])}
    original.pop('phrase_markers')
    return _unpack_inline(original)


def _prune_inline(envelope):
    phrases, used = envelope['phrase_dictionary'], Counter()
    def count(value):
        if isinstance(value, dict):
            if set(value) == {'$inline'}:
                used.update(p for p in _inline_parts(value['$inline'], len(phrases)) if type(p) is int)
            else:
                for v in value.values():
                    count(v)
        elif isinstance(value, list):
            for v in value:
                count(v)
    count(envelope['payload'])
    count(envelope['string_dictionary'])
    remove = {i for i, n in used.items() if n * ((len(encoded(phrases[i].replace('«', '««'))) - 2)
              - (len(str(i)) + 2)) <= len(encoded(phrases[i])) + 1}
    order = [i for i in range(len(phrases)) if i not in remove]
    mapping = {old: new for new, old in enumerate(order)}
    def rebuild(value):
        if isinstance(value, dict):
            if set(value) == {'$inline'}:
                return {'$inline': ''.join(('«' + str(mapping[p]) + '»' if p not in remove
                    else phrases[p].replace('«', '««')) if type(p) is int else p.replace('«', '««')
                    for p in _inline_parts(value['$inline'], len(phrases)))}
            return {k: rebuild(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rebuild(v) for v in value]
        return value
    result = {**envelope, 'payload': rebuild(envelope['payload']),
              'string_dictionary': rebuild(envelope['string_dictionary']),
              'phrase_dictionary': [phrases[i] for i in order]}
    require(unpack(result) == unpack(envelope), 'Phrase pruning changed source evidence')
    return result, {phrases[i] for i in remove}


def _pack_grouped(dense):
    pool, candidates = _phrase_candidates(dense, 16384), []
    for _ in range(8):
        candidate = _pack_inline(dense, phrases=pool, shortest=True)
        if not candidate:
            break
        pruned, remove = _prune_inline(candidate)
        if pruned['phrase_dictionary']:
            candidates.append(_group_inline(pruned))
        if not remove:
            break
        pool = [phrase for phrase in pool if phrase not in remove]
    return min(candidates, key=lambda e: len(encoded(e))) if candidates else None


def _complete_layouts(payload):
    # Compare complete encodings: the smallest dense intermediate can split
    # passages so the later inline pass cannot share them. Keep all four
    # existing layouts until their exact-text inline sharing is finished.
    smallest = len(encoded(payload))
    last_dense = None
    for dense in _dense_layouts(payload):
        last_dense = dense
        smallest = min(smallest, len(encoded(dense)))
        yield DENSE_INSTRUCTIONS, dense
        inline = _pack_inline(dense)
        if inline:
            smallest = min(smallest, len(encoded(inline)))
            yield INLINE_INSTRUCTIONS, inline
    if smallest >= GROUPED_MIN_CHARACTERS:
        # One additional bounded search on the final content/8 layout. Retain
        # every existing complete encoding and choose only by final length.
        grouped = _pack_grouped(last_dense)
        if grouped:
            yield GROUPED_INSTRUCTIONS, grouped


def pack(payload):
    return min((envelope for _, envelope in _complete_layouts(payload)),
               key=lambda e: len(encoded(e)))


def unpack(envelope):
    if envelope.get('schema_version') == 'underwriting-transport/1': return _unpack_legacy(envelope)
    if envelope.get('schema_version') == 'underwriting-transport/3': return _unpack_inline(envelope)
    if envelope.get('schema_version') == 'underwriting-transport/4': return _unpack_grouped(envelope)
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
    candidates = [encoded(payload)]
    candidates.extend(instructions + encoded(envelope)
                      for instructions, envelope in _complete_layouts(payload))
    # Retain the old, readable layout when it is smaller, and continue decoding
    # saved paid prompts without changing their evidence or session identities.
    if REFERENCE not in encoded(payload):
        candidates.append(INSTRUCTIONS+encoded(_pack_legacy(payload)))
    return min(candidates,key=len)
