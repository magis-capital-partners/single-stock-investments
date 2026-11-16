"""Lossless one-character containers over the existing bounded transport/6."""
from __future__ import annotations
import copy
from underwriting_contract import require
from underwriting_compact_transport import INSTRUCTIONS as OLD_INSTRUCTIONS, MAX_CONTAINER_DEPTH

SCHEMA='underwriting-transport/7'
TOKEN='^'
OBJECT='!'
LITERAL='$literal_v7'
INSTRUCTIONS=OLD_INSTRUCTIONS.replace('underwriting-transport/6',SCHEMA).replace('$t objects','^ objects').replace('$o stores','! stores')+(
    'Container ! restores the exact one-key $o object; ^ restores the exact one-key $t object. '
    'Before those expansions, $literal_v7 restores its ordered [key,value] pairs: restore values, '
    'preserve the literal keys, and never reinterpret that restored object.\n')


def compact(envelope):
    from underwriting_transport import encoded
    from underwriting_compact_transport import unpack as unpack_old
    require(envelope.get('schema_version')=='underwriting-transport/6','Marker source must use transport/6')
    original=unpack_old(envelope)
    def convert(value,depth=0):
        require(depth<=MAX_CONTAINER_DEPTH,'Marker container depth exceeds bound')
        if isinstance(value,dict):
            if set(value)=={'$t'}:
                require(isinstance(value['$t'],str),'Invalid token container')
                return {TOKEN:value['$t']}
            if set(value)=={'$o'}:
                require(isinstance(value['$o'],list),'Invalid schema container')
                return {OBJECT:convert(value['$o'],depth+1)}
            if {TOKEN,OBJECT,LITERAL}.intersection(value):
                return {LITERAL:[[key,convert(item,depth+1)] for key,item in value.items()]}
            return {key:convert(item,depth+1) for key,item in value.items()}
        if isinstance(value,list):return [convert(item,depth+1) for item in value]
        return copy.deepcopy(value)
    result={**copy.deepcopy(envelope),'schema_version':SCHEMA,
            'payload':convert(envelope['payload']),'string_dictionary':convert(envelope['string_dictionary'])}
    require(encoded(unpack(result))==encoded(original),'Marker transport changed source characters, types or order')
    return result


def unpack(envelope):
    from underwriting_compact_transport import unpack as unpack_old
    require(envelope.get('schema_version')==SCHEMA,'Unknown marker transport')
    require(set(envelope)=={'schema_version','payload_hash','payload','object_schemas','string_dictionary',
                            'literal_dictionary','derived_dictionary','maximum_dag_depth','literal_escape'},
            'Invalid marker envelope fields')
    def restore(value,depth=0):
        require(depth<=MAX_CONTAINER_DEPTH,'Marker container depth exceeds bound')
        if isinstance(value,dict):
            if TOKEN in value:
                require(set(value)=={TOKEN} and isinstance(value[TOKEN],str),'Ambiguous marker token object')
                return {'$t':value[TOKEN]}
            if OBJECT in value:
                require(set(value)=={OBJECT} and isinstance(value[OBJECT],list),'Ambiguous marker schema object')
                return {'$o':restore(value[OBJECT],depth+1)}
            if LITERAL in value:
                require(set(value)=={LITERAL} and isinstance(value[LITERAL],list),'Invalid marker literal object')
                result={}
                for pair in value[LITERAL]:
                    require(isinstance(pair,list) and len(pair)==2 and isinstance(pair[0],str)
                            and pair[0] not in result,'Invalid marker literal keys')
                    result[pair[0]]=restore(pair[1],depth+1)
                return result
            require('$t' not in value and '$o' not in value,'Unconverted compact marker')
            return {key:restore(item,depth+1) for key,item in value.items()}
        if isinstance(value,list):return [restore(item,depth+1) for item in value]
        return copy.deepcopy(value)
    original={**copy.deepcopy(envelope),'schema_version':'underwriting-transport/6',
              'payload':restore(envelope['payload']),'string_dictionary':restore(envelope['string_dictionary'])}
    return unpack_old(original)


STRING_SCHEMA='underwriting-transport/8'
STRING_ESCAPE='~'
STRING_INSTRUCTIONS=(
    'The payload uses underwriting-transport/8 LOSSLESS storage, not a summary. '
    'FIRST restore strings recursively in payload and string_dictionary ONLY: a string starting ~ '
    'must have ^ or ~ immediately after it; remove exactly that first ~ and keep the result literal '
    'without interpreting it again. A string starting ^ instead restores the one-key ^ object '
    'whose value is every remaining character unchanged. Other strings stay literal. '
    'Dictionary entries outside string_dictionary and all schema keys remain untouched. '
    'Then apply the following unchanged container and source restoration rules.\n'
    +INSTRUCTIONS.replace(SCHEMA,STRING_SCHEMA))


def compact_strings(envelope):
    from underwriting_transport import encoded
    require(envelope.get('schema_version')==SCHEMA,'String source must use transport/7')
    original=unpack(envelope)
    def convert(value,depth=0):
        require(depth<=MAX_CONTAINER_DEPTH,'String container depth exceeds bound')
        if isinstance(value,dict):
            if set(value)=={TOKEN}:
                require(isinstance(value[TOKEN],str),'Invalid marker token string')
                return TOKEN+value[TOKEN]
            return {key:convert(item,depth+1) for key,item in value.items()}
        if isinstance(value,list):return [convert(item,depth+1) for item in value]
        if isinstance(value,str) and value.startswith((TOKEN,STRING_ESCAPE)):
            return STRING_ESCAPE+value
        return copy.deepcopy(value)
    result={**copy.deepcopy(envelope),'schema_version':STRING_SCHEMA,
            'payload':convert(envelope['payload']),'string_dictionary':convert(envelope['string_dictionary'])}
    require(encoded(unpack_strings(result))==encoded(original),'String transport changed original characters, types or order')
    return result


def unpack_strings(envelope):
    require(envelope.get('schema_version')==STRING_SCHEMA,'Unknown string transport')
    def restore(value,depth=0):
        require(depth<=MAX_CONTAINER_DEPTH,'String container depth exceeds bound')
        if isinstance(value,str):
            if value.startswith(STRING_ESCAPE):
                require(len(value)>1 and value[1] in (TOKEN,STRING_ESCAPE),'Invalid string literal escape')
                return value[1:]
            if value.startswith(TOKEN):return {TOKEN:value[1:]}
            return value
        if isinstance(value,dict):
            require(TOKEN not in value,'Unconverted string token container')
            return {key:restore(item,depth+1) for key,item in value.items()}
        if isinstance(value,list):return [restore(item,depth+1) for item in value]
        return copy.deepcopy(value)
    original={**copy.deepcopy(envelope),'schema_version':SCHEMA,
              'payload':restore(envelope['payload']),'string_dictionary':restore(envelope['string_dictionary'])}
    return unpack(original)
