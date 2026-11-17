"""Lossless joined string arrays over the complete transport/9 envelope."""
from __future__ import annotations
import copy
import re
from underwriting_contract import digest, require
from underwriting_dictionary_transport import SCHEMA as INNER_SCHEMA, INSTRUCTIONS as INNER_INSTRUCTIONS
from underwriting_token_transport import MAX_ENTRIES, MAX_DICTIONARY_TEXT

SCHEMA='underwriting-transport/10'
ARRAY='|A|'
LITERAL='|S|'
INSTRUCTIONS=(
    'The payload uses underwriting-transport/10 LOSSLESS storage, not a summary. '
    'FIRST restore encoded_envelope values recursively, keeping object keys unchanged. '
    'A string beginning |S| restores to the exact remaining string, without further decoding. '
    'A string beginning |A| restores to an ordered list of strings: scan the remainder, '
    'split at each unescaped |, and decode ONLY backslash-backslash to one backslash '
    'and backslash-| to one literal |. Keep empty members. Do not decode restored members again. '
    'Every other string and primitive stays unchanged; recurse into ordinary arrays and objects. '
    'Then apply ALL following unchanged transport/9 rules to the restored inner envelope. '
    'All original characters, types, order, IDs, hashes and evidence remain unchanged.\n'
    +INNER_INSTRUCTIONS)

def _joined(values):
    return ARRAY+'|'.join(value.replace('\\','\\\\').replace('|','\\|') for value in values)

def _restore_members(text):
    require(len(text)<=MAX_DICTIONARY_TEXT,'Joined array exceeds existing text bound')
    values=[];part=[];index=0
    while index<len(text):
        char=text[index]
        if char=='\\':
            index+=1
            require(index<len(text) and text[index] in ('\\','|'),'Invalid joined-array escape')
            part.append(text[index])
        elif char=='|':
            values.append(''.join(part));part=[]
            require(len(values)<MAX_ENTRIES,'Joined array exceeds existing entry bound')
        else:
            part.append(char)
        index+=1
    values.append(''.join(part))
    return values

def _restore(value):
    if isinstance(value,dict):
        return {key:_restore(item) for key,item in value.items()}
    if isinstance(value,list):
        return [_restore(item) for item in value]
    if isinstance(value,str) and value.startswith('|'):
        if value.startswith(LITERAL):
            original=value[len(LITERAL):]
            require(original.startswith('|'),'Invalid joined-array literal escape')
            return original
        require(value.startswith(ARRAY),'Unknown joined-array marker')
        return _restore_members(value[len(ARRAY):])
    return copy.deepcopy(value)

def compact(envelope):
    from underwriting_transport import encoded
    from underwriting_dictionary_transport import unpack as unpack_inner
    require(isinstance(envelope,dict) and envelope.get('schema_version')==INNER_SCHEMA,
            'Joined arrays require the complete transport/9 envelope')
    original=unpack_inner(envelope)
    def pack(value):
        if isinstance(value,dict):
            return {key:pack(item) for key,item in value.items()}
        if isinstance(value,list):
            if value and len(value)<=MAX_ENTRIES and all(type(item) is str for item in value):
                candidate=_joined(value)
                if len(encoded(candidate))<len(encoded(value)):
                    return candidate
            return [pack(item) for item in value]
        if isinstance(value,str) and value.startswith('|'):
            return LITERAL+value
        return copy.deepcopy(value)
    result={'schema_version':SCHEMA,'payload_hash':envelope['payload_hash'],
            'transport_hash':digest(envelope),'encoded_envelope':pack(envelope)}
    require(encoded(_restore(result['encoded_envelope']))==encoded(envelope),
            'Joined arrays changed the complete inner envelope')
    require(encoded(unpack(result))==encoded(original),
            'Joined arrays changed original characters, types or order')
    return result

def unpack(envelope):
    from underwriting_dictionary_transport import unpack as unpack_inner
    require(isinstance(envelope,dict) and set(envelope)=={
        'schema_version','payload_hash','transport_hash','encoded_envelope'},
        'Invalid joined-array envelope fields')
    require(envelope['schema_version']==SCHEMA and all(isinstance(envelope[key],str)
            and re.fullmatch(r'[0-9a-f]{64}',envelope[key])
            for key in ('payload_hash','transport_hash')),'Invalid joined-array identity')
    require(isinstance(envelope['encoded_envelope'],dict),'Invalid joined-array inner envelope')
    restored=_restore(envelope['encoded_envelope'])
    require(restored.get('schema_version')==INNER_SCHEMA and
            restored.get('payload_hash')==envelope['payload_hash'] and
            digest(restored)==envelope['transport_hash'],'Joined-array inner identity changed')
    # Keep every existing dictionary, scope, escape, ordering, depth, expansion
    # and original payload hash guard in the unchanged transport/9 decoder.
    return unpack_inner(restored)
