"""Lossless explicit-key dictionary rows over complete transport/8."""
from __future__ import annotations
import copy
from underwriting_contract import require
from underwriting_marker_transport import STRING_SCHEMA, STRING_INSTRUCTIONS
from underwriting_token_transport import MAX_ENTRIES

SCHEMA='underwriting-transport/9'
INSTRUCTIONS=(
    'The payload uses underwriting-transport/9 LOSSLESS storage, not a summary. '
    'FIRST restore literal_dictionary and derived_dictionary ONLY: each is an ordered list of strings. '
    'The FIRST character of each row is its exact explicit lookup key; EVERY remaining character is '
    'that entry value unchanged, including an empty value. Restore the ordered key/value objects; '
    'never calculate keys from row positions, Unicode values or any ordinal. Keep every other field '
    'unchanged. Then apply all following unchanged transport/8 restoration rules.\n'
    +STRING_INSTRUCTIONS.replace(STRING_SCHEMA,SCHEMA))


def compact(envelope):
    from underwriting_transport import encoded
    from underwriting_marker_transport import unpack_strings
    require(envelope.get('schema_version')==STRING_SCHEMA,'Dictionary rows require transport/8')
    original=unpack_strings(envelope)
    result=copy.deepcopy(envelope);result['schema_version']=SCHEMA
    for field in ('literal_dictionary','derived_dictionary'):
        result[field]=[key+value for key,value in envelope[field].items()]
    require(encoded(unpack(result))==encoded(original),'Dictionary rows changed original characters, types or order')
    return result


def unpack(envelope):
    from underwriting_marker_transport import unpack_strings
    require(envelope.get('schema_version')==SCHEMA,'Unknown dictionary-row transport')
    require(set(envelope)=={'schema_version','payload_hash','payload','object_schemas','string_dictionary',
                           'literal_dictionary','derived_dictionary','maximum_dag_depth','literal_escape'},
            'Invalid dictionary-row envelope fields')
    result=copy.deepcopy(envelope);result['schema_version']=STRING_SCHEMA
    total=0
    for field in ('literal_dictionary','derived_dictionary'):
        rows=envelope[field]
        require(isinstance(rows,list) and len(rows)<=MAX_ENTRIES,'Invalid dictionary rows')
        values={}
        for row in rows:
            require(isinstance(row,str) and len(row)>=1,'Invalid dictionary row')
            key=row[0]
            require(key not in values,'Duplicate dictionary row key')
            values[key]=row[1:]
        total+=len(values)
        require(total<=MAX_ENTRIES,'Dictionary rows exceed entry bound')
        result[field]=values
    # The unchanged decoder verifies key identity/order, disjoint scopes, all
    # backward references, escaping, depth, expansion and original payload hash.
    return unpack_strings(result)
