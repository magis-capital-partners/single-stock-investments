"""Bounded lossless token dictionaries for complete CPRT source evidence."""
from __future__ import annotations
import copy
import re
from collections import Counter
from functools import lru_cache
from underwriting_contract import digest, require

SCHEMA='underwriting-transport/5'
KEYS=''.join(chr(i) for start,end in ((0x4e00,0xa000),(0x3400,0x4dc0),(0xac00,0xd7a4)) for i in range(start,end))[:32768]
MAX_ENTRIES=32768
MAX_DEPTH=12
MAX_RESTORED=16_000_000
MAX_DICTIONARY_TEXT=64_000_000
INSTRUCTIONS=('The payload uses underwriting-transport/5 LOSSLESS token dictionaries. Every single-character key in literal_dictionary or derived_dictionary is an explicit lookup key; look up that exact character, never calculate an index. Literal dictionary values are exact literal source text. Expand derived_dictionary in written order, then $tokens objects. In these encoded values every dictionary key character refers to its exact dictionary entry; ~ escapes the next literal character, including ~~ for a literal ~. Every other character is literal. References only point backward; maximum depth is twelve. Then restore transport/2: @digits references the zero-based string_dictionary, @@ loses one leading @, $o stores [schema_index,values] zipped with object_schemas, and $text concatenates restored strings. All original source characters, types, order, financial values, dates, units, IDs and hashes are unchanged. Use original evidence IDs in your answer.\n')


def eligible(payload):
    packet=payload.get('packet') if isinstance(payload,dict) else None
    if not isinstance(packet,dict) or packet.get('ticker')!='CPRT':return False
    scope=(packet.get('primary_reference_usage') or {}).get('owner_authorized_scope') or {}
    return scope.get('parent')=='CPRT' and scope.get('target_cik')=='1637873' and scope.get('document_context_characters')==450000


