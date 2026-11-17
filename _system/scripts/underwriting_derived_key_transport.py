"""Lossless explicit derived-key streams over unchanged complete transport/12."""
from __future__ import annotations
import copy
import re
from underwriting_contract import require
from underwriting_token_transport import KEYS, MAX_ENTRIES, MAX_DICTIONARY_TEXT
from underwriting_array_transport import ARRAY, _joined, _restore_members
from underwriting_literal_key_transport import SCHEMA as INNER_SCHEMA, INSTRUCTIONS as INNER_INSTRUCTIONS, _decode as literal_rows
SCHEMA='underwriting-transport/13'
MARKER='|D|'
KEY_SET=frozenset(KEYS)
INSTRUCTIONS=(
 'The payload uses underwriting-transport/13 LOSSLESS storage. FIRST restore only '
 'encoded_envelope.encoded_envelope.derived_dictionary from its |D| stream. '
 'Obtain the already-defined explicit keys from the literal |K| stream using the following transport/12 rule. '
 'Scan the derived stream in order. An unescaped key-alphabet character not previously defined starts '
 'the next row and is its exact explicit key; earlier defined key characters inside a row remain references. '
 'A completed row defines its key for later rows. Preserve the original ~ escape and its following ~ or key '
 'as two unchanged characters. The outer escape ~| followed by one inactive key-alphabet character '
 'restores only that character literally; that glyph must never be an actual dictionary key. '
 'Retain every other character, including backslashes and |. Restore ordered key-plus-value rows, '
 'then re-encode them with the unchanged |A| joined-array rule. NEVER generate keys from ordinals. '
 'Change only the outer schema version to transport/12 and apply all following unchanged rules.\n'+INNER_INSTRUCTIONS)

def _encode(rows,literal_keys):
 require(isinstance(rows,list) and rows and all(isinstance(x,str) and x for x in rows),'Invalid derived rows')
 keys=list(literal_keys)+[x[0] for x in rows]
 require(len(keys)<=MAX_ENTRIES and len(set(keys))==len(keys) and all(k in KEY_SET for k in keys),'Invalid explicit derived keys')
 active=set(keys);out=[];total=0
 for row in rows:
  out.append(row[0]);value=row[1:];index=0;total+=len(row)
  require(total<=MAX_DICTIONARY_TEXT,'Derived stream exceeds existing text bound')
  while index<len(value):
   char=value[index]
   if char=='~':
    require(index+1<len(value) and (value[index+1]=='~' or value[index+1] in active),'Invalid original derived escape')
    out.append(value[index:index+2]);index+=2;continue
   out.append('~|'+char if char in KEY_SET and char not in active else char);index+=1
 return MARKER+''.join(out)

def _decode(value,literal_keys):
 require(isinstance(value,str) and value.startswith(MARKER),'Invalid derived stream')
 text=value[len(MARKER):];require(len(text)<=MAX_DICTIONARY_TEXT,'Derived encoded stream exceeds existing text bound')
 require(isinstance(literal_keys,(list,tuple)) and 0<len(literal_keys)<=MAX_ENTRIES and all(isinstance(k,str) and len(k)==1 and k in KEY_SET for k in literal_keys) and len(set(literal_keys))==len(literal_keys),'Invalid existing explicit literal keys')
 defined=set(literal_keys);seen=set(defined);rows=[];part=[];current=None;inactive=set();index=0;total=0
 while index<len(text):
  char=text[index]
  if char=='~':
   require(bool(part) and index+1<len(text),'Invalid derived stream escape')
   if text[index+1]=='|':
    require(index+2<len(text) and text[index+2] in KEY_SET,'Invalid inactive derived glyph')
    part.append(text[index+2]);inactive.add(text[index+2]);index+=3;total+=1
   else:
    require(text[index+1]=='~' or text[index+1] in KEY_SET,'Invalid original derived escape')
    part.append(text[index:index+2]);index+=2;total+=2
  elif char in KEY_SET and char not in defined:
   require(char not in seen,'Duplicate or cyclic explicit derived key')
   if part:rows.append(''.join(part));defined.add(current)
   require(len(seen)<MAX_ENTRIES,'Derived stream entry count exceeds existing bound');seen.add(char);part=[char];current=char;index+=1;total+=1
  else:
   require(bool(part),'Derived text precedes its explicit key');part.append(char);index+=1;total+=1
  require(total<=MAX_DICTIONARY_TEXT,'Derived decoded stream exceeds existing text bound')
 require(bool(part),'Empty derived stream');rows.append(''.join(part));defined.add(current)
 require(not inactive.intersection(defined),'Inactive escape hides an actual dictionary key')
 return rows

def compact(envelope):
 from underwriting_transport import encoded
 from underwriting_literal_key_transport import unpack as unpack_inner
 require(isinstance(envelope,dict) and envelope.get('schema_version')==INNER_SCHEMA,'Derived streams require complete transport/12')
 original=unpack_inner(envelope);leaf=envelope['encoded_envelope']['encoded_envelope'];source=leaf.get('derived_dictionary')
 if not isinstance(source,str) or not source.startswith(ARRAY):return None
 rows=_restore_members(source[len(ARRAY):])
 if not rows or any(not x for x in rows):return None
 keys=[row[0] for row in literal_rows(leaf.get('literal_dictionary'))];stream=_encode(rows,keys)
 if len(encoded(stream))>=len(encoded(source)):return None
 result=copy.deepcopy(envelope);result['schema_version']=SCHEMA;result['encoded_envelope']['encoded_envelope']['derived_dictionary']=stream
 require(_joined(_decode(stream,keys))==source,'Derived stream changed original ordered definitions')
 require(encoded(unpack(result))==encoded(original),'Derived stream changed original characters types or order')
 return result

def unpack(envelope):
 from underwriting_literal_key_transport import unpack as unpack_inner
 require(isinstance(envelope,dict) and set(envelope)=={'schema_version','payload_hash','transport_hash','encoded_envelope'},'Invalid derived-stream fields')
 require(envelope['schema_version']==SCHEMA and all(isinstance(envelope[k],str) and re.fullmatch(r'[0-9a-f]{64}',envelope[k]) for k in ('payload_hash','transport_hash')),'Invalid derived-stream identity')
 restored=copy.deepcopy(envelope);restored['schema_version']=INNER_SCHEMA
 frame=restored.get('encoded_envelope');require(isinstance(frame,dict),'Invalid derived inner envelope')
 leaf=frame.get('encoded_envelope');require(isinstance(leaf,dict),'Missing derived inner dictionaries')
 keys=[row[0] for row in literal_rows(leaf.get('literal_dictionary'))]
 leaf['derived_dictionary']=_joined(_decode(leaf.get('derived_dictionary'),keys))
 return unpack_inner(restored)
