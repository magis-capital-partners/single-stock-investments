"""Lossless prefix-coded string arrays over the unchanged transport/9 envelope."""
from __future__ import annotations
import bisect
import copy
import re
from underwriting_contract import digest, require
from underwriting_dictionary_transport import SCHEMA as INNER_SCHEMA, INSTRUCTIONS as INNER_INSTRUCTIONS
from underwriting_token_transport import MAX_ENTRIES, MAX_DICTIONARY_TEXT
from underwriting_compact_transport import MAX_CONTAINER_DEPTH
from underwriting_array_transport import ARRAY, LITERAL, _joined, _restore_members
SCHEMA='underwriting-transport/11'
FRONT='|F|'
INSTRUCTIONS=(
 'The payload uses underwriting-transport/11 LOSSLESS storage, not a summary. '
 'FIRST restore encoded_envelope values recursively, keeping object keys unchanged. '
 'A string beginning |S| restores to its exact remaining string without further decoding. '
 'A string beginning |A| restores its ordered string members: split only at unescaped |, '
 'decoding ONLY backslash-backslash to one backslash and backslash-| to one literal |; keep empty members. '
 'A string beginning |F| first splits and unescapes members by those same rules. '
 'Decode these records in order: Ltext means the literal text after L; '
 'pN:text means the first N Unicode characters of the immediately preceding decoded member plus literal text; '
 'PI,N:text means the first N Unicode characters of earlier decoded member I, using zero-based indices, plus literal text. '
 'The first member must be literal. Do not decode restored members again. '
 'In an ordinary array, an initial negative integer I restores the one-key ! object with value [-I-1,remaining array members]. An initial !L strips only that marker and restores a literal array. Restore member values recursively; do not reinterpret restored containers. Every other string and primitive stays unchanged. '
 'Then apply ALL following unchanged transport/9 rules to the restored inner envelope. '
 'All original characters, types, order, IDs, hashes and evidence remain unchanged.\n'+INNER_INSTRUCTIONS)

def _common(left,right):
 n=0
 while n<min(len(left),len(right)) and left[n]==right[n]:n+=1
 return n

def _front_join(values):
 from underwriting_transport import encoded
 ordered=[];first={};records=[]
 def cost(record):return len(encoded(_joined([record])))
 for index,value in enumerate(values):
  best='L'+value;best_cost=cost(best)
  position=bisect.bisect_left(ordered,value);candidates=set()
  if index:candidates.add(index-1)
  for neighbor in (position-1,position):
   if 0<=neighbor<len(ordered):candidates.add(first[ordered[neighbor]])
  for previous in sorted(candidates):
   n=_common(values[previous],value)
   if not n:continue
   record=('p'+str(n) if previous==index-1 else 'P'+str(previous)+','+str(n))+':'+value[n:]
   size=cost(record)
   if size<best_cost:best,best_cost=record,size
  records.append(best)
  if value not in first:first[value]=index;ordered.insert(position,value)
 return FRONT+_joined(records)[len(ARRAY):]

def _number(text,maximum):
 require(isinstance(text,str) and len(text)<=len(str(maximum)) and re.fullmatch(r'0|[1-9][0-9]*',text) is not None,'Invalid prefix-array integer')
 value=int(text);require(value<=maximum,'Prefix-array integer exceeds existing bound');return value

def _front_members(text,remaining=MAX_DICTIONARY_TEXT):
 result=[];total=0
 for record in _restore_members(text):
  require(isinstance(record,str) and record,'Invalid prefix-array record')
  if record[0]=='L':
   value=record[1:];require(len(value)<=remaining-total,'Prefix-array expansion exceeds existing text bound')
  else:
   require(record[0] in ('p','P') and ':' in record,'Unknown prefix-array record')
   header,tail=record[1:].split(':',1)
   if record[0]=='p':
    require(bool(result),'Prefix-array previous member is missing');index=len(result)-1;n=_number(header,MAX_DICTIONARY_TEXT)
   else:
    require(header.count(',')==1,'Invalid prefix-array reference');idx,count=header.split(',');index=_number(idx,MAX_ENTRIES-1);n=_number(count,MAX_DICTIONARY_TEXT)
   require(index<len(result) and n<=len(result[index]),'Prefix-array reference is missing, forward or out of range')
   require(n+len(tail)<=remaining-total,'Prefix-array expansion exceeds existing text bound');value=result[index][:n]+tail
  total+=len(value);result.append(value);require(len(result)<=MAX_ENTRIES,'Prefix-array exceeds existing entry bound')
 return result