def pack(payload):
    from underwriting_transport import _pack_dense, encoded, unpack as unpack_transport
    base=_pack_dense(payload,lambda text:[text]);texts=set()
    def collect(value):
        if isinstance(value,dict):
            require('$tokens' not in value,'Reserved token marker in original evidence')
            for item in value.values():collect(item)
        elif isinstance(value,list):
            for item in value:collect(item)
        elif isinstance(value,str) and len(value)>16:texts.add(value)
    def validate_source(value):
        if isinstance(value,dict):
            require('$tokens' not in value,'Reserved token marker in original evidence')
            for item in value.values():validate_source(item)
        elif isinstance(value,list):
            for item in value:validate_source(item)
    try:validate_source(payload);collect(base['payload']);collect(base['string_dictionary'])
    except ValueError:return None
    if not texts:return None
    tokens={s:re.findall(r'\S+\s*|\s+',s) for s in sorted(texts)}
    counts=Counter(word for words in tokens.values() for word in words)
    entries=sorted((word for word,n in counts.items() if n>=3),key=lambda word:(-counts[word]*max(1,len(word)-3),word))[:8192]
    indices={word:i for i,word in enumerate(entries)};depth=[0]*len(entries)
    streams={s:[indices.get(word,word) for word in words] for s,words in tokens.items()}
    for iteration in range(32):
        pairs=Counter()
        for stream in streams.values():
            pairs.update((a,b) for a,b in zip(stream,stream[1:]) if type(a) is int and type(b) is int and max(depth[a],depth[b])<4)
        ranked=sorted(((n*3-len(encoded([a,b]))-1,(a,b)) for (a,b),n in pairs.items() if n>=5),reverse=True)
        selected={pair:len(entries)+i for i,(gain,pair) in enumerate(ranked[:min(512,16384-len(entries))]) if gain>0}
        if not selected:break
        for (a,b),index in selected.items():
            require(index==len(entries),'Token dictionary ordering changed')
            entries.append([a,b]);depth.append(1+max(depth[a],depth[b]))
        for text,stream in list(streams.items()):
            out=[];i=0
            while i<len(stream):
                pair=(stream[i],stream[i+1]) if i+1<len(stream) and type(stream[i]) is int and type(stream[i+1]) is int else None
                if pair in selected:out.append(selected[pair]);i+=2
                else:out.append(stream[i]);i+=1
            streams[text]=out
    for iteration in range(24):
        runs=Counter()
        for stream in streams.values():
            for width in (8,16,32,64):
                runs.update(tuple(stream[i:i+width]) for i in range(len(stream)-width+1)
                    if max((depth[x] for x in stream[i:i+width] if type(x) is int),default=0)<MAX_DEPTH)
        ranked=[]
        for run,n in runs.items():
            if n<2:continue
            length=sum(3 if type(x) is int else len(x) for x in run)
            gain=n*(length-3)-(length+12)
            if gain>16:ranked.append((gain,repr(run),run))
        ranked.sort(reverse=True)
        selected={run:len(entries)+i for i,(_,__,run) in enumerate(ranked[:min(2048,65536-len(entries))])}
        if not selected:break
        for run,index in selected.items():
            require(index==len(entries),'Token dictionary ordering changed')
            entries.append(list(run));depth.append(1+max((depth[x] for x in run if type(x) is int),default=0))
        for text,stream in list(streams.items()):
            out=[];i=0
            while i<len(stream):
                candidate=next((selected.get(tuple(stream[i:i+w])) for w in (64,32,16,8) if i+w<=len(stream) and tuple(stream[i:i+w]) in selected),None)
                if candidate is not None:out.append(candidate);i+=len(entries[candidate])
                else:out.append(stream[i]);i+=1
            streams[text]=out
    literal_count=next((i for i,x in enumerate(entries) if isinstance(x,list)),len(entries))
    nodes=[[entry] if isinstance(entry,str) else entry for entry in entries];used=set()
    def visit(index):
        if index in used:return
        used.add(index)
        for child in nodes[index]:
            if type(child) is int:visit(child)
    for stream in streams.values():
        for child in stream:
            if type(child) is int:visit(child)
    uses=Counter(child for stream in streams.values() for child in stream if type(child) is int)
    for index in used:uses.update(child for child in nodes[index] if type(child) is int)
    remove={i for i in used if uses[i]<=1}
    @lru_cache(None)
    def flatten(index):
        out=[]
        for child in nodes[index]:
            if type(child) is int and child in remove:out.extend(flatten(child))
            else:out.append(child)
        return tuple(out)
    # Remove definitions whose exact key/definition overhead exceeds their reuse.
    # This changes storage only: every removed definition is inlined verbatim.
    for iteration in range(20):
        flatten.cache_clear();reachable=set()
        def visit_remaining(index):
            if index in remove:
                for child in flatten(index):
                    if type(child) is int:visit_remaining(child)
                return
            if index in reachable:return
            reachable.add(index)
            for child in flatten(index):
                if type(child) is int:visit_remaining(child)
        for stream in streams.values():
            for child in stream:
                if type(child) is int:visit_remaining(child)
        references=Counter()
        def count_remaining(atoms):
            for child in atoms:
                for item in (flatten(child) if type(child) is int and child in remove else [child]):
                    if type(item) is int:references[item]+=1
        for stream in streams.values():count_remaining(stream)
        for index in reachable:count_remaining(flatten(index))
        discarded=set()
        for index in reachable:
            inline=''.join(KEYS[0] if type(child) is int else child.replace('~','~~') for child in flatten(index))
            length=len(encoded(inline))-2
            if references[index]*(length-1)-(length+7)<=0:discarded.add(index)
        if not discarded:break
        remove.update(discarded)
    flatten.cache_clear()
    keep=sorted(reachable-remove)
    if not keep or len(keep)>MAX_ENTRIES:return None
    codes={old:KEYS[i] for i,old in enumerate(keep)}
    active=set(codes.values())
    def literal(text):return ''.join('~'+c if c=='~' or c in active else c for c in text)
    def render(atoms):
        out=[]
        for child in atoms:
            parts=flatten(child) if type(child) is int and child in remove else [child]
            out.extend(codes[x] if type(x) is int else literal(x) for x in parts)
        return ''.join(out)
    literals={codes[i]:entries[i] for i in keep if i<literal_count}
    derived={codes[i]:render(flatten(i)) for i in keep if i>=literal_count}
    def transform(value):
        if isinstance(value,dict):return {key:transform(item) for key,item in value.items()}
        if isinstance(value,list):return [transform(item) for item in value]
        if isinstance(value,str) and value in streams:return {'$tokens':render(streams[value])}
        return value
    envelope={**base,'schema_version':SCHEMA,'payload':transform(base['payload']),
        'string_dictionary':transform(base['string_dictionary']),'literal_dictionary':literals,
        'derived_dictionary':derived,'maximum_dag_depth':MAX_DEPTH,'literal_escape':'~'}
    require(encoded(unpack_transport(envelope))==encoded(payload),'Token transport changed source characters, types or order')
    return envelope


