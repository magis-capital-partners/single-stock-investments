"""Lossless explicit-key literal streams over unchanged complete transport/11."""
from __future__ import annotations
import copy
import re
from underwriting_contract import digest, require
from underwriting_token_transport import KEYS, MAX_ENTRIES, MAX_DICTIONARY_TEXT
from underwriting_array_transport import ARRAY, _joined, _restore_members
from underwriting_front_array_transport import SCHEMA as INNER_SCHEMA, INSTRUCTIONS as INNER_INSTRUCTIONS
SCHEMA='underwriting-transport/12'
MARKER='|K|'
ESCAPE='~'
KEY_SET=frozenset(KEYS)
INSTRUCTIONS=(
 'The payload uses underwriting-transport/12 LOSSLESS storage. FIRST restore only '
 'encoded_envelope.encoded_envelope.literal_dictionary, a |K| string. Scan after |K|. '
 'Each unescaped character in the existing key alphabet (Unicode U+4E00 through U+9FFF, '
 'U+3400 through U+4DBF, or U+AC00 through U+C03F) starts a row and is its exact explicit lookup key. '
 'Every following character belongs literally to that row until the next unescaped key. '
 '~ escapes exactly the next ~ or key-alphabet character; preserve that escaped character as literal text. '
 'Keys occur explicitly in the stream: NEVER generate a key from a position, ordinal or Unicode number. '
 'Restore the ordered rows with that key followed by its complete literal value, including empty values. '
 'Re-encode those rows using the unchanged |A| joined-array rule (escape backslash and |). '
 'Keep every other field unchanged. The result is the exact complete transport/11 envelope; '
 'apply ALL following unchanged rules. No evidence is omitted.\n'+INNER_INSTRUCTIONS)

def _encode(rows):
 require(isinstance(rows,list) and 0<len(rows)<=MAX_ENTRIES,'Invalid explicit-key literal rows')
 parts=[];seen=set();total=0
 for row in rows:
  require(isinstance(row,str) and row and row[0] in KEY_SET and row[0] not in seen,'Invalid explicit literal key')
  seen.add(row[0]);total+=len(row);require(total<=MAX_DICTIONARY_TEXT,'Explicit-key literal text exceeds existing bound')
  parts.append(row[0]+''.join(ESCAPE+c if c==ESCAPE or c in KEY_SET else c for c in row[1:]))
 return MARKER+''.join(parts)

def _decode(value):
 require(isinstance(value,str) and value.startswith(MARKER),'Invalid explicit-key literal stream')
 text=value[len(MARKER):];require(len(text)<=MAX_DICTIONARY_TEXT,'Explicit-key encoded text exceeds existing bound')
 rows=[];part=[];seen=set();index=0;total=0
 while index<len(text):
  char=text[index]
  if char==ESCAPE:
   index+=1;require(index<len(text) and (text[index]==ESCAPE or text[index] in KEY_SET),'Invalid explicit-key literal escape')
   require(bool(part),'Literal text precedes its explicit key');part.append(text[index])
  elif char in KEY_SET:
   require(char not in seen,'Duplicate explicit literal key');seen.add(char)
   if part:rows.append(''.join(part))
   require(len(rows)<MAX_ENTRIES,'Explicit-key literal entry count exceeds existing bound');part=[char]
  else:
   require(bool(part),'Literal text precedes its explicit key');part.append(char)
  total+=1;require(total<=MAX_DICTIONARY_TEXT,'Explicit-key literal text exceeds existing bound');index+=1
 require(bool(part),'Empty explicit-key literal stream');rows.append(''.join(part))
 return rows

def compact(envelope):
 from underwriting_transport import encoded
 from underwriting_front_array_transport import unpack as unpack_inner
 require(isinstance(envelope,dict) and envelope.get('schema_version')==INNER_SCHEMA,'Literal streams require complete transport/11')
 original=unpack_inner(envelope);inner=envelope.get('encoded_envelope')
 require(isinstance(inner,dict),'Missing complete inner dictionary envelope')
 source=inner.get('literal_dictionary')
 if not isinstance(source,str) or not source.startswith(ARRAY):return None
 rows=_restore_members(source[len(ARRAY):]);stream=_encode(rows)
 if len(encoded(stream))>=len(encoded(source)):return None
 result={'schema_version':SCHEMA,'payload_hash':envelope['payload_hash'],'transport_hash':digest(envelope),'encoded_envelope':copy.deepcopy(envelope)}
 result['encoded_envelope']['encoded_envelope']['literal_dictionary']=stream
 require(_joined(_decode(stream))==source,'Literal stream changed original ordered rows')
 require(encoded(unpack(result))==encoded(original),'Literal stream changed original characters types or order')
 return result

def unpack(envelope):
 from underwriting_front_array_transport import unpack as unpack_inner
 require(isinstance(envelope,dict) and set(envelope)=={'schema_version','payload_hash','transport_hash','encoded_envelope'},'Invalid literal-stream envelope fields')
 require(envelope['schema_version']==SCHEMA and all(isinstance(envelope[k],str) and re.fullmatch(r'[0-9a-f]{64}',envelope[k]) for k in ('payload_hash','transport_hash')),'Invalid literal-stream identity')
 restored=copy.deepcopy(envelope['encoded_envelope'])
 require(isinstance(restored,dict) and restored.get('schema_version')==INNER_SCHEMA and restored.get('payload_hash')==envelope['payload_hash'],'Literal-stream inner identity changed')
 inner=restored.get('encoded_envelope');require(isinstance(inner,dict),'Missing literal-stream inner envelope')
 inner['literal_dictionary']=_joined(_decode(inner.get('literal_dictionary')))
 require(digest(restored)==envelope['transport_hash'],'Literal-stream complete envelope hash changed')
 return unpack_inner(restored)
