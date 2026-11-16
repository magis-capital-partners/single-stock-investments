"""Lossless short containers over the existing bounded token transport."""
from __future__ import annotations
import copy
from underwriting_contract import require
from underwriting_token_transport import INSTRUCTIONS as TOKEN_INSTRUCTIONS

SCHEMA = 'underwriting-transport/6'
LITERAL = '$literal_v6'
SHORT = '$t'
MAX_CONTAINER_DEPTH = 128
INSTRUCTIONS = TOKEN_INSTRUCTIONS.replace('underwriting-transport/5', SCHEMA).replace('$tokens objects', '$t objects') + (
    'Before token expansion, an object containing only $literal_v6 restores its ordered [key,value] pairs; '
    'restore each value, then keep those original literal keys without interpreting the restored object again.\n')


def compact(envelope):
    """Only container syntax changes; dictionary texts and all leaf values stay exact."""
    from underwriting_transport import encoded
    from underwriting_token_transport import unpack as unpack_tokens
    require(envelope.get('schema_version') == 'underwriting-transport/5', 'Compact source must use token transport/5')
    original = unpack_tokens(envelope)
    def convert(value, depth=0):
        require(depth <= MAX_CONTAINER_DEPTH, 'Compact container depth exceeds bound')
        if isinstance(value, dict):
            if '$tokens' in value:
                require(set(value) == {'$tokens'} and isinstance(value['$tokens'], str), 'Ambiguous compact source object')
                return {SHORT:value['$tokens']}
            if {SHORT,LITERAL}.intersection(value):
                return {LITERAL:[[key,convert(item,depth+1)] for key,item in value.items()]}
            return {key:convert(item,depth+1) for key,item in value.items()}
        if isinstance(value, list):
            return [convert(item,depth+1) for item in value]
        return copy.deepcopy(value)
    result = {**copy.deepcopy(envelope), 'schema_version':SCHEMA,
              'payload':convert(envelope['payload']), 'string_dictionary':convert(envelope['string_dictionary'])}
    require(encoded(unpack(result)) == encoded(original), 'Compact transport changed source characters, types or order')
    return result


def unpack(envelope):
    from underwriting_token_transport import unpack as unpack_tokens
    require(envelope.get('schema_version') == SCHEMA, 'Unknown compact transport')
    require(set(envelope) == {'schema_version','payload_hash','payload','object_schemas','string_dictionary',
                            'literal_dictionary','derived_dictionary','maximum_dag_depth','literal_escape'},
            'Invalid compact envelope fields')
    def restore(value, depth=0):
        require(depth <= MAX_CONTAINER_DEPTH, 'Compact container depth exceeds bound')
        if isinstance(value, dict):
            if SHORT in value:
                require(set(value) == {SHORT} and isinstance(value[SHORT], str), 'Ambiguous compact token object')
                return {'$tokens':value[SHORT]}
            if LITERAL in value:
                require(set(value) == {LITERAL} and isinstance(value[LITERAL],list), 'Invalid compact literal object')
                result = {}
                for pair in value[LITERAL]:
                    require(isinstance(pair,list) and len(pair)==2 and isinstance(pair[0],str)
                            and pair[0] not in result, 'Invalid compact literal keys')
                    result[pair[0]] = restore(pair[1],depth+1)
                return result
            require('$tokens' not in value, 'Unconverted token marker in compact payload')
            return {key:restore(item,depth+1) for key,item in value.items()}
        if isinstance(value, list):
            return [restore(item,depth+1) for item in value]
        return copy.deepcopy(value)
    original = {**copy.deepcopy(envelope), 'schema_version':'underwriting-transport/5',
                'payload':restore(envelope['payload']), 'string_dictionary':restore(envelope['string_dictionary'])}
    return unpack_tokens(original)