def unpack(envelope):
    from underwriting_transport import unpack as unpack_transport, encoded
    require(set(envelope)=={'schema_version','payload_hash','payload','object_schemas','string_dictionary','literal_dictionary','derived_dictionary','maximum_dag_depth','literal_escape'},'Invalid token envelope fields')
    require(envelope.get('literal_escape')=='~' and envelope.get('schema_version')==SCHEMA and type(envelope['maximum_dag_depth']) is int and envelope['maximum_dag_depth']==MAX_DEPTH,'Invalid token depth limit')
    literals,derived=envelope['literal_dictionary'],envelope['derived_dictionary']
    require(isinstance(literals,dict) and isinstance(derived,dict) and not set(literals)&set(derived),'Invalid token dictionaries')
    keys=list(literals)+list(derived)
    require(0<len(keys)<=MAX_ENTRIES and keys==list(KEYS[:len(keys)]),'Invalid token key order or identity')
    require(all(isinstance(text,str) for text in list(literals.values())+list(derived.values())),'Invalid token dictionary value')
    active=set(keys);expanded={};depth={};edges={};total=0
    def decode(text,known):
        require(isinstance(text,str),'Invalid token source text')
        out=[];refs=set();size=0;i=0
        while i<len(text):
            c=text[i]
            if c=='~':
                require(i+1<len(text) and (text[i+1]=='~' or text[i+1] in active),'Invalid literal token escape')
                piece=text[i+1];i+=2
            elif c in active:
                require(c in known,'Unknown, forward or cyclic token reference')
                refs.add(c);piece=known[c];i+=1
            else:piece=c;i+=1
            size+=len(piece);require(size<=MAX_RESTORED,'Token expansion exceeds bounded source size');out.append(piece)
        return ''.join(out),refs
    for key,text in literals.items():
        require(len(text)<=MAX_RESTORED,'Literal token exceeds bounded source size')
        expanded[key]=text;depth[key]=0;edges[key]=set();total+=len(text)
    require(total<=MAX_DICTIONARY_TEXT,'Token dictionary expansion exceeds bound')
    for key,text in derived.items():
        value,refs=decode(text,expanded)
        current=1+max((depth[k] for k in refs),default=0)
        require(current<=MAX_DEPTH,'Token dictionary nesting exceeds bound')
        total+=len(value);require(total<=MAX_DICTIONARY_TEXT,'Token dictionary expansion exceeds bound')
        expanded[key]=value;depth[key]=current;edges[key]=refs
    used=set()
    def restore(value):
        if isinstance(value,dict):
            if '$tokens' in value:
                require(set(value)=={'$tokens'},'Ambiguous token source object')
                result,refs=decode(value['$tokens'],expanded);used.update(refs);return result
            return {key:restore(item) for key,item in value.items()}
        if isinstance(value,list):return [restore(item) for item in value]
        return copy.deepcopy(value)
    base={'schema_version':'underwriting-transport/2','payload_hash':envelope['payload_hash'],
        'payload':restore(envelope['payload']),'object_schemas':copy.deepcopy(envelope['object_schemas']),
        'string_dictionary':restore(envelope['string_dictionary'])}
    pending=list(used)
    while pending:
        for child in edges[pending.pop()]:
            if child not in used:used.add(child);pending.append(child)
    require(used==set(keys),'Unused token dictionary entries')
    result=unpack_transport(base)
    require(len(encoded(result))<=MAX_RESTORED,'Restored token payload exceeds bound')
    return result