def _restore(value,budget=None,depth=0):
 require(depth<=MAX_CONTAINER_DEPTH,'Prefix-array container depth exceeds existing bound')
 if budget is None:budget=[0]
 def consume(text):
  budget[0]+=len(text);require(budget[0]<=MAX_DICTIONARY_TEXT,'Prefix-array expansion exceeds existing text bound');return text
 if isinstance(value,dict):return {key:_restore(item,budget,depth+1) for key,item in value.items()}
 if isinstance(value,list):
  if value and type(value[0]) is int and value[0]<0:
   require(-MAX_ENTRIES<=value[0]<=-1,'Schema-row index exceeds existing bound')
   return {'!':[-value[0]-1,[_restore(item,budget,depth+1) for item in value[1:]]]}
  if value and isinstance(value[0],str) and value[0]=='!L':return [_restore(item,budget,depth+1) for item in value[1:]]
  return [_restore(item,budget,depth+1) for item in value]
 if isinstance(value,str):
  if value.startswith('|'):
   if value.startswith(LITERAL):
    original=value[len(LITERAL):];require(original.startswith('|'),'Invalid prefix-array literal escape');return consume(original)
   if value.startswith(ARRAY):members=_restore_members(value[len(ARRAY):])
   else:
    require(value.startswith(FRONT),'Unknown prefix-array marker');members=_front_members(value[len(FRONT):],MAX_DICTIONARY_TEXT-budget[0])
   return [consume(member) for member in members]
  return consume(value)
 return copy.deepcopy(value)

def compact(envelope):
 from underwriting_transport import encoded
 from underwriting_dictionary_transport import unpack as unpack_inner
 require(isinstance(envelope,dict) and envelope.get('schema_version')==INNER_SCHEMA,'Prefix arrays require the complete transport/9 envelope')
 original=unpack_inner(envelope)
 def pack(value,depth=0):
  require(depth<=MAX_CONTAINER_DEPTH,'Prefix-array container depth exceeds existing bound')
  if isinstance(value,dict):
   if set(value)=={'!'}:
    row=value['!']
    if isinstance(row,list) and len(row)==2 and type(row[0]) is int and 0<=row[0]<MAX_ENTRIES and isinstance(row[1],list):
     return [-row[0]-1]+[pack(item,depth+1) for item in row[1]]
   return {key:pack(item,depth+1) for key,item in value.items()}
  if isinstance(value,list):
   if value and len(value)<=MAX_ENTRIES and all(type(item) is str for item in value):
    candidates=[value,_joined(value),_front_join(value)];best=min(candidates,key=lambda v:len(encoded(v)))
    if isinstance(best,str):return best
   converted=[pack(item,depth+1) for item in value]
   if value and ((type(value[0]) is int and value[0]<0) or value[0]=='!L'):return ['!L']+converted
   return converted
  if isinstance(value,str) and value.startswith('|'):return LITERAL+value
  return copy.deepcopy(value)
 result={'schema_version':SCHEMA,'payload_hash':envelope['payload_hash'],'transport_hash':digest(envelope),'encoded_envelope':pack(envelope)}
 require(encoded(_restore(result['encoded_envelope']))==encoded(envelope),'Prefix arrays changed the complete inner envelope')
 require(encoded(unpack(result))==encoded(original),'Prefix arrays changed original characters, types or order')
 return result

def unpack(envelope):
 from underwriting_dictionary_transport import unpack as unpack_inner
 require(isinstance(envelope,dict) and set(envelope)=={'schema_version','payload_hash','transport_hash','encoded_envelope'},'Invalid prefix-array envelope fields')
 require(envelope['schema_version']==SCHEMA and all(isinstance(envelope[key],str) and re.fullmatch(r'[0-9a-f]{64}',envelope[key]) for key in ('payload_hash','transport_hash')),'Invalid prefix-array identity')
 require(isinstance(envelope['encoded_envelope'],dict),'Invalid prefix-array inner envelope');restored=_restore(envelope['encoded_envelope'])
 require(restored.get('schema_version')==INNER_SCHEMA and restored.get('payload_hash')==envelope['payload_hash'] and digest(restored)==envelope['transport_hash'],'Prefix-array inner identity changed')
 return unpack_inner(restored)
